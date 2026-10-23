"""Offline evidence candidate inspection never grants BytePlus capacity."""
import copy
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from scripts.byteplus_attended_canary_evidence import (
    CanaryEvidenceInputError,
    inspect_attended_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "examples" / "byteplus_attended_canary_template.json"
SHA = "a" * 64


def template():
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def complete_example():
    d = template()
    d["client"].update(version="2.1.296", binary_sha256=SHA)
    d["attempt"].update(
        operation_id="attended-demo-1",
        attended=True,
        started_at_unix=1792728000,
        ended_at_unix=1792728120,
        requested_model="glm-5.3-flash",
        served_model="glm-5.3-flash",
        terminal_outcome="success",
        artifact_sha256="b" * 64,
    )
    for prefix, observed in (("before", 1792727980), ("after", 1792728150)):
        snap = d[prefix]
        snap["observed_at_unix"] = observed
        snap["used_percent_rounded"] = dict(session=0, weekly=0, monthly=0)
        snap["reset_at"] = {
            "session": "2026-10-23T00:00:00+08:00",
            "weekly": "2026-10-26T00:00:00+08:00",
            "monthly": "2026-11-22T23:59:59+08:00",
        }
    return d


def test_blank_template_valid_but_completely_non_authoritative():
    d = template()
    before = copy.deepcopy(d)
    report = inspect_attended_evidence(d)
    assert d == before
    assert not report["candidate_fields_complete"]
    assert "attended_session" in report["missing_or_inconclusive"]
    assert report["evidence_scope"] == "OPERATOR_SUPPLIED_UNVERIFIED"
    assert report["actual_concurrent_worker_limit"] is None
    assert report["estimated_startable_jobs"] is None
    assert report["autonomous_start_authorized"] is False


def test_even_complete_self_report_and_receipt_hash_cannot_approve_worker():
    d = complete_example()
    d["provider_receipt_sha256"] = "c" * 64
    report = inspect_attended_evidence(d)
    assert report["candidate_fields_complete"] is True
    assert report["missing_or_inconclusive"] == []
    assert report["provider_receipt_digest_supplied"] is True
    assert report["quota_snapshot_windows_comparable"] is True
    for field in ("served_model_proven_by_issuer", "individual_request_debit_proven",
                  "provider_origin_attested", "capacity_fact_issued", "autonomous_start_authorized"):
        assert report[field] is False


def test_changed_rounded_percent_still_not_proof_of_single_request():
    d = complete_example()
    d["after"]["used_percent_rounded"]["weekly"] = 1
    report = inspect_attended_evidence(d)
    assert report["candidate_fields_complete"] is True
    assert report["individual_request_debit_proven"] is False


def test_missing_or_changed_reset_blocks_comparable_snapshot():
    for different in (None, "2026-10-27T00:00:00+08:00"):
        d = complete_example()
        d["after"]["reset_at"]["weekly"] = different
        v = inspect_attended_evidence(d)
        assert not v["quota_snapshot_windows_comparable"]
        assert "comparable_management_windows" in v["missing_or_inconclusive"]


def test_real_cli_session_reset_missing_both_still_reports_inconclusive():
    d = complete_example()
    for position in ("before", "after"):
        d[position]["reset_at"]["session"] = None
    report = inspect_attended_evidence(d)
    assert report["candidate_fields_complete"] is True
    assert report["weekly_monthly_windows_comparable"] is True
    assert report["session_window_comparable"] is False
    assert report["quota_snapshot_windows_comparable"] is False
    assert report["inconclusive_caveats"] == ["session_reset_not_reported"]
    assert report["individual_request_debit_proven"] is False
    assert report["provider_origin_attested"] is False
    assert report["capacity_fact_issued"] is False


@pytest.mark.parametrize("which", ["before", "after"])
def test_one_sided_missing_session_reset_refuses_completeness(which):
    d = complete_example()
    d[which]["reset_at"]["session"] = None
    report = inspect_attended_evidence(d)
    assert report["candidate_fields_complete"] is False
    assert "session_window_reset_discontinuity" in report["missing_or_inconclusive"]


def test_changed_session_reset_refuses_completeness():
    d = complete_example()
    d["after"]["reset_at"]["session"] = "2026-10-24T00:00:00+08:00"
    report = inspect_attended_evidence(d)
    assert report["candidate_fields_complete"] is False
    assert report["session_window_comparable"] is False
    assert "session_window_reset_discontinuity" in report["missing_or_inconclusive"]


def test_missing_session_percentage_refuses_completeness_even_when_reset_unknown():
    d = complete_example()
    d["before"]["reset_at"]["session"] = None
    d["after"]["reset_at"]["session"] = None
    d["after"]["used_percent_rounded"]["session"] = None
    report = inspect_attended_evidence(d)
    assert report["candidate_fields_complete"] is False
    assert "session_window_percentages" in report["missing_or_inconclusive"]


def test_requested_served_model_mismatch_never_passes_completeness():
    d = complete_example()
    d["attempt"]["served_model"] = "dola-seed-2.0-lite"
    v = inspect_attended_evidence(d)
    assert not v["candidate_fields_complete"]
    assert "requested_served_model_match" in v["missing_or_inconclusive"]


@pytest.mark.parametrize("change", [
    lambda d: d.__setitem__("api_key", "secret"),
    lambda d: d["client"].__setitem__("endpoint", "https://ark.ap-southeast.bytepluses.com/api/v3"),
    lambda d: d["client"].__setitem__("name", "unreviewed launcher"),
    lambda d: d["attempt"].__setitem__("operation_id", "a@b.com"),
    lambda d: d["attempt"].__setitem__("requested_model", "glm-5.3"),
    lambda d: d["attempt"].__setitem__("attended", 1),
    lambda d: d["attempt"].__setitem__("started_at_unix", False),
    lambda d: d["before"]["used_percent_rounded"].__setitem__("weekly", True),
    lambda d: d["before"]["used_percent_rounded"].__setitem__("session", -1),
    lambda d: d["after"]["reset_at"].__setitem__("monthly", "2026-11-22 01:00:00"),
    lambda d: d["attempt"].__setitem__("artifact_sha256", "not-a-hash"),
    lambda d: d.__setitem__("provider_receipt_sha256", "BAD"),
    lambda d: d["after"].__setitem__("observed_at_unix", d["before"]["observed_at_unix"]),
])
def test_bad_or_privacy_extending_evidence_fails_closed(change):
    d = complete_example()
    change(d)
    with pytest.raises(CanaryEvidenceInputError):
        inspect_attended_evidence(d)


@pytest.mark.parametrize("field", ["before", "after"])
def test_snapshot_wrong_shape_refused(field):
    d = complete_example()
    d[field]["account_id"] = "do-not-store"
    with pytest.raises(CanaryEvidenceInputError):
        inspect_attended_evidence(d)


def test_observation_must_enclose_attempt_to_count_completeness():
    d = complete_example()
    d["before"]["observed_at_unix"] = d["attempt"]["started_at_unix"] + 1
    d["after"]["observed_at_unix"] = d["attempt"]["ended_at_unix"] - 1
    v = inspect_attended_evidence(d)
    assert "pre_attempt_management_snapshot" in v["missing_or_inconclusive"]
    assert "post_attempt_management_snapshot" in v["missing_or_inconclusive"]
    assert not v["candidate_fields_complete"]


def test_preflight_never_calls_network_or_subprocess(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("attempted network or process execution")
    with monkeypatch.context() as p:
        p.setattr(socket, "socket", forbidden)
        p.setattr(subprocess, "Popen", forbidden)
        assert inspect_attended_evidence(template())["capacity_fact_issued"] is False


def test_cli_json_contract():
    proc = subprocess.run([sys.executable, "-m", "scripts.byteplus_attended_canary_evidence", str(TEMPLATE)],
                          cwd=ROOT, capture_output=True, text=True, check=True, timeout=15)
    row = json.loads(proc.stdout)
    assert row["schema"] == "mastermind.byteplus_attended_evidence_inspection.v1"
    assert row["evidence_scope"] == "OPERATOR_SUPPLIED_UNVERIFIED"
    assert row["autonomous_start_authorized"] is False
    assert proc.stderr == ""


def test_cli_never_echoes_unrecognized_private_payload(tmp_path):
    d = template()
    d["user_email"] = "secret@example.invalid"
    path = tmp_path / "private.json"
    path.write_text(json.dumps(d))
    proc = subprocess.run([sys.executable, "-m", "scripts.byteplus_attended_canary_evidence", str(path)],
                          cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert proc.returncode == 2
    assert "secret@" not in proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["capacity_fact_issued"] is False
