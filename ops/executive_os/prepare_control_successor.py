"""Prepare a supplied Control configuration for the existing installer.

This is an offline input transform, not an installed-config reader or publisher.
Only proof_base_sha, its installer-owned proof_source_repository checkout, and
ceo_ingress_app_macro_root change. Host policy, arming, identities and all other
supplied values remain the installer's responsibility.
The caller supplies the already-approved Macro root; this tool does not inspect
that root, attest its seal, load referenced runtime files, or authorize activation.

Example (all paths are explicit):
  python3 ops/executive_os/prepare_control_successor.py \
    --input /staging/control-input.json --output /staging/control-successor.json \
    --source-sha <40-hex-commit> --macro-root /approved/sealed/Macro

The output is a candidate --control-config input. The existing install and
Control startup validations still apply, including their host-file checks.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any


_MAX_INPUT_BYTES = 1024 * 1024
_LIVE_CONFIG_ROOT = Path("/Library/Application Support/MastermindExecutive/config")
_ADMIN_CHECKOUT_ROOT = Path("/var/db/mastermind-executive/control/admin-checkout")
_CHANGED_FIELDS = frozenset({"proof_base_sha", "proof_source_repository", "ceo_ingress_app_macro_root"})


class PreparationError(ValueError):
    """The supplied offline configuration cannot produce this successor."""


def _absolute_path(value: Any) -> Path:
    if (type(value) is not str or "\x00" in value or value.startswith("//") or not Path(value).is_absolute()
            or ".." in Path(value).parts or str(Path(value)) != value):
        raise PreparationError("an explicit canonical absolute path is required")
    return Path(value)


def _offline_path(value: str) -> Path:
    path = _absolute_path(value)
    if path == _LIVE_CONFIG_ROOT or _LIVE_CONFIG_ROOT in path.parents:
        raise PreparationError("use a supplied offline input and output, not installed configuration paths")
    resolved = path.resolve(strict=False)
    if resolved == _LIVE_CONFIG_ROOT or _LIVE_CONFIG_ROOT in resolved.parents:
        raise PreparationError("offline paths must not alias installed configuration")
    return path


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise PreparationError("duplicate JSON key")
        document[key] = value
    return document


def _constant(_value: str) -> Any:
    raise PreparationError("non-finite JSON number")


def _parse(raw: bytes) -> dict[str, Any]:
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                              parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PreparationError("input must contain strict UTF-8 JSON") from exc
    if type(document) is not dict:
        raise PreparationError("input must contain a complete Control configuration object")
    try:
        json.dumps(document, allow_nan=False)
    except ValueError as exc:
        raise PreparationError("non-finite JSON number") from exc
    return document


def _read(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 0 < before.st_size <= _MAX_INPUT_BYTES):
            raise PreparationError("input must be a single-link regular file of at most 1 MiB")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(_MAX_INPUT_BYTES + 1)
        after = os.fstat(fd)
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size,
                                 info.st_mtime_ns, info.st_ctime_ns)
        if len(raw) != before.st_size or identity(before) != identity(after):
            raise PreparationError("input changed while reading")
        return raw
    finally:
        os.close(fd)


def _validate_document(document: dict[str, Any]) -> None:
    """Use the source contract and its pure validators, without host reads.

    load_control_config also opens staged Fabric bindings/content profiles and
    attests a configured Python executable. Those live checks deliberately stay
    with that existing loader; an offline preparation cannot claim they passed.
    """
    from scripts import executive_os_phase1c as control
    from ops.executive_os.coo_principal_host import validate_control_coo

    value = copy.deepcopy(document)
    keys = set(value)
    missing = control._CONFIG_REQUIRED - keys
    unknown = keys - control._CONFIG_REQUIRED - control._CONFIG_OPTIONAL
    if missing or unknown:
        raise PreparationError(f"Control schema drift: missing={sorted(missing)}, unknown={sorted(unknown)}")
    if value["schema_version"] != control.CONTROL_CONFIG_SCHEMA_VERSION:
        raise PreparationError("unsupported Control configuration schema")
    required_app = control._CEO_INGRESS_CONFIG_KEYS | control._CEO_INGRESS_APP_CONFIG_KEYS
    if not required_app <= keys:
        raise PreparationError("a complete existing App and CeoIngress binding is required")
    if type(value["proof_base_sha"]) is not str or not re.fullmatch(r"[0-9a-f]{40}", value["proof_base_sha"]):
        raise PreparationError("proof_base_sha must be a full lowercase commit SHA")
    try:
        if type(value["proof_source_repository"]) is not str or "\x00" in value["proof_source_repository"]:
            raise PreparationError("proof_source_repository must be an absolute path")
        control._absolute_path(value["proof_source_repository"])
        control._absolute_path(value["ceo_ingress_app_macro_root"])
        control._validate_fabric_bridge_config(value)
        control.company_consultation_launchd_entry(value)
        validate_control_coo(value)
        control._validate_subscription_canary_realm_config(value)
        for name in ("control_uid", "worker_uid", "worker_gid", "shared_run_gid",
                     "ceo_ingress_peer_uid", "ceo_ingress_app_peer_uid"):
            control._integer(value[name], name)
        peers = value["allowed_peer_uids"]
        if type(peers) is not list or not peers:
            raise PreparationError("allowed_peer_uids must be a non-empty list")
        for peer in peers:
            control._integer(peer, "allowed_peer_uids")
        if value["worker_uid"] == value["control_uid"]:
            raise PreparationError("worker_uid must differ from control_uid")
        if value["ceo_ingress_app_peer_uid"] in {
                value["control_uid"], value["worker_uid"], value["ceo_ingress_peer_uid"], *peers}:
            raise PreparationError("App peer must be distinct from the other service identities")
        if type(value["ceo_ingress_app_armed"]) is not bool:
            raise PreparationError("App admission arming must be boolean")
        workspace = {"workspace_acquisition", "workspace_resource_policy", "workspace_control_room"}
        if keys & workspace:
            if not workspace <= keys:
                raise PreparationError("workspace acquisition requires the complete existing binding")
            control.validate_workspace_control_room(value["workspace_control_room"],
                                                   control_uid=value["control_uid"])
        if {"content_observer", "content_observer_profile_path"} <= keys:
            raise PreparationError("content observer sources are mutually exclusive")
        if "content_observer" in value:
            control._validate_content_profiles(value["content_observer"],
                                               expected_release_sha=value["proof_base_sha"])
    except (control.ServiceError, argparse.ArgumentTypeError, TypeError, ValueError) as exc:
        raise PreparationError(str(exc)) from exc


def build_successor(document: dict[str, Any], *, source_sha: str,
                    macro_root: str) -> dict[str, Any]:
    """Return a separate mapping; never mutate or normalize unrelated input."""
    if type(source_sha) is not str or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise PreparationError("source-sha must be a full lowercase commit SHA")
    _absolute_path(macro_root)
    _validate_document(document)
    successor = copy.deepcopy(document)
    successor["proof_base_sha"] = source_sha
    successor["proof_source_repository"] = str(_ADMIN_CHECKOUT_ROOT / source_sha)
    successor["ceo_ingress_app_macro_root"] = macro_root
    _validate_document(successor)
    return successor


def prepare(*, input_path: str, output_path: str, source_sha: str,
            macro_root: str) -> dict[str, Any]:
    source = _offline_path(input_path)
    destination = _offline_path(output_path)
    if source == destination:
        raise PreparationError("output must differ from input")
    raw = _read(source)
    document = _parse(raw)
    successor = build_successor(document, source_sha=source_sha, macro_root=macro_root)
    encoded = (json.dumps(successor, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        destination.unlink()
        raise
    changed = sorted(key for key in _CHANGED_FIELDS if document[key] != successor[key])
    return {
        "prepared": True,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "output_sha256": hashlib.sha256(encoded).hexdigest(),
        "changed_fields": changed,
        "unchanged_fields": len(document) - len(changed),
        "validation": "offline schema and pure validators; existing installer and live Control loader still apply",
        "macro_seal_verified": False,
        "installed_configuration_changed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("input", "output", "source-sha", "macro-root"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(input_path=args.input, output_path=args.output,
                         source_sha=args.source_sha, macro_root=args.macro_root)
    except (OSError, PreparationError) as exc:
        print(f"Control successor preparation refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
