from kairota.adapters.github.normalizers import (
    linked_issue_numbers,
    normalize_check_run,
    normalize_commit_status,
    normalize_pull_request,
    normalize_review_summary,
)
from kairota.contracts.enums import (
    CheckConclusion,
    CheckStatus,
    PullRequestState,
    ReviewGateState,
)


def test_pull_request_normalizer_extracts_closing_issue_numbers() -> None:
    pull_request = normalize_pull_request(
        {
            "id": 99,
            "number": 5,
            "html_url": "https://example.test/pull/5",
            "state": "open",
            "draft": False,
            "body": "Fixes #12 and resolves #7",
            "head": {"ref": "feature", "sha": "abc123"},
        }
    )

    assert pull_request.provider_pr_id == "99"
    assert pull_request.state == PullRequestState.OPEN
    assert pull_request.linked_issue_numbers == (7, 12)
    assert linked_issue_numbers("no link") == ()


def test_check_and_status_normalizers_map_gate_state() -> None:
    check = normalize_check_run(
        {
            "id": 1,
            "name": "test",
            "status": "completed",
            "conclusion": "failure",
            "head_sha": "abc123",
            "pull_requests": [{"number": 5}],
        }
    )
    status = normalize_commit_status(
        {"context": "ci", "state": "pending", "target_url": "https://example.test"},
        pull_request_number=5,
        head_sha_value="abc123",
    )

    assert check is not None
    assert check.status == CheckStatus.COMPLETED
    assert check.conclusion == CheckConclusion.FAILURE
    assert status.status == CheckStatus.IN_PROGRESS
    assert status.conclusion == CheckConclusion.UNKNOWN


def test_review_normalizer_prefers_unresolved_threads() -> None:
    review = normalize_review_summary(
        5,
        reviews=({"state": "APPROVED"},),
        review_threads=({"id": "thread-1", "isResolved": False},),
        head_sha_value="abc123",
    )

    assert review.state == ReviewGateState.UNRESOLVED_THREADS
    assert review.unresolved_count == 1
    assert review.summary == {"review_count": 1, "thread_count": 1}
