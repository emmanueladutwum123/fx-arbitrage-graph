"""Public market-data sources (no API keys). Each returns a list of :class:`fxarb.Quote`."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from ..graph import Quote

__all__ = ["DEFAULT_FEES", "FETCHERS", "fetch_json", "fetch_quotes"]

USER_AGENT = "fxarb/0.1 (+https://github.com/emmanueladutwum123/fx-arbitrage-graph)"

#: Entry-tier spot TAKER fees, checked 2026-11-21 on each exchange's own fee page
#: (kraken.com/pro/fees: Tier 1 0.40% maker / 0.80% taker; binance.us/en/fee: 0% maker /
#: 0.02% taker on all pairs except BNB/USD). Fees change: override with --fee.
DEFAULT_FEES: dict[str, float] = {
    "kraken": 0.0080,
    "binanceus": 0.0002,
    "frankfurter": 0.0,
}


def fetch_json(url: str, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def fetch_quotes(venue: str, fee: float | None = None) -> list[Quote]:
    """Live top-of-book quotes from ``venue`` with ``fee`` applied (default: entry tier)."""
    try:
        fetcher = FETCHERS[venue]
    except KeyError:
        raise ValueError(f"unknown venue {venue!r}; choose from {sorted(FETCHERS)}") from None
    return fetcher(DEFAULT_FEES[venue] if fee is None else fee)


from . import binanceus, frankfurter, kraken  # noqa: E402

FETCHERS = {
    "kraken": kraken.fetch,
    "binanceus": binanceus.fetch,
    "frankfurter": frankfurter.fetch,
}
