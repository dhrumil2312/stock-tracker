"""Provider selection honours NEWS_PROVIDER and falls back when keys are missing."""
from __future__ import annotations

import pytest

from app.config import settings
from app.services.news import get_news_provider
from app.services.news.exa import ExaProvider
from app.services.news.mock import MockProvider


@pytest.fixture()
def clear_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "exa_api_key", None)
    monkeypatch.setattr(settings, "newsapi_api_key", None)


def test_mock_is_returned_when_requested(monkeypatch: pytest.MonkeyPatch, clear_keys: None) -> None:
    monkeypatch.setattr(settings, "news_provider", "mock")
    assert isinstance(get_news_provider(), MockProvider)


def test_exa_used_when_requested_with_key(monkeypatch: pytest.MonkeyPatch, clear_keys: None) -> None:
    monkeypatch.setattr(settings, "news_provider", "exa")
    monkeypatch.setattr(settings, "exa_api_key", "test-key")
    assert isinstance(get_news_provider(), ExaProvider)


def test_falls_back_to_available_key(monkeypatch: pytest.MonkeyPatch, clear_keys: None) -> None:
    # NewsAPI requested but only an Exa key present -> use Exa, not mock.
    monkeypatch.setattr(settings, "news_provider", "newsapi")
    monkeypatch.setattr(settings, "exa_api_key", "test-key")
    assert isinstance(get_news_provider(), ExaProvider)


def test_falls_back_to_mock_without_any_key(monkeypatch: pytest.MonkeyPatch, clear_keys: None) -> None:
    monkeypatch.setattr(settings, "news_provider", "exa")
    assert isinstance(get_news_provider(), MockProvider)
