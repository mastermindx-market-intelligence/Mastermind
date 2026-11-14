"""Tests for scripts/mmos_rollback.py (snapshot / plan / execute rollback).

Hermetic: fake bundles under tmp "Applications" dirs; the real /Applications
and ~/Applications are never touched. Dry-run purity is asserted with whole
tree hashes so any stray write fails the test.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import mmos_installed_receipt as mr  # noqa: E402
from scripts import mmos_rollback as rb  # noqa: E402
from tests.mmos_fake_bundle import make_fake_app  # noqa: E402

REV_A = "3652d8907df1738de551dd3032b42aa2a2acb482"
IDENT_A = "mmos-persistent-login-20261109-3652d89"
REV_B = "06ef56a39c085af72bcbf0866db8e43f99cd6034"
IDENT_B = "mmos-office-connection-06ef56a3-20261109-01a1a4bf"


def tree_hash(root: Path) -> str:
    """Hash everything (kind, mode, mtime_ns, content) under root."""
    root = Path(root)
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        stat = path.lstat()
        if path.is_symlink():
            digest.update(f"{rel}|link|{os.readlink(path)}".encode())
        elif path.is_dir():
            digest.update(f"{rel}|dir|{stat.st_mode}|{stat.st_mtime_ns}".encode())
        else:
            file_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            digest.update(f"{rel}|file|{stat.st_mode}|{stat.st_mtime_ns}|{file_digest}".encode())
    return digest.hexdigest()


class Lane:
    def __init__(self, tmp_path: Path):
        self.apps = tmp_path / "Applications"
        self.archive = tmp_path / "archive"
        self.apps.mkdir()
        self.archive.mkdir()

    def install(self, revision, identity):
        return make_fake_app(self.apps, revision=revision, identity=identity, marker=True)

    def args(self, bundle: Path, *rest):
        return ["--bundle", str(bundle), "--archive-root", str(self.archive), *rest]


@pytest.fixture()
def lane(tmp_path):
    return Lane(tmp_path)


@pytest.fixture(autouse=True)
def _deterministic_process_table(monkeypatch):
    """No live process matches a fake bundle by default, on every machine.

    The real host may genuinely run Mastermind OS (executable basename
    `mastermind-os`), which would make basename-ambiguity refusals
    machine-dependent. Tests that need a live app re-patch ps_snapshot.
    """
    monkeypatch.setattr(mr, "ps_snapshot", lambda: [])


def _only_entry(parent: Path, prefix: str) -> Path:
    matches = [p for p in parent.iterdir() if p.name.startswith(prefix)]
    assert len(matches) == 1, [p.name for p in parent.iterdir()]
    return matches[0]


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

def test_snapshot_creates_archive_and_is_idempotent(lane, capsys):
    current = lane.install(REV_A, IDENT_A)
    assert rb.main(lane.args(current, "snapshot")) == rb.EXIT_OK
    dest = _only_entry(lane.archive, f"{IDENT_A}-{REV_A[:12]}")
    assert (dest / "Mastermind OS.app" / "Contents" / "MacOS" / "mastermind-os").is_file()
    receipt = json.loads((dest / "receipt.json").read_text())
    assert receipt["schema"] == mr.SCHEMA
    assert (dest / "receipt.digest").read_text().strip() == receipt["receipt_digest"]
    first_hash = tree_hash(lane.archive)

    assert rb.main(lane.args(current, "snapshot")) == rb.EXIT_OK
    assert "already archived" in capsys.readouterr().out
    assert tree_hash(lane.archive) == first_hash  # no second copy, mtimes untouched


def test_snapshot_disambiguates_same_name_different_bytes(lane):
    current = lane.install(REV_A, IDENT_A)
    assert rb.main(lane.args(current, "snapshot")) == rb.EXIT_OK
    # Rebuild at the SAME identity/revision but different bytes (toolchain drift).
    exe = current / "Contents" / "MacOS" / "mastermind-os"
    exe.write_bytes(exe.read_bytes() + b"rebuild-padding")
    exe.chmod(0o755)
    assert rb.main(lane.args(current, "snapshot")) == rb.EXIT_OK
    entries = [p.name for p in lane.archive.iterdir()]
    base = f"{IDENT_A}-{REV_A[:12]}"
    assert sum(1 for name in entries if name == base or name.startswith(base + "--")) == 2


def test_snapshot_missing_bundle_is_error(lane, capsys):
    assert rb.main(lane.args(lane.apps / "Ghost.app", "snapshot")) == rb.EXIT_ERROR


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

def test_plan_prints_steps_and_changes_nothing(lane, capsys):
    current = lane.install(REV_A, IDENT_A)
    assert rb.main(lane.args(current, "snapshot")) == rb.EXIT_OK
    dest = _only_entry(lane.archive, f"{IDENT_A}-{REV_A[:12]}")
    apps_hash, archive_hash = tree_hash(lane.apps), tree_hash(lane.archive)

    assert rb.main(lane.args(current, "plan", "--to", str(dest))) == rb.EXIT_OK
    out = capsys.readouterr().out
    for needle in (
        "NOTHING has been changed",
        "HUMAN STEP",
        "Quit Mastermind OS",
        "rollback-tmp-",
        "mmos_installed_receipt.py",
        "Build details",
        REV_A,
        IDENT_A,
    ):
        assert needle in out, needle
    assert tree_hash(lane.apps) == apps_hash
    assert tree_hash(lane.archive) == archive_hash


def test_plan_accepts_receipt_json_path(lane, capsys):
    current = lane.install(REV_A, IDENT_A)
    assert rb.main(lane.args(current, "snapshot")) == rb.EXIT_OK
    dest = _only_entry(lane.archive, f"{IDENT_A}-{REV_A[:12]}")
    assert rb.main(lane.args(current, "plan", "--to", str(dest / "receipt.json"))) == rb.EXIT_OK
    assert "ROLLBACK PLAN" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# execute refusals
# ---------------------------------------------------------------------------

def test_execute_refused_without_flag(lane, capsys):
    current = lane.install(REV_A, IDENT_A)
    assert rb.main(lane.args(current, "snapshot")) == rb.EXIT_OK
    dest = _only_entry(lane.archive, f"{IDENT_A}-{REV_A[:12]}")
    apps_hash, archive_hash = tree_hash(lane.apps), tree_hash(lane.archive)
    assert rb.main(lane.args(current, "execute", "--to", str(dest))) == rb.EXIT_REFUSED_DRY_RUN
    out = capsys.readouterr().out
    assert "EXECUTE REFUSED" in out and "--execute" in out
    assert tree_hash(lane.apps) == apps_hash
    assert tree_hash(lane.archive) == archive_hash


def test_dry_run_allowed_even_while_app_running(lane, capsys, monkeypatch):
    # Regression: a read-only dry-run must not demand quitting the app; the
    # running-app refusal guards only the real mutation (caught live on
    # m2studio where the real app shares the executable basename).
    current = lane.install(REV_A, IDENT_A)
    assert rb.main(lane.args(current, "snapshot")) == rb.EXIT_OK
    dest = _only_entry(lane.archive, f"{IDENT_A}-{REV_A[:12]}")
    exe = current / "Contents" / "MacOS" / "mastermind-os"
    monkeypatch.setattr(mr, "ps_snapshot", lambda: [(73195, str(exe))])
    apps_hash, archive_hash = tree_hash(lane.apps), tree_hash(lane.archive)
    rc = rb.main(lane.args(current, "execute", "--to", str(dest)))
    assert rc == rb.EXIT_REFUSED_DRY_RUN
    assert "EXECUTE REFUSED" in capsys.readouterr().out
    assert tree_hash(lane.apps) == apps_hash
    assert tree_hash(lane.archive) == archive_hash


def test_execute_refused_when_app_runs_from_current_bundle(lane, capsys, monkeypatch):
    current = lane.install(REV_A, IDENT_A)
    assert rb.main(lane.args(current, "snapshot")) == rb.EXIT_OK
    dest = _only_entry(lane.archive, f"{IDENT_A}-{REV_A[:12]}")
    exe = current / "Contents" / "MacOS" / "mastermind-os"
    monkeypatch.setattr(mr, "ps_snapshot", lambda: [(73195, str(exe))])
    apps_hash, archive_hash = tree_hash(lane.apps), tree_hash(lane.archive)
    rc = rb.main(lane.args(current, "execute", "--to", str(dest), "--execute"))
    assert rc == rb.EXIT_REFUSED_RUNNING
    out = capsys.readouterr().out
    assert "HUMAN STEP" in out and "quit" in out.lower()
    assert tree_hash(lane.apps) == apps_hash
    assert tree_hash(lane.archive) == archive_hash


def test_execute_refused_on_digest_mismatch(lane, capsys):
    current = lane.install(REV_A, IDENT_A)
    assert rb.main(lane.args(current, "snapshot")) == rb.EXIT_OK
    dest = _only_entry(lane.archive, f"{IDENT_A}-{REV_A[:12]}")
    archived_exe = dest / "Mastermind OS.app" / "Contents" / "MacOS" / "mastermind-os"
    archived_exe.write_bytes(archived_exe.read_bytes() + b"tamper")  # archive no longer matches receipt
    apps_hash = tree_hash(lane.apps)
    rc = rb.main(lane.args(current, "execute", "--to", str(dest), "--execute"))
    assert rc == rb.EXIT_VERIFY_FAILED
    assert "digest" in capsys.readouterr().err
    assert tree_hash(lane.apps) == apps_hash  # install dir untouched


def test_execute_refused_on_traversal_target(lane, capsys):
    current = lane.install(REV_A, IDENT_A)
    assert rb.main(lane.args(current, "snapshot")) == rb.EXIT_OK
    apps_hash, archive_hash = tree_hash(lane.apps), tree_hash(lane.archive)
    escapes = [
        str(lane.archive / ".." / ".." / "evil"),
        "/tmp",
        str(lane.archive / "sub" / ".." / ".." / ".." / "etc"),
    ]
    for target in escapes:
        assert rb.main(lane.args(current, "execute", "--to", target, "--execute")) == rb.EXIT_REFUSED_TARGET
        assert rb.main(lane.args(current, "plan", "--to", target)) == rb.EXIT_REFUSED_TARGET
    capsys.readouterr()
    assert tree_hash(lane.apps) == apps_hash
    assert tree_hash(lane.archive) == archive_hash


def test_execute_missing_current_bundle_is_error(lane):
    assert rb.main(lane.args(lane.apps / "Ghost.app", "execute", "--to", str(lane.archive), "--execute")) \
        == rb.EXIT_ERROR


# ---------------------------------------------------------------------------
# real execute (against fake bundles only)
# ---------------------------------------------------------------------------

def test_execute_installs_archive_and_preserves_previous(lane, capsys):
    current = lane.install(REV_A, IDENT_A)  # currently installed: A
    assert rb.main(lane.args(current, "snapshot")) == rb.EXIT_OK
    dest_a = _only_entry(lane.archive, f"{IDENT_A}-{REV_A[:12]}")

    # Build the ROLLBACK TARGET B, archive it, then swap it in as installed.
    target_b = make_fake_app(lane.apps.parent / "staging", revision=REV_B, identity=IDENT_B)
    assert rb.main(lane.args(target_b, "snapshot")) == rb.EXIT_OK
    dest_b = _only_entry(lane.archive, f"{IDENT_B}-{REV_B[:12]}")
    expected_digest = (dest_b / "receipt.digest").read_text().strip()

    rc = rb.main(lane.args(current, "execute", "--to", str(dest_b), "--execute"))
    assert rc == rb.EXIT_OK
    out = capsys.readouterr().out
    assert expected_digest in out
    assert "HUMAN" in out

    fresh = mr.observe_bundle(current)
    assert fresh["receipt_digest"] == expected_digest
    assert fresh["source_revision"]["value"] == REV_B
    assert fresh["build_identity"]["value"] == IDENT_B

    preserved = sorted(lane.archive.glob("rollback-tmp-*"))
    assert len(preserved) == 1
    old = preserved[0] / "Mastermind OS.app"
    assert (old / "Contents" / "MacOS" / "mastermind-os").is_file()
    old_receipt = mr.observe_bundle(old)
    assert old_receipt["source_revision"]["value"] == REV_A  # previous bundle retained
    assert (dest_a / "receipt.digest").read_text().strip() == old_receipt["receipt_digest"]


# ---------------------------------------------------------------------------
# install (place a freshly built .app at the install location)
# ---------------------------------------------------------------------------

def _built_source(lane: Lane, revision: str, identity: str) -> Path:
    staging = lane.apps.parent / "build-output"
    staging.mkdir(exist_ok=True)
    return make_fake_app(staging, revision=revision, identity=identity, marker=True)


def test_install_refused_without_flag(lane, capsys):
    current = lane.install(REV_A, IDENT_A)
    source = _built_source(lane, REV_B, IDENT_B)
    apps_hash, archive_hash = tree_hash(lane.apps), tree_hash(lane.archive)
    rc = rb.main(lane.args(current, "install", "--from", str(source)))
    assert rc == rb.EXIT_REFUSED_DRY_RUN
    out = capsys.readouterr().out
    for needle in (
        "INSTALL PLAN",
        "NOTHING has been changed",
        "HUMAN STEP",
        "Quit Mastermind OS",
        "install-tmp-",
        "mmos_installed_receipt.py",
        "Build details",
        REV_B,
        IDENT_B,
    ):
        assert needle in out, needle
    assert "INSTALL REFUSED" in out and "--execute" in out
    assert tree_hash(lane.apps) == apps_hash
    assert tree_hash(lane.archive) == archive_hash  # dry-run does not even snapshot


def test_install_dry_run_allowed_even_while_app_running(lane, capsys, monkeypatch):
    current = lane.install(REV_A, IDENT_A)
    source = _built_source(lane, REV_B, IDENT_B)
    exe = current / "Contents" / "MacOS" / "mastermind-os"
    monkeypatch.setattr(mr, "ps_snapshot", lambda: [(4242, str(exe))])
    apps_hash, archive_hash = tree_hash(lane.apps), tree_hash(lane.archive)
    rc = rb.main(lane.args(current, "install", "--from", str(source)))
    assert rc == rb.EXIT_REFUSED_DRY_RUN
    assert "INSTALL REFUSED" in capsys.readouterr().out
    assert tree_hash(lane.apps) == apps_hash
    assert tree_hash(lane.archive) == archive_hash


def test_install_refused_when_app_runs_from_current_bundle(lane, capsys, monkeypatch):
    current = lane.install(REV_A, IDENT_A)
    source = _built_source(lane, REV_B, IDENT_B)
    exe = current / "Contents" / "MacOS" / "mastermind-os"
    monkeypatch.setattr(mr, "ps_snapshot", lambda: [(4242, str(exe))])
    apps_hash, archive_hash = tree_hash(lane.apps), tree_hash(lane.archive)
    rc = rb.main(lane.args(current, "install", "--from", str(source), "--execute"))
    assert rc == rb.EXIT_REFUSED_RUNNING
    out = capsys.readouterr().out
    assert "HUMAN STEP" in out and "quit" in out.lower()
    assert tree_hash(lane.apps) == apps_hash
    assert tree_hash(lane.archive) == archive_hash


def test_install_refused_on_self_install(lane, capsys):
    current = lane.install(REV_A, IDENT_A)
    nested = current / "Contents" / "Nested.app"
    nested.mkdir()
    apps_hash = tree_hash(lane.apps)
    assert rb.main(lane.args(current, "install", "--from", str(current))) == rb.EXIT_ARGS
    assert rb.main(lane.args(current, "install", "--from", str(nested))) == rb.EXIT_ARGS
    capsys.readouterr()
    assert tree_hash(lane.apps) == apps_hash


def test_install_missing_or_non_app_source_is_args_error(lane, capsys):
    current = lane.install(REV_A, IDENT_A)
    assert rb.main(lane.args(current, "install", "--from",
                             str(lane.apps.parent / "ghost.app"))) == rb.EXIT_ARGS
    staging = lane.apps.parent / "not-an-app"
    staging.mkdir()
    assert rb.main(lane.args(current, "install", "--from", str(staging))) == rb.EXIT_ARGS
    capsys.readouterr()


def test_install_executes_snapshots_preserves_and_verifies(lane, capsys):
    current = lane.install(REV_A, IDENT_A)  # currently installed: A
    source = _built_source(lane, REV_B, IDENT_B)  # fresh build: B
    source_receipt = mr.observe_bundle(source)

    rc = rb.main(lane.args(current, "install", "--from", str(source), "--execute"))
    assert rc == rb.EXIT_OK
    out = capsys.readouterr().out
    assert source_receipt["receipt_digest"] in out
    assert "HUMAN" in out

    # Install location now carries the source bytes under the source digest.
    fresh = mr.observe_bundle(current)
    assert fresh["receipt_digest"] == source_receipt["receipt_digest"]
    assert fresh["source_revision"]["value"] == REV_B
    assert fresh["build_identity"]["value"] == IDENT_B

    # The previous bundle was snapshotted (digest-named rollback anchor)…
    snapshot_dir = _only_entry(lane.archive, f"{IDENT_A}-{REV_A[:12]}")
    assert (snapshot_dir / "receipt.digest").read_text().strip() \
        == mr.observe_bundle(snapshot_dir / "Mastermind OS.app")["receipt_digest"]
    # …and also preserved under install-tmp-<ts>.
    preserved = sorted(lane.archive.glob("install-tmp-*"))
    assert len(preserved) == 1
    old = mr.observe_bundle(preserved[0] / "Mastermind OS.app")
    assert old["source_revision"]["value"] == REV_A
    assert old["receipt_digest"] == (snapshot_dir / "receipt.digest").read_text().strip()

    # The source build output is untouched by the install.
    assert mr.observe_bundle(source)["receipt_digest"] == source_receipt["receipt_digest"]


def test_install_fresh_without_current_bundle(lane, capsys):
    target = lane.apps / "Mastermind OS.app"  # nothing installed yet
    source = _built_source(lane, REV_B, IDENT_B)
    rc = rb.main(lane.args(target, "install", "--from", str(source)))
    assert rc == rb.EXIT_REFUSED_DRY_RUN
    assert "fresh install" in capsys.readouterr().out

    rc = rb.main(lane.args(target, "install", "--from", str(source), "--execute"))
    assert rc == rb.EXIT_OK
    fresh = mr.observe_bundle(target)
    assert fresh["receipt_digest"] == mr.observe_bundle(source)["receipt_digest"]
    assert not list(lane.archive.glob("install-tmp-*"))  # nothing to preserve
    assert not list(lane.archive.iterdir())  # nothing was snapshotted either
