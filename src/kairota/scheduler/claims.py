from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from kairota.contracts.enums import (
    LeaseStatus,
    LockHolderSource,
    PullRequestState,
    SchedulerDecisionCode,
    WorkItemStatus,
)
from kairota.domain.state_machine import is_work_item_transition_allowed
from kairota.models.records import (
    AuditEvent,
    Lease,
    LockHolder,
    RepoPullRequest,
    WorkItem,
)
from kairota.scheduler.planner import FALLBACK_CONFLICT_KEY


@dataclass(frozen=True)
class ClaimResult:
    claimed: bool
    work_item_id: str
    lease_id: str | None = None
    fencing_token: str | None = None
    conflict_keys: tuple[str, ...] = ()
    reason: SchedulerDecisionCode | None = None
    explanation: str | None = None


@dataclass(frozen=True)
class LeaseHeartbeatResult:
    refreshed: bool
    lease_id: str
    explanation: str | None = None


@dataclass(frozen=True)
class LeaseExpiryResult:
    expired_lease_ids: tuple[str, ...]
    released_lock_ids: tuple[str, ...]


def claim_work_item(
    session: Session,
    *,
    work_item_id: str,
    owner: str,
    conflict_keys: frozenset[str],
    lease_ttl: timedelta,
    now: datetime | None = None,
) -> ClaimResult:
    observed_at = now or datetime.now(UTC)
    keys = normalized_conflict_keys(conflict_keys)
    work_item = load_work_item_for_update(session, work_item_id)
    if work_item is None:
        return ClaimResult(
            claimed=False,
            work_item_id=work_item_id,
            reason=SchedulerDecisionCode.BLOCKED_BY_STATUS,
            explanation="Work item does not exist.",
        )

    if work_item.status != WorkItemStatus.READY.value:
        return ClaimResult(
            claimed=False,
            work_item_id=work_item_id,
            reason=SchedulerDecisionCode.BLOCKED_BY_STATUS,
            explanation="Work item is not ready.",
        )

    active_lease = session.scalar(
        select(Lease.id).where(
            Lease.work_item_id == work_item_id,
            Lease.status == LeaseStatus.ACTIVE.value,
        )
    )
    if active_lease:
        return ClaimResult(
            claimed=False,
            work_item_id=work_item_id,
            reason=SchedulerDecisionCode.BLOCKED_BY_STATUS,
            explanation="Work item already has an active lease.",
        )

    conflicts = tuple(
        session.scalars(
            select(LockHolder.conflict_key)
            .where(
                LockHolder.released_at.is_(None),
                LockHolder.conflict_key.in_(keys),
            )
            .order_by(LockHolder.conflict_key)
        )
    )
    if conflicts:
        return ClaimResult(
            claimed=False,
            work_item_id=work_item_id,
            conflict_keys=conflicts,
            reason=SchedulerDecisionCode.BLOCKED_BY_CONFLICT_KEY,
            explanation="Conflict keys are already locked.",
        )

    if not is_work_item_transition_allowed(
        WorkItemStatus(work_item.status),
        WorkItemStatus.CLAIMED,
    ):
        return ClaimResult(
            claimed=False,
            work_item_id=work_item_id,
            reason=SchedulerDecisionCode.BLOCKED_BY_STATUS,
            explanation="Work item transition to claimed is not allowed.",
        )

    lease = Lease(
        work_item_id=work_item_id,
        owner=owner,
        status=LeaseStatus.ACTIVE.value,
        fencing_token=str(uuid4()),
        heartbeat_at=observed_at,
        expires_at=observed_at + lease_ttl,
    )
    session.add(lease)
    session.flush()

    locks = [
        LockHolder(
            conflict_key=key,
            source=LockHolderSource.LEASE.value,
            lease_id=lease.id,
        )
        for key in keys
    ]
    session.add_all(locks)
    work_item.status = WorkItemStatus.CLAIMED.value
    session.add(
        AuditEvent(
            actor=owner,
            action="claim_work_item",
            subject_type="work_item",
            subject_id=work_item_id,
            summary="Work item claimed with active lease.",
            details={"lease_id": lease.id, "conflict_keys": list(keys)},
        )
    )
    session.flush()

    return ClaimResult(
        claimed=True,
        work_item_id=work_item_id,
        lease_id=lease.id,
        fencing_token=lease.fencing_token,
        conflict_keys=keys,
    )


