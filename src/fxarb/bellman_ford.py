"""Negative-cycle detection: Bellman–Ford and SPFA (queue-based Bellman–Ford).

Both run from a *virtual source*: an extra vertex with a 0-weight edge to every real
vertex. We never materialise it; we simply start every distance at 0 and treat
"pred = -1" as "reached directly from the virtual source".

Cycles are returned closed and in trading order: ``[v0, v1, ..., vk, v0]`` means
trade v0 -> v1 -> ... -> vk -> v0.

See ``docs/theory.md`` for the proofs behind every step here.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "DEFAULT_EPS",
    "SearchResult",
    "bellman_ford",
    "cycle_from_pred",
    "find_pred_cycle",
    "spfa",
]

#: A relaxation must improve a distance by more than this to count. Weights are
#: -log(rate); 1e-12 in log space is a relative price change of 1e-12, far below any
#: real price tick, and well above accumulated float rounding on graphs of this size.
DEFAULT_EPS = 1e-12

WeightedEdges = Sequence[tuple[int, int, float]]


@dataclass(frozen=True, slots=True)
class SearchResult:
    cycle: list[int] | None
    """Closed negative cycle ``[v0, ..., v0]`` in trading order, or None."""
    rounds: int
    """Bellman–Ford rounds (or SPFA passes) executed."""
    relaxations: int
    """Successful distance updates."""
    edge_scans: int
    """Edge relaxation attempts: the unit of work in the O(V·E) bound."""

    @property
    def found(self) -> bool:
        return self.cycle is not None


def cycle_from_pred(pred: Sequence[int], start: int, n: int) -> list[int]:
    """Recover the cycle reachable backwards from ``start`` along predecessor links.

    Walking back ``n`` steps is guaranteed to land on the cycle (the chain can hold at
    most ``n`` distinct vertices before it repeats). Raises if the chain reaches the
    virtual source instead, which the theory says cannot happen when this is called.
    """
    x = start
    for _ in range(n):
        x = pred[x]
        if x < 0:
            raise RuntimeError("predecessor walk reached the source: no cycle on this chain")
    # x is on the cycle. Collect it backwards, then reverse into trading order.
    back = [x]
    y = pred[x]
    while y != x:
        back.append(y)
        y = pred[y]
    back.append(x)
    back.reverse()
    return back


def find_pred_cycle(pred: Sequence[int]) -> list[int] | None:
    """Find any cycle in the predecessor graph (each vertex has out-degree <= 1).

    O(n) colouring walk. Every cycle in the predecessor graph has negative weight
    (theory.md, Lemma 4), so this is a sound early-exit check.
    """
    n = len(pred)
    state = [0] * n  # 0 = unseen, otherwise id of the walk that first visited it
    for s in range(n):
        if state[s]:
            continue
        walk_id = s + 1
        x = s
        while x >= 0 and not state[x]:
            state[x] = walk_id
            x = pred[x]
        if x >= 0 and state[x] == walk_id:
            return cycle_from_pred(pred, x, n)
    return None


def bellman_ford(n: int, edges: WeightedEdges, eps: float = DEFAULT_EPS) -> SearchResult:
    """Classic Bellman–Ford with early exit.

    Rounds 1..n-1 relax every edge. If a round changes nothing, distances are final and
    there is no negative cycle. If round n still improves some vertex v, a negative
    cycle exists and v's predecessor chain leads into it.
    """
    dist = [0.0] * n
    pred = [-1] * n
    relaxations = scans = 0
    for rnd in range(1, n + 1):
        last_changed = -1
        for u, v, w in edges:
            nd = dist[u] + w
            if nd < dist[v] - eps:
                dist[v] = nd
                pred[v] = u
                last_changed = v
                relaxations += 1
        scans += len(edges)
        if last_changed < 0:
            return SearchResult(None, rnd, relaxations, scans)
        if rnd == n:
            cyc = cycle_from_pred(pred, last_changed, n)
            return SearchResult(cyc, rnd, relaxations, scans)
    # n == 0
    return SearchResult(None, 0, relaxations, scans)


def spfa(n: int, edges: WeightedEdges, eps: float = DEFAULT_EPS) -> SearchResult:
    """Shortest Path Faster Algorithm: Bellman–Ford that only rescans vertices whose
    distance just changed, using a FIFO queue.

    Correctness tools (theory.md, Section 5):

    * FIFO order splits the work into *passes*; after pass k every distance is at most
      the weight of the best walk with <= k edges, exactly as after Bellman–Ford round k.
      So a relaxation in pass n proves a negative cycle, and the queue emptying proves
      there is none.
    * Every n relaxations we also look for a cycle in the predecessor graph (O(n), so
      O(1) amortised per relaxation). Any such cycle is negative, so this lets SPFA stop
      long before pass n on graphs that have one.
    """
    if n == 0:
        return SearchResult(None, 0, 0, 0)
    adj: list[list[tuple[int, float]]] = [[] for _ in range(n)]
    for u, v, w in edges:
        adj[u].append((v, w))

    dist = [0.0] * n
    pred = [-1] * n
    queue: deque[int] = deque(range(n))
    in_queue = [True] * n
    relaxations = scans = 0
    passes = 1
    remaining_in_pass = n  # vertices still to pop before this pass ends
    next_check = n

    while queue:
        u = queue.popleft()
        in_queue[u] = False
        du = dist[u]
        for v, w in adj[u]:
            scans += 1
            nd = du + w
            if nd < dist[v] - eps:
                dist[v] = nd
                pred[v] = u
                relaxations += 1
                if passes >= n:
                    return SearchResult(cycle_from_pred(pred, v, n), passes, relaxations, scans)
                if relaxations >= next_check:
                    next_check += n
                    cyc = find_pred_cycle(pred)
                    if cyc is not None:
                        return SearchResult(cyc, passes, relaxations, scans)
                if not in_queue[v]:
                    in_queue[v] = True
                    queue.append(v)
        remaining_in_pass -= 1
        if remaining_in_pass == 0 and queue:
            passes += 1
            remaining_in_pass = len(queue)
    return SearchResult(None, passes, relaxations, scans)
