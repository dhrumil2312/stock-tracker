# Price pipeline

Standalone job. It fetches 30 days of prices, flags days with `|daily return| >= 2%`, and materializes a **tradeable universe**. It does not serve HTTP, does not talk to chat, and does not call any news API.

Full data-layer rules: [database.md](database.md).

## Why this split

News quota is scarce. Scanning ~40 tickers every run would burn it. Prices are free (yfinance). So:

1. Pipeline builds the universe and stores move dates.
2. Chat (later) only accepts a universe ticker, then fetches news for **that ticker’s move windows**.

Ticker data and chat stay separate products on the same database.

```
seed list (~40 liquid names)
        |
        v
  yfinance 30d daily bars
        |
        v
  daily_return from adj_close
        |
        v
  price_moves where abs(return) >= 0.02
        |
        v
  companies.in_universe = 1 if the ticker has >= 1 move
        |
        v
  SQLite (shared db/)
        |
        +--> later API: list universe, get bars + moves
        |
        +--> later chat: user enters universe ticker -> fetch news then
```

## Seed vs universe

| Set | Meaning | Where |
| --- | --- | --- |
| Seed | Names we **scan** | `pipeline/seed_tickers.py` (hardcoded) |
| Tradeable universe | Seed names with **at least one** `\|daily_return\| >= 2%` in the window | `companies.in_universe = 1` |

A quiet mega-cap with no 2% day is stored in `companies` and `price_bars` but is **not** tradeable.

## Seed list (v1)

About 40 liquid names, mixed sectors. Uppercase, no `BRK.B`-style suffixes in v1.

- Tech: `AAPL MSFT GOOGL AMZN META NVDA AMD AVGO CRM ORCL`
- Comm / consumer: `NFLX DIS KO PEP WMT COST TSLA F`
- Finance: `JPM BAC GS V MA`
- Health: `UNH JNJ LLY PFE`
- Energy / industrial: `XOM CVX CAT BA`
- Other: `HD NKE SPY QQQ` (ETFs so macro days still produce moves)

Plus a few more liquid names at implement time to land near 40–50. Skip blanks; de-dupe.

## Stages

### 1. Load seed

Read the static list. This is not the universe.

### 2. Migrate then connect

`db.migrate(conn)` then write. Empty or stale files get schema v1 automatically.

### 3. Batch download

```python
yf.download(seed, period="1mo", interval="1d", auto_adjust=False, group_by="ticker", threads=True)
```

Empty / all-NaN tickers are logged, kept `in_universe = 0`, and do not fail the whole job.

Company metadata (`name`, `sector`, `industry`, `exchange`) is best-effort and **only** for names that make the universe if `Ticker.info` is slow. Ticker string is enough as `name` for a first run.

### 4. Daily returns

Sort bars by date. Persist `price_bars`.

```
daily_return_t = (adj_close_t - adj_close_t-1) / adj_close_t-1
```

First bar: `daily_return` is NULL and cannot be a move.

### 5. Major-move days

Insert `price_moves` for every bar with `abs(daily_return) >= 0.02`.

| Field | Rule |
| --- | --- |
| `direction` | `up` if return > 0 else `down` |
| `window_start` | previous **trading** date (overnight / weekend news later) |
| `window_end` | move date + 1 **calendar** day |
| `threshold` | `0.02` |

Store every qualifying day. No “top N” cap (that only mattered when news ran in-pipeline).

On re-run: upsert bars on `(ticker, date)`; delete and replace `price_moves` for scanned tickers in the lookback; recompute `in_universe`.

### 6. Tradeable universe

- Start from `in_universe = 0` for the seed.
- Set `1` if the ticker has ≥1 `price_moves` row.
- Guardrail (seed is already liquid): skip universe if last `adj_close < 5` or 30-day average volume is tiny.

### 7. Run record

One row in `pipeline_runs`: seed size, bars upserted, moves found, universe size, status (`running` → `success` | `partial` | `failed`), error text.

`partial` = download worked for some tickers, others empty. Exit code 0 unless the download fails entirely (exit 1).

## CLI

```
python -m pipeline.run
```

Prints seed count, failures, universe tickers, and per-ticker move dates/magnitudes.

No HTTP. No news. No chat.

## Package layout

```
pipeline/
├── __init__.py
├── seed_tickers.py    # SEED_TICKERS + load_seed()
├── prices.py          # download, returns, persist bars + moves
├── universe.py        # refresh in_universe
└── run.py             # CLI orchestrator
```

`pipeline` imports `db`. `db` does not import `pipeline`.

## Later handoff (not this job)

**Ticker API:** list `WHERE in_universe = 1`; return bars + moves for one universe ticker.

**Chat:** user must enter a universe ticker. Load that ticker’s `price_moves` windows, fetch news then, cache by ticker. Until that happens, news quota is unused.




hmm this is much better but we removed the data fro mthe ehader row. Oh les add the open hight low and closed and vol symmetrically in the header itself? And how can we make sure the news are really related to the move? 
example MSFT went up 2.68% and the news for indestry are NVIDA agrees to buy hugging face not sure if they both are dirrectly related? 