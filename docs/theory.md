# Arbitrage as a negative cycle: the mathematics

This note proves every claim the code relies on. Section numbers are referred to from
docstrings in `src/fxarb/`.

## 0. Setup and notation

A **market** is a directed graph $G = (V, E)$ with $n = |V|$ vertices (assets) and
$m = |E|$ edges. An edge $(u, v)$ carries a **rate** $r(u,v) > 0$: one unit of $u$ converts
into $r(u,v)$ units of $v$. Rates already include costs. For a pair BASE/QUOTE with best
bid $b$, best ask $a$ and proportional fee $f$:

$$
r(\text{BASE}, \text{QUOTE}) = b\,(1-f), \qquad r(\text{QUOTE}, \text{BASE}) = \frac{1-f}{a}.
$$

(When several venues quote the same ordered pair we keep only the largest rate; any cycle
through a worse parallel edge is dominated by the same cycle through the best one.)

A **walk** is a sequence of vertices $x_0, x_1, \dots, x_k$ with $(x_{i-1}, x_i) \in E$; it has
$k$ edges. A **path** is a walk with no repeated vertex. A **cycle** is a walk with
$x_k = x_0$, $k \ge 2$, and $x_0, \dots, x_{k-1}$ distinct. Trading around a cycle $C$
multiplies your holding by $R(C) = \prod_{i=1}^{k} r(x_{i-1}, x_i)$. $C$ is an
**arbitrage** if $R(C) > 1$.

Define the **weight** $w(u,v) = -\log r(u,v)$ and $w(C) = \sum_i w(x_{i-1}, x_i)$. The base of
the logarithm does not matter; the code uses $\ln$.

## 1. Products become sums

**Theorem 1.** A cycle $C$ is an arbitrage if and only if $w(C) < 0$.

*Proof.* Since $\log$ turns products into sums,
$w(C) = -\sum_i \log r(x_{i-1}, x_i) = -\log R(C)$. Since $\log$ is strictly increasing,
$R(C) > 1 \iff \log R(C) > 0 \iff w(C) < 0$. $\blacksquare$

So "is there an arbitrage?" is exactly "does $G$ contain a negative-weight cycle?".

**Proposition 1 (consistent prices rule out arbitrage).** Suppose there is a price
$p : V \to (0, \infty)$ in some common unit such that every rate satisfies
$r(u,v) \le p(u)/p(v)$ (no conversion gives you more value than you put in). Then no cycle
is an arbitrage.

*Proof.* For a cycle $C$, $R(C) \le \prod_i p(x_{i-1})/p(x_i) = 1$, because the product
telescopes: every $p(x_i)$ appears once in a numerator and once in a denominator. $\blacksquare$

This is why the ECB reference rates show no arbitrage (each cross rate *is*
$p(u)/p(v)$, with equality), and why a market built from one price vector plus any
non-negative spread or fee never contains a cycle (this is a property test in
`tests/test_algorithms.py`). The converse also holds: if $G$ has no negative cycle, the
shortest-path distances $\delta$ of Section 2 satisfy the triangle inequality
$\delta(v) \le \delta(u) + w(u,v) = \delta(u) - \ln r(u,v)$. Rearranging,
$r(u,v) \le e^{\delta(u)}/e^{\delta(v)}$, so $p = e^{\delta}$ is a consistent price vector.
"No arbitrage" and "consistent prices exist" are the same statement.

## 2. Bellman–Ford from a virtual source

Add a new vertex $s$ and an edge $(s, v)$ of weight $0$ to every $v \in V$. Call the
result $G'$. Every vertex is now reachable from $s$, so *every* negative cycle in $G$ is
reachable, not just those near some chosen start currency. The code never builds $s$:
it starts every distance at $0$ (the weight of the edge $s \to v$) and uses
`pred = -1` to mean "reached directly from $s$".

**Algorithm.** Keep $d(v)$ and $\text{pred}(v)$, initially $d(v) = 0$, $\text{pred}(v) = -1$.
*Relaxing* edge $(u,v)$ means: if $d(u) + w(u,v) < d(v)$, set $d(v) \leftarrow d(u) + w(u,v)$
and $\text{pred}(v) \leftarrow u$. A *round* relaxes every edge of $G$ once, in a fixed
order. Run rounds $1, 2, \dots, n$; round $n$ is the check.

