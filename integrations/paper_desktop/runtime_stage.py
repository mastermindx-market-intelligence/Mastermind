"""Stage an immutable-by-generation Paper bridge runtime for Studio Direct.

This installer owns only local Paper bridge runtime materialization. It never
starts/stops Studio Direct, changes provider apps, contacts Paper, or mutates an
existing runtime generation.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import venv

SCHEMA = "mastermind.paper_runtime.v1"
GENERATION_RE = re.compile(r"v[1-9][0-9]{0,3}")
PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
SOURCE_FILES = ("bridge.py",)
REVIEWED_GENERATIONS = {
    "v2": {
        "bridge.py": "83e36b0bcd0acabbf5dd6ace5b708e5797a52e7db732e8dbbf848ded781c231d",
    },
}


class Refusal(RuntimeError):
    pass


class RetryableRefusal(Refusal):
    """Definite pre-commit refusal that may be retried after state reconciliation."""


class EffectUnknown(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _runtime_root(root: Path | None = None) -> Path:
    if root is not None:
        target = root.absolute()
        anchor = target.parent
    else:
        anchor = Path.home().absolute()
        target = anchor / ".local" / "share" / "mastermind-paper" / "runtime"
    # Refuse user-controlled symlink components before creating or reading the
    # fixed runtime root. Test-only root injection uses its immediate parent as
    # the trust anchor; production checks every component below the real home.
    current = anchor
    try:
        info = current.lstat()
    except OSError as exc:
        raise Refusal("RUNTIME_ROOT_UNSAFE") from exc
    if stat.S_ISLNK(info.st_mode):
        raise Refusal("RUNTIME_ROOT_UNSAFE")
    try:
        relative = target.relative_to(anchor)
    except ValueError as exc:
        raise Refusal("RUNTIME_ROOT_UNSAFE") from exc
    for part in relative.parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise Refusal("RUNTIME_ROOT_UNSAFE")
    return target


def _require_private_dir(path: Path, *, create: bool = False) -> Path:
    if create:
        try:
            path.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=False)
        except FileExistsError:
            pass
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise Refusal("PRIVATE_DIRECTORY_REQUIRED")
    return path


def _read_source(source_dir: Path | None = None) -> dict[str, bytes]:
    source = source_dir if source_dir is not None else Path(__file__).resolve().parent
    files = {}
    for name in SOURCE_FILES:
        path = source / name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise Refusal("SOURCE_FILE_UNSAFE")
        files[name] = path.read_bytes()
    return files


def _expected_hashes(files: dict[str, bytes]) -> dict[str, str]:
    return {name: _sha256(data) for name, data in sorted(files.items())}


def _reviewed_hashes(generation: str) -> dict[str, str]:
    if not GENERATION_RE.fullmatch(generation):
        raise Refusal("GENERATION_INVALID")
    expected = REVIEWED_GENERATIONS.get(generation)
    if expected is None:
        raise Refusal("GENERATION_UNSUPPORTED")
    return dict(expected)


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, PRIVATE_FILE_MODE)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


@contextlib.contextmanager
def _stage_lock(root: Path):
    lock_path = root / ".stage.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, PRIVATE_FILE_MODE)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
            raise Refusal("UNSAFE_STAGE_LOCK")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refusal("RUNTIME_STAGE_BUSY") from exc
        yield
    finally:
        os.close(fd)


def _probe_bridge(target: Path) -> None:
    python = target / "venv" / "bin" / "python"
    bridge = target / "source" / "bridge.py"
    if not python.exists() or not bridge.is_file():
        raise Refusal("RUNTIME_INCOMPLETE")
    try:
        result = subprocess.run(
            [str(python), str(bridge), "--help"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
            env={"PATH": os.environ.get("PATH", ""), "HOME": str(Path.home())},
        )
    except subprocess.TimeoutExpired as exc:
        # This probe runs before the generation rename commit point. Python's
        # run(timeout=...) kills and waits for the probe child before raising,
        # so the target generation is definitely absent and a later caller may
        # retry only after reconciling that same target state.
        raise RetryableRefusal("BRIDGE_PROBE_TIMEOUT") from exc
    if result.returncode != 0:
        raise Refusal("BRIDGE_PROBE_FAILED")


def _receipt(target: Path) -> dict:
    path = target / "RUNTIME.json"
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise Refusal("RUNTIME_RECEIPT_UNSAFE")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise Refusal("RUNTIME_RECEIPT_INVALID") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise Refusal("RUNTIME_RECEIPT_INVALID")
    return value


def verify(generation: str, *, root: Path | None = None, _source_dir: Path | None = None) -> dict:
    expected = _reviewed_hashes(generation)
    root = _require_private_dir(_runtime_root(root))
    target = root / generation
    info = target.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise Refusal("RUNTIME_DIRECTORY_UNSAFE")
    receipt = _receipt(target)
    if (
        receipt.get("generation") != generation
        or receipt.get("source_sha256") != expected
        or receipt.get("bridge_sha256") != expected["bridge.py"]
        or receipt.get("network_install_performed") is not False
        or receipt.get("production_acceptance") is not False
    ):
        raise Refusal("GENERATION_COLLISION")
    source = target / "source"
    _require_private_dir(source)
    observed = {}
    for name, digest in expected.items():
        path = source / name
        file_info = path.lstat()
        if not stat.S_ISREG(file_info.st_mode) or file_info.st_uid != os.getuid() or file_info.st_mode & 0o077:
            raise Refusal("RUNTIME_SOURCE_UNSAFE")
        observed[name] = _sha256(path.read_bytes())
        if observed[name] != digest:
            raise Refusal("GENERATION_COLLISION")
    _probe_bridge(target)
    return {
        "state": "RUNTIME_VERIFIED",
        "schema": SCHEMA,
        "generation": generation,
        "path": str(target),
        "source_sha256": observed,
        "bridge_sha256": observed["bridge.py"],
        "python_path": str(target / "venv" / "bin" / "python"),
        "production_acceptance": False,
    }


def stage(generation: str, *, root: Path | None = None, _source_dir: Path | None = None) -> dict:
    reviewed = _reviewed_hashes(generation)
    root = _require_private_dir(_runtime_root(root), create=True)
    target = root / generation
    files = _read_source(_source_dir)
    hashes = _expected_hashes(files)
    if hashes != reviewed:
        raise Refusal("SOURCE_HASH_MISMATCH")
    with _stage_lock(root):
        if target.exists() or target.is_symlink():
            return {**verify(generation, root=root, _source_dir=_source_dir), "state": "RUNTIME_ALREADY_PRESENT"}
        tmp = Path(tempfile.mkdtemp(prefix=f".{generation}.stage-", dir=root))
        tmp.chmod(PRIVATE_DIR_MODE)
        try:
            source = tmp / "source"
            source.mkdir(mode=PRIVATE_DIR_MODE)
            for name, data in files.items():
                _write_private(source / name, data)
            # The Studio Direct bridge is dependency-free. Keep this runtime
            # bridge-only and offline; the optional local MCP server and SDK are
            # deliberately not projected into this production runtime.
            venv.EnvBuilder(with_pip=False, clear=False, symlinks=False, upgrade=False).create(tmp / "venv")
            _probe_bridge(tmp)
            receipt = {
                "schema": SCHEMA,
                "generation": generation,
                "source_sha256": hashes,
                "bridge_sha256": hashes["bridge.py"],
                "python_source": os.path.realpath(sys.executable),
                "python_version": platform.python_version(),
                "network_install_performed": False,
                "production_acceptance": False,
            }
            _write_private(tmp / "RUNTIME.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
            # Same-root rename makes the complete generation visible atomically.
            # After this commit point any failure is effect-ambiguous: the
            # generation may already be visible even if durable sync or final
            # verification cannot complete.
            committed = False
            try:
                os.rename(tmp, target)
                committed = True
                root_fd = os.open(root, os.O_RDONLY)
                try:
                    os.fsync(root_fd)
                finally:
                    os.close(root_fd)
                result = verify(generation, root=root, _source_dir=_source_dir)
            except (Refusal, OSError, subprocess.SubprocessError) as exc:
                if committed:
                    raise EffectUnknown("RUNTIME_EFFECT_UNKNOWN") from exc
                raise
        finally:
            if tmp.exists():
                shutil.rmtree(tmp)
        result["state"] = "RUNTIME_STAGED"
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["stage", "verify"])
    parser.add_argument("--generation", required=True)
    args = parser.parse_args()
    try:
        result = stage(args.generation) if args.action == "stage" else verify(args.generation)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except EffectUnknown:
        print(json.dumps({
            "state": "EFFECT_UNKNOWN",
            "retry_allowed": False,
            "generation": args.generation,
            "reconcile_action": "verify",
        }))
        return 3
    except RetryableRefusal as exc:
        print(json.dumps({
            "state": str(exc),
            "retry_allowed": True,
            "generation": args.generation,
            "reconcile_action": "verify",
        }))
        return 2
    except (Refusal, OSError, subprocess.SubprocessError) as exc:
        code = str(exc) if isinstance(exc, Refusal) else "LOCAL_FAILURE"
        print(json.dumps({"state": code, "retry_allowed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())