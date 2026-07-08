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
    create_code = main(
        [
            "work-items",
            "create",
            "--idempotency-key",
            "cli-create",
            "--title",
            "CLI work",
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
    created = read_json(capsys)
    work_item_id = str(created["id"])
    assert create_code == 0
    assert created["status"] == "ready"

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
