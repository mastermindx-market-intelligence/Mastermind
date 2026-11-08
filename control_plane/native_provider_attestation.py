"""Root-produced native Claude CLI/SDK attestation, not account readiness.

The producer consumes the existing installation receipts. The startup reader
checks their sealed postimage without launching a provider, importing its SDK,
reading credentials, or manufacturing a Worker Broker readiness receipt.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from control_plane.codex_provider_realm import _native_open, ProviderRealmError
from control_plane.fs_security import has_macos_acl, FilesystemSecurityError
from control_plane.worker_execution_contract import BinaryAttestation

SCHEMA = "mastermind.native_claude_attestation/v2"
CLAUDE_TEAM = "Q6L2SF6YDW"
CLI_VERSION = "2.1.275"
SDK_VERSION = "0.2.160"
_ROOT_UID = 0
_LIMIT = 65536
_IDENTITY = ("device", "inode", "size", "mode", "uid", "gid", "mtime_ns", "ctime_ns")
_DURABLE_IDENTITY = ("inode", "size", "mode", "uid", "gid", "mtime_ns", "ctime_ns")


class NativeAttestationError(ValueError):
    """Native installation authority is absent, malformed, or stale."""


def _fail(message):
    raise NativeAttestationError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _identity(info):
    return dict(zip(_IDENTITY, (info.st_dev, info.st_ino, info.st_size,
        stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid, info.st_mtime_ns, info.st_ctime_ns)))


def _durable_identity(info):
    full = _identity(info)
    return {key: full[key] for key in _DURABLE_IDENTITY}


def _runtime_identity(path):
    with _native_open(Path(path)) as (fd, info):
        _check_entry(Path(path), fd, info)
        return _identity(info)


def _check_entry(path, fd, info, directory=False):
    if (not (stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
            or info.st_uid != _ROOT_UID or info.st_mode & 0o022
            or (not directory and info.st_nlink != 1)
            or has_macos_acl(path, descriptor=fd, expected_identity=info)):
        _fail("native installation custody is unsafe")


def _read(fd, limit):
    data = bytearray()
    while len(data) <= limit:
        block = os.read(fd, min(65536, limit + 1 - len(data)))
        if not block:
            break
        data.extend(block)
    if len(data) > limit:
        _fail("native receipt exceeds its bound")
    return bytes(data)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _fail("duplicate native receipt field")
        result[key] = value
    return result


def _json_receipt(path, *, mode, gid=None, digest=None):
    with _native_open(Path(path)) as (fd, info):
        if stat.S_IMODE(info.st_mode) != mode or (gid is not None and info.st_gid != gid):
            _fail("native receipt mode/group differs from its consumer")
        if not 0 < info.st_size <= _LIMIT:
            _fail("native receipt size is invalid")
        raw = _read(fd, _LIMIT)
        if len(raw) != info.st_size or (digest is not None and hashlib.sha256(raw).hexdigest() != digest):
            _fail("native source receipt changed")
        value = json.loads(raw, object_pairs_hook=_pairs,
                           parse_constant=lambda _: _fail("non-finite receipt value"))
        if not isinstance(value, dict):
            _fail("native receipt is not an object")
        return value


def _file_observation(path, *, content=False):
    with _native_open(Path(path)) as (fd, info):
        _check_entry(Path(path), fd, info)
        result = {"path": str(path), "identity": _identity(info)}
        if content:
            if not 0 < info.st_size <= 512 * 1024 * 1024:
                _fail("native executable size is invalid")
            digest = hashlib.sha256()
            while block := os.read(fd, 1024 * 1024):
                digest.update(block)
            result["sha256"] = digest.hexdigest()
        return result


def _sdk_tree(root, *, content=False):
    """Seal every SDK entry through held descriptors; no symlinks or imports."""
    identities, contents = [], []
    total_bytes = 0
    def visit(fd, path, relative):
        nonlocal total_bytes
        before = os.fstat(fd)
        _check_entry(path, fd, before, directory=True)
        identities.append([relative, "directory", _durable_identity(before)])
        with os.scandir(fd) as entries:
            names = sorted(entry.name for entry in entries)
        for name in names:
            if len(identities) >= 20000:
                _fail("native SDK tree exceeds entry bound")
            child_path, rel = path / name, f"{relative}/{name}"
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            directory = stat.S_ISDIR(info.st_mode)
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            if directory:
                flags |= os.O_DIRECTORY
            child = os.open(name, flags, dir_fd=fd)
            try:
                current = os.fstat(child)
                if _identity(current) != _identity(info):
                    _fail("native SDK entry changed while opening")
                _check_entry(child_path, child, current, directory=directory)
                if directory:
                    visit(child, child_path, rel)
                else:
                    identities.append([rel, "file", _durable_identity(current)])
                    total_bytes += current.st_size
                    if total_bytes > 4 * 1024**3:
                        _fail("native SDK tree exceeds byte bound")
                    if content:
                        digest = hashlib.sha256()
                        while block := os.read(child, 1024 * 1024):
                            digest.update(block)
                        contents.append([rel, digest.hexdigest()])
                if _identity(os.fstat(child)) != _identity(current):
                    _fail("native SDK entry changed during observation")
            finally:
                os.close(child)
        if _identity(os.fstat(fd)) != _identity(before):
            _fail("native SDK directory changed during observation")
    with _native_open(Path(root), directory=True) as (fd, _):
        readable = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
        try:
            visit(readable, Path(root), ".")
        finally:
            os.close(readable)
    return {"entries": len(identities), "identity_sha256": hashlib.sha256(_canonical(identities)).hexdigest(),
            "content_sha256": hashlib.sha256(_canonical(contents)).hexdigest() if content else None}


def build_native_claude_attestation(*, binary_path: Path, sdk_python: Path,
        cli_provision_receipt: Path, cli_receipt_sha256: str,
        sdk_provision_receipt: Path, sdk_receipt_sha256: str) -> dict:
    """Root-only installation observation. Publication is the installer owner's act."""
    if os.geteuid() != _ROOT_UID:
        _fail("native attestation producer requires root")
    # The incumbent host provisioner finalized its root-only receipt at 0600.
    # Consume its pinned bytes without changing that historical artifact.
    cli_source = _json_receipt(cli_provision_receipt, mode=0o600, digest=cli_receipt_sha256)
    sdk_source = _json_receipt(sdk_provision_receipt, mode=0o400, digest=sdk_receipt_sha256)
    if (cli_source.get("schema") != "mastermind.claude_native_host_provision.v1"
            or cli_source.get("status") != "PROVISIONED_NOT_AUTHENTICATED"
            or cli_source.get("binary") != str(binary_path)
            or cli_source.get("version_under_principal") != f"{CLI_VERSION} (Claude Code)"
            or sdk_source.get("status") != "INSTALLED_IMPORT_PROVEN"
            or sdk_source.get("python_path") != str(sdk_python)
            or sdk_source.get("import_probe", {}).get("sdk") != SDK_VERSION):
        _fail("native provision evidence is not the qualified installation")
    cli = _file_observation(binary_path, content=True)
    python = _file_observation(sdk_python, content=True)
    # Hold the full identities from the same descriptors used to hash bytes.
    # Device is boot-local for persistence, but remains a within-call fence.
    cli_runtime = cli["identity"]
    python_runtime = python["identity"]
    if (_runtime_identity(binary_path) != cli_runtime
            or _runtime_identity(sdk_python) != python_runtime
            or cli["sha256"] != cli_source.get("binary_sha256")
            or python["sha256"] != sdk_source.get("python_sha256")
            or not cli["identity"]["mode"] & 0o111
            or not python["identity"]["mode"] & 0o111):
        _fail("native executable differs from its installation receipt")
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": "/var/empty", "LANG": "C"}
    subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(binary_path)],
                   check=True, capture_output=True, timeout=60, env=env)
    signing = subprocess.run(["/usr/bin/codesign", "-dv", "--verbose=4", str(binary_path)],
                   check=True, capture_output=True, timeout=30, env=env)
    if f"TeamIdentifier={CLAUDE_TEAM}" not in signing.stderr.decode().splitlines():
        _fail("native Claude signer is not qualified")
    sdk_root = sdk_python.parent.parent
    if sdk_source.get("target") != str(sdk_root):
        _fail("SDK root differs from provisioned target")
    tree = _sdk_tree(sdk_root, content=True)
    if _runtime_identity(binary_path) != cli_runtime:
        _fail("native CLI changed during attestation")
    if _runtime_identity(sdk_python) != python_runtime:
        _fail("native SDK interpreter changed during attestation")
    cli.update(version=CLI_VERSION, team_identifier=CLAUDE_TEAM)
    # Only the serialized receipt loses its boot-local device identity.
    cli["identity"] = {key: cli_runtime[key] for key in _DURABLE_IDENTITY}
    python["identity"] = {key: python_runtime[key] for key in _DURABLE_IDENTITY}
    return {"schema_version": SCHEMA, "recorded_at": datetime.now(timezone.utc).isoformat(),
            "cli": cli, "sdk": {"python": python, "root": str(sdk_root), "version": SDK_VERSION, **tree},
            "source_receipts": {"cli": {"path": str(cli_provision_receipt), "sha256": cli_receipt_sha256},
                                "sdk": {"path": str(sdk_provision_receipt), "sha256": sdk_receipt_sha256}}}


