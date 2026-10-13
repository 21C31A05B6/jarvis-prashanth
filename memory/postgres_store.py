"""PostgreSQL persistence and conversational analysis for JARVIS OS.

Connects to the configured Neon / PostgreSQL database and:
1. Logs complete A-to-Z conversations (user speech, text, JARVIS speech, tool calls & results).
2. Analyzes overall conversation patterns, user habits, and operational boundaries.
3. Enforces that any task given to JARVIS operates strictly within the analyzed range and constraints.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("jarvis.postgres_store")

DEFAULT_DATABASE_URL = (
    "postgresql://neondb_owner:npg_aO9iK0jICrdM@ep-young-glade-aem4imaf-pooler.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require"
)


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        url = DEFAULT_DATABASE_URL
    if "neon.tech" in url and "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def _init_tables() -> None:
    """Ensure all required tables and indexes exist in NeonDB PostgreSQL."""
    try:
        import psycopg

        url = get_database_url()
        with psycopg.connect(url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                # 1. Important memories
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS important_memories (
                        id SERIAL PRIMARY KEY,
                        category VARCHAR(64) DEFAULT 'important',
                        key VARCHAR(120),
                        content TEXT NOT NULL,
                        raw_utterance TEXT,
                        source VARCHAR(32) DEFAULT 'jarvis',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS ix_important_memories_cat_key 
                        ON important_memories (category, key);
                    """
                )

                # 2. Complete A-to-Z conversation logging
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jarvis_conversations (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(64) NOT NULL,
                        role VARCHAR(32) NOT NULL,
                        content TEXT NOT NULL,
                        tool_name VARCHAR(128) DEFAULT '',
                        tool_args TEXT DEFAULT '',
                        tool_result TEXT DEFAULT '',
                        source VARCHAR(32) DEFAULT 'desktop',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS ix_jarvis_conv_sess ON jarvis_conversations (session_id, created_at);
                    CREATE INDEX IF NOT EXISTS ix_jarvis_conv_role ON jarvis_conversations (role);
                    """
                )

                # 3. Analyzed insights, learned preferences & operational range constraints
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jarvis_analysis_insights (
                        id SERIAL PRIMARY KEY,
                        insight_type VARCHAR(64) NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        description TEXT NOT NULL,
                        source VARCHAR(32) DEFAULT 'auto_analysis',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS ix_jarvis_insights_type ON jarvis_analysis_insights (insight_type);
                    """
                )
                conn.commit()
    except Exception as e:
        print(f"[Postgres Store] [Warning] Init tables: {e}")


_tables_initialized = False
_init_lock = threading.Lock()


def ensure_tables_initialized() -> None:
    global _tables_initialized
    if not _tables_initialized:
        with _init_lock:
            if not _tables_initialized:
                _init_tables()
                _tables_initialized = True


# ---------------------------------------------------------------------------
# Background Async Queue for Non-Blocking Conversation Logging
# ---------------------------------------------------------------------------

_log_queue: queue.Queue[dict[str, Any]] = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()


