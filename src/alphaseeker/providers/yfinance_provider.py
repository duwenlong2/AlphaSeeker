from __future__ import annotations

from datetime import datetime, timedelta

from alphaseeker.models import StockSnapshot
from alphaseeker.providers.base import MarketDataProvider


def _to_yf_symbol(symbol: str) -> str:
    code, suffix = symbol.split(".") if "." in symbol else (symbol, "")
    suffix = suffix.upper()
    if suffix == "SH":
        return f"{code}.SS"
    if suffix == "SZ":
        return f"{code}.SZ"
    return symbol


class YFinanceMarketDataProvider(MarketDataProvider):
    def get_snapshots(self, symbols: list[str]) -> list[StockSnapshot]:
        try:
            import yfinance as yf
        except Exception as e:
            raise RuntimeError("未安装 yfinance，请先安装依赖。") from e

        out: list[StockSnapshot] = []
        failures: list[str] = []
        end = datetime.utcnow()
        start = end - timedelta(days=45)

        for symbol in symbols:
            yf_symbol = _to_yf_symbol(symbol)
            try:
                ticker = yf.Ticker(yf_symbol)
                hist = ticker.history(start=start, end=end, interval="1d", auto_adjust=True)
                if hist is None or hist.empty:
                    failures.append(f"{symbol}: empty history")
                    continue

                closes = hist["Close"].dropna().tolist()
                if not closes:
                    continue

                latest_price = float(closes[-1])
                pct_20d = None
                if len(closes) >= 21 and float(closes[-21]) != 0:
                    pct_20d = round((float(closes[-1]) / float(closes[-21]) - 1) * 100, 2)

                info = {}
                try:
                    info = ticker.fast_info or {}
                except Exception:
                    info = {}

                name = str(info.get("shortName") or symbol)
                volume = hist["Volume"].dropna().tolist() if "Volume" in hist.columns else []
                volume_ratio = None
                if len(volume) >= 6:
                    avg5 = sum(volume[-6:-1]) / 5 if sum(volume[-6:-1]) else 0
                    if avg5:
                        volume_ratio = round(float(volume[-1]) / avg5, 2)

                out.append(
                    StockSnapshot(
                        symbol=symbol,
                        name=name,
                        price=latest_price,
                        pe_ttm=None,
                        pb=None,
                        roe=None,
                        revenue_yoy=None,
                        pct_chg_20d=pct_20d,
                        volume_ratio=volume_ratio,
                    )
                )
            except Exception as e:
                failures.append(f"{symbol}: {type(e).__name__}: {e}")
                continue

        if symbols and not out:
            sample = "; ".join(failures[:3]) if failures else "unknown"
            raise RuntimeError(f"yfinance 获取快照失败（0/{len(symbols)}）。样本原因: {sample}")

        return out
