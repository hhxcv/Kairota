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
    priority: int = Field(default=100, ge=0)
    risk: RiskLevel = RiskLevel.MEDIUM
    work_type: WorkType = WorkType.IMPLEMENTATION
    autonomy_mode: AutonomyMode = AutonomyMode.AI_ASSISTED
    acceptance: str | None = None
    validation: str | None = None
    expected_touch: str | None = None
    source_url: str | None = None


class WorkItemRead(WorkItemCreate):
    id: str
    status: WorkItemStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SchedulerDecisionRead(ContractModel):
    id: str
    cycle_id: str
    work_item_id: str
    code: SchedulerDecisionCode
    explanation: str | None = None
    blocking_facts: JsonObject = Field(default_factory=dict)


class LeaseRead(ContractModel):
    id: str
    work_item_id: str
    owner: str
    status: LeaseStatus
    fencing_token: str
    expires_at: datetime


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
    role: WorkerRole
    status: WorkerRunStatus
    result: WorkerRunResult | None = None
    validation: JsonObject = Field(default_factory=dict)


class RepositoryRead(ContractModel):
    id: str
    provider: RepositoryProvider
    provider_repo_id: str
    name: str
    default_branch: str
    sync_status: str


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
