"""Industry/macro stories about another seeded name should not explain this move."""
from __future__ import annotations

from app.models import Article
from app.services.news.relevance import filter_for_ticker


def _art(title: str, category: str, snippet: str = "") -> Article:
    return Article(
        title=title,
        url=f"https://example.com/{title}",
        snippet=snippet or None,
        category=category,
    )


def test_drops_nvidia_deal_from_msft_industry_news() -> None:
    kept = filter_for_ticker(
        [_art("NVIDIA agrees to buy Hugging Face", "industry")],
        ticker="MSFT",
        company_name="Microsoft Corp.",
        industry="Software",
    )
    assert kept == []


def test_keeps_sector_news_without_a_peer_name() -> None:
    kept = filter_for_ticker(
        [_art("Software sector faces new cloud regulation", "industry")],
        ticker="MSFT",
        company_name="Microsoft Corp.",
        industry="Software",
    )
    assert len(kept) == 1


def test_keeps_company_story_for_that_ticker() -> None:
    kept = filter_for_ticker(
        [_art("Microsoft beats earnings estimates", "company")],
        ticker="MSFT",
        company_name="Microsoft Corp.",
        industry="Software",
    )
    assert len(kept) == 1


def test_keeps_macro_without_single_stock_hook() -> None:
    kept = filter_for_ticker(
        [_art("Fed holds interest rates steady", "macro")],
        ticker="MSFT",
        company_name="Microsoft Corp.",
        industry="Software",
    )
    assert len(kept) == 1


def test_drops_macro_that_is_really_another_stock() -> None:
    kept = filter_for_ticker(
        [_art("NVIDIA soars after the Fed decision", "macro")],
        ticker="MSFT",
        company_name="Microsoft Corp.",
        industry="Software",
    )
    assert kept == []