def _require_shape(document):
    if set(document) != {"schema_version", "recorded_at", "cli", "sdk", "source_receipts"} or document["schema_version"] != SCHEMA:
        _fail("native attestation schema differs")
    cli, sdk = document["cli"], document["sdk"]
    if (not isinstance(cli, dict) or set(cli) != {"path", "identity", "sha256", "version", "team_identifier"}
            or not isinstance(sdk, dict) or set(sdk) != {"python", "root", "version", "entries", "identity_sha256", "content_sha256"}
            or not isinstance(sdk["python"], dict) or set(sdk["python"]) != {"path", "identity", "sha256"}):
        _fail("native attestation fields differ")
    for executable in (cli, sdk["python"]):
        identity = executable["identity"]
        if (not isinstance(identity, dict) or set(identity) != set(_DURABLE_IDENTITY)
                or any(type(v) is not int or v < 0 for v in identity.values())
                or identity["uid"] != _ROOT_UID or identity["mode"] & 0o022 or not identity["mode"] & 0o111):
            _fail("native executable identity is malformed")
    for digest in (cli["sha256"], sdk["python"]["sha256"], sdk["identity_sha256"], sdk["content_sha256"]):
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            _fail("native attestation digest is malformed")
    if type(sdk["entries"]) is not int or not 1 <= sdk["entries"] <= 20000:
        _fail("native SDK count is malformed")
    sources = document["source_receipts"]
    if not isinstance(sources, dict) or set(sources) != {"cli", "sdk"}:
        _fail("native provenance is malformed")
    for source in sources.values():
        if (not isinstance(source, dict) or set(source) != {"path", "sha256"}
                or not isinstance(source["path"], str) or not Path(source["path"]).is_absolute()
                or not isinstance(source["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is None):
            _fail("native provenance is malformed")
    try:
        recorded = datetime.fromisoformat(document["recorded_at"])
        if recorded.utcoffset() != timezone.utc.utcoffset(recorded):
            _fail("native attestation timestamp is not UTC")
    except (TypeError, ValueError):
        _fail("native attestation timestamp is invalid")


def load_native_claude_attestation(receipt_path: Path, *, expected_binary_path: Path,
        expected_owner_gid: int, allowed_versions: frozenset[str], sdk_python: Path) -> BinaryAttestation:
    """Check current CLI/SDK postimage without provider work or credential access."""
    try:
        document = _json_receipt(receipt_path, mode=0o440, gid=expected_owner_gid)
        _require_shape(document)
        cli, sdk = document["cli"], document["sdk"]
        if (cli["path"] != str(expected_binary_path) or cli["version"] != CLI_VERSION
                or cli["version"] not in allowed_versions or cli["team_identifier"] != CLAUDE_TEAM
                or sdk["python"]["path"] != str(sdk_python) or sdk["root"] != str(sdk_python.parent.parent)
                or sdk["version"] != SDK_VERSION):
            _fail("native receipt does not match the configured installation")
        runtime_identities = {}
        for executable in (cli, sdk["python"]):
            current = _file_observation(Path(executable["path"]))["identity"]
            if {key: current[key] for key in _DURABLE_IDENTITY} != executable["identity"]:
                _fail("native executable changed since attestation")
            runtime_identities[executable["path"]] = current
        tree = _sdk_tree(Path(sdk["root"]))
        if tree["entries"] != sdk["entries"] or tree["identity_sha256"] != sdk["identity_sha256"]:
            _fail("native SDK changed since attestation")
        # Re-read root authority after observing its consumers; revocation wins.
        if _json_receipt(receipt_path, mode=0o440, gid=expected_owner_gid) != document:
            _fail("native receipt changed during observation")
        for executable in (cli, sdk["python"]):
            if _file_observation(Path(executable["path"]))["identity"] != runtime_identities[executable["path"]]:
                _fail("native executable changed during SDK observation")
        runtime_identity = _runtime_identity(Path(cli["path"]))
        if runtime_identity != runtime_identities[cli["path"]]:
            _fail("native executable changed during final attestation")
        return BinaryAttestation(path=cli["path"], real_path=cli["path"], version=cli["version"],
            sha256=cli["sha256"], team_identifier=cli["team_identifier"],
            **{key: runtime_identity[key] for key in ("size", "device", "inode", "mode", "uid", "gid", "mtime_ns")})
    except (OSError, ProviderRealmError, FilesystemSecurityError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeAttestationError("native attestation is unavailable or invalid") from exc


# DeepSeek uses a complete pnpm closure. It is intentionally separate from the
# Claude SDK's no-symlink contract above.
DSH_SCHEMA = "mastermind.native_deepseek_attestation/v1"
DSH_ENTRYPOINT = "native_worker.mjs"
DSH_DONOR_SHA = "687f282e8625c6b8d11ff58211a90524be2e4317"
DSH_PROTOCOL_NAME = "deepseek-harness-acp"
DSH_PROTOCOL_VERSION = "0.0.1"
DSH_MODEL_PROVIDER = "deepseek-account"
_DSH_ENTRIES = 200000
_DSH_BYTES = 16 * 1024**3
_DSH_DEPTH = 64
_DSH_PATH_BYTES = 4096
_DSH_MANIFEST_BYTES = 64 * 1024**2
_DSH_INSTALLATION_SEAL = object()


def _deepseek_path(value):
    if (type(value) is not str or not value or len(value.encode()) > _DSH_PATH_BYTES
            or not Path(value).is_absolute() or str(Path(value)) != value
            or ".." in Path(value).parts):
        _fail("native DeepSeek path is not canonical")
    return Path(value)


def _deepseek_links(entries, root):
    """Resolve the observed graph, never follow a live named dependency link."""
    for name, row in entries.items():
        if row["kind"] != "symlink":
            continue
        pending, resolved, hops = list(Path(name).parts), [], 0
        while pending:
            part = pending.pop(0)
            if part in ("", "."):
                continue
            if part == "..":
                if not resolved:
                    _fail("native DeepSeek link escapes package")
                resolved.pop()
                continue
            relative = "/".join(resolved + [part])
            current = entries.get(relative)
            if current is None:
                _fail("native DeepSeek link is dangling")
            if current["kind"] == "symlink":
                hops += 1
                if hops > 40:
                    _fail("native DeepSeek link expansion exceeds bound")
                target = Path(current["target"])
                if target.is_absolute():
                    try:
                        target = target.relative_to(root)
                    except ValueError:
                        _fail("native DeepSeek link escapes package")
                    resolved = []
                pending = list(target.parts) + pending
            else:
                if pending and current["kind"] != "directory":
                    _fail("native DeepSeek link crosses a non-directory")
                resolved.append(part)


def _deepseek_tree(root, *, content=False):
    """Observe the whole bounded package via held ancestors, without imports."""
    root = _deepseek_path(str(root))
    identities, contents, entries = [], {}, {}
    total_bytes, entry_count = 0, 0

    def add(relative, kind, info, target=None):
        nonlocal entry_count
        entry_count += 1
        if entry_count > _DSH_ENTRIES or len(relative.encode()) > _DSH_PATH_BYTES:
            _fail("native DeepSeek package exceeds entry/path bound")
        row = [relative, kind, _durable_identity(info), info.st_nlink]
        if target is not None:
            row.append(target)
        identities.append(row)
        entries[relative] = {"kind": kind, **({"target": target} if target is not None else {})}

    def visit(fd, path, relative, depth):
        nonlocal total_bytes
        if depth > _DSH_DEPTH:
            _fail("native DeepSeek package exceeds depth bound")
        before = os.fstat(fd)
        _check_entry(path, fd, before, directory=True)
        add(relative, "directory", before)
        names = []
        with os.scandir(fd) as stream:
            for entry in stream:
                if len(names) + entry_count >= _DSH_ENTRIES:
                    _fail("native DeepSeek package exceeds entry bound")
                names.append(entry.name)
        for name in sorted(names):
            rel = name if relative == "." else relative + "/" + name
            if len(rel.encode()) > _DSH_PATH_BYTES:
                _fail("native DeepSeek package exceeds path bound")
            child_path = path / name
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                # Symlink mode is normally 0777; it is the link/target custody,
                # not that synthetic writable mode, which this branch admits.
                if (info.st_uid != _ROOT_UID or info.st_nlink != 1
                        or has_macos_acl(child_path, expected_identity=info, allow_symlink=True)):
                    _fail("native DeepSeek link custody is unsafe")
                target = os.readlink(name, dir_fd=fd)
                if not target or len(target.encode()) > _DSH_PATH_BYTES or "\x00" in target:
                    _fail("native DeepSeek link target exceeds bound")
                if _identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != _identity(info):
                    _fail("native DeepSeek link changed during observation")
                add(rel, "symlink", info, target)
                if content:
                    contents[rel] = {"symlink": target}
                continue
            directory = stat.S_ISDIR(info.st_mode)
            if not directory and not stat.S_ISREG(info.st_mode):
                _fail("native DeepSeek package contains a special object")
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            if directory:
                flags |= os.O_DIRECTORY
            child = os.open(name, flags, dir_fd=fd)
            try:
                current = os.fstat(child)
                if _identity(current) != _identity(info):
                    _fail("native DeepSeek entry changed while opening")
                _check_entry(child_path, child, current, directory=directory)
                if directory:
                    visit(child, child_path, rel, depth + 1)
                else:
                    add(rel, "file", current)
                    total_bytes += current.st_size
                    if total_bytes > _DSH_BYTES:
                        _fail("native DeepSeek package exceeds byte bound")
                    if content:
                        digest, consumed = hashlib.sha256(), 0
                        while block := os.read(child, min(1024**2, current.st_size + 1 - consumed)):
                            consumed += len(block)
                            if consumed > current.st_size:
                                _fail("native DeepSeek file grew during observation")
                            digest.update(block)
                        if consumed != current.st_size:
                            _fail("native DeepSeek file changed during observation")
                        contents[rel] = {"sha256": digest.hexdigest(),
                                         "mode": stat.S_IMODE(current.st_mode)}
                if (_identity(os.fstat(child)) != _identity(current)
                        or _identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != _identity(current)):
                    _fail("native DeepSeek entry changed during observation")
            finally:
                os.close(child)
        if _identity(os.fstat(fd)) != _identity(before):
            _fail("native DeepSeek directory changed during observation")

    with _native_open(root, directory=True) as (fd, _):
        readable = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                           dir_fd=fd)
        try:
            visit(readable, root, ".", 0)
        finally:
            os.close(readable)
    _deepseek_links(entries, root)
    return {"entries": entry_count, "total_bytes": total_bytes,
            "identity_sha256": hashlib.sha256(_canonical(identities)).hexdigest(),
            "content_sha256": hashlib.sha256(_canonical(contents)).hexdigest() if content else None,
            **({"files": contents} if content else {})}


def _deepseek_manifest(release):
    path = release / "package-manifest.json"
    with _native_open(path) as (fd, info):
        _check_entry(path, fd, info)
        if not 0 < info.st_size <= _DSH_MANIFEST_BYTES:
            _fail("native DeepSeek manifest size is invalid")
        raw = _read(fd, _DSH_MANIFEST_BYTES)
        if len(raw) != info.st_size:
            _fail("native DeepSeek manifest changed")
        document = json.loads(raw, object_pairs_hook=_pairs,
                              parse_constant=lambda _: _fail("non-finite manifest value"))
    if (type(document) is not dict
            or set(document) != {"schema", "donor_sha", "files", "installed"}
            or document["schema"] != "mastermind.dsh_attended_package_closure.v1"
            or document["donor_sha"] != DSH_DONOR_SHA or document["installed"] is not False
            or type(document["files"]) is not dict):
        _fail("native DeepSeek manifest differs")
    return raw, document


def build_native_deepseek_attestation(*, binary_path: Path, release: Path,
                                      source_repo: Path, source_sha: str) -> dict:
    """Root qualification only; no service/account/session creation or publication."""
    if os.geteuid() != _ROOT_UID:
        _fail("native attestation producer requires root")
    from integrations.deepseek_harness.package_attended import qualify_native_worker_package
    binary_path, release = _deepseek_path(str(binary_path)), _deepseek_path(str(release))
    # Bound and establish root custody before the existing package qualifier
    # enumerates/hashes its manifest. Its publication inventories predate these
    # worker-side package budgets and cannot be the first admission check.
    initial = _deepseek_tree(release)
    qualified = qualify_native_worker_package(
        release=release, source_repo=source_repo, source_sha=source_sha)
    binary = _file_observation(binary_path, content=True)
    runtime = binary["identity"]
    if qualified.get("node") != {"path": str(binary_path), "sha256": binary["sha256"]}:
        _fail("native DeepSeek Node differs from protected build")
    if not runtime["mode"] & 0o111:
        _fail("native DeepSeek Node is not executable")
    # Only the root installation producer executes the already root-custodied
    # Node --version. Worker startup and final write guards never execute it.
    result = subprocess.run([str(binary_path), "--version"], check=True, capture_output=True,
        timeout=30, env={"PATH": "/usr/bin:/bin", "HOME": "/var/empty", "LANG": "C"})
    version = result.stdout.decode("ascii").strip()
    if re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", version) is None or result.stderr:
        _fail("native DeepSeek Node version is invalid")
    raw, manifest = _deepseek_manifest(release)
    tree = _deepseek_tree(release, content=True)
    files = tree.pop("files")
    files.pop("package-manifest.json", None)
    if (files != manifest["files"]
            or hashlib.sha256(raw).hexdigest() != qualified["package_manifest_sha256"]):
        _fail("native DeepSeek package differs from protected qualification")
    entry = _file_observation(release / DSH_ENTRYPOINT, content=True)
    if entry["sha256"] != qualified["entrypoint_sha256"]:
        _fail("native DeepSeek entry differs from protected qualification")
    after = _deepseek_tree(release)
    if (any(after[k] != tree[k] or after[k] != initial[k]
            for k in ("entries", "total_bytes", "identity_sha256"))
            or _runtime_identity(binary_path) != runtime
            or _runtime_identity(release / DSH_ENTRYPOINT) != entry["identity"]
            or _deepseek_manifest(release)[0] != raw):
        _fail("native DeepSeek installation changed during qualification")
    from ops.executive_os.install_source_policy import validate_acceptance_source
    if validate_acceptance_source(source_repo=source_repo, expected_sha=source_sha) != qualified["source_tree"]:
        _fail("native DeepSeek protected source changed during qualification")
    binary.update(version=version, team_identifier=None)
    binary["identity"] = {k: runtime[k] for k in _DURABLE_IDENTITY}
    entry["identity"] = {k: entry["identity"][k] for k in _DURABLE_IDENTITY}
    return {"schema_version": DSH_SCHEMA, "recorded_at": datetime.now(timezone.utc).isoformat(),
            "node": binary, "package": {"root": str(release), "donor_sha": DSH_DONOR_SHA,
                "entry": entry, **tree}, "qualification": qualified}


def _deepseek_digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _deepseek_shape(doc):
    if (type(doc) is not dict
            or set(doc) != {"schema_version", "recorded_at", "node", "package", "qualification"}
            or doc["schema_version"] != DSH_SCHEMA):
        _fail("native DeepSeek attestation schema differs")
    node, package, qualified = doc["node"], doc["package"], doc["qualification"]
    if (type(node) is not dict
            or set(node) != {"path", "identity", "sha256", "version", "team_identifier"}
            or type(package) is not dict
            or set(package) != {"root", "donor_sha", "entry", "entries", "total_bytes",
                                "identity_sha256", "content_sha256"}
            or type(package["entry"]) is not dict
            or set(package["entry"]) != {"path", "identity", "sha256"}
            or type(qualified) is not dict
            or set(qualified) != {"schema", "source_sha", "source_tree", "build_sha256",
                "package_manifest_sha256", "entrypoint_sha256", "native_worker", "node"}
            or qualified["schema"] != "mastermind.dsh_native_worker_qualification/v1"):
        _fail("native DeepSeek attestation fields differ")
    if (type(qualified["node"]) is not dict or set(qualified["node"]) != {"path", "sha256"}
            or qualified["node"] != {"path": node["path"], "sha256": node["sha256"]}):
        _fail("native DeepSeek Node is not the protected executable")
    worker = qualified["native_worker"]
    if (type(worker) is not dict
            or set(worker) != {"schema", "entry", "sha256", "agent_name", "agent_version", "model_provider"}
            or worker["schema"] != "mastermind.dsh_native_worker_entry/v1"
            or worker["entry"] != DSH_ENTRYPOINT
            or worker["agent_name"] != DSH_PROTOCOL_NAME
            or worker["agent_version"] != DSH_PROTOCOL_VERSION
            or worker["model_provider"] != DSH_MODEL_PROVIDER
            or worker["sha256"] != qualified["entrypoint_sha256"]):
        _fail("native DeepSeek fixed entry qualification differs")
    for item in (node, package["entry"]):
        _deepseek_path(item["path"])
        identity = item["identity"]
        if (type(identity) is not dict or set(identity) != set(_DURABLE_IDENTITY)
                or any(type(v) is not int or v < 0 for v in identity.values())
                or identity["uid"] != _ROOT_UID or identity["mode"] & 0o022
                or not _deepseek_digest(item["sha256"])):
            _fail("native DeepSeek executable identity is malformed")
    root = _deepseek_path(package["root"])
    if (package["donor_sha"] != DSH_DONOR_SHA
            or package["entry"]["path"] != str(root / DSH_ENTRYPOINT)
            or package["entry"]["sha256"] != qualified["entrypoint_sha256"]
            or node["team_identifier"] is not None or not node["identity"]["mode"] & 0o111
            or type(node["version"]) is not str
            or re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", node["version"]) is None
            or type(package["entries"]) is not int or not 1 <= package["entries"] <= _DSH_ENTRIES
            or type(package["total_bytes"]) is not int or not 1 <= package["total_bytes"] <= _DSH_BYTES):
        _fail("native DeepSeek installation identity is invalid")
    for key in ("source_sha", "source_tree"):
        if type(qualified[key]) is not str or re.fullmatch(r"[0-9a-f]{40}", qualified[key]) is None:
            _fail("native DeepSeek protected source is invalid")
    for value in (package["identity_sha256"], package["content_sha256"],
                  qualified["build_sha256"], qualified["package_manifest_sha256"],
                  qualified["entrypoint_sha256"]):
        if not _deepseek_digest(value):
            _fail("native DeepSeek digest is malformed")
    try:
        recorded = datetime.fromisoformat(doc["recorded_at"])
        if recorded.utcoffset() != timezone.utc.utcoffset(recorded):
            _fail("native DeepSeek attestation timestamp is not UTC")
    except (TypeError, ValueError):
        _fail("native DeepSeek attestation timestamp is invalid")


def _deepseek_receipt_observation(path):
    with _native_open(path) as (fd, info):
        _check_entry(path, fd, info)
        if not 0 < info.st_size <= _LIMIT:
            _fail("native DeepSeek receipt exceeds its bound")
        raw = _read(fd, _LIMIT)
        if len(raw) != info.st_size:
            _fail("native DeepSeek receipt changed during read")
        return {"path": str(path), "identity": _identity(info),
                "sha256": hashlib.sha256(raw).hexdigest()}


def _observe_deepseek(receipt_path, binary_path, release, gid, versions, *,
                      expected_receipt=None, expected_binary=None):
    receipt = _deepseek_receipt_observation(receipt_path)
    if expected_receipt is not None and receipt != expected_receipt:
        _fail("native DeepSeek receipt changed since binding")
    doc = _json_receipt(receipt_path, mode=0o440, gid=gid, digest=receipt["sha256"])
    _deepseek_shape(doc)
    node, package = doc["node"], doc["package"]
    if (node["path"] != str(binary_path) or package["root"] != str(release)
            or node["version"] not in versions):
        _fail("native DeepSeek receipt differs from configured installation")
    current = {}
    for item in (node, package["entry"]):
        observation = _file_observation(Path(item["path"]))["identity"]
        if {k: observation[k] for k in _DURABLE_IDENTITY} != item["identity"]:
            _fail("native DeepSeek executable changed since attestation")
        current[item["path"]] = observation
    tree = _deepseek_tree(release)
    if any(tree[k] != package[k] for k in ("entries", "total_bytes", "identity_sha256")):
        _fail("native DeepSeek package changed since attestation")
    if _deepseek_receipt_observation(receipt_path) != receipt:
        _fail("native DeepSeek receipt changed during observation")
    for path, identity in current.items():
        if _runtime_identity(Path(path)) != identity:
            _fail("native DeepSeek executable changed during package observation")
    runtime = current[node["path"]]
    binary = BinaryAttestation(path=node["path"], real_path=node["path"], version=node["version"],
        sha256=node["sha256"], team_identifier=None,
        **{k: runtime[k] for k in ("size", "device", "inode", "mode", "uid", "gid", "mtime_ns")})
    if expected_binary is not None and binary != expected_binary:
        _fail("native DeepSeek Node changed since binding")
    return doc, binary, receipt


# A nominal, revalidating source capability; a JSON blob cannot construct it.
import dataclasses as _dataclasses


@_dataclasses.dataclass(frozen=True, repr=False)
class NativeDeepSeekInstallation:
    binary: BinaryAttestation
    release: Path
    entrypoint: Path
    source_digest: str
    source_sha: str
    package_manifest_sha256: str
    donor_sha: str
    _receipt_path: Path
    _receipt: object = _dataclasses.field(repr=False, compare=False)
    _gid: int = _dataclasses.field(repr=False)
    _versions: frozenset[str] = _dataclasses.field(repr=False)
    _seal: object = _dataclasses.field(repr=False, compare=False)

    def require_current(self):
        if self._seal is not _DSH_INSTALLATION_SEAL:
            _fail("native DeepSeek installation capability is absent")
        receipt = json.loads(self._receipt)
        if (self.entrypoint != self.release / DSH_ENTRYPOINT
                or self.source_digest != receipt["sha256"]):
            _fail("native DeepSeek public binding differs from its original receipt")
        document, _, _ = _observe_deepseek(
            self._receipt_path, Path(self.binary.path), self.release,
            self._gid, self._versions, expected_receipt=receipt, expected_binary=self.binary)
        if (self.source_sha != document["qualification"]["source_sha"]
                or self.package_manifest_sha256 != document["qualification"]["package_manifest_sha256"]
                or self.donor_sha != document["package"]["donor_sha"]):
            _fail("native DeepSeek source identity differs from its original receipt")


def load_native_deepseek_attestation(receipt_path: Path, *, expected_binary_path: Path,
        expected_release: Path, expected_owner_gid: int,
        allowed_versions: frozenset[str]) -> NativeDeepSeekInstallation:
    """No Git, Node, SDK/provider import, credentials, or subprocess on this path."""
    try:
        receipt_path, binary_path, release = map(_deepseek_path,
            map(str, (receipt_path, expected_binary_path, expected_release)))
        if (type(expected_owner_gid) is not int or expected_owner_gid <= 0
                or type(allowed_versions) is not frozenset or not 1 <= len(allowed_versions) <= 4
                or any(type(v) is not str or re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", v) is None
                       for v in allowed_versions)):
            _fail("native DeepSeek loader configuration is invalid")
        document, binary, receipt = _observe_deepseek(receipt_path, binary_path, release,
                                               expected_owner_gid, allowed_versions)
        return NativeDeepSeekInstallation(binary, release, release / DSH_ENTRYPOINT,
            receipt["sha256"], document["qualification"]["source_sha"],
            document["qualification"]["package_manifest_sha256"], document["package"]["donor_sha"], receipt_path,
            _canonical(receipt), expected_owner_gid,
            allowed_versions, _DSH_INSTALLATION_SEAL)
    except (OSError, ProviderRealmError, FilesystemSecurityError, KeyError, TypeError,
            UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeAttestationError("native DeepSeek attestation is unavailable or invalid") from exc
