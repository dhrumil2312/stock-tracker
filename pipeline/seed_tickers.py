"""Hardcoded liquid names to scan. Not the tradeable universe."""

from __future__ import annotations

from typing import TypedDict

SEED_TICKERS: tuple[str, ...] = (
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "NVDA",
    "AMD",
    "AVGO",
    "CRM",
    "ORCL",
    "INTC",
    "QCOM",
    "ADBE",
    "NOW",
    "NFLX",
    "DIS",
    "KO",
    "PEP",
    "WMT",
    "COST",
    "TSLA",
    "F",
    "UBER",
    "MCD",
    "SBUX",
    "JPM",
    "BAC",
    "GS",
    "V",
    "MA",
    "UNH",
    "JNJ",
    "LLY",
    "PFE",
    "ABBV",
    "MRK",
    "XOM",
    "CVX",
    "COP",
    "CAT",
    "BA",
    "GE",
    "HD",
    "NKE",
    "SPY",
    "QQQ",
)


def load_seed() -> list[str]:
    seen: list[str] = []
    for raw in SEED_TICKERS:
        ticker = raw.strip().upper()
        if ticker and ticker not in seen:
            seen.append(ticker)
    return seen


class CompanyMeta(TypedDict):
    name: str
    exchange: str
    sector: str
    industry: str


COMPANY_META: dict[str, CompanyMeta] = {
    "AAPL": {"name": "Apple Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Consumer Electronics"},
    "MSFT": {"name": "Microsoft Corp.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software"},
    "GOOGL": {"name": "Alphabet Inc.", "exchange": "NASDAQ", "sector": "Communication Services", "industry": "Internet Content"},
    "AMZN": {"name": "Amazon.com Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Internet Retail"},
    "META": {"name": "Meta Platforms Inc.", "exchange": "NASDAQ", "sector": "Communication Services", "industry": "Internet Content"},
    "NVDA": {"name": "NVIDIA Corp.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors"},
    "AMD": {"name": "Advanced Micro Devices", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors"},
    "AVGO": {"name": "Broadcom Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors"},
    "CRM": {"name": "Salesforce Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Software"},
    "ORCL": {"name": "Oracle Corp.", "exchange": "NYSE", "sector": "Technology", "industry": "Software"},
    "INTC": {"name": "Intel Corp.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors"},
    "QCOM": {"name": "QUALCOMM Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors"},
    "ADBE": {"name": "Adobe Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software"},
    "NOW": {"name": "ServiceNow Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Software"},
    "NFLX": {"name": "Netflix Inc.", "exchange": "NASDAQ", "sector": "Communication Services", "industry": "Entertainment"},
    "DIS": {"name": "Walt Disney Co.", "exchange": "NYSE", "sector": "Communication Services", "industry": "Entertainment"},
    "KO": {"name": "Coca-Cola Co.", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Beverages"},
    "PEP": {"name": "PepsiCo Inc.", "exchange": "NASDAQ", "sector": "Consumer Defensive", "industry": "Beverages"},
    "WMT": {"name": "Walmart Inc.", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Discount Stores"},
    "COST": {"name": "Costco Wholesale", "exchange": "NASDAQ", "sector": "Consumer Defensive", "industry": "Discount Stores"},
    "TSLA": {"name": "Tesla Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers"},
    "F": {"name": "Ford Motor Co.", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers"},
    "UBER": {"name": "Uber Technologies", "exchange": "NYSE", "sector": "Technology", "industry": "Software"},
    "MCD": {"name": "McDonald's Corp.", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Restaurants"},
    "SBUX": {"name": "Starbucks Corp.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Restaurants"},
    "JPM": {"name": "JPMorgan Chase", "exchange": "NYSE", "sector": "Financial Services", "industry": "Banks"},
    "BAC": {"name": "Bank of America", "exchange": "NYSE", "sector": "Financial Services", "industry": "Banks"},
    "GS": {"name": "Goldman Sachs", "exchange": "NYSE", "sector": "Financial Services", "industry": "Capital Markets"},
    "V": {"name": "Visa Inc.", "exchange": "NYSE", "sector": "Financial Services", "industry": "Credit Services"},
    "MA": {"name": "Mastercard Inc.", "exchange": "NYSE", "sector": "Financial Services", "industry": "Credit Services"},
    "UNH": {"name": "UnitedHealth Group", "exchange": "NYSE", "sector": "Healthcare", "industry": "Healthcare Plans"},
    "JNJ": {"name": "Johnson & Johnson", "exchange": "NYSE", "sector": "Healthcare", "industry": "Drug Manufacturers"},
    "LLY": {"name": "Eli Lilly", "exchange": "NYSE", "sector": "Healthcare", "industry": "Drug Manufacturers"},
    "PFE": {"name": "Pfizer Inc.", "exchange": "NYSE", "sector": "Healthcare", "industry": "Drug Manufacturers"},
    "ABBV": {"name": "AbbVie Inc.", "exchange": "NYSE", "sector": "Healthcare", "industry": "Drug Manufacturers"},
    "MRK": {"name": "Merck & Co.", "exchange": "NYSE", "sector": "Healthcare", "industry": "Drug Manufacturers"},
    "XOM": {"name": "Exxon Mobil", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas"},
    "CVX": {"name": "Chevron Corp.", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas"},
    "COP": {"name": "ConocoPhillips", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas"},
    "CAT": {"name": "Caterpillar Inc.", "exchange": "NYSE", "sector": "Industrials", "industry": "Farm & Heavy Machinery"},
    "BA": {"name": "Boeing Co.", "exchange": "NYSE", "sector": "Industrials", "industry": "Aerospace & Defense"},
    "GE": {"name": "GE Aerospace", "exchange": "NYSE", "sector": "Industrials", "industry": "Aerospace & Defense"},
    "HD": {"name": "Home Depot", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Home Improvement"},
    "NKE": {"name": "Nike Inc.", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Footwear & Accessories"},
    "SPY": {"name": "SPDR S&P 500 ETF", "exchange": "NYSE Arca", "sector": "ETF", "industry": "Large Blend"},
    "QQQ": {"name": "Invesco QQQ Trust", "exchange": "NASDAQ", "sector": "ETF", "industry": "Large Growth"},
}


def company_meta(ticker: str) -> CompanyMeta | None:
    return COMPANY_META.get(ticker.strip().upper())
