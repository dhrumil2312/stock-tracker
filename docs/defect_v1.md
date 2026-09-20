# Defect report — v1

Scope: full review of backend, pipeline, `db/`, frontend, docs, and tests.
Context: **localhost-only, never deployed to production.** Severities below are
calibrated to that — classic prod concerns (rate limiting, hardened CORS, error
leakage) are downgraded; correctness, "does the feature actually work", and live
API-cost/secret issues are kept high.

Verified working during review: `python -m unittest tests.test_news_cache` (3
pass), `app.main:app` imports, `GET /api/health`, `GET /api/tickers` (46),
`GET /api/tickers/AAPL` (22 prices, 3 movements).

---

## HIGH

### H1 — Real, live API keys sit in `backend/.env`
- **Where:** `backend/.env` (`NEWSAPI_API_KEY`, `EXA_API_KEY`, `OPENROUTER_API_KEY`).
- **What:** The file contains what look like real, active keys (not placeholders).
  `.gitignore` does exclude `.env`, and it is **not** currently tracked by git, so
  it will not be committed — good. But the keys are live in the working tree, were
  exposed during this review, and `/api/health` confirms they load (`news_provider:
  exa`, `chat: openrouter:...`), so the app makes real, billable calls with them.
- **Why it matters (even on localhost):** these keys can be abused / run up cost if
  they leak; the security policy requires rotating any exposed secret.
- **Fix:** Rotate all three keys at the providers. Keep `backend/.env.example`
  (already clean) as the template and never store real keys in a file that lives in
  the repo tree. Confirm `.env` stays untracked (`git check-ignore backend/.env`).

### H2 — Default chat models are almost certainly invalid OpenRouter slugs → chat silently degrades
- **Where:** `backend/app/config.py:32` (`chat_model = "deepseek/deepseek-v4.1-flash"`)
  and `CHAT_MODELS` (`config.py:52-56`: `deepseek/deepseek-v4.1-flash`,
  `google/gemini-3.6-flash`).
- **What:** These slugs don't correspond to models OpenRouter actually serves
  (`anthropic/claude-3.5-haiku` is real; the other two look like placeholder/future
  names). A request with an unknown model returns an HTTP error, which
  `chat.answer` catches and swallows into the canned fallback
  (`services/chat.py:80-82`).
- **Why it matters:** with the default model the LLM chat feature never works — the
  user always gets "Chat model error (...). Showing data summary instead." and it
  looks like a fallback, not a config bug.
- **Fix:** Set `chat_model` and `CHAT_MODELS` to slugs that exist on OpenRouter
  (verify against `https://openrouter.ai/models`). At minimum make the default one
  that resolves. Consider logging the underlying error so a bad slug is
  distinguishable from a network/auth failure.

### H3 — README describes a different app than the code (Claude/Anthropic vs OpenRouter)
- **Where:** `README.md:8, 20, 49, 67` vs `backend/app/config.py:28-37`,
  `backend/app/services/chat.py`.
- **What:** README says chat is "Claude (`claude-haiku-4-5`)" and requires
  `ANTHROPIC_API_KEY`. The code uses **OpenRouter** (`OPENROUTER_API_KEY`, OpenAI-
  compatible endpoint). The setup step `cp backend/.env.example ... # add ... ANTHROPIC_API_KEY`
  will leave a new user with chat that never turns on.
- **Fix:** Update README chat sections and the keys table to `OPENROUTER_API_KEY` /
  OpenRouter, matching `.env.example`.

### H4 — README/docs disagree on the default news provider
- **Where:** `README.md:8, 23-27, 65` ("newsapi (default)") vs
  `config.py:24` (`news_provider = "exa"`) and `backend/.env.example` ("Exa … default").
- **What:** Config and `.env.example` default to `exa`; README says `newsapi` is the
  default. Confusing for setup and for reasoning about which key you actually need.
- **Fix:** Pick one default and make README, `config.py`, and `.env.example` agree.

---

## MEDIUM

### M1 — Pipeline only stores ~30 days, contradicting the "historical" story
- **Where:** `pipeline/prices.py:16` (`LOOKBACK_PERIOD = "1mo"`),
  `_drop_stale_moves` (`prices.py:282-291`).
- **What:** Each run deletes moves not in the latest 1-month window. So the app can
  only ever explain moves from the last ~month. README/design tout Exa's
  "arbitrary historical" strength and "explain older movements" (`README.md:29-31`,
  `docs/design.md`), but there is no historical data to explain — the Exa capability
  is effectively unreachable through the pipeline.
- **Fix:** Either widen `LOOKBACK_PERIOD` (and stop dropping still-valid older moves),
  or adjust the docs to state the app is a rolling ~30-day tracker.

### M2 — `docs/design.md` documents a superseded schema as current
- **Where:** `docs/design.md:28, 63-116, 154-158` vs `db/migrations/003_news_scoped.sql`.
- **What:** design.md presents the `move_articles` / move-id-keyed `news_fetches`
  schema and a "current state" table as the plan of record. Migration `003` dropped
  `move_articles`, dropped the `price_moves.id` coupling, and re-keyed the cache to
  `(scope, subject, move_date)`. Anyone reading design.md will build the wrong mental
  model. (`db/AGENTS.md` is correct and up to date — design.md is the stale one.)
- **Fix:** Add a note/section to design.md pointing at `003` and the scoped cache, or
  update the schema block and the state table.

