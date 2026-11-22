"""Kraken public REST: every spot pair's best bid/ask in one request."""

from __future__ import annotations

from typing import Any

from ..graph import Quote

ASSET_PAIRS_URL = "https://api.kraken.com/0/public/AssetPairs"
TICKER_URL = "https://api.kraken.com/0/public/Ticker"

#: Kraken's legacy asset codes -> common tickers.
RENAME = {"XBT": "BTC", "XDG": "DOGE"}


def _name(code: str) -> str:
    return RENAME.get(code, code)


def parse(asset_pairs: dict[str, Any], ticker: dict[str, Any], fee: float) -> list[Quote]:
    """Turn raw AssetPairs + Ticker responses into quotes. Skips pairs that are offline,
    dark-pool, missing a quote, or have a zero/crossed book (counted, never invented)."""
    if asset_pairs.get("error") or ticker.get("error"):
        raise RuntimeError(f"Kraken error: {asset_pairs.get('error') or ticker.get('error')}")
    pairs = asset_pairs["result"]
    tick = ticker["result"]
    by_alt = {p.get("altname"): k for k, p in pairs.items()}
    quotes: list[Quote] = []
    for key, t in tick.items():
        meta = pairs.get(key) or pairs.get(by_alt.get(key, ""))
        if not meta or meta.get("status", "online") != "online" or key.endswith(".d"):
            continue
        ws = meta.get("wsname", "")
        if "/" not in ws:
            continue
        base, quote = (_name(x) for x in ws.split("/", 1))
        try:
            ask, ask_vol = float(t["a"][0]), float(t["a"][2])
            bid, bid_vol = float(t["b"][0]), float(t["b"][2])
            quotes.append(Quote(base, quote, bid, ask, bid_vol, ask_vol, fee=fee, venue="kraken"))
        except (KeyError, IndexError, ValueError):
            continue  # zero price, zero size, crossed book or malformed row
    return quotes


def fetch(fee: float) -> list[Quote]:
    from . import fetch_json

    return parse(fetch_json(ASSET_PAIRS_URL), fetch_json(TICKER_URL), fee)
