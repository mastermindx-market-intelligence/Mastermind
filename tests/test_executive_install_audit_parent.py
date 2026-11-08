"""Run the real installer substep against temporary custody/occupant cases.

Only native ACL/ownership collaborators are simulated. Directory creation,
nofollow opens, inode comparisons and exclusive-creation refusal are real; no
production directory, service or installer is run.
"""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "ops/executive_os/install.sh").read_text()


def section(name):
    return TEXT.split(f"# --- BEGIN {name} ---\n", 1)[1].split(f"# --- END {name} ---", 1)[0]


@pytest.fixture
def provision(tmp_path):
    base = tmp_path / "MastermindExecutive"
    base.mkdir(mode=0o755)
    calls = tmp_path / "acl-calls"
    mutations = tmp_path / "ownership-calls"
    runner = tmp_path / "os-python"
    launcher = f'#!/bin/sh\n\'\'\'exec\' {shlex.quote(sys.executable)} "$0" "$@"\n\' \'\'\'\n'
    runner.write_text(launcher + '''
import os, sys
args = sys.argv[1:]
assert args[:4] == ["-I", "-S", "-B", "-"]
sys.argv = args[3:]
real_stat, real_fstat, real_mkdir = os.stat, os.fstat, os.mkdir
def root_info(info):
    fields = list(info)
    fields[4:6] = [0, 0]
    for key, index, value in (("BAD_OWNER", 4, 501), ("BAD_GROUP", 5, 20)):
        if os.environ.get(key):
            bad = real_stat(os.environ[key], follow_symlinks=False)
            if (info.st_dev, info.st_ino) == (bad.st_dev, bad.st_ino):
                fields[index] = value
    return os.stat_result(fields)
os.stat = lambda *a, **kw: root_info(real_stat(*a, **kw))
os.fstat = lambda *a, **kw: root_info(real_fstat(*a, **kw))
def chown(fd, uid, gid):
    assert (uid, gid) == (0, 0)
    with open(os.environ["MUTATIONS"], "a") as stream:
        stream.write("fchown:0:0\\n")
os.fchown = chown
def mkdir(path, mode=0o777, *, dir_fd=None):
    if os.environ.get("RACE") == "1" and path == "audit":
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dir_fd)
        os.write(fd, b"racing occupant\\n")
        os.close(fd)
    return real_mkdir(path, mode, dir_fd=dir_fd)
os.mkdir = mkdir
exec(compile(sys.stdin.read(), "installer-audit-parent", "exec"))
''')
    runner.chmod(0o755)
    script = (
        "set -euo pipefail\numask 077\n"
        + "require_native_no_acl() { printf '%s\\n' \"$2\" >> \"$CALLS\"; "
        + "[ \"${BAD_ACL:-}\" != \"$2\" ]; }\n"
        + section("gateway audit parent provisioning")
        + "\nprovision_gateway_audit_parent || exit 65\n"
    )

    def run(**updates):
        return subprocess.run(
            ["/bin/bash", "-c", script],
            env={**os.environ, "SYSTEM_ROOT": str(base), "PYTHON_BINARY": str(runner),
                 "CALLS": str(calls), "MUTATIONS": str(mutations), **updates},
            capture_output=True, text=True,
        )

    return base, calls, mutations, run


def snapshot(path):
    info = path.lstat()
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode, info.st_mtime_ns


def test_missing_parent_is_created_without_gateway_leaf(provision):
    base, calls, mutations, run = provision
    result = run()
    assert result.returncode == 0, result.stderr
    parent = base / "audit"
    info = parent.stat()
    assert info.st_mode & 0o7777 == 0o755
    assert mutations.read_text() == "fchown:0:0\n"
    assert list(parent.iterdir()) == []
    assert calls.read_text().splitlines() == [str(base), str(parent)]


