from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console
from rich.table import Table

from alphaseeker.pipelines.shadow_scan import run_shadow_scan
from alphaseeker.providers.mock_provider import MockMarketDataProvider, MockNewsProvider


def _read_watchlist(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"watchlist not found: {path}")
    return [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def cmd_scan(args: argparse.Namespace) -> None:
    symbols = _read_watchlist(args.watchlist)
    report = run_shadow_scan(
        watchlist=symbols,
        market_provider=MockMarketDataProvider(),
        news_provider=MockNewsProvider(),
        topn=args.topn,
    )

    table = Table(title="AlphaSeeker 推荐结果（Shadow Mode）")
    table.add_column("代码")
    table.add_column("总分")
    table.add_column("理由")
    table.add_column("风险")

    for item in report["recommendations"]:
        table.add_row(
            item["symbol"],
            str(item["total_score"]),
            item["reason"],
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
    scan.set_defaults(func=cmd_scan)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
