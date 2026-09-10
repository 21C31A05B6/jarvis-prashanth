"""Microsoft Teams integration.

Two modes:
  - Webhook (simplest): a channel "Incoming Webhook" connector URL, used to
    post messages/adaptive cards into one channel with no app registration.
  - Graph API (optional, richer): device-code OAuth against Microsoft Graph
    (via the ``msal`` package) for listing teams/channels and posting as the
    signed-in user. Requires an Azure AD app registration.
"""

from __future__ import annotations

from actions._integration_common import (
    IntegrationError, bounded_limit, load_secret, save_secret, clear_secret, missing_dependency,
)

_WEBHOOK_KEY = "teams_webhook_url"
_GRAPH_TOKEN_KEY = "teams_graph_token_cache"
_GRAPH_CLIENT_ID_KEY = "teams_graph_client_id"
_GRAPH_ACCOUNT_KEY = "teams_graph_account"
_GRAPH_SCOPES = ["Chat.ReadWrite", "Channel.ReadBasic.All", "ChannelMessage.Send", "Team.ReadBasic.All"]
_GRAPH_AUTHORITY = "https://login.microsoftonline.com/common"
_GRAPH_API = "https://graph.microsoft.com/v1.0"


def _requests():
    try:
        import requests
        return requests
    except ImportError as exc:
        raise IntegrationError("The 'requests' package is required for Teams integration.") from exc


def _connect(params: dict) -> str:
    webhook = str(params.get("webhook_url") or "").strip()
    client_id = str(params.get("client_id") or "").strip()
    messages = []

    if webhook:
        save_secret(_WEBHOOK_KEY, webhook)
        messages.append("Webhook connected")

    if client_id:
        try:
            import msal
        except ImportError as exc:
            return str(missing_dependency("msal", "Microsoft Teams (Graph API)")) if not messages else "; ".join(messages) + f". Graph sign-in skipped: {missing_dependency('msal', 'Teams Graph API')}"
        save_secret(_GRAPH_CLIENT_ID_KEY, client_id)
        app = msal.PublicClientApplication(client_id, authority=_GRAPH_AUTHORITY)
        flow = app.initiate_device_flow(scopes=_GRAPH_SCOPES)
        if "user_code" not in flow:
            return "Could not start Microsoft sign-in: " + str(flow.get("error_description", flow))
        print(f"[Teams] {flow['message']}")
        result = app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            return f"Microsoft sign-in failed: {result.get('error_description', result)}"
        save_secret(_GRAPH_TOKEN_KEY, __import__("json").dumps(result))
        account = result.get("id_token_claims", {}).get("preferred_username", "")
        save_secret(_GRAPH_ACCOUNT_KEY, account)
        messages.append(f"Graph API signed in as {account} (code: {flow['user_code']} was used)")

    if not messages:
        return (
            "To connect Teams: for simple channel posting, add an 'Incoming Webhook' connector to "
            "a channel in Teams and pass its URL as 'webhook_url'. For reading channels/chats, "
            "register an Azure AD app (public client, device code flow enabled) and pass its "
            "client_id."
        )
    return "Microsoft Teams: " + "; ".join(messages) + "."


def _status() -> str:
    webhook = load_secret(_WEBHOOK_KEY)
    account = load_secret(_GRAPH_ACCOUNT_KEY)
    if not webhook and not account:
        return "Microsoft Teams is not connected. Say 'connect Teams' with a webhook URL or Graph client_id."
    parts = []
    if webhook:
        parts.append("webhook connected")
    if account:
        parts.append(f"Graph API signed in as {account}")
    return "Microsoft Teams: " + ", ".join(parts) + "."


def _disconnect() -> str:
    clear_secret(_WEBHOOK_KEY)
    clear_secret(_GRAPH_TOKEN_KEY)
    clear_secret(_GRAPH_CLIENT_ID_KEY)
    clear_secret(_GRAPH_ACCOUNT_KEY)
    return "The local Microsoft Teams connection(s) were removed from JARVIS."


