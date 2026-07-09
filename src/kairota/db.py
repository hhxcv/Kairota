from __future__ import annotations

from pathlib import Path
from threading import Lock

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from kairota.config import Settings, get_settings

ROOT = Path(__file__).resolve().parents[2]
_ready_database_urls: set[str] = set()
_ready_lock = Lock()


def database_url(settings: Settings | None = None) -> str:
    app_settings = settings or get_settings()
    return app_settings.database_url


def ensure_database_parent(settings: Settings | None = None) -> None:
    url = make_url(database_url(settings))
    if not url.drivername.startswith("sqlite"):
        return
    if not url.database or url.database == ":memory:":
        return
    Path(url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def ensure_database_ready(settings: Settings | None = None) -> None:
    app_settings = settings or get_settings()
    url = database_url(app_settings)
    with _ready_lock:
        if url in _ready_database_urls:
            return
        ensure_database_parent(app_settings)
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "head")
        _ready_database_urls.add(url)


def create_sync_engine(settings: Settings | None = None) -> Engine:
    ensure_database_parent(settings)
    return create_engine(database_url(settings), pool_pre_ping=True)


def create_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=create_sync_engine(settings), expire_on_commit=False)
