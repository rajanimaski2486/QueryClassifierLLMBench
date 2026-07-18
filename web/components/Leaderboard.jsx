"use client";

import { useMemo, useState } from "react";
import { f3, ms, methodLabel, pctFmt, shortModel } from "./format";

const COLS = [
  { key: "composite", label: "Composite", get: (s) => s.composite, fmt: f3 },
  { key: "route_f1", label: "Route mF1", get: (s) => s.route.macro_f1, fmt: f3 },
  { key: "route_acc", label: "Route acc", get: (s) => s.route.accuracy, fmt: f3 },
  { key: "type_f1", label: "Type mF1", get: (s) => s.type.macro_f1, fmt: f3 },
  { key: "cat_f1", label: "Cat mF1", get: (s) => s.categories.macro.f1, fmt: f3 },
  { key: "ent_f1", label: "Ent F1", get: (s) => s.entities.exact.f1, fmt: f3 },
  {
    key: "halluc",
    label: "Halluc.",
    get: (s) => s.entities.hallucination_rate,
    fmt: pctFmt,
  },
  {
    key: "schema",
    label: "Schema ok",
    get: (s) => s.adherence.schema_valid_rate,
    fmt: pctFmt,
  },
  {
    key: "json",
    label: "JSON ok",
    get: (s) => s.adherence.json_valid_rate,
    fmt: pctFmt,
  },
  {
    key: "tool",
    label: "Tool rate",
    get: (s) => s.adherence.tool_call_rate,
    fmt: pctFmt,
  },
  { key: "eff", label: "Effic.", get: (s) => s.efficiency, fmt: f3 },
  { key: "p95", label: "p95", get: (s) => s.ops.latency_p95_ms, fmt: ms },
];

export default function Leaderboard({ rows }) {
  const [sortKey, setSortKey] = useState("composite");
  const [asc, setAsc] = useState(false);

  const sorted = useMemo(() => {
    const col = COLS.find((c) => c.key === sortKey) ?? COLS[0];
    return [...rows].sort((a, b) => {
      const va = col.get(a) ?? -Infinity;
      const vb = col.get(b) ?? -Infinity;
      return asc ? va - vb : vb - va;
    });
  }, [rows, sortKey, asc]);

  const maxComposite = Math.max(...rows.map((r) => r.composite), 0.0001);

  return (
    <div className="card">
      <h2>Leaderboard</h2>
      <p className="desc">
        One row per model, shown with its best structured-output method, over
        all 77 gold queries. Sorted by composite (0.45·route macro-F1 +
        0.35·quality + 0.10·schema + 0.10·efficiency). Click a column to
        re-sort.
      </p>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Model</th>
            <th>Method</th>
            {COLS.map((c) => (
              <th
                key={c.key}
                className="sortable"
                onClick={() => {
                  if (sortKey === c.key) setAsc(!asc);
                  else {
                    setSortKey(c.key);
                    setAsc(false);
                  }
                }}
              >
                {c.label}
                {sortKey === c.key ? (asc ? " ↑" : " ↓") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((s, i) => (
            <tr key={s.model + s.method}>
              <td className="muted">{i + 1}</td>
              <td>
                <span className="model-name">{shortModel(s.model)}</span>
                <span className={`pill ${s.tier}`}>{s.tier}</span>
              </td>
              <td>{methodLabel[s.method] ?? s.method}</td>
              {COLS.map((c) => (
                <td key={c.key}>
                  {c.key === "composite" ? (
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 8,
                      }}
                    >
                      <span
                        aria-hidden
                        style={{
                          width: 64,
                          height: 6,
                          borderRadius: 4,
                          background: "var(--grid)",
                          overflow: "hidden",
                          display: "inline-block",
                        }}
                      >
                        <span
                          style={{
                            display: "block",
                            height: "100%",
                            width: `${(s.composite / maxComposite) * 100}%`,
                            background: "var(--series-1)",
                            borderRadius: 4,
                          }}
                        />
                      </span>
                      <strong>{f3(s.composite)}</strong>
                    </span>
                  ) : (
                    c.fmt(c.get(s))
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
