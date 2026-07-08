from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from kairota import __version__
from kairota.adapters.github.models import GitHubClient
from kairota.api.routes import router
from kairota.config import Settings, get_settings
from kairota.db import create_session_factory


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    github_client: GitHubClient | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name, version=__version__)
    app.state.settings = app_settings
    app.state.github_client = github_client
    app.state.session_factory = (
        session_factory
        if session_factory is not None
        else create_session_factory(app_settings)
        if app_settings.database_url
        else None
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


app = create_app()
