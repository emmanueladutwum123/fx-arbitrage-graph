"""Bellman–Ford and SPFA: property tests against the math and against brute force."""

from __future__ import annotations

import itertools
import math

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from fxarb import Quote, QuoteGraph, bellman_ford, evaluate_cycle, find_negative_cycle, spfa
from fxarb.bellman_ford import find_pred_cycle
from fxarb.brute import min_cycle_weight
from strategies import consistent_market, random_rate_graph

METHODS = ["bf", "spfa"]


def assert_valid_cycle(n: int, edges: list[tuple[int, int, float]], cyc: list[int]) -> float:
    """Closed, simple, made of real edges, negative. Returns its weight."""
    assert cyc[0] == cyc[-1]
    body = cyc[:-1]
    assert len(body) >= 2
    assert len(set(body)) == len(body), f"cycle repeats a vertex: {cyc}"
    wmap = {(u, v): w for u, v, w in edges}
    total = 0.0
    for a, b in itertools.pairwise(cyc):
        assert (a, b) in wmap, f"edge {a}->{b} not in graph"
        total += wmap[(a, b)]
    assert total < 0
    return total


# ---------------------------------------------------------------- property tests


@settings(max_examples=300, deadline=None)
@given(consistent_market())
def test_consistent_market_with_spread_has_no_cycle(market: tuple[list[Quote], dict]) -> None:
    quotes, _ = market
    g = QuoteGraph.from_quotes(quotes)
    for m in METHODS:
        assert find_negative_cycle(g, m).cycle is None


@settings(max_examples=300, deadline=None)
@given(consistent_market(min_assets=2), st.data())
def test_injected_mispricing_beyond_costs_is_found(
    market: tuple[list[Quote], dict], data: st.DataObject
) -> None:
    quotes, _ = market
    assume(quotes)
    q = data.draw(st.sampled_from(quotes))
    # A second venue bids for q.base above the fair ask by more than the round-trip cost:
    # sell base there at bid', buy it back on the fair venue at q.ask.
    # Round trip product = bid'(1-f2) * (1-f)/ask > 1  <=>  bid' > ask / ((1-f)(1-f2)).
    f2 = data.draw(st.floats(0.0, 0.005))
    edge = data.draw(st.floats(1e-4, 0.05))
    bid2 = q.ask / ((1 - q.fee) * (1 - f2)) * (1 + edge)
    rogue = Quote(q.base, q.quote, bid=bid2, ask=bid2 * 1.001, fee=f2, venue="rogue")
    g = QuoteGraph.from_quotes([*quotes, rogue])
    for m in METHODS:
        res = find_negative_cycle(g, m)
        assert res.cycle is not None
        rep = evaluate_cycle(g, res.cycle)
        assert rep.product > 1
        assert rep.weight < 0
        assert math.isclose(rep.weight, -math.log(rep.product), rel_tol=1e-9, abs_tol=1e-12)


@settings(max_examples=500, deadline=None)
@given(random_rate_graph())
def test_bf_and_spfa_agree_with_brute_force(g: tuple[int, list[tuple[int, int, float]]]) -> None:
    n, edges = g
    _, best_w = min_cycle_weight(n, edges)
    # keep away from the eps boundary, where "negative" depends on float rounding
    assume(not (-1e-9 < best_w < 1e-9))
    expected = best_w < 0
    for algo in (bellman_ford, spfa):
        res = algo(n, edges)
        assert res.found == expected, f"{algo.__name__} disagrees with brute force"
        if res.cycle is not None:
            w = assert_valid_cycle(n, edges, res.cycle)
            assert w >= best_w - 1e-12  # cannot beat the true minimum


@settings(max_examples=200, deadline=None)
@given(random_rate_graph(max_n=7))
def test_work_is_within_ve_bound(g: tuple[int, list[tuple[int, int, float]]]) -> None:
    n, edges = g
    for algo in (bellman_ford, spfa):
        res = algo(n, edges)
        assert res.rounds <= max(n, 1)
        assert res.edge_scans <= max(n, 1) * len(edges)


# ---------------------------------------------------------------- edge cases


def test_empty_and_single_vertex() -> None:
    for algo in (bellman_ford, spfa):
        assert algo(0, []).cycle is None
        assert algo(1, []).cycle is None


