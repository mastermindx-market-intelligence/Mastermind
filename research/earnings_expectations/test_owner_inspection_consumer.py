"""Exercise existing K3E producer format through the read-only casebook consumer."""
import json

import pytest

from expectation_owner_adapter import OwnerContractError
from replay_casebook import build_report, main, markdown
from test_expectation_owner_adapter import owner_document, recalc


def test_native_owner_capture_status_appears_without_false_issuer_binding(tmp_path):
    fixture = tmp_path / "k3e_inspection.json"
    fixture.write_text(json.dumps(owner_document()))
    report = build_report(owner_inspection_path=fixture)
    block = report["native_expectation_owner_inspection"]
    assert report["sample_size"] == 9
    assert report["point_in_time_analyst_consensus"] == "NOT_ADMITTED"
    assert block["source_schema"] == "k3e.declared_capture_inspection.v1"
    assert block["ticker_compat"] == "GOOGL"
    assert block["issuer_binding"] == "NOT_ESTABLISHED_BY_TICKER_COMPAT_ALONE"
    assert block["baseline_value"] is None
    assert block["baseline_status"] == "UNESTIMABLE"
    assert "NORMALIZED_CONSUMER_ADMISSION_NOT_GRANTED" in block["reason_codes"]
    assert "raw-observation-not-normalized" not in json.dumps(report)
    formatted = markdown(report)
    assert "Existing Macro EXP-1/K3E declared-capture inspection" in formatted
    assert "No baseline value" in formatted
    assert "SOURCE_USE_RIGHTS_UNKNOWN" in formatted


def test_cli_json_and_markdown_emit_exact_source_refusal(tmp_path, capsys):
    fixture = tmp_path / "owner.json"
    fixture.write_text(json.dumps(owner_document()))
    assert main(["--format", "json", "--owner-inspection", str(fixture)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["native_expectation_owner_inspection"]["baseline_use"] == "NOT_ADMITTED"
    assert main(["--format", "markdown", "--owner-inspection", str(fixture)]) == 0
    formatted = capsys.readouterr().out
    assert "UNESTIMABLE" in formatted
    assert "GOOGL / EPS / 0q" in formatted


def test_invalid_digest_cannot_be_downgraded_to_empty_owner_state(tmp_path):
    doc = owner_document()
    doc["semantic_payload"]["normalized_baseline"]["value"] = 99.0
    fixture = tmp_path / "bad.json"
    fixture.write_text(json.dumps(doc))
    with pytest.raises(OwnerContractError, match="SOURCE_OWNER_DIGEST_MISMATCH"):
        build_report(owner_inspection_path=fixture)
    fixture.write_text(json.dumps(recalc(doc)))
    with pytest.raises(OwnerContractError, match="NORMALIZED_BASELINE_PROMOTION_REQUIRES_NEW_CONTRACT"):
        build_report(owner_inspection_path=fixture)


def test_missing_requested_owner_file_refuses_instead_of_silent_fallback(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_report(owner_inspection_path=tmp_path / "missing.json")


def test_without_owner_file_base_report_remains_provenance_honest():
    report = build_report()
    assert report["native_expectation_owner_inspection"] is None
    assert report["management_guidance_status"] == "AVAILABLE_COMPANY_MANAGEMENT_GUIDANCE_ONLY"
    assert report["media_reported_expectation_status"] == "PUBLIC_ARTICLE_WITNESSES_ONLY_NOT_ADMITTED_AS_PIT"

def test_cli_invalid_owner_digest_returns_structured_refusal(tmp_path, capsys):
    doc = owner_document()
    doc['semantic_payload']['normalized_baseline']['value'] = 42.0
    fixture = tmp_path / 'tampered.json'
    fixture.write_text(json.dumps(doc))
    assert main(['--format', 'json', '--owner-inspection', str(fixture)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'REFUSED'
    assert result['reason'] == 'SOURCE_OWNER_DIGEST_MISMATCH'
    assert result['authority'] == 'RESEARCH_ONLY_NO_TRADING'
    assert '42' not in json.dumps(result)


def test_cli_nonexistent_owner_file_fail_closed_without_traceback(tmp_path, capsys):
    missing = tmp_path / 'not_present.json'
    assert main(['--format', 'markdown', '--owner-inspection', str(missing)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert captured.err.strip() == 'Research source refused: RESEARCH_SOURCE_INPUT_INVALID'


def test_cli_old_contract_with_non_null_baseline_remains_unadmitted(tmp_path, capsys):
    doc = owner_document()
    doc['semantic_payload']['normalized_baseline']['value'] = 3.14
    fixture = tmp_path / 'unsupported_future_owner_contract.json'
    fixture.write_text(json.dumps(recalc(doc)))
    assert main(['--format', 'json', '--owner-inspection', str(fixture)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['reason'] == 'NORMALIZED_BASELINE_PROMOTION_REQUIRES_NEW_CONTRACT'
    assert 'baseline_value' not in result
