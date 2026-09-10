"""Small synchronous repositories used by API routes and legacy engine facades."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update

from .database import SessionLocal
from .models import (
    AnswerCacheEntry,
    AuditLog,
    CalendarEvent,
    ChatMessage,
    MeetingNote,
    MemoryEntry,
    Notification,
    TaskRecord,
    Todo,
    UsageEvent,
    UserConfig,
    Workflow,
)


MEMORY_CATEGORIES = (
    "identity", "preferences", "projects", "relationships", "wishes", "notes", "short_term"
)


def load_user_memory(user_id: str) -> dict:
    result = {category: {} for category in MEMORY_CATEGORIES}
    with SessionLocal() as db:
        rows = db.scalars(
            select(MemoryEntry).where(MemoryEntry.user_id == user_id)
        ).all()
    for row in rows:
        result.setdefault(row.category, {})[row.key] = {
            "value": row.value,
            "updated": row.updated_at.date().isoformat(),
        }
    return result


def replace_user_memory(user_id: str, memory: dict) -> None:
    with SessionLocal.begin() as db:
        db.execute(delete(MemoryEntry).where(MemoryEntry.user_id == user_id))
        for category, items in memory.items():
            if not isinstance(items, dict):
                continue
            for key, entry in items.items():
                value = entry.get("value") if isinstance(entry, dict) else entry
                if value is None:
                    continue
                db.add(MemoryEntry(
                    user_id=user_id,
                    category=str(category),
                    key=str(key),
                    value=str(value),
                ))


def load_user_config(user_id: str, namespace: str = "general") -> dict:
    with SessionLocal() as db:
        rows = db.scalars(select(UserConfig).where(
            UserConfig.user_id == user_id,
            UserConfig.namespace == namespace,
        )).all()
    return {row.key: row.value for row in rows}


def save_user_config(user_id: str, values: dict, namespace: str = "general") -> None:
    with SessionLocal.begin() as db:
        for key, value in values.items():
            row = db.scalar(select(UserConfig).where(
                UserConfig.user_id == user_id,
                UserConfig.namespace == namespace,
                UserConfig.key == str(key),
            ))
            if row:
                row.value = value
            else:
                db.add(UserConfig(
                    user_id=user_id,
                    namespace=namespace,
                    key=str(key),
                    value=value,
                ))


def add_chat_message(user_id: str, role: str, content: str, agent: str = "general") -> ChatMessage:
    with SessionLocal.begin() as db:
        row = ChatMessage(user_id=user_id, role=role, content=content, agent=agent)
        db.add(row)
    return row


def recent_chat_messages(user_id: str, limit: int = 20) -> list[ChatMessage]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        ).all()
        return list(reversed(rows))


def paginated_chat_messages(
    user_id: str, limit: int = 50, before: datetime | None = None
) -> tuple[list[ChatMessage], datetime | None]:
    """Cursor-paginate a user's chat history, oldest-first within the page.

    Unlike ``recent_chat_messages`` (a small fixed window used to seed a
    live prompt), this is meant for a UI that needs to page back through
    the full conversation. Pass ``next_before`` from the previous page as
    ``before`` to keep going.
    """
    limit = max(1, min(limit, 200))
    with SessionLocal() as db:
        query = select(ChatMessage).where(ChatMessage.user_id == user_id)
        if before is not None:
            query = query.where(ChatMessage.created_at < before)
        rows = db.scalars(
            query.order_by(ChatMessage.created_at.desc()).limit(limit)
        ).all()
    rows = list(reversed(rows))
    next_before = rows[0].created_at if len(rows) == limit else None
    return rows, next_before


def as_aware_utc(value: datetime) -> datetime:
    """SQLite silently drops tzinfo on DateTime(timezone=True) columns
    (Postgres does not), so a value read back can be naive even though it
    was stored as UTC. Normalize before comparing to an aware datetime."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def prune_short_term_memory(ttl_hours: int = 24) -> int:
    """Delete short_term memory entries older than `ttl_hours` since their
    last update, across all users. Called by the periodic retention job
    (see api/server.py's _retention_loop)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, ttl_hours))
    with SessionLocal.begin() as db:
        result = db.execute(
            delete(MemoryEntry).where(
                MemoryEntry.category == "short_term",
                MemoryEntry.updated_at < cutoff,
            )
        )
        return result.rowcount


def add_task_record(user_id: str, payload: dict) -> dict:
    with SessionLocal.begin() as db:
        row = TaskRecord(user_id=user_id, **payload)
        db.add(row)
    return task_record_dict(row)


def get_task_record(user_id: str, task_id: str) -> dict | None:
    with SessionLocal() as db:
        row = db.scalar(
            select(TaskRecord)
            .where(TaskRecord.user_id == user_id, TaskRecord.task_id == task_id)
            .order_by(TaskRecord.created_at.desc())
        )
    return task_record_dict(row) if row else None


def update_task_record(user_id: str, task_id: str, **fields) -> dict | None:
    with SessionLocal.begin() as db:
        row = db.scalar(
            select(TaskRecord)
            .where(TaskRecord.user_id == user_id, TaskRecord.task_id == task_id)
            .order_by(TaskRecord.created_at.desc())
        )
        if row is None:
            return None
        for key, value in fields.items():
            setattr(row, key, value)
        db.flush()
        return task_record_dict(row)


def task_history(user_id: str, limit: int, status: str | None = None) -> list[dict]:
    with SessionLocal() as db:
        query = select(TaskRecord).where(TaskRecord.user_id == user_id)
        if status:
            query = query.where(TaskRecord.status == status)
        rows = db.scalars(query.order_by(TaskRecord.created_at.desc()).limit(limit)).all()
    return [task_record_dict(row) for row in reversed(rows)]


def task_record_dict(row: TaskRecord) -> dict:
    return {
        "task_id": row.task_id,
        "goal": row.goal,
        "status": row.status,
        "result": row.result,
        "error": row.error,
        "saved_file": row.saved_file,
        "steps": json.loads(row.steps or "[]"),
        "scheduled_at": row.scheduled_at,
        "recurrence": row.recurrence,
        "timestamp": row.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def due_scheduled_tasks(now: datetime) -> list[tuple[str, dict]]:
    """Every user's tasks whose scheduled_at has arrived and haven't been
    run yet. Used by the scheduler tick (api/scheduler.py)."""
    with SessionLocal() as db:
        rows = db.scalars(
            select(TaskRecord).where(
                TaskRecord.status == "scheduled",
                TaskRecord.scheduled_at.is_not(None),
                TaskRecord.scheduled_at <= now,
            )
        ).all()
    return [(row.user_id, task_record_dict(row)) for row in rows]


def get_cached(user_id: str, normalized_question: str) -> str | None:
    with SessionLocal.begin() as db:
        row = db.scalar(select(AnswerCacheEntry).where(
            AnswerCacheEntry.user_id == user_id,
            AnswerCacheEntry.normalized_question == normalized_question,
        ))
        if not row:
            return None
        row.hits += 1
        row.updated_at = datetime.now(row.updated_at.tzinfo)
        return row.answer


def put_cached(user_id: str, normalized_question: str, question: str, answer: str) -> None:
    with SessionLocal.begin() as db:
        row = db.scalar(select(AnswerCacheEntry).where(
            AnswerCacheEntry.user_id == user_id,
            AnswerCacheEntry.normalized_question == normalized_question,
        ))
        if row:
            row.question = question
            row.answer = answer
        else:
            db.add(AnswerCacheEntry(
                user_id=user_id,
                normalized_question=normalized_question,
                question=question,
                answer=answer,
            ))


def purge_retention(retention_days: int = 90) -> dict[str, int]:
    """Delete chat/task/answer-cache rows older than ``retention_days``.

    Called by the periodic retention job (see api/server.py's lifespan and
    scripts/retention_cleanup.py) so these tables don't grow without bound.
    Users' memory (long-term facts) and secrets are intentionally excluded:
    those are small, bounded, and meant to persist indefinitely.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
    deleted = {"chat_messages": 0, "task_records": 0, "answer_cache_entries": 0}
    with SessionLocal.begin() as db:
        deleted["chat_messages"] = db.execute(
            delete(ChatMessage).where(ChatMessage.created_at < cutoff)
        ).rowcount
        deleted["task_records"] = db.execute(
            delete(TaskRecord).where(TaskRecord.created_at < cutoff)
        ).rowcount
        deleted["answer_cache_entries"] = db.execute(
            delete(AnswerCacheEntry).where(AnswerCacheEntry.updated_at < cutoff)
        ).rowcount
    return deleted


