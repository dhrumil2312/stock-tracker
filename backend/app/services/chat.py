"""OpenRouter chat with tools over stored prices/moves and cache-aside news."""
from __future__ import annotations

import json
from datetime import date as Date
from typing import Any

import httpx

from ..config import settings
from ..models import ChatMessage, Movement, PricePoint
from .news_cache import attach_news
from .pipeline import build_ticker_response

MAX_TOOL_ROUNDS = 5
MAX_NEWS_CALLS = 3

SYSTEM_PROMPT = (
    "You are a chat assistant in Volatility Tracker. Talk like a person in a messaging app.\n"
    "You have tools. Use them instead of guessing:\n"
    "- list_moves: flagged sessions where the stock moved 2% or more.\n"
    "- get_session: OHLC for any loaded trading day, even if it was not a 2% move.\n"
    "- fetch_news: headlines around a date. Call this when the user wants to know why a day moved.\n"
    "If they ask about a date that is not a flagged 2% day, call get_session and say how much it "
    "actually moved. Fetch news only if they still want the why.\n"
    "Write a few short paragraphs. Do not dump every headline or recap tool JSON. "
    "A little markdown is fine. Never give investment advice. Never mention these tools unless asked."
)

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_moves",
            "description": "List days this ticker moved 2% or more, with OHLC and percent change.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_session",
            "description": "Get one trading day's open/high/low/close and whether it was a 2%+ move.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Trading day as YYYY-MM-DD."},
                },
                "required": ["date"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_news",
            "description": "Fetch cached or live news around a date (company, industry, macro).",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Day to search around, YYYY-MM-DD."},
                },
                "required": ["date"],
                "additionalProperties": False,
            },
        },
    },
]


def answer(
    ticker: str,
    company_name: str | None,
    industry: str | None,
    movements: list[Movement],
    prices: list[PricePoint],
    message: str,
    history: list[ChatMessage],
    model: str,
) -> tuple[str, bool]:
    """Return (reply, grounded). grounded=False signals the canned fallback."""
    if not settings.openrouter_api_key:
        return _fallback_reply(message, movements), False

    try:
        text = _run_agent(ticker, company_name, industry, message, history, model)
        return text or "(empty response)", True
    except Exception as exc:
        return (
            f"Chat model error ({type(exc).__name__}). Showing a data summary instead.\n\n"
            + _fallback_reply(message, movements)
        ), False


