"""Read seeded companies, bars, and 2% moves from the shared SQLite database."""
from __future__ import annotations

from typing import Any

from db import connect
from pipeline.seed_tickers import company_meta, load_seed

from ..models import Movement, PricePoint, TickerSummary
from .stocks import StockDataError


def _resolved_meta(ticker: str, row: Any | None) -> dict[str, Any]:
    seed = company_meta(ticker)
    name = _row_text(row, "name")
    if not name or name == ticker:
        name = seed["name"] if seed else ticker
    return {
        "ticker": ticker,
        "name": name,
        "exchange": _row_text(row, "exchange") or (seed["exchange"] if seed else None),
        "sector": _row_text(row, "sector") or (seed["sector"] if seed else None),
        "industry": _row_text(row, "industry") or (seed["industry"] if seed else None),
    }


def list_seed_tickers() -> list[TickerSummary]:
    seed = load_seed()
    if not seed:
        return []

    placeholders = ",".join("?" * len(seed))
    conn = connect()
    try:
        rows = conn.execute(
            f"""
            SELECT ticker, name, exchange, sector, industry
            FROM companies
            WHERE ticker IN ({placeholders})
            """,
            seed,
        ).fetchall()
    finally:
        conn.close()

    by_ticker = {row["ticker"]: row for row in rows}
    summaries: list[TickerSummary] = []
    for ticker in seed:
        row = by_ticker.get(ticker)
        meta = _resolved_meta(ticker, row)
        summaries.append(
            TickerSummary(
                ticker=ticker,
                name=meta["name"],
                exchange=meta["exchange"],
                sector=meta["sector"],
                industry=meta["industry"],
            )
        )
    return summaries


def load_ticker(ticker: str) -> tuple[dict[str, Any], list[PricePoint], list[Movement]]:
    ticker = ticker.upper().strip()
    if ticker not in set(load_seed()):
        raise StockDataError(f"'{ticker}' is not in the seeded ticker list.")

    conn = connect()
    try:
        company = conn.execute(
            """
            SELECT ticker, name, exchange, sector, industry
            FROM companies
            WHERE ticker = ?
            """,
            (ticker,),
        ).fetchone()
        if company is None:
            raise StockDataError(f"No stored data for '{ticker}'. Run the price pipeline.")

        bar_rows = conn.execute(
            """
            SELECT date, open, high, low, close, adj_close, volume, daily_return
            FROM price_bars
            WHERE ticker = ?
            ORDER BY date
            """,
            (ticker,),
        ).fetchall()
        if not bar_rows:
            raise StockDataError(f"No stored prices for '{ticker}'. Run the price pipeline.")

        move_rows = conn.execute(
            """
            SELECT
              m.date,
              m.pct_change,
              m.direction,
              m.adj_close,
              m.prev_adj_close,
              m.volume AS move_volume,
              m.window_start,
              m.window_end,
              b.open,
              b.high,
              b.low,
              b.close,
              b.volume AS bar_volume
            FROM price_moves m
            LEFT JOIN price_bars b
              ON b.ticker = m.ticker AND b.date = m.date
            WHERE m.ticker = ?
            ORDER BY m.date
            """,
            (ticker,),
        ).fetchall()
    finally:
        conn.close()

    meta = _resolved_meta(ticker, company)
    return meta, [_price_point(row) for row in bar_rows], [_movement(row) for row in move_rows]


def _price_point(row: Any) -> PricePoint:
    close = _row_float(row, "close")
    adj = _row_float(row, "adj_close")
    if close is None:
        close = adj
    if close is None:
        raise StockDataError("Stored price bar is missing close.")
    return PricePoint(
        date=row["date"],
        open=_row_float(row, "open"),
        high=_row_float(row, "high"),
        low=_row_float(row, "low"),
        close=round(close, 4),
        adj_close=_round_price(adj) if adj is not None else None,
        volume=_row_int(row, "volume") or 0,
        pct_change=_as_percent(row["daily_return"]),
    )


def _movement(row: Any) -> Movement:
    close = _row_float(row, "close")
    adj = _row_float(row, "adj_close")
    if close is None:
        close = adj
    if close is None:
        raise StockDataError("Stored move is missing close.")
    volume = _row_int(row, "bar_volume")
    if volume is None:
        volume = _row_int(row, "move_volume")
    pct = _as_percent(row["pct_change"])
    if pct is None:
        raise StockDataError("Stored move is missing pct_change.")
    return Movement(
        date=row["date"],
        open=_round_price(_row_float(row, "open")),
        high=_round_price(_row_float(row, "high")),
        low=_round_price(_row_float(row, "low")),
        close=round(close, 4),
        adj_close=_round_price(adj) if adj is not None else None,
        prev_adj_close=_round_price(_row_float(row, "prev_adj_close")),
        volume=volume,
        pct_change=pct,
        direction=row["direction"],
        window_start=row["window_start"],
        window_end=row["window_end"],
    )


def _as_percent(value: Any) -> float | None:
    number = _as_float(value)
    if number is None:
        return None
    return round(number * 100.0, 3)


def _round_price(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def _row_text(row: Any, key: str) -> str | None:
    if row is None:
        return None
    value = row[key]
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _row_float(row: Any, key: str) -> float | None:
    return _as_float(row[key])


def _row_int(row: Any, key: str) -> int | None:
    number = _as_float(row[key])
    if number is None:
        return None
    return int(number)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
