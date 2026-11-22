"""Parsers, recording round trip, symbol reconciliation and CLI smoke tests (offline)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from fxarb import Quote, QuoteGraph, find_negative_cycle
from fxarb.cli import main
from fxarb.recording import (
    analyze,
    load_json_snapshot,
    read_recording,
    reconcile_symbols,
    record,
    save_json_snapshot,
    usd_values,
)
from fxarb.sources import binanceus, frankfurter, kraken

KRAKEN_PAIRS = {
    "error": [],
    "result": {
        "XXBTZUSD": {"altname": "XBTUSD", "wsname": "XBT/USD", "status": "online"},
        "XETHZUSD": {"altname": "ETHUSD", "wsname": "ETH/USD", "status": "online"},
        "XETHXXBT": {"altname": "ETHXBT", "wsname": "ETH/XBT", "status": "online"},
        "OLDPAIR": {"altname": "OLD", "wsname": "OLD/USD", "status": "delisted"},
    },
}
KRAKEN_TICKER = {
    "error": [],
    "result": {
        "XXBTZUSD": {"a": ["60001.0", "1", "1.500"], "b": ["60000.0", "2", "2.250"]},
        "XETHZUSD": {"a": ["3000.5", "3", "3.000"], "b": ["3000.0", "4", "4.000"]},
        "XETHXXBT": {"a": ["0.05002", "1", "10.0"], "b": ["0.0", "0", "0.0"]},  # empty bid
        "OLDPAIR": {"a": ["1.0", "1", "1.0"], "b": ["0.9", "1", "1.0"]},
    },
}


def test_kraken_parser() -> None:
    qs = kraken.parse(KRAKEN_PAIRS, KRAKEN_TICKER, fee=0.008)
    pairs = {q.pair: q for q in qs}
    assert set(pairs) == {"BTC/USD", "ETH/USD"}  # renamed XBT; skipped empty + delisted
    btc = pairs["BTC/USD"]
    assert (btc.bid, btc.ask, btc.bid_size, btc.ask_size, btc.fee) == (60000, 60001, 2.25, 1.5, 0.008)


def test_kraken_parser_raises_on_api_error() -> None:
    with pytest.raises(RuntimeError):
        kraken.parse({"error": ["EGeneral:Too many requests"]}, KRAKEN_TICKER, 0.0)


def test_binanceus_parser() -> None:
    info = {
        "symbols": [
            {"symbol": "BTCUSD", "baseAsset": "BTC", "quoteAsset": "USD", "status": "TRADING"},
            {"symbol": "XYZUSD", "baseAsset": "XYZ", "quoteAsset": "USD", "status": "BREAK"},
        ]
    }
    book = [
        {"symbol": "BTCUSD", "bidPrice": "100", "bidQty": "1", "askPrice": "101", "askQty": "2"},
        {"symbol": "XYZUSD", "bidPrice": "1", "bidQty": "1", "askPrice": "1", "askQty": "1"},
    ]
    qs = binanceus.parse(info, book, fee=0.0002)
    assert [q.pair for q in qs] == ["BTC/USD"]


def test_frankfurter_reference_rates_have_no_arbitrage() -> None:
    payload = {"base": "EUR", "rates": {"USD": 1.099, "JPY": 174.35, "GBP": 0.8412, "GHS": 12.71}}
    g = QuoteGraph.from_quotes(frankfurter.parse(payload, fee=0.0))
    assert g.n == 5 and len(g) == 20
    for m in ("bf", "spfa"):
        assert find_negative_cycle(g, m).cycle is None


def test_usd_values_by_bfs() -> None:
    qs = [
        Quote("BTC", "USD", 99.0, 101.0),
        Quote("ETH", "BTC", 0.049, 0.051),
        Quote("FOO", "BAR", 1.0, 1.0),  # not connected to USD
    ]
    v = usd_values(qs)
    assert v["BTC"] == pytest.approx(100.0)
    assert v["ETH"] == pytest.approx(5.0)
    assert "FOO" not in v


def test_reconcile_symbols_splits_colliding_tickers() -> None:
    qs = [
        Quote("ONE", "USD", 0.15, 0.16, venue="a"),
        Quote("ONE", "USD", 0.0012, 0.0013, venue="b"),  # same code, different token
        Quote("BTC", "USD", 100.0, 100.1, venue="a"),
        Quote("BTC", "USD", 100.0, 100.3, venue="b"),
    ]
    out, split = reconcile_symbols(qs, tol=0.10)
    assert split == ["ONE"]
    assert {q.base for q in out} == {"ONE@a", "ONE@b", "BTC"}
    g = QuoteGraph.from_quotes(out)
    assert find_negative_cycle(g).cycle is None  # the fake 100x "arbitrage" is gone


def _fake_fetch(prices: list[float]) -> list:  # type: ignore[type-arg]
    it = iter(prices)

    def fetch() -> list[Quote]:
        p = next(it)
        return [
            Quote("BTC", "USD", 100.0, 100.5, 1.0, 1.0, venue="x"),
            Quote("BTC", "USD", p, p + 0.5, 2.0, 2.0, venue="y"),
        ]

    return [fetch]


@pytest.mark.parametrize("suffix", [".csv", ".csv.gz", ".parquet"])
def test_record_and_analyze_round_trip(tmp_path: Path, suffix: str) -> None:
    if suffix == ".parquet":
        pytest.importorskip("pyarrow")
    out = tmp_path / f"rec{suffix}"
    # snapshot 2 and 3: venue y bids 101 while x asks 100.5 -> 2-cycle worth +0.5%
    (fetch,) = _fake_fetch([100.2, 101.0, 101.0, 100.2])
    n = record(fetch, out, interval=0.0, count=4, log=lambda _: None)
    assert n == 4
    snaps = read_recording(out)
    assert len(snaps) == 4 and all(len(s.quotes) == 2 for s in snaps)
    res = analyze(snaps, {"free": {"x": 0.0, "y": 0.0}, "costly": {"x": 0.01, "y": 0.01}})
    free, costly = res["scenarios"]["free"], res["scenarios"]["costly"]
    assert free["snapshots_with_cycle"] == 2
    assert free["episodes"] == 1 and free["episode_snapshots"]["max"] == 2
    assert free["net_return"]["max"] == pytest.approx(101 / 100.5 - 1)
    assert free["max_size_usd"]["max"] == pytest.approx(100.5)  # 1 BTC offered at 100.5
    assert costly["snapshots_with_cycle"] == 0


def test_json_snapshot_round_trip(tmp_path: Path) -> None:
    qs = [Quote("BTC", "USD", 100.0, 100.5, 1.5, math.inf, venue="x")]
    p = tmp_path / "s.json"
    save_json_snapshot(p, qs, ts=1_800_000_000.0)
    snap = load_json_snapshot(p)
    assert snap.ts == 1_800_000_000.0 and snap.quotes[0].pair == "BTC/USD"


def test_cli_demo(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "negative cycle" in out and "EUR" in out and "JPY" in out
    assert main(["demo", "--bump", "0"]) == 0
    assert "no arbitrage" in capsys.readouterr().out


def test_cli_scan_from_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "s.json"
    save_json_snapshot(
        p,
        [
            Quote("BTC", "USD", 101.0, 101.5, 1.0, 1.0, venue="x"),
            Quote("BTC", "USD", 99.5, 100.0, 1.0, 1.0, venue="y"),
        ],
        ts=0.0,
    )
    assert main(["scan", "--from-json", str(p), "--fee", "0"]) == 0
    assert "Found 1 profitable cycle" in capsys.readouterr().out
    assert main(["scan", "--from-json", str(p), "--fee", "0.01"]) == 0
    assert "No profitable cycle" in capsys.readouterr().out


@pytest.mark.network
def test_live_kraken_reachable() -> None:
    qs = kraken.fetch(0.008)
    assert len(qs) > 100
