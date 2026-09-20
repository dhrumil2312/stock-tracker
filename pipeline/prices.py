"""Download 30d daily bars, compute returns, persist bars and >=2% moves."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from db import utc_now
from pipeline.seed_tickers import company_meta

MOVE_THRESHOLD = 0.02
LOOKBACK_PERIOD = "1mo"

_COLUMN_MAP = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "adj close": "adj_close",
    "adj_close": "adj_close",
}


class DownloadError(RuntimeError):
    """yfinance returned nothing usable."""


def download_prices(tickers: list[str]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    if not tickers:
        return {}, []
    data = yf.download(
        tickers,
        period=LOOKBACK_PERIOD,
        interval="1d",
        auto_adjust=False,
        group_by="ticker",
        threads=True,
        progress=False,
    )
    if data is None or data.empty:
        raise DownloadError("yfinance returned no rows")

    frames: dict[str, pd.DataFrame] = {}
    failed: list[str] = []
    ticker_count = len(tickers)
    for ticker in tickers:
        frame = _ticker_frame(data, ticker, ticker_count=ticker_count)
        if frame is None:
            failed.append(ticker)
            continue
        frames[ticker] = frame
    if not frames:
        raise DownloadError("yfinance returned no per-ticker frames")
    return frames, failed


def persist_prices(
    conn: sqlite3.Connection,
    tickers: list[str],
    frames: dict[str, pd.DataFrame],
) -> tuple[int, int]:
    now = utc_now()
    for ticker in tickers:
        meta = company_meta(ticker)
        conn.execute(
            """
            INSERT INTO companies (ticker, name, exchange, sector, industry, in_universe, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(ticker) DO UPDATE SET
              name = excluded.name,
              exchange = excluded.exchange,
              sector = excluded.sector,
              industry = excluded.industry,
              updated_at = excluded.updated_at
            """,
            (
                ticker,
                meta["name"] if meta else ticker,
                meta["exchange"] if meta else None,
                meta["sector"] if meta else None,
                meta["industry"] if meta else None,
                now,
            ),
        )

    bars_upserted = 0
    moves_found = 0
    for ticker, frame in frames.items():
        bars, moves = bars_and_moves(ticker, frame)
        conn.execute("DELETE FROM price_bars WHERE ticker = ?", (ticker,))
        _upsert_bars(conn, bars)
        _upsert_moves(conn, moves)
        _drop_stale_moves(conn, ticker, [m["date"] for m in moves])
        bars_upserted += len(bars)
        moves_found += len(moves)
    return bars_upserted, moves_found


def bars_and_moves(ticker: str, frame: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = frame.sort_index()
    bars: list[dict[str, Any]] = []
    moves: list[dict[str, Any]] = []
    prev_adj: float | None = None
    prev_date: str | None = None

    for idx, row in ordered.iterrows():
        bar_date = _bar_date(idx)
        adj = _as_float(row.get("adj_close"))
        if adj is None:
            adj = _as_float(row.get("close"))
        close = _as_float(row.get("close", adj))
        if adj is None:
            prev_adj = None
            prev_date = None
            continue
        daily_return = None
        if prev_adj is not None and prev_adj != 0:
            daily_return = (adj - prev_adj) / prev_adj
        volume = _as_int(row.get("volume"))
        bars.append(
            {
                "ticker": ticker,
                "date": bar_date,
                "open": _as_float(row.get("open")),
                "high": _as_float(row.get("high")),
                "low": _as_float(row.get("low")),
                "close": close,
                "adj_close": adj,
                "volume": volume,
                "daily_return": daily_return,
            }
        )
        if daily_return is not None and abs(daily_return) >= MOVE_THRESHOLD and prev_date is not None:
            moves.append(
                {
                    "ticker": ticker,
                    "date": bar_date,
                    "pct_change": daily_return,
                    "direction": "up" if daily_return > 0 else "down",
                    "adj_close": adj,
                    "prev_adj_close": prev_adj,
                    "volume": volume,
                    "threshold": MOVE_THRESHOLD,
                    "window_start": prev_date,
                    "window_end": (
                        date.fromisoformat(bar_date) + timedelta(days=1)
                    ).isoformat(),
                }
            )
        prev_adj = adj
        prev_date = bar_date
    return bars, moves


def _ticker_frame(
    data: pd.DataFrame,
    ticker: str,
    *,
    ticker_count: int,
) -> pd.DataFrame | None:
    if isinstance(data.columns, pd.MultiIndex):
        levels = [set(data.columns.get_level_values(i)) for i in range(data.columns.nlevels)]
        if ticker in levels[0]:
            frame = data[ticker].copy()
        elif ticker in levels[-1]:
            frame = data.xs(ticker, axis=1, level=-1).copy()
        else:
            return None
    else:
        if ticker_count != 1:
            return None
        frame = data.copy()

    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [str(col[-1]) for col in frame.columns]
    frame = _normalize_columns(frame)
    if "close" not in frame.columns and "adj_close" not in frame.columns:
        return None
    if "adj_close" not in frame.columns:
        frame["adj_close"] = frame["close"]
    frame = frame.dropna(how="all")
    if frame.empty:
        return None
    return frame


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    mapping: dict[Any, str] = {}
    for col in frame.columns:
        key = str(col).strip().lower().replace("_", " ")
        mapped = _COLUMN_MAP.get(key)
        if mapped:
            mapping[col] = mapped
    return frame.rename(columns=mapping)


def _bar_date(idx: Any) -> str:
    ts = pd.Timestamp(idx)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.date().isoformat()


def _as_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    if number is None:
        return None
    return int(number)


def _upsert_bars(conn: sqlite3.Connection, bars: list[dict[str, Any]]) -> None:
    if not bars:
        return
    conn.executemany(
        """
        INSERT INTO price_bars (
          ticker, date, open, high, low, close, adj_close, volume, daily_return
        ) VALUES (
          :ticker, :date, :open, :high, :low, :close, :adj_close, :volume, :daily_return
        )
        ON CONFLICT(ticker, date) DO UPDATE SET
          open = excluded.open,
          high = excluded.high,
          low = excluded.low,
          close = excluded.close,
          adj_close = excluded.adj_close,
          volume = excluded.volume,
          daily_return = excluded.daily_return
        """,
        bars,
    )


def _upsert_moves(conn: sqlite3.Connection, moves: list[dict[str, Any]]) -> None:
    """Upsert on (ticker, date) so price_moves.id stays stable across re-runs.

    The news cache keys off move_id. Delete-and-replace would mint new ids and
    CASCADE-wipe cached articles, causing repeat provider calls for the same days.
    """
    if not moves:
        return
    conn.executemany(
        """
        INSERT INTO price_moves (
          ticker, date, pct_change, direction, adj_close, prev_adj_close,
          volume, threshold, window_start, window_end
        ) VALUES (
          :ticker, :date, :pct_change, :direction, :adj_close, :prev_adj_close,
          :volume, :threshold, :window_start, :window_end
        )
        ON CONFLICT(ticker, date) DO UPDATE SET
          pct_change = excluded.pct_change,
          direction = excluded.direction,
          adj_close = excluded.adj_close,
          prev_adj_close = excluded.prev_adj_close,
          volume = excluded.volume,
          threshold = excluded.threshold,
          window_start = excluded.window_start,
          window_end = excluded.window_end
        """,
        moves,
    )


def _drop_stale_moves(conn: sqlite3.Connection, ticker: str, keep_dates: list[str]) -> None:
    if not keep_dates:
        conn.execute("DELETE FROM price_moves WHERE ticker = ?", (ticker,))
        return
    placeholders = ",".join("?" * len(keep_dates))
    conn.execute(
        f"DELETE FROM price_moves WHERE ticker = ? AND date NOT IN ({placeholders})",
        [ticker, *keep_dates],
    )
