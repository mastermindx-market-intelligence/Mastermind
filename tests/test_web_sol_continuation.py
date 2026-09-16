from __future__ import annotations

import pytest

from control_plane.web_sol_continuation import (
    MAX_PACKET_BYTES,
    WebSolContinuationError,
    build_continuation,
    canonical_bytes,
)


def _agentos(*, huge: bool = False) -> dict:
    long = "x" * 20_000 if huge else "next useful action"
    row = {
        "key": "TARGET",
        "status": "active",
        "program": "program-a",
        "owner": "ceo-sol",
        "p0": "EXECUTIVE_OS",
        "next_action": long,
        "blocked_by": [long],
        "wait": {"condition": long} if huge else None,
        "needs_ceo": {"question": long} if huge else None,
        "claim": {"worker": long} if huge else None,
        "collisions": [{"detail": long}] if huge else [],
        "source": "agentos/workstreams/WS-TARGET.md",
        "wave_detail": [
            {
                "id": "DONE-1",
                "status": "done",
                "depends_on": [],
                "deps_satisfied": True,
                "next_action": "COMPLETED_DO_NOT_REPEAT",
                "prs": [1],
                "wait": None,
            },
            {
                "id": "W2",
                "status": "in_progress",
                "depends_on": ["DONE-1"],
                "deps_satisfied": True,
                "next_action": long,
                "prs": [2, 3],
                "wait": {"condition": long} if huge else None,
            },
        ],
    }
    context = {
        "schema": "context_bundle.v1",
        "generated_at": "2026-09-15T00:00:00Z",
        "source_records_digest": "sha256:" + "a" * 64,
        "target": {"workstream": "WS:TARGET"},
        "sections": [
            {
                "id": "workstream",
                "items": [
                    {
                        "kind": "workstream",
                        "key": "WS:TARGET",
                        "path": "agentos/workstreams/WS-TARGET.md",
                        "locator": "agentos/workstreams/WS-TARGET.md#frontmatter",
                        "authority_class": "A4",
                        "status": "active",
                        "updated": "2026-09-15",
                        "excerpt": long,
                        "why_included": long,
                    }
                ],
            }
        ],
    }
    return {
        "available": True,
        "source_sha": "b" * 40,
        "state": {"schema": "agent_os_state.v1", "workstreams": [row]},
        "contexts": [context],
        "warnings": [long] if huge else [],
    }


def test_continuation_is_strictly_bounded_and_excludes_raw_context() -> None:
    packet = build_continuation(_agentos(huge=True), "WS:TARGET")
    raw = canonical_bytes(packet)
    assert len(raw) <= MAX_PACKET_BYTES
    assert b'"excerpt"' not in raw
    assert b'"why_included"' not in raw
    assert b"x" * 5000 not in raw
    assert packet["state"]["next_action"]["truncated"] is True
    assert packet["active_waves"][0]["next_action"]["truncated"] is True
    assert packet["state"]["wait"]["present"] is True
    assert "condition" not in packet["state"]["wait"]


def test_continuation_preserves_do_not_redo_and_evidence_coordinates() -> None:
    packet = build_continuation(_agentos(), "WS:TARGET")
    assert packet["do_not_redo"] == ["DONE-1"]
    assert packet["active_waves"][0]["id"] == "W2"
    wave = packet["active_waves"][0]
    assert wave["depends_on"] == ["DONE-1"]
    assert wave["depends_on_total"] == 1
    assert wave["depends_on_truncated"] is False
    assert wave["prs"] == [2, 3]
    assert wave["prs_total"] == 2
    assert wave["prs_truncated"] is False
    assert packet["state"]["blocked_by_total"] == 1
    assert packet["state"]["blocked_by_truncated"] is False
    assert packet["warnings_total"] == 0
    assert packet["warnings_truncated"] is False
    assert packet["evidence_refs"] == [
        {
            "kind": "workstream",
            "key": "WS:TARGET",
            "path": "agentos/workstreams/WS-TARGET.md",
            "locator": "agentos/workstreams/WS-TARGET.md#frontmatter",
            "authority_class": "A4",
            "status": "active",
            "updated": "2026-09-15",
            "occurrences": 1,
        }
    ]
    assert packet["evidence_ref_total"] == 1
    assert packet["evidence_ref_unique_total"] == 1
    assert packet["evidence_refs_truncated"] is False


