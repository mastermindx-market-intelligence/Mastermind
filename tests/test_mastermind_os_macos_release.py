"""Release qualification refuses unsigned, mismatched, or changing Mac bundles."""
import importlib.util
import json
import plistlib
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def release(monkeypatch):
    path = Path(__file__).parents[1] / "app/mastermind_os/tools/qualify_macos_release.py"
    spec = importlib.util.spec_from_file_location("os_mac_release", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.sys, "platform", "darwin")
    return module


@pytest.fixture
def candidate(tmp_path):
    app = tmp_path / "Mastermind OS.app"
    executable = app / "Contents/MacOS/mastermind-os"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"qualified native executable")
    executable.chmod(0o755)
    info = {
        "CFBundleIdentifier": "com.mastermind.os",
        "CFBundleShortVersionString": "0.2.0",
        "CFBundleExecutable": "mastermind-os",
        "MMSourceRevision": "a" * 40,
        "MMBuildIdentity": "mastermind-os-beta-001",
    }
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
    return app


@pytest.fixture
def expected():
    return dict(source_revision="a" * 40, build_identity="mastermind-os-beta-001",
                version="0.2.0", team_id="ABCDE12345")


@pytest.fixture
def apple(monkeypatch, release):
    calls = []
    evidence = {
        "display": "Identifier=com.mastermind.os\nAuthority=Developer ID Application: Example (ABCDE12345)\n"
                   "TeamIdentifier=ABCDE12345\nCodeDirectory v=20500 flags=0x10000(runtime) hashes=1\n",
        "assessment": "accepted\nsource=Notarized Developer ID\n",
        "fail": None,
        "mutate": None,
    }

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs["timeout"] == 30
        assert kwargs.get("shell", False) is False
        assert args[0] in {"/usr/bin/codesign", "/usr/bin/xcrun", "/usr/sbin/spctl"}
        kind = "display" if "--display" in args else (
            "assessment" if "--assess" in args else "staple" if "stapler" in args else "signature")
        if kind == "assessment" and evidence["mutate"]:
            evidence["mutate"]()
        return subprocess.CompletedProcess(args, 1 if evidence["fail"] == kind else 0,
                                           stdout="", stderr=evidence.get(kind, ""))

    monkeypatch.setattr(release.subprocess, "run", run)
    return evidence, calls


def test_qualified_bundle_has_scoped_receipt(release, candidate, expected, apple):
    receipt = release.qualify(candidate, **expected)
    assert receipt["schema"] == "mastermind.os_macos_release_qualification.v1"
    assert receipt["qualification"] == "SIGNED_NOTARIZED_APP_VERIFIED"
    assert receipt["source_revision"] == expected["source_revision"]
    assert len(receipt["bundle_sha256"]) == 64
    assert receipt["release_authorized"] is False
    assert receipt["updater_qualified"] is False
    assert len(apple[1]) == 4
    assert all("submit" not in c and "staple" not in c for c in apple[1])


@pytest.mark.parametrize("failure", ["signature", "display", "staple", "assessment"])
def test_each_apple_failure_refuses(release, candidate, expected, apple, failure):
    apple[0]["fail"] = failure
    with pytest.raises(release.QualificationError):
        release.qualify(candidate, **expected)


@pytest.mark.parametrize("old,new", [
    ("Authority=Developer ID Application: Example (ABCDE12345)", "Signature=adhoc"),
    ("TeamIdentifier=ABCDE12345", "TeamIdentifier=OTHER12345"),
    ("Identifier=com.mastermind.os", "Identifier=com.another.app"),
    ("flags=0x10000(runtime)", "flags=0x0(none)"),
])
def test_signature_identity_and_hardened_runtime(release, candidate, expected, apple, old, new):
    apple[0]["display"] = apple[0]["display"].replace(old, new)
    with pytest.raises(release.QualificationError):
        release.qualify(candidate, **expected)


def test_gatekeeper_success_without_notarized_source_refuses(release, candidate, expected, apple):
    apple[0]["assessment"] = "accepted\nsource=Developer ID\n"
    with pytest.raises(release.QualificationError):
        release.qualify(candidate, **expected)