For $k \ge 0$ let $\delta_k(v)$ be the least weight of a walk in $G'$ from $s$ to $v$ that uses
at most $k$ edges of $G$ (after the first edge $s \to x_0$). Let $\sigma(v)$ be the least
weight of a *path* from $s$ to $v$ in $G'$. There are finitely many paths, so $\sigma(v)$
always exists, even when $G$ has negative cycles.

**Lemma 1 (every value is earned).** At every moment, $d(v)$ equals the weight of some walk
from $s$ to $v$.

*Proof.* True initially ($d(v) = 0 = w(s,v)$). A relaxation sets
$d(v) = d(u) + w(u,v)$: the walk for $u$ followed by the edge $(u,v)$. $\blacksquare$

**Lemma 2 (round $k$).** After round $k$, $d(v) \le \delta_k(v)$ for every $v$.

*Proof.* Induction on $k$. For $k = 0$, $d(v) = 0 = \delta_0(v)$. Let $k \ge 1$ and take a best
walk $W$ to $v$ with at most $k$ edges of $G$. If it has fewer than $k$, then
$w(W) = \delta_{k-1}(v) \ge d(v)$ by induction (distances never increase). Otherwise $W$ ends
with an edge $(u, v)$, and the part before it is a walk to $u$ with at most $k-1$ edges of
$G$, so $\delta_{k-1}(u) \le w(W) - w(u,v)$. When round $k$ relaxes $(u,v)$, $d(u) \le \delta_{k-1}(u)$
already, so afterwards $d(v) \le d(u) + w(u,v) \le w(W) = \delta_k(v)$. $\blacksquare$

**Lemma 3 (paths are short).** A path in $G$ has at most $n - 1$ edges.

*Proof.* A path with $k$ edges visits $k + 1$ distinct vertices, and there are only $n$, so
$k + 1 \le n$. (This is the fact from Problem 4a of the graph handout.) $\blacksquare$

Consequently a path from $s$ uses at most $n-1$ edges of $G$, so $\sigma(v) \ge \delta_{n-1}(v)$.

**Theorem 2 ($n-1$ rounds suffice).** If $G$ has no negative cycle, then after round $n-1$,
$d(v) = \delta(v)$, the true shortest-path distance from $s$, for every $v$.

*Proof.* Take any walk from $s$ to $v$. If it repeats a vertex it contains a cycle; deleting
that cycle gives a shorter walk to $v$ whose weight is no larger, because the cycle has
weight $\ge 0$. Repeating, every walk can be replaced by a path of no greater weight, so
$\delta(v) = \sigma(v)$. By Lemma 3, $\sigma(v) = \delta_{n-1}(v)$. Lemma 2 gives
$d(v) \le \delta_{n-1}(v) = \delta(v)$, and Lemma 1 gives $d(v) \ge \delta(v)$ (it is the weight
of a walk, and $\delta(v)$ is the least such weight). $\blacksquare$

**Theorem 3 (the round-$n$ check).** Round $n$ changes some distance if and only if $G$
contains a negative cycle.

*Proof.* ($\Rightarrow$, by contrapositive.) Suppose $G$ has no negative cycle. By Theorem 2,
$d = \delta$ after round $n-1$. Shortest distances satisfy the triangle inequality
$\delta(v) \le \delta(u) + w(u,v)$: a best walk to $u$ followed by $(u,v)$ is a walk to $v$. So
no edge can be relaxed in round $n$.

($\Leftarrow$, by contradiction.) Let $C = x_0 \to x_1 \to \dots \to x_k = x_0$ be a cycle with
$w(C) < 0$, and suppose round $n$ changes nothing. Then after round $n$ every edge satisfies
$d(v) \le d(u) + w(u,v)$; in particular $d(x_i) \le d(x_{i-1}) + w(x_{i-1}, x_i)$ for
$i = 1, \dots, k$. All $d$ values are finite real numbers, so we may add the $k$ inequalities.
Each $d(x_i)$ appears exactly once on each side, so they cancel and leave
$0 \le w(C)$, a contradiction. $\blacksquare$

