"""Export scored results to web/public/results.json for the static dashboard.

Bundles: leaderboard (with composite + all metrics), per-query drill-down
(gold labels + every model's parsed output and telemetry), and run metadata.
No API keys or raw HTTP details leave this machine's results.jsonl except
model text outputs.

Usage: python bench/export.py [--results results.jsonl]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from scorer import build_report  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(ROOT, "results.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "public", "results.json"))
    args = ap.parse_args()

    report = build_report(args.results)

    gold = []
    with open(os.path.join(ROOT, "data", "gold.jsonl")) as f:
        for line in f:
            if line.strip():
                g = json.loads(line)
                gold.append({k: g[k] for k in (
                    "id", "query", "len_band", "anchor", "entity_load", "ambiguity",
                    "gold_type", "gold_categories", "gold_entities", "gold_route",
                )})  # label_note is human-only: not exported

    roster = {f"{s['model']}|{s['method']}" for s in report["leaderboard"]}
    per_query = defaultdict(dict)
    with open(args.results) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if f"{r['model']}|{r['method']}" not in roster:
                continue
            per_query[r["id"]][f"{r['model']}|{r['method']}"] = {
                "parsed": r.get("parsed"),
                "schema_valid": r.get("schema_valid"),
                "json_valid": r.get("json_valid"),
                "tool_called": r.get("tool_called"),
                "mode_used": r.get("mode_used"),
                "latency_ms": r.get("latency_ms"),
                "output_tokens": r.get("output_tokens"),
                "error": (r.get("error") or "")[:200] or None,
            }

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "weights": report["weights"],
        "leaderboard": report["leaderboard"],
        "gold": gold,
        "per_query": per_query,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"wrote {args.out} ({os.path.getsize(args.out)//1024} KiB, "
          f"{len(report['leaderboard'])} leaderboard rows, {len(gold)} queries)")


if __name__ == "__main__":
    main()
