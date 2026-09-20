"""Mark seed tickers with at least one major move as the tradeable universe."""

from __future__ import annotations

import sqlite3

MIN_LAST_PRICE = 5.0
MIN_AVG_VOLUME = 100_000


def refresh_universe(
    conn: sqlite3.Connection,
    seed: list[str],
    min_last_price: float = MIN_LAST_PRICE,
    min_avg_volume: float = MIN_AVG_VOLUME,
) -> list[str]:
    conn.execute("UPDATE companies SET in_universe = 0")
    if not seed:
        return []

    placeholders = ",".join("?" * len(seed))
    rows = conn.execute(
        f"""
        SELECT
          m.ticker,
          (
            SELECT adj_close
            FROM price_bars
            WHERE ticker = m.ticker
            ORDER BY date DESC
            LIMIT 1
          ) AS last_price,
          (
            SELECT AVG(volume)
            FROM price_bars
            WHERE ticker = m.ticker
          ) AS avg_volume
        FROM (
          SELECT DISTINCT ticker
          FROM price_moves
          WHERE ticker IN ({placeholders})
        ) AS m
        """,
        seed,
    ).fetchall()

    universe: list[str] = []
    for row in rows:
        ticker = row["ticker"]
        last_price = row["last_price"]
        avg_volume = row["avg_volume"]
        if last_price is None or last_price < min_last_price:
            continue
        if avg_volume is None or avg_volume < min_avg_volume:
            continue
        conn.execute("UPDATE companies SET in_universe = 1 WHERE ticker = ?", (ticker,))
        universe.append(ticker)
    return sorted(universe)
