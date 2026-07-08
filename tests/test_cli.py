import json

from pytest import CaptureFixture

from kairota.cli import main


def test_health_command_outputs_json(capsys: CaptureFixture[str]) -> None:
    exit_code = main(["health"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["service"] == "Kairota"
    assert payload["version"] == "0.1.0"
