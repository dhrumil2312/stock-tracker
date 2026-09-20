"""Router-level tests through the FastAPI app (TestClient triggers migrations)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import CHAT_MODELS, settings
from app.main import app

BARS = [
    {"date": "2026-09-17", "close": 100.0, "daily_return": 0.01},
    {"date": "2026-09-18", "close": 105.0, "daily_return": 0.05},
]
MOVES = [
    {"date": "2026-09-18", "pct_change": 0.05, "direction": "up", "close": 105.0},
]


@pytest.fixture()
def client(temp_db, monkeypatch: pytest.MonkeyPatch):
    # Keep chat offline: no key means the deterministic fallback answers.
    monkeypatch.setattr(settings, "openrouter_api_key", None)
    with TestClient(app) as c:  # `with` runs the lifespan, migrating temp_db
        yield c


def test_health_reports_provider(client) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_chat_models_returns_allow_list(client) -> None:
    resp = client.get("/api/chat/models")
    assert resp.status_code == 200
    assert [m["id"] for m in resp.json()] == [m["id"] for m in CHAT_MODELS]


def test_get_tickers_lists_seed(client, seed_ticker) -> None:
    seed_ticker("NVDA", name="NVIDIA Corp.", bars=BARS, moves=MOVES)
    resp = client.get("/api/tickers")
    assert resp.status_code == 200
    assert any(t["ticker"] == "NVDA" for t in resp.json())


def test_get_ticker_detail(client, seed_ticker) -> None:
    seed_ticker("NVDA", name="NVIDIA Corp.", bars=BARS, moves=MOVES)
    resp = client.get("/api/tickers/NVDA")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "NVDA"
    assert len(body["movements"]) == 1
    assert body["movements"][0]["articles"] == []


def test_get_ticker_news_for_day(client, seed_ticker) -> None:
    seed_ticker("NVDA", name="NVIDIA Corp.", bars=BARS, moves=MOVES)
    resp = client.get(
        "/api/tickers/NVDA",
        params={"include_news": True, "start": "2026-09-18", "end": "2026-09-18"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["movements"]) == 1
    assert body["movements"][0]["date"] == "2026-09-18"


def test_get_ticker_unknown_is_404(client) -> None:
    resp = client.get("/api/tickers/NOTATICKER")
    assert resp.status_code == 404


def test_post_chat_rejects_empty_message(client) -> None:
    resp = client.post("/api/chat", json={"ticker": "NVDA", "message": "   ", "start": "2026-09-18"})
    assert resp.status_code == 422


def test_post_chat_allows_missing_date(client, seed_ticker) -> None:
    seed_ticker("NVDA", name="NVIDIA Corp.", bars=BARS, moves=MOVES)
    resp = client.post("/api/chat", json={"ticker": "NVDA", "message": "why?"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")


def test_post_chat_rejects_unlisted_model(client, seed_ticker) -> None:
    seed_ticker("NVDA", name="NVIDIA Corp.", bars=BARS, moves=MOVES)
    resp = client.post(
        "/api/chat",
        json={"ticker": "NVDA", "message": "why?", "start": "2026-09-18", "model": "evil/model"},
    )
    assert resp.status_code == 400


def test_post_chat_unknown_ticker_is_404(client) -> None:
    resp = client.post(
        "/api/chat", json={"ticker": "NOTATICKER", "message": "why?", "start": "2026-09-18"}
    )
    assert resp.status_code == 404


def test_post_chat_returns_fallback_reply(client, seed_ticker) -> None:
    seed_ticker("NVDA", name="NVIDIA Corp.", bars=BARS, moves=MOVES)
    resp = client.post(
        "/api/chat",
        json={"ticker": "NVDA", "message": "why did it move?"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert "Biggest flagged move" in body
    assert "event: done" in body
    assert '"grounded": false' in body
