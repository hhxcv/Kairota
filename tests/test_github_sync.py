from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from kairota.adapters.github.models import (
    GitHubCheckSnapshot,
    GitHubClient,
    GitHubIssueSnapshot,
    GitHubPullRequestSnapshot,
    GitHubRepositoryConfig,
    GitHubRepositorySnapshot,
    GitHubReviewSnapshot,
    GitHubSyncOptions,
    GitHubSyncSnapshot,
)
from kairota.contracts.enums import (
    CheckConclusion,
    CheckStatus,
    PullRequestState,
    RepositoryIssueState,
    RepositoryProvider,
    RepositorySyncMode,
    ReviewGateState,
    WorkItemStatus,
)
from kairota.contracts.schemas import RepositorySyncCommand
from kairota.models.records import (
    ExternalRef,
    RepoCheckSummary,
    RepoPullRequest,
    RepoReviewSummary,
    Repository,
    SyncCursor,
    WorkItem,
)
from kairota.services.github_sync import issue_external_id, sync_repository_command


class FakeGitHubClient:
    def __init__(self, *snapshots: GitHubSyncSnapshot) -> None:
        self.snapshots = list(snapshots)
        self.calls: list[GitHubRepositoryConfig] = []
        self.options: list[GitHubSyncOptions | None] = []

    def fetch_repository_snapshot(
        self,
        repository: GitHubRepositoryConfig,
        cursor: str | None = None,
        options: GitHubSyncOptions | None = None,
    ) -> GitHubSyncSnapshot:
        del cursor
        self.calls.append(repository)
        self.options.append(options)
        if len(self.calls) <= len(self.snapshots):
            return self.snapshots[len(self.calls) - 1]
        return self.snapshots[-1]


@pytest.fixture()
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_path = tmp_path / "kairota.sqlite"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(config, "head")

    db_engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        yield db_engine
    finally:
        db_engine.dispose()


def repository_snapshot(provider_repo_id: str = "repo-1") -> GitHubRepositorySnapshot:
    return GitHubRepositorySnapshot(
        provider_repo_id=provider_repo_id,
        name="owner/repo",
        default_branch="main",
    )


def issue(number: int = 7, state: str = "open") -> GitHubIssueSnapshot:
    return GitHubIssueSnapshot(
        number=number,
        provider_issue_id=f"issue-{number}",
        title=f"Issue {number}",
        url=f"https://example.test/issues/{number}",
        state=state,
    )


def pull_request(
    *,
    state: PullRequestState = PullRequestState.OPEN,
    head_sha: str = "sha-1",
    merged: bool = False,
) -> GitHubPullRequestSnapshot:
    return GitHubPullRequestSnapshot(
        number=3,
        provider_pr_id="pr-3",
        url="https://example.test/pull/3",
        state=PullRequestState.MERGED if merged else state,
        draft=False,
        head_branch="feature",
        head_sha=head_sha,
        merged=merged,
        merge_commit_sha="merge-sha" if merged else None,
        linked_issue_numbers=(7,),
    )


def check(
    *,
    conclusion: CheckConclusion = CheckConclusion.SUCCESS,
    status: CheckStatus = CheckStatus.COMPLETED,
    head_sha: str = "sha-1",
) -> GitHubCheckSnapshot:
    return GitHubCheckSnapshot(
        pull_request_number=3,
        name="ci",
        status=status,
        conclusion=conclusion,
        head_sha=head_sha,
        required=True,
    )


def review(
    *,
    state: ReviewGateState = ReviewGateState.APPROVED,
    unresolved_count: int = 0,
    head_sha: str = "sha-1",
) -> GitHubReviewSnapshot:
    return GitHubReviewSnapshot(
        pull_request_number=3,
        state=state,
        unresolved_count=unresolved_count,
        head_sha=head_sha,
        summary={"review_count": 1, "thread_count": unresolved_count},
    )


def sync_snapshot(
    *,
    provider_repo_id: str = "repo-1",
    issues: tuple[GitHubIssueSnapshot, ...] = (),
    prs: tuple[GitHubPullRequestSnapshot, ...] = (),
    checks: tuple[GitHubCheckSnapshot, ...] = (),
    reviews: tuple[GitHubReviewSnapshot, ...] = (),
) -> GitHubSyncSnapshot:
    return GitHubSyncSnapshot(
        repository=repository_snapshot(provider_repo_id),
        issues=issues,
        pull_requests=prs,
        checks=checks,
        reviews=reviews,
    )


def create_repository(session: Session, provider_repo_id: str = "repo-1") -> Repository:
    repository = Repository(
        provider=RepositoryProvider.GITHUB.value,
        provider_repo_id=provider_repo_id,
        name="owner/repo",
        default_branch="main",
        sync_status="unknown",
    )
    session.add(repository)
    session.flush()
    return repository