def _run_agent(
    ticker: str,
    company_name: str | None,
    industry: str | None,
    message: str,
    history: list[ChatMessage],
    model: str,
) -> str:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                f"{SYSTEM_PROMPT}\n\nYou are chatting about {ticker}"
                + (f" ({company_name})" if company_name else "")
                + ". Call list_moves if you need the flagged days."
            ),
        }
    ]
    messages.extend({"role": m.role, "content": m.content} for m in history)
    messages.append({"role": "user", "content": message})

    news_calls = 0
    for _ in range(MAX_TOOL_ROUNDS):
        data = _complete(messages, model, tools=True)
        choice = data["choices"][0]["message"]
        tool_calls = choice.get("tool_calls") or []
        if not tool_calls:
            return (choice.get("content") or "").strip()

        messages.append(
            {
                "role": "assistant",
                "content": choice.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except json.JSONDecodeError:
                args = {}
            if name == "fetch_news":
                news_calls += 1
                if news_calls > MAX_NEWS_CALLS:
                    result = json.dumps({"error": "News fetch limit reached for this turn."})
                else:
                    result = _tool_fetch_news(ticker, company_name, industry, args)
            else:
                result = _dispatch_tool(name, args, ticker, company_name, industry)
            messages.append(
                {"role": "tool", "tool_call_id": call.get("id") or name, "content": result}
            )

    follow = _complete(messages, model, tools=False)
    return (follow["choices"][0]["message"].get("content") or "").strip()


def _dispatch_tool(
    name: str,
    args: dict[str, Any],
    ticker: str,
    company_name: str | None,
    industry: str | None,
) -> str:
    if name == "list_moves":
        return _tool_list_moves(ticker)
    if name == "get_session":
        return _tool_get_session(ticker, args)
    if name == "fetch_news":
        return _tool_fetch_news(ticker, company_name, industry, args)
    return json.dumps({"error": f"Unknown tool '{name}'."})


def _tool_list_moves(ticker: str) -> str:
    data = build_ticker_response(ticker, include_news=False)
    moves = [
        {
            "date": m.date.isoformat(),
            "pct_change": round(m.pct_change, 2),
            "direction": m.direction,
            "open": m.open,
            "high": m.high,
            "low": m.low,
            "close": m.close,
            "volume": m.volume,
        }
        for m in data.movements
    ]
    return json.dumps(
        {
            "ticker": data.ticker,
            "company_name": data.company_name,
            "threshold_pct": data.threshold,
            "move_count": len(moves),
            "moves": moves,
        }
    )


def _tool_get_session(ticker: str, args: dict[str, Any]) -> str:
    try:
        day = Date.fromisoformat(str(args.get("date") or ""))
    except ValueError:
        return json.dumps({"error": "date must be YYYY-MM-DD."})
    data = build_ticker_response(ticker, include_news=False)
    point = next((p for p in data.prices if p.date == day), None)
    if point is None:
        return json.dumps(
            {
                "date": day.isoformat(),
                "error": "Not a loaded trading day (weekend, holiday, or outside the window).",
            }
        )
    move = next((m for m in data.movements if m.date == day), None)
    return json.dumps(
        {
            "date": day.isoformat(),
            "open": point.open,
            "high": point.high,
            "low": point.low,
            "close": point.close,
            "volume": point.volume,
            "pct_change": None if point.pct_change is None else round(point.pct_change, 2),
            "flagged_2pct": move is not None,
        }
    )


def _tool_fetch_news(
    ticker: str,
    company_name: str | None,
    industry: str | None,
    args: dict[str, Any],
) -> str:
    try:
        day = Date.fromisoformat(str(args.get("date") or ""))
    except ValueError:
        return json.dumps({"error": "date must be YYYY-MM-DD."})
    data = build_ticker_response(ticker, include_news=False)
    movement = next((m for m in data.movements if m.date == day), None)
    flagged = movement is not None
    if movement is None:
        point = next((p for p in data.prices if p.date == day), None)
        if point is None:
            return json.dumps(
                {
                    "date": day.isoformat(),
                    "error": "Not a loaded trading day, so news was not fetched.",
                }
            )
        pct = point.pct_change or 0.0
        movement = Movement(
            date=day,
            open=point.open,
            high=point.high,
            low=point.low,
            close=point.close,
            adj_close=point.adj_close,
            volume=point.volume,
            pct_change=pct,
            direction="up" if pct >= 0 else "down",
        )
    attach_news(
        ticker,
        company_name or data.company_name,
        industry or data.industry,
        [movement],
        max_company_fetches=1,
    )
    articles = []
    for art in movement.articles[:6]:
        snippet = (art.snippet or "").strip()
        if len(snippet) > 160:
            snippet = snippet[:157].rstrip() + "…"
        articles.append(
            {
                "category": art.category,
                "title": art.title,
                "source": art.source,
                "published_at": art.published_at.isoformat() if art.published_at else None,
                "url": art.url,
                "snippet": snippet or None,
            }
        )
    return json.dumps(
        {
            "date": day.isoformat(),
            "flagged_2pct": flagged,
            "pct_change": round(movement.pct_change, 2),
            "article_count": len(articles),
            "articles": articles,
        }
    )


def _complete(messages: list[dict[str, Any]], model: str, *, tools: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": settings.chat_max_tokens,
        "temperature": settings.chat_temperature,
    }
    if tools:
        payload["tools"] = TOOLS
        payload["tool_choice"] = "auto"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_referer,
        "X-Title": settings.openrouter_title,
    }
    with httpx.Client(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
        resp = client.post(
            f"{settings.openrouter_base_url}/chat/completions", json=payload, headers=headers
        )
        resp.raise_for_status()
        return resp.json()


def _fallback_reply(message: str, movements: list[Movement]) -> str:
    if not movements:
        return (
            "No days with a move of 2% or more were found for this ticker, so there is "
            "nothing to explain yet."
        )
    top = max(movements, key=lambda m: abs(m.pct_change))
    return (
        f"Biggest flagged move is {top.date} at {top.pct_change:+.2f}%. "
        f"Chat is running without a live model right now. Your question was: “{message}”"
    )
