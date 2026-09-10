"""WhatsApp integration via Meta's official WhatsApp Business Cloud API.

This only works with a real, Meta-provisioned WhatsApp Business account: a
phone_number_id from the Meta developer console and a permanent access
token. There is no unofficial/personal-WhatsApp path here — Meta does not
support that, and JARVIS does not attempt to work around it.

Outside a 24-hour customer service window, WhatsApp requires pre-approved
message templates rather than free-form text; this module supports both.
"""

from __future__ import annotations

from actions._integration_common import IntegrationError, load_secret, save_secret, clear_secret

_TOKEN_KEY = "whatsapp_access_token"
_PHONE_ID_KEY = "whatsapp_phone_number_id"
_GRAPH_VERSION = "v21.0"


def _requests():
    try:
        import requests
        return requests
    except ImportError as exc:
        raise IntegrationError("The 'requests' package is required for WhatsApp integration.") from exc


def _api_url(phone_id: str) -> str:
    return f"https://graph.facebook.com/{_GRAPH_VERSION}/{phone_id}/messages"


def _connect(params: dict) -> str:
    token = str(params.get("access_token") or params.get("token") or "").strip()
    phone_id = str(params.get("phone_number_id") or "").strip()
    if not token or not phone_id:
        return (
            "To connect WhatsApp: in Meta for Developers, set up a WhatsApp Business app, get a "
            "phone_number_id from the API Setup page, generate a permanent access token (System "
            "User token recommended for production), and pass both 'access_token' and "
            "'phone_number_id'."
        )
    requests = _requests()
    try:
        resp = requests.get(
            f"https://graph.facebook.com/{_GRAPH_VERSION}/{phone_id}",
            params={"fields": "display_phone_number,verified_name", "access_token": token},
            timeout=15,
        )
        resp.raise_for_status()
        info = resp.json()
    except Exception as exc:
        return f"WhatsApp credential validation failed: {exc}"
    save_secret(_TOKEN_KEY, token)
    save_secret(_PHONE_ID_KEY, phone_id)
    return f"WhatsApp connected: {info.get('verified_name', 'business account')} ({info.get('display_phone_number', phone_id)})."


def _status() -> str:
    token = load_secret(_TOKEN_KEY)
    phone_id = load_secret(_PHONE_ID_KEY)
    if not token or not phone_id:
        return "WhatsApp is not connected. Say 'connect WhatsApp' with an access token and phone_number_id."
    return f"WhatsApp is connected (phone_number_id: {phone_id})."


def _disconnect() -> str:
    clear_secret(_TOKEN_KEY)
    clear_secret(_PHONE_ID_KEY)
    return "The local WhatsApp connection was removed from JARVIS."


def _require_creds() -> tuple[str, str]:
    token = load_secret(_TOKEN_KEY)
    phone_id = load_secret(_PHONE_ID_KEY)
    if not token or not phone_id:
        raise IntegrationError("WhatsApp is not connected. Say 'connect WhatsApp' first.")
    return token, phone_id


def _send_message(params: dict) -> str:
    requests = _requests()
    token, phone_id = _require_creds()
    to = str(params.get("to") or "").strip()
    text = str(params.get("message") or params.get("text") or "").strip()
    if not to or not text:
        return "Both a recipient 'to' (E.164 phone number) and 'message' text are required."
    body = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    try:
        resp = requests.post(_api_url(phone_id), headers={"Authorization": f"Bearer {token}"}, json=body, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        detail = ""
        try:
            detail = exc.response.json().get("error", {}).get("message", "")  # type: ignore[union-attr]
        except Exception:
            pass
        return (
            f"Could not send WhatsApp message: {detail or exc}. Note: outside the 24-hour customer "
            "service window, WhatsApp requires an approved message template instead of free text."
        )
    data = resp.json()
    msg_id = data.get("messages", [{}])[0].get("id", "")
    return f"WhatsApp message sent to {to} (id: {msg_id})."


def _send_template(params: dict) -> str:
    requests = _requests()
    token, phone_id = _require_creds()
    to = str(params.get("to") or "").strip()
    template = str(params.get("template_name") or "").strip()
    language = str(params.get("language") or "en_US").strip()
    if not to or not template:
        return "A recipient 'to' and 'template_name' (approved in Meta Business Manager) are required."
    components = params.get("components")  # optional pre-built Graph API components list
    body = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {"name": template, "language": {"code": language}},
    }
    if components:
        body["template"]["components"] = components
    try:
        resp = requests.post(_api_url(phone_id), headers={"Authorization": f"Bearer {token}"}, json=body, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        return f"Could not send WhatsApp template message: {exc}"
    data = resp.json()
    msg_id = data.get("messages", [{}])[0].get("id", "")
    return f"WhatsApp template '{template}' sent to {to} (id: {msg_id})."


def whatsapp_control(parameters: dict | None = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action", "status")).lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {"login": "connect", "authorize": "connect", "logout": "disconnect", "send": "send_message"}
    action = aliases.get(action, action)
    if player:
        player.write_log(f"[WhatsApp] {action}")

    try:
        if action == "connect":
            return _connect(params)
        if action == "status":
            return _status()
        if action == "disconnect":
            return _disconnect()
        if action == "send_message":
            return _send_message(params)
        if action == "send_template":
            return _send_template(params)
        return f"Unknown WhatsApp action: {action}"
    except IntegrationError as exc:
        return str(exc)
    except Exception as exc:
        return f"WhatsApp action failed: {exc}"