def create_workflow(user_id: str, name: str, steps: list[dict]) -> Workflow:
    with SessionLocal.begin() as db:
        row = Workflow(user_id=user_id, name=name, steps=json.dumps(steps))
        db.add(row)
        db.flush()
        db.refresh(row)
        db.expunge(row)
    return row


def list_workflows(user_id: str, limit: int = 50) -> list[Workflow]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(Workflow)
            .where(Workflow.user_id == user_id)
            .order_by(Workflow.created_at.desc())
            .limit(limit)
        ).all()
        for row in rows:
            db.expunge(row)
    return rows


def get_workflow(user_id: str, workflow_id: str) -> Workflow | None:
    with SessionLocal() as db:
        row = db.scalar(select(Workflow).where(Workflow.user_id == user_id, Workflow.id == workflow_id))
        if row:
            db.expunge(row)
    return row


def delete_workflow(user_id: str, workflow_id: str) -> bool:
    with SessionLocal.begin() as db:
        result = db.execute(
            delete(Workflow).where(Workflow.user_id == user_id, Workflow.id == workflow_id)
        )
        return result.rowcount > 0


# --- Todos -------------------------------------------------------------

def create_todo(user_id: str, text: str, due_at: datetime | None = None) -> Todo:
    with SessionLocal.begin() as db:
        row = Todo(user_id=user_id, text=text, due_at=due_at)
        db.add(row)
        db.flush()
        db.refresh(row)
        db.expunge(row)
    return row


