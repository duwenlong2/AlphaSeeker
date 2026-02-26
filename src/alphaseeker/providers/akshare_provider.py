from __future__ import annotations

from datetime import datetime, timedelta

from alphaseeker.models import NewsItem, StockSnapshot
from alphaseeker.providers.base import MarketDataProvider, NewsProvider


def _safe_float(v: object) -> float | None:
    if v is None:
        return None
    if isinstance(v, str) and v.strip() in {"", "-", "--", "None", "nan"}:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _normalize_symbol(symbol: str) -> str:
    return symbol.split(".")[0].strip()


def _digits_only(code: str) -> str:
    return "".join(ch for ch in str(code) if ch.isdigit())


class AkshareMarketDataProvider(MarketDataProvider):
    def __init__(self, lookback_days: int = 40) -> None:
        self.lookback_days = lookback_days

    @staticmethod
    def _pick_col(columns: list[str], candidates: list[str]) -> str | None:
        for c in candidates:
            if c in columns:
                return c
        return None

    def _calc_20d_change(self, ak, code: str) -> float | None:
        end = datetime.now()
        start = end - timedelta(days=self.lookback_days)
        try:
            hist = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq",
            )
            if hist is None or hist.empty:
                return None

            close_col = "收盘"
            if close_col not in hist.columns:
                return None

            closes = hist[close_col].dropna().tolist()
            if len(closes) < 21:
                return None

            base = float(closes[-21])
            latest = float(closes[-1])
            if base == 0:
                return None
            return round((latest / base - 1) * 100, 2)
        except Exception:
            return None

    def get_snapshots(self, symbols: list[str]) -> list[StockSnapshot]:
        try:
            import akshare as ak
        except Exception as e:
            raise RuntimeError("未安装 akshare，请先安装依赖。") from e

        out: list[StockSnapshot] = []
        source = "eastmoney"
        try:
            spot = ak.stock_zh_a_spot_em()
        except Exception:
            try:
                spot = ak.stock_zh_a_spot()
                source = "sina"
            except Exception as e:
                raise RuntimeError(
                    f"AkShare 行情请求失败（eastmoney/sina 均不可用）。"
                    f" 原始错误: {type(e).__name__}: {e}"
                ) from e

        if spot is None or spot.empty:
            return out

        columns = [str(c) for c in spot.columns]
        code_col = self._pick_col(columns, ["代码", "symbol", "代码", "证券代码"])
        if code_col not in spot.columns:
            return out

        name_col = self._pick_col(columns, ["名称", "name", "证券简称"])
        price_col = self._pick_col(columns, ["最新价", "trade", "最新", "当前价"])
        pe_col = self._pick_col(columns, ["市盈率-动态", "pe", "市盈率"])
        pb_col = self._pick_col(columns, ["市净率", "pb"])
        vol_ratio_col = self._pick_col(columns, ["量比", "volume_ratio"])

        by_code: dict[str, object] = {}
        for _, row in spot.iterrows():
            raw = str(row[code_col]).strip()
            by_code[raw] = row
            digits = _digits_only(raw)
            if digits:
                by_code[digits] = row

        for symbol in symbols:
            code = _normalize_symbol(symbol)
            row = by_code.get(code) or by_code.get(_digits_only(code))
            if row is None:
                continue

            price = _safe_float(row.get(price_col)) if price_col else None
            if price is None:
                continue

            snapshot = StockSnapshot(
                symbol=symbol,
                name=str(row.get(name_col, code)) if name_col else code,
                price=price,
                pe_ttm=_safe_float(row.get(pe_col)) if pe_col else None,
                pb=_safe_float(row.get(pb_col)) if pb_col else None,
                roe=None,
                revenue_yoy=None,
                pct_chg_20d=self._calc_20d_change(ak, code) if source == "eastmoney" else None,
                volume_ratio=_safe_float(row.get(vol_ratio_col)) if vol_ratio_col else None,
            )
            out.append(snapshot)

        return out


class AkshareNewsProvider(NewsProvider):
    def get_news(self, symbols: list[str]) -> list[NewsItem]:
        try:
            import akshare as ak
        except Exception as e:
            raise RuntimeError("未安装 akshare，请先安装依赖。") from e

        out: list[NewsItem] = []
        now = datetime.utcnow()

        for symbol in symbols:
            code = _normalize_symbol(symbol)
            try:
                try:
                    news_df = ak.stock_news_em(symbol=code)
                except Exception:
                    continue
                if news_df is None or news_df.empty:
                    continue

                title_col = "新闻标题" if "新闻标题" in news_df.columns else None
                if title_col is None:
                    for c in news_df.columns:
                        if "标题" in str(c):
                            title_col = c
                            break
                if title_col is None:
                    continue

                time_col = "发布时间" if "发布时间" in news_df.columns else None
                top_rows = news_df.head(3)

                for _, row in top_rows.iterrows():
                    title = str(row.get(title_col, "")).strip()
                    if not title:
                        continue

                    published_at = now
                    if time_col is not None:
                        raw = row.get(time_col)
                        try:
                            published_at = datetime.fromisoformat(str(raw).replace("Z", ""))
                        except Exception:
                            published_at = now

                    out.append(
                        NewsItem(
                            symbol=symbol,
                            title=title,
                            source="akshare",
                            published_at=published_at,
                        )
                    )
            except Exception:
                continue

        return out


class NullNewsProvider(NewsProvider):
    def get_news(self, symbols: list[str]) -> list[NewsItem]:
        return []
