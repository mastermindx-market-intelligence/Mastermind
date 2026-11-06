"""Hermetic hostile-archive and bridge-qualification tests for the fleet payload."""
from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path
import socket
import subprocess
import tarfile

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "prepare_signed_peekaboo_helper_macos.py"
spec = importlib.util.spec_from_file_location("signed_native_helper", SOURCE)
helper = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(helper)


def archive(path, *, symlink=False, extra=False):
    with tarfile.open(path, "w:gz") as bundle:
        folder = tarfile.TarInfo(helper.ROOT_NAME)
        folder.type = tarfile.DIRTYPE
        bundle.addfile(folder)
        for name in sorted(helper.MEMBER_NAMES - {helper.ROOT_NAME}):
            part = tarfile.TarInfo(name)
            if symlink and name.endswith("/peekaboo"):
                part.type = tarfile.SYMTYPE
                part.linkname = "/Applications/Peekaboo.app"
                bundle.addfile(part)
            else:
                data = b"fixture"
                part.size = len(data)
                bundle.addfile(part, BytesIO(data))
        if extra:
            part = tarfile.TarInfo(helper.ROOT_NAME + "/../outside")
            part.size = 1
            bundle.addfile(part, BytesIO(b"x"))


def test_rejects_unpinned_archive_before_extraction(tmp_path):
    path = tmp_path / "unapproved.tar.gz"
    path.write_bytes(b"not a signed release")
    with pytest.raises(helper.QualificationRefused, match="DIGEST_REFUSED"):
        helper.inspect_archive(path)


@pytest.mark.parametrize("symlink,extra", [(True, False), (False, True)])
def test_rejects_link_and_traversal_even_after_digest_gate(tmp_path, monkeypatch, symlink, extra):
    path = tmp_path / "hostile.tar.gz"
    archive(path, symlink=symlink, extra=extra)
    monkeypatch.setattr(helper, "digest_file", lambda _: helper.ARCHIVE_SHA256)
    with pytest.raises(helper.QualificationRefused, match="LAYOUT_REFUSED"):
        helper.extract_verified(path, tmp_path / "extracted")
    assert not (tmp_path / "outside").exists()


def test_signature_refuses_wrong_team_and_bundle(tmp_path, monkeypatch):
    candidate = tmp_path / "peekaboo"
    candidate.write_text("binary")
    def fake_call(argv, timeout=20):
        if "--verify" in argv:
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(argv, 0, "",
            "Identifier=other.bundle\nTeamIdentifier=ATTACKER")
    monkeypatch.setattr(helper, "command", fake_call)
    with pytest.raises(helper.QualificationRefused, match="SIGNER_MISMATCH"):
        helper.signature(candidate, expected_id=helper.CLI_ID)


def test_bridge_source_and_permission_facts_are_independent_of_worker_admission(
    tmp_path, monkeypatch
):
    endpoint = tmp_path / "owned.sock"
    sock = socket.socket(socket.AF_UNIX)
    sock.bind(str(endpoint))
    try:
        def fake_call(argv, timeout=20):
            assert argv[-2:] == ["--bridge-socket", str(endpoint)]
            return subprocess.CompletedProcess(argv, 0,
                '{"success":true,"data":{"source":"bridge","permissions":['
                '{"name":"Accessibility","isGranted":true},'
                '{"name":"Screen Recording","isGranted":true},'
                '{"name":"Event Synthesizing","isGranted":true}]}}', "")
        monkeypatch.setattr(helper, "command", fake_call)
        result = helper.verify_bridge(tmp_path / "peekaboo", endpoint)
        assert result["observation_ready"] is True
        assert result["source"] == "bridge"
        def wrong_source(argv, timeout=20):
            good = fake_call(argv, timeout)
            return subprocess.CompletedProcess(argv, 0,
                good.stdout.replace('"source":"bridge"', '"source":"local"'), "")
        monkeypatch.setattr(helper, "command", wrong_source)
        with pytest.raises(helper.QualificationRefused, match="RESULT_UNQUALIFIED"):
            helper.verify_bridge(tmp_path / "peekaboo", endpoint)
    finally:
        sock.close()