def test_existing_safe_parent_and_leaf_are_unchanged(provision):
    base, _, mutations, run = provision
    parent = base / "audit"
    parent.mkdir(mode=0o750)
    leaf = parent / "os-commission-publication"
    leaf.mkdir(mode=0o700)
    record = leaf / "retained.json"
    record.write_bytes(b"original audit record\n")
    before = {p: snapshot(p) for p in (parent, leaf, record)}
    result = run()
    assert result.returncode == 0, result.stderr
    assert {p: snapshot(p) for p in before} == before
    assert record.read_bytes() == b"original audit record\n"
    assert not mutations.exists()


@pytest.mark.parametrize("damage", ["symlink", "dangling", "file", "owner", "group", "writable", "acl"])
def test_unsafe_existing_parent_refuses_without_repair(provision, damage):
    base, _, mutations, run = provision
    parent = base / "audit"
    updates = {}
    if damage in {"symlink", "dangling"}:
        target = base / "other"
        if damage == "symlink":
            target.mkdir()
        parent.symlink_to(target, target_is_directory=True)
    elif damage == "file":
        parent.write_bytes(b"retain occupant\n")
    else:
        parent.mkdir(mode=0o755)
        if damage == "owner":
            updates["BAD_OWNER"] = str(parent)
        elif damage == "group":
            updates["BAD_GROUP"] = str(parent)
        elif damage == "writable":
            parent.chmod(0o775)
        elif damage == "acl":
            updates["BAD_ACL"] = str(parent)
    before = snapshot(parent)
    result = run(**updates)
    assert result.returncode == 65
    assert snapshot(parent) == before
    assert not mutations.exists()
    assert not (parent / "os-commission-publication").exists()
    if damage == "file":
        assert parent.read_bytes() == b"retain occupant\n"


@pytest.mark.parametrize("damage", ["owner", "group", "writable", "acl", "symlink"])
def test_unsafe_base_refuses_before_parent_creation(provision, damage):
    base, _, mutations, run = provision
    updates = {}
    if damage == "owner":
        updates["BAD_OWNER"] = str(base)
    elif damage == "group":
        updates["BAD_GROUP"] = str(base)
    elif damage == "writable":
        base.chmod(0o777)
    elif damage == "acl":
        updates["BAD_ACL"] = str(base)
    else:
        target = base.with_name("retained-base")
        base.rename(target)
        base.symlink_to(target, target_is_directory=True)
    before = snapshot(base)
    result = run(**updates)
    assert result.returncode == 65
    assert snapshot(base) == before
    assert not (base / "audit").exists()
    assert not mutations.exists()


def test_racing_occupant_is_retained_without_custody_change(provision):
    base, _, mutations, run = provision
    result = run(RACE="1")
    assert result.returncode == 65
    assert (base / "audit").read_bytes() == b"racing occupant\n"
    assert not mutations.exists()


def test_stage_only_exits_before_audit_parent_call(tmp_path):
    marker = tmp_path / "unexpected-parent-provision"
    script = (
        "set -euo pipefail\nSTAGE_RELEASE_ONLY=1\nEXPECTED_SHA=source\n"
        + "stage_sealed_release() { :; }\n"
        + "provision_gateway_audit_parent() { touch " + shlex.quote(str(marker)) + "; }\n"
        + section("stage-only dispatch")
        + "\nprovision_gateway_audit_parent || exit 65\n"
    )
    result = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '"staged_unselected":true' in result.stdout
    assert not marker.exists()
    assert TEXT.index("# --- END stage-only dispatch ---") < TEXT.index(
        "\nprovision_gateway_audit_parent || exit 65\n"
    )


def _normal_fragment():
    start = TEXT.index('wait_for_launchd_absent "$RELAY_LABEL" relay || exit 65\n')
    end = TEXT.index('\n# This remains a substep of the existing serialized installer publication.', start)
    return TEXT[start:end]


