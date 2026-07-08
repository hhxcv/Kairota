from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from kairota.contracts.enums import (
    AutonomyMode,
    CheckConclusion,
    CheckStatus,
    EventStatus,
    LeaseStatus,
    LockHolderSource,
    OutboxStatus,
    PullRequestState,
    RepositoryProvider,
    ReviewGateState,
    RiskLevel,
    SchedulerDecisionCode,
    WorkerRole,
    WorkerRunResult,
    WorkerRunStatus,
    WorkItemStatus,
    WorkType,
)

JsonObject = dict[str, Any]


class ContractModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class WorkItemCreate(ContractModel):
    title: str = Field(min_length=1, max_length=240)
    status: WorkItemStatus = WorkItemStatus.NEEDS_TRIAGE
    priority: int = Field(default=100, ge=0)
    risk: RiskLevel = RiskLevel.MEDIUM
    work_type: WorkType = WorkType.IMPLEMENTATION
    autonomy_mode: AutonomyMode = AutonomyMode.AI_ASSISTED
    acceptance: str | None = None
    validation: str | None = None
    expected_touch: str | None = None
    source_url: str | None = None
    conflict_keys: tuple[str, ...] = Field(default_factory=tuple)
    dependency_ids: tuple[str, ...] = Field(default_factory=tuple)


class WorkItemRead(WorkItemCreate):
    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QueueSummaryRead(ContractModel):
    total: int
    by_status: dict[str, int] = Field(default_factory=dict)
    active_leases: int
    active_locks: int


class QueueWorkbenchRunRead(ContractModel):
    id: str
    lease_id: str | None = None
    role: WorkerRole
    status: WorkerRunStatus
    result: WorkerRunResult | None = None
    heartbeat_at: datetime | None = None
    closed_at: datetime | None = None


class QueueWorkbenchRowRead(ContractModel):
    id: str
    title: str
    section: str
    status: WorkItemStatus
    priority: int
    risk: RiskLevel
    work_type: WorkType
    autonomy_mode: AutonomyMode
    expected_touch: str | None = None
    acceptance: str | None = None
    validation: str | None = None
    source_url: str | None = None
    conflict_keys: tuple[str, ...] = Field(default_factory=tuple)
    dependency_ids: tuple[str, ...] = Field(default_factory=tuple)
    reason_code: str
    next_action: str
    worker_run: QueueWorkbenchRunRead | None = None
    repository: JsonObject = Field(default_factory=dict)


class QueueWorkbenchSectionRead(ContractModel):
    id: str
    title: str
    count: int
    rows: tuple[QueueWorkbenchRowRead, ...] = Field(default_factory=tuple)


class QueueWorkbenchEventRead(ContractModel):
    id: str
    kind: str
    summary: str
    subject_type: str | None = None
    subject_id: str | None = None
    status: str | None = None
    created_at: datetime | None = None
    details: JsonObject = Field(default_factory=dict)


class QueueWorkbenchRead(ContractModel):
    summary: QueueSummaryRead
    sections: tuple[QueueWorkbenchSectionRead, ...]
    decision_inbox: tuple[QueueWorkbenchRowRead, ...] = Field(default_factory=tuple)
    recent_events: tuple[QueueWorkbenchEventRead, ...] = Field(default_factory=tuple)
    failures: tuple[QueueWorkbenchEventRead, ...] = Field(default_factory=tuple)


class SchedulerDecisionRead(ContractModel):
    id: str
    cycle_id: str
    work_item_id: str
    code: SchedulerDecisionCode
    explanation: str | None = None
    blocking_facts: JsonObject = Field(default_factory=dict)


class SchedulerCycleCreate(ContractModel):
    queue_key: str = Field(default="default", min_length=1, max_length=160)
    capacity: int = Field(default=1, ge=0, le=100)


class SchedulerCycleRead(ContractModel):
    id: str
    queue_key: str
    result: str
    assigned_count: int
    rejected_count: int
    decisions: tuple[SchedulerDecisionRead, ...] = Field(default_factory=tuple)


class LeaseRead(ContractModel):
    id: str
    work_item_id: str
    owner: str
    status: LeaseStatus
    fencing_token: str
    expires_at: datetime


