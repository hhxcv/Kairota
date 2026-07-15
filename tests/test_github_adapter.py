import hashlib
import hmac
import json

import httpx
import pytest

from kairota.adapters.github.client import GitHubHttpClient
from kairota.adapters.github.models import GitHubProjectConfig
from kairota.adapters.github.webhook import (
    WebhookNormalizationError,
    normalize_webhook_event,
    verify_signature,
)


def test_client_uses_rest_and_filters_pull_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_get(url: str, **_kwargs: object) -> httpx.Response:
        calls.append(url)
        request = httpx.Request("GET", url)
        if url.endswith("/repos/owner/repo"):
            return httpx.Response(
                200,
                request=request,
                json={"id": 10, "full_name": "owner/repo"},
            )
        return httpx.Response(
            200,
            request=request,
            json=[
                issue_payload(1),
                {**issue_payload(2), "pull_request": {"url": "ignored"}},
            ],
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    client = GitHubHttpClient(api_url="https://api.github.test")
    snapshot = client.fetch_project_snapshot(project_config())

    assert [issue.number for issue in snapshot.issues] == [1]
    assert calls == [
        "https://api.github.test/repos/owner/repo",
        "https://api.github.test/repos/owner/repo/issues?state=all&per_page=100",
    ]
    assert all("graphql" not in url.lower() for url in calls)


def test_client_fetches_exact_issue_for_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_get(url: str, **_kwargs: object) -> httpx.Response:
        calls.append(url)
        request = httpx.Request("GET", url)
        payload = (
            {"id": 10, "full_name": "owner/repo"}
            if url.endswith("/repos/owner/repo")
            else issue_payload(7)
        )
        return httpx.Response(200, request=request, json=payload)

    monkeypatch.setattr(httpx, "get", fake_get)
    client = GitHubHttpClient(api_url="https://api.github.test")
    snapshot = client.fetch_project_snapshot(project_config(), issue_numbers=(7,))

    assert [issue.number for issue in snapshot.issues] == [7]
    assert calls[-1].endswith("/issues/7")


def test_client_rejects_silently_truncated_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, **_kwargs: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        if url.endswith("/repos/owner/repo"):
            return httpx.Response(
                200,
                request=request,
                json={"id": 10, "full_name": "owner/repo"},
            )
        return httpx.Response(
            200,
            request=request,
            json=[issue_payload(1)],
            headers={"Link": '<https://api.github.test/page/2>; rel="next"'},
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    client = GitHubHttpClient(api_url="https://api.github.test", max_pages=1)

    with pytest.raises(RuntimeError, match="pagination exceeded"):
        client.fetch_project_snapshot(project_config())


def test_webhook_verification_and_issue_only_normalization() -> None:
    payload = json.dumps(
        {
            "action": "closed",
            "repository": {"id": 10, "full_name": "owner/repo"},
            "issue": {"number": 7},
        }
    ).encode()
    signature = "sha256=" + hmac.new(b"secret", payload, hashlib.sha256).hexdigest()

    assert verify_signature(
        secret="secret", payload=payload, signature_header=signature
    )
    event = normalize_webhook_event(
        event_type="issues", delivery_id="delivery-1", payload=payload
    )
    assert event.issue_number == 7
    assert event.project_name == "owner/repo"

    with pytest.raises(WebhookNormalizationError, match="Only GitHub Issue"):
        normalize_webhook_event(
            event_type="pull_request", delivery_id="delivery-2", payload=payload
        )


def project_config() -> GitHubProjectConfig:
    return GitHubProjectConfig(
        owner="owner", name="repo", provider_repo_id="owner/repo"
    )


def issue_payload(number: int) -> dict[str, object]:
    return {
        "id": number,
        "number": number,
        "title": f"Issue {number}",
        "html_url": f"https://github.test/owner/repo/issues/{number}",
        "state": "open",
        "updated_at": "2026-07-10T00:00:00Z",
    }
