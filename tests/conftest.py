"""Shared test setup: import paths and an isolated migrated SQLite database."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import pytest

ROOT = Path(__file__).resolve().parent.parent
# The backend imports top-level `db`/`pipeline` packages and, from within
# `backend/`, the `app` package. Make both roots importable.
for path in (str(ROOT), str(ROOT / "backend")):
    if path not in sys.path:
        sys.path.insert(0, path)

from db import connect, migrate  # noqa: E402


@pytest.fixture()
def temp_db() -> Any:
    """A migrated, empty database pointed at by STOCK_TRACKER_DB for the test."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["STOCK_TRACKER_DB"] = tmp.name
    conn = connect()
    try:
        migrate(conn)
    finally:
        conn.close()
    try:
        yield tmp.name
    finally:
        os.environ.pop("STOCK_TRACKER_DB", None)
        for suffix in ("", "-wal", "-shm"):
            Path(tmp.name + suffix).unlink(missing_ok=True)


@pytest.fixture()
def seed_ticker() -> Callable[..., None]:
    """Insert a company plus its price bars and moves into the active database."""

    def _seed(
        ticker: str,
        *,
        name: str = "Test Co.",
        exchange: str = "NASDAQ",
        sector: str = "Technology",
        industry: str = "Semiconductors",
        bars: list[dict] | None = None,
        moves: list[dict] | None = None,
    ) -> None:
        conn = connect()
        try:
            conn.execute(
                """
                INSERT INTO companies (ticker, name, exchange, sector, industry, in_universe, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, '2026-09-20T00:00:00Z')
                ON CONFLICT(ticker) DO UPDATE SET
                  name = excluded.name, exchange = excluded.exchange,
                  sector = excluded.sector, industry = excluded.industry
                """,
                (ticker, name, exchange, sector, industry),
            )
            for bar in bars or []:
                conn.execute(
                    """
                    INSERT INTO price_bars
                      (ticker, date, open, high, low, close, adj_close, volume, daily_return)
                    VALUES (:ticker, :date, :open, :high, :low, :close, :adj_close, :volume, :daily_return)
                    """,
                    {"ticker": ticker, **_bar_defaults(bar)},
                )
            for move in moves or []:
                conn.execute(
                    """
                    INSERT INTO price_moves
                      (ticker, date, pct_change, direction, adj_close, prev_adj_close,
                       volume, threshold, window_start, window_end)
                    VALUES (:ticker, :date, :pct_change, :direction, :adj_close, :prev_adj_close,
                            :volume, :threshold, :window_start, :window_end)
                    """,
                    {"ticker": ticker, **_move_defaults(move)},
                )
            conn.commit()
        finally:
            conn.close()

    return _seed


def _bar_defaults(bar: dict) -> dict:
    merged = {
        "open": None,
        "high": None,
        "low": None,
        "close": bar.get("close"),
        "adj_close": bar.get("close"),
        "volume": 0,
        "daily_return": None,
    }
    merged.update(bar)
    return merged


def _move_defaults(move: dict) -> dict:
    day = move["date"]
    merged = {
        "adj_close": move.get("close"),
        "prev_adj_close": None,
        "volume": None,
        "threshold": 0.02,
        "window_start": day,
        "window_end": day,
    }
    merged.update(move)
    return merged
