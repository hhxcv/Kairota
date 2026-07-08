from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from kairota.contracts.enums import (
    AutonomyMode,
    LeaseStatus,
    RiskLevel,
    SchedulerDecisionCode,
    WorkerRunResult,
    WorkItemStatus,
    WorkType,
)
from kairota.contracts.schemas import (
    ClaimWorkItemCommand,
    M1ExitSmokeRead,
    SchedulerCycleCreate,
    SmokeCheckRead,
    WorkerRunCloseCommand,
    WorkerRunCreateCommand,
    WorkerRunReportCommand,
    WorkItemCreate,
)
from kairota.services.demo_data import (
    ensure_conflict_keys,
    ensure_lease,
    ensure_lock_holder,
    ensure_work_item,
    seed_m1_demo_data,
)
from kairota.services.queue_workbench import queue_workbench
from kairota.services.scheduler_cycles import (
    claim_work_item_command,
    expire_stale_leases_command,
    run_scheduler_cycle_command,
)
from kairota.services.work_items import create_work_item_command
from kairota.services.worker_runs import (
    close_worker_run_command,
    create_worker_run_command,
    report_worker_run_command,
)


def run_m1_exit_smoke(
    session: Session,
    *,
    idempotency_prefix: str = "m1-exit-smoke",
) -> M1ExitSmokeRead:
    checks: list[SmokeCheckRead] = []
    seed = seed_m1_demo_data(session)
    record_check(
        checks,
        "seed_demo_data",
        seed.status == "seeded" and len(seed.work_item_ids) >= 6,
        {
            "work_items": len(seed.work_item_ids),
            "repositories": len(seed.repository_ids),
        },
    )

    happy_path = run_happy_path(session, idempotency_prefix=idempotency_prefix)
    checks.extend(happy_path)
    failure_paths = run_failure_paths(session, idempotency_prefix=idempotency_prefix)
    checks.extend(failure_paths)
    workbench = queue_workbench(session)
    section_ids = tuple(section.id for section in workbench.sections)
    record_check(
        checks,
        "workbench_sections_visible",
        section_ids == ("ready", "running", "blocked", "waiting", "failed", "done"),
        {"sections": section_ids},
    )
    decision_ids = {row.id for row in workbench.decision_inbox}
    record_check(
        checks,
        "ci_and_review_gates_visible",
        {"m1-demo-failed", "m1-demo-review"}.issubset(decision_ids),
        {"decision_count": len(decision_ids)},
    )
    recovery_signal_ids = {signal.id for signal in workbench.recovery_signals}
    record_check(
        checks,
        "recovery_signals_visible",
        bool(recovery_signal_ids),
        {"signals": tuple(sorted(recovery_signal_ids))},
    )
    status = "passed" if all(check.status == "passed" for check in checks) else "failed"
    return M1ExitSmokeRead(status=status, checks=tuple(checks))


