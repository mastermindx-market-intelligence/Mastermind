"""Real-process stdin/out consumer for the non-executable global shadow."""
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

from scripts.compare_global_shadow import MAX_REQUEST_BYTES, REQUEST_SCHEMA, parse_request, InvalidRequest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "_global_shadow_test_fixtures", ROOT / "tests" / "test_global_shadow_research.py"
)
assert spec is not None and spec.loader is not None
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


def request():
    return {
        "schema": REQUEST_SCHEMA,
        "context": f.context(),
        "book": f.book(),
        "alternatives": [
            f.alt("hold"),
            f.alt("cash", {}, 1),
            f.alt("china", {"SPY": .3, "FXI": .3}),
        ],
        "scenarios": [f.scenario()],
        "as_of": f.AS_OF,
    }


def call(raw: bytes):
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.compare_global_shadow"],
        input=raw, cwd=ROOT, capture_output=True, timeout=15,
    )
    assert proc.stderr == b"", proc.stderr.decode("utf-8", errors="replace")[:200]
    return proc.returncode, json.loads(proc.stdout)


def serial(obj):
    return json.dumps(obj, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def test_real_cli_machine_response_is_stale_and_no_capital_authority():
    rc, result = call(serial(request()))
    assert rc == 0
    assert result["status"] == "AVAILABLE"
    assert result["market_context"]["status"] == "STALE"
    assert result["market_context"]["excluded_ids"] == ["USO"]
    assert result["market_context"]["source_authenticated"] is False
    assert all(v is False for v in result["authority"].values())
    assert result["no_predictive_claim"] is True
    assert [r["alternative_id"] for r in result["alternatives"]] == ["cash", "china", "hold"]


def test_actual_cli_cash_returns_use_only_supplied_hypothetical_numbers():
    rc, result = call(serial(request()))
    assert rc == 0
    rows = {x["alternative_id"]: x for x in result["alternatives"]}
    assert rows["hold"]["scenario_results"][0]["net_return"] == pytest.approx(-.0596)
    assert rows["cash"]["scenario_results"][0]["net_return"] == pytest.approx(.00064)
    assert rows["china"]["scenario_results"][0]["net_return"] == pytest.approx(-.01496)
    assert "rank" not in result and "trade" not in result


def test_unavailable_uso_cannot_be_sneaked_into_research_alternative():
    obj = request()
    obj["alternatives"].append(f.alt("USO_buy", {"USO": .2, "SPY": .4}))
    rc, result = call(serial(obj))
    assert rc == 0
    rows = {x["alternative_id"]: x for x in result["alternatives"]}
    assert rows["USO_buy"]["status"] == "UNAVAILABLE"
    assert rows["china"]["status"] == "AVAILABLE"


def test_foreign_hk_listing_forgery_abstains():
    obj = request()
    obj["context"]["rows"][0]["listing_market"] = "HK"
    rc, result = call(serial(obj))
    assert rc == 0
    assert result["reasons"] == ["context_row_invalid"]
    assert result["status"] == "UNAVAILABLE"


def test_real_process_disallows_named_real_account():
    obj = request()
    obj["book"]["book_id"] = "autonomous"
    rc, result = call(serial(obj))
    assert rc == 0
    assert result["reasons"] == ["research_book_identity_invalid"]
    assert result["authority"]["can_trade"] is False


@pytest.mark.parametrize("bad", [
    b"", b"null", b"[]", b"{", b"{}", b"\xff",
    b'{"schema":"x"}',
    b'{"schema":"x","schema":"y"}',
])
def test_malformed_or_duplicate_top_level_json_sanitized(bad):
    rc, result = call(bad)
    assert rc == 2
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "request_unqualified"
    assert not any(result["authority"].values())
    assert "account" not in json.dumps(result).lower()


def test_duplicate_nested_account_key_is_refused():
    raw = serial(request())
    # Duplicate a nested field, not only the top-level request schema.
    raw = raw.replace(b'"book_id":"global_research_shadow"', b'"book_id":"global_research_shadow","book_id":"autonomous"', 1)
    rc, result = call(raw)
    assert rc == 2
    assert result["reason"] == "request_unqualified"


@pytest.mark.parametrize("literal", [b"NaN", b"Infinity", b"-Infinity"])
def test_nonfinite_json_constant_refused(literal):
    raw = serial(request()).replace(b'"cash_return":0.001', b'"cash_return":' + literal, 1)
    assert raw != serial(request())
    rc, result = call(raw)
    assert rc == 2
    assert result["reason"] == "request_unqualified"


def test_max_payload_size_bounded_before_qualification():
    rc, result = call(b" " * (MAX_REQUEST_BYTES + 1))
    assert rc == 2
    assert result["reason"] == "request_unqualified"


def test_extra_unknown_request_fields_not_interpreted_as_authority():
    obj = request()
    obj["can_trade"] = True
    rc, result = call(serial(obj))
    assert rc == 2
    assert result["authority"]["can_trade"] is False


def test_missing_scenarios_keeps_semantic_unavailable_not_transport_error():
    obj = request()
    obj["scenarios"] = []
    rc, result = call(serial(obj))
    assert rc == 0
    assert result["status"] == "UNAVAILABLE"
    assert result["reasons"] == ["alternatives_or_scenarios_missing_or_duplicate"]


def test_no_input_mutation_when_parsing_and_executing():
    obj = request()
    before = copy.deepcopy(obj)
    parsed = parse_request(serial(obj))
    assert parsed == before
    _, result = call(serial(obj))
    assert obj == before and result["no_predictive_claim"]


def test_parse_request_invalid_type_is_error():
    with pytest.raises(InvalidRequest):
        parse_request(b"{}")


def test_degenerate_non_object_context_abstains_without_leaking_input():
    obj = request()
    obj["book"]["book_revision"] = "secret-token-lookalike"
    obj["context"] = "not_a_context"
    rc, result = call(serial(obj))
    assert rc == 2
    assert "secret-token-lookalike" not in json.dumps(result)


def test_cli_has_no_net_data_or_account_write_imports():
    source = (ROOT / "scripts" / "compare_global_shadow.py").read_text()
    for banned in ("requests", "httpx", "socket.", "open(", "sqlite3", "pickle", "portfolio.paper_account"):
        assert banned not in source
