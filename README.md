# 📈 Stock Movement Explainer

Explains major stock price movements using relevant news. Give it a ticker; it
fetches historical prices (yfinance), flags days with a large single-day move,
finds explanatory news for each move (company / industry / macro), and lets you
chat over the findings.

- **Backend:** FastAPI + yfinance + NewsAPI (news) + Claude (chat)
- **Frontend:** React + Vite + TypeScript (recharts)

## Architecture

```
Ticker + filters
   └─► FastAPI
         ├─ stocks.py   yfinance prices → detect_movements (|Δ| ≥ threshold%)
         ├─ news/       NewsProvider interface → NewsApiProvider (keyword, ~30-day)
         │                                      → ExaProvider    (semantic, historical)
         │                                      → MockProvider   (keyless fallback)
         └─ chat.py     Claude (claude-haiku-4-5), grounded on movements + news
```

News providers are pluggable (`NEWS_PROVIDER` env var):

- **`newsapi`** (default) — NewsAPI.org. Simple keyword search; free tier covers
  the **last ~30 days**, which fits explaining *recent* movements. Company news is
  precise; industry/macro are approximated with boolean keyword queries.
- **`exa`** — Exa AI. Semantic search with **arbitrary historical** date windows;
  better at linking macro/political articles that never name the ticker. Use when
  you need to explain older movements.
- **`mock`** — labelled placeholder articles so the app runs with **no keys**.

Without an API key for the chosen provider, it automatically falls back to `mock`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/tickers/{ticker}` | Prices + movements + news. Filters: `start`, `end`, `threshold`, `include_news` |
| POST | `/api/chat` | Chat grounded on a ticker's data. Body: `ticker`, `message`, `history[]`, optional `start`/`end`/`threshold` |
| GET | `/api/health` | Which news/chat backends are active |

## Run

### Backend
```bash
python3 -m venv .venv && source .venv/bin/activate   # from repo root
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env                 # add EXA_API_KEY + ANTHROPIC_API_KEY (optional)
cd backend && uvicorn app.main:app --reload --port 8000
```
Docs at http://localhost:8000/docs

### Frontend
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api → :8000)
```

## Keys (all optional)

| Var | Enables | Without it |
|---|---|---|
| `NEWSAPI_API_KEY` | Real news (last ~30 days) — **default** | Labelled `[MOCK]` articles |
| `EXA_API_KEY` | Historical/semantic news (set `NEWS_PROVIDER=exa`) | Labelled `[MOCK]` articles |
| `ANTHROPIC_API_KEY` | Claude-powered chat | Deterministic data summary |

## Movement definition

A **major movement** is a trading day whose close-over-close change satisfies
`|pct_change| ≥ threshold` (default **2%**, configurable per request). News
fan-out is capped to the largest movements to bound external API calls.
