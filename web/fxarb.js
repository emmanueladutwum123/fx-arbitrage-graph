/* fxarb.js: the same graph model and negative-cycle search as the Python package
 * (src/fxarb), for the browser. No dependencies, no network. Exposes globalThis.FXARB. */
(function (root) {
  "use strict";
  const EPS = 1e-12;

  /** quotes: [{venue, base, quote, bid, ask, bidSize, askSize}], fees: {venue: fee} */
  function buildGraph(quotes, fees) {
    const assets = [], index = new Map(), best = new Map();
    const vertex = a => { if (!index.has(a)) { index.set(a, assets.length); assets.push(a); } return index.get(a); };
    const add = (u, v, rate, capacity, q, side) => {
      const iu = vertex(u), iv = vertex(v), key = iu * 1e6 + iv, cur = best.get(key);
      if (!cur || rate > cur.rate) best.set(key, { u: iu, v: iv, rate, capacity, venue: q.venue, pair: q.base + "/" + q.quote, side });
    };
    for (const q of quotes) {
      const keep = 1 - (fees[q.venue] || 0);
      add(q.base, q.quote, q.bid * keep, q.bidSize, q, "sell");          // sell base at the bid
      add(q.quote, q.base, keep / q.ask, q.askSize * q.ask, q, "buy");   // buy base at the ask
    }
    const edges = [...best.values()];
    for (const e of edges) e.w = -Math.log(e.rate);
    const lookup = new Map(edges.map(e => [e.u * 1e6 + e.v, e]));
    return { assets, edges, edge: (u, v) => lookup.get(u * 1e6 + v) };
  }

  function cycleFromPred(pred, start, n) {
    let x = start;
    for (let i = 0; i < n; i++) { x = pred[x]; if (x < 0) throw new Error("walk reached the source"); }
    const back = [x]; let y = pred[x];
    while (y !== x) { back.push(y); y = pred[y]; }
    back.push(x); back.reverse();
    return back;
  }

  function findPredCycle(pred) {
    const n = pred.length, state = new Int32Array(n);
    for (let s = 0; s < n; s++) {
      if (state[s]) continue;
      let x = s;
      while (x >= 0 && !state[x]) { state[x] = s + 1; x = pred[x]; }
      if (x >= 0 && state[x] === s + 1) return cycleFromPred(pred, x, n);
    }
    return null;
  }

  /** Bellman–Ford from a virtual source, early exit, optional predecessor-cycle check. */
  function bellmanFord(n, edges, predCheck = true) {
    const dist = new Float64Array(n), pred = new Int32Array(n).fill(-1);
    let scans = 0;
    for (let rnd = 1; rnd <= n; rnd++) {
      let last = -1;
      for (const e of edges) {
        const nd = dist[e.u] + e.w;
        if (nd < dist[e.v] - EPS) { dist[e.v] = nd; pred[e.v] = e.u; last = e.v; }
      }
      scans += edges.length;
      if (last < 0) return { cycle: null, rounds: rnd, scans };
      if (rnd === n) return { cycle: cycleFromPred(pred, last, n), rounds: rnd, scans };
      if (predCheck) { const c = findPredCycle(pred); if (c) return { cycle: c, rounds: rnd, scans }; }
    }
    return { cycle: null, rounds: 0, scans };
  }

  const PREFERRED = ["USD", "EUR", "USDT", "USDC", "GBP", "BTC", "ETH", "JPY"];
  function rotate(cyc, assets) {
    let body = cyc.slice(0, -1);
    const names = body.map(i => assets[i]);
    for (const p of PREFERRED) { const k = names.indexOf(p); if (k >= 0) { body = body.slice(k).concat(body.slice(0, k)); break; } }
    return body.concat([body[0]]);
  }
  function canonicalKey(names) {
    const body = names.slice(0, -1); let bestRot = null;
    for (let i = 0; i < body.length; i++) { const r = body.slice(i).concat(body.slice(0, i)).join(">"); if (bestRot === null || r < bestRot) bestRot = r; }
    return bestRot;
  }

  function evaluate(g, cyc) {
    const legs = []; let product = 1, weight = 0, maxSize = Infinity, bottleneck = 0, running = 1;
    for (let i = 0; i + 1 < cyc.length; i++) {
      const e = g.edge(cyc[i], cyc[i + 1]); legs.push(e);
      const bound = e.capacity / running;
      if (bound < maxSize) { maxSize = bound; bottleneck = i; }
      running *= e.rate; product *= e.rate; weight += e.w;
    }
    return { assets: cyc.map(i => g.assets[i]), legs, product, weight, net: product - 1, maxSize, bottleneck };
  }

  /** Up to `limit` distinct profitable cycles: find one, delete its bottleneck leg, repeat. */
  function findCycles(g, limit = 5) {
    const found = [], seen = new Set();
    let edges = g.edges.slice(), rounds = 0, scans = 0;
    for (let t = 0; t < limit * 3 && found.length < limit; t++) {
      const r = bellmanFord(g.assets.length, edges);
      if (t === 0) { rounds = r.rounds; scans = r.scans; }
      if (!r.cycle) break;
      const rep = evaluate(g, rotate(r.cycle, g.assets));
      const cut = rep.legs[rep.bottleneck];
      edges = edges.filter(e => e !== cut);
      const key = canonicalKey(rep.assets);
      if (seen.has(key) || rep.net <= 0) continue;
      seen.add(key); found.push(rep);
    }
    return { cycles: found, rounds, scans };
  }

  /** USD value of each asset from mid prices, breadth-first from USD. */
  function usdValues(quotes) {
    const adj = new Map(), push = (a, b, m) => { if (!adj.has(a)) adj.set(a, []); adj.get(a).push([b, m]); };
    for (const q of quotes) { const mid = (q.bid + q.ask) / 2; push(q.quote, q.base, mid); push(q.base, q.quote, 1 / mid); }
    const vals = new Map([["USD", 1]]), todo = ["USD"];
    for (let h = 0; h < todo.length; h++) {
      const a = todo[h];
      for (const [b, m] of adj.get(a) || []) if (!vals.has(b)) { vals.set(b, vals.get(a) * m); todo.push(b); }
    }
    return vals;
  }

  /** Same ticker, different token: split a symbol by venue if its USD prices disagree > tol. */
  function reconcile(quotes, tol = 0.10) {
    const venues = [...new Set(quotes.map(q => q.venue))].sort();
    if (venues.length < 2) return { quotes, split: [] };
    const vals = Object.fromEntries(venues.map(v => [v, usdValues(quotes.filter(q => q.venue === v))]));
    const syms = new Set(quotes.flatMap(q => [q.base, q.quote])), split = new Set();
    for (const a of syms) {
      if (a === "USD") continue;
      const seen = venues.filter(v => vals[v].has(a)).map(v => vals[v].get(a));
      if (seen.length >= 2 && Math.max(...seen) / Math.min(...seen) > 1 + tol) split.add(a);
    }
    const ren = (a, v) => split.has(a) ? a + "@" + v : a;
    return { quotes: quotes.map(q => ({ ...q, base: ren(q.base, q.venue), quote: ren(q.quote, q.venue) })), split: [...split].sort() };
  }

  function quotesFromSnapshot(snap) {
    return snap.quotes.map(([venue, base, quote, bid, ask, bidSize, askSize]) => ({ venue, base, quote, bid, ask, bidSize, askSize }));
  }

  root.FXARB = { EPS, buildGraph, bellmanFord, findCycles, evaluate, usdValues, reconcile, canonicalKey, quotesFromSnapshot, cycleFromPred, findPredCycle };
  if (typeof module !== "undefined") module.exports = root.FXARB;
})(typeof globalThis !== "undefined" ? globalThis : this);
