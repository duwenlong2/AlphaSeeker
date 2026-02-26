from __future__ import annotations

from alphaseeker.providers.akshare_provider import (
    AkshareMarketDataProvider,
    AkshareNewsProvider,
    NullNewsProvider,
)
from alphaseeker.providers.base import MarketDataProvider, NewsProvider
from alphaseeker.providers.baostock_provider import BaostockMarketDataProvider
from alphaseeker.providers.mock_provider import MockMarketDataProvider, MockNewsProvider
from alphaseeker.providers.yfinance_provider import YFinanceMarketDataProvider


def build_market_provider(kind: str) -> MarketDataProvider:
    mode = kind.strip().lower()
    if mode == "mock":
        return MockMarketDataProvider()
    if mode == "akshare":
        return AkshareMarketDataProvider()
    if mode == "baostock":
        return BaostockMarketDataProvider()
    if mode == "yfinance":
        return YFinanceMarketDataProvider()
    raise ValueError(f"不支持的 market provider: {kind}")


def build_news_provider(kind: str, market_provider_kind: str = "mock") -> NewsProvider:
    mode = kind.strip().lower()
    if mode == "auto":
        mode = "mock" if market_provider_kind.strip().lower() == "mock" else "none"

    if mode == "mock":
        return MockNewsProvider()
    if mode == "akshare":
        return AkshareNewsProvider()
    if mode == "none":
        return NullNewsProvider()
    raise ValueError(f"不支持的 news provider: {kind}")
