from __future__ import annotations

from alphaseeker.config import AppConfig
from alphaseeker.models import Recommendation


def assign_target_weights(recs: list[Recommendation], config: AppConfig) -> list[Recommendation]:
    if not recs:
        return recs

    max_positions = max(1, config.portfolio.max_positions)
    selected = recs[:max_positions]

    investable_ratio = 1.0 - config.portfolio.cash_buffer_ratio
    per_position = min(investable_ratio / len(selected), config.portfolio.max_position_ratio)

    execution_note = (
        f"止损{int(config.portfolio.stop_loss_ratio * 100)}% / "
        f"止盈{int(config.portfolio.take_profit_ratio * 100)}% / "
        f"回撤止盈{int(config.portfolio.trailing_stop_ratio * 100)}%"
    )

    for rec in selected:
        rec.suggested_weight = round(per_position, 4)
        rec.execution_note = execution_note

    return selected
