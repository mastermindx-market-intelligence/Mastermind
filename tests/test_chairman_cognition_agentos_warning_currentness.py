"""RED tests for typed Agent OS currentness channels in Chairman Cognition A2.

Agent OS deliberately separates unavailable joins (inputs.degraded), malformed
readiness truth (readiness.degraded), and advisory state/hygiene observations
(warnings).  Advisory warnings remain content-bound evidence; they are not
source-unavailability by themselves.
"""
from __future__ import annotations

from copy import deepcopy

from control_plane.chairman_cognition_sources import (
    _agentos_brief_status,
    _agentos_receipt,
    _payload_digest,
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
