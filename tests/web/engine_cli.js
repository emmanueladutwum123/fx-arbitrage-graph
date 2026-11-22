// node tests/web/engine_cli.js <snapshot.json> <fees-json> : prints the JS engine's result as JSON
const fs = require("fs");
const F = require("../../web/fxarb.js");
const snap = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const fees = JSON.parse(process.argv[3]);
const quotes = F.quotesFromSnapshot(snap).filter(q => q.venue in fees);
const { quotes: qs, split } = F.reconcile(quotes);
const g = F.buildGraph(qs, fees);
const r = F.findCycles(g, 5);
console.log(JSON.stringify({ n: g.assets.length, m: g.edges.length, split,
  cycles: r.cycles.map(c => ({ assets: c.assets, product: c.product, maxSize: c.maxSize })) }));
