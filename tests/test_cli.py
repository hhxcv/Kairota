import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pytest import CaptureFixture, MonkeyPatch

from kairota.cli import main
from kairota.config import get_settings


def test_health_command_outputs_json(capsys: CaptureFixture[str]) -> None:
    exit_code = main(["health"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["service"] == "Kairota"
    assert payload["version"] == "0.1.0"


def test_cli_uses_internal_database_without_explicit_url(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.delenv("KAIROTA_DATABASE_URL", raising=False)
    monkeypatch.setenv("KAIROTA_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        exit_code = main(
            [
                "work-items",
                "create",
                "--idempotency-key",
                "cli-default-db-create",
                "--title",
                "CLI default database work",
            ]
        )
    finally:
        get_settings.cache_clear()

    assert exit_code == 0
    assert read_json(capsys)["title"] == "CLI default database work"
    assert (tmp_path / "kairota.sqlite").exists()


def test_serve_uses_fixed_defaults(monkeypatch: MonkeyPatch) -> None:
    prepared: list[bool] = []
    served: list[dict[str, object]] = []

    def fake_ready() -> None:
        prepared.append(True)

    def fake_run(app: str, *, host: str, port: int) -> None:
        served.append({"app": app, "host": host, "port": port})

    monkeypatch.setattr("kairota.cli.ensure_database_ready", fake_ready)
    monkeypatch.setattr("uvicorn.run", fake_run)

    assert main(["serve"]) == 0
    assert prepared == [True]
    assert served == [
        {
            "app": "kairota.api.app:app",
            "host": "127.0.0.1",
            "port": 8010,
        }
    ]


@pytest.fixture()
def cli_database(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[None]:
    db_path = tmp_path / "kairota.sqlite"
    db_url = f"sqlite:///{db_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(config, "head")

    monkeypatch.setenv("KAIROTA_DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def read_json(capsys: CaptureFixture[str]) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def test_cli_smoke_for_m1_api_wrappers(
    cli_database: None,
    capsys: CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "repositories",
                "register",
                "--idempotency-key",
                "cli-register",
                "--remote",
                "https://github.com/owner/repo.git",
            ]
        )
        == 0
    )
    repository = read_json(capsys)
    repository_id = str(repository["id"])
    assert repository["name"] == "owner/repo"

    create_code = main(
        [
            "work-items",
            "create",
            "--idempotency-key",
            "cli-create",
            "--title",
            "CLI work",
            "--repository-id",
            repository_id,
            "--priority",
            "10",
        ]
    )
    created = read_json(capsys)
    work_item_id = str(created["id"])
    assert create_code == 0
    assert created["status"] == "needs_triage"

    assert (
        main(
            [
                "work-items",
                "triage",
                work_item_id,
                "--idempotency-key",
                "cli-triage",
                "--status",
                "ready",
                "--priority",
                "10",
                "--expected-touch",
                "src/kairota/cli.py",
                "--acceptance",
                "CLI command works",
                "--validation",
                "pytest",
                "--conflict-key",
                "runtime:cli",
            ]
        )
        == 0
    )
    triaged = read_json(capsys)
    assert triaged["status"] == "ready"

    assert (
        main(
            [
                "queue",
                "ready",
                "--repository-id",
                repository_id,
            ]
        )
        == 0
    )
    ready = json.loads(capsys.readouterr().out)
    assert ready[0]["id"] == work_item_id

    assert (
        main(
            [
                "queue",
                "claim-next",
                "--idempotency-key",
                "cli-claim-next",
                "--owner",
                "slot-claim-next",
                "--repository-id",
                repository_id,
            ]
        )
        == 0
    )
    claim_next = read_json(capsys)
    assert claim_next["work_item_id"] == work_item_id

    second_create_code = main(
        [
            "work-items",
            "create",
            "--idempotency-key",
            "cli-create-second",
            "--title",
            "Second CLI work",
            "--repository-id",
            repository_id,
            "--status",
            "ready",
            "--expected-touch",
            "src/kairota/cli.py",
            "--acceptance",
            "CLI command works",
            "--validation",
            "pytest",
            "--conflict-key",
            "runtime:cli-second",
        ]
    )
    created = read_json(capsys)
    work_item_id = str(created["id"])
    assert second_create_code == 0
    assert created["status"] == "ready"

    assert (
        main(
            [
                "queue",
                "claim-next",
                "--idempotency-key",
                "cli-capped-claim-next",
                "--owner",
                "slot-capped",
                "--repository-id",
                repository_id,
                "--max-active-leases",
                "1",
            ]
        )
        == 2
    )
    capped = read_json(capsys)
    assert capped["reason_code"] == "blocked_by_capacity"

    assert main(["work-items", "show", work_item_id]) == 0
    shown = read_json(capsys)
    assert shown["id"] == work_item_id

    assert main(["work-items", "list", "--status", "ready"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["id"] == work_item_id

    assert main(["queue", "summary"]) == 0
    summary = read_json(capsys)
    assert summary["by_status"]["ready"] == 1

    assert (
        main(
            [
                "scheduler",
                "run",
                "--idempotency-key",
                "cli-cycle",
                "--repository-id",
                repository_id,
                "--capacity",
                "1",
            ]
        )
        == 0
    )
    cycle = read_json(capsys)
    assert cycle["assigned_count"] == 1

    assert (
        main(
            [
                "work-items",
                "claim",
                work_item_id,
                "--idempotency-key",
                "cli-claim",
                "--owner",
                "slot-1",
            ]
        )
        == 0
    )
    claim = read_json(capsys)
    lease_id = str(claim["lease_id"])
    fencing_token = str(claim["fencing_token"])

    assert (
        main(
            [
                "leases",
                "heartbeat",
                lease_id,
                "--idempotency-key",
                "cli-heartbeat",
                "--fencing-token",
                fencing_token,
            ]
        )
        == 0
    )
    heartbeat = read_json(capsys)
    assert heartbeat["refreshed"] is True

    assert (
        main(
            [
                "worker-runs",
                "create",
                "--idempotency-key",
                "cli-worker-run-create",
                "--work-item-id",
                work_item_id,
                "--lease-id",
                lease_id,
                "--fencing-token",
                fencing_token,
            ]
        )
        == 0
    )
    worker_run = read_json(capsys)
    worker_run_id = str(worker_run["id"])
    assert worker_run["status"] == "running"

    assert main(["worker-runs", "show", worker_run_id]) == 0
    shown_worker_run = read_json(capsys)
    assert shown_worker_run["lease_id"] == lease_id

    assert (
        main(
            [
                "worker-runs",
                "heartbeat",
                worker_run_id,
                "--idempotency-key",
                "cli-worker-run-heartbeat",
                "--fencing-token",
                fencing_token,
            ]
        )
        == 0
    )
    worker_run_heartbeat = read_json(capsys)
    assert worker_run_heartbeat["status"] == "running"

    assert (
        main(
            [
                "worker-runs",
                "report",
                worker_run_id,
                "--idempotency-key",
                "cli-worker-run-report",
                "--fencing-token",
                fencing_token,
                "--validation-json",
                '{"pytest":"passed"}',
                "--public-mutations-json",
                '{"pr":7}',
            ]
        )
        == 0
    )
    worker_run_report = read_json(capsys)
    assert worker_run_report["status"] == "reporting"
    assert worker_run_report["validation"]["pytest"] == "passed"

    assert (
        main(
            [
                "worker-runs",
                "close",
                worker_run_id,
                "--idempotency-key",
                "cli-worker-run-close",
                "--fencing-token",
                fencing_token,
                "--result",
                "blocked",
                "--cost-summary-json",
                '{"estimated":true}',
            ]
        )
        == 0
    )
    worker_run_close = read_json(capsys)
    assert worker_run_close["status"] == "closed"
    assert worker_run_close["result"] == "blocked"

    assert main(["reconcile", "leases", "--idempotency-key", "cli-reconcile"]) == 0
    reconcile = read_json(capsys)
    assert reconcile["expired_lease_ids"] == []

    assert (
        main(
            [
                "sync",
                "repository",
                "repo-1",
                "--idempotency-key",
                "cli-sync-missing",
            ]
        )
        == 2
    )
    sync = read_json(capsys)
    assert sync["reason_code"] == "repository_not_found"


def test_cli_demo_seed_workbench_and_m1_exit_smoke(
    cli_database: None,
    capsys: CaptureFixture[str],
) -> None:
    assert main(["demo", "seed"]) == 0
    seed = read_json(capsys)
    assert seed["status"] == "seeded"
    assert "m1-demo-ready" in seed["work_item_ids"]

    assert main(["queue", "workbench"]) == 0
    workbench = read_json(capsys)
    assert [section["id"] for section in workbench["sections"]] == [
        "ready",
        "running",
        "blocked",
        "waiting",
        "failed",
        "done",
    ]
    assert workbench["recovery_signals"]

    assert (
        main(
            [
                "smoke",
                "m1-exit",
                "--idempotency-prefix",
                "cli-m1-exit-smoke",
            ]
        )
        == 0
    )
    smoke = read_json(capsys)
    assert smoke["status"] == "passed"


def test_cli_reports_claim_blocked(
    cli_database: None,
    capsys: CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "work-items",
                "create",
                "--idempotency-key",
                "cli-blocked-create",
                "--title",
                "Blocked work",
            ]
        )
        == 0
    )
    created = read_json(capsys)

    assert (
        main(
            [
                "work-items",
                "claim",
                str(created["id"]),
                "--idempotency-key",
                "cli-blocked-claim",
                "--owner",
                "slot-1",
            ]
        )
        == 2
    )
    blocked = read_json(capsys)
    assert blocked["status"] == "blocked"
    assert blocked["reason_code"] == "blocked_by_status"
