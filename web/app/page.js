"use client";

import { useEffect, useState } from "react";
import Leaderboard from "../components/Leaderboard";
import SizeChart from "../components/SizeChart";
import QueryExplorer from "../components/QueryExplorer";

export default function Page() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch("./results.json")
      .then((r) => {
        if (!r.ok) throw new Error(`results.json: HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err)
    return (
      <main>
        <h1>Routing Bench</h1>
        <p className="subtitle">
          Could not load results.json — run <code>python bench/export.py</code>{" "}
          first. ({err})
        </p>
      </main>
    );
  if (!data)
    return (
      <main>
        <h1>Routing Bench</h1>
        <p className="subtitle">Loading results…</p>
      </main>
    );

  // one row per model: its best-composite structured-output method
  const best = new Map();
  for (const s of data.leaderboard) {
    const cur = best.get(s.model);
    if (!cur || s.composite > cur.composite) best.set(s.model, s);
  }
  const rows = [...best.values()].sort((a, b) => b.composite - a.composite);
  const modelKeys = rows.map((s) => `${s.model}|${s.method}`);

  return (
    <main>
      <h1>Routing Bench — stock-image query classification</h1>
      <p className="subtitle">
        {rows.length} models (each shown with its best structured-output
        method) over {data.gold.length} gold queries
        · NVIDIA-hosted models, all calls made offline by the runner · generated{" "}
        {data.generated_at}
      </p>
      <Leaderboard rows={rows} />
      <SizeChart rows={rows} />
      <QueryExplorer
        gold={data.gold}
        perQuery={data.per_query}
        modelKeys={modelKeys}
      />
      <p className="footer-note">
        Composite weights: route macro-F1 {data.weights.route_macro_f1} ·
        quality mean {data.weights.quality_mean} · schema-valid rate{" "}
        {data.weights.schema_valid_rate} · efficiency {data.weights.efficiency}
        . Efficiency = normalized 1/(p95 latency × credits per query). Route
        macro-F1 is the primary quality signal because hybrid_v2 covers 23/77
        gold rows and plain accuracy rewards over-predicting it.
      </p>
    </main>
  );
}
