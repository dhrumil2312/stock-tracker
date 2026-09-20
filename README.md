# 📈 Stock Movement Explainer

Explains major stock price movements using relevant news. Pick a ticker; a batch
pipeline stores its recent daily prices (yfinance) and flags days with a large
single-day move, the API attaches explanatory news for each move
(company / industry / macro), and you can chat over the findings.

- **Pipeline:** yfinance → daily bars + `|Δ| ≥ 2%` moves → shared SQLite
- **Backend:** FastAPI (reads prices, caches news, proxies chat)
- **Frontend:** React + Vite + TypeScript (recharts)
- **News:** Exa (default) / NewsAPI / keyless Mock
- **Chat:** OpenRouter (OpenAI-compatible), with a deterministic fallback

## Architecture

```
python -m pipeline.run           ← ONLY caller of yfinance (batch)
   └─► data/stock_tracker.db  (SQLite, WAL)  companies · price_bars · price_moves
                    ▲
        reads / writes news
                    │
FastAPI backend
   ├─ /api/tickers        seeded companies
   ├─ /api/tickers/{t}    stored bars + moves (|Δ| ≥ threshold%) + cached news
   │      └─ news/        NewsProvider → ExaProvider  (semantic, historical)
   │                                   → NewsApiProvider (keyword, ~30 days)
   │                                   → MockProvider   (keyless fallback)
   └─ /api/chat           OpenRouter chat (agentic tools over moves + on-demand news)
                    │ JSON
                    ▼
             React frontend (Vite dev server proxies /api → :8000)
```

**Key rule:** the backend never pulls prices. Prices/moves exist only because
`pipeline.run` wrote them. The backend reads that data and *may* write the news
cache (cache-aside), so repeated requests never re-hit the news API.

## News providers

Selected with the `NEWS_PROVIDER` env var:

- **`exa`** (default) — Exa AI. Semantic search with historical date windows;
  good at linking macro/political articles that never name the ticker.
- **`newsapi`** — NewsAPI.org. Keyword search; the free tier covers roughly the
  **last ~30 days**. Company news is precise; industry/macro are approximated with
  boolean keyword queries.
- **`mock`** — labelled `[MOCK]` placeholder articles so the app runs with **no
  keys**.

If the chosen provider has no key set, it falls through to any other available
key, and finally to `mock`.

Industry and macro fetches are shared by date across tickers, so at attach time a
per-ticker relevance filter drops articles that are really about a different
seeded company (e.g. an NVIDIA deal landing on MSFT's day).

## Chat

Chat calls **OpenRouter** (OpenAI-compatible API) as a small **agent**: the model
is given tools and decides when to use them, so answers stay grounded in stored
data rather than guesses.

- `list_moves` — the ticker's flagged 2%+ days (OHLC + percent change)
- `get_session` — OHLC for any loaded trading day, even one that wasn't a 2% move
- `fetch_news` — cache-aside news around a date (company / industry / macro),
  fetched on demand only when the user asks *why* a day moved

The loop is bounded (max 5 tool rounds, max 3 news fetches per turn). The client
may pick only from a curated model allow-list (`CHAT_MODELS` in
`backend/app/config.py`); an arbitrary model string is never forwarded. Without
`OPENROUTER_API_KEY`, chat returns a deterministic data summary instead.

---

## Quick start

Prerequisites: Python 3.12+ and Node 18+.

### 1. Backend + pipeline (Python)

```bash
# from repo root
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt      # also covers pipeline deps (pandas, yfinance)

# populate the database (REQUIRED before the API returns ticker data)
python -m pipeline.run

# start the API
cd backend && uvicorn app.main:app --reload --port 8000
```

`python -m pipeline.run` downloads ~30 days of daily bars for the seed list,
computes moves, and writes them to `data/stock_tracker.db` (created automatically;
migrations run on both pipeline runs and API startup). Re-run it whenever you want
fresh prices. Until it has run at least once, `GET /api/tickers/{ticker}` returns
404 ("run the price pipeline").

Interactive API docs: http://localhost:8000/docs
Health / active backends: http://localhost:8000/api/health

### 2. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api → :8000)
```

Open http://localhost:5173, search a seeded ticker, and explore its moves and chat.

---

## Enabling news and chat (API keys)

Everything runs **keyless** out of the box (mock news + canned chat). To turn on
real news and LLM chat, add keys to `backend/.env`.

```bash
cp backend/.env.example backend/.env
# then edit backend/.env and fill in the keys you want
```

| Var | Enables | Where to get it | Without it |
|---|---|---|---|
| `EXA_API_KEY` | Historical/semantic news (**default provider**) | https://dashboard.exa.ai | Falls back to any other key, else `[MOCK]` news |
| `NEWSAPI_API_KEY` | Keyword news, last ~30 days (`NEWS_PROVIDER=newsapi`) | https://newsapi.org/register | Falls back to any other key, else `[MOCK]` news |
| `OPENROUTER_API_KEY` | LLM-powered chat | https://openrouter.ai/keys | Deterministic data summary |

`backend/.env` is git-ignored — keep real keys out of version control. `.env` is
read relative to the backend working directory, so it must live in `backend/`.
After editing, restart the backend and check `GET /api/health` to confirm which
`news_provider` and `chat` backend are active.

### Optional overrides (defaults shown in `backend/.env.example`)

```
NEWS_PROVIDER=exa                        # exa | newsapi | mock
CHAT_MODEL=deepseek/deepseek-v4.1-flash  # must be one of CHAT_MODELS in config.py
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DEFAULT_MOVEMENT_THRESHOLD=2.0
NEWS_MAX_MOVES_WITH_NEWS=6               # news fan-out cap per request
NEWS_MAX_ARTICLES_PER_SCOPE=3
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Chat model allow-list (curated in `backend/app/config.py`): `deepseek/deepseek-v4.1-flash`,
`google/gemini-3.6-flash`, `anthropic/claude-3.5-haiku`. `CHAT_MODEL` must be one
of these ids.

---

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/tickers` | Seeded companies |
| GET | `/api/tickers/{ticker}` | Prices + movements + news. Query params: `include_news`, `start`, `end`, `threshold`, `direction`, `news_category` |
| GET | `/api/chat/models` | Curated chat-model allow-list |
| POST | `/api/chat` | Agentic chat over a ticker. Body: `ticker`, `message`, `history[]`, optional `model`, `threshold` |
| GET | `/api/health` | Active news/chat backends |

## Movement definition

A **major movement** is a trading day whose close-over-close change satisfies
`|pct_change| ≥ threshold` (default **2%**, configurable per request). The pipeline
scans a rolling ~30-day window, and news fan-out is capped to the largest moves per
request to bound external API calls.

## Tests

The suite uses **pytest** (fixtures + import paths live in `tests/conftest.py`).
Run it from the repo root:

```bash
source .venv/bin/activate
pip install pytest        # not in requirements.txt
pytest
```

## Project layout

```
pipeline/   batch price job (only yfinance caller)
db/         shared SQLite connection + SQL migrations
backend/    FastAPI app (readers + news cache + chat)
frontend/   React + Vite client
docs/       design notes
tests/      backend tests
```
