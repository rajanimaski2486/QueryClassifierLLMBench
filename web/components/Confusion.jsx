"use client";

import { useState } from "react";
import { methodLabel, shortModel } from "./format";

/* Route confusion matrix (gold rows × predicted cols, 5 routes + abstain)
   as a sequential-blue heatmap, one model × method at a time. */
export default function Confusion({ rows }) {
  const keys = rows.map((s) => `${s.model}|${s.method}`);
  const [sel, setSel] = useState(keys[0] ?? "");
  const [tip, setTip] = useState(null);

  const s = rows.find((r) => `${r.model}|${r.method}` === sel);
  if (!s) return null;

  const labels = s.route.confusion_labels;
  const m = s.route.confusion;
  const rowMax = m.map((r) => Math.max(...r, 1));
  const steps = [
    "var(--surface-1)",
    "var(--seq-100)",
    "var(--seq-250)",
    "var(--seq-400)",
    "var(--seq-550)",
    "var(--seq-700)",
  ];
  const cellColor = (v, max) => {
    if (v === 0) return steps[0];
    const t = v / max;
    return steps[Math.min(5, 1 + Math.floor(t * 4.999))];
  };
  const cell = 62;

  return (
    <div className="card" onMouseLeave={() => setTip(null)}>
      <h2>Route confusion</h2>
      <p className="desc">
        Rows are gold routes, columns are predictions; "abstain" collects
        missing or schema-invalid route outputs. Shading is scaled within each
        gold row, so rare routes (hybrid_v3 = 9, knn = 15 queries) stay
        readable next to hybrid_v2 (23).
      </p>
      <div className="row">
        <select value={sel} onChange={(e) => setSel(e.target.value)}>
          {rows.map((r) => {
            const k = `${r.model}|${r.method}`;
            return (
              <option key={k} value={k}>
                {shortModel(r.model)} · {methodLabel[r.method]}
              </option>
            );
          })}
        </select>
        <span className="small muted">
          route macro-F1 {s.route.macro_f1.toFixed(3)} · accuracy{" "}
          {s.route.accuracy.toFixed(3)}
        </span>
      </div>
      <svg
        width={cell * (labels.length + 1) + 90}
        height={cell * (labels.length + 1) + 10}
        role="img"
        aria-label="Route confusion matrix"
      >
        {labels.map((lab, j) => (
          <text
            key={`c${lab}`}
            x={90 + j * cell + cell / 2}
            y={16}
            textAnchor="middle"
            fontSize="11"
            fill="var(--text-muted)"
          >
            {lab}
          </text>
        ))}
        {labels.map((glab, i) => (
          <g key={`r${glab}`}>
            <text
              x={82}
              y={30 + i * cell + cell / 2 + 4}
              textAnchor="end"
              fontSize="11"
              fill="var(--text-muted)"
            >
              {glab}
            </text>
            {labels.map((plab, j) => {
              const v = m[i][j];
              const bg = cellColor(v, rowMax[i]);
              const strong = v > 0 && v / rowMax[i] > 0.55;
              return (
                <g key={plab}>
                  <rect
                    x={90 + j * cell}
                    y={30 + i * cell}
                    width={cell - 2}
                    height={cell - 2}
                    rx={6}
                    fill={bg}
                    stroke={i === j ? "var(--baseline)" : "var(--grid)"}
                    onMouseMove={(e) =>
                      setTip({
                        x: e.clientX,
                        y: e.clientY,
                        body: `gold ${glab} → predicted ${plab}: ${v}`,
                      })
                    }
                  />
                  {v > 0 && (
                    <text
                      x={90 + j * cell + (cell - 2) / 2}
                      y={30 + i * cell + (cell - 2) / 2 + 4}
                      textAnchor="middle"
                      fontSize="13"
                      fontWeight="600"
                      fill={strong ? "#fff" : "var(--text-primary)"}
                      pointerEvents="none"
                    >
                      {v}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        ))}
      </svg>
      {tip && (
        <div className="tooltip" style={{ left: tip.x + 14, top: tip.y + 14 }}>
          {tip.body}
        </div>
      )}
    </div>
  );
}
