"""Cache-aside news keyed by (scope, subject, move_date), not by a ticker's move.

Company fetches are per ticker-day. Industry fetches are shared by
`companies.industry` + date. Macro fetches are shared by date across all tickers.
Chat never writes here; it only reads movements after articles are attached.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import date as Date, datetime, timedelta, timezone
from typing import Literal

from db import connect, utc_now

from ..config import settings
from ..models import Article, Movement
from .news import NewsProvider, get_news_provider
from .news.base import NewsQuery, NewsScope
from .news.relevance import filter_for_ticker

_locks_guard = threading.Lock()
_scope_locks: dict[tuple[str, str, str], threading.Lock] = {}


def _lock_for(scope: str, subject: str, move_date: Date) -> threading.Lock:
    key = (scope, subject, move_date.isoformat())
    with _locks_guard:
        return _scope_locks.setdefault(key, threading.Lock())


def query_hash(
    provider: NewsProvider,
    scope: NewsScope,
    subject: str,
    query: NewsQuery,
    max_articles: int,
) -> str:
    prompt = query.prompt(scope) if provider.query_style == "semantic" else query.keyword_query(scope)
    payload = json.dumps(
        {
            "provider": provider.name,
            "style": provider.query_style,
            "scope": scope,
            "subject": subject,
            "start": query.start.isoformat(),
            "end": query.end.isoformat(),
            "max": max_articles,
            "prompt": prompt,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _parse_fetched_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_fresh(status: str, fetched_at: str, move_date: Date) -> bool:
    fetched = _parse_fetched_at(fetched_at)
    now = datetime.now(timezone.utc)
    age = now - fetched.astimezone(timezone.utc)
    if status == "error":
        return age < timedelta(hours=settings.news_error_ttl_hours)
    move_age_days = (Date.today() - move_date).days
    if move_age_days > settings.news_recent_days:
        return True
    return age < timedelta(hours=settings.news_recent_ttl_hours)


def _get_fetch(conn, scope: str, subject: str, move_date: Date, provider: str, qhash: str):
    return conn.execute(
        """
        SELECT id, status, article_count, fetched_at
        FROM news_fetches
        WHERE scope = ? AND subject = ? AND move_date = ? AND provider = ? AND query_hash = ?
        """,
        (scope, subject, move_date.isoformat(), provider, qhash),
    ).fetchone()


def load_articles(conn, fetch_id: int, category: NewsScope) -> list[Article]:
    rows = conn.execute(
        """
        SELECT a.title, a.url, a.source, a.published_at, a.snippet
        FROM fetch_articles fa
        JOIN news_articles a ON a.id = fa.article_id
        WHERE fa.fetch_id = ?
        ORDER BY fa.rank ASC, a.published_at DESC
        """,
        (fetch_id,),
    ).fetchall()
    articles: list[Article] = []
    for row in rows:
        articles.append(
            Article(
                title=row["title"],
                url=row["url"],
                source=row["source"],
                published_at=row["published_at"],
                snippet=row["snippet"],
                category=category,
            )
        )
    return articles


def _store_fetch(
    conn,
    *,
    scope: NewsScope,
    subject: str,
    query: NewsQuery,
    provider: NewsProvider,
    max_articles: int,
    articles: list[Article],
    status: str,
) -> int:
    now = utc_now()
    move_date = query.movement.date.isoformat()
    qhash = query_hash(provider, scope, subject, query, max_articles)
    conn.execute(
        """
        INSERT INTO news_fetches (
          scope, subject, move_date, window_start, window_end,
          provider, query_hash, status, article_count, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(scope, subject, move_date, provider, query_hash) DO UPDATE SET
          window_start = excluded.window_start,
          window_end = excluded.window_end,
          status = excluded.status,
          article_count = excluded.article_count,
          fetched_at = excluded.fetched_at
        """,
        (
            scope,
            subject,
            move_date,
            query.start.isoformat(),
            query.end.isoformat(),
            provider.name,
            qhash,
            status,
            len(articles),
            now,
        ),
    )
    fetch_id = conn.execute(
        """
        SELECT id FROM news_fetches
        WHERE scope = ? AND subject = ? AND move_date = ? AND provider = ? AND query_hash = ?
        """,
        (scope, subject, move_date, provider.name, qhash),
    ).fetchone()["id"]
    conn.execute("DELETE FROM fetch_articles WHERE fetch_id = ?", (fetch_id,))
    for rank, art in enumerate(articles, start=1):
        conn.execute(
            """
            INSERT INTO news_articles (url, title, source, published_at, snippet, content, fetched_at)
            VALUES (?, ?, ?, ?, ?, NULL, ?)
            ON CONFLICT(url) DO UPDATE SET
              title = excluded.title,
              source = excluded.source,
              published_at = excluded.published_at,
              snippet = excluded.snippet,
              fetched_at = excluded.fetched_at
            """,
            (
                art.url,
                art.title,
                art.source,
                art.published_at.isoformat() if art.published_at else None,
                art.snippet,
                now,
            ),
        )
        article_id = conn.execute(
            "SELECT id FROM news_articles WHERE url = ?", (art.url,)
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO fetch_articles (fetch_id, article_id, rank)
            VALUES (?, ?, ?)
            ON CONFLICT(fetch_id, article_id) DO UPDATE SET rank = excluded.rank
            """,
            (fetch_id, article_id, rank),
        )
    conn.commit()
    return fetch_id


