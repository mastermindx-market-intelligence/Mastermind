"""Offline refusal diagnostics must never disclose input or authorize a probe."""
from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from ops.executive_os import provider_identity_probe as probe


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/executive_os/provider_identity_probe.py"
SECRET = "sk-never-output-person@example.invalid"
LIVE_ARGS = ["--expected-kind", "device-auth", "--workspace-binding-class",
             "company-workspace-admin-attested"]


def document(code="company_plan_required", **extra):
    return {"schema_version": probe.SCHEMA_VERSION, "passed": False,
            "refusal": code, **extra}


@pytest.mark.parametrize("code", [
    "credential_identity_changed_during_probe", "login_status_unreviewed",
    "forced_auth_configuration_present", "app_server_timeout",
])
def test_live_main_retains_only_closed_exception_codes(monkeypatch, capsys, code):
    monkeypatch.setattr(probe.sys, "platform", "darwin")
    monkeypatch.setattr(probe.os, "geteuid", lambda: 0)

    def fail(**kwargs):
        raise probe.IdentityProbeError(code)

    monkeypatch.setattr(probe, "live_probe", fail)
    assert probe.main(LIVE_ARGS) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["refusal"] == code
    assert output["passed"] is False


@pytest.mark.parametrize("error", [
    probe.IdentityProbeError(SECRET), probe.IdentityProbeError("future_code"),
    probe.IdentityProbeError("app_server_timeout", SECRET),
    OSError(SECRET), subprocess.SubprocessError(SECRET),
])
def test_live_main_never_echoes_unknown_exception(monkeypatch, capsys, error):
    monkeypatch.setattr(probe.sys, "platform", "darwin")
    monkeypatch.setattr(probe.os, "geteuid", lambda: 0)

    def fail(**kwargs):
        raise error

    monkeypatch.setattr(probe, "live_probe", fail)
    assert probe.main(LIVE_ARGS) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["refusal"] == "identity_probe_failed"
    assert SECRET not in captured.out + captured.err


def test_policy_failure_with_injected_identifiers_emits_only_code():
    doc = document(email=SECRET, accountId=SECRET, stderr=SECRET,
                   config_path=SECRET, traceback=SECRET)
    assert probe.bounded_refusal_from_document(doc) == "company_plan_required"


@pytest.mark.parametrize("doc", [
    None, [], {}, document(schema_version="wrong"), document(passed=True),
    document(passed=0), document("future_code"), document(SECRET),
    document("company_plan_required\n" + SECRET), document([SECRET]),
    document({"refusal": SECRET}), document(None),
])
def test_malformed_or_unknown_documents_emit_generic_code(doc):
    assert probe.bounded_refusal_from_document(doc) == "identity_probe_failed"


@pytest.mark.parametrize("payload,expected", [
    (json.dumps(document()).encode(), "company_plan_required"),
    (b"", "identity_probe_failed"),
    (b"{", "identity_probe_failed"),
    (b"\xff", "identity_probe_failed"),
    (b"[" * 1500, "identity_probe_failed"),
    (json.dumps(document(email=SECRET * 2000)).encode(), "identity_probe_failed"),
    (b'{"schema_version":"mastermind.executive_provider_identity/v1",'
     b'"passed":false,"refusal":"app_server_timeout",'
     b'"refusal":"company_plan_required"}', "identity_probe_failed"),
], ids=["policy", "empty", "malformed", "encoding", "depth", "oversized", "duplicate"])
def test_offline_cli_handles_untrusted_input_without_live_probe(payload, expected):
    result = subprocess.run([sys.executable, "-I", "-S", "-B", str(SCRIPT),
                             "--refusal-code-stdin"], input=payload,
                            capture_output=True, timeout=5)
    assert result.returncode == 0
    assert result.stdout == (expected + "\n").encode()
    assert result.stderr == b""


def test_offline_mode_never_enters_live_or_seat_probe(monkeypatch, capsys):
    monkeypatch.setattr(probe.sys, "stdin", io.TextIOWrapper(io.BytesIO(
        json.dumps(document()).encode())))

    def forbidden(*args, **kwargs):
        pytest.fail("diagnostic input must never initiate identity/provider work")

    monkeypatch.setattr(probe, "live_probe", forbidden)
    monkeypatch.setattr(probe, "_seat_compare_main", forbidden)
    assert probe.main(["--refusal-code-stdin"]) == 0
    assert capsys.readouterr().out == "company_plan_required\n"


@pytest.mark.parametrize("extra,expected,status", [
    ("--unexpected", "identity_probe_failed", 0),
    ("--compare-seat-stdin", "UNKNOWN", 2),
])
def test_offline_mode_rejects_mixed_arguments_without_consuming_input(
    monkeypatch, capsys, extra, expected, status
):
    class Unreadable:
        @property
        def buffer(self):
            pytest.fail("mixed mode must not read a seat identity")

    monkeypatch.setattr(probe.sys, "stdin", Unreadable())
    assert probe.main(["--refusal-code-stdin", extra]) == status
    assert capsys.readouterr().out == expected + "\n"


def test_successful_live_document_is_unchanged(monkeypatch, capsys):
    expected = {"schema_version": probe.SCHEMA_VERSION, "passed": True, "refusal": None}
    monkeypatch.setattr(probe.sys, "platform", "darwin")
    monkeypatch.setattr(probe.os, "geteuid", lambda: 0)
    monkeypatch.setattr(probe, "live_probe", lambda **kwargs: expected.copy())
    assert probe.main(LIVE_ARGS) == 0
    assert json.loads(capsys.readouterr().out) == expected


@pytest.mark.parametrize("present", [True, False])
def test_provision_failure_reports_sanitized_code_and_stays_before_reservation(tmp_path, present):
    source = (ROOT / "ops/executive_os/provision-worker-auth.sh").read_text()
    start = source.index('    refusal_code="$(', source.index('IDENTITY_RESULT="$('))
    end = source.index("    exit 65", start) + len("    exit 65")
    assert end < source.index('"$SCRIPT_DIR/provider_readiness.py" reserve')
    # Run only the failure handler: no root, login, credential or provider seam.
    identity_result = tmp_path / SECRET
    if present:
        identity_result.write_text(json.dumps(document(email=SECRET)))
    command = ('PYTHON_BINARY="$1"; SCRIPT_DIR="$2"; IDENTITY_RESULT="$3"\n'
               'trap \'rm -f "$IDENTITY_RESULT"\' EXIT\n' + source[start:end])
    result = subprocess.run(["/bin/bash", "-c", command, "diagnostic-test",
                             sys.executable, str(SCRIPT.parent), str(identity_result)],
                            capture_output=True, timeout=5)
    assert result.returncode == 65
    assert result.stdout == b""
    expected = "company_plan_required" if present else "identity_probe_failed"
    assert result.stderr == ("provider identity policy refused before inference: "
                             + expected + "; no canary spent\n").encode()
    assert not identity_result.exists()
