import json
from pathlib import Path

import pytest

from kairota.cli import main
from kairota.config import get_settings


def configure_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("KAIROTA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("KAIROTA_DATABASE_URL", raising=False)
    get_settings.cache_clear()


def test_health_initializes_internal_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_data_dir(monkeypatch, tmp_path)
    assert main(["health"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert (tmp_path / "kairota.sqlite").exists()


def test_project_register_and_list_use_internal_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_data_dir(monkeypatch, tmp_path)
    assert main(["projects", "register", "https://github.com/owner/repo.git"]) == 0
    registered = json.loads(capsys.readouterr().out)
    assert registered["name"] == "owner/repo"

    assert main(["projects", "list"]) == 0
    projects = json.loads(capsys.readouterr().out)
    assert [project["name"] for project in projects] == ["owner/repo"]


def test_serve_uses_fixed_defaults_and_uvicorn_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("kairota.cli.ensure_database_ready", lambda: None)
    monkeypatch.setattr(
        "kairota.cli.uvicorn.run",
        lambda app, **kwargs: calls.append({"app": app, **kwargs}),
    )

    assert main(["serve"]) == 0
    assert calls == [
        {
            "app": "kairota.api.app:create_app",
            "host": "127.0.0.1",
            "port": 8010,
            "reload": False,
            "factory": True,
        }
    ]
