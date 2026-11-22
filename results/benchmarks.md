# Benchmarks: Bellman–Ford vs SPFA (pure Python)

Measured 2026-11-22T02:24:39Z on Apple M2, 8 logical cores, 8 GiB, Darwin 27.0.0, CPython 3.12.13. Median wall time of repeated runs, single thread. Real graphs come from the snapshot `web/data/snapshot.json` taken 2026-11-22T02:11:50Z.

BF = classic Bellman–Ford with early exit (stops at round n when a cycle exists). BF+check = the same plus an O(V) predecessor-graph cycle check after each round. SPFA = queue-based, with the same check every V relaxations.

| case | V | E | BF ms | BF rounds | BF+check ms | BF+check rounds | SPFA ms | BF edge scans | SPFA edge scans | cycle |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| real binanceus, taker fees | 205 | 530 | 0.04 | 2 | 0.05 | 2 | 0.08 | 1,060 | 560 | no |
| real binanceus, no fees | 205 | 530 | 3.58 | 205 | 0.05 | 2 | 0.09 | 108,650 | 776 | yes |
| real kraken, taker fees | 632 | 2706 | 0.30 | 3 | 0.39 | 3 | 0.61 | 8,118 | 5,039 | no |
| real kraken, no fees | 632 | 2706 | 70.58 | 632 | 0.13 | 1 | 0.77 | 1,710,192 | 6,072 | yes |
| real binanceus+kraken, taker fees | 704 | 3086 | 0.44 | 4 | 0.60 | 4 | 0.73 | 12,344 | 5,433 | no |
| real binanceus+kraken, no fees | 704 | 3086 | 93.41 | 704 | 0.15 | 1 | 0.87 | 2,172,544 | 6,703 | yes |
| synthetic n=100, deg 8, consistent | 100 | 800 | 0.11 | 4 | 0.12 | 4 | 0.13 | 3,200 | 1,433 | no |
| synthetic n=100, deg 8, 1% mispricing | 100 | 800 | 3.07 | 100 | 0.07 | 2 | 0.16 | 80,000 | 1,705 | yes |
| synthetic n=300, deg 8, consistent | 300 | 2400 | 0.37 | 4 | 0.42 | 4 | 0.64 | 9,600 | 6,521 | no |
| synthetic n=300, deg 8, 1% mispricing | 300 | 2400 | 30.31 | 300 | 0.24 | 2 | 0.53 | 720,000 | 4,579 | yes |
| synthetic n=1000, deg 8, consistent | 1000 | 8000 | 1.71 | 5 | 2.00 | 5 | 2.43 | 40,000 | 17,751 | no |
| synthetic n=1000, deg 8, 1% mispricing | 1000 | 8000 | 376.46 | 1000 | 0.88 | 2 | 1.63 | 8,000,000 | 7,987 | yes |
| synthetic n=3000, deg 8, consistent | 3000 | 24000 | 5.01 | 5 | 5.99 | 5 | 9.80 | 120,000 | 80,297 | no |
| synthetic n=3000, deg 8, 1% mispricing | 3000 | 24000 | 3321.10 | 3000 | 2.71 | 2 | 4.81 | 72,000,000 | 25,266 | yes |
| adversarial chain n=200 (reverse order) | 200 | 199 | 1.55 | 200 | 2.67 | 200 | 3.38 | 39,800 | 19,900 | no |
| adversarial chain n=800 (reverse order) | 800 | 799 | 25.68 | 800 | 47.13 | 800 | 57.60 | 639,200 | 319,600 | no |

## C++20 extension (pybind11, `-O3`) vs pure Python

Same algorithms, same edge order, identical results (tests/test_cpp.py). Times exclude the one-time conversion of the edge list into the C++ graph.

| case | V | E | BF py ms | BF C++ ms | speedup | BF+check py | BF+check C++ | SPFA py | SPFA C++ | speedup |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| real binanceus, taker fees | 205 | 530 | 0.04 | 0.001 | 29× | 0.05 | 0.002 | 0.08 | 0.003 | 23× |
| real binanceus, no fees | 205 | 530 | 3.58 | 0.075 | 48× | 0.05 | 0.002 | 0.09 | 0.004 | 23× |
| real kraken, taker fees | 632 | 2706 | 0.30 | 0.010 | 32× | 0.39 | 0.012 | 0.61 | 0.015 | 42× |
| real kraken, no fees | 632 | 2706 | 70.58 | 2.132 | 33× | 0.13 | 0.006 | 0.77 | 0.018 | 42× |
| real binanceus+kraken, taker fees | 704 | 3086 | 0.44 | 0.012 | 37× | 0.60 | 0.015 | 0.73 | 0.017 | 43× |
| real binanceus+kraken, no fees | 704 | 3086 | 93.41 | 2.665 | 35× | 0.15 | 0.006 | 0.87 | 0.020 | 43× |
| synthetic n=100, deg 8, consistent | 100 | 800 | 0.11 | 0.003 | 37× | 0.12 | 0.004 | 0.13 | 0.004 | 36× |
| synthetic n=100, deg 8, 1% mispricing | 100 | 800 | 3.07 | 0.053 | 58× | 0.07 | 0.002 | 0.16 | 0.004 | 35× |
| synthetic n=300, deg 8, consistent | 300 | 2400 | 0.37 | 0.012 | 31× | 0.42 | 0.014 | 0.64 | 0.019 | 34× |
| synthetic n=300, deg 8, 1% mispricing | 300 | 2400 | 30.31 | 0.476 | 64× | 0.24 | 0.011 | 0.53 | 0.015 | 36× |
| synthetic n=1000, deg 8, consistent | 1000 | 8000 | 1.71 | 0.062 | 28× | 2.00 | 0.071 | 2.43 | 0.109 | 22× |
| synthetic n=1000, deg 8, 1% mispricing | 1000 | 8000 | 376.46 | 17.819 | 21× | 0.88 | 0.051 | 1.63 | 0.048 | 34× |
| synthetic n=3000, deg 8, consistent | 3000 | 24000 | 5.01 | 0.220 | 23× | 5.99 | 0.255 | 9.80 | 0.568 | 17× |
| synthetic n=3000, deg 8, 1% mispricing | 3000 | 24000 | 3321.10 | 218.650 | 15× | 2.71 | 0.172 | 4.81 | 0.234 | 21× |
| adversarial chain n=200 (reverse order) | 200 | 199 | 1.55 | 0.028 | 56× | 2.67 | 0.104 | 3.38 | 0.106 | 32× |
| adversarial chain n=800 (reverse order) | 800 | 799 | 25.68 | 0.404 | 64× | 47.13 | 1.543 | 57.60 | 1.561 | 37× |
