from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class GitHubProjectConfig:
    owner: str
    name: str
    provider_repo_id: str


@dataclass(frozen=True)
class GitHubProjectSnapshot:
    provider_repo_id: str
    name: str


@dataclass(frozen=True)
class GitHubIssueSnapshot:
    number: int
    provider_issue_id: str
    title: str
    url: str
    state: str
    updated_at: str | None = None


@dataclass(frozen=True)
class GitHubSyncSnapshot:
    project: GitHubProjectSnapshot
    issues: tuple[GitHubIssueSnapshot, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GitHubWebhookEvent:
    delivery_id: str
    event_type: str
    action: str | None
    project_name: str
    provider_repo_id: str
    issue_number: int
    payload_hash: str


class GitHubClient(Protocol):
    def fetch_project_snapshot(
        self,
        project: GitHubProjectConfig,
        *,
        issue_numbers: tuple[int, ...] = (),
    ) -> GitHubSyncSnapshot: ...
