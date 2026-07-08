from __future__ import annotations

import re
from typing import Any

from kairota.adapters.github.models import (
    GitHubCheckSnapshot,
    GitHubIssueSnapshot,
    GitHubPullRequestSnapshot,
    GitHubRepositorySnapshot,
    GitHubReviewSnapshot,
)
from kairota.contracts.enums import (
    CheckConclusion,
    CheckStatus,
    PullRequestState,
    ReviewGateState,
)

JsonObject = dict[str, Any]

CLOSING_ISSUE_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(?P<number>\d+)\b",
    re.IGNORECASE,
)


def normalize_repository(payload: JsonObject) -> GitHubRepositorySnapshot:
    full_name = str(payload.get("full_name") or payload.get("name") or "")
    provider_id = str(payload.get("id") or full_name)
    default_branch = str(payload.get("default_branch") or "main")
    return GitHubRepositorySnapshot(
        provider_repo_id=provider_id,
        name=full_name,
        default_branch=default_branch,
    )


def normalize_issue(payload: JsonObject) -> GitHubIssueSnapshot:
    number = int(payload["number"])
    return GitHubIssueSnapshot(
        number=number,
        provider_issue_id=str(payload.get("id") or number),
        title=str(payload.get("title") or f"Issue #{number}"),
        url=str(payload.get("html_url") or payload.get("url") or ""),
        state=str(payload.get("state") or "open"),
        updated_at=optional_str(payload.get("updated_at")),
    )


def normalize_pull_request(payload: JsonObject) -> GitHubPullRequestSnapshot:
    number = int(payload["number"])
    state = pull_request_state(payload)
    body = optional_str(payload.get("body")) or ""
    return GitHubPullRequestSnapshot(
        number=number,
        provider_pr_id=str(payload.get("id") or number),
        url=str(payload.get("html_url") or payload.get("url") or ""),
        state=state,
        draft=bool(payload.get("draft", False)),
        head_branch=head_ref(payload),
        head_sha=head_sha(payload),
        merged=bool(payload.get("merged", False)) or state == PullRequestState.MERGED,
        merge_commit_sha=optional_str(payload.get("merge_commit_sha")),
        linked_issue_numbers=linked_issue_numbers(body),
        updated_at=optional_str(payload.get("updated_at")),
    )


def normalize_check_run(
    payload: JsonObject,
    *,
    pull_request_number: int | None = None,
) -> GitHubCheckSnapshot | None:
    pr_number = pull_request_number or first_pull_request_number(payload)
    if pr_number is None:
        return None
    return GitHubCheckSnapshot(
        pull_request_number=pr_number,
        name=str(payload.get("name") or "check_run"),
        status=check_status(str(payload.get("status") or "unknown")),
        conclusion=check_conclusion(optional_str(payload.get("conclusion"))),
        head_sha=optional_str(payload.get("head_sha")),
        required=bool(payload.get("required", False)),
        details_url=optional_str(payload.get("details_url") or payload.get("html_url")),
    )


def normalize_commit_status(
    payload: JsonObject,
    *,
    pull_request_number: int,
    head_sha_value: str | None,
) -> GitHubCheckSnapshot:
    state = str(payload.get("state") or "pending")
    return GitHubCheckSnapshot(
        pull_request_number=pull_request_number,
        name=str(payload.get("context") or "status"),
        status=status_check_status(state),
        conclusion=status_check_conclusion(state),
        head_sha=head_sha_value or optional_str(payload.get("sha")),
        required=bool(payload.get("required", False)),
        details_url=optional_str(payload.get("target_url")),
    )


def normalize_review_summary(
    pull_request_number: int,
    *,
    reviews: tuple[JsonObject, ...] = (),
    review_threads: tuple[JsonObject, ...] = (),
    head_sha_value: str | None = None,
) -> GitHubReviewSnapshot:
    unresolved_count = sum(
        1 for thread in review_threads if not bool(thread.get("isResolved"))
    )
    states = [str(review.get("state") or "").upper() for review in reviews]
    if unresolved_count > 0:
        state = ReviewGateState.UNRESOLVED_THREADS
    elif "CHANGES_REQUESTED" in states:
        state = ReviewGateState.CHANGES_REQUESTED
    elif "APPROVED" in states:
        state = ReviewGateState.APPROVED
    elif states:
        state = ReviewGateState.WAITING
    else:
        state = ReviewGateState.UNKNOWN

    return GitHubReviewSnapshot(
        pull_request_number=pull_request_number,
        state=state,
        unresolved_count=unresolved_count,
        head_sha=head_sha_value,
        summary={
            "review_count": len(reviews),
            "thread_count": len(review_threads),
        },
    )


def linked_issue_numbers(body: str) -> tuple[int, ...]:
    numbers = {int(match.group("number")) for match in CLOSING_ISSUE_RE.finditer(body)}
    return tuple(sorted(numbers))


def pull_request_state(payload: JsonObject) -> PullRequestState:
    if bool(payload.get("merged", False)):
        return PullRequestState.MERGED
    state = str(payload.get("state") or "open")
    if state == "closed":
        return PullRequestState.CLOSED
    return PullRequestState.OPEN


def head_ref(payload: JsonObject) -> str | None:
    head = payload.get("head")
    if isinstance(head, dict):
        return optional_str(head.get("ref"))
    return None


def head_sha(payload: JsonObject) -> str | None:
    head = payload.get("head")
    if isinstance(head, dict):
        return optional_str(head.get("sha"))
    return None


def first_pull_request_number(payload: JsonObject) -> int | None:
    pull_requests = payload.get("pull_requests")
    if not isinstance(pull_requests, list) or not pull_requests:
        return None
    first = pull_requests[0]
    if not isinstance(first, dict) or "number" not in first:
        return None
    return int(first["number"])


def check_status(value: str) -> CheckStatus:
    if value == "queued":
        return CheckStatus.QUEUED
    if value == "in_progress":
        return CheckStatus.IN_PROGRESS
    if value == "completed":
        return CheckStatus.COMPLETED
    return CheckStatus.UNKNOWN


def check_conclusion(value: str | None) -> CheckConclusion:
    if value is None:
        return CheckConclusion.UNKNOWN
    try:
        return CheckConclusion(value)
    except ValueError:
        return CheckConclusion.UNKNOWN


def status_check_status(state: str) -> CheckStatus:
    if state == "pending":
        return CheckStatus.IN_PROGRESS
    return CheckStatus.COMPLETED


def status_check_conclusion(state: str) -> CheckConclusion:
    if state == "success":
        return CheckConclusion.SUCCESS
    if state == "failure":
        return CheckConclusion.FAILURE
    if state == "error":
        return CheckConclusion.ACTION_REQUIRED
    if state == "pending":
        return CheckConclusion.UNKNOWN
    return CheckConclusion.UNKNOWN


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
