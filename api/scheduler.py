"""Periodic scheduler: runs due scheduled tasks and reschedules recurring
ones.

Implemented as a lightweight tick (every ~30s, started from api/server.py's
lifespan) rather than a heavyweight job queue — appropriate for this app's
expected task volume. A tick that finds nothing due is a single cheap
indexed query (see api/repositories.py's due_scheduled_tasks).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("jarvis.scheduler")

RECURRENCE_DELTAS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),  # a simple, deliberate approximation
}


async def run_scheduler_tick(now: datetime | None = None) -> int:
    """Run every task whose scheduled_at has arrived. Returns how many ran."""
    from agent.task_runner import run_task_steps, summarize_task_status
    from api.repositories import add_task_record, create_notification, due_scheduled_tasks, update_task_record
    from core.tenant import tenant_scope

    now = now or datetime.now(timezone.utc)
    due = due_scheduled_tasks(now)

    for user_id, task in due:
        with tenant_scope(user_id):
            try:
                results = await run_task_steps(task["steps"])
                status = summarize_task_status(results)
                summary = "\n".join(
                    f"Step {r['step']} [{r['status']}]: {r['output'][:200]}" for r in results
                )
                update_task_record(
                    user_id, task["task_id"],
                    status=status, steps=json.dumps(results), result=summary,
                )
                create_notification(
                    user_id,
                    title=f"Scheduled task {status}: {task['goal'][:80]}",
                    body=summary[:2000],
                    kind="task",
                )
                _maybe_reschedule(user_id, task, results)
            except Exception:
                logger.exception("Scheduler tick failed for task %s", task.get("task_id"))
    return len(due)


def _maybe_reschedule(user_id: str, task: dict, results: list[dict]) -> None:
    from api.repositories import add_task_record, as_aware_utc

    delta = RECURRENCE_DELTAS.get(task.get("recurrence", "none"))
    if delta is None:
        return
    next_at = as_aware_utc(task["scheduled_at"]) + delta
    next_steps = [
        {
            **step,
            "status": "pending",
            "output": "",
            "attempts": 0,
            "approved": not step.get("requires_approval", False),
        }
        for step in results
    ]
    add_task_record(user_id, {
        "task_id": uuid.uuid4().hex,
        "goal": task["goal"],
        "status": "scheduled",
        "steps": json.dumps(next_steps),
        "scheduled_at": next_at,
        "recurrence": task["recurrence"],
    })
