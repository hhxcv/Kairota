from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from kairota.adapters.github.models import (
    GitHubIssueSnapshot,
    GitHubProjectConfig,
    GitHubProjectSnapshot,
    GitHubSyncSnapshot,
)
from kairota.api.app import create_app
from kairota.config import Settings


class FakeGitHubClient:
    def __init__(self, project_name: str = "owner/repo") -> None:
        self.project_name = project_name
        self.provider_repo_id = f"provider-{project_name}"
        self.issues: dict[int, GitHubIssueSnapshot] = {}
        self.calls: list[tuple[str, tuple[int, ...]]] = []
        self.error: Exception | None = None

    def set_issue(
        self,
        number: int,
        *,
        state: str = "open",
        title: str | None = None,
        updated_at: str | None = None,
    ) -> None:
        self.issues[number] = GitHubIssueSnapshot(
            number=number,
            provider_issue_id=f"issue-{number}",
            title=title or f"Issue {number}",
            url=f"https://example.test/{self.project_name}/issues/{number}",
            state=state,
            updated_at=updated_at or f"2026-07-10T00:{number % 60:02d}:00Z",
        )

    def fetch_project_snapshot(
        self,
        project: GitHubProjectConfig,
        *,
        issue_numbers: tuple[int, ...] = (),
    ) -> GitHubSyncSnapshot:
        self.calls.append((f"{project.owner}/{project.name}", issue_numbers))
        if self.error is not None:
            raise self.error
        numbers = issue_numbers or tuple(sorted(self.issues))
        return GitHubSyncSnapshot(
            project=GitHubProjectSnapshot(
                provider_repo_id=self.provider_repo_id,
                name=self.project_name,
            ),
            issues=tuple(self.issues[number] for number in numbers),
        )


@pytest.fixture()
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    db_path = tmp_path / "kairota.sqlite"
    db_url = f"sqlite:///{db_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(config, "head")
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
    )
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()


@pytest.fixture()
def github() -> FakeGitHubClient:
    return FakeGitHubClient()


@pytest.fixture()
def api_client(
    session_factory: sessionmaker[Session],
    github: FakeGitHubClient,
) -> Iterator[TestClient]:
    settings = Settings(
        app_name="Kairota Test",
        auto_migrate=False,
        github_webhook_secret="test-secret",
        sync_stale_after_seconds=300,
    )
    app = create_app(
        settings,
        session_factory=session_factory,
        github_client=github,
    )
    with TestClient(app) as client:
        yield client
