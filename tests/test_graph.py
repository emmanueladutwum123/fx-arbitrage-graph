import math

import pytest

from fxarb import Quote, QuoteGraph


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bid": 0.0, "ask": 1.0},
        {"bid": -1.0, "ask": 1.0},
        {"bid": 1.0, "ask": 0.0},
        {"bid": 1.0, "ask": -2.0},
        {"bid": math.nan, "ask": 1.0},
        {"bid": 1.0, "ask": math.inf},
        {"bid": 1.1, "ask": 1.0},  # crossed book
        {"bid": 1.0, "ask": 1.0, "fee": 1.0},
        {"bid": 1.0, "ask": 1.0, "fee": -0.01},
        {"bid": 1.0, "ask": 1.0, "bid_size": 0.0},
        {"bid": 1.0, "ask": 1.0, "ask_size": -5.0},
    ],
)
def test_bad_quotes_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        Quote("BTC", "USD", **kwargs)


def test_same_asset_rejected() -> None:
    with pytest.raises(ValueError):
        Quote("USD", "USD", 1.0, 1.0)


@pytest.mark.parametrize("rate", [0.0, -1.0, math.nan, math.inf])
def test_bad_rates_rejected(rate: float) -> None:
    g = QuoteGraph()
    with pytest.raises(ValueError):
        g.add_rate("A", "B", rate)


def test_self_loop_rejected() -> None:
    with pytest.raises(ValueError):
        QuoteGraph().add_rate("A", "A", 1.0)


def test_quote_edges_use_bid_to_sell_and_ask_to_buy() -> None:
    q = Quote("BTC", "USD", bid=100.0, ask=101.0, bid_size=2.0, ask_size=3.0, fee=0.001)
    g = QuoteGraph.from_quotes([q])
    btc, usd = g.index("BTC"), g.index("USD")
    sell = g.edge(btc, usd)
    buy = g.edge(usd, btc)
    assert sell.rate == pytest.approx(100.0 * 0.999)
    assert sell.capacity == 2.0  # BTC units
    assert sell.side == "sell"
    assert buy.rate == pytest.approx(0.999 / 101.0)
    assert buy.capacity == pytest.approx(3.0 * 101.0)  # USD units
    assert buy.side == "buy"
    # a round trip on one pair always loses the spread plus two fees
    assert sell.rate * buy.rate < 1


def test_best_parallel_edge_kept() -> None:
    g = QuoteGraph()
    g.add_rate("A", "B", 1.0, venue="x")
    g.add_rate("A", "B", 1.2, venue="y")
    g.add_rate("A", "B", 1.1, venue="z")
    e = g.edge(g.index("A"), g.index("B"))
    assert e.rate == 1.2 and e.venue == "y"
    assert len(g) == 1


def test_missing_quotes_mean_missing_edges() -> None:
    g = QuoteGraph.from_rate_matrix({"A": {"B": 2.0}, "B": {}, "C": {"A": 0.5}})
    assert g.n == 3
    assert len(g) == 2
    assert (g.index("B"), g.index("A")) not in {(e.u, e.v) for e in g.edges}


def test_without_edge_does_not_mutate_original() -> None:
    g = QuoteGraph.from_rate_matrix({"A": {"B": 2.0}, "B": {"A": 0.6}})
    h = g.without_edge(0, 1)
    assert len(g) == 2 and len(h) == 1
