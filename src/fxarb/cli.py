"""Command line: ``fxarb scan | record | analyze | demo``."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from .bellman_ford import bellman_ford
from .graph import Quote, QuoteGraph
from .profit import CycleReport, find_cycles, find_negative_cycle
from .recording import (
    analyze,
    load_json_snapshot,
    read_recording,
    reconcile_symbols,
    record,
    save_json_snapshot,
    usd_values,
    with_fees,
)
from .sources import DEFAULT_FEES, FETCHERS, fetch_quotes

CRYPTO_VENUES = ["kraken", "binanceus"]


def _venues(arg: Sequence[str]) -> list[str]:
    out: list[str] = []
    for v in arg:
        out.extend(CRYPTO_VENUES if v == "all" else [v])
    for v in out:
        if v not in FETCHERS:
            raise SystemExit(f"unknown venue {v!r}; choose from {sorted(FETCHERS)} or 'all'")
    return out


def _fees(venues: Sequence[str], fee: float | None) -> dict[str, float]:
    return {v: DEFAULT_FEES.get(v, 0.0) if fee is None else fee for v in venues}


def _fmt_money(x: float) -> str:
    return "unlimited" if not math.isfinite(x) else f"${x:,.2f}"


def _print_cycles(reps: Sequence[CycleReport], usd: dict[str, float]) -> None:
    for k, r in enumerate(reps, 1):
        v = usd.get(r.assets[0], math.nan)
        size = r.max_size * v
        print(f"\n#{k}  {r.describe()}")
        print(
            f"    net return {r.net_return:+.4%}   "
            + (
                "depth unknown (sample rates)"
                if not math.isfinite(r.max_size)
                else f"max size {r.max_size:.6g} {r.assets[0]} (~{_fmt_money(size)})"
                f"   max profit ~{_fmt_money(size * r.net_return)}"
            )
        )
        for i, e in enumerate(r.legs):
            mark = "  <- bottleneck" if i == r.bottleneck and math.isfinite(r.max_size) else ""
            print(
                f"    {r.assets[i]:>6} -> {r.assets[i + 1]:<6} x{e.rate:<14.8g}"
                f" {e.side:4} {e.pair} @ {e.venue}{mark}"
            )


# --------------------------------------------------------------------------- scan


def cmd_scan(a: argparse.Namespace) -> int:
    if a.from_json:
        snap = load_json_snapshot(Path(a.from_json))
        raw, ts = snap.quotes, snap.ts
        venues = sorted({q.venue for q in raw})
        fees = _fees(venues, a.fee)
        quotes = with_fees(raw, fees)
        print(f"Loaded {len(raw)} quotes from {a.from_json} (snapshot ts {ts:.0f})")
    else:
        venues = _venues(a.venue)
        fees = _fees(venues, a.fee)
        quotes = []
        ts = time.time()
        for v in venues:
            try:
                got = fetch_quotes(v, fees[v])
            except OSError as exc:
                print(f"! {v}: unreachable ({exc}). No data invented; skipping.", file=sys.stderr)
                continue
            print(f"Fetched {len(got)} quotes from {v} (fee {fees[v]:.4%})")
            quotes.extend(got)
        if not quotes:
            print("No data fetched.", file=sys.stderr)
            return 2
        if a.save_json:
            save_json_snapshot(Path(a.save_json), quotes, ts, note=a.note or "")
            print(f"Saved snapshot to {a.save_json}")
    quotes, split = reconcile_symbols(quotes, a.symbol_tol)
    if split:
        print(
            f"Kept {len(split)} symbol(s) apart by venue (prices disagree > {a.symbol_tol:.0%}): "
            + ", ".join(split[:12])
            + (" ..." if len(split) > 12 else "")
        )
    g = QuoteGraph.from_quotes(quotes)
    t0 = time.perf_counter()
    res = find_negative_cycle(g, a.method)
    dt = time.perf_counter() - t0
    print(
        f"Graph: {g.n} assets, {len(g)} directed edges. {a.method.upper()}: "
        f"{res.rounds} rounds/passes, {res.edge_scans:,} edge scans, {dt * 1e3:.1f} ms."
    )
    reps = find_cycles(g, limit=a.limit, method=a.method)
    if not reps:
        print(f"No profitable cycle after fees ({', '.join(f'{v} {f:.2%}' for v, f in fees.items())}).")
        return 0
    print(f"Found {len(reps)} profitable cycle(s) after fees:")
    _print_cycles(reps, usd_values(quotes))
    return 0


# --------------------------------------------------------------------------- record / analyze


def cmd_record(a: argparse.Namespace) -> int:
    venues = _venues(a.venue)

    def fetch() -> list[Quote]:
        qs: list[Quote] = []
        for v in venues:
            qs.extend(fetch_quotes(v, 0.0))
        return qs

    count = a.count if a.count else max(1, int(a.duration // a.interval))
    out = Path(a.out)
    print(f"Recording {count} snapshots of {venues} every {a.interval}s to {out}")
    n = record(fetch, out, a.interval, count)
    print(f"Done: {n} snapshots.")
    return 0 if n else 2


def cmd_analyze(a: argparse.Namespace) -> int:
    snaps = read_recording(Path(a.path))
    venues = sorted({q.venue for s in snaps for q in s.quotes})
    subsets = [[v] for v in venues] + ([venues] if len(venues) > 1 else [])
    scenarios: dict[str, dict[str, float]] = {}
    for sub in subsets:
        tag = "+".join(sub)
        scenarios[f"{tag} | no fees"] = dict.fromkeys(sub, 0.0)
        scenarios[f"{tag} | taker fees"] = _fees(sub, None)
        if a.fee is not None:
            scenarios[f"{tag} | fee {a.fee:g}"] = _fees(sub, a.fee)
    print(f"Analyzing {len(snaps)} snapshots from {a.path} ...")
    res = analyze(snaps, scenarios, limit=a.limit, method=a.method, progress=print, symbol_tol=a.symbol_tol)
    res["source_file"] = str(a.path)
    print_analysis(res)
    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json_out).write_text(json.dumps(res, indent=2, default=str) + "\n")
        print(f"\nWrote {a.json_out}")
    return 0


def print_analysis(res: dict) -> None:  # type: ignore[type-arg]
    print(
        f"\n{res['snapshots']} snapshots, {res['start']} -> {res['end']} "
        f"(median interval {res['median_interval_s']}s), venues {res['venues']}, "
        f"~{res['assets_median']} assets / {res['pairs_median']} pairs per snapshot"
    )
    gaps = res.get("recording_gaps") or []
    if gaps:
        print(
            "recording gaps (not counted as continuous): "
            + ", ".join(f"{g['from'][11:19]}-{g['to'][11:19]} ({g['seconds']}s)" for g in gaps)
            + f"; continuous coverage {res['covered_s'] / 60:.1f} min"
        )
    for name, s in res["scenarios"].items():
        fees = ", ".join(f"{v} {f:.2%}" for v, f in s["fees"].items())
        print(f"\n== {name} ({fees})")
        print(
            f"  snapshots with >=1 cycle: {s['snapshots_with_cycle']}/{res['snapshots']}"
            f" ({s['fraction_with_cycle']:.1%});  distinct cycles: {s['distinct_cycles']};"
            f"  observations: {s['cycle_observations']}"
        )
        if not s["cycle_observations"]:
            continue
        nr, sz, pr = s["net_return"], s["max_size_usd"], s["max_profit_usd"]
        print(f"  net return  median {nr['median']:+.4%}  p90 {nr['p90']:+.4%}  max {nr['max']:+.4%}")
        print(f"  max size    median ${sz['median']:,.2f}  p90 ${sz['p90']:,.2f}  max ${sz['max']:,.2f}")
        print(f"  max profit  median ${pr['median']:,.4f}  p90 ${pr['p90']:,.4f}  max ${pr['max']:,.4f}")
        es = s["episode_span_s"]
        print(
            f"  persistence {s['episodes']} episodes; median {s['episode_snapshots']['median']}"
            f" snapshot(s) (span {es['median']:.0f}s), longest {s['episode_snapshots']['max']}"
            f" snapshots ({es['max']:.0f}s)"
        )
        print(f"  cycle lengths {s['cycle_length_counts']}")
        if s.get("symbols_split_median"):
            print(f"  symbols kept apart by venue (median per snapshot): {s['symbols_split_median']}")
        for b in s["top_by_profit"][:5]:
            print(
                f"    {b['net_return']:+.3%}  ~${b['max_profit_usd']:,.4f} on ${b['max_size_usd']:,.2f}"
                f"  {b['cycle']}"
            )


# --------------------------------------------------------------------------- demo


def cmd_demo(a: argparse.Namespace) -> int:
    """The 5-currency teaching example from the web demo, in the terminal."""
    quote = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "JPY": 150.0, "GHS": 12.0}
    s, bump = a.spread / 100, a.bump / 100
    rates = {x: {y: quote[y] / quote[x] * (1 - s) for y in quote if y != x} for x in quote}
    rates["EUR"]["JPY"] *= 1 + bump
    rates["JPY"]["EUR"] /= 1 + bump
    g = QuoteGraph.from_rate_matrix(rates)
    print("Sample rates (not live). Spread per trade", f"{a.spread}%, EUR->JPY mispriced by {a.bump}%")
    edges = g.weighted_edges()
    n = g.n
    dist, pred = [0.0] * n, [-1] * n
    print("\nround  " + "  ".join(f"{c:>8}" for c in g.assets))
    print("start  " + "  ".join(f"{d:8.4f}" for d in dist))
    for rnd in range(1, n + 1):
        changed = []
        for u, v, w in edges:
            if dist[u] + w < dist[v] - 1e-12:
                dist[v], pred[v] = dist[u] + w, u
                changed.append(g.assets[v])
        label = f"chk {rnd}" if rnd == n else f"{rnd:>5}"
        print(
            f"{label}  " + "  ".join(f"{d:8.4f}" for d in dist),
            f"  improved: {sorted(set(changed)) or '-'}",
        )
        if not changed:
            print(f"\nRound {rnd} changed nothing: no negative cycle, no arbitrage.")
            return 0
    res = bellman_ford(n, edges)
    assert res.cycle is not None
    reps = find_cycles(g, limit=1)
    print(f"\nRound {n} still improved a distance: negative cycle.")
    _print_cycles(reps, {"USD": 1.0})
    r = reps[0]
    print(f"\n    product of rates {r.product:.6f} > 1  <=>  total weight {r.weight:.6f} < 0")
    return 0


# --------------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fxarb", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("scan", help="fetch live quotes (or a saved snapshot) and look for cycles")
    sc.add_argument("--venue", nargs="+", default=["kraken"], help="kraken, binanceus, frankfurter, all")
    sc.add_argument("--fee", type=float, help="override taker fee for every venue (0.001 = 0.1%%)")
    sc.add_argument("--method", choices=["bf", "spfa"], default="spfa")
    sc.add_argument(
        "--symbol-tol",
        type=float,
        default=0.10,
        help="split a symbol by venue if its USD prices differ by more than this",
    )
    sc.add_argument("--limit", type=int, default=10, help="max distinct cycles to list")
    sc.add_argument("--save-json", help="also save the raw snapshot (for the web demo)")
    sc.add_argument("--from-json", help="scan a saved snapshot instead of fetching")
    sc.add_argument("--note", help="note stored in the saved snapshot")
    sc.set_defaults(func=cmd_scan)

    rc = sub.add_parser("record", help="snapshot order books on an interval")
    rc.add_argument("--venue", nargs="+", default=["kraken"])
    rc.add_argument("--interval", type=float, default=10.0, help="seconds between snapshots")
    g = rc.add_mutually_exclusive_group(required=True)
    g.add_argument("--count", type=int, help="number of snapshots")
    g.add_argument("--duration", type=float, help="seconds to record")
    rc.add_argument("--out", required=True, help=".csv, .csv.gz or .parquet")
    rc.set_defaults(func=cmd_record)

    an = sub.add_parser("analyze", help="how often, how big and how long cycles appear")
    an.add_argument("path")
    an.add_argument("--fee", type=float, help="extra scenario with this fee on every venue")
    an.add_argument("--limit", type=int, default=20, help="max distinct cycles per snapshot")
    an.add_argument("--method", choices=["bf", "spfa"], default="spfa")
    an.add_argument(
        "--symbol-tol",
        type=float,
        default=0.10,
        help="split a symbol by venue if its USD prices differ by more than this",
    )
    an.add_argument("--json-out", help="write full results as JSON")
    an.set_defaults(func=cmd_analyze)

    dm = sub.add_parser("demo", help="step through Bellman-Ford on 5 sample currencies")
    dm.add_argument("--spread", type=float, default=0.05, help="%% lost per trade")
    dm.add_argument("--bump", type=float, default=0.8, help="%% mispricing on EUR->JPY")
    dm.set_defaults(func=cmd_demo)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
