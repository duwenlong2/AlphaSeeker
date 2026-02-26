from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ScoreWeights:
    valuation: float = 0.30
    quality: float = 0.25
    catalyst: float = 0.25
    trend: float = 0.20


@dataclass(slots=True)
class Thresholds:
    min_price: float = 2.0
    min_roe: float = 3.0
    max_pe: float = 80.0
    max_risk_penalty: float = 30.0
    min_total_score: float = 55.0
    max_20d_chg_for_entry: float = 35.0


@dataclass(slots=True)
class PortfolioPolicy:
    cash_buffer_ratio: float = 0.20
    max_positions: int = 5
    max_position_ratio: float = 0.20
    stop_loss_ratio: float = 0.08
    take_profit_ratio: float = 0.18
    trailing_stop_ratio: float = 0.08


@dataclass(slots=True)
class NewsPolicy:
    keyword_weight_base: float = 0.40
    structured_weight_base: float = 0.60
    structured_weight_step: float = 0.05
    structured_weight_max: float = 0.80
    event_impact_scale: float = 18.0
    event_half_life_hours: float = 36.0


@dataclass(slots=True)
class AppConfig:
    weights: ScoreWeights = field(default_factory=ScoreWeights)
    thresholds: Thresholds = field(default_factory=Thresholds)
    portfolio: PortfolioPolicy = field(default_factory=PortfolioPolicy)
    news: NewsPolicy = field(default_factory=NewsPolicy)
