from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from alphaseeker.config import AppConfig
from alphaseeker.providers.base import MarketDataProvider, NewsProvider
from alphaseeker.skills.ranker import rank_stocks


def run_shadow_scan(
    watchlist: list[str],
    market_provider: MarketDataProvider,
    news_provider: NewsProvider,
    topn: int = 5,
    output_dir: str = "data/reports",
) -> dict:
    cfg = AppConfig()
    snapshots = market_provider.get_snapshots(watchlist)
    news = news_provider.get_news(watchlist)
    recs = rank_stocks(snapshots=snapshots, news=news, config=cfg, topn=topn)

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "watchlist_size": len(watchlist),
        "topn": topn,
        "recommendations": [asdict(r) for r in recs],
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"scan_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    report["file"] = str(out_file)
    return report
