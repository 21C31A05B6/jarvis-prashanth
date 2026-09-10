"""Generic cloud storage integration, supporting multiple providers behind
one tool so JARVIS can move files to/from the cloud regardless of which
service the user has:
  - "s3": Amazon S3 (or any S3-compatible endpoint), via boto3.
  - "dropbox": Dropbox, via its plain REST API (no SDK dependency needed).

Google Drive has its own richer tool (``actions/drive_control.py``); use
that for Drive-specific work like sharing and Google Docs export.
"""

from __future__ import annotations

from pathlib import Path

from actions._integration_common import (
    IntegrationError, load_secret, save_secret, save_json_secret, load_json_secret,
    clear_secret, missing_dependency,
)

_S3_CREDS_KEY = "cloud_s3_credentials"
_DROPBOX_TOKEN_KEY = "cloud_dropbox_token"


def _requests():
    try:
        import requests
        return requests
    except ImportError as exc:
        raise IntegrationError("The 'requests' package is required for Dropbox integration.") from exc


# ---------------------------------------------------------------- S3 -----

def _s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise missing_dependency("boto3", "Amazon S3") from exc
    creds = load_json_secret(_S3_CREDS_KEY)
    if not creds:
        raise IntegrationError("S3 is not connected. Say 'connect cloud storage' (provider=s3) with your credentials.")
    kwargs = {
        "aws_access_key_id": creds.get("access_key_id"),
        "aws_secret_access_key": creds.get("secret_access_key"),
        "region_name": creds.get("region") or "us-east-1",
    }
    if creds.get("endpoint_url"):
        kwargs["endpoint_url"] = creds["endpoint_url"]
    return boto3.client("s3", **kwargs), creds.get("bucket", "")


def _s3_connect(params: dict) -> str:
    access_key = str(params.get("access_key_id") or "").strip()
    secret_key = str(params.get("secret_access_key") or "").strip()
    bucket = str(params.get("bucket") or "").strip()
    if not access_key or not secret_key or not bucket:
        return "S3 needs access_key_id, secret_access_key, and bucket (region and endpoint_url are optional)."
    try:
        import boto3
    except ImportError as exc:
        return str(missing_dependency("boto3", "Amazon S3"))
    creds = {
        "access_key_id": access_key,
        "secret_access_key": secret_key,
        "bucket": bucket,
        "region": params.get("region") or "us-east-1",
        "endpoint_url": params.get("endpoint_url") or "",
    }
    try:
        kwargs = {
            "aws_access_key_id": access_key, "aws_secret_access_key": secret_key,
            "region_name": creds["region"],
        }
        if creds["endpoint_url"]:
            kwargs["endpoint_url"] = creds["endpoint_url"]
        client = boto3.client("s3", **kwargs)
        client.list_objects_v2(Bucket=bucket, MaxKeys=1)
    except Exception as exc:
        return f"S3 connection test failed: {exc}"
    save_json_secret(_S3_CREDS_KEY, creds)
    return f"S3 connected to bucket '{bucket}'."


def _s3_list(params: dict) -> str:
    client, bucket = _s3_client()
    prefix = str(params.get("prefix") or params.get("query") or "")
    try:
        resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=50)
    except Exception as exc:
        return f"Could not list S3 objects: {exc}"
    objects = resp.get("Contents", [])
    if not objects:
        return f"No objects found in s3://{bucket}/{prefix}"
    lines = [f"- {o['Key']} ({o['Size']} bytes)" for o in objects]
    return f"Objects in s3://{bucket}:\n" + "\n".join(lines)


def _s3_upload(params: dict) -> str:
    client, bucket = _s3_client()
    file_path = str(params.get("file_path") or "").strip()
    if not file_path or not Path(file_path).is_file():
        return "A valid local file_path is required."
    key = str(params.get("key") or Path(file_path).name)
    try:
        client.upload_file(file_path, bucket, key)
    except Exception as exc:
        return f"Upload failed: {exc}"
    return f"Uploaded to s3://{bucket}/{key}."


def _s3_download(params: dict) -> str:
    client, bucket = _s3_client()
    key = str(params.get("key") or "").strip()
    if not key:
        return "An object 'key' is required."
    dest = str(params.get("destination") or "").strip() or str(Path.home() / "Downloads" / Path(key).name)
    try:
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        client.download_file(bucket, key, dest)
    except Exception as exc:
        return f"Download failed: {exc}"
    return f"Downloaded s3://{bucket}/{key} to {dest}."


def _s3_delete(params: dict) -> str:
    client, bucket = _s3_client()
    key = str(params.get("key") or "").strip()
    if not key:
        return "An object 'key' is required."
    try:
        client.delete_object(Bucket=bucket, Key=key)
    except Exception as exc:
        return f"Delete failed: {exc}"
    return f"Deleted s3://{bucket}/{key}."


# ----------------------------------------------------------- Dropbox -----

def _dropbox_headers() -> dict:
    token = load_secret(_DROPBOX_TOKEN_KEY)
    if not token:
        raise IntegrationError("Dropbox is not connected. Say 'connect cloud storage' (provider=dropbox) with an access token.")
    return {"Authorization": f"Bearer {token}"}


