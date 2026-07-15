from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from kairota import __version__
from kairota.adapters.github.client import ensure_github_client
from kairota.adapters.github.models import GitHubClient
from kairota.api.routes import router
from kairota.config import Settings, get_settings
from kairota.db import create_session_factory, ensure_database_ready
from kairota.services.github_sync import sync_enabled_projects

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    github_client: GitHubClient | None = None,
    *,
    start_background_sync: bool | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    injected_session_factory = session_factory is not None
    if session_factory is None and app_settings.auto_migrate:
        ensure_database_ready(app_settings)
    resolved_session_factory = session_factory or create_session_factory(app_settings)
    background_enabled = (
        not injected_session_factory
        if start_background_sync is None
        else start_background_sync
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task: asyncio.Task[None] | None = None
        if background_enabled:
            task = asyncio.create_task(background_sync_loop(app))
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.github_client = github_client
    app.state.session_factory = resolved_session_factory
    if app_settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(app_settings.cors_allow_origins),
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=app_settings.app_name,
            version=__version__,
        )

    app.include_router(router)
    return app


async def background_sync_loop(app: FastAPI) -> None:
    settings: Settings = app.state.settings
    client = ensure_github_client(app.state.github_client, settings)
    while True:
        try:
            await asyncio.to_thread(
                sync_enabled_projects,
                app.state.session_factory,
                client,
            )
        except Exception:
            # Individual sync failures are persisted; this guard keeps the loop alive
            # if setup or database access itself fails.
            logger.exception("Background GitHub synchronization failed.")
        await asyncio.sleep(settings.sync_interval_seconds)
