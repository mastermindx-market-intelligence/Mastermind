"""Immutable, hash-locked Company stdio runtime; no Runtime or scheduler here."""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

SOURCE = Path(__file__).absolute().parents[2]
SYSTEM = Path("/Library/Application Support/MastermindExecutive")
CONFIG = SYSTEM / "config/company-consultation-edge.json"
CONTROL = SYSTEM / "config/control.json"
BASE_RECEIPT = SYSTEM / "python-runtime.json"
BASE_PYTHON = Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12")
SOCKET = "/var/run/mastermind-executive/company-consultation.sock"
RECEIPT = ".company-mcp-runtime.json"
INCOMPLETE = ".incomplete"
LOCK_RELATIVE = "requirements/executive-mcp-macos-arm64-py312.lock"
SCHEMA = "mastermind.company_mcp_edge/v1"
CONFIG_KEYS = {"schema", "release_sha", "control_uid", "worker_uid", "entry_sha256", "receipt_sha256"}
ENV = {"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"}
# -B is explicit in every child: isolated mode ignores PYTHONDONTWRITEBYTECODE.
PIP_BOOTSTRAP = ("import os,runpy,sys; os.environ['PIP_CONFIG_FILE']=os.devnull; "
                 "sys.path.insert(0,sys.argv.pop(1)); "
                 "runpy.run_module('pip',run_name='__main__')")


class EdgeError(RuntimeError):
    pass


def digest(path):
    with Path(path).open("rb") as stream:
        result = hashlib.file_digest(stream, "sha256")
    return result.hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _security():
    if str(SOURCE) not in sys.path:
        sys.path.insert(0, str(SOURCE))
    from control_plane.fs_security import has_macos_acl
    return has_macos_acl


def sealed(path, *, directory=False, wheel=True):
    """Direct root-owned chain; ACLs and writable ancestors are not trusted."""
    path = Path(path)
    if not path.is_absolute():
        raise EdgeError("edge path must be absolute")
    acl = _security()
    for node in (path, *path.parents):
        info = node.lstat()
        is_dir = directory or node != path
        if (info.st_uid != 0 or (wheel and (node == path or node == SYSTEM or SYSTEM in node.parents) and info.st_gid != 0)
                or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode)
                or not (stat.S_ISDIR(info.st_mode) if is_dir else stat.S_ISREG(info.st_mode))
                or (not is_dir and info.st_nlink != 1)
                or acl(node, expected_identity=info)):
            raise EdgeError("edge path custody differs")
    return path


def read_config():
    sealed(CONFIG)
    if stat.S_IMODE(CONFIG.stat().st_mode) != 0o444:
        raise EdgeError("edge config mode differs")
    raw = json.loads(CONFIG.read_bytes())
    if (type(raw) is not dict or set(raw) != CONFIG_KEYS or raw["schema"] != SCHEMA
            or type(raw["release_sha"]) is not str
            or re.fullmatch("[0-9a-f]{40}", raw["release_sha"]) is None
            or any(type(raw[k]) is not int or raw[k] <= 0 for k in ("control_uid", "worker_uid"))
            or raw["control_uid"] == raw["worker_uid"]
            or any(type(raw[k]) is not str or re.fullmatch("[0-9a-f]{64}", raw[k]) is None
                   for k in ("entry_sha256", "receipt_sha256"))):
        raise EdgeError("edge config differs")
    return raw


def source_evidence():
    if SOURCE.parent != SYSTEM / "releases" or re.fullmatch("[0-9a-f]{40}", SOURCE.name) is None:
        raise EdgeError("edge requires an exact installed release")
    sealed(SOURCE, directory=True)
    from ops.executive_os import release_manifest
    manifest = SOURCE / release_manifest.MANIFEST_NAME
    sealed(manifest)
    identity = json.loads(manifest.read_bytes())
    release_manifest.verify(SOURCE, SOURCE.name, identity["tree_sha"])
    lock = SOURCE / LOCK_RELATIVE
    return dict(release_sha=SOURCE.name, tree_sha=identity["tree_sha"],
                source_manifest_sha256=digest(manifest), lock_sha256=digest(lock))


def inventory(root):
    """Closed immutable wheel tree; relative in-tree interpreter links only."""
    root = sealed(root, directory=True)
    if stat.S_IMODE(root.stat().st_mode) != 0o555:
        raise EdgeError("SDK runtime root must be immutable")
    result = []
    acl = _security()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative in {RECEIPT, INCOMPLETE}:
            continue
        info = path.lstat()
        if (path.suffix in {".pth", ".pyc", ".pyo"}
                or path.name in {"sitecustomize.py", "usercustomize.py", "__pycache__"}):
            raise EdgeError("SDK tree contains startup code or bytecode")
        if (info.st_uid != 0 or info.st_gid != 0 or (not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o222)
                or acl(path, expected_identity=info, allow_symlink=stat.S_ISLNK(info.st_mode))):
            raise EdgeError("SDK tree custody differs")
        entry = dict(path=relative, mode=stat.S_IMODE(info.st_mode))
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            if relative not in {"bin/python", "bin/python3"} or target != "python3.12":
                raise EdgeError("SDK tree symlink differs")
            entry.update(type="symlink", target=target)
        elif stat.S_ISDIR(info.st_mode):
            entry.update(type="directory")
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            entry.update(type="file", size=info.st_size, sha256=digest(path))
        else:
            raise EdgeError("SDK tree contains unsupported object")
        result.append(entry)
    return result


