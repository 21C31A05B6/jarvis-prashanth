"""Hosted developer assistant tools.

Deliberately text-generation-only: no code execution, no subprocess, no
filesystem writes. `actions/code_helper.py`'s `run`/`build` actions do
execute code, which is why they're desktop-only (see agent/agents.py's
module docstring) — running arbitrary user code on a shared hosted server
is a real remote-code-execution risk. These functions generate advice,
tests, and command suggestions as text for the user (or the desktop app) to
act on, never execute anything themselves.
"""

from __future__ import annotations

import json
import re


async def debug_code(code: str, error: str, language: str, api_key: str) -> dict:
    payload = await _synthesize_json(
        api_key,
        system_instruction=(
            "You are a debugging assistant. Given source code and an error "
            "message, identify the root cause and propose a fix. Respond with "
            'ONLY a JSON object: {"explanation": "...", "fix": "..."}. '
            "explanation should describe the root cause in 2-4 sentences. fix "
            "should be the corrected code (the full snippet, not just a diff). "
            "No other text, no markdown fences."
        ),
        prompt=f"Language: {language}\n\nCode:\n{code}\n\nError:\n{error}",
    )
    return {
        "explanation": str(payload.get("explanation", "")).strip(),
        "fix": str(payload.get("fix", "")).strip(),
    }


async def generate_tests(code: str, language: str, api_key: str) -> dict:
    payload = await _synthesize_json(
        api_key,
        system_instruction=(
            "You write unit tests. Given source code, generate a complete, "
            "runnable test file covering the normal cases, edge cases, and "
            'error cases. Respond with ONLY a JSON object: {"tests": "...", '
            '"framework": "..."}. Use the standard test framework for the '
            "language (pytest for Python, jest for JS/TS, etc). No other "
            "text, no markdown fences."
        ),
        prompt=f"Language: {language}\n\nCode to test:\n{code}",
    )
    return {
        "tests": str(payload.get("tests", "")).strip(),
        "framework": str(payload.get("framework", "")).strip(),
    }


async def review_project(description: str, api_key: str) -> dict:
    payload = await _synthesize_json(
        api_key,
        system_instruction=(
            "You are a senior engineer doing an architecture/code review. "
            "Given a description of a project (structure, key files, or "
            "pasted code), give constructive feedback. Respond with ONLY a "
            'JSON object: {"summary": "...", "strengths": ["..."], '
            '"concerns": ["..."], "suggestions": ["..."]}. Each list should '
            "have 2-5 short, concrete items. No other text, no markdown "
            "fences."
        ),
        prompt=description,
    )
    return {
        "summary": str(payload.get("summary", "")).strip(),
        "strengths": [str(item) for item in payload.get("strengths", [])][:8],
        "concerns": [str(item) for item in payload.get("concerns", [])][:8],
        "suggestions": [str(item) for item in payload.get("suggestions", [])][:8],
    }


async def suggest_command(task: str, shell: str, api_key: str) -> dict:
    payload = await _synthesize_json(
        api_key,
        system_instruction=(
            "You are a terminal/command-line assistant. Given a task and a "
            "shell, suggest the exact command to run. Respond with ONLY a "
            'JSON object: {"command": "...", "explanation": "...", '
            '"caution": "..."}. explanation is 1-2 sentences on what it does. '
            "caution is a short warning if the command is destructive or "
            "irreversible (empty string if not). No other text, no markdown "
            "fences. Never suggest a command that would need to be run as "
            "root/administrator without saying so in caution."
        ),
        prompt=f"Shell: {shell}\n\nTask: {task}",
    )
    return {
        "command": str(payload.get("command", "")).strip(),
        "explanation": str(payload.get("explanation", "")).strip(),
        "caution": str(payload.get("caution", "")).strip(),
    }


async def _synthesize_json(api_key: str, system_instruction: str, prompt: str) -> dict:
    import asyncio

    def call() -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_instruction),
        )
        return str(response.text or "").strip()

    raw = await asyncio.to_thread(call)
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except (ValueError, TypeError):
        return {"summary": raw, "explanation": raw}
