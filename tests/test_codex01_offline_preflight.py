"""Offline-only CODEX-01 sandbox tests; never runs a Codex CLI or provider."""
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

from ops.executive_os import codex01_offline_preflight as subject


def test_policy_keeps_deny_default_and_no_network_or_ambient_home():
    text = subject.policy(Path("/private/tmp/mmx_codex01_offline_unittest"))
    assert text.startswith("(version 1)\n(deny default)\n")
    assert "(allow process-exec)" in text
    assert "(deny network*)" in text
    assert "(allow network" not in text
    assert "(allow mach-lookup" not in text
    for root in subject.DENIED_READ_ROOTS:
        assert f'(deny file-read* (subpath "{root}"))' in text
    assert '(allow file-write* (subpath "/private/tmp/mmx_codex01_offline_unittest"))' in text
    assert "(allow file-write*)" not in text
    assert "(allow file-read*)" in text  # Sandbox runtime baseline, explicit protected denies


@pytest.mark.parametrize("bad", [
    Path("/"), Path("relative"), Path("/private/tmp/unowned-workspace"),
    Path("/Users/chriswong/mmx_codex01_offline_fake"),
])
def test_invalid_scratch_refused(bad):
    with pytest.raises(ValueError):
        subject.policy(bad)


def test_fixture_allow_must_be_exact_child_of_explicit_denied_test_directory():
    scratch = Path("/private/tmp/mmx_codex01_offline_unittest")
    with pytest.raises(ValueError):
        subject.policy(scratch, allow_fixture=Path("/etc/passwd"))
    with pytest.raises(ValueError):
        subject.policy(scratch, deny_fixture=Path("/Volumes"))
    with pytest.raises(ValueError):
        subject.policy(scratch, deny_fixture=scratch / "secret",
                       allow_fixture=scratch / "outside")
    text = subject.policy(scratch, deny_fixture=scratch / "secret",
                          allow_fixture=scratch / "secret" / "file")
    assert '(deny file-read* (subpath "/private/tmp/mmx_codex01_offline_unittest/secret"))' in text
    assert '(allow file-read* (literal "/private/tmp/mmx_codex01_offline_unittest/secret/file"))' in text


def test_nonexistent_lexical_traversal_is_not_an_eligible_fixture():
    scratch = Path("/private/tmp/mmx_codex01_offline_unittest")
    denied = scratch / "blocked"
    # pathlib.is_relative_to is lexical, not a traversal/alias guard.
    with pytest.raises(ValueError):
        subject.policy(scratch, deny_fixture=scratch / ".." / "outside-uncreated")
    with pytest.raises(ValueError):
        subject.policy(scratch, deny_fixture=denied,
                       allow_fixture=denied / ".." / ".." / "outside-uncreated")


def test_nonexistent_child_under_existing_symlink_parent_cannot_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(subject, "SCRATCH_PARENT", tmp_path)
    scratch = tmp_path / "mmx_codex01_offline_fixture"
    scratch.mkdir(mode=0o700)
    outside = tmp_path / "outside-test-only"
    outside.mkdir()
    (scratch / "alias").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        subject.policy(scratch, deny_fixture=scratch / "alias" / "uncreated")
    blocked = scratch / "blocked"
    blocked.mkdir()
    (blocked / "alias").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        subject.policy(scratch, deny_fixture=blocked,
                       allow_fixture=blocked / "alias" / "uncreated")


def test_existing_internal_symlink_ancestor_is_not_an_eligible_fixture(tmp_path, monkeypatch):
    # Even when the alias currently targets scratch, retargeting after
    # qualification could change the exception's effective filesystem scope.
    monkeypatch.setattr(subject, "SCRATCH_PARENT", tmp_path)
    scratch = tmp_path / "mmx_codex01_offline_alias"
    scratch.mkdir(mode=0o700)
    inside = scratch / "real"
    inside.mkdir()
    (scratch / "alias").symlink_to(inside, target_is_directory=True)
    with pytest.raises(ValueError):
        subject.policy(scratch, deny_fixture=scratch / "alias" / "missing")


def test_literal_disallows_ambiguous_profile_text():
    for value in ["not/absolute", "/tmp/new\n(allow network*)", "/tmp/\x00hidden"]:
        with pytest.raises(ValueError):
            subject._literal(value)


def test_credential_free_child_environment_has_no_ambient_authority(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "a-private-value-never-used")
    monkeypatch.setenv("HOME", "/Users/someone")
    monkeypatch.setenv("GITHUB_TOKEN", "a-private-value-never-used")
    env = subject._env(Path("/private/tmp/test-isolation"))
    assert "OPENAI_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert env["HOME"] == "/private/tmp/test-isolation/home"
    assert env["CODEX_HOME"] == "/private/tmp/test-isolation/codex-home"
    assert env["PYTHONNOUSERSITE"] == "1"


def test_sensitive_path_probe_cannot_enumerate_names_when_sandbox_fails_open():
    source = Path(subject.__file__).read_text(encoding="utf-8")
    section = source.split("for key, root in (", 1)[1].split(
        'checks["outside_write_denied"]', 1
    )[0]
    assert "os.listdir(" not in section
    assert "os.scandir(" not in section
    assert "os.O_DIRECTORY" in section
    assert "os.close(fd)" in section


def test_negative_write_probe_cannot_create_a_host_file_even_if_denial_fails():
    source = Path(subject.__file__).read_text(encoding="utf-8")
    probe = source.split('checks["outside_write_denied"] = _probe(', 1)[1].split(
        'checks["loopback_network_denied"]', 1
    )[0]
    assert "/dev/null" in probe and "os.O_WRONLY" in probe
    assert all(word not in probe for word in (
        "os.O_CREAT", "os.O_TRUNC", "os.write", ".write_text(", "os.remove("
    ))


def test_unix_ipc_probe_uses_only_private_dummy_socket():
    source = Path(subject.__file__).read_text(encoding="utf-8")
    assert 'socket_path = scratch / "local-socket-only.sock"' in source
    assert "listener.bind(str(socket_path))" in source
    assert 'checks["unix_socket_denied"]' in source
    # No production/private service socket is touched by the preflight.
    assert "com.mastermind.executive." not in source


def test_no_generic_command_or_candidate_invocation_interface():
    module = Path(subject.__file__)
    p = subprocess.run(
        [sys.executable, str(module), "--run", "codex"],
        capture_output=True, text=True, timeout=8, check=False
    )
    assert p.returncode == 2
    assert "offline benign preflight only" in p.stderr
    assert p.stdout == ""


def test_nonmac_host_reports_unavailable(monkeypatch):
    monkeypatch.setattr(subject.platform, "system", lambda: "Linux")
    result = subject.preflight()
    assert result == {
        "schema": subject.SCHEMA, "state": "UNAVAILABLE",
        "checks": {}, "candidate_invoked": False,
        "provider_invoked": False, "installation_changed": False,
    }


@pytest.mark.skipif(platform.system() != "Darwin", reason="requires actual macOS Sandbox")
def test_real_darwin_sandbox_isolation_no_codex_or_network():
    receipt = subject.preflight()
    assert receipt["schema"] == subject.SCHEMA
    assert receipt["state"] == "PASS", receipt["checks"]
    assert all(receipt["checks"].values())
    assert len(receipt["checks"]) == 16
    assert receipt["candidate_invoked"] is False
    assert receipt["provider_invoked"] is False
    assert receipt["installation_changed"] is False
