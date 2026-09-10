"""Workflow recording: capture a sequence of tool calls during a live
desktop session and persist them as a named, replayable workflow.

Recording and replay only make sense on the desktop app — the steps are
desktop tool calls (open_app, computer_control, file_controller, etc.).
Listing and deleting previously recorded workflows also work from the
hosted API for visibility/management, reusing the same tenant-aware
local-file-vs-database storage split as memory/memory_manager.py.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from threading import Lock

from memory.memory_manager import _hosted_mode, get_base_dir

WORKFLOWS_PATH = get_base_dir() / "memory" / "workflows.json"
_lock = Lock()

# Recording your own start/stop/list/replay commands would nest a workflow
# inside itself; never capture the recorder's own control tool.
_EXCLUDED_TOOLS = {"workflow_control"}


class WorkflowRecorder:
    """Lives on a JarvisLive engine instance; tracks an in-progress
    recording (if any) and appends each successful tool call to it."""

    def __init__(self):
        self._active_name: str | None = None
        self._steps: list[dict] = []

    @property
    def is_recording(self) -> bool:
        return self._active_name is not None

    def start(self, name: str) -> str:
        self._active_name = (name or "").strip() or "Untitled workflow"
        self._steps = []
        return (
            f"Recording workflow '{self._active_name}'. Every action you take "
            "will be captured until you say stop."
        )

    def record_step(self, tool: str, parameters: dict) -> None:
        if not self.is_recording or tool in _EXCLUDED_TOOLS:
            return
        self._steps.append({"tool": tool, "parameters": dict(parameters or {})})

    def stop(self) -> str:
        if not self.is_recording:
            return "No workflow is currently being recorded."
        name, steps = self._active_name, self._steps
        self._active_name, self._steps = None, []
        if not steps:
            return f"Stopped recording '{name}', but no actions were captured — nothing was saved."
        save_workflow(name, steps)
        return f"Saved workflow '{name}' with {len(steps)} step(s). Say \"replay {name}\" to run it again."


def load_workflows() -> list[dict]:
    from core.tenant import get_current_user_id

    user_id = get_current_user_id()
    if user_id:
        from api.repositories import list_workflows

        return [
            {
                "id": row.id,
                "name": row.name,
                "steps": json.loads(row.steps or "[]"),
                "created_at": row.created_at.isoformat(),
            }
            for row in list_workflows(user_id)
        ]
    if _hosted_mode():
        raise RuntimeError(
            "Hosted API request executed without a tenant context; refusing to "
            "read local workflow storage to avoid cross-tenant data leaks."
        )
    if not WORKFLOWS_PATH.exists():
        return []
    with _lock:
        try:
            data = json.loads(WORKFLOWS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []


def save_workflow(name: str, steps: list[dict]) -> None:
    from core.tenant import get_current_user_id

    user_id = get_current_user_id()
    if user_id:
        from api.repositories import create_workflow

        create_workflow(user_id, name, steps)
        return
    if _hosted_mode():
        raise RuntimeError(
            "Hosted API request executed without a tenant context; refusing to "
            "write local workflow storage to avoid cross-tenant data leaks."
        )
    workflows = load_workflows()
    workflows.append({
        "id": uuid.uuid4().hex,
        "name": name,
        "steps": steps,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    WORKFLOWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        WORKFLOWS_PATH.write_text(json.dumps(workflows, indent=2, ensure_ascii=False), encoding="utf-8")


def find_workflow(name_or_id: str) -> dict | None:
    needle = (name_or_id or "").strip().lower()
    for workflow in load_workflows():
        if workflow["id"] == name_or_id or workflow["name"].strip().lower() == needle:
            return workflow
    return None


def delete_workflow_by_name(name_or_id: str) -> bool:
    from core.tenant import get_current_user_id

    workflow = find_workflow(name_or_id)
    if not workflow:
        return False
    user_id = get_current_user_id()
    if user_id:
        from api.repositories import delete_workflow

        return delete_workflow(user_id, workflow["id"])
    remaining = [w for w in load_workflows() if w["id"] != workflow["id"]]
    with _lock:
        WORKFLOWS_PATH.write_text(json.dumps(remaining, indent=2, ensure_ascii=False), encoding="utf-8")
    return True
