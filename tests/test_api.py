import hashlib
import hmac
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from kairota.adapters.github.models import (
    GitHubIssueSnapshot,
    GitHubRepositoryConfig,
    GitHubRepositorySnapshot,
    GitHubSyncSnapshot,
)
from kairota.api.app import create_app
from kairota.config import Settings
from kairota.contracts.enums import RepositoryProvider
from kairota.models.records import Repository


class FakeGitHubClient:
    def fetch_repository_snapshot(
        self,
        repository: GitHubRepositoryConfig,
        cursor: str | None = None,
    ) -> GitHubSyncSnapshot:
        del repository, cursor
        return GitHubSyncSnapshot(
            repository=GitHubRepositorySnapshot(
                provider_repo_id="repo-1",
                name="owner/repo",
                default_branch="main",
            ),
            issues=(
                GitHubIssueSnapshot(
                    number=7,
                    provider_issue_id="issue-7",
                    title="Synced issue",
                    url="https://example.test/issues/7",
                    state="open",
                ),
            ),
        )


def test_healthz_returns_runtime_identity() -> None:
    app = create_app(Settings(app_name="Kairota Test"))
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Kairota Test",
        "version": "0.1.0",
    }


@pytest.fixture()
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    db_path = tmp_path / "kairota.sqlite"
    db_url = f"sqlite:///{db_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(config, "head")

    engine = create_engine(db_url)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> TestClient:
    app = create_app(
        Settings(app_name="Kairota Test", database_url="sqlite:///test.sqlite"),
        session_factory=session_factory,
        github_client=FakeGitHubClient(),
    )
    return TestClient(app)


def ready_work_item_payload(title: str = "Implement API") -> dict[str, object]:
    return {
        "title": title,
        "status": "ready",
        "priority": 10,
        "risk": "medium",
        "work_type": "implementation",
        "autonomy_mode": "ai_assisted",
        "expected_touch": "src/kairota/api/**",
        "acceptance": "REST contract exists",
        "validation": "pytest",
        "conflict_keys": ["runtime:api"],
    }


def create_ready_work_item(client: TestClient, key: str = "create-ready") -> str:
    response = client.post(
        "/work-items",
        headers={"Idempotency-Key": key},
        json=ready_work_item_payload(),
    )
    assert response.status_code == 200
    return str(response.json()["id"])


