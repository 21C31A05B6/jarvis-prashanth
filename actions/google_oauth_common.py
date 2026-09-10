"""Shared Google OAuth (Desktop app flow) plumbing for Calendar and Drive.

Mirrors the pattern already used for Gmail in ``actions/email_control.py``:
a Google Cloud "Desktop app" OAuth client JSON is discovered on disk, the
user completes consent in a local-server browser flow, and the resulting
refresh token is stored only in the OS keychain (via ``core.secret_store``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from actions._integration_common import IntegrationError, load_secret, save_secret, clear_secret, missing_dependency


def google_dependencies():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        return Request, Credentials, InstalledAppFlow, build
    except ImportError as exc:
        raise missing_dependency(
            "google-api-python-client google-auth-httplib2 google-auth-oauthlib",
            "Google",
        ) from exc


def discover_client_path(explicit_path: str = "", env_var: str = "GOOGLE_OAUTH_CLIENT_FILE") -> Path | None:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    env_path = os.environ.get(env_var, "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())

    project = Path(__file__).resolve().parent.parent
    candidates.extend([
        project / "config" / "google_credentials.json",
        project / "config" / "gmail_credentials.json",
        project / "config" / "credentials.json",
        Path.home() / "Downloads" / "google_credentials.json",
        Path.home() / "Downloads" / "credentials.json",
    ])
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        try:
            candidates.extend(sorted(
                downloads.glob("client_secret_*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )[:5])
        except OSError:
            pass

    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        if _valid_client_file(resolved):
            return resolved
    return None


def _valid_client_file(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        installed = data.get("installed") if isinstance(data, dict) else None
        return bool(
            isinstance(installed, dict)
            and installed.get("client_id")
            and installed.get("auth_uri")
            and installed.get("token_uri")
        )
    except (OSError, ValueError, TypeError):
        return False


def save_credentials(token_key: str, credentials, client_path: str = "", client_path_key: str = "") -> bool:
    ok = save_secret(token_key, credentials.to_json())
    if client_path and client_path_key:
        save_secret(client_path_key, client_path)
    return ok


def load_credentials(token_key: str, scopes: tuple[str, ...]):
    Request, Credentials, _InstalledAppFlow, _build = google_dependencies()
    payload = load_secret(token_key)
    if not payload:
        return None
    try:
        credentials = Credentials.from_authorized_user_info(json.loads(payload), list(scopes))
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            save_credentials(token_key, credentials)
        if not credentials.valid:
            return None
        return credentials
    except Exception:
        return None


def clear_credentials(token_key: str, account_key: str = "") -> None:
    clear_secret(token_key)
    if account_key:
        clear_secret(account_key)


def connect_flow(
    *,
    service_name: str,
    service_id: str,
    api_service: str,
    api_version: str,
    scopes: tuple[str, ...],
    token_key: str,
    account_key: str,
    client_path_key: str,
    explicit_path: str = "",
    account_lookup=None,
) -> str:
    """Run the OAuth consent flow and persist credentials. Returns a status string."""
    try:
        _Request, _Credentials, InstalledAppFlow, build = google_dependencies()
    except IntegrationError as exc:
        return str(exc)

    saved_path = load_secret(client_path_key) or ""
    path = discover_client_path(explicit_path or saved_path)
    if not path:
        return (
            f"{service_name} needs a Google Desktop OAuth credentials JSON file. In Google Cloud: "
            f"enable the {service_name} API, configure the OAuth consent screen, create an OAuth "
            "Client ID with application type Desktop app, then download the JSON and either place it "
            "at config/google_credentials.json or pass its path as credentials_path."
        )
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(path), list(scopes))
        credentials = flow.run_local_server(port=0, open_browser=True, prompt="consent")
        service = build(api_service, api_version, credentials=credentials, cache_discovery=False)
        account = ""
        if account_lookup:
            try:
                account = account_lookup(service) or ""
            except Exception:
                account = ""
        save_credentials(token_key, credentials, str(path), client_path_key)
        if account:
            save_secret(account_key, account)
        who = f" as {account}" if account else ""
        return f"{service_name} connected{who}. JARVIS can now use {service_name} on your behalf."
    except Exception as exc:
        return f"{service_name} connection failed: {exc}"


def get_service(
    *,
    api_service: str,
    api_version: str,
    scopes: tuple[str, ...],
    token_key: str,
):
    _Request, _Credentials, _InstalledAppFlow, build = google_dependencies()
    credentials = load_credentials(token_key, scopes)
    if not credentials:
        return None
    return build(api_service, api_version, credentials=credentials, cache_discovery=False)
