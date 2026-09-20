"""Pydantic schemas shared across the API."""
from __future__ import annotations

from datetime import date as Date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class PricePoint(BaseModel):
    date: Date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    adj_close: Optional[float] = None
    volume: int = 0
    pct_change: Optional[float] = Field(
        default=None, description="Close-over-close percent change vs previous trading day."
    )


class Article(BaseModel):
    title: str
    url: str
    source: Optional[str] = None
    published_at: Optional[Date] = None
    snippet: Optional[str] = None
    # How the article relates to the movement: company / industry / macro.
    category: Literal["company", "industry", "macro", "unknown"] = "unknown"


class Movement(BaseModel):
    date: Date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    adj_close: Optional[float] = None
    prev_adj_close: Optional[float] = None
    volume: Optional[int] = None
    pct_change: float
    direction: Literal["up", "down"]
    window_start: Optional[Date] = None
    window_end: Optional[Date] = None
    articles: list[Article] = Field(default_factory=list)


class TickerSummary(BaseModel):
    ticker: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None


class TickerResponse(BaseModel):
    ticker: str
    threshold: float
    currency: Optional[str] = None
    company_name: Optional[str] = None
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    prices: list[PricePoint]
    movements: list[Movement]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    ticker: str
    message: str
    history: list[ChatMessage] = Field(default_factory=list)
    model: Optional[str] = Field(
        default=None, description="OpenRouter model id; must be in the allow-list. Defaults to server default."
    )
    start: Optional[Date] = Field(
        default=None, description="Optional hint date (YYYY-MM-DD). Chat is not locked to it."
    )
    end: Optional[Date] = None
    threshold: Optional[float] = Field(
        default=None, description="Minimum |percent change| for moves included in chat context."
    )


class ChatResponse(BaseModel):
    reply: str
    grounded: bool = Field(
        default=True, description="True when the reply was produced by the live chat model over cached news."
    )
    model: Optional[str] = Field(default=None, description="Model id used to produce the reply.")


class ChatModelOption(BaseModel):
    id: str
    label: str
    short: Optional[str] = None
