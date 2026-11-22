"""Record top-of-book snapshots over time, and analyze how often cycles appear."""

from __future__ import annotations

import csv
import gzip
import io
import itertools
import json
import math
import statistics
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, cast

from .graph import Quote, QuoteGraph
from .profit import CycleReport, canonical_key, find_cycles

__all__ = [
    "FIELDS",
    "Snapshot",
    "analyze",
    "load_json_snapshot",
    "read_recording",
    "reconcile_symbols",
    "record",
    "save_json_snapshot",
    "usd_values",
]

FIELDS = ["ts", "venue", "base", "quote", "bid", "bid_size", "ask", "ask_size"]


@dataclass
class Snapshot:
    ts: float
    quotes: list[Quote] = field(default_factory=list)


# --------------------------------------------------------------------------- I/O


def _open_text(path: Path, mode: str) -> IO[str]:
    if path.suffix == ".gz":
        raw = cast(IO[bytes], gzip.open(path, mode + "b"))  # noqa: SIM115 (caller closes)
        return io.TextIOWrapper(raw, encoding="utf-8", newline="")
    return path.open(mode, encoding="utf-8", newline="")


def _rows(ts: float, quotes: Iterable[Quote]) -> Iterator[list[Any]]:
    for q in quotes:
        yield [round(ts, 3), q.venue, q.base, q.quote, q.bid, q.bid_size, q.ask, q.ask_size]


