"""Prepare and import web assets inside the existing exact-SHA release owner.

Preparation is a root-owned build attestation: source is a clean protected Git
archive, npm runs as the existing non-root operator, and only captured output
bytes are published. It proves that build, not Auth0 registration or enrollment.
Import never builds, changes a sealed release, or owns a service lifecycle.

Two explicitly supplied PUBLIC Launch inputs may enable an immutable operator
Launch binding: the exact qualified Executive resource (the public
OS_EXECUTIVE_RESOURCE constant) and one bounded canonical closed Launch
manifest read from an explicit sealed file. Both absent keeps the historical
read-only default build and its closed v1 receipt; both present produces a
separate closed schema v2 receipt that binds the exact resource and canonical
manifest bytes. An enabled recipe is build-input evidence only: it is never
user permission, Auth0 authority, or live Launch capability. Caller VITE
environment is never inherited; only the exact paired inputs enter the build.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.executive_os.executive_mcp_entry import (OS_EXECUTIVE_RESOURCE, build_os_asset_manifest,
                                                  require_sealed_path)
from ops.executive_os.install_source_policy import InstallSourcePolicyError, validate_acceptance_source, _git
from control_plane.fs_security import FilesystemSecurityError, has_macos_acl

SCHEMA = "mastermind.os_web_build.v1"
LAUNCH_SCHEMA = "mastermind.os_web_build.launch.v2"
LAUNCH_MODE = "web+launch"
LAUNCH_RESOURCE_ENV = "VITE_MM_EXECUTIVE_RESOURCE"
LAUNCH_CONFIG_ENV = "VITE_MM_LAUNCH_CONFIG"
# The incumbent TS Launch decoder accepts raw strings up to 16384 UTF-16 code
# units, but this closed receipt is read back through a 16384-byte budget that
# must also carry source, builder and asset evidence. Canonical manifest inputs
# are therefore capped below so a fully populated enabled receipt always fits;
# larger inputs refuse before the build instead of being silently truncated.
LAUNCH_MANIFEST_MAX_BYTES = 4096
LAUNCH_MANIFEST_MAX_UTF16 = 16384
RECEIPT_MAX_BYTES = 16384
DIST = "app/mastermind_os/dist"
RECEIPT = "build-receipt.json"
INSTALLED_RECEIPT = "app/mastermind_os/web-build-receipt.json"
RECIPE = ["npm ci --ignore-scripts", "npm run build"]
CONTROL_TEMPLATE = "ops/executive_os/control.json.template"
INPUTS = ("app/mastermind_os/package.json", "app/mastermind_os/package-lock.json",
          "app/mastermind_os/vite.config.ts", "app/mastermind_os/src/public-config.ts",
          "control_plane/fs_security.py", CONTROL_TEMPLATE,
          "ops/executive_os/os_release_assets.py", "ops/executive_os/executive_mcp_entry.py",
          "integrations/mastermind_executive_app/os_assets.py")
# Enabled receipts bind the exact decoder law that qualified their manifest.
# The historical v1 input set is unchanged for default-viewer compatibility.
LAUNCH_INPUTS = (*INPUTS, "app/mastermind_os/src/launch-config.ts")


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _require_root():
    if os.geteuid() != 0:
        raise ValueError("asset preparation/import requires the release owner")


def _client(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_-]{8,128}", value) is None:
        raise ValueError("real public SPA client input required")
    return value


def _source_inputs(repo, sha, *, names=INPUTS):
    return {name: _hash(_git(repo, "show", f"{sha}:{name}").stdout.encode()) for name in names}


def _reserved_service_uids(repo, sha):
    # Preserve the closed Control-to-ingress reservation, including the gaps,
    # from the same source generation as the build. The protected template
    # owns those topology identities; the asset preparer does not assign them.
    template = json.loads(_git(repo, "show", f"{sha}:{CONTROL_TEMPLATE}").stdout)
    first, last = template["control_uid"], template["ceo_ingress_app_peer_uid"]
    if type(first) is not int or type(last) is not int or first <= 0 or last < first:
        raise ValueError("source service identity reservation refused")
    return range(first, last + 1)


def _no_acl(path, before, *, descriptor=None):
    try:
        if has_macos_acl(path, expected_identity=before, descriptor=descriptor):
            raise ValueError("asset path has a macOS ACL")
    except FilesystemSecurityError as exc:
        raise ValueError("asset ACL observation refused") from exc


def _sealed_path(path, *, directory=False):
    """POSIX and descriptor-bound ACL checks for the entire trusted chain.

    An ACL can grant writes without changing mode0444/0755. Reject every ACL,
    query failure and ownership/identity drift rather than inheriting caller-write access
    into a root-owned artifact or laundering ACL-bearing origin bytes at import.
    The existing observer is a no-op off Darwin, preserving Linux behavior.
    """
    require_sealed_path(path, directory=directory)
    for node in (path, *path.parents):
        before = node.lstat()
        _no_acl(node, before)
        after = node.lstat()
        metadata = lambda s: (s.st_dev, s.st_ino, s.st_uid, s.st_gid, s.st_mode)
        if metadata(before) != metadata(after):
            raise ValueError("asset path metadata changed during ACL observation")
        if before.st_ctime_ns != after.st_ctime_ns:
            if not stat.S_ISDIR(before.st_mode):
                raise ValueError("asset path metadata changed during ACL observation")
            # A separate root publication can change an ancestor's directory
            # entries and ctime without changing its custody. Observe its ACL
            # again so an ACL added during the first read is still refused.
            # File-byte stability is checked separately by _read on its fd.
            _no_acl(node, after)
            if metadata(after) != metadata(node.lstat()):
                raise ValueError("asset path metadata changed during ACL observation")
    require_sealed_path(path, directory=directory)


def _read(path, maximum=4 * 1024 * 1024):
    # Nonblocking prevents a replaced special file from hanging qualification.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= maximum:
            raise ValueError("asset file type, link count or budget refused")
        _no_acl(path, before, descriptor=fd)
        chunks, size = [], 0
        while size <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - size))
            if not part:
                break
            chunks.append(part)
            size += len(part)
        data = b"".join(chunks)
        after = os.fstat(fd)
        _no_acl(path, after, descriptor=fd)
        current = path.lstat()
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(current) or len(data) != before.st_size:
            raise ValueError("asset bytes changed during capture")
        return data
    finally:
        os.close(fd)


def _capture_dist(source, *, sealed):
    root = source / DIST
    if root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root:
        raise ValueError("asset directory refused")
    files, directories = {}, set()
    for path in root.rglob("*"):
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            directories.add(path.relative_to(root).as_posix())
            if sealed:
                _sealed_path(path, directory=True)
        elif stat.S_ISREG(info.st_mode):
            if sealed:
                _sealed_path(path)
            files[path.relative_to(root).as_posix()] = _read(path)
        else:
            raise ValueError("asset links or special files refused")
    if sealed:
        _sealed_path(root, directory=True)
    # Validate the captured snapshot with the incumbent validator, never reopen
    # original assets for copying. Extra directories remain part of the check.
    with tempfile.TemporaryDirectory(prefix="mmos-asset-check-") as temp:
        check = Path(temp)
        for name in sorted(directories):
            (check / DIST / name).mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            target = check / DIST / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        actual = build_os_asset_manifest(check)
    return actual, files


def _archive(repo, sha, destination):
    completed = subprocess.run(["/usr/bin/git", "--no-optional-locks", "-c", f"safe.directory={repo}",
                                "-C", str(repo), "archive", sha, "app/mastermind_os"],
                               capture_output=True, check=True, timeout=30)
    if len(completed.stdout) > 128 * 1024 * 1024:
        raise ValueError("app source archive exceeds budget")
    with tarfile.open(fileobj=io.BytesIO(completed.stdout)) as archive:
        for member in archive.getmembers():
            name = Path(member.name)
            if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()):
                raise ValueError("app source archive topology refused")
            if any(part in {"node_modules", "dist"} or part.startswith(".env") for part in name.parts):
                raise ValueError("app source archive includes generated or dotenv inputs")
        archive.extractall(destination, filter="data")


def _build(app, *, build_user, node, npm_cli, web_client_id, reserved_service_uids,
           executive_resource=None, launch_manifest=None):
    if executive_resource is not None or launch_manifest is not None:
        if executive_resource is None or launch_manifest is None:
            raise ValueError("enabled Launch build requires the complete qualified input pair")
    operator = pwd.getpwnam(build_user)
    if operator.pw_uid <= 0 or operator.pw_uid in reserved_service_uids:
        raise ValueError("build requires an existing non-service operator")
    # These tools execute only after dropping to the trusted existing operator.
    # Homebrew's operator-owned runtime is valid; do not require new root Node
    # provisioning or execute its npm under root. Bind selected physical files
    # and their pre/post bytes to this build attestation instead.
    node, npm_cli = Path(node).resolve(strict=True), Path(npm_cli).resolve(strict=True)
    tools = {}
    for path in (node, npm_cli):
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, operator.pw_uid)
                or info.st_mode & 0o022 or info.st_nlink != 1):
            raise ValueError("operator build tool custody refused")
        tools[str(path)] = _hash(_read(path, maximum=256 * 1024 * 1024))
    if not os.access(node, os.X_OK):
        raise ValueError("build Node executable refused")
    workspace = app.parents[1]
    # npm rejects loading one pathname for two configuration scopes. Use two
    # distinct empty files so neither scope reads the operator's saved config.
    user_config = workspace / ".npm-user-config"
    global_config = workspace / ".npm-global-config"
    for config in (user_config, global_config):
        with config.open("x"):
            pass
        config.chmod(0o444)
    for path in [workspace, *workspace.rglob("*")]:
        os.chown(path, operator.pw_uid, operator.pw_gid, follow_symlinks=False)
    # The build environment is closed by construction: ambient VITE variables
    # are never inherited, and the only Launch inputs are the exact qualified
    # pair already validated before the build was allowed to start.
    env = {"PATH": f"{node.parent}:/usr/bin:/bin", "HOME": str(workspace), "LC_ALL": "C",
           "npm_config_cache": str(workspace / ".npm-cache"), "npm_config_userconfig": str(user_config),
           "npm_config_globalconfig": str(global_config), "VITE_MM_WEB_CLIENT_ID": _client(web_client_id)}
    if executive_resource is not None:
        env[LAUNCH_RESOURCE_ENV] = executive_resource
        env[LAUNCH_CONFIG_ENV] = launch_manifest.decode("utf-8")
    for args in (("ci", "--ignore-scripts"), ("run", "build")):
        subprocess.run([str(node), str(npm_cli), *args], cwd=app, env=env, check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=300, user=operator.pw_uid, group=operator.pw_gid, extra_groups=[])
    for path, digest in tools.items():
        if _hash(_read(Path(path), maximum=256 * 1024 * 1024)) != digest:
            raise ValueError("operator build tool changed")
    return {"operator_uid": operator.pw_uid, "tools": tools}


def _publish_file(path, data):
    missing = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    _sealed_path(parent, directory=True)
    for directory in reversed(missing):
        directory.mkdir(mode=0o755)
        directory.chmod(0o755)
        _sealed_path(directory, directory=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o444)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            _no_acl(path, os.fstat(handle.fileno()), descriptor=handle.fileno())
    except Exception:
        # Retain an own partial artifact; do not pathname-delete a replacement.
        raise


_LAUNCH_ROOT_KEYS = frozenset(("v", "workstream", "priority", "projects", "profiles",
                               "attemptLimit", "allowedWritePaths", "validation"))
_LAUNCH_VALIDATION_KEYS = frozenset(("pytest_targets", "compileall_paths", "git_diff_check"))


def _utf16_length(value):
    # The incumbent decoder measures raw.length in UTF-16 code units; Python
    # string length counts code points, so astral characters must count twice.
    return sum(2 if ord(character) > 0xFFFF else 1 for character in value)


def _launch_string(value, maximum=256):
    if type(value) is not str or not 0 < _utf16_length(value) <= maximum:
        return None
    if any(ord(character) <= 0x1F or ord(character) == 0x7F for character in value):
        return None
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        return None
    return value


def _launch_list(value):
    if type(value) is not list or len(value) > 16:
        return None
    if any(_launch_string(item) is None for item in value):
        return None
    return value


def _launch_paths(value):
    if _launch_list(value) is None:
        return None
    for path in value:
        if path.startswith("/") or "\\" in path:
            return None
        if any(segment in ("", ".", "..", ".git") for segment in path.split("/")):
            return None
    return value


def _launch_choices(value, *, profile):
    if type(value) is not list or not 0 < len(value) <= 16:
        return None
    refs = []
    for choice in value:
        if type(choice) is not dict or set(choice) != {"ref", "label"}:
            return None
        if _launch_string(choice["label"], 120) is None or _launch_string(choice["ref"], 64) is None:
            return None
        if profile:
            if choice["ref"] not in ("research_only", "bounded_code_change"):
                return None
        elif re.fullmatch(r"[a-z][a-z0-9._-]{1,63}", choice["ref"]) is None:
            return None
        refs.append(choice["ref"])
    if len(set(refs)) != len(refs):
        return None
    return value


def _decode_launch_binding(parsed):
    """Mirror app/mastermind_os/src/launch-config.ts decodeLaunchBindingConfig.

    Booleans are not integers, unknown fields and duplicate keys refuse, and
    profile/write-path/validation coherence follows the TS decoder exactly.
    """
    if type(parsed) is not dict or any(key not in _LAUNCH_ROOT_KEYS for key in parsed):
        return None
    if type(parsed["v"]) is not int or parsed["v"] != 1:
        return None
    if (_launch_string(parsed["workstream"], 72) is None
            or re.fullmatch(r"WS:[A-Z0-9][A-Za-z0-9._-]{1,63}", parsed["workstream"]) is None):
        return None
    if type(parsed["priority"]) is not int or not -100 <= parsed["priority"] <= 100:
        return None
    if _launch_choices(parsed["projects"], profile=False) is None:
        return None
    if _launch_choices(parsed["profiles"], profile=True) is None:
        return None
    if "attemptLimit" in parsed:
        limit = parsed["attemptLimit"]
        if type(limit) is not int or limit not in (1, 2, 3):
            return None
    if "allowedWritePaths" in parsed and _launch_paths(parsed["allowedWritePaths"]) is None:
        return None
    if "validation" in parsed:
        validation = parsed["validation"]
        if type(validation) is not dict or any(key not in _LAUNCH_VALIDATION_KEYS for key in validation):
            return None
        if "pytest_targets" in validation and _launch_list(validation["pytest_targets"]) is None:
            return None
        if "compileall_paths" in validation and _launch_paths(validation["compileall_paths"]) is None:
            return None
        if "git_diff_check" in validation and type(validation["git_diff_check"]) is not bool:
            return None
    write_count = len(parsed["allowedWritePaths"]) if "allowedWritePaths" in parsed else 0
    validation = parsed.get("validation") or {}
    has_validation = bool(validation.get("pytest_targets") or validation.get("compileall_paths")
                          or validation.get("git_diff_check"))
    for profile in parsed["profiles"]:
        if profile["ref"] == "research_only" and (write_count or has_validation):
            return None
        if profile["ref"] == "bounded_code_change" and (not write_count or not has_validation):
            return None
    return parsed


def _reject_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate JSON key in launch manifest")
        seen[key] = value
    return seen


def _no_surrogates(value):
    if type(value) is str:
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("launch manifest contains an unpaired Unicode surrogate")
    elif type(value) is list:
        for item in value:
            _no_surrogates(item)
    elif type(value) is dict:
        for key, item in value.items():
            _no_surrogates(key)
            _no_surrogates(item)


def decode_launch_manifest(raw):
    """Validate exact canonical public Launch manifest bytes; return those bytes.

    The canonical serialization convention is the incumbent receipt encoding:
    UTF-8, sorted keys, compact separators, non-ASCII escaped, one trailing
    newline. Input bytes must already be exactly that encoding; they are never
    rewritten. Every refusal below happens before any build effect.
    """
    if type(raw) is not bytes and type(raw) is not bytearray:
        raise ValueError("launch manifest input must be exact canonical bytes")
    raw = bytes(raw)
    if not 0 < len(raw) <= LAUNCH_MANIFEST_MAX_BYTES:
        raise ValueError(f"launch manifest must be 1..{LAUNCH_MANIFEST_MAX_BYTES} canonical UTF-8 bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("launch manifest must be UTF-8") from exc
    if _utf16_length(text) > LAUNCH_MANIFEST_MAX_UTF16:
        raise ValueError("launch manifest exceeds the incumbent decoder UTF-16 code-unit limit")
    parsed = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    _no_surrogates(parsed)
    if raw != _canonical(parsed):
        raise ValueError("launch manifest bytes are not the canonical JSON encoding")
    if _decode_launch_binding(parsed) is None:
        raise ValueError("launch manifest refused by the incumbent Launch decoder law")
    return raw


def _validate_executive_resource(value):
    # Only the exact protected public constant is qualified; a blank or
    # different URL is not a resource swap surface.
    if type(value) is not str or value != OS_EXECUTIVE_RESOURCE:
        raise ValueError("executive resource must be the exact qualified OS resource")
    return value


def _public_launch_inputs(executive_resource, launch_manifest):
    """Return the qualified pair, or (None, None) for the default read-only build."""
    if executive_resource is None and launch_manifest is None:
        return None, None
    if executive_resource is None or launch_manifest is None:
        raise ValueError("enabled Launch build inputs require both the exact resource and one canonical manifest")
    return _validate_executive_resource(executive_resource), decode_launch_manifest(launch_manifest)


def _receipt_launch_inputs(receipt):
    """Discriminate the closed receipt version and revalidate its Launch binding."""
    if type(receipt) is not dict:
        raise ValueError("build provenance differs from target source")
    schema = receipt.get("schema")
    if schema == SCHEMA:
        # Historical v1 receipts qualify the default read-only view only; they
        # never carry, and can never be promoted to, Launch evidence.
        return None, None
    if schema == LAUNCH_SCHEMA:
        resource = _validate_executive_resource(receipt.get("executive_resource"))
        config = receipt.get("launch_config")
        if type(config) is not str:
            raise ValueError("closed Launch input binding refused")
        manifest = decode_launch_manifest(config.encode("utf-8"))
        if receipt.get("launch_config_sha256") != _hash(manifest):
            raise ValueError("closed Launch input binding refused")
        return resource, manifest
    raise ValueError("build provenance differs from target source")


def prepare(*, source_repo, expected_sha, web_client_id, output, build_user, node, npm_cli,
            executive_resource=None, launch_manifest=None):
    _require_root()
    source_repo, output = Path(source_repo), Path(output)
    _sealed_path(output.parent, directory=True)
    tree = validate_acceptance_source(source_repo=source_repo, expected_sha=expected_sha)
    # Validate the complete public input pair before any build effect.
    executive_resource, launch_manifest = _public_launch_inputs(executive_resource, launch_manifest)
    inputs = _source_inputs(source_repo, expected_sha,
                            names=LAUNCH_INPUTS if executive_resource is not None else INPUTS)
    for name in (*INPUTS[-3:], "control_plane/fs_security.py"):
        if inputs[name] != _hash((ROOT / name).read_bytes()):
            raise ValueError("preparer is not the exact source generation")
    _client(web_client_id)
    if output.exists() or output.is_symlink():
        raise ValueError("build artifact already exists")
    with tempfile.TemporaryDirectory(prefix=".os-web-build-", dir=output.parent) as temp:
        work = Path(temp)
        _archive(source_repo, expected_sha, work)
        builder = _build(work / "app/mastermind_os", build_user=build_user, node=node, npm_cli=npm_cli,
                         web_client_id=web_client_id,
                         reserved_service_uids=_reserved_service_uids(source_repo, expected_sha),
                         executive_resource=executive_resource, launch_manifest=launch_manifest)
        actual, files = _capture_dist(work, sealed=False)
        if "asset-manifest.json" in files:
            raise ValueError("build must not supply its own asset manifest")
        # Recheck the source after the bounded build. Archive bytes are the only
        # source executed; ignored dotenv or checkout dist never enter it.
        if validate_acceptance_source(source_repo=source_repo, expected_sha=expected_sha) != tree:
            raise ValueError("source changed during preparation")
        receipt = {"schema": SCHEMA, "source_sha": expected_sha, "source_tree": tree,
                   "source_inputs": inputs, "mode": "web", "recipe": RECIPE,
                   "builder": builder,
                   "web_client_id": web_client_id, "asset_manifest_sha256": _hash(_canonical(actual))}
        if executive_resource is not None:
            receipt = {"schema": LAUNCH_SCHEMA, "source_sha": expected_sha, "source_tree": tree,
                       "source_inputs": inputs, "mode": LAUNCH_MODE, "recipe": RECIPE,
                       "builder": builder, "web_client_id": web_client_id,
                       "asset_manifest_sha256": _hash(_canonical(actual)),
                       "executive_resource": executive_resource,
                       "launch_config": launch_manifest.decode("utf-8"),
                       "launch_config_sha256": _hash(launch_manifest)}
        receipt_bytes = _canonical(receipt)
        if len(receipt_bytes) > RECEIPT_MAX_BYTES:
            raise ValueError("closed build receipt exceeds the qualified budget")
        output.mkdir(mode=0o755)
        for name, data in files.items():
            _publish_file(output / DIST / name, data)
        _publish_file(output / DIST / "asset-manifest.json", _canonical(actual))
        _publish_file(output / RECEIPT, receipt_bytes)
    return _hash(receipt_bytes)


@dataclass(frozen=True)
class AssetBundle:
    files: dict[str, bytes]
    receipt: bytes
    digest: str


def qualify(bundle, *, expected_sha, tree_sha, source_repo, expected_digest=None):
    bundle = Path(bundle)
    _sealed_path(bundle, directory=True)
    _sealed_path(bundle / RECEIPT)
    receipt_bytes = _read(bundle / RECEIPT, RECEIPT_MAX_BYTES)
    receipt = json.loads(receipt_bytes)
    launch_resource, _ = _receipt_launch_inputs(receipt)
    required = {"schema", "source_sha", "source_tree", "source_inputs", "mode", "recipe", "builder",
                "web_client_id", "asset_manifest_sha256"}
    if launch_resource is not None:
        required = required | {"executive_resource", "launch_config", "launch_config_sha256"}
    if (type(receipt) is not dict or set(receipt) != required
            or receipt["schema"] not in (SCHEMA, LAUNCH_SCHEMA)
            or receipt["source_sha"] != expected_sha or receipt["source_tree"] != tree_sha
            or receipt["mode"] != (LAUNCH_MODE if launch_resource is not None else "web")
            or receipt["recipe"] != RECIPE
            or _git(source_repo, "rev-parse", f"{expected_sha}^{{tree}}").stdout.strip() != tree_sha
            or receipt["source_inputs"] != _source_inputs(
                source_repo, expected_sha,
                names=LAUNCH_INPUTS if launch_resource is not None else INPUTS)):
        raise ValueError("build provenance differs from target source")
    _client(receipt["web_client_id"])
    builder = receipt["builder"]
    if (type(builder) is not dict or set(builder) != {"operator_uid", "tools"}
            or type(builder["operator_uid"]) is not int or builder["operator_uid"] <= 0
            or builder["operator_uid"] in _reserved_service_uids(source_repo, expected_sha)
            or type(builder["tools"]) is not dict
            or len(builder["tools"]) != 2
            or any(type(path) is not str or type(digest) is not str or not Path(path).is_absolute()
                   or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                   for path, digest in builder["tools"].items())):
        raise ValueError("trusted non-root build attestation refused")
    actual, files = _capture_dist(bundle, sealed=True)
    manifest = files.get("asset-manifest.json")
    if manifest is None or json.loads(manifest) != actual or _hash(manifest) != receipt["asset_manifest_sha256"]:
        raise ValueError("asset manifest differs from captured bytes")
    # A closed artifact root cannot smuggle any other installation file.
    expected_paths = {"app", "app/mastermind_os", DIST, RECEIPT,
                      *(f"{DIST}/{name}" for name in files),
                      *(str((Path(DIST) / name).parent) for name in files)}
    for name in list(expected_paths):
        expected_paths.update(str(parent) for parent in Path(name).parents if str(parent) != ".")
    if {str(p.relative_to(bundle)) for p in bundle.rglob("*")} != expected_paths:
        raise ValueError("build artifact topology differs")
    digest = _hash(_canonical({"receipt": _hash(receipt_bytes), "files": {k: _hash(v) for k, v in sorted(files.items())}}))
    if expected_digest is not None and digest != expected_digest:
        raise ValueError("build artifact changed after preflight")
    return AssetBundle(files, receipt_bytes, digest)


def compare_existing(checked, release):
    release = Path(release)
    _sealed_path(release, directory=True)
    _sealed_path(release / INSTALLED_RECEIPT)
    _, files = _capture_dist(release, sealed=True)
    if files != checked.files or _read(release / INSTALLED_RECEIPT, RECEIPT_MAX_BYTES) != checked.receipt:
        raise ValueError("existing sealed release assets differ")


def import_assets(checked, staging):
    staging = Path(staging)
    if os.path.lexists(staging / ".executive-release-manifest.json") or os.path.lexists(staging / DIST):
        raise ValueError("cannot amend a sealed or asset-bearing release")
    _sealed_path(staging, directory=True)
    for name, data in checked.files.items():
        _publish_file(staging / DIST / name, data)
    _publish_file(staging / INSTALLED_RECEIPT, checked.receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check", "import"))
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--tree-sha")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--release-root", type=Path)
    parser.add_argument("--expected-digest")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--web-client-id")
    parser.add_argument("--executive-resource")
    parser.add_argument("--launch-manifest", type=Path)
    parser.add_argument("--build-user")
    parser.add_argument("--node", type=Path)
    parser.add_argument("--npm-cli", type=Path)
    args = parser.parse_args()
    _require_root()
    if args.command == "prepare":
        if None in (args.output, args.web_client_id, args.build_user, args.node, args.npm_cli):
            raise ValueError("preparation inputs required")
        if (args.executive_resource is None) != (args.launch_manifest is None):
            raise ValueError("enabled Launch build inputs require both the exact resource and one canonical manifest")
        launch_manifest = None
        if args.launch_manifest is not None:
            _sealed_path(args.launch_manifest)
            launch_manifest = _read(args.launch_manifest, LAUNCH_MANIFEST_MAX_BYTES)
        print(prepare(source_repo=args.source_repo, expected_sha=args.expected_sha, output=args.output,
                      web_client_id=args.web_client_id, build_user=args.build_user, node=args.node,
                      npm_cli=args.npm_cli, executive_resource=args.executive_resource,
                      launch_manifest=launch_manifest))
    else:
        if args.bundle is None or args.tree_sha is None:
            raise ValueError("qualified artifact inputs required")
        checked = qualify(args.bundle, expected_sha=args.expected_sha, tree_sha=args.tree_sha,
                          source_repo=args.source_repo, expected_digest=args.expected_digest)
        if args.command == "import":
            if args.release_root is None:
                raise ValueError("staging destination required")
            import_assets(checked, args.release_root)
        elif args.release_root is not None and os.path.lexists(args.release_root):
            compare_existing(checked, args.release_root)
        print(checked.digest)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, InstallSourcePolicyError, subprocess.SubprocessError):
        print("OS web release assets refused", file=sys.stderr)
        raise SystemExit(65)
