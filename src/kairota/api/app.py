from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from kairota import __version__
from kairota.config import Settings, get_settings


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name, version=__version__)

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=app_settings.app_name,
            version=__version__,
        )

    return app


app = create_app()