def test_work_item_create_replays_same_idempotent_command(
    client: TestClient,
) -> None:
    payload = ready_work_item_payload()

    first = client.post(
        "/work-items",
        headers={"Idempotency-Key": "same-create"},
        json=payload,
    )
    second = client.post(
        "/work-items",
        headers={"Idempotency-Key": "same-create"},
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["conflict_keys"] == ["runtime:api"]


def test_work_item_create_rejects_idempotency_payload_conflict(
    client: TestClient,
) -> None:
    first = client.post(
        "/work-items",
        headers={"Idempotency-Key": "conflicting-create"},
        json=ready_work_item_payload("Original"),
    )
    second = client.post(
        "/work-items",
        headers={"Idempotency-Key": "conflicting-create"},
        json=ready_work_item_payload("Changed"),
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["reason_code"] == "idempotency_conflict"


def test_work_item_create_rejects_unsafe_initial_status(
    client: TestClient,
) -> None:
    response = client.post(
        "/work-items",
        headers={"Idempotency-Key": "unsafe-status"},
        json={"title": "Unsafe", "status": "claimed"},
    )

    assert response.status_code == 409
    assert response.json()["reason_code"] == "invalid_initial_status"


def test_queue_summary_and_work_item_detail(client: TestClient) -> None:
    work_item_id = create_ready_work_item(client)

    detail = client.get(f"/work-items/{work_item_id}")
    summary = client.get("/queue/summary")

    assert detail.status_code == 200
    assert detail.json()["id"] == work_item_id
    assert summary.status_code == 200
    assert summary.json()["total"] == 1
    assert summary.json()["by_status"]["ready"] == 1


def test_scheduler_cycle_records_decisions(client: TestClient) -> None:
    work_item_id = create_ready_work_item(client)

    response = client.post(
        "/scheduler/cycles",
        headers={"Idempotency-Key": "cycle-1"},
        json={"queue_key": "default", "capacity": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assigned_count"] == 1
    assert payload["decisions"][0]["work_item_id"] == work_item_id
    assert payload["decisions"][0]["code"] == "assigned"


def test_claim_blocked_response_is_machine_readable(client: TestClient) -> None:
    response = client.post(
        "/work-items",
        headers={"Idempotency-Key": "create-needs-triage"},
        json={"title": "Needs triage"},
    )
    assert response.status_code == 200
    work_item_id = str(response.json()["id"])

    claim = client.post(
        f"/work-items/{work_item_id}/claim",
        headers={"Idempotency-Key": "claim-blocked"},
        json={"owner": "slot-1"},
    )

    assert claim.status_code == 409
    assert claim.json()["status"] == "blocked"
    assert claim.json()["reason_code"] == "blocked_by_status"


def test_claim_and_heartbeat_success(client: TestClient) -> None:
    work_item_id = create_ready_work_item(client)

    claim = client.post(
        f"/work-items/{work_item_id}/claim",
        headers={"Idempotency-Key": "claim-ready"},
        json={"owner": "slot-1"},
    )
    assert claim.status_code == 200
    lease_id = claim.json()["lease_id"]
    fencing_token = claim.json()["fencing_token"]

    heartbeat = client.post(
        f"/leases/{lease_id}/heartbeat",
        headers={"Idempotency-Key": "heartbeat-1"},
        json={"fencing_token": fencing_token},
    )

    assert heartbeat.status_code == 200
    assert heartbeat.json()["refreshed"] is True


def test_worker_run_endpoints_enforce_lease_authority(client: TestClient) -> None:
    work_item_id = create_ready_work_item(client, "create-worker-run")
    claim = client.post(
        f"/work-items/{work_item_id}/claim",
        headers={"Idempotency-Key": "claim-worker-run"},
        json={"owner": "slot-1"},
    )
    assert claim.status_code == 200
    lease_id = claim.json()["lease_id"]
    fencing_token = claim.json()["fencing_token"]

    created = client.post(
        "/worker-runs",
        headers={"Idempotency-Key": "worker-run-create"},
        json={
            "work_item_id": work_item_id,
            "lease_id": lease_id,
            "fencing_token": fencing_token,
        },
    )
    assert created.status_code == 200
    worker_run_id = created.json()["id"]
    assert created.json()["status"] == "running"
    assert created.json()["started_at"] is not None

    detail = client.get(f"/worker-runs/{worker_run_id}")
    assert detail.status_code == 200
    assert detail.json()["lease_id"] == lease_id

    stale = client.post(
        f"/worker-runs/{worker_run_id}/heartbeat",
        headers={"Idempotency-Key": "worker-run-stale-heartbeat"},
        json={"fencing_token": "stale-token"},
    )
    assert stale.status_code == 409
    assert stale.json()["reason_code"] == "invalid_fencing_token"

    report = client.post(
        f"/worker-runs/{worker_run_id}/report",
        headers={"Idempotency-Key": "worker-run-report"},
        json={
            "fencing_token": fencing_token,
            "validation": {"pytest": "passed"},
            "public_mutations": {"pr": 7},
        },
    )
    assert report.status_code == 200
    assert report.json()["status"] == "reporting"
    assert report.json()["validation"]["pytest"] == "passed"

    closed = client.post(
        f"/worker-runs/{worker_run_id}/close",
        headers={"Idempotency-Key": "worker-run-close"},
        json={"fencing_token": fencing_token, "result": "blocked"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["result"] == "blocked"
    assert client.get(f"/work-items/{work_item_id}").json()["status"] == "blocked"


def test_repository_sync_uses_github_adapter(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session, session.begin():
        repository = Repository(
            provider=RepositoryProvider.GITHUB.value,
            provider_repo_id="repo-1",
            name="owner/repo",
            default_branch="main",
            sync_status="unknown",
        )
        session.add(repository)
        session.flush()
        repository_id = repository.id

    response = client.post(
        f"/repositories/{repository_id}/sync",
        headers={"Idempotency-Key": "api-sync"},
    )

    assert response.status_code == 200
    assert response.json()["issues_seen"] == 1
    assert response.json()["work_items_created"] == 1


def test_github_webhook_route_verifies_signature(
    session_factory: sessionmaker[Session],
) -> None:
    app = create_app(
        Settings(
            app_name="Kairota Test",
            database_url="sqlite:///test.sqlite",
            github_webhook_secret="secret",
        ),
        session_factory=session_factory,
        github_client=FakeGitHubClient(),
    )
    client = TestClient(app)
    payload = json.dumps(
        {
            "action": "opened",
            "repository": {
                "id": 123,
                "full_name": "owner/repo",
                "default_branch": "main",
            },
            "issue": {
                "id": 456,
                "number": 7,
                "title": "Webhook issue",
                "html_url": "https://example.test/issues/7",
                "state": "open",
            },
        },
        sort_keys=True,
    ).encode("utf-8")
    signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()

    invalid = client.post(
        "/webhooks/github",
        content=payload,
        headers={
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery-invalid",
            "X-Hub-Signature-256": "sha256=wrong",
        },
    )
    valid = client.post(
        "/webhooks/github",
        content=payload,
        headers={
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery-valid",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
    )

    assert invalid.status_code == 401
    assert invalid.json()["reason_code"] == "invalid_github_signature"
    assert valid.status_code == 200
    assert valid.json()["work_items_created"] == 1
