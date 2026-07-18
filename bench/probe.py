"""Probe NVIDIA NIM models for structured-output support.

For each candidate model, tries:
  1. response_format={"type": "json_object"}  (JSON mode)
  2. tools + forced tool_choice               (tool calling)

Prints a support matrix used to fill in models.yaml `methods`.
Run:  .venv/bin/python bench/probe.py
"""
import json
import os
import sys
import time

import httpx

BASE = "https://integrate.api.nvidia.com/v1"
KEY = os.environ["NVIDIA_API_KEY"]

CANDIDATES = [
    "meta/llama-3.1-8b-instruct",
    "mistralai/mistral-7b-instruct-v0.3",
    "google/gemma-3-12b-it",
    "nvidia/llama-3.1-nemotron-nano-8b-v1",
    "nvidia/nemotron-3-nano-30b-a3b",
    "meta/llama-3.3-70b-instruct",
    "qwen/qwen3-next-80b-a3b-instruct",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
]

PROMPT = 'Classify the query "red rose" as JSON: {"type": "subject|technical", "entities": []}. Reply with JSON only.'

TOOL = {
    "type": "function",
    "function": {
        "name": "classify_query",
        "description": "Classify a stock image search query",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["subject", "technical"]},
                "entities": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["type", "entities"],
        },
    },
}


def call(client, model, extra):
    messages = [{"role": "user", "content": PROMPT}]
    if os.environ.get("PROBE_SYSTEM"):
        messages.insert(0, {"role": "system", "content": os.environ["PROBE_SYSTEM"]})
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": int(os.environ.get("PROBE_MAX_TOKENS", "300")),
        "temperature": 0.0,
        **extra,
    }
    t0 = time.time()
    try:
        r = client.post(f"{BASE}/chat/completions", json=body, timeout=90)
    except Exception as e:
        return {"ok": False, "err": f"transport:{e}", "ms": int((time.time() - t0) * 1000)}
    ms = int((time.time() - t0) * 1000)
    if r.status_code != 200:
        return {"ok": False, "err": f"{r.status_code}:{r.text[:160]}", "ms": ms}
    d = r.json()
    msg = d["choices"][0]["message"]
    out = {"ok": True, "ms": ms, "finish": d["choices"][0].get("finish_reason")}
    if msg.get("tool_calls"):
        args = msg["tool_calls"][0]["function"]["arguments"]
        try:
            json.loads(args)
            out["tool_json"] = True
        except Exception:
            out["tool_json"] = False
        out["mode"] = "tool_call"
    else:
        content = msg.get("content") or ""
        out["mode"] = "content"
        try:
            json.loads(content.strip().removeprefix("```json").removesuffix("```").strip())
            out["content_json"] = True
        except Exception:
            out["content_json"] = False
            out["snippet"] = content[:120].replace("\n", " ")
    return out


def main():
    candidates = sys.argv[1:] or CANDIDATES
    results = {}
    with httpx.Client(headers={"Authorization": f"Bearer {KEY}"}) as client:
        for m in candidates:
            row = {}
            row["json_mode"] = call(client, m, {"response_format": {"type": "json_object"}})
            time.sleep(1.6)
            row["tool_forced"] = call(
                client, m,
                {"tools": [TOOL], "tool_choice": {"type": "function", "function": {"name": "classify_query"}}},
            )
            time.sleep(1.6)
            if not row["tool_forced"]["ok"]:
                row["tool_auto"] = call(client, m, {"tools": [TOOL], "tool_choice": "auto"})
                time.sleep(1.6)
            results[m] = row
            print(f"== {m}")
            for k, v in row.items():
                print(f"   {k}: {json.dumps(v)[:220]}")
            sys.stdout.flush()
    path = os.path.join(os.path.dirname(__file__), "..", "probe_results.json")
    merged = {}
    if os.path.exists(path):
        with open(path) as f:
            merged = json.load(f)
    merged.update(results)
    with open(path, "w") as f:
        json.dump(merged, f, indent=2)


if __name__ == "__main__":
    main()
