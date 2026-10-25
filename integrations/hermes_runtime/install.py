"""Install, upgrade, roll back, and uninstall the user-level Hermes runtime.

Nothing here contacts a host bus. `--fetch` is the only network path and it
refuses every revision except the pinned SHA. Tests use a local upstream tree.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .constants import INSTALL_SCHEMA, MANIFEST_SCHEMA, PINNED_UPSTREAM_SHA, UPSTREAM_REPOSITORY
from .errors import RuntimeRefusal
from .hermes_config import render_hermes_config, sha256_text
from .profile import (
    RuntimeProfile,
    assert_outside_repository,
    dump_profile,
    load_profile,
    profile_sha256,
    repo_root,
)
from .secrets import load_secrets
from .systemd_unit import assert_systemd_user_dir, render_user_unit

_UNSAFE = set(" \n\r\t\"'`$")


def pinned_fetch_commands(dest: Path) -> list[list[str]]:
    root = str(dest)
    if any(ch in root for ch in _UNSAFE):
        raise RuntimeRefusal("UNSAFE_PATH")
    return [
        ["git", "init", "--quiet", root],
        ["git", "-C", root, "remote", "add", "origin", UPSTREAM_REPOSITORY],
        ["git", "-C", root, "fetch", "--depth", "1", "origin", PINNED_UPSTREAM_SHA],
        ["git", "-C", root, "checkout", "--detach", "FETCH_HEAD"],
    ]


def assert_checkout_sha(source: Path) -> None:
    proc = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    head = (proc.stdout or "").strip()
    if proc.returncode != 0 or head != PINNED_UPSTREAM_SHA:
        raise RuntimeRefusal("CHECKOUT_SHA_MISMATCH")


def fetch_pinned_upstream(dest: Path) -> None:
    if dest.exists():
        raise RuntimeRefusal("FETCH_DEST_EXISTS")
    dest.mkdir(parents=True)
    try:
        for command in pinned_fetch_commands(dest):
            proc = subprocess.run(command, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                raise RuntimeRefusal("UPSTREAM_FETCH_FAILED")
        assert_checkout_sha(dest)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise


def install(
    *,
    profile_path: Path,
    state_dir: Path,
    systemd_user_dir: Path,
    secrets_file: Path,
    hermes_bin: Path,
    upstream_source: Path | None = None,
    fetch: bool = False,
    python_executable: str | None = None,
) -> dict:
    if fetch == bool(upstream_source):
        raise RuntimeRefusal("UPSTREAM_SOURCE_REQUIRED")
    profile = load_profile(profile_path, state_dir=state_dir, secrets_file=secrets_file)
    # Touch the secrets file for mode and ownership before creating state.
    load_secrets(profile.secrets_file)
    unit_dir = assert_systemd_user_dir(systemd_user_dir)
    assert_outside_repository(unit_dir, label="SYSTEMD_USER_DIR")
    bin_path = _hermes_bin(hermes_bin)
    if state_dir.exists():
        if state_dir.is_symlink() or not state_dir.is_dir():
            raise RuntimeRefusal("STATE_DIR_SYMLINK_REFUSED")
        if not (state_dir / "install-manifest.json").is_file():
            raise RuntimeRefusal("INSTALL_REFUSED_UNOWNED_STATE")
    else:
        state_dir.mkdir(mode=0o700)
        os.chmod(state_dir, 0o700)
    release_id = _allocate_release(state_dir)
    release = state_dir / "releases" / release_id
    release.mkdir(mode=0o700)
    previous = os.readlink(state_dir / "current") if (state_dir / "current").is_symlink() else None
    try:
        if fetch:
            fetch_pinned_upstream(release / "upstream")
            upstream_attested = True
        else:
            assert upstream_source is not None
            _copy_upstream(upstream_source, release / "upstream")
            upstream_attested = False
        _write_release(profile, release, bin_path, upstream_attested)
        _switch_current(state_dir, release_id)
        unit = _install_unit(profile, unit_dir, python_executable or sys.executable)
        _write_manifest(profile, unit_dir, unit)
    except Exception:
        shutil.rmtree(release, ignore_errors=True)
        _restore_current(state_dir, previous)
        releases = state_dir / "releases"
        if previous is None and releases.is_dir() and not any(releases.iterdir()):
            shutil.rmtree(state_dir, ignore_errors=True)
        raise
    return {
        "schema": INSTALL_SCHEMA,
        "status": "INSTALLED",
        "role": profile.role,
        "sha": profile.sha,
        "release": release_id,
        "service": profile.service_name,
        "unit": str(unit),
        "upstream_attested": upstream_attested,
        "secrets_recorded": False,
    }


def rollback(state_dir: Path) -> dict:
    link = state_dir / "current"
    if not link.is_symlink():
        raise RuntimeRefusal("ROLLBACK_UNAVAILABLE")
    target = os.readlink(link)
    if not target.startswith("releases/") or "/" in target[len("releases/"):]:
        raise RuntimeRefusal("CURRENT_LINK_NOT_RELATIVE")
    current = target[len("releases/"):]
    if not current.isdigit() or int(current) <= 1:
        raise RuntimeRefusal("ROLLBACK_UNAVAILABLE")
    previous = str(int(current) - 1)
    if not (state_dir / "releases" / previous).is_dir():
        raise RuntimeRefusal("ROLLBACK_UNAVAILABLE")
    _switch_current(state_dir, previous)
    manifest_path = state_dir / "install-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["current_release"] = previous
    _atomic_write(manifest_path, _json(manifest), 0o600)
    return {
        "schema": INSTALL_SCHEMA,
        "status": "ROLLED_BACK",
        "release": previous,
        "secrets_recorded": False,
    }


def uninstall(*, state_dir: Path, systemd_user_dir: Path) -> dict:
    if not state_dir.exists():
        return {"schema": INSTALL_SCHEMA, "status": "ABSENT", "secrets_recorded": False}
    if state_dir.is_symlink() or not state_dir.is_dir():
        raise RuntimeRefusal("STATE_DIR_SYMLINK_REFUSED")
    manifest_path = state_dir / "install-manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RuntimeRefusal("UNINSTALL_REFUSED_WITHOUT_MANIFEST")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("owns_state_dir") is not True:
        raise RuntimeRefusal("UNINSTALL_REFUSED_WITHOUT_MANIFEST")
    if Path(manifest["state_dir"]).resolve() != state_dir.resolve():
        raise RuntimeRefusal("STATE_DIR_MISMATCH")
    unit_dir = assert_systemd_user_dir(systemd_user_dir)
    if Path(manifest["systemd_user_dir"]).resolve() != unit_dir:
        raise RuntimeRefusal("SYSTEMD_DIR_MISMATCH")
    secrets_file = Path(manifest["secrets_file"])
    unit = Path(manifest["unit_path"])
    wants = Path(manifest["wants_path"])
    _remove_unit_file(unit, unit_dir)
    _remove_unit_file(wants, unit_dir)
    wants_dir = unit_dir / "default.target.wants"
    if wants_dir.is_dir() and not any(wants_dir.iterdir()):
        wants_dir.rmdir()
    shutil.rmtree(state_dir)
    return {
        "schema": INSTALL_SCHEMA,
        "status": "UNINSTALLED",
        "secrets_file_preserved": str(secrets_file),
        "secrets_recorded": False,
    }


def _hermes_bin(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise RuntimeRefusal("HERMES_BIN_NOT_EXECUTABLE")
    if any(ch in str(resolved) for ch in _UNSAFE):
        raise RuntimeRefusal("UNSAFE_PATH")
    return resolved


def _allocate_release(state: Path) -> str:
    releases = state / "releases"
    releases.mkdir(mode=0o700, exist_ok=True)
    counter = state / "next-release"
    if not counter.exists():
        nxt = 1
    else:
        raw = counter.read_text(encoding="utf-8").strip()
        if not raw.isdigit():
            raise RuntimeRefusal("RELEASE_COUNTER_CORRUPT")
        nxt = int(raw)
    _atomic_write(counter, f"{nxt + 1}\n".encode("ascii"), 0o600)
    return str(nxt)


def _copy_upstream(source: Path, dest: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise RuntimeRefusal("UPSTREAM_SOURCE_INVALID")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise RuntimeRefusal("UPSTREAM_SYMLINK_REFUSED")
    shutil.copytree(source, dest, symlinks=False)


def _write_release(profile: RuntimeProfile, release: Path, bin_path: Path, upstream_attested: bool) -> None:
    home = release / "hermes-home"
    role_dir = home / "profiles" / profile.role
    role_dir.mkdir(parents=True, mode=0o700)
    config = render_hermes_config(profile)
    _atomic_write(role_dir / "config.yaml", config.encode("utf-8"), 0o600)
    soul = _soul_bytes(profile.role)
    _atomic_write(role_dir / "SOUL.md", soul, 0o644)
    dumped = dump_profile(profile)
    _atomic_write(release / "profile.yaml", dumped.encode("utf-8"), 0o600)
    bin_dir = release / "bin"
    bin_dir.mkdir(mode=0o700)
    os.symlink(bin_path, bin_dir / "hermes")
    _atomic_write(release / "release-id", f"{release.name}\n".encode("ascii"), 0o600)
    receipt = {
        "schema": INSTALL_SCHEMA,
        "status": "RELEASE_WRITTEN",
        "sha": profile.sha,
        "role": profile.role,
        "allowlist": sorted(profile.tool_allowlist),
        "profile_sha256": profile_sha256(dumped),
        "hermes_config_sha256": sha256_text(config),
        "soul_sha256": hashlib_sha256(soul),
        "upstream_attested": upstream_attested,
        "secrets_recorded": False,
    }
    _atomic_write(release / "install-receipt.json", _json(receipt), 0o600)


def _soul_bytes(role: str) -> bytes:
    path = repo_root() / "integrations" / "hermes_qualification" / "profiles" / role / "SOUL.md"
    if path.is_symlink() or not path.is_file():
        raise RuntimeRefusal("ROLE_SOUL_MISSING")
    return path.read_bytes()


def _restore_current(state: Path, previous: str | None) -> None:
    link = state / "current"
    if previous is None:
        if link.is_symlink() or link.exists():
            link.unlink()
        return
    tmp = state / f".current-restore.{os.getpid()}"
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    os.symlink(previous, tmp)
    os.replace(tmp, link)


def _switch_current(state: Path, release_id: str) -> None:
    if not release_id.isdigit():
        raise RuntimeRefusal("RELEASE_ID_INVALID")
    tmp = state / f".current.{os.getpid()}"
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    os.symlink(f"releases/{release_id}", tmp)
    os.replace(tmp, state / "current")


def _install_unit(profile: RuntimeProfile, unit_dir: Path, python_executable: str) -> Path:
    unit_dir.mkdir(parents=True, exist_ok=True)
    text = render_user_unit(profile, python_executable=python_executable, repo_root=repo_root())
    unit = unit_dir / f"{profile.service_name}.service"
    _atomic_write(unit, text.encode("utf-8"), 0o644)
    wants_dir = unit_dir / "default.target.wants"
    wants_dir.mkdir(mode=0o755, exist_ok=True)
    wants = wants_dir / unit.name
    if wants.exists() or wants.is_symlink():
        wants.unlink()
    os.symlink(f"../{unit.name}", wants)
    return unit


def _write_manifest(profile: RuntimeProfile, unit_dir: Path, unit: Path) -> dict:
    current = os.readlink(profile.state_dir / "current")
    release = current.split("/", 1)[1]
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "owns_state_dir": True,
        "service_name": profile.service_name,
        "state_dir": str(profile.state_dir),
        "systemd_user_dir": str(unit_dir),
        "unit_path": str(unit),
        "wants_path": str(unit_dir / "default.target.wants" / unit.name),
        "secrets_file": str(profile.secrets_file),
        "current_release": release,
        "sha": profile.sha,
        "secrets_recorded": False,
    }
    _atomic_write(profile.state_dir / "install-manifest.json", _json(manifest), 0o600)
    return manifest


def _remove_unit_file(path: Path, unit_dir: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    resolved_parent = path.parent.resolve()
    if path.is_symlink():
        # Delete the symlink itself. Never follow it into another tree.
        if resolved_parent != unit_dir.resolve() and resolved_parent != (unit_dir / "default.target.wants").resolve():
            raise RuntimeRefusal("UNIT_PATH_ESCAPES")
        path.unlink()
        return
    try:
        path.resolve().relative_to(unit_dir.resolve())
    except ValueError:
        raise RuntimeRefusal("UNIT_PATH_ESCAPES") from None
    path.unlink()


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(tmp, flags, mode)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def _json(payload: dict) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def hashlib_sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()
