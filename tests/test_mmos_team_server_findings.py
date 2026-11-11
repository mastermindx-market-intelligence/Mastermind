"""Failing-test-first: the FIXED behaviour of tools/mmos_team_server/node_install.py.

These tests are written to the spec (RI-D findings F1-F8, F26 and item 12), not
to the current implementation. Against the current code most of them FAIL; that
is the intended outcome of this commit. Each test names the finding it pins.

No network, no launchd, no real port, no ~/.t3, no ~/.mastermind/t3-team*.
"""
import ast
import hashlib
import importlib.util
import inspect
import io
import json
import os
import re
import sqlite3
import subprocess
import tarfile
import textwrap
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent
# MMOS_NODE_INSTALL lets the driver point the suite at an exact revision of the
# module (e.g. a `git show HEAD:...` copy) while the working tree is mid-edit.
TOOL = Path(os.environ.get(
    "MMOS_NODE_INSTALL", REPO / "tools" / "mmos_team_server" / "node_install.py"))
PY = "/opt/homebrew/bin/python3.12"
LABEL = "com.mastermind.t3-team-dev-tsh"

_loader = importlib.util.spec_from_file_location("node_install_findings", TOOL)
node_install = importlib.util.module_from_spec(_loader)
_loader.loader.exec_module(node_install)

PREFIX = f"node-v{node_install.VERSION}-darwin-arm64"


# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------

@pytest.fixture
def inputs(tmp_path, monkeypatch):
    """A fake official archive + checksum, with OFFICIAL_SHA256 re-pinned.

    The archive carries a ~4 KB member so that a mid-stream byte flip lands in
    the deflate data (a zlib error -> tarfile.ReadError) rather than in the
    gzip header (BadGzipFile, which is an OSError and would be caught).
    """
    root = tmp_path / "server"
    root.mkdir(mode=0o700)
    archive = tmp_path / node_install.ARCHIVE
    checksum = tmp_path / "SHASUMS256.txt"
    with tarfile.open(archive, "w:gz") as tf:
        def file(name, body, mode=0o755):
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = mode
            tf.addfile(info, io.BytesIO(body))
        file(PREFIX + "/bin/node", b"never-executed-test-fixture\n")
        file(PREFIX + "/lib/node_modules/npm/package.json", b"{}")
        file(PREFIX + "/lib/node_modules/npm/README.md", b"x" * 4096)
        link = tarfile.TarInfo(PREFIX + "/bin/npm")
        link.type = tarfile.SYMTYPE
        link.linkname = node_install.ALLOWED_LINKS["npm"]
        tf.addfile(link)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n")
    monkeypatch.setattr(node_install, "OFFICIAL_SHA256", digest)
    return root, archive, checksum


SCHEMA = getattr(node_install, "SCHEMA_VERSION", 1)


def add_server_receipt(root):
    """A complete fake packed dist plus config/server-runtime.json."""
    build = root / "runtime" / "packed" / "dist"
    recorded = []
    for name in node_install.REQUIRED_DIST_FILES:
        target = build / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x")
        body = b"x"
        recorded.append({"path": name, "bytes": len(body),
                         "sha256": hashlib.sha256(body).hexdigest()})
    # Panel R1: digests beside dist/ + post-hash BUILD_RECEIPT inside it.
    (build / "BUILD_RECEIPT.json").write_text("{}\n")
    (root / "runtime" / "packed" / "file-digests.json").write_text(
        json.dumps(recorded))
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "server-runtime.json").write_text(json.dumps({
        "schemaVersion": SCHEMA,
        "serverBin": str(build / "bin.mjs"),
        "buildDir": str(build),
    }))
    return build


def _node_receipt(install_dir, node):
    return {
        "schemaVersion": SCHEMA,
        "kind": "official-nodejs-install",
        "version": "v" + node_install.VERSION,
        "architecture": "arm64",
        "platform": "darwin",
        "nodePath": str(node),
        "installDir": str(install_dir),
        "archiveSha256": node_install.OFFICIAL_SHA256,
        "treeSha256": node_install.tree_sha256(install_dir),
    }


