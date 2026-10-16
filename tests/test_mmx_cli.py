from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mmx.py"


def _module():
    spec = importlib.util.spec_from_file_location("mmx_cli_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_command_mapping_is_closed_and_local(tmp_path: Path):
    module = _module()
    parser = module._parser()

    args = parser.parse_args(["executive", "state"])
    assert args.socket == module.DEFAULT_CONTROL_SOCKET
    assert module._request(args) == ("status", {})

    args = parser.parse_args(["executive", "job", "JOB-123"])
    assert module._request(args) == ("job", {"job_id": "JOB-123"})

    args = parser.parse_args(["executive", "intent", "CEO-123"])
    assert module._request(args) == ("ceo-intent-status", {"intent_id": "CEO-123"})

    intent_path = tmp_path / "intent.json"
    intent = {"schema": "mastermind.ceo_intent.v1", "operation_key": "test-op"}
    intent_path.write_text(json.dumps(intent), encoding="utf-8")
    args = parser.parse_args(["executive", "submit", str(intent_path)])
    assert module._request(args) == ("submit-ceo-intent", {"intent": intent})

    with pytest.raises(SystemExit):
        parser.parse_args(["executive", "--socket", "relative.sock", "state"])
    with pytest.raises(SystemExit):
        parser.parse_args(["executive", "remote", "https://example.invalid"])


def test_state_uses_existing_control_transport(monkeypatch, capsys):
    module = _module()
    seen = {}

    async def fake_transport(socket_path, command, values):
        seen.update(socket=socket_path, command=command, values=values)
        return {"ok": True, "result": {"status": "READY"}}

    monkeypatch.setattr(module, "send_control_request", fake_transport)
    code = module.main(["executive", "--socket", "/tmp/executive.sock", "state"])
    assert code == 0
    assert seen == {
        "socket": Path("/tmp/executive.sock"),
        "command": "status",
        "values": {},
    }
    assert json.loads(capsys.readouterr().out) == {"status": "READY"}


def test_submit_preserves_admission_not_execution_semantics(monkeypatch, tmp_path: Path, capsys):
    module = _module()
    intent = {
        "schema": "mastermind.ceo_intent.v1",
        "operation_key": "mmx-shell-test-001",
        "objective": "bounded test",
    }
    path = tmp_path / "intent.json"
    path.write_text(json.dumps(intent), encoding="utf-8")
    seen = {}

    async def fake_transport(socket_path, command, values):
        seen.update(command=command, values=values)
        return {
            "ok": True,
            "result": {
                "intent_id": "CEO-1",
                "job_id": "JOB-1",
                "status": "QUEUED",
                "accepted": True,
                "dispatched": False,
            },
        }

    monkeypatch.setattr(module, "send_control_request", fake_transport)
    code = module.main(["executive", "--socket", "/tmp/executive.sock", "submit", str(path)])
    assert code == 0
    assert seen == {"command": "submit-ceo-intent", "values": {"intent": intent}}
    out = capsys.readouterr().out
    assert "JOB-1  [QUEUED]" in out
    assert "dispatched  False  (submission is not execution)" in out


def test_refusal_is_nonzero_and_not_rendered_as_success(monkeypatch, capsys):
    module = _module()

    async def fake_transport(socket_path, command, values):
        return {"ok": False, "error": {"code": "NOT_READY", "message": "closed"}}

    monkeypatch.setattr(module, "send_control_request", fake_transport)
    code = module.main(["executive", "--socket", "/tmp/executive.sock", "jobs"])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "refused: [NOT_READY] closed" in captured.err


def test_json_mode_returns_full_service_envelope(monkeypatch, capsys):
    module = _module()
    response = {"ok": True, "result": {"status": "READY"}, "request_id": "x"}

    async def fake_transport(socket_path, command, values):
        return response

    monkeypatch.setattr(module, "send_control_request", fake_transport)
    code = module.main([
        "executive", "--socket", "/tmp/executive.sock", "--json", "state"
    ])
    assert code == 0
    assert json.loads(capsys.readouterr().out) == response
