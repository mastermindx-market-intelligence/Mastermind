#!/usr/bin/env python3
"""support_bundle: pure file publication helper, Python3 stdlib only."""

import os, sys, json, hashlib, tempfile, shutil, fcntl,errno,stat,time
from pathlib import Path

# Fixed public source closure (no credentials or controller-only helpers)
SOURCE_FILES = frozenset({
    "remote_sub_exec.py",
    "artifact_production.py",
    "artifact_reader.py",
    "native_remote.py",
    "go_remote_codex.py",
    "go_remote_capsule.py",
    "lane_runtime.py",
    "sub.sh",
    "slot.py",
    "glm_bound_claude.py",
    "pick.py",
    "model_tier.py",
    "codex_usage.py",
    "mm_codex_exec.sh",
    "glm_codex_exec.sh",
    "go_codex_exec.sh",
    "qwen_exec.sh",
    "fabric_client_projection.py",
    "studio_mcp_projection.sh",
    "mm_feeder_lib.py",
    "pool_ledger.py",
    "lease_broker.py",
    "glm_keys.py",
    "bailian_keys.py",
})

# Preserve both historical fixed closures while adding one new exact generation.
# No arbitrary subset is accepted.
PREVIOUS_SOURCE_FILES = SOURCE_FILES - {"glm_bound_claude.py"}
LEGACY_SOURCE_FILES = PREVIOUS_SOURCE_FILES - {"artifact_production.py", "artifact_reader.py"}
PRE_OPERATOR_SOURCE_FILES = SOURCE_FILES
SOURCE_FILES = PRE_OPERATOR_SOURCE_FILES | {"fabric_operator_client.py", "fabric_operator_stop.py"}
OPERATOR_SOURCE_FILES = SOURCE_FILES
SOURCE_FILES = OPERATOR_SOURCE_FILES | {"fabric_policy_snapshot.py", "pools.yaml"}
POLICY_SOURCE_FILES = SOURCE_FILES
SOURCE_FILES = POLICY_SOURCE_FILES | {"fabric_operator_diagnostics.py"}
PRE_CPU_STRESS_SOURCE_FILES = SOURCE_FILES
SOURCE_FILES = PRE_CPU_STRESS_SOURCE_FILES | {"yes"}
PRE_CPU_SCOPE_SOURCE_FILES = SOURCE_FILES
# Add the optional original-worker user-cgroup helper to NEW immutable support
# generations only. Every preceding immutable generation remains accepted.
SOURCE_FILES = PRE_CPU_SCOPE_SOURCE_FILES | {"fabric_cpu_scope.py"}
PRE_QUOTA_CONTINUITY_SOURCE_FILES = SOURCE_FILES
SOURCE_FILES = PRE_QUOTA_CONTINUITY_SOURCE_FILES | {"provider_outcome.py", "quota_circuit.py", "recovery_artifacts.py", "capacity_preflight.py"}
PRE_NATIVE_BINDING_SOURCE_FILES = SOURCE_FILES
SOURCE_FILES = PRE_NATIVE_BINDING_SOURCE_FILES | {"native_runtime_bindings.py"}
PRE_COMMISSION_DEADLINE_SOURCE_FILES = SOURCE_FILES
SOURCE_FILES = PRE_COMMISSION_DEADLINE_SOURCE_FILES | {"commission_deadline.py"}
# A configured physical root adds the portable custody reader only to that
# exact new closure. Legacy/default artifact digests retain SOURCE_FILES.
PHYSICAL_ROOT_SOURCE_FILES = SOURCE_FILES | {"artifact_delivery.py"}
# Old immutable generations continue to authenticate their exact closures.
PAID_MODEL_SOURCE_FILES = SOURCE_FILES | {"paid_glm_model_client.py", "paid_model_owner.py", "linux_process_identity.py"}
PAID_MODEL_PHYSICAL_ROOT_SOURCE_FILES = PAID_MODEL_SOURCE_FILES | {"artifact_delivery.py"}
SOURCE_GENERATIONS = (PAID_MODEL_PHYSICAL_ROOT_SOURCE_FILES, PAID_MODEL_SOURCE_FILES, PHYSICAL_ROOT_SOURCE_FILES, SOURCE_FILES, PRE_COMMISSION_DEADLINE_SOURCE_FILES, PRE_NATIVE_BINDING_SOURCE_FILES, PRE_QUOTA_CONTINUITY_SOURCE_FILES, PRE_CPU_SCOPE_SOURCE_FILES, PRE_CPU_STRESS_SOURCE_FILES, POLICY_SOURCE_FILES, OPERATOR_SOURCE_FILES, PRE_OPERATOR_SOURCE_FILES, PREVIOUS_SOURCE_FILES, LEGACY_SOURCE_FILES)

