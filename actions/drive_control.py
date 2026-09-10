"""Google Drive integration: connect via OAuth, list/search/upload/download/
share files. Shares the Google OAuth plumbing used by Calendar and Gmail.
"""

from __future__ import annotations

from pathlib import Path

from actions._integration_common import IntegrationError, bounded_limit, load_secret
from actions.google_oauth_common import connect_flow, get_service, clear_credentials

SCOPES = ("https://www.googleapis.com/auth/drive",)
_TOKEN_KEY = "gdrive_oauth_credentials"
_ACCOUNT_KEY = "gdrive_account_email"
_CLIENT_PATH_KEY = "google_oauth_client_path"


def _service():
    return get_service(api_service="drive", api_version="v3", scopes=SCOPES, token_key=_TOKEN_KEY)


def _account_lookup(service) -> str:
    about = service.about().get(fields="user").execute()
    return about.get("user", {}).get("emailAddress", "")


def _connect(credentials_path: str = "") -> str:
    return connect_flow(
        service_name="Google Drive",
        service_id="drive",
        api_service="drive",
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
        return "Google Drive is not connected. Say 'connect Google Drive' to start OAuth."
    try:
        service = _service()
        if not service:
            return "Google Drive was connected but the session expired. Reconnect it."
        return f"Google Drive is connected as {account}."
    except IntegrationError as exc:
        return str(exc)


def _require_service():
    service = _service()
    if not service:
        raise IntegrationError("Google Drive is not connected. Say 'connect Google Drive' first.")
    return service


def _fmt_file(f: dict) -> str:
    size = f.get("size")
    size_str = f" ({int(size) // 1024} KB)" if size else ""
    return f"- [{f.get('id')}] {f.get('name')}{size_str} — {f.get('mimeType', '')}"


def _list(params: dict) -> str:
    service = _require_service()
    limit = bounded_limit(params.get("limit", 10))
    query = str(params.get("query") or "").strip()
    q = f"name contains '{query}' and trashed = false" if query else "trashed = false"
    try:
        result = service.files().list(
            q=q, pageSize=limit, fields="files(id,name,mimeType,size,webViewLink)"
        ).execute()
    except Exception as exc:
        return f"Could not list Drive files: {exc}"
    files = result.get("files", [])
    if not files:
        return "No matching files found in Drive."
    return "Drive files:\n" + "\n".join(_fmt_file(f) for f in files)


def _upload(params: dict) -> str:
    service = _require_service()
    from googleapiclient.http import MediaFileUpload

    path = str(params.get("file_path") or "").strip()
    if not path or not Path(path).is_file():
        return "A valid local file_path is required to upload to Drive."
    folder_id = params.get("folder_id")
    metadata = {"name": params.get("name") or Path(path).name}
    if folder_id:
        metadata["parents"] = [folder_id]
    media = MediaFileUpload(path, resumable=True)
    try:
        uploaded = service.files().create(
            body=metadata, media_body=media, fields="id,name,webViewLink"
        ).execute()
    except Exception as exc:
        return f"Upload failed: {exc}"
    return f"Uploaded '{uploaded.get('name')}' to Drive: {uploaded.get('webViewLink', uploaded.get('id'))}"


def _download(params: dict) -> str:
    service = _require_service()
    import io
    from googleapiclient.http import MediaIoBaseDownload

    file_id = str(params.get("file_id") or "").strip()
    if not file_id:
        return "A file_id from a Drive list/search is required to download."
    dest = str(params.get("destination") or "").strip() or str(Path.home() / "Downloads" / file_id)
    try:
        meta = service.files().get(fileId=file_id, fields="name,mimeType").execute()
        if meta.get("mimeType", "").startswith("application/vnd.google-apps"):
            request = service.files().export_media(fileId=file_id, mimeType="application/pdf")
            dest_path = Path(dest if dest.endswith(".pdf") else f"{dest}.pdf")
        else:
            request = service.files().get_media(fileId=file_id)
            dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        buffer = io.FileIO(str(dest_path), "wb")
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _status_obj, done = downloader.next_chunk()
    except Exception as exc:
        return f"Download failed: {exc}"
    return f"Downloaded '{meta.get('name')}' to {dest_path}."


def _create_folder(params: dict) -> str:
    service = _require_service()
    name = str(params.get("name") or "").strip()
    if not name:
        return "A folder name is required."
    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if params.get("folder_id"):
        metadata["parents"] = [params["folder_id"]]
    try:
        folder = service.files().create(body=metadata, fields="id,name").execute()
    except Exception as exc:
        return f"Could not create folder: {exc}"
    return f"Created folder '{folder.get('name')}' ({folder.get('id')})."


def _share(params: dict) -> str:
    service = _require_service()
    file_id = str(params.get("file_id") or "").strip()
    email = str(params.get("email") or "").strip()
    role = str(params.get("role") or "reader").strip().lower()
    if role not in ("reader", "writer", "commenter"):
        role = "reader"
    if not file_id:
        return "A file_id is required to share."
    try:
        if email:
            service.permissions().create(
                fileId=file_id, body={"type": "user", "role": role, "emailAddress": email},
                sendNotificationEmail=True,
            ).execute()
        else:
            service.permissions().create(
                fileId=file_id, body={"type": "anyone", "role": role}
            ).execute()
        meta = service.files().get(fileId=file_id, fields="webViewLink").execute()
    except Exception as exc:
        return f"Sharing failed: {exc}"
    who = f" with {email}" if email else " with anyone who has the link"
    return f"Shared{who} ({role}): {meta.get('webViewLink')}"


def _delete(params: dict) -> str:
    service = _require_service()
    file_id = str(params.get("file_id") or "").strip()
    if not file_id:
        return "A file_id is required to delete."
    try:
        service.files().delete(fileId=file_id).execute()
    except Exception as exc:
        return f"Could not delete the file: {exc}"
    return "File deleted from Drive."


def drive_control(parameters: dict | None = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action", "list")).lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {"login": "connect", "authorize": "connect", "logout": "disconnect", "list_files": "list", "find": "search"}
    action = aliases.get(action, action)
    if player:
        player.write_log(f"[Drive] {action}")

    try:
        if action == "connect":
            return _connect(str(params.get("credentials_path", "")).strip())
        if action == "status":
            return _status()
        if action == "disconnect":
            clear_credentials(_TOKEN_KEY, _ACCOUNT_KEY)
            return "The local Google Drive connection was removed from JARVIS."
        if action in ("list", "search"):
            return _list(params)
        if action == "upload":
            return _upload(params)
        if action == "download":
            return _download(params)
        if action == "create_folder":
            return _create_folder(params)
        if action == "share":
            return _share(params)
        if action == "delete":
            return _delete(params)
        return f"Unknown Drive action: {action}"
    except IntegrationError as exc:
        return str(exc)
    except Exception as exc:
        return f"Google Drive action failed: {exc}"
