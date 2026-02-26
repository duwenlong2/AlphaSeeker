from __future__ import annotations

from collections import defaultdict

from alphaseeker.config import AppConfig
from alphaseeker.models import NewsItem, Recommendation, StockSnapshot
from alphaseeker.skills.news_analysis import build_symbol_news_signals
from alphaseeker.skills.scoring import (
    catalyst_scores,
    market_regime_signal,
    quality_score,
    risk_penalty,
    trend_score,
    valuation_score,
)


def rank_stocks(
    snapshots: list[StockSnapshot],
    news: list[NewsItem],
    config: AppConfig,
    topn: int,
) -> list[Recommendation]:
    news_map: dict[str, list[NewsItem]] = defaultdict(list)
    for n in news:
        news_map[n.symbol].append(n)

    cata_map = catalyst_scores(news)
    news_signals = build_symbol_news_signals(
        news,
        impact_scale=config.news.event_impact_scale,
        half_life_hours=config.news.event_half_life_hours,
    )
    regime_adjustment, regime_note = market_regime_signal(snapshots)
    recs: list[Recommendation] = []

    for s in snapshots:
        v = valuation_score(s)
        q = quality_score(s)
        c_raw = cata_map.get(s.symbol, 50.0)
        news_sig = news_signals.get(s.symbol)
        news_score = news_sig.score if news_sig else 50.0
        event_count = news_sig.event_count if news_sig else 0
        structured_weight = min(
            config.news.structured_weight_max,
            config.news.structured_weight_base + event_count * config.news.structured_weight_step,
        )
        keyword_weight = max(0.0, 1.0 - structured_weight)
        if event_count == 0:
            structured_weight = config.news.structured_weight_base
            keyword_weight = config.news.keyword_weight_base
        c = round(c_raw * keyword_weight + news_score * structured_weight, 2)
        t = trend_score(s)
        rp, risk_note = risk_penalty(s, news_map.get(s.symbol, []))

        w = config.weights
        total = v * w.valuation + q * w.quality + c * w.catalyst + t * w.trend - rp + regime_adjustment

        if rp > config.thresholds.max_risk_penalty:
            continue

        if total < config.thresholds.min_total_score:
            continue

        if s.pct_chg_20d is not None and s.pct_chg_20d > config.thresholds.max_20d_chg_for_entry:
            continue

        reason = (
            f"估值{v} 质量{q} 催化{c} 趋势{t} 新闻{news_score}"
            f" 融合(k{round(keyword_weight, 2)}/n{round(structured_weight, 2)})"
            f" 市场{regime_note}{regime_adjustment:+.1f}"
        )
        recs.append(
            Recommendation(
                symbol=s.symbol,
                name=s.name,
                total_score=round(total, 2),
                valuation_score=v,
                quality_score=q,
                catalyst_score=c,
                trend_score=t,
                risk_penalty=rp,
                entry_price=s.price,
                reason=reason,
                risk_note=risk_note,
                regime_adjustment=regime_adjustment,
                news_score=news_score,
                news_event_count=news_sig.event_count if news_sig else 0,
                news_summary=news_sig.summary if news_sig else "无有效新闻事件",
            )
        )

    recs.sort(key=lambda x: x.total_score, reverse=True)
    return recs[:topn]
