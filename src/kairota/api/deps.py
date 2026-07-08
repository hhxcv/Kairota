from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker


def get_session(request: Request) -> Iterator[Session]:
    raw_session_factory = request.app.state.session_factory
    if raw_session_factory is None:
        raise HTTPException(
            status_code=503,
            detail="Database access is not configured.",
        )
    session_factory = cast(sessionmaker[Session], raw_session_factory)
    with session_factory() as session:
        yield session
