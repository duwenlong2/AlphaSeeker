from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from math import exp

from alphaseeker.models import NewsItem


@dataclass(slots=True)
class NewsEvent:
    symbol: str
    title: str
    event_type: str
    sentiment: str
    confidence: float
    decay_weight: float
    source: str
    published_at: datetime


@dataclass(slots=True)
class SymbolNewsSignal:
    symbol: str
    score: float
    event_count: int
    positive_count: int
    negative_count: int
    summary: str


EVENT_DISPLAY_NAME: dict[str, str] = {
    "earnings_growth": "业绩增长",
    "new_order": "新增订单",
    "buyback": "回购增持",
    "innovation": "创新突破",
    "policy_support": "政策支持",
    "shareholder_reduction": "股东减持",
    "earnings_drop": "业绩下滑",
    "compliance_risk": "合规风险",
    "delist_or_default": "退市违约",
    "neutral": "中性信息",
}

EVENT_IMPACT_MULTIPLIER: dict[str, float] = {
    "earnings_growth": 1.1,
    "new_order": 1.0,
    "buyback": 1.0,
    "innovation": 0.9,
    "policy_support": 0.85,
    "shareholder_reduction": 1.05,
    "earnings_drop": 1.1,
    "compliance_risk": 1.15,
    "delist_or_default": 1.25,
    "neutral": 0.4,
}


POSITIVE_RULES: list[tuple[str, str, float]] = [
    ("业绩预增|净利增长|利润增长", "earnings_growth", 1.0),
    ("中标|订单|签约", "new_order", 0.8),
    ("回购|增持", "buyback", 0.9),
    ("新品|新产品|技术突破", "innovation", 0.7),
    ("政策支持|补贴|放开", "policy_support", 0.7),
]

NEGATIVE_RULES: list[tuple[str, str, float]] = [
    ("减持|清仓", "shareholder_reduction", 1.0),
    ("亏损|预亏|下滑", "earnings_drop", 1.0),
    ("诉讼|处罚|调查", "compliance_risk", 0.9),
    ("退市|违约|暴雷", "delist_or_default", 1.1),
]

SOURCE_WEIGHT: dict[str, float] = {
    "akshare": 0.9,
    "mock": 0.6,
    "unknown": 0.5,
}


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _norm_title(title: str) -> str:
    cleaned = re.sub(r"\s+", "", title.lower())
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]", "", cleaned)
    return cleaned


def deduplicate_news(news: list[NewsItem]) -> list[NewsItem]:
    seen: set[tuple[str, str]] = set()
    out: list[NewsItem] = []
    for item in news:
        key = (item.symbol, _norm_title(item.title))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _classify_title(title: str) -> tuple[str, str, float]:
    for pattern, event_type, w in NEGATIVE_RULES:
        if re.search(pattern, title):
            return event_type, "negative", w
    for pattern, event_type, w in POSITIVE_RULES:
        if re.search(pattern, title):
            return event_type, "positive", w
    return "neutral", "neutral", 0.2


def _source_confidence(source: str) -> float:
    return SOURCE_WEIGHT.get(source, SOURCE_WEIGHT["unknown"])


def _time_decay_weight(published_at: datetime, half_life_hours: float = 36.0) -> float:
    now = datetime.now(timezone.utc)
    age_hours = max(0.0, (now - _to_utc(published_at)).total_seconds() / 3600)
    lam = 0.69314718056 / half_life_hours
    return max(0.05, exp(-lam * age_hours))


def extract_news_events(news: list[NewsItem], half_life_hours: float = 36.0) -> list[NewsEvent]:
    deduped = deduplicate_news(news)
    out: list[NewsEvent] = []

    for item in deduped:
        event_type, sentiment, strength = _classify_title(item.title)
        confidence = min(1.0, max(0.1, strength * _source_confidence(item.source)))
        decay_weight = _time_decay_weight(item.published_at, half_life_hours=half_life_hours)

        out.append(
            NewsEvent(
                symbol=item.symbol,
                title=item.title,
                event_type=event_type,
                sentiment=sentiment,
                confidence=round(confidence, 4),
                decay_weight=round(decay_weight, 4),
                source=item.source,
                published_at=item.published_at,
            )
        )

    return out


def build_symbol_news_signals(
    news: list[NewsItem],
    impact_scale: float = 18.0,
    half_life_hours: float = 36.0,
) -> dict[str, SymbolNewsSignal]:
    events = extract_news_events(news, half_life_hours=half_life_hours)
    symbol_map: dict[str, list[NewsEvent]] = {}
    for e in events:
        symbol_map.setdefault(e.symbol, []).append(e)

    signals: dict[str, SymbolNewsSignal] = {}
    for symbol, evs in symbol_map.items():
        score = 50.0
        pos = 0
        neg = 0
        tags: list[str] = []

        for e in evs:
            event_boost = EVENT_IMPACT_MULTIPLIER.get(e.event_type, 1.0)
            impact = impact_scale * e.confidence * e.decay_weight * event_boost
            event_name = EVENT_DISPLAY_NAME.get(e.event_type, e.event_type)
            if e.sentiment == "positive":
                score += impact
                pos += 1
                tags.append(f"+{event_name}")
            elif e.sentiment == "negative":
                score -= impact
                neg += 1
                tags.append(f"-{event_name}")
            else:
                tags.append(event_name)

        score = max(0.0, min(100.0, score))
        summary = "、".join(tags[:4]) if tags else "无有效新闻事件"

        signals[symbol] = SymbolNewsSignal(
            symbol=symbol,
            score=round(score, 2),
            event_count=len(evs),
            positive_count=pos,
            negative_count=neg,
            summary=summary,
        )

    return signals