def link_issue_work_item(
    session: Session,
    repository: Repository,
    *,
    status: WorkItemStatus,
) -> WorkItem:
    work_item = WorkItem(
        title="Linked work",
        repository_id=repository.id,
        status=status.value,
        priority=10,
        risk="medium",
        work_type="implementation",
        autonomy_mode="ai_assisted",
    )
    session.add(work_item)
    session.flush()
    session.add(
        ExternalRef(
            provider=RepositoryProvider.GITHUB.value,
            external_type="issue",
            external_id=issue_external_id(repository.id, 7),
            url="https://example.test/issues/7",
            work_item_id=work_item.id,
            repository_id=repository.id,
        )
    )
    session.flush()
    return work_item


def status_for(session: Session, work_item_id: str) -> str:
    return str(
        session.scalar(select(WorkItem.status).where(WorkItem.id == work_item_id))
    )


def test_poll_sync_creates_issue_work_item_and_replays_idempotently(
    engine: Engine,
) -> None:
    snapshot = sync_snapshot(issues=(issue(),))
    client: GitHubClient = FakeGitHubClient(snapshot)

    with Session(engine) as session, session.begin():
        repository = create_repository(session)
        first = sync_repository_command(
            session,
            repository_id=repository.id,
            idempotency_key="sync-1",
            client=client,
        )
        second = sync_repository_command(
            session,
            repository_id=repository.id,
            idempotency_key="sync-1",
            client=client,
        )

        assert first.work_items_created == 1
        assert not first.replayed
        assert second.replayed
        assert session.scalar(select(SyncCursor.id)) is not None
        assert (
            session.scalar(select(WorkItem.status)) == WorkItemStatus.NEEDS_TRIAGE.value
        )
        assert session.scalar(select(WorkItem.repository_id)) == repository.id


def test_poll_sync_passes_bounded_issue_options_to_adapter(engine: Engine) -> None:
    snapshot = sync_snapshot(issues=(issue(),))
    fake_client = FakeGitHubClient(snapshot)

    with Session(engine) as session, session.begin():
        repository = create_repository(session)
        result = sync_repository_command(
            session,
            repository_id=repository.id,
            idempotency_key="sync-issue-options",
            client=fake_client,
            command=RepositorySyncCommand(
                mode=RepositorySyncMode.ISSUES,
                issue_state=RepositoryIssueState.OPEN,
                labels=("kairota",),
                issue_numbers=(7,),
                max_pages=1,
            ),
        )

        assert result.issues_seen == 1
        options = fake_client.options[0]
        assert options is not None
        assert options.mode == RepositorySyncMode.ISSUES
        assert options.issue_state == RepositoryIssueState.OPEN
        assert options.labels == ("kairota",)
        assert options.issue_numbers == (7,)
        assert options.max_pages == 1


def test_issue_close_marks_work_item_done(engine: Engine) -> None:
    snapshot = sync_snapshot(issues=(issue(state="closed"),))
    client: GitHubClient = FakeGitHubClient(snapshot)

    with Session(engine) as session, session.begin():
        repository = create_repository(session)
        result = sync_repository_command(
            session,
            repository_id=repository.id,
            idempotency_key="sync-closed-issue",
            client=client,
        )

        assert result.transitions_applied == 1
        assert session.scalar(select(WorkItem.status)) == WorkItemStatus.DONE.value


def test_open_issue_sync_refreshes_tracked_active_issue_state(engine: Engine) -> None:
    fake_client = FakeGitHubClient(
        sync_snapshot(issues=()),
        sync_snapshot(issues=(issue(state="closed"),)),
    )

    with Session(engine) as session, session.begin():
        repository = create_repository(session)
        work_item = link_issue_work_item(
            session,
            repository,
            status=WorkItemStatus.READY,
        )
        result = sync_repository_command(
            session,
            repository_id=repository.id,
            idempotency_key="sync-open-refresh-tracked",
            client=fake_client,
            command=RepositorySyncCommand(
                mode=RepositorySyncMode.ISSUES,
                issue_state=RepositoryIssueState.OPEN,
                max_pages=1,
            ),
        )

        assert result.issues_seen == 1
        assert result.transitions_applied == 1
        assert status_for(session, work_item.id) == WorkItemStatus.DONE.value
        assert len(fake_client.options) == 2
        assert fake_client.options[0] is not None
        assert fake_client.options[0].issue_state == RepositoryIssueState.OPEN
        assert fake_client.options[1] is not None
        assert fake_client.options[1].issue_state == RepositoryIssueState.ALL
        assert fake_client.options[1].issue_numbers == (7,)


