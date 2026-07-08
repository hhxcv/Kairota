from fastapi.testclient import TestClient

from kairota.api.app import create_app
from kairota.config import Settings


def test_healthz_returns_runtime_identity() -> None:
    app = create_app(Settings(app_name="Kairota Test"))
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Kairota Test",
        "version": "0.1.0",
    }
