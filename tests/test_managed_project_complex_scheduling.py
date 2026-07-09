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

ISSUE_KEYS = (
    "A01",
    "A02",
    "A03",
    "A04",
    "B01",
    "B02",
    "C01",
    "C02",
    "D01",
    "D02",
    "D03",
    "E01",
    "E02",
    "E03",
    "F01",
    "F02",
    "F03",
    "F04",
    "G01",
    "G02",
    "I01",
    "I02",
    "I03",
    "I04",
)


class ComplexDogfoodGitHubClient:
    def __init__(self) -> None:
        self.calls: list[GitHubRepositoryConfig] = []

    def fetch_repository_snapshot(
        self,
        repository: GitHubRepositoryConfig,
        cursor: str | None = None,
    ) -> GitHubSyncSnapshot:
        del cursor
        self.calls.append(repository)
        return GitHubSyncSnapshot(
            repository=GitHubRepositorySnapshot(
                provider_repo_id="github:kairota-project/kairota",
                name="kairota-project/kairota",
                default_branch="main",
            ),
            issues=tuple(
                GitHubIssueSnapshot(
                    number=200 + index,
                    provider_issue_id=f"complex-issue-{key}",
                    title=f"Dogfood complex {key}",
                    url=f"https://example.test/kairota/issues/{200 + index}",
                    state="open",
                )
                for index, key in enumerate(ISSUE_KEYS, start=1)
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
def github_client() -> ComplexDogfoodGitHubClient:
    return ComplexDogfoodGitHubClient()


@pytest.fixture()
def client(
    session_factory: sessionmaker[Session],
    github_client: ComplexDogfoodGitHubClient,
) -> TestClient:
    app = create_app(
        Settings(app_name="Kairota Complex Dogfood", database_url="sqlite:///test.sqlite"),
        session_factory=session_factory,
        github_client=github_client,
    )
    return TestClient(app)


def test_complex_issue_graph_respects_worker_cap_and_scheduler_reasons(
    client: TestClient,
    github_client: ComplexDogfoodGitHubClient,
) -> None:
    registered = client.post(
        "/repositories",
        headers={"Idempotency-Key": "complex-dogfood-register"},
        json={"remote": "kairota-project/kairota"},
    )
    assert registered.status_code == 200
    repository_id = str(registered.json()["id"])

    synced = client.post(
        f"/repositories/{repository_id}/sync",
        headers={"Idempotency-Key": "complex-dogfood-sync"},
    )
    assert synced.status_code == 200
    assert synced.json()["work_items_created"] == len(ISSUE_KEYS)
    assert github_client.calls[0].owner == "kairota-project"

    work_items = client.get(f"/work-items?repository_id={repository_id}")
    assert work_items.status_code == 200
    by_key = {
        item["title"].replace("Dogfood complex ", ""): str(item["id"])
        for item in work_items.json()
    }
    assert set(by_key) == set(ISSUE_KEYS)

    def triage(
        key: str,
        *,
        priority: int,
        status: str = "ready",
        expected_touch: str | None = None,
        acceptance: str | None = None,
        validation: str | None = None,
        conflict_keys: list[str] | None = None,
        dependencies: tuple[str, ...] = (),
    ) -> None:
        payload: dict[str, object] = {
            "status": status,
            "priority": priority,
            "risk": "medium",
            "work_type": "implementation",
            "autonomy_mode": "ai_assisted",
            "dependency_ids": [by_key[dependency] for dependency in dependencies],
        }
        if expected_touch is not None:
            payload["expected_touch"] = expected_touch
        if acceptance is not None:
            payload["acceptance"] = acceptance
        if validation is not None:
            payload["validation"] = validation
        if conflict_keys is not None:
            payload["conflict_keys"] = conflict_keys

        response = client.post(
            f"/work-items/{by_key[key]}/triage",
            headers={"Idempotency-Key": f"complex-dogfood-triage-{key}"},
            json=payload,
        )
        assert response.status_code == 200

    def ready(
        key: str,
        *,
        priority: int,
        conflict_keys: list[str] | None = None,
        dependencies: tuple[str, ...] = (),
    ) -> None:
        triage(
            key,
            priority=priority,
            expected_touch=f"src/kairota/{key.lower()}.py",
            acceptance=f"{key} has observable completion evidence.",
            validation="python -m pytest",
            conflict_keys=conflict_keys
            if conflict_keys is not None
            else [f"repo:kairota-project/kairota:path:{key.lower()}"],
            dependencies=dependencies,
        )

    for index, key in enumerate(("A01", "A02", "A03", "A04"), start=1):
        ready(key, priority=index)
    ready("B01", priority=20, conflict_keys=["shared:editor"])
    ready("B02", priority=21, conflict_keys=["shared:editor"])
    ready("C01", priority=30, dependencies=("A01",))
    ready("C02", priority=31, dependencies=("A02", "B01"))
    triage(
        "D01",
        priority=40,
        acceptance="Missing touch is management metadata only.",
        validation="python -m pytest",
        conflict_keys=["missing:touch"],
    )
    triage(
        "D02",
        priority=41,
        expected_touch="src/kairota/missing_acceptance.py",
        validation="python -m pytest",
        conflict_keys=["missing:acceptance"],
    )
    triage(
        "D03",
        priority=42,
        expected_touch="src/kairota/missing_validation.py",
        acceptance="Missing validation is management metadata only.",
        conflict_keys=["missing:validation"],
    )
    triage("E01", priority=50, status="blocked")
    triage("E02", priority=51, status="backlog")
    triage("E03", priority=52, status="human_decision")
    for index, key in enumerate(("F01", "F02", "F03", "F04"), start=60):
        ready(key, priority=index)
    ready("G01", priority=70, conflict_keys=[])
    ready("G02", priority=71, conflict_keys=[])
    for index, key in enumerate(("I01", "I02", "I03", "I04"), start=80):
        ready(key, priority=index)

    claims: list[dict[str, object]] = []
    for index in range(1, 5):
        claimed = client.post(
            "/queue/claim-next",
            headers={"Idempotency-Key": f"complex-dogfood-claim-{index}"},
            json={
                "repository_id": repository_id,
                "queue_key": "dogfood",
                "owner": f"dogfood-worker-{index}",
                "max_active_leases": 4,
            },
        )
        assert claimed.status_code == 200
        claims.append(claimed.json())

    assert [claim["work_item_id"] for claim in claims] == [
        by_key["A01"],
        by_key["A02"],
        by_key["A03"],
        by_key["A04"],
    ]

    capped = client.post(
        "/queue/claim-next",
        headers={"Idempotency-Key": "complex-dogfood-claim-cap"},
        json={
            "repository_id": repository_id,
            "queue_key": "dogfood",
            "owner": "dogfood-worker-5",
            "max_active_leases": 4,
        },
    )
    summary_at_cap = client.get(f"/queue/summary?repository_id={repository_id}")
    assert capped.status_code == 409
    assert capped.json()["reason_code"] == "blocked_by_capacity"
    assert summary_at_cap.status_code == 200
    assert summary_at_cap.json()["active_leases"] == 4

    plan = client.post(
        "/scheduler/cycles",
        headers={"Idempotency-Key": "complex-dogfood-plan"},
        json={"repository_id": repository_id, "queue_key": "dogfood", "capacity": 24},
    )
    assert plan.status_code == 200
    decisions = {
        str(decision["work_item_id"]): decision["code"]
        for decision in plan.json()["decisions"]
    }
    assert decisions[by_key["B01"]] == "assigned"
    assert decisions[by_key["B02"]] == "blocked_by_conflict_key"
    assert decisions[by_key["C01"]] == "blocked_by_dependency"
    assert decisions[by_key["C02"]] == "blocked_by_dependency"
    assert decisions[by_key["D01"]] == "assigned"
    assert decisions[by_key["D02"]] == "assigned"
    assert decisions[by_key["D03"]] == "assigned"
    assert decisions[by_key["E01"]] == "blocked_by_status"
    assert decisions[by_key["G01"]] == "assigned"
    assert decisions[by_key["G02"]] == "blocked_by_conflict_key"

    run_ids: list[str] = []
    for index, claim in enumerate(claims, start=1):
        started = client.post(
            "/worker-runs",
            headers={"Idempotency-Key": f"complex-dogfood-run-{index}"},
            json={
                "work_item_id": claim["work_item_id"],
                "lease_id": claim["lease_id"],
                "fencing_token": claim["fencing_token"],
                "role": "worker",
            },
        )
        assert started.status_code == 200
        run_ids.append(str(started.json()["id"]))

    reported = client.post(
        f"/worker-runs/{run_ids[0]}/report",
        headers={"Idempotency-Key": "complex-dogfood-report-blocked"},
        json={
            "fencing_token": claims[0]["fencing_token"],
            "validation": {"scenario": "worker-found-blocker"},
            "public_mutations": {"issue": 201},
        },
    )
    assert reported.status_code == 200

    closed = client.post(
        f"/worker-runs/{run_ids[0]}/close",
        headers={"Idempotency-Key": "complex-dogfood-close-blocked"},
        json={
            "fencing_token": claims[0]["fencing_token"],
            "result": "blocked",
            "validation": {"reason": "dependency contract unclear"},
        },
    )
    assert closed.status_code == 200
    assert client.get(f"/work-items/{by_key['A01']}").json()["status"] == "blocked"

    replacement = client.post(
        "/queue/claim-next",
        headers={"Idempotency-Key": "complex-dogfood-claim-replacement"},
        json={
            "repository_id": repository_id,
            "queue_key": "dogfood",
            "owner": "dogfood-worker-5",
            "max_active_leases": 4,
        },
    )
    summary_after_replacement = client.get(
        f"/queue/summary?repository_id={repository_id}"
    )
    assert replacement.status_code == 200
    assert replacement.json()["work_item_id"] == by_key["B01"]
    assert summary_after_replacement.status_code == 200
    assert summary_after_replacement.json()["active_leases"] == 4