def fake_runtime(tmp_path):
    """A root whose receipts are genuine-shaped (treeSha256 + in-tree receipt).

    Deliberately stronger than the helper of the same name in
    tests/test_mmos_team_server_runtime.py: the fixed runtime_paths requires an
    in-tree INSTALL_RECEIPT.json and a matching treeSha256, so a receipt
    without them would make the doctor tests pass for the wrong reason.
    """
    root = tmp_path / "server"
    root.mkdir(mode=0o700)
    install_dir = root / "runtime" / PREFIX
    (install_dir / "bin").mkdir(parents=True)
    node = install_dir / "bin" / "node"
    node.write_text("#!/bin/sh\n")
    node.chmod(0o700)
    receipt = _node_receipt(install_dir, node)
    payload = json.dumps(receipt, indent=2) + "\n"
    (install_dir / "INSTALL_RECEIPT.json").write_text(payload)
    build = add_server_receipt(root)
    (root / "config" / "node-runtime.json").write_text(payload)
    (root / "runtime" / "install-receipt.json").write_text(payload)
    return root, node, build


def real_install(inputs):
    """A genuine install_node() on the fixture archive, plus a server receipt."""
    root, archive, checksum = inputs
    node_install.install_node(str(root), str(archive), str(checksum))
    add_server_receipt(root)
    return root


