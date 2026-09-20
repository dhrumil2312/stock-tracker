"""Exa and NewsAPI parse provider JSON into Article models (HTTP is mocked)."""
from __future__ import annotations

from datetime import date

import pytest

from app.models import Movement
from app.services.news import exa as exa_mod
from app.services.news import newsapi as newsapi_mod
from app.services.news.base import NewsQuery
from app.services.news.exa import ExaProvider
from app.services.news.newsapi import NewsApiProvider


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.captured: dict = {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _query() -> NewsQuery:
    move = Movement(date=date(2026, 9, 18), close=100.0, pct_change=3.0, direction="up")
    return NewsQuery("NVDA", "NVIDIA", "Semiconductors", move)


def test_exa_maps_results_to_articles(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "results": [
            {
                "url": "https://ex.com/a",
                "title": "Chip demand soars",
                "author": "Jane",
                "publishedDate": "2026-09-18T12:00:00Z",
                "text": "  Long body text  ",
            },
            {"title": "No URL, skipped"},  # dropped: no url
        ]
    }
    monkeypatch.setattr(exa_mod.httpx, "post", lambda *a, **k: _FakeResponse(payload))

    articles = ExaProvider(api_key="k").fetch_scope("company", "NVDA", _query(), max_articles=5)
    assert len(articles) == 1
    art = articles[0]
    assert art.url == "https://ex.com/a"
    assert art.source == "Jane"
    assert art.published_at == date(2026, 9, 18)
    assert art.snippet == "Long body text"
    assert art.category == "company"


def test_exa_respects_max_articles(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"results": [{"url": f"https://ex.com/{i}", "title": str(i)} for i in range(5)]}
    monkeypatch.setattr(exa_mod.httpx, "post", lambda *a, **k: _FakeResponse(payload))
    articles = ExaProvider(api_key="k").fetch_scope("macro", "*", _query(), max_articles=2)
    assert len(articles) == 2


def test_exa_parse_date_handles_garbage() -> None:
    assert ExaProvider._parse_date(None) is None
    assert ExaProvider._parse_date("not-a-date") is None


def test_newsapi_maps_articles(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "articles": [
            {
                "url": "https://n.com/a",
                "title": "Sector rallies",
                "publishedAt": "2026-09-18T09:30:00Z",
                "source": {"name": "Reuters"},
                "description": "  desc  ",
            },
            {"title": "no url"},  # dropped
        ]
    }
    monkeypatch.setattr(newsapi_mod.httpx, "get", lambda *a, **k: _FakeResponse(payload))

    articles = NewsApiProvider(api_key="k").fetch_scope("industry", "Semi", _query(), max_articles=5)
    assert len(articles) == 1
    art = articles[0]
    assert art.url == "https://n.com/a"
    assert art.source == "Reuters"
    assert art.published_at == date(2026, 9, 18)
    assert art.snippet == "desc"
    assert art.category == "industry"
