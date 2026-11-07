"""Install, upgrade, roll back, and uninstall the user-level Hermes runtime.

Nothing here contacts a host bus. `--fetch` is the only network path and it
refuses every revision except the pinned SHA. Tests use a local upstream tree.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import ExitStack
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


def assert_checkout_sha(source: Path, *, native_environment: dict | None = None) -> None:
    proc = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        **({"env": native_environment} if native_environment is not None else {}),
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
    hermes_config_renderer: Callable[[RuntimeProfile], str] | None = None,
    native_installation: dict | None = None,
) -> dict:
    if fetch == bool(upstream_source):
        raise RuntimeRefusal("UPSTREAM_SOURCE_REQUIRED")
    profile = load_profile(profile_path, state_dir=state_dir, secrets_file=secrets_file)
    native = None
    if profile.gateway_backend == "native-session-authority":
        from ops.executive_os.release_manifest import _hermes_native_gateway, ReleaseManifestError
        try:
            native = _hermes_native_gateway(native_installation, role=profile.role)
        except (ReleaseManifestError, TypeError, ValueError):
            raise RuntimeRefusal("NATIVE_INSTALLATION_REQUIRED") from None
        if native.get("evaluation_inputs") is not None and (
                native.get("primary_application") is not None
                or profile.model_provider == "mastermind-fabric"):
            raise RuntimeRefusal("NATIVE_EVAL_INPUTS_UNQUALIFIED")
        if (fetch or upstream_source is None
                or upstream_source.resolve() != Path(native["vendor_root"])):
            raise RuntimeRefusal("NATIVE_VENDOR_SELECTION_MISMATCH")
    elif native_installation is not None:
        raise RuntimeRefusal("NATIVE_INSTALLATION_NOT_SELECTED")
    _assert_secrets_outside_state(profile.secrets_file, state_dir)
    # Touch the secrets file for mode and ownership before creating state.
    load_secrets(profile.secrets_file)
    unit_dir = assert_systemd_user_dir(systemd_user_dir)
    assert_outside_repository(unit_dir, label="SYSTEMD_USER_DIR")
    bin_path = (repo_root() / "integrations/hermes_runtime/native/hermes"
                if native is not None else _hermes_bin(hermes_bin))
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
    source_lifetime = ExitStack()
    derivation = None
    derivation_check = None
    try:
        if native is not None:
            vendor = Path(native["vendor_root"])
            from .native_gateway_entry import native_git_environment
            git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
            git_env.update(native_git_environment(vendor))
            assert_checkout_sha(vendor, native_environment=git_env)
            if "vendor_derivation" in native:
                derivation, derivation_check = _qualify_native_derivation(native, profile, source_lifetime)
            else:
                clean = subprocess.run(["git", "-C", str(vendor), "status", "--porcelain=v1",
                                        "--untracked-files=all"], env=git_env, capture_output=True,
                                       check=False, timeout=30)
                if clean.returncode or clean.stdout:
                    raise RuntimeRefusal("NATIVE_VENDOR_CHECKOUT_DIRTY")
            os.symlink(vendor, release / "upstream")
            upstream_attested = True
        elif fetch:
            fetch_pinned_upstream(release / "upstream")
            upstream_attested = True
        else:
            assert upstream_source is not None
            _copy_upstream(upstream_source, release / "upstream")
            upstream_attested = False
        _write_release(profile, release, bin_path, upstream_attested, hermes_config_renderer,
                       native_installation=native, native_derivation=derivation)
        if derivation_check is not None:
            derivation_check()
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
    finally:
        source_lifetime.close()
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


def _qualify_native_derivation(native: dict, profile: RuntimeProfile, lifetime: ExitStack):
    """The existing held release/inventory, not a generic dirty-checkout escape."""
    from ops.executive_os.release_manifest import _HeldReleaseSources, _linux_source_acl
    from ops.executive_os.native_gateway_sources import NativeSourceClosure, verify_vendor_derivation
    owner = _HeldReleaseSources(repo_root())
    lifetime.callback(owner.close)
    installation = owner.hermes_runtime_input()
    selected = [row for row in (installation or {}).get("roles", [])
                if row["role"] == profile.role and row["state_dir"] == str(profile.state_dir)]
    if len(selected) != 1 or selected[0].get("native_gateway") != native:
        raise RuntimeRefusal("NATIVE_DERIVATION_RECIPE_MISMATCH")
    closure = NativeSourceClosure(owner, native, _linux_source_acl)
    lifetime.callback(closure.close)
    receipt = verify_vendor_derivation(owner, native, _linux_source_acl)
    def check():
        closure.check()
        owner.check()
    check()
    return receipt, check


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
    _qualify_native_rollback(state_dir / "releases" / current,
                             state_dir / "releases" / previous)
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


def _qualify_native_rollback(current: Path, previous: Path) -> None:
    """A role symlink cannot restore a different held release/unit recipe."""
    current_receipt = json.loads((current / "install-receipt.json").read_text(encoding="utf-8"))
    previous_receipt = json.loads((previous / "install-receipt.json").read_text(encoding="utf-8"))
    if "native_gateway" not in current_receipt and "native_gateway" not in previous_receipt:
        return
    fields = ("native_gateway", "native_vendor_derivation", "native_launcher_sha256",
              "native_adapter_sha256", "profile_sha256")
    if (any(current_receipt.get(key) != previous_receipt.get(key) for key in fields)
            or (current / "bin/hermes").resolve(strict=True)
               != (previous / "bin/hermes").resolve(strict=True)):
        raise RuntimeRefusal("NATIVE_ROLLBACK_REQUIRES_MATCHING_RELEASE_RECIPE")


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


def _assert_secrets_outside_state(secrets_file: Path, state_dir: Path) -> None:
    secret = secrets_file.expanduser().resolve()
    state = state_dir.expanduser().resolve()
    if secret == state:
        raise RuntimeRefusal("SECRETS_INSIDE_STATE_DIR")
    try:
        secret.relative_to(state)
    except ValueError:
        return
    raise RuntimeRefusal("SECRETS_INSIDE_STATE_DIR")


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


def _write_release(
    profile: RuntimeProfile,
    release: Path,
    bin_path: Path,
    upstream_attested: bool,
    hermes_config_renderer: Callable[[RuntimeProfile], str] | None = None,
    *, native_installation: dict | None = None,
    native_derivation: dict | None = None,
) -> None:
    consumer = (native_installation or {}).get("executive_consumer")
    evaluation_inputs = (native_installation or {}).get("evaluation_inputs")
    primary = (native_installation or {}).get("primary_application")
    if evaluation_inputs is not None and (primary is not None or profile.model_provider == "mastermind-fabric"):
        raise RuntimeRefusal("NATIVE_EVAL_INPUTS_UNQUALIFIED")
    home = release / "hermes-home"
    role_dir = home / "profiles" / profile.role
    role_dir.mkdir(parents=True, mode=0o700)
    if primary is not None:
        from integrations.hermes_application_fabric.publication import expected_native_config as application_config
        expected_config = application_config(profile, primary, consumer)
        if hermes_config_renderer is not None and hermes_config_renderer(profile) != expected_config:
            raise RuntimeRefusal("NATIVE_GATEWAY_CONFIG_MISMATCH")
        hermes_config_renderer = lambda profile: expected_config
    if native_installation is not None and hermes_config_renderer is None:
        from integrations.hermes_harness.native_byok import expected_native_config
        hermes_config_renderer = lambda profile: expected_native_config(
            profile, consumer, evaluation_inputs=evaluation_inputs)
    config = (
        hermes_config_renderer(profile)
        if hermes_config_renderer is not None
        else render_hermes_config(profile)
    )
    if not isinstance(config, str) or len(config.encode("utf-8")) > 64 * 1024:
        raise RuntimeRefusal("NATIVE_CONFIG_INVALID")
    if native_installation is not None:
        from integrations.hermes_harness.native_byok import expected_native_config
        expected = (application_config(profile, primary, consumer) if primary is not None
                    else expected_native_config(profile, consumer, evaluation_inputs=evaluation_inputs))
        if config != expected:
            raise RuntimeRefusal("NATIVE_GATEWAY_CONFIG_MISMATCH")
    _atomic_write(role_dir / "config.yaml", config.encode("utf-8"), 0o600)
    plugin_digest = None
    if consumer is not None:
        plugin_digest = _install_consumer_plugin(role_dir, consumer)
    soul = _soul_bytes(profile.role)
    _atomic_write(role_dir / "SOUL.md", soul, 0o600)
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
    if native_installation is not None:
        if ("vendor_derivation" in native_installation) != (native_derivation is not None):
            raise RuntimeRefusal("NATIVE_DERIVATION_PROOF_REQUIRED")
        receipt.update(native_gateway=native_installation,
                       native_launcher_sha256=hashlib_sha256(bin_path.read_bytes()),
                       native_adapter_sha256=hashlib_sha256(
                           (repo_root() / "integrations/hermes_runtime/native_gateway_entry.py").read_bytes()))
        if native_derivation is not None:
            receipt["native_vendor_derivation"] = native_derivation
        if plugin_digest is not None:
            # Source package equality only. The held release capability,
            # never role-home ownership, authenticates it before import.
            receipt.update(native_consumer_plugin_sha256=plugin_digest)
    _atomic_write(release / "install-receipt.json", _json(receipt), 0o600)


def _install_consumer_plugin(role_dir: Path, consumer: dict) -> str:
    """Record the source package; never copy executable code into role custody.

    The held release owner qualifies these same bytes again before any native
    discovery/import. A source digest in this receipt alone grants no load.
    """
    from integrations.hermes_harness.native_executive_consumer import (
        CONSUMER_PLUGIN_NAME, plugin_package_digest)
    target = role_dir / "plugins" / CONSUMER_PLUGIN_NAME
    if os.path.lexists(target):
        raise RuntimeRefusal("NATIVE_CONSUMER_ROLE_PACKAGE_FORBIDDEN")
    source = repo_root() / "integrations/hermes_harness" / CONSUMER_PLUGIN_NAME
    observed = plugin_package_digest(source)
    if observed != consumer["plugin"]["digest"]:
        raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_SOURCE_MISMATCH")
    return observed



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
    _atomic_write(unit, text.encode("utf-8"), 0o600)
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

