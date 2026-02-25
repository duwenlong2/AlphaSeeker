from __future__ import annotations

from datetime import datetime, timedelta

from alphaseeker.models import NewsItem, StockSnapshot
from alphaseeker.providers.base import MarketDataProvider, NewsProvider


class MockMarketDataProvider(MarketDataProvider):
    def get_snapshots(self, symbols: list[str]) -> list[StockSnapshot]:
        out: list[StockSnapshot] = []
        for i, symbol in enumerate(symbols):
            out.append(
                StockSnapshot(
                    symbol=symbol,
                    name=f"{symbol}_NAME",
                    price=3.0 + i * 1.6,
                    pe_ttm=10.0 + i * 6.0,
                    pb=1.0 + i * 0.3,
                    roe=7.0 + i * 2.0,
                    revenue_yoy=5.0 + i * 3.0,
                    pct_chg_20d=-2.0 + i * 1.5,
                    volume_ratio=1.0 + i * 0.2,
                )
            )
        return out


class MockNewsProvider(NewsProvider):
    POSITIVE = ["中标", "回购", "增长", "业绩预增", "新产品", "政策支持"]
    NEGATIVE = ["减持", "诉讼", "亏损", "处罚", "退市", "违约"]

    def get_news(self, symbols: list[str]) -> list[NewsItem]:
        now = datetime.utcnow()
        out: list[NewsItem] = []
        for i, symbol in enumerate(symbols):
            if i % 2 == 0:
                title = f"{symbol} 公告：签订重大订单，业绩预增"
            else:
                title = f"{symbol} 公告：股东计划减持"
            out.append(
                NewsItem(
                    symbol=symbol,
                    title=title,
                    source="mock",
                    published_at=now - timedelta(hours=i),
                )
            )
        return out
