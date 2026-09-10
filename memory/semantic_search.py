"""Semantic search over a user's memory entries.

Ranks stored memory (across all categories) by relevance to a natural-
language query using Gemini text embeddings + cosine similarity. If the
embedding call fails for any reason (bad key, quota, network), falls back
to a simple keyword/substring relevance score rather than erroring out —
the same defensive pattern `actions/web_search.py` already uses for its
Gemini → DuckDuckGo fallback.
"""

from __future__ import annotations

import math
import re

EMBEDDING_MODEL = "gemini-embedding-001"


def _flatten(memory: dict) -> list[dict]:
    flat = []
    for category, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            value = entry.get("value") if isinstance(entry, dict) else entry
            if not value:
                continue
            flat.append({"category": category, "key": key, "value": str(value)})
    return flat


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_score(query: str, text: str) -> float:
    query_terms = set(re.findall(r"\w+", query.lower()))
    text_terms = set(re.findall(r"\w+", text.lower()))
    if not query_terms:
        return 0.0
    return len(query_terms & text_terms) / len(query_terms)


def _embed(client, texts: list[str]) -> list[list[float]]:
    response = client.models.embed_content(model=EMBEDDING_MODEL, contents=texts)
    return [list(embedding.values) for embedding in response.embeddings]


def semantic_search_memory(memory: dict, query: str, api_key: str, top_k: int = 5) -> list[dict]:
    """Return up to `top_k` memory entries most relevant to `query`, each as
    `{category, key, value, score}`, highest score first."""
    entries = _flatten(memory)
    if not entries or not query.strip():
        return []

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        texts = [query] + [f"{entry['category']}/{entry['key']}: {entry['value']}" for entry in entries]
        vectors = _embed(client, texts)
        query_vector, entry_vectors = vectors[0], vectors[1:]
        for entry, vector in zip(entries, entry_vectors):
            entry["score"] = round(_cosine(query_vector, vector), 4)
    except Exception:
        for entry in entries:
            entry["score"] = round(_keyword_score(query, f"{entry['key']} {entry['value']}"), 4)

    entries.sort(key=lambda entry: entry["score"], reverse=True)
    return [entry for entry in entries if entry["score"] > 0][:top_k]