def _run_normal(provision, *, seal_rc=0, absence_at="", bad_acl="", fsync_at=0):
    base, calls, mutations, _ = provision
    events = base.parent / "normal-events"
    script = (
        "set -euo pipefail\numask 077\n"
        + "RELAY_LABEL=relay\nCONTROL_LABEL=control\nWORKER_LABEL=worker\n"
        + "BACKUP_LABEL=backup\nPRIVILEGED_LABEL=privileged\n"
        + "wait_for_launchd_absent() { printf 'absent:%s\\n' \"$2\" >> \"$EVENTS\"; "
        + "[ \"$ABSENCE_AT\" != \"$2\" ]; }\n"
        + "stage_sealed_release() { printf 'seal\\n' >> \"$EVENTS\"; return \"$SEAL_RC\"; }\n"
        + "require_native_no_acl() { printf '%s\\n' \"$2\" >> \"$CALLS\"; "
        + "printf 'acl:%s\\n' \"$2\" >> \"$EVENTS\"; [ \"$BAD_ACL\" != \"$2\" ]; }\n"
        + section("gateway audit parent provisioning")
        + "\n" + _normal_fragment()
        + "\nprintf 'published\\n' >> \"$EVENTS\"\n"
    )
    result = subprocess.run(
        ["/bin/bash", "-c", script],
        env={"PATH": os.defpath, "SYSTEM_ROOT": str(base),
             "PYTHON_BINARY": str(base.parent / "os-python"),
             "CALLS": str(calls), "MUTATIONS": str(mutations), "EVENTS": str(events),
             "SEAL_RC": str(seal_rc), "ABSENCE_AT": absence_at, "BAD_ACL": bad_acl,
             "FSYNC_AT": str(fsync_at), "FSYNC_CALLS": str(base.parent / "fsync-calls")},
        capture_output=True, text=True, timeout=10,
    )
    return result, events.read_text().splitlines()


@pytest.mark.parametrize("seal_rc", [0, 67])
def test_actual_admin_only_dispatch_exits_before_provisioning(tmp_path, seal_rc):
    events = tmp_path / "admin-events"
    script = (
        "set -euo pipefail\nSTAGE_ADMIN_CHECKOUT_ONLY=1\nEXPECTED_SHA=source\n"
        + "stage_sealed_release() { printf 'seal\\n' >> \"$EVENTS\"; return \"$SEAL_RC\"; }\n"
        + "prepare_admin_checkout() { printf 'checkout\\n' >> \"$EVENTS\"; }\n"
        + "provision_gateway_audit_parent() { printf 'unexpected-audit\\n' >> \"$EVENTS\"; }\n"
        + section("admin-checkout-only dispatch")
        + "\nprovision_gateway_audit_parent || exit 65\n"
        + "printf 'unexpected-normal\\n' >> \"$EVENTS\"\n"
    )
    result = subprocess.run(["/bin/bash", "-c", script],
        env={"PATH": os.defpath, "EVENTS": str(events), "SEAL_RC": str(seal_rc)},
        capture_output=True, text=True, timeout=10)
    assert result.returncode == (0 if seal_rc == 0 else 65), result.stderr
    assert events.read_text().splitlines() == (["seal", "checkout"] if seal_rc == 0 else ["seal"])
    assert ('"staged_admin_checkout":true' in result.stdout) is (seal_rc == 0)
    assert TEXT.index("# --- END admin-checkout-only dispatch ---") < TEXT.index(
        "# --- BEGIN gateway audit parent provisioning ---")


