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
    GitHubSyncOptions,
    GitHubSyncSnapshot,
)
from kairota.api.app import create_app
from kairota.config import Settings


class DogfoodGitHubClient:
    def __init__(self) -> None:
        self.calls: list[GitHubRepositoryConfig] = []

    def fetch_repository_snapshot(
        self,
        repository: GitHubRepositoryConfig,
        cursor: str | None = None,
        options: GitHubSyncOptions | None = None,
    ) -> GitHubSyncSnapshot:
        del cursor, options
        self.calls.append(repository)
        return GitHubSyncSnapshot(
            repository=GitHubRepositorySnapshot(
                provider_repo_id="github:kairota-project/kairota",
                name="kairota-project/kairota",
                default_branch="main",
            ),
            issues=(
                GitHubIssueSnapshot(
                    number=101,
                    provider_issue_id="issue-101",
                    title="Dogfood managed-project scheduling smoke",
                    url="https://example.test/kairota/issues/101",
                    state="open",
                ),
            ),
        )


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
def github_client() -> DogfoodGitHubClient:
    return DogfoodGitHubClient()


@pytest.fixture()
def client(
    session_factory: sessionmaker[Session],
    github_client: DogfoodGitHubClient,
) -> TestClient:
    app = create_app(
        Settings(app_name="Kairota Dogfood Test", database_url="sqlite:///test.sqlite"),
        session_factory=session_factory,
        github_client=github_client,
    )
    return TestClient(app)


def test_kairota_can_register_sync_triage_schedule_and_record_own_work(
    client: TestClient,
    github_client: DogfoodGitHubClient,
) -> None:
    registered = client.post(
        "/repositories",
        headers={"Idempotency-Key": "dogfood-register"},
        json={"remote": "kairota-project/kairota"},
    )
    assert registered.status_code == 200
    repository_id = str(registered.json()["id"])

    synced = client.post(
        f"/repositories/{repository_id}/sync",
        headers={"Idempotency-Key": "dogfood-sync-issues"},
    )
    assert synced.status_code == 200
    assert synced.json()["work_items_created"] == 1
    assert github_client.calls[0].owner == "kairota-project"
    assert github_client.calls[0].name == "kairota"

    work_items = client.get(f"/work-items?repository_id={repository_id}")
    assert work_items.status_code == 200
    assert len(work_items.json()) == 1
    work_item = work_items.json()[0]
    work_item_id = str(work_item["id"])
    assert work_item["repository_id"] == repository_id
    assert work_item["status"] == "needs_triage"

    ready_before_triage = client.get(f"/queue/ready?repository_id={repository_id}")
    assert ready_before_triage.status_code == 200
    assert ready_before_triage.json() == []

    triaged = client.post(
        f"/work-items/{work_item_id}/triage",
        headers={"Idempotency-Key": "dogfood-triage-issue-101"},
        json={
            "status": "ready",
            "priority": 5,
            "risk": "medium",
            "work_type": "implementation",
            "autonomy_mode": "ai_assisted",
            "expected_touch": "skills/kairota-managed-project; src/kairota/**",
            "acceptance": (
                "Kairota dogfood skill and managed-project flow are verified."
            ),
            "validation": "pytest tests/test_managed_project_dogfood.py",
            "conflict_keys": [
                "repo:kairota-project/kairota:path:skills/kairota-managed-project",
                "repo:kairota-project/kairota:path:src/kairota",
            ],
        },
    )
    assert triaged.status_code == 200
    assert triaged.json()["status"] == "ready"

    plan = client.post(
        "/scheduler/cycles",
        headers={"Idempotency-Key": "dogfood-plan-ready"},
        json={"repository_id": repository_id, "queue_key": "dogfood", "capacity": 1},
    )
    assert plan.status_code == 200
    assert plan.json()["repository_id"] == repository_id
    assert plan.json()["assigned_count"] == 1
    assert plan.json()["decisions"][0]["work_item_id"] == work_item_id

    claimed = client.post(
        "/queue/claim-next",
        headers={"Idempotency-Key": "dogfood-claim-next"},
        json={
            "repository_id": repository_id,
            "queue_key": "dogfood",
            "owner": "dogfood-worker",
        },
    )
    assert claimed.status_code == 200
    assert claimed.json()["claimed"] is True
    assert claimed.json()["work_item_id"] == work_item_id
    lease_id = str(claimed.json()["lease_id"])
    fencing_token = str(claimed.json()["fencing_token"])

    started = client.post(
        "/worker-runs",
        headers={"Idempotency-Key": "dogfood-worker-run"},
        json={
            "work_item_id": work_item_id,
            "lease_id": lease_id,
            "fencing_token": fencing_token,
            "role": "worker",
        },
    )
    assert started.status_code == 200
    worker_run_id = str(started.json()["id"])
    assert started.json()["status"] == "running"

    reported = client.post(
        f"/worker-runs/{worker_run_id}/report",
        headers={"Idempotency-Key": "dogfood-worker-report"},
        json={
            "fencing_token": fencing_token,
            "validation": {"dogfood": "registered-synced-triaged-claimed"},
            "public_mutations": {"issue": 101},
        },
    )
    assert reported.status_code == 200
    assert reported.json()["validation"]["dogfood"] == (
        "registered-synced-triaged-claimed"
    )

    closed = client.post(
        f"/worker-runs/{worker_run_id}/close",
        headers={"Idempotency-Key": "dogfood-worker-close"},
        json={
            "fencing_token": fencing_token,
            "result": "blocked",
            "validation": {"reason": "offline dogfood smoke stops before real PR"},
        },
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["result"] == "blocked"

    workbench = client.get(f"/queue/workbench?repository_id={repository_id}")
    assert workbench.status_code == 200
    sections = {section["id"]: section for section in workbench.json()["sections"]}
    assert sections["blocked"]["count"] == 1
    assert sections["blocked"]["rows"][0]["repository_id"] == repository_id
