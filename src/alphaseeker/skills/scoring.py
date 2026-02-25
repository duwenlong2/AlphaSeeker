from __future__ import annotations

from collections import defaultdict

from alphaseeker.models import NewsItem, StockSnapshot


def _clamp(v: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, v))


def valuation_score(s: StockSnapshot) -> float:
    # PE 越低越好，但过低可能有陷阱，这里先做简化
    pe_part = 70.0 if s.pe_ttm is None else _clamp(100 - s.pe_ttm)
    pb_part = 70.0 if s.pb is None else _clamp(100 - s.pb * 25)
    return round(pe_part * 0.6 + pb_part * 0.4, 2)


def quality_score(s: StockSnapshot) -> float:
    roe_part = 50.0 if s.roe is None else _clamp(s.roe * 4)
    rev_part = 50.0 if s.revenue_yoy is None else _clamp(50 + s.revenue_yoy * 2)
    return round(roe_part * 0.6 + rev_part * 0.4, 2)


def trend_score(s: StockSnapshot) -> float:
    chg = 0.0 if s.pct_chg_20d is None else s.pct_chg_20d
    vol = 1.0 if s.volume_ratio is None else s.volume_ratio
    return round(_clamp(50 + chg * 3 + (vol - 1) * 15), 2)


def catalyst_scores(news: list[NewsItem]) -> dict[str, float]:
    positive = ["中标", "回购", "增长", "业绩预增", "新产品", "政策支持"]
    negative = ["减持", "诉讼", "亏损", "处罚", "退市", "违约"]

    scores = defaultdict(lambda: 50.0)
    for n in news:
        score = scores[n.symbol]
        for kw in positive:
            if kw in n.title:
                score += 12
        for kw in negative:
            if kw in n.title:
                score -= 18
        scores[n.symbol] = _clamp(score)
    return {k: round(v, 2) for k, v in scores.items()}


def risk_penalty(s: StockSnapshot, symbol_news: list[NewsItem]) -> tuple[float, str]:
    p = 0.0
    notes: list[str] = []

    if s.price < 2:
        p += 15
        notes.append("低价波动风险")
    if s.pe_ttm is not None and s.pe_ttm > 80:
        p += 15
        notes.append("估值偏高")
    if s.roe is not None and s.roe < 3:
        p += 20
        notes.append("盈利质量偏弱")

    risky_words = ["减持", "诉讼", "处罚", "退市", "违约"]
    for n in symbol_news:
        if any(w in n.title for w in risky_words):
            p += 20
            notes.append("负面新闻催化")
            break

    if not notes:
        notes.append("无显著风险")
    return round(min(100.0, p), 2), "、".join(notes)
