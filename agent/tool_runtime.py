"""Executes the small subset of tools verified safe to run from the hosted,
multi-tenant REST/WS API (see agent/agents.py's module docstring for why
this list is short and deliberate).

Each entry point here should have already been read end-to-end and
confirmed to: (a) resolve the caller's own Gemini key via the existing
tenant-aware `memory.config_manager.get_gemini_key()` chain rather than a
global one, (b) never write to the server's local filesystem, (c) never
shell out to a subprocess or a local browser.
"""

from __future__ import annotations

import asyncio


async def run_web_search(query: str) -> str:
    from actions.web_search import web_search

    return await asyncio.to_thread(web_search, {"query": query, "mode": "search"})


async def run_compare(items: list[str], aspect: str = "general") -> str:
    """Multi-source comparison, reusing web_search.py's existing `_compare`
    (already does one search per item and synthesizes a comparison —
    genuinely multi-source research, not a single query)."""
    from actions.web_search import web_search

    return await asyncio.to_thread(web_search, {"items": items, "mode": "compare", "aspect": aspect})
