"""Thin GitHub REST API client.

Uses the user's own personal access token (stored like the Gemini key, via
api/secret_service.py) rather than a GitHub OAuth App — building and
maintaining an OAuth App is a separate, deployment-specific setup step
(app registration, callback URL, client secret) that can't be provisioned
generically here. A PAT is real, scoped, revocable by the user at any time
from https://github.com/settings/tokens, and works immediately.
"""

from __future__ import annotations

import asyncio

import requests

API_BASE = "https://api.github.com"
TIMEOUT_SECONDS = 15


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "jarvis-os",
    }


def _raise_for_github_error(response: requests.Response) -> None:
    if response.status_code == 401:
        raise PermissionError("GitHub token is invalid or expired.")
    if response.status_code == 403:
        raise PermissionError("GitHub token lacks permission for this action, or the rate limit was hit.")
    if response.status_code == 404:
        raise LookupError("Not found on GitHub (check the owner/repo name and token scopes).")
    response.raise_for_status()


def _list_repos_sync(token: str) -> list[dict]:
    response = requests.get(
        f"{API_BASE}/user/repos",
        headers=_headers(token),
        params={"sort": "updated", "per_page": 30},
        timeout=TIMEOUT_SECONDS,
    )
    _raise_for_github_error(response)
    return [
        {
            "full_name": repo["full_name"],
            "description": repo.get("description") or "",
            "private": repo["private"],
            "default_branch": repo.get("default_branch", "main"),
            "open_issues": repo.get("open_issues_count", 0),
            "url": repo["html_url"],
        }
        for repo in response.json()
    ]


def _list_issues_sync(token: str, owner: str, repo: str, state: str) -> list[dict]:
    response = requests.get(
        f"{API_BASE}/repos/{owner}/{repo}/issues",
        headers=_headers(token),
        params={"state": state, "per_page": 30},
        timeout=TIMEOUT_SECONDS,
    )
    _raise_for_github_error(response)
    return [
        {
            "number": issue["number"],
            "title": issue["title"],
            "state": issue["state"],
            "url": issue["html_url"],
            "is_pull_request": "pull_request" in issue,
        }
        for issue in response.json()
    ]


def _create_issue_sync(token: str, owner: str, repo: str, title: str, body: str) -> dict:
    response = requests.post(
        f"{API_BASE}/repos/{owner}/{repo}/issues",
        headers=_headers(token),
        json={"title": title, "body": body},
        timeout=TIMEOUT_SECONDS,
    )
    _raise_for_github_error(response)
    issue = response.json()
    return {"number": issue["number"], "title": issue["title"], "url": issue["html_url"]}


async def list_repos(token: str) -> list[dict]:
    return await asyncio.to_thread(_list_repos_sync, token)


async def list_issues(token: str, owner: str, repo: str, state: str = "open") -> list[dict]:
    return await asyncio.to_thread(_list_issues_sync, token, owner, repo, state)


async def create_issue(token: str, owner: str, repo: str, title: str, body: str) -> dict:
    return await asyncio.to_thread(_create_issue_sync, token, owner, repo, title, body)
