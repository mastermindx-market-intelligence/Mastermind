"""One-shot, non-daemon observer-owned export entrypoint; no privileged edits."""
from __future__ import annotations

import json
from control_plane import fleet_health_handoff as handoff
from test_fleet_health_handoff import NOW, roots


def test_one_shot_cli_exports_only_sanitized_report(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(handoff.time, "time", lambda: NOW)
    assert callable(getattr(handoff, "main", None)), "one-shot exporter CLI missing"
    observer, shared = roots(tmp_path)
    code = handoff.main([
        "--once", "--observer-root", str(observer),
        "--handoff-root", str(shared),
    ])
    assert code == 0
    stdout = capsys.readouterr().out
    receipt = json.loads(stdout)
    assert receipt["published"] is True
    assert receipt["admission_authoritative"] is False
    assert str(observer) not in stdout
    assert (shared / handoff.HANDOFF_FILE).exists()


def test_one_shot_cli_refuses_missing_explicit_switch(tmp_path, capsys):
    observer, shared = roots(tmp_path)
    code = handoff.main([
        "--observer-root", str(observer),
        "--handoff-root", str(shared),
    ])
    assert code != 0
    assert not (shared / handoff.HANDOFF_FILE).exists()


def test_one_shot_cli_refuses_broken_private_source_without_echo(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(handoff.time, "time", lambda: NOW)
    observer, shared = roots(tmp_path)
    (observer / "hosts.json").unlink()
    code = handoff.main([
        "--once", "--observer-root", str(observer),
        "--handoff-root", str(shared),
    ])
    captured = capsys.readouterr()
    assert code != 0
    assert captured.out == ""
    assert str(observer) not in captured.err
    assert "unavailable" in captured.err.lower()
    assert not (shared / handoff.HANDOFF_FILE).exists()
