"""Compose #1469 quota exclusion with the complete native/routing candidate.

All provider state is synthetic cached data. The current-host, original GLM
pairing fixture and native installation holds are not retried or cleared.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sys

import pytest
import yaml

from tests.test_native_fabric_protected_broker_composition import (
    FIXTURES, _apply, _module, broker, complete_broker,
)

EXACT_INPUTS = {
    "glm_quota_admission.patch": "40f269ceb2cf38c4e03f7abb8f811849116e4dd5",
    "quota_remote.py.txt": "3dc8d38ba8259909774e0bb67693c13634daeb6c",
}


@pytest.fixture
def current_candidate(complete_broker, tmp_path, monkeypatch):
    for name, expected in EXACT_INPUTS.items():
        content = (FIXTURES / name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        assert blob == expected
    ext = tmp_path / "ext"
    ext.mkdir()
    target = ext / "lease_broker.py"
    target.write_text(complete_broker._composed_source)
    _apply(tmp_path, FIXTURES / "glm_quota_admission.patch", "--directory=ext")
    # Only the accepted quota intersection in account_cap may differ.
    def method_shapes(source):
        cls = next(n for n in ast.parse(source).body
                   if isinstance(n, ast.ClassDef) and n.name == "Broker")
        return {n.name: ast.dump(n, include_attributes=False)
                for n in cls.body if isinstance(n, ast.FunctionDef)}
    before = method_shapes(complete_broker._composed_source)
    after = method_shapes(target.read_text())
    assert before.keys() == after.keys()
    assert [n for n in before if before[n] != after[n]] == ["account_cap"]
    shutil.copyfile(FIXTURES / "native_broker_admission.py.txt", ext / "native_broker_admission.py")
    shutil.copyfile(FIXTURES / "quota_remote.py.txt", ext / "quota_remote.py")
    names = ("_routing_quota_native_fixture", "_routing_quota_reader_fixture", "_routing_quota_broker_fixture")
    prior = {name: sys.modules.get(name) for name in names}
    def forbidden(*args, **kwargs):
        raise AssertionError("quota composition attempted provider/credential/refresh I/O")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    native = _module(names[0], ext / "native_broker_admission.py")
    monkeypatch.setitem(sys.modules, "native_broker_admission", native)
    reader = _module(names[1], ext / "quota_remote.py")
    monkeypatch.setitem(sys.modules, "quota_remote", reader)
    candidate = _module(names[2], target)
    monkeypatch.setattr(reader, "_glm_accounts_dict", forbidden)
    monkeypatch.setattr(reader, "_live_glm", forbidden)
    monkeypatch.setattr(reader, "_atomic_write", forbidden)
    monkeypatch.setattr(reader, "READERS", {"glm": forbidden, "minimax": forbidden})
    yield candidate, reader
    for name in names:
        if prior[name] is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prior[name]


def quota_state(current_candidate, tmp_path, monkeypatch, observation="fresh"):
    module, reader = current_candidate
    br, clock = broker(module, tmp_path)
    Path(br.accounts_path).write_text(yaml.safe_dump({"providers": {"glm": {
        "enabled": True, "accounts": [
            {"name": "exhausted", "per_account_cap": 12, "per_model_caps": {"glm-5.3": 6}},
            {"name": "ready", "per_account_cap": 12, "per_model_caps": {"glm-5.3": 6}},
        ],
    }}}))
    br.external_gates = True
    now = clock[0]
    def stamp(value):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    measured = now - 1000 if observation == "stale" else now + 1000 if observation == "future" else now
    state = {"provider": "glm", "source": "PROVIDER_AUTHORITATIVE", "window": "weekly",
             "remaining_pct": 2, "observed_at": stamp(measured),
             "reset_at": stamp(now - 1 if observation == "passed_reset" else now + 3600)}
    data = {} if observation == "missing" else {"glm": {"accounts": {"exhausted": {
        "refreshed_at": measured, "states": [state],
    }}}}
    cache = tmp_path / "synthetic-quota.json"
    cache.write_text(json.dumps(data))
    monkeypatch.setattr(reader, "CACHE_PATH", str(cache))
    return br, cache


def test_quota_exclusion_precedes_utilization_and_expiry(current_candidate, tmp_path, monkeypatch):
    br, cache = quota_state(current_candidate, tmp_path, monkeypatch)
    original = cache.read_bytes()
    seen = []
    def urgency(names):
        seen.append(set(names))
        # A favorable ranking must not resurrect an excluded account.
        return {"exhausted": 1.0} if "exhausted" in names else {}
    monkeypatch.setattr(br, "_fresh_glm_expiring_accounts", urgency)
    assert [a["name"] for a in br.grantable_accounts("glm")] == ["ready"]
    with br._conn() as conn:
        assert br._pick_account(conn, "glm", None, model="glm-5.3") == "ready"
        assert br._pick_account(conn, "glm", "exhausted", model="glm-5.3") is None
        assert len(br._active_leases(conn)) == 0
    assert seen and all("exhausted" not in names for names in seen)
    assert cache.read_bytes() == original


@pytest.mark.parametrize("observation", ["missing", "stale", "future", "passed_reset"])
def test_uncertain_quota_does_not_invent_parking(current_candidate, tmp_path, monkeypatch, observation):
    br, cache = quota_state(current_candidate, tmp_path, monkeypatch, observation)
    original = cache.read_bytes()
    # Incumbent unknown-data behavior is preserved; this grants no quota/lease.
    assert {a["name"] for a in br.grantable_accounts("glm")} == {"exhausted", "ready"}
    assert cache.read_bytes() == original
