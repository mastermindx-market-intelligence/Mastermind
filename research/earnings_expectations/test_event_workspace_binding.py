"""Only the incumbent Earnings OS reader can verify the immutable event workspace.

This adapter tests economic identity alignment and fail-closed boundaries using
synthetic reader envelopes; no test claims live R2 publication proof.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from event_workspace_binding import (
    NativeEventBindingError, bind_native_event, candidate_identity,
)

BASE = Path(__file__).parent / "sourced_event_packets"


def _packet(name="googl_2026q2"):
    return json.loads((BASE / (name + ".json")).read_text())


def _owner(packet):
    candidate = candidate_identity(packet)
    event_id = candidate["candidate_event_id"]
    generation = "a" * 24
    base = "https://pub-source-owner.r2.dev/company_intelligence/event_workspaces"
    return {
        "available": True,
        "event_id": event_id,
        "authority": "context_only",
        "is_context_only": True,
        "display_only": True,
        "untrusted_source_data": True,
        "workspace": {
            "schema": "event_workspace.v1",
            "event_id": event_id,
            "issuer": {
                "company_id": candidate["issuer_company_id"],
                "listings": [
                    {"ticker": candidate["research_security_ticker"]},
                    {"ticker": "GOOG" if candidate["research_security_ticker"] == "GOOGL" else "OTHER"},
                ],
            },
            "fiscal_period": {
                "year": candidate["fiscal_year"],
                "quarter": candidate["fiscal_quarter"],
                "calendar_end": None,
            },
            "authority": "context_only",
            "prophet_flags": {
                "may_rank": False, "may_size": False, "may_gate": False,
                "prophet_authority": False,
            },
            "generated_at": "2026-10-14T21:20:00Z",
            "generation_id": generation,
        },
        "receipt": {
            "generation_id": generation,
            "marker_sha256": "b" * 64,
            "workspace_sha256": "c" * 64,
            "marker_url": base + "/manifest.json",
            "immutable_manifest_url": (
                base + "/generations/" + generation + "/manifest.json"
            ),
            "workspace_url": (
                base + "/generations/" + generation + "/workspaces/"
                + event_id + ".json"
            ),
        },
    }


@pytest.mark.parametrize("name,expected", [
    ("googl_2025q4", "evt_cik0001652044_2025q4_results"),
    ("googl_2026q1", "evt_cik0001652044_2026q1_results"),
    ("googl_2026q2", "evt_cik0001652044_2026q2_results"),
    ("amzn_2025q4", "evt_cik0001018724_2025q4_results"),
    ("amzn_2026q1", "evt_cik0001018724_2026q1_results"),
    ("amzn_2026q2", "evt_cik0001018724_2026q2_results"),
    ("msft_fy2026q2", "evt_cik0000789019_2026q2_results"),
    ("msft_fy2026q3", "evt_cik0000789019_2026q3_results"),
    ("msft_fy2026q4", "evt_cik0000789019_2026q4_results"),
])
def test_issuer_quarter_candidate_matches_existing_macro_format(name, expected):
    p = _packet(name)
    assert candidate_identity(p)["candidate_event_id"] == expected
    binding = bind_native_event(p, _owner(p))
    assert binding["status"] == "IDENTITY_MATCHED_OWNER_READER_RECEIPT_DECLARED"
    assert binding["candidate_event_id"] == expected
    assert binding["owner_workspace_sha256"] == "c" * 64
    assert binding["owner_verified_by_this_helper"] is False
    assert binding["source_owner_identity_admitted"] is False
    assert binding["authority"] == "RESEARCH_DISPLAY_ONLY_NO_TRADING"


def test_dual_class_googl_goog_issuer_is_one_cik():
    packet = _packet("googl_2026q2")
    owner = _owner(packet)
    owner["workspace"]["issuer"]["listings"] = [
        {"ticker": "GOOGL"}, {"ticker": "GOOG"}
    ]
    binding = bind_native_event(packet, owner)
    assert binding["candidate_event_id"] == "evt_cik0001652044_2026q2_results"


def test_missing_owner_is_not_assumed_to_be_current():
    packet = _packet()
    out = bind_native_event(packet, {"available": False, "note": "not published"})
    assert out["status"] == "OWNER_EVENT_UNAVAILABLE"
    assert out["source_owner_identity_admitted"] is False
    assert "owner_generation_id" not in out


@pytest.mark.parametrize(("component", "key", "value", "reason"), [
    ("root", "authority", "predictive", "NATIVE_OWNER_READER_CONTEXT_ENVELOPE_REQUIRED"),
    ("root", "is_context_only", False, "NATIVE_OWNER_READER_CONTEXT_ENVELOPE_REQUIRED"),
    ("root", "event_id", "evt_cik0000320193_2026q3_results", "NATIVE_EVENT_IDENTITY_MISMATCH"),
    ("workspace", "schema", "event_workspace.v2", "NATIVE_WORKSPACE_SCHEMA_UNSUPPORTED"),
    ("workspace", "event_id", "evt_cik0000320193_2026q3_results", "NATIVE_EVENT_IDENTITY_MISMATCH"),
    ("issuer", "company_id", "cik:0000320193", "NATIVE_ISSUER_IDENTITY_MISMATCH"),
    ("fiscal_period", "quarter", 1, "NATIVE_FISCAL_TARGET_MISMATCH"),
    ("fiscal_period", "quarter", "2", "NATIVE_FISCAL_TARGET_MISMATCH"),
    ("issuer", "listings", [{"ticker": "MSFT"}], "NATIVE_LISTING_ALIAS_MISMATCH"),
    ("workspace", "authority", "trade", "NATIVE_EVENT_AUTHORITY_NOT_CONTEXT_ONLY"),
    ("workspace", "prophet_flags", {"may_rank": True}, "NATIVE_EVENT_AUTHORITY_NOT_CONTEXT_ONLY"),
    ("receipt", "generation_id", "f" * 24, "NATIVE_GENERATION_RECEIPT_MISMATCH"),
    ("receipt", "workspace_sha256", "not-a-hash", "NATIVE_IMMUTABLE_HASH_RECEIPT_REQUIRED"),
    ("receipt", "workspace_url", "https://bad.r2.dev/file", "NATIVE_IMMUTABLE_RECEIPT_ORIGIN_MISMATCH"),
    ("receipt", "marker_url", "http://private.test", "IMMUTABLE_OWNER_RECEIPT_URL_REQUIRED"),
    ("workspace", "generated_at", "not-a-date", "NATIVE_GENERATION_CLOCK_REQUIRED"),
])
def test_wrong_binding_and_source_authority_fail_closed(component, key, value, reason):
    packet = _packet()
    native = _owner(packet)
    obj = native if component == "root" else (
        native["workspace"] if component == "workspace" else
        native["receipt"] if component == "receipt" else
        native["workspace"][component]
    )
    obj[key] = value
    with pytest.raises(NativeEventBindingError, match=reason):
        bind_native_event(packet, native)


def test_real_case_identity_from_cik_never_from_security_ticker():
    packet = _packet("googl_2026q2")
    owner = _owner(packet)
    owner["workspace"]["issuer"]["company_id"] = "cik:0001018724"
    with pytest.raises(NativeEventBindingError, match="NATIVE_ISSUER_IDENTITY_MISMATCH"):
        bind_native_event(packet, owner)


@pytest.mark.parametrize(("field", "value"), [
    ("issuer_ref", "TICKER:GOOGL"),
    ("issuer_ref", "CIK:BAD"),
    ("fiscal_target", "2026FY2026Q2"),
    ("fiscal_target", "2026Q5"),
    ("fiscal_target", "2026Q2Q3"),
])
def test_ambiguous_research_identity_cannot_adopt_event(field, value):
    packet = _packet()
    packet["event"][field] = value
    with pytest.raises(NativeEventBindingError, match="CIK_AND_EXPLICIT_FISCAL_QUARTER_REQUIRED"):
        candidate_identity(packet)


def test_unsupported_non_issuer_ticker_is_not_silently_joined():
    packet = _packet()
    packet["price_series"]["issuer"]["ticker"] = "NVDA"
    with pytest.raises(NativeEventBindingError, match="NATIVE_LISTING_ALIAS_MISMATCH"):
        bind_native_event(packet, _owner(_packet()))

def test_malformed_security_bundle_refuses_without_attribute_error():
    packet = _packet()
    packet['price_series'] = {'issuer': None}
    with pytest.raises(NativeEventBindingError, match='EXPLICIT_RESEARCH_SECURITY_TICKER_REQUIRED'):
        candidate_identity(packet)


def test_missing_research_event_identity_refuses_without_key_error():
    packet = _packet()
    packet['event'].pop('event_ref')
    with pytest.raises(NativeEventBindingError, match='RESEARCH_EVENT_ID_REQUIRED'):
        candidate_identity(packet)


def test_owner_generation_clock_must_be_timezone_qualified():
    packet = _packet()
    owner = _owner(packet)
    owner['workspace']['generated_at'] = '2026-10-14T20:00:00'
    with pytest.raises(NativeEventBindingError, match='NATIVE_GENERATION_CLOCK_REQUIRED'):
        bind_native_event(packet, owner)


def test_owner_only_reports_receipt_even_if_source_hash_shape_passes():
    packet = _packet()
    owner = _owner(packet)
    owner['receipt']['workspace_sha256'] = 'e' * 64
    out = bind_native_event(packet, owner)
    assert out['owner_workspace_sha256'] == 'e' * 64
    assert out['owner_verified_by_this_helper'] is False
    assert out['source_owner_identity_admitted'] is False
    assert out['status'] == 'IDENTITY_MATCHED_OWNER_READER_RECEIPT_DECLARED'

def test_later_owner_generation_cannot_be_recast_as_historical_event_evidence():
    p = _packet('googl_2026q2')
    r = bind_native_event(p, _owner(p))
    assert r['owner_generation_postdates_research_asof'] is True
    assert r['historical_event_availability_verified'] is False
    assert r['source_owner_identity_admitted'] is False


def test_older_owner_generation_still_does_not_grant_historical_availability():
    p = _packet()
    owner = _owner(p)
    owner['workspace']['generated_at'] = '2026-07-01T20:00:00Z'
    r = bind_native_event(p, owner)
    assert r['owner_generation_postdates_research_asof'] is False
    assert r['historical_event_availability_verified'] is False


def test_without_research_cutoff_owner_availability_stays_unknown():
    p = _packet()
    p.pop('evaluated_asof_utc')
    r = bind_native_event(p, _owner(p))
    assert r['owner_generation_postdates_research_asof'] is None
    assert r['historical_event_availability_verified'] is False


@pytest.mark.parametrize('clock', ['2026-07-01T10:00:00', 'invalid', False])
def test_invalid_asof_cannot_create_a_historical_owner_join(clock):
    p = _packet()
    p['evaluated_asof_utc'] = clock
    with pytest.raises(NativeEventBindingError, match='RESEARCH_ASOF_UTC_INVALID'):
        bind_native_event(p, _owner(_packet()))


def test_unpublished_owner_is_not_historical_proof():
    p = _packet()
    unavailable = bind_native_event(p, {'available': False})
    assert unavailable['historical_event_availability_verified'] is False
    assert unavailable['owner_generation_postdates_research_asof'] is None
