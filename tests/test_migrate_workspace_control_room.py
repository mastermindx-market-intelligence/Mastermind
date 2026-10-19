"""I3 — the reviewed stdlib-only migration tool that turns the legacy
``workspace_control_room: {"port": int}`` stanza into the new unix stanza.

Every case runs the tool as a subprocess so the test exercises the real
stdin/stdout/stderr contract: the seat sees the exit code, the refusal
message on stderr, the summary JSON line on stdout.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane import executive_installed_peer as installed_peer
from scripts import executive_os_phase1c as phase1c
from tests.executive_installed_control_fixture import (
    installed_control_config,
    unix_stanza,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "ops/executive_os/migrate_workspace_control_room.py"


_REFUSE_PREFIX = "workspace Control Room migration refused: "
_NOT_NEEDED_PREFIX = "workspace Control Room migration not needed: "


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(TOOL), *args],
        text=True, capture_output=True,
    )


def _write_input(tmp_path: Path, document: dict, *, raw_text: bytes | None = None) -> Path:
    path = tmp_path / "control.json"
    if raw_text is not None:
        path.write_bytes(raw_text)
    else:
        path.write_text(json.dumps(document))
    return path


def _output_path(tmp_path: Path) -> Path:
    return tmp_path / "control.unix.json"


def _make_legacy_config(tmp_path: Path, *, port: int = 8787,
                        extra_overrides: dict | None = None,
                        workspace_socket_path: str | None = None) -> dict:
    document = installed_control_config(
        tmp_path, control_uid=450,
        workspace_socket_path=workspace_socket_path or phase1c._CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET)
    # Replace the closed unix stanza with a legacy tcp one so the legacy refusal
    # is exercised; the rest of the document still passes load_control_config
    # after migration.
    document.pop("workspace_control_room")
    document["workspace_control_room"] = {"port": int(port)}
    if extra_overrides:
        document.update(extra_overrides)
    return document


# -- happy path --------------------------------------------------------------

def test_happy_path_migrates_legacy_to_unix_and_shared_validator_accepts(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    input_path = _write_input(tmp_path, legacy)
    out = _output_path(tmp_path)

    # First prove the shared validator REFUSES the legacy stanza (the same
    # validator that install.sh / load_control_config consult).
    from scripts.executive_os_phase1c import ServiceError, validate_workspace_control_room
    original_input = input_path.read_text()
    with pytest.raises(ServiceError) as failure_info:
        validate_workspace_control_room(legacy["workspace_control_room"], control_uid=450)
    assert "legacy TCP port stanza refused" in str(failure_info.value)
    assert input_path.read_text() == original_input, "input file must not be touched"

    result = _run("--input", str(input_path), "--output", str(out))

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not result.stderr

    # Output mode is 0o600 (no group/other read).
    output_mode = stat_octal_mode(out)
    assert output_mode == 0o600

    # Output == input with only the stanza replaced; key order preserved.
    output_doc = json.loads(out.read_text())
    expected = json.loads(original_input)
    for key, value in expected.items():
        if key == "workspace_control_room":
            assert output_doc[key] == {
                "transport": "unix",
                "socket_path": phase1c._CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET,
                "launchd_socket_name": phase1c._WORKSPACE_CONTROL_ROOM_SOCKET_NAME,
                "allowed_peer_uids": [450],
            }
        else:
            assert output_doc[key] == value

    # Every non-stanza key preserves its position.
    output_keys = list(output_doc)
    input_keys = list(expected)
    assert output_keys == input_keys
    assert output_keys.index("workspace_control_room") == input_keys.index("workspace_control_room")

    # Input bytes unchanged.
    assert input_path.read_text() == original_input

    # Summary JSON fields exact.
    summary = json.loads(result.stdout)
    assert summary == {
        "migrated": True,
        "removed": {"port": 8787},
        "added": output_doc["workspace_control_room"],
        "input_sha256": hashlib.sha256(original_input.encode()).hexdigest(),
        "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "unchanged_keys": len([k for k in output_doc if k != "workspace_control_room"]),
    }

    # The shared validator ACCEPTS the migrated stanza.
    validate_workspace_control_room(output_doc["workspace_control_room"], control_uid=450)

    # The installed launchd entry matches the installed_peer 4-socket template.
    entry = phase1c.workspace_control_room_launchd_entry(
        {"control_uid": 450, "workspace_control_room": output_doc["workspace_control_room"]},
        control_gid=450)
    assert entry == installed_peer._WORKSPACE_CONTROL_ROOM_SOCKET


def stat_octal_mode(path: Path) -> int:
    """Return the permission mode (low 12 bits) as an octal int."""

    return stat.S_IMODE(os.stat(str(path)).st_mode)


# Replace the helper at module scope so the test can use it.
import stat  # noqa: E402  (placed here to keep the test file linear)


# -- refusals (rc 2) --------------------------------------------------------

def _assert_refused(tmp_path: Path, document: dict, *, raw_text: bytes | None = None,
                     expected_message: str, mutate_output_before_run=None) -> None:
    input_path = _write_input(tmp_path, document, raw_text=raw_text)
    out = _output_path(tmp_path)
    if mutate_output_before_run is not None:
        mutate_output_before_run(out)
    result = _run("--input", str(input_path), "--output", str(out))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stdout == ""
    assert result.stderr.startswith(_REFUSE_PREFIX), result.stderr
    assert expected_message in result.stderr, result.stderr
    assert not out.exists(), "refusal must not create the output"


def test_refuses_when_workspace_acquisition_absent(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    legacy.pop("workspace_acquisition")
    _assert_refused(tmp_path, legacy, expected_message="workspace_acquisition key absent")


def test_refuses_when_control_uid_missing(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    legacy.pop("control_uid")
    _assert_refused(tmp_path, legacy, expected_message="control_uid key absent")


def test_refuses_when_control_uid_is_bool(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    legacy["control_uid"] = True
    _assert_refused(tmp_path, legacy, expected_message="control_uid must be a positive integer")


def test_refuses_when_control_uid_is_zero(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    legacy["control_uid"] = 0
    _assert_refused(tmp_path, legacy, expected_message="control_uid must be a positive integer")


def test_refuses_stanza_with_extra_host_key(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    legacy["workspace_control_room"] = {"port": 8787, "host": "127.0.0.1"}
    _assert_refused(tmp_path, legacy,
                    expected_message='workspace_control_room must be exactly {"port": int}')


def test_refuses_port_true(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    legacy["workspace_control_room"] = {"port": True}
    _assert_refused(tmp_path, legacy,
                    expected_message="workspace_control_room.port must be an integer")


def test_refuses_port_string(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    legacy["workspace_control_room"] = {"port": "8787"}
    _assert_refused(tmp_path, legacy,
                    expected_message="workspace_control_room.port must be an integer")


def test_refuses_port_zero(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    legacy["workspace_control_room"] = {"port": 0}
    _assert_refused(tmp_path, legacy,
                    expected_message="workspace_control_room.port out of range")


def test_refuses_port_over_max(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    legacy["workspace_control_room"] = {"port": 65536}
    _assert_refused(tmp_path, legacy,
                    expected_message="workspace_control_room.port out of range")


def test_refuses_stanza_as_list(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    legacy["workspace_control_room"] = []
    _assert_refused(tmp_path, legacy,
                    expected_message='workspace_control_room must be exactly {"port": int}')


def test_refuses_duplicate_top_level_key(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    raw_text = json.dumps(legacy)
    # Inject a duplicate "control_uid" key at the end.
    raw_text = raw_text[:-1] + ',"control_uid":450}'
    input_path = tmp_path / "control.json"
    input_path.write_bytes(raw_text.encode())
    out = _output_path(tmp_path)
    result = _run("--input", str(input_path), "--output", str(out))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr.startswith(_REFUSE_PREFIX), result.stderr
    assert "duplicate top-level key in input" in result.stderr
    assert not out.exists()


def test_refuses_top_level_array(tmp_path):
    raw = b"[1, 2, 3]"
    input_path = tmp_path / "control.json"
    input_path.write_bytes(raw)
    out = _output_path(tmp_path)
    result = _run("--input", str(input_path), "--output", str(out))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr.startswith(_REFUSE_PREFIX), result.stderr
    assert "top-level JSON value must be an object" in result.stderr
    assert not out.exists()


def test_refuses_input_that_is_a_symlink(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    real_path = _write_input(tmp_path, legacy)
    link_path = tmp_path / "control.symlink.json"
    os.symlink(str(real_path), str(link_path))
    out = _output_path(tmp_path)
    result = _run("--input", str(link_path), "--output", str(out))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr.startswith(_REFUSE_PREFIX), result.stderr
    assert "input is not a regular file" in result.stderr
    assert not out.exists()


def test_refuses_when_output_already_exists(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    input_path = _write_input(tmp_path, legacy)
    out = _output_path(tmp_path)
    out.write_text("placeholder")
    out_bytes_before = out.read_bytes()
    result = _run("--input", str(input_path), "--output", str(out))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr.startswith(_REFUSE_PREFIX), result.stderr
    assert "output path already exists" in result.stderr
    assert out.read_bytes() == out_bytes_before, "refusal must not touch the existing output"


def test_refuses_when_output_equals_input(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    input_path = _write_input(tmp_path, legacy)
    result = _run("--input", str(input_path), "--output", str(input_path))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr.startswith(_REFUSE_PREFIX), result.stderr
    assert "resolves to the input path" in result.stderr


def test_relative_input_path_returns_usage_exit(tmp_path):
    legacy = _make_legacy_config(tmp_path)
    _write_input(tmp_path, legacy)
    out = _output_path(tmp_path)
    result = _run("--input", "relative/path", "--output", str(out))
    assert result.returncode == 64, (result.stdout, result.stderr)
    assert not out.exists()


# -- not needed (rc 3) -------------------------------------------------------

def test_not_needed_when_stanza_absent(tmp_path):
    document = _make_legacy_config(tmp_path)
    document.pop("workspace_control_room")
    input_path = _write_input(tmp_path, document)
    out = _output_path(tmp_path)
    result = _run("--input", str(input_path), "--output", str(out))
    assert result.returncode == 3, (result.stdout, result.stderr)
    assert result.stdout == ""
    assert result.stderr.startswith(_NOT_NEEDED_PREFIX)
    assert "workspace_control_room key absent" in result.stderr
    assert not out.exists()


def test_not_needed_when_stanza_already_unix(tmp_path):
    document = _make_legacy_config(tmp_path)
    document.pop("workspace_control_room")
    document["workspace_control_room"] = unix_stanza(450)
    input_path = _write_input(tmp_path, document)
    out = _output_path(tmp_path)
    result = _run("--input", str(input_path), "--output", str(out))
    assert result.returncode == 3, (result.stdout, result.stderr)
    assert result.stdout == ""
    assert result.stderr.startswith(_NOT_NEEDED_PREFIX)
    assert "already in unix/launchd shape" in result.stderr
    assert not out.exists()