"""CLI: scan seed prices and materialize the tradeable universe."""

from __future__ import annotations

import json
import sqlite3
import sys

from db import connect, migrate, utc_now
from pipeline.prices import DownloadError, download_prices, persist_prices
from pipeline.seed_tickers import load_seed
from pipeline.universe import refresh_universe


def main() -> int:
    seed = load_seed()
    conn = connect()
    migrate(conn)

    started = utc_now()
    cursor = conn.execute(
        """
        INSERT INTO pipeline_runs (started_at, status, seed_count)
        VALUES (?, 'running', ?)
        """,
        (started, len(seed)),
    )
    run_id = cursor.lastrowid
    conn.commit()

    print(f"Seed: {len(seed)} tickers")
    try:
        frames, failed = download_prices(seed)
    except DownloadError as exc:
        _finish_run(conn, run_id, "failed", 0, 0, 0, str(exc))
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1

    try:
        bars_upserted, moves_found = persist_prices(conn, seed, frames)
        universe = refresh_universe(conn, seed)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        _finish_run(conn, run_id, "failed", 0, 0, 0, str(exc))
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1

    status = "partial" if failed else "success"
    error = json.dumps({"failed": failed}) if failed else None
    _finish_run(conn, run_id, status, bars_upserted, moves_found, len(universe), error)

    print(f"Failed: {', '.join(failed) if failed else '(none)'}")
    print(f"Bars upserted: {bars_upserted}")
    print(f"Moves: {moves_found}")
    print(f"Universe ({len(universe)}): {', '.join(universe) if universe else '(empty)'}")
    _print_moves(conn, universe)
    conn.close()
    return 0


def _finish_run(
    conn: sqlite3.Connection,
    run_id: int | None,
    status: str,
    bars_upserted: int,
    moves_found: int,
    universe_count: int,
    error: str | None,
) -> None:
    conn.execute(
        """
        UPDATE pipeline_runs
        SET finished_at = ?,
            status = ?,
            bars_upserted = ?,
            moves_found = ?,
            universe_count = ?,
            error = ?
        WHERE id = ?
        """,
        (utc_now(), status, bars_upserted, moves_found, universe_count, error, run_id),
    )
    conn.commit()


def _print_moves(conn: sqlite3.Connection, universe: list[str]) -> None:
    for ticker in universe:
        rows = conn.execute(
            """
            SELECT date, pct_change
            FROM price_moves
            WHERE ticker = ?
            ORDER BY date
            """,
            (ticker,),
        ).fetchall()
        print(f"\n  {ticker}  ({len(rows)})")
        for row in rows:
            print(f"    {row['date']}  {row['pct_change']:+.2%}")


if __name__ == "__main__":
    raise SystemExit(main())
