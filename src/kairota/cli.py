from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import cast

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from kairota import __version__
from kairota.adapters.github.client import GitHubHttpClient
from kairota.config import get_settings
from kairota.contracts.enums import (
    AutonomyMode,
    RiskLevel,
    WorkerRole,
    WorkerRunResult,
    WorkItemStatus,
    WorkType,
)
from kairota.contracts.schemas import (
    ClaimNextWorkItemCommand,
    ClaimWorkItemCommand,
    LeaseHeartbeatCommand,
    RepositoryCreate,
    SchedulerCycleCreate,
    WorkerRunCloseCommand,
    WorkerRunCreateCommand,
    WorkerRunHeartbeatCommand,
    WorkerRunReportCommand,
    WorkItemCreate,
    WorkItemTriageCommand,
)
from kairota.db import create_session_factory
from kairota.services.demo_data import seed_m1_demo_data
from kairota.services.errors import CommandBlockedError
from kairota.services.github_sync import sync_repository_command
from kairota.services.idempotency import IdempotencyConflictError
from kairota.services.m1_exit import run_m1_exit_smoke
from kairota.services.queue_workbench import queue_workbench
from kairota.services.repositories import (
    get_repository,
    list_repositories,
    register_repository_command,
)
from kairota.services.scheduler_cycles import (
    claim_next_work_item_command,
    claim_work_item_command,
    expire_stale_leases_command,
    heartbeat_lease_command,
    run_scheduler_cycle_command,
)
from kairota.services.work_items import (
    create_work_item_command,
    get_work_item,
    list_work_items,
    queue_summary,
    triage_work_item_command,
)
from kairota.services.worker_runs import (
    close_worker_run_command,
    create_worker_run_command,
    get_worker_run,
    heartbeat_worker_run_command,
    report_worker_run_command,
)


def alembic_config() -> Config:
    return Config("alembic.ini")


