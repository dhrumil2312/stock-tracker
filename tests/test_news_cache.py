"""News cache: scoped fetches are stored once and reused across tickers."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from db import connect, migrate  # noqa: E402

from app.models import Article, Movement  # noqa: E402
from app.services.news.base import NewsProvider, NewsQuery, NewsScope  # noqa: E402
from app.services.news_cache import attach_news  # noqa: E402


def _movement(day: str, pct: float) -> Movement:
    d = date.fromisoformat(day)
    return Movement(
        date=d,
        close=100.0,
        pct_change=pct,
        direction="up" if pct > 0 else "down",
        window_start=d,
        window_end=d,
    )


class CountingProvider(NewsProvider):
    name = "mock"
    query_style = "semantic"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def fetch_scope(
        self, scope: NewsScope, subject: str, query: NewsQuery, max_articles: int
    ) -> list[Article]:
        self.calls.append((scope, subject, query.movement.date.isoformat()))
        return [
            Article(
                title=f"{scope} {subject} {query.movement.date}",
                url=f"https://example.com/{scope}/{subject}/{query.movement.date}",
                source="test",
                published_at=query.movement.date,
                snippet="test snippet",
                category=scope,
            )
        ]


class NewsCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        os.environ["STOCK_TRACKER_DB"] = self.tmp.name
        conn = connect()
        try:
            migrate(conn)
        finally:
            conn.close()
        self.provider = CountingProvider()

    def tearDown(self) -> None:
        os.environ.pop("STOCK_TRACKER_DB", None)
        Path(self.tmp.name).unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(self.tmp.name + suffix).unlink(missing_ok=True)

    def test_second_attach_does_not_call_provider(self) -> None:
        moves = [_movement("2026-09-18", 3.2)]
        attach_news("NVDA", "NVIDIA", "Semiconductors", moves, provider=self.provider)
        first = len(self.provider.calls)
        self.assertGreater(first, 0)
        attach_news("NVDA", "NVIDIA", "Semiconductors", moves, provider=self.provider)
        self.assertEqual(len(self.provider.calls), first)

    def test_industry_and_macro_are_shared_across_tickers(self) -> None:
        nvda = [_movement("2026-09-18", 4.1)]
        amd = [_movement("2026-09-18", 3.5)]
        attach_news("NVDA", "NVIDIA", "Semiconductors", nvda, provider=self.provider)
        attach_news("AMD", "AMD", "Semiconductors", amd, provider=self.provider)
        scopes = [call[0] for call in self.provider.calls]
        self.assertEqual(scopes.count("company"), 2)
        self.assertEqual(scopes.count("industry"), 1)
        self.assertEqual(scopes.count("macro"), 1)
        self.assertTrue(any(a.category == "macro" for a in amd[0].articles))
        self.assertTrue(any(a.category == "industry" for a in amd[0].articles))

    def test_industry_story_about_another_ticker_is_dropped(self) -> None:
        class MixedProvider(CountingProvider):
            def fetch_scope(self, scope, subject, query, max_articles):
                self.calls.append((scope, subject, query.movement.date.isoformat()))
                if scope == "industry":
                    return [
                        Article(
                            title="NVIDIA agrees to buy Hugging Face",
                            url="https://example.com/hf",
                            source="test",
                            published_at=query.movement.date,
                            snippet="Chipmaker buys the model host.",
                            category="industry",
                        )
                    ]
                if scope == "macro":
                    return [
                        Article(
                            title="Fed holds interest rates steady",
                            url="https://example.com/fed",
                            source="test",
                            published_at=query.movement.date,
                            snippet="Policy unchanged.",
                            category="macro",
                        )
                    ]
                return [
                    Article(
                        title=f"{query.ticker} stock {query.movement.date}",
                        url=f"https://example.com/{query.ticker}",
                        source="test",
                        published_at=query.movement.date,
                        snippet="test snippet",
                        category="company",
                    )
                ]

        provider = MixedProvider()
        msft = [_movement("2026-09-18", 2.68)]
        attach_news("MSFT", "Microsoft Corp.", "Software", msft, provider=provider)
        titles = [a.title for a in msft[0].articles]
        self.assertIn("MSFT stock 2026-09-18", titles)
        self.assertIn("Fed holds interest rates steady", titles)
        self.assertNotIn("NVIDIA agrees to buy Hugging Face", titles)

    def test_empty_result_is_not_refetched(self) -> None:
        class EmptyProvider(CountingProvider):
            def fetch_scope(self, scope, subject, query, max_articles):
                self.calls.append((scope, subject, query.movement.date.isoformat()))
                return []

        provider = EmptyProvider()
        moves = [_movement("2026-09-10", -2.4)]
        attach_news("AAPL", "Apple", "Consumer Electronics", moves, provider=provider)
        n = len(provider.calls)
        attach_news("AAPL", "Apple", "Consumer Electronics", moves, provider=provider)
        self.assertEqual(len(provider.calls), n)
        self.assertEqual(moves[0].articles, [])


if __name__ == "__main__":
    unittest.main()
