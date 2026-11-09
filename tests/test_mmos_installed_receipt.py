"""Tests for scripts/mmos_installed_receipt.py (installed-bundle receipts).

Hermetic: every test runs against fake .app bundles under pytest tmp paths.
The two "real-blob regression" cases encode the exact embedded-string layout
observed in the two real installed builds on 2026-11-09 so the calibrated
heuristic cannot silently drift.
"""
from __future__ import annotations

import json
import subprocess as _sp
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import mmos_installed_receipt as mr  # noqa: E402
from tests.mmos_fake_bundle import fake_executable_bytes, make_fake_app  # noqa: E402

REV_A = "3652d8907df1738de551dd3032b42aa2a2acb482"
IDENT_A = "mmos-persistent-login-20261109-3652d89"
REV_BAK = "06ef56a39c085af72bcbf0866db8e43f99cd6034"
IDENT_BAK = "mmos-office-connection-06ef56a3-20261109-01a1a4bf"


# ---------------------------------------------------------------------------
# embedded extraction
# ---------------------------------------------------------------------------

def test_marker_beats_heuristic_blob(tmp_path):
    bundle = make_fake_app(
        tmp_path, revision=REV_A, identity=IDENT_A, marker=True,
    )
    receipt = mr.observe_bundle(bundle, observed_at="2026-11-09T00:00:00Z", host="t")
    assert receipt["source_revision"] == {"value": REV_A, "provenance": "embedded_marker"}
    assert receipt["build_identity"]["value"] == IDENT_A
    assert receipt["build_identity"]["provenance"] == "embedded_marker"


def test_heuristic_scan_matches_real_current_build_blob(tmp_path):
    # marker=False reproduces the CURRENT real installed build's rodata layout.
    bundle = make_fake_app(tmp_path, revision=REV_A, identity=IDENT_A, marker=False)
    receipt = mr.observe_bundle(bundle, observed_at="2026-11-09T00:00:00Z", host="t")
    assert receipt["source_revision"] == {"value": REV_A, "provenance": "heuristic_scan"}
    assert receipt["build_identity"]["value"] == IDENT_A  # 'native' seam trimmed
    assert receipt["build_identity"]["provenance"] == "heuristic_scan"
    assert "native" in receipt["build_identity"].get("detail", "")


def test_heuristic_scan_matches_real_backup_build_blob(tmp_path):
    bundle = make_fake_app(tmp_path, revision=REV_BAK, identity=IDENT_BAK, marker=False)
    receipt = mr.observe_bundle(bundle, observed_at="2026-11-09T00:00:00Z", host="t")
    assert receipt["source_revision"] == {"value": REV_BAK, "provenance": "heuristic_scan"}
    assert receipt["build_identity"]["value"] == IDENT_BAK
    assert receipt["build_identity"]["provenance"] == "heuristic_scan"


def test_unknown_when_no_revision_present(tmp_path):
    bundle = make_fake_app(
        tmp_path, executable_bytes=b"\xcf\xfa\xed\xfe" + b"no receipts here\x00" * 8
    )
    receipt = mr.observe_bundle(bundle)
    assert receipt["source_revision"] == {"value": None, "provenance": "unknown"}
    assert receipt["build_identity"] == {"value": None, "provenance": "unknown"}


def test_unknown_on_ambiguous_version_anchored_pairs(tmp_path):
    blob = fake_executable_bytes(revision=REV_A, identity=IDENT_A, marker=False, decoys=False)
    blob += fake_executable_bytes(
        revision=REV_BAK, identity=IDENT_BAK, marker=False, decoys=False
    )
    bundle = make_fake_app(tmp_path, executable_bytes=blob)
    receipt = mr.observe_bundle(bundle)
    assert receipt["source_revision"]["provenance"] == "unknown"
    assert receipt["source_revision"]["value"] is None
    assert receipt["build_identity"]["value"] is None


def test_bare_decoy_hex40_is_never_selected(tmp_path):
    # decoys=True plants three real-world decoys; none is version-anchored.
    bundle = make_fake_app(tmp_path, revision=REV_A, identity=IDENT_A, marker=False)
    receipt = mr.observe_bundle(bundle)
    assert receipt["source_revision"]["value"] == REV_A
    for decoy in ("b940084d", "2bd378ed", "000011112222"):
        assert not (receipt["source_revision"]["value"] or "").startswith(decoy)


def test_revision_known_identity_unknown_when_run_empty(tmp_path):
    blob = fake_executable_bytes(revision=REV_A, identity=IDENT_A, marker=False, decoys=False)
    blob = blob.replace(IDENT_A.encode() + b"native", b"")  # nothing after the rev
    bundle = make_fake_app(tmp_path, executable_bytes=blob)
    receipt = mr.observe_bundle(bundle)
    assert receipt["source_revision"] == {"value": REV_A, "provenance": "heuristic_scan"}
    assert receipt["build_identity"] == {"value": None, "provenance": "unknown"}