class ClaimWorkItemCommand(ContractModel):
    owner: str = Field(min_length=1, max_length=160)
    lease_ttl_seconds: int = Field(default=1800, gt=0, le=86_400)


class ClaimWorkItemRead(ContractModel):
    claimed: bool
    work_item_id: str
    lease_id: str | None = None
    fencing_token: str | None = None
    conflict_keys: tuple[str, ...] = Field(default_factory=tuple)
    reason: SchedulerDecisionCode | None = None
    explanation: str | None = None


class LeaseHeartbeatCommand(ContractModel):
    fencing_token: str = Field(min_length=1, max_length=120)
    lease_ttl_seconds: int = Field(default=1800, gt=0, le=86_400)


class LeaseHeartbeatRead(ContractModel):
    refreshed: bool
    lease_id: str
    explanation: str | None = None


class LeaseExpiryRead(ContractModel):
    expired_lease_ids: tuple[str, ...] = Field(default_factory=tuple)
    released_lock_ids: tuple[str, ...] = Field(default_factory=tuple)


class BlockedCommandResponse(ContractModel):
    status: str = "blocked"
    reason_code: str
    explanation: str
    details: JsonObject = Field(default_factory=dict)


class LockHolderRead(ContractModel):
    id: str
    conflict_key: str
    source: LockHolderSource
    lease_id: str | None = None
    pull_request_id: str | None = None
    released_at: datetime | None = None


class WorkerRunRead(ContractModel):
    id: str
    work_item_id: str
    lease_id: str | None = None
    role: WorkerRole
    status: WorkerRunStatus
    result: WorkerRunResult | None = None
    validation: JsonObject = Field(default_factory=dict)
    public_mutations: JsonObject = Field(default_factory=dict)
    cost_summary: JsonObject = Field(default_factory=dict)
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    closed_at: datetime | None = None


class WorkerRunCreateCommand(ContractModel):
    work_item_id: str
    lease_id: str
    fencing_token: str = Field(min_length=1, max_length=120)
    role: WorkerRole = WorkerRole.WORKER


class WorkerRunHeartbeatCommand(ContractModel):
    fencing_token: str = Field(min_length=1, max_length=120)


class WorkerRunReportCommand(ContractModel):
    fencing_token: str = Field(min_length=1, max_length=120)
    validation: JsonObject = Field(default_factory=dict)
    public_mutations: JsonObject = Field(default_factory=dict)
    cost_summary: JsonObject = Field(default_factory=dict)


class WorkerRunCloseCommand(WorkerRunReportCommand):
    result: WorkerRunResult


class RepositoryRead(ContractModel):
    id: str
    provider: RepositoryProvider
    provider_repo_id: str
    name: str
    default_branch: str
    sync_status: str


class RepositorySyncRead(ContractModel):
    repository_id: str
    provider: RepositoryProvider
    status: str
    replayed: bool = False
    issues_seen: int = 0
    pull_requests_seen: int = 0
    checks_seen: int = 0
    reviews_seen: int = 0
    work_items_created: int = 0
    transitions_applied: int = 0
    stale_summaries_marked: int = 0
    inbound_event_id: str | None = None


class PullRequestSummaryRead(ContractModel):
    id: str
    repository_id: str
    provider_pr_id: str
    number: int
    state: PullRequestState
    draft: bool
    head_sha: str | None = None
    merged: bool


class CheckSummaryRead(ContractModel):
    id: str
    pull_request_id: str
    name: str
    status: CheckStatus
    conclusion: CheckConclusion
    head_sha: str | None = None
    required: bool
    stale: bool


class ReviewSummaryRead(ContractModel):
    id: str
    pull_request_id: str
    state: ReviewGateState
    unresolved_count: int
    stale: bool


class InboundEventRead(ContractModel):
    id: str
    provider: RepositoryProvider
    idempotency_key: str
    event_type: str
    action: str | None = None
    payload_hash: str
    status: EventStatus


class OutboxEventRead(ContractModel):
    id: str
    idempotency_key: str
    target: str
    action: str
    payload: JsonObject = Field(default_factory=dict)
    status: OutboxStatus
    retry_count: int
