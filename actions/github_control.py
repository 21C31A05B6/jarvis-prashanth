"""GitHub integration using a Personal Access Token (fine-grained or
classic) stored in the OS keychain. Uses the REST API directly via
``requests`` — no extra SDK dependency needed.
"""

from __future__ import annotations

from actions._integration_common import (
    IntegrationError, bounded_limit, load_secret, save_secret, clear_secret, http_error_message,
)

_TOKEN_KEY = "github_pat"
_LOGIN_KEY = "github_login"
_API = "https://api.github.com"


def _requests():
    try:
        import requests
        return requests
    except ImportError as exc:
        raise IntegrationError("The 'requests' package is required for GitHub integration.") from exc


def _headers() -> dict:
    token = load_secret(_TOKEN_KEY)
    if not token:
        raise IntegrationError("GitHub is not connected. Say 'connect GitHub' and provide a personal access token.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _connect(params: dict) -> str:
    token = str(params.get("token") or params.get("access_token") or "").strip()
    if not token:
        return (
            "To connect GitHub, create a personal access token at "
            "https://github.com/settings/tokens (repo + read:org scopes are enough for most tasks) "
            "and pass it as 'token'."
        )
    requests = _requests()
    try:
        resp = requests.get(f"{_API}/user", headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }, timeout=15)
        resp.raise_for_status()
        login = resp.json().get("login", "")
    except Exception as exc:
        return f"GitHub token validation failed: {exc}"
    save_secret(_TOKEN_KEY, token)
    save_secret(_LOGIN_KEY, login)
    return f"GitHub connected as {login}."


def _status() -> str:
    login = load_secret(_LOGIN_KEY)
    token = load_secret(_TOKEN_KEY)
    if not token:
        return "GitHub is not connected. Say 'connect GitHub' with a personal access token."
    return f"GitHub is connected as {login or '(unknown user)'}."


def _disconnect() -> str:
    clear_secret(_TOKEN_KEY)
    clear_secret(_LOGIN_KEY)
    return "The local GitHub connection was removed from JARVIS. Revoke the token on GitHub if you want it fully invalidated."


def _repo_arg(params: dict) -> str:
    repo = str(params.get("repo") or params.get("repository") or "").strip()
    if not repo:
        raise IntegrationError("A 'repo' in owner/name form (e.g. octocat/Hello-World) is required.")
    return repo


