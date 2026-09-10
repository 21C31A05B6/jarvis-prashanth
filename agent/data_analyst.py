"""Hosted CSV/data analysis and natural-language-to-SQL.

Operates on pasted CSV text, not an uploaded file or a live database
connection — no file-handling or DB-credential surface to secure. The SQL
assistant executes the generated query against a fresh, request-scoped,
in-memory SQLite database built only from the pasted data: it never touches
any real database, and the connection (and the data in it) is discarded the
moment the request finishes.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3

MAX_ROWS = 20_000


def _read_csv(csv_text: str):
    import pandas as pd

    frame = pd.read_csv(io.StringIO(csv_text))
    if len(frame) > MAX_ROWS:
        frame = frame.head(MAX_ROWS)
    return frame


def analyze_csv(csv_text: str) -> dict:
    """Real descriptive statistics per column, plus a suggested chart spec
    the frontend can render directly (labels/values/type — no image
    generation needed for a REST API response)."""
    frame = _read_csv(csv_text)

    columns = []
    numeric_columns = []
    for name in frame.columns:
        series = frame[name]
        is_numeric = str(series.dtype).startswith(("int", "float"))
        entry = {
            "name": str(name),
            "dtype": str(series.dtype),
            "non_null": int(series.notna().sum()),
            "null_count": int(series.isna().sum()),
        }
        if is_numeric:
            numeric_columns.append(str(name))
            described = series.describe()
            entry.update({
                "min": _safe_float(described.get("min")),
                "max": _safe_float(described.get("max")),
                "mean": _safe_float(described.get("mean")),
                "std": _safe_float(described.get("std")),
            })
        else:
            top = series.value_counts().head(5)
            entry["top_values"] = [{"value": str(k), "count": int(v)} for k, v in top.items()]
        columns.append(entry)

    chart = None
    if numeric_columns:
        target = numeric_columns[0]
        label_column = next((c for c in frame.columns if c not in numeric_columns), None)
        sample = frame.head(20)
        chart = {
            "chart_type": "bar",
            "title": f"{target} by {label_column or 'row'}",
            "labels": [str(v) for v in (sample[label_column] if label_column else sample.index)],
            "values": [_safe_float(v) or 0.0 for v in sample[target]],
        }

    return {
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "columns": columns,
        "chart": chart,
    }


def _safe_float(value) -> float | None:
    import math

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


async def query_data(csv_text: str, question: str, api_key: str) -> dict:
    frame = _read_csv(csv_text)

    connection = sqlite3.connect(":memory:")
    try:
        frame.to_sql("data", connection, index=False, if_exists="replace")
        schema = ", ".join(f"{col} ({dtype})" for col, dtype in zip(frame.columns, frame.dtypes.astype(str)))

        sql = await _generate_sql(schema, question, api_key)
        if not _is_read_only(sql):
            raise ValueError("Only read-only SELECT queries are allowed.")

        cursor = connection.execute(sql)
        column_names = [description[0] for description in cursor.description]
        rows = cursor.fetchmany(200)
        return {
            "sql": sql,
            "columns": column_names,
            "rows": [list(row) for row in rows],
        }
    finally:
        connection.close()


def _is_read_only(sql: str) -> bool:
    normalized = sql.strip().lower()
    if not normalized.startswith("select"):
        return False
    forbidden = ("insert", "update", "delete", "drop", "alter", "create", "attach", "pragma", ";--")
    return not any(keyword in normalized for keyword in forbidden)


async def _generate_sql(schema: str, question: str, api_key: str) -> str:
    import asyncio

    def call() -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=f"Table \"data\" has columns: {schema}\n\nQuestion: {question}",
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You translate natural-language questions into a single SQLite "
                    "SELECT query against a table named \"data\" with the given "
                    "columns. Respond with ONLY the SQL query, no explanation, no "
                    "markdown fences, no trailing semicolon-comment tricks. Never "
                    "generate anything other than a single read-only SELECT."
                ),
            ),
        )
        return str(response.text or "").strip()

    raw = await asyncio.to_thread(call)
    return re.sub(r"^```(?:sql)?|```$", "", raw, flags=re.MULTILINE).strip()