### M3 — Stale/incorrect code comment in `_upsert_moves`
- **Where:** `pipeline/prices.py:252-256`.
- **What:** The docstring says news "keys off move_id" and that delete-and-replace
  "would … CASCADE-wipe cached articles." After migration `003` the news cache no
  longer references `price_moves.id` at all, so this rationale is obsolete and
  misleading (it implies a coupling that no longer exists).
- **Fix:** Rewrite the comment to reflect the scoped `(scope, subject, move_date)`
  cache; the upsert-on-`(ticker, date)` is still fine but for a different reason.

### M4 — News fan-out cap can leave lower-ranked movements with no news
- **Where:** `backend/app/services/news_cache.py:269-311`; `news_max_moves_with_news = 6`
  (`config.py:14`).
- **What:** `allow_fetch` is true only for the top-N moves by `|%|`. It gates **all**
  scopes (company, industry, macro), not just company — despite the docstring
  implying industry/macro fetch independently. A ticker with more than 6 qualifying
  moves shows the rest with zero articles on first load (unless another ticker
  happened to populate the shared industry/macro rows for that date). All such moves
  are still rendered in the UI, so the gap is visible.
- **Why it's only MEDIUM:** with a 1-month window, >6 moves is uncommon.
- **Fix:** Either raise the cap, or let the cheap shared industry/macro scopes fetch
  for every displayed move-date and cap only the per-ticker company scope, and align
  the docstring.

### M5 — Frontend never uses the `start` / `end` / `threshold` / `direction` filters
- **Where:** `frontend/src/api.ts:21-24` (`fetchTicker` hardcodes only
  `include_news=true`), `frontend/src/App.tsx`. Backend supports them
  (`routers/tickers.py:22-33`) and README advertises them (`README.md:39`).
- **What:** There is no UI to set date range / threshold / direction, and the client
  wouldn't send them anyway. The "in this window" copy (`App.tsx:161`) and the
  `≥ {threshold}%` label imply filtering that the user can't control.
- **Fix:** Either add the controls and pass them through `fetchTicker`, or remove the
  filter claims from the README and soften the UI copy. (Note the `MovementList`
  category buttons only filter *articles* client-side — separate from these.)

### M6 — `is_fresh` mixes local date with UTC for age math
- **Where:** `backend/app/services/news_cache.py:60-69`.
- **What:** Move "recency" uses `Date.today()` (local/naive), while fetch age uses
  `datetime.now(timezone.utc)`. Near midnight and depending on server TZ, a move can
  be classified recent/not-recent inconsistently, flipping between "cache forever"
  and "TTL applies."
- **Fix:** Use a single UTC clock: derive today from `datetime.now(timezone.utc).date()`.

---

## LOW

### L1 — `chat.answer` swallows every exception into the fallback
- **Where:** `backend/app/services/chat.py:80-82`. Catches bare `Exception` and
  returns the canned summary with a generic `type(exc).__name__` string. A bad model
  slug, an auth failure, and a network timeout are indistinguishable, and nothing is
  logged. Graceful degradation is fine, but log the real error (see H2).

### L2 — No tests outside the news cache
- **Where:** `tests/` has only `test_news_cache.py`. `pipeline/prices.py` (return
  math, column normalization, move detection), `services/tickers.py`,
  `services/chat.py` (context builder, fallback), `config.resolve_chat_model`, and
  the whole frontend are untested. Well short of the 80% target. Add unit tests for
  the pure functions (`bars_and_moves`, `build_context`, `resolve_chat_model`,
  `_apply_filters`) — they're easy wins with no I/O.

### L3 — `resolve_chat_model(None)` bypasses the allow-list; `.env` comments contradict
- **Where:** `config.py:60-66`. The default path returns `settings.chat_model`
  without checking membership in `CHAT_MODEL_IDS`. `backend/.env` comment says
  `CHAT_MODEL` can be "any OpenRouter model slug" while `.env.example` says it "must
  be one of CHAT_MODELS." If an operator sets a default that isn't in the list, the
  `/api/chat/models` selector won't show the model actually in use. Decide whether the
  default must be in the allow-list and make the two `.env` comments agree.

### L4 — Naive SQL splitter in the migration runner
- **Where:** `db/migrate.py:16-23`. Splits on `;` and strips only full-line `--`
  comments. Fine for the current three migrations, but a future migration with a
  trigger body, a `BEGIN…END`, or a `;`/`--` inside a string literal will break
  silently. Note the limitation, or switch to `conn.executescript()` per file.

### L5 — CORS uses `allow_credentials=True` with `allow_methods/headers=["*"]`
- **Where:** `backend/app/main.py:33-39`. Origins are explicit (not wildcard), so this
  is safe. But no credentials/cookies are used anywhere, so `allow_credentials=True`
  is unnecessary. Minor cleanup; not a risk on localhost.

### L6 — Broad `except Exception` → 502 in the ticker route
- **Where:** `backend/app/routers/tickers.py:46-47`. Any unexpected error becomes a
  502 with the exception text echoed to the client (`detail=f"...: {exc}"`). Harmless
  on localhost, but it both hides the stack trace from logs and echoes internals to
  the response. Consider logging server-side and returning a generic message.

---

## Not defects (verified OK)
- News cache hit/negative-cache/cross-ticker sharing behave per tests.
- `backend/.env` is **not** git-tracked (only `LICENSE` is committed); `.gitignore`
  covers `.env`, `*.db`, `node_modules/`, `dist/`.
- SQLite connection sets WAL + `foreign_keys=ON` + `busy_timeout`; each
  `attach_news` uses its own connection with a per-scope in-process lock.
- Sync FastAPI endpoints doing blocking SQLite/`httpx` are fine — FastAPI runs
  `def` handlers in a threadpool.
```