@pytest.mark.parametrize("case", ["success", "seal_failure", "provision_failure", "absence_failure"])
def test_actual_normal_install_seals_then_provisions(provision, case):
    base, calls, mutations, _ = provision
    result, events = _run_normal(provision,
        seal_rc=67 if case == "seal_failure" else 0,
        absence_at="worker" if case == "absence_failure" else "",
        bad_acl=str(base) if case == "provision_failure" else "")
    absence = ["absent:" + name for name in ("relay", "control", "worker", "backup", "privileged")]
    assert result.returncode == (0 if case == "success" else 65), result.stderr
    if case == "absence_failure":
        assert events == absence[:3]
    elif case == "seal_failure":
        assert events == absence + ["seal"]
    elif case == "provision_failure":
        assert events == absence + ["seal", "acl:" + str(base)]
    else:
        assert events == absence + ["seal", "acl:" + str(base), "acl:" + str(base / "audit"), "published"]
        assert (base / "audit").stat().st_mode & 0o7777 == 0o755
        assert calls.read_text().splitlines() == [str(base), str(base / "audit")]
        assert mutations.read_text() == "fchown:0:0\n"
    if case != "success":
        assert not (base / "audit").exists()
        assert not mutations.exists()


def _instrument_runner(provision, source):
    base, _, _, _ = provision
    runner = base.parent / "os-python"
    original = runner.read_text()
    anchor = 'exec(compile(sys.stdin.read(), "installer-audit-parent", "exec"))'
    assert original.count(anchor) == 1
    runner.write_text(original.replace(anchor, source + "\n" + anchor))


@pytest.mark.parametrize("which", [1, 2])
def test_each_directory_fsync_failure_retains_partial_parent_and_stops_publication(provision, which):
    base, calls, mutations, _ = provision
    _instrument_runner(provision, '''
real_fsync = os.fsync
fsync_count = 0
def failing_fsync(fd):
    global fsync_count
    fsync_count += 1
    info = os.fstat(fd)
    with open(os.environ["FSYNC_CALLS"], "a") as stream:
        stream.write(f"{fsync_count}:{info.st_dev}:{info.st_ino}\\n")
    if fsync_count == int(os.environ["FSYNC_AT"]):
        raise OSError(5, "synthetic directory fsync failure")
    return real_fsync(fd)
os.fsync = failing_fsync
''')
    result, events = _run_normal(provision, fsync_at=which)
    assert result.returncode == 65
    assert "published" not in events and events.count("seal") == 1
    assert calls.read_text().splitlines() == [str(base)]
    assert mutations.read_text() == "fchown:0:0\n"
    parent = base / "audit"
    info = parent.stat()
    assert info.st_mode & 0o7777 == 0o755 and list(parent.iterdir()) == []
    observed = [tuple(map(int, line.split(":"))) for line in (base.parent / "fsync-calls").read_text().splitlines()]
    assert [item[0] for item in observed] == list(range(1, which + 1))
    assert observed[0][1:] == (info.st_dev, info.st_ino)
    if which == 2:
        assert observed[1][1:] == (base.stat().st_dev, base.stat().st_ino)


def test_replaced_observed_parent_refuses_before_custody_change(provision):
    base, _, mutations, _ = provision
    parent = base / "audit"
    parent.mkdir(mode=0o755)
    record = parent / "retained-record"
    record.write_bytes(b"retain original inode\n")
    original_parent, original_record = snapshot(parent), snapshot(record)
    _instrument_runner(provision, '''
real_open = os.open
def replace_before_open(path, flags, mode=0o777, *, dir_fd=None):
    if path == "audit" and dir_fd is not None:
        os.rename("audit", "retained-audit", src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        real_mkdir("audit", 0o755, dir_fd=dir_fd)
    return real_open(path, flags, mode, dir_fd=dir_fd)
os.open = replace_before_open
''')
    result, events = _run_normal(provision)
    assert result.returncode == 65
    assert "published" not in events and events.count("seal") == 1
    assert not mutations.exists()
    assert snapshot(base / "retained-audit") == original_parent
    assert snapshot(base / "retained-audit" / "retained-record") == original_record
    assert (base / "retained-audit" / "retained-record").read_bytes() == b"retain original inode\n"
    assert parent.is_dir() and list(parent.iterdir()) == []
