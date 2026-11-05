"""Hermetic checks for the exact existing M1 Chris Admin Paper-only selector."""
import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


SOURCE = Path(__file__).with_name("private_service.py")
SPEC = importlib.util.spec_from_file_location("paper_m1_under_test", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ORIGINAL_LIFECYCLE_MUTEX = MODULE._c2_lifecycle_mutex


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


@pytest.fixture
def enrolled(tmp_path, monkeypatch):
    """All source/identity data is synthetic; no live config is loaded or modified."""
    home = tmp_path / "home"
    base = home / ".local/share/studio-direct-mcp/private/chrisadmin"
    base.mkdir(parents=True, mode=0o700)
    state = base / "state"
    state.mkdir(mode=0o700)
    (home / ".local/share/mastermind-paper/runtime/v5").mkdir(parents=True)
    (home / ".local/share/mastermind-paper/runtime/v20").mkdir(parents=True)
    label = "com.mastermind.studio-direct-private.chrisadmin"
    old = {
        "enabled": True,
        "pythonPath": str(home / MODULE.M1_PAPER_V5_RUNTIME_REL / "venv/bin/python"),
        "bridgePath": str(home / MODULE.M1_PAPER_V5_RUNTIME_REL / "source/bridge.py"),
        "bridgeSha256": MODULE.M1_PAPER_V5_BRIDGE_SHA256,
        "appPath": str(home / MODULE.PAPER_APP_REL),
        "commandTimeoutMs": MODULE.PAPER_COMMAND_TIMEOUT_MS,
    }
    nonpaper = {"accountLabel": "chrisadmin", "port": 45018, "host": "127.0.0.1",
                "childEnv": {"NODE_OPTIONS": ""}}
    config = {**nonpaper, "paperDesign": old}
    config_path = base / "config.json"
    manifest_path = base / "manifest.json"
    plist_path = base / "service.plist"
    config_path.write_bytes(json.dumps(config, indent=2).encode())
    plist_path.write_bytes(b"synthetic plist identity")
    initial = {"account": "chrisadmin", "label": label, "configHash": digest(config_path.read_bytes()),
               "plistHash": digest(plist_path.read_bytes()),
               "files": {"private-tunnel-gateway.mjs": "a" * 64}, "version": 2}
    manifest_path.write_bytes(json.dumps(initial, indent=2).encode())
    for f in (config_path, plist_path, manifest_path):
        f.chmod(0o600)
    roots = {"base": base, "state": state, "config": config_path, "manifest": manifest_path, "plist": plist_path}
    monkeypatch.setattr(MODULE, "M1_PAPER_V5_MANIFEST_SHA256", digest(manifest_path.read_bytes()))
    monkeypatch.setattr(MODULE, "M1_PAPER_V5_CONFIG_SHA256", digest(config_path.read_bytes()))
    monkeypatch.setattr(MODULE, "M1_PAPER_V5_PLIST_SHA256", digest(plist_path.read_bytes()))
    monkeypatch.setattr(MODULE, "M1_PAPER_V5_NONPAPER_SHA256", digest(json.dumps(nonpaper,
                           sort_keys=True, separators=(",", ":")).encode()))
    monkeypatch.setattr(MODULE, "_user_root", lambda: home)
    monkeypatch.setattr(MODULE, "_build_runtime_roots", lambda account: roots)
    monkeypatch.setattr(MODULE, "_assert_dest_safe", lambda path: None)
    monkeypatch.setattr(MODULE, "_valid_manifest", lambda *a: True)
    monkeypatch.setattr(MODULE, "_verify_paper_runtime", lambda *args, **kwargs: {"state": "RUNTIME_VERIFIED"})
    monkeypatch.setattr(MODULE, "_lifecycle_inspect", lambda *args, **kwargs: None)
    monkeypatch.setattr(MODULE, "_c2_lifecycle_mutex", lambda account: contextlib.nullcontext())

    def verify_install(account, given_label, given_roots, require_runtime_seal=True):
        current = json.loads(manifest_path.read_bytes())
        if (current["account"] != account or current["label"] != given_label
                or current["configHash"] != digest(config_path.read_bytes())
                or current["plistHash"] != digest(plist_path.read_bytes())):
            raise RuntimeError("synthetic install integrity mismatch")
        return current

    monkeypatch.setattr(MODULE, "_verify_staged_install", verify_install)
    args = lambda preview=False: SimpleNamespace(account="chrisadmin", m1_v20=True,
        preflight_only=preview, expected_manifest_sha256=MODULE.M1_PAPER_V5_MANIFEST_SHA256)
    return args, config_path, manifest_path, plist_path, initial


def test_preview_is_exactly_effect_none(enrolled, capsys):
    args, c, m, p, _ = enrolled
    before = (c.read_bytes(), m.read_bytes(), p.read_bytes())
    assert MODULE.cmd_paper_runtime_upgrade(args(True)) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["preflight"] is True
    assert response["effect"] == "NOT_APPLIED"
    assert (response["fromGeneration"], response["toGeneration"]) == ("v5", "v20")
    assert response["serviceStarted"] is False
    assert before == (c.read_bytes(), m.read_bytes(), p.read_bytes())


def test_apply_changes_only_paper_config_and_manifest_hash(enrolled, capsys):
    args, c, m, p, before_manifest = enrolled
    original = json.loads(c.read_bytes())
    original_plist = p.read_bytes()
    assert MODULE.cmd_paper_runtime_upgrade(args()) == 0
    out = json.loads(capsys.readouterr().out)
    new = json.loads(c.read_bytes())
    new_manifest = json.loads(m.read_bytes())
    assert out["effect"] == "INSTALLED_NOT_STARTED"
    assert new["paperDesign"]["bridgeSha256"] == MODULE.M1_PAPER_V20_BRIDGE_SHA256
    assert "/runtime/v20/" in new["paperDesign"]["bridgePath"]
    assert {k:v for k,v in new.items() if k!="paperDesign"} == {k:v for k,v in original.items() if k!="paperDesign"}
    assert {k:v for k,v in new_manifest.items() if k!="configHash"} == {k:v for k,v in before_manifest.items() if k!="configHash"}
    assert new_manifest["configHash"] == digest(c.read_bytes())
    assert p.read_bytes() == original_plist


def test_wrong_predecessor_refuses_without_effect(enrolled):
    args, c, m, p, _ = enrolled
    before=(c.read_bytes(),m.read_bytes(),p.read_bytes())
    bad = args()
    bad.expected_manifest_sha256 = "0" * 64
    with pytest.raises(SystemExit, match="predecessor manifest CAS mismatch"):
        MODULE.cmd_paper_runtime_upgrade(bad)
    assert before == (c.read_bytes(),m.read_bytes(),p.read_bytes())


def test_live_service_refuses_before_config_change(enrolled, monkeypatch):
    args,c,m,p,_=enrolled
    before=(c.read_bytes(),m.read_bytes(),p.read_bytes())
    monkeypatch.setattr(MODULE, "_lifecycle_inspect", lambda *a, **kw: {"state":"running","pid":123})
    with pytest.raises(SystemExit, match="service is loaded"):
        MODULE.cmd_paper_runtime_upgrade(args())
    assert before==(c.read_bytes(),m.read_bytes(),p.read_bytes())


def test_precommit_failure_rolls_back_exact_bytes(enrolled,monkeypatch):
    args,c,m,p,_=enrolled
    before=(c.read_bytes(),m.read_bytes(),p.read_bytes())
    original=MODULE._atomic_write_bytes
    calls=0
    def fail_after_first(path,data,*a,**kw):
        nonlocal calls
        calls+=1
        original(path,data,*a,**kw)
        if calls==1:raise OSError("synthetic fsync error before manifest commit")
    monkeypatch.setattr(MODULE, "_atomic_write_bytes", fail_after_first)
    with pytest.raises(OSError,match="synthetic"):
        MODULE.cmd_paper_runtime_upgrade(args())
    assert before==(c.read_bytes(),m.read_bytes(),p.read_bytes())


def test_post_manifest_commit_failure_does_not_blindly_replay(enrolled,monkeypatch):
    args,c,m,p,_=enrolled
    original=MODULE._verify_staged_install
    called=0
    def fail_verify(*a,**kw):
        nonlocal called
        called+=1
        if called>=3:raise RuntimeError("simulated post-commit fault")
        return original(*a,**kw)
    monkeypatch.setattr(MODULE, "_verify_staged_install", fail_verify)
    with pytest.raises(SystemExit,match="EFFECT_UNKNOWN"):
        MODULE.cmd_paper_runtime_upgrade(args())
    updated=json.loads(c.read_bytes())
    manifest=json.loads(m.read_bytes())
    assert updated["paperDesign"]["bridgeSha256"]==MODULE.M1_PAPER_V20_BRIDGE_SHA256
    assert manifest["configHash"]==digest(c.read_bytes())


def test_original_chrisadmin_mutex_admits_actual_apply_not_a_mock(enrolled, monkeypatch, capsys):
    """Regression: dry run previously passed, but live M1 apply was refused by account gate."""
    args, config_path, manifest_path, plist_path, _ = enrolled
    monkeypatch.setattr(MODULE, "_c2_lifecycle_mutex", ORIGINAL_LIFECYCLE_MUTEX)
    assert MODULE.cmd_paper_runtime_upgrade(args()) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["effect"] == "INSTALLED_NOT_STARTED"
    assert json.loads(config_path.read_bytes())["paperDesign"]["bridgeSha256"] == MODULE.M1_PAPER_V20_BRIDGE_SHA256
    assert json.loads(manifest_path.read_bytes())["configHash"] == digest(config_path.read_bytes())
    lock = config_path.parent / "state" / MODULE.C2_LIFECYCLE_LOCK_NAME
    assert lock.is_file() and (lock.stat().st_mode & 0o777) == 0o600
    assert lock.stat().st_size == 0
    assert plist_path.read_bytes() == b"synthetic plist identity"
    with pytest.raises(SystemExit, match="cannot select another account"):
        with ORIGINAL_LIFECYCLE_MUTEX("not-an-enrolled-account"):
            pass
