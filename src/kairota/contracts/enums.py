from __future__ import annotations

from enum import StrEnum


class WorkItemStatus(StrEnum):
    NEEDS_TRIAGE = "needs_triage"
    BACKLOG = "backlog"
    READY = "ready"
    CLAIMED = "claimed"
    IMPLEMENTING = "implementing"
    PR_OPEN = "pr_open"
    WAITING_CHECKS = "waiting_checks"
    MERGE_ARMED = "merge_armed"
    MERGED = "merged"
    DONE = "done"
    BLOCKED = "blocked"
    HUMAN_DECISION = "human_decision"
    STRICT_AI_REVIEW = "strict_ai_review"
    CI_FAILED = "ci_failed"
    GATE_FAILED = "gate_failed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkType(StrEnum):
    IMPLEMENTATION = "implementation"
    DOCS = "docs"
    TEST = "test"
    DESIGN = "design"
    GOVERNANCE = "governance"
    OPERATIONS = "operations"


class AutonomyMode(StrEnum):
    HUMAN_REQUIRED = "human_required"
    AI_ASSISTED = "ai_assisted"
    FULLY_AUTONOMOUS = "fully_autonomous"


class SchedulerDecisionCode(StrEnum):
    ASSIGNED = "assigned"
    BLOCKED_BY_DEPENDENCY = "blocked_by_dependency"
    BLOCKED_BY_STATUS = "blocked_by_status"
    BLOCKED_BY_CONFLICT_KEY = "blocked_by_conflict_key"
    BLOCKED_BY_CAPACITY = "blocked_by_capacity"
    BLOCKED_BY_MISSING_EXPECTED_TOUCH = "blocked_by_missing_expected_touch"
    BLOCKED_BY_MISSING_ACCEPTANCE = "blocked_by_missing_acceptance"
    BLOCKED_BY_MISSING_VALIDATION = "blocked_by_missing_validation"
    BLOCKED_BY_REVIEW_GATE = "blocked_by_review_gate"
    BLOCKED_BY_CI = "blocked_by_ci"
    BLOCKED_BY_HUMAN_DECISION = "blocked_by_human_decision"
    BLOCKED_BY_EXPIRED_OR_STALE_SOURCE = "blocked_by_expired_or_stale_source"


class LeaseStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"
    SUPERSEDED = "superseded"


class LockHolderSource(StrEnum):
    LEASE = "lease"
    PULL_REQUEST = "pull_request"
    FALLBACK = "fallback"


class WorkerRole(StrEnum):
    WORKER = "worker"
    REVIEWER = "reviewer"
    SCHEDULER = "scheduler"
    TRIAGER = "triager"
    REPAIR_AGENT = "repair_agent"
    CONSULTANT = "consultant"


class WorkerRunStatus(StrEnum):
    PLANNED = "planned"
    CLAIMED = "claimed"
    RUNNING = "running"
    REPORTING = "reporting"
    CLOSED = "closed"


class WorkerRunResult(StrEnum):
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    ABANDONED = "abandoned"


class RepositoryProvider(StrEnum):
    GITHUB = "github"


class PullRequestState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class CheckStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


class CheckConclusion(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class ReviewGateState(StrEnum):
    UNKNOWN = "unknown"
    WAITING = "waiting"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    UNRESOLVED_THREADS = "unresolved_threads"


class EventStatus(StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
    SKIPPED = "skipped"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