def _db_writer_worker():
    import psycopg

    last_analysis_time = time.time()
    turns_since_analysis = 0

    while True:
        try:
            item = _log_queue.get()
            if item is None:
                break

            items_to_insert = [item]
            # Drain any pending items in queue to batch write
            while not _log_queue.empty() and len(items_to_insert) < 25:
                try:
                    next_item = _log_queue.get_nowait()
                    if next_item is None:
                        break
                    items_to_insert.append(next_item)
                except queue.Empty:
                    break

            ensure_tables_initialized()
            url = get_database_url()
            with psycopg.connect(url, connect_timeout=10) as conn:
                with conn.cursor() as cur:
                    for record in items_to_insert:
                        cur.execute(
                            """
                            INSERT INTO jarvis_conversations 
                            (session_id, role, content, tool_name, tool_args, tool_result, source, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                record["session_id"][:64],
                                record["role"][:32],
                                record["content"],
                                record.get("tool_name", "")[:128],
                                record.get("tool_args", ""),
                                record.get("tool_result", ""),
                                record.get("source", "desktop")[:32],
                                record.get("created_at", datetime.now(timezone.utc)),
                            ),
                        )
                    conn.commit()

            turns_since_analysis += len(items_to_insert)
            # Run analysis every 10 turns or every 60 seconds if new turns occurred
            now = time.time()
            if turns_since_analysis >= 10 or (turns_since_analysis > 0 and (now - last_analysis_time) > 60):
                try:
                    _perform_conversation_analysis_sync()
                    last_analysis_time = now
                    turns_since_analysis = 0
                except Exception as ex:
                    print(f"[Postgres Store] [Warning] Analysis worker error: {ex}")

        except Exception as exc:
            print(f"[Postgres Store] [Error] DB Writer loop error: {exc}")
            time.sleep(2)


def _ensure_worker():
    global _worker_started
    if not _worker_started:
        with _worker_lock:
            if not _worker_started:
                t = threading.Thread(target=_db_writer_worker, daemon=True, name="PostgresStoreWorker")
                t.start()
                _worker_started = True


def log_conversation_turn(
    session_id: str,
    role: str,
    content: str,
    tool_name: str = "",
    tool_args: str = "",
    tool_result: str = "",
    source: str = "desktop",
) -> None:
    """Non-blocking queueing of conversation turns into NeonDB PostgreSQL."""
    if not content and not tool_name:
        return
    _ensure_worker()
    _log_queue.put({
        "session_id": session_id or "default_session",
        "role": role,
        "content": str(content or "").strip(),
        "tool_name": str(tool_name or "").strip(),
        "tool_args": str(tool_args or "").strip(),
        "tool_result": str(tool_result or "").strip()[:5000],  # cap long outputs
        "source": source,
        "created_at": datetime.now(timezone.utc),
    })


# ---------------------------------------------------------------------------
# Important Item Persistence
# ---------------------------------------------------------------------------

def store_important_item(
    content: str,
    key: str = "",
    category: str = "important",
    raw_utterance: str = "",
    source: str = "jarvis",
) -> None:
    """Store an important note/memory into PostgreSQL in a background thread."""
    if not content or not content.strip():
        return

    content_clean = content.strip()
    key_clean = (key or "note").strip()[:120]
    category_clean = (category or "important").strip()[:64]
    raw_clean = (raw_utterance or "").strip()

    def _worker():
        try:
            ensure_tables_initialized()
            import psycopg

            url = get_database_url()
            with psycopg.connect(url, connect_timeout=10) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO important_memories (category, key, content, raw_utterance, source, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            category_clean,
                            key_clean,
                            content_clean,
                            raw_clean,
                            source,
                            datetime.now(timezone.utc),
                            datetime.now(timezone.utc),
                        ),
                    )
                    conn.commit()
            print(f"[Postgres Store] [Saved to Neon DB] [{category_clean}/{key_clean}] {content_clean[:80]}")
        except Exception as exc:
            print(f"[Postgres Store] [Error] Failed to save to PostgreSQL: {exc}")

    threading.Thread(target=_worker, daemon=True).start()


def fetch_important_memories(limit: int = 20) -> list[dict[str, Any]]:
    """Retrieve recent important memories from the PostgreSQL database."""
    try:
        ensure_tables_initialized()
        import psycopg

        url = get_database_url()
        with psycopg.connect(url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, category, key, content, raw_utterance, source, created_at
                    FROM important_memories
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                results = []
                for row in rows:
                    results.append({
                        "id": row[0],
                        "category": row[1],
                        "key": row[2],
                        "content": row[3],
                        "raw_utterance": row[4],
                        "source": row[5],
                        "created_at": str(row[6]),
                    })
                return results
    except Exception as exc:
        print(f"[Postgres Store] [Warning] Fetch error: {exc}")
        return []


def fetch_recent_conversations(limit: int = 50) -> list[dict[str, Any]]:
    """Retrieve recent conversation logs from NeonDB PostgreSQL."""
    try:
        ensure_tables_initialized()
        import psycopg

        url = get_database_url()
        with psycopg.connect(url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, session_id, role, content, tool_name, tool_args, tool_result, created_at
                    FROM jarvis_conversations
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                results = []
                for row in rows:
                    results.append({
                        "id": row[0],
                        "session_id": row[1],
                        "role": row[2],
                        "content": row[3],
                        "tool_name": row[4],
                        "tool_args": row[5],
                        "tool_result": row[6],
                        "created_at": str(row[7]),
                    })
                results.reverse()  # chronological order
                return results
    except Exception as exc:
        print(f"[Postgres Store] [Warning] Fetch conversation error: {exc}")
        return []


# ---------------------------------------------------------------------------
# Conversation Analysis & Operational Range Memory
# ---------------------------------------------------------------------------

def _perform_conversation_analysis_sync() -> None:
    """Analyze recent conversations stored in NeonDB and extract operational ranges."""
    conversations = fetch_recent_conversations(limit=60)
    if not conversations:
        return

    import psycopg

    user_statements = [c["content"] for c in conversations if c["role"] == "user"]
    all_text = " \n ".join(user_statements)

    # Detect user constraints and instructions
    ranges: list[tuple[str, str, str]] = []

    # 1. Installation & Environment Range
    if re.search(r"\b(manual\s*install|no\s*auto\s*install|manual\s*setup)\b", all_text, re.I):
        ranges.append((
            "operational_range",
            "Installation Policy",
            "Maintain manual installation mode only. Do not auto-install or run hidden background install scripts without explicit consent.",
        ))

    # 2. Window / Process Spawning Range
    if re.search(r"\b(cmd|command\s*prompt|terminal|flashing|opening\s*and\s*closing)\b", all_text, re.I):
        ranges.append((
            "operational_range",
            "Process Execution Policy",
            "Background commands and tasks must always run hidden without flashing command prompt or terminal windows (CREATE_NO_WINDOW).",
        ))

    # 3. Task Workflow Range
    if re.search(r"\b(todo|task\s*scheduler|remember\s*me|auto\s*execute)\b", all_text, re.I):
        ranges.append((
            "operational_range",
            "Task Execution & Notification Range",
            "Tasks designated for JARVIS execution should run autonomously at the due time. Tasks designated as 'Remember Me' must alert the user directly aloud if active/online, or dispatch via email to prashanthpogula24@gmail.com if offline.",
        ))

    # 4. Scope and Workspace Range
    workspace_path = os.getcwd().replace("\\", "/")
    ranges.append((
        "operational_range",
        "Primary Workspace Boundary",
        f"Primary project operational boundary is locked to: '{workspace_path}'. Never modify system files or external directories outside user project boundaries.",
    ))

    # 5. Database Logging Range
    ranges.append((
        "operational_range",
        "NeonDB Persistent Record",
        "All conversations and task outcomes are logged continuously to NeonDB PostgreSQL for complete auditability and continuous context.",
    ))

    url = get_database_url()
    with psycopg.connect(url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            for insight_type, title, description in ranges:
                cur.execute(
                    """
                    SELECT id FROM jarvis_analysis_insights 
                    WHERE insight_type = %s AND title = %s
                    LIMIT 1
                    """,
                    (insight_type, title),
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        """
                        UPDATE jarvis_analysis_insights 
                        SET description = %s, updated_at = %s 
                        WHERE id = %s
                        """,
                        (description, datetime.now(timezone.utc), existing[0]),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO jarvis_analysis_insights (insight_type, title, description, source, created_at, updated_at)
                        VALUES (%s, %s, %s, 'auto_analysis', %s, %s)
                        """,
                        (insight_type, title, description, datetime.now(timezone.utc), datetime.now(timezone.utc)),
                    )
            conn.commit()


