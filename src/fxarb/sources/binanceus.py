"""Binance.US public REST. (Global binance.com returns HTTP 451 from US addresses.)"""

from __future__ import annotations

from typing import Any

from ..graph import Quote

EXCHANGE_INFO_URL = "https://api.binance.us/api/v3/exchangeInfo"
BOOK_TICKER_URL = "https://api.binance.us/api/v3/ticker/bookTicker"


def parse(exchange_info: dict[str, Any], book: list[dict[str, Any]], fee: float) -> list[Quote]:
    symbols = {
        s["symbol"]: (s["baseAsset"], s["quoteAsset"])
        for s in exchange_info["symbols"]
        if s.get("status") == "TRADING"
    }
    quotes: list[Quote] = []
    for row in book:
        bq = symbols.get(row.get("symbol", ""))
        if bq is None:
            continue
        try:
            quotes.append(
                Quote(
                    bq[0],
                    bq[1],
                    float(row["bidPrice"]),
                    float(row["askPrice"]),
                    float(row["bidQty"]),
                    float(row["askQty"]),
                    fee=fee,
                    venue="binanceus",
                )
            )
        except (KeyError, ValueError):
            continue  # empty side (price 0), crossed or malformed
    return quotes


def fetch(fee: float) -> list[Quote]:
    from . import fetch_json

    return parse(fetch_json(EXCHANGE_INFO_URL), fetch_json(BOOK_TICKER_URL), fee)
