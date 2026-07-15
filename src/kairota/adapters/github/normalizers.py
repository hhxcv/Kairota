from __future__ import annotations

from typing import Any

from kairota.adapters.github.models import GitHubIssueSnapshot, GitHubProjectSnapshot

JsonObject = dict[str, Any]


def normalize_project(payload: JsonObject) -> GitHubProjectSnapshot:
    return GitHubProjectSnapshot(
        provider_repo_id=str(payload["id"]),
        name=str(payload["full_name"]),
    )


def normalize_issue(payload: JsonObject) -> GitHubIssueSnapshot:
    return GitHubIssueSnapshot(
        number=int(payload["number"]),
        provider_issue_id=str(payload["id"]),
        title=str(payload["title"]),
        url=str(payload["html_url"]),
        state=str(payload["state"]),
        updated_at=optional_str(payload.get("updated_at")),
    )


def optional_str(value: object) -> str | None:
    return str(value) if value not in (None, "") else None