# ---------------------------------------------------------------------------
# receipt shape / determinism
# ---------------------------------------------------------------------------

def test_receipt_has_required_fields(tmp_path):
    bundle = make_fake_app(tmp_path, revision=REV_A, identity=IDENT_A)
    receipt = mr.observe_bundle(bundle)
    assert receipt["schema"] == mr.SCHEMA
    assert receipt["bundle_exists"] is True
    assert receipt["info_plist"] == {
        "CFBundleIdentifier": "com.mastermind.os",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "CFBundleExecutable": "mastermind-os",
    }
    exe = receipt["executable"]
    assert exe["path"].endswith("Contents/MacOS/mastermind-os")
    assert isinstance(exe["sha256"], str) and len(exe["sha256"]) == 64
    assert isinstance(exe["size_bytes"], int) and exe["size_bytes"] > 0
    assert isinstance(exe["mtime"], str)
    assert receipt["codesign"]["status"] in {"signed", "unsigned", "unknown"}
    assert set(receipt["running_app"]) >= {"from_this_bundle", "pids", "detail"}
    assert receipt["receipt_digest"].startswith("sha256:")
    assert len(receipt["receipt_digest"]) == len("sha256:") + 64


def test_digest_is_deterministic_across_observers(tmp_path):
    bundle = make_fake_app(tmp_path, revision=REV_A, identity=IDENT_A)
    first = mr.observe_bundle(bundle, observed_at="2026-11-09T01:00:00Z", host="host-a")
    second = mr.observe_bundle(bundle, observed_at="2026-11-10T23:00:00Z", host="host-b")
    assert first["receipt_digest"] == second["receipt_digest"]
    assert first["observed_at"] != second["observed_at"]


def test_plist_encoding_does_not_change_digest(tmp_path):
    xml = make_fake_app(tmp_path / "xml", revision=REV_A, identity=IDENT_A, binary_plist=False)
    binp = make_fake_app(tmp_path / "bin", revision=REV_A, identity=IDENT_A, binary_plist=True)
    assert mr.observe_bundle(xml)["receipt_digest"] == mr.observe_bundle(binp)["receipt_digest"]


def test_missing_bundle_is_honest_unknown_exit_zero(tmp_path, capsys):
    rc = mr.main(["--bundle", str(tmp_path / "Not Installed.app")])
    assert rc == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["bundle_exists"] is False
    assert receipt["info_plist"] is None
    assert receipt["executable"]["sha256"] is None
    assert receipt["source_revision"] == {"value": None, "provenance": "unknown"}
    assert receipt["running_app"]["from_this_bundle"] is None


def test_malformed_args_exit_2(tmp_path, capsys):
    assert mr.main(["--bundle", "   "]) == 2
    with pytest.raises(SystemExit) as exc:
        mr.build_parser().parse_args(["--totally-unknown-flag"])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# codesign / running-app observation seams
# ---------------------------------------------------------------------------

def _fake_codesign(returncode=0, stderr=""):
    def run(cmd, **kwargs):
        return _sp.CompletedProcess(cmd, returncode, stdout="", stderr=stderr)
    return run


def test_codesign_parse_signed(tmp_path, monkeypatch):
    monkeypatch.setattr(mr.subprocess, "run", _fake_codesign(
        stderr="Identifier=com.mastermind.os\nTeamIdentifier=not set\nSignature=adhoc\n"
    ))
    status = mr.codesign_display(tmp_path / "x.app")
    assert status["status"] == "signed"
    assert status["identifier"] == "com.mastermind.os"
    assert status["team_identifier"] is None
    assert status["signature"] == "adhoc"


def test_codesign_unsigned_and_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(mr.subprocess, "run", _fake_codesign(
        returncode=1, stderr="x.app: code object is not signed at all\n"
    ))
    assert mr.codesign_display(tmp_path / "x.app")["status"] == "unsigned"

    def boom(cmd, **kwargs):
        raise FileNotFoundError("codesign")

    monkeypatch.setattr(mr.subprocess, "run", boom)
    assert mr.codesign_display(tmp_path / "x.app")["status"] == "unknown"


def test_running_app_exact_ambiguous_none(tmp_path, monkeypatch):
    bundle = make_fake_app(tmp_path, revision=REV_A, identity=IDENT_A)
    exe = bundle / "Contents" / "MacOS" / "mastermind-os"

    monkeypatch.setattr(mr, "ps_snapshot", lambda: [(73195, str(exe))])
    running = mr.running_app(exe)
    assert running["from_this_bundle"] is True and running["pids"] == [73195]

    monkeypatch.setattr(mr, "ps_snapshot", lambda: [(1, "/elsewhere/mastermind-os")])
    assert mr.running_app(exe)["from_this_bundle"] is None

    monkeypatch.setattr(mr, "ps_snapshot", lambda: [])
    assert mr.running_app(exe)["from_this_bundle"] is False

    monkeypatch.setattr(mr, "ps_snapshot", lambda: None)
    assert mr.running_app(exe)["from_this_bundle"] is None
