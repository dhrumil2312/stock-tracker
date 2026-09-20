"""MockProvider yields one labelled placeholder article per scope."""
from __future__ import annotations

from datetime import date

from app.models import Movement
from app.services.news.base import NewsQuery
from app.services.news.mock import MockProvider


def _query() -> NewsQuery:
    move = Movement(date=date(2026, 9, 18), close=100.0, pct_change=3.0, direction="up")
    return NewsQuery("NVDA", "NVIDIA", "Semiconductors", move)


def test_each_scope_is_categorised_and_labelled() -> None:
    provider = MockProvider()
    query = _query()
    for scope in ("company", "industry", "macro"):
        articles = provider.fetch_scope(scope, "NVDA", query, max_articles=3)
        assert len(articles) == 1
        assert articles[0].category == scope
        assert articles[0].title.startswith("[MOCK]")
        assert articles[0].url


def test_respects_max_articles_zero() -> None:
    provider = MockProvider()
    assert provider.fetch_scope("company", "NVDA", _query(), max_articles=0) == []
