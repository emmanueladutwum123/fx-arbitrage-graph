"""Brute-force reference: enumerate every simple directed cycle. Exponential; tests only."""

from __future__ import annotations

from collections.abc import Iterator

from .bellman_ford import WeightedEdges

__all__ = ["min_cycle_weight", "simple_cycles"]

MAX_BRUTE_N = 9


def simple_cycles(n: int, edges: WeightedEdges) -> Iterator[tuple[list[int], float]]:
    """Yield ``(closed_cycle, total_weight)`` for every simple cycle, each exactly once.

    Each cycle is generated from its smallest vertex, visiting only larger vertices,
    so rotations are never repeated.
    """
    if n > MAX_BRUTE_N:
        raise ValueError(f"brute force is for tiny graphs (n <= {MAX_BRUTE_N}), got n={n}")
    adj: list[list[tuple[int, float]]] = [[] for _ in range(n)]
    for u, v, w in edges:
        adj[u].append((v, w))

    def dfs(
        start: int, x: int, path: list[int], wsum: float, on: list[bool]
    ) -> Iterator[tuple[list[int], float]]:
        for y, w in adj[x]:
            if y == start:
                yield [*path, start], wsum + w
            elif y > start and not on[y]:
                on[y] = True
                path.append(y)
                yield from dfs(start, y, path, wsum + w, on)
                path.pop()
                on[y] = False

    for s in range(n):
        on = [False] * n
        on[s] = True
        yield from dfs(s, s, [s], 0.0, on)


def min_cycle_weight(n: int, edges: WeightedEdges) -> tuple[list[int] | None, float]:
    """The most negative simple cycle and its weight (``(None, inf)`` if acyclic)."""
    best: list[int] | None = None
    best_w = float("inf")
    for cyc, w in simple_cycles(n, edges):
        if w < best_w:
            best, best_w = cyc, w
    return best, best_w