def run(command):
    return subprocess.run([str(v) for v in command], check=True, env=ENV)


def verify_base(base):
    keys = {"runtime_root", "python_binary", "python_binary_sha256",
            "python_framework_sha256", "python_version", "team_identifier"}
    if type(base) is not dict or set(base) != keys or base["python_binary"] != str(BASE_PYTHON):
        raise EdgeError("base Python attestation differs")
    if base["runtime_root"] != str(BASE_PYTHON.parents[1]):
        raise EdgeError("base Python root differs")
    for path, key in ((BASE_PYTHON, "python_binary_sha256"),
                      (BASE_PYTHON.parents[1] / "Python", "python_framework_sha256")):
        sealed(path)
        if digest(path) != base[key]:
            raise EdgeError("base Python bytes differ")
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", base["runtime_root"]])


def verify(config=None):
    config = read_config() if config is None else config
    source = source_evidence()
    if config["release_sha"] != SOURCE.name or config["entry_sha256"] != digest(Path(__file__)):
        raise EdgeError("edge release binding differs")
    root = SYSTEM / "mcp-runtimes" / SOURCE.name
    sealed(root, directory=True)
    if (root / INCOMPLETE).exists() or (root / INCOMPLETE).is_symlink():
        raise EdgeError("SDK runtime is incomplete")
    receipt = root / RECEIPT
    sealed(receipt)
    if stat.S_IMODE(receipt.stat().st_mode) != 0o444 or digest(receipt) != config["receipt_sha256"]:
        raise EdgeError("SDK receipt differs")
    raw = json.loads(receipt.read_bytes())
    expected_keys = {"schema", "source", "base", "control_uid", "worker_uid",
                     "inventory_sha256", "inventory_entries", "pip_check_passed"}
    if (type(raw) is not dict or set(raw) != expected_keys or raw["schema"] != SCHEMA
            or raw["source"] != source or raw["pip_check_passed"] is not True
            or any(raw[k] != config[k] for k in ("control_uid", "worker_uid"))):
        raise EdgeError("SDK receipt binding differs")
    verify_base(raw["base"])
    entries = inventory(root)
    if (raw["inventory_sha256"] != hashlib.sha256(encoded(entries)).hexdigest()
            or type(raw["inventory_entries"]) is not int or raw["inventory_entries"] != len(entries)):
        raise EdgeError("SDK runtime tree differs")
    return root, raw


def publish(path, value):
    """New publication only. Existing or ambiguous state is preserved."""
    if path.exists() or path.is_symlink():
        raise EdgeError("edge publication already exists")
    fd, temporary = tempfile.mkstemp(prefix=".company-edge-", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded(value)); stream.flush()
            os.fchmod(stream.fileno(), 0o444)
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        temporary.unlink()
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _config_for(root, control):
    return dict(schema=SCHEMA, release_sha=SOURCE.name,
                control_uid=control["control_uid"], worker_uid=control["worker_uid"],
                receipt_sha256=digest(root / RECEIPT), entry_sha256=digest(Path(__file__)))


def _archive_incomplete(root):
    # Caller owns the single provision lock; there is no published launcher
    # binding and Company intake is disabled. Never delete partial evidence.
    sealed(root, directory=True)
    marker = root / INCOMPLETE
    if marker.exists() or marker.is_symlink():
        sealed(marker)
    elif stat.S_IMODE(root.stat().st_mode) != 0o700 or any(root.iterdir()):
        raise EdgeError("SDK recovery requires a marker or exact empty pre-marker root")
    archive = SYSTEM / "mcp-runtime-archive"
    if not archive.exists():
        archive.mkdir(mode=0o700)
    sealed(archive, directory=True)
    target = archive / (SOURCE.name + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                        + "-" + uuid4().hex)
    if target.exists() or target.is_symlink():
        raise EdgeError("SDK recovery target exists")
    before = root.lstat()
    if (root.lstat().st_dev, root.lstat().st_ino) != (before.st_dev, before.st_ino):
        raise EdgeError("SDK recovery source changed")
    root.rename(target)
    fsync_directory(root.parent)
    fsync_directory(archive)
    print(json.dumps({"schema": SCHEMA, "recovery": "ARCHIVED_INCOMPLETE",
                      "release_sha": SOURCE.name, "archive": str(target)}, sort_keys=True))


def provision(*, recover_incomplete=False):
    prior_umask = os.umask(0o077)
    try:
        return _provision(recover_incomplete=recover_incomplete)
    finally:
        os.umask(prior_umask)


