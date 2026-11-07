"""Event-identity crosswalk is an explicit research-only consumer attachment."""
import json

import pytest

from event_workspace_binding import NativeEventBindingError
from replay_casebook import build_report, main, markdown
from test_event_workspace_binding import _owner, _packet


SOURCE = "earnings:CIK:1652044:2026Q2"


def _receipt_file(tmp_path, packet=None):
    packet = packet or _packet()
    path = tmp_path / "native_reader_receipt.json"
    path.write_text(json.dumps(_owner(packet)))
    return path


def test_one_selected_canonical_event_attaches_only_to_matching_research_row(tmp_path):
    path = _receipt_file(tmp_path)
    report = build_report(native_event_workspace_path=path, native_event_ref=SOURCE)
    bound = report["native_event_workspace_binding"]
    assert report["sample_size"] == 9
    assert bound["status"] == "IDENTITY_MATCHED_OWNER_READER_RECEIPT_DECLARED"
    assert bound["candidate_event_id"] == "evt_cik0001652044_2026q2_results"
    assert bound["research_event_ref"] == SOURCE
    assert report["tradeable_alpha_status"] == "NOT_ESTABLISHED"
    assert bound["owner_verified_by_this_helper"] is False
    assert bound["source_owner_identity_admitted"] is False
    assert "https://" not in json.dumps(bound)


def test_markdown_and_json_consumers_keep_reader_non_admission(tmp_path, capsys):
    path = _receipt_file(tmp_path)
    assert main(["--format", "json", "--native-event-workspace", str(path),
                 "--native-event-ref", SOURCE]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["native_event_workspace_binding"]["status"] == "IDENTITY_MATCHED_OWNER_READER_RECEIPT_DECLARED"
    assert data["point_in_time_analyst_consensus"] == "NOT_ADMITTED"
    assert main(["--format", "markdown", "--native-event-workspace", str(path),
                 "--native-event-ref", SOURCE]) == 0
    md = capsys.readouterr().out
    assert "Existing Earnings Intelligence event identity (owner receipt only)" in md
    assert "does not re-fetch or hash-verify" in md
    assert "evt_cik0001652044_2026q2_results" in md


def test_explicit_event_and_owner_receipt_are_both_required(tmp_path, capsys):
    path = _receipt_file(tmp_path)
    assert main(["--format", "json", "--native-event-workspace", str(path)]) == 2
    err = json.loads(capsys.readouterr().out)
    assert err["reason"] == "NATIVE_WORKSPACE_AND_EXPLICIT_EVENT_REF_REQUIRED"
    assert main(["--format", "json", "--native-event-ref", SOURCE]) == 2
    err = json.loads(capsys.readouterr().out)
    assert err["reason"] == "NATIVE_WORKSPACE_AND_EXPLICIT_EVENT_REF_REQUIRED"


def test_wrong_issuer_quarter_or_event_cannot_attach(tmp_path, capsys):
    path = _receipt_file(tmp_path)
    for event in ("earnings:CIK:1018724:2026Q2", "earnings:CIK:1652044:2028Q2"):
        assert main(["--format", "json", "--native-event-workspace", str(path),
                     "--native-event-ref", event]) == 2
        err = json.loads(capsys.readouterr().out)
        if event == "earnings:CIK:1018724:2026Q2":
            assert err["reason"] == "NATIVE_EVENT_IDENTITY_MISMATCH"
        else:
            assert err["reason"] == "RESEARCH_EVENT_UNAVAILABLE_OR_AMBIGUOUS"


def test_missing_native_owner_does_not_create_new_event_truth(tmp_path):
    path = tmp_path / "owner_not_published.json"
    path.write_text(json.dumps({"available": False, "note": "not covered"}))
    report = build_report(native_event_workspace_path=path, native_event_ref=SOURCE)
    assert report["native_event_workspace_binding"]["status"] == "OWNER_EVENT_UNAVAILABLE"
    assert report["native_event_workspace_binding"]["owner_verified_by_this_helper"] is False


def test_no_native_reader_context_keeps_existing_report_unchanged():
    r = build_report()
    assert r["native_event_workspace_binding"] is None
    assert r["sample_size"] == 9
    assert r["point_in_time_analyst_consensus"] == "NOT_ADMITTED"
    assert "Existing Earnings Intelligence event identity" not in markdown(r)


def test_tampered_native_event_does_not_silently_fallback(tmp_path, capsys):
    p = _packet()
    owner = _owner(p)
    owner["workspace"]["fiscal_period"]["quarter"] = 1
    path = tmp_path / "wrong_quarter.json"
    path.write_text(json.dumps(owner))
    assert main(["--format", "json", "--native-event-workspace", str(path),
                 "--native-event-ref", SOURCE]) == 2
    err = json.loads(capsys.readouterr().out)
    assert err["reason"] == "NATIVE_FISCAL_TARGET_MISMATCH"
    assert err["status"] == "REFUSED"
