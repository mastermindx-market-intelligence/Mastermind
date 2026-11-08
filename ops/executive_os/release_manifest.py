"""Create or verify the root-owned exact-SHA Executive release manifest.

The manifest freezes the exact installed release closure and may optionally
freeze one closed Hermes runtime installation input alongside it. That member
is data, never self-attestation: it records the interpreter, startup recipe
and role accounts the operator approved for the two Hermes roles.
"""
from __future__ import annotations

import sys

_HERMES_SITE_NAMES = ("site", "sitecustomize", "usercustomize")
_HERMES_EARLY_NO_SITE = False


def _hermes_recipe_is_qualified() -> bool:
    """The fixed Linux CPython 3.12 -I -S -B recipe with no loaded site module.

    A site module that is already loaded means ambient code may have run;
    the recipe is then not qualified, whatever the interpreter flags say.
    """
    return (sys.implementation.name == "cpython"
            and sys.version_info[:2] == (3, 12)
            and sys.platform.startswith("linux")
            and sys.flags.isolated and sys.flags.no_site and sys.flags.no_user_site
            and sys.flags.dont_write_bytecode and sys.flags.safe_path
            and not any(name in sys.modules and sys.modules[name] is not None
                       for name in _HERMES_SITE_NAMES))


def _install_no_site_sentinels() -> None:
    """Block any later site/sitecustomize/usercustomize import. Idempotent."""
    for name in _HERMES_SITE_NAMES:
        sys.modules[name] = None


# The Hermes runtime entry must execute under the fixed no-site recipe before
# any ordinary import. This is the canonical early policy: it refuses a
# preloaded site/sitecustomize/usercustomize module and installs blocking
# sentinels for them. It runs only for the actual hermes-runtime command, so
# the legacy create/verify entry keeps ordinary module imports. The policy is
# never installed late by importing the initializer. Root dependency preparation
# uses the same early recipe and never enters a native package or model.
if len(sys.argv) > 1 and sys.argv[1] in {"hermes-runtime", "prepare-hermes-dependencies"}:
    if not _hermes_recipe_is_qualified():
        sys.stderr.write("HERMES_RELEASE_SOURCE_UNQUALIFIED\n")
        raise SystemExit(78)
    _install_no_site_sentinels()
    _HERMES_EARLY_NO_SITE = True

import argparse
from contextlib import ExitStack, contextmanager
import errno
import importlib.abc
import importlib.util
import re
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

_RELEASE_ROOT = Path(__file__).parents[2]


def has_macos_acl(*args: Any, **kwargs: Any) -> bool:
    # Legacy create/verify keep their existing helper and path behavior. The
    # isolated Hermes entry must execute no repository import before custody.
    root = _RELEASE_ROOT.resolve()
    if os.fspath(root) not in sys.path:
        sys.path.insert(0, os.fspath(root))
    from control_plane.fs_security import has_macos_acl as observe
    return observe(*args, **kwargs)


SCHEMA_VERSION = "mastermind.executive_release_manifest/v1"
MANIFEST_NAME = ".executive-release-manifest.json"

# The optional frozen member: the operator-approved Hermes runtime
# installation input. It is data the operator supplies, never a claim this
# module makes about the host, an interpreter, an account or a running unit.
HERMES_RUNTIME_SCHEMA = "mastermind.hermes_runtime_installation/v1"
HERMES_RUNTIME_PROFILE = "cpython-3.12-linux-root-prefix-nosite.v1"
HERMES_ROLES = ("mmmeta", "mmsecretary")
HERMES_RUNTIME_KEYS = frozenset(
    {"schema", "bootstrap_python", "launch_python", "startup", "roles"})
_MANIFEST_LEGACY_KEYS = frozenset({"schema_version", "commit_sha", "tree_sha", "entries"})
_MANIFEST_KEYS = _MANIFEST_LEGACY_KEYS | {"hermes_runtime"}
_MAX_HERMES_DOCUMENT = 16 * 1024
_MAX_CLI_ARGUMENT = 64 * 1024

# A path may never name or carry a systemd unit, a unit fragment or a unit
# drop-in directory: those surfaces can redirect an absolute path.
_UNIT_SUFFIXES = (".service", ".socket", ".timer", ".target", ".mount",
                  ".automount", ".swap", ".device", ".slice", ".scope", ".path")
_UNIT_DIRECTORIES = ("/etc/systemd/system", "/run/systemd/system",
                     "/usr/lib/systemd/system", "/lib/systemd/system")
# The same characters the existing root-unit path contract refuses. A frozen
# member must never carry a path that the shared unit recipe cannot render.
_UNSAFE_PATH_CHARACTERS = frozenset(" \r\n\t\"'$\\%;") | {chr(96)}


class ReleaseManifestError(RuntimeError):
    pass


def _has_acl(path: Path, info: os.stat_result) -> bool:
    try:
        return has_macos_acl(
            path,
            expected_identity=info,
            allow_symlink=stat.S_ISLNK(info.st_mode),
        )
    except RuntimeError:
        raise ReleaseManifestError(f"cannot inspect release ACL: {path.name}")


def _validate_owned_info(info: os.stat_result, *, label: str) -> None:
    if info.st_uid != 0 or info.st_gid != 0:
        raise ReleaseManifestError(f"release object is not root:wheel: {label}")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ReleaseManifestError(f"release object is writable by group or other: {label}")


