"""Google Calendar integration: connect via OAuth, list/search/create/update/
delete events. Follows the same connect/status/disconnect shape as Gmail in
``actions/email_control.py``.
"""

from __future__ import annotations

from actions._integration_common import IntegrationError, bounded_limit, load_secret, save_secret
from actions.google_oauth_common import connect_flow, get_service, clear_credentials

SCOPES = ("https://www.googleapis.com/auth/calendar",)
_TOKEN_KEY = "gcal_oauth_credentials"
_ACCOUNT_KEY = "gcal_account_email"
_CLIENT_PATH_KEY = "google_oauth_client_path"


def _service():
    return get_service(api_service="calendar", api_version="v3", scopes=SCOPES, token_key=_TOKEN_KEY)


def _account_lookup(service) -> str:
    cal = service.calendarList().get(calendarId="primary").execute()
    return cal.get("id", "") or cal.get("summary", "")


def _connect(credentials_path: str = "") -> str:
    return connect_flow(
        service_name="Google Calendar",
        service_id="calendar",
        api_service="calendar",
        api_version="v3",
        scopes=SCOPES,
        token_key=_TOKEN_KEY,
        account_key=_ACCOUNT_KEY,
        client_path_key=_CLIENT_PATH_KEY,
        explicit_path=credentials_path,
        account_lookup=_account_lookup,
    )


def _status() -> str:
    account = load_secret(_ACCOUNT_KEY)
    if not account:
        return "Google Calendar is not connected. Say 'connect Google Calendar' to start OAuth."
    try:
        service = _service()
        if not service:
            return "Google Calendar was connected but the session expired. Reconnect it."
        return f"Google Calendar is connected as {account}."
    except IntegrationError as exc:
        return str(exc)


def _require_service():
    service = _service()
    if not service:
        raise IntegrationError("Google Calendar is not connected. Say 'connect Google Calendar' first.")
    return service


def _fmt_event(ev: dict) -> str:
    start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date", "")
    end = ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date", "")
    summary = ev.get("summary", "(no title)")
    loc = f" @ {ev['location']}" if ev.get("location") else ""
    return f"- [{ev.get('id')}] {summary}{loc} | {start} → {end}"


def _list(params: dict) -> str:
    from datetime import datetime, timezone

    service = _require_service()
    limit = bounded_limit(params.get("limit", 10))
    time_min = params.get("time_min") or datetime.now(timezone.utc).isoformat()
    calendar_id = params.get("calendar_id", "primary") or "primary"
    try:
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=params.get("time_max") or None,
            maxResults=limit,
            singleEvents=True,
            orderBy="startTime",
            q=params.get("query") or None,
        ).execute()
    except Exception as exc:
        return f"Could not list calendar events: {exc}"
    items = result.get("items", [])
    if not items:
        return "No upcoming events found."
    lines = [_fmt_event(ev) for ev in items]
    return "Upcoming events:\n" + "\n".join(lines)


def _create(params: dict) -> str:
    service = _require_service()
    summary = str(params.get("summary") or params.get("title") or "").strip()
    start = str(params.get("start") or "").strip()
    end = str(params.get("end") or "").strip()
    if not summary or not start:
        return "An event title and start time (ISO 8601, e.g. 2026-09-02T15:00:00) are required."
    if not end:
        end = start
    calendar_id = params.get("calendar_id", "primary") or "primary"
    all_day = "T" not in start
    body = {
        "summary": summary,
        "location": params.get("location") or None,
        "description": params.get("description") or None,
        "start": {"date": start} if all_day else {"dateTime": start},
        "end": {"date": end} if all_day else {"dateTime": end},
    }
    attendees = params.get("attendees")
    if attendees:
        emails = [a.strip() for a in str(attendees).split(",") if a.strip()]
        if emails:
            body["attendees"] = [{"email": e} for e in emails]
    try:
        created = service.events().insert(calendarId=calendar_id, body=body).execute()
    except Exception as exc:
        return f"Could not create the event: {exc}"
    return f"Event created: {created.get('summary')} ({created.get('id')})."


def _update(params: dict) -> str:
    service = _require_service()
    event_id = str(params.get("event_id") or "").strip()
    if not event_id:
        return "An event_id from the events list is required to update an event."
    calendar_id = params.get("calendar_id", "primary") or "primary"
    try:
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    except Exception as exc:
        return f"Could not find that event: {exc}"
    if params.get("summary"):
        event["summary"] = params["summary"]
    if params.get("location"):
        event["location"] = params["location"]
    if params.get("description"):
        event["description"] = params["description"]
    if params.get("start"):
        event["start"] = {"date": params["start"]} if "T" not in params["start"] else {"dateTime": params["start"]}
    if params.get("end"):
        event["end"] = {"date": params["end"]} if "T" not in params["end"] else {"dateTime": params["end"]}
    try:
        updated = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
    except Exception as exc:
        return f"Could not update the event: {exc}"
    return f"Event updated: {updated.get('summary')}."


def _delete(params: dict) -> str:
    service = _require_service()
    event_id = str(params.get("event_id") or "").strip()
    if not event_id:
        return "An event_id from the events list is required to delete an event."
    calendar_id = params.get("calendar_id", "primary") or "primary"
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    except Exception as exc:
        return f"Could not delete the event: {exc}"
    return "Event deleted."


def calendar_control(parameters: dict | None = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action", "list")).lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {"login": "connect", "authorize": "connect", "logout": "disconnect", "events": "list", "upcoming": "list"}
    action = aliases.get(action, action)
    if player:
        player.write_log(f"[Calendar] {action}")

    try:
        if action == "connect":
            return _connect(str(params.get("credentials_path", "")).strip())
        if action == "status":
            return _status()
        if action == "disconnect":
            clear_credentials(_TOKEN_KEY, _ACCOUNT_KEY)
            return "The local Google Calendar connection was removed from JARVIS."
        if action in ("list", "search"):
            return _list(params)
        if action == "create":
            return _create(params)
        if action == "update":
            return _update(params)
        if action == "delete":
            return _delete(params)
        return f"Unknown Calendar action: {action}"
    except IntegrationError as exc:
        return str(exc)
    except Exception as exc:
        return f"Google Calendar action failed: {exc}"
