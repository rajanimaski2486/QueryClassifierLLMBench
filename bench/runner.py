"""Async benchmark runner.

Calls every (model x method x query) combination against the NVIDIA
OpenAI-compatible endpoint, respecting a global RPM budget, and appends one
telemetry record per combination to results.jsonl. Safe to re-run: existing
(model, method, id) triples are skipped, so an interrupted run resumes.

Usage:
  python bench/runner.py                 # full run
  python bench/runner.py --limit 3       # smoke test on first 3 queries
  python bench/runner.py --models meta/llama-3.1-8b-instruct --methods json_mode
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time

import httpx
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from prompts import system_prompt, user_prompt  # noqa: E402
from schema import TOOL_DEF, coerce, extract_json, validate_strict  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 4 attempts x 150s timeout bounds a hopeless call at ~11 min; against the
# free tier's queued serverless endpoints more retries only stall the run.
MAX_ATTEMPTS = 4


class RateLimiter:
    """Global sliding-window limiter: at most `rpm` request starts per 60s."""

    def __init__(self, rpm: int):
        self.rpm = rpm
        self.stamps: list[float] = []
        self.lock = asyncio.Lock()

    async def acquire(self):
        while True:
            async with self.lock:
                now = time.monotonic()
                self.stamps = [t for t in self.stamps if now - t < 60]
                if len(self.stamps) < self.rpm:
                    self.stamps.append(now)
                    return
                wait = 60 - (now - self.stamps[0]) + 0.05
            await asyncio.sleep(wait)


def load_config():
    with open(os.path.join(ROOT, "bench", "models.yaml")) as f:
        return yaml.safe_load(f)


def load_gold():
    rows = []
    with open(os.path.join(ROOT, "data", "gold.jsonl")) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_body(model_cfg: dict, method: str, query: str, json_fallback: bool) -> dict:
    sys_text = system_prompt(method)
    if model_cfg.get("system_prefix"):
        sys_text = model_cfg["system_prefix"] + "\n" + sys_text
    body = {
        "model": model_cfg["id"],
        "messages": [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": user_prompt(query)},
        ],
        "temperature": 0.0,
        "max_tokens": model_cfg.get("max_tokens", 2048),
    }
    if model_cfg.get("extra_body"):
        body.update(model_cfg["extra_body"])
    if method == "json_mode" and not json_fallback:
        body["response_format"] = {"type": "json_object"}
    elif method == "tool_call":
        body["tools"] = [TOOL_DEF]
        body["tool_choice"] = (
            {"type": "function", "function": {"name": "classify_query"}}
            if model_cfg.get("tool_choice", "forced") == "forced"
            else "auto"
        )
    return body


def _is_response_format_rejection(status: int, text: str) -> bool:
    return status in (400, 422) and "response_format" in text


async def run_one(client, limiter, cfg, model_cfg, method, row) -> dict:
    rec = {
        "model": model_cfg["id"],
        "tier": model_cfg["tier"],
        "method": method,
        "id": row["id"],
        "query": row["query"],
    }
    json_fallback = False
    attempts = 0
    err = None
    resp_json = None
    latency_ms = None

    while attempts < MAX_ATTEMPTS:
        attempts += 1
        body = build_body(model_cfg, method, row["query"], json_fallback)
        await limiter.acquire()
        t0 = time.monotonic()
        try:
            r = await client.post("/chat/completions", json=body)
        except Exception as e:
            err = f"transport:{type(e).__name__}:{e}"
            await asyncio.sleep(min(2 ** attempts, 30) + random.random())
            continue
        latency_ms = int((time.monotonic() - t0) * 1000)
        if r.status_code == 200:
            resp_json = r.json()
            err = None
            # some NIM models accept response_format but then emit degenerate
            # output (endless whitespace until length) — detect and redo the
            # call as a strict-prompt parse
            if method == "json_mode" and not json_fallback:
                choice = (resp_json.get("choices") or [{}])[0]
                content = (choice.get("message") or {}).get("content") or ""
                if choice.get("finish_reason") == "length" and extract_json(content)[0] is None:
                    json_fallback = True
                    resp_json = None
                    continue
            break
        text = r.text[:300]
        err = f"http {r.status_code}: {text}"
        if method == "json_mode" and not json_fallback and _is_response_format_rejection(r.status_code, text):
            json_fallback = True  # server rejected response_format; strict-prompt parse instead
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            retry_after = r.headers.get("retry-after")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2 ** attempts, 45)
            await asyncio.sleep(delay + random.random())
            continue
        break  # non-retryable 4xx

    rec["attempts"] = attempts
    rec["credits"] = attempts  # free tier: 1 credit per request made
    rec["latency_ms"] = latency_ms
    rec["error"] = err

    if method == "json_mode":
        rec["mode_used"] = "strict_prompt" if json_fallback else "json_object"

    raw_text, tool_called = None, False
    usage = {}
    if resp_json:
        usage = resp_json.get("usage") or {}
        choice = (resp_json.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        rec["finish_reason"] = choice.get("finish_reason")
        if msg.get("tool_calls"):
            tool_called = True
            raw_text = msg["tool_calls"][0].get("function", {}).get("arguments")
        else:
            raw_text = msg.get("content")

    rec["tool_called"] = tool_called
    rec["raw"] = raw_text
    rec["prompt_tokens"] = usage.get("prompt_tokens")
    rec["output_tokens"] = usage.get("completion_tokens")

    obj, json_valid = extract_json(raw_text) if raw_text else (None, False)
    rec["json_valid"] = json_valid
    rec["schema_errors"] = validate_strict(obj) if json_valid else ["no json"]
    rec["schema_valid"] = json_valid and not rec["schema_errors"]
    rec["parsed"] = coerce(obj)
    rec["malformed"] = not json_valid
    return rec


def existing_keys(out_path: str) -> set:
    done = set()
    if os.path.exists(out_path):
        with open(out_path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add((r["model"], r["method"], r["id"]))
                except Exception:
                    continue
    return done


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only the first N gold rows")
    ap.add_argument("--ids", help="comma-separated query ids")
    ap.add_argument("--models", help="comma-separated model ids (default: all in models.yaml)")
    ap.add_argument("--methods", help="comma-separated subset of json_mode,tool_call")
    ap.add_argument("--out", default=os.path.join(ROOT, "results.jsonl"))
    args = ap.parse_args()

    cfg = load_config()
    gold = load_gold()
    if args.ids:
        want = set(args.ids.split(","))
        gold = [g for g in gold if g["id"] in want]
    if args.limit:
        gold = gold[: args.limit]

    models = cfg["models"]
    if args.models:
        want = set(args.models.split(","))
        models = [m for m in models if m["id"] in want]

    jobs = []
    for m in models:
        methods = m.get("methods", ["json_mode", "tool_call"])
        if args.methods:
            methods = [x for x in methods if x in args.methods.split(",")]
        for method in methods:
            for row in gold:
                jobs.append((m, method, row))

    done = existing_keys(args.out)
    jobs = [(m, meth, row) for m, meth, row in jobs if (m["id"], meth, row["id"]) not in done]
    # interleave models so one slow endpoint can't hog every concurrency slot
    random.Random(0).shuffle(jobs)
    print(f"{len(jobs)} calls to make ({len(done)} already done), rpm={cfg['rate_limit']['rpm']}")

    limiter = RateLimiter(cfg["rate_limit"]["rpm"])
    sem = asyncio.Semaphore(cfg["rate_limit"].get("concurrency", 4))
    key = os.environ["NVIDIA_API_KEY"]
    out_lock = asyncio.Lock()
    n_done = 0

    async with httpx.AsyncClient(
        base_url=cfg["base_url"],
        headers={"Authorization": f"Bearer {key}"},
        timeout=httpx.Timeout(240, connect=15),
    ) as client:

        async def worker(m, method, row):
            nonlocal n_done
            async with sem:
                rec = await run_one(client, limiter, cfg, m, method, row)
            async with out_lock:
                with open(args.out, "a") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_done += 1
                flag = "ok " if rec["schema_valid"] else ("ERR" if rec["error"] else "bad")
                print(f"[{n_done}/{len(jobs)}] {flag} {m['id']} {method} {row['id']} "
                      f"{rec['latency_ms']}ms", flush=True)

        await asyncio.gather(*(worker(m, meth, row) for m, meth, row in jobs))

    print("done ->", args.out)


if __name__ == "__main__":
    asyncio.run(main())
