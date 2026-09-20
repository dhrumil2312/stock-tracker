"""load_ticker / list_seed_tickers read seeded companies, bars, and moves."""
from __future__ import annotations

import pytest

from app.services.stocks import StockDataError
from app.services.tickers import list_seed_tickers, load_ticker

# NVDA is in the hardcoded seed list, so it is a valid ticker to load.
BARS = [
    {"date": "2026-09-17", "open": 95.0, "high": 101.0, "low": 94.0, "close": 100.0,
     "volume": 1000, "daily_return": 0.01},
    {"date": "2026-09-18", "open": 100.0, "high": 108.0, "low": 99.0, "close": 105.0,
     "volume": 2000, "daily_return": 0.05},
]
MOVES = [
    {"date": "2026-09-18", "pct_change": 0.05, "direction": "up", "close": 105.0,
     "prev_adj_close": 100.0, "volume": 2000},
]


def test_load_ticker_returns_meta_prices_and_moves(temp_db, seed_ticker) -> None:
    seed_ticker("NVDA", name="NVIDIA Corp.", industry="Semiconductors", bars=BARS, moves=MOVES)
    meta, prices, moves = load_ticker("nvda")  # lower-case is normalised

    assert meta["ticker"] == "NVDA"
    assert meta["industry"] == "Semiconductors"
    assert len(prices) == 2
    assert len(moves) == 1
    move = moves[0]
    assert move.direction == "up"
    assert move.pct_change == pytest.approx(5.0)  # stored as a fraction, surfaced as percent
    assert move.close == 105.0


def test_load_ticker_rejects_unseeded_symbol() -> None:
    with pytest.raises(StockDataError):
        load_ticker("NOTATICKER")


def test_load_ticker_without_stored_prices_raises(temp_db, seed_ticker) -> None:
    seed_ticker("NVDA", bars=[], moves=[])
    with pytest.raises(StockDataError):
        load_ticker("NVDA")


def test_list_seed_tickers_fills_meta_from_seed(temp_db, seed_ticker) -> None:
    seed_ticker("NVDA", name="NVIDIA Corp.", bars=BARS, moves=MOVES)
    summaries = list_seed_tickers()

    by_ticker = {s.ticker: s for s in summaries}
    assert "NVDA" in by_ticker
    # AAPL is seeded in metadata but has no DB row; name comes from the seed table.
    assert by_ticker["AAPL"].name == "Apple Inc."
