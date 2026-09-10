"""Compatibility layer so call sites written for the deprecated
``google-generativeai`` package can run on the actively maintained
``google-genai`` SDK without each caller having to learn the new
client/response shape.

Only one Gemini SDK generation (``google-genai``) is a real dependency of
this project; this module is the single place that talks to it on behalf of
the simple "configure + GenerativeModel + generate_content" call sites that
used to import ``google.generativeai`` directly.
"""

from __future__ import annotations

from google import genai as _genai
from google.genai import types as _types


class _CompatResponse:
    __slots__ = ("text",)

    def __init__(self, text: str):
        self.text = text


class _CompatModel:
    """Mimics the small slice of the legacy ``GenerativeModel`` surface
    (``.generate_content(prompt).text``) that this project actually uses.
    """

    def __init__(self, client: _genai.Client, model_name: str, system_instruction: str | None = None):
        self._client = client
        self._model_name = model_name
        self._system_instruction = system_instruction

    def generate_content(self, prompt: str) -> _CompatResponse:
        config = None
        if self._system_instruction:
            config = _types.GenerateContentConfig(system_instruction=self._system_instruction)
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=config,
        )
        return _CompatResponse(str(response.text or ""))


def get_model(model_name: str, api_key: str, system_instruction: str | None = None) -> _CompatModel:
    """Return an object exposing ``.generate_content(prompt).text``, backed
    by the current ``google-genai`` SDK.

    Replaces the ``genai.configure(api_key=...); genai.GenerativeModel(...)``
    pattern from the deprecated ``google-generativeai`` package.
    """
    if not api_key:
        raise ValueError("A Gemini API key is required")
    client = _genai.Client(api_key=api_key)
    return _CompatModel(client, model_name, system_instruction)