def _dropbox_connect(params: dict) -> str:
    token = str(params.get("access_token") or params.get("token") or "").strip()
    if not token:
        return (
            "Dropbox needs an access_token. Create an app at https://www.dropbox.com/developers/apps, "
            "generate an access token (or set up OAuth for a refresh token), and pass it as "
            "'access_token'."
        )
    requests = _requests()
    try:
        resp = requests.post(
            "https://api.dropboxapi.com/2/users/get_current_account",
            headers={"Authorization": f"Bearer {token}"}, timeout=15,
        )
        resp.raise_for_status()
        info = resp.json()
    except Exception as exc:
        return f"Dropbox token validation failed: {exc}"
    save_secret(_DROPBOX_TOKEN_KEY, token)
    return f"Dropbox connected as {info.get('email', 'unknown account')}."


def _dropbox_list(params: dict) -> str:
    requests = _requests()
    path = str(params.get("prefix") or params.get("path") or "")
    try:
        resp = requests.post(
            "https://api.dropboxapi.com/2/files/list_folder",
            headers={**_dropbox_headers(), "Content-Type": "application/json"},
            json={"path": path}, timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        return f"Could not list Dropbox files: {exc}"
    entries = resp.json().get("entries", [])
    if not entries:
        return f"No files found in Dropbox path '{path or '/'}'."
    lines = [f"- {e['name']} ({e.get('.tag', 'file')})" for e in entries]
    return "Dropbox files:\n" + "\n".join(lines)


def _dropbox_upload(params: dict) -> str:
    requests = _requests()
    file_path = str(params.get("file_path") or "").strip()
    if not file_path or not Path(file_path).is_file():
        return "A valid local file_path is required."
    dest = str(params.get("key") or params.get("path") or f"/{Path(file_path).name}")
    if not dest.startswith("/"):
        dest = "/" + dest
    try:
        data = Path(file_path).read_bytes()
        resp = requests.post(
            "https://content.dropboxapi.com/2/files/upload",
            headers={
                **_dropbox_headers(),
                "Dropbox-API-Arg": __import__("json").dumps({"path": dest, "mode": "overwrite"}),
                "Content-Type": "application/octet-stream",
            },
            data=data, timeout=60,
        )
        resp.raise_for_status()
    except Exception as exc:
        return f"Upload failed: {exc}"
    return f"Uploaded to Dropbox:{dest}."


def _dropbox_download(params: dict) -> str:
    requests = _requests()
    src = str(params.get("key") or params.get("path") or "").strip()
    if not src:
        return "A Dropbox path is required."
    if not src.startswith("/"):
        src = "/" + src
    dest = str(params.get("destination") or "").strip() or str(Path.home() / "Downloads" / Path(src).name)
    try:
        resp = requests.post(
            "https://content.dropboxapi.com/2/files/download",
            headers={**_dropbox_headers(), "Dropbox-API-Arg": __import__("json").dumps({"path": src})},
            timeout=60,
        )
        resp.raise_for_status()
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(resp.content)
    except Exception as exc:
        return f"Download failed: {exc}"
    return f"Downloaded Dropbox:{src} to {dest}."


def _dropbox_delete(params: dict) -> str:
    requests = _requests()
    path = str(params.get("key") or params.get("path") or "").strip()
    if not path:
        return "A Dropbox path is required."
    if not path.startswith("/"):
        path = "/" + path
    try:
        resp = requests.post(
            "https://api.dropboxapi.com/2/files/delete_v2",
            headers={**_dropbox_headers(), "Content-Type": "application/json"},
            json={"path": path}, timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        return f"Delete failed: {exc}"
    return f"Deleted Dropbox:{path}."


# --------------------------------------------------------- dispatcher -----

def _provider(params: dict) -> str:
    p = str(params.get("provider") or "").strip().lower()
    if p in ("s3", "aws", "amazon"):
        return "s3"
    if p in ("dropbox", "db"):
        return "dropbox"
    if not p:
        if load_secret(_DROPBOX_TOKEN_KEY) and not load_json_secret(_S3_CREDS_KEY):
            return "dropbox"
        return "s3"
    return p


def cloud_storage(parameters: dict | None = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action", "status")).lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {"login": "connect", "authorize": "connect", "logout": "disconnect", "ls": "list"}
    action = aliases.get(action, action)
    provider = _provider(params)
    if player:
        player.write_log(f"[CloudStorage] {provider} // {action}")

    try:
        if action == "connect":
            return _s3_connect(params) if provider == "s3" else _dropbox_connect(params)
        if action == "status":
            s3_ok = bool(load_json_secret(_S3_CREDS_KEY))
            db_ok = bool(load_secret(_DROPBOX_TOKEN_KEY))
            if not s3_ok and not db_ok:
                return "No cloud storage provider is connected. Say 'connect cloud storage' with provider=s3 or provider=dropbox."
            parts = []
            if s3_ok:
                parts.append(f"S3 connected (bucket: {load_json_secret(_S3_CREDS_KEY).get('bucket')})")
            if db_ok:
                parts.append("Dropbox connected")
            return "; ".join(parts) + "."
        if action == "disconnect":
            if provider == "s3":
                clear_secret(_S3_CREDS_KEY)
                return "S3 connection removed."
            clear_secret(_DROPBOX_TOKEN_KEY)
            return "Dropbox connection removed."
        if action == "list":
            return _s3_list(params) if provider == "s3" else _dropbox_list(params)
        if action == "upload":
            return _s3_upload(params) if provider == "s3" else _dropbox_upload(params)
        if action == "download":
            return _s3_download(params) if provider == "s3" else _dropbox_download(params)
        if action == "delete":
            return _s3_delete(params) if provider == "s3" else _dropbox_delete(params)
        return f"Unknown cloud storage action: {action}"
    except IntegrationError as exc:
        return str(exc)
    except Exception as exc:
        return f"Cloud storage action failed: {exc}"
