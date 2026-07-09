import httpx

from kairota.adapters.github.client import GitHubHttpClient
from kairota.adapters.github.models import GitHubRepositoryConfig, GitHubSyncOptions
from kairota.contracts.enums import RepositoryIssueState, RepositorySyncMode


def test_repository_snapshot_uses_rest_without_native_review_calls(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        del kwargs
        calls.append(url)
        if url.endswith("/repos/owner/repo"):
            payload: object = {
                "id": 123,
                "full_name": "owner/repo",
                "default_branch": "main",
            }
        elif "/issues?" in url:
            payload = []
        elif "/pulls?" in url:
            payload = [
                {
                    "id": 5,
                    "number": 5,
                    "html_url": "https://example.test/pull/5",
                    "state": "open",
                    "draft": False,
                    "body": "Fixes #7",
                    "head": {"ref": "feature", "sha": "sha-1"},
                }
            ]
        elif url.endswith("/commits/sha-1/check-runs"):
            payload = {"check_runs": []}
        elif url.endswith("/commits/sha-1/statuses"):
            payload = []
        else:
            raise AssertionError(f"Unexpected GitHub REST call: {url}")
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    def fail_post(*args, **kwargs):
        del args, kwargs
        raise AssertionError("GitHub adapter must not call GraphQL.")

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fail_post)
    client = GitHubHttpClient(api_url="https://api.example.test", token="token")

    snapshot = client.fetch_repository_snapshot(
        GitHubRepositoryConfig(
            owner="owner",
            name="repo",
            provider_repo_id="owner/repo",
        )
    )

    assert len(snapshot.pull_requests) == 1
    assert snapshot.reviews == ()
    assert not any("/graphql" in call for call in calls)
    assert not any(call.endswith("/pulls/5/reviews") for call in calls)


def test_issue_only_snapshot_skips_pull_requests_and_checks(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        del kwargs
        calls.append(url)
        if url.endswith("/repos/owner/repo"):
            payload: object = {
                "id": 123,
                "full_name": "owner/repo",
                "default_branch": "main",
            }
        elif "/issues?" in url:
            payload = [
                {
                    "id": 7,
                    "number": 7,
                    "html_url": "https://example.test/issues/7",
                    "title": "Issue 7",
                    "state": "open",
                    "labels": [{"name": "kairota"}],
                },
                {
                    "id": 8,
                    "number": 8,
                    "html_url": "https://example.test/pull/8",
                    "title": "Pull 8",
                    "state": "open",
                    "pull_request": {},
                    "labels": [{"name": "kairota"}],
                },
            ]
        else:
            raise AssertionError(f"Unexpected GitHub REST call: {url}")
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    client = GitHubHttpClient(api_url="https://api.example.test", token="token")

    snapshot = client.fetch_repository_snapshot(
        GitHubRepositoryConfig(
            owner="owner",
            name="repo",
            provider_repo_id="owner/repo",
        ),
        options=GitHubSyncOptions(
            mode=RepositorySyncMode.ISSUES,
            issue_state=RepositoryIssueState.OPEN,
            labels=("kairota",),
            max_pages=1,
        ),
    )

    assert [issue.number for issue in snapshot.issues] == [7]
    assert snapshot.pull_requests == ()
    assert snapshot.checks == ()
    assert not any("/pulls?" in call for call in calls)
    assert not any("/check-runs" in call for call in calls)