def _list_repos(params: dict) -> str:
    requests = _requests()
    limit = bounded_limit(params.get("limit", 10), maximum=30)
    org = str(params.get("org") or "").strip()
    url = f"{_API}/orgs/{org}/repos" if org else f"{_API}/user/repos"
    try:
        resp = requests.get(url, headers=_headers(), params={"per_page": limit, "sort": "updated"}, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        return http_error_message("GitHub", exc)
    repos = resp.json()
    if not repos:
        return "No repositories found."
    lines = [f"- {r['full_name']} ({'private' if r.get('private') else 'public'}) — {r.get('description') or 'no description'}" for r in repos]
    return "Repositories:\n" + "\n".join(lines)


def _list_issues(params: dict) -> str:
    requests = _requests()
    repo = _repo_arg(params)
    limit = bounded_limit(params.get("limit", 10), maximum=30)
    state = str(params.get("state") or "open").strip().lower()
    try:
        resp = requests.get(
            f"{_API}/repos/{repo}/issues", headers=_headers(),
            params={"state": state, "per_page": limit}, timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        return http_error_message("GitHub", exc)
    issues = [i for i in resp.json() if "pull_request" not in i]
    if not issues:
        return f"No {state} issues found in {repo}."
    lines = [f"- #{i['number']} {i['title']} (by {i['user']['login']})" for i in issues]
    return f"{state.capitalize()} issues in {repo}:\n" + "\n".join(lines)


def _create_issue(params: dict) -> str:
    requests = _requests()
    repo = _repo_arg(params)
    title = str(params.get("title") or "").strip()
    if not title:
        return "An issue title is required."
    body = {"title": title, "body": params.get("body") or ""}
    labels = params.get("labels")
    if labels:
        body["labels"] = [l.strip() for l in str(labels).split(",") if l.strip()]
    try:
        resp = requests.post(f"{_API}/repos/{repo}/issues", headers=_headers(), json=body, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        return http_error_message("GitHub", exc)
    issue = resp.json()
    return f"Created issue #{issue['number']}: {issue['html_url']}"


def _comment_issue(params: dict) -> str:
    requests = _requests()
    repo = _repo_arg(params)
    number = str(params.get("issue_number") or params.get("number") or "").strip()
    comment = str(params.get("comment") or params.get("body") or "").strip()
    if not number or not comment:
        return "Both issue_number and comment text are required."
    try:
        resp = requests.post(
            f"{_API}/repos/{repo}/issues/{number}/comments", headers=_headers(),
            json={"body": comment}, timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        return http_error_message("GitHub", exc)
    return f"Comment posted on {repo}#{number}."


def _create_pr(params: dict) -> str:
    requests = _requests()
    repo = _repo_arg(params)
    title = str(params.get("title") or "").strip()
    head = str(params.get("head") or params.get("branch") or "").strip()
    base = str(params.get("base") or "main").strip()
    if not title or not head:
        return "A title and head branch are required to open a pull request."
    body = {"title": title, "head": head, "base": base, "body": params.get("body") or ""}
    try:
        resp = requests.post(f"{_API}/repos/{repo}/pulls", headers=_headers(), json=body, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        return http_error_message("GitHub", exc)
    pr = resp.json()
    return f"Opened pull request #{pr['number']}: {pr['html_url']}"


def _list_prs(params: dict) -> str:
    requests = _requests()
    repo = _repo_arg(params)
    limit = bounded_limit(params.get("limit", 10), maximum=30)
    state = str(params.get("state") or "open").strip().lower()
    try:
        resp = requests.get(
            f"{_API}/repos/{repo}/pulls", headers=_headers(),
            params={"state": state, "per_page": limit}, timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        return http_error_message("GitHub", exc)
    prs = resp.json()
    if not prs:
        return f"No {state} pull requests found in {repo}."
    lines = [f"- #{p['number']} {p['title']} ({p['head']['ref']} → {p['base']['ref']})" for p in prs]
    return f"{state.capitalize()} pull requests in {repo}:\n" + "\n".join(lines)


def _get_file(params: dict) -> str:
    import base64
    requests = _requests()
    repo = _repo_arg(params)
    path = str(params.get("path") or "").strip()
    ref = params.get("ref")
    if not path:
        return "A file path within the repo is required."
    try:
        resp = requests.get(
            f"{_API}/repos/{repo}/contents/{path}", headers=_headers(),
            params={"ref": ref} if ref else {}, timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        return http_error_message("GitHub", exc)
    data = resp.json()
    if isinstance(data, list):
        return "That path is a directory:\n" + "\n".join(f"- {f['name']}" for f in data)
    content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
    if len(content) > 4000:
        content = content[:4000] + "\n... (truncated)"
    return f"{path}:\n```\n{content}\n```"


def _search_code(params: dict) -> str:
    requests = _requests()
    query = str(params.get("query") or "").strip()
    if not query:
        return "A search query is required."
    repo = params.get("repo")
    q = f"{query} repo:{repo}" if repo else query
    try:
        resp = requests.get(f"{_API}/search/code", headers=_headers(), params={"q": q}, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        return http_error_message("GitHub", exc)
    items = resp.json().get("items", [])[:bounded_limit(params.get("limit", 10), maximum=20)]
    if not items:
        return "No matching code found."
    lines = [f"- {i['repository']['full_name']}: {i['path']}" for i in items]
    return "Code search results:\n" + "\n".join(lines)


def github_control(parameters: dict | None = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action", "status")).lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {"login": "connect", "authorize": "connect", "logout": "disconnect", "repos": "list_repos", "issues": "list_issues", "prs": "list_prs", "pulls": "list_prs"}
    action = aliases.get(action, action)
    if player:
        player.write_log(f"[GitHub] {action}")

    try:
        if action == "connect":
            return _connect(params)
        if action == "status":
            return _status()
        if action == "disconnect":
            return _disconnect()
        if action == "list_repos":
            return _list_repos(params)
        if action == "list_issues":
            return _list_issues(params)
        if action == "create_issue":
            return _create_issue(params)
        if action == "comment_issue":
            return _comment_issue(params)
        if action == "create_pr":
            return _create_pr(params)
        if action == "list_prs":
            return _list_prs(params)
        if action == "get_file":
            return _get_file(params)
        if action == "search_code":
            return _search_code(params)
        return f"Unknown GitHub action: {action}"
    except IntegrationError as exc:
        return str(exc)
    except Exception as exc:
        return f"GitHub action failed: {exc}"
