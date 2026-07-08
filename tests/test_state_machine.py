from kairota.contracts.enums import WorkItemStatus
from kairota.domain.state_machine import is_work_item_transition_allowed


def test_ready_can_be_claimed_or_blocked() -> None:
    assert is_work_item_transition_allowed(
        WorkItemStatus.READY,
        WorkItemStatus.CLAIMED,
    )
    assert is_work_item_transition_allowed(
        WorkItemStatus.READY,
        WorkItemStatus.BLOCKED,
    )


def test_done_is_terminal_except_idempotent_self_transition() -> None:
    assert is_work_item_transition_allowed(
        WorkItemStatus.DONE,
        WorkItemStatus.DONE,
    )
    assert not is_work_item_transition_allowed(
        WorkItemStatus.DONE,
        WorkItemStatus.READY,
    )


def test_repository_pr_states_can_record_observed_merge() -> None:
    for status in (
        WorkItemStatus.PR_OPEN,
        WorkItemStatus.WAITING_CHECKS,
        WorkItemStatus.STRICT_AI_REVIEW,
        WorkItemStatus.CI_FAILED,
        WorkItemStatus.GATE_FAILED,
    ):
        assert is_work_item_transition_allowed(status, WorkItemStatus.MERGED)