def _doctor(root, capsys):
    """Run doctor with launchctl stubbed; fail cleanly if it raises."""
    try:
        with patch.object(node_install.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            code = node_install.doctor(str(root), LABEL)
    except BaseException as exc:  # noqa: BLE001 - the point of the test
        capsys.readouterr()
        pytest.fail(f"doctor raised {type(exc).__name__}: {exc}; "
                    "expected one 'doctor_error=' line and return 1")
    return code, capsys.readouterr()


def _assert_one_doctor_error(code, captured):
    combined = captured.out + captured.err
    assert "Traceback (most recent call last)" not in combined, combined
    errors = [line for line in combined.splitlines()
              if line.startswith("doctor_error=")]
    assert len(errors) == 1, combined
    assert code == 1, combined


# --------------------------------------------------------------------------
# F1 — a broken archive must end in one "team_runtime:" line, not a traceback
# --------------------------------------------------------------------------

def _break_archive(archive, checksum, monkeypatch, mode):
    raw = archive.read_bytes()
    if mode == "truncated":
        broken = raw[: len(raw) // 2]
    else:
        buf = bytearray(raw)
        start = int(len(buf) * 0.6)
        for index in range(start, min(start + 256, len(buf))):
            buf[index] ^= 0xFF
        broken = bytes(buf)
    archive.write_bytes(broken)
    digest = hashlib.sha256(broken).hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n")
    monkeypatch.setattr(node_install, "OFFICIAL_SHA256", digest)


def _run_main(argv):
    try:
        return node_install.main(argv), None
    except BaseException as exc:  # noqa: BLE001 - the point of the test
        return None, exc


@pytest.mark.parametrize("mode", ["truncated", "corrupt"])
def test_broken_archive_reports_one_team_runtime_line(inputs, capsys,
                                                      monkeypatch, mode):
    root, archive, checksum = inputs
    _break_archive(archive, checksum, monkeypatch, mode)
    code, exc = _run_main(["install", "--root", str(root),
                           "--archive", str(archive),
                           "--checksum", str(checksum)])
    captured = capsys.readouterr()
    if exc is not None:
        pytest.fail(f"main() raised {type(exc).__name__}: {exc}; expected "
                    "exit 1 with a single 'team_runtime:' line (F1)")
    combined = captured.out + captured.err
    assert "Traceback (most recent call last)" not in combined, combined
    lines = [line for line in combined.splitlines()
             if line.startswith("team_runtime:")]
    assert len(lines) == 1, combined
    assert code == 1, combined


# --------------------------------------------------------------------------
# F2 — doctor must report sqlite failures as one "doctor_error=" line
# --------------------------------------------------------------------------

LOCK_CHILD = """
import sqlite3, sys, time
db, marker = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(db, timeout=10, isolation_level=None)
conn.execute("BEGIN EXCLUSIVE")
open(marker, "w").close()
time.sleep(60)
"""


def _fresh_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE scratch(x)")
    conn.execute("DROP TABLE scratch")
    conn.commit()
    conn.close()


def _migrated_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE effect_sql_migrations(migration_id INTEGER)")
    conn.execute("INSERT INTO effect_sql_migrations VALUES (7)")
    conn.commit()
    conn.close()


@pytest.mark.parametrize("case", ["no-tables", "exclusive-lock", "corrupt"])
def test_doctor_reports_sqlite_failure_as_one_line(tmp_path, capsys, case):
    root, _, _ = fake_runtime(tmp_path)
    db = root / "home" / "userdata" / "statev2.sqlite"
    db.parent.mkdir(parents=True)
    proc = None
    try:
        if case == "no-tables":
            _fresh_db(db)
        elif case == "exclusive-lock":
            _migrated_db(db)
            marker = tmp_path / "locked"
            script = tmp_path / "lock_child.py"
            script.write_text(LOCK_CHILD)
            proc = subprocess.Popen([PY, "-I", str(script), str(db), str(marker)])
            deadline = time.time() + 10
            while not marker.exists() and time.time() < deadline:
                time.sleep(0.05)
            assert marker.exists(), "lock child never acquired BEGIN EXCLUSIVE"
        else:
            db.write_bytes(b"this is not a sqlite database\n" * 64)
        code, captured = _doctor(root, capsys)
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=10)
    _assert_one_doctor_error(code, captured)


# --------------------------------------------------------------------------
# F3 — a hung launchctl must be one "doctor_error=" line
# --------------------------------------------------------------------------

def test_doctor_reports_launchctl_timeout_as_one_line(tmp_path, capsys):
    root, _, _ = fake_runtime(tmp_path)
    try:
        with patch.object(node_install.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("launchctl", 10)):
            code = node_install.doctor(str(root), LABEL)
    except BaseException as exc:  # noqa: BLE001 - the point of the test
        capsys.readouterr()
        pytest.fail(f"doctor raised {type(exc).__name__}: {exc}; expected one "
                    "'doctor_error=' line and return 1 (F3)")
    _assert_one_doctor_error(code, capsys.readouterr())


# --------------------------------------------------------------------------
# F4 — a conflicting activation receipt must refuse BEFORE publishing
# --------------------------------------------------------------------------

def test_conflicting_activation_receipt_publishes_nothing(inputs):
    root, archive, checksum = inputs
    runtime = root / "runtime"
    runtime.mkdir(mode=0o700)
    planted = runtime / "install-receipt.json"
    planted.write_text(json.dumps({"schemaVersion": 1, "kind": "foreign"}) + "\n")
    planted.chmod(0o600)

    with pytest.raises(node_install.InstallError, match="receipt"):
        node_install.install_node(str(root), str(archive), str(checksum))

    # F4: the refusal must publish nothing — no tree, no activation marker.
    assert list(root.glob("runtime/node-v*")) == [], \
        "install published a runtime tree before refusing (F4)"
    assert not (root / "config" / "node-runtime.json").exists(), \
        "install wrote an activation marker before refusing (F4)"


# --------------------------------------------------------------------------
# F5 / F6 — leftovers from a killed install must not block the retry
# --------------------------------------------------------------------------

def test_leftover_staging_directory_does_not_block_install(inputs, capsys):
    root, archive, checksum = inputs
    dead = root / "runtime" / "staging" / ".node-install-dead"
    dead.mkdir(parents=True, mode=0o700)
    for path in (root / "runtime", root / "runtime" / "staging"):
        path.chmod(0o700)

    node_install.install_node(str(root), str(archive), str(checksum))

    assert "NODE_INSTALLED" in capsys.readouterr().out
    assert list((root / "runtime" / "staging").iterdir()) == [], \
        "staging was not cleaned after a successful retry (F5)"


def test_leftover_activation_temp_does_not_block_install(inputs, capsys):
    root, archive, checksum = inputs
    config = root / "config"
    config.mkdir(mode=0o700)
    (config / "node-runtime.json.tmp").write_text("")

    node_install.install_node(str(root), str(archive), str(checksum))

    assert "NODE_INSTALLED" in capsys.readouterr().out
    assert not (config / "node-runtime.json.tmp").exists(), \
        "the stale activation temp was not removed under the install lock (F6)"


# --------------------------------------------------------------------------
# F7 — a planted change in the published tree must be refused on retry
# --------------------------------------------------------------------------

def _plant(root, kind):
    lib = root / "runtime" / PREFIX / "lib"
    if kind == "symlinked-dir":
        (lib / "planted").symlink_to("/etc", target_is_directory=True)
    elif kind == "empty-dir":
        (lib / "emptydir").mkdir()
    else:
        (lib / "extra.txt").write_text("planted\n")


@pytest.mark.parametrize("kind", ["symlinked-dir", "empty-dir", "extra-file"])
def test_planted_tree_change_is_refused(inputs, kind):
    root = real_install(inputs)
    _plant(root, kind)
    with pytest.raises(node_install.InstallError,
                       match="tree no longer matches|fresh extraction"):
        node_install.install_node(str(root), str(inputs[1]), str(inputs[2]))


def test_old_receipt_format_requires_reinstall(inputs):
    """A schemaVersion-1 receipt in the OLD shape (no treeSha256) must be
    refused by resolve with a message that tells the operator to reinstall."""
    root = real_install(inputs)
    config = root / "config" / "node-runtime.json"
    old = json.loads(config.read_text())
    # Mimic the OLD receipt format exactly: schemaVersion 1 and no treeSha256.
    old["schemaVersion"] = 1
    old.pop("treeSha256", None)
    payload = json.dumps(old, indent=2) + "\n"
    config.write_text(payload)
    (root / "runtime" / "install-receipt.json").write_text(payload)

    with pytest.raises(node_install.InstallError, match="reinstall"):
        node_install.resolve_command(str(root), "node")


# --------------------------------------------------------------------------
# F8 — a FIFO in the published tree must refuse promptly, never hang
# --------------------------------------------------------------------------

FIFO_CHILD = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("ni", sys.argv[1])
ni = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ni)
root, archive, checksum = sys.argv[2:5]
digest = open(checksum, encoding="utf-8").read().split()[0]
ni.OFFICIAL_SHA256 = digest
try:
    ni.install_node(root, archive, checksum)
