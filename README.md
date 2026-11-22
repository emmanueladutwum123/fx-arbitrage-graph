# fx-arbitrage-graph

[![CI](https://github.com/emmanueladutwum123/fx-arbitrage-graph/actions/workflows/ci.yml/badge.svg)](https://github.com/emmanueladutwum123/fx-arbitrage-graph/actions/workflows/ci.yml)
[![Demo](https://img.shields.io/badge/demo-GitHub%20Pages-22628a)](https://emmanueladutwum123.github.io/fx-arbitrage-graph/)
[![Slides](https://img.shields.io/badge/slides-reveal.js-b83c0a)](https://emmanueladutwum123.github.io/fx-arbitrage-graph/slides/)

Can you make money just by exchanging currencies in a circle? This project turns that
question into graph theory and answers it on real exchange data.

* **Assets are vertices.** A quote "1 unit of *u* buys *r* units of *v*" is a directed edge
  *u → v*.
* **Weight each edge by −log r.** Then a round trip is profitable,
  r₁·r₂·…·r<sub>k</sub> > 1, exactly when its weights add up to less than zero. **Arbitrage is a
  negative-weight cycle.**
* **Bellman–Ford finds negative cycles.** Start it from a virtual source (distance 0 to every
  vertex) and relax all edges n − 1 times. A shortest path never repeats a vertex, so it has at
  most n − 1 edges. If round n still improves a distance, there is a negative cycle, and
  walking the predecessor pointers back recovers the trade. O(V·E).

Every step is proved in [`docs/theory.md`](docs/theory.md).

A 70-second captioned walkthrough of the demo (fair market, mispriced quote, real snapshot) is at
[`docs/video/demo-walkthrough.mp4`](docs/video/demo-walkthrough.mp4), also served at
[/video/demo-walkthrough.mp4](https://emmanueladutwum123.github.io/fx-arbitrage-graph/video/demo-walkthrough.mp4).
It is built from real renders of the page by `scripts/make_demo_video.py`.

![Bellman–Ford on a fair market (stops after round 2), then with one mispriced quote (round 5 still improves, so a negative cycle is found)](docs/img/bellman-ford-demo.gif)

## What's here

| | |
|---|---|
| `src/fxarb/` | Python package: quote graph, Bellman–Ford, SPFA, brute-force checker, profit and size of a cycle, data sources, CLI |
| `docs/theory.md` | The math: log transform, proof that n − 1 rounds suffice, correctness of the round-n check, why the predecessor walk lands on the cycle, complexity, SPFA, why not Dijkstra |
| `web/` | Interactive demo, deployed to [GitHub Pages](https://emmanueladutwum123.github.io/fx-arbitrage-graph/). Step-through teaching mode, plus a live-snapshot mode on recorded Kraken and Binance.US order books. Static and offline: no network calls, works from `file://` |
| `slides/` | 20-minute talk for Math 280 (reveal.js + KaTeX, bundled for offline use), [live](https://emmanueladutwum123.github.io/fx-arbitrage-graph/slides/), [PDF](slides/fx-arbitrage-slides.pdf) |
| `results/` | Measured benchmarks and the analysis of a real 2-hour recording |
| `cpp/` | Optional C++20 port (pybind11), cross-checked against the Python code |

## Install and use

```bash
git clone https://github.com/emmanueladutwum123/fx-arbitrage-graph
cd fx-arbitrage-graph
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # add ,parquet for Parquet recordings
```

```bash
fxarb demo                                   # the 5-currency example, round by round
fxarb demo --bump 0                          # fair market: stops early, no cycle

fxarb scan --venue frankfurter               # ECB reference rates (no arbitrage, by design)
fxarb scan --venue kraken                    # live Kraken top of book, 0.80% taker fee
fxarb scan --venue all --fee 0               # Kraken + Binance.US, ignoring fees
fxarb scan --venue all --save-json web/data/snapshot.json   # refresh the demo's snapshot

fxarb record --venue kraken binanceus --interval 5 --duration 7200 \
             --out recordings/run.csv.gz     # .csv, .csv.gz or .parquet
fxarb analyze recordings/run.csv.gz --fee 0.001 --json-out results/run.json
```

`scan` and `analyze` use public REST endpoints only (no API keys). Fees are stored nowhere in a
recording; `analyze` applies them afterwards, so one recording can be studied at several fee
levels. Default fees are each exchange's entry-tier **taker** fee, checked on 2026-11-21 on the
exchanges' own pages: Kraken Pro Tier 1 is 0.40% maker / **0.80%** taker
([kraken.com/pro/fees](https://www.kraken.com/pro/fees)); Binance.US is 0% maker / **0.02%** taker
([binance.us/en/fee](https://www.binance.us/en/fee)). Fees change, so pass `--fee` to override.

To serve the demo locally: `python -m http.server -d web` (or just open `web/index.html`).

## How the data is turned into a graph

For a pair BASE/QUOTE with best bid *b*, best ask *a*, depth at those prices, and fee *f*:

* sell BASE at the bid: edge BASE → QUOTE, rate *b*(1 − *f*), capacity = bid size (in BASE);
* buy BASE at the ask: edge QUOTE → BASE, rate (1 − *f*)/*a*, capacity = ask size × *a* (in QUOTE).

When several venues quote the same direction, only the best rate is kept (a worse parallel edge
can never be part of a better cycle). The **maximum tradable size** of a cycle is set by its
tightest leg: starting with *x* units, the amount reaching leg *i* is *x*·r₁⋯r<sub>i−1</sub>, which
must not exceed that leg's capacity.

**Same ticker, different token.** Combining venues exposed symbols whose prices differ by 1.7× to
100× between Kraken and Binance.US (for example `ONE`, `ENJ`): either different tokens under one
ticker, or a token whose deposits are halted on one side. Treating them as one asset produced fake
"+10,000%" cycles. When a symbol's USD value differs by more than 10% between venues, the scanner
keeps the venues apart (`ENJ@kraken`, `ENJ@binanceus`).

## Results on real data

RESULTS_SECTION

## Performance

Pure Python, single thread, measured on an Apple M2 (8 cores, 8 GiB), macOS, CPython 3.12. Full
table with edge-scan counts: [`results/benchmarks.md`](results/benchmarks.md).

| graph | V | E | cycle? | Bellman–Ford | BF + pred check | SPFA | C++ BF + check |
|---|---:|---:|:---:|---:|---:|---:|---:|
| real kraken, taker fees | 632 | 2,706 | no | 0.30 ms (3 rounds) | 0.39 ms | 0.61 ms | 0.012 ms |
| real kraken, no fees | 632 | 2,706 | yes | 70.58 ms (632 rounds) | 0.13 ms | 0.77 ms | 0.006 ms |
| real binanceus+kraken, taker fees | 704 | 3,086 | no | 0.44 ms (4 rounds) | 0.60 ms | 0.73 ms | 0.015 ms |
| real binanceus+kraken, no fees | 704 | 3,086 | yes | 93.41 ms (704 rounds) | 0.15 ms | 0.87 ms | 0.006 ms |
| synthetic n=3000, deg 8, consistent | 3,000 | 24,000 | no | 5.01 ms (5 rounds) | 5.99 ms | 9.80 ms | 0.255 ms |
| synthetic n=3000, deg 8, 1% mispricing | 3,000 | 24,000 | yes | 3321.10 ms (3000 rounds) | 2.71 ms | 4.81 ms | 0.172 ms |
| adversarial chain n=800 (reverse order) | 800 | 799 | no | 25.68 ms (800 rounds) | 47.13 ms | 57.60 ms | 1.543 ms |

What the numbers say:

* **With no cycle (the normal case after fees), early exit makes Bellman–Ford fast**: real
  graphs of 200–700 assets settle in 2–4 rounds, under a millisecond. Plain Bellman–Ford is
  slightly faster than SPFA here, most likely because its inner loop does less bookkeeping.
* **With a cycle, classic Bellman–Ford must run all n rounds** before the round-n check fires:
  3.3 s for 3,000 assets. The fix is the predecessor-graph check (any cycle of predecessor
  pointers is negative, Lemma 4 in the theory notes): it finds a cycle after 1–2 rounds, 540× to
  1,200× sooner on these graphs. This check, not SPFA's queue, is where SPFA's speed on these graphs comes
  from; in pure Python, Bellman–Ford with the check beats SPFA.
* **Worst case is real:** on a chain whose edges are listed back to front, every variant needs
  all n rounds, as the O(V·E) bound allows.
* **C++20 (pybind11, `-O3`)** runs the same algorithms 15–64× faster than pure Python with
  identical results ([table](results/benchmarks.md#c20-extension-pybind11--o3-vs-pure-python)).

## Tests

`pytest` runs 70+ tests, including property-based tests with Hypothesis:

* markets priced from one consistent set of values plus any positive spread **never** contain a
  cycle (300 random markets);
* injecting a mispricing larger than the round-trip cost **always** produces a cycle whose
  product is > 1 (300 random markets);
* Bellman–Ford, Bellman–Ford with the predecessor check, and SPFA agree with a brute-force
  enumeration of every simple cycle on 500 random small graphs, and every returned cycle is
  simple, made of real edges and negative;
* edge cases: 2-cycles across venues, 2-cycles killed by fees, disconnected markets, missing
  quotes, zero, negative, NaN and crossed prices rejected, float noise on reference rates;
* the browser engine (`web/fxarb.js`, run under Node) matches the Python package on the real
  snapshot; the C++ extension matches it exactly on random graphs;
* the slides' speaker-note timings add up to exactly 18:00, and each script fits its time at
  130 words per minute.

CI runs ruff, mypy (strict) and the tests on Python 3.11–3.13, and builds the C++ extension.

## Limitations

* **Top of book only.** Size is limited to the best price level; deeper levels have worse
  prices, so larger trades earn less than the reported return.
* **Latency.** A snapshot is one REST response. By the time three or four orders reach the
  exchange, the prices can have moved, and other traders with co-located servers see the same
  gaps first. A cycle that lasts one 5-second snapshot is not something you could reliably catch.
* **Cross-venue cycles need money already on both exchanges.** Moving coins between exchanges
  takes minutes to hours and costs withdrawal fees, so those cycles are an upper bound.
* **Fees are the entry tier.** Very large traders pay much less, which is why the analysis also
  reports a hypothetical lower-fee scenario.
* **Bellman–Ford finds *a* negative cycle, not the best one.** Finding the most profitable simple
  cycle is NP-hard (it would decide Hamiltonian cycle). `find_cycles` lists several cycles
  greedily by deleting each cycle's tightest leg and searching again.
* Minimum order sizes and price/lot rounding are not modelled.

These are the reasons real arbitrage is rare and short-lived: when a gap is bigger than the costs,
someone faster closes it.

## License

MIT, see [LICENSE](LICENSE). Bundled third-party code in `slides/vendor/` (reveal.js, KaTeX) is
MIT-licensed; their licenses are included.
