"""Chat SSE fallback, error degrade, and tool-loop behavior."""
from __future__ import annotations

import json
from datetime import date

import pytest

from app.config import settings
from app.models import Article, Movement
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


def _events(iter_events) -> list[tuple[str, dict]]:
    return list(iter_events)


def test_fallback_reports_no_movements() -> None:
    reply = chat_service._fallback_reply("why?", [])
    assert "nothing to explain" in reply


def test_fallback_highlights_largest_move() -> None:
    moves = [_movement("2026-09-10", 2.5), _movement("2026-09-18", -8.1)]
    reply = chat_service._fallback_reply("why?", moves)
    assert "2026-09-18" in reply
    assert "-8.10%" in reply
    assert "without a live model" not in reply


def test_fallback_mentions_missing_key_only_when_asked() -> None:
    moves = [_movement("2026-09-10", 3.5)]
    keyed = chat_service._fallback_reply("why?", moves, no_key=True)
    assert "without a live model" in keyed
    assert "2026-09-10" in keyed


def test_iter_chat_sse_uses_fallback_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", None)
    events = _events(
        chat_service.iter_chat_sse(
            "NVDA",
            "NVIDIA",
            "Semiconductors",
            [_movement("2026-09-18", 5.0)],
            "why?",
            [],
            "x",
        )
    )
    kinds = [kind for kind, _ in events]
    assert kinds[0] == "status"
    assert kinds[-1] == "done"
    token = next(payload["text"] for kind, payload in events if kind == "token")
    done = next(payload for kind, payload in events if kind == "done")
    assert "Biggest flagged move" in token
    assert "without a live model" in token
    assert done["grounded"] is False


def test_iter_chat_sse_degrades_on_model_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(chat_service, "_complete", _boom)
    events = _events(
        chat_service.iter_chat_sse(
            "NVDA",
            "NVIDIA",
            "Semiconductors",
            [_movement("2026-09-18", 5.0)],
            "why?",
            [],
            "x",
        )
    )
    token = next(payload["text"] for kind, payload in events if kind == "token")
    done = next(payload for kind, payload in events if kind == "done")
    assert "model connection error (RuntimeError)" in token
    assert "without a live model" not in token
    assert done["grounded"] is False


def test_biggest_move_uses_tools_instead_of_asking_date(
    monkeypatch: pytest.MonkeyPatch, temp_db, seed_ticker
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    seed_ticker(
        "AAPL",
        name="Apple Inc.",
        bars=[
            {"date": "2026-09-09", "close": 100.0, "daily_return": 0.0},
            {"date": "2026-09-10", "close": 103.56, "daily_return": 0.0356},
        ],
        moves=[{"date": "2026-09-10", "pct_change": 0.0356, "direction": "up", "close": 103.56}],
    )
    step = {"n": 0}

    def fake_complete(messages, model, *, tools):
        step["n"] += 1
        last = messages[-1]
        if step["n"] == 1:
            assert last["role"] == "user"
            assert "biggest" in last["content"].lower()
            return "", [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "list_moves", "arguments": "{}"},
                }
            ]
        if step["n"] == 2:
            assert last["role"] == "tool"
            moves = json.loads(last["content"])["moves"]
            assert moves[0]["date"] == "2026-09-10"
            return "", [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "fetch_news", "arguments": '{"date":"2026-09-10"}'},
                }
            ]
        return "Apple's biggest flagged jump was 2026-09-10 on iPhone demand.", []

    monkeypatch.setattr(chat_service, "_complete", fake_complete)
    monkeypatch.setattr(
        chat_service,
        "_tool_fetch_news",
        lambda *_a, **_k: json.dumps(
            {
                "date": "2026-09-10",
                "articles": [{"title": "iPhone demand lifts Apple", "category": "company"}],
            }
        ),
    )

    events = _events(
        chat_service.iter_chat_sse(
            "AAPL",
            "Apple Inc.",
            "Consumer Electronics",
            [_movement("2026-09-10", 3.56)],
            "What drove the biggest move?",
            [],
            "deepseek/deepseek-v4.1-flash",
        )
    )
    statuses = [payload["message"] for kind, payload in events if kind == "status"]
    token = next(payload["text"] for kind, payload in events if kind == "token")
    done = next(payload for kind, payload in events if kind == "done")
    assert any("flagged move days" in s for s in statuses)
    assert any("Fetching news for 2026-09-10" in s for s in statuses)
    assert "2026-09-10" in token
    assert "iPhone" in token
    assert "which date" not in token.lower()
    assert done["grounded"] is True


def test_parse_month_day_accepts_common_chat_phrases() -> None:
    assert chat_service._parse_month_day("2026-09-01") == (9, 1, 2026)
    assert chat_service._parse_month_day("September 1") == (9, 1, None)
    assert chat_service._parse_month_day("sept 2") == (9, 2, None)
    assert chat_service._parse_month_day("9/1") == (9, 1, None)


def test_get_session_uses_loaded_year_not_labor_day(temp_db, seed_ticker) -> None:
    seed_ticker(
        "AAPL",
        name="Apple Inc.",
        bars=[
            {"date": "2026-08-31", "close": 314.0, "daily_return": 0.0},
            {"date": "2026-09-01", "close": 325.13, "open": 316.98, "high": 327.3, "low": 314.73, "daily_return": 0.0261},
            {"date": "2026-09-02", "close": 326.0, "daily_return": 0.0027},
        ],
        moves=[{"date": "2026-09-01", "pct_change": 2.61, "direction": "up", "close": 325.13}],
    )
    named = json.loads(chat_service._tool_get_session("AAPL", {"date": "September 1"}))
    assert named["date"] == "2026-09-01"
    assert named["weekday"] == "Tuesday"
    assert named["flagged_2pct"] is True

    wrong_year = json.loads(chat_service._tool_get_session("AAPL", {"date": "2025-09-01"}))
    assert wrong_year["date"] == "2026-09-01"
    assert wrong_year["remapped_from_year"] == 2025
    assert wrong_year["flagged_2pct"] is True

    sept2 = json.loads(chat_service._tool_get_session("AAPL", {"date": "sept 2"}))
    assert sept2["date"] == "2026-09-02"
    assert sept2["flagged_2pct"] is False

    missing = json.loads(chat_service._tool_get_session("AAPL", {"date": "2026-09-06"}))
    assert "error" in missing
    assert "holiday" not in missing["error"].lower()
    assert missing["window_start"] == "2026-08-31"
    assert "2026-09-01" in missing["nearest_loaded"]