def run_happy_path(
    session: Session,
    *,
    idempotency_prefix: str,
) -> tuple[SmokeCheckRead, ...]:
    checks: list[SmokeCheckRead] = []
    happy_conflict_key = f"runtime:{idempotency_prefix}:happy"
    work_item = create_work_item_command(
        session,
        command=WorkItemCreate(
            title="M1 smoke implementable work",
            status=WorkItemStatus.READY,
            priority=5,
            risk=RiskLevel.MEDIUM,
            work_type=WorkType.IMPLEMENTATION,
            autonomy_mode=AutonomyMode.AI_ASSISTED,
            acceptance="Smoke work can be claimed and reported.",
            validation="M1 exit smoke passes.",
            expected_touch="src/kairota/services/m1_exit.py",
            conflict_keys=(happy_conflict_key,),
        ),
        idempotency_key=f"{idempotency_prefix}:happy:create",
        actor="smoke",
    )
    cycle = run_scheduler_cycle_command(
        session,
        command=SchedulerCycleCreate(queue_key="m1-exit-smoke", capacity=1),
        idempotency_key=f"{idempotency_prefix}:happy:schedule",
    )
    claim = claim_work_item_command(
        session,
        work_item_id=work_item.id,
        command=ClaimWorkItemCommand(owner="m1-smoke-slot", lease_ttl_seconds=1800),
        idempotency_key=f"{idempotency_prefix}:happy:claim",
    )
    record_check(
        checks,
        "schedule_and_claim_ready_work",
        cycle.assigned_count >= 1 and claim.claimed and claim.lease_id is not None,
        {"work_item_id": work_item.id},
    )
    if not claim.lease_id or not claim.fencing_token:
        return tuple(checks)

    worker_run = create_worker_run_command(
        session,
        command=WorkerRunCreateCommand(
            work_item_id=work_item.id,
            lease_id=claim.lease_id,
            fencing_token=claim.fencing_token,
        ),
        idempotency_key=f"{idempotency_prefix}:happy:worker-run:create",
        actor="smoke",
    )
    reported = report_worker_run_command(
        session,
        worker_run_id=worker_run.id,
        command=WorkerRunReportCommand(
            fencing_token=claim.fencing_token,
            validation={"m1_exit_smoke": "reported"},
            public_mutations={"repository": "none"},
        ),
        idempotency_key=f"{idempotency_prefix}:happy:worker-run:report",
        actor="smoke",
    )
    closed = close_worker_run_command(
        session,
        worker_run_id=worker_run.id,
        command=WorkerRunCloseCommand(
            fencing_token=claim.fencing_token,
            result=WorkerRunResult.BLOCKED,
            validation={"m1_exit_smoke": "closed"},
        ),
        idempotency_key=f"{idempotency_prefix}:happy:worker-run:close",
        actor="smoke",
    )
    record_check(
        checks,
        "worker_run_lifecycle_records_evidence",
        reported.validation.get("m1_exit_smoke") == "reported"
        and closed.result == WorkerRunResult.BLOCKED.value,
        {"worker_run_id": worker_run.id},
    )
    return tuple(checks)


