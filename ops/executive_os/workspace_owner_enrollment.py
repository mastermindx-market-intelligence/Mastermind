"""Workspace owner binding compiler — pure compile plus CLI effect edge.

Converts an authorized local owner request (paths only) plus a validated
Workspace ResourcePolicy into the closed
``mastermind.workspace_acquisition_bindings.v1`` wire document that the
existing validator already accepts.

The compiler does NOT issue authority, register a client, install a config,
start a service, mint permission receipts, or open any second auth /
broker / reader / lifecycle plane. It does NOT import Runtime, the control
plane, an HTTP client, an OAuth client, an MCP server, subprocess,
launchctl, keychain, or any token store.

Public surface
--------------
``compile_bindings(policy, values)``
    Pure function: validated ``ResourcePolicy`` + closed value-bearing
    request mapping → the validated binding dict. Performs the policy
    fence, the workspace fence, the allowlist fence, the duplicate-client
    fence, the closed-slot fence, and the textual-value fence, then
    round-trips the result through ``validate_workspace_bindings``.

``main(argv=None)``
    Effect edge that loads the policy + request paths, performs the
    private-file fences, performs the output/parent/root fences, and
    writes the closed document with one exclusive atomic write. Emits
    one redacted receipt on stdout and a fixed bounded refusal text on
    stderr; never raises through to a traceback.

The effect edge enforces every safety fence through descriptor-bound
operations: every authority file and every private slot input is opened
once with ``O_RDONLY|O_NOFOLLOW|O_CLOEXEC`` and the closed payload is
written to one descriptor-bound directory descriptor via
``O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC``. No path is ever reopened. The
single failure path through final verification removes only the
descriptor-bound own inode when the directory entry still matches.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from typing import Any, Mapping

from common.executive_workspace_contract import (
    BINDINGS_SCHEMA,
    RESOURCE,
    SCOPE,
    canonical,
)
from integrations.business_mcp_auth.claims import _client_ref
from integrations.business_mcp_auth.contracts import (
    AuthError,
    ResourcePolicy,
    load_resource_policy,
    subject_digest,
    validate_resource_policy,
)
from integrations.mastermind_workspace_app.contract import (
    validate_workspace_bindings,
)


REQUEST_SCHEMA = "mastermind.workspace_owner_binding_request.v1"
RECEIPT_SCHEMA = "mastermind.workspace_owner_binding_compiler_receipt.v1"
PROFILE_ORDER = ("web", "mac")
SLOT_KEYS = frozenset({
    "enabled", "client_id_file", "subject_file", "permission_receipt_file",
})
VALUE_KEYS = frozenset({
    "enabled", "client_id", "subject", "permission_receipt",
})
_RECEIPT_KEYS = frozenset({
    "schema", "status", "output_sha256", "enabled_profiles", "output_path",
})
_MAX_TEXT_BYTES = 4096
_MAX_RECEIPT_BYTES = 1 << 20
_MAX_AUTHORITY_BYTES = 1 << 20
_MAX_OUTPUT_BYTES = 1 << 24
_MAX_PATH_BYTES = 4096
_REFUSAL_TEXT = "workspace owner binding compiler refused"
_REFUSAL_EXIT = 1
_GROUP_OR_WORLD = stat.S_IRWXG | stat.S_IRWXO
_PARENT_WRITABLE_BITS = stat.S_IWGRP | stat.S_IWOTH
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class WorkspaceOwnerCompilerError(RuntimeError):
    """One typed refusal; never echoes paths, raw bytes, or policy contents."""

    def __init__(self, code: str = "refused") -> None:
        super().__init__(_REFUSAL_TEXT)
        self.code = code


def _refuse(code: str = "refused") -> "None":
    raise WorkspaceOwnerCompilerError(code)


def _close_checked(fd: int, *, label: str) -> None:
    """Close an owned descriptor or turn the close failure into a refusal."""

    try:
        os.close(fd)
    except OSError:
        _refuse(f"{label}_close")


def _is_absolute_string(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("/")
        and "\x00" not in value
        and 1 <= len(value) <= _MAX_PATH_BYTES
    )


def _require_absolute_path(value: Any, label: str) -> str:
    if not _is_absolute_string(value):
        _refuse(f"{label}_not_absolute")
    return value


def _check_text_shape(value: str, *, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        _refuse(f"{label}_type")
    if not value or value != value.strip():
        _refuse(f"{label}_blank")
    if _CONTROL_RE.search(value):
        _refuse(f"{label}_control")
    if len(value.encode("utf-8")) > maximum:
        _refuse(f"{label}_oversized")
    return value


def _validate_request_shape(request: Any) -> None:
    """Validate the closed on-disk request mapping (path-bearing form)."""

    if not isinstance(request, Mapping):
        _refuse("request_shape")
    if set(request) != {"schema", "profiles"}:
        _refuse("request_shape")
    if request["schema"] != REQUEST_SCHEMA:
        _refuse("request_schema")
    profiles = request["profiles"]
    if not isinstance(profiles, Mapping) or set(profiles) != set(PROFILE_ORDER):
        _refuse("request_profiles")
    for name in PROFILE_ORDER:
        slot = profiles[name]
        if not isinstance(slot, Mapping) or set(slot) != SLOT_KEYS:
            _refuse("request_slot")
        enabled = slot["enabled"]
        if not isinstance(enabled, bool):
            _refuse("request_enabled")
        for key in ("client_id_file", "subject_file", "permission_receipt_file"):
            value = slot[key]
            if enabled:
                _require_absolute_path(value, f"{name}_{key}")
            else:
                if value is not None:
                    _refuse(f"{name}_{key}_must_be_null")


def _validate_values_shape(values: Any) -> None:
    """Validate the closed value-bearing mapping passed to ``compile_bindings``."""

    if not isinstance(values, Mapping) or set(values) != set(PROFILE_ORDER):
        _refuse("values_shape")
    for name in PROFILE_ORDER:
        slot = values[name]
        if not isinstance(slot, Mapping) or set(slot) != VALUE_KEYS:
            _refuse("values_slot")
        if not isinstance(slot["enabled"], bool):
            _refuse("values_enabled")


def _build_binding(
    policy: Any,
    *,
    client_id: str,
    subject: str,
    receipt_bytes: bytes,
    issuer_digest: str,
) -> dict:
    """Compute the closed one-slot binding dict. Caller enforces duplicate-client."""

    subject_ref = subject_digest(issuer=policy.issuer, subject=subject)
    if subject_ref not in policy.allowed_subject_digests:
        _refuse("subject_not_allowlisted")
    client_ref = _client_ref({"client_id": client_id}, policy.issuer)
    if not _HEX64.fullmatch(client_ref):
        _refuse("client_ref_shape")
    permission_digest = hashlib.sha256(receipt_bytes).hexdigest()
    if not _HEX64.fullmatch(permission_digest):
        _refuse("permission_digest_shape")
    return {
        "policy_id": policy.policy_id,
        "issuer_digest": issuer_digest,
        "subject_digest": subject_ref,
        "client_ref": client_ref,
        "resource": RESOURCE,
        "scopes": [SCOPE],
        "permission_digest": permission_digest,
    }


def compile_bindings(
    policy: Any,
    values: Mapping[str, Mapping[str, Any]],
) -> dict:
    """Pure compile: policy + closed value-bearing request → validated binding."""

    if not isinstance(policy, ResourcePolicy):
        _refuse("policy_type")
    policy = validate_resource_policy(policy)
    if policy.resource != RESOURCE or policy.required_scopes != (SCOPE,):
        _refuse("workspace_fence")
    _validate_values_shape(values)

    issuer_digest = hashlib.sha256(policy.issuer.encode("utf-8")).hexdigest()
    profiles: dict = {}
    seen_clients: set = set()
    for name in PROFILE_ORDER:
        slot = values[name]
        if not slot["enabled"]:
            profiles[name] = {"enabled": False, "binding": None}
            continue
        client_id = _check_text_shape(
            slot["client_id"], label=f"{name}_client_id", maximum=_MAX_TEXT_BYTES,
        )
        subject = _check_text_shape(
            slot["subject"], label=f"{name}_subject", maximum=_MAX_TEXT_BYTES,
        )
        receipt = slot["permission_receipt"]
        if not isinstance(receipt, (bytes, bytearray)):
            _refuse(f"{name}_receipt_type")
        receipt_bytes = bytes(receipt)
        if not receipt_bytes:
            _refuse(f"{name}_receipt_empty")
        if len(receipt_bytes) > _MAX_RECEIPT_BYTES:
            _refuse(f"{name}_receipt_oversized")
        binding = _build_binding(
            policy,
            client_id=client_id,
            subject=subject,
            receipt_bytes=receipt_bytes,
            issuer_digest=issuer_digest,
        )
        client_ref = binding["client_ref"]
        if client_ref in seen_clients:
            _refuse("duplicate_client")
        seen_clients.add(client_ref)
        profiles[name] = {"enabled": True, "binding": binding}

    document = {"schema": BINDINGS_SCHEMA, "profiles": profiles}
    return validate_workspace_bindings(document, policy)


# ---------------------------------------------------------------------------
# CLI edge — descriptor-bound safe-path fences.
# ---------------------------------------------------------------------------


def _open_private_fd(
    path: str, *, label: str, maximum: int,
) -> tuple[int, os.stat_result, bytes]:
    """Open ``path`` once with O_RDONLY|O_NOFOLLOW|O_CLOEXEC and read fully.

    Returns ``(fd, fstat, bytes)``. Caller owns the descriptor.
    Validates root-owned regular file with no group/world bits, one link,
    and size within ``maximum`` (ceiling is enforced both before and
    during the bounded read). Never reopens by path.
    """

    try:
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError:
        _refuse(f"{label}_open")
    try:
        info = os.fstat(fd)
    except OSError:
        _close_checked(fd, label=f"{label}_input")
        _refuse(f"{label}_fstat")
    if stat.S_ISLNK(info.st_mode):
        _close_checked(fd, label=f"{label}_input")
        _refuse(f"{label}_symlink")
    if not stat.S_ISREG(info.st_mode):
        _close_checked(fd, label=f"{label}_input")
        _refuse(f"{label}_not_regular")
    if info.st_uid != 0:
        _close_checked(fd, label=f"{label}_input")
        _refuse(f"{label}_owner")
    mode = stat.S_IMODE(info.st_mode)
    if mode & _GROUP_OR_WORLD:
        _close_checked(fd, label=f"{label}_input")
        _refuse(f"{label}_mode")
    if info.st_nlink != 1:
        _close_checked(fd, label=f"{label}_input")
        _refuse(f"{label}_link")
    if info.st_size > maximum:
        _close_checked(fd, label=f"{label}_input")
        _refuse(f"{label}_oversized")

    try:
        data = _bounded_read(fd, maximum, label=label)
    except WorkspaceOwnerCompilerError:
        _close_checked(fd, label=f"{label}_input")
        raise
    return fd, info, data


def _bounded_read(fd: int, maximum: int, *, label: str) -> bytes:
    """Read from ``fd`` enforcing a hard ceiling and rejecting any extra byte."""

    chunks = []
    remaining = maximum
    try:
        while remaining > 0:
            try:
                chunk = os.read(fd, remaining)
            except OSError:
                _refuse(f"{label}_unreadable")
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        if remaining == 0:
            try:
                tail = os.read(fd, 1)
            except OSError:
                _refuse(f"{label}_unreadable")
            if tail:
                _refuse(f"{label}_oversized")
    finally:
        pass
    return b"".join(chunks)


def _read_text_private(path: str, *, label: str) -> str:
    """Descriptor-bound private text read with strict shape checks."""

    fd, _info, raw = _open_private_fd(
        path, label=label, maximum=_MAX_TEXT_BYTES,
    )
    try:
        if len(raw) > _MAX_TEXT_BYTES:
            _refuse(f"{label}_oversized")
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError:
            _refuse(f"{label}_decode")
    finally:
        _close_checked(fd, label=f"{label}_input")
    if not value or value != value.strip():
        _refuse(f"{label}_blank")
    if _CONTROL_RE.search(value):
        _refuse(f"{label}_control")
    return value


def _read_receipt_private(path: str, *, label: str) -> bytes:
    """Descriptor-bound opaque bounded bytes read."""

    fd, _info, raw = _open_private_fd(
        path, label=label, maximum=_MAX_RECEIPT_BYTES,
    )
    try:
        return raw
    finally:
        _close_checked(fd, label=f"{label}_input")


def _read_authority_json(path: str, *, label: str) -> Any:
    """Descriptor-bound JSON read for an authority file (policy / request)."""

    fd, _info, raw = _open_private_fd(
        path, label=f"{label}_authority", maximum=_MAX_AUTHORITY_BYTES,
    )
    try:
        if not raw:
            _refuse(f"{label}_empty")
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _refuse(f"{label}_decode")
    finally:
        _close_checked(fd, label=f"{label}_authority")


def _split_output_path(output: str) -> tuple[str, str]:
    parent = os.path.dirname(output)
    basename = os.path.basename(output)
    if not parent or not basename:
        _refuse("output_path")
    if basename != os.path.splitdrive(basename)[1].lstrip(os.sep):
        _refuse("output_path")
    if os.sep in basename or "/" in basename or "\x00" in basename:
        _refuse("output_path")
    if basename in (".", ".."):
        _refuse("output_path")
    if not _is_absolute_string(parent) or not _is_absolute_string(output):
        _refuse("output_not_absolute")
    return parent, basename


def _open_parent_fd(parent: str) -> tuple[int, os.stat_result]:
    try:
        fd = os.open(
            parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError:
        _refuse("parent_open")
    try:
        info = os.fstat(fd)
    except OSError:
        _close_checked(fd, label="parent")
        _refuse("parent_fstat")
    if stat.S_ISLNK(info.st_mode):
        _close_checked(fd, label="parent")
        _refuse("parent_symlink")
    if not stat.S_ISDIR(info.st_mode):
        _close_checked(fd, label="parent")
        _refuse("parent_not_dir")
    if info.st_uid != 0:
        _close_checked(fd, label="parent")
        _refuse("parent_owner")
    if stat.S_IMODE(info.st_mode) & _PARENT_WRITABLE_BITS:
        _close_checked(fd, label="parent")
        _refuse("parent_writable")
    return fd, info


def _exclusive_create_in_parent(
    parent_fd: int, basename: str,
) -> tuple[int, os.stat_result]:
    try:
        fd = os.open(
            basename,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o400,
            dir_fd=parent_fd,
        )
    except OSError:
        _refuse("output_create")
    try:
        info = os.fstat(fd)
    except OSError:
        _close_checked(fd, label="output")
        _refuse("output_fstat")
    return fd, info


class _OutputCursor:
    """One descriptor-bound output under one validated parent descriptor.

    Funnels every post-create failure through one conservative refusal.
    No conditional unlink primitive is exposed, so cleanup never removes
    a pathname; this guarantees that a foreign replacement survives.
    """

    def __init__(self, parent_fd: int, parent_path: str, basename: str) -> None:
        self.parent_fd = parent_fd
        self.parent_path = parent_path
        self.basename = basename
        self.fd: int | None = None
        self.dev: int = 0
        self.ino: int = 0
        self.created_mode = 0o400
        self.committed = False

    def capture_create(self, fd: int, info: os.stat_result) -> None:
        self.fd = fd
        self.dev = info.st_dev
        self.ino = info.st_ino

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        """Close the owned output descriptor; a close failure is material."""

        if self.fd is None:
            return
        fd = self.fd
        self.fd = None
        _close_checked(fd, label="output")

    def abort(self, code: str) -> "None":
        """Close the owned descriptor and refuse without pathname cleanup."""

        if self.committed:
            _refuse(code)
        if self.fd is not None:
            self.close()
        # No conditional unlink primitive is available; preserve the entry.
        _refuse(code)


def _complete_write(cursor: _OutputCursor, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        try:
            written = os.write(cursor.fd, view)
        except OSError:
            cursor.abort("short_write")
        if written <= 0:
            cursor.abort("short_write")
        view = view[written:]


def _finalize_output(cursor: _OutputCursor) -> None:
    """Run fchmod, fsync, parent fsync, readback; one path through cleanup."""

    assert cursor.fd is not None
    try:
        os.fchmod(cursor.fd, 0o400)
    except OSError:
        cursor.abort("output_fchmod")
    try:
        os.fsync(cursor.fd)
    except OSError:
        cursor.abort("output_fsync")

    # Readback through a fresh descriptor bound to the same parent fd.
    try:
        read_fd = os.open(
            cursor.basename,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=cursor.parent_fd,
        )
    except OSError:
        cursor.abort("readback_open")
    try:
        try:
            read_info = os.fstat(read_fd)
        except OSError:
            cursor.abort("readback_fstat")
        if (
            read_info.st_dev != cursor.dev
            or read_info.st_ino != cursor.ino
            or read_info.st_uid != 0
            or read_info.st_nlink != 1
            or not stat.S_ISREG(read_info.st_mode)
            or stat.S_IMODE(read_info.st_mode) != 0o400
            or read_info.st_size != len(cursor._payload_size)
        ):
            cursor.abort("readback_identity")
        # Bounded readback.
        remaining = len(cursor._payload_size)
        chunks = []
        while remaining > 0:
            try:
                chunk = os.read(read_fd, remaining)
            except OSError:
                cursor.abort("readback_unreadable")
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        if remaining == 0:
            try:
                tail = os.read(read_fd, 1)
            except OSError:
                cursor.abort("readback_unreadable")
            if tail:
                cursor.abort("readback_oversized")
        readback = b"".join(chunks)
    finally:
        _close_checked(read_fd, label="readback")

    if readback != cursor._payload_size:
        cursor.abort("readback_mismatch")

    try:
        os.fsync(cursor.parent_fd)
    except OSError:
        cursor.abort("parent_fsync")


def write_binding_document(
    output: str,
    payload: bytes,
    *,
    parent_fd: int | None = None,
) -> int:
    """Write ``payload`` to ``output`` once with descriptor-bound fencing.

    When ``parent_fd`` is provided, the caller has already validated the
    parent descriptor; ``output`` must use the same basename and the
    directory entry is bound through ``dir_fd`` to that descriptor.
    """

    if not isinstance(payload, (bytes, bytearray)):
        _refuse("payload_type")
    payload_bytes = bytes(payload)
    if len(payload_bytes) > _MAX_OUTPUT_BYTES:
        _refuse("payload_oversized")

    owns_parent = parent_fd is None
    if parent_fd is None:
        parent_path, basename = _split_output_path(output)
        parent_fd, _parent_info = _open_parent_fd(parent_path)
    else:
        parent_path = "<prevalidated>"
        basename = os.path.basename(output)
        if not basename or os.sep in basename or "/" in basename:
            _refuse("output_path")
        if basename in (".", ".."):
            _refuse("output_path")

    cursor = _OutputCursor(parent_fd, parent_path, basename)
    cursor._payload_size = payload_bytes  # internal stash for finalize
    try:
        try:
            fd, info = _exclusive_create_in_parent(parent_fd, basename)
        except WorkspaceOwnerCompilerError:
            cursor.abort("output_create")
        cursor.capture_create(fd, info)
        try:
            _complete_write(cursor, payload_bytes)
            _finalize_output(cursor)
            cursor.close()
        except WorkspaceOwnerCompilerError as exc:
            cursor.abort(exc.code)
        cursor.commit()
    finally:
        if owns_parent:
            _close_checked(parent_fd, label="parent")
    return cursor.ino


# ---------------------------------------------------------------------------
# Closed, non-emitting CLI parser.
# ---------------------------------------------------------------------------


def _parse_argv(argv: list[str] | None) -> tuple[str, str, str]:
    """Reject every malformed input without echoing values or program names."""

    if argv is None:
        _refuse("argv_none")
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        _refuse("argv_shape")
    if len(argv) != 6:
        _refuse("argv_length")
    if argv[0] != "--policy" or argv[2] != "--request" or argv[4] != "--output":
        _refuse("argv_options")
    for value in (argv[1], argv[3], argv[5]):
        if not isinstance(value, str) or "\x00" in value:
            _refuse("argv_value")
    return argv[1], argv[3], argv[5]


def _build_receipt(
    document: Mapping[str, Any], output_path: str, payload: bytes,
) -> dict:
    enabled = sorted(
        name for name, slot in document["profiles"].items() if slot["enabled"]
    )
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "compiled",
        "output_sha256": hashlib.sha256(payload).hexdigest(),
        "enabled_profiles": enabled,
        "output_path": output_path,
    }
    if set(receipt) != _RECEIPT_KEYS:
        _refuse("receipt_shape")
    return receipt


def _emit_receipt(receipt: Mapping[str, Any]) -> None:
    encoded = json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    sys.stdout.write(encoded)
    sys.stdout.flush()


def _stderr_refuse() -> None:
    sys.stderr.write(_REFUSAL_TEXT + "\n")
    sys.stderr.flush()


def _refusal_exit() -> int:
    """Best-effort fixed refusal without allowing an I/O traceback to escape."""

    try:
        _stderr_refuse()
    except (OSError, ValueError):
        pass
    return _REFUSAL_EXIT


def _serialize_document(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    """Effect edge; never raises — every refusal becomes the fixed stderr."""

    try:
        policy_path, request_path, output_path = _parse_argv(argv)

        geteuid = getattr(os, "geteuid", None)
        if geteuid is not None and geteuid() != 0:
            return _refusal_exit()

        _split_output_path(output_path)

        policy_value = _read_authority_json(policy_path, label="policy")
        policy = load_resource_policy(policy_value)

        request_value = _read_authority_json(request_path, label="request")
        _validate_request_shape(request_value)

        values: dict = {}
        for name in PROFILE_ORDER:
            slot = request_value["profiles"][name]
            if not slot["enabled"]:
                values[name] = {
                    "enabled": False,
                    "client_id": None,
                    "subject": None,
                    "permission_receipt": None,
                }
                continue
            client_id = _read_text_private(
                slot["client_id_file"], label=f"{name}_client_id",
            )
            subject = _read_text_private(
                slot["subject_file"], label=f"{name}_subject",
            )
            permission_receipt = _read_receipt_private(
                slot["permission_receipt_file"],
                label=f"{name}_receipt",
            )
            if not client_id:
                _refuse(f"{name}_client_id_blank")
            if not subject:
                _refuse(f"{name}_subject_blank")
            if not permission_receipt:
                _refuse(f"{name}_receipt_blank")
            values[name] = {
                "enabled": True,
                "client_id": client_id,
                "subject": subject,
                "permission_receipt": permission_receipt,
            }

        document = compile_bindings(policy, values)
        payload = _serialize_document(document)

        write_binding_document(output_path, payload)
        receipt = _build_receipt(document, output_path, payload)
    except WorkspaceOwnerCompilerError:
        return _refusal_exit()
    except AuthError:
        return _refusal_exit()
    except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return _refusal_exit()

    try:
        _emit_receipt(receipt)
    except (OSError, ValueError, TypeError):
        return _refusal_exit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
