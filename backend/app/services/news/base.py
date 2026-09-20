"""NewsProvider interface and shared query construction."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date as Date, timedelta
from typing import Literal

from ...models import Article, Movement

NewsScope = Literal["company", "industry", "macro"]

# Pad around a move so overnight / weekend coverage is not missed.
NEWS_PAD_DAYS = 2


class NewsQuery:
    """A search window derived from a single movement, at three relevance levels."""

    def __init__(
        self,
        ticker: str,
        company_name: str | None,
        industry: str | None,
        movement: Movement,
    ):
        self.ticker = ticker
        self.company_name = company_name or ticker
        self.industry = (industry or "").strip() or None
        self.movement = movement
        start = movement.date - timedelta(days=NEWS_PAD_DAYS)
        end = movement.date + timedelta(days=1)
        if movement.window_start is not None:
            start = min(start, movement.window_start)
        if movement.window_end is not None:
            end = max(end, movement.window_end)
        self.start: Date = start
        self.end: Date = end

    def prompt(self, scope: NewsScope) -> str:
        """Natural-language query for SEMANTIC providers (Exa)."""
        direction = "surged" if self.movement.direction == "up" else "fell"
        if scope == "company":
            return (
                f"{self.company_name} ({self.ticker}) stock {direction} — "
                "earnings, product, lawsuit, guidance news"
            )
        if scope == "industry":
            sector = self.industry or "the sector"
            return (
                f"{sector} sector news {self.movement.date}: "
                "competitors, supply, regulation"
            )
        return (
            f"Macro and political events {self.movement.date}: "
            "interest rates, regulation, geopolitics affecting markets"
        )

    def keyword_query(self, scope: NewsScope) -> str:
        """Boolean-keyword query for KEYWORD providers (NewsAPI)."""
        if scope == "company":
            name = self.company_name
            return f'"{name}" AND (earnings OR revenue OR guidance OR lawsuit OR launch OR "product")'
        if scope == "industry":
            sector = self.industry or self.company_name
            return f'"{sector}" AND (competitor OR rival OR industry OR sector OR market)'
        return '"Federal Reserve" OR "interest rate" OR inflation OR regulation OR tariff OR geopolitics'


class NewsProvider(ABC):
    """Fetches explanatory articles for one relevance scope around a move date."""

    name: str = "unknown"
    query_style: str = "semantic"

    @abstractmethod
    def fetch_scope(
        self, scope: NewsScope, subject: str, query: NewsQuery, max_articles: int
    ) -> list[Article]:
        ...
