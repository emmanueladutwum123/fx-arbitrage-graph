"""What a cycle is worth: product of rates, net return, and the largest tradable size."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .bellman_ford import DEFAULT_EPS, SearchResult, bellman_ford, spfa
from .graph import Edge, QuoteGraph

__all__ = [
    "PREFERRED_STARTS",
    "CycleReport",
    "canonical_key",
    "evaluate_cycle",
    "find_cycles",
    "find_negative_cycle",
    "rotate_to_preferred",
]

#: When a cycle passes through one of these, report it starting there (easier to read).
PREFERRED_STARTS = ("USD", "EUR", "USDT", "USDC", "GBP", "BTC", "ETH", "JPY")


@dataclass(frozen=True)
class CycleReport:
    assets: list[str]
    """Closed cycle in trading order, e.g. ['USD', 'BTC', 'ETH', 'USD']."""
    legs: list[Edge]
    product: float
    """Product of after-fee rates. > 1 means the round trip makes money."""
    weight: float
    """Sum of -log(rate) over the legs. Equals -log(product); < 0 iff product > 1."""
    max_size: float
    """Largest starting amount (in units of assets[0]) that every leg can fill at the quoted
    top-of-book price. The tightest leg bounds the whole cycle."""
    bottleneck: int
    """Index into ``legs`` of the leg that sets ``max_size``."""

    @property
    def net_return(self) -> float:
        return self.product - 1.0

    @property
    def max_profit(self) -> float:
        """Profit in units of assets[0] at max_size (inf if depth is unknown)."""
        return self.max_size * self.net_return

    @property
    def length(self) -> int:
        return len(self.legs)

    def describe(self) -> str:
        return " → ".join(self.assets)


def evaluate_cycle(graph: QuoteGraph, cycle: Sequence[int]) -> CycleReport:
    """Price a closed cycle ``[v0, ..., v0]`` on ``graph``.

    Max size: if we start with x units of v0, the amount entering leg i is
    x * r_0 * ... * r_{i-1}, and it must not exceed leg i's capacity c_i. So
    x <= c_i / (r_0 ... r_{i-1}) for every i, and max_size is the minimum of those bounds.
    """
    if len(cycle) < 3 or cycle[0] != cycle[-1]:
        raise ValueError("cycle must be closed and have at least 2 legs: [v0, v1, ..., v0]")
    legs = [graph.edge(cycle[i], cycle[i + 1]) for i in range(len(cycle) - 1)]
    product = 1.0
    weight = 0.0
    max_size = math.inf
    bottleneck = 0
    running = 1.0  # units entering the current leg per 1 unit of v0
    for i, e in enumerate(legs):
        bound = e.capacity / running
        if bound < max_size:
            max_size, bottleneck = bound, i
        running *= e.rate
        product *= e.rate
        weight += e.weight
    return CycleReport(
        assets=[graph.assets[i] for i in cycle],
        legs=legs,
        product=product,
        weight=weight,
        max_size=max_size,
        bottleneck=bottleneck,
    )


def rotate_to_preferred(cycle: Sequence[int], graph: QuoteGraph) -> list[int]:
    """Same cycle, started at the most familiar asset on it (product is unchanged)."""
    body = list(cycle[:-1])
    names = [graph.assets[i] for i in body]
    for pref in PREFERRED_STARTS:
        if pref in names:
            k = names.index(pref)
            body = body[k:] + body[:k]
            break
    return [*body, body[0]]


def canonical_key(assets: Sequence[str]) -> str:
    """Rotation-independent identity of a closed cycle, used to track it over time."""
    body = list(assets[:-1])
    k = min(range(len(body)), key=lambda i: body[i:] + body[:i])
    body = body[k:] + body[:k]
    return ">".join(body)


def find_negative_cycle(
    graph: QuoteGraph, method: str = "spfa", eps: float = DEFAULT_EPS
) -> SearchResult:
    edges = graph.weighted_edges()
    if method == "bf":
        return bellman_ford(graph.n, edges, eps)
    if method == "spfa":
        return spfa(graph.n, edges, eps)
    raise ValueError(f"unknown method {method!r} (use 'bf' or 'spfa')")


def find_cycles(
    graph: QuoteGraph,
    limit: int = 10,
    method: str = "spfa",
    eps: float = DEFAULT_EPS,
    min_return: float = 0.0,
) -> list[CycleReport]:
    """Up to ``limit`` distinct profitable cycles.

    Greedy, not exhaustive: after each cycle is found, its weakest-capacity leg is
    deleted and the search is rerun, so later cycles must avoid that leg.
    Cycles whose net return is not above ``min_return`` are dropped (they arise only
    from float noise at the eps boundary).
    """
    found: list[CycleReport] = []
    seen: set[str] = set()
    g = graph
    for _ in range(limit * 3):  # some rounds may rediscover a rotation; cap the work
        if len(found) >= limit:
            break
        res = find_negative_cycle(g, method, eps)
        if res.cycle is None:
            break
        cyc = rotate_to_preferred(res.cycle, g)
        rep = evaluate_cycle(g, cyc)
        cut = rep.legs[rep.bottleneck]
        g = g.without_edge(cut.u, cut.v)
        key = canonical_key(rep.assets)
        if key in seen or rep.net_return <= min_return:
            continue
        seen.add(key)
        found.append(rep)
    return found