def _graph_token() -> str:
    import json
    try:
        import msal
    except ImportError as exc:
        raise missing_dependency("msal", "Microsoft Teams (Graph API)") from exc
    client_id = load_secret(_GRAPH_CLIENT_ID_KEY)
    cache_raw = load_secret(_GRAPH_TOKEN_KEY)
    if not client_id or not cache_raw:
        raise IntegrationError("Teams Graph API is not connected. Say 'connect Teams' with a client_id first.")
    result = json.loads(cache_raw)
    app = msal.PublicClientApplication(client_id, authority=_GRAPH_AUTHORITY)
    accounts = app.get_accounts()
    refreshed = None
    if accounts:
        refreshed = app.acquire_token_silent(_GRAPH_SCOPES, account=accounts[0])
    if not refreshed and result.get("refresh_token"):
        refreshed = app.acquire_token_by_refresh_token(result["refresh_token"], scopes=_GRAPH_SCOPES)
    if refreshed and "access_token" in refreshed:
        save_secret(_GRAPH_TOKEN_KEY, json.dumps(refreshed))
        return refreshed["access_token"]
    if "access_token" in result:
        return result["access_token"]
    raise IntegrationError("The Teams Graph session expired. Reconnect Teams.")


def _send_message(params: dict) -> str:
    requests = _requests()
    text = str(params.get("message") or params.get("text") or "").strip()
    if not text:
        return "Message text is required."
    webhook = load_secret(_WEBHOOK_KEY)
    channel_id = str(params.get("channel_id") or "").strip()
    team_id = str(params.get("team_id") or "").strip()

    if channel_id and team_id:
        try:
            token = _graph_token()
            resp = requests.post(
                f"{_GRAPH_API}/teams/{team_id}/channels/{channel_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"body": {"content": text}}, timeout=15,
            )
            resp.raise_for_status()
        except IntegrationError:
            raise
        except Exception as exc:
            return f"Could not send Teams channel message: {exc}"
        return "Message sent to the Teams channel."

    if webhook:
        try:
            resp = requests.post(webhook, json={"text": text}, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            return f"Could not send via Teams webhook: {exc}"
        return "Message sent via Teams webhook."
    return "Connect a webhook, or provide team_id and channel_id with a Graph sign-in, to send a message."


def _list_teams(params: dict) -> str:
    requests = _requests()
    token = _graph_token()
    try:
        resp = requests.get(f"{_GRAPH_API}/me/joinedTeams", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        return f"Could not list teams: {exc}"
    teams = resp.json().get("value", [])
    if not teams:
        return "No joined teams found."
    lines = [f"- {t['displayName']} ({t['id']})" for t in teams]
    return "Microsoft Teams:\n" + "\n".join(lines)


def _list_channels(params: dict) -> str:
    requests = _requests()
    team_id = str(params.get("team_id") or "").strip()
    if not team_id:
        return "A team_id is required."
    token = _graph_token()
    try:
        resp = requests.get(f"{_GRAPH_API}/teams/{team_id}/channels", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        return f"Could not list channels: {exc}"
    channels = resp.json().get("value", [])
    if not channels:
        return "No channels found."
    lines = [f"- {c['displayName']} ({c['id']})" for c in channels]
    return "Channels:\n" + "\n".join(lines)


def teams_control(parameters: dict | None = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action", "status")).lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {"login": "connect", "authorize": "connect", "logout": "disconnect", "send": "send_message", "teams": "list_teams", "channels": "list_channels"}
    action = aliases.get(action, action)
    if player:
        player.write_log(f"[Teams] {action}")

    try:
        if action == "connect":
            return _connect(params)
        if action == "status":
            return _status()
        if action == "disconnect":
            return _disconnect()
        if action == "send_message":
            return _send_message(params)
        if action == "list_teams":
            return _list_teams(params)
        if action == "list_channels":
            return _list_channels(params)
        return f"Unknown Teams action: {action}"
    except IntegrationError as exc:
        return str(exc)
    except Exception as exc:
        return f"Microsoft Teams action failed: {exc}"
