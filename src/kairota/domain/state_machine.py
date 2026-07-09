from __future__ import annotations

from kairota.contracts.enums import WorkItemStatus

ALLOWED_WORK_ITEM_TRANSITIONS: dict[WorkItemStatus, frozenset[WorkItemStatus]] = {
    WorkItemStatus.NEEDS_TRIAGE: frozenset(
        {
            WorkItemStatus.BACKLOG,
            WorkItemStatus.READY,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.HUMAN_DECISION,
            WorkItemStatus.DONE,
        }
    ),
    WorkItemStatus.BACKLOG: frozenset(
        {
            WorkItemStatus.READY,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.HUMAN_DECISION,
            WorkItemStatus.DONE,
        }
    ),
    WorkItemStatus.READY: frozenset(
        {
            WorkItemStatus.CLAIMED,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.HUMAN_DECISION,
            WorkItemStatus.DONE,
        }
    ),
    WorkItemStatus.CLAIMED: frozenset(
        {
            WorkItemStatus.IMPLEMENTING,
            WorkItemStatus.READY,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.HUMAN_DECISION,
            WorkItemStatus.DONE,
        }
    ),
    WorkItemStatus.IMPLEMENTING: frozenset(
        {
            WorkItemStatus.PR_OPEN,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.HUMAN_DECISION,
            WorkItemStatus.DONE,
        }
    ),
    WorkItemStatus.PR_OPEN: frozenset(
        {
            WorkItemStatus.WAITING_CHECKS,
            WorkItemStatus.MERGE_ARMED,
            WorkItemStatus.MERGED,
            WorkItemStatus.CI_FAILED,
            WorkItemStatus.STRICT_AI_REVIEW,
            WorkItemStatus.GATE_FAILED,
            WorkItemStatus.HUMAN_DECISION,
            WorkItemStatus.DONE,
        }
    ),
    WorkItemStatus.WAITING_CHECKS: frozenset(
        {
            WorkItemStatus.PR_OPEN,
            WorkItemStatus.MERGE_ARMED,
            WorkItemStatus.MERGED,
            WorkItemStatus.CI_FAILED,
            WorkItemStatus.STRICT_AI_REVIEW,
            WorkItemStatus.GATE_FAILED,
            WorkItemStatus.HUMAN_DECISION,
            WorkItemStatus.DONE,
        }
    ),
    WorkItemStatus.MERGE_ARMED: frozenset(
        {
            WorkItemStatus.MERGED,
            WorkItemStatus.PR_OPEN,
            WorkItemStatus.CI_FAILED,
            WorkItemStatus.STRICT_AI_REVIEW,
            WorkItemStatus.HUMAN_DECISION,
            WorkItemStatus.DONE,
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
            WorkItemStatus.MERGED,
            WorkItemStatus.GATE_FAILED,
            WorkItemStatus.HUMAN_DECISION,
            WorkItemStatus.DONE,
        }
    ),
    WorkItemStatus.CI_FAILED: frozenset(
        {
            WorkItemStatus.PR_OPEN,
            WorkItemStatus.WAITING_CHECKS,
            WorkItemStatus.MERGED,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.HUMAN_DECISION,
            WorkItemStatus.DONE,
        }
    ),
    WorkItemStatus.GATE_FAILED: frozenset(
        {
            WorkItemStatus.PR_OPEN,
            WorkItemStatus.WAITING_CHECKS,
            WorkItemStatus.STRICT_AI_REVIEW,
            WorkItemStatus.MERGED,
            WorkItemStatus.HUMAN_DECISION,
            WorkItemStatus.DONE,
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
