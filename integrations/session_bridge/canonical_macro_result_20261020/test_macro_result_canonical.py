"""Run-scoped custom stdout delivery from canonical Fabric result. No live work."""
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


def workspace(tmp_path):
    (tmp_path / "lanes").mkdir(mode=0o700)
    return tmp_path


def canonical(here, rid=ID):
    return here / "lanes" / (rid + ".remote.stdout")


def controller(here, run_id, destination):
    return subprocess.run(
        [sys.executable, str(HELPER), "mirror-new-macro-result",
         str(here), run_id, str(destination)],
        capture_output=True, text=True, timeout=8,
    )


def test_canonical_retained_and_custom_exclusive_without_autoaccept(tmp_path, monkeypatch):
    workspace(tmp_path)
    original = canonical(tmp_path)
    payload = b"worker-result\n" * 1024 + b"\x00tail"
    original.write_bytes(payload)
    mode = original.stat().st_mode
    target = tmp_path / "caller-selected.out"
    p = controller(tmp_path, ID, target)
    assert p.returncode == 0, p.stderr
    assert original.read_bytes() == payload
    assert target.read_bytes() == payload
    assert original.stat().st_mode == mode
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.stat().st_nlink == 1
    assert hashlib.sha256(payload).hexdigest() in p.stdout
    assert "CUSTOM_RESULT_BOUND_FROM_CANONICAL" in p.stdout

    # Canonical result visibility does not authorize automatic acceptance.
    sys.path.insert(0, str(ROOT))
    import fabric_task
    monkeypatch.setattr(fabric_task, "HERE", tmp_path)
    logdir = tmp_path / "state" / "remote_sub"
    logdir.mkdir(parents=True)
    (logdir / (ID + ".log")).write_text(
        f"2026-10-20T04:00Z [remote_sub id={ID} host=ubuntu1] LAUNCH stdout=x\n"
        f"2026-10-20T04:01Z [remote_sub id={ID} host=ubuntu1] DONE rc=0 signal=ok\n")
    status = fabric_task.inspect_run(ID)
    assert status["state"] == "TERMINAL"
    assert status["result_available"] is True
    assert status["accepted"] is not True


def test_existing_custom_target_never_overwritten(tmp_path):
    workspace(tmp_path)
    canonical(tmp_path).write_text("new canonical")
    target = tmp_path / "caller.out"
    target.write_text("another worker's result")
    p = controller(tmp_path, ID, target)
    assert p.returncode != 0
    assert target.read_text() == "another worker's result"
    assert canonical(tmp_path).read_text() == "new canonical"


def test_custom_destination_symlink_refused(tmp_path):
    workspace(tmp_path)
    canonical(tmp_path).write_text("canonical data")
    real = tmp_path / "other"
    real.write_text("other worker")
    target = tmp_path / "caller.out"
    target.symlink_to(real)
    assert controller(tmp_path, ID, target).returncode != 0
    assert target.is_symlink() and real.read_text() == "other worker"


def test_untrusted_custom_destination_directory_refused(tmp_path):
    workspace(tmp_path)
    canonical(tmp_path).write_text("canonical data")
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    unsafe.chmod(0o777)
    target = unsafe / "caller.out"
    assert controller(tmp_path, ID, target).returncode != 0
    assert not target.exists()
    assert canonical(tmp_path).read_text() == "canonical data"


def test_shared_writable_or_hardlinked_canonical_refused(tmp_path):
    workspace(tmp_path)
    original = canonical(tmp_path)
    original.write_text("untrusted canonical")
    original.chmod(0o666)
    target = tmp_path / "caller.out"
    assert controller(tmp_path, ID, target).returncode != 0
    original.chmod(0o600)
    clone = tmp_path / "hardlink"
    os.link(original, clone)
    assert controller(tmp_path, ID, target).returncode != 0
    assert not target.exists() and clone.read_text() == "untrusted canonical"


@pytest.mark.parametrize("invalid", ["..", "a/../b", "-invalid", "a:b", ""])
def test_invalid_canonical_run_id_refused(tmp_path, invalid):
    workspace(tmp_path)
    canonical(tmp_path).write_text("true canonical")
    assert controller(tmp_path, invalid, tmp_path / "caller.out").returncode != 0
    assert not (tmp_path / "caller.out").exists()


def test_oversized_canonical_cannot_be_misrepresented(tmp_path):
    workspace(tmp_path)
    original = canonical(tmp_path)
    original.write_bytes(b"x" * (8_388_608 + 1))
    p = controller(tmp_path, ID, tmp_path / "caller.out")
    assert p.returncode != 0
    assert original.stat().st_size == 8_388_609
    assert not (tmp_path / "caller.out").exists()


