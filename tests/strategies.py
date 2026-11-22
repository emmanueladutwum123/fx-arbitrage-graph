"""Hypothesis strategies for random markets."""

from __future__ import annotations

import itertools
import math

from hypothesis import strategies as st

from fxarb import Quote

ASSETS = ["USD", "EUR", "GBP", "JPY", "GHS", "BTC", "ETH", "SOL"]


@st.composite
def consistent_market(
    draw: st.DrawFn,
    min_assets: int = 2,
    max_assets: int = 8,
    min_spread: float = 1e-5,
) -> tuple[list[Quote], dict[str, float]]:
    """A market priced from one hidden 'true value' per asset, plus a positive spread and
    a non-negative fee on every pair. Returns (quotes, true_values_in_USD)."""
    n = draw(st.integers(min_assets, max_assets))
    names = ASSETS[:n]
    # log-uniform true values across 8 orders of magnitude (JPY ~ 0.007 .. BTC ~ 1e5)
    logs = draw(st.lists(st.floats(-6, 6), min_size=n, max_size=n))
    value = {a: math.exp(x) for a, x in zip(names, logs, strict=True)}
    pairs = list(itertools.combinations(names, 2))
    keep = draw(st.lists(st.booleans(), min_size=len(pairs), max_size=len(pairs)))
    quotes: list[Quote] = []
    for (a, b), k in zip(pairs, keep, strict=True):
        if not k:
            continue
        mid = value[a] / value[b]  # units of b per unit of a
        s = draw(st.floats(min_spread, 0.01))
        f = draw(st.floats(0.0, 0.005))
        quotes.append(Quote(a, b, bid=mid * (1 - s), ask=mid * (1 + s), fee=f, venue="fair"))
    return quotes, value


@st.composite
def random_rate_graph(draw: st.DrawFn, max_n: int = 6) -> tuple[int, list[tuple[int, int, float]]]:
    """Arbitrary small digraph with log-normal rates: negative cycles are common."""
    n = draw(st.integers(1, max_n))
    edges: list[tuple[int, int, float]] = []
    for u in range(n):
        for v in range(n):
            if u != v and draw(st.booleans()):
                edges.append((u, v, draw(st.floats(-0.5, 0.5))))  # weight = -log(rate)
    order = draw(st.permutations(range(len(edges))))
    return n, [edges[i] for i in order]