except ni.InstallError as exc:
    print("REFUSED:", exc)
    sys.exit(0)
except BaseException as exc:
    print("OTHER:", type(exc).__name__, exc)
    sys.exit(2)
print("INSTALLED")
sys.exit(3)
"""


def test_fifo_in_published_tree_refuses_promptly(inputs, tmp_path):
    root = real_install(inputs)
    fifo = root / "runtime" / PREFIX / "lib" / "planted-fifo"
    fifo.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(fifo)

    script = tmp_path / "fifo_child.py"
    script.write_text(FIFO_CHILD)
    try:
        result = subprocess.run(
            [PY, "-I", str(script), str(TOOL), str(root),
             str(inputs[1]), str(inputs[2])],
            capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        pytest.fail("install_node hung on a FIFO in the published tree (F8)")

    assert result.returncode == 0, (
        f"expected a prompt InstallError refusal, got rc={result.returncode}: "
        f"{result.stdout}{result.stderr}")
    assert "REFUSED" in result.stdout, result.stdout


# --------------------------------------------------------------------------
# F26 — doctor must never print the pairing token
# --------------------------------------------------------------------------

SENTINEL = "PAIRTOKEN-SENSITIVE-123"


def test_doctor_never_prints_pairing_token(tmp_path, capsys):
    root, _, _ = fake_runtime(tmp_path)
    run = root / "run"
    run.mkdir()
    access = run / "access.txt"
    access.write_text(f"Connection string: {SENTINEL}\n")
    access.chmod(0o600)

    code, captured = _doctor(root, capsys)
    combined = captured.out + captured.err
    assert SENTINEL not in combined, "doctor printed the pairing token (F26)"
    assert "pairingFileAgeSeconds=" in combined, combined
    assert code in (0, 1)


def test_doctor_source_never_reads_access_file():
    """Non-vacuous compile check: no open()/read() call in doctor's source
    takes an argument that names the access file."""
    source = textwrap.dedent(inspect.getsource(node_install.doctor))
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        else:
            continue
        if name not in ("open", "read", "read_text", "read_bytes"):
            continue
        arguments = list(node.args) + [kw.value for kw in node.keywords]
        for argument in arguments:
            for sub in ast.walk(argument):
                if isinstance(sub, ast.Name) and "access" in sub.id:
                    offenders.append(ast.dump(node))
    assert not offenders, f"doctor reads the access file: {offenders}"


# --------------------------------------------------------------------------
# item 12 — runtime_paths must pin installDir and verify the in-tree receipt
# --------------------------------------------------------------------------

def test_runtime_paths_rejects_foreign_install_dir(inputs):
    root = real_install(inputs)
    other = root / "runtime" / "other"
    (other / "bin").mkdir(parents=True)
    node = other / "bin" / "node"
    node.write_text("#!/bin/sh\n")
    node.chmod(0o700)
    config = root / "config" / "node-runtime.json"
    receipt = json.loads(config.read_text())
    receipt["installDir"] = str(other)
    receipt["nodePath"] = str(node)
    config.write_text(json.dumps(receipt, indent=2) + "\n")

    with pytest.raises(node_install.InstallError):
        node_install.runtime_paths(str(root))


def test_runtime_paths_requires_in_tree_receipt(inputs):
    root = real_install(inputs)
    (root / "runtime" / PREFIX / "INSTALL_RECEIPT.json").unlink()
    with pytest.raises(node_install.InstallError):
        node_install.runtime_paths(str(root))


def test_runtime_paths_rejects_tree_digest_mismatch(inputs):
    root = real_install(inputs)
    config = root / "config" / "node-runtime.json"
    receipt = json.loads(config.read_text())
    receipt["treeSha256"] = "0" * 64
    config.write_text(json.dumps(receipt, indent=2) + "\n")
    with pytest.raises(node_install.InstallError):
        node_install.runtime_paths(str(root))


def test_runtime_paths_rejects_symlinked_node(inputs):
    root = real_install(inputs)
    node = root / "runtime" / PREFIX / "bin" / "node"
    elsewhere = root / "runtime" / PREFIX / "bin" / "node-real"
    node.rename(elsewhere)
    node.symlink_to(elsewhere)
    with pytest.raises(node_install.InstallError, match="must not be a symlink"):
        node_install.runtime_paths(str(root))


def test_runtime_paths_rejects_node_outside_install_dir(inputs):
    root = real_install(inputs)
    other = root / "runtime" / PREFIX / "bin" / "node2"
    other.write_text("#!/bin/sh\n")
    other.chmod(0o700)
    config = root / "config" / "node-runtime.json"
    receipt = json.loads(config.read_text())
    receipt["nodePath"] = str(other)
    config.write_text(json.dumps(receipt, indent=2) + "\n")
    with pytest.raises(node_install.InstallError,
                       match="nodePath must be installDir/bin/node|"
                             "does not resolve to installDir/bin/node"):
        node_install.runtime_paths(str(root))


# --------------------------------------------------------------------------
# item 11 — the pinned constants must match the real official release
# --------------------------------------------------------------------------

def test_pinned_constants_match_the_official_release():
    assert node_install.ARCHIVE == f"node-v{node_install.VERSION}-darwin-arm64.tar.gz"
    assert re.fullmatch(r"\d+\.\d+\.\d+", node_install.VERSION)
    assert re.fullmatch(r"[0-9a-f]{64}", node_install.OFFICIAL_SHA256)

    shasums = (Path.home() / ".mastermind" / "mmos_dev" / "tsh" / "downloads"
               / f"SHASUMS256-v{node_install.VERSION}.txt")
    if not shasums.is_file():
        pytest.skip(f"official SHASUMS not present: {shasums}")
    recorded = [line.split("  ", 1)[0] for line in shasums.read_text().splitlines()
                if line.endswith("  " + node_install.ARCHIVE)]
    assert recorded == [node_install.OFFICIAL_SHA256]
