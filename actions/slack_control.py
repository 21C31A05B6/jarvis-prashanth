"""Slack integration using a Bot User OAuth Token (xoxb-...) stored in the
OS keychain. Uses Slack's Web API directly via ``requests``.
"""

from __future__ import annotations

from actions._integration_common import (
    IntegrationError, bounded_limit, load_secret, save_secret, clear_secret,
)

_TOKEN_KEY = "slack_bot_token"
_TEAM_KEY = "slack_team_name"
_API = "https://slack.com/api"


def _requests():
    try:
        import requests
        return requests
    except ImportError as exc:
        raise IntegrationError("The 'requests' package is required for Slack integration.") from exc


def _headers() -> dict:
    token = load_secret(_TOKEN_KEY)
    if not token:
        raise IntegrationError("Slack is not connected. Say 'connect Slack' and provide a bot token.")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}


def _call(method: str, requests, http_method: str = "GET", **kwargs) -> dict:
    fn = requests.post if http_method == "POST" else requests.get
    resp = fn(f"{_API}/{method}", headers=_headers(), timeout=15, **kwargs)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise IntegrationError(f"Slack API error ({method}): {data.get('error', 'unknown_error')}")
    return data


def _connect(params: dict) -> str:
    token = str(params.get("token") or params.get("bot_token") or "").strip()
    if not token:
        return (
            "To connect Slack, create a Slack app at https://api.slack.com/apps, add the "
            "chat:write, channels:read, channels:history, and users:read scopes, install it to "
            "your workspace, and pass the Bot User OAuth Token (starts with xoxb-) as 'token'."
        )
    requests = _requests()
    try:
        resp = requests.get(f"{_API}/auth.test", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        data = resp.json()
        if not data.get("ok"):
            return f"Slack token validation failed: {data.get('error', 'unknown_error')}"
    except Exception as exc:
        return f"Slack token validation failed: {exc}"
    save_secret(_TOKEN_KEY, token)
    save_secret(_TEAM_KEY, data.get("team", ""))
    return f"Slack connected to workspace '{data.get('team')}' as {data.get('user')}."


def _status() -> str:
    token = load_secret(_TOKEN_KEY)
    if not token:
        return "Slack is not connected. Say 'connect Slack' with a bot token."
    team = load_secret(_TEAM_KEY)
    return f"Slack is connected to workspace '{team or 'unknown'}'."


def _disconnect() -> str:
    clear_secret(_TOKEN_KEY)
    clear_secret(_TEAM_KEY)
    return "The local Slack connection was removed from JARVIS. Uninstall the app in Slack to revoke it fully."


def _list_channels(params: dict) -> str:
    requests = _requests()
    limit = bounded_limit(params.get("limit", 20), maximum=100)
    data = _call("conversations.list", requests, params={"limit": limit, "types": "public_channel,private_channel"})
    channels = data.get("channels", [])
    if not channels:
        return "No channels found."
    lines = [f"- #{c['name']} ({c['id']}){' [private]' if c.get('is_private') else ''}" for c in channels]
    return "Slack channels:\n" + "\n".join(lines)


def _resolve_channel(requests, name_or_id: str) -> str:
    if not name_or_id:
        raise IntegrationError("A Slack channel name or ID is required.")
    if name_or_id.startswith("#"):
        name_or_id = name_or_id[1:]
    if name_or_id.upper().startswith(("C", "D", "G")) and name_or_id.isupper():
        return name_or_id
    data = _call("conversations.list", requests, params={"limit": 200, "types": "public_channel,private_channel"})
    for c in data.get("channels", []):
        if c["name"] == name_or_id:
            return c["id"]
    return name_or_id


def _send_message(params: dict) -> str:
    requests = _requests()
    channel = str(params.get("channel") or "").strip()
    text = str(params.get("message") or params.get("text") or "").strip()
    if not channel or not text:
        return "Both a channel and message text are required."
    channel_id = _resolve_channel(requests, channel)
    data = _call("chat.postMessage", requests, http_method="POST", json={"channel": channel_id, "text": text})
    return f"Message sent to Slack channel {channel} (ts={data.get('ts')})."


def _read_channel(params: dict) -> str:
    requests = _requests()
    channel = str(params.get("channel") or "").strip()
    if not channel:
        return "A channel name or ID is required."
    channel_id = _resolve_channel(requests, channel)
    limit = bounded_limit(params.get("limit", 15), maximum=50)
    data = _call("conversations.history", requests, params={"channel": channel_id, "limit": limit})
    messages = data.get("messages", [])
    if not messages:
        return f"No recent messages found in {channel}."
    lines = [f"- {m.get('user', 'unknown')}: {m.get('text', '')}" for m in reversed(messages)]
    return f"Recent messages in {channel}:\n" + "\n".join(lines)


def _search(params: dict) -> str:
    requests = _requests()
    query = str(params.get("query") or "").strip()
    if not query:
        return "A search query is required."
    data = _call("search.messages", requests, params={"query": query, "count": bounded_limit(params.get("limit", 10), maximum=20)})
    matches = data.get("messages", {}).get("matches", [])
    if not matches:
        return f"No Slack messages found for '{query}'."
    lines = [f"- #{m.get('channel', {}).get('name', '?')} — {m.get('username', 'unknown')}: {m.get('text', '')}" for m in matches]
    return f"Search results for '{query}':\n" + "\n".join(lines)


def slack_control(parameters: dict | None = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action", "status")).lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {"login": "connect", "authorize": "connect", "logout": "disconnect", "send": "send_message", "channels": "list_channels", "history": "read_channel"}
    action = aliases.get(action, action)
    if player:
        player.write_log(f"[Slack] {action}")

    try:
        if action == "connect":
            return _connect(params)
        if action == "status":
            return _status()
        if action == "disconnect":
            return _disconnect()
        if action == "list_channels":
            return _list_channels(params)
        if action == "send_message":
            return _send_message(params)
        if action == "read_channel":
            return _read_channel(params)
        if action == "search":
            return _search(params)
        return f"Unknown Slack action: {action}"
    except IntegrationError as exc:
        return str(exc)
    except Exception as exc:
        return f"Slack action failed: {exc}"
