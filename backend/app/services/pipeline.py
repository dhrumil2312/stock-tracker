"""Assemble the full picture for a ticker: prices, movements, and attached news.

Shared by both the /tickers and /chat routers so they agree on the data.
"""
from __future__ import annotations

from datetime import date as Date
from typing import Literal

from ..config import settings
from ..models import Movement, PricePoint, TickerResponse
from .news_cache import attach_news
from .tickers import load_ticker

NewsCategory = Literal["company", "industry", "macro"]


def build_ticker_response(
    ticker: str,
    include_news: bool = False,
    start: Date | None = None,
    end: Date | None = None,
    threshold: float | None = None,
    direction: Literal["up", "down"] | None = None,
    news_category: NewsCategory | None = None,
) -> TickerResponse:
    ticker = ticker.upper().strip()
    meta, points, movements = load_ticker(ticker)
    thresh = settings.default_movement_threshold if threshold is None else threshold
    points, movements = _apply_filters(points, movements, start, end, thresh, direction)

    if include_news and movements:
        attach_news(
            ticker,
            meta.get("name"),
            meta.get("industry") or meta.get("sector"),
            movements,
            category=news_category,
        )

    return TickerResponse(
        ticker=ticker,
        threshold=thresh,
        company_name=meta.get("name"),
        exchange=meta.get("exchange"),
        sector=meta.get("sector"),
        industry=meta.get("industry"),
        prices=points,
        movements=movements,
    )


def _apply_filters(
    prices: list[PricePoint],
    movements: list[Movement],
    start: Date | None,
    end: Date | None,
    threshold: float,
    direction: Literal["up", "down"] | None,
) -> tuple[list[PricePoint], list[Movement]]:
    if start is not None:
        prices = [p for p in prices if p.date >= start]
        movements = [m for m in movements if m.date >= start]
    if end is not None:
        prices = [p for p in prices if p.date <= end]
        movements = [m for m in movements if m.date <= end]
    movements = [m for m in movements if abs(m.pct_change) >= threshold]
    if direction is not None:
        movements = [m for m in movements if m.direction == direction]
    return prices, movements
