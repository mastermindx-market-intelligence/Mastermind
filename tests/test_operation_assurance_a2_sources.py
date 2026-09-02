"""tests.test_operation_assurance_a2_sources — OLS-A2 AGENT_OS gather adapter.

Covers control_plane.operation_assurance_sources: frontmatter parsing,
seat-grammar derivation, and every refusal/degraded-fact shape the design's
Section 4/9 vocabulary requires (SOURCE_MISSING / SOURCE_PARTIAL /
SOURCE_TRUNCATED / SOURCE_CONFLICTED / INVALID_SOURCE_BUNDLE).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.operation_assurance_sources import (
    STATUS_OK,
    STATUS_SOURCE_MISSING,
    STATUS_SOURCE_PARTIAL,
    STATUS_SOURCE_TRUNCATED,
    SourceFacts,
    SourceGatherError,
    derive_seat_token,
    gather_agent_os_source_facts,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "operation_assurance_a2"
REV = "a3f6ef40d41e6d308c8d8cdc35f76802cd0525e4"


def _gather(name: str, **overrides):
    kwargs = dict(repo="mastermindx-market-intelligence/macro", revision=REV, observed_at="2026-09-02T00:00:00Z")
    kwargs.update(overrides)
    return gather_agent_os_source_facts(FIXTURES / name, **kwargs)


# ---------------------------------------------------------------------------
# Seat grammar (design Section 4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "owner,expected",
    [
        ("Fable principal (COO seat), Sol retains architecture", "COO"),
        ("(coo seat)", "COO"),
        ("(Chairman Seat)", "CHAIRMAN"),
        ("(CEO seat)", "CEO"),
        ("(WORKER seat)", "WORKER"),
    ],
)
def test_seat_grammar_exact_single_match(owner: str, expected: str) -> None:
    assert derive_seat_token(owner) == expected


@pytest.mark.parametrize(
    "owner",
    [
        "Fable principal, no seat token at all",
        "(COO seat) plus also (CEO seat) - two matches",
        "",
    ],
)
def test_seat_grammar_zero_or_multiple_matches_return_none(owner: str) -> None:
    assert derive_seat_token(owner) is None


def test_seat_grammar_repair_fix2_duplicate_identical_tokens_return_none() -> None:
    # design: "Exactly one match is required; zero or multiple matches make
    # the record an explicit SOURCE_PARTIAL fact" — two RAW matches for the
    # same seat (even identical case) is "multiple matches", not "the same
    # seat mentioned twice"; the closed grammar counts occurrences, not
    # distinct values.
    assert derive_seat_token("(COO seat) ... (COO seat)") is None
    assert derive_seat_token("(coo seat) ... (COO SEAT)") is None


# ---------------------------------------------------------------------------
# Real-record parsing (hostile fixture = byte-exact capture at the pinned SHA)
# ---------------------------------------------------------------------------


def test_hostile_fixture_parses_both_real_records_ok() -> None:
    facts = _gather("hostile")
    statuses = {f.path: f.status for f in facts.facts}
    assert statuses["agentos/workstreams/WS-OPERATION-ASSURANCE.md"] == STATUS_OK
    assert statuses["agentos/handoffs/OPERATION-ASSURANCE-2026-09-01.md"] == STATUS_OK


def test_hostile_workstream_payload_matches_the_captured_record() -> None:
    facts = _gather("hostile")
    ws = next(f for f in facts.facts if f.path.endswith("WS-OPERATION-ASSURANCE.md"))
    assert ws.payload["key"] == "OPERATION-ASSURANCE"
    assert ws.payload["status"] == "active"
    wave_a2 = next(w for w in ws.payload["waves"] if w["id"] == "A2")
    assert wave_a2["status"] == "in_progress"
    assert "Sol accepts before implementation" in wave_a2["next_action"]
    assert ws.payload["next_action"].startswith("Author and land the A2")
    assert "fable-002" in ws.payload["next_action"]
    assert derive_seat_token(ws.payload["owner"]) == "COO"


def test_hostile_handoff_payload_is_evidence_shaped() -> None:
    facts = _gather("hostile")
    ho = next(f for f in facts.facts if "handoffs" in f.path)
    assert ho.payload["workstream"] == "WS:OPERATION-ASSURANCE"
    assert ho.payload["model"] == "fable"
    assert ho.payload["ended_because"] == "complete"
    assert ho.payload["prs"] == [279, 324]
    assert ho.payload["changed"][0]["path"].startswith("mastermindx-market-intelligence/Mastermind")


def test_facts_are_byte_digested_and_source_ref_is_deterministic() -> None:
    facts = _gather("hostile")
    ws = next(f for f in facts.facts if f.path.endswith("WS-OPERATION-ASSURANCE.md"))
    raw = (FIXTURES / "hostile" / ws.path).read_bytes()
    import hashlib

    assert ws.content_digest == hashlib.sha256(raw).hexdigest()
    assert ws.source_ref() == f"{ws.repo}@{ws.revision}:{ws.path}#sha256:{ws.content_digest}"


# ---------------------------------------------------------------------------
# Refusal / degraded shapes
# ---------------------------------------------------------------------------


def test_missing_target_synthesizes_an_explicit_source_missing_fact() -> None:
    facts = _gather("missing")
    fact = next(f for f in facts.facts if f.path.endswith("WS-OPERATION-ASSURANCE.md"))
    assert fact.status == STATUS_SOURCE_MISSING
    assert fact.payload is None
    assert "OPERATION-ASSURANCE" in fact.reason


def test_malformed_status_enum_is_source_partial_not_a_healthy_default() -> None:
    facts = _gather("malformed")
    fact = facts.facts[0]
    assert fact.status == STATUS_SOURCE_PARTIAL
    assert fact.payload is None
    assert "not_a_real_status" in fact.reason


def test_truncated_record_is_flagged_and_never_partially_parsed() -> None:
    facts = _gather("truncated")
    fact = facts.facts[0]
    assert fact.status == STATUS_SOURCE_TRUNCATED
    assert fact.payload is None
    ws_family = next(c for c in facts.coverage if c.record_schema == "agentos.workstream.v1")
    assert ws_family.truncated is True


def test_repair_fix3_truncated_digest_is_explicitly_marked_as_a_prefix() -> None:
    # a digest-keyed supersession contract must never mistake a
    # prefix-of-256KiB digest for the real full-record digest.
    facts = _gather("truncated")
    fact = facts.facts[0]
    assert fact.content_digest.startswith("prefix-sha256:")
    raw_hex = fact.content_digest.removeprefix("prefix-sha256:")
    assert len(raw_hex) == 64
    int(raw_hex, 16)  # still a valid hex digest underneath the marker


def test_repair_fix3_ok_record_digest_is_never_prefix_marked() -> None:
    facts = _gather("hostile")
    for fact in facts.facts:
        assert fact.status == "OK"
        assert not fact.content_digest.startswith("prefix-sha256:")


def test_conflicting_duplicate_key_marks_both_facts_conflicted() -> None:
    facts = _gather("conflict")
    ws_facts = [f for f in facts.facts if f.record_schema == "agentos.workstream.v1"]
    assert len(ws_facts) == 2
    assert all(f.status == STATUS_OK for f in ws_facts)
    assert all(f.conflict == "CONFLICT" for f in ws_facts)


def test_gather_never_asserts_current_or_fresh_freshness() -> None:
    # design Section 4: the adapter never derives a Freshness value at all —
    # it is the Steward-level composer's job (compiler layer) to always emit
    # UNKNOWN. The wire itself carries no freshness field, only observed_at.
    facts = _gather("hostile")
    for fact in facts.facts:
        assert fact.observed_at == "2026-09-02T00:00:00Z"


# ---------------------------------------------------------------------------
# Whole-call refusals (INVALID_SOURCE_BUNDLE)
# ---------------------------------------------------------------------------


def test_abbreviated_revision_is_refused() -> None:
    with pytest.raises(SourceGatherError) as exc:
        _gather("hostile", revision=REV[:12])
    assert exc.value.reason_code == "INVALID_SOURCE_BUNDLE"


def test_nonexistent_repo_root_is_refused() -> None:
    with pytest.raises(SourceGatherError) as exc:
        gather_agent_os_source_facts(
            FIXTURES / "does_not_exist",
            repo="r",
            revision=REV,
            observed_at="2026-09-02T00:00:00Z",
        )
    assert exc.value.reason_code == "INVALID_SOURCE_BUNDLE"


def test_malformed_observed_at_is_refused() -> None:
    with pytest.raises(SourceGatherError):
        _gather("hostile", observed_at="not-a-timestamp")


def test_empty_repo_identity_is_refused() -> None:
    with pytest.raises(SourceGatherError):
        _gather("hostile", repo="")


# ---------------------------------------------------------------------------
# Wire round-trip: SourceFacts.to_dict/from_dict is the frozen, invocation-
# local wire this design defines (Section 3) — never persisted, but it must
# survive one JSON round trip for the CLI's --from-facts mode.
# ---------------------------------------------------------------------------


def test_source_facts_wire_round_trips_through_json() -> None:
    import json

    facts = _gather("hostile")
    doc = json.loads(json.dumps(facts.to_dict()))
    restored = SourceFacts.from_dict(doc)
    assert restored.to_dict() == facts.to_dict()


def test_source_facts_from_dict_refuses_malformed_document() -> None:
    with pytest.raises(SourceGatherError):
        SourceFacts.from_dict({"not": "a valid document"})
    with pytest.raises(SourceGatherError):
        SourceFacts.from_dict("not even a dict")  # type: ignore[arg-type]