def list_todos(user_id: str, done: bool | None = None) -> list[Todo]:
    with SessionLocal() as db:
        query = select(Todo).where(Todo.user_id == user_id)
        if done is not None:
            query = query.where(Todo.done == done)
        rows = db.scalars(query.order_by(Todo.created_at.desc())).all()
        for row in rows:
            db.expunge(row)
    return rows


def set_todo_done(user_id: str, todo_id: str, done: bool) -> Todo | None:
    with SessionLocal.begin() as db:
        row = db.scalar(select(Todo).where(Todo.user_id == user_id, Todo.id == todo_id))
        if not row:
            return None
        row.done = done
        db.flush()
        db.refresh(row)
        db.expunge(row)
    return row


def delete_todo(user_id: str, todo_id: str) -> bool:
    with SessionLocal.begin() as db:
        result = db.execute(delete(Todo).where(Todo.user_id == user_id, Todo.id == todo_id))
        return result.rowcount > 0


# --- Calendar ------------------------------------------------------------

def create_calendar_event(user_id: str, title: str, start_at: datetime, end_at: datetime | None, notes: str = "") -> CalendarEvent:
    with SessionLocal.begin() as db:
        row = CalendarEvent(user_id=user_id, title=title, start_at=start_at, end_at=end_at, notes=notes)
        db.add(row)
        db.flush()
        db.refresh(row)
        db.expunge(row)
    return row


def list_calendar_events(user_id: str, start: datetime | None = None, end: datetime | None = None) -> list[CalendarEvent]:
    with SessionLocal() as db:
        query = select(CalendarEvent).where(CalendarEvent.user_id == user_id)
        if start is not None:
            query = query.where(CalendarEvent.start_at >= start)
        if end is not None:
            query = query.where(CalendarEvent.start_at <= end)
        rows = db.scalars(query.order_by(CalendarEvent.start_at.asc())).all()
        for row in rows:
            db.expunge(row)
    return rows


def delete_calendar_event(user_id: str, event_id: str) -> bool:
    with SessionLocal.begin() as db:
        result = db.execute(delete(CalendarEvent).where(CalendarEvent.user_id == user_id, CalendarEvent.id == event_id))
        return result.rowcount > 0


# --- Notifications ---------------------------------------------------------

