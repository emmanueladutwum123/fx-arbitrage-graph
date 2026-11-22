"""The browser engine (web/fxarb.js) must agree with the Python package on real data."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from fxarb import QuoteGraph, evaluate_cycle, find_negative_cycle
from fxarb.recording import load_json_snapshot, reconcile_symbols, with_fees

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "web" / "data" / "snapshot.json"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None or not SNAP.exists(), reason="needs node + snapshot")

SCENARIOS = [
    {"kraken": 0.008},
    {"kraken": 0.0},
    {"binanceus": 0.0},
    {"kraken": 0.0, "binanceus": 0.0},
    {"kraken": 0.008, "binanceus": 0.0002},
]


@pytest.mark.parametrize("fees", SCENARIOS, ids=lambda f: "+".join(f"{k}:{v}" for k, v in f.items()))
def test_js_engine_matches_python(fees: dict[str, float]) -> None:
    assert NODE is not None
    out = subprocess.run(
        [NODE, str(ROOT / "tests/web/engine_cli.js"), str(SNAP), json.dumps(fees)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    js = json.loads(out)
    snap = load_json_snapshot(SNAP)
    qs, split = reconcile_symbols([q for q in snap.quotes if q.venue in fees])
    g = QuoteGraph.from_quotes(with_fees(qs, fees))
    assert js["split"] == split
    assert (js["n"], js["m"]) == (g.n, len(g))
    py_found = find_negative_cycle(g).cycle is not None
    assert bool(js["cycles"]) == py_found
    for c in js["cycles"]:  # every cycle the page shows re-prices identically in Python
        rep = evaluate_cycle(g, [g.index(a) for a in c["assets"]])
        assert math.isclose(rep.product, c["product"], rel_tol=1e-12)
        assert rep.product > 1
        assert math.isclose(rep.max_size, c["maxSize"], rel_tol=1e-9) or rep.max_size == c["maxSize"]
