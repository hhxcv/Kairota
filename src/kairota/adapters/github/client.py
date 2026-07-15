from __future__ import annotations

from typing import Any

import httpx

from kairota.adapters.github.models import (
    GitHubClient,
    GitHubProjectConfig,
    GitHubSyncSnapshot,
)
from kairota.adapters.github.normalizers import normalize_issue, normalize_project
from kairota.config import Settings

JsonObject = dict[str, Any]


class GitHubHttpClient:
    def __init__(
        self,
        *,
        api_url: str,
        token: str | None = None,
        timeout_seconds: float = 20.0,
        max_pages: int = 20,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.max_pages = max_pages

    @classmethod
    def from_settings(cls, settings: Settings) -> GitHubHttpClient:
        return cls(api_url=settings.github_api_url, token=settings.github_token)

    def fetch_project_snapshot(
        self,
        project: GitHubProjectConfig,
        *,
        issue_numbers: tuple[int, ...] = (),
    ) -> GitHubSyncSnapshot:
        repo_path = f"{project.owner}/{project.name}"
        project_snapshot = normalize_project(self.get(f"/repos/{repo_path}"))
        if issue_numbers:
            payloads = [
                self.get(f"/repos/{repo_path}/issues/{number}")
                for number in sorted(set(issue_numbers))
            ]
        else:
            payloads = self.get_list(
                f"/repos/{repo_path}/issues?state=all&per_page=100"
            )
        issues = tuple(
            normalize_issue(payload)
            for payload in payloads
            if "pull_request" not in payload
        )
        return GitHubSyncSnapshot(project=project_snapshot, issues=issues)

    def get(self, path: str) -> JsonObject:
        payload = self.get_json(path)
        if not isinstance(payload, dict):
            raise TypeError("GitHub response was not a JSON object.")
        return payload

    def get_list(self, path: str) -> list[JsonObject]:
        items: list[JsonObject] = []
        next_url: str | None = f"{self.api_url}{path}"
        for _page in range(self.max_pages):
            if next_url is None:
                break
            response = httpx.get(
                next_url,
                headers=self.headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise TypeError("GitHub response was not a JSON list.")
            items.extend(item for item in payload if isinstance(item, dict))
            next_url = response.links.get("next", {}).get("url")
        if next_url is not None:
            raise RuntimeError(
                "GitHub Issue pagination exceeded the configured safety limit."
            )
        return items

    def get_json(self, path: str) -> object:
        response = httpx.get(
            f"{self.api_url}{path}",
            headers=self.headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    @property
    def headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "kairota-sync",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers


def ensure_github_client(
    client: GitHubClient | None, settings: Settings
) -> GitHubClient:
    return client if client is not None else GitHubHttpClient.from_settings(settings)
