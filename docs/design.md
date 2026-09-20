# System design — persistence, news cache, and chat

What we are building and how the pieces relate. This is the plan of record; it
extends [database.md](database.md) and [pipeline.md](pipeline.md). No code in this
doc is applied yet.

## One-paragraph summary

A batch **pipeline** pulls prices and computes ≥2% moves into one central SQLite
database. The **backend** only *reads* prices/moves from that database — it never
calls yfinance. News is added by the backend on demand (cache-aside) and stored in
the same database, so repeated requests never re-hit the news API. Chat reads the
stored data and calls Claude only.

## Components

```
                        ┌──────────────────────────────┐
                        │        pipeline/ (batch)      │
                        │  python -m pipeline.run       │
                        │  yfinance → bars + ≥2% moves  │  ← ONLY caller of yfinance
                        └───────────────┬───────────────┘
                                        │ writes
                                        ▼
        ┌───────────────────────────────────────────────────────────┐
        │            db/  →  data/stock_tracker.db (SQLite, WAL)      │
        │  companies · price_bars · price_moves · pipeline_runs       │
        │  news_articles · move_articles · news_fetches   (002, new)  │
        └───────────────┬───────────────────────────┬───────────────┘
                reads    │                           │  reads + writes news
                         ▼                           ▼
        ┌───────────────────────────────┐   ┌────────────────────────────┐
        │   backend/ (FastAPI, reader)  │   │  external (only on miss)    │
        │  GET  /api/tickers            │──►│  NewsAPI  (news, cache-aside)│
        │  GET  /api/tickers/{t}        │   │  Claude   (chat, never cached)│
        │  POST /api/chat               │   └────────────────────────────┘
        └───────────────┬───────────────┘
                        │ JSON
                        ▼
                 React frontend
```

## Principles

1. **One central database** — `db/` at repo root, file at `data/stock_tracker.db`.
   Pipeline and backend both `import db`; neither opens `sqlite3` directly.
2. **The backend never pulls prices.** Prices/moves exist only because
   `pipeline.run` wrote them. A ticker with no stored data is a 404 that says
   "run the pipeline", not a live fetch. (Already true: `backend/app/services/stocks.py`
   holds only `StockDataError`; `services/tickers.py` reads the DB.)
3. **News is cache-aside, owned by the backend.** First request for a move's news
   hits NewsAPI and writes the result to the DB. Every later request reads the DB.
   This is the "don't hit external sources on every user call" requirement.
4. **Chat never touches yfinance/NewsAPI.** It assembles context from the DB and
   calls Claude. Only the LLM call is external.
5. **SQLite now, Postgres later** — keep table/column names portable; swap the
   driver in `db.connect()` when we outgrow one writer.

See [`db/AGENTS.md`](../db/AGENTS.md) for the enforced reader/writer contract and
migration rules.

## Current state vs. this design

| Concern | Now | This design |
| --- | --- | --- |
| Prices/moves | pipeline writes, backend reads ✅ | unchanged |
| News | backend fetches **live every request**, not stored ❌ | cache-aside into `news_*` tables |
| Chat | Claude over in-memory movements ✅ | Claude over **DB-sourced** movements + cached news |

The only new persistence work is the news cache (migration `002`).

## Proposed schema — `db/migrations/002_news.sql`

News attaches to a **`price_moves.id`** (moves are pre-computed by the pipeline and
already carry `window_start` / `window_end`, so no window recomputation is needed).

```sql
-- News articles, deduplicated by URL across all tickers/moves.
CREATE TABLE news_articles (
  id           INTEGER PRIMARY KEY,
  url          TEXT NOT NULL UNIQUE,
  title        TEXT NOT NULL,
  source       TEXT,
  published_at TEXT,             -- YYYY-MM-DD, nullable
  snippet      TEXT,
  content      TEXT,
  fetched_at   TEXT NOT NULL     -- UTC ISO-8601
);

-- Which article explains which move, and at what relevance level.
CREATE TABLE move_articles (
  move_id    INTEGER NOT NULL REFERENCES price_moves(id) ON DELETE CASCADE,
  article_id INTEGER NOT NULL REFERENCES news_articles(id) ON DELETE CASCADE,
  category   TEXT NOT NULL DEFAULT 'unknown'
             CHECK (category IN ('company','industry','macro','unknown')),
  rank       INTEGER,
  PRIMARY KEY (move_id, article_id)
);

-- Fetch ledger = the cache control table (incl. negative caching).
-- A row here means "this move was searched with this provider+query already".
CREATE TABLE news_fetches (
  id            INTEGER PRIMARY KEY,
  move_id       INTEGER NOT NULL REFERENCES price_moves(id) ON DELETE CASCADE,
  provider      TEXT NOT NULL,        -- 'newsapi' | 'exa' | 'mock'
  query_hash    TEXT NOT NULL,        -- hash of provider + query params
  status        TEXT NOT NULL         -- 'ok' | 'empty' | 'error'
                CHECK (status IN ('ok','empty','error')),
  article_count INTEGER NOT NULL DEFAULT 0,
  fetched_at    TEXT NOT NULL,        -- UTC ISO-8601, drives TTL
  UNIQUE (move_id, provider, query_hash)
);

CREATE INDEX idx_move_articles_move ON move_articles(move_id);
CREATE INDEX idx_news_fetches_move  ON news_fetches(move_id);
```

