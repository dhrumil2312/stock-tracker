"""Ticker search and detail: seed list, prices, and days that moved more than 2%."""
from __future__ import annotations

from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..models import TickerResponse, TickerSummary
from ..services.pipeline import build_ticker_response
from ..services.stocks import StockDataError
from ..services.tickers import list_seed_tickers

router = APIRouter(prefix="/api/tickers", tags=["tickers"])


@router.get("", response_model=list[TickerSummary])
def get_tickers() -> list[TickerSummary]:
    return list_seed_tickers()


@router.get("/{ticker}", response_model=TickerResponse)
def get_ticker(
    ticker: str,
    include_news: bool = Query(False, description="Attach cached news. Off by default; set true with start/end for one day."),
    start: Date | None = Query(None, description="Inclusive start date (YYYY-MM-DD)."),
    end: Date | None = Query(None, description="Inclusive end date (YYYY-MM-DD)."),
    threshold: float | None = Query(None, description="Minimum |percent change|. Defaults to 2."),
    direction: Literal["up", "down"] | None = Query(None),
    news_category: Literal["company", "industry", "macro"] | None = Query(
        None, description="If set, only return articles of this relevance level."
    ),
) -> TickerResponse:
    try:
        return build_ticker_response(
            ticker,
            include_news=include_news,
            start=start,
            end=end,
            threshold=threshold,
            direction=direction,
            news_category=news_category,
        )
    except StockDataError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to build ticker data: {exc}")