def test_duplicate_evidence_coordinates_collapse_without_losing_multiplicity() -> None:
    agentos = _agentos(huge=True)
    original = agentos["contexts"][0]["sections"][0]["items"][0]
    agentos["contexts"][0]["sections"][0]["items"] = [
        {
            **original,
            "excerpt": f"distinct source excerpt {index} " + "x" * 20_000,
            "why_included": f"distinct inclusion reason {index} " + "x" * 20_000,
        }
        for index in range(30)
    ]

    packet = build_continuation(agentos, "WS:TARGET")
    raw = canonical_bytes(packet)

    assert len(raw) <= MAX_PACKET_BYTES
    assert len(packet["evidence_refs"]) == 1
    assert packet["evidence_refs"][0]["occurrences"] == 30
    assert packet["evidence_ref_total"] == 30
    assert packet["evidence_ref_unique_total"] == 1
    assert packet["evidence_refs_truncated"] is False
    assert b'"excerpt"' not in raw
    assert b'"why_included"' not in raw


def test_opaque_owner_state_is_digest_only() -> None:
    packet = build_continuation(_agentos(huge=True), "WS:TARGET")
    for field in ("wait", "needs_ceo", "claim", "collisions"):
        marker = packet["state"][field]
        assert marker["present"] is True
        assert len(marker["sha256"]) == 64
        assert set(marker) == {"present", "sha256", "source_field"}


def test_refuses_wrong_or_unavailable_canonical_source() -> None:
    with pytest.raises(WebSolContinuationError, match="exact WS"):
        build_continuation(_agentos(), "TARGET")
    with pytest.raises(WebSolContinuationError, match="unavailable"):
        build_continuation({"available": False}, "WS:TARGET")
    with pytest.raises(WebSolContinuationError, match="exactly one requested workstream"):
        bad = _agentos()
        bad["state"]["workstreams"] = []
        build_continuation(bad, "WS:TARGET")


def test_collection_limits_are_explicit_not_silent() -> None:
    agentos = _agentos()
    row = agentos["state"]["workstreams"][0]
    row["blocked_by"] = [f"blocker-{index}" for index in range(9)]
    row["wave_detail"][1]["depends_on"] = [f"D{index}" for index in range(20)]
    row["wave_detail"][1]["prs"] = list(range(1, 21))
    agentos["warnings"] = [f"warning-{index}" for index in range(11)]

    packet = build_continuation(agentos, "WS:TARGET")
    wave = packet["active_waves"][0]

    assert len(packet["state"]["blocked_by"]) == 6
    assert packet["state"]["blocked_by_total"] == 9
    assert packet["state"]["blocked_by_truncated"] is True
    assert len(wave["depends_on"]) == 16
    assert wave["depends_on_total"] == 20
    assert wave["depends_on_truncated"] is True
    assert len(wave["prs"]) == 16
    assert wave["prs_total"] == 20
    assert wave["prs_truncated"] is True
    assert len(packet["warnings"]) == 8
    assert packet["warnings_total"] == 11
    assert packet["warnings_truncated"] is True


def test_refuses_packet_that_cannot_fit_without_dropping_required_state() -> None:
    bad = _agentos()
    bad["state"]["workstreams"][0]["wave_detail"] = [
        {
            "id": f"W{index}",
            "status": "todo",
            "depends_on": [],
            "deps_satisfied": True,
            "next_action": "y" * 2000,
            "prs": [],
            "wait": None,
        }
        for index in range(16)
    ]
    with pytest.raises(WebSolContinuationError, match="strict 8192-byte ceiling"):
        build_continuation(bad, "WS:TARGET")
