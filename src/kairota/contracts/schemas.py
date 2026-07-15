from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from kairota.contracts.enums import (
    IssueSourceState,
    SchedulingState,
    SyncHealth,
)

JsonObject = dict[str, Any]


class ContractModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_utc_datetimes(self, value: Any) -> Any:
        if not isinstance(value, datetime):
            return value
        aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ProjectCreate(ContractModel):
    remote: str = Field(min_length=1, max_length=500)


class ProjectUpdate(ContractModel):
    enabled: bool


class ProjectSyncStateRead(ContractModel):
    health: SyncHealth
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None


class ProjectRead(ContractModel):
    id: str
    provider_repo_id: str
    name: str
    enabled: bool
    sync: ProjectSyncStateRead
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DependencyRead(ContractModel):
    issue_id: str
    number: int
    title: str
    source_state: IssueSourceState
    url: str


class ManagedIssueRead(ContractModel):
    id: str
    project_id: str
    number: int
    title: str
    url: str
    source_state: IssueSourceState
    scheduling_state: SchedulingState
    scheduling_version: int
    analysis_version: int
    analysis_completed: bool
    manual_hold_reason: str | None = None
    in_progress_since: datetime | None = None
    source_updated_at: str | None = None
    last_synced_at: datetime | None = None
    dependencies: tuple[DependencyRead, ...] = Field(default_factory=tuple)
    dependency_closed_count: int = 0
    blocking_reasons: tuple[str, ...] = Field(default_factory=tuple)
    claimable_now: bool = False
    claim_block_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IssuePageRead(ContractModel):
    items: tuple[ManagedIssueRead, ...]
    total: int
    page: int
    page_size: int
    by_state: dict[str, int] = Field(default_factory=dict)


class IssueAnalysisCommand(ContractModel):
    expected_analysis_version: int = Field(ge=0)
    dependency_issue_numbers: tuple[int, ...] = Field(default_factory=tuple)
    manual_hold_reason: str | None = Field(default=None, max_length=500)


class IssueClaimCommand(ContractModel):
    expected_scheduling_version: int = Field(ge=0)


class IssueReleaseCommand(ContractModel):
    expected_scheduling_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)


class ProjectSyncRead(ContractModel):
    project_id: str
    status: SyncHealth
    issues_seen: int = 0
    issues_created: int = 0
    issues_updated: int = 0
    transitions_applied: int = 0
    replayed: bool = False
    inbound_event_id: str | None = None
    error: str | None = None


class BlockedCommandResponse(ContractModel):
    status: str = "blocked"
    reason_code: str
    explanation: str
    details: JsonObject = Field(default_factory=dict)
