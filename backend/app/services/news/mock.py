"""Keyless mock provider so the app runs end-to-end without an EXA_API_KEY.

Generates plausible, clearly-labelled placeholder articles across all three
relevance levels (company / industry / macro) for each movement window.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from ...models import Article
from .base import NewsProvider, NewsQuery, NewsScope


class MockProvider(NewsProvider):
    name = "mock"
    query_style = "semantic"

    def fetch_scope(
        self, scope: NewsScope, subject: str, query: NewsQuery, max_articles: int
    ) -> list[Article]:
        move_date = query.movement.date
        if scope == "company":
            title = f"[MOCK] {query.company_name} ({query.ticker}) on {move_date}"
            url = f"https://news.google.com/search?q={quote_plus(f'{query.ticker} stock {move_date}')}"
            snippet = "Placeholder company-specific story. Set EXA_API_KEY for real articles."
        elif scope == "industry":
            sector = query.industry or subject
            title = f"[MOCK] {sector} sector news on {move_date}"
            url = f"https://news.google.com/search?q={quote_plus(f'{sector} industry {move_date}')}"
            snippet = "Placeholder industry/competitor story, shared across tickers in this industry."
        else:
            title = f"[MOCK] Macro backdrop on {move_date}: rates, regulation, geopolitics"
            url = f"https://news.google.com/search?q={quote_plus(f'markets macro {move_date}')}"
            snippet = "Placeholder macro/political story, shared across all tickers that day."
        return [
            Article(
                title=title,
                url=url,
                source="mock-news",
                published_at=move_date,
                snippet=snippet,
                category=scope,
            )
        ][:max_articles]
