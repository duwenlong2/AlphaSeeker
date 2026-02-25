from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class StockSnapshot:
    symbol: str
    name: str
    price: float
    pe_ttm: float | None
    pb: float | None
    roe: float | None
    revenue_yoy: float | None
    pct_chg_20d: float | None
    volume_ratio: float | None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class NewsItem:
    symbol: str
    title: str
    source: str
    published_at: datetime


@dataclass(slots=True)
class Recommendation:
    symbol: str
    name: str
    total_score: float
    valuation_score: float
    quality_score: float
    catalyst_score: float
    trend_score: float
    risk_penalty: float
    reason: str
    risk_note: str
    generated_at: datetime = field(default_factory=datetime.utcnow)
