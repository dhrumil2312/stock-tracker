"""OpenRouter chat with tools over stored prices/moves and cache-aside news."""
from __future__ import annotations

from collections.abc import Iterator
import json
import logging
import re
import time
from datetime import date as Date
from typing import Any

import httpx

from ..config import settings
from ..models import ChatMessage, Movement
from .news_cache import attach_news
from .pipeline import build_ticker_response

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
MAX_NEWS_CALLS = 3

SYSTEM_PROMPT = (
    "You are a chat assistant in Volatility Tracker. Talk like a person in a messaging app.\n"
    "You have tools. Use them instead of guessing:\n"
    "- list_moves: flagged sessions where the stock moved 2% or more.\n"
    "- get_session: OHLC for any loaded trading day, even if it was not a 2% move.\n"
    "- fetch_news: headlines around a date. Call this when the user wants to know why a day moved.\n"
    "If they ask what drove the biggest move, call list_moves, pick the largest |pct_change|, "
    "fetch_news for that date, and answer — do not ask them for the date. "
    "If they ask about a date that is not a flagged 2% day, call get_session and say how much it "
    "actually moved. Fetch news only if they still want the why.\n"
    "When the user names a month and day without a year, use the year of the loaded price window — "
    "never last year. Always call get_session before saying a day was closed; do not invent holidays.\n"
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
                    "date": {
                        "type": "string",
                        "description": "Trading day as YYYY-MM-DD in the loaded window (not a prior year).",
                    },
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
                    "date": {
                        "type": "string",
                        "description": "Day to search around, YYYY-MM-DD in the loaded window.",
                    },
                },
                "required": ["date"],
                "additionalProperties": False,
            },
        },
    },
]


