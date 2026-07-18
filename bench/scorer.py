"""Score results.jsonl against data/gold.jsonl.

Per (model x method):
  type       accuracy + macro-F1
  categories multi-label micro/macro P/R/F1
  entities   entity-level F1 (exact + partial char-overlap), hallucination
             rate on empty-entity rows
  route      accuracy + macro-F1 + 6x6 confusion (5 routes + abstain)
  ops        p50/p95 latency, output tokens, credits, malformed rate
  adherence  json_valid_rate, schema_valid_rate, tool_call_rate, mode_used mix

Composite weights live in models.yaml (frozen but editable):
  composite = w_route*route_macro_f1
            + w_quality*mean(type_macro_f1, category_macro_f1, entity_exact_f1)
            + w_schema*schema_valid_rate
            + w_efficiency*efficiency
  efficiency = 1/(p95_latency_s * credits_per_query), normalized to [0,1]
               by the max across leaderboard rows.

Route macro-F1 is the primary quality metric: hybrid_v2 is over-represented
(23/77) so accuracy alone rewards over-predicting it; macro-F1 weights the
rare routes (hybrid_v3=9, knn=15) equally.

Usage: python bench/scorer.py [--results results.jsonl] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from statistics import median

sys.path.insert(0, os.path.dirname(__file__))
from schema import ABSTAIN, CATEGORIES, ROUTES, TYPES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTIAL_THRESHOLD = 0.5  # char-overlap ratio for a partial entity match


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def macro_f1(golds, preds, labels):
    """Macro-F1 over `labels`; predictions outside labels only hurt recall
    of the gold class (standard treatment of abstain/invalid)."""
    f1s = []
    per_label = {}
    for lab in labels:
        tp = sum(1 for g, p in zip(golds, preds) if g == lab and p == lab)
        fp = sum(1 for g, p in zip(golds, preds) if g != lab and p == lab)
        fn = sum(1 for g, p in zip(golds, preds) if g == lab and p != lab)
        p_, r_, f_ = prf(tp, fp, fn)
        per_label[lab] = {"precision": p_, "recall": r_, "f1": f_, "support": tp + fn}
        f1s.append(f_)
    return sum(f1s) / len(f1s) if f1s else 0.0, per_label


def norm_ent(e: str) -> str:
    return " ".join(e.casefold().split())


def char_overlap(a: str, b: str) -> float:
    m = SequenceMatcher(None, a, b).find_longest_match(0, len(a), 0, len(b))
    return m.size / max(len(a), len(b)) if a and b else 0.0


def match_entities(gold: list[str], pred: list[str]):
    """Greedy one-to-one matching. Returns (exact_tp, partial_tp).
    partial_tp includes exact matches (exact is a perfect overlap)."""
    g = [norm_ent(x) for x in gold]
    p = [norm_ent(x) for x in pred]
    exact_tp = 0
    g_left, p_left = list(g), list(p)
    for x in list(p_left):
        if x in g_left:
            exact_tp += 1
            g_left.remove(x)
            p_left.remove(x)
    partial_tp = exact_tp
    # among the leftovers, greedily pair best char-overlap >= threshold
    pairs = sorted(
        ((char_overlap(gg, pp), gi, pi) for gi, gg in enumerate(g_left) for pi, pp in enumerate(p_left)),
        reverse=True,
    )
    used_g, used_p = set(), set()
    for score, gi, pi in pairs:
        if score < PARTIAL_THRESHOLD:
            break
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        partial_tp += 1
    return exact_tp, partial_tp


def pct(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, round(q / 100 * (len(xs) - 1))))
    return xs[i]


def score_group(gold_by_id: dict, recs: list[dict]) -> dict:
    by_id = {r["id"]: r for r in recs}
    ids = [i for i in gold_by_id if i in by_id]
    n = len(ids)

    # ---- type
    t_gold = [gold_by_id[i]["gold_type"] for i in ids]
    t_pred = [(by_id[i]["parsed"].get("type") or ABSTAIN) for i in ids]
    type_acc = sum(g == p for g, p in zip(t_gold, t_pred)) / n if n else 0.0
    type_mf1, type_per = macro_f1(t_gold, t_pred, TYPES)

    # ---- categories (multi-label)
    cat_stats = {c: [0, 0, 0] for c in CATEGORIES}  # tp, fp, fn
    for i in ids:
        g = set(gold_by_id[i]["gold_categories"])
        p = set(by_id[i]["parsed"].get("categories") or [])
        for c in CATEGORIES:
            if c in g and c in p:
                cat_stats[c][0] += 1
            elif c in p:
                cat_stats[c][1] += 1
            elif c in g:
                cat_stats[c][2] += 1
    tp = sum(v[0] for v in cat_stats.values())
    fp = sum(v[1] for v in cat_stats.values())
    fn = sum(v[2] for v in cat_stats.values())
    cat_micro_p, cat_micro_r, cat_micro_f1 = prf(tp, fp, fn)
    per_cat = {c: dict(zip(("precision", "recall", "f1"), prf(*v))) | {"support": v[0] + v[2]} for c, v in cat_stats.items()}
    cat_macro_p = sum(v["precision"] for v in per_cat.values()) / len(CATEGORIES)
    cat_macro_r = sum(v["recall"] for v in per_cat.values()) / len(CATEGORIES)
    cat_macro_f1 = sum(v["f1"] for v in per_cat.values()) / len(CATEGORIES)

    # ---- entities
    ex_tp = pa_tp = e_fp_ex = e_fn_ex = e_fp_pa = e_fn_pa = 0
    empty_rows = halluc_rows = 0
    for i in ids:
        g = gold_by_id[i]["gold_entities"]
        p = by_id[i]["parsed"].get("entities") or []
        ex, pa = match_entities(g, p)
        ex_tp += ex
        pa_tp += pa
        e_fp_ex += len(p) - ex
        e_fn_ex += len(g) - ex
        e_fp_pa += len(p) - pa
        e_fn_pa += len(g) - pa
        if not g:
            empty_rows += 1
            if p:
                halluc_rows += 1
    ent_exact = dict(zip(("precision", "recall", "f1"), prf(ex_tp, e_fp_ex, e_fn_ex)))
    ent_partial = dict(zip(("precision", "recall", "f1"), prf(pa_tp, e_fp_pa, e_fn_pa)))
    halluc_rate = halluc_rows / empty_rows if empty_rows else 0.0

    # ---- route
    r_gold = [gold_by_id[i]["gold_route"] for i in ids]
    r_pred = [(by_id[i]["parsed"].get("route") or ABSTAIN) for i in ids]
    route_acc = sum(g == p for g, p in zip(r_gold, r_pred)) / n if n else 0.0
    route_mf1, route_per = macro_f1(r_gold, r_pred, ROUTES)
    axes = ROUTES + [ABSTAIN]
    confusion = [[0] * len(axes) for _ in axes]
    for g, p in zip(r_gold, r_pred):
        confusion[axes.index(g)][axes.index(p if p in axes else ABSTAIN)] += 1

    # ---- ops + adherence
    lats = [by_id[i]["latency_ms"] for i in ids if by_id[i].get("latency_ms")]
    outs = [by_id[i]["output_tokens"] for i in ids if isinstance(by_id[i].get("output_tokens"), int)]
    credits = [by_id[i].get("credits", 1) for i in ids]
    modes = defaultdict(int)
    for i in ids:
        modes[by_id[i].get("mode_used") or ("tool" if by_id[i]["method"] == "tool_call" else "?")] += 1

    return {
        "n": n,
        "type": {"accuracy": type_acc, "macro_f1": type_mf1, "per_label": type_per},
        "categories": {
            "micro": {"precision": cat_micro_p, "recall": cat_micro_r, "f1": cat_micro_f1},
            "macro": {"precision": cat_macro_p, "recall": cat_macro_r, "f1": cat_macro_f1},
            "per_label": per_cat,
        },
        "entities": {
            "exact": ent_exact,
            "partial": ent_partial,
            "hallucination_rate": halluc_rate,
            "empty_gold_rows": empty_rows,
        },
        "route": {
            "accuracy": route_acc,
            "macro_f1": route_mf1,
            "per_label": route_per,
            "confusion_labels": axes,
            "confusion": confusion,
        },
        "ops": {
            "latency_p50_ms": pct(lats, 50),
            "latency_p95_ms": pct(lats, 95),
            "output_tokens_mean": sum(outs) / len(outs) if outs else None,
            "credits_total": sum(credits),
            "credits_per_query": sum(credits) / n if n else None,
            "malformed_rate": sum(1 for i in ids if by_id[i].get("malformed")) / n if n else 0.0,
            "error_rate": sum(1 for i in ids if by_id[i].get("error")) / n if n else 0.0,
        },
        "adherence": {
            "json_valid_rate": sum(1 for i in ids if by_id[i].get("json_valid")) / n if n else 0.0,
            "schema_valid_rate": sum(1 for i in ids if by_id[i].get("schema_valid")) / n if n else 0.0,
            "tool_call_rate": sum(1 for i in ids if by_id[i].get("tool_called")) / n if n else 0.0,
            "modes_used": dict(modes),
        },
    }


def build_report(results_path: str) -> dict:
    import yaml

    with open(os.path.join(ROOT, "bench", "models.yaml")) as f:
        cfg = yaml.safe_load(f)
    weights = cfg["composite_weights"]

    gold_by_id = {}
    with open(os.path.join(ROOT, "data", "gold.jsonl")) as f:
        for line in f:
            if line.strip():
                g = json.loads(line)
                gold_by_id[g["id"]] = g

    roster = {m["id"] for m in cfg["models"]}
    groups = defaultdict(list)
    with open(results_path) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                if r["model"] in roster:  # swapped-out models stay in the raw file only
                    groups[(r["model"], r["method"])].append(r)

    tiers = {m["id"]: m["tier"] for m in cfg["models"]}
    rows = []
    for (model, method), recs in sorted(groups.items()):
        s = score_group(gold_by_id, recs)
        s["model"] = model
        s["method"] = method
        s["tier"] = tiers.get(model, "?")
        rows.append(s)

    # efficiency normalized across rows
    raw_eff = {}
    for s in rows:
        p95 = s["ops"]["latency_p95_ms"]
        cpq = s["ops"]["credits_per_query"]
        raw_eff[(s["model"], s["method"])] = 1.0 / ((p95 / 1000.0) * cpq) if p95 and cpq else 0.0
    max_eff = max(raw_eff.values(), default=0.0)
    for s in rows:
        eff = raw_eff[(s["model"], s["method"])] / max_eff if max_eff else 0.0
        s["efficiency"] = eff
        quality = (s["type"]["macro_f1"] + s["categories"]["macro"]["f1"] + s["entities"]["exact"]["f1"]) / 3
        s["composite"] = (
            weights["route_macro_f1"] * s["route"]["macro_f1"]
            + weights["quality_mean"] * quality
            + weights["schema_valid_rate"] * s["adherence"]["schema_valid_rate"]
            + weights["efficiency"] * eff
        )
    rows.sort(key=lambda s: s["composite"], reverse=True)
    return {"weights": weights, "leaderboard": rows, "gold_n": len(gold_by_id)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(ROOT, "results.jsonl"))
    ap.add_argument("--json", help="also dump full report to this path")
    args = ap.parse_args()

    report = build_report(args.results)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)

    print(f"{'model':44} {'method':9} {'comp':>6} {'routeF1':>7} {'routeAcc':>8} "
          f"{'typeF1':>6} {'catF1':>6} {'entF1':>6} {'halluc':>6} {'schema':>6} {'p95ms':>7}")
    for s in report["leaderboard"]:
        print(f"{s['model']:44} {s['method']:9} {s['composite']:6.3f} {s['route']['macro_f1']:7.3f} "
              f"{s['route']['accuracy']:8.3f} {s['type']['macro_f1']:6.3f} "
              f"{s['categories']['macro']['f1']:6.3f} {s['entities']['exact']['f1']:6.3f} "
              f"{s['entities']['hallucination_rate']:6.2f} {s['adherence']['schema_valid_rate']:6.2f} "
              f"{s['ops']['latency_p95_ms'] or 0:7.0f}")


if __name__ == "__main__":
    main()
