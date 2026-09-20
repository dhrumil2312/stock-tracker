"""NewsQuery derives search windows and per-scope prompts from a movement."""
from __future__ import annotations

from datetime import date, timedelta

from app.models import Movement
from app.services.news.base import NEWS_PAD_DAYS, NewsQuery


def _movement(day: str, direction: str = "up", **kw) -> Movement:
    d = date.fromisoformat(day)
    return Movement(
        date=d,
        close=100.0,
        pct_change=3.0 if direction == "up" else -3.0,
        direction=direction,
        **kw,
    )


def test_window_pads_around_move_date() -> None:
    query = NewsQuery("NVDA", "NVIDIA", "Semiconductors", _movement("2026-09-18"))
    assert query.start == date(2026, 9, 18) - timedelta(days=NEWS_PAD_DAYS)
    assert query.end == date(2026, 9, 19)


def test_window_expands_to_cover_movement_window() -> None:
    move = _movement(
        "2026-09-18",
        window_start=date(2026, 9, 10),
        window_end=date(2026, 9, 25),
    )
    query = NewsQuery("NVDA", "NVIDIA", "Semiconductors", move)
    assert query.start == date(2026, 9, 10)
    assert query.end == date(2026, 9, 25)


def test_company_name_falls_back_to_ticker() -> None:
    query = NewsQuery("NVDA", None, "Semiconductors", _movement("2026-09-18"))
    assert query.company_name == "NVDA"


def test_blank_industry_becomes_none() -> None:
    query = NewsQuery("NVDA", "NVIDIA", "   ", _movement("2026-09-18"))
    assert query.industry is None


def test_semantic_prompt_reflects_direction_and_scope() -> None:
    up = NewsQuery("NVDA", "NVIDIA", "Semiconductors", _movement("2026-09-18", "up"))
    down = NewsQuery("NVDA", "NVIDIA", "Semiconductors", _movement("2026-09-18", "down"))
    assert "surged" in up.prompt("company")
    assert "fell" in down.prompt("company")
    assert "Semiconductors" in up.prompt("industry")
    assert "Macro" in up.prompt("macro")


def test_keyword_query_is_boolean_per_scope() -> None:
    query = NewsQuery("NVDA", "NVIDIA", "Semiconductors", _movement("2026-09-18"))
    assert "NVIDIA" in query.keyword_query("company")
    assert "Semiconductors" in query.keyword_query("industry")
    assert "Federal Reserve" in query.keyword_query("macro")
