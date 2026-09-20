# Shared database and migrations

Pipeline and backend share one SQLite file. The data layer lives at repo root as `db/`, not under `pipeline/`.

## Why not `pipeline/db/`

The pipeline is a writer. The backend will be a reader (and later a writer for news/chat). Putting schema and connection code inside `pipeline/` would force the API to import the job package. Both import `db` instead.

```
pipeline.run  --writes-->  data/stock_tracker.db  <--reads--  backend
                    ^
                    |
                 db.migrate()
                 db.connect()
```

## Do we need migrations?

Yes — a small SQL-file runner, not Alembic.

Schema will change in this project (news tables, chat tables). Pipeline CLI and backend startup must apply the same version or they will disagree. `CREATE TABLE IF NOT EXISTS` in one giant `schema.sql` does not evolve columns safely.

Alembic is skipped for the time box: extra config, extra dependency, one developer, SQLite.

## Layout

```
db/
├── __init__.py          # connect(path) -> sqlite3.Connection
├── migrate.py           # migrate(conn) applies pending files
└── migrations/
    └── 001_initial.sql  # companies, price_bars, price_moves, pipeline_runs
```

Database file: `data/stock_tracker.db` (WAL mode, `PRAGMA foreign_keys = ON`).

## How migrations run

1. `connect()` opens SQLite, enables WAL and foreign keys, sets `row_factory`.
2. `migrate(conn)` ensures a bookkeeping table exists:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,      -- filename stem, e.g. 001_initial
  applied_at TEXT NOT NULL       -- UTC ISO-8601, e.g. 2026-09-20T15:30:00Z
);
```

3. It lists `db/migrations/*.sql` in lexicographic order.
4. For each file whose stem is not in `schema_migrations`, it runs the SQL inside a transaction and inserts the version.

Both entrypoints call this **before** any query:

- `python -m pipeline.run`
- backend process startup (later)

Idempotent runner; **not** idempotent SQL. A given `NNN_*.sql` is applied once. Do not edit a file that has already been applied. Add `002_...sql` instead.

## Naming

`NNN_short_description.sql` — three-digit prefix so order is obvious:

- `001_initial.sql`
- `002_news.sql` (later)
- `003_chat.sql` (later)

## Access rules

| Table | Pipeline | Backend (later) |
| --- | --- | --- |
| `companies` | upsert seed; set `in_universe` | read; reject tickers with `in_universe = 0` |
| `price_bars` | upsert 30d daily bars | read |
| `price_moves` | replace for lookback window | read; news windows come from here |
| `pipeline_runs` | insert/update scan rows | read last status |
| `schema_migrations` | applied by `db.migrate` | applied by `db.migrate` |

Neither package opens `sqlite3.connect` itself. News and chat tables are not in `001`; they land in later migrations when those features are designed.

## Schema v1 (`001_initial.sql`)

Dates on bars and moves are `YYYY-MM-DD`. Timestamps on runs are UTC ISO-8601. Tickers are uppercase.

Synthetic example: ticker `AAPL`, bar date `2026-09-18`, `daily_return` `0.0231`, `in_universe` `1`.

```sql
CREATE TABLE companies (
  ticker TEXT PRIMARY KEY,
  name TEXT,
  exchange TEXT,
  sector TEXT,
  industry TEXT,
  in_universe INTEGER NOT NULL DEFAULT 0 CHECK (in_universe IN (0, 1)),
  updated_at TEXT NOT NULL
);

CREATE TABLE price_bars (
  ticker TEXT NOT NULL REFERENCES companies(ticker),
  date TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  adj_close REAL,
  volume INTEGER,
  daily_return REAL,
  PRIMARY KEY (ticker, date)
);

CREATE TABLE price_moves (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL REFERENCES companies(ticker),
  date TEXT NOT NULL,
  pct_change REAL NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('up','down')),
  adj_close REAL,
  prev_adj_close REAL,
  volume INTEGER,
  threshold REAL NOT NULL DEFAULT 0.02,
  window_start TEXT NOT NULL,
  window_end TEXT NOT NULL,
  UNIQUE (ticker, date)
);

CREATE TABLE pipeline_runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  seed_count INTEGER,
  bars_upserted INTEGER,
  moves_found INTEGER,
  universe_count INTEGER,
  error TEXT
);

CREATE INDEX idx_companies_universe ON companies(in_universe);
CREATE INDEX idx_moves_ticker_date ON price_moves(ticker, date);
CREATE INDEX idx_bars_ticker_date ON price_bars(ticker, date);
```

`window_start` / `window_end` are stored now so a later news fetch can use move windows without recomputing. The price job does not fetch news.

## Concurrency

SQLite plus WAL: one writer at a time. The pipeline is a batch job; the backend is request-time reads. Do not run two pipeline scans against the same file at once. Backend should treat a scan in `pipeline_runs.status = 'running'` as read-only / possibly stale.

## What this is not

- Not Postgres (swap later by keeping table names and migration files).
- Not Alembic / Flyway.
- Not a migration that deletes `data/stock_tracker.db` as a “reset” in production code. For local reset, delete the file and re-run migrate + pipeline.
