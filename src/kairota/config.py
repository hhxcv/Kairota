from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8010


def default_data_dir() -> Path:
    override = os.environ.get("KAIROTA_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "Kairota"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Kairota"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / (
        "kairota"
    )


def default_database_url() -> str:
    return f"sqlite:///{(default_data_dir() / 'kairota.sqlite').as_posix()}"


def default_cors_allow_origins() -> tuple[str, ...]:
    vite_ports = (5173, *range(5180, 5191))
    return tuple(
        f"http://{host}:{port}"
        for host in ("127.0.0.1", "localhost")
        for port in vite_ports
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KAIROTA_",
        extra="ignore",
    )

    app_name: str = "Kairota"
    database_url: str = Field(default_factory=default_database_url, repr=False)
    auto_migrate: bool = True
    github_token: str | None = Field(default=None, repr=False)
    github_api_url: str = "https://api.github.com"
    github_webhook_secret: str | None = Field(default=None, repr=False)
    cors_allow_origins: tuple[str, ...] = Field(
        default_factory=default_cors_allow_origins
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
