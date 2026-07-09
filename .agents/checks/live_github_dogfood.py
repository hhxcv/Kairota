"""Run an opt-in live GitHub dogfood scheduling scenario.

This check creates temporary GitHub issues in the current repository, syncs
them into an isolated Kairota database, verifies scheduling behavior, and then
closes the temporary issues. It requires the GitHub CLI and authenticated issue
write access.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from collections import Counter
from collections.abc import MutableSet, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kairota.adapters.github.client import GitHubHttpClient
from kairota.api.app import create_app
from kairota.config import Settings

ROOT = Path(__file__).resolve().parents[2]
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
ISSUE_NUMBER_RE = re.compile(r"/issues/(?P<number>\d+)")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get("KAIROTA_GITHUB_TOKEN") or gh_auth_token()
    repo = args.repo or current_github_repo()
    run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    prefix = f"Dogfood live {run_id}"
    issue_numbers: list[int] = []
    issue_numbers_by_key: dict[str, int] = {}
    closed_issue_numbers: set[int] = set()
    cleanup_errors: list[str] = []
    summary: dict[str, Any] | None = None

    try:
        for key in ISSUE_KEYS:
            issue_number = create_issue(repo, prefix, key)
            issue_numbers.append(issue_number)
            issue_numbers_by_key[key] = issue_number
        summary = run_kairota_scenario(
            repo=repo,
            token=token,
            run_id=run_id,
            prefix=prefix,
            issue_numbers_by_key=issue_numbers_by_key,
            closed_issue_numbers=closed_issue_numbers,
            worker_cap=args.worker_cap,
            sync_attempts=args.sync_attempts,
            sync_wait_seconds=args.sync_wait_seconds,
            database_url=args.database_url,
        )
        summary["temporary_issues_created"] = len(issue_numbers)
        summary["temporary_issue_cleanup"] = (
            "skipped" if args.keep_issues else "requested"
        )
        if args.summary_output:
            Path(args.summary_output).write_text(
                json.dumps(summary, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    finally:
        if not args.keep_issues:
            for number in issue_numbers:
                if number in closed_issue_numbers:
                    continue
                try:
                    close_issue(repo, number)
                except subprocess.CalledProcessError as exc:
                    cleanup_errors.append(str(exc.returncode))
            if cleanup_errors:
                print(
                    json.dumps(
                        {
                            "cleanup_status": "incomplete",
                            "cleanup_errors": len(cleanup_errors),
                        },
                        sort_keys=True,
                    )
                )


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create, sync, schedule, and close 24 live dogfood issues."
    )
    parser.add_argument("--repo", help="GitHub repository in owner/name form.")
    parser.add_argument("--worker-cap", type=int, default=4)
    parser.add_argument("--sync-attempts", type=int, default=6)
    parser.add_argument("--sync-wait-seconds", type=float, default=10.0)
    parser.add_argument(
        "--database-url",
        help="Optional SQLAlchemy database URL to preserve for API/UI inspection.",
    )
    parser.add_argument(
        "--summary-output",
        help="Optional JSON path for the validation summary.",
    )
    parser.add_argument(
        "--keep-issues",
        action="store_true",
        help="Leave temporary issues open for manual inspection.",
    )
    return parser.parse_args(argv)


def gh_auth_token() -> str:
    token = run_gh(["auth", "token"]).strip()
    if not token:
        raise RuntimeError("GitHub token is unavailable from gh auth token.")
    return token


def current_github_repo() -> str:
    return run_gh(
        ["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    ).strip()


def create_issue(repo: str, prefix: str, key: str) -> int:
    output = run_gh(
        [
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            f"{prefix} {key}",
            "--body",
            (
                "Temporary Kairota live dogfood validation issue. "
                "The validation check closes it automatically."
            ),
        ]
    )
    match = ISSUE_NUMBER_RE.search(output)
    if match is None:
        raise RuntimeError("Could not parse created issue number from gh output.")
    return int(match.group("number"))


def close_issue(repo: str, number: int) -> None:
    run_gh(
        [
            "issue",
            "close",
            str(number),
            "--repo",
            repo,
            "--comment",
            "Closing temporary Kairota live dogfood validation issue.",
        ]
    )


def run_gh(args: Sequence[str]) -> str:
    result = subprocess.run(
        ["gh", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def run_kairota_scenario(
    *,
    repo: str,
    token: str,
    run_id: str,
    prefix: str,
    issue_numbers_by_key: dict[str, int],
    closed_issue_numbers: MutableSet[int],
    worker_cap: int,
    sync_attempts: int,
    sync_wait_seconds: float,
    database_url: str | None = None,
) -> dict[str, Any]:
    if database_url is not None:
        return run_kairota_scenario_in_database(
            repo=repo,
            token=token,
            run_id=run_id,
            prefix=prefix,
            issue_numbers_by_key=issue_numbers_by_key,
            closed_issue_numbers=closed_issue_numbers,
            worker_cap=worker_cap,
            sync_attempts=sync_attempts,
            sync_wait_seconds=sync_wait_seconds,
            db_url=database_url,
        )
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "kairota.sqlite"
        db_url = f"sqlite:///{db_path.as_posix()}"
        return run_kairota_scenario_in_database(
            repo=repo,
            token=token,
            run_id=run_id,
            prefix=prefix,
            issue_numbers_by_key=issue_numbers_by_key,
            closed_issue_numbers=closed_issue_numbers,
            worker_cap=worker_cap,
            sync_attempts=sync_attempts,
            sync_wait_seconds=sync_wait_seconds,
            db_url=db_url,
        )


def run_kairota_scenario_in_database(
    *,
    repo: str,
    token: str,
    run_id: str,
    prefix: str,
    issue_numbers_by_key: dict[str, int],
    closed_issue_numbers: MutableSet[int],
    worker_cap: int,
    sync_attempts: int,
    sync_wait_seconds: float,
    db_url: str,
) -> dict[str, Any]:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(config, "head")
    engine = create_engine(db_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        settings = Settings(
            app_name="Kairota Live Dogfood",
            database_url=db_url,
            github_token=token,
        )
        client = TestClient(
            create_app(
                settings,
                session_factory=session_factory,
                github_client=GitHubHttpClient.from_settings(settings),
            )
        )
        repository_id = register_repository(client, repo, run_id)
        work_items = sync_until_observed(
            client,
            repository_id,
            run_id,
            prefix,
            sync_attempts,
            sync_wait_seconds,
        )
        by_key = {
            item["title"].replace(f"{prefix} ", ""): str(item["id"])
            for item in work_items
        }
        triage_scenario(client, by_key, run_id)
        claims = claim_workers(client, repository_id, run_id, worker_cap)
        worker_runs = [
            start_worker_run(
                client,
                run_id,
                claim,
                worker_index=index,
            )
            for index, claim in enumerate(claims, start=1)
        ]
        capped = post(
            client,
            "/queue/claim-next",
            f"live-{run_id}-claim-cap",
            {
                "repository_id": repository_id,
                "queue_key": "live-dogfood",
                "owner": "live-worker-over-cap",
                "max_active_leases": worker_cap,
            },
            expected_status=409,
        )
        plan_before_done = run_scenario_plan(
            client,
            repository_id,
            run_id,
            "before-done",
            by_key,
        )

        complete_issue_work(
            client,
            repo=repo,
            issue_numbers_by_key=issue_numbers_by_key,
            closed_issue_numbers=closed_issue_numbers,
            repository_id=repository_id,
            run_id=run_id,
            key="A01",
            claim=claims[0],
            worker_run=worker_runs[0],
        )
        replacement_b01 = claim_one_worker(
            client,
            repository_id,
            run_id,
            "replacement-b01",
            "live-worker-replacement-b01",
            worker_cap,
        )
        replacement_b01_run = start_worker_run(
            client,
            run_id,
            replacement_b01,
            worker_index=5,
        )
        complete_issue_work(
            client,
            repo=repo,
            issue_numbers_by_key=issue_numbers_by_key,
            closed_issue_numbers=closed_issue_numbers,
            repository_id=repository_id,
            run_id=run_id,
            key="A02",
            claim=claims[1],
            worker_run=worker_runs[1],
        )
        complete_issue_work(
            client,
            repo=repo,
            issue_numbers_by_key=issue_numbers_by_key,
            closed_issue_numbers=closed_issue_numbers,
            repository_id=repository_id,
            run_id=run_id,
            key="B01",
            claim=replacement_b01,
            worker_run=replacement_b01_run,
        )
        replacement_b02 = claim_one_worker(
            client,
            repository_id,
            run_id,
            "replacement-b02",
            "live-worker-replacement-b02",
            worker_cap,
        )
        replacement_c01 = claim_one_worker(
            client,
            repository_id,
            run_id,
            "replacement-c01",
            "live-worker-replacement-c01",
            worker_cap,
        )
        capped_after_replacements = post(
            client,
            "/queue/claim-next",
            f"live-{run_id}-claim-cap-after-replacements",
            {
                "repository_id": repository_id,
                "queue_key": "live-dogfood",
                "owner": "live-worker-over-cap-after-replacements",
                "max_active_leases": worker_cap,
            },
            expected_status=409,
        )
        plan_after_done = run_scenario_plan(
            client,
            repository_id,
            run_id,
            "after-done",
            by_key,
        )
        workbench = get_workbench(client, repository_id)
        summary = client.get(f"/queue/summary?repository_id={repository_id}")
        assert summary.status_code == 200
        return {
            "status": "passed",
            "run_id": run_id,
            "scenario_prefix": prefix,
            "repository_id": repository_id,
            "issues_observed": len(work_items),
            "initial_claimed": [
                item_key(by_key, str(claim["work_item_id"])) for claim in claims
            ],
            "capacity_reason": capped["reason_code"],
            "capacity_reason_after_replacements": capped_after_replacements[
                "reason_code"
            ],
            "plan_before_done": plan_before_done,
            "plan_after_done": plan_after_done,
            "completed_issue_keys": ["A01", "A02", "B01"],
            "replacement_claimed": [
                item_key(by_key, str(replacement_b01["work_item_id"])),
                item_key(by_key, str(replacement_b02["work_item_id"])),
                item_key(by_key, str(replacement_c01["work_item_id"])),
            ],
            "section_counts": section_counts(workbench),
            "active_leases": summary.json()["active_leases"],
        }
    finally:
        engine.dispose()


def register_repository(client: TestClient, repo: str, run_id: str) -> str:
    response = post(
        client,
        "/repositories",
        f"live-{run_id}-register",
        {"remote": repo},
    )
    return str(response["id"])


def sync_until_observed(
    client: TestClient,
    repository_id: str,
    run_id: str,
    prefix: str,
    sync_attempts: int,
    sync_wait_seconds: float,
) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    for attempt in range(1, sync_attempts + 1):
        post(
            client,
            f"/repositories/{repository_id}/sync",
            f"live-{run_id}-sync-{attempt}",
            {},
        )
        response = client.get(f"/work-items?repository_id={repository_id}")
        assert response.status_code == 200
        observed = [
            item
            for item in response.json()
            if str(item["title"]).startswith(f"{prefix} ")
        ]
        if len(observed) == len(ISSUE_KEYS):
            return observed
        time.sleep(sync_wait_seconds)
    raise RuntimeError(
        f"Observed {len(observed)} of {len(ISSUE_KEYS)} temporary issues after sync."
    )


def triage_scenario(client: TestClient, by_key: dict[str, str], run_id: str) -> None:
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
        post(
            client,
            f"/work-items/{by_key[key]}/triage",
            f"live-{run_id}-triage-{key}",
            payload,
        )

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


def run_scenario_plan(
    client: TestClient,
    repository_id: str,
    run_id: str,
    label: str,
    by_key: dict[str, str],
) -> dict[str, Any]:
    cycle = post(
        client,
        "/scheduler/cycles",
        f"live-{run_id}-plan-{label}",
        {
            "repository_id": repository_id,
            "queue_key": "live-dogfood",
            "capacity": len(ISSUE_KEYS),
        },
    )
    decisions_by_key = {
        item_key(by_key, str(decision["work_item_id"])): decision["code"]
        for decision in cycle["decisions"]
    }
    code_counts = Counter(str(code) for code in decisions_by_key.values())
    assert_decision_subset(label, decisions_by_key)
    return {
        "assigned_count": cycle["assigned_count"],
        "rejected_count": cycle["rejected_count"],
        "code_counts": dict(sorted(code_counts.items())),
        "selected_decisions": {
            key: decisions_by_key.get(key)
            for key in (
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
                "G01",
                "G02",
            )
        },
    }


def assert_decision_subset(label: str, decisions_by_key: dict[str, str]) -> None:
    expected_before_done = {
        "B01": "assigned",
        "B02": "blocked_by_conflict_key",
        "C01": "blocked_by_dependency",
        "C02": "blocked_by_dependency",
        "D01": "assigned",
        "D02": "assigned",
        "D03": "assigned",
        "E01": "blocked_by_status",
        "E02": "blocked_by_status",
        "E03": "blocked_by_status",
        "G01": "assigned",
        "G02": "blocked_by_conflict_key",
    }
    expected_after_done = {
        "B02": "blocked_by_status",
        "C01": "blocked_by_status",
        "C02": "assigned",
        "D01": "assigned",
        "D02": "assigned",
        "D03": "assigned",
        "E01": "blocked_by_status",
        "E02": "blocked_by_status",
        "E03": "blocked_by_status",
        "G01": "assigned",
        "G02": "blocked_by_conflict_key",
    }
    expected = (
        expected_before_done if label == "before-done" else expected_after_done
    )
    mismatches = {
        key: {"expected": value, "actual": decisions_by_key.get(key)}
        for key, value in expected.items()
        if decisions_by_key.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"Unexpected scheduler decisions for {label}: {mismatches}")


def claim_workers(
    client: TestClient,
    repository_id: str,
    run_id: str,
    worker_cap: int,
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for index in range(1, worker_cap + 1):
        claims.append(
            post(
                client,
                "/queue/claim-next",
                f"live-{run_id}-claim-{index}",
                {
                    "repository_id": repository_id,
                    "queue_key": "live-dogfood",
                    "owner": f"live-worker-{index}",
                    "max_active_leases": worker_cap,
                },
            )
        )
    return claims


def claim_one_worker(
    client: TestClient,
    repository_id: str,
    run_id: str,
    claim_key: str,
    owner: str,
    worker_cap: int,
) -> dict[str, Any]:
    claim = post(
        client,
        "/queue/claim-next",
        f"live-{run_id}-claim-{claim_key}",
        {
            "repository_id": repository_id,
            "queue_key": "live-dogfood",
            "owner": owner,
            "max_active_leases": worker_cap,
        },
    )
    if not claim.get("claimed"):
        raise RuntimeError(f"Expected claim for {claim_key}, got {claim}.")
    return claim


def start_worker_run(
    client: TestClient,
    run_id: str,
    claim: dict[str, Any],
    *,
    worker_index: int,
) -> dict[str, Any]:
    return post(
        client,
        "/worker-runs",
        f"live-{run_id}-run-{worker_index}",
        {
            "work_item_id": claim["work_item_id"],
            "lease_id": claim["lease_id"],
            "fencing_token": claim["fencing_token"],
            "role": "worker",
        },
    )


def complete_issue_work(
    client: TestClient,
    *,
    repo: str,
    issue_numbers_by_key: dict[str, int],
    closed_issue_numbers: MutableSet[int],
    repository_id: str,
    run_id: str,
    key: str,
    claim: dict[str, Any],
    worker_run: dict[str, Any],
) -> None:
    issue_number = issue_numbers_by_key[key]
    close_issue(repo, issue_number)
    closed_issue_numbers.add(issue_number)
    sync_until_work_item_done(
        client,
        repository_id=repository_id,
        run_id=run_id,
        key=key,
        work_item_id=str(claim["work_item_id"]),
    )
    close_worker_run_done(client, run_id, key, worker_run, claim)


def sync_until_work_item_done(
    client: TestClient,
    *,
    repository_id: str,
    run_id: str,
    key: str,
    work_item_id: str,
    attempts: int = 6,
    wait_seconds: float = 3.0,
) -> None:
    for attempt in range(1, attempts + 1):
        post(
            client,
            f"/repositories/{repository_id}/sync",
            f"live-{run_id}-sync-close-{key}-{attempt}",
            {},
        )
        response = client.get(f"/work-items/{work_item_id}")
        assert response.status_code == 200
        if response.json()["status"] == "done":
            return
        time.sleep(wait_seconds)
    raise RuntimeError(f"{key} did not sync to done after GitHub issue close.")


def close_worker_run_done(
    client: TestClient,
    run_id: str,
    key: str,
    worker_run: dict[str, Any],
    claim: dict[str, Any],
) -> None:
    post(
        client,
        f"/worker-runs/{worker_run['id']}/report",
        f"live-{run_id}-report-{key}",
        {
            "fencing_token": claim["fencing_token"],
            "validation": {"scenario": "live-worker-completed-issue"},
            "public_mutations": {"closed_issue_key": key},
        },
    )
    post(
        client,
        f"/worker-runs/{worker_run['id']}/close",
        f"live-{run_id}-close-{key}",
        {
            "fencing_token": claim["fencing_token"],
            "result": "done",
            "validation": {"source": "github_issue_closed"},
        },
    )


def get_workbench(client: TestClient, repository_id: str) -> dict[str, Any]:
    response = client.get(f"/queue/workbench?repository_id={repository_id}")
    assert response.status_code == 200
    return dict(response.json())


def section_counts(workbench: dict[str, Any]) -> dict[str, int]:
    return {
        str(section["id"]): int(section["count"])
        for section in workbench["sections"]
    }


def post(
    client: TestClient,
    path: str,
    key: str,
    payload: dict[str, object],
    *,
    expected_status: int = 200,
) -> dict[str, Any]:
    response = client.post(path, headers={"Idempotency-Key": key}, json=payload)
    if response.status_code != expected_status:
        raise RuntimeError(
            f"{path} returned {response.status_code}: {response.text[:500]}"
        )
    return dict(response.json())


def item_key(by_key: dict[str, str], work_item_id: str) -> str:
    for key, candidate_id in by_key.items():
        if candidate_id == work_item_id:
            return key
    return work_item_id


if __name__ == "__main__":
    raise SystemExit(main())