def test_pull_request_open_and_successful_gates_move_to_merge_armed(
    engine: Engine,
) -> None:
    client: GitHubClient = FakeGitHubClient(
        sync_snapshot(prs=(pull_request(),), checks=(check(),), reviews=(review(),))
    )

    with Session(engine) as session, session.begin():
        repository = create_repository(session)
        work_item = link_issue_work_item(
            session,
            repository,
            status=WorkItemStatus.IMPLEMENTING,
        )
        result = sync_repository_command(
            session,
            repository_id=repository.id,
            idempotency_key="sync-pr-open",
            client=client,
        )

        assert result.transitions_applied == 2
        assert status_for(session, work_item.id) == WorkItemStatus.MERGE_ARMED.value
        assert session.scalar(select(RepoPullRequest.head_sha)) == "sha-1"


def test_failed_check_moves_pr_work_to_ci_failed(engine: Engine) -> None:
    client: GitHubClient = FakeGitHubClient(
        sync_snapshot(
            prs=(pull_request(),),
            checks=(check(conclusion=CheckConclusion.FAILURE),),
            reviews=(review(),),
        )
    )

    with Session(engine) as session, session.begin():
        repository = create_repository(session)
        work_item = link_issue_work_item(
            session,
            repository,
            status=WorkItemStatus.PR_OPEN,
        )
        sync_repository_command(
            session,
            repository_id=repository.id,
            idempotency_key="sync-failed-check",
            client=client,
        )

        assert status_for(session, work_item.id) == WorkItemStatus.CI_FAILED.value


def test_requested_changes_and_unresolved_threads_require_strict_ai_review(
    engine: Engine,
) -> None:
    for index, gate_state in enumerate(
        (
            ReviewGateState.CHANGES_REQUESTED,
            ReviewGateState.UNRESOLVED_THREADS,
        )
    ):
        with Session(engine) as session, session.begin():
            repository = create_repository(session, f"repo-review-{index}")
            work_item = link_issue_work_item(
                session,
                repository,
                status=WorkItemStatus.PR_OPEN,
            )
            client: GitHubClient = FakeGitHubClient(
                sync_snapshot(
                    provider_repo_id=f"repo-review-{index}",
                    prs=(pull_request(),),
                    checks=(check(),),
                    reviews=(
                        review(
                            state=gate_state,
                            unresolved_count=1
                            if gate_state == ReviewGateState.UNRESOLVED_THREADS
                            else 0,
                        ),
                    ),
                )
            )

            sync_repository_command(
                session,
                repository_id=repository.id,
                idempotency_key=f"sync-review-{gate_state.value}",
                client=client,
            )

            assert (
                status_for(session, work_item.id)
                == WorkItemStatus.STRICT_AI_REVIEW.value
            )


def test_pull_request_merged_and_closed_unmerged_reducers(engine: Engine) -> None:
    scenarios = (
        (pull_request(merged=True), WorkItemStatus.MERGED),
        (pull_request(state=PullRequestState.CLOSED), WorkItemStatus.HUMAN_DECISION),
    )
    for index, (pr_snapshot, expected_status) in enumerate(scenarios):
        with Session(engine) as session, session.begin():
            repository = create_repository(session, f"repo-terminal-{index}")
            work_item = link_issue_work_item(
                session,
                repository,
                status=WorkItemStatus.PR_OPEN,
            )
            client: GitHubClient = FakeGitHubClient(
                sync_snapshot(
                    provider_repo_id=f"repo-terminal-{index}",
                    prs=(pr_snapshot,),
                )
            )

            sync_repository_command(
                session,
                repository_id=repository.id,
                idempotency_key=f"sync-pr-terminal-{index}",
                client=client,
            )

            assert status_for(session, work_item.id) == expected_status.value


def test_head_sha_change_marks_old_summaries_stale_and_unarms_merge(
    engine: Engine,
) -> None:
    first = sync_snapshot(
        prs=(pull_request(head_sha="sha-1"),),
        checks=(check(head_sha="sha-1"),),
        reviews=(review(head_sha="sha-1"),),
    )
    second = sync_snapshot(prs=(pull_request(head_sha="sha-2"),))
    client: GitHubClient = FakeGitHubClient(first, second)

    with Session(engine) as session, session.begin():
        repository = create_repository(session)
        work_item = link_issue_work_item(
            session,
            repository,
            status=WorkItemStatus.PR_OPEN,
        )
        sync_repository_command(
            session,
            repository_id=repository.id,
            idempotency_key="sync-head-1",
            client=client,
        )
        result = sync_repository_command(
            session,
            repository_id=repository.id,
            idempotency_key="sync-head-2",
            client=client,
        )

        assert status_for(session, work_item.id) == WorkItemStatus.PR_OPEN.value
        assert result.stale_summaries_marked == 2
        assert session.scalar(select(RepoCheckSummary.stale)) is True
        assert session.scalar(select(RepoReviewSummary.stale)) is True
