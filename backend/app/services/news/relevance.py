"""Drop articles that are really about another seeded name.

Industry/macro fetches are shared by date, so a NVIDIA deal can land on MSFT's
day. Filter at attach time (per ticker) so the cache stays shared.
"""
from __future__ import annotations

import re

from pipeline.seed_tickers import COMPANY_META, load_seed

from ...models import Article

_SUFFIX = re.compile(
    r"\s+(inc\.?|corp\.?|corporation|co\.?|ltd\.?|llc\.?|plc\.?|platforms)\.?$",
    re.IGNORECASE,
)


def filter_for_ticker(
    articles: list[Article],
    *,
    ticker: str,
    company_name: str | None,
    industry: str | None = None,
) -> list[Article]:
    self_aliases = _aliases(ticker, company_name)
    peers = _peer_aliases(ticker)
    industry_aliases = _industry_aliases(industry)
    return [
        art
        for art in articles
        if _keep(art, self_aliases, peers, industry_aliases)
    ]


def _keep(
    art: Article,
    self_aliases: list[str],
    peers: list[tuple[str, str]],
    industry_aliases: list[str],
) -> bool:
    text = f"{art.title} {art.snippet or ''}"
    mentions_self = _mentions_any(text, self_aliases)
    peer_hit = _mentioned_peer(text, peers)
    if art.category == "company":
        return mentions_self or not peer_hit
    if peer_hit and not mentions_self:
        return False
    if art.category == "industry" and industry_aliases:
        return mentions_self or _mentions_any(text, industry_aliases) or not peer_hit
    return True


def _aliases(ticker: str, company_name: str | None) -> list[str]:
    names = [ticker]
    if company_name:
        names.append(company_name)
        names.extend(_brand_parts(company_name))
    meta = COMPANY_META.get(ticker.upper())
    if meta:
        names.append(meta["name"])
        names.extend(_brand_parts(meta["name"]))
    return _unique(names)


def _peer_aliases(ticker: str) -> list[tuple[str, str]]:
    mine = ticker.upper()
    out: list[tuple[str, str]] = []
    for other in load_seed():
        if other == mine:
            continue
        for alias in _aliases(other, None):
            out.append((other, alias))
    return out


def _industry_aliases(industry: str | None) -> list[str]:
    if not industry:
        return []
    parts = [industry]
    for token in re.split(r"[\s/,|-]+", industry):
        if len(token) > 3:
            parts.append(token)
    return _unique(parts)


def _brand_parts(name: str) -> list[str]:
    stripped = _SUFFIX.sub("", name.strip()).strip(" .,")
    if not stripped:
        return []
    parts = [stripped]
    first = stripped.split()[0]
    if len(first) > 3 and first.lower() not in {"advanced", "general", "united", "international"}:
        parts.append(first)
    return parts


def _mentioned_peer(text: str, peers: list[tuple[str, str]]) -> bool:
    return any(_mentions(text, alias) for _ticker, alias in peers)


def _mentions_any(text: str, aliases: list[str]) -> bool:
    return any(_mentions(text, alias) for alias in aliases)


def _mentions(text: str, alias: str) -> bool:
    token = alias.strip()
    if not token:
        return False
    if re.fullmatch(r"[A-Z]{1,5}", token):
        return (
            re.search(rf"(?<![A-Za-z])\$?{re.escape(token)}(?![A-Za-z])", text) is not None
        )
    return re.search(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", text, re.IGNORECASE) is not None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value.strip())
    return out
