"""Exa AI news provider.

Uses Exa's neural search with a published-date window around each movement so
we can retrieve *historical* news. Runs three semantic queries per movement
(company / industry / macro) to satisfy the easy/medium/hard relevance levels.

Docs: https://docs.exa.ai/reference/search
"""
from __future__ import annotations

from datetime import datetime, time, timezone

import httpx

from ...models import Article
from .base import NewsProvider, NewsQuery, NewsScope

EXA_SEARCH_URL = "https://api.exa.ai/search"


def _iso(d, end_of_day: bool = False) -> str:
    t = time.max if end_of_day else time.min
    return datetime.combine(d, t, tzinfo=timezone.utc).isoformat()


class ExaProvider(NewsProvider):
    name = "exa"
    query_style = "semantic"

    def __init__(self, api_key: str, timeout: float = 20.0):
        self._api_key = api_key
        self._timeout = timeout

    def fetch_scope(
        self, scope: NewsScope, subject: str, query: NewsQuery, max_articles: int
    ) -> list[Article]:
        payload = {
            "query": query.prompt(scope),
            "numResults": max_articles,
            "type": "auto",
            "category": "news",
            "startPublishedDate": _iso(query.start),
            "endPublishedDate": _iso(query.end, end_of_day=True),
            "contents": {"text": {"maxCharacters": 600}},
        }
        resp = httpx.post(
            EXA_SEARCH_URL,
            json=payload,
            headers={"x-api-key": self._api_key, "Content-Type": "application/json"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        articles: list[Article] = []
        for row in data.get("results") or []:
            url = row.get("url")
            if not url:
                continue
            articles.append(
                Article(
                    title=row.get("title") or url,
                    url=url,
                    source=row.get("author") or "Exa",
                    published_at=self._parse_date(row.get("publishedDate")),
                    snippet=(row.get("text") or "").strip()[:400] or None,
                    category=scope,
                )
            )
        return articles[:max_articles]

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
