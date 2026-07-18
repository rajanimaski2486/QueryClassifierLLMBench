"use client";

import { useState } from "react";
import { methodLabel, shortModel } from "./format";

function Tooltip({ tip }) {
  if (!tip) return null;
  return (
    <div className="tooltip" style={{ left: tip.x + 14, top: tip.y + 14 }}>
      {tip.body}
    </div>
  );
}

/* Horizontal grouped bars: p50 (blue) and p95 (aqua) latency per row,
   plus a second single-series chart for mean output tokens. */
export default function OpsBars({ rows }) {
  const [tip, setTip] = useState(null);

  const sorted = [...rows].sort(
    (a, b) => (a.ops.latency_p95_ms ?? 0) - (b.ops.latency_p95_ms ?? 0)
  );
  const maxLat = Math.max(...sorted.map((r) => r.ops.latency_p95_ms ?? 0), 1);
  const maxTok = Math.max(
    ...sorted.map((r) => r.ops.output_tokens_mean ?? 0),
    1
  );

  const rowH = 34;
  const labelW = 250;
  const chartW = 420;
  const tokW = 190;
  const H = sorted.length * rowH + 26;

  const hover = (e, body) => setTip({ x: e.clientX, y: e.clientY, body });

  return (
    <div className="card" onMouseLeave={() => setTip(null)}>
      <h2>Latency &amp; output volume</h2>
      <p className="desc">
        Per model × method over successful calls. Free-tier credits are 1 per
        request, so cost tracks request count (retries included) — the
        efficiency term in the composite uses p95 × credits/query.
      </p>
      <div className="legend">
        <span>
          <span className="swatch" style={{ background: "var(--series-1)" }} />
          p50 latency
        </span>
        <span>
          <span className="swatch" style={{ background: "var(--series-2)" }} />
          p95 latency
        </span>
        <span>
          <span className="swatch" style={{ background: "var(--seq-250)" }} />
          mean output tokens
        </span>
      </div>
      <svg
        width={labelW + chartW + tokW + 40}
        height={H}
        role="img"
        aria-label="Latency and output token bars per model and method"
      >
        {sorted.map((s, i) => {
          const y = i * rowH + 20;
          const p50 = s.ops.latency_p50_ms ?? 0;
          const p95 = s.ops.latency_p95_ms ?? 0;
          const tok = s.ops.output_tokens_mean ?? 0;
          const name = `${shortModel(s.model)} · ${methodLabel[s.method]}`;
          return (
            <g key={s.model + s.method}>
              <text
                x={labelW - 8}
                y={y + 11}
                textAnchor="end"
                fill="var(--text-secondary)"
                fontSize="12"
              >
                {name}
              </text>
              <rect
                x={labelW}
                y={y}
                width={Math.max(2, (p50 / maxLat) * chartW)}
                height={7}
                rx={3.5}
                fill="var(--series-1)"
                onMouseMove={(e) =>
                  hover(e, `${name} — p50 ${Math.round(p50).toLocaleString()} ms`)
                }
              />
              <rect
                x={labelW}
                y={y + 9}
                width={Math.max(2, (p95 / maxLat) * chartW)}
                height={7}
                rx={3.5}
                fill="var(--series-2)"
                onMouseMove={(e) =>
                  hover(e, `${name} — p95 ${Math.round(p95).toLocaleString()} ms`)
                }
              />
              <text
                x={labelW + (p95 / maxLat) * chartW + 6}
                y={y + 14}
                fontSize="11"
                fill="var(--text-muted)"
              >
                {Math.round(p95).toLocaleString()}
              </text>
              <rect
                x={labelW + chartW + 40}
                y={y + 2}
                width={Math.max(2, (tok / maxTok) * tokW)}
                height={10}
                rx={4}
                fill="var(--seq-250)"
                onMouseMove={(e) =>
                  hover(e, `${name} — ${Math.round(tok)} output tokens/query (mean)`)
                }
              />
            </g>
          );
        })}
        <line
          x1={labelW}
          y1={10}
          x2={labelW}
          y2={H - 6}
          stroke="var(--baseline)"
        />
        <line
          x1={labelW + chartW + 40}
          y1={10}
          x2={labelW + chartW + 40}
          y2={H - 6}
          stroke="var(--baseline)"
        />
      </svg>
      <Tooltip tip={tip} />
    </div>
  );
}
