"""Benchmark Bellman–Ford vs SPFA on a real crypto snapshot and on synthetic markets.

Usage:  python scripts/benchmark.py [--snapshot web/data/snapshot.json] [--out results/]
Every number written is measured on the machine running this script.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from fxarb import Quote, QuoteGraph, bellman_ford, spfa
from fxarb.bellman_ford import SearchResult, WeightedEdges
from fxarb.recording import load_json_snapshot, reconcile_symbols, with_fees
from fxarb.sources import DEFAULT_FEES

Algo = Callable[[int, WeightedEdges], SearchResult]


def machine() -> dict[str, str]:
    cpu = platform.processor() or platform.machine()
    mem = ""
    if sys.platform == "darwin":
        try:
            cpu = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
            mem_b = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True))
            mem = f"{mem_b / 2**30:.0f} GiB"
        except (OSError, subprocess.CalledProcessError):
            pass
    return {
        "cpu": cpu,
        "logical_cores": str(os.cpu_count()),
        "memory": mem,
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
    }


def time_it(algo: Algo, n: int, edges: WeightedEdges, repeat: int) -> tuple[float, SearchResult]:
    times = []
    res = algo(n, edges)
    for _ in range(repeat):
        t0 = time.perf_counter()
        res = algo(n, edges)
        times.append(time.perf_counter() - t0)
    return statistics.median(times), res


def synthetic(n: int, degree: int, rng: random.Random, inject: bool) -> QuoteGraph:
    """Consistent market (one hidden value per asset), ~degree pairs per asset, 0.1% spread
    and 0.1% fee. With ``inject``, one extra venue bids 1% over fair on one pair."""
    value = [math.exp(rng.uniform(-8, 8)) for _ in range(n)]
    pairs: set[tuple[int, int]] = set()
    for i in range(1, n):  # random spanning tree keeps it connected
        pairs.add((rng.randrange(i), i))
    while len(pairs) < min(n * degree // 2, n * (n - 1) // 2):
        a, b = rng.sample(range(n), 2)
        pairs.add((min(a, b), max(a, b)))
    quotes = []
    for a, b in pairs:
        mid = value[a] / value[b]
        quotes.append(Quote(f"A{a}", f"A{b}", mid * 0.999, mid * 1.001, fee=0.001, venue="s"))
    if inject:
        a, b = next(iter(pairs))
        mid = value[a] / value[b]
        quotes.append(Quote(f"A{a}", f"A{b}", mid * 1.01, mid * 1.012, fee=0.001, venue="rogue"))
    rng.shuffle(quotes)
    return QuoteGraph.from_quotes(quotes)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default="web/data/snapshot.json")
    ap.add_argument("--out", default="results")
    ap.add_argument("--repeat", type=int, default=7)
    a = ap.parse_args()
    rng = random.Random(280)
    rows: list[dict[str, object]] = []

    def bench(label: str, g: QuoteGraph, repeat: int) -> None:
        edges = g.weighted_edges()
        r: dict[str, object] = {"case": label, "V": g.n, "E": len(edges)}

        def bf_check(n: int, e: WeightedEdges) -> SearchResult:
            return bellman_ford(n, e, pred_check=True)

        for name, algo in (("bf", bellman_ford), ("bfpc", bf_check), ("spfa", spfa)):
            t, res = time_it(algo, g.n, edges, repeat)
            r[f"{name}_ms"] = t * 1e3
            r[f"{name}_scans"] = res.edge_scans
            r[f"{name}_rounds"] = res.rounds
            r[f"{name}_cycle"] = res.found
        assert r["bf_cycle"] == r["spfa_cycle"] == r["bfpc_cycle"], f"algorithms disagree on {label}"
        rows.append(r)
        print(
            f"{label:<44} V={g.n:>5} E={len(edges):>6}  BF {r['bf_ms']:>9.2f} ms"
            f" ({r['bf_rounds']} rounds)  BF+check {r['bfpc_ms']:>8.2f} ms ({r['bfpc_rounds']})"
            f"  SPFA {r['spfa_ms']:>8.2f} ms  cycle={r['bf_cycle']}"
        )

    snap = load_json_snapshot(Path(a.snapshot))
    venues = sorted({q.venue for q in snap.quotes})
    for sub in [[v] for v in venues] + [venues]:
        qs, _ = reconcile_symbols([q for q in snap.quotes if q.venue in sub])
        tag = "+".join(sub)
        for fee_name, fees in (
            ("taker fees", {v: DEFAULT_FEES[v] for v in sub}),
            ("no fees", dict.fromkeys(sub, 0.0)),
        ):
            bench(f"real {tag}, {fee_name}", QuoteGraph.from_quotes(with_fees(qs, fees)), a.repeat)

    for n in (100, 300, 1000, 3000):
        for inject in (False, True):
            g = synthetic(n, 8, rng, inject)
            bench(f"synthetic n={n}, deg 8, {'1% mispricing' if inject else 'consistent'}", g, 3)

    # Adversarial for both: a long chain whose edges are listed back to front, so each
    # Bellman–Ford round only pushes the improvement one step further.
    for n in (200, 800):
        chain = QuoteGraph()
        for i in range(n - 1, 0, -1):
            chain.add_rate(f"C{i - 1}", f"C{i}", 1.001)  # each step gains 0.1%
        bench(f"adversarial chain n={n} (reverse order)", chain, 3)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **machine()}
    meta["snapshot"] = a.snapshot
    meta["snapshot_time"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(snap.ts))
    (out / "benchmarks.json").write_text(json.dumps({"machine": meta, "rows": rows}, indent=2) + "\n")
    lines = [
        "# Benchmarks: Bellman–Ford vs SPFA (pure Python)",
        "",
        f"Measured {meta['measured_at']} on {meta['cpu']}, {meta['logical_cores']} logical cores, "
        f"{meta['memory']}, {meta['os']}, {meta['implementation']} {meta['python']}. "
        "Median wall time of repeated runs, single thread. Real graphs come from the "
        f"snapshot `{a.snapshot}` taken {meta['snapshot_time']}.",
        "",
        "BF = classic Bellman–Ford with early exit (stops at round n when a cycle exists). "
        "BF+check = the same plus an O(V) predecessor-graph cycle check after each round. "
        "SPFA = queue-based, with the same check every V relaxations.",
        "",
        "| case | V | E | BF ms | BF rounds | BF+check ms | BF+check rounds | SPFA ms "
        "| BF edge scans | SPFA edge scans | cycle |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['case']} | {r['V']} | {r['E']} | {r['bf_ms']:.2f} | {r['bf_rounds']} | "
            f"{r['bfpc_ms']:.2f} | {r['bfpc_rounds']} | {r['spfa_ms']:.2f} | "
            f"{r['bf_scans']:,} | {r['spfa_scans']:,} | "
            f"{'yes' if r['bf_cycle'] else 'no'} |"
        )
    (out / "benchmarks.md").write_text("\n".join(lines) + "\n")
    print(f"\nWrote {out / 'benchmarks.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