def test_two_cycle_across_venues() -> None:
    # Venue x bids 101 for BTC while venue y asks 100: buy on y, sell on x.
    g = QuoteGraph.from_quotes(
        [
            Quote("BTC", "USD", bid=101.0, ask=101.5, venue="x"),
            Quote("BTC", "USD", bid=99.5, ask=100.0, venue="y"),
        ]
    )
    for m in METHODS:
        res = find_negative_cycle(g, m)
        assert res.cycle is not None and len(res.cycle) == 3
        rep = evaluate_cycle(g, res.cycle)
        assert rep.product == pytest.approx(1.01)
        assert {leg.venue for leg in rep.legs} == {"x", "y"}


def test_two_cycle_killed_by_fees() -> None:
    g = QuoteGraph.from_quotes(
        [
            Quote("BTC", "USD", bid=100.3, ask=101.0, fee=0.002, venue="x"),
            Quote("BTC", "USD", bid=99.5, ask=100.0, fee=0.002, venue="y"),
        ]
    )
    # 100.3/100 = 1.003 gross, but (1-0.002)^2 ~ 0.996 -> loses after fees
    for m in METHODS:
        assert find_negative_cycle(g, m).cycle is None


def test_disconnected_markets() -> None:
    rates = {
        # component 1: consistent, no arbitrage
        "USD": {"EUR": 0.92 * 0.999},
        "EUR": {"USD": 1 / 0.92 * 0.999},
        # component 2: a profitable triangle
        "A": {"B": 2.0},
        "B": {"C": 3.0},
        "C": {"A": 0.2},  # 2*3*0.2 = 1.2
        # component 3: isolated vertex
        "Z": {},
    }
    g = QuoteGraph.from_rate_matrix(rates)
    for m in METHODS:
        res = find_negative_cycle(g, m)
        assert res.cycle is not None
        assert {g.assets[i] for i in res.cycle} == {"A", "B", "C"}


def test_triangle_through_pair_missing_from_fair_market() -> None:
    # Fair market only quotes A/B and B/C; a rogue venue quotes A/C too high.
    a_b, b_c = 2.0, 5.0  # so fair A/C = 10
    quotes = [
        Quote("A", "B", bid=a_b * 0.999, ask=a_b * 1.001, venue="fair"),
        Quote("B", "C", bid=b_c * 0.999, ask=b_c * 1.001, venue="fair"),
    ]
    g0 = QuoteGraph.from_quotes(quotes)
    assert find_negative_cycle(g0).cycle is None
    rogue = Quote("A", "C", bid=10.2, ask=10.25, venue="rogue")
    g = QuoteGraph.from_quotes([*quotes, rogue])
    for m in METHODS:
        res = find_negative_cycle(g, m)
        assert res.cycle is not None
        rep = evaluate_cycle(g, res.cycle)
        assert rep.length == 3 and rep.product > 1


def test_eps_ignores_float_noise_on_reference_rates() -> None:
    # Cross rates computed from one vector are consistent: every cycle product is 1
    # up to rounding. No cycle should be reported.
    vec = {"EUR": 1.0, "USD": 1.0987, "JPY": 171.33, "GBP": 0.8412, "CHF": 0.9311}
    rates = {a: {b: vec[b] / vec[a] for b in vec if b != a} for a in vec}
    g = QuoteGraph.from_rate_matrix(rates)
    for m in METHODS:
        assert find_negative_cycle(g, m).cycle is None


def test_find_pred_cycle() -> None:
    assert find_pred_cycle([-1, 0, 1]) is None
    cyc = find_pred_cycle([2, 0, 1, -1])  # 0<-2<-1<-0 : edges 2->0, 0->1, 1->2
    assert cyc is not None
    assert cyc[0] == cyc[-1] and sorted(cyc[:-1]) == [0, 1, 2]
    # trading order follows edges pred[v] -> v
    for a, b in itertools.pairwise(cyc):
        assert [2, 0, 1, -1][b] == a


def test_demo_scenario_matches_web_demo() -> None:
    """The same 5-currency market as web/index.html (sample rates, not live)."""
    quote = {"USD": 1, "EUR": 0.92, "GBP": 0.79, "JPY": 150, "GHS": 12}
    s = 0.0005

    def market(bump: float) -> QuoteGraph:
        r = {a: {b: quote[b] / quote[a] * (1 - s) for b in quote if b != a} for a in quote}
        r["EUR"]["JPY"] *= 1 + bump
        r["JPY"]["EUR"] /= 1 + bump
        return QuoteGraph.from_rate_matrix(r)

    for m in METHODS:
        assert find_negative_cycle(market(0.0), m).cycle is None
        res = find_negative_cycle(market(0.008), m)
        assert res.cycle is not None
        names = [market(0.008).assets[i] for i in res.cycle]
        assert "EUR" in names and "JPY" in names
