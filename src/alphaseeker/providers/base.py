from __future__ import annotations

from abc import ABC, abstractmethod

from alphaseeker.models import NewsItem, StockSnapshot


class MarketDataProvider(ABC):
    @abstractmethod
    def get_snapshots(self, symbols: list[str]) -> list[StockSnapshot]:
        raise NotImplementedError


class NewsProvider(ABC):
    @abstractmethod
    def get_news(self, symbols: list[str]) -> list[NewsItem]:
        raise NotImplementedError
