"""Hermetic canonical result binding; no remote workers, credentials or leases."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "remote_sub_helpers.py"
SHELL = ROOT / "remote_sub.sh"
ID = "fif-canon-proof-20261020-r1"


def controller(here, run_id, source):
    return subprocess.run(
        [sys.executable, str(HELPER), "mirror-new-macro-result",
         str(here), run_id, str(source)],
        capture_output=True, text=True, timeout=8,
    )


def workspace(tmp_path):
    (tmp_path / "lanes").mkdir(mode=0o700)
    return tmp_path


def test_custom_result_mirrors_exclusively_and_remains_unaccepted(tmp_path, monkeypatch):
    workspace(tmp_path)
    custom = tmp_path / "deliverables.out"
    payload = (b"worker-result\n" * 1024) + b"\x00tail"
    custom.write_bytes(payload)
    mode = custom.stat().st_mode
    p = controller(tmp_path, ID, custom)
    assert p.returncode == 0, p.stderr
    expected = tmp_path / "lanes" / (ID + ".remote.stdout")
    assert expected.read_bytes() == payload
    assert custom.read_bytes() == payload
    assert custom.stat().st_mode == mode
    assert expected.stat().st_nlink == 1
    assert expected.stat().st_mode & 0o777 == 0o600
    assert hashlib.sha256(payload).hexdigest() in p.stdout
    assert "bytes=" + str(len(payload)) in p.stdout

    # Only the file becomes visible; no automatic acceptance/review exists.
    sys.path.insert(0, str(ROOT))
    import fabric_task
    monkeypatch.setattr(fabric_task, "HERE", tmp_path)
    logdir = tmp_path / "state" / "remote_sub"
    logdir.mkdir(parents=True)
    (logdir / (ID + ".log")).write_text(
        f"2026-10-20T04:00Z [remote_sub id={ID} host=ubuntu1] LAUNCH stdout=x\n"
        f"2026-10-20T04:01Z [remote_sub id={ID} host=ubuntu1] DONE rc=0 signal=ok\n"
    )
    current = fabric_task.inspect_run(ID)
    assert current["state"] == "TERMINAL"
    assert current["result_available"] is True
    assert current["accepted"] is not True


def test_refuses_preexisting_canonical_without_overwrite(tmp_path):
    workspace(tmp_path)
    custom = tmp_path / "result.out"
    custom.write_text("new")
    canonical = tmp_path / "lanes" / (ID + ".remote.stdout")
    canonical.write_text("original")
    p = controller(tmp_path, ID, custom)
    assert p.returncode != 0
    assert canonical.read_text() == "original"
    assert custom.read_text() == "new"


def test_refuses_symlink_source(tmp_path):
    workspace(tmp_path)
    real = tmp_path / "real.out"
    real.write_text("task result")
    link = tmp_path / "symlink.out"
    link.symlink_to(real)
    assert controller(tmp_path, ID, link).returncode != 0
    assert not (tmp_path / "lanes" / (ID + ".remote.stdout")).exists()


def test_refuses_shared_writable_or_hardlinked_custom_output(tmp_path):
    workspace(tmp_path)
    original = tmp_path / "untrusted.out"
    original.write_text("not trustworthy")
    original.chmod(0o666)
    assert controller(tmp_path, ID, original).returncode != 0
    original.chmod(0o600)
    clone = tmp_path / "hardlink.out"
    os.link(original, clone)
    assert controller(tmp_path, ID, original).returncode != 0
    assert not (tmp_path / "lanes" / (ID + ".remote.stdout")).exists()
    assert clone.read_text() == "not trustworthy"


def test_refuses_nonprivate_canonical_directory(tmp_path):
    workspace(tmp_path)
    (tmp_path / "lanes").chmod(0o777)
    f = tmp_path / "result.out"
    f.write_text("task result")
    assert controller(tmp_path, ID, f).returncode != 0
    assert not (tmp_path / "lanes" / (ID + ".remote.stdout")).exists()


@pytest.mark.parametrize("invalid", ["..", "a/../b", "-invalid", "a:b", ""])
def test_invalid_run_identity_fails_closed(tmp_path, invalid):
    workspace(tmp_path)
    f = tmp_path / "result.out"
    f.write_text("task result")
    assert controller(tmp_path, invalid, f).returncode != 0


def test_oversized_stdout_not_made_canonical(tmp_path):
    workspace(tmp_path)
    f = tmp_path / "oversized.out"
    f.write_bytes(b"x" * (8_388_608 + 1))
    p = controller(tmp_path, ID, f)
    assert p.returncode != 0
    assert f.stat().st_size == 8_388_609
    assert not (tmp_path / "lanes" / (ID + ".remote.stdout")).exists()


def test_missing_stdout_no_placeholder(tmp_path):
    workspace(tmp_path)
    assert controller(tmp_path, ID, tmp_path / "missing").returncode != 0
    assert not list((tmp_path / "lanes").iterdir())


def run_mirror_shell_block(tmp_path, *, state="ok", source_kind="regular"):
    workspace(tmp_path)
    localout = tmp_path / "custom.out"
    if source_kind == "regular":
        localout.write_text("completed worker output\n")
    elif source_kind == "symlink":
        actual = tmp_path / "actual"
        actual.write_text("completed worker output\n")
        localout.symlink_to(actual)
    shutil.copy2(HELPER, tmp_path / HELPER.name)

    text = SHELL.read_text()
    assert text.count("# New Macro Fabric workspaces must expose") == 1
    a = text.index("# New Macro Fabric workspaces must expose")
    b = text.index('if [ "$NATIVE_MODE" -eq 1 ]; then', a)
    block = text[a:b]
    assert 'mirror-new-macro-result' in block
    code = (
        'set -eu\n'
        'log() { printf "%s\\n" "$*" >> "$HERE/mirror.log"; }\n'
        + block
        + 'printf "RSYNC_RC=%s\\n" "$RSYNC_RC"\n'
    )
    env = {
        **os.environ,
        "HERE": str(tmp_path),
        "ID": ID,
        "NEW_MACRO_COMMIT": "a" * 40,
        "RC_OBSERVED": "1",
        "WORKER_RC": "0" if state == "ok" else "7",
        "RSYNC_RC": "0",
        "LOCAL_OUT": str(localout),
        "REMOTE_SUB_PYTHON": sys.executable,
    }
    p = subprocess.run(["bash", "-c", code], env=env,
                       capture_output=True, text=True, timeout=8)
    return p, localout


def test_actual_controller_guard_mirrors_successful_custom_result(tmp_path):
    p, original = run_mirror_shell_block(tmp_path)
    assert p.returncode == 0, p.stderr
    assert "RSYNC_RC=0" in p.stdout
    assert (tmp_path / "lanes" / (ID + ".remote.stdout")).read_bytes() == original.read_bytes()
    assert "CANONICAL_RESULT_BOUND" in (tmp_path / "mirror.log").read_text()


def test_actual_controller_guard_skips_nonzero_worker(tmp_path):
    p, original = run_mirror_shell_block(tmp_path, state="failed")
    assert p.returncode == 0, p.stderr
    assert not (tmp_path / "lanes" / (ID + ".remote.stdout")).exists()
    assert not (tmp_path / "mirror.log").exists()
    assert original.exists()


def test_actual_controller_guard_fails_closed_when_copy_unverifiable(tmp_path):
    p, original = run_mirror_shell_block(tmp_path, source_kind="symlink")
    assert p.returncode == 0, p.stderr
    assert "RSYNC_RC=76" in p.stdout
    assert "CANONICAL_RESULT_MIRROR_FAILED" in (tmp_path / "mirror.log").read_text()
    assert not (tmp_path / "lanes" / (ID + ".remote.stdout")).exists()
    assert original.is_symlink()


@pytest.mark.parametrize("collision", ["custom", "canonical", "symlink_custom"])
def test_new_macro_preflight_refuses_output_collisions_before_transport(tmp_path, collision):
    workspace(tmp_path)
    src = tmp_path / "packet.txt"
    src.write_text("hermetic worker packet")
    requested = tmp_path / "requested.out"
    canonical = tmp_path / "lanes" / (ID + ".remote.stdout")
    if collision == "custom":
        requested.write_text("old custom result")
    elif collision == "canonical":
        canonical.write_text("old canonical result")
    elif collision == "symlink_custom":
        actual = tmp_path / "old"
        actual.write_text("old custom result")
        requested.symlink_to(actual)
    env = dict(
        os.environ,
        REMOTE_SUB_HERE=str(tmp_path),
        POOL_ORCHESTRATOR_ID="root1",
        POOL_PARENT_RUN_ID="parent1",
        REMOTE_SUB_SSH_CMD="/nonexistent-must-not-execute",
    )
    p = subprocess.run(
        ["bash", str(SHELL), "mb", "glm", str(src),
         "~/lanes/repos/macro", "glm-5.3-flash",
         "--run-id", ID, "--new-macro-worktree", "a" * 40,
         "--out", str(requested)],
        env=env, capture_output=True, text=True, timeout=12,
    )
    assert p.returncode == 78, (p.stdout, p.stderr)
    # This guard runs before launch/state retention; its diagnostic remains
    # on the original controller stderr, without minting a fake run receipt.
    events = p.stderr
    suffix = "OUTPUT_PREEXISTS" if collision != "canonical" else "CANONICAL_PREEXISTS"
    assert "FABRIC_NEW_MACRO_" + suffix in events
    assert "LEASE_OK" not in events
    assert "LAUNCH stdout=" not in events
    if collision == "custom":
        assert requested.read_text() == "old custom result"
    elif collision == "canonical":
        assert canonical.read_text() == "old canonical result"
    else:
        assert requested.is_symlink()