@pytest.mark.parametrize("key,value", [
    ("MMSourceRevision", "b" * 40), ("MMBuildIdentity", "another-build"),
    ("CFBundleIdentifier", "com.another.app"), ("CFBundleShortVersionString", "9.0.0"),
    ("CFBundleExecutable", "../../outside"),
])
def test_signed_metadata_must_match_expected_release(release, candidate, expected, apple, key, value):
    path = candidate / "Contents/Info.plist"
    info = plistlib.loads(path.read_bytes())
    info[key] = value
    path.write_bytes(plistlib.dumps(info))
    with pytest.raises(release.QualificationError):
        release.qualify(candidate, **expected)


def test_bundle_change_during_checks_refuses(release, candidate, expected, apple):
    apple[0]["mutate"] = lambda: (candidate / "Contents/MacOS/mastermind-os").write_bytes(b"changed")
    with pytest.raises(release.QualificationError, match="BUNDLE_CHANGED"):
        release.qualify(candidate, **expected)


def test_external_symlink_refused_before_apple_commands(release, candidate, expected, apple, tmp_path):
    (candidate / "Contents/external").symlink_to(tmp_path)
    with pytest.raises(release.QualificationError, match="SYMLINK"):
        release.qualify(candidate, **expected)
    assert apple[1] == []


def test_command_timeout_is_refusal_without_raw_output(release, candidate, expected, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 30, output="private diagnostic")
    monkeypatch.setattr(release.subprocess, "run", timeout)
    with pytest.raises(release.QualificationError) as err:
        release.qualify(candidate, **expected)
    assert "private diagnostic" not in str(err.value)


def test_receipt_file_is_exclusive(release, candidate, expected, apple, tmp_path):
    out = tmp_path / "receipt.json"
    args = ["--app", str(candidate), "--source-revision", expected["source_revision"],
            "--build-identity", expected["build_identity"], "--version", expected["version"],
            "--team-id", expected["team_id"], "--out", str(out)]
    assert release.main(args) == 0
    saved = out.read_bytes()
    assert json.loads(saved)["release_authorized"] is False
    assert release.main(args) == 1
    assert out.read_bytes() == saved


def test_receipt_cannot_mutate_qualified_bundle(release, candidate, expected, apple):
    args = ["--app", str(candidate), "--source-revision", expected["source_revision"],
            "--build-identity", expected["build_identity"], "--version", expected["version"],
            "--team-id", expected["team_id"], "--out", str(candidate / "receipt.json")]
    assert release.main(args) == 1
    assert not (candidate / "receipt.json").exists()
    assert apple[1] == []


def test_non_macos_cannot_emit_verified_receipt(release, candidate, expected, apple, monkeypatch):
    monkeypatch.setattr(release.sys, "platform", "linux")
    with pytest.raises(release.QualificationError, match="MACOS_REQUIRED"):
        release.qualify(candidate, **expected)
    assert apple[1] == []


@pytest.mark.parametrize("field,value", [
    ("source_revision", "main"), ("team_id", "guessed"),
    ("build_identity", "contains whitespace"), ("version", "latest"),
])
def test_invalid_expectation_refuses_before_commands(release, candidate, expected, apple, field, value):
    expected[field] = value
    with pytest.raises(release.QualificationError):
        release.qualify(candidate, **expected)
    assert apple[1] == []


def test_malformed_info_refuses(release, candidate, expected, apple):
    (candidate / "Contents/Info.plist").write_text("not a plist")
    with pytest.raises(release.QualificationError, match="INVALID_INFO_PLIST"):
        release.qualify(candidate, **expected)
    assert apple[1] == []


def test_duplicate_signature_field_refuses(release, candidate, expected, apple):
    apple[0]["display"] += "TeamIdentifier=ABCDE12345\n"
    with pytest.raises(release.QualificationError, match="SIGNATURE_METADATA_INVALID"):
        release.qualify(candidate, **expected)


def test_refusal_does_not_write_receipt(release, candidate, expected, apple, tmp_path):
    apple[0]["fail"] = "assessment"
    out = tmp_path / "refused.json"
    assert release.main(["--app", str(candidate), "--source-revision", expected["source_revision"],
                         "--build-identity", expected["build_identity"], "--version", expected["version"],
                         "--team-id", expected["team_id"], "--out", str(out)]) == 1
    assert not out.exists()