def iter_chat_sse(
    ticker: str,
    company_name: str | None,
    industry: str | None,
    movements: list[Movement],
    message: str,
    history: list[ChatMessage],
    model: str,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (event, payload) pairs for an SSE chat response."""
    yield ("status", {"message": "Thinking…"})
    if not settings.openrouter_api_key:
        yield ("token", {"text": _fallback_reply(message, movements, no_key=True)})
        yield ("done", {"grounded": False, "model": None})
        return
    try:
        yield from _run_agent_sse(ticker, company_name, industry, message, history, model)
    except Exception as exc:
        log.exception("chat agent failed for %s", ticker)
        yield (
            "token",
            {
                "text": (
                    f"I hit a model connection error ({type(exc).__name__}) and could not finish that answer. "
                    "Try once more.\n\n" + _fallback_reply(message, movements)
                )
            },
        )
        yield ("done", {"grounded": False, "model": model})


def _run_agent_sse(
    ticker: str,
    company_name: str | None,
    industry: str | None,
    message: str,
    history: list[ChatMessage],
    model: str,
) -> Iterator[tuple[str, dict[str, Any]]]:
    data = build_ticker_response(ticker, include_news=False)
    window = _window_blurb(data.prices, data.movements)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                f"{SYSTEM_PROMPT}\n\nYou are chatting about {ticker}"
                + (f" ({company_name})" if company_name else "")
                + f". Today is {Date.today().isoformat()}. {window} "
                "Call list_moves if you need the flagged days."
            ),
        }
    ]
    messages.extend({"role": m.role, "content": m.content} for m in history)
    messages.append({"role": "user", "content": message})

    news_calls = 0
    for round_i in range(MAX_TOOL_ROUNDS):
        content, tool_calls = _complete(messages, model, tools=True)
        if not tool_calls:
            yield ("token", {"text": content.strip() or _final_text(messages, model)})
            yield ("done", {"grounded": True, "model": model})
            return

        messages.append({"role": "assistant", "content": content or "", "tool_calls": tool_calls})
        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except json.JSONDecodeError:
                args = {}
            yield ("status", {"message": _tool_status(name, args)})
            if name == "fetch_news":
                news_calls += 1
                if news_calls > MAX_NEWS_CALLS:
                    result = json.dumps({"error": "News fetch limit reached for this turn."})
                else:
                    result = _tool_fetch_news(ticker, company_name, industry, args)
            else:
                result = _dispatch_tool(name, args, ticker, company_name, industry)
            messages.append({"role": "tool", "tool_call_id": call.get("id") or name, "content": result})
        if round_i == MAX_TOOL_ROUNDS - 1:
            break

    yield ("token", {"text": _final_text(messages, model)})
    yield ("done", {"grounded": True, "model": model})


def _tool_status(name: str, args: dict[str, Any]) -> str:
    day = str(args.get("date") or "").strip()
    if name == "list_moves":
        return "Checking flagged move days…"
    if name == "get_session":
        return f"Looking up {day or 'that session'}…"
    if name == "fetch_news":
        return f"Fetching news for {day or 'that day'}…"
    return "Working…"


def _window_blurb(prices: list, movements: list[Movement]) -> str:
    if not prices:
        return "No trading days are loaded for this ticker."
    first, last = prices[0].date.isoformat(), prices[-1].date.isoformat()
    if not movements:
        return f"Loaded sessions run {first} through {last}. No 2%+ days in that window."
    flagged = ", ".join(f"{m.date.isoformat()} {m.pct_change:+.2f}%" for m in movements)
    return f"Loaded sessions run {first} through {last}. Flagged 2%+ days: {flagged}."


_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _parse_month_day(raw: str) -> tuple[int, int, int | None] | None:
    text = re.sub(r"[.,]", " ", str(raw or "")).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return None
    try:
        parsed = Date.fromisoformat(text[:10])
        return parsed.month, parsed.day, parsed.year
    except ValueError:
        pass
    numeric = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", text)
    if numeric:
        month, day, year_s = int(numeric.group(1)), int(numeric.group(2)), numeric.group(3)
        year = int(year_s) if year_s else None
        if year is not None and year < 100:
            year += 2000
        return _validated_mdy(month, day, year)
    named = re.fullmatch(
        r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
        r"dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?",
        text,
        re.I,
    )
    if not named:
        return None
    month = _MONTHS.get(named.group(1).lower())
    if month is None:
        return None
    year = int(named.group(3)) if named.group(3) else None
    return _validated_mdy(month, int(named.group(2)), year)


def _validated_mdy(month: int, day: int, year: int | None) -> tuple[int, int, int | None] | None:
    probe = year or 2024
    try:
        Date(probe, month, day)
    except ValueError:
        return None
    return month, day, year


def _resolve_loaded_date(
    month: int, day: int, year: int | None, prices: list
) -> tuple[Date | None, bool]:
    loaded = [p.date for p in prices]
    same = [d for d in loaded if d.month == month and d.day == day]
    if year is None:
        if same:
            return max(same), False
        if not loaded:
            return None, False
        try:
            return Date(max(d.year for d in loaded), month, day), False
        except ValueError:
            return None, False
    try:
        requested = Date(year, month, day)
    except ValueError:
        return None, False
    if requested in loaded:
        return requested, False
    if same:
        return min(same, key=lambda d: (abs(d.year - year), -d.year)), True
    return requested, False


def _tool_date(raw: Any, prices: list) -> tuple[Date | None, dict[str, Any] | None]:
    parsed = _parse_month_day(str(raw or ""))
    if parsed is None:
        return None, {"error": "date must be YYYY-MM-DD or a month and day like 'September 1'."}
    month, day, year = parsed
    resolved, remapped = _resolve_loaded_date(month, day, year, prices)
    if resolved is None:
        return None, {"error": "Could not parse that date."}
    return resolved, {"remapped_from_year": year} if remapped else None


def _missing_session_error(day: Date, prices: list) -> str:
    loaded = [p.date for p in prices]
    nearest = sorted(loaded, key=lambda d: abs((d - day).days))[:4]
    payload: dict[str, Any] = {
        "date": day.isoformat(),
        "weekday": day.strftime("%A"),
        "error": "No price bar for this calendar date in the loaded window.",
        "window_start": loaded[0].isoformat() if loaded else None,
        "window_end": loaded[-1].isoformat() if loaded else None,
        "nearest_loaded": [d.isoformat() for d in nearest],
    }
    return json.dumps(payload)


def _final_text(messages: list[dict[str, Any]], model: str) -> str:
    content, _ = _complete(messages, model, tools=False)
    return content.strip() or "(empty response)"


def _complete(messages: list[dict[str, Any]], model: str, *, tools: bool) -> tuple[str, list[dict[str, Any]]]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": settings.chat_max_tokens,
        "temperature": settings.chat_temperature,
        # DeepSeek V4.1 Flash otherwise spends the token budget on hidden reasoning
        # and returns empty content (or drops the HTTP connection mid-stream).
        "reasoning": {"enabled": False},
    }
    if tools:
        payload["tools"] = TOOLS
        payload["tool_choice"] = "auto"
    data = _post_openrouter(payload)
    choice = (data.get("choices") or [{}])[0].get("message") or {}
    return _message_text(choice.get("content")), list(choice.get("tool_calls") or [])


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") in (None, "text"):
                parts.append(str(item.get("text") or ""))
        return "".join(parts).strip()
    return ""


def _post_openrouter(payload: dict[str, Any]) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=httpx.Timeout(90.0, connect=15.0), http2=False) as client:
                resp = client.post(
                    f"{settings.openrouter_base_url}/chat/completions",
                    json=payload,
                    headers=_openrouter_headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError, httpx.TimeoutException) as exc:
            last_exc = exc
            log.warning("OpenRouter attempt %s/3 failed: %s", attempt + 1, exc)
            time.sleep(0.5 * (attempt + 1))
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code >= 500 and attempt < 2:
                last_exc = exc
                log.warning("OpenRouter HTTP %s on attempt %s/3", exc.response.status_code, attempt + 1)
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
    assert last_exc is not None
    raise last_exc


def _openrouter_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_referer,
        "X-Title": settings.openrouter_title,
    }


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
    data = build_ticker_response(ticker, include_news=False)
    day, extra = _tool_date(args.get("date"), data.prices)
    if day is None:
        return json.dumps(extra or {"error": "date is required."})
    point = next((p for p in data.prices if p.date == day), None)
    if point is None:
        return _missing_session_error(day, data.prices)
    move = next((m for m in data.movements if m.date == day), None)
    payload: dict[str, Any] = {
        "date": day.isoformat(),
        "weekday": day.strftime("%A"),
        "open": point.open,
        "high": point.high,
        "low": point.low,
        "close": point.close,
        "volume": point.volume,
        "pct_change": None if point.pct_change is None else round(point.pct_change, 2),
        "flagged_2pct": move is not None,
    }
    if extra:
        payload.update(extra)
    return json.dumps(payload)


def _tool_fetch_news(
    ticker: str,
    company_name: str | None,
    industry: str | None,
    args: dict[str, Any],
) -> str:
    data = build_ticker_response(ticker, include_news=False)
    day, extra = _tool_date(args.get("date"), data.prices)
    if day is None:
        return json.dumps(extra or {"error": "date is required."})
    movement = next((m for m in data.movements if m.date == day), None)
    flagged = movement is not None
    if movement is None:
        point = next((p for p in data.prices if p.date == day), None)
        if point is None:
            return _missing_session_error(day, data.prices)
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
    payload: dict[str, Any] = {
        "date": day.isoformat(),
        "flagged_2pct": flagged,
        "pct_change": round(movement.pct_change, 2),
        "article_count": len(articles),
        "articles": articles,
    }
    if extra:
        payload.update(extra)
    return json.dumps(payload)


def _fallback_reply(message: str, movements: list[Movement], *, no_key: bool = False) -> str:
    if not movements:
        return (
            "No days with a move of 2% or more were found for this ticker, so there is "
            "nothing to explain yet."
        )
    top = max(movements, key=lambda m: abs(m.pct_change))
    base = f"Biggest flagged move is {top.date} at {top.pct_change:+.2f}%."
    if no_key:
        return f"{base} Chat is running without a live model right now. Your question was: “{message}”"
    return f"{base} Ask again if you want the news around that session."
