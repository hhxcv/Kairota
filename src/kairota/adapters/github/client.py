from __future__ import annotations

from typing import Any

import httpx

from kairota.adapters.github.models import (
    GitHubClient,
    GitHubRepositoryConfig,
    GitHubSyncSnapshot,
)
from kairota.adapters.github.normalizers import (
    normalize_check_run,
    normalize_commit_status,
    normalize_issue,
    normalize_pull_request,
    normalize_repository,
)
from kairota.config import Settings

JsonObject = dict[str, Any]


class GitHubHttpClient:
    def __init__(
        self,
        *,
        api_url: str,
        token: str | None = None,
        timeout_seconds: float = 20.0,
        max_pages: int = 10,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.max_pages = max_pages

    @classmethod
    def from_settings(cls, settings: Settings) -> GitHubHttpClient:
        return cls(api_url=settings.github_api_url, token=settings.github_token)

    def fetch_repository_snapshot(
        self,
        repository: GitHubRepositoryConfig,
        cursor: str | None = None,
    ) -> GitHubSyncSnapshot:
        del cursor
        repo_path = f"{repository.owner}/{repository.name}"
        repo_payload = self.get(f"/repos/{repo_path}")
        repository_snapshot = normalize_repository(repo_payload)

        issue_payloads = [
            payload
            for payload in self.get_list(
                f"/repos/{repo_path}/issues?state=all&per_page=100"
            )
            if "pull_request" not in payload
        ]
        pull_request_payloads = self.get_list(
            f"/repos/{repo_path}/pulls?state=all&per_page=100"
        )

        issues = tuple(normalize_issue(payload) for payload in issue_payloads)
        pull_requests = tuple(
            normalize_pull_request(payload) for payload in pull_request_payloads
        )
        checks = []
        for pull_request in pull_requests:
            if not pull_request.head_sha:
                continue
            check_runs = self.get_list(
                f"/repos/{repo_path}/commits/{pull_request.head_sha}/check-runs"
            )
            for check_run in check_runs:
                check = normalize_check_run(
                    check_run,
                    pull_request_number=pull_request.number,
                )
                if check is not None:
                    checks.append(check)

            statuses = self.get_list(
                f"/repos/{repo_path}/commits/{pull_request.head_sha}/statuses"
            )
            checks.extend(
                normalize_commit_status(
                    status,
                    pull_request_number=pull_request.number,
                    head_sha_value=pull_request.head_sha,
                )
                for status in statuses
            )

        return GitHubSyncSnapshot(
            repository=repository_snapshot,
            issues=issues,
            pull_requests=pull_requests,
            checks=tuple(checks),
            reviews=(),
            next_cursor=None,
        )

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
            items.extend(list_items(payload))
            next_url = response.links.get("next", {}).get("url")
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


def list_items(payload: object) -> list[JsonObject]:
    if isinstance(payload, dict) and isinstance(payload.get("check_runs"), list):
        return [item for item in payload["check_runs"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise TypeError("GitHub response was not a JSON list.")


def ensure_github_client(
    client: GitHubClient | None,
    settings: Settings,
) -> GitHubClient:
    if client is not None:
        return client
    return GitHubHttpClient.from_settings(settings)
