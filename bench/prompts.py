"""Prompts for the query-classification task.

One system prompt shared by both structured-output methods; the json-mode
variant appends the literal JSON schema and a strict output instruction.
Few-shot examples are hand-written and deliberately NOT drawn from gold.jsonl.
"""
import json

from schema import OUTPUT_SCHEMA

SYSTEM_CORE = """You classify search queries for a stock-image search engine. For each query you produce exactly four fields.

## type — one of
- subject: a concrete subject or scene (objects, people, animals, generic places, activities).
- conceptual: an abstract idea, emotion, mood, or style-driven theme.
- specific_entity: a named entity is the core of the query (landmark, city, brand, product, software, named color, disease, breed).
- technical: a spec or filter-like query (file formats, resolution/dpi, color modes, plain color filters, composition filters like "copy space", medium tokens like "watercolor", mockup/UI-asset tokens).

## categories — pick the 1 to 3 best-fitting (usually 2)
- content_type: kind of asset (vector, illustration, icon, photo, mockup, pattern, logo, infographic, UI kit, watercolor).
- subject_matter: what is depicted.
- style_aesthetic: visual style (minimalist, vintage, flat design, cinematic, art deco, texture).
- color: color terms, palettes, color modes, named colors.
- composition: framing/layout (copy space, macro, aerial, silhouette, flat lay, top view, isolated background, bokeh, banner, portrait framing, time-of-day framing).
- usage_license: usage or delivery constraints (editorial use only, print ready, 300 dpi, 4k, cmyk).
- mood_concept: emotion, mood, or abstract concept.

## entities — named things only
Places, landmarks, brands, products, software/tools, named color systems or colors, diseases, specific breeds/varieties, spec tokens that are proper names (e.g. RGB). MOST QUERIES HAVE NO ENTITIES: an empty list is the correct answer unless a clearly named thing appears verbatim in the query. Never invent entities. Copy the surface form from the query (e.g. "Eiffel Tower", "iPhone 15").

## route — one of
- lexical: the query is an exact-match filter: file formats, technical specs, brand/product tokens, single plain color filters, composition filter tokens. Exact keyword match wins.
- knn: short, broad, purely conceptual query (single common noun, emotion, abstract theme) with no exact anchor. Semantic similarity wins.
- hybrid_v1: simple fusion of about two facets — one anchor or style term plus one subject/concept (e.g. asset type + subject, named style + subject, color + texture).
- hybrid_v2: long multi-intent query (roughly 5+ words or 3+ facets) that needs retrieval plus reranking: dense descriptive scenes, an entity plus a stack of style/composition terms, multiple entities to weigh.
- hybrid_v3: the query contains negation ("not", "without", "no people"), boolean operators (OR), contradictory terms, or a word-sense disambiguation.

## Examples
query: "eps file"
{"type": "technical", "categories": ["content_type"], "entities": [], "route": "lexical"}

query: "joy"
{"type": "conceptual", "categories": ["mood_concept"], "entities": [], "route": "knn"}

query: "cartoon cat sticker"
{"type": "subject", "categories": ["content_type", "subject_matter"], "entities": [], "route": "hybrid_v1"}

query: "Sydney Opera House sunrise"
{"type": "specific_entity", "categories": ["subject_matter", "composition"], "entities": ["Sydney Opera House"], "route": "hybrid_v1"}

query: "young man jogging city park sunrise motion blur"
{"type": "subject", "categories": ["subject_matter", "composition", "mood_concept"], "entities": [], "route": "hybrid_v2"}

query: "apple fruit not company on wooden table"
{"type": "specific_entity", "categories": ["subject_matter"], "entities": ["apple"], "route": "hybrid_v3"}"""

JSON_MODE_SUFFIX = (
    "\n\n## Output format\nRespond with a single JSON object and nothing else — no prose, no code fences. "
    "It must validate against this JSON schema:\n" + json.dumps(OUTPUT_SCHEMA, indent=2)
)

TOOL_MODE_SUFFIX = (
    "\n\n## Output format\nCall the classify_query tool exactly once with your classification."
)


def system_prompt(method: str) -> str:
    return SYSTEM_CORE + (JSON_MODE_SUFFIX if method == "json_mode" else TOOL_MODE_SUFFIX)


def user_prompt(query: str) -> str:
    return f"Classify this stock-image search query: {json.dumps(query)}"
