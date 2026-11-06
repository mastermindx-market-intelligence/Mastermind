"""Hermetic fleet selector apply tests: actual lifecycle mutex, source-only fixtures."""
import hashlib
import importlib.util
import json
import subprocess
import sys
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).with_name("private_service.py")
SPEC = importlib.util.spec_from_file_location("paper_fleet_selector_under_test", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def digest(b):
    return hashlib.sha256(b).hexdigest()


def as_bytes(x):
    return json.dumps(x, indent=2, sort_keys=True).encode()


ALL_SEATS = (
    "admin-business", "chatgpt1", "chatgpt2-business", "chatgpt3",
    "chatgpt3-w570f6f34", "chatgpt3-wa2a9e6f9", "chatgpt4",
    "mastermind-os-publication",
)


@pytest.fixture(params=ALL_SEATS)
def seat(request, tmp_path, monkeypatch):
    account = request.param
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    base = home / ".local/share/studio-direct-mcp/private" / account
    base.mkdir(parents=True)
    state = base / "state"
    state.mkdir(mode=0o700)
    config_path = base / "config.json"
    manifest_path = base / "manifest.json"
    plist_path = base / "service.plist"
    name = "com.mastermind.studio-direct-private." + account
    module = MODULE._frozen_paper_fleet_module()
    generation = "v12" if account in ("chatgpt4", "mastermind-os-publication") else "v10"
    runtime = home / ".local/share/mastermind-paper/runtime" / generation
    nonpaper = {"accountLabel": account, "host": "127.0.0.1", "port": 42142}
    config = {
        **nonpaper,
        "paperDesign": {
            "enabled": True,
            "pythonPath": str(runtime / "venv/bin/python"),
            "bridgePath": str(runtime / "source/bridge.py"),
            "bridgeSha256": module.PREDECESSORS[generation],
            "appPath": str(home / "Applications/Paper.app"),
            "commandTimeoutMs": 70000,
        },
    }
    config_path.write_bytes(as_bytes(config))
    plist_path.write_bytes(b"sealed original launchd plist for fixture")
    manifest = {
        "version": 2,
        "account": account,
        "label": name,
        "files": {"private-tunnel-gateway.mjs": "a" * 64},
        "configHash": digest(config_path.read_bytes()),
        "plistHash": digest(plist_path.read_bytes()),
    }
    manifest_path.write_bytes(as_bytes(manifest))
    for file in (config_path, manifest_path, plist_path):
        file.chmod(0o600)
    pin = {
        "generation": generation,
        "bridge_sha256": module.PREDECESSORS[generation],
        "config_sha256": digest(config_path.read_bytes()),
        "manifest_sha256": digest(manifest_path.read_bytes()),
        "plist_sha256": digest(plist_path.read_bytes()),
        "nonpaper_sha256": module._canonical_hash(nonpaper),
        "file_count": len(manifest["files"]),
    }
    monkeypatch.setattr(module, "COHORTS", {**module.COHORTS, account: pin})
    monkeypatch.setattr(MODULE, "_frozen_paper_fleet_module", lambda: module)
    monkeypatch.setattr(MODULE, "_user_root", lambda: home)
    roots = {
        "base": base, "state": state, "config": config_path,
        "manifest": manifest_path, "plist": plist_path,
    }
    monkeypatch.setattr(MODULE, "_build_runtime_roots", lambda a: roots)
    monkeypatch.setattr(MODULE, "_assert_dest_safe", lambda p: None)
    monkeypatch.setattr(MODULE, "_valid_manifest", lambda *args: True)
    monkeypatch.setattr(MODULE, "_verify_paper_runtime", lambda *a, **kw: {"state": "RUNTIME_VERIFIED"})
    monkeypatch.setattr(MODULE, "_lifecycle_inspect", lambda *a, **kw: None)

    def verify_install(candidate, label, given, require_runtime_seal=True):
        data = json.loads(manifest_path.read_bytes())
        if (candidate != account or label != name or given != roots
                or data["configHash"] != digest(config_path.read_bytes())
                or data["plistHash"] != digest(plist_path.read_bytes())
                or data["files"] != manifest["files"]):
            raise RuntimeError("synthetic sealed installation changed")
        return data

    monkeypatch.setattr(MODULE, "_verify_staged_install", verify_install)
    make_args = lambda preview=False: SimpleNamespace(
        account=account, preflight_only=preview, m1_v20=False, fleet_v20=True,
        expected_manifest_sha256=pin["manifest_sha256"])
    return (make_args, config_path, manifest_path, plist_path, state, manifest,
            nonpaper, pin)


def test_exact_source_cohort_registration_is_immutable():
    module = MODULE._frozen_paper_fleet_module()
    assert set(module.COHORTS) == set(ALL_SEATS)
    assert module.PREDECESSORS["v10"] == MODULE.PAPER_V10_BRIDGE_SHA256
    assert module.PREDECESSORS["v12"] == MODULE.PAPER_BRIDGE_SHA256
    assert module.TARGET_BRIDGE_SHA256 == MODULE.PAPER_V20_BRIDGE_SHA256
    assert set(ALL_SEATS) - MODULE.NATIVE_POOL_PIN_ACCOUNTS == {"mastermind-os-publication"}


def test_read_only_preflight_all_eight_preserves_original_bytes(seat, capsys):
    args, config, manifest, plist, state, _, _, pin = seat
    before = (config.read_bytes(), manifest.read_bytes(), plist.read_bytes())
    assert MODULE.cmd_paper_runtime_upgrade(args(True)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["effect"] == "NOT_APPLIED"
    assert out["preflight"] is True
    assert out["originalManifestSha256"] == pin["manifest_sha256"]
    assert (config.read_bytes(), manifest.read_bytes(), plist.read_bytes()) == before
    assert not (state / MODULE.C2_LIFECYCLE_LOCK_NAME).exists()


def test_apply_all_eight_uses_real_lock_and_preserves_non_paper(seat, capsys):
    args, config, manifest, plist, state, predecessor, nonpaper, pin = seat
    original_plist = plist.read_bytes()
    assert MODULE.cmd_paper_runtime_upgrade(args()) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["effect"] == "APPLIED"
    assert result["fromGeneration"] == pin["generation"]
    assert result["toGeneration"] == "v20"
    updated = json.loads(config.read_bytes())
    assert updated["paperDesign"]["bridgeSha256"] == MODULE.PAPER_V20_BRIDGE_SHA256
    assert "/runtime/v20/" in updated["paperDesign"]["bridgePath"]
    assert {k: v for k, v in updated.items() if k != "paperDesign"} == nonpaper
    newer = json.loads(manifest.read_bytes())
    assert {k: v for k, v in newer.items() if k != "configHash"} == {
        k: v for k, v in predecessor.items() if k != "configHash"}
    assert newer["configHash"] == digest(config.read_bytes())
    assert plist.read_bytes() == original_plist
    lock = state / MODULE.C2_LIFECYCLE_LOCK_NAME
    assert lock.is_file() and stat.S_IMODE(lock.stat().st_mode) == 0o600
    assert lock.stat().st_size == 0
    with pytest.raises(SystemExit, match="CAS mismatch"):
        MODULE.cmd_paper_runtime_upgrade(args())


def test_new_workspace_successor_full_dispatch_readonly_and_apply(seat, monkeypatch, capsys):
    """Exercise the real v20 command; a pure cohort planner test misses dispatcher gates."""
    make_args, config, manifest_path, plist, state, manifest, nonpaper, pin = seat
    account = make_args().account
    successors = {"admin-business", "chatgpt3-w570f6f34", "chatgpt3-wa2a9e6f9"}
    if account not in successors:
        pytest.skip("not a newer twelve-file successor")

    # The base fixture represents the sealed original predecessor. Advance its
    # manifest only, preserving config, plist and all original identity fields,
    # exactly as the separate Git/Workspace publisher did in production.
    manifest["files"].update({
        f"workspace-fixture-{i:02d}.mjs": "a" * 64 for i in range(11)
    })
    assert len(manifest["files"]) == 12
    manifest_path.write_bytes(as_bytes(manifest))
    newer_pin = {**pin, "manifest_sha256": digest(manifest_path.read_bytes()),
                 "file_count": len(manifest["files"])}
    module = MODULE._frozen_paper_fleet_module()
    monkeypatch.setattr(module, "WORKSPACE_12FILE_SUCCESSORS",
                        {**module.WORKSPACE_12FILE_SUCCESSORS, account: newer_pin})

    # Valid source+header+live fixture: PREVIEW has no effect, not even a lock file.
    preview = make_args(True)
    preview.expected_manifest_sha256 = newer_pin["manifest_sha256"]
    original = (config.read_bytes(), manifest_path.read_bytes(), plist.read_bytes())
    assert MODULE.cmd_paper_runtime_upgrade(preview) == 0
    readback = json.loads(capsys.readouterr().out)
    assert readback["effect"] == "NOT_APPLIED"
    assert readback["originalManifestSha256"] == newer_pin["manifest_sha256"]
    assert readback["preservedGatewayFiles"] == 12
    assert original == (config.read_bytes(), manifest_path.read_bytes(), plist.read_bytes())
    assert not (state / MODULE.C2_LIFECYCLE_LOCK_NAME).exists()

    # Same original transaction, now on an exact newer predecessor.
    apply = make_args()
    apply.expected_manifest_sha256 = newer_pin["manifest_sha256"]
    assert MODULE.cmd_paper_runtime_upgrade(apply) == 0
    accepted = json.loads(capsys.readouterr().out)
    assert accepted["effect"] == "APPLIED"
    assert accepted["preservedGatewayFiles"] == 12
    assert accepted["fromGeneration"] == "v10"
    assert accepted["toGeneration"] == "v20"
    installed = json.loads(config.read_bytes())
    assert {k: v for k, v in installed.items() if k != "paperDesign"} == nonpaper
    assert "/runtime/v20/" in installed["paperDesign"]["bridgePath"]
    assert json.loads(manifest_path.read_bytes())["files"] == manifest["files"]
    assert plist.read_bytes() == original[2]
    with pytest.raises(SystemExit, match="CAS mismatch"):
        MODULE.cmd_paper_runtime_upgrade(apply)


def test_unknown_seat_real_mutex_refuses_without_widening():
    with pytest.raises(SystemExit, match="cannot select another account"):
        with MODULE._c2_lifecycle_mutex("unreviewed-paper-seat"):
            pass


def test_live_service_refuses_without_config_change(seat, monkeypatch):
    args, config, manifest, plist, _, _, _, _ = seat
    before = (config.read_bytes(), manifest.read_bytes(), plist.read_bytes())
    monkeypatch.setattr(MODULE, "_lifecycle_inspect", lambda *a, **k: {"state":"running","pid":123})
    with pytest.raises(SystemExit, match="service is loaded"):
        MODULE.cmd_paper_runtime_upgrade(args())
    assert before == (config.read_bytes(), manifest.read_bytes(), plist.read_bytes())


def test_wrong_manifest_pin_refuses_without_writes(seat):
    args, config, manifest, plist, _, _, _, _ = seat
    before = (config.read_bytes(), manifest.read_bytes(), plist.read_bytes())
    arg = args();arg.expected_manifest_sha256 = "0" * 64
    with pytest.raises(SystemExit, match="frozen predecessor"):
        MODULE.cmd_paper_runtime_upgrade(arg)
    assert before == (config.read_bytes(), manifest.read_bytes(), plist.read_bytes())


def test_post_commit_fault_is_effect_unknown_not_replayed(seat, monkeypatch):
    args, config, manifest, _, _, _, _, _ = seat
    original = MODULE._verify_staged_install
    calls = 0
    def fail_after_manifest(*a, **kw):
        nonlocal calls
        calls += 1
        if calls >= 3:
            raise RuntimeError("injected post-commit verification fault")
        return original(*a, **kw)
    monkeypatch.setattr(MODULE, "_verify_staged_install", fail_after_manifest)
    with pytest.raises(SystemExit, match="EFFECT_UNKNOWN"):
        MODULE.cmd_paper_runtime_upgrade(args())
    assert json.loads(config.read_bytes())["paperDesign"]["bridgeSha256"] == MODULE.PAPER_V20_BRIDGE_SHA256
    assert json.loads(manifest.read_bytes())["configHash"] == digest(config.read_bytes())


def test_fleet_flag_cannot_be_combined_with_m1_v20(seat):
    args, *_ = seat
    case = args()
    case.m1_v20 = True
    with pytest.raises(SystemExit, match="conflicting cohort"):
        MODULE.cmd_paper_runtime_upgrade(case)

def test_precommit_exception_restores_all_original_bytes(seat, monkeypatch):
    args, config, manifest, plist, *_ = seat
    before = (config.read_bytes(), manifest.read_bytes(), plist.read_bytes())
    original = MODULE._atomic_write_bytes
    calls = 0
    def fail_before_manifest_commit(path, data, *a, **kw):
        nonlocal calls
        calls += 1
        original(path, data, *a, **kw)
        if calls == 1:
            raise OSError("injected write error before manifest commit")
    monkeypatch.setattr(MODULE, "_atomic_write_bytes", fail_before_manifest_commit)
    with pytest.raises(SystemExit, match="NOT_APPLIED"):
        MODULE.cmd_paper_runtime_upgrade(args())
    assert before == (config.read_bytes(), manifest.read_bytes(), plist.read_bytes())


def test_sealed_module_refuses_unreviewed_source_digest(monkeypatch):
    monkeypatch.setattr(MODULE, "FLEET_V20_COHORT_SOURCE_SHA256", "0" * 64)
    with pytest.raises(SystemExit, match="source hash differs"):
        MODULE._frozen_paper_fleet_module()


def test_verified_fleet_source_is_read_once_before_execution(monkeypatch):
    original_reader = MODULE._fabric_release_bytes
    calls = []

    def secure_read_once(path, *, limit):
        calls.append((path.name, limit))
        return original_reader(path, limit=limit)

    monkeypatch.setattr(MODULE, "_fabric_release_bytes", secure_read_once)
    module = MODULE._frozen_paper_fleet_module()
    assert len(module.COHORTS) == len(ALL_SEATS)
    assert calls == [("paper_v20_fleet_cohorts.py", 64 * 1024)]


def test_untrusted_bytes_refuse_before_any_module_execution(monkeypatch):
    # A changed file can never enter Python's loader after the trusted hash
    # check, because exactly those read bytes are the compiled source.
    monkeypatch.setattr(MODULE, "_fabric_release_bytes", lambda *a, **k:
                        b'raise RuntimeError("unreviewed source executed")')
    with pytest.raises(SystemExit, match="source hash differs"):
        MODULE._frozen_paper_fleet_module()


def test_existing_lifecycle_lock_blocks_second_process(seat):
    args, _, _, _, state, *_ = seat
    lock_path = state / MODULE.C2_LIFECYCLE_LOCK_NAME
    script = (
        'import fcntl, os, sys; fd=os.open(sys.argv[1], os.O_RDWR); '
        'fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)'
    )
    with MODULE._c2_lifecycle_mutex(args().account):
        locked = subprocess.run([sys.executable, "-c", script, str(lock_path)],
                                capture_output=True, text=True, timeout=5)
        assert locked.returncode != 0
    released = subprocess.run([sys.executable, "-c", script, str(lock_path)],
                              capture_output=True, text=True, timeout=5)
    assert released.returncode == 0, released.stderr[:200]


def test_fleet_flag_on_other_admitted_account_refuses_without_lock_inode(seat):
    args, config, manifest, plist, state, *_ = seat
    before = (config.read_bytes(), manifest.read_bytes(), plist.read_bytes())
    for unrelated in ("fabric-read", "chatgpt2-personal", "unreviewed-paper-seat"):
        invalid = args()
        invalid.account = unrelated
        with pytest.raises(SystemExit, match="not in reviewed cohort"):
            MODULE.cmd_paper_runtime_upgrade(invalid)
        assert before == (config.read_bytes(), manifest.read_bytes(), plist.read_bytes())
        assert not (state / MODULE.C2_LIFECYCLE_LOCK_NAME).exists()
