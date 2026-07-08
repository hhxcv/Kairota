from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from kairota import __version__
from kairota.config import get_settings
from kairota.contracts.enums import (
    AutonomyMode,
    RiskLevel,
    WorkItemStatus,
    WorkType,
)
from kairota.contracts.schemas import (
    ClaimWorkItemCommand,
    LeaseHeartbeatCommand,
    SchedulerCycleCreate,
    WorkItemCreate,
)
from kairota.db import create_session_factory
from kairota.services.errors import CommandBlockedError
from kairota.services.idempotency import IdempotencyConflictError
from kairota.services.scheduler_cycles import (
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
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_work_items_list(args: argparse.Namespace) -> int:
    with session_scope() as session:
        status = WorkItemStatus(args.status) if args.status else None
        result = list_work_items(session, status=status)
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
        result = queue_summary(session)
    print_json(result.model_dump(mode="json"))
    return 0


def cmd_scheduler_run(args: argparse.Namespace) -> int:
    payload = SchedulerCycleCreate(queue_key=args.queue_key, capacity=args.capacity)
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


def cmd_sync_repository(args: argparse.Namespace) -> int:
    print_blocked(
        "not_implemented_yet",
        "Repository sync is planned for M1.5 and is not implemented yet.",
        {"repository_id": args.repository_id},
    )
    return 2


def session_scope() -> Session:
    return create_session_factory()()


def print_json(payload: object) -> None:
    print(json.dumps(payload, sort_keys=True))


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
    work_item_list.set_defaults(func=cmd_work_items_list)

    work_item_show = work_item_subparsers.add_parser("show", help="Show work.")
    work_item_show.add_argument("work_item_id")
    work_item_show.set_defaults(func=cmd_work_items_show)

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
    queue_summary_parser.set_defaults(func=cmd_queue_summary)

    scheduler = subparsers.add_parser("scheduler", help="Run scheduler commands.")
    scheduler_subparsers = scheduler.add_subparsers(
        dest="scheduler_command", required=True
    )
    scheduler_run = scheduler_subparsers.add_parser(
        "run", help="Run one scheduler cycle."
    )
    scheduler_run.add_argument("--idempotency-key", required=True)
    scheduler_run.add_argument("--queue-key", default="default")
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

    sync = subparsers.add_parser("sync", help="Run adapter sync commands.")
    sync_subparsers = sync.add_subparsers(dest="sync_command", required=True)
    sync_repository = sync_subparsers.add_parser(
        "repository", help="Sync one repository."
    )
    sync_repository.add_argument("repository_id")
    sync_repository.set_defaults(func=cmd_sync_repository)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


__all__ = ["main"]
