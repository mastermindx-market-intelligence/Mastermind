"""Regression for the F12 JSON wire boundary; synthetic values only."""
import copy
import json
import math
import pytest
from integrations.research_read_mcp import CONTRACT
from integrations.research_read_mcp import contracts as c

def status():
    return {
        "contract": CONTRACT, "source_state": "SOURCE_FRESH",
        "producer": {"last_success_at": "2026-10-07T00:00:00Z", "age_seconds": 1.5, "stale": False},
        "catalog": {"report_count": 2},
        "coverage": {"full_text_ratio": 1.0, "rio_ratio": 0.5},
        "degradation": [],
        "generation": {"server_contract": CONTRACT, "read_port_contract": "research_vault.read_status.v1", "mastermind_commit": "b" * 40},
    }

FIELDS = [("producer", "age_seconds"), ("coverage", "full_text_ratio"), ("coverage", "rio_ratio")]
NONFINITE = [float("nan"), float("inf"), float("-inf")]

@pytest.mark.parametrize("parent,field", FIELDS)
@pytest.mark.parametrize("value", NONFINITE, ids=["nan", "positive_infinity", "negative_infinity"])
def test_status_nonfinite_is_internal_error_without_rewrite(parent, field, value):
    result = status()
    result[parent][field] = value
    before = json.dumps(result, sort_keys=True)
    with pytest.raises(c.ContractViolation) as caught:
        c.validate_output("research_status", result)
    assert caught.value.code == "INTERNAL_ERROR"
    assert str(caught.value) == "INTERNAL_ERROR"
    assert caught.value.__cause__ is None
    assert json.dumps(result, sort_keys=True) == before
    assert result[parent][field] is value

@pytest.mark.parametrize("value", NONFINITE, ids=["nan", "positive_infinity", "negative_infinity"])
def test_result_wire_bytes_cannot_certify_nonfinite_json(value):
    with pytest.raises(ValueError):
        c.result_wire_bytes({"nested": {"number": value}})

@pytest.mark.parametrize("value", [0, 0.0, -0.0, 0.5, 1, 1.0])
def test_finite_coverage_is_unchanged_and_strict_json(value):
    result = status()
    result["coverage"]["full_text_ratio"] = value
    result["coverage"]["rio_ratio"] = value
    before = copy.deepcopy(result)
    c.validate_output("research_status", result)
    assert result == before
    strict_compact = json.dumps(result, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    strict_rendered = json.dumps(result, indent=2, allow_nan=False)
    assert c.result_wire_bytes(result) == len(strict_compact.encode()) + len(strict_rendered.encode())

@pytest.mark.parametrize("value", [None, 0, -0.0, 1.5, 1e100])
def test_finite_or_unknown_age_preserved(value):
    result = status()
    result["producer"]["age_seconds"] = value
    c.validate_output("research_status", result)
    assert result["producer"]["age_seconds"] == value

def test_literal_nonfinite_words_are_not_numbers():
    result = status()
    result["generation"]["read_port_contract"] = "NaN Infinity -Infinity"
    c.validate_output("research_status", result)
    assert c.result_wire_bytes(result) > 0
