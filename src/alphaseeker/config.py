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


@dataclass(slots=True)
class AppConfig:
    weights: ScoreWeights = field(default_factory=ScoreWeights)
    thresholds: Thresholds = field(default_factory=Thresholds)
