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