# Fixed symlinks inside ext -> stable_ext/<name>
_EXT_SYMLINKS = frozenset({
    "active","lanes","slots","state","broker","lane_bin",
    "hosts.json","bailian_policy.json","bailian_usage.json",
    "GROK_EXHAUSTED","glm_window_state.json","glm_shim","go_shim",
    "codex_glm","codex_go","codex_minimax",
})

# Fixed symlinks at release root
_ROOT_SYMLINKS = {
    "orch": "..",
    "codex_bailian": "..",
    "minimax_claude_home": "..",
    "glm_claude_home": "..",
    "go_claude_home": "..",
}

_SCHEMA = "remote-support-code.v1"
_LOCK_PATH = ".publication.lock"   # relative to support-releases dir


def _hex64(data: bytes) -> str:
    h = hashlib.sha256(data).hexdigest()
    if len(h) != 64 or h != h.lower():
        raise ValueError(f"invalid hex64 digest {h!r}")
    return h


def _load_manifest(path: Path) -> dict:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("manifest contains duplicate keys")
            result[key] = value
        return result
    obj = json.loads(path.read_text(), object_pairs_hook=unique_pairs)
    if not isinstance(obj, dict):
        raise ValueError("manifest must be a JSON object")
    return obj


def _verify_source_file(src: Path, expected_hash: str) -> None:
    if not src.is_file() or os.path.islink(src):
        raise ValueError(f"{src}: must be regular file, not symlink")
    if src.stat().st_size != os.path.getsize(src):
        raise ValueError(f"{src}: size mismatch")
    actual = _hex64(src.read_bytes())
    if actual != expected_hash.lower():
        raise ValueError(f"{src}: hash mismatch {actual} != {expected_hash}")


def _verify_dest_file(dst: Path, expected_hash: str) -> None:
    """Rehash COPIED destination bytes before publish to catch copy corruption."""
    if os.path.islink(dst):
        raise ValueError(f"{dst}: destination must not be a symlink")
    actual = _hex64(dst.read_bytes())
    if actual != expected_hash.lower():
        raise ValueError(f"{dst}: destination hash mismatch {actual} != {expected_hash}")


def _reject_overlap(source_dir: Path, stable_ext: Path, releases_dir: Path) -> None:
    canon_src = source_dir.resolve()
    canon_stable = stable_ext.resolve()
    canon_rel = releases_dir.resolve()
    if canon_stable in canon_src.parents or canon_src == canon_stable:
        raise ValueError("source_dir must not be inside stable_ext")
    if canon_rel in canon_src.parents or canon_src == canon_rel:
        raise ValueError("source_dir must not be inside support-releases")
    if canon_src in canon_stable.parents or canon_src == canon_stable:
        raise ValueError("source_dir must not be inside stable_ext")
    if canon_src in canon_rel.parents or canon_src == canon_rel:
        raise ValueError("source_dir must not be inside support-releases")


def _copy_file(src: Path, dst: Path, mode: int = 0o555) -> None:
    shutil.copy2(src, dst)
    os.chmod(dst, mode)


def _canon_manifest(manifest: dict) -> bytes:
    return json.dumps(
        {"schema": _SCHEMA, "files": manifest},
        sort_keys=True, separators=(",", ":")
    ).encode()


def _require_kind(path, kind, mode=None):
    try:
        observed = path.lstat()
    except OSError as exc:
        raise ValueError(f"unavailable publication path: {path}") from exc
    if not kind(observed.st_mode):
        raise ValueError(f"unexpected file kind: {path}")
    if mode is not None and stat.S_IMODE(observed.st_mode) != mode:
        raise ValueError(f"unexpected mode: {path}")


def _release_metadata(manifest, digest, stable_ext):
    links = {"ext/" + n: str(stable_ext / n) for n in _EXT_SYMLINKS}
    links.update({n: str(stable_ext.parent / n) for n in _ROOT_SYMLINKS})
    return {"schema": _SCHEMA, "files": manifest, "digest": digest, "links": links}


