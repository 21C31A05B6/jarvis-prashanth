"""Multi-query research reports and text/meeting summarization for the
hosted API.

Research reports run one hosted-safe `web_search` per angle (genuinely
multiple sources, not one query dressed up as "research"), then ask Gemini
to synthesize the results into a structured, cited report. Text/meeting
summarization is a direct Gemini call over user-supplied text — no file
upload or URL fetching, which keeps this hosted-safe (no SSRF surface) at
the cost of not doing live document/webpage fetching itself; the user
pastes the text they want researched or summarized.
"""

from __future__ import annotations

import json
import re


def _default_angles(topic: str) -> list[str]:
    return [topic, f"{topic} pros and cons", f"{topic} latest developments"]


async def run_research_report(topic: str, angles: list[str], api_key: str) -> dict:
    from agent.tool_runtime import run_web_search

    queries = angles or _default_angles(topic)
    findings = []
    for query in queries:
        try:
            result = await run_web_search(query)
        except Exception as exc:
            result = f"(search failed: {exc})"
        findings.append(f"### {query}\n{result}")

    combined = "\n\n".join(findings)
    report = await _synthesize(
        api_key,
        system_instruction=(
            "You are a research analyst. Synthesize the search results below into "
            "a clear, well-organized report on the topic. Structure it with a short "
            "summary, then key findings as bullet points. Where sources disagree or "
            "a claim is uncertain, say so plainly rather than picking one side "
            "silently. Do not invent facts not present in the search results."
        ),
        prompt=f"Topic: {topic}\n\nSearch results from {len(queries)} queries:\n\n{combined}",
    )
    return {"topic": topic, "report": report, "sources_queried": queries}


async def summarize_text(text: str, context: str, api_key: str) -> dict:
    payload = await _synthesize_json(
        api_key,
        system_instruction=(
            "Summarize the given text. Respond with ONLY a JSON object of the form "
            '{"summary": "...", "key_points": ["...", "..."]}. The summary should be '
            "2-4 sentences. key_points should be 3-6 short bullet-point strings. No "
            "other text, no markdown fences."
        ),
        prompt=(f"Context: {context}\n\n" if context else "") + f"Text:\n{text}",
    )
    return {
        "summary": str(payload.get("summary", "")).strip(),
        "key_points": [str(item) for item in payload.get("key_points", [])][:8],
    }


async def summarize_meeting(transcript: str, api_key: str) -> dict:
    payload = await _synthesize_json(
        api_key,
        system_instruction=(
            "Summarize this meeting transcript. Respond with ONLY a JSON object of "
            'the form {"summary": "...", "action_items": ["...", "..."]}. The summary '
            "should cover what was discussed and decided, 3-6 sentences. action_items "
            "should be concrete, assignable tasks mentioned or implied in the "
            "meeting — if there genuinely are none, return an empty list. No other "
            "text, no markdown fences."
        ),
        prompt=f"Transcript:\n{transcript}",
    )
    return {
        "summary": str(payload.get("summary", "")).strip(),
        "action_items": [str(item) for item in payload.get("action_items", [])][:20],
    }


async def _synthesize(api_key: str, system_instruction: str, prompt: str) -> str:
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

    return await asyncio.to_thread(call)


async def _synthesize_json(api_key: str, system_instruction: str, prompt: str) -> dict:
    raw = await _synthesize(api_key, system_instruction, prompt)
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except (ValueError, TypeError):
        return {"summary": raw, "key_points": [], "action_items": []}
