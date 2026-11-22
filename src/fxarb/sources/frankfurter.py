"""ECB euro reference rates via the Frankfurter API.

These are one published *vector* of rates against EUR. Every cross rate is a ratio of
two entries, so every cycle's product telescopes to exactly 1: the graph is consistent by
construction and can contain no arbitrage. Scanning it is a sanity check, not a hunt.
"""

from __future__ import annotations

from typing import Any

from ..graph import Quote

URL = "https://api.frankfurter.dev/v1/latest"


def parse(payload: dict[str, Any], fee: float) -> list[Quote]:
    base = payload["base"]
    vec = {base: 1.0, **{k: float(v) for k, v in payload["rates"].items()}}
    codes = sorted(vec)
    quotes = []
    for i, a in enumerate(codes):
        for b in codes[i + 1 :]:
            mid = vec[b] / vec[a]  # units of b per unit of a
            quotes.append(Quote(a, b, mid, mid, fee=fee, venue="ecb"))
    return quotes


def fetch(fee: float) -> list[Quote]:
    from . import fetch_json

    return parse(fetch_json(URL), fee)