def _release_root(path: Path) -> Path:
    lexical = Path(path)
    info = lexical.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ReleaseManifestError("release root must be a direct real directory")
    _validate_owned_info(info, label=".")
    if stat.S_IMODE(info.st_mode) & 0o055 != 0o055:
        raise ReleaseManifestError("release root must be traversable by both service UIDs")
    if _has_acl(lexical, info):
        raise ReleaseManifestError("release root has a filesystem ACL")
    return lexical.resolve(strict=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entries(root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False):
        base = Path(directory)
        names.sort()
        filenames.sort()
        for name in [*names, *filenames]:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if relative == MANIFEST_NAME:
                continue
            info = path.lstat()
            _validate_owned_info(info, label=relative)
            if _has_acl(path, info):
                raise ReleaseManifestError(f"release object has a filesystem ACL: {relative}")
            common = {
                "path": relative,
                "mode": stat.S_IMODE(info.st_mode),
                "uid": info.st_uid,
                "gid": info.st_gid,
            }
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                if os.path.isabs(target):
                    raise ReleaseManifestError(f"absolute release symlink is forbidden: {relative}")
                resolved = (path.parent / target).resolve(strict=False)
                try:
                    resolved.relative_to(root)
                except ValueError as exc:
                    raise ReleaseManifestError(
                        f"release symlink escapes the release root: {relative}"
                    ) from exc
                result.append({**common, "type": "symlink", "target": target})
            elif stat.S_ISDIR(info.st_mode):
                result.append({**common, "type": "directory"})
            elif stat.S_ISREG(info.st_mode):
                result.append(
                    {
                        **common,
                        "type": "file",
                        "size": info.st_size,
                        "sha256": _sha256_file(path),
                    }
                )
            else:
                raise ReleaseManifestError(f"unsupported release object: {relative}")
    return result


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ReleaseManifestError("release manifest is not canonical") from exc


def _safe_installation_path(value: Any) -> str:
    """One normalized absolute path; no traversal, control or unit surface."""
    if type(value) is not str or not 1 < len(value) <= 4096:
        raise ReleaseManifestError("Hermes installation path is invalid")
    if (not value.startswith("/")
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(c in _UNSAFE_PATH_CHARACTERS for c in value)):
        raise ReleaseManifestError("Hermes installation path is invalid")
    if str(PurePosixPath(value)) != value:
        raise ReleaseManifestError("Hermes installation path is not normalized")
    parts = value.split("/")[1:]
    if any(part in ("", ".", "..") for part in parts):
        raise ReleaseManifestError("Hermes installation path is not normalized")
    if any(part.endswith(_UNIT_SUFFIXES) for part in parts):
        raise ReleaseManifestError("Hermes installation path names a unit")
    if any(value == directory or value.startswith(directory + "/")
           for directory in _UNIT_DIRECTORIES):
        raise ReleaseManifestError("Hermes installation path names a unit directory")
    return value


def _within(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _hermes_binary(value: Any) -> dict[str, str]:
    if type(value) is not dict or set(value) != {"path", "real_path", "sha256"}:
        raise ReleaseManifestError("Hermes runtime interpreter is invalid")
    digest = value["sha256"]
    if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ReleaseManifestError("Hermes runtime interpreter digest is invalid")
    return {
        "path": _safe_installation_path(value["path"]),
        "real_path": _safe_installation_path(value["real_path"]),
        "sha256": digest,
    }


def _hermes_startup(value: Any) -> dict[str, str]:
    if (type(value) is not dict
            or set(value) != {"profile", "prefix", "exec_prefix",
                              "base_prefix", "base_exec_prefix"}):
        raise ReleaseManifestError("Hermes runtime startup is invalid")
    if value["profile"] != HERMES_RUNTIME_PROFILE:
        raise ReleaseManifestError("Hermes runtime startup profile is unqualified")
    startup = {"profile": HERMES_RUNTIME_PROFILE}
    for key in ("prefix", "exec_prefix", "base_prefix", "base_exec_prefix"):
        startup[key] = _safe_installation_path(value[key])
    if startup["base_prefix"] != startup["prefix"]:
        raise ReleaseManifestError("Hermes runtime startup prefix is not a root prefix")
    if startup["base_exec_prefix"] != startup["exec_prefix"]:
        raise ReleaseManifestError("Hermes runtime startup prefix is not a root prefix")
    if not _within(startup["exec_prefix"], startup["prefix"]):
        raise ReleaseManifestError("Hermes runtime startup prefixes disagree")
    return startup


def _hermes_restart(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReleaseManifestError("Hermes runtime restart bound is invalid")
    if type(value) is int and not 0 <= value <= 60:
        raise ReleaseManifestError("Hermes runtime restart bound is invalid")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ReleaseManifestError("Hermes runtime restart bound is invalid") from exc
    if not 0 <= number <= 60:
        raise ReleaseManifestError("Hermes runtime restart bound is invalid")
    return int(number) if number.is_integer() else number


def _hermes_native_gateway(value: Any, *, role: str = "mmsecretary",
                           _defer_consumer: bool = False) -> dict[str, Any]:
    # This bootstrap owner must remain stdlib-only until its held source loader
    # is installed. The runtime contract is checked against these closed values.
    if type(role) is not str or role not in HERMES_ROLES or type(_defer_consumer) is not bool:
        raise ReleaseManifestError("Hermes native role is invalid")
    enrollment_schema = {
        "mmsecretary": "mastermind.hermes_secretary_session_enrollment/v1",
        "mmmeta": "mastermind.hermes_meta_session_enrollment/v1",
    }[role]
    keys = {"schema", "python", "startup", "vendor_root", "import_roots", "dependency_inventory"}
    if type(value) is not dict:
        raise ReleaseManifestError("Hermes native installation is invalid")
    derivation = value.get("vendor_derivation")
    if "vendor_derivation" in value:
        keys = keys | {"vendor_derivation"}
        if (type(derivation) is not dict
                or set(derivation) != {"kind", "base_sha", "patch_sha256", "source_root"}
                or derivation["base_sha"] != "1c0cd667746d3395fe9e1b6c74f8f85952486f18"
                or (derivation["kind"], derivation["patch_sha256"]) not in (
                    ("computer_env_guard", "d17af87e60a1f92a52ef446ad393ce2841c876a28e2ae0580bc7e6db09d6721f"),
                    ("diagnostic_privacy", "ded504ad2d660f14c89527ec74593fcc459485666fbb0994bb92f7b02c878bce"),
                    ("workspace_oauth_privacy", "1d1df9a1fde6654d1690715e52ed10524c6b1b4d9af24b406243324d212146ce"),
                    ("native_eval_inputs", "8c2a20ab5b7dde2bda052ad275a0defe5f5e689b1cabf6e5882c412d948a9211"))):
            raise ReleaseManifestError("Hermes vendor derivation is invalid")
        derivation = dict(derivation, source_root=_safe_installation_path(derivation["source_root"]))
    version = value.get("schema")
    enrollment = None
    consumer = None
    if version in ("mastermind.hermes_native_gateway_installation/v2",
                   "mastermind.hermes_native_gateway_installation/v3"):
        keys = keys | {"session_enrollment"}
        enrollment = value.get("session_enrollment")
        if (type(enrollment) is not dict
                or set(enrollment) != {"schema", "request_id"}
                or enrollment.get("schema") != enrollment_schema):
            raise ReleaseManifestError("Hermes session enrollment is invalid")
        request_id = enrollment["request_id"]
        if (type(request_id) is not str or not 1 <= len(request_id) <= 256
                or any(ord(c) < 32 or ord(c) == 127 for c in request_id)):
            raise ReleaseManifestError("Hermes enrollment request identity is invalid")
        try:
            request_id.encode("utf-8", "strict")
        except UnicodeError:
            raise ReleaseManifestError("Hermes enrollment request identity is invalid") from None
        if version == "mastermind.hermes_native_gateway_installation/v3":
            # The optional qualified consumer. It is a closed, non-secret
            # document: the frozen target material, the mission joins, the
            # approved MCP/public client metadata, the installed enrollment
            # identity and the sealed plugin package. A credential, a bearer
            # template or a client secret cannot be carried by it.
            keys = keys | {"executive_consumer"}
            consumer = value.get("executive_consumer")
            if type(consumer) is not dict:
                raise ReleaseManifestError("Hermes executive consumer is invalid")
            # A structural bootstrap snapshot is opaque, detached and bounded
            # by the complete installation limit. It is never a qualified
            # publication until the same semantic owner runs under held imports.
            consumer = _closed_json(_canonical(consumer))
            # Context v2 imports these native memory bodies. Require the fixed
            # privacy repair even during deferred bootstrap qualification; the
            # held owner separately verifies its full tree and installed receipt.
            if (consumer.get("schema") == "mastermind.hermes_native_executive_consumer/v2"
                    and (derivation is None or derivation["kind"] != "diagnostic_privacy")):
                raise ReleaseManifestError("Hermes context requires diagnostic privacy derivation")
            if (consumer.get("schema") in {"mastermind.hermes_native_executive_consumer/v3", "mastermind.hermes_native_executive_consumer/v4"}
                    and (derivation is None or derivation["kind"] not in {"workspace_oauth_privacy", "native_eval_inputs"})):
                raise ReleaseManifestError("Hermes current context requires Workspace OAuth privacy derivation")
            if not _defer_consumer:
                try:
                    from integrations.hermes_harness.native_executive_consumer import (
                        validate_consumer_publication,
                    )
                    consumer = validate_consumer_publication(consumer)
                    if (consumer["session"]["request_id"] != enrollment["request_id"]
                            or consumer["session"]["role"] != role):
                        raise ValueError("consumer enrollment identity differs")
                except Exception:
                    raise ReleaseManifestError("Hermes executive consumer is invalid") from None
    elif version != "mastermind.hermes_native_gateway_installation/v1":
        raise ReleaseManifestError("Hermes native installation is invalid")
    evaluation_inputs = None
    if "evaluation_inputs" in value:
        keys = keys | {"evaluation_inputs"}
        evaluation_inputs = value["evaluation_inputs"]
        if (type(evaluation_inputs) is not dict or set(evaluation_inputs) != {"schema", "artifact_root"}
                or evaluation_inputs["schema"] != "mastermind.hermes_native_eval_inputs/v1"
                or role != "mmmeta"
                or version != "mastermind.hermes_native_gateway_installation/v3"
                or consumer is None or consumer.get("schema") not in {
                    "mastermind.hermes_native_executive_consumer/v3", "mastermind.hermes_native_executive_consumer/v4"}
                or derivation is None or derivation["kind"] != "native_eval_inputs"):
            raise ReleaseManifestError("Hermes evaluation input selection is invalid")
        evaluation_inputs = {"schema": evaluation_inputs["schema"],
                             "artifact_root": _safe_installation_path(evaluation_inputs["artifact_root"])}
    if derivation is not None and derivation["kind"] == "native_eval_inputs" and evaluation_inputs is None:
        raise ReleaseManifestError("Hermes evaluation derivation requires its selected receiver")
    if set(value) != keys:
        raise ReleaseManifestError("Hermes native installation is invalid")
    binary = _hermes_binary(value["python"])
    startup = _hermes_startup(value["startup"])
    vendor = _safe_installation_path(value["vendor_root"])
    roots = value["import_roots"]
    if type(roots) is not list or not 1 <= len(roots) <= 4:
        raise ReleaseManifestError("Hermes native import roots are invalid")
    roots = [_safe_installation_path(root) for root in roots]
    if (roots[0] != vendor or len(set(roots)) != len(roots)
            or any(a != b and (_within(a, b) or _within(b, a))
                   for a in roots for b in roots)):
        raise ReleaseManifestError("Hermes native import roots overlap")
    inventory = value["dependency_inventory"]
    if (type(inventory) is not dict or set(inventory) != {"path", "sha256", "size"}
            or type(inventory["sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", inventory["sha256"]) is None
            or type(inventory["size"]) is not int
            or not 1 <= inventory["size"] <= 8 * 1024 * 1024):
        raise ReleaseManifestError("Hermes native inventory binding is invalid")
    inventory_path = _safe_installation_path(inventory["path"])
    if any(_within(inventory_path, root) for root in roots):
        raise ReleaseManifestError("Hermes native inventory is inside its own closure")
    if evaluation_inputs is not None and any(
            _within(evaluation_inputs["artifact_root"], root) or _within(root, evaluation_inputs["artifact_root"])
            for root in (*roots, inventory_path, derivation["source_root"])):
        raise ReleaseManifestError("Hermes evaluation store overlaps native source")
    if derivation is not None and (
        any(_within(derivation["source_root"], root) or _within(root, derivation["source_root"])
            for root in roots) or _within(inventory_path, derivation["source_root"])
    ):
        raise ReleaseManifestError("Hermes vendor derivation paths overlap")
    return {"schema": value["schema"], "python": binary, "startup": startup,
            "vendor_root": vendor, "import_roots": roots,
            "dependency_inventory": {"path": inventory_path, "sha256": inventory["sha256"],
                                     "size": inventory["size"]},
            **({"session_enrollment": dict(enrollment)} if enrollment is not None else {}),
            **({"vendor_derivation": derivation} if derivation is not None else {}),
            **({"evaluation_inputs": dict(evaluation_inputs)} if evaluation_inputs is not None else {}),
            **({"executive_consumer": json.loads(json.dumps(consumer))}
               if consumer is not None else {})}


def _hermes_roles(value: Any, *, _defer_consumer: bool = False) -> list[dict[str, Any]]:
    if type(value) is not list or len(value) != len(HERMES_ROLES):
        raise ReleaseManifestError("Hermes runtime roles are invalid")
    rows: list[dict[str, Any]] = []
    for role, row in zip(HERMES_ROLES, value):
        if (type(row) is not dict
                or set(row) not in (
                    {"role", "uid", "gid", "state_dir", "restart_sec",
                     "start_limit_burst", "start_limit_interval_sec"},
                    {"role", "uid", "gid", "state_dir", "restart_sec",
                     "start_limit_burst", "start_limit_interval_sec", "native_gateway"})):
            raise ReleaseManifestError("Hermes runtime role row is invalid")
        if row["role"] != role:
            raise ReleaseManifestError("Hermes runtime role order is invalid")
        native = (_hermes_native_gateway(row["native_gateway"], role=role,
                                         _defer_consumer=_defer_consumer)
                  if "native_gateway" in row else None)
        if (not _defer_consumer and native is not None and "executive_consumer" in native
                and native["executive_consumer"]["session"]["role"] != role):
            raise ReleaseManifestError("Hermes executive consumer role differs")
        uid, gid = row["uid"], row["gid"]
        if type(uid) is not int or not 1 <= uid <= 2 ** 31 - 1:
            raise ReleaseManifestError("Hermes runtime role uid is invalid")
        if type(gid) is not int or not 1 <= gid <= 2 ** 31 - 1:
            raise ReleaseManifestError("Hermes runtime role gid is invalid")
        burst, interval = row["start_limit_burst"], row["start_limit_interval_sec"]
        if type(burst) is not int or not 1 <= burst <= 10:
            raise ReleaseManifestError("Hermes runtime start limit burst is invalid")
        if type(interval) is not int or not 1 <= interval <= 3600:
            raise ReleaseManifestError("Hermes runtime start limit interval is invalid")
        rows.append({
            "role": role, "uid": uid, "gid": gid,
            "state_dir": _safe_installation_path(row["state_dir"]),
            "restart_sec": _hermes_restart(row["restart_sec"]),
            "start_limit_burst": burst,
            "start_limit_interval_sec": interval,
            **({"native_gateway": native} if native is not None else {}),
        })
    if rows[0]["uid"] == rows[1]["uid"] or rows[0]["gid"] == rows[1]["gid"]:
        raise ReleaseManifestError("Hermes runtime role identities are not distinct")
    return rows


def validate_hermes_runtime_installation(value: Any, *, _defer_consumer: bool = False) -> dict[str, Any]:
    """Validate one closed installation input and return its detached form.

    The returned document is canonical: integral restart bounds are
    normalized, the two interpreter documents are required to be equal, and
    no credential, provider, model, environment, command, unit path,
    implementation label or release root is accepted.
    """
    if type(_defer_consumer) is not bool:
        raise ReleaseManifestError("Hermes bootstrap selection is invalid")
    if type(value) is not dict or set(value) != HERMES_RUNTIME_KEYS:
        raise ReleaseManifestError("Hermes runtime installation is invalid")
    if value["schema"] != HERMES_RUNTIME_SCHEMA:
        raise ReleaseManifestError("Hermes runtime installation schema is invalid")
    bootstrap = _hermes_binary(value["bootstrap_python"])
    launch = _hermes_binary(value["launch_python"])
    if bootstrap != launch:
        raise ReleaseManifestError("Hermes runtime interpreter documents differ")
    startup = _hermes_startup(value["startup"])
    for key in ("path", "real_path"):
        if not _within(launch[key], startup["exec_prefix"]):
            raise ReleaseManifestError("Hermes runtime interpreter is outside its prefix")
    document = {
        "schema": HERMES_RUNTIME_SCHEMA,
        "bootstrap_python": bootstrap,
        "launch_python": launch,
        "startup": startup,
        "roles": _hermes_roles(value["roles"], _defer_consumer=_defer_consumer),
    }
    if len(_canonical(document)) > _MAX_HERMES_DOCUMENT:
        raise ReleaseManifestError("Hermes runtime installation exceeds its byte budget")
    return document


def _document(root: Path, commit_sha: str, tree_sha: str,
              *, hermes_runtime: Any = None) -> dict[str, Any]:
    if len(commit_sha) != 40 or len(tree_sha) != 40:
        raise ReleaseManifestError("release commit and tree identities must be exact SHA-1 values")
    value: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "entries": _entries(root),
    }
    if hermes_runtime is not None:
        value["hermes_runtime"] = validate_hermes_runtime_installation(hermes_runtime)
    return value


def create(root: Path, commit_sha: str, tree_sha: str,
           *, hermes_runtime: Any = None) -> Path:
    root = _release_root(root)
    manifest = root / MANIFEST_NAME
    if manifest.exists() or manifest.is_symlink():
        raise ReleaseManifestError("release manifest already exists")
    value = _document(root, commit_sha, tree_sha, hermes_runtime=hermes_runtime)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{MANIFEST_NAME}.", dir=root)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o444)
        if os.geteuid() == 0:
            os.chown(temporary, 0, 0)
        temporary.replace(manifest)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return manifest


class _Unspecified:
    """Ordinary inspection: any present member is validated, nothing expected."""

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return "<unspecified>"


_UNSPECIFIED = _Unspecified()


def verify(root: Path, commit_sha: str, tree_sha: str,
           *, expected_hermes_runtime: Any = _UNSPECIFIED) -> dict[str, Any]:
    """Verify the installed release against its frozen manifest.

    Without an explicit expectation this is ordinary inspection: the whole
    persisted manifest is decoded with the closed decoder, any present
    installation member is validated, and the existing full closure is
    recomputed and compared. An explicit ``None`` requires the member to be
    absent; an explicit document requires exact validated equality. A
    persisted member is never discarded to hide a mismatch.
    """
    root = _release_root(root)
    manifest = root / MANIFEST_NAME
    info = manifest.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ReleaseManifestError("release manifest is not a regular file")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ReleaseManifestError("release manifest is writable by group or other")
    _validate_owned_info(info, label=MANIFEST_NAME)
    if _has_acl(manifest, info):
        raise ReleaseManifestError("release manifest has a filesystem ACL")
    try:
        raw = manifest.read_bytes()
    except OSError as exc:
        raise ReleaseManifestError("release manifest is invalid") from exc
    persisted = _closed_json(raw)
    if type(persisted) is not dict or set(persisted) not in (
            _MANIFEST_LEGACY_KEYS, _MANIFEST_KEYS):
        raise ReleaseManifestError("release manifest is invalid")
    observed = _document(root, commit_sha, tree_sha)
    if any(persisted.get(key) != observed[key] for key in observed):
        raise ReleaseManifestError("installed release differs from its exact-SHA manifest")
    member = None
    if "hermes_runtime" in persisted:
        member = validate_hermes_runtime_installation(persisted["hermes_runtime"])
    if expected_hermes_runtime is not _UNSPECIFIED:
        if expected_hermes_runtime is None:
            if member is not None:
                raise ReleaseManifestError(
                    "installed release manifest hermes runtime differs")
        elif member != validate_hermes_runtime_installation(expected_hermes_runtime):
            raise ReleaseManifestError("installed release manifest hermes runtime differs")
    return persisted



# The Linux runtime consumer shares the existing manifest and release owner.
# This is source custody, not independent interpreter/installed-unit attestation.
_LINUX_RELEASES = Path("/opt/mastermind-executive/releases")
_FIRST_PARTY = ("common", "control_plane", "integrations", "ops", "scripts")
_YAML_ROOT = "ops/native_fabric/quota_continuity/candidate"
_CUSTODY_ROOT = "ops/native_fabric/quota_continuity/candidate"
_MAX_SOURCE = 4 * 1024 * 1024


def _held_identity(info: os.stat_result, directory: bool) -> tuple:
    fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")
    if not directory:
        fields += ("st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
    return tuple(getattr(info, key) for key in fields)


def _linux_source_acl(descriptor: int, directory: bool) -> None:
    """Any ACL attribute or any observation error except ENODATA refuses."""
    names = ("system.posix_acl_access", "system.posix_acl_default") if directory else ("system.posix_acl_access",)
    for name in names:
        try:
            os.getxattr(descriptor, name)
        except OSError as exc:
            if exc.errno == errno.ENODATA:
                continue
            raise ReleaseManifestError("release source ACL is unqualified") from exc
        except (AttributeError, TypeError, ValueError) as exc:
            raise ReleaseManifestError("descriptor ACL observation is unavailable") from exc
        raise ReleaseManifestError("release source has an ACL")


def _closed_json(raw: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ReleaseManifestError("release manifest has a duplicate key")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ReleaseManifestError("release manifest is invalid") from exc


class _HeldReleaseSources:
    """Physical Linux descriptors and manifest-matched immutable source bytes."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.stack = ExitStack()
        self.held: dict[Path, tuple] = {}
        self.sources: dict[str, bytes] = {}
        self.total = 0
        self.closed = False
        try:
            if (not sys.platform.startswith("linux") or self.root.parent != _LINUX_RELEASES
                    or re.fullmatch(r"[0-9a-f]{40}", self.root.name) is None):
                raise ReleaseManifestError("fixed Linux release root is required")
            self.hold(self.root, directory=True)
            raw = self.read(self.root / MANIFEST_NAME, _MAX_SOURCE)
            self._manifest_sha256 = hashlib.sha256(raw).hexdigest()
            document = _closed_json(raw)
            if (type(document) is not dict
                    or set(document) not in (_MANIFEST_LEGACY_KEYS, _MANIFEST_KEYS)
                    or document["schema_version"] != SCHEMA_VERSION
                    or document["commit_sha"] != self.root.name
                    or type(document["tree_sha"]) is not str
                    or re.fullmatch(r"[0-9a-f]{40}", document["tree_sha"]) is None
                    or type(document["entries"]) is not list
                    or not 1 <= len(document["entries"]) <= 16384):
                raise ReleaseManifestError("release manifest identity is invalid")
            self.entries: dict[str, dict] = {}
            common = {"path", "type", "mode", "uid", "gid"}
            for entry in document["entries"]:
                name = entry.get("path") if type(entry) is dict else None
                if (type(name) is not str or not name or len(name) > 4096 or "\\" in name
                        or name.startswith("/") or any(p in ("", ".", "..") for p in name.split("/"))
                        or name in self.entries):
                    raise ReleaseManifestError("release manifest path is invalid")
                kind = entry.get("type")
                extra = ({"file": {"size", "sha256"}, "directory": set(), "symlink": {"target"}}.get(kind)
                         if type(kind) is str else None)
                if (extra is None or set(entry) != common | extra
                        or type(entry["mode"]) is not int or not 0 <= entry["mode"] <= 0o7777
                        or type(entry["uid"]) is not int or entry["uid"] != 0
                        or type(entry["gid"]) is not int or entry["gid"] != 0):
                    raise ReleaseManifestError("release manifest entry is invalid")
                if kind == "file" and (
                    type(entry["size"]) is not int or entry["size"] < 0
                    or type(entry["sha256"]) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None
                ):
                    raise ReleaseManifestError("release manifest file is invalid")
                if kind == "symlink" and (type(entry["target"]) is not str or not entry["target"]):
                    raise ReleaseManifestError("release manifest link is invalid")
                self.entries[name] = entry
            self.hermes_runtime: dict[str, Any] | None = None
            if "hermes_runtime" in document:
                self.hermes_runtime = validate_hermes_runtime_installation(
                    document["hermes_runtime"], _defer_consumer=True)
            self.check()
        except BaseException:
            self.close()
            raise

    def hold(self, path: Path, *, directory: bool = False) -> int:
        if self.closed:
            raise ReleaseManifestError("release source context is closed")
        path = Path(path)
        if not path.is_absolute() or any(p in (".", "..") for p in path.parts):
            raise ReleaseManifestError("release source path is invalid")
        if path in self.held:
            record = self.held[path]
            if record[4] != directory:
                raise ReleaseManifestError("release source type changed")
            return record[0]
        if len(self.held) >= 1024:
            raise ReleaseManifestError("release source descriptor limit exceeded")
        if path == Path("/"):
            parent, name = None, "/"
        else:
            parent, name = self.hold(path.parent, directory=True), path.name
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        if directory:
            flags |= os.O_DIRECTORY
        try:
            fd = os.open(name, flags, dir_fd=parent)
        except OSError as exc:
            raise ReleaseManifestError("release source open refused") from exc
        self.stack.callback(os.close, fd)
        info = os.fstat(fd)
        if (not (stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
                or info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022
                or (not directory and info.st_nlink != 1)):
            raise ReleaseManifestError("release source ownership or mode is invalid")
        _linux_source_acl(fd, directory)
        self.held[path] = (fd, _held_identity(info, directory), parent, name, directory)
        self.check()
        return fd

    def read(self, path: Path, maximum: int) -> bytes:
        fd = self.hold(path)
        info = os.fstat(fd)
        if not 0 <= info.st_size <= maximum:
            raise ReleaseManifestError("release source size exceeds limit")
        raw = os.pread(fd, info.st_size + 1, 0)
        if len(raw) != info.st_size:
            raise ReleaseManifestError("release source read is incomplete")
        self.check()
        return raw

    def source(self, relative: str) -> bytes:
        entry = self.entries.get(relative)
        if type(entry) is not dict or entry.get("type") != "file":
            raise ReleaseManifestError("release source is not listed")
        if relative not in self.sources:
            raw = self.read(self.root / relative, _MAX_SOURCE)
            info = os.fstat(self.held[self.root / relative][0])
            if (stat.S_IMODE(info.st_mode) != entry["mode"]
                    or len(raw) != entry["size"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]):
                raise ReleaseManifestError("release source differs from manifest")
            self.total += len(raw)
            if self.total > 32 * 1024 * 1024:
                raise ReleaseManifestError("release source byte limit exceeded")
            self.sources[relative] = raw
        self.check()
        return self.sources[relative]

    def directory(self, relative: str) -> None:
        entry = self.entries.get(relative)
        if type(entry) is not dict or entry.get("type") != "directory":
            raise ReleaseManifestError("release package is not listed")
        fd = self.hold(self.root / relative, directory=True)
        if stat.S_IMODE(os.fstat(fd).st_mode) != entry["mode"]:
            raise ReleaseManifestError("release package differs from manifest")

    def manifest_sha256(self) -> str:
        """Digest of the original bytes retained by this held manifest."""
        self.check()
        return self._manifest_sha256

    def hermes_runtime_input(self, *, _defer_consumer: bool = False) -> dict[str, Any] | None:
        """The detached, checked approved installation input.

        An absent member is ``None``; a malformed member already refused
        while the held manifest was decoded.
        """
        self.check()
        if self.hermes_runtime is None:
            return None
        return validate_hermes_runtime_installation(self.hermes_runtime, _defer_consumer=_defer_consumer)

    def check(self) -> None:
        if self.closed:
            raise ReleaseManifestError("release source context is closed")
        for fd, identity, parent, name, directory in self.held.values():
            try:
                if (_held_identity(os.fstat(fd), directory) != identity
                        or _held_identity(os.stat(name, dir_fd=parent, follow_symlinks=False), directory) != identity):
                    raise ReleaseManifestError("held release source changed")
                _linux_source_acl(fd, directory)
            except OSError as exc:
                raise ReleaseManifestError("held release source is unavailable") from exc

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.stack.close()


class _ReleaseSourceFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, owner: _HeldReleaseSources):
        self.owner = owner
        self.owned: dict[str, Any] = {}
        self.baseline = tuple(sys.meta_path)
        self.paths = tuple(sys.path)
        self.predecessor = None

    def check(self):
        prefix = [] if self.predecessor is None else [self.predecessor]
        if list(sys.meta_path) != prefix + [self] + list(self.baseline):
            raise ReleaseManifestError("release import finder order changed")
        if tuple(sys.path) != self.paths:
            raise ReleaseManifestError("release import path changed")
        observed = {name: module for name, module in tuple(sys.modules.items())
                    if any(name == root or name.startswith(root + ".") for root in _FIRST_PARTY)}
        if set(observed) != set(self.owned) or any(observed[name] is not module for name, module in self.owned.items()):
            raise ReleaseManifestError("release module ownership changed")
        self.owner.check()

    def find_spec(self, fullname, path=None, target=None):
        if not any(fullname == root or fullname.startswith(root + ".") for root in _FIRST_PARTY):
            return None
        self.check()
        relative = fullname.replace(".", "/")
        init, module = relative + "/__init__.py", relative + ".py"
        if init in self.owner.entries:
            origin, package = init, True
        elif module in self.owner.entries:
            origin, package = module, False
        else:
            self.owner.directory(relative)
            origin, package = relative, True
        if package:
            self.owner.directory(relative)
        spec = importlib.util.spec_from_loader(fullname, self, origin=str(self.owner.root / origin), is_package=package)
        if package:
            spec.submodule_search_locations = []
        spec.has_location = True
        return spec

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        self.owned[module.__name__] = module
        self.check()
        relative = Path(module.__spec__.origin).relative_to(self.owner.root).as_posix()
        if self.owner.entries[relative]["type"] == "directory":
            self.owner.directory(relative)
            module.__file__ = None
        else:
            raw = self.owner.source(relative)
            module.__file__ = str(self.owner.root / relative)
            self.owner.check()
            exec(compile(raw, module.__file__, "exec", dont_inherit=True), module.__dict__)
        self.check()


@contextmanager
def _held_release_imports(owner: _HeldReleaseSources):
    if any(name == root or name.startswith(root + ".") for name in sys.modules for root in _FIRST_PARTY):
        raise ReleaseManifestError("ambient first-party imports are refused")
    finder = _ReleaseSourceFinder(owner)
    sys.meta_path.insert(0, finder)
    try:
        yield finder
        owner.check()
    finally:
        drift = tuple(sys.path) != finder.paths or any(
            (name == root or name.startswith(root + ".")) and name not in finder.owned
            for name in sys.modules for root in _FIRST_PARTY)
        for name, module in reversed(list(finder.owned.items())):
            if sys.modules.get(name) is module:
                del sys.modules[name]
            else:
                drift = True
        indices = [i for i, item in enumerate(sys.meta_path) if item is finder]
        if list(sys.meta_path) != [finder] + list(finder.baseline):
            drift = True
        for index in reversed(indices):
            del sys.meta_path[index]
        if drift:
            raise ReleaseManifestError("held release import ownership changed")


def _qualify_held_hermes_runtime(owner, finder, candidate):
    """Qualify the exact staged bytes through the existing held source loader."""
    if not isinstance(finder, _ReleaseSourceFinder) or finder.owner is not owner:
        raise ReleaseManifestError("Hermes source qualification requires its held importer")
    finder.check()
    qualified = validate_hermes_runtime_installation(candidate)
    if _canonical(qualified) != _canonical(candidate):
        raise ReleaseManifestError("Hermes installation changed during semantic qualification")
    finder.check()
    return qualified


def linux_release_root() -> Path:
    """The fixed Linux release root that holds the exact-SHA installed releases."""
    return _LINUX_RELEASES


def _runtime_custody(factory: Any, installation: dict[str, Any], owner: "_HeldReleaseSources"):
    """Enter the shared runtime custody for the approved installation input.

    The shared factory owns the secret-free interpreter custody. There is no
    private, fallback or permissive alias path here: an uncomposed helper is
    a refusal, not a degraded mode.
    """
    try:
        held = factory.held_runtime_custody
    except AttributeError as exc:
        raise ReleaseManifestError("Hermes runtime custody is not composed") from exc
    return held(bootstrap_python=installation["bootstrap_python"],
                launch_python=installation["launch_python"],
                startup=installation["startup"],
                boundary_check=owner.check)


def _main_custody_observer(owner: "_HeldReleaseSources", finder: Any,
                           runtime: Any, installation: dict[str, Any]):
    """Measure this main process inside its held source and runtime contexts."""
    installation = validate_hermes_runtime_installation(installation)
    process_owner = importlib.import_module(
        _CUSTODY_ROOT.replace("/", ".") + ".linux_process_identity")
    if (not callable(getattr(runtime, "check", None))
            or type(getattr(runtime, "launch_fd", None)) is not int):
        raise ReleaseManifestError("Hermes runtime custody is invalid")
    pid = os.getpid()
    matches = [row for row in installation["roles"]
               if (row["uid"] == os.getuid() == os.geteuid()
                   and row["gid"] == os.getgid() == os.getegid())]
    if len(matches) != 1:
        raise ReleaseManifestError("Hermes role principal differs from installation")
    approved = matches[0]
    launch = installation["launch_python"]
    startup = installation["startup"]
    manifest_sha = owner.manifest_sha256()
    birth = None

    def observe() -> dict[str, Any]:
        nonlocal birth
        finder.check()
        runtime.check()
        if (os.getpid() != pid or not _HERMES_EARLY_NO_SITE
                or not _hermes_recipe_is_qualified()
                or any(name not in sys.modules or sys.modules[name] is not None
                       for name in _HERMES_SITE_NAMES)
                or sys.executable != launch["path"]
                or any(getattr(sys, name) != startup[name]
                       for name in ("prefix", "exec_prefix", "base_prefix", "base_exec_prefix"))):
            raise ReleaseManifestError("Hermes actual startup differs from installation")
        try:
            measured = process_owner.inspect_linux_process_image(pid)
        except process_owner.LinuxProcessIdentityError as exc:
            raise ReleaseManifestError("Hermes main process is unavailable") from exc
        image = os.fstat(runtime.launch_fd)
        expected_image = {
            "device": image.st_dev, "inode": image.st_ino, "mode": image.st_mode,
            "uid": image.st_uid, "gid": image.st_gid, "size": image.st_size,
            "mtime_ns": image.st_mtime_ns, "ctime_ns": image.st_ctime_ns,
            "sha256": launch["sha256"],
        }
        if (any(measured.get(key) != value for key, value in expected_image.items())
                or measured.get("real_uid") != approved["uid"]
                or measured.get("effective_uid") != approved["uid"]
                or measured.get("real_gid") != approved["gid"]
                or measured.get("effective_gid") != approved["gid"]
                or owner.manifest_sha256() != manifest_sha):
            raise ReleaseManifestError("Hermes main custody differs from installation")
        current = (pid, measured["boot_id"], measured["start_identity"],
                   measured["real_uid"], measured["effective_uid"],
                   measured["real_gid"], measured["effective_gid"])
        if birth is None:
            birth = current
        elif current != birth:
            raise ReleaseManifestError("Hermes main process custody changed")
        runtime.check()
        finder.check()
        return {"pid": pid, "start_ticks": measured["start_identity"],
                "uid": approved["uid"], "gid": approved["gid"],
                "manifest_sha256": manifest_sha, "image_sha256": measured["sha256"]}

    # This qualification precedes CLI import and any role/credential read.
    observe()
    return observe


class _NativeGatewayLaunch:
    """Private launch capability constructed only by the held release entry."""

    def __init__(self, owner, finder, runtime, closure, row):
        self.owner, self.finder, self.runtime, self.closure = owner, finder, runtime, closure
        self.row = row
        self.recipe = row["native_gateway"]
        self.launcher = owner.root / "integrations/hermes_runtime/native/hermes"
        self.launcher_bytes = owner.source("integrations/hermes_runtime/native/hermes")
        self.adapter_bytes = owner.source("integrations/hermes_runtime/native_gateway_entry.py")
        self._births = {}
        self.derivation = None
        if "vendor_derivation" in self.recipe:
            from ops.executive_os.native_gateway_sources import verify_vendor_derivation
            self.derivation = verify_vendor_derivation(owner, self.recipe, _linux_source_acl)

    def check(self):
        self.finder.check()
        self.runtime.check()
        self.closure.check()
        self.owner.check()

    def qualify(self, profile, hermes_bin):
        from integrations.hermes_runtime.errors import RuntimeRefusal
        from integrations.hermes_runtime.profile import profile_sha256, dump_profile
        if (profile.gateway_backend != "native-session-authority"
                or profile.role != self.row["role"]
                or str(profile.state_dir) != self.row["state_dir"]
                or os.getuid() != os.geteuid() or os.getuid() != self.row["uid"]
                or os.getgid() != os.getegid() or os.getgid() != self.row["gid"]
                or Path(hermes_bin) != profile.state_dir / "current/bin/hermes"
                or Path(hermes_bin).resolve(strict=True) != self.launcher):
            raise RuntimeRefusal("NATIVE_GATEWAY_INSTALLATION_MISMATCH")
        receipt_path = profile.state_dir / "current/install-receipt.json"
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(receipt_path, flags)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600
                    or not 1 <= before.st_size <= 65536):
                raise RuntimeRefusal("NATIVE_GATEWAY_RECEIPT_UNQUALIFIED")
            raw = os.read(fd, 65537)
            if len(raw) != before.st_size or _held_identity(os.fstat(fd), False) != _held_identity(before, False):
                raise RuntimeRefusal("NATIVE_GATEWAY_RECEIPT_CHANGED")
        finally:
            os.close(fd)
        receipt = _closed_json(raw)
        if (type(receipt) is not dict
                or receipt.get("native_gateway") != self.recipe
                or receipt.get("native_launcher_sha256") != hashlib.sha256(self.launcher_bytes).hexdigest()
                or receipt.get("native_adapter_sha256") != hashlib.sha256(self.adapter_bytes).hexdigest()
                or receipt.get("profile_sha256") != profile_sha256(dump_profile(profile))
                or receipt.get("upstream_attested") is not True
                or receipt.get("native_vendor_derivation") != self.derivation
                or receipt.get("sha") != profile.sha or receipt.get("role") != profile.role):
            raise RuntimeRefusal("NATIVE_GATEWAY_RECEIPT_MISMATCH")
        consumer = self.recipe.get("executive_consumer")
        if consumer is not None:
            # Qualify physical custody through the original held release.
            # The role-home receipt's digest is only an equality witness.
            from integrations.hermes_harness.native_executive_consumer import held_plugin_package_digest
            if (receipt.get("native_consumer_plugin_sha256") != consumer["plugin"]["digest"]
                    or held_plugin_package_digest(self.owner) != consumer["plugin"]["digest"]):
                raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_UNPROVEN")
        self.check()

    def argv(self, profile, hermes_bin, *, tools=False):
        self.qualify(profile, hermes_bin)
        command = (["tools", "list", "--platform", "cli"] if tools
                   else ["gateway", "run", "--external-supervisor"])
        return [self.recipe["python"]["path"], "-I", "-S", "-B", str(self.launcher),
                "-p", profile.role, *command]

    def observe_child(self, pid):
        process = importlib.import_module(_CUSTODY_ROOT.replace("/", ".") + ".linux_process_identity")
        measured = process.inspect_linux_process_image(pid)
        image = os.fstat(self.runtime.launch_fd)
        expected = {"device": image.st_dev, "inode": image.st_ino, "mode": image.st_mode,
                    "uid": image.st_uid, "gid": image.st_gid, "size": image.st_size,
                    "mtime_ns": image.st_mtime_ns, "ctime_ns": image.st_ctime_ns,
                    "sha256": self.recipe["python"]["sha256"]}
        if (any(measured.get(k) != value for k, value in expected.items())
                or any(measured.get(k) != self.row["uid"] for k in ("real_uid", "effective_uid"))
                or any(measured.get(k) != self.row["gid"] for k in ("real_gid", "effective_gid"))):
            raise ReleaseManifestError("Hermes native child image differs from installation")
        birth = (measured["boot_id"], measured["start_identity"])
        if self._births.setdefault(pid, birth) != birth:
            raise ReleaseManifestError("Hermes native child identity changed")
        self.runtime.check()
        self.owner.check()
        return measured


def _hermes_runtime(argv: list[str]) -> int:
    if (not argv or argv[0] not in {"supervise", "canary", "isolation-probe", "native-gateway",
                                    "enroll-secretary-session", "enroll-meta-session",
                                    "eval-submit", "eval-read", "eval-publish", "eval-trial"}
            or not _HERMES_EARLY_NO_SITE or not _hermes_recipe_is_qualified()
            or any(name not in sys.modules or sys.modules[name] is not None
                   for name in _HERMES_SITE_NAMES)):
        raise ReleaseManifestError("Hermes requires the fixed early isolated Linux recipe")
    entry = Path(__file__)
    root = entry.parents[2]
    if (not entry.is_absolute() or root.parent != _LINUX_RELEASES
            or entry != root / "ops/executive_os/release_manifest.py"):
        raise ReleaseManifestError("Hermes entry is outside the fixed release")
    owner = _HeldReleaseSources(root)
    original_paths = tuple(sys.path)
    closure = None
    try:
        owner.source("ops/executive_os/release_manifest.py")
        installation = owner.hermes_runtime_input(_defer_consumer=True)
        if installation is None:
            raise ReleaseManifestError("Hermes installation input is absent")
        label = os.environ.get("MM_HERMES_IMPLEMENTATION_SHA")
        if label is not None and label != root.name:
            raise ReleaseManifestError("Hermes implementation label differs from release")
        child_entry = argv[0] == "native-gateway"
        row = None
        native = None
        if child_entry or any("native_gateway" in item for item in installation["roles"]):
            matches = [item for item in installation["roles"]
                       if item["uid"] == os.getuid() == os.geteuid()
                       and item["gid"] == os.getgid() == os.getegid()]
            if len(matches) != 1:
                raise ReleaseManifestError("Hermes role principal differs from installation")
            row = matches[0]
            native = row.get("native_gateway")
        if child_entry and native is None:
            raise ReleaseManifestError("Hermes native installation input is absent")
        # Qualify publications and dependency bytes while only the original
        # isolated stdlib paths are visible. Unqualified vendor paths must not
        # supply an ordinary import used by either qualification owner.
        with _held_release_imports(owner) as finder:
            installation = _qualify_held_hermes_runtime(owner, finder, installation)
            if row is not None:
                row = next(item for item in installation["roles"] if item["role"] == row["role"])
                native = row.get("native_gateway")
            if native is not None:
                from ops.executive_os.native_gateway_sources import NativeSourceClosure
                closure = NativeSourceClosure(owner, native, _linux_source_acl)
                closure.check()
            finder.check()
        # The same held source owner and closure survive this finite import
        # scope. A fresh finder freezes the one selected native path recipe;
        # neither finder's path-drift protection is relaxed or refreshed.
        if native is not None:
            owner.check()
            closure.check()
            sys.path[:] = [native["vendor_root"], *original_paths, *native["import_roots"][1:]]
        with _held_release_imports(owner) as finder:
            finder.check()
            if closure is not None:
                closure.check()
            factory = importlib.import_module(_CUSTODY_ROOT.replace("/", ".") + ".paid_initializer")
            with ExitStack() as contexts:
                execution = installation
                if child_entry:
                    execution = dict(installation, bootstrap_python=native["python"],
                                     launch_python=native["python"], startup=native["startup"])
                runtime = contexts.enter_context(_runtime_custody(factory, execution, owner))
                native_runtime = runtime if child_entry else None
                if native is not None and not child_entry:
                    native_runtime = contexts.enter_context(factory.held_runtime_custody(
                        bootstrap_python=installation["bootstrap_python"],
                        launch_python=native["python"], startup=native["startup"],
                        boundary_check=owner.check))
                yaml_owner = importlib.import_module(_YAML_ROOT.replace("/", ".") + ".paid_yaml_runtime")
                with yaml_owner.held_yaml(
                    owner.source(_YAML_ROOT + "/paid_pyyaml_6_0_3.zip"),
                    owner.source(_YAML_ROOT + "/paid_pyyaml_provenance.json"),
                    owner.check,
                ) as yaml:
                    finder.predecessor = yaml.__loader__
                    finder.check()
                    native_launch = (_NativeGatewayLaunch(owner, finder, native_runtime, closure, row)
                                     if native is not None else None)
                    if child_entry:
                        if (sys.executable != native["python"]["path"]
                                or any(getattr(sys, key) != native["startup"][key]
                                       for key in ("prefix", "exec_prefix", "base_prefix", "base_exec_prefix"))):
                            raise ReleaseManifestError("Hermes native startup differs from installation")
                        native_launch.check()
                        native_launch.observe_child(os.getpid())
                        from integrations.hermes_runtime.native_gateway_entry import run
                        result = run(native_launch, argv[1:])
                    else:
                        custody_observer = _main_custody_observer(owner, finder, runtime, installation)
                        if argv[0] == "isolation-probe":
                            from integrations.hermes_runtime.isolation_probe import main as entry_main
                            finder.check()
                            result = entry_main(argv[1:])
                        else:
                            from integrations.hermes_runtime.cli import main as entry_main
                            kwargs = {"custody_observer": custody_observer}
                            if native_launch is not None:
                                kwargs["native_launch"] = native_launch
                            finder.check()
                            result = entry_main(argv, **kwargs)
                        custody_observer()
                    finder.check()
                    if native_launch is not None:
                        native_launch.check()
                    return result
    finally:
        if closure is not None:
            closure.close()
        sys.path[:] = original_paths
        owner.close()


def _prepare_hermes_dependencies(argv: list[str]) -> int:
    """Qualify native dependencies within the existing root enrollment."""
    if (not _HERMES_EARLY_NO_SITE or not _hermes_recipe_is_qualified()
            or os.getuid() != 0 or os.geteuid() != 0):
        raise ReleaseManifestError("native dependency preparation requires the root recipe")
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--tree-sha", required=True)
    parser.add_argument("--hermes-runtime-json", required=True)
    args = parser.parse_args(argv)
    raw = args.hermes_runtime_json.encode("utf-8")
    if not 0 < len(raw) <= _MAX_CLI_ARGUMENT:
        raise ReleaseManifestError("Hermes installation argument is invalid")
    expected = validate_hermes_runtime_installation(_closed_json(raw), _defer_consumer=True)
    if args.root.name != args.commit_sha:
        raise ReleaseManifestError("native dependency release differs")
    owner = _HeldReleaseSources(args.root)
    try:
        document = _closed_json(owner.read(args.root / MANIFEST_NAME, _MAX_SOURCE))
        retained = owner.hermes_runtime_input(_defer_consumer=True)
        if document["tree_sha"] != args.tree_sha or retained != expected:
            raise ReleaseManifestError("native dependency installation differs")
        selected = {}
        for row in expected["roles"]:
            native = row.get("native_gateway")
            if native is None:
                continue
            path = native["dependency_inventory"]["path"]
            selection = (native["import_roots"], native["dependency_inventory"],
                         native.get("vendor_derivation"))
            if path in selected and selected[path][0] != selection:
                raise ReleaseManifestError("native dependency inventory selection conflicts")
            selected[path] = (selection, native)
        if not selected:
            raise ReleaseManifestError("native dependency input is absent")
        # Load only immutable first-party code through its existing owner.
        # No native package, model, credential or runtime unit is entered.
        with _held_release_imports(owner) as finder:
            qualified = _qualify_held_hermes_runtime(owner, finder, retained)
            expected = _qualify_held_hermes_runtime(owner, finder, expected)
            if qualified != expected:
                raise ReleaseManifestError("native dependency installation differs")
            # selected contains only structurally qualified path recipes whose
            # complete documents now passed the same semantic/source boundary.
            from ops.executive_os.native_gateway_sources import prepare_inventory
            for _, native in selected.values():
                if "vendor_derivation" in native:
                    from ops.executive_os.native_gateway_sources import prepare_vendor_derivation
                    prepare_vendor_derivation(owner, native, _linux_source_acl)
                prepare_inventory(owner, native, _linux_source_acl)
        owner.check()
    finally:
        owner.close()
    print(json.dumps({"ok": True, "commit_sha": args.commit_sha,
                      "native_dependencies": "qualified", "services_activated": False},
                     sort_keys=True))
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "prepare-hermes-dependencies":
        try:
            return _prepare_hermes_dependencies(sys.argv[2:])
        except (ReleaseManifestError, OSError, ValueError, ImportError, SyntaxError):
            print("HERMES_NATIVE_DEPENDENCIES_UNQUALIFIED", file=sys.stderr)
            return 78
    if len(sys.argv) > 1 and sys.argv[1] == "hermes-runtime":
        try:
            if not _hermes_recipe_is_qualified():
                raise ReleaseManifestError("Hermes requires the fixed isolated Linux recipe")
            return _hermes_runtime(sys.argv[2:])
        except (ReleaseManifestError, OSError, ValueError, ImportError, SyntaxError):
            print("HERMES_RELEASE_SOURCE_UNQUALIFIED", file=sys.stderr)
            return 78  # Existing Hermes CONFIG_EXIT; no unqualified import to read it.
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("create", "verify"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--tree-sha", required=True)
    parser.add_argument(
        "--hermes-runtime-json",
        help=("Optional approved installation input as one JSON object. "
              "For verify, omitted means ordinary inspection and null means the "
              "member must be absent; a persisted member is never null."),
    )
    args = parser.parse_args()
    expectation: Any = _UNSPECIFIED
    if args.hermes_runtime_json is not None:
        raw = args.hermes_runtime_json.encode("utf-8")
        if not 0 < len(raw) <= _MAX_CLI_ARGUMENT:
            raise ReleaseManifestError("Hermes runtime installation argument is invalid")
        expectation = _closed_json(raw)
        if expectation is not None:
            # The member is validated before any release read or mutation.
            expectation = validate_hermes_runtime_installation(expectation)
    if args.command == "create":
        create(args.root, args.commit_sha, args.tree_sha,
               hermes_runtime=None if expectation is _UNSPECIFIED or expectation is None
               else expectation)
    else:
        verify(args.root, args.commit_sha, args.tree_sha,
               expected_hermes_runtime=expectation)
    print(json.dumps({"ok": True, "commit_sha": args.commit_sha}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
