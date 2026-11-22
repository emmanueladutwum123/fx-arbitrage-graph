"""fxarb: find currency and crypto arbitrage as negative cycles in a quote graph."""

from .bellman_ford import DEFAULT_EPS, SearchResult, bellman_ford, spfa
from .graph import Edge, Quote, QuoteGraph
from .profit import CycleReport, evaluate_cycle, find_cycles, find_negative_cycle

__all__ = [
    "DEFAULT_EPS",
    "CycleReport",
    "Edge",
    "Quote",
    "QuoteGraph",
    "SearchResult",
    "bellman_ford",
    "evaluate_cycle",
    "find_cycles",
    "find_negative_cycle",
    "spfa",
]

__version__ = "0.1.0"
