from __future__ import annotations

from datetime import datetime, timedelta

from alphaseeker.models import StockSnapshot
from alphaseeker.providers.base import MarketDataProvider


def _to_bs_symbol(symbol: str) -> str:
    code, suffix = symbol.split(".") if "." in symbol else (symbol, "")
    suffix = suffix.upper()
    if suffix == "SH":
        return f"sh.{code}"
    if suffix == "SZ":
        return f"sz.{code}"
    return symbol


class BaostockMarketDataProvider(MarketDataProvider):
    def get_snapshots(self, symbols: list[str]) -> list[StockSnapshot]:
        try:
            import baostock as bs
        except Exception as e:
            raise RuntimeError("未安装 baostock，请先安装依赖。") from e

        lg = bs.login()
        if lg.error_code != "0":
            raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")

        out: list[StockSnapshot] = []
        start = (datetime.utcnow() - timedelta(days=45)).strftime("%Y-%m-%d")
        end = datetime.utcnow().strftime("%Y-%m-%d")

        try:
            for symbol in symbols:
                bs_symbol = _to_bs_symbol(symbol)
                rs = bs.query_history_k_data_plus(
                    bs_symbol,
                    "date,code,close,volume",
                    start_date=start,
                    end_date=end,
                    frequency="d",
                    adjustflag="2",
                )

                if rs.error_code != "0":
                    continue

                rows: list[list[str]] = []
                while rs.error_code == "0" and rs.next():
                    rows.append(rs.get_row_data())

                if len(rows) < 2:
                    continue

                closes = [float(r[2]) for r in rows if r[2] not in {"", "None"}]
                volumes = [float(r[3]) for r in rows if r[3] not in {"", "None"}]
                if not closes:
                    continue

                latest_price = float(closes[-1])
                pct_20d = None
                if len(closes) >= 21 and closes[-21] != 0:
                    pct_20d = round((closes[-1] / closes[-21] - 1) * 100, 2)

                volume_ratio = None
                if len(volumes) >= 6:
                    avg5 = sum(volumes[-6:-1]) / 5 if sum(volumes[-6:-1]) else 0
                    if avg5:
                        volume_ratio = round(volumes[-1] / avg5, 2)

                out.append(
                    StockSnapshot(
                        symbol=symbol,
                        name=bs_symbol,
                        price=latest_price,
                        pe_ttm=None,
                        pb=None,
                        roe=None,
                        revenue_yoy=None,
                        pct_chg_20d=pct_20d,
                        volume_ratio=volume_ratio,
                    )
                )
        finally:
            bs.logout()

        if symbols and not out:
            raise RuntimeError("baostock 未返回可用行情数据。")

        return out
