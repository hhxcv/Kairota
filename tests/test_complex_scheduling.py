from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from kairota.contracts.schemas import (
    IssueAnalysisCommand,
    IssueClaimCommand,
    ProjectCreate,
)
from kairota.models.records import ManagedIssue
from kairota.services.github_sync import sync_project
from kairota.services.issues import (
    analyze_issue_command,
    claim_issue_command,
    get_issue_read,
    list_issues,
)
from kairota.services.projects import register_project_command

DEPENDENCIES: dict[int, tuple[int, ...]] = {
    1: (),
    2: (),
    3: (),
    4: (),
    5: (1,),
    6: (1, 2),
    7: (2,),
    8: (2, 3),
    9: (3,),
    10: (3, 4),
    11: (4,),
    12: (1, 4),
    13: (5, 6),
    14: (6, 7),
    15: (7, 8),
    16: (8, 9),
    17: (9, 10),
    18: (10, 11),
    19: (11, 12),
    20: (5, 12),
    21: (13, 14, 15),
    22: (16, 17),
    23: (18, 19, 20),
    24: (21, 22, 23),
}


def test_main_ai_can_drive_twenty_four_issue_graph_with_external_worker_cap(
    session_factory: sessionmaker[Session], github: Any
) -> None:
    for number in DEPENDENCIES:
        github.set_issue(number)
    with session_factory.begin() as session:
        project = register_project_command(
            session,
            command=ProjectCreate(remote="owner/repo"),
            idempotency_key="register-complex",
        )
        sync_project(session, project_id=project.id, client=github)
        issue_ids = {
            issue.number: issue.id
            for issue in session.scalars(select(ManagedIssue))
        }
        for number, dependencies in DEPENDENCIES.items():
            issue = get_issue_read(session, issue_ids[number])
            assert issue is not None
            analyze_issue_command(
                session,
                issue_id=issue.id,
                command=IssueAnalysisCommand(
                    expected_analysis_version=issue.analysis_version,
                    dependency_issue_numbers=dependencies,
                ),
                idempotency_key=f"analyze-{number}",
            )

    dispatched: set[int] = set()
    batches: list[tuple[int, ...]] = []
    while len(dispatched) < len(DEPENDENCIES):
        with session_factory.begin() as session:
            page = list_issues(
                session,
                project_ids=(project.id,),
                page_size=100,
            )
            in_progress = [
                issue for issue in page.items if issue.scheduling_state == "in_progress"
            ]
            assert in_progress == []
            ready = [
                issue
                for issue in page.items
                if issue.scheduling_state == "ready"
                and issue.number not in dispatched
            ]
            batch = tuple(issue.number for issue in ready[:4])
            assert batch, "The dependency graph stopped making progress."
            for issue in ready[:4]:
                claimed = claim_issue_command(
                    session,
                    issue_id=issue.id,
                    command=IssueClaimCommand(
                        expected_scheduling_version=issue.scheduling_version
                    ),
                    idempotency_key=f"claim-{issue.number}",
                )
                assert claimed.scheduling_state == "in_progress"
            batches.append(batch)

        for number in batch:
            github.set_issue(number, state="closed")
            dispatched.add(number)
        with session_factory.begin() as session:
            sync_project(
                session,
                project_id=project.id,
                client=github,
                issue_numbers=batch,
            )

    with session_factory() as session:
        final = list_issues(
            session,
            project_ids=(project.id,),
            page_size=100,
        )
    assert final.total == 24
    assert final.by_state["closed"] == 24
    assert all(issue.scheduling_state == "closed" for issue in final.items)
    assert max(map(len, batches)) == 4
    assert len(dispatched) == 24