**Corollary (early exit).** The same summation shows that if *any* round changes nothing,
then $G$ has no negative cycle, so the algorithm may stop there. On real markets with
fees this typically happens after 2 to 5 rounds (`results/benchmarks.md`).

## 3. Recovering the cycle

**Lemma 4a (predecessor invariant).** At every moment, if $\text{pred}(v) = u \ne -1$ then
$d(v) \ge d(u) + w(u,v)$.

*Proof.* When the pointer is set, equality holds. Afterwards $d(v)$ cannot change without
resetting the pointer, and $d(u)$ can only decrease. $\blacksquare$

**Lemma 4 (predecessor cycles are negative).** If the predecessor pointers ever form a cycle,
that cycle has negative weight.

*Proof.* Let the cycle be $x_0 \to x_1 \to \dots \to x_{k-1} \to x_0$, meaning
$\text{pred}(x_i) = x_{i-1}$ (indices mod $k$), and suppose the last of these pointers to be set
was $\text{pred}(x_0) \leftarrow x_{k-1}$. Look at the values $d$ just *before* that relaxation.
The relaxation happened, so $d(x_0) > d(x_{k-1}) + w(x_{k-1}, x_0)$. The other $k - 1$
pointers already existed, so by Lemma 4a $d(x_i) \ge d(x_{i-1}) + w(x_{i-1}, x_i)$ for
$i = 1, \dots, k-1$. Adding all $k$ inequalities, the $d$ terms cancel exactly as in
Theorem 3, leaving $0 > w(C)$. $\blacksquare$

**Theorem 4 (the predecessor walk lands in a negative cycle).** Suppose vertex $v$ is
relaxed during round $n$. Then, right after that relaxation, following predecessor pointers
from $v$ for $n$ steps reaches a vertex on a cycle of predecessor pointers, and that cycle
is negative, i.e. an arbitrage.

*Proof.* Let $x_0 = v$ and $x_{j+1} = \text{pred}(x_j)$. First we show this chain never reaches
$-1$ without repeating a vertex. Suppose instead $x_0, x_1, \dots, x_q$ are distinct and
$\text{pred}(x_q) = -1$. Then $x_q$ was never relaxed, so $d(x_q) = 0$, and
$P = s \to x_q \to x_{q-1} \to \dots \to x_0$ is a path in $G'$. Chaining Lemma 4a along $P$,

$$
d(v) \;\ge\; d(x_q) + \sum_{j=1}^{q} w(x_j, x_{j-1}) \;=\; w(P) \;\ge\; \sigma(v) \;\ge\; \delta_{n-1}(v) \;\ge\; d^{(n-1)}(v),
$$

where $d^{(n-1)}(v)$ is the value of $d(v)$ at the end of round $n-1$ (the last step is
Lemma 2). But $v$ was just relaxed in round $n$, so $d(v) < d^{(n-1)}(v)$. Contradiction.

So the chain repeats a vertex. Each vertex has one predecessor, so once the chain repeats it
goes around the same cycle forever: the chain is a "tail" followed by a cycle. Tail and
cycle together use at most $n$ distinct vertices and the cycle has at least 2, so the tail
has fewer than $n$ vertices and $x_n$ is on the cycle. By Lemma 4 the cycle is negative,
and by Theorem 1 it is an arbitrage. From $x_n$ we follow pointers until we return to
$x_n$, which lists the cycle backwards; reversing it gives the trading order. $\blacksquare$

