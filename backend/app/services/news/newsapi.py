"""NewsAPI.org keyword provider.

Free tier covers roughly the last 30 days, so older movement windows may return
empty. Industry/macro are approximated with boolean keyword queries.

Docs: https://newsapi.org/docs/endpoints/everything
"""
from __future__ import annotations

import httpx

from ...models import Article
from .base import NewsProvider, NewsQuery, NewsScope

NEWSAPI_URL = "https://newsapi.org/v2/everything"


class NewsApiProvider(NewsProvider):
    name = "newsapi"
    query_style = "keyword"

    def __init__(self, api_key: str, timeout: float = 20.0):
        self._api_key = api_key
        self._timeout = timeout

    def fetch_scope(
        self, scope: NewsScope, subject: str, query: NewsQuery, max_articles: int
    ) -> list[Article]:
        resp = httpx.get(
            NEWSAPI_URL,
            params={
                "q": query.keyword_query(scope),
                "from": query.start.isoformat(),
                "to": query.end.isoformat(),
                "language": "en",
                "sortBy": "relevancy",
                "pageSize": max_articles,
                "apiKey": self._api_key,
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        articles: list[Article] = []
        for row in data.get("articles") or []:
            url = row.get("url")
            if not url:
                continue
            published = (row.get("publishedAt") or "")[:10] or None
            source = (row.get("source") or {}).get("name")
            articles.append(
                Article(
                    title=row.get("title") or url,
                    url=url,
                    source=source,
                    published_at=published,
                    snippet=(row.get("description") or "").strip()[:400] or None,
                    category=scope,
                )
            )
        return articles[:max_articles]