def _verify_release(root, expected):
    _require_kind(root, stat.S_ISDIR, 0o555)
    ext = root / "ext"
    _require_kind(ext, stat.S_ISDIR, 0o555)
    meta = root / "RELEASE.json"
    _require_kind(meta, stat.S_ISREG, 0o444)
    if _load_manifest(meta) != expected:
        raise ValueError("release metadata mismatch")
    if {p.name for p in root.iterdir()} != {"ext", "RELEASE.json", *_ROOT_SYMLINKS}:
        raise ValueError("unexpected release contents")
    if (frozenset(expected["files"]) not in SOURCE_GENERATIONS
            or {p.name for p in ext.iterdir()} != set(expected["files"]) | _EXT_SYMLINKS):
        raise ValueError("unexpected ext contents")
    for name, wanted in expected["files"].items():
        path = ext / name
        _require_kind(path, stat.S_ISREG, 0o555)
        if _hex64(path.read_bytes()) != wanted:
            raise ValueError("release source hash mismatch: " + name)
    for name, target in expected["links"].items():
        path = root / name
        _require_kind(path, stat.S_ISLNK)
        if os.readlink(path) != target:
            raise ValueError("release binding mismatch: " + name)


def _discard_own_staging(root):
    # Only the unpublished tempfile directory created by this invocation.
    # Make its two real directories writable; never chmod symlink targets.
    _require_kind(root, stat.S_ISDIR)
    root.chmod(0o700)
    ext = root / "ext"
    if ext.exists() and not ext.is_symlink():
        _require_kind(ext, stat.S_ISDIR)
        ext.chmod(0o700)
    shutil.rmtree(root)


def publish(source_dir: Path, stable_ext: Path, manifest: dict) -> Path:
    stable_ext = Path(stable_ext).resolve(strict=True)
    _require_kind(stable_ext, stat.S_ISDIR)
    releases_dir = stable_ext.parent / "support-releases"
    _require_kind(releases_dir, stat.S_ISDIR)
    source_dir = Path(source_dir).resolve(strict=True)
    _require_kind(source_dir, stat.S_ISDIR)
    _reject_overlap(source_dir, stable_ext, releases_dir)
    if not isinstance(manifest, dict) or frozenset(manifest) not in SOURCE_GENERATIONS:
        raise ValueError("manifest must name exactly the fixed source files")
    for name, wanted in manifest.items():
        if not isinstance(wanted, str) or len(wanted) != 64 or any(c not in "0123456789abcdef" for c in wanted):
            raise ValueError("hash must be 64 lowercase hex characters")
        _require_kind(source_dir / name, stat.S_ISREG)
        _verify_source_file(source_dir / name, wanted)
    if "pools.yaml" in manifest:
        from fabric_policy_snapshot import validate_publication
        try:
            validate_publication(source_dir / "pools.yaml", stable_ext)
        except ValueError as exc:
            # Only a verified critical-policy difference can need refresh.
            # Compatible advisory snapshots keep working beside active lanes;
            # malformed policy, permission/lock and other refusals propagate.
            if str(exc) != "ROUTING_CRITICAL_POLICY_MISMATCH":
                raise
            outcome = ensure_policy(source_dir / "pools.yaml", stable_ext,
                                    manifest["pools.yaml"])
            validate_publication(source_dir / "pools.yaml", stable_ext)
            print(f"{outcome} sha256={manifest['pools.yaml']}", file=sys.stderr)
    digest = _hex64(_canon_manifest(manifest))
    final = releases_dir / digest
    expected = _release_metadata(manifest, digest, stable_ext)
    # This is only an artifact-publication lock. Host/provider admission stays
    # in the existing shared paths and is never granted here.
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(releases_dir / _LOCK_PATH, flags, 0o600)
    with os.fdopen(fd, "r+") as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise ValueError("publication lock must be regular")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            if os.path.lexists(final):
                _verify_release(final, expected)
                return final / "ext"
            staged = Path(tempfile.mkdtemp(prefix="_pub_", dir=releases_dir))
            try:
                ext = staged / "ext"
                ext.mkdir()
                for name in sorted(manifest):
                    shutil.copy2(source_dir / name, ext / name)
                    _require_kind(ext / name, stat.S_ISREG)
                    (ext / name).chmod(0o555)
                for name, target in expected["links"].items():
                    os.symlink(target, staged / name)
                metadata = staged / "RELEASE.json"
                metadata.write_text(json.dumps(expected, sort_keys=True) + "\n")
                metadata.chmod(0o444)
                ext.chmod(0o555)
                staged.chmod(0o555)
                # Rehash copied bytes and verify ALL bindings before exposure.
                _verify_release(staged, expected)
                # Darwin requires the moved directory to be writable. Only the
                # root is temporarily writable; code and bindings stay sealed.
                # The publication lock covers rename AND final sealing. No
                # caller receives the path until the complete contract passes.
                staged.chmod(0o755)
                os.rename(staged, final)
                staged = None
                # A failure here deliberately retains an unusable release;
                # reuse verifies and refuses it, never repairs published bytes.
                final.chmod(0o555)
                _verify_release(final, expected)
                return final / "ext"
            finally:
                if staged is not None:
                    _discard_own_staging(staged)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


