# Design docs

Shared data layer and the price pipeline. Chat, news, and HTTP APIs are out of scope here; they will read the same database later.

| Doc | What it locks |
| --- | --- |
| [database.md](database.md) | SQLite location, migrations, schema, who reads/writes |
| [pipeline.md](pipeline.md) | Seed scan, >=2% moves, tradeable universe, CLI |

Target layout after implementation:

```
stock-tracker/
├── docs/
│   ├── README.md
│   ├── database.md
│   └── pipeline.md
├── db/                         # shared by pipeline and backend
│   ├── __init__.py             # connect()
│   ├── migrate.py              # apply pending SQL files
│   └── migrations/
│       └── 001_initial.sql
├── pipeline/                   # writes prices + universe only
│   ├── __init__.py
│   ├── seed_tickers.py
│   ├── prices.py
│   ├── universe.py
│   └── run.py
├── data/
│   └── stock_tracker.db        # runtime; gitignored
├── backend/                    # later: reads db, serves API/chat
├── frontend/                   # later
└── requirements.txt
```
