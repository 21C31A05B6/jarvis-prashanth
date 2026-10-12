"""Routes a chat message to the agent best equipped to handle it.

The primary router is a deterministic keyword-scored classifier: fast, free,
fully unit-testable, and predictable — the same message always routes the
same way, which matters for a feature people will come to rely on. It is
intentionally not an LLM call: routing is on the hot path of every chat
message, and a wrong LLM classification is harder to reason about than a
wrong keyword match.
"""

from __future__ import annotations

import re

from agent.agents import AGENTS

# Ordered by specificity: more specific/technical keywords are checked
# first so e.g. "debug this SQL query" scores coding higher than data.
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "planning": (
        "plan", "planning", "roadmap", "step by step", "break down",
        "break this down", "steps to", "outline a plan", "multi-step",
    ),
    "coding": (
        "code", "function", "bug", "debug", "error", "exception", "stack trace",
        "refactor", "python", "javascript", "typescript", "compile", "script",
        "repository", "repo", "pull request", "pr ", "unit test", "api endpoint",
    ),
    "email": (
        "email", "e-mail", "gmail", "inbox", "draft a reply", "reply to",
        "compose a message to", "cc ", "bcc ",
    ),
    "computer": (
        "open the app", "open app", "close the app", "click on", "take a screenshot",
        "screenshot", "my screen", "on my screen", "mouse", "keyboard", "volume",
        "brightness", "wallpaper", "organize my files", "rename the file",
    ),
    "data": (
        "csv", "spreadsheet", "excel", "dataset", "data set", "column", "columns",
        "pivot table", "chart this", "visualize this data", "analyze this file",
        "analyze the data",
    ),
    "research": (
        "research", "search the web", "look up", "find information", "compare",
        "latest news", "summarize this article", "summarize this video",
        "what is", "who is", "sources", "citations",
    ),
    "hermes": (
        "hermes", "subagent", "subagents", "parallel work", "mixture of agents",
        "moa", "docker container", "docker sandbox", "isolated docker",
        "remote execution", "daytona", "modal sandbox", "vercel sandbox",
        "mcp server", "cronjob", "self-improving", "skill generation",
    ),
}

_COMPILED: dict[str, list[re.Pattern]] = {
    agent_id: [re.compile(re.escape(keyword), re.IGNORECASE) for keyword in keywords]
    for agent_id, keywords in _KEYWORDS.items()
}


def route_message(text: str) -> str:
    """Return the id of the agent best suited to handle `text`, or
    "general" if nothing scores a confident match."""
    if not text or not text.strip():
        return "general"

    scores: dict[str, int] = {agent_id: 0 for agent_id in _COMPILED}
    for agent_id, patterns in _COMPILED.items():
        for pattern in patterns:
            if pattern.search(text):
                scores[agent_id] += 1

    best_agent = max(scores, key=lambda agent_id: scores[agent_id])
    if scores[best_agent] == 0:
        return "general"
    return best_agent


def is_known_agent(agent_id: str) -> bool:
    return agent_id == "general" or agent_id in AGENTS
