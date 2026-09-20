-- Replace move-scoped news cache with scoped, shareable fetches.
-- 002 created move_articles + news_fetches keyed by price_moves.id.
-- Industry/macro articles are not owned by a ticker, so drop that coupling.

DROP TABLE IF EXISTS move_articles;
DROP TABLE IF EXISTS news_fetches;

CREATE TABLE news_fetches (
  id            INTEGER PRIMARY KEY,
  scope         TEXT NOT NULL CHECK (scope IN ('company','industry','macro')),
  subject       TEXT NOT NULL,
  move_date     TEXT NOT NULL,
  window_start  TEXT NOT NULL,
  window_end    TEXT NOT NULL,
  provider      TEXT NOT NULL,
  query_hash    TEXT NOT NULL,
  status        TEXT NOT NULL CHECK (status IN ('ok','empty','error')),
  article_count INTEGER NOT NULL DEFAULT 0,
  fetched_at    TEXT NOT NULL,
  UNIQUE (scope, subject, move_date, provider, query_hash)
);

CREATE TABLE fetch_articles (
  fetch_id   INTEGER NOT NULL REFERENCES news_fetches(id) ON DELETE CASCADE,
  article_id INTEGER NOT NULL REFERENCES news_articles(id) ON DELETE CASCADE,
  rank       INTEGER,
  PRIMARY KEY (fetch_id, article_id)
);

CREATE INDEX idx_news_fetches_lookup ON news_fetches(scope, subject, move_date);
CREATE INDEX idx_fetch_articles_fetch ON fetch_articles(fetch_id);
