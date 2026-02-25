from __future__ import annotations

from collections import defaultdict

from alphaseeker.config import AppConfig
from alphaseeker.models import NewsItem, Recommendation, StockSnapshot
from alphaseeker.skills.scoring import (
    catalyst_scores,
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
    recs: list[Recommendation] = []

    for s in snapshots:
        v = valuation_score(s)
        q = quality_score(s)
        c = cata_map.get(s.symbol, 50.0)
        t = trend_score(s)
        rp, risk_note = risk_penalty(s, news_map.get(s.symbol, []))

        w = config.weights
        total = v * w.valuation + q * w.quality + c * w.catalyst + t * w.trend - rp

        if rp > config.thresholds.max_risk_penalty:
            continue

        reason = f"估值{v} 质量{q} 催化{c} 趋势{t}"
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
                reason=reason,
                risk_note=risk_note,
            )
        )

    recs.sort(key=lambda x: x.total_score, reverse=True)
    return recs[:topn]
