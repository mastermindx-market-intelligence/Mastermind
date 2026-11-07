#!/usr/bin/env python3
"""Fail-closed CLI for one private Web-Sol deployment transaction."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

from integrations.chairman_surfaces import web_sol_deployment as deployment
from integrations.chairman_surfaces import web_sol_deployment_apply as applier
from integrations.chairman_surfaces import web_sol_instance as instance
from integrations.chairman_surfaces import web_sol_protocol as protocol

ERROR_SCHEMA = "mastermind.web_sol_deployment_apply_error.v1"
REQUEST_SCHEMA = "mastermind.web_sol_deployment_apply_request.v1"
PRIVATE_STATE_SCHEMA = "mastermind.web_sol_deployment_apply_private_state.v1"
MAX_JSON_BYTES = 8_388_608
MAX_JSON_DEPTH = 64
MAX_JSON_INTEGER_DIGITS = 64
MAX_ARTIFACTS = 16
MAX_ARTIFACT_BYTES = 1_048_576
MAX_TOTAL_ARTIFACT_BYTES = 4_194_304
_HEX40_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_HEX64_RE = re.compile(r"\A[0-9a-f]{64}\Z")

_PERMISSION_BITS_MASK = stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
        result[key] = value
    return result


def _reject_constant(_literal: str) -> Any:
    raise applier.WebSolDeploymentApplyError("INVALID_INPUT")


def _bounded_integer(literal: str) -> int:
    if len(literal.lstrip("-")) > MAX_JSON_INTEGER_DIGITS:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    return int(literal)


def _check_depth(value: Any) -> None:
    pending: list[tuple[Any, int]] = [(value, 0)]
    while pending:
        node, parent_depth = pending.pop()
        if type(node) not in (dict, list):
            continue
        depth = parent_depth + 1
        if depth > MAX_JSON_DEPTH:
            raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
        children = node.values() if type(node) is dict else node
        pending.extend((child, depth) for child in children)


def _decode_private_json_payload(payload: bytes) -> Any:
    if type(payload) is not bytes or len(payload) > MAX_JSON_BYTES:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_int=_bounded_integer,
        )
        _check_depth(value)
        return value
    except applier.WebSolDeploymentApplyError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT") from None


def _private_json_file(path: Path) -> Any:
    try:
        parent, parent_descriptor = _open_state_parent(path)
    except applier.WebSolDeploymentApplyError as exc:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT") from exc
    try:
        value, _payload = _private_json_at(
            parent_descriptor,
            path.name,
            error_code="INVALID_INPUT",
        )
        if not _state_parent_binding_current(parent, parent_descriptor):
            raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
        return value
    finally:
        os.close(parent_descriptor)


def _exact_dict(value: object, keys: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    return value


def _exact_list(value: object) -> list[Any]:
    if type(value) is not list:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    return value


def _string(value: object, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    return value


def _integer(value: object, *, minimum: int = 0, maximum: int = 2**31 - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    return value


def _digest(value: object, *, width: int = 64) -> str:
    text = _string(value, maximum=width)
    pattern = _HEX40_RE if width == 40 else _HEX64_RE
    if pattern.fullmatch(text) is None:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    return text


def _absolute_path(value: object) -> Path:
    text = _string(value)
    path = Path(text)
    if not path.is_absolute() or ".." in path.parts:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    return path


def _decode_artifact(raw: object) -> deployment.DeploymentArtifact:
    row = _exact_dict(
        raw,
        frozenset({"kind", "destination", "content_base64", "mode", "sha256"}),
    )
    encoded = _string(row["content_base64"], maximum=2 * MAX_ARTIFACT_BYTES)
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT") from None
    if not content or len(content) > MAX_ARTIFACT_BYTES:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    expected = _digest(row["sha256"])
    if hashlib.sha256(content).hexdigest() != expected:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    try:
        artifact = deployment.DeploymentArtifact(
            kind=_string(row["kind"], maximum=64),
            destination=_absolute_path(row["destination"]),
            content=content,
            mode=_integer(row["mode"], maximum=_PERMISSION_BITS_MASK),
        )
    except deployment.WebSolDeploymentError as exc:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT") from exc
    return artifact


class _ReleaseIdentity:
    def __init__(self, source_commit: str) -> None:
        self.package_version = protocol.WEB_SOL_PACKAGE_VERSION
        self.source_commit = source_commit


def _decode_bundle(raw: object) -> deployment.DeploymentBundle:
    row = _exact_dict(
        raw,
        frozenset(
            {
                "instance_id",
                "native_host_name",
                "source_commit",
                "wrapper_argv",
                "bundle_digest",
                "artifacts",
            }
        ),
    )
    instance_id = _digest(row["instance_id"])
    native_host_name = _string(row["native_host_name"], maximum=255)
    source_commit = _digest(row["source_commit"], width=40)
    if instance.native_host_name(instance_id) != native_host_name:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    argv = tuple(_string(item, maximum=4096) for item in _exact_list(row["wrapper_argv"]))
    if not 1 <= len(argv) <= 32:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    raw_artifacts = _exact_list(row["artifacts"])
    if not 1 <= len(raw_artifacts) <= MAX_ARTIFACTS:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    artifacts = tuple(_decode_artifact(item) for item in raw_artifacts)
    if sum(len(item.content) for item in artifacts) > MAX_TOTAL_ARTIFACT_BYTES:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    if (
        len({item.kind for item in artifacts}) != len(artifacts)
        or len({str(item.destination) for item in artifacts}) != len(artifacts)
    ):
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    bundle_digest = _digest(row["bundle_digest"])
    recomputed = deployment._bundle_digest(  # noqa: SLF001
        release=_ReleaseIdentity(source_commit),
        instance_id=instance_id,
        artifacts=artifacts,
    )
    if recomputed != bundle_digest:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    return deployment.DeploymentBundle(
        instance_id=instance_id,
        native_host_name=native_host_name,
        source_commit=source_commit,
        wrapper_argv=argv,
        artifacts=artifacts,
        bundle_digest=bundle_digest,
    )


def _decode_change(raw: object) -> deployment.DeploymentChange:
    row = _exact_dict(
        raw,
        frozenset({"path", "action", "prior_sha256", "next_sha256", "mode"}),
    )
    action = _string(row["action"], maximum=16)
    if action not in {"CREATE", "UPDATE", "UNCHANGED"}:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    prior = row["prior_sha256"]
    if prior is not None:
        prior = _digest(prior)
    return deployment.DeploymentChange(
        path=_absolute_path(row["path"]),
        action=action,
        prior_sha256=prior,
        next_sha256=_digest(row["next_sha256"]),
        mode=_integer(row["mode"], maximum=_PERMISSION_BITS_MASK),
    )


def _decode_plan(
    raw: object,
    bundle: deployment.DeploymentBundle,
) -> deployment.DeploymentPlan:
    row = _exact_dict(
        raw,
        frozenset({"bundle_digest", "changes", "rollback_entries"}),
    )
    bundle_digest = _digest(row["bundle_digest"])
    if bundle_digest != bundle.bundle_digest:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    changes = tuple(_decode_change(item) for item in _exact_list(row["changes"]))
    if len(changes) != len(bundle.artifacts):
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    if len({str(item.path) for item in changes}) != len(changes):
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")

    rollback: list[tuple[str, str, str | None]] = []
    seen: set[str] = set()
    for raw_entry in _exact_list(row["rollback_entries"]):
        entry = _exact_dict(
            raw_entry,
            frozenset({"path", "prior_state", "prior_sha256"}),
        )
        path = str(_absolute_path(entry["path"]))
        if path in seen:
            raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
        seen.add(path)
        state = _string(entry["prior_state"], maximum=16)
        prior = entry["prior_sha256"]
        if state == "ABSENT":
            if prior is not None:
                raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
        elif state == "PRESENT":
            prior = _digest(prior)
        else:
            raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
        rollback.append((path, state, prior))
    if len(rollback) != len(changes):
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")

    rollback_by_path = {path: (state, digest) for path, state, digest in rollback}
    for change in changes:
        expected = (
            ("ABSENT", None)
            if change.prior_sha256 is None
            else ("PRESENT", change.prior_sha256)
        )
        if rollback_by_path.get(str(change.path)) != expected:
            raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    return deployment.DeploymentPlan(
        bundle_digest=bundle_digest,
        changes=changes,
        _rollback_entries=tuple(rollback),
    )


def _decode_request(
    raw: object,
) -> tuple[
    deployment.DeploymentBundle,
    deployment.DeploymentPlan,
    dict[str, object],
]:
    row = _exact_dict(
        raw,
        frozenset(
            {
                "schema",
                "operation_key",
                "install_root",
                "expected_uid",
                "expected_gid",
                "bundle",
                "plan",
            }
        ),
    )
    if row["schema"] != REQUEST_SCHEMA:
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    bundle = _decode_bundle(row["bundle"])
    plan = _decode_plan(row["plan"], bundle)
    metadata: dict[str, object] = {
        "operation_key": _string(row["operation_key"], maximum=128),
        "install_root": _absolute_path(row["install_root"]),
        "expected_uid": _integer(row["expected_uid"]),
        "expected_gid": _integer(row["expected_gid"]),
    }
    return bundle, plan, metadata


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _encoded_preimage(row: applier.ArtifactPreimage) -> dict[str, object]:
    return {
        "kind": row.kind,
        "path": str(row.path),
        "path_digest": row.path_digest,
        "prior_state": row.prior_state,
        "prior_bytes_base64": (
            None
            if row.prior_bytes is None
            else base64.b64encode(row.prior_bytes).decode("ascii")
        ),
        "prior_sha256": row.prior_sha256,
        "prior_mode": row.prior_mode,
        "prior_uid": row.prior_uid,
        "prior_gid": row.prior_gid,
    }


def _encoded_directory_preimage(
    row: applier.DirectoryPreimage,
) -> dict[str, object]:
    return {
        "path": str(row.path),
        "path_digest": row.path_digest,
        "prior_state": row.prior_state,
        "prior_dev": row.prior_dev,
        "prior_ino": row.prior_ino,
        "prior_mode": row.prior_mode,
        "prior_uid": row.prior_uid,
        "prior_gid": row.prior_gid,
    }


def _private_state_document(
    *,
    request_document: dict[str, Any],
    prepared: applier.PreparedDeployment,
    phase: str,
    applied: applier.AppliedDeployment | None = None,
) -> dict[str, object]:
    if phase not in {
        "PREPARED", "APPLIED", "ROLLED_BACK", "CONFLICT",
        "ABORTED_ROLLED_BACK",
    }:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    applied_row: dict[str, object] | None = None
    if applied is not None:
        applied_row = {
            "changed_paths": [str(path) for path in applied.changed_paths],
            "created_directories": [str(path) for path in applied.created_directories],
            "reconciled_paths": [str(path) for path in applied.reconciled_paths],
        }
    body: dict[str, object] = {
        "schema": PRIVATE_STATE_SCHEMA,
        "phase": phase,
        "request": request_document,
        "prepared": {
            "prepared_digest": prepared.prepared_digest,
            "cleanup_nonce": prepared.cleanup_nonce,
            "preimages": [_encoded_preimage(row) for row in prepared.preimages],
            "directory_preimages": [
                _encoded_directory_preimage(row)
                for row in prepared.directory_preimages
            ],
        },
        "applied": applied_row,
        "production_acceptance_granted": False,
    }
    body["state_digest"] = hashlib.sha256(_canonical_bytes(body)).hexdigest()
    if len(_canonical_bytes(body)) + 1 > MAX_JSON_BYTES:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    return body


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare, apply, verify, or roll back one Web-Sol bundle."
    )
    parser.add_argument(
        "mode",
        choices=("preflight", "apply", "verify", "rollback"),
    )
    parser.add_argument("--request", type=Path)
    parser.add_argument("--state", type=Path)
    return parser


def _emit(value: object, *, stream: object | None = None) -> None:
    if stream is None:
        stream = sys.stdout
    print(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ),
        file=stream,
    )


def _assert_state_outside_install_root(
    state_path: Path,
    install_root: Path,
    *,
    error_code: str,
) -> None:
    if not state_path.is_absolute() or ".." in state_path.parts:
        raise applier.WebSolDeploymentApplyError(error_code)
    try:
        state_path.relative_to(install_root)
    except ValueError:
        return
    raise applier.WebSolDeploymentApplyError(error_code)


def _apply_and_persist_terminal_refusal(
    *,
    request_document: dict[str, Any],
    prepared: applier.PreparedDeployment,
    state_path: Path,
    expected_state_digest: str,
) -> applier.AppliedDeployment:
    """Apply once and seal definite terminal refusals against replay."""

    try:
        return applier.apply_deployment(prepared)
    except applier.WebSolDeploymentApplyError as exc:
        terminal_phase = {
            ("PREIMAGE_CONFLICT", "CONFLICT"): "CONFLICT",
            (
                "APPLY_ABORTED_ROLLED_BACK",
                "ABORTED_ROLLED_BACK",
            ): "ABORTED_ROLLED_BACK",
        }.get((exc.code, prepared._state))
        if terminal_phase is None:
            raise
        terminal_state = _private_state_document(
            request_document=request_document,
            prepared=prepared,
            phase=terminal_phase,
        )
        _write_private_state(
            state_path,
            terminal_state,
            expected_digest=expected_state_digest,
        )
        raise


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.mode in {"verify", "rollback"}:
            if args.state is None or args.request is not None:
                raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
            phase, request_document, prepared, applied, state_digest = (
                _decode_private_state(_private_state_file(args.state))
            )
            _assert_state_outside_install_root(
                args.state,
                prepared.install_root,
                error_code="STATE_INVALID",
            )
            if phase != "APPLIED" or applied is None:
                raise applier.WebSolDeploymentApplyError("TRANSACTION_CONSUMED")
            if args.mode == "verify":
                _emit(applier.verify_applied_deployment(applied))
                return 0
            reconciled_rollback = applier.reconcile_applied_rollback(applied)
            rollback_receipt = (
                applier.rollback_deployment(applied)
                if reconciled_rollback is None
                else reconciled_rollback
            )
            terminal_state = _private_state_document(
                request_document=request_document,
                prepared=prepared,
                phase="ROLLED_BACK",
                applied=applied,
            )
            _write_private_state(
                args.state,
                terminal_state,
                expected_digest=state_digest,
            )
            _emit(rollback_receipt)
            return 0

        if args.request is None:
            raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
        request_document = _private_json_file(args.request)
        bundle, plan, request_meta = _decode_request(request_document)
        if args.state is not None:
            _assert_state_outside_install_root(
                args.state,
                request_meta["install_root"],
                error_code="INVALID_INPUT",
            )
        if (
            args.mode == "apply"
            and args.state is not None
            and (args.state.exists() or args.state.is_symlink())
        ):
            phase, state_request, state_prepared, state_applied, _state_digest = (
                _decode_private_state(_private_state_file(args.state))
            )
            if _canonical_bytes(state_request) != _canonical_bytes(request_document):
                raise applier.WebSolDeploymentApplyError("STATE_CONFLICT")
            if phase == "APPLIED" and state_applied is not None:
                applier.verify_applied_deployment(state_applied)
                _emit(state_applied.public_receipt)
                return 0
            if phase in {"ROLLED_BACK", "CONFLICT", "ABORTED_ROLLED_BACK"}:
                raise applier.WebSolDeploymentApplyError("TRANSACTION_CONSUMED")
            if phase == "PREPARED" and state_applied is None:
                reconciled = applier.reconcile_prepared_deployment(state_prepared)
                resumed = (
                    _apply_and_persist_terminal_refusal(
                        request_document=state_request,
                        prepared=state_prepared,
                        state_path=args.state,
                        expected_state_digest=_state_digest,
                    )
                    if reconciled is None
                    else reconciled
                )
                resumed_state = _private_state_document(
                    request_document=state_request,
                    prepared=state_prepared,
                    phase="APPLIED",
                    applied=resumed,
                )
                _write_private_state(
                    args.state,
                    resumed_state,
                    expected_digest=_state_digest,
                )
                _emit(resumed.public_receipt)
                return 0
            raise applier.WebSolDeploymentApplyError("STATE_RECOVERY_REQUIRED")
        prepared = applier.prepare_deployment(
            bundle,
            plan,
            install_root=request_meta["install_root"],
            expected_uid=request_meta["expected_uid"],
            expected_gid=request_meta["expected_gid"],
            operation_key=request_meta["operation_key"],
        )
        if args.mode == "preflight":
            if args.state is not None:
                raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
            _emit(prepared.public_receipt)
            return 0
        if args.mode == "apply":
            if args.state is None:
                raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
            initial_state = _private_state_document(
                request_document=request_document,
                prepared=prepared,
                phase="PREPARED",
            )
            _write_private_state(args.state, initial_state, expected_digest=None)
            applied = _apply_and_persist_terminal_refusal(
                request_document=request_document,
                prepared=prepared,
                state_path=args.state,
                expected_state_digest=initial_state["state_digest"],
            )
            applied_state = _private_state_document(
                request_document=request_document,
                prepared=prepared,
                phase="APPLIED",
                applied=applied,
            )
            _write_private_state(
                args.state,
                applied_state,
                expected_digest=initial_state["state_digest"],
            )
            _emit(applied.public_receipt)
            return 0
        raise applier.WebSolDeploymentApplyError("INVALID_INPUT")
    except applier.WebSolDeploymentApplyError as exc:
        _emit(
            {
                "schema": ERROR_SCHEMA,
                "status": "REFUSED",
                "code": exc.code,
                "target_effect": (
                    "UNKNOWN"
                    if exc.code.endswith("EFFECT_UNKNOWN")
                    else "NONE"
                ),
                "production_acceptance_granted": False,
            },
            stream=sys.stderr,
        )
        return 2


def _state_parent(path: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    parent = path.parent
    try:
        info = parent.lstat()
    except OSError as exc:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    return parent


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if type(written) is not int or written <= 0:
            raise OSError("short write")
        offset += written


def _state_parent_binding_current(parent: Path, descriptor: int) -> bool:
    try:
        named = parent.lstat()
        opened = os.fstat(descriptor)
    except OSError:
        return False
    return (
        stat.S_ISDIR(named.st_mode)
        and not stat.S_ISLNK(named.st_mode)
        and (named.st_dev, named.st_ino) == (opened.st_dev, opened.st_ino)
        and named.st_uid == opened.st_uid == os.geteuid()
        and named.st_gid == opened.st_gid
        and stat.S_IMODE(named.st_mode) == stat.S_IMODE(opened.st_mode)
        and not (stat.S_IMODE(opened.st_mode) & 0o022)
    )


def _open_state_parent(path: Path) -> tuple[Path, int]:
    parent = _state_parent(path)
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise applier.WebSolDeploymentApplyError("STATE_EFFECT_UNKNOWN")
    try:
        descriptor = os.open(
            parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
    except OSError as exc:
        raise applier.WebSolDeploymentApplyError("STATE_EFFECT_UNKNOWN") from exc
    if not _state_parent_binding_current(parent, descriptor):
        os.close(descriptor)
        raise applier.WebSolDeploymentApplyError("STATE_EFFECT_UNKNOWN")
    return parent, descriptor


def _private_json_at(
    parent_descriptor: int,
    name: str,
    *,
    error_code: str,
) -> tuple[Any, bytes]:
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise applier.WebSolDeploymentApplyError(error_code)
    try:
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            stat.S_ISLNK(named.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or named.st_nlink != 1
            or named.st_uid != os.geteuid()
            or stat.S_IMODE(named.st_mode) != 0o600
        ):
            raise applier.WebSolDeploymentApplyError(error_code)
        flags = os.O_RDONLY | os.O_NOFOLLOW
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
                raise applier.WebSolDeploymentApplyError(error_code)
            payload = bytearray()
            while len(payload) <= MAX_JSON_BYTES:
                chunk = os.read(
                    descriptor,
                    min(65536, MAX_JSON_BYTES + 1 - len(payload)),
                )
                if not chunk:
                    break
                payload.extend(chunk)
            final = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if (
            len(payload) > MAX_JSON_BYTES
            or (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        ):
            raise applier.WebSolDeploymentApplyError(error_code)
        try:
            value = _decode_private_json_payload(bytes(payload))
        except applier.WebSolDeploymentApplyError as exc:
            raise applier.WebSolDeploymentApplyError(error_code) from exc
        return value, bytes(payload)
    except applier.WebSolDeploymentApplyError:
        raise
    except OSError as exc:
        raise applier.WebSolDeploymentApplyError(error_code) from exc


def _private_state_file(path: Path) -> Any:
    try:
        parent, parent_descriptor = _open_state_parent(path)
    except applier.WebSolDeploymentApplyError as exc:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID") from exc
    try:
        value, _payload = _private_json_at(
            parent_descriptor,
            path.name,
            error_code="STATE_INVALID",
        )
        if not _state_parent_binding_current(parent, parent_descriptor):
            raise applier.WebSolDeploymentApplyError("STATE_INVALID")
        return value
    finally:
        os.close(parent_descriptor)


def _write_private_state(
    path: Path,
    document: dict[str, object],
    *,
    expected_digest: str | None,
) -> None:
    parent, parent_descriptor = _open_state_parent(path)
    name = path.name
    temporary_name = f".{name}.mmx-state.tmp"
    try:
        try:
            current, _current_payload = _private_json_at(
                parent_descriptor,
                name,
                error_code="STATE_CONFLICT",
            )
        except applier.WebSolDeploymentApplyError as exc:
            try:
                os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
            except FileNotFoundError:
                existing = False
            except OSError as stat_exc:
                raise applier.WebSolDeploymentApplyError(
                    "STATE_EFFECT_UNKNOWN"
                ) from stat_exc
            else:
                existing = True
            if existing:
                raise
            current = None

        if current is not None:
            if expected_digest is None:
                raise applier.WebSolDeploymentApplyError("STATE_CONFLICT")
            if type(current) is not dict or current.get("state_digest") != expected_digest:
                raise applier.WebSolDeploymentApplyError("STATE_CONFLICT")
        elif expected_digest is not None:
            raise applier.WebSolDeploymentApplyError("STATE_EFFECT_UNKNOWN")

        try:
            os.stat(temporary_name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise applier.WebSolDeploymentApplyError("STATE_EFFECT_UNKNOWN") from exc
        else:
            raise applier.WebSolDeploymentApplyError("STATE_CONFLICT")

        payload = _canonical_bytes(document) + b"\n"
        if len(payload) > MAX_JSON_BYTES:
            raise applier.WebSolDeploymentApplyError("STATE_INVALID")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        descriptor = -1
        try:
            descriptor = os.open(
                temporary_name,
                flags,
                0o600,
                dir_fd=parent_descriptor,
            )
            _write_all(descriptor, payload)
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
            temp_info = os.fstat(descriptor)
        except OSError as exc:
            raise applier.WebSolDeploymentApplyError("STATE_EFFECT_UNKNOWN") from exc
        finally:
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError as exc:
                    raise applier.WebSolDeploymentApplyError(
                        "STATE_EFFECT_UNKNOWN"
                    ) from exc

        try:
            named = os.stat(
                temporary_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                stat.S_ISLNK(named.st_mode)
                or not stat.S_ISREG(named.st_mode)
                or named.st_dev != temp_info.st_dev
                or named.st_ino != temp_info.st_ino
                or named.st_uid != os.geteuid()
                or stat.S_IMODE(named.st_mode) != 0o600
                or named.st_size != len(payload)
            ):
                raise applier.WebSolDeploymentApplyError("STATE_EFFECT_UNKNOWN")
            os.replace(
                temporary_name,
                name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.fsync(parent_descriptor)
            _value, observed_payload = _private_json_at(
                parent_descriptor,
                name,
                error_code="STATE_EFFECT_UNKNOWN",
            )
            if observed_payload != payload:
                raise applier.WebSolDeploymentApplyError("STATE_EFFECT_UNKNOWN")
            if not _state_parent_binding_current(parent, parent_descriptor):
                raise applier.WebSolDeploymentApplyError("STATE_EFFECT_UNKNOWN")
        except applier.WebSolDeploymentApplyError:
            raise
        except OSError as exc:
            raise applier.WebSolDeploymentApplyError("STATE_EFFECT_UNKNOWN") from exc
    finally:
        os.close(parent_descriptor)


def _decode_preimage(
    raw: object,
    artifacts: dict[str, deployment.DeploymentArtifact],
) -> applier.ArtifactPreimage:
    row = _exact_dict(
        raw,
        frozenset(
            {
                "kind", "path", "path_digest", "prior_state",
                "prior_bytes_base64", "prior_sha256", "prior_mode",
                "prior_uid", "prior_gid",
            }
        ),
    )
    path = _absolute_path(row["path"])
    path_digest = _digest(row["path_digest"])
    if hashlib.sha256(str(path).encode("utf-8")).hexdigest() != path_digest:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    artifact = artifacts.get(str(path))
    kind = _string(row["kind"], maximum=64)
    if artifact is None or artifact.kind != kind:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    state = _string(row["prior_state"], maximum=16)
    encoded = row["prior_bytes_base64"]
    prior_sha = row["prior_sha256"]
    mode = row["prior_mode"]
    uid = row["prior_uid"]
    gid = row["prior_gid"]
    if state == "ABSENT":
        if any(value is not None for value in (encoded, prior_sha, mode, uid, gid)):
            raise applier.WebSolDeploymentApplyError("STATE_INVALID")
        content = None
    elif state == "PRESENT":
        encoded_limit = 4 * ((applier.MAX_PREIMAGE_BYTES + 2) // 3)
        if type(encoded) is not str or len(encoded) > encoded_limit:
            raise applier.WebSolDeploymentApplyError("STATE_INVALID")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            raise applier.WebSolDeploymentApplyError("STATE_INVALID") from None
        if len(content) > applier.MAX_PREIMAGE_BYTES:
            raise applier.WebSolDeploymentApplyError("STATE_INVALID")
        prior_sha = _digest(prior_sha)
        if hashlib.sha256(content).hexdigest() != prior_sha:
            raise applier.WebSolDeploymentApplyError("STATE_INVALID")
        mode = _integer(mode, maximum=_PERMISSION_BITS_MASK)
        uid = _integer(uid)
        gid = _integer(gid)
    else:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    return applier.ArtifactPreimage(
        kind=kind, path=path, path_digest=path_digest, prior_state=state,
        prior_bytes=content, prior_sha256=prior_sha, prior_mode=mode,
        prior_uid=uid, prior_gid=gid,
    )


def _decode_directory_preimage(
    raw: object,
    allowed_paths: set[str],
) -> applier.DirectoryPreimage:
    row = _exact_dict(
        raw,
        frozenset(
            {
                "path", "path_digest", "prior_state", "prior_dev",
                "prior_ino", "prior_mode", "prior_uid", "prior_gid",
            }
        ),
    )
    path = _absolute_path(row["path"])
    if str(path) not in allowed_paths:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    path_digest = _digest(row["path_digest"])
    if hashlib.sha256(str(path).encode("utf-8")).hexdigest() != path_digest:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    state = _string(row["prior_state"], maximum=16)
    dev = row["prior_dev"]
    ino = row["prior_ino"]
    mode = row["prior_mode"]
    uid = row["prior_uid"]
    gid = row["prior_gid"]
    if state == "ABSENT":
        if any(value is not None for value in (dev, ino, mode, uid, gid)):
            raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    elif state == "PRESENT":
        dev = _integer(dev, maximum=2**63 - 1)
        ino = _integer(ino, maximum=2**63 - 1)
        mode = _integer(mode, maximum=_PERMISSION_BITS_MASK)
        uid = _integer(uid)
        gid = _integer(gid)
    else:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    return applier.DirectoryPreimage(
        path=path, path_digest=path_digest, prior_state=state,
        prior_dev=dev, prior_ino=ino, prior_mode=mode,
        prior_uid=uid, prior_gid=gid,
    )


def _directory_paths(
    install_root: Path,
    bundle: deployment.DeploymentBundle,
) -> set[str]:
    paths = {str(install_root)}
    for artifact in bundle.artifacts:
        try:
            relative = artifact.destination.parent.relative_to(install_root)
        except ValueError as exc:
            raise applier.WebSolDeploymentApplyError("STATE_INVALID") from exc
        current = install_root
        for part in relative.parts:
            current = current / part
            paths.add(str(current))
    return paths


def _decode_private_state(
    raw: object,
) -> tuple[
    str, dict[str, Any], applier.PreparedDeployment,
    applier.AppliedDeployment | None, str,
]:
    row = _exact_dict(
        raw,
        frozenset(
            {
                "schema", "phase", "request", "prepared", "applied",
                "production_acceptance_granted", "state_digest",
            }
        ),
    )
    if (
        row["schema"] != PRIVATE_STATE_SCHEMA
        or row["production_acceptance_granted"] is not False
    ):
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    provided_digest = _digest(row["state_digest"])
    unsigned = dict(row)
    unsigned.pop("state_digest")
    if hashlib.sha256(_canonical_bytes(unsigned)).hexdigest() != provided_digest:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    phase = _string(row["phase"], maximum=32)
    if phase not in {
        "PREPARED", "APPLIED", "ROLLED_BACK", "CONFLICT",
        "ABORTED_ROLLED_BACK",
    }:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    request_document = row["request"]
    if type(request_document) is not dict:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    bundle, plan, request_meta = _decode_request(request_document)
    prepared_row = _exact_dict(
        row["prepared"],
        frozenset(
            {"prepared_digest", "cleanup_nonce", "preimages", "directory_preimages"}
        ),
    )
    artifacts = {str(item.destination): item for item in bundle.artifacts}
    preimages = tuple(
        _decode_preimage(item, artifacts)
        for item in _exact_list(prepared_row["preimages"])
    )
    if (
        len(preimages) != len(artifacts)
        or len({str(row.path) for row in preimages}) != len(preimages)
        or sum(len(row.prior_bytes or b"") for row in preimages)
        > applier.MAX_TOTAL_PREIMAGE_BYTES
    ):
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    allowed_directories = _directory_paths(request_meta["install_root"], bundle)
    directory_preimages = tuple(
        _decode_directory_preimage(item, allowed_directories)
        for item in _exact_list(prepared_row["directory_preimages"])
    )
    if (
        len(directory_preimages) != len(allowed_directories)
        or {str(item.path) for item in directory_preimages} != allowed_directories
    ):
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    prepared_digest = _digest(prepared_row["prepared_digest"])
    try:
        cleanup_nonce = applier._cleanup_nonce(  # noqa: SLF001
            prepared_row["cleanup_nonce"]
        )
    except applier.WebSolDeploymentApplyError as exc:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID") from exc
    prepared = applier.PreparedDeployment(
        operation_key=request_meta["operation_key"], bundle=bundle, plan=plan,
        install_root=request_meta["install_root"],
        expected_uid=request_meta["expected_uid"],
        expected_gid=request_meta["expected_gid"],
        preimages=preimages, directory_preimages=directory_preimages,
        cleanup_nonce=cleanup_nonce, prepared_digest=prepared_digest,
    )
    try:
        recomputed = applier._prepared_digest_from_state(  # noqa: SLF001
            operation_key=prepared.operation_key, bundle=bundle, plan=plan,
            expected_uid=prepared.expected_uid, expected_gid=prepared.expected_gid,
            cleanup_nonce=cleanup_nonce,
            preimages=preimages, directory_preimages=directory_preimages,
        )
    except applier.WebSolDeploymentApplyError as exc:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID") from exc
    if recomputed != prepared_digest:
        raise applier.WebSolDeploymentApplyError("STATE_INVALID")
    applied_value = row["applied"]
    applied: applier.AppliedDeployment | None = None
    if phase in {"PREPARED", "CONFLICT", "ABORTED_ROLLED_BACK"}:
        if applied_value is not None:
            raise applier.WebSolDeploymentApplyError("STATE_INVALID")
        if phase != "PREPARED":
            prepared._state = phase
    else:
        applied_row = _exact_dict(
            applied_value,
            frozenset({"changed_paths", "created_directories", "reconciled_paths"}),
        )
        artifact_paths = set(artifacts)
        directory_paths = {str(item.path) for item in directory_preimages}
        changed = tuple(_absolute_path(item) for item in _exact_list(applied_row["changed_paths"]))
        created = tuple(_absolute_path(item) for item in _exact_list(applied_row["created_directories"]))
        reconciled = tuple(_absolute_path(item) for item in _exact_list(applied_row["reconciled_paths"]))
        if (
            len({str(item) for item in changed}) != len(changed)
            or len({str(item) for item in created}) != len(created)
            or len({str(item) for item in reconciled}) != len(reconciled)
            or not {str(item) for item in changed}.issubset(artifact_paths)
            or not {str(item) for item in created}.issubset(directory_paths)
            or not {str(item) for item in reconciled}.issubset({str(item) for item in changed})
        ):
            raise applier.WebSolDeploymentApplyError("STATE_INVALID")
        expected_changed = {
            str(item.path) for item in plan.changes if item.action != "UNCHANGED"
        }
        expected_created = {
            str(item.path) for item in directory_preimages
            if item.prior_state == "ABSENT"
        }
        if (
            {str(item) for item in changed} != expected_changed
            or {str(item) for item in created} != expected_created
        ):
            raise applier.WebSolDeploymentApplyError("STATE_INVALID")
        prepared._state = "APPLIED" if phase == "APPLIED" else "ROLLED_BACK"
        applied = applier.AppliedDeployment(
            prepared=prepared,
            changed_paths=changed,
            created_directories=created,
            reconciled_paths=reconciled,
            _state="APPLIED" if phase == "APPLIED" else "ROLLED_BACK",
        )
    return phase, request_document, prepared, applied, provided_digest


if __name__ == "__main__":
    raise SystemExit(main())