Why a separate `news_fetches` ledger instead of inferring "already fetched" from
`move_articles`: it lets us cache **empty** results (searched, found nothing) so a
quiet news day is not re-queried on every request, and it records the exact
`query_hash` so changing the query/provider forces a refresh.

## Read/write flow — `GET /api/tickers/{ticker}?include_news=true`

```
load company + bars + moves from DB           (reader; no external)
for each move (capped to N largest):
    key = (move_id, provider, query_hash)
    row = news_fetches[key]
    ├─ row exists AND fresh (per TTL) ──► read move_articles + news_articles  (no external)
    └─ missing OR stale ──► provider.fetch()               (EXTERNAL, once)
                             upsert news_articles (by url)
                             upsert move_articles (move_id, article_id, category)
                             upsert news_fetches  (status, article_count, fetched_at)
                             then read back
assemble TickerResponse from DB rows
```

Warm move within TTL → **zero external calls**. Cold/stale → one NewsAPI call for
that move, then cached.

### Freshness / TTL

| Case | Rule | Rationale |
| --- | --- | --- |
| Move older than `NEWS_RECENT_DAYS` (≈3) | never refetch | the event already happened |
| Recent move | refetch if `fetched_at` older than `NEWS_RECENT_TTL` (≈12h) | new coverage may surface |
| `status = 'empty'` | same TTL as above | avoids hammering on quiet days |
| `status = 'error'` | short retry TTL (≈1h) | transient provider failures |

TTLs live in `backend/app/config.py` (settings), not hard-coded.

## Chat design

- `POST /api/chat` builds context from the DB (company, moves, and cached
  `news_articles`) and calls **Claude** (`claude-haiku-4-5`). No price/news APIs.
- If a move has no cached news yet, chat triggers the same cache-aside path as the
  ticker endpoint (fetch once, store), then answers.
- Optional later `003_chat.sql` — a `chat_messages` log `(id, ticker, role,
  content, created_at)` for history/analytics. Not required for the feature; chat
  itself is stateless per request with client-sent history.

## New backend module (planned, not built)

- `backend/app/services/news_cache.py` (or a `NewsRepository`) — the only place
  that reads/writes `news_*`. Wraps a provider from `services/news/` and the DB.
- `services/pipeline.build_ticker_response` changes from "fetch news live" to
  "read/refresh via `news_cache`". Router signatures unchanged.
- Backend acquires a per-`move_id` in-process lock before a cold fetch to avoid two
  concurrent requests fetching the same window (thundering herd). Single-process
  only; revisit at the Postgres migration.

## Config additions (planned)

```
NEWS_RECENT_DAYS         = 3
NEWS_RECENT_TTL_HOURS    = 12
NEWS_ERROR_TTL_HOURS     = 1
NEWS_MAX_MOVES_WITH_NEWS = 25     # fan-out cap per request
```

## Cleanup before implementing

An earlier exploratory scaffold used SQLAlchemy/Alembic and conflicts with the
raw-SQL approach chosen here. Remove before building on this design:

- `backend/db/` (`base.py`, `models.py`, `__init__.py`) — SQLAlchemy ORM, unused.
- SQLAlchemy/Alembic/aiosqlite lines in `backend/requirements.txt`.
- `database_url` / TTL fields in `backend/app/config.py` that assume SQLAlchemy
  (keep the news TTL settings, drop the `sqlite+aiosqlite` URL).

## Build phases

1. `002_news.sql` + `db/AGENTS.md` contract (schema only).
2. `news_cache` read/write module + provider wiring.
3. Rewire `build_ticker_response` to cache-aside; add per-move lock.
4. Point chat context at the DB + cached news.
5. Tests: cache hit makes no provider call; empty/negative cache; TTL expiry.

## What this is not

- Not a second database. One file, one `db/` package.
- Not a backend that pulls prices. Prices come only from `pipeline.run`.
- Not Alembic/ORM. Raw SQL migrations, append-only.
- Not a news pre-fetch in the pipeline. News is lazy/cache-aside at the backend
  (the pipeline stays a pure price job).
