from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from kairota.contracts.enums import (
    CheckConclusion,
    CheckStatus,
    PullRequestState,
    ReviewGateState,
)

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class GitHubRepositoryConfig:
    owner: str
    name: str
    provider_repo_id: str


@dataclass(frozen=True)
class GitHubRepositorySnapshot:
    provider_repo_id: str
    name: str
    default_branch: str


@dataclass(frozen=True)
class GitHubIssueSnapshot:
    number: int
    provider_issue_id: str
    title: str
    url: str
    state: str
    updated_at: str | None = None


@dataclass(frozen=True)
class GitHubPullRequestSnapshot:
    number: int
    provider_pr_id: str
    url: str
    state: PullRequestState
    draft: bool
    head_branch: str | None
    head_sha: str | None
    merged: bool
    merge_commit_sha: str | None = None
    linked_issue_numbers: tuple[int, ...] = field(default_factory=tuple)
    updated_at: str | None = None


@dataclass(frozen=True)
class GitHubCheckSnapshot:
    pull_request_number: int
    name: str
    status: CheckStatus
    conclusion: CheckConclusion
    head_sha: str | None
    required: bool = False
    details_url: str | None = None


@dataclass(frozen=True)
class GitHubReviewSnapshot:
    pull_request_number: int
    state: ReviewGateState
    unresolved_count: int = 0
    head_sha: str | None = None
    summary: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class GitHubSyncSnapshot:
    repository: GitHubRepositorySnapshot
    issues: tuple[GitHubIssueSnapshot, ...] = field(default_factory=tuple)
    pull_requests: tuple[GitHubPullRequestSnapshot, ...] = field(default_factory=tuple)
    checks: tuple[GitHubCheckSnapshot, ...] = field(default_factory=tuple)
    reviews: tuple[GitHubReviewSnapshot, ...] = field(default_factory=tuple)
    next_cursor: str | None = None


@dataclass(frozen=True)
class GitHubWebhookEvent:
    event_type: str
    delivery_id: str
    action: str | None
    external_id: str | None
    payload_hash: str
    snapshot: GitHubSyncSnapshot


class GitHubClient(Protocol):
    def fetch_repository_snapshot(
        self,
        repository: GitHubRepositoryConfig,
        cursor: str | None = None,
    ) -> GitHubSyncSnapshot:
        """Return one bounded repository snapshot for polling sync."""
        ...