def _ensure_scope(
    conn,
    *,
    provider: NewsProvider,
    scope: NewsScope,
    subject: str,
    query: NewsQuery,
    max_articles: int,
    allow_fetch: bool,
) -> list[Article]:
    qhash = query_hash(provider, scope, subject, query, max_articles)
    move_date = query.movement.date
    row = _get_fetch(conn, scope, subject, move_date, provider.name, qhash)
    if row is not None and is_fresh(row["status"], row["fetched_at"], move_date):
        return load_articles(conn, row["id"], scope)
    if not allow_fetch:
        return load_articles(conn, row["id"], scope) if row is not None else []

    with _lock_for(scope, subject, move_date):
        row = _get_fetch(conn, scope, subject, move_date, provider.name, qhash)
        if row is not None and is_fresh(row["status"], row["fetched_at"], move_date):
            return load_articles(conn, row["id"], scope)
        try:
            articles = provider.fetch_scope(scope, subject, query, max_articles)
            status = "ok" if articles else "empty"
        except Exception:
            articles = []
            status = "error"
        fetch_id = _store_fetch(
            conn,
            scope=scope,
            subject=subject,
            query=query,
            provider=provider,
            max_articles=max_articles,
            articles=articles,
            status=status,
        )
        return load_articles(conn, fetch_id, scope)


def _dedupe(articles: list[Article]) -> list[Article]:
    seen: set[str] = set()
    out: list[Article] = []
    for art in articles:
        if art.url in seen:
            continue
        seen.add(art.url)
        out.append(art)
    return out


def attach_news(
    ticker: str,
    company_name: str | None,
    industry: str | None,
    movements: list[Movement],
    *,
    max_articles: int | None = None,
    max_company_fetches: int | None = None,
    category: Literal["company", "industry", "macro"] | None = None,
    provider: NewsProvider | None = None,
) -> None:
    """Fill `movement.articles` from scoped cache. Mutates `movements` in place.

    New *company* provider calls are capped to the largest `|%|` moves.
    Industry/macro are one fetch per (subject, date) and are reused across tickers.
    """
    if not movements:
        return
    max_articles = max_articles if max_articles is not None else settings.news_max_articles_per_scope
    max_company_fetches = (
        max_company_fetches if max_company_fetches is not None else settings.news_max_moves_with_news
    )
    provider = provider or get_news_provider()
    industry_subject = (industry or "").strip() or None
    ranked = sorted(movements, key=lambda m: abs(m.pct_change), reverse=True)
    fetch_dates = {m.date for m in ranked[:max_company_fetches]}

    conn = connect()
    try:
        for movement in movements:
            query = NewsQuery(ticker, company_name, industry_subject, movement)
            allow_fetch = movement.date in fetch_dates
            bundled: list[Article] = []
            bundled.extend(
                _ensure_scope(
                    conn,
                    provider=provider,
                    scope="company",
                    subject=ticker,
                    query=query,
                    max_articles=max_articles,
                    allow_fetch=allow_fetch,
                )
            )
            if industry_subject:
                bundled.extend(
                    _ensure_scope(
                        conn,
                        provider=provider,
                        scope="industry",
                        subject=industry_subject,
                        query=query,
                        max_articles=max_articles,
                        allow_fetch=allow_fetch,
                    )
                )
            bundled.extend(
                _ensure_scope(
                    conn,
                    provider=provider,
                    scope="macro",
                    subject="*",
                    query=query,
                    max_articles=max_articles,
                    allow_fetch=allow_fetch,
                )
            )
            articles = _dedupe(bundled)
            articles = filter_for_ticker(
                articles,
                ticker=ticker,
                company_name=company_name,
                industry=industry_subject,
            )
            if category:
                articles = [a for a in articles if a.category == category]
            movement.articles = articles
    finally:
        conn.close()
