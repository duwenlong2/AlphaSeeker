from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from alphaseeker.config import AppConfig
from alphaseeker.providers.base import MarketDataProvider, NewsProvider
from alphaseeker.skills.allocation import assign_target_weights
from alphaseeker.skills.ranker import rank_stocks
from alphaseeker.skills.scoring import market_regime_signal


def _diag_ok(stage: str, started_at: float, detail: str, **meta: object) -> dict:
    return {
        "stage": stage,
        "status": "ok",
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        "detail": detail,
        "meta": meta,
    }


def _diag_error(stage: str, started_at: float, exc: Exception, **meta: object) -> dict:
    return {
        "stage": stage,
        "status": "error",
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        "error_type": type(exc).__name__,
        "error": str(exc),
        "meta": meta,
    }


def _diag_warn(stage: str, started_at: float, detail: str, **meta: object) -> dict:
    return {
        "stage": stage,
        "status": "warning",
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        "detail": detail,
        "meta": meta,
    }


def run_shadow_scan(
    watchlist: list[str],
    market_provider: MarketDataProvider,
    news_provider: NewsProvider,
    topn: int = 5,
    output_dir: str = "data/reports",
) -> dict:
    cfg = AppConfig()
    diagnostics: list[dict] = []
    status = "ok"
    failed_stage = ""

    snapshots = []
    news = []
    recs = []

    t = time.perf_counter()
    try:
        snapshots = market_provider.get_snapshots(watchlist)
        diagnostics.append(
            _diag_ok(
                "market_data",
                t,
                "行情快照获取成功",
                provider=type(market_provider).__name__,
                snapshot_count=len(snapshots),
            )
        )
    except Exception as e:
        status = "failed"
        failed_stage = "market_data"
        diagnostics.append(
            _diag_error(
                "market_data",
                t,
                e,
                provider=type(market_provider).__name__,
            )
        )

    if status != "failed":
        t = time.perf_counter()
        try:
            news = news_provider.get_news(watchlist)
            diagnostics.append(
                _diag_ok(
                    "news_data",
                    t,
                    "新闻数据获取成功",
                    provider=type(news_provider).__name__,
                    news_count=len(news),
                )
            )
        except Exception as e:
            status = "degraded"
            diagnostics.append(
                _diag_warn(
                    "news_data",
                    t,
                    "新闻获取失败，已降级为空新闻继续执行",
                    provider=type(news_provider).__name__,
                    error_type=type(e).__name__,
                    error=str(e),
                )
            )
            news = []

    if status != "failed":
        t = time.perf_counter()
        try:
            recs = rank_stocks(snapshots=snapshots, news=news, config=cfg, topn=topn)
            diagnostics.append(
                _diag_ok(
                    "ranking",
                    t,
                    "评分排序完成",
                    recommendation_count=len(recs),
                )
            )
            rec_with_news = [r for r in recs if (r.news_event_count or 0) > 0]
            avg_news_score = (
                round(sum(r.news_score for r in recs) / len(recs), 2) if recs else 0.0
            )
            diagnostics.append(
                _diag_ok(
                    "news_signal",
                    t,
                    "新闻信号融合完成",
                    recommendation_with_news=len(rec_with_news),
                    recommendation_count=len(recs),
                    news_coverage_ratio=round(len(rec_with_news) / len(recs), 4) if recs else 0.0,
                    avg_news_score=avg_news_score,
                )
            )
            if recs:
                regime_adjustment, regime_note = market_regime_signal(snapshots)
                diagnostics.append(
                    _diag_ok(
                        "market_regime",
                        t,
                        "市场环境融合完成",
                        regime_adjustment=regime_adjustment,
                        regime_note=regime_note,
                    )
                )
        except Exception as e:
            status = "failed"
            failed_stage = "ranking"
            diagnostics.append(_diag_error("ranking", t, e))

    if status != "failed":
        t = time.perf_counter()
        try:
            recs = assign_target_weights(recs, cfg)
            diagnostics.append(
                _diag_ok(
                    "allocation",
                    t,
                    "仓位分配完成",
                    position_count=len(recs),
                )
            )
        except Exception as e:
            status = "failed"
            failed_stage = "allocation"
            diagnostics.append(_diag_error("allocation", t, e))

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "status": status,
        "failed_stage": failed_stage,
        "watchlist_size": len(watchlist),
        "topn": topn,
        "providers": {
            "market": type(market_provider).__name__,
            "news": type(news_provider).__name__,
        },
        "policy": {
            "cash_buffer_ratio": cfg.portfolio.cash_buffer_ratio,
            "max_positions": cfg.portfolio.max_positions,
            "max_position_ratio": cfg.portfolio.max_position_ratio,
            "min_total_score": cfg.thresholds.min_total_score,
            "max_20d_chg_for_entry": cfg.thresholds.max_20d_chg_for_entry,
            "news_keyword_weight_base": cfg.news.keyword_weight_base,
            "news_structured_weight_base": cfg.news.structured_weight_base,
            "news_structured_weight_step": cfg.news.structured_weight_step,
            "news_structured_weight_max": cfg.news.structured_weight_max,
            "news_event_impact_scale": cfg.news.event_impact_scale,
            "news_event_half_life_hours": cfg.news.event_half_life_hours,
        },
        "diagnostics": diagnostics,
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
