"""PostgreSQL persistence for important memories and notes.

Connects to the configured Neon / PostgreSQL database and asynchronously persists
any facts, notes, or statements marked as important by the user.
"""

from __future__ import annotations

import logging
import os
import threading
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
    # Ensure SSL mode if connecting to Neon without explicit params
    if "neon.tech" in url and "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def _init_table() -> None:
    """Ensure the important_memories table exists in PostgreSQL."""
    try:
        import psycopg

        url = get_database_url()
        with psycopg.connect(url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
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
                conn.commit()
    except Exception as e:
        print(f"[Postgres Store] [Warning] Init table: {e}")


# Run table init once lazily
_table_initialized = False
_init_lock = threading.Lock()


def ensure_table_initialized() -> None:
    global _table_initialized
    if not _table_initialized:
        with _init_lock:
            if not _table_initialized:
                _init_table()
                _table_initialized = True


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
            ensure_table_initialized()
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
        ensure_table_initialized()
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

