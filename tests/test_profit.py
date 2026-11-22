import math

import pytest

from fxarb import Quote, QuoteGraph, evaluate_cycle, find_cycles
from fxarb.profit import canonical_key, rotate_to_preferred


def triangle() -> QuoteGraph:
    g = QuoteGraph()
    g.add_rate("USD", "BTC", 1 / 100, capacity=500.0)  # can spend up to 500 USD
    g.add_rate("BTC", "ETH", 20.0, capacity=10.0)  # can sell up to 10 BTC
    g.add_rate("ETH", "USD", 5.1, capacity=40.0)  # can sell up to 40 ETH
    return g


def test_product_return_and_weight() -> None:
    g = triangle()
    cyc = [g.index(a) for a in ["USD", "BTC", "ETH", "USD"]]
    rep = evaluate_cycle(g, cyc)
    assert rep.product == pytest.approx(0.01 * 20 * 5.1)  # 1.02
    assert rep.net_return == pytest.approx(0.02)
    assert rep.weight == pytest.approx(-math.log(1.02))
    assert rep.describe() == "USD → BTC → ETH → USD"


def test_max_size_is_set_by_tightest_leg() -> None:
    g = triangle()
    rep = evaluate_cycle(g, [g.index(a) for a in ["USD", "BTC", "ETH", "USD"]])
    # leg bounds in USD: 500 ; 10 BTC / 0.01 = 1000 ; 40 ETH / (0.01*20) = 200
    assert rep.max_size == pytest.approx(200.0)
    assert rep.bottleneck == 2
    assert rep.max_profit == pytest.approx(200.0 * 0.02)


def test_max_size_from_quote_depth() -> None:
    # Buy BTC with USD at ask 100 (only 1.5 BTC offered), sell BTC on venue x at 101.
    g = QuoteGraph.from_quotes(
        [
            Quote("BTC", "USD", 101.0, 101.5, bid_size=4.0, ask_size=9.0, venue="x"),
            Quote("BTC", "USD", 99.5, 100.0, bid_size=9.0, ask_size=1.5, venue="y"),
        ]
    )
    cyc = [g.index("USD"), g.index("BTC"), g.index("USD")]
    rep = evaluate_cycle(g, cyc)
    assert rep.max_size == pytest.approx(150.0)  # 1.5 BTC * 100 USD
    assert rep.max_profit == pytest.approx(1.5)  # 1.5 BTC * (101 - 100)


def test_rejects_open_cycle() -> None:
    g = triangle()
    with pytest.raises(ValueError):
        evaluate_cycle(g, [0, 1, 2])


def test_rotation_and_canonical_key() -> None:
    g = triangle()
    cyc = [g.index(a) for a in ["BTC", "ETH", "USD", "BTC"]]
    rot = rotate_to_preferred(cyc, g)
    assert [g.assets[i] for i in rot] == ["USD", "BTC", "ETH", "USD"]
    assert evaluate_cycle(g, rot).product == pytest.approx(evaluate_cycle(g, cyc).product)
    assert canonical_key(["BTC", "ETH", "USD", "BTC"]) == canonical_key(
        ["USD", "BTC", "ETH", "USD"]
    )
    assert canonical_key(["A", "B", "C", "A"]) != canonical_key(["A", "C", "B", "A"])


def test_find_cycles_returns_distinct_profitable_cycles() -> None:
    g = triangle()
    # a second, independent profitable 2-cycle
    g.add_rate("GBP", "EUR", 1.2)
    g.add_rate("EUR", "GBP", 0.85)  # 1.02
    reps = find_cycles(g, limit=5)
    keys = {canonical_key(r.assets) for r in reps}
    assert len(keys) == len(reps) == 2
    assert all(r.product > 1 for r in reps)