def test_missing_canonical_source_never_creates_custom_placeholder(tmp_path):
    workspace(tmp_path)
    assert controller(tmp_path, ID, tmp_path / "caller.out").returncode != 0
    assert not (tmp_path / "caller.out").exists()


def post_transfer(tmp_path, *, run_id=ID, macro=True, rc=0,
                  custom=None, source_kind="regular"):
    workspace(tmp_path)
    target = custom or tmp_path / "caller.out"
    shutil.copy2(HELPER, tmp_path / HELPER.name)
    fake = tmp_path / "fake-rsync"
    fake.write_text('#!/bin/sh\nprintf "from-remote:%s\\n" "$2" > "$3"\n')
    fake.chmod(0o700)
    text = SHELL.read_text()
    a = text.index('WORKER_RC="$RC"\n\n# Only successful, observed new-Macro workers')
    b = text.index('if [ "$NATIVE_MODE" -eq 1 ]; then', a)
    block = text[a:b]
    assert 'RSYNC_DEST="$CAPTURE_TMP"' in block
    assert 'publish-new-macro-canonical' in block
    assert 'mirror-new-macro-result' in block
    shell = ('set -eu\n'
             'log() { printf "%s\\n" "$*" >> "$HERE/mirror.log"; }\n'
             + block + 'printf "RSYNC_RC=%s\\n" "$RSYNC_RC"\n')
    env = dict(
        os.environ,
        HERE=str(tmp_path), ID=run_id, NEW_MACRO_COMMIT="a"*40 if macro else "",
        RC_OBSERVED="1", RC=str(rc), WORKER_RC=str(rc), RSYNC_RC="0",
        LOCAL_OUT=str(target), REMOTE_SUB_PYTHON=sys.executable,
        REMOTE_STDOUT="lanes-"+run_id+".stdout", SSH_ALIAS="fakehost",
        RSYNC_CMD=str(fake),
    )
    p = subprocess.run(["bash", "-c", shell], env=env,
                       capture_output=True, text=True, timeout=10)
    return p, target


def publish_capture(here, run_id, capture):
    return subprocess.run([
        sys.executable, str(HELPER), "publish-new-macro-canonical",
        str(here), run_id, str(capture)
    ],capture_output=True,text=True,timeout=8)


def test_capture_promotes_only_exclusively_and_preserves_payload(tmp_path):
    workspace(tmp_path)
    staged = tmp_path / "lanes" / (".macro-capture." + ID + ".abcdef01")
    staged.write_bytes(b"verified first transfer")
    staged.chmod(0o644)  # Simulates rsync preserving a permissive upstream mode.
    p = publish_capture(tmp_path, ID, staged)
    assert p.returncode == 0,p.stderr
    assert not staged.exists()
    assert canonical(tmp_path).read_bytes() == b"verified first transfer"
    assert canonical(tmp_path).stat().st_mode & 0o777 == 0o600
    assert "CANONICAL_RESULT_CAPTURED" in p.stdout


def test_capture_cannot_overwrite_earlier_same_run_result(tmp_path):
    workspace(tmp_path)
    already = canonical(tmp_path)
    already.write_bytes(b"first run")
    staged = tmp_path / "lanes" / (".macro-capture." + ID + ".abcdef02")
    staged.write_bytes(b"second attempt must not replace")
    p = publish_capture(tmp_path, ID, staged)
    assert p.returncode != 0
    assert already.read_bytes() == b"first run"
    assert staged.read_bytes() == b"second attempt must not replace"


def test_capture_symlink_and_noncanonical_paths_refused(tmp_path):
    workspace(tmp_path)
    real = tmp_path / "real"
    real.write_bytes(b"source")
    staged = tmp_path / "lanes" / (".macro-capture." + ID + ".abcdef03")
    staged.symlink_to(real)
    assert publish_capture(tmp_path, ID, staged).returncode != 0
    assert staged.is_symlink() and real.read_bytes()==b"source"
    assert publish_capture(tmp_path, ID, real).returncode != 0
    assert not canonical(tmp_path).exists()


def test_real_controller_block_binds_run_scoped_output_first(tmp_path):
    p, custom = post_transfer(tmp_path)
    assert p.returncode == 0, p.stderr
    assert "RSYNC_RC=0" in p.stdout
    assert canonical(tmp_path).read_bytes() == custom.read_bytes()
    assert "from-remote:" in custom.read_text()
    assert "CUSTOM_RESULT_BOUND_FROM_CANONICAL" in (tmp_path / "mirror.log").read_text()


