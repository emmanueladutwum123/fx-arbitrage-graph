"""The optional C++ extension must return exactly what the Python implementation returns."""

from __future__ import annotations

import pytest
from hypothesis import given, settings

from fxarb import bellman_ford, spfa
from strategies import random_rate_graph

fxarb_cpp = pytest.importorskip("fxarb_cpp")


@settings(max_examples=400, deadline=None)
@given(random_rate_graph(max_n=8))
def test_cpp_matches_python_exactly(g: tuple[int, list[tuple[int, int, float]]]) -> None:
    n, edges = g
    cg = fxarb_cpp.Graph(n, edges)
    for pred_check in (False, True):
        py = bellman_ford(n, edges, pred_check=pred_check)
        assert cg.bellman_ford(pred_check=pred_check) == (
            py.cycle,
            py.rounds,
            py.relaxations,
            py.edge_scans,
        )
    py = spfa(n, edges)
    assert cg.spfa() == (py.cycle, py.rounds, py.relaxations, py.edge_scans)


def test_cpp_rejects_bad_edges() -> None:
    with pytest.raises(IndexError):
        fxarb_cpp.Graph(2, [(0, 5, 1.0)])
