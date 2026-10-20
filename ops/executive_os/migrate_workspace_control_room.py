"""Workspace Control Room migration tool (stdlib only).

Seat command:

    sudo /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \\
      -I -S -B \\
      "$SOURCE_REPO/ops/executive_os/migrate_workspace_control_room.py" \\
      --input "$CONTROL_INPUT" --output "$CONTROL_INPUT_UNIX"

The live control.json is never hand-edited. This tool reads the host's
legacy ``workspace_control_room: {"port": <int>}`` stanza, replaces it in
place (key position preserved) with the closed unix/launchd stanza that
install.sh projects and load_control_config admits, and writes the
successor next to the input. Any failure refuses loudly and writes nothing;
the input file is never modified. A legacy stanza that reaches install.sh
or load_control_config is refused loudly by the shared
``validate_workspace_control_room`` validator.

Exit codes: 0 migrated, 2 refused, 3 not needed, 64 usage.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import pathlib
import stat as _stat_module
import sys
from typing import Any


_MAX_INPUT_BYTES = 1024 * 1024
_OUTPUT_MODE = 0o600
_USAGE_EXIT = 64
_REFUSE_EXIT = 2
_NOT_NEEDED_EXIT = 3


# Symbols resolved from phase1c at module import; the values are filled in by
# _import_phase1c() before any user-facing entry point runs.
_CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET: str = ""
_WORKSPACE_CONTROL_ROOM_SOCKET_NAME: str = ""


def _resolve_release_root() -> pathlib.Path:
    """Locate the release root as the parent of ops/executive_os/."""

    return pathlib.Path(__file__).resolve().parents[2]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="migrate_workspace_control_room.py",
        description=(
            "Convert a legacy workspace_control_room {\"port\": int} stanza into "
            "the closed unix/launchd stanza, writing the successor next to the "
            "input without touching it."
        ),
    )
    parser.add_argument("--input", required=True,
                        help="absolute path of the legacy control config (read-only)")
    parser.add_argument("--output", required=True,
                        help="absolute path of the migrated successor (must not exist)")
    args = parser.parse_args(argv[1:])
    input_path = pathlib.Path(args.input)
    output_path = pathlib.Path(args.output)
    if not input_path.is_absolute():
        parser.error("--input must be an absolute path")
    if not output_path.is_absolute():
        parser.error("--output must be an absolute path")
    return args


def _read_input(path: pathlib.Path) -> bytes:
    """Read with O_NOFOLLOW; refuse symlinks, missing files, oversize, non-regular.

    Loops until ``st_size`` bytes are read; a short read or premature EOF
    refuses so the input's content cannot mutate between the fstat that
    fixes the bound and the read that fills it.
    """

    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    eloop = getattr(errno, "ELOOP", 40)
    enoent = getattr(errno, "ENOENT", 2)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        if exc.errno in (eloop,):
            _refuse("input is not a regular file")
        if exc.errno == enoent:
            _refuse("input path does not exist")
        _refuse("input unavailable")
    try:
        info = os.fstat(fd)
        if not _stat_module.S_ISREG(info.st_mode):
            _refuse("input is not a regular file")
        if info.st_size > _MAX_INPUT_BYTES:
            _refuse("input exceeds 1 MiB bound")
        if info.st_size == 0:
            _refuse("input is empty")
        expected = info.st_size
        view = bytearray(expected)
        written = 0
        while written < expected:
            chunk = os.read(fd, expected - written)
            if chunk == b"":
                _refuse("input changed while reading")
            view[written:written + len(chunk)] = chunk
            written += len(chunk)
        # The file must not have grown between fstat and the read that filled
        # the bound; one extra byte after st_size means the bound was a lie.
        trailing = os.read(fd, 1)
        if trailing != b"":
            _refuse("input changed while reading")
        return bytes(view)
    finally:
        os.close(fd)


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _value in pairs:
        if key in seen:
            _refuse("duplicate key in input")
        seen.add(key)
    # Build an ordered dict that preserves the original key order.
    ordered: dict[str, Any] = {}
    for key, value in pairs:
        ordered[key] = value
    return ordered


def _refuse_constant(_name: str) -> Any:
    _refuse("input contains a non-finite JSON number")


def _parse_json(raw: bytes) -> dict[str, Any]:
    """Strict JSON; refuse duplicate keys, NaN/Infinity, non-dict top level."""

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _refuse("input is not UTF-8")
    decoder = json.JSONDecoder(object_pairs_hook=_reject_duplicates, parse_constant=_refuse_constant)
    try:
        document = decoder.decode(text)
    except json.JSONDecodeError:
        _refuse("input is not valid JSON")
    if type(document) is not dict:
        _refuse("top-level JSON value must be an object")
    return document


def _validate_legacy(document: dict[str, Any]) -> int:
    if "workspace_acquisition" not in document:
        _refuse("workspace_acquisition key absent")
    if "control_uid" not in document:
        _refuse("control_uid key absent")
    raw_uid = document["control_uid"]
    if type(raw_uid) is bool or type(raw_uid) is not int:
        _refuse("control_uid must be a positive integer")
    if raw_uid <= 0:
        _refuse("control_uid must be a positive integer")
    if "workspace_control_room" not in document:
        _not_needed("workspace_control_room key absent")
    stanza = document["workspace_control_room"]
    if type(stanza) is dict and "transport" in stanza and "port" not in stanza:
        # Already in the new shape; re-validate through it to confirm. A
        # malformed successor shape (transport mismatch, non-canonical
        # socket_path, extra peer uid, ...) is a refused topology, not a
        # "not needed" silent pass.
        try:
            validate_workspace_control_room(stanza, control_uid=int(raw_uid))
        except ServiceError as exc:
            _refuse("workspace_control_room unix stanza fails the shared validator: " + str(exc))
        _not_needed("workspace_control_room already in unix/launchd shape")
    if not (type(stanza) is dict and set(stanza) == {"port"}):
        _refuse("workspace_control_room must be exactly {\"port\": int}")
    port = stanza["port"]
    if type(port) is bool or type(port) is not int:
        _refuse("workspace_control_room.port must be an integer")
    if port < 1 or port > 65535:
        _refuse("workspace_control_room.port out of range")
    return int(port)


def _build_successor(document: dict[str, Any], *, port: int, control_uid: int) -> dict[str, Any]:
    """Build the same dict with workspace_control_room replaced in place."""

    new_stanza = {
        "transport": "unix",
        "socket_path": _CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET,
        "launchd_socket_name": _WORKSPACE_CONTROL_ROOM_SOCKET_NAME,
        "allowed_peer_uids": [int(control_uid)],
    }
    successor: dict[str, Any] = {}
    for key, value in document.items():
        if key == "workspace_control_room":
            successor[key] = new_stanza
        else:
            successor[key] = value
    return successor


def _write_output(path: pathlib.Path, document: dict[str, Any]) -> bytes:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(str(path), flags, _OUTPUT_MODE)
    except FileExistsError:
        _refuse("output path already exists")
    raw = (json.dumps(document, indent=2) + "\n").encode("utf-8")
    try:
        os.fchmod(fd, _OUTPUT_MODE)
        written = 0
        while written < len(raw):
            chunk = os.write(fd, raw[written:])
            if chunk == 0:
                raise OSError("write returned 0 bytes")
            written += chunk
        os.fsync(fd)
    except Exception:
        os.close(fd)
        try:
            os.unlink(str(path))
        except OSError:
            pass
        _refuse("failed to write output")
    os.close(fd)
    return raw


def _refuse(message: str) -> "None":
    sys.stderr.write("workspace Control Room migration refused: " + message + "\n")
    sys.stderr.flush()
    sys.exit(_REFUSE_EXIT)


def _not_needed(reason: str) -> "None":
    sys.stderr.write("workspace Control Room migration not needed: " + reason + "\n")
    sys.stderr.flush()
    sys.exit(_NOT_NEEDED_EXIT)


def main(argv: list[str]) -> int:
    try:
        args = _parse_args(argv)
    except SystemExit as failure:
        sys.exit(_USAGE_EXIT if failure.code else int(failure.code))

    input_path = pathlib.Path(args.input)
    output_path = pathlib.Path(args.output)

    # Resolve first so we can compare canonical paths before any create/exists
    # check triggers an OSError on a non-existent input.
    resolved_input = input_path.resolve()
    resolved_output = output_path.resolve()
    if resolved_input == resolved_output:
        _refuse("output path resolves to the input path")
    if not input_path.exists():
        _refuse("input path does not exist")
    if output_path.exists():
        _refuse("output path already exists")
    parent = output_path.parent
    if not parent.is_dir():
        _refuse("output parent is not an existing directory")

    raw = _read_input(input_path)
    document = _parse_json(raw)
    port = _validate_legacy(document)
    control_uid = int(document["control_uid"])
    successor = _build_successor(document, port=port, control_uid=control_uid)

    # Validate the successor with the shared validator before writing.
    try:
        validate_workspace_control_room(
            successor["workspace_control_room"], control_uid=control_uid)
    except ServiceError as exc:
        _refuse("successor failed shared validator: " + str(exc))

    output_bytes = _write_output(output_path, successor)
    summary = {
        "migrated": True,
        "removed": {"port": int(port)},
        "added": successor["workspace_control_room"],
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "unchanged_keys": len([k for k in successor if k != "workspace_control_room"]),
    }
    sys.stdout.write(json.dumps(summary) + "\n")
    sys.stdout.flush()
    return 0


# These names are filled in by _import_phase1c() before main() runs.
validate_workspace_control_room = None  # type: ignore[assignment]
ServiceError: type = type("ServiceError", (Exception,), {})  # placeholder


def _import_phase1c() -> None:
    global _CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET, _WORKSPACE_CONTROL_ROOM_SOCKET_NAME
    global validate_workspace_control_room, ServiceError
    release_root = _resolve_release_root()
    sys.path.insert(0, str(release_root))
    from scripts.executive_os_phase1c import (
        _CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET as canonical_socket,
        _WORKSPACE_CONTROL_ROOM_SOCKET_NAME as socket_name,
        ServiceError as _service_error,
        validate_workspace_control_room as _validator,
    )
    _CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET = canonical_socket
    _WORKSPACE_CONTROL_ROOM_SOCKET_NAME = socket_name
    validate_workspace_control_room = _validator
    ServiceError = _service_error


if __name__ == "__main__":
    _import_phase1c()
    sys.exit(main(sys.argv))
