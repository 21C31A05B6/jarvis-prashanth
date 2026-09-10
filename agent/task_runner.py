"""Executes the steps produced by `agent.planner.create_plan` from the
hosted API.

Two safety layers apply to every step, in order:

1. **Approval gate** (`flag_steps_needing_approval` / this module's
   `requires_approval`/`approved` step fields): any step that looks like it
   *changes* something in the world (sends, deletes, buys, posts, deploys,
   ...) is flagged and won't run until a human explicitly approves it via
   `POST /tasks/{id}/approve-step/{n}`. This is independent of whether the
   step is currently hosted-runnable at all — it's a real, general-purpose
   checkpoint that stays meaningful as more tools get wired for hosted
   execution over time.
2. **Hosted-capability gate** (`HOSTED_RUNNABLE_TOOLS`): only steps using a
   tool verified safe for headless server execution (today: `web_search`,
   via `agent.tool_runtime`) are actually run. Every other step is marked
   `skipped_desktop_only` with a clear reason — the same honesty principle
   as `agent/agents.py`'s `hosted_tool_names`: a step that can't really be
   executed here doesn't get to *look* like it succeeded.
"""

from __future__ import annotations

import asyncio

HOSTED_RUNNABLE_TOOLS = {"web_search"}

_WRITE_SHAPED_KEYWORDS = (
    "send", "delete", "remove", "purchase", "buy", "pay", "post", "publish",
    "deploy", "transfer", "cancel", "unsubscribe", "share", "upload",
    "install", "uninstall", "reply",
)

MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5


def flag_steps_needing_approval(steps: list[dict]) -> list[dict]:
    """Mark any step that looks like it changes something in the world as
    needing approval before it can run. Pure function — safe to call right
    after planning, before the plan is ever persisted or executed."""
    flagged = []
    for step in steps:
        haystack = f"{step.get('tool', '')} {step.get('description', '')}".lower()
        needs_approval = any(keyword in haystack for keyword in _WRITE_SHAPED_KEYWORDS)
        flagged.append({
            **step,
            "requires_approval": needs_approval,
            "approved": not needs_approval,
        })
    return flagged


async def run_task_steps(steps: list[dict]) -> list[dict]:
    from agent.tool_runtime import run_web_search

    results = []
    for step in steps:
        tool = step.get("tool", "")
        description = step.get("description", "")
        parameters = step.get("parameters") or {}
        entry = {
            "step": step.get("step"),
            "tool": tool,
            "description": description,
            "requires_approval": bool(step.get("requires_approval", False)),
            "approved": bool(step.get("approved", True)),
        }

        if entry["requires_approval"] and not entry["approved"]:
            entry["status"] = "awaiting_approval"
            entry["output"] = (
                "This step changes something (e.g. sends, deletes, or publishes "
                "something) and needs your approval before it runs. Approve it, "
                "then run the task again."
            )
            results.append(entry)
            continue

        if tool not in HOSTED_RUNNABLE_TOOLS:
            entry["status"] = "skipped_desktop_only"
            entry["output"] = (
                f"'{tool}' requires the JARVIS desktop app and wasn't run. "
                "Use the desktop app to execute this step, or ask a specialist "
                "agent for help with it directly."
            )
            results.append(entry)
            continue

        query = parameters.get("query") or description
        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                entry["output"] = await run_web_search(query)
                entry["status"] = "completed"
                entry["attempts"] = attempt
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
        if last_error is not None:
            entry["status"] = "failed"
            entry["output"] = f"Step failed after {MAX_ATTEMPTS} attempts: {last_error}"
            entry["attempts"] = MAX_ATTEMPTS
        results.append(entry)
    return results


def summarize_task_status(results: list[dict]) -> str:
    if not results:
        return "completed"
    statuses = {result["status"] for result in results}
    if statuses == {"completed"}:
        return "completed"
    if "awaiting_approval" in statuses and statuses <= {"awaiting_approval", "skipped_desktop_only"}:
        return "awaiting_approval"
    if "failed" in statuses:
        return "partial" if "completed" in statuses else "failed"
    if statuses == {"skipped_desktop_only"}:
        return "skipped_desktop_only"
    return "partial"
