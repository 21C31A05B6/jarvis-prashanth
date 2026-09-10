"""Discord integration via the official REST API.

Two credential modes are supported:
  - Bot token: full read/write access to servers the bot has been invited to.
  - Webhook URL: the simplest way to post messages into one channel, no bot
    invite required.

This is distinct from the desktop-automation Discord support in
``actions/send_message.py`` (which types into the Discord desktop app).
"""

from __future__ import annotations

from actions._integration_common import (
    IntegrationError, bounded_limit, load_secret, save_secret, clear_secret,
)

_BOT_TOKEN_KEY = "discord_bot_token"
_WEBHOOK_KEY = "discord_webhook_url"
_BOT_NAME_KEY = "discord_bot_name"
_API = "https://discord.com/api/v10"


def _requests():
    try:
        import requests
        return requests
    except ImportError as exc:
        raise IntegrationError("The 'requests' package is required for Discord integration.") from exc


def _bot_headers() -> dict:
    token = load_secret(_BOT_TOKEN_KEY)
    if not token:
        raise IntegrationError(
            "Discord bot is not connected. Say 'connect Discord' with a bot token, or use a webhook "
            "for simple message sending."
        )
    return {"Authorization": f"Bot {token}", "Content-Type": "application/json"}


def _connect(params: dict) -> str:
    token = str(params.get("bot_token") or params.get("token") or "").strip()
    webhook = str(params.get("webhook_url") or "").strip()
    if not token and not webhook:
        return (
            "To connect Discord: create an application at https://discord.com/developers/applications, "
            "add a bot, invite it to your server with 'Send Messages' and 'Read Message History' "
            "permissions, and pass the bot token as 'bot_token'. For simple one-channel posting "
            "without a bot, create a channel webhook instead and pass its URL as 'webhook_url'."
        )
    requests = _requests()
    messages = []
    if token:
        try:
            resp = requests.get(f"{_API}/users/@me", headers={"Authorization": f"Bot {token}"}, timeout=15)
            resp.raise_for_status()
            me = resp.json()
        except Exception as exc:
            return f"Discord bot token validation failed: {exc}"
        save_secret(_BOT_TOKEN_KEY, token)
        save_secret(_BOT_NAME_KEY, f"{me.get('username', '')}#{me.get('discriminator', '0')}")
        messages.append(f"Bot connected as {me.get('username')}")
    if webhook:
        try:
            resp = requests.get(webhook, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            return f"Discord webhook validation failed: {exc}"
        save_secret(_WEBHOOK_KEY, webhook)
        messages.append("Webhook connected")
    return "Discord: " + "; ".join(messages) + "."


def _status() -> str:
    token = load_secret(_BOT_TOKEN_KEY)
    webhook = load_secret(_WEBHOOK_KEY)
    if not token and not webhook:
        return "Discord is not connected. Say 'connect Discord' with a bot token or webhook URL."
    parts = []
    if token:
        parts.append(f"bot connected as {load_secret(_BOT_NAME_KEY) or 'unknown'}")
    if webhook:
        parts.append("webhook connected")
    return "Discord: " + ", ".join(parts) + "."


def _disconnect() -> str:
    clear_secret(_BOT_TOKEN_KEY)
    clear_secret(_WEBHOOK_KEY)
    clear_secret(_BOT_NAME_KEY)
    return "The local Discord connection(s) were removed from JARVIS."


def _send_message(params: dict) -> str:
    requests = _requests()
    text = str(params.get("message") or params.get("text") or "").strip()
    if not text:
        return "Message text is required."
    channel_id = str(params.get("channel_id") or "").strip()
    webhook = load_secret(_WEBHOOK_KEY)
    if channel_id:
        try:
            resp = requests.post(
                f"{_API}/channels/{channel_id}/messages", headers=_bot_headers(),
                json={"content": text}, timeout=15,
            )
            resp.raise_for_status()
        except IntegrationError:
            raise
        except Exception as exc:
            return f"Could not send Discord message: {exc}"
        return f"Message sent to Discord channel {channel_id}."
    if webhook:
        try:
            resp = requests.post(webhook, json={"content": text}, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            return f"Could not send via Discord webhook: {exc}"
        return "Message sent via Discord webhook."
    return "Provide a channel_id (requires a connected bot) or connect a webhook to send messages."


def _list_guilds(params: dict) -> str:
    requests = _requests()
    try:
        resp = requests.get(f"{_API}/users/@me/guilds", headers=_bot_headers(), timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        return f"Could not list servers: {exc}"
    guilds = resp.json()
    if not guilds:
        return "The bot is not a member of any servers."
    lines = [f"- {g['name']} ({g['id']})" for g in guilds]
    return "Discord servers:\n" + "\n".join(lines)


def _list_channels(params: dict) -> str:
    requests = _requests()
    guild_id = str(params.get("guild_id") or params.get("server_id") or "").strip()
    if not guild_id:
        return "A guild_id (server ID) is required."
    try:
        resp = requests.get(f"{_API}/guilds/{guild_id}/channels", headers=_bot_headers(), timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        return f"Could not list channels: {exc}"
    channels = [c for c in resp.json() if c.get("type") == 0]
    if not channels:
        return "No text channels found."
    lines = [f"- #{c['name']} ({c['id']})" for c in channels]
    return "Discord channels:\n" + "\n".join(lines)


def _read_channel(params: dict) -> str:
    requests = _requests()
    channel_id = str(params.get("channel_id") or "").strip()
    if not channel_id:
        return "A channel_id is required."
    limit = bounded_limit(params.get("limit", 15), maximum=50)
    try:
        resp = requests.get(
            f"{_API}/channels/{channel_id}/messages", headers=_bot_headers(),
            params={"limit": limit}, timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        return f"Could not read channel: {exc}"
    messages = resp.json()
    if not messages:
        return "No recent messages found."
    lines = [f"- {m['author']['username']}: {m.get('content', '')}" for m in reversed(messages)]
    return "Recent messages:\n" + "\n".join(lines)


def discord_control(parameters: dict | None = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action", "status")).lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {"login": "connect", "authorize": "connect", "logout": "disconnect", "send": "send_message", "servers": "list_guilds", "guilds": "list_guilds", "channels": "list_channels", "history": "read_channel"}
    action = aliases.get(action, action)
    if player:
        player.write_log(f"[Discord] {action}")

    try:
        if action == "connect":
            return _connect(params)
        if action == "status":
            return _status()
        if action == "disconnect":
            return _disconnect()
        if action == "send_message":
            return _send_message(params)
        if action == "list_guilds":
            return _list_guilds(params)
        if action == "list_channels":
            return _list_channels(params)
        if action == "read_channel":
            return _read_channel(params)
        return f"Unknown Discord action: {action}"
    except IntegrationError as exc:
        return str(exc)
    except Exception as exc:
        return f"Discord action failed: {exc}"