This is exactly `cycle_from_pred` in `src/fxarb/bellman_ford.py`. Lemma 4 also justifies the
optional early check (`pred_check=True`, and SPFA's periodic check): if the pointers form a
cycle at *any* time, that cycle is an arbitrage, so we may stop at once.

**Remark (a negative cycle, not the best one).** Bellman–Ford returns *some* negative cycle.
Finding the *most* negative simple cycle is NP-hard: give every edge of a graph weight $-1$;
its most negative simple cycle has weight $-n$ exactly when the graph has a Hamiltonian
cycle. That is why `find_cycles` lists several cycles greedily (delete the bottleneck leg,
search again) and does not claim to find the best.

## 4. Complexity

* **Bellman–Ford:** at most $n$ rounds, each scanning $m$ edges in $O(1)$ each: $O(nm) = O(VE)$
  time. The virtual source adds $n$ implicit edges, which does not change the bound. Cycle
  recovery is $O(n)$. Memory is $O(n + m)$. With early exit the best case is $O(m)$ (one round).
  For a complete market of $n$ currencies, $m = n(n-1)$, so $O(n^3)$.
* **Optional predecessor check:** $O(n)$ per round (each vertex has one pointer), so
  $O(n^2)$ extra in total, within $O(nm)$ whenever $m \ge n$.
* **SPFA:** same worst case $O(VE)$ (Section 5 shows at most $n$ passes, each scanning each
  edge at most once), usually far less.
* **Brute force:** a complete digraph on $n$ vertices has
  $\sum_{k=2}^{n} \binom{n}{k}(k-1)!$ simple cycles (2,365 for $n=7$, 1,112,073 for $n = 10$), which
  is why `brute.py` refuses graphs with more than 9 vertices.

## 5. SPFA (queue-based Bellman–Ford)

SPFA keeps a FIFO queue of vertices whose distance changed and only rescans their outgoing
edges. Initially all $n$ vertices are queued (they all just got $d = 0$ from $s$). Call the
first $n$ pops **pass 1**; pass $k+1$ consists of the vertices in the queue when pass $k$ ends.

**Lemma 5.** After pass $k$, $d(v) \le \delta_k(v)$.

*Proof sketch.* As in Lemma 2. Take a best walk ending with edge $(u,v)$. After pass $k-1$,
$d(u) \le \delta_{k-1}(u)$; consider the last change of $d(u)$ (or the start, if it never
changed). At that moment $u$ is in the queue or is added to it, so it is popped again,
in pass $k$ at the latest, and that pop relaxes $(u,v)$ with $d(u) \le \delta_{k-1}(u)$. $\blacksquare$

Hence the proof of Theorem 4 applies word for word to a vertex relaxed in pass $n$, so the
code stops there with a cycle. If the queue empties, every edge $(u,v)$ was scanned after
the last change of $d(u)$, so $d(v) \le d(u) + w(u,v)$ for all edges, and the summation in
Theorem 3 shows there is no negative cycle. Every $n$ relaxations the code also runs the
$O(n)$ predecessor-cycle check, which is sound by Lemma 4 and costs $O(1)$ amortised per
relaxation.

## 6. Why not Dijkstra?

Dijkstra's algorithm settles the closest unsettled vertex and never revisits it. That is
safe only if extending a path can never make it shorter, which needs $w \ge 0$. Exchange
graphs have negative weights whenever a rate exceeds 1 (1 USD buys 150 JPY, so
$w = -\ln 150 < 0$). Example with source $s$: $w(s,a) = 1$, $w(s,b) = 2$, $w(b,a) = -2$.
Dijkstra settles $a$ at distance 1, but $s \to b \to a$ has weight 0. With a negative cycle
it is worse: shortest walks do not exist at all, since going around the cycle again
always lowers the weight. Bellman–Ford does not settle vertices early, which is why it
tolerates negative edges and can *detect* negative cycles.

## 7. Floating point

The code relaxes only when the improvement exceeds $\varepsilon = 10^{-12}$ (in natural-log
units, a relative price change of $10^{-12}$). The proofs above are in exact arithmetic. With
the tolerance, every successful relaxation still makes a strict improvement, so Lemma 4
still yields $w(C) < -\varepsilon < 0$ for any predecessor cycle. What changes is that cycles with
$-\varepsilon \le w(C) < 0$ may go unreported. These are float noise: a reference-rate graph like
the ECB's has every cycle product equal to 1 up to rounding (about $10^{-16}$ relative), and
real arbitrage worth trading is many orders of magnitude larger than $10^{-12}$. As a final
guard, every reported cycle is re-priced from its edges (`evaluate_cycle`), and cycles with
product $\le 1$ are dropped.
