from __future__ import annotations

from enum import StrEnum


class IssueSourceState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class SchedulingState(StrEnum):
    NEEDS_ANALYSIS = "needs_analysis"
    BLOCKED = "blocked"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class SyncHealth(StrEnum):
    UNKNOWN = "unknown"
    SYNCING = "syncing"
    HEALTHY = "healthy"
    ERROR = "error"


class EventStatus(StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
