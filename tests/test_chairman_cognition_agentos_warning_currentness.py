"""RED tests for typed Agent OS currentness channels in Chairman Cognition A2.

Agent OS deliberately separates unavailable joins (inputs.degraded), malformed
readiness truth (readiness.degraded), and advisory state/hygiene observations
(warnings).  Advisory warnings remain content-bound evidence; they are not
source-unavailability by themselves.
"""
from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

from control_plane.chairman_cognition_sources import (
    AGENT_OS_SOURCE_REF,
    _agentos_brief_status,
    _agentos_receipt,
    _payload_digest,
    compose_input,
    evaluate_bundle,
)


_OBSERVED_AT = "2026-09-03T11:20:00Z"
_MACRO_SHA = "a" * 40
_RECORDS_DIGEST = "sha256:" + "b" * 64


def _brief(*, warnings: list[object] | None = None) -> dict[str, object]:
    return {
        "schema": "ceo_brief.v1",
        "generated_at": _OBSERVED_AT,
        "since": "2026-09-02T11:20:00Z",
        "since_label": "24h",
        "counts": {
            "total": 1,
            "active": 1,
            "awaiting_ci": 0,
            "blocked": 0,
            "done_in_window": 0,
        },
        "inputs": {
            "worktrees": 1,
            "active_builds_age_hours": 0.25,
            "degraded": [],
        },
        "needs_ceo": [],
        "blocked": [],
        "finished": [],
        "running": {
            "active": 1,
            "awaiting_ci": 0,
            "awaiting_review": 0,
            "blocked": 0,
            "proposed": 0,
            "open_prs": 0,
            "stale_claims": 0,
            "claims_without_worktree": 0,
        },
        "readiness": {
            "schema": "agentos.readiness.v1",
            "records": [],
            "degraded": [],
        },
        "warnings": [] if warnings is None else warnings,
    }


def _receipt(brief: dict[str, object], *, attested_payload_digest: str | None = None):
    return _agentos_receipt(
        {"macro": {"sha": _MACRO_SHA}, "brief": brief},
        _OBSERVED_AT,
        {
            "revision": _MACRO_SHA,
            "state": "CURRENT",
            "load_bearing": True,
            "observed_at": _OBSERVED_AT,
        },
        {
            "source_records_digest": _RECORDS_DIGEST,
            "payload_digest": attested_payload_digest or _payload_digest(brief),
        },
    )


def _public_bundle_with_warnings(warnings: list[str]) -> dict[str, object]:
    fixture_path = Path(__file__).with_name("test_chairman_cognition_sources.py")
    spec = importlib.util.spec_from_file_location(
        "_chairman_cognition_sources_test_fixtures", fixture_path
    )
    assert spec is not None
    assert spec.loader is not None
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)

    brief = fixture_module._brief(warnings=warnings)  # type: ignore[attr-defined]
    boot = fixture_module._boot_packet(brief=brief)  # type: ignore[attr-defined]
    return fixture_module._bundle(boot=boot)  # type: ignore[attr-defined,no-any-return]


def test_advisory_agentos_warnings_preserve_current_source() -> None:
    brief = _brief(
        warnings=[
            "WS:X — status is 'active' but every wave is done/dropped",
            "agentos/workstreams/WS-X.md: [phantom-owns-path] path is absent",
            "agentos/decisions/DEC-X.md: [review-overdue] review date passed",
        ]
    )

    valid, observed_at = _agentos_brief_status(brief)

    assert valid is True
    assert observed_at == _OBSERVED_AT
    assert _receipt(brief)["state"] == "CURRENT"


def test_advisory_warnings_reach_current_through_public_composer() -> None:
    bundle = _public_bundle_with_warnings(
        ["agentos/decisions/DEC-X.md: [review-overdue] review date passed"]
    )

    composed = compose_input(bundle)
    receipt = next(
        item
        for item in composed["source_receipts"]
        if item["source_ref"] == AGENT_OS_SOURCE_REF
    )
    assert receipt["state"] == "CURRENT"

    result = evaluate_bundle(bundle)
    summary = next(
        item
        for item in result["source_summary"]
        if item["source_ref"] == AGENT_OS_SOURCE_REF
    )
    assert summary["state"] == "CURRENT"
    assert result["packet"]["recommended_option_id"] == "OPT-COMPOSE"


def test_unavailable_agentos_input_remains_noncurrent() -> None:
    brief = _brief()
    brief["inputs"]["degraded"] = ["active_builds.v1 unavailable"]  # type: ignore[index]

    assert _agentos_brief_status(brief)[0] is False
    assert _receipt(brief)["state"] == "UNKNOWN"


def test_degraded_readiness_remains_noncurrent() -> None:
    brief = _brief()
    brief["readiness"]["degraded"] = ["record excluded (malformed): WS:X"]  # type: ignore[index]

    assert _agentos_brief_status(brief)[0] is False
    assert _receipt(brief)["state"] == "UNKNOWN"


def test_malformed_warning_wire_remains_noncurrent() -> None:
    brief = _brief(warnings=["valid warning", 7])

    assert _agentos_brief_status(brief)[0] is False
    assert _receipt(brief)["state"] == "UNKNOWN"


def test_warning_mutation_after_attestation_is_conflict() -> None:
    brief = _brief(warnings=["original advisory warning"])
    attested_digest = _payload_digest(brief)
    mutated = deepcopy(brief)
    mutated["warnings"] = ["different advisory warning"]

    assert _receipt(mutated, attested_payload_digest=attested_digest)["state"] == "CONFLICT"
