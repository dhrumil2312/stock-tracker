"""Errors raised when ticker data cannot be served."""
from __future__ import annotations


class StockDataError(Exception):
    """Raised when a ticker is unknown or has no stored price data."""
