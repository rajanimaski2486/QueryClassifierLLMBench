"""Task schema: enums, JSON schema for model output, validation + lenient coercion.

The gold dataset (data/gold.jsonl) is frozen; nothing here rewrites it.
Models are asked to emit: {"type", "categories", "entities", "route"}.
"""
from __future__ import annotations

import json
import re

TYPES = ["subject", "conceptual", "specific_entity", "technical"]

CATEGORIES = [
    "content_type",
    "subject_matter",
    "style_aesthetic",
    "color",
    "composition",
    "usage_license",
    "mood_concept",
]

ROUTES = ["lexical", "knn", "hybrid_v1", "hybrid_v2", "hybrid_v3"]

ABSTAIN = "abstain"  # confusion-matrix bucket for missing/invalid route

# JSON schema shown to models (json mode) and used as tool parameters.
# Note: gold rows carry 1-3 categories, so minItems is 1 even though most
# queries take 2-3.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": TYPES},
        "categories": {
            "type": "array",
            "items": {"type": "string", "enum": CATEGORIES},
            "minItems": 1,
            "maxItems": 3,
        },
        "entities": {"type": "array", "items": {"type": "string"}},
        "route": {"type": "string", "enum": ROUTES},
    },
    "required": ["type", "categories", "entities", "route"],
    "additionalProperties": False,
}

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def extract_json(text: str):
    """Best-effort: pull the first JSON object out of model text.

    Returns (obj, json_valid). json_valid is True only when some JSON object
    was recovered at all.
    """
    if not text:
        return None, False
    text = _THINK_RE.sub("", text).strip()
    candidates = []
    m = _FENCE_RE.search(text)
    if m:
        candidates.append(m.group(1).strip())
    candidates.append(text)
    # first balanced {...} block
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : i + 1])
                    break
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj, True
        except Exception:
            continue
    return None, False


def validate_strict(obj) -> list[str]:
    """Errors against OUTPUT_SCHEMA. Empty list == schema-valid."""
    errs = []
    if not isinstance(obj, dict):
        return ["not an object"]
    for k in ("type", "categories", "entities", "route"):
        if k not in obj:
            errs.append(f"missing key: {k}")
    if obj.get("type") not in TYPES:
        errs.append(f"type not in enum: {obj.get('type')!r}")
    cats = obj.get("categories")
    if not isinstance(cats, list) or not (1 <= len(cats) <= 3) or any(c not in CATEGORIES for c in (cats or [])):
        errs.append(f"categories invalid: {cats!r}")
    ents = obj.get("entities")
    if not isinstance(ents, list) or any(not isinstance(e, str) for e in (ents or [])):
        errs.append(f"entities invalid: {ents!r}")
    if obj.get("route") not in ROUTES:
        errs.append(f"route not in enum: {obj.get('route')!r}")
    extra = set(obj) - {"type", "categories", "entities", "route"} if isinstance(obj, dict) else set()
    if extra:
        errs.append(f"extra keys: {sorted(extra)}")
    return errs


_KEY_ALIASES = {
    "type": ["type", "gold_type", "query_type"],
    "categories": ["categories", "gold_categories", "category"],
    "entities": ["entities", "gold_entities", "entity"],
    "route": ["route", "gold_route", "routing"],
}


def coerce(obj) -> dict:
    """Lenient normalization for scoring. Invalid fields become None/[].

    Scored independently per field so a bad route doesn't void good entities.
    """
    out = {"type": None, "categories": [], "entities": [], "route": None}
    if not isinstance(obj, dict):
        return out
    low = { (k.lower() if isinstance(k, str) else k): v for k, v in obj.items() }

    def pick(field):
        for a in _KEY_ALIASES[field]:
            if a in low:
                return low[a]
        return None

    t = pick("type")
    if isinstance(t, str) and t.strip().lower().replace(" ", "_") in TYPES:
        out["type"] = t.strip().lower().replace(" ", "_")

    cats = pick("categories")
    if isinstance(cats, str):
        cats = [cats]
    if isinstance(cats, list):
        seen = []
        for c in cats:
            if isinstance(c, str):
                cn = c.strip().lower().replace(" ", "_").replace("-", "_")
                if cn in CATEGORIES and cn not in seen:
                    seen.append(cn)
        out["categories"] = seen

    ents = pick("entities")
    if isinstance(ents, str):
        ents = [ents] if ents.strip() else []
    if isinstance(ents, list):
        out["entities"] = [e.strip() for e in ents if isinstance(e, str) and e.strip()]

    r = pick("route")
    if isinstance(r, str):
        rn = r.strip().lower().replace(" ", "_").replace("-", "_")
        if rn in ROUTES:
            out["route"] = rn
    return out


TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "classify_query",
        "description": (
            "Record the classification of a stock-image search query: its type, "
            "search categories, named entities, and retrieval route."
        ),
        "parameters": OUTPUT_SCHEMA,
    },
}
