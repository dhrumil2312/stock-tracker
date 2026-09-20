# AGENTS.md — `db/` (shared data layer)

Scope: this file governs work inside `db/`. It is the single source of truth for
how the SQLite database, its schema, and its migrations are used by **both** the
`pipeline/` (writer) and `backend/` (reader) packages.

## What `db/` is

One shared SQLite database for the whole project. `db/` owns connection setup and
schema migrations; it does **not** contain business logic.

```
pipeline.run  --writes-->  data/stock_tracker.db  <--reads--  backend
                     ^
                     |
             db.connect() / db.migrate()
```

- DB file: `data/stock_tracker.db` (WAL mode, `PRAGMA foreign_keys = ON`, `busy_timeout`).
- Public API (import from `db`, never `import sqlite3` in feature code):
  `connect(path=None)`, `migrate(conn)`, `utc_now()`, `DEFAULT_DB_PATH`, `REPO_ROOT`.

## Reader / writer contract

| Table | `pipeline/` (writer) | `backend/` |
| --- | --- | --- |
| `companies` | upsert seed, set `in_universe` | read only |
| `price_bars` | upsert daily bars | read only |
| `price_moves` | replace per lookback window | read only (news windows come from `window_start`/`window_end`) |
| `pipeline_runs` | insert/update scan rows | read last status |
| `news_articles` | — | **read + write** (global by URL) |
| `news_fetches` / `fetch_articles` (`003`) | — | **read + write** (scoped cache: company / industry / macro) |

**The backend never pulls prices.** Price data is produced only by
`python -m pipeline.run`. The backend reads what the pipeline wrote. The backend
*may* write **news** tables (cache-aside), never price tables.

## Migration rules (STRICT)

- Migrations are plain SQL files: `db/migrations/NNN_short_description.sql`.
- `migrate(conn)` applies any file whose stem is not yet in `schema_migrations`,
  in lexicographic order, once each.
- **Append-only. Never edit a migration that has already been applied.** To change
  the schema, add the next `NNN_*.sql`.
- Both entrypoints call `migrate()` before any query: `pipeline.run` and (later)
  backend startup. Runner is idempotent; the SQL is not.
- No Alembic, no ORM. Deliberate: single dev, SQLite, time-boxed. Keep raw SQL.
  (If a SQLAlchemy/Alembic setup appears under `backend/db/`, it is stray — see
  the design doc's "Cleanup" note — do not build on it.)

## Conventions

- Tickers: uppercase. Bar/move dates: `YYYY-MM-DD` (TEXT). Timestamps: UTC ISO-8601
  via `utc_now()`.
- Booleans as `INTEGER CHECK (col IN (0,1))`. Enums as `TEXT CHECK (col IN (...))`.
- Index any `(ticker, date)` or `(move_id, ...)` lookup added by a new feature.

## Concurrency

SQLite + WAL = one writer at a time. The pipeline is a batch job; the backend is
request-time reads (plus small news upserts). Do not run two pipeline scans on the
same file concurrently. Treat a run with `pipeline_runs.status = 'running'` as
possibly-stale.

## Local reset

Delete `data/stock_tracker.db*` (db, `-wal`, `-shm`), then re-run `db.migrate()` and
`python -m pipeline.run`. Never ship code that deletes the DB as a "reset".

## Next migrations (planned — see `docs/`)

- `002_news.sql` — applied. First news tables (`move_articles` was dropped in `003`).
- `003_news_scoped.sql` — `news_fetches` keyed by `(scope, subject, move_date)` plus `fetch_articles`. No chat table.
