"""Fail closed on historical bar materializations without canonical source admission."""
from copy import deepcopy
import json

import pytest

from tiingo_manifest_inspection import ManifestRefusal, inspect_file, inspect_tiingo_manifest


def materialization(**changes):
    obj = {
        "schema": "mastermind.tiingo.materialized_receipt.v1",
        "source_receipt_schema": "mastermind.tiingo.raw_receipt.v1",
        "source_vendor": "tiingo",
        "source_observed_at_utc": "2026-10-12T14:59:04.419408+00:00",
        "view_schema": "mastermind.tiingo.research_views.v2",
        "rows": 570,
        "pit_backtest_eligible": False,
        "redistribution_admitted": False,
        "dataos_identity_admitted": False,
        "output_path": "/sensitive/vendor/internal.parquet",
        "source_sha256": "aa" * 32,
        "output_sha256": "bb" * 32,
    }
    obj.update(changes)
    return obj


def test_actual_observed_flag_shape_refuses_all_unadmitted_capabilities():
    r = inspect_tiingo_manifest(materialization())
    assert r["source_declared_flags"] == {
        "pit_backtest_eligible": False,
        "redistribution_admitted": False,
        "dataos_identity_admitted": False,
    }
    assert r["historical_price_admission"] == "NOT_ADMITTED"
    assert r["export_or_backtest_permitted_by_this_helper"] is False
    assert set(r["reason_codes"]) == {
        "PIT_BACKTEST_ELIGIBLE_FALSE",
        "REDISTRIBUTION_ADMITTED_FALSE",
        "DATAOS_IDENTITY_ADMITTED_FALSE",
    }
    assert "internal.parquet" not in json.dumps(r)
    assert "a" * 64 not in json.dumps(r)


@pytest.mark.parametrize("one", (
    "pit_backtest_eligible",
    "redistribution_admitted",
    "dataos_identity_admitted",
))
def test_one_false_flag_is_sufficient_to_prevent_export(one):
    flags = {
        "pit_backtest_eligible": True,
        "redistribution_admitted": True,
        "dataos_identity_admitted": True,
    }
    flags[one] = False
    result = inspect_tiingo_manifest(materialization(**flags))
    assert result["historical_price_admission"] == "NOT_ADMITTED"
    assert any(one.upper() in code for code in result["reason_codes"])


def test_all_true_flags_still_need_actual_owner_acceptance():
    result = inspect_tiingo_manifest(materialization(
        pit_backtest_eligible=True,
        redistribution_admitted=True,
        dataos_identity_admitted=True,
    ))
    assert result["reason_codes"] == ["CANONICAL_SOURCE_OWNER_ACCEPTANCE_UNVERIFIED"]
    assert result["export_or_backtest_permitted_by_this_helper"] is False


@pytest.mark.parametrize("field,value,reason", [
    ("schema", "other", "UNSUPPORTED_MATERIALIZATION_OWNER"),
    ("source_receipt_schema", "other", "UNSUPPORTED_MATERIALIZATION_OWNER"),
    ("source_vendor", "unknown", "UNSUPPORTED_MATERIALIZATION_OWNER"),
    ("source_observed_at_utc", "2026-10-12", "SOURCE_OBSERVATION_UTC_REQUIRED"),
    ("source_observed_at_utc", "2026-10-12T14:59:04-07:00", "SOURCE_OBSERVATION_UTC_REQUIRED"),
    ("view_schema", "inferred", "UNSUPPORTED_MATERIALIZED_VIEW"),
    ("rows", -1, "INVALID_MATERIALIZATION_ROWS"),
    ("rows", 1.2, "INVALID_MATERIALIZATION_ROWS"),
    ("pit_backtest_eligible", "true", "MATERIALIZATION_ADMISSION_FLAG_MISSING_OR_NOT_BOOLEAN"),
    ("redistribution_admitted", None, "MATERIALIZATION_ADMISSION_FLAG_MISSING_OR_NOT_BOOLEAN"),
    ("dataos_identity_admitted", 1, "MATERIALIZATION_ADMISSION_FLAG_MISSING_OR_NOT_BOOLEAN"),
])
def test_invalid_or_incomplete_manifest_refuses(field, value, reason):
    candidate = materialization(**{field: value})
    with pytest.raises(ManifestRefusal, match=reason):
        inspect_tiingo_manifest(candidate)


def test_file_inspection_is_read_only_and_no_price_data(tmp_path):
    path = tmp_path / "manifest.json"
    obj = materialization()
    path.write_text(json.dumps(obj))
    assert inspect_file(path)["source_rows_reported"] == 570
    assert json.loads(path.read_text()) == obj


def test_non_object_refuses():
    with pytest.raises(ManifestRefusal, match="SOURCE_RECEIPT_OBJECT_REQUIRED"):
        inspect_tiingo_manifest(["raw", "bars"])

def test_report_composes_existing_materialization_without_vendor_bar_leak(tmp_path):
    from replay_casebook import build_report
    receipt = tmp_path / 'source.json'
    receipt.write_text(json.dumps(materialization()))
    report = build_report(tiingo_manifest_path=receipt)
    block = report['historical_price_materialization_inspection']
    assert report['sample_size'] == 9
    assert block['historical_price_admission'] == 'NOT_ADMITTED'
    assert block['export_or_backtest_permitted_by_this_helper'] is False
    assert '/sensitive' not in json.dumps(report)
    assert report['point_in_time_analyst_consensus'] == 'NOT_ADMITTED'


def test_cli_shows_explicit_tiingo_admission_refusal_and_no_price_exports(tmp_path, capsys):
    from replay_casebook import main
    receipt = tmp_path / 'source.json'
    receipt.write_text(json.dumps(materialization()))
    assert main(['--format', 'json', '--tiingo-manifest', str(receipt)]) == 0
    data = json.loads(capsys.readouterr().out)
    diag = data['historical_price_materialization_inspection']
    assert diag['source_declared_flags']['redistribution_admitted'] is False
    assert diag['historical_price_admission'] == 'NOT_ADMITTED'
    assert 'output_path' not in json.dumps(data)
    assert main(['--format', 'markdown', '--tiingo-manifest', str(receipt)]) == 0
    message = capsys.readouterr().out
    assert 'Existing Tiingo materialization status (NOT source admission)' in message
    assert 'REDISTRIBUTION_ADMITTED_FALSE' in message


def test_cli_bad_rights_diagnostics_refuse_typed(tmp_path, capsys):
    from replay_casebook import main
    p = tmp_path / 'invalid.json'
    p.write_text(json.dumps(materialization(redistribution_admitted='granted')))
    assert main(['--format', 'json', '--tiingo-manifest', str(p)]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out['status'] == 'REFUSED'
    assert out['reason'] == 'MATERIALIZATION_ADMISSION_FLAG_MISSING_OR_NOT_BOOLEAN'


def test_no_tiingo_receipt_keeps_standalone_evidence_unchanged():
    from replay_casebook import build_report
    r = build_report()
    assert r['historical_price_materialization_inspection'] is None
    assert r['sample_size'] == 9
