"""Chat context building and the keyless fallback / error-degrade paths."""
from __future__ import annotations

from datetime import date

import pytest

from app.config import settings
from app.models import Article, ChatMessage, Movement
from app.services import chat as chat_service


def _movement(day: str, pct: float, articles: list[Article] | None = None) -> Movement:
    d = date.fromisoformat(day)
    return Movement(
        date=d,
        close=100.0,
        pct_change=pct,
        direction="up" if pct > 0 else "down",
        articles=articles or [],
    )


def _article(title: str, category: str = "company") -> Article:
    return Article(title=title, url=f"https://example.com/{title}", category=category)


def test_build_context_lists_moves_and_articles() -> None:
    move = _movement("2026-09-18", 3.2, [_article("Chip demand soars")])
    context = chat_service.build_context("NVDA", "NVIDIA", [move])
    assert "NVDA (NVIDIA)" in context
    assert "2026-09-18" in context
    assert "+3.20%" in context
    assert "Chip demand soars" in context


def test_build_context_marks_moves_without_news() -> None:
    context = chat_service.build_context("NVDA", None, [_movement("2026-09-18", 3.2)])
    assert "no news found in window" in context


def test_build_context_includes_ohlc_and_volume_details() -> None:
    move = Movement(
        date=date(2026, 9, 18),
        open=100.0,
        high=110.0,
        low=99.0,
        close=105.0,
        prev_adj_close=100.0,
        volume=1234,
        pct_change=5.0,
        direction="up",
        articles=[_article("Chip demand soars")],
    )
    context = chat_service.build_context("NVDA", "NVIDIA", [move])
    for token in ("open 100.0", "high 110.0", "low 99.0", "prev 100.0", "vol 1234"):
        assert token in context


def test_answer_uses_fallback_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", None)
    reply, grounded = chat_service.answer(
        "NVDA", "NVIDIA", [_movement("2026-09-18", 5.0)], "why?", history=[], model="x"
    )
    assert grounded is False
    assert "Biggest move" in reply
    assert "OPENROUTER_API_KEY" in reply


def test_fallback_reports_no_movements() -> None:
    reply = chat_service._fallback_reply("why?", [])
    assert "nothing to explain" in reply


def test_fallback_highlights_largest_move() -> None:
    moves = [_movement("2026-09-10", 2.5), _movement("2026-09-18", -8.1)]
    reply = chat_service._fallback_reply("why?", moves)
    assert "2026-09-18" in reply
    assert "-8.10%" in reply


class _FakeClient:
    """Minimal stand-in for httpx.Client used by _call_openrouter."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.request: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json, headers):
        self.request = {"url": url, "json": json, "headers": headers}
        return _FakePostResponse(self._payload)


class _FakePostResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_answer_returns_grounded_reply_from_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    payload = {"choices": [{"message": {"content": "  It surged on strong earnings.  "}}]}
    fake = _FakeClient(payload)
    monkeypatch.setattr(chat_service.httpx, "Client", lambda *a, **k: fake)

    reply, grounded = chat_service.answer(
        "NVDA",
        "NVIDIA",
        [_movement("2026-09-18", 5.0)],
        "why?",
        history=[ChatMessage(role="user", content="hi")],
        model="anthropic/claude-3.5-haiku",
    )
    assert grounded is True
    assert reply == "It surged on strong earnings."
    # The chosen model and system prompt are forwarded to OpenRouter.
    assert fake.request["json"]["model"] == "anthropic/claude-3.5-haiku"
    assert fake.request["json"]["messages"][0]["role"] == "system"


def test_answer_degrades_gracefully_on_model_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(chat_service, "_call_openrouter", _boom)
    reply, grounded = chat_service.answer(
        "NVDA", "NVIDIA", [_movement("2026-09-18", 5.0)], "why?", history=[], model="x"
    )
    assert grounded is False
    assert "Chat model error (RuntimeError)" in reply
