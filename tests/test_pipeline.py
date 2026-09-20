"""build_ticker_response applies date/threshold/direction filters over stored data."""
from __future__ import annotations

import pytest

from app.services.pipeline import build_ticker_response

BARS = [
    {"date": "2026-09-10", "close": 100.0, "daily_return": 0.005},
    {"date": "2026-09-15", "close": 108.0, "daily_return": 0.08},
    {"date": "2026-09-18", "close": 103.0, "daily_return": -0.05},
]
MOVES = [
    {"date": "2026-09-15", "pct_change": 0.08, "direction": "up", "close": 108.0},
    {"date": "2026-09-18", "pct_change": -0.05, "direction": "down", "close": 103.0},
]


@pytest.fixture()
def nvda(temp_db, seed_ticker):
    seed_ticker("NVDA", name="NVIDIA Corp.", industry="Semiconductors", bars=BARS, moves=MOVES)
    return "NVDA"


def test_returns_all_moves_above_default_threshold(nvda) -> None:
    resp = build_ticker_response(nvda, include_news=False)
    assert resp.ticker == "NVDA"
    assert {m.date.isoformat() for m in resp.movements} == {"2026-09-15", "2026-09-18"}


def test_threshold_filters_smaller_moves(nvda) -> None:
    resp = build_ticker_response(nvda, include_news=False, threshold=6.0)
    assert [m.date.isoformat() for m in resp.movements] == ["2026-09-15"]
    assert resp.threshold == 6.0


def test_direction_filter(nvda) -> None:
    resp = build_ticker_response(nvda, include_news=False, direction="down")
    assert [m.direction for m in resp.movements] == ["down"]


def test_date_window_filters_prices_and_moves(nvda) -> None:
    from datetime import date

    resp = build_ticker_response(
        nvda, include_news=False, start=date(2026, 9, 16), end=date(2026, 9, 30)
    )
    assert [m.date.isoformat() for m in resp.movements] == ["2026-09-18"]
    assert all(p.date >= date(2026, 9, 16) for p in resp.prices)


def test_news_attached_via_mock_provider(nvda) -> None:
    # No provider keys in the test env -> MockProvider, so this stays offline.
    resp = build_ticker_response(nvda, include_news=True)
    assert any(m.articles for m in resp.movements)
