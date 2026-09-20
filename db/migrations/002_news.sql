-- News cache: articles are stored once (by URL) and linked to price moves.
-- news_fetches is the cache ledger, including empty/error results so we do
-- not re-hit the provider for the same move + query.

CREATE TABLE news_articles (
  id           INTEGER PRIMARY KEY,
  url          TEXT NOT NULL UNIQUE,
  title        TEXT NOT NULL,
  source       TEXT,
  published_at TEXT,
  snippet      TEXT,
  content      TEXT,
  fetched_at   TEXT NOT NULL
);

CREATE TABLE move_articles (
  move_id    INTEGER NOT NULL REFERENCES price_moves(id) ON DELETE CASCADE,
  article_id INTEGER NOT NULL REFERENCES news_articles(id) ON DELETE CASCADE,
  category   TEXT NOT NULL DEFAULT 'unknown'
             CHECK (category IN ('company','industry','macro','unknown')),
  rank       INTEGER,
  PRIMARY KEY (move_id, article_id)
);

CREATE TABLE news_fetches (
  id            INTEGER PRIMARY KEY,
  move_id       INTEGER NOT NULL REFERENCES price_moves(id) ON DELETE CASCADE,
  provider      TEXT NOT NULL,
  query_hash    TEXT NOT NULL,
  status        TEXT NOT NULL
                CHECK (status IN ('ok','empty','error')),
  article_count INTEGER NOT NULL DEFAULT 0,
  fetched_at    TEXT NOT NULL,
  UNIQUE (move_id, provider, query_hash)
);

CREATE INDEX idx_move_articles_move ON move_articles(move_id);
CREATE INDEX idx_news_fetches_move  ON news_fetches(move_id);
