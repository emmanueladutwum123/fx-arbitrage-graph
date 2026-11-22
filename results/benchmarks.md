# Benchmarks: Bellman–Ford vs SPFA (pure Python)

Measured 2026-11-22T02:13:19Z on Apple M2, 8 logical cores, 8 GiB, Darwin 27.0.0, CPython 3.12.13. Median wall time of repeated runs, single thread. Real graphs come from the snapshot `web/data/snapshot.json` taken 2026-11-22T02:11:50Z.

BF = classic Bellman–Ford with early exit (stops at round n when a cycle exists). BF+check = the same plus an O(V) predecessor-graph cycle check after each round. SPFA = queue-based, with the same check every V relaxations.

| case | V | E | BF ms | BF rounds | BF+check ms | BF+check rounds | SPFA ms | BF edge scans | SPFA edge scans | cycle |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| real binanceus, taker fees | 205 | 530 | 0.03 | 2 | 0.05 | 2 | 0.07 | 1,060 | 560 | no |
| real binanceus, no fees | 205 | 530 | 3.59 | 205 | 0.05 | 2 | 0.09 | 108,650 | 776 | yes |
| real kraken, taker fees | 632 | 2706 | 0.30 | 3 | 0.39 | 3 | 0.61 | 8,118 | 5,039 | no |
| real kraken, no fees | 632 | 2706 | 70.30 | 632 | 0.13 | 1 | 0.76 | 1,710,192 | 6,072 | yes |
| real binanceus+kraken, taker fees | 704 | 3086 | 0.44 | 4 | 0.60 | 4 | 0.69 | 12,344 | 5,433 | no |
| real binanceus+kraken, no fees | 704 | 3086 | 92.57 | 704 | 0.15 | 1 | 0.86 | 2,172,544 | 6,703 | yes |
| synthetic n=100, deg 8, consistent | 100 | 800 | 0.11 | 4 | 0.12 | 4 | 0.13 | 3,200 | 1,433 | no |
| synthetic n=100, deg 8, 1% mispricing | 100 | 800 | 3.07 | 100 | 0.07 | 2 | 0.16 | 80,000 | 1,705 | yes |
| synthetic n=300, deg 8, consistent | 300 | 2400 | 0.36 | 4 | 0.41 | 4 | 0.63 | 9,600 | 6,521 | no |
| synthetic n=300, deg 8, 1% mispricing | 300 | 2400 | 30.59 | 300 | 0.24 | 2 | 0.53 | 720,000 | 4,579 | yes |
| synthetic n=1000, deg 8, consistent | 1000 | 8000 | 1.66 | 5 | 1.98 | 5 | 2.32 | 40,000 | 17,751 | no |
| synthetic n=1000, deg 8, 1% mispricing | 1000 | 8000 | 372.01 | 1000 | 0.89 | 2 | 1.62 | 8,000,000 | 7,987 | yes |
| synthetic n=3000, deg 8, consistent | 3000 | 24000 | 5.01 | 5 | 6.03 | 5 | 9.62 | 120,000 | 80,297 | no |
| synthetic n=3000, deg 8, 1% mispricing | 3000 | 24000 | 3306.78 | 3000 | 2.70 | 2 | 4.77 | 72,000,000 | 25,266 | yes |
| adversarial chain n=200 (reverse order) | 200 | 199 | 1.55 | 200 | 2.66 | 200 | 3.32 | 39,800 | 19,900 | no |
| adversarial chain n=800 (reverse order) | 800 | 799 | 25.48 | 800 | 46.67 | 800 | 58.81 | 639,200 | 319,600 | no |
