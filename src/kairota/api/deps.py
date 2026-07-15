from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from kairota.adapters.github.client import ensure_github_client
from kairota.adapters.github.models import GitHubClient
from kairota.config import Settings


def get_session(request: Request) -> Iterator[Session]:
    raw_session_factory = request.app.state.session_factory
    if raw_session_factory is None:
        raise HTTPException(
            status_code=503,
            detail="Database access is not configured.",
        )
    session_factory = cast(sessionmaker[Session], raw_session_factory)
    with session_factory() as session:
        session.info["request"] = request
        yield session


def get_github_client(request: Request) -> GitHubClient:
    settings = cast(Settings, request.app.state.settings)
    raw_client = getattr(request.app.state, "github_client", None)
    return ensure_github_client(cast(GitHubClient | None, raw_client), settings)
