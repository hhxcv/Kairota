import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from kairota.api.app import create_app
from kairota.config import Settings


def register_project(client: TestClient, remote: str = "owner/repo") -> dict[str, Any]:
    response = client.post(
        "/projects",
        headers={"Idempotency-Key": f"register-{remote}"},
        json={"remote": remote},
    )
    assert response.status_code == 200
    return response.json()


def test_health_and_local_cors(api_client: TestClient) -> None:
    response = api_client.get(
        "/healthz", headers={"Origin": "http://127.0.0.1:5180"}
    )
    assert response.json() == {
        "status": "ok",
        "service": "Kairota Test",
        "version": "0.1.0",
    }
    assert response.headers["access-control-allow-origin"] == (
        "http://127.0.0.1:5180"
    )


def test_project_issue_analysis_claim_and_release_api(
    api_client: TestClient, github: Any
) -> None:
    github.set_issue(1)
    project = register_project(api_client)
    sync = api_client.post(
        f"/projects/{project['id']}/sync",
        headers={"Idempotency-Key": "sync-1"},
    )
    assert sync.status_code == 200
    assert sync.json()["issues_created"] == 1

    page = api_client.get(
        "/issues",
        params=[("project_id", project["id"]), ("state", "needs_analysis")],
    ).json()
    issue = page["items"][0]
    assert issue["last_synced_at"].endswith("Z")
    analyzed = api_client.put(
        f"/issues/{issue['id']}/analysis",
        headers={"Idempotency-Key": "analyze-1"},
        json={
            "expected_analysis_version": issue["analysis_version"],
            "dependency_issue_numbers": [],
        },
    )
    assert analyzed.status_code == 200
    ready = analyzed.json()
    assert ready["scheduling_state"] == "ready"
    assert ready["claimable_now"] is True

    claimed = api_client.post(
        f"/issues/{issue['id']}/claim",
        headers={"Idempotency-Key": "claim-1"},
        json={"expected_scheduling_version": ready["scheduling_version"]},
    )
    assert claimed.status_code == 200
    running = claimed.json()
    assert running["scheduling_state"] == "in_progress"

    conflict = api_client.post(
        f"/issues/{issue['id']}/claim",
        headers={"Idempotency-Key": "claim-2"},
        json={"expected_scheduling_version": ready["scheduling_version"]},
    )
    assert conflict.status_code == 409
    assert conflict.json()["reason_code"] == "state_in_progress"

    released = api_client.post(
        f"/issues/{issue['id']}/release",
        headers={"Idempotency-Key": "release-1"},
        json={
            "expected_scheduling_version": running["scheduling_version"],
            "reason": "Main AI restart reconciliation.",
        },
    )
    assert released.status_code == 200
    assert released.json()["scheduling_state"] == "needs_analysis"


def test_issue_list_supports_multi_project_multi_state_and_pagination(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    github: Any,
) -> None:
    github.set_issue(1)
    github.set_issue(2, state="closed")
    first = register_project(api_client)
    api_client.post(
        f"/projects/{first['id']}/sync",
        headers={"Idempotency-Key": "sync-filter"},
    )
    second = register_project(api_client, "other/repo")

    response = api_client.get(
        "/issues",
        params=[
            ("project_id", first["id"]),
            ("project_id", second["id"]),
            ("state", "needs_analysis"),
            ("state", "closed"),
            ("page", "1"),
            ("page_size", "1"),
        ],
    )
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 2
    assert len(page["items"]) == 1
    assert page["by_state"]["needs_analysis"] == 1
    assert page["by_state"]["closed"] == 1


def test_webhook_refreshes_exact_issue_and_replays_delivery(
    api_client: TestClient, github: Any
) -> None:
    github.set_issue(7)
    project = register_project(api_client)
    api_client.post(
        f"/projects/{project['id']}/sync",
        headers={"Idempotency-Key": "sync-webhook"},
    )
    github.set_issue(7, state="closed")
    payload = json.dumps(
        {
            "action": "closed",
            "repository": {
                "id": github.provider_repo_id,
                "full_name": "owner/repo",
            },
            "issue": {"number": 7, "state": "open"},
        }
    ).encode()
    signature = "sha256=" + hmac.new(
        b"test-secret", payload, hashlib.sha256
    ).hexdigest()
    headers = {
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": "delivery-7",
        "X-Hub-Signature-256": signature,
        "Content-Type": "application/json",
    }

    first = api_client.post("/webhooks/github", content=payload, headers=headers)
    replay = api_client.post("/webhooks/github", content=payload, headers=headers)

    assert first.status_code == 200
    assert first.json()["replayed"] is False
    assert replay.json()["replayed"] is True
    assert github.calls[-1] == ("owner/repo", (7,))
    issue = api_client.get("/issues").json()["items"][0]
    assert issue["scheduling_state"] == "closed"


def test_writes_require_idempotency_key(api_client: TestClient) -> None:
    response = api_client.post("/projects", json={"remote": "owner/repo"})
    assert response.status_code == 400
    assert response.json()["reason_code"] == "missing_idempotency_key"


def test_default_database_is_internal_and_auto_migrated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    github: Any,
) -> None:
    monkeypatch.setenv("KAIROTA_DATA_DIR", str(tmp_path))
    settings = Settings(auto_migrate=True)
    app = create_app(settings, github_client=github, start_background_sync=False)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
    assert (tmp_path / "kairota.sqlite").exists()