def test_two_different_run_ids_cannot_overwrite_shared_custom_filename(tmp_path):
    p1, custom = post_transfer(tmp_path,run_id="worker-one")
    assert p1.returncode == 0 and "RSYNC_RC=0" in p1.stdout
    first = custom.read_bytes()
    # Simulates a post-launch collision despite both preflight checks having
    # passed before either output existed.
    p2, _ = post_transfer_second(tmp_path,run_id="worker-two",custom=custom)
    assert p2.returncode == 0 and "RSYNC_RC=76" in p2.stdout
    assert custom.read_bytes() == first
    assert canonical(tmp_path, "worker-one").exists()
    assert canonical(tmp_path, "worker-two").exists()
    assert canonical(tmp_path, "worker-two").read_bytes() != canonical(tmp_path, "worker-one").read_bytes()


def post_transfer_second(tmp_path, *, run_id, custom):
    # The first call created the lanes directory; reuse it without deletion.
    text = SHELL.read_text()
    a = text.index('WORKER_RC="$RC"\n\n# Only successful, observed new-Macro workers')
    b = text.index('if [ "$NATIVE_MODE" -eq 1 ]; then', a)
    block = text[a:b]
    script = ('set -eu\n'
              'log() { printf "%s\\n" "$*" >> "$HERE/mirror2.log"; }\n'
              + block + 'printf "RSYNC_RC=%s\\n" "$RSYNC_RC"\n')
    env = dict(
        os.environ, HERE=str(tmp_path), ID=run_id,
        NEW_MACRO_COMMIT="a"*40, RC_OBSERVED="1", RC="0", RSYNC_RC="0",
        LOCAL_OUT=str(custom), REMOTE_SUB_PYTHON=sys.executable,
        REMOTE_STDOUT="lanes-"+run_id+".stdout", SSH_ALIAS="fakehost",
        RSYNC_CMD=str(tmp_path / "fake-rsync"),
    )
    p = subprocess.run(["bash", "-c", script],env=env,capture_output=True,text=True,timeout=10)
    return p, custom


def test_nonzero_worker_uses_original_custom_output_contract(tmp_path):
    p, custom = post_transfer(tmp_path,rc=7)
    assert p.returncode == 0, p.stderr
    assert "RSYNC_RC=0" in p.stdout
    assert custom.is_file() and not canonical(tmp_path).exists()


def test_non_macro_worker_retains_unmodified_custom_output_contract(tmp_path):
    p, custom = post_transfer(tmp_path,macro=False)
    assert p.returncode == 0, p.stderr
    assert custom.is_file() and not canonical(tmp_path).exists()


@pytest.mark.parametrize("collision", ["custom", "canonical", "symlink_custom"])
def test_macro_preflight_refuses_output_collisions_before_provider(tmp_path, collision):
    workspace(tmp_path)
    packet = tmp_path / "packet.txt"
    packet.write_text("hermetic worker packet")
    requested = tmp_path / "requested.out"
    stored = canonical(tmp_path)
    if collision == "custom":
        requested.write_text("old caller output")
    elif collision == "canonical":
        stored.write_text("old canonical output")
    else:
        actual = tmp_path / "old"
        actual.write_text("previous run output")
        requested.symlink_to(actual)
    env = dict(os.environ,REMOTE_SUB_HERE=str(tmp_path),
               POOL_ORCHESTRATOR_ID="root1", POOL_PARENT_RUN_ID="parent1",
               REMOTE_SUB_SSH_CMD="/nonexistent-transport-must-not-run")
    p = subprocess.run(
        ["bash", str(SHELL), "mb", "glm", str(packet),
         "~/lanes/repos/macro", "glm-5.3-flash",
         "--run-id", ID, "--new-macro-worktree", "a"*40,
         "--out", str(requested)],
        env=env,capture_output=True,text=True,timeout=12,
    )
    assert p.returncode == 78, p.stderr
    diagnostic = ("CANONICAL_PREEXISTS" if collision == "canonical"
                  else "OUTPUT_PREEXISTS")
    assert "FABRIC_NEW_MACRO_"+diagnostic in p.stderr
    assert "LAUNCH stdout" not in p.stderr
    if collision == "custom":
        assert requested.read_text() == "old caller output"
    elif collision == "canonical":
        assert stored.read_text() == "old canonical output"
    else:
        assert requested.is_symlink()