def run_failure_paths(
    session: Session,
    *,
    idempotency_prefix: str,
) -> tuple[SmokeCheckRead, ...]:
    checks: list[SmokeCheckRead] = []
    conflict_key = f"runtime:{idempotency_prefix}:conflict"
    stale_conflict_key = f"runtime:{idempotency_prefix}:stale-lease"
    blocker = create_work_item_command(
        session,
        command=WorkItemCreate(
            title="M1 smoke unfinished dependency",
            status=WorkItemStatus.BACKLOG,
            priority=70,
            risk=RiskLevel.MEDIUM,
            work_type=WorkType.IMPLEMENTATION,
            autonomy_mode=AutonomyMode.AI_ASSISTED,
            acceptance="Dependency remains incomplete.",
            validation="Dependency smoke.",
            expected_touch="docs/validation/m1-exit-checklist.md",
        ),
        idempotency_key=f"{idempotency_prefix}:dependency:blocker",
        actor="smoke",
    )
    dependent = create_work_item_command(
        session,
        command=WorkItemCreate(
            title="M1 smoke dependency-blocked work",
            status=WorkItemStatus.READY,
            priority=71,
            risk=RiskLevel.MEDIUM,
            work_type=WorkType.IMPLEMENTATION,
            autonomy_mode=AutonomyMode.AI_ASSISTED,
            acceptance="Scheduler rejects incomplete dependency.",
            validation="Dependency smoke.",
            expected_touch="src/kairota/scheduler/planner.py",
            dependency_ids=(blocker.id,),
            conflict_keys=("runtime:m1-smoke-dependency",),
        ),
        idempotency_key=f"{idempotency_prefix}:dependency:dependent",
        actor="smoke",
    )
    dependency_cycle = run_scheduler_cycle_command(
        session,
        command=SchedulerCycleCreate(queue_key="m1-exit-smoke-dependency", capacity=10),
        idempotency_key=f"{idempotency_prefix}:dependency:schedule",
    )
    dependency_decision = next(
        (
            decision
            for decision in dependency_cycle.decisions
            if decision.work_item_id == dependent.id
        ),
        None,
    )
    record_check(
        checks,
        "blocked_dependency_rejected",
        dependency_decision is not None
        and dependency_decision.code == SchedulerDecisionCode.BLOCKED_BY_DEPENDENCY,
        {"work_item_id": dependent.id},
    )

    first_conflict = create_work_item_command(
        session,
        command=WorkItemCreate(
            title="M1 smoke first conflict holder",
            status=WorkItemStatus.READY,
            priority=80,
            risk=RiskLevel.MEDIUM,
            work_type=WorkType.IMPLEMENTATION,
            autonomy_mode=AutonomyMode.AI_ASSISTED,
            acceptance="First claim holds lock.",
            validation="Conflict smoke.",
            expected_touch="src/kairota/scheduler/claims.py",
            conflict_keys=(conflict_key,),
        ),
        idempotency_key=f"{idempotency_prefix}:conflict:first",
        actor="smoke",
    )
    second_conflict = create_work_item_command(
        session,
        command=WorkItemCreate(
            title="M1 smoke second conflict holder",
            status=WorkItemStatus.READY,
            priority=81,
            risk=RiskLevel.MEDIUM,
            work_type=WorkType.IMPLEMENTATION,
            autonomy_mode=AutonomyMode.AI_ASSISTED,
            acceptance="Second claim is blocked by active lock.",
            validation="Conflict smoke.",
            expected_touch="src/kairota/scheduler/claims.py",
            conflict_keys=(conflict_key,),
        ),
        idempotency_key=f"{idempotency_prefix}:conflict:second",
        actor="smoke",
    )
    first_claim = claim_work_item_command(
        session,
        work_item_id=first_conflict.id,
        command=ClaimWorkItemCommand(owner="m1-smoke-conflict-a"),
        idempotency_key=f"{idempotency_prefix}:conflict:first-claim",
    )
    second_claim = claim_work_item_command(
        session,
        work_item_id=second_conflict.id,
        command=ClaimWorkItemCommand(owner="m1-smoke-conflict-b"),
        idempotency_key=f"{idempotency_prefix}:conflict:second-claim",
    )
    record_check(
        checks,
        "conflict_lock_blocks_second_claim",
        first_claim.claimed
        and not second_claim.claimed
        and second_claim.reason == SchedulerDecisionCode.BLOCKED_BY_CONFLICT_KEY.value,
        {"conflict_key": conflict_key},
    )

    stale_work_item_id = f"{idempotency_prefix}:stale-lease-work"
    now = datetime.now(UTC)
    ensure_work_item(
        session,
        {
            "id": stale_work_item_id,
            "title": "M1 smoke stale lease",
            "status": WorkItemStatus.CLAIMED,
            "priority": 90,
            "risk": RiskLevel.HIGH,
            "work_type": WorkType.OPERATIONS,
            "autonomy_mode": AutonomyMode.AI_ASSISTED,
            "expected_touch": "src/kairota/scheduler/claims.py",
            "acceptance": "Expired lease is reconciled.",
            "validation": "Lease reconciliation smoke.",
            "conflict_keys": (),
            "dependency_ids": (),
        },
    )
    ensure_conflict_keys(
        session,
        work_item_id=stale_work_item_id,
        conflict_keys=(stale_conflict_key,),
    )
    stale_lease_id = f"{idempotency_prefix}:stale-lease"
    ensure_lease(
        session,
        lease_id=stale_lease_id,
        work_item_id=stale_work_item_id,
        status=LeaseStatus.ACTIVE,
        fencing_token=f"{idempotency_prefix}:stale-token",
        heartbeat_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )
    ensure_lock_holder(
        session,
        lock_id=f"{idempotency_prefix}:stale-lock",
        conflict_key=stale_conflict_key,
        lease_id=stale_lease_id,
    )
    expiry = expire_stale_leases_command(
        session,
        idempotency_key=f"{idempotency_prefix}:stale:reconcile",
    )
    record_check(
        checks,
        "expired_lease_reconciled",
        stale_lease_id in expiry.expired_lease_ids,
        {"expired_lease_ids": expiry.expired_lease_ids},
    )
    return tuple(checks)


def record_check(
    checks: list[SmokeCheckRead],
    name: str,
    passed: bool,
    details: dict[str, object],
) -> None:
    checks.append(
        SmokeCheckRead(
            name=name,
            status="passed" if passed else "failed",
            details=details,
        )
    )