def _provision(*, recover_incomplete=False):
    if os.geteuid() != 0 or sys.platform != "darwin":
        raise EdgeError("SDK provisioner requires root on macOS")
    source = source_evidence()
    # The existing provisioner owns all signed interpreter pins.
    run(["/bin/bash", SOURCE / "ops/executive_os/provision-python-runtime.sh", "--verify-only"])
    from scripts.executive_os_phase1c import load_control_config
    control = load_control_config(CONTROL, enforce_current_uid=False)
    if control["proof_base_sha"] != SOURCE.name:
        raise EdgeError("SDK release differs from installed control")
    if control.get("company_consultation", {}).get("armed", False):
        raise EdgeError("SDK provisioning requires Company intake disabled")
    parent = SYSTEM / "mcp-runtimes"
    if not parent.exists():
        parent.mkdir(mode=0o755)
        parent.chmod(0o755)
    sealed(parent, directory=True)
    if stat.S_IMODE(parent.stat().st_mode) != 0o755:
        raise EdgeError("SDK parent traversal mode differs")
    lock = parent / ".provision.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise EdgeError("SDK provision lock differs")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if CONFIG.exists() or CONFIG.is_symlink():
            if recover_incomplete:
                raise EdgeError("SDK recovery refuses a published binding")
            verify()
            return
        root = parent / SOURCE.name
        if recover_incomplete:
            _archive_incomplete(root)
            return
        if root.exists() or root.is_symlink():
            # Only a fully sealed complete receipt can recover missing config.
            # A failed build retains its marker for the explicit archive owner.
            config = _config_for(root, control)
            verify(config)
            publish(CONFIG, config)
            return
        root.mkdir(mode=0o700)
        marker_fd = os.open(root / INCOMPLETE,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(marker_fd, 0o600)
            with os.fdopen(marker_fd, "wb", closefd=False) as marker:
                marker.write(b"build in progress\n")
                marker.flush()
                os.fsync(marker.fileno())
        finally:
            os.close(marker_fd)
        fsync_directory(root)
        fsync_directory(parent)
        run([BASE_PYTHON, "-I", "-S", "-B", "-m", "venv", "--copies", "--without-pip", root])
        wheels = list((BASE_PYTHON.parents[1] / "lib/python3.12/ensurepip/_bundled").glob("pip-*.whl"))
        if len(wheels) != 1:
            raise EdgeError("attested bundled pip wheel differs")
        python = root / "bin/python3.12"
        pip = [python, "-I", "-B", "-c", PIP_BOOTSTRAP, wheels[0], "--isolated",
               "--disable-pip-version-check", "--no-input", "--no-cache-dir"]
        run([*pip, "install", "--no-compile", "--require-hashes", "--only-binary=:all:",
             "--index-url", "https://pypi.org/simple", "-r", SOURCE / LOCK_RELATIVE])
        run([*pip, "check"])
        base_raw = json.loads(BASE_RECEIPT.read_bytes())
        base = {k: base_raw[k] for k in ("runtime_root", "python_binary", "python_binary_sha256",
            "python_framework_sha256", "python_version", "team_identifier")}
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                continue
            path.chmod(0o555 if path.is_dir() or path.stat().st_mode & 0o111 else 0o444)
            if path.is_file():
                with path.open("rb") as frozen_file:
                    os.fsync(frozen_file.fileno())
        for directory in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
            fsync_directory(directory)
        root.chmod(0o555)
        fsync_directory(root)
        entries = inventory(root)
        raw = dict(schema=SCHEMA, source=source, base=base,
                   control_uid=control["control_uid"], worker_uid=control["worker_uid"],
                   inventory_sha256=hashlib.sha256(encoded(entries)).hexdigest(),
                   inventory_entries=len(entries), pip_check_passed=True)
        publish(root / RECEIPT, raw)
        # Marker removal is the only completion transition, after receipt durability.
        (root / INCOMPLETE).unlink()
        fsync_directory(root)
        config = _config_for(root, control)
        verify(config)
        publish(CONFIG, config)
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("provision", "recover-incomplete", "verify", "stdio", "sdk-stdio"))
    args = parser.parse_args(argv)
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise EdgeError("edge requires isolated Python without bytecode")
    if args.command in {"provision", "recover-incomplete"}:
        provision(recover_incomplete=args.command == "recover-incomplete")
        return 0
    config = read_config()
    root, _ = verify(config)
    if args.command == "verify":
        return 0
    if os.geteuid() != config["worker_uid"]:
        raise EdgeError("Company stdio requires the installed worker UID")
    python = root / "bin/python3.12"
    if args.command == "stdio":
        os.execve(python, [str(python), "-I", "-B", str(Path(__file__)), "sdk-stdio"], ENV)
    if (Path(sys.executable).absolute() != python or Path(sys.prefix) != root
            or Path(sys.base_prefix) != BASE_PYTHON.parents[1]):
        raise EdgeError("Company SDK interpreter differs")
    from integrations.company_consultation_host_transport import run_company_consultation_stdio
    asyncio.run(run_company_consultation_stdio(socket_path=SOCKET, server_uid=config["control_uid"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
