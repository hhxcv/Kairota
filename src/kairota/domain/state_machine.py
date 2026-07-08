from __future__ import annotations

from kairota.contracts.enums import WorkItemStatus

ALLOWED_WORK_ITEM_TRANSITIONS: dict[WorkItemStatus, frozenset[WorkItemStatus]] = {
    WorkItemStatus.NEEDS_TRIAGE: frozenset(
        {
            WorkItemStatus.BACKLOG,
            WorkItemStatus.READY,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.HUMAN_DECISION,
        }
    ),
    WorkItemStatus.BACKLOG: frozenset(
        {WorkItemStatus.READY, WorkItemStatus.BLOCKED, WorkItemStatus.HUMAN_DECISION}
    ),
    WorkItemStatus.READY: frozenset(
        {WorkItemStatus.CLAIMED, WorkItemStatus.BLOCKED, WorkItemStatus.HUMAN_DECISION}
    ),
    WorkItemStatus.CLAIMED: frozenset(
        {
            WorkItemStatus.IMPLEMENTING,
            WorkItemStatus.READY,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.HUMAN_DECISION,
        }
    ),
    WorkItemStatus.IMPLEMENTING: frozenset(
        {
            WorkItemStatus.PR_OPEN,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.HUMAN_DECISION,
        }
    ),
    WorkItemStatus.PR_OPEN: frozenset(
        {
            WorkItemStatus.WAITING_CHECKS,
            WorkItemStatus.MERGE_ARMED,
            WorkItemStatus.CI_FAILED,
            WorkItemStatus.STRICT_AI_REVIEW,
            WorkItemStatus.GATE_FAILED,
            WorkItemStatus.HUMAN_DECISION,
        }
    ),
    WorkItemStatus.WAITING_CHECKS: frozenset(
        {
            WorkItemStatus.PR_OPEN,
            WorkItemStatus.MERGE_ARMED,
            WorkItemStatus.CI_FAILED,
            WorkItemStatus.STRICT_AI_REVIEW,
            WorkItemStatus.GATE_FAILED,
            WorkItemStatus.HUMAN_DECISION,
        }
    ),
    WorkItemStatus.MERGE_ARMED: frozenset(
        {
            WorkItemStatus.MERGED,
            WorkItemStatus.PR_OPEN,
            WorkItemStatus.CI_FAILED,
            WorkItemStatus.STRICT_AI_REVIEW,
            WorkItemStatus.HUMAN_DECISION,
        }
    ),
    WorkItemStatus.MERGED: frozenset(
        {WorkItemStatus.DONE, WorkItemStatus.HUMAN_DECISION}
    ),
    WorkItemStatus.BLOCKED: frozenset(
        {WorkItemStatus.READY, WorkItemStatus.HUMAN_DECISION, WorkItemStatus.DONE}
    ),
    WorkItemStatus.HUMAN_DECISION: frozenset(
        {
            WorkItemStatus.NEEDS_TRIAGE,
            WorkItemStatus.BACKLOG,
            WorkItemStatus.READY,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.DONE,
        }
    ),
    WorkItemStatus.STRICT_AI_REVIEW: frozenset(
        {
            WorkItemStatus.PR_OPEN,
            WorkItemStatus.WAITING_CHECKS,
            WorkItemStatus.MERGE_ARMED,
            WorkItemStatus.GATE_FAILED,
            WorkItemStatus.HUMAN_DECISION,
        }
    ),
    WorkItemStatus.CI_FAILED: frozenset(
        {
            WorkItemStatus.PR_OPEN,
            WorkItemStatus.WAITING_CHECKS,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.HUMAN_DECISION,
        }
    ),
    WorkItemStatus.GATE_FAILED: frozenset(
        {
            WorkItemStatus.PR_OPEN,
            WorkItemStatus.WAITING_CHECKS,
            WorkItemStatus.STRICT_AI_REVIEW,
            WorkItemStatus.HUMAN_DECISION,
        }
    ),
    WorkItemStatus.DONE: frozenset(),
}


def is_work_item_transition_allowed(
    current: WorkItemStatus,
    target: WorkItemStatus,
) -> bool:
    if current == target:
        return True
    return target in ALLOWED_WORK_ITEM_TRANSITIONS[current]
