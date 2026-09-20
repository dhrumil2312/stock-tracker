"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import connect, migrate

from .config import settings
from .routers import chat, tickers
from .services.news import get_news_provider


@asynccontextmanager
async def lifespan(_app: FastAPI):
    conn = connect()
    try:
        migrate(conn)
    finally:
        conn.close()
    yield


app = FastAPI(
    title="Volatility Tracker",
    description="Flags days a ticker moved more than 2% and lets you chat over the details.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tickers.router)
app.include_router(chat.router)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    provider = get_news_provider()
    return {
        "status": "ok",
        "news_provider": provider.name,
        "chat": f"openrouter:{settings.chat_model}" if settings.openrouter_api_key else "fallback",
    }
