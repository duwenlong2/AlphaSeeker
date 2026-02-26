from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console
from rich.table import Table

from alphaseeker.pipelines.shadow_scan import run_shadow_scan
from alphaseeker.providers.factory import build_market_provider, build_news_provider


def _print_diagnostics(report: dict) -> None:
    diagnostics = report.get("diagnostics", [])
    if not diagnostics:
        return

    table = Table(title="执行诊断")
    table.add_column("环节")
    table.add_column("状态")
    table.add_column("耗时(ms)")
    table.add_column("说明")

    for item in diagnostics:
        status = str(item.get("status", "unknown"))
        detail = item.get("detail") or item.get("error") or ""
        table.add_row(
            str(item.get("stage", "-")),
            status,
            str(item.get("duration_ms", "-")),
            str(detail),
        )

    Console().print(table)


def _read_watchlist(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"watchlist not found: {path}")
    return [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def cmd_scan(args: argparse.Namespace) -> None:
    symbols = _read_watchlist(args.watchlist)
    market_provider = build_market_provider(args.market_provider)
    news_provider = build_news_provider(args.news_provider, args.market_provider)

    report = run_shadow_scan(
        watchlist=symbols,
        market_provider=market_provider,
        news_provider=news_provider,
        topn=args.topn,
    )

    _print_diagnostics(report)

    status = report.get("status", "ok")
    if status == "failed":
        Console().print(
            f"[red]扫描失败，失败环节：{report.get('failed_stage', 'unknown')}[/red]"
        )
        Console().print(f"报告已保存: {report.get('file', 'N/A')}")
        raise SystemExit(1)
    if status == "degraded":
        Console().print("[yellow]扫描降级完成：部分环节失败，已使用降级路径。[/yellow]")

    table = Table(title="AlphaSeeker 推荐结果（Shadow Mode）")
    table.add_column("代码")
    table.add_column("总分")
    table.add_column("新闻分")
    table.add_column("建议仓位")
    table.add_column("理由")
    table.add_column("新闻摘要")
    table.add_column("风险")

    for item in report["recommendations"]:
        table.add_row(
            item["symbol"],
            str(item["total_score"]),
            str(item.get("news_score", 50.0)),
            f"{item.get('suggested_weight', 0) * 100:.1f}%",
            item["reason"],
            item.get("news_summary", ""),
            item["risk_note"],
        )

    console = Console()
    console.print(table)
    console.print(f"\n报告已保存: {report['file']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alphaseeker")
    sub = parser.add_subparsers(required=True)

    scan = sub.add_parser("scan", help="运行盯盘扫描并输出候选股票")
    scan.add_argument("--watchlist", type=str, required=True, help="股票池文件，每行一个代码")
    scan.add_argument("--topn", type=int, default=5, help="输出前 N 个")
    scan.add_argument(
        "--market-provider",
        type=str,
        default="mock",
        choices=["mock", "akshare", "baostock", "yfinance"],
        help="行情数据源（mock/akshare/baostock/yfinance）",
    )
    scan.add_argument(
        "--news-provider",
        type=str,
        default="auto",
        choices=["auto", "mock", "akshare", "none"],
        help="新闻数据源（auto/mock/akshare/none）",
    )
    scan.set_defaults(func=cmd_scan)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