def cmd_health(_args: argparse.Namespace) -> int:
    settings = get_settings()
    payload = {
        "status": "ok",
        "service": settings.app_name,
        "version": __version__,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


def cmd_db_upgrade(_args: argparse.Namespace) -> int:
    command.upgrade(alembic_config(), "head")
    return 0


def cmd_db_downgrade(_args: argparse.Namespace) -> int:
    command.downgrade(alembic_config(), "base")
    return 0


def cmd_work_items_create(args: argparse.Namespace) -> int:
    payload = WorkItemCreate(
        title=args.title,
        repository_id=args.repository_id,
        status=args.status,
        priority=args.priority,
        risk=args.risk,
        work_type=args.work_type,
        autonomy_mode=args.autonomy_mode,
        acceptance=args.acceptance,
        validation=args.validation,
        expected_touch=args.expected_touch,
        source_url=args.source_url,
        conflict_keys=tuple(args.conflict_key),
        dependency_ids=tuple(args.dependency_id),
    )
    try:
        with session_scope() as session, session.begin():
            result = create_work_item_command(
                session,
                command=payload,
                idempotency_key=args.idempotency_key,
                actor="cli",
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    except CommandBlockedError as exc:
        print_blocked(exc.reason_code, exc.explanation, exc.details)
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_work_items_list(args: argparse.Namespace) -> int:
    with session_scope() as session:
        status = WorkItemStatus(args.status) if args.status else None
        result = list_work_items(
            session,
            status=status,
            repository_id=args.repository_id,
        )
    print_json([item.model_dump(mode="json") for item in result])
    return 0


def cmd_work_items_show(args: argparse.Namespace) -> int:
    with session_scope() as session:
        result = get_work_item(session, args.work_item_id)
    if result is None:
        print_blocked("not_found", "Work item not found.", {"id": args.work_item_id})
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_work_items_triage(args: argparse.Namespace) -> int:
    payload = WorkItemTriageCommand(
        status=args.status,
        priority=args.priority,
        risk=args.risk,
        work_type=args.work_type,
        autonomy_mode=args.autonomy_mode,
        acceptance=args.acceptance,
        validation=args.validation,
        expected_touch=args.expected_touch,
        conflict_keys=tuple(args.conflict_key),
        dependency_ids=tuple(args.dependency_id),
    )
    try:
        with session_scope() as session, session.begin():
            result = triage_work_item_command(
                session,
                work_item_id=args.work_item_id,
                command=payload,
                idempotency_key=args.idempotency_key,
                actor="cli",
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    except CommandBlockedError as exc:
        print_blocked(exc.reason_code, exc.explanation, exc.details)
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_work_items_claim(args: argparse.Namespace) -> int:
    payload = ClaimWorkItemCommand(
        owner=args.owner,
        lease_ttl_seconds=args.lease_ttl_seconds,
    )
    try:
        with session_scope() as session, session.begin():
            result = claim_work_item_command(
                session,
                work_item_id=args.work_item_id,
                command=payload,
                idempotency_key=args.idempotency_key,
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    except CommandBlockedError as exc:
        print_blocked(exc.reason_code, exc.explanation, exc.details)
        return 2
    if not result.claimed:
        print_blocked(
            str(result.reason or "blocked"),
            result.explanation or "Work item claim was blocked.",
            {
                "work_item_id": result.work_item_id,
                "conflict_keys": result.conflict_keys,
            },
        )
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_queue_summary(_args: argparse.Namespace) -> int:
    with session_scope() as session:
        result = queue_summary(session, repository_id=_args.repository_id)
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_queue_workbench(_args: argparse.Namespace) -> int:
    with session_scope() as session:
        result = queue_workbench(session, repository_id=_args.repository_id)
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_queue_ready(args: argparse.Namespace) -> int:
    with session_scope() as session:
        result = list_work_items(
            session,
            status=WorkItemStatus.READY,
            repository_id=args.repository_id,
        )
    print_json([item.model_dump(mode="json") for item in result])
    return 0


def cmd_queue_claim_next(args: argparse.Namespace) -> int:
    payload = ClaimNextWorkItemCommand(
        owner=args.owner,
        lease_ttl_seconds=args.lease_ttl_seconds,
        repository_id=args.repository_id,
        queue_key=args.queue_key,
    )
    try:
        with session_scope() as session, session.begin():
            result = claim_next_work_item_command(
                session,
                command=payload,
                idempotency_key=args.idempotency_key,
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    except CommandBlockedError as exc:
        print_blocked(exc.reason_code, exc.explanation, exc.details)
        return 2
    if not result.claimed:
        print_blocked(
            str(result.reason or "no_schedulable_work"),
            result.explanation or "No schedulable work item was found.",
            {"repository_id": args.repository_id},
        )
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_demo_seed(_args: argparse.Namespace) -> int:
    with session_scope() as session, session.begin():
        result = seed_m1_demo_data(session)
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_smoke_m1_exit(args: argparse.Namespace) -> int:
    with session_scope() as session, session.begin():
        result = run_m1_exit_smoke(
            session,
            idempotency_prefix=args.idempotency_prefix,
        )
    print_json(result.model_dump(mode="json"))
    return 0 if result.status == "passed" else 2


def cmd_scheduler_run(args: argparse.Namespace) -> int:
    payload = SchedulerCycleCreate(
        queue_key=args.queue_key,
        repository_id=args.repository_id,
        capacity=args.capacity,
    )
    try:
        with session_scope() as session, session.begin():
            result = run_scheduler_cycle_command(
                session,
                command=payload,
                idempotency_key=args.idempotency_key,
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    except CommandBlockedError as exc:
        print_blocked(exc.reason_code, exc.explanation, exc.details)
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_leases_heartbeat(args: argparse.Namespace) -> int:
    payload = LeaseHeartbeatCommand(
        fencing_token=args.fencing_token,
        lease_ttl_seconds=args.lease_ttl_seconds,
    )
    try:
        with session_scope() as session, session.begin():
            result = heartbeat_lease_command(
                session,
                lease_id=args.lease_id,
                command=payload,
                idempotency_key=args.idempotency_key,
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    if not result.refreshed:
        print_blocked(
            "lease_heartbeat_blocked",
            result.explanation or "Lease heartbeat was blocked.",
            {"lease_id": result.lease_id},
        )
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_reconcile_leases(args: argparse.Namespace) -> int:
    try:
        with session_scope() as session, session.begin():
            result = expire_stale_leases_command(
                session,
                idempotency_key=args.idempotency_key,
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_worker_runs_create(args: argparse.Namespace) -> int:
    payload = WorkerRunCreateCommand(
        work_item_id=args.work_item_id,
        lease_id=args.lease_id,
        fencing_token=args.fencing_token,
        role=WorkerRole(args.role),
    )
    try:
        with session_scope() as session, session.begin():
            result = create_worker_run_command(
                session,
                command=payload,
                idempotency_key=args.idempotency_key,
                actor="cli",
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    except CommandBlockedError as exc:
        print_blocked(exc.reason_code, exc.explanation, exc.details)
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_worker_runs_show(args: argparse.Namespace) -> int:
    with session_scope() as session:
        result = get_worker_run(session, args.worker_run_id)
    if result is None:
        print_blocked(
            "not_found",
            "Worker run not found.",
            {"id": args.worker_run_id},
        )
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_worker_runs_heartbeat(args: argparse.Namespace) -> int:
    payload = WorkerRunHeartbeatCommand(fencing_token=args.fencing_token)
    try:
        with session_scope() as session, session.begin():
            result = heartbeat_worker_run_command(
                session,
                worker_run_id=args.worker_run_id,
                command=payload,
                idempotency_key=args.idempotency_key,
                actor="cli",
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    except CommandBlockedError as exc:
        print_blocked(exc.reason_code, exc.explanation, exc.details)
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_worker_runs_report(args: argparse.Namespace) -> int:
    try:
        payload = WorkerRunReportCommand(
            fencing_token=args.fencing_token,
            validation=json_object_arg(args.validation_json),
            public_mutations=json_object_arg(args.public_mutations_json),
            cost_summary=json_object_arg(args.cost_summary_json),
        )
    except ValueError as exc:
        print_blocked("invalid_json", str(exc))
        return 2
    try:
        with session_scope() as session, session.begin():
            result = report_worker_run_command(
                session,
                worker_run_id=args.worker_run_id,
                command=payload,
                idempotency_key=args.idempotency_key,
                actor="cli",
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    except CommandBlockedError as exc:
        print_blocked(exc.reason_code, exc.explanation, exc.details)
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_worker_runs_close(args: argparse.Namespace) -> int:
    try:
        payload = WorkerRunCloseCommand(
            fencing_token=args.fencing_token,
            result=WorkerRunResult(args.result),
            validation=json_object_arg(args.validation_json),
            public_mutations=json_object_arg(args.public_mutations_json),
            cost_summary=json_object_arg(args.cost_summary_json),
        )
    except ValueError as exc:
        print_blocked("invalid_json", str(exc))
        return 2
    try:
        with session_scope() as session, session.begin():
            result = close_worker_run_command(
                session,
                worker_run_id=args.worker_run_id,
                command=payload,
                idempotency_key=args.idempotency_key,
                actor="cli",
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    except CommandBlockedError as exc:
        print_blocked(exc.reason_code, exc.explanation, exc.details)
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_repositories_register(args: argparse.Namespace) -> int:
    payload = RepositoryCreate(
        remote=args.remote,
        name=args.name,
        provider_repo_id=args.provider_repo_id,
        default_branch=args.default_branch,
    )
    try:
        with session_scope() as session, session.begin():
            result = register_repository_command(
                session,
                command=payload,
                idempotency_key=args.idempotency_key,
                actor="cli",
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    except CommandBlockedError as exc:
        print_blocked(exc.reason_code, exc.explanation, exc.details)
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_repositories_list(_args: argparse.Namespace) -> int:
    with session_scope() as session:
        result = list_repositories(session)
    print_json([repository.model_dump(mode="json") for repository in result])
    return 0


def cmd_repositories_show(args: argparse.Namespace) -> int:
    with session_scope() as session:
        result = get_repository(session, args.repository_id)
    if result is None:
        print_blocked(
            "repository_not_found",
            "Repository does not exist.",
            {"repository_id": args.repository_id},
        )
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_sync_repository(args: argparse.Namespace) -> int:
    settings = get_settings()
    client = GitHubHttpClient.from_settings(settings)
    try:
        with session_scope() as session, session.begin():
            result = sync_repository_command(
                session,
                repository_id=args.repository_id,
                idempotency_key=args.idempotency_key,
                client=client,
            )
    except IdempotencyConflictError as exc:
        print_blocked("idempotency_conflict", str(exc))
        return 2
    except CommandBlockedError as exc:
        print_blocked(exc.reason_code, exc.explanation, exc.details)
        return 2
    print_json(result.model_dump(mode="json"))
    return 0


def session_scope() -> Session:
    return create_session_factory()()


def print_json(payload: object) -> None:
    print(json.dumps(payload, sort_keys=True))


def json_object_arg(value: str | None) -> dict[str, object]:
    if value is None:
        return {}
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    return cast(dict[str, object], payload)


def print_blocked(
    reason_code: str,
    explanation: str,
    details: dict[str, object] | None = None,
) -> None:
    print_json(
        {
            "status": "blocked",
            "reason_code": reason_code,
            "explanation": explanation,
            "details": details or {},
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kairota")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    health = subparsers.add_parser("health", help="Print runtime health JSON.")
    health.set_defaults(func=cmd_health)

    db_upgrade = subparsers.add_parser("db-upgrade", help="Apply DB migrations.")
    db_upgrade.set_defaults(func=cmd_db_upgrade)

    db_downgrade = subparsers.add_parser(
        "db-downgrade",
        help="Downgrade DB migrations to base.",
    )
    db_downgrade.set_defaults(func=cmd_db_downgrade)

    work_items = subparsers.add_parser(
        "work-items",
        help="Create and inspect work items.",
    )
    work_item_subparsers = work_items.add_subparsers(
        dest="work_item_command", required=True
    )

    work_item_create = work_item_subparsers.add_parser("create", help="Create work.")
    work_item_create.add_argument("--idempotency-key", required=True)
    work_item_create.add_argument("--title", required=True)
    work_item_create.add_argument("--repository-id")
    work_item_create.add_argument(
        "--status",
        choices=[status.value for status in WorkItemStatus],
        default=WorkItemStatus.NEEDS_TRIAGE.value,
    )
    work_item_create.add_argument("--priority", type=int, default=100)
    work_item_create.add_argument(
        "--risk",
        choices=[risk.value for risk in RiskLevel],
        default=RiskLevel.MEDIUM.value,
    )
    work_item_create.add_argument(
        "--work-type",
        choices=[work_type.value for work_type in WorkType],
        default=WorkType.IMPLEMENTATION.value,
    )
    work_item_create.add_argument(
        "--autonomy-mode",
        choices=[mode.value for mode in AutonomyMode],
        default=AutonomyMode.AI_ASSISTED.value,
    )
    work_item_create.add_argument("--acceptance")
    work_item_create.add_argument("--validation")
    work_item_create.add_argument("--expected-touch")
    work_item_create.add_argument("--source-url")
    work_item_create.add_argument("--conflict-key", action="append", default=[])
    work_item_create.add_argument("--dependency-id", action="append", default=[])
    work_item_create.set_defaults(func=cmd_work_items_create)

    work_item_list = work_item_subparsers.add_parser("list", help="List work.")
    work_item_list.add_argument(
        "--status", choices=[status.value for status in WorkItemStatus]
    )
    work_item_list.add_argument("--repository-id")
    work_item_list.set_defaults(func=cmd_work_items_list)

    work_item_show = work_item_subparsers.add_parser("show", help="Show work.")
    work_item_show.add_argument("work_item_id")
    work_item_show.set_defaults(func=cmd_work_items_show)

    work_item_triage = work_item_subparsers.add_parser(
        "triage", help="Set scheduling facts for work."
    )
    work_item_triage.add_argument("work_item_id")
    work_item_triage.add_argument("--idempotency-key", required=True)
    work_item_triage.add_argument(
        "--status",
        choices=[
            WorkItemStatus.BACKLOG.value,
            WorkItemStatus.READY.value,
            WorkItemStatus.BLOCKED.value,
            WorkItemStatus.HUMAN_DECISION.value,
        ],
        default=WorkItemStatus.READY.value,
    )
    work_item_triage.add_argument("--priority", type=int, default=100)
    work_item_triage.add_argument(
        "--risk",
        choices=[risk.value for risk in RiskLevel],
        default=RiskLevel.MEDIUM.value,
    )
    work_item_triage.add_argument(
        "--work-type",
        choices=[work_type.value for work_type in WorkType],
        default=WorkType.IMPLEMENTATION.value,
    )
    work_item_triage.add_argument(
        "--autonomy-mode",
        choices=[mode.value for mode in AutonomyMode],
        default=AutonomyMode.AI_ASSISTED.value,
    )
    work_item_triage.add_argument("--acceptance")
    work_item_triage.add_argument("--validation")
    work_item_triage.add_argument("--expected-touch")
    work_item_triage.add_argument("--conflict-key", action="append", default=[])
    work_item_triage.add_argument("--dependency-id", action="append", default=[])
    work_item_triage.set_defaults(func=cmd_work_items_triage)

    work_item_claim = work_item_subparsers.add_parser("claim", help="Claim work.")
    work_item_claim.add_argument("work_item_id")
    work_item_claim.add_argument("--idempotency-key", required=True)
    work_item_claim.add_argument("--owner", required=True)
    work_item_claim.add_argument("--lease-ttl-seconds", type=int, default=1800)
    work_item_claim.set_defaults(func=cmd_work_items_claim)

    queue = subparsers.add_parser("queue", help="Inspect queue state.")
    queue_subparsers = queue.add_subparsers(dest="queue_command", required=True)
    queue_summary_parser = queue_subparsers.add_parser(
        "summary", help="Print queue summary."
    )
    queue_summary_parser.add_argument("--repository-id")
    queue_summary_parser.set_defaults(func=cmd_queue_summary)
    queue_workbench_parser = queue_subparsers.add_parser(
        "workbench", help="Print queue workbench read model."
    )
    queue_workbench_parser.add_argument("--repository-id")
    queue_workbench_parser.set_defaults(func=cmd_queue_workbench)
    queue_ready_parser = queue_subparsers.add_parser(
        "ready", help="Print ready work items."
    )
    queue_ready_parser.add_argument("--repository-id")
    queue_ready_parser.set_defaults(func=cmd_queue_ready)
    queue_claim_next_parser = queue_subparsers.add_parser(
        "claim-next", help="Claim the next schedulable work item."
    )
    queue_claim_next_parser.add_argument("--idempotency-key", required=True)
    queue_claim_next_parser.add_argument("--owner", required=True)
    queue_claim_next_parser.add_argument("--repository-id")
    queue_claim_next_parser.add_argument("--queue-key", default="default")
    queue_claim_next_parser.add_argument("--lease-ttl-seconds", type=int, default=1800)
    queue_claim_next_parser.set_defaults(func=cmd_queue_claim_next)

    demo = subparsers.add_parser("demo", help="Seed local demo data.")
    demo_subparsers = demo.add_subparsers(dest="demo_command", required=True)
    demo_seed = demo_subparsers.add_parser("seed", help="Seed M1 queue demo records.")
    demo_seed.set_defaults(func=cmd_demo_seed)

    smoke = subparsers.add_parser("smoke", help="Run local smoke checks.")
    smoke_subparsers = smoke.add_subparsers(dest="smoke_command", required=True)
    smoke_m1_exit = smoke_subparsers.add_parser(
        "m1-exit", help="Run the M1 exit smoke check."
    )
    smoke_m1_exit.add_argument(
        "--idempotency-prefix",
        default="m1-exit-smoke",
        help="Prefix for deterministic smoke idempotency keys.",
    )
    smoke_m1_exit.set_defaults(func=cmd_smoke_m1_exit)

    scheduler = subparsers.add_parser("scheduler", help="Run scheduler commands.")
    scheduler_subparsers = scheduler.add_subparsers(
        dest="scheduler_command", required=True
    )
    scheduler_run = scheduler_subparsers.add_parser(
        "run", help="Run one scheduler cycle."
    )
    scheduler_run.add_argument("--idempotency-key", required=True)
    scheduler_run.add_argument("--queue-key", default="default")
    scheduler_run.add_argument("--repository-id")
    scheduler_run.add_argument("--capacity", type=int, default=1)
    scheduler_run.set_defaults(func=cmd_scheduler_run)

    leases = subparsers.add_parser("leases", help="Manage leases.")
    lease_subparsers = leases.add_subparsers(dest="lease_command", required=True)
    lease_heartbeat = lease_subparsers.add_parser("heartbeat", help="Refresh a lease.")
    lease_heartbeat.add_argument("lease_id")
    lease_heartbeat.add_argument("--idempotency-key", required=True)
    lease_heartbeat.add_argument("--fencing-token", required=True)
    lease_heartbeat.add_argument("--lease-ttl-seconds", type=int, default=1800)
    lease_heartbeat.set_defaults(func=cmd_leases_heartbeat)

    reconcile = subparsers.add_parser("reconcile", help="Run reconciliation commands.")
    reconcile_subparsers = reconcile.add_subparsers(
        dest="reconcile_command", required=True
    )
    reconcile_leases = reconcile_subparsers.add_parser(
        "leases", help="Expire stale leases."
    )
    reconcile_leases.add_argument("--idempotency-key", required=True)
    reconcile_leases.set_defaults(func=cmd_reconcile_leases)

    worker_runs = subparsers.add_parser(
        "worker-runs",
        help="Manage worker run lifecycle records.",
    )
    worker_run_subparsers = worker_runs.add_subparsers(
        dest="worker_run_command", required=True
    )
    worker_run_create = worker_run_subparsers.add_parser(
        "create", help="Start a worker run."
    )
    worker_run_create.add_argument("--idempotency-key", required=True)
    worker_run_create.add_argument("--work-item-id", required=True)
    worker_run_create.add_argument("--lease-id", required=True)
    worker_run_create.add_argument("--fencing-token", required=True)
    worker_run_create.add_argument(
        "--role",
        choices=[role.value for role in WorkerRole],
        default=WorkerRole.WORKER.value,
    )
    worker_run_create.set_defaults(func=cmd_worker_runs_create)

    worker_run_show = worker_run_subparsers.add_parser("show", help="Show a run.")
    worker_run_show.add_argument("worker_run_id")
    worker_run_show.set_defaults(func=cmd_worker_runs_show)

    worker_run_heartbeat = worker_run_subparsers.add_parser(
        "heartbeat", help="Refresh a worker run heartbeat."
    )
    worker_run_heartbeat.add_argument("worker_run_id")
    worker_run_heartbeat.add_argument("--idempotency-key", required=True)
    worker_run_heartbeat.add_argument("--fencing-token", required=True)
    worker_run_heartbeat.set_defaults(func=cmd_worker_runs_heartbeat)

    worker_run_report = worker_run_subparsers.add_parser(
        "report", help="Record worker run evidence."
    )
    worker_run_report.add_argument("worker_run_id")
    worker_run_report.add_argument("--idempotency-key", required=True)
    worker_run_report.add_argument("--fencing-token", required=True)
    worker_run_report.add_argument("--validation-json")
    worker_run_report.add_argument("--public-mutations-json")
    worker_run_report.add_argument("--cost-summary-json")
    worker_run_report.set_defaults(func=cmd_worker_runs_report)

    worker_run_close = worker_run_subparsers.add_parser(
        "close", help="Close a worker run."
    )
    worker_run_close.add_argument("worker_run_id")
    worker_run_close.add_argument("--idempotency-key", required=True)
    worker_run_close.add_argument("--fencing-token", required=True)
    worker_run_close.add_argument(
        "--result",
        choices=[result.value for result in WorkerRunResult],
        required=True,
    )
    worker_run_close.add_argument("--validation-json")
    worker_run_close.add_argument("--public-mutations-json")
    worker_run_close.add_argument("--cost-summary-json")
    worker_run_close.set_defaults(func=cmd_worker_runs_close)

    repositories = subparsers.add_parser(
        "repositories",
        help="Register and inspect managed repositories.",
    )
    repository_subparsers = repositories.add_subparsers(
        dest="repository_command", required=True
    )
    repository_register = repository_subparsers.add_parser(
        "register", help="Register a managed GitHub repository."
    )
    repository_register.add_argument("--idempotency-key", required=True)
    repository_register.add_argument("--remote")
    repository_register.add_argument("--name")
    repository_register.add_argument("--provider-repo-id")
    repository_register.add_argument("--default-branch", default="main")
    repository_register.set_defaults(func=cmd_repositories_register)
    repository_list = repository_subparsers.add_parser(
        "list", help="List managed repositories."
    )
    repository_list.set_defaults(func=cmd_repositories_list)
    repository_show = repository_subparsers.add_parser(
        "show", help="Show a managed repository."
    )
    repository_show.add_argument("repository_id")
    repository_show.set_defaults(func=cmd_repositories_show)

    sync = subparsers.add_parser("sync", help="Run adapter sync commands.")
    sync_subparsers = sync.add_subparsers(dest="sync_command", required=True)
    sync_repository = sync_subparsers.add_parser(
        "repository", help="Sync one repository."
    )
    sync_repository.add_argument("repository_id")
    sync_repository.add_argument("--idempotency-key", required=True)
    sync_repository.set_defaults(func=cmd_sync_repository)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


__all__ = ["main"]