def heartbeat_lease(
    session: Session,
    *,
    lease_id: str,
    fencing_token: str,
    lease_ttl: timedelta,
    now: datetime | None = None,
) -> LeaseHeartbeatResult:
    observed_at = now or datetime.now(UTC)
    lease = load_lease_for_update(session, lease_id)
    if lease is None:
        return LeaseHeartbeatResult(False, lease_id, "Lease does not exist.")

    if lease.status != LeaseStatus.ACTIVE.value:
        return LeaseHeartbeatResult(False, lease_id, "Lease is not active.")

    if lease.fencing_token != fencing_token:
        return LeaseHeartbeatResult(False, lease_id, "Fencing token does not match.")

    lease.heartbeat_at = observed_at
    lease.expires_at = observed_at + lease_ttl
    session.flush()
    return LeaseHeartbeatResult(True, lease_id)


def expire_stale_leases(
    session: Session,
    *,
    now: datetime | None = None,
) -> LeaseExpiryResult:
    observed_at = now or datetime.now(UTC)
    stale_leases = tuple(
        session.scalars(
            select(Lease)
            .where(
                Lease.status == LeaseStatus.ACTIVE.value,
                Lease.expires_at <= observed_at,
            )
            .with_for_update()
            .order_by(Lease.id)
        )
    )

    expired_ids: list[str] = []
    released_lock_ids: list[str] = []
    for lease in stale_leases:
        lease.status = LeaseStatus.EXPIRED.value
        expired_ids.append(lease.id)

        locks = tuple(
            session.scalars(
                select(LockHolder)
                .where(
                    LockHolder.lease_id == lease.id,
                    LockHolder.released_at.is_(None),
                )
                .with_for_update()
                .order_by(LockHolder.id)
            )
        )
        for lock in locks:
            lock.released_at = observed_at
            released_lock_ids.append(lock.id)

        work_item = load_work_item_for_update(session, lease.work_item_id)
        if work_item is not None:
            recovery_status = recovery_status_for_expired_lease(session, work_item.id)
            work_item.status = recovery_status.value

        session.add(
            AuditEvent(
                actor="scheduler",
                action="expire_lease",
                subject_type="lease",
                subject_id=lease.id,
                summary="Expired stale lease and released lease-held locks.",
                details={"work_item_id": lease.work_item_id},
            )
        )

    session.flush()
    return LeaseExpiryResult(tuple(expired_ids), tuple(released_lock_ids))


def recovery_status_for_expired_lease(
    session: Session,
    work_item_id: str,
) -> WorkItemStatus:
    open_pr_exists = session.scalar(
        select(RepoPullRequest.id)
        .where(
            RepoPullRequest.work_item_id == work_item_id,
            RepoPullRequest.state.in_(
                [PullRequestState.OPEN.value, PullRequestState.MERGED.value]
            ),
        )
        .limit(1)
    )
    if open_pr_exists:
        return WorkItemStatus.HUMAN_DECISION
    return WorkItemStatus.READY


def load_work_item_for_update(session: Session, work_item_id: str) -> WorkItem | None:
    return session.scalar(
        select(WorkItem).where(WorkItem.id == work_item_id).with_for_update()
    )


def load_lease_for_update(session: Session, lease_id: str) -> Lease | None:
    return session.scalar(select(Lease).where(Lease.id == lease_id).with_for_update())


def normalized_conflict_keys(conflict_keys: frozenset[str]) -> tuple[str, ...]:
    if conflict_keys:
        return tuple(sorted(conflict_keys))
    return (FALLBACK_CONFLICT_KEY,)
