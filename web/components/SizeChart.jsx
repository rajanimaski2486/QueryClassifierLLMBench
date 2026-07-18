"use client";

import { useState } from "react";
import { shortModel } from "./format";

/* Scatter: x = model size (log scale, B params), y = route macro-F1,
   bubble area = p95 latency. One hue; identity via direct labels. */

const PARAMS = {
  "meta/llama-3.1-8b-instruct": 8,
  "nvidia/nvidia-nemotron-nano-9b-v2": 9,
  "openai/gpt-oss-20b": 20,
  "nvidia/nemotron-3-nano-30b-a3b": 30,
  "nvidia/llama-3.3-nemotron-super-49b-v1.5": 49,
  "openai/gpt-oss-120b": 120,
  "qwen/qwen3.5-122b-a10b": 122,
};

const SHORT = {
  "meta/llama-3.1-8b-instruct": "llama-8b",
  "nvidia/nvidia-nemotron-nano-9b-v2": "nano-9b",
  "openai/gpt-oss-20b": "gpt-oss-20b",
  "nvidia/nemotron-3-nano-30b-a3b": "nano-30b",
  "nvidia/llama-3.3-nemotron-super-49b-v1.5": "super-49b",
  "openai/gpt-oss-120b": "gpt-oss-120b",
  "qwen/qwen3.5-122b-a10b": "qwen3.5-122b",
};

const W = 720;
const H = 420;
const PAD = { l: 56, r: 150, t: 16, b: 46 };

export default function SizeChart({ rows }) {
  const [tip, setTip] = useState(null);

  const pts = rows
    .filter((s) => PARAMS[s.model] && s.ops.latency_p95_ms)
    .map((s) => ({
      model: s.model,
      size: PARAMS[s.model],
      quality: s.route.macro_f1,
      p95: s.ops.latency_p95_ms,
      method: s.method,
    }));
  if (!pts.length) return null;

  const xMin = Math.log10(6);
  const xMax = Math.log10(180);
  const yMin = 0.3;
  const yMax = 0.85;
  const x = (size) =>
    PAD.l + ((Math.log10(size) - xMin) / (xMax - xMin)) * (W - PAD.l - PAD.r);
  const y = (q) => PAD.t + (1 - (q - yMin) / (yMax - yMin)) * (H - PAD.t - PAD.b);

  const maxP95 = Math.max(...pts.map((p) => p.p95));
  const r = (p95) => 6 + Math.sqrt(p95 / maxP95) * 22; // area ~ latency

  const xTicks = [8, 20, 50, 120];
  const yTicks = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8];

  return (
    <div className="card" onMouseLeave={() => setTip(null)}>
      <h2>Size vs quality vs latency</h2>
      <p className="desc">
        Each bubble is a model (best method). Horizontal: parameter count (log
        scale). Vertical: route macro-F1. Bubble area: p95 latency — bigger =
        slower. Size buys quality up to ~50B, but latency here is free-tier
        queue time, not compute: the two largest models are slow because of
        demand, not weights.
      </p>
      <svg width={W} height={H} role="img" aria-label="Model size versus route quality, bubble area shows p95 latency">
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} y1={y(t)} x2={W - PAD.r} y2={y(t)} stroke="var(--grid)" />
            <text x={PAD.l - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--text-muted)">
              {t.toFixed(1)}
            </text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={t} x={x(t)} y={H - PAD.b + 18} textAnchor="middle" fontSize="11" fill="var(--text-muted)">
            {t}B
          </text>
        ))}
        <line x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} stroke="var(--baseline)" />
        <text x={(PAD.l + W - PAD.r) / 2} y={H - 8} textAnchor="middle" fontSize="12" fill="var(--text-secondary)">
          model size (parameters, log scale)
        </text>
        <text
          x={14}
          y={(PAD.t + H - PAD.b) / 2}
          textAnchor="middle"
          fontSize="12"
          fill="var(--text-secondary)"
          transform={`rotate(-90 14 ${(PAD.t + H - PAD.b) / 2})`}
        >
          route macro-F1
        </text>
        {pts.map((p) => (
          <g key={p.model}>
            <circle
              cx={x(p.size)}
              cy={y(p.quality)}
              r={r(p.p95)}
              fill="var(--series-1)"
              fillOpacity="0.35"
              stroke="var(--series-1)"
              strokeWidth="2"
              onMouseMove={(e) =>
                setTip({
                  x: e.clientX,
                  y: e.clientY,
                  body: `${shortModel(p.model)} — ${p.size}B params · route macro-F1 ${p.quality.toFixed(3)} · p95 ${(p.p95 / 1000).toFixed(1)}s`,
                })
              }
            />
            <text
              x={x(p.size) + (x(p.size) > (PAD.l + W - PAD.r) / 2 ? -(r(p.p95) + 6) : r(p.p95) + 6)}
              y={y(p.quality) + 4}
              textAnchor={x(p.size) > (PAD.l + W - PAD.r) / 2 ? "end" : "start"}
              fontSize="11"
              fill="var(--text-primary)"
              pointerEvents="none"
            >
              {SHORT[p.model] ?? shortModel(p.model)}
            </text>
          </g>
        ))}
      </svg>
      <div className="legend">
        <span>
          <span className="swatch" style={{ background: "var(--series-1)", borderRadius: "50%" }} />
          bubble area = p95 latency (largest ≈ {(maxP95 / 1000).toFixed(0)}s)
        </span>
      </div>
      {tip && (
        <div className="tooltip" style={{ left: tip.x + 14, top: tip.y + 14 }}>
          {tip.body}
        </div>
      )}
    </div>
  );
}
