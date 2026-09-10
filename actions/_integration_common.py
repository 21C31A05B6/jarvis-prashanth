"""Shared helpers for third-party API integrations (Calendar, Drive, GitHub,
Slack, Discord, Teams, WhatsApp, cloud storage, external AI models, ...).

All credentials are stored in the OS keychain via ``core.secret_store``,
never written to disk in plaintext. Keys are namespaced per hosted tenant
(when JARVIS is running in hosted/multi-user mode) so one user's tokens are
never visible to another.
"""

from __future__ import annotations

import json
from typing import Any, Optional


def secret_store():
    from core.secret_store import get_secret_store

    return get_secret_store()


def tenant_key(base_key: str) -> str:
    """Namespace a secret-store key by the current hosted tenant, if any."""
    try:
        from core.tenant import get_current_user_id

        user_id = get_current_user_id()
    except Exception:
        user_id = None
    return f"{base_key}:{user_id}" if user_id else base_key


def save_secret(base_key: str, value: str) -> bool:
    try:
        secret_store().set(tenant_key(base_key), value)
        return True
    except Exception:
        return False


def load_secret(base_key: str) -> Optional[str]:
    try:
        return secret_store().get(tenant_key(base_key))
    except Exception:
        return None


def clear_secret(base_key: str) -> None:
    try:
        secret_store().delete(tenant_key(base_key))
    except Exception:
        pass


def save_json_secret(base_key: str, value: dict) -> bool:
    return save_secret(base_key, json.dumps(value, ensure_ascii=False))


def load_json_secret(base_key: str) -> Optional[dict]:
    raw = load_secret(base_key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def bounded_limit(value: Any, default: int = 10, minimum: int = 1, maximum: int = 50) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(minimum, min(maximum, n))


class IntegrationError(RuntimeError):
    """Raised for user-facing integration failures (missing deps, bad auth)."""


def missing_dependency(package_hint: str, feature: str) -> "IntegrationError":
    return IntegrationError(
        f"{feature} support is not installed. Run: pip install {package_hint}"
    )


def http_error_message(service: str, exc: Exception) -> str:
    """Turn a requests/HTTP exception into a friendly, actionable message."""
    try:
        import requests

        if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
            status = exc.response.status_code
            try:
                body = exc.response.json()
                detail = (
                    body.get("message")
                    or body.get("error", {}).get("message")
                    if isinstance(body.get("error"), dict)
                    else body.get("error")
                ) or str(body)[:200]
            except Exception:
                detail = (exc.response.text or "")[:200]
            if status in (401, 403):
                return (
                    f"{service} rejected the request ({status}). The stored credentials may be "
                    f"invalid, expired, or missing a required permission/scope. Detail: {detail}"
                )
            return f"{service} request failed ({status}): {detail}"
    except Exception:
        pass
    return f"{service} request failed: {exc}"
