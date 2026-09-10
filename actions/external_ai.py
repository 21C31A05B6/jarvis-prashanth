"""Lets JARVIS delegate a prompt to an external AI model the user has their
own API key for — useful for comparing answers, using a specialized model,
or falling back if Gemini is unavailable.

Supported providers:
  - "openai": any OpenAI model (gpt-4.1, o-series, etc.) via the official SDK.
  - "anthropic": any Claude model, via a direct REST call (no SDK dependency).
  - "custom": any OpenAI-compatible endpoint (local models, OpenRouter,
    Azure OpenAI, etc.) — pass base_url.
"""

from __future__ import annotations

from actions._integration_common import (
    IntegrationError, load_secret, save_secret, save_json_secret, load_json_secret,
    clear_secret, missing_dependency,
)

_KEY_PREFIX = "external_ai_key"
_DEFAULT_PROVIDER_KEY = "external_ai_default_provider"
_CUSTOM_CONFIG_KEY = "external_ai_custom_config"

_DEFAULT_MODELS = {
    "openai": "gpt-4.1",
    "anthropic": "claude-sonnet-4-6",
    "custom": "",
}


def _requests():
    try:
        import requests
        return requests
    except ImportError as exc:
        raise IntegrationError("The 'requests' package is required for this integration.") from exc


def _normalize_provider(value: str) -> str:
    p = (value or "").strip().lower()
    if p in ("gpt", "chatgpt"):
        return "openai"
    if p in ("claude",):
        return "anthropic"
    return p or (load_secret(_DEFAULT_PROVIDER_KEY) or "openai")


def _connect(params: dict) -> str:
    provider = _normalize_provider(str(params.get("provider") or ""))
    api_key = str(params.get("api_key") or "").strip()
    if provider not in ("openai", "anthropic", "custom"):
        return "provider must be one of: openai, anthropic, custom."
    if not api_key:
        return f"An api_key for '{provider}' is required to connect."
    save_secret(f"{_KEY_PREFIX}:{provider}", api_key)
    save_secret(_DEFAULT_PROVIDER_KEY, provider)
    if provider == "custom":
        base_url = str(params.get("base_url") or "").strip()
        if not base_url:
            return "provider=custom also needs a base_url (an OpenAI-compatible /v1 endpoint)."
        save_json_secret(_CUSTOM_CONFIG_KEY, {
            "base_url": base_url,
            "model": str(params.get("model") or "").strip(),
        })
    return f"External AI provider '{provider}' connected. It will be used by default for ask_external_model."


def _status() -> str:
    connected = [p for p in ("openai", "anthropic", "custom") if load_secret(f"{_KEY_PREFIX}:{p}")]
    if not connected:
        return "No external AI model is connected. Say 'connect external AI' with a provider and api_key."
    default = load_secret(_DEFAULT_PROVIDER_KEY) or connected[0]
    return f"External AI providers connected: {', '.join(connected)}. Default: {default}."


def _disconnect(params: dict) -> str:
    provider = _normalize_provider(str(params.get("provider") or ""))
    clear_secret(f"{_KEY_PREFIX}:{provider}")
    if provider == "custom":
        clear_secret(_CUSTOM_CONFIG_KEY)
    return f"External AI provider '{provider}' disconnected."


def _ask_openai(prompt: str, model: str, api_key: str, system: str = "") -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise missing_dependency("openai", "OpenAI") from exc
    client = OpenAI(api_key=api_key)
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    resp = client.chat.completions.create(model=model or _DEFAULT_MODELS["openai"], messages=messages)
    return resp.choices[0].message.content or ""


def _ask_anthropic(prompt: str, model: str, api_key: str, system: str = "") -> str:
    requests = _requests()
    body = {
        "model": model or _DEFAULT_MODELS["anthropic"],
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body, timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "\n".join(parts)


def _ask_custom(prompt: str, model: str, api_key: str, system: str = "") -> str:
    requests = _requests()
    config = load_json_secret(_CUSTOM_CONFIG_KEY) or {}
    base_url = str(config.get("base_url") or "").rstrip("/")
    if not base_url:
        raise IntegrationError("No base_url configured for the custom provider. Reconnect with base_url set.")
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model or config.get("model") or "", "messages": messages}, timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def _ask(params: dict) -> str:
    prompt = str(params.get("prompt") or params.get("query") or "").strip()
    if not prompt:
        return "A prompt is required."
    provider = _normalize_provider(str(params.get("provider") or ""))
    api_key = load_secret(f"{_KEY_PREFIX}:{provider}")
    if not api_key:
        return f"'{provider}' is not connected. Say 'connect external AI' with provider='{provider}' and an api_key."
    model = str(params.get("model") or "").strip()
    system = str(params.get("system") or "").strip()
    try:
        if provider == "openai":
            text = _ask_openai(prompt, model, api_key, system)
        elif provider == "anthropic":
            text = _ask_anthropic(prompt, model, api_key, system)
        else:
            text = _ask_custom(prompt, model, api_key, system)
    except IntegrationError:
        raise
    except Exception as exc:
        return f"The external model call failed: {exc}"
    return text or "(The external model returned no content.)"


def external_ai(parameters: dict | None = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action", "ask")).lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {"login": "connect", "authorize": "connect", "logout": "disconnect", "query": "ask", "chat": "ask"}
    action = aliases.get(action, action)
    if player:
        player.write_log(f"[ExternalAI] {action}")

    try:
        if action == "connect":
            return _connect(params)
        if action == "status":
            return _status()
        if action == "disconnect":
            return _disconnect(params)
        if action == "ask":
            return _ask(params)
        return f"Unknown external AI action: {action}"
    except IntegrationError as exc:
        return str(exc)
    except Exception as exc:
        return f"External AI action failed: {exc}"