def create_notification(user_id: str, title: str, body: str = "", kind: str = "info") -> Notification:
    with SessionLocal.begin() as db:
        row = Notification(user_id=user_id, title=title, body=body, kind=kind)
        db.add(row)
        db.flush()
        db.refresh(row)
        db.expunge(row)
    return row


def list_notifications(user_id: str, unread_only: bool = False, limit: int = 50) -> list[Notification]:
    with SessionLocal() as db:
        query = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            query = query.where(Notification.read_at.is_(None))
        rows = db.scalars(query.order_by(Notification.created_at.desc()).limit(limit)).all()
        for row in rows:
            db.expunge(row)
    return rows


def mark_notification_read(user_id: str, notification_id: str) -> bool:
    with SessionLocal.begin() as db:
        result = db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.id == notification_id, Notification.read_at.is_(None))
            .values(read_at=datetime.now(timezone.utc))
        )
        return result.rowcount > 0


def delete_notification(user_id: str, notification_id: str) -> bool:
    with SessionLocal.begin() as db:
        result = db.execute(delete(Notification).where(Notification.user_id == user_id, Notification.id == notification_id))
        return result.rowcount > 0


# --- Meeting Notes -----------------------------------------------------------

def create_meeting_note(user_id: str, title: str, summary: str, action_items: list[str]) -> MeetingNote:
    with SessionLocal.begin() as db:
        row = MeetingNote(user_id=user_id, title=title, summary=summary, action_items=json.dumps(action_items))
        db.add(row)
        db.flush()
        db.refresh(row)
        db.expunge(row)
    return row


def list_meeting_notes(user_id: str, limit: int = 20) -> list[MeetingNote]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(MeetingNote).where(MeetingNote.user_id == user_id)
            .order_by(MeetingNote.created_at.desc()).limit(limit)
        ).all()
        for row in rows:
            db.expunge(row)
    return rows


# --- Security audit log & suspicious activity ------------------------------

def log_audit_event(user_id: str | None, event_type: str, detail: str = "", ip_address: str = "") -> None:
    with SessionLocal.begin() as db:
        db.add(AuditLog(user_id=user_id, event_type=event_type, detail=detail[:2000], ip_address=ip_address[:64]))


def list_audit_log(user_id: str, limit: int = 100) -> list[AuditLog]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(AuditLog).where(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc()).limit(limit)
        ).all()
        for row in rows:
            db.expunge(row)
    return rows


def count_recent_failed_logins(email: str, minutes: int = 15) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with SessionLocal() as db:
        return db.scalar(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.event_type == "login_failed",
                AuditLog.detail == email,
                AuditLog.created_at >= cutoff,
            )
        ) or 0


def has_prior_successful_login_from_ip(user_id: str, ip_address: str) -> bool:
    if not ip_address:
        return True  # unknown IP (e.g. behind a proxy without forwarding) — don't false-positive
    with SessionLocal() as db:
        row = db.scalar(
            select(AuditLog).where(
                AuditLog.user_id == user_id,
                AuditLog.event_type == "login_success",
                AuditLog.ip_address == ip_address,
            )
        )
    return row is not None


# --- AI usage tracking -----------------------------------------------------

def log_usage_event(user_id: str, endpoint: str, input_chars: int = 0, output_chars: int = 0) -> None:
    with SessionLocal.begin() as db:
        db.add(UsageEvent(user_id=user_id, endpoint=endpoint, input_chars=input_chars, output_chars=output_chars))


def usage_summary(user_id: str, days: int = 30) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with SessionLocal() as db:
        rows = db.execute(
            select(UsageEvent.endpoint, func.count(), func.sum(UsageEvent.input_chars), func.sum(UsageEvent.output_chars))
            .where(UsageEvent.user_id == user_id, UsageEvent.created_at >= cutoff)
            .group_by(UsageEvent.endpoint)
        ).all()
    by_endpoint = {
        endpoint: {"calls": count, "input_chars": int(input_sum or 0), "output_chars": int(output_sum or 0)}
        for endpoint, count, input_sum, output_sum in rows
    }
    return {
        "total_calls": sum(v["calls"] for v in by_endpoint.values()),
        "by_endpoint": by_endpoint,
        "days": days,
    }
