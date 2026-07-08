from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from kairota.config import Settings, get_settings


def database_url(settings: Settings | None = None) -> str:
    app_settings = settings or get_settings()
    if not app_settings.database_url:
        raise RuntimeError("KAIROTA_DATABASE_URL is required for database access")
    return app_settings.database_url


def create_sync_engine(settings: Settings | None = None) -> Engine:
    return create_engine(database_url(settings), pool_pre_ping=True)


def create_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=create_sync_engine(settings), expire_on_commit=False)