def record(
    fetch: Callable[[], list[Quote]],
    out: Path,
    interval: float,
    count: int,
    log: Callable[[str], None] = print,
) -> int:
    """Take ``count`` snapshots ``interval`` seconds apart. Fees are NOT stored: they are
    applied at analysis time, so one recording can be studied at several fee levels.

    ``.csv`` / ``.csv.gz`` are appended snapshot by snapshot (safe to interrupt);
    ``.parquet`` is written once at the end (requires pyarrow). Returns snapshots taken.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    parquet = out.suffix == ".parquet"
    buffer: list[list[Any]] = []
    fh: IO[str] | None = None
    writer = None
    if not parquet:
        new = not out.exists()
        fh = _open_text(out, "a")
        writer = csv.writer(fh)
        if new:
            writer.writerow(FIELDS)
    taken = 0
    try:
        next_t = time.monotonic()
        last_ts = -math.inf
        while taken < count:
            # Snapshots are grouped by timestamp (stored to the millisecond), so keep them
            # strictly increasing even if two fetches land in the same millisecond.
            ts = max(round(time.time(), 3), round(last_ts + 0.001, 3))
            try:
                quotes = fetch()
            except Exception as exc:  # network hiccup: log it, keep the schedule
                log(f"[{time.strftime('%H:%M:%S')}] fetch failed: {exc!r}")
                quotes = []
            if quotes:
                last_ts = ts
                rows = list(_rows(ts, quotes))
                if writer is not None and fh is not None:
                    writer.writerows(rows)
                    fh.flush()
                else:
                    buffer.extend(rows)
                taken += 1
                log(f"[{time.strftime('%H:%M:%S')}] snapshot {taken}/{count}: {len(quotes)} quotes")
            next_t += interval
            if next_t < time.monotonic():  # fell behind (stall or sleep): skip, don't burst
                next_t = time.monotonic() + interval
            time.sleep(max(0.0, next_t - time.monotonic()))
    except KeyboardInterrupt:
        log("interrupted; keeping what was recorded")
    finally:
        if fh is not None:
            fh.close()
        if parquet and buffer:
            import pyarrow as pa
            import pyarrow.parquet as pq

            cols = list(zip(*buffer, strict=True))
            pq.write_table(pa.table({k: list(v) for k, v in zip(FIELDS, cols, strict=True)}), out)
    return taken


def read_recording(path: Path) -> list[Snapshot]:
    """Load a recording, grouped into snapshots by timestamp (in time order)."""
    rows: Iterable[dict[str, Any]]
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq

        rows = pq.read_table(path).to_pylist()
    else:
        with _open_text(path, "r") as fh:
            rows = list(csv.DictReader(fh))
    snaps: dict[float, Snapshot] = {}
    for r in rows:
        ts = float(r["ts"])
        snap = snaps.setdefault(ts, Snapshot(ts))
        snap.quotes.append(
            Quote(
                str(r["base"]),
                str(r["quote"]),
                float(r["bid"]),
                float(r["ask"]),
                float(r["bid_size"]),
                float(r["ask_size"]),
                venue=str(r["venue"]),
            )
        )
    return [snaps[t] for t in sorted(snaps)]


def save_json_snapshot(path: Path, quotes: Sequence[Quote], ts: float, note: str = "") -> None:
    """Compact JSON for the web demo: no fees inside, the page applies its own."""
    venues = sorted({q.venue for q in quotes})
    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
        "ts": round(ts, 3),
        "venues": venues,
        "note": note,
        "fields": ["venue", "base", "quote", "bid", "ask", "bid_size", "ask_size"],
        "quotes": [[q.venue, q.base, q.quote, q.bid, q.ask, q.bid_size, q.ask_size] for q in quotes],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")


def load_json_snapshot(path: Path) -> Snapshot:
    data = json.loads(path.read_text(encoding="utf-8"))
    quotes = [Quote(b, q, bid, ask, bs, az, venue=v) for v, b, q, bid, ask, bs, az in data["quotes"]]
    return Snapshot(float(data["ts"]), quotes)


def with_fees(quotes: Iterable[Quote], fees: dict[str, float]) -> list[Quote]:
    return [
        Quote(q.base, q.quote, q.bid, q.ask, q.bid_size, q.ask_size, fees.get(q.venue, 0.0), q.venue)
        for q in quotes
    ]


# --------------------------------------------------------------------------- valuation


def usd_values(quotes: Iterable[Quote]) -> dict[str, float]:
    """USD value of each asset from mid prices, by breadth-first search outward from USD.
    Uses only quotes in the snapshot (USDT, USDC, EUR... are valued at their market price)."""
    adj: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for q in quotes:
        mid = (q.bid + q.ask) / 2  # units of quote per base
        adj[q.quote].append((q.base, mid))  # value(base) = value(quote) * mid
        adj[q.base].append((q.quote, 1 / mid))
    vals = {"USD": 1.0}
    todo = deque(["USD"])
    while todo:
        a = todo.popleft()
        for b, m in adj[a]:
            if b not in vals:
                vals[b] = vals[a] * m
                todo.append(b)
    return vals


def reconcile_symbols(quotes: Sequence[Quote], tol: float = 0.10) -> tuple[list[Quote], list[str]]:
    """Ticker symbols are not identities: the same code can name different tokens on two
    exchanges (or a migrated / deposit-halted token). When a symbol's USD value on two
    venues differs by more than ``tol``, keep the venues apart by renaming it
    ``SYMBOL@venue`` everywhere. Returns (quotes, symbols that were split)."""
    venues = sorted({q.venue for q in quotes})
    if len(venues) < 2:
        return list(quotes), []
    vals = {v: usd_values([q for q in quotes if q.venue == v]) for v in venues}
    split: set[str] = set()
    syms = {a for q in quotes for a in (q.base, q.quote)}
    for a in syms:
        if a == "USD":
            continue
        seen = [vals[v][a] for v in venues if a in vals[v]]
        if len(seen) >= 2 and max(seen) / min(seen) > 1 + tol:
            split.add(a)

    def ren(a: str, v: str) -> str:
        return f"{a}@{v}" if a in split else a

    out = [
        Quote(
            ren(q.base, q.venue),
            ren(q.quote, q.venue),
            q.bid,
            q.ask,
            q.bid_size,
            q.ask_size,
            q.fee,
            q.venue,
        )
        for q in quotes
    ]
    return out, sorted(split)


# --------------------------------------------------------------------------- analysis


def _q(xs: Sequence[float], p: float) -> float:
    if not xs:
        return math.nan
    s = sorted(xs)
    return s[min(len(s) - 1, round(p * (len(s) - 1)))]


def analyze(
    snapshots: Sequence[Snapshot],
    fee_scenarios: dict[str, dict[str, float]],
    limit: int = 20,
    method: str = "spfa",
    progress: Callable[[str], None] | None = None,
    symbol_tol: float = 0.10,
) -> dict[str, Any]:
    """For each scenario: how often profitable cycles appear, how big, how long.

    A scenario maps venue -> fee; only quotes from the listed venues are used, so
    ``{"kraken": 0.008}`` is a single-venue scan and two venues make it cross-venue
    (with :func:`reconcile_symbols` applied)."""
    if not snapshots:
        raise ValueError("recording is empty")
    ts = [s.ts for s in snapshots]
    gaps = [b - a for a, b in itertools.pairwise(ts)]
    step = statistics.median(gaps) if gaps else 0.0
    # A pause in recording (network outage, machine asleep) must not make two snapshots on
    # either side of it look consecutive, or cycle lifetimes would be overstated.
    contiguous = [True] + [g <= 2 * step for g in gaps]
    breaks = [(a, b) for (a, b), ok in zip(itertools.pairwise(ts), contiguous[1:], strict=True) if not ok]
    out: dict[str, Any] = {
        "snapshots": len(snapshots),
        "start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts[0])),
        "end": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts[-1])),
        "median_interval_s": step if gaps else None,
        "recording_gaps": [
            {
                "from": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(a)),
                "to": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(b)),
                "seconds": round(b - a),
            }
            for a, b in breaks
        ],
        "covered_s": round(sum(g for g, ok in zip(gaps, contiguous[1:], strict=True) if ok)),
        "venues": sorted({q.venue for s in snapshots for q in s.quotes}),
        "assets_median": statistics.median(
            len({a for q in s.quotes for a in (q.base, q.quote)}) for s in snapshots
        ),
        "pairs_median": statistics.median(len(s.quotes) for s in snapshots),
        "scenarios": {},
    }
    for name, fees in fee_scenarios.items():
        per_snap: list[list[CycleReport]] = []
        split_counts: list[int] = []
        usd: list[dict[str, float]] = []
        for i, s in enumerate(snapshots):
            qs = [q for q in s.quotes if q.venue in fees]
            qs, split = reconcile_symbols(qs, symbol_tol)
            split_counts.append(len(split))
            usd.append(usd_values(qs))  # value split symbols on their own venue
            g = QuoteGraph.from_quotes(with_fees(qs, fees))
            per_snap.append(find_cycles(g, limit=limit, method=method))
            if progress and (i + 1) % 25 == 0:
                progress(f"  {name}: {i + 1}/{len(snapshots)} snapshots")
        summary = _summarize(fees, per_snap, ts, usd, limit, contiguous)
        summary["symbols_split_median"] = statistics.median(split_counts)
        out["scenarios"][name] = summary
    return out


def _summarize(
    fees: dict[str, float],
    per_snap: list[list[CycleReport]],
    ts: list[float],
    usd: list[dict[str, float]],
    limit: int,
    contiguous: Sequence[bool] | None = None,
) -> dict[str, Any]:
    # Track each distinct cycle across consecutive snapshots to measure persistence.
    runs: dict[str, list[list[int]]] = defaultdict(list)
    best: dict[str, dict[str, Any]] = {}
    returns: list[float] = []
    sizes_usd: list[float] = []
    profits_usd: list[float] = []
    lengths: list[int] = []
    for i, reps in enumerate(per_snap):
        for r in reps:
            key = canonical_key(r.assets)
            rs = runs[key]
            if rs and rs[-1][-1] == i - 1 and (contiguous is None or contiguous[i]):
                rs[-1].append(i)
            else:
                rs.append([i])
            v = usd[i].get(r.assets[0], math.nan)
            size_usd = r.max_size * v
            returns.append(r.net_return)
            sizes_usd.append(size_usd)
            profits_usd.append(size_usd * r.net_return)
            lengths.append(r.length)
            if key not in best or r.net_return > best[key]["net_return"]:
                best[key] = {
                    "cycle": r.describe(),
                    "net_return": r.net_return,
                    "max_size_usd": size_usd,
                    "max_profit_usd": size_usd * r.net_return,
                    "legs": [f"{e.venue}:{e.pair}:{e.side}" for e in r.legs],
                    "first_seen": time.strftime("%H:%M:%S", time.gmtime(ts[i])),
                }
    spans = [ts[run[-1]] - ts[run[0]] for rs in runs.values() for run in rs]
    counts = [len(run) for rs in runs.values() for run in rs]
    hit = sum(1 for reps in per_snap if reps)
    finite = [x for x in sizes_usd if math.isfinite(x)]
    pfin = [x for x in profits_usd if math.isfinite(x)]
    for k, b in best.items():
        b["episodes"] = len(runs[k])
        b["max_consecutive_snapshots"] = max(len(r) for r in runs[k])
    top = sorted(best.values(), key=lambda b: -b["max_profit_usd"])[:10]
    return {
        "fees": fees,
        "snapshots_with_cycle": hit,
        "fraction_with_cycle": hit / len(per_snap),
        "cycle_observations": len(returns),
        "distinct_cycles": len(best),
        "capped_at_limit": sum(1 for reps in per_snap if len(reps) >= limit),
        "cycle_length_counts": {str(k): lengths.count(k) for k in sorted(set(lengths))},
        "net_return": {"median": _q(returns, 0.5), "p90": _q(returns, 0.9), "max": _q(returns, 1)},
        "max_size_usd": {"median": _q(finite, 0.5), "p90": _q(finite, 0.9), "max": _q(finite, 1)},
        "max_profit_usd": {"median": _q(pfin, 0.5), "p90": _q(pfin, 0.9), "max": _q(pfin, 1)},
        "episodes": len(spans),
        "episode_snapshots": {"median": _q(counts, 0.5), "max": _q(counts, 1)},
        "episode_span_s": {"median": _q(spans, 0.5), "max": _q(spans, 1)},
        "top_by_profit": top,
    }
