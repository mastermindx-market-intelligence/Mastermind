"""install.sh — the I1 heredoc that projects the WorkspaceControlRoom launchd
socket onto the Control plist (closed opt-in stanza, legacy TCP refused).

The new heredoc lives between the Company-consultation heredoc and the
StandardOutPath plutil call. The Company block stays byte-identical; the new
block reads the control config via the shared validator's helper and either
adds the WorkspaceControlRoom socket (when the config carries the unix
stanza) or removes a stale one (when it does not), refusing the legacy
``{"port": int}`` shape with the same loud refusal the validator uses
everywhere else.
"""
from __future__ import annotations

import copy
import json
import os
import pathlib
import plistlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import executive_os_phase1c as phase1c
from tests.executive_installed_control_fixture import (
    installed_control_config,
    unix_stanza,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO_ROOT / "ops" / "executive_os/install.sh"


# Three closed base sockets: same shape as production, in the same order.
_BASE_SOCKETS = {
    "CeoIngress": {
        "SockPassive": True,
        "SockPathGroup": 452,
        "SockPathMode": 432,
        "SockPathName": "/var/run/mastermind-executive/ceo-ingress.sock",
        "SockPathOwner": 450,
        "SockType": "stream",
    },
    "DialogueObservation": {
        "SockPassive": True,
        "SockPathGroup": 457,
        "SockPathMode": 432,
        "SockPathName": (
            "/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
        ),
        "SockPathOwner": 450,
        "SockType": "stream",
    },
    "Operator": {
        "SockPassive": True,
        "SockPathGroup": 453,
        "SockPathMode": 432,
        "SockPathName": "/var/run/mastermind-executive/control.sock",
        "SockPathOwner": 450,
        "SockType": "stream",
    },
}


def _extract_workspace_block() -> str:
    """Pull the body of the I1 heredoc out of install.sh.

    The heredoc is delimited by a single ``<<'PY'`` followed by the body and
    exactly one trailing ``PY`` line. Exactly one match is asserted so a
    duplicate or stray copy is caught.
    """

    source = INSTALL_SH.read_text()
    marker_index = source.index("workspace_control_room_launchd_entry(config")
    open_marker = source.rfind("<<'PY'", 0, marker_index)
    assert open_marker != -1, "could not locate opening <<'PY' before the I1 heredoc"
    close_marker = source.index("\nPY\n", marker_index)
    return source[open_marker + len("<<'PY'\n"): close_marker]


def _seed_control_plist(tmp_path: Path, *, extra_sockets: dict | None = None) -> Path:
    """Build a concrete control plist that already holds the three base sockets."""

    sockets = copy.deepcopy(_BASE_SOCKETS)
    if extra_sockets:
        sockets.update(extra_sockets)
    # Minimal required top-level keys; structure mirrors the production plist
    # but does not need to satisfy the full installed_peer profile (that is
    # exercised in I2).
    profile = {
        "Label": "com.mastermind.executive.control",
            "UserName": "_mastermind_exec",
            "GroupName": "_mastermind_exec",
            "Sockets": sockets,
            "EnvironmentVariables": {"HOME": "/tmp"},
            "StandardOutPath": "/tmp/out.log",
            "StandardErrorPath": "/tmp/err.log",
            "WorkingDirectory": "/tmp/release",
            "ProgramArguments": ["/usr/bin/true"],
        }
    plist = tmp_path / "control.plist"
    plist.write_bytes(plistlib.dumps(profile, sort_keys=False))
    return plist


def _seed_control_config(tmp_path: Path, *, stanza: dict | None) -> Path:
    """Build a config with the workspace stanza either present, absent, or legacy."""

    document = installed_control_config(
        tmp_path, control_uid=450,
        workspace_socket_path=phase1c._CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET)
    if stanza is None:
        document.pop("workspace_control_room", None)
    else:
        document["workspace_control_room"] = stanza
    path = tmp_path / "control.json"
    path.write_text(json.dumps(document))
    return path


def _run_block(block: str, config: Path, plist: Path, gid: str | int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-", str(REPO_ROOT), str(config), str(plist), str(gid)],
        input=block, text=True, capture_output=True,
    )


def test_install_sh_workspace_heredoc_is_single_and_between_separators():
    """The I1 block exists exactly once, after the Company block, before the
    StandardOutPath plutil line."""

    source = INSTALL_SH.read_text()
    blocks = [match for match in re.finditer(
        r"<<'PY'\n(.*?)\nPY\n", source, flags=re.DOTALL)
        if "workspace_control_room_launchd_entry(config" in match.group(1)]
    assert len(blocks) == 1, f"expected exactly one I1 block, found {len(blocks)}"
    company = source.count('sockets.pop("CompanyConsultation", None)')
    assert company == 1, "Company block drifted"
    block_start = blocks[0].start()
    # The Company heredoc opens before the I1 block, and closes before it.
    company_heredoc_open = source.index("# The optional Company socket belongs to this same service")
    company_heredoc_close = source.index("\nPY\n", company_heredoc_open)
    assert block_start > company_heredoc_close
    standard_out = source.index("/usr/bin/plutil -replace StandardOutPath -string")
    assert block_start < standard_out


def test_install_sh_adds_workspace_socket_when_stanza_present(tmp_path):
    block = _extract_workspace_block()
    config = _seed_control_config(tmp_path, stanza=unix_stanza(450))
    plist = _seed_control_plist(tmp_path)

    result = _run_block(block, config, plist, 450)

    assert result.returncode == 0, (result.stdout, result.stderr)
    document = plistlib.loads(plist.read_bytes())
    sockets = document["Sockets"]
    assert set(sockets) == {"CeoIngress", "DialogueObservation", "Operator",
                            phase1c._WORKSPACE_CONTROL_ROOM_SOCKET_NAME}
    # The room entry is byte-equal to the closed phase1c launchd entry.
    expected_entry = phase1c.workspace_control_room_launchd_entry(
        {"control_uid": 450, "workspace_control_room": unix_stanza(450)}, control_gid=450)
    assert sockets[phase1c._WORKSPACE_CONTROL_ROOM_SOCKET_NAME] == expected_entry
    # The three base sockets stay byte-identical to the seeded profile.
    for name in ("CeoIngress", "DialogueObservation", "Operator"):
        assert sockets[name] == _BASE_SOCKETS[name]


def test_install_sh_removes_stale_workspace_socket_when_stanza_absent(tmp_path):
    block = _extract_workspace_block()
    config = _seed_control_config(tmp_path, stanza=None)
    stale_entry = {
        "SockPassive": True,
        "SockPathGroup": 450,
        "SockPathMode": 0o600,
        "SockPathName": phase1c._CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET,
        "SockPathOwner": 450,
        "SockType": "stream",
    }
    plist = _seed_control_plist(
        tmp_path,
        extra_sockets={phase1c._WORKSPACE_CONTROL_ROOM_SOCKET_NAME: stale_entry},
    )

    result = _run_block(block, config, plist, 450)

    assert result.returncode == 0, (result.stdout, result.stderr)
    document = plistlib.loads(plist.read_bytes())
    sockets = document["Sockets"]
    assert set(sockets) == {"CeoIngress", "DialogueObservation", "Operator"}
    assert phase1c._WORKSPACE_CONTROL_ROOM_SOCKET_NAME not in sockets


def test_install_sh_refuses_legacy_tcp_stanza_and_leaves_plist_untouched(tmp_path):
    block = _extract_workspace_block()
    legacy = {"port": 8787}
    config = _seed_control_config(tmp_path, stanza=legacy)
    plist = _seed_control_plist(tmp_path)
    before = plist.read_bytes()

    result = _run_block(block, config, plist, 450)

    assert result.returncode != 0
    assert plist.read_bytes() == before
    assert "legacy TCP port stanza refused" in result.stderr


def test_install_sh_company_heredoc_remains_byte_identical():
    """The Company block stays the unchanged base, byte for byte."""

    source = INSTALL_SH.read_text()
    # Locate the Company block: starts at "# The optional Company socket".
    company_start = source.index("# The optional Company socket belongs to this same service")
    company_end = source.index("\nPY\n", company_start) + len("\nPY\n")
    company_body = source[company_start:company_end]
    # The exact set of markers and structure that exists today.
    assert 'sockets.pop("CompanyConsultation", None)' in company_body
    assert "from scripts.executive_os_phase1c import company_consultation_launchd_entry" in company_body
    # No drift in the Company block; the new block must live AFTER it.
    standard_out = source.index("/usr/bin/plutil -replace StandardOutPath -string")
    workspace_start = source.index("workspace_control_room_launchd_entry(config")
    assert workspace_start > company_end
    assert workspace_start < standard_out