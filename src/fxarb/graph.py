"""Quote graph: assets are vertices, executable conversions are weighted directed edges.

A quote for the pair BASE/QUOTE with best bid ``b`` and best ask ``a`` gives two edges:

* sell BASE at the bid:  BASE -> QUOTE with rate ``b * (1 - fee)``
* buy BASE at the ask:   QUOTE -> BASE with rate ``(1 / a) * (1 - fee)``

Every edge has weight ``-log(rate)``, so a cycle whose rates multiply to more than 1
(a profitable round trip) is exactly a cycle of negative total weight.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

__all__ = ["Edge", "Quote", "QuoteGraph"]


def _check_positive_finite(name: str, value: float) -> None:
    if not (isinstance(value, int | float) and math.isfinite(value) and value > 0):
        raise ValueError(f"{name} must be a positive finite number, got {value!r}")


@dataclass(frozen=True, slots=True)
class Quote:
    """Top of book for one trading pair on one venue.

    ``bid_size`` and ``ask_size`` are quantities of the BASE asset available at the
    best bid and best ask. ``fee`` is the proportional taker fee (0.004 = 0.40%).
    """

    base: str
    quote: str
    bid: float
    ask: float
    bid_size: float = math.inf
    ask_size: float = math.inf
    fee: float = 0.0
    venue: str = ""

    def __post_init__(self) -> None:
        if not self.base or not self.quote:
            raise ValueError("base and quote must be non-empty")
        if self.base == self.quote:
            raise ValueError(f"base and quote must differ, got {self.base}/{self.quote}")
        _check_positive_finite("bid", self.bid)
        _check_positive_finite("ask", self.ask)
        if self.bid > self.ask:
            raise ValueError(
                f"crossed book for {self.base}/{self.quote}: bid {self.bid} > ask {self.ask}"
            )
        for name, size in (("bid_size", self.bid_size), ("ask_size", self.ask_size)):
            if not (size > 0):  # also rejects NaN; inf allowed (unknown depth)
                raise ValueError(f"{name} must be positive, got {size!r}")
        if not (0.0 <= self.fee < 1.0):
            raise ValueError(f"fee must be in [0, 1), got {self.fee!r}")

    @property
    def pair(self) -> str:
        return f"{self.base}/{self.quote}"


@dataclass(frozen=True, slots=True)
class Edge:
    """One executable conversion u -> v.

    ``rate`` is units of v received per unit of u, after fees.
    ``capacity`` is the most units of u this leg can absorb (top-of-book depth).
    """

    u: int
    v: int
    rate: float
    capacity: float = math.inf
    venue: str = ""
    pair: str = ""
    side: str = ""  # "sell" (base -> quote at the bid) or "buy" (quote -> base at the ask)

    @property
    def weight(self) -> float:
        return -math.log(self.rate)


@dataclass
class QuoteGraph:
    """Directed graph of conversions. Keeps the single best edge per ordered pair (u, v).

    Keeping only the best parallel edge loses no arbitrage: any cycle through a worse
    parallel edge has a better twin through the best one.
    """

    assets: list[str] = field(default_factory=list)
    _index: dict[str, int] = field(default_factory=dict, repr=False)
    _best: dict[tuple[int, int], Edge] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ building
    def vertex(self, asset: str) -> int:
        """Index of ``asset``, adding it if new."""
        idx = self._index.get(asset)
        if idx is None:
            idx = len(self.assets)
            self.assets.append(asset)
            self._index[asset] = idx
        return idx

    def index(self, asset: str) -> int:
        return self._index[asset]

    def __contains__(self, asset: object) -> bool:
        return asset in self._index

    def add_rate(
        self,
        u: str,
        v: str,
        rate: float,
        *,
        capacity: float = math.inf,
        venue: str = "",
        pair: str = "",
        side: str = "",
    ) -> None:
        """Add the conversion u -> v at ``rate`` (keeps it only if it beats the current best)."""
        if u == v:
            raise ValueError("self-loops are not conversions")
        _check_positive_finite("rate", rate)
        if not (capacity > 0):
            raise ValueError(f"capacity must be positive, got {capacity!r}")
        iu, iv = self.vertex(u), self.vertex(v)
        cur = self._best.get((iu, iv))
        if cur is None or rate > cur.rate:
            self._best[(iu, iv)] = Edge(iu, iv, rate, capacity, venue, pair, side)

    def add_quote(self, q: Quote) -> None:
        keep = 1.0 - q.fee
        # Sell 1 BASE at the bid -> bid*(1-fee) QUOTE. Capacity in BASE units.
        self.add_rate(
            q.base,
            q.quote,
            q.bid * keep,
            capacity=q.bid_size,
            venue=q.venue,
            pair=q.pair,
            side="sell",
        )
        # Spend 1 QUOTE buying BASE at the ask -> (1/ask)*(1-fee) BASE.
        # Capacity in QUOTE units = ask_size * ask.
        self.add_rate(
            q.quote,
            q.base,
            keep / q.ask,
            capacity=q.ask_size * q.ask,
            venue=q.venue,
            pair=q.pair,
            side="buy",
        )

    @classmethod
    def from_quotes(cls, quotes: Iterable[Quote]) -> QuoteGraph:
        g = cls()
        for q in quotes:
            g.add_quote(q)
        return g

    @classmethod
    def from_rate_matrix(cls, rates: Mapping[str, Mapping[str, float]]) -> QuoteGraph:
        """Build from ``rates[u][v]`` = units of v per unit of u (missing = no quote)."""
        g = cls()
        for u in rates:
            g.vertex(u)
        for u, row in rates.items():
            for v, r in row.items():
                if u != v:
                    g.add_rate(u, v, r)
        return g

    # ------------------------------------------------------------------ views
    @property
    def n(self) -> int:
        return len(self.assets)

    @property
    def edges(self) -> list[Edge]:
        return list(self._best.values())

    def edge(self, u: int, v: int) -> Edge:
        return self._best[(u, v)]

    def weighted_edges(self) -> list[tuple[int, int, float]]:
        """(u, v, -log rate) triples: the input the algorithms work on."""
        return [(e.u, e.v, -math.log(e.rate)) for e in self._best.values()]

    def without_edge(self, u: int, v: int) -> QuoteGraph:
        """Copy with one edge removed (used to look for further distinct cycles)."""
        g = QuoteGraph(list(self.assets), dict(self._index), dict(self._best))
        g._best.pop((u, v), None)
        return g

    def __len__(self) -> int:
        return len(self._best)