def trigger_conversation_analysis() -> None:
    """Trigger background analysis of conversation history in NeonDB."""
    threading.Thread(target=_perform_conversation_analysis_sync, daemon=True, name="ConvAnalysisThread").start()


def get_operational_range_context() -> str:
    """Retrieve the formatted operational range and boundaries for Gemini prompt injection."""
    try:
        ensure_tables_initialized()
        import psycopg

        url = get_database_url()
        with psycopg.connect(url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT title, description 
                    FROM jarvis_analysis_insights
                    WHERE insight_type = 'operational_range'
                    ORDER BY id ASC
                    """
                )
                rows = cur.fetchall()
                if not rows:
                    # Seed baseline if empty
                    _perform_conversation_analysis_sync()
                    return (
                        "[USER OPERATIONAL RANGE & STRICT CONSTRAINTS (FROM NEONDB POSTGRESQL)]\n"
                        "- Operational Scope: Respect user project directory and manual control policies.\n"
                        "- Notification Scope: Speak aloud if online; email to prashanthpogula24@gmail.com if offline.\n"
                        "- Process Scope: No visible flashing cmd windows; execute smoothly in background.\n"
                        "CRITICAL: Execute all requested tasks strictly within these learned boundaries only.\n"
                    )

                lines = [
                    "[USER OPERATIONAL RANGE & STRICT CONSTRAINTS (FROM NEONDB POSTGRESQL)]",
                    "The following constraints have been analyzed from the user's conversation history in NeonDB. "
                    "You must perform all actions strictly within this operational range:",
                ]
                for title, desc in rows:
                    lines.append(f"- **{title}**: {desc}")
                lines.append("CRITICAL: Do NOT exceed these boundaries or perform actions outside this specified range.")
                return "\n".join(lines) + "\n"
    except Exception as exc:
        print(f"[Postgres Store] [Warning] Operational range context fetch error: {exc}")
        return ""


def is_task_within_range(task_text: str, command: str = "") -> tuple[bool, str]:
    """Check if a given task or shell command is within the user's operational range."""
    combined = f"{task_text} {command}".lower()

    # Reject dangerous system destruction outside range
    dangerous_patterns = [
        r"\bformat\s+[c-z]:",
        r"\bdel\s+/[sfq]\s+c:\\windows",
        r"\brmdir\s+/[sq]\s+c:\\windows",
        r"\bdrop\s+database\b",
        r"\brm\s+-rf\s+/(etc|boot|sys|var)",
    ]
    for pat in dangerous_patterns:
        if re.search(pat, combined):
            return False, f"Action blocked: matches prohibited command pattern outside allowed operational range ({pat})"

    return True, "Within allowed operational range."
