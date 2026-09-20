"""News provider selection."""
from __future__ import annotations

from ...config import settings
from .base import NewsProvider
from .exa import ExaProvider
from .mock import MockProvider


def get_news_provider() -> NewsProvider:
    """Return the configured provider, falling back when no key is set.

    If NEWS_PROVIDER is newsapi but only EXA_API_KEY is present, use Exa.
    """
    requested = (settings.news_provider or "").strip().lower()
    if requested == "mock":
        return MockProvider()
    if requested == "exa" and settings.exa_api_key:
        return ExaProvider(api_key=settings.exa_api_key)
    if requested == "newsapi" and settings.newsapi_api_key:
        from .newsapi import NewsApiProvider

        return NewsApiProvider(api_key=settings.newsapi_api_key)
    if settings.exa_api_key:
        return ExaProvider(api_key=settings.exa_api_key)
    if settings.newsapi_api_key:
        from .newsapi import NewsApiProvider

        return NewsApiProvider(api_key=settings.newsapi_api_key)
    return MockProvider()


__all__ = ["NewsProvider", "get_news_provider"]