_POLICY_LOCK_WAIT_SECONDS = 2.0


def _acquire_policy_lock(fd):
    # Wait for a short metadata critical section, never for a host slot or worker.
    deadline = time.monotonic() + _POLICY_LOCK_WAIT_SECONDS
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BlockingIOError(errno.EAGAIN, "SUPPORT_ADMISSION_LOCK_BUSY")
            time.sleep(min(0.02, remaining))


def _is_retained_settlement_metadata(path):
    """Classify retained metadata; never settle a run or remove a lane marker.

    Every non-metadata entry still blocks publication, including the original
    run marker if removal was interrupted. Do not ignore arbitrary dotfiles.
    """
    import re
    match = re.fullmatch(r"\.([A-Za-z0-9][A-Za-z0-9_.:-]{0,127})\.preexec-settlement\.json", path.name)
    if not match:
        return False
    try:
        from lane_runtime import LaneRuntimeError, validate_preexec_settlement_receipt
    except ImportError:
        return False
    descriptor = None
    try:
        visible = path.lstat()
        if not stat.S_ISREG(visible.st_mode) or visible.st_size > 1048576:
            return False
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        opened = os.fstat(descriptor)
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid()
                or opened.st_mode & 0o022 or identity(opened) != identity(visible)):
            return False
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raw = os.read(descriptor, 1048577)
        if (len(raw) != opened.st_size or identity(os.fstat(descriptor)) != identity(opened)
                or identity(path.lstat()) != identity(opened)):
            return False
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate settlement key")
                result[key] = value
            return result
        value = json.loads(raw, object_pairs_hook=unique_pairs)
        if type(value) is not dict or value.get('run_id') != match[1]:
            return False
        validate_preexec_settlement_receipt(value)
        return True
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, LaneRuntimeError):
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def ensure_policy(source, stable_ext, expected_hash):
    """Refresh live policy only while the EXISTING physical admission lock is idle."""
    source, stable_ext = Path(source), Path(stable_ext).resolve(strict=True)
    _require_kind(source, stat.S_ISREG)
    _require_kind(stable_ext, stat.S_ISDIR)
    data = source.read_bytes()
    if len(data) > 2 * 1024 * 1024 or _hex64(data) != expected_hash:
        raise ValueError("SUPPORT_POLICY_HASH_MISMATCH")
    active = stable_ext / "active"
    _require_kind(active, stat.S_ISDIR)
    target = stable_ext.parent / "orch/fabric/pools.yaml"
    _require_kind(target.parent, stat.S_ISDIR)
    fd = os.open(active / ".admission.lock",
                 os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, "r+") as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise ValueError("SUPPORT_ADMISSION_LOCK_INVALID")
        _acquire_policy_lock(lock.fileno())
        try:
            old_mode = 0o600
            if os.path.lexists(target):
                _require_kind(target, stat.S_ISREG)
                old_mode = stat.S_IMODE(target.stat().st_mode)
                if target.read_bytes() == data:
                    return "POLICY_CURRENT"
            if any(p.name != ".admission.lock" and not _is_retained_settlement_metadata(p)
                   for p in active.iterdir()):
                raise ValueError("SUPPORT_POLICY_STALE_ACTIVE_REFUSED")
            descriptor, name = tempfile.mkstemp(prefix=".pools-policy-", dir=target.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fchmod(stream.fileno(), old_mode)
                    os.fsync(stream.fileno())
                os.replace(name, target)
            finally:
                if os.path.lexists(name):
                    os.unlink(name)
            return "POLICY_REFRESHED_IDLE"
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _cli():
    try:
        if len(sys.argv) == 5 and sys.argv[1] == "--policy":
            print(ensure_policy(sys.argv[2], sys.argv[3], sys.argv[4]))
        elif len(sys.argv) == 4:
            print(publish(Path(sys.argv[1]), Path(sys.argv[2]),
                          _load_manifest(Path(sys.argv[3]))))
        else:
            raise ValueError("usage: support_bundle.py <source_dir> <stable_ext> <manifest_json> | --policy <source> <stable_ext> <sha256>")
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
