#!/usr/bin/env python3
"""Adopt and verify one exact installed Studio Direct control-helper bundle.

This is deployment plumbing for the existing control surface. It never starts,
stops, restarts, upgrades, or otherwise mutates a Studio Direct seat or tunnel.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

SCHEMA = "mastermind.studio_direct_control_bundle.v1"
# The new fleet-status module successor remains part of the ONE original
# private-service control bundle, never an independently installed helper.
LEGACY_CONTROL_FILES = (
    "private_service.py",
    "private_tunnel_service.py",
    "studio_direct_control.py",
)
STATUS_CONTROL_FILES = (*LEGACY_CONTROL_FILES, "private_service_status_successor.py")
CAPTURED_CONTROL_FILES = (
    *STATUS_CONTROL_FILES,
    "private_service_pin.py",
    "private_service_pin_enrollment.py",
    "paper_v20_fleet_cohorts.py",
    "ops/native_fabric/quota_continuity/rollout/native_install.py",
    "ops/native_fabric/quota_continuity/rollout/native_generation.py",
    "ops/fabric_launch/install.py",
)
# Preserve the exact ten-member captured generation for locked migration.
REVIEW_CONTROL_FILES = (
    *CAPTURED_CONTROL_FILES,
    "fleet_git_failure_compat.py",
    "ops/native_fabric/quota_continuity/rollout/build_review_stage.py",
    "ops/native_fabric/quota_continuity/rollout/preimages/native_generation_75330d.py",
)
# Exact Go verification inputs for the installed owner; never a source-path fallback.
GO_REVIEW_SOURCE_FILES = (
    "control_plane/provider_protocols.py",
    "ops/native_fabric/paid_canonical_glm/candidate/glm_shim.py",
    "ops/native_fabric/provider_plans/maintenance_guard/lease_broker.py.patch",
    "ops/native_fabric/provider_plans/maintenance_guard/remote_sub_exec.py.patch",
    "ops/native_fabric/provider_plans/memory118/fabric_memory_view.py",
    "ops/native_fabric/provider_plans/memory118/lease_broker.after-maintenance.py.patch",
    "ops/native_fabric/provider_plans/memory118/native_owner/fabric_operator_contract.py",
    "ops/native_fabric/provider_plans/memory118/native_owner/fabric_operator_owner.py",
    "ops/native_fabric/provider_plans/memory118/native_owner/protected_memory_economic.py",
    "ops/native_fabric/provider_plans/memory118/native_owner/provider_outcome.py",
    "ops/native_fabric/provider_plans/memory118/native_owner/run_observation_delivery.py",
    "ops/native_fabric/provider_plans/memory118_support_status/after_terminal_diagnostics/profile.json",
    "ops/native_fabric/provider_plans/memory118_support_status/artifact_delivery.py.patch",
    "ops/native_fabric/provider_plans/memory118_support_status/fabric_task.py.patch",
    "ops/native_fabric/provider_plans/patches/pick_remote_plan_modes.forward.patch",
    "ops/native_fabric/provider_plans/profile.json",
    "ops/native_fabric/provider_plans/remote_placement/profile.json",
    "ops/native_fabric/provider_plans/router_admission.json",
    "ops/native_fabric/provider_plans/terminal_diagnostics/component.json",
    "ops/native_fabric/provider_plans/terminal_diagnostics/current40/profile.json",
    "ops/native_fabric/provider_plans/terminal_diagnostics/native_plan_worker.py.forward.patch",
    "ops/native_fabric/quota_continuity/candidate/application_http_transports.py",
    "ops/native_fabric/quota_continuity/candidate/go_lease_capability.py",
    "ops/native_fabric/quota_continuity/candidate/go_lease_gateway.py",
    "ops/native_fabric/quota_continuity/candidate/go_shim.py",
    "ops/native_fabric/quota_continuity/candidate/lease_broker.py",
    "ops/native_fabric/quota_continuity/candidate/native_go_entry.py",
    "ops/native_fabric/quota_continuity/rollout/application_http_realm_projection.py",
    "ops/native_fabric/quota_continuity/rollout/preimages/glm_application_core_5c3d/go_lease_capability.py",
    "ops/native_fabric/quota_continuity/rollout/preimages/glm_application_core_5c3d/go_lease_gateway.py",
    "ops/native_fabric/quota_continuity/rollout/preimages/glm_application_core_5c3d/lease_broker.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/composition.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/experiential_bridge.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/experiential_host_context.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/experiential_plan_policy.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/experiential_transport.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/native40-profile.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/native40-provenance.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/native_plan_worker.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/memory_support/composition.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/memory_support/fabric_task.py.forward.patch",
    "ops/native_fabric/quota_continuity/rollout/provider_application/memory_support/lease_broker.py.forward.patch",
    "ops/native_fabric/quota_continuity/rollout/provider_application/remote-placement.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/terminal_diagnostics/composition.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/terminal_diagnostics/native_plan_worker.py.forward.patch",
    "ops/native_fabric/quota_continuity/source/application_http_transports.py.preimage",
    "ops/native_fabric/quota_continuity/source/codex_provider_realm.py.preimage",
    "ops/native_fabric/quota_continuity/source/glm_keys.py",
    "ops/native_fabric/quota_continuity/source/go_shim.py",
    "ops/native_fabric/support_policy_status/reader.py",
)
CONTROL_FILES = (*REVIEW_CONTROL_FILES, *GO_REVIEW_SOURCE_FILES)
# Exact inert pre-control-bundle snapshots observed on the original M2 host.
# These are NOT executable/source dependencies and confer no runtime authority.
# Preserve them without admission of arbitrary pre-* names or changed content.
HISTORICAL_CONTROL_BACKUPS = {
    'private_service.py.pre-exact-legacy-manifests-20261022': 'a184ca7f3408e20454adf4f1e5986add845b5742908efd9ed4e0f552755820bb',
    'private_service.py.pre-sealed-byte-validation-20261022': 'e636a728dbde6ca43b2248456aaabddbab8d78693066df7717030d07e757ebe4',
    'private_tunnel_service.py.pre-concurrency8-20261022': '4a7d425a2345eaf30b56ed1ca148e0afa2f8e474bd03e2453d4e0a9a4ef85467',
    'private_tunnel_service.py.pre-exact-sealed-roster-20261022': 'c3753a0c4167560a7980c366e707ce41153d93b8a8710ba4365ba9a45ff8d81f',
    'private_tunnel_service.py.pre-sealed-argv-20261022': 'b0449df0252159dbebed084ccc3d4520690ff811f0e30125d37ca8effb3e68fa',
    'studio_direct_control.py.pre-public-projection-20261022': '6fca63efd82132f3063d065d9757e10c22e7d4cef4b6549b24068b407bce912d',
}

FILE_MODE = 0o600
DIR_MODE = 0o700


class Refusal(RuntimeError):
    pass


class EffectUnknown(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_regular(path: Path, *, executable: bool = False, private: bool = False) -> Path:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise Refusal("REGULAR_FILE_REQUIRED")
    if info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o022:
        raise Refusal("CURRENT_USER_OWNERSHIP_REQUIRED")
    if private and stat.S_IMODE(info.st_mode) != FILE_MODE:
        raise Refusal("PRIVATE_FILE_REQUIRED")
    if executable and not (info.st_mode & stat.S_IXUSR):
        raise Refusal("EXECUTABLE_REQUIRED")
    return path


def _require_private_dir(path: Path) -> Path:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise Refusal("PRIVATE_DIRECTORY_REQUIRED")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != DIR_MODE:
        raise Refusal("PRIVATE_DIRECTORY_REQUIRED")
    return path


def _require_control_paths(control_root: Path, launcher: Path) -> None:
    home = Path.home()
    if (not home.is_absolute()
            or control_root != home / ".local/share/studio-direct-mcp/control"
            or launcher != home / ".local/bin/studio-direct"):
        raise Refusal("CONTROL_LAYOUT_INVALID")
    # Match the consumer boundary; platform aliases above HOME remain allowed.
    for path in (control_root, launcher.parent):
        current = path
        while True:
            info = current.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o022):
                raise Refusal("CONTROL_ANCESTOR_UNSAFE")
            if current == home:
                break
            current = current.parent


def _source_files(source: Path) -> dict[str, Path]:
    # The existing source entrypoint remains integrations/studio_direct_mcp.
    # Native imports retain their repository-relative depth inside the bundle.
    if source.parts[-2:] != ("integrations", "studio_direct_mcp"):
        raise Refusal("SOURCE_LAYOUT_INVALID")
    repository = source.parent.parent
    rows = {}
    for name in CONTROL_FILES:
        relative = Path(name) if "/" in name else Path("integrations/studio_direct_mcp") / name
        path = repository / relative
        current = repository
        for part in (None, *relative.parts[:-1]):
            if part is not None:
                current = current / part
            info = current.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o022):
                raise Refusal("SOURCE_DIRECTORY_INVALID")
        rows[name] = _require_regular(path)
    return rows


def _directory_members(names):
    directories = {Path("."): {"manifest.json"}}
    for name in names:
        relative = Path(name)
        for index, part in enumerate(relative.parts):
            parent = Path(*relative.parts[:index])
            directories.setdefault(parent, set()).add(part)
            if index < len(relative.parts) - 1:
                directories.setdefault(parent / part, set())
    return directories


def _require_code_layout(root: Path, names, *, complete: bool, allow_cache: bool = False) -> None:
    directories = _directory_members(names)
    for relative, expected in directories.items():
        directory = root / relative
        if not os.path.lexists(directory):
            if complete:
                raise Refusal("CONTROL_BUNDLE_CONTENTS_INVALID")
            continue
        _require_private_dir(directory)
        observed = {path.name for path in directory.iterdir()}
        if relative == Path("."):
            for metadata in ("manifest.json", ".control-bundle.lock"):
                if metadata in observed:
                    _require_regular(directory / metadata, private=True)
            observed.discard(".control-bundle.lock")
        if relative == Path(".") and "__pycache__" in observed and allow_cache:
            # Admit only bounded old caches for legacy observation or migration.
            # A new installed bundle never executes or retains these bytes.
            cache = directory / "__pycache__"
            info = cache.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o022):
                raise Refusal("CONTROL_BUNDLE_CONTENTS_INVALID")
            stems = {Path(name).stem for name in names if "/" not in name}
            for cached in cache.iterdir():
                if (not cached.name.endswith(".pyc")
                        or not any(cached.name.startswith(stem + ".") for stem in stems)):
                    raise Refusal("CONTROL_BUNDLE_CONTENTS_INVALID")
                _require_regular(cached)
            observed.remove("__pycache__")
        if relative == Path("."):
            for backup, expected_hash in HISTORICAL_CONTROL_BACKUPS.items():
                if backup not in observed:
                    continue
                original = _require_regular(directory / backup, private=True)
                if _sha256(original) != expected_hash:
                    raise Refusal("CONTROL_BUNDLE_HISTORICAL_BACKUP_CHANGED")
                observed.remove(backup)
        if not observed <= expected or (complete and observed != expected):
            raise Refusal("CONTROL_BUNDLE_CONTENTS_INVALID")
    for name in names:
        path = root / name
        if os.path.lexists(path):
            _require_regular(path, private=True)


def _member_path(root: Path, name: str) -> Path:
    path = root / name
    current = root
    for part in Path(name).parts[:-1]:
        current = current / part
        _require_private_dir(current)
    return path


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate control manifest key")
        value[key] = item
    return value


def _bundle_digest(files: dict[str, str], launcher_hash: str) -> str:
    payload = json.dumps(
        {"files": dict(sorted(files.items())), "launcherHash": launcher_hash},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _manifest_payload(source: Path, files: dict[str, Path], launcher: Path) -> dict:
    digests = {name: _sha256(path) for name, path in sorted(files.items())}
    launcher_hash = _sha256(launcher)
    return {
        "schema": SCHEMA,
        "files": digests,
        "launcher": str(launcher),
        "launcherHash": launcher_hash,
        "bundleDigest": _bundle_digest(digests, launcher_hash),
        "source": str(source),
    }


def _read_manifest(path: Path) -> dict:
    _require_regular(path, private=True)
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError) as exc:
        raise Refusal("CONTROL_MANIFEST_INVALID") from exc
    expected_keys = {"schema", "files", "launcher", "launcherHash", "bundleDigest", "source"}
    if not isinstance(value, dict) or set(value) != expected_keys or value.get("schema") != SCHEMA:
        raise Refusal("CONTROL_MANIFEST_INVALID")
    files = value.get("files")
    # Legacy three/four and captured ten/thirteen-member identities remain observable
    # for migration. New runtime admission requires the full reviewed source closure.
    if (not isinstance(files, dict)
            or frozenset(files) not in (frozenset(LEGACY_CONTROL_FILES),
                                       frozenset(STATUS_CONTROL_FILES),
                                       frozenset(CAPTURED_CONTROL_FILES),
                                       frozenset(REVIEW_CONTROL_FILES), frozenset(CONTROL_FILES))):
        raise Refusal("CONTROL_MANIFEST_INVALID")
    if any(not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest) for digest in files.values()):
        raise Refusal("CONTROL_MANIFEST_INVALID")
    launcher = value.get("launcher")
    launcher_hash = value.get("launcherHash")
    source = value.get("source")
    bundle_digest = value.get("bundleDigest")
    if (not isinstance(launcher, str) or not Path(launcher).is_absolute()
            or not isinstance(source, str) or not Path(source).is_absolute()
            or not isinstance(launcher_hash, str) or len(launcher_hash) != 64
            or any(c not in "0123456789abcdef" for c in launcher_hash)
            or not isinstance(bundle_digest, str) or len(bundle_digest) != 64
            or any(c not in "0123456789abcdef" for c in bundle_digest)):
        raise Refusal("CONTROL_MANIFEST_INVALID")
    if bundle_digest != _bundle_digest(files, launcher_hash):
        raise Refusal("CONTROL_MANIFEST_INVALID")
    return value


def _verify_locked(*, control_root: Path, launcher: Path) -> dict:
    root = _require_private_dir(control_root)
    manifest = _read_manifest(root / "manifest.json")
    _require_regular(launcher, executable=True)
    if manifest.get("launcher") != str(launcher) or manifest.get("launcherHash") != _sha256(launcher):
        raise Refusal("CONTROL_BUNDLE_MISMATCH")
    _require_code_layout(
        root, manifest["files"], complete=True,
        allow_cache=frozenset(manifest["files"]) not in (
            frozenset(CAPTURED_CONTROL_FILES), frozenset(REVIEW_CONTROL_FILES), frozenset(CONTROL_FILES)),
    )
    observed = {}
    for name in manifest["files"]:
        path = _require_regular(_member_path(root, name), private=True)
        observed[name] = _sha256(path)
        if manifest["files"].get(name) != observed[name]:
            raise Refusal("CONTROL_BUNDLE_MISMATCH")
    return {
        "state": "CONTROL_BUNDLE_VERIFIED",
        "schema": SCHEMA,
        "files": observed,
        "launcherHash": _sha256(launcher),
        "bundleDigest": manifest["bundleDigest"],
        "source": manifest.get("source"),
    }


def verify(*, control_root: Path, launcher: Path) -> dict:
    _require_control_paths(control_root, launcher)
    root = _require_private_dir(control_root)
    if not os.path.lexists(root / ".control-bundle.lock"):
        # Legacy identity observation is read-only and does not claim a locked
        # generation. Every captured cohort requires its existing lock.
        manifest = _read_manifest(root / "manifest.json")
        if frozenset(manifest["files"]) in (
                frozenset(CAPTURED_CONTROL_FILES), frozenset(REVIEW_CONTROL_FILES), frozenset(CONTROL_FILES)):
            raise Refusal("CONTROL_BUNDLE_LOCK_REQUIRED")
        observed = _verify_locked(control_root=root, launcher=launcher)
        identity = ("schema", "files", "launcherHash", "bundleDigest", "source")
        if (os.path.lexists(root / ".control-bundle.lock")
                or any(observed[key] != manifest[key] for key in identity)):
            raise Refusal("CONTROL_BUNDLE_CHANGED")
        return observed
    with _lock(root, shared=True, create=False):
        return _verify_locked(control_root=root, launcher=launcher)


@contextlib.contextmanager
def _lock(root: Path, *, shared: bool = False, create: bool = True):
    path = root / ".control-bundle.lock"
    flags = os.O_RDONLY if shared else os.O_RDWR
    if create:
        flags |= os.O_CREAT
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, FILE_MODE)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != FILE_MODE):
            raise Refusal("CONTROL_BUNDLE_LOCK_UNSAFE")
        try:
            operation = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
            fcntl.flock(fd, operation | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refusal("CONTROL_BUNDLE_BUSY") from exc
        named = path.lstat()
        if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
            raise Refusal("CONTROL_BUNDLE_LOCK_UNSAFE")
        yield
    finally:
        os.close(fd)


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, FILE_MODE)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def _verify_original_before_upgrade(
    *, control_root: Path, launcher: Path, expected_bundle_digest: str | None,
) -> str | None:
    """Verify original installed bytes or prove a genuinely empty first install.

    No existing installed helper may be replaced without its verified prior
    bundle digest supplied by the release operator. This is the incumbent
    owner's original bundle; not an additional state store or lease.
    """
    manifest_path = control_root / "manifest.json"
    present = manifest_path.exists() or manifest_path.is_symlink()
    if not present:
        if any((control_root / name).exists() or (control_root / name).is_symlink()
               for name in CONTROL_FILES):
            raise Refusal("CONTROL_BUNDLE_UNMANIFESTED")
        if expected_bundle_digest is not None:
            raise Refusal("CONTROL_BUNDLE_UNEXPECTED_CAS")
        return None

    if (type(expected_bundle_digest) is not str
            or len(expected_bundle_digest) != 64
            or any(c not in "0123456789abcdef" for c in expected_bundle_digest)):
        raise Refusal("CONTROL_BUNDLE_CAS_REQUIRED")
    # This caller already holds the original exclusive bundle lock. Calling
    # verify() here would try a second nonreentrant shared lock (BUSY). Read
    # the original manifest and reseal every originally declared module in
    # place, both before staging and immediately before the first replacement.
    # The precommit pass deliberately does not treat this install's OWN stage
    # directory as a foreign installed generation.
    original = _read_manifest(manifest_path)
    if (original["launcher"] != str(launcher)
            or original["launcherHash"] != _sha256(launcher)):
        raise Refusal("CONTROL_BUNDLE_MISMATCH")
    for name, digest in original["files"].items():
        path = _require_regular(_member_path(control_root, name), private=True)
        if _sha256(path) != digest:
            raise Refusal("CONTROL_BUNDLE_MISMATCH")
    if original["bundleDigest"] != expected_bundle_digest:
        raise Refusal("CONTROL_BUNDLE_CAS_MISMATCH")
    # Bind the full original manifest bytes (including advisory source pointer)
    # for the in-transaction precommit comparison.
    return _sha256(manifest_path)


def install(
    *, source: Path, control_root: Path, launcher: Path,
    expected_bundle_digest: str | None = None,
) -> dict:
    _require_control_paths(control_root, launcher)
    root = _require_private_dir(control_root)
    _require_regular(launcher, executable=True)
    source_files = _source_files(source)
    payload = _manifest_payload(source, source_files, launcher)
    with _lock(root):
        _require_code_layout(root, CONTROL_FILES, complete=False, allow_cache=True)
        original_manifest_sha = _verify_original_before_upgrade(
            control_root=root, launcher=launcher,
            expected_bundle_digest=expected_bundle_digest,
        )
        stage = Path(tempfile.mkdtemp(prefix=".control-bundle.stage-", dir=root))
        committed = False
        try:
            stage.chmod(DIR_MODE)
            directories = sorted(_directory_members(CONTROL_FILES), key=lambda item: len(item.parts))
            for relative in directories:
                if relative != Path("."):
                    (stage / relative).mkdir(mode=DIR_MODE)
            for name, src in source_files.items():
                _write_private(stage / name, src.read_bytes())
                if _sha256(stage / name) != payload["files"][name]:
                    raise Refusal("STAGED_HASH_MISMATCH")
            manifest_bytes = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
            _write_private(stage / "manifest.json", manifest_bytes)
            # Check the entire original helper/launcher seal again immediately
            # before the first replace. An intervening mutation is a pre-effect
            # refusal, never a reason to overwrite or repair blindly.
            current_manifest_sha = _verify_original_before_upgrade(
                control_root=root, launcher=launcher,
                expected_bundle_digest=expected_bundle_digest,
            )
            if current_manifest_sha != original_manifest_sha:
                raise Refusal("CONTROL_BUNDLE_ORIGINAL_CHANGED")
            cache = root / "__pycache__"
            if os.path.lexists(cache):
                committed = True
                shutil.rmtree(cache)
            for relative in directories:
                if relative == Path("."):
                    continue
                destination = root / relative
                if not os.path.lexists(destination):
                    committed = True
                    destination.mkdir(mode=DIR_MODE)
                _require_private_dir(destination)
            for name in CONTROL_FILES:
                committed = True
                os.replace(stage / name, _member_path(root, name))
            os.replace(stage / "manifest.json", root / "manifest.json")
            # Exactly one cleanup attempt. A failure after installed writes
            # preserves its stage and effect classification for reconciliation.
            shutil.rmtree(stage)
            for relative in reversed(directories):
                directory = _require_private_dir(root / relative)
                dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            result = _verify_locked(control_root=root, launcher=launcher)
            if set(result["files"]) != set(CONTROL_FILES):
                raise Refusal("CONTROL_BUNDLE_MISMATCH")
        except BaseException as exc:
            if committed:
                raise EffectUnknown("CONTROL_BUNDLE_EFFECT_UNKNOWN") from exc
            try:
                shutil.rmtree(stage)
            except OSError as cleanup:
                raise Refusal("CONTROL_BUNDLE_STAGE_CLEANUP_FAILED") from cleanup
            raise
    return {**result, "state": "CONTROL_BUNDLE_INSTALLED"}


def _default_paths() -> tuple[Path, Path, Path]:
    source = Path(__file__).resolve().parent
    home = Path.home()
    return (
        source,
        home / ".local" / "share" / "studio-direct-mcp" / "control",
        home / ".local" / "bin" / "studio-direct",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "install"))
    parser.add_argument(
        "--expected-bundle-digest",
        help="exact digest of the currently verified installed bundle; required for upgrades",
    )
    args = parser.parse_args(argv)
    source, control_root, launcher = _default_paths()
    try:
        if args.action == "verify":
            if args.expected_bundle_digest is not None:
                raise Refusal("CONTROL_BUNDLE_EXPECTATION_UNSUPPORTED_FOR_VERIFY")
            result = verify(control_root=control_root, launcher=launcher)
        else:
            result = install(
                source=source, control_root=control_root, launcher=launcher,
                expected_bundle_digest=args.expected_bundle_digest,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except EffectUnknown:
        print(json.dumps({"state": "EFFECT_UNKNOWN", "retry_allowed": False, "reconcile_action": "verify"}))
        return 3
    except (Refusal, OSError) as exc:
        state = str(exc) if isinstance(exc, Refusal) else "LOCAL_FAILURE"
        print(json.dumps({"state": state, "retry_allowed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
