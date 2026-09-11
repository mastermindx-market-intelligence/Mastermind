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


def test_repair_fix7_empty_flow_mapping_lists_parse_as_zero_items() -> None:
    # found via the FIX 7 real-tree-shaped proof: a handoff whose
    # unverified/unresolved lists are genuinely empty (an EMPTY list is a
    # valid, schema-documented answer) must parse, not refuse.
    from control_plane.operation_assurance_sources import parse_handoff_frontmatter

    text = """---
schema: agentos.handoff.v1
workstream: "WS:OPERATION-ASSURANCE"
session: s
model: sonnet
ended_because: complete
mission: >
  m
state_before: >
  b
changed: []
verified: []
unverified: []
unresolved: []
next_actions:
  - "keep going"
do_not_redo:
  - "nothing yet"
danger_areas:
  - "none"
---
body
"""
    payload = parse_handoff_frontmatter(text)
    assert payload["changed"] == []
    assert payload["verified"] == []
    assert payload["unverified"] == []


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


# ---------------------------------------------------------------------------
# REPAIR B1 (Sol pre-review): --from-facts must be a genuinely CLOSED wire,
# not a field-copying passthrough. Every mutation class below must refuse
# with SourceGatherError (CLI exit 2), never silently accepted.
# ---------------------------------------------------------------------------


def _baseline_doc() -> dict:
    import copy
    import json

    facts = _gather("hostile")
    return copy.deepcopy(json.loads(json.dumps(facts.to_dict())))


def _ws_fact(doc: dict) -> dict:
    return next(f for f in doc["facts"] if f["record_schema"] == "agentos.workstream.v1")


def _ho_fact(doc: dict) -> dict:
    return next(f for f in doc["facts"] if f["record_schema"] == "agentos.handoff.v1")


def _assert_refused(doc: dict) -> None:
    with pytest.raises(SourceGatherError):
        SourceFacts.from_dict(doc)


def test_b1_baseline_document_is_accepted() -> None:
    # sanity: the mutation tests below all start from something that DOES
    # parse, so a refusal in them is meaningful.
    SourceFacts.from_dict(_baseline_doc())


def test_b1_unknown_top_level_key_refused() -> None:
    doc = _baseline_doc()
    doc["evil_field"] = "pwned"
    _assert_refused(doc)


def test_b1_missing_top_level_key_refused() -> None:
    doc = _baseline_doc()
    del doc["revision_binding"]
    _assert_refused(doc)


def test_b1_wrong_schema_refused() -> None:
    doc = _baseline_doc()
    doc["schema"] = "not.the.right.schema"
    _assert_refused(doc)


def test_b1_wrong_source_owner_at_top_level_refused() -> None:
    doc = _baseline_doc()
    doc["source_owner"] = "SOMEONE_ELSE"
    _assert_refused(doc)


def test_b1_bad_revision_binding_refused() -> None:
    doc = _baseline_doc()
    doc["revision_binding"] = "TOTALLY_VERIFIED"
    _assert_refused(doc)


def test_b1_unknown_fact_field_refused() -> None:
    doc = _baseline_doc()
    _ws_fact(doc)["evil_field"] = "pwned"
    _assert_refused(doc)


def test_b1_missing_fact_field_refused() -> None:
    doc = _baseline_doc()
    del _ws_fact(doc)["conflict"]
    _assert_refused(doc)


def test_b1_unknown_fact_status_refused() -> None:
    doc = _baseline_doc()
    _ws_fact(doc)["status"] = "TOTALLY_FINE"
    _assert_refused(doc)


def test_b1_unknown_fact_conflict_enum_refused() -> None:
    doc = _baseline_doc()
    _ws_fact(doc)["conflict"] = "MAYBE"
    _assert_refused(doc)


def test_b1_unknown_fact_record_schema_refused() -> None:
    doc = _baseline_doc()
    _ws_fact(doc)["record_schema"] = "not.a.schema"
    _assert_refused(doc)


@pytest.mark.parametrize(
    "bad_digest",
    [
        "not-hex-at-all",
        "deadbeef",  # too short
        "g" * 64,  # not hex
        "prefix-sha256:" + "a" * 64,  # marker present on a non-truncated fact
    ],
)
def test_b1_malformed_digest_shapes_refused(bad_digest: str) -> None:
    doc = _baseline_doc()
    _ws_fact(doc)["content_digest"] = bad_digest
    _assert_refused(doc)


def test_b1_truncated_fact_without_prefix_marker_refused() -> None:
    doc = _baseline_doc()
    fact = _ws_fact(doc)
    fact["status"] = "SOURCE_TRUNCATED"
    fact["reason"] = "record exceeds MAX_FILE_BYTES"
    fact["payload"] = None
    fact["content_digest"] = "a" * 64  # missing the required prefix-sha256: marker
    _assert_refused(doc)


def test_b1_ok_fact_with_non_null_reason_refused() -> None:
    doc = _baseline_doc()
    _ws_fact(doc)["reason"] = "should be null on an OK fact"
    _assert_refused(doc)


def test_b1_non_ok_fact_with_non_null_payload_refused() -> None:
    doc = _baseline_doc()
    fact = _ws_fact(doc)
    fact["status"] = "SOURCE_MISSING"
    fact["reason"] = "synthetic"
    # payload stays non-null despite the status change -> refused
    _assert_refused(doc)


def test_b1_mixed_repo_across_facts_refused() -> None:
    doc = _baseline_doc()
    _ws_fact(doc)["repo"] = "a-different/repo"
    _assert_refused(doc)


def test_b1_mixed_revision_across_facts_refused_single_revision_rule() -> None:
    doc = _baseline_doc()
    _ws_fact(doc)["revision"] = "b" * 40
    _assert_refused(doc)


def test_b1_mixed_observed_at_across_facts_refused_single_cutoff_rule() -> None:
    doc = _baseline_doc()
    _ws_fact(doc)["observed_at"] = "2099-01-01T00:00:00Z"
    _assert_refused(doc)


def test_b1_duplicate_fact_path_refused() -> None:
    doc = _baseline_doc()
    dup = dict(_ws_fact(doc))
    doc["facts"].append(dup)
    _assert_refused(doc)


def test_b1_inconsistent_coverage_ok_count_refused() -> None:
    doc = _baseline_doc()
    ws_cov = next(c for c in doc["coverage"] if c["record_schema"] == "agentos.workstream.v1")
    ws_cov["ok"] = 999
    _assert_refused(doc)


def test_b1_inconsistent_coverage_attempted_count_refused() -> None:
    doc = _baseline_doc()
    ws_cov = next(c for c in doc["coverage"] if c["record_schema"] == "agentos.workstream.v1")
    ws_cov["attempted"] = 0  # a fact is present, so 0 is inconsistent
    _assert_refused(doc)


def test_b1_inconsistent_coverage_truncated_flag_refused() -> None:
    doc = _baseline_doc()
    ws_cov = next(c for c in doc["coverage"] if c["record_schema"] == "agentos.workstream.v1")
    ws_cov["truncated"] = True  # no truncated fact is present
    _assert_refused(doc)


def test_b1_missing_coverage_family_refused() -> None:
    doc = _baseline_doc()
    doc["coverage"] = [c for c in doc["coverage"] if c["record_schema"] != "agentos.handoff.v1"]
    _assert_refused(doc)


def test_b1_duplicate_coverage_family_refused() -> None:
    doc = _baseline_doc()
    doc["coverage"].append(dict(doc["coverage"][0]))
    _assert_refused(doc)


def test_b1_ok_payload_unknown_field_refused_on_ingest() -> None:
    # a payload that would have never survived the ORIGINAL frontmatter
    # parse (an injected unknown field) must also be refused when it
    # arrives pre-parsed via --from-facts, not merely trusted.
    doc = _baseline_doc()
    _ws_fact(doc)["payload"]["evil_field"] = "pwned"
    _assert_refused(doc)


def test_b1_ok_payload_bad_status_enum_refused_on_ingest() -> None:
    doc = _baseline_doc()
    _ws_fact(doc)["payload"]["status"] = "not_a_real_status"
    _assert_refused(doc)


def test_b1_ok_payload_missing_required_field_refused_on_ingest() -> None:
    doc = _baseline_doc()
    del _ws_fact(doc)["payload"]["waves"]
    _assert_refused(doc)


def test_b1_ok_payload_bad_seat_grammar_refused_on_ingest() -> None:
    doc = _baseline_doc()
    _ws_fact(doc)["payload"]["owner"] = "no seat token here"
    _assert_refused(doc)


def test_b1_ok_handoff_payload_bad_model_enum_refused_on_ingest() -> None:
    doc = _baseline_doc()
    _ho_fact(doc)["payload"]["model"] = "not_a_real_model"
    _assert_refused(doc)


# --- duplicate JSON keys: must be caught at the RAW TEXT level (a parsed
# dict can never itself carry a duplicate key), so these go through
# from_json_bytes directly rather than from_dict.


def test_b1_duplicate_json_key_at_top_level_refused() -> None:
    raw = b'{"schema": "a", "schema": "b"}'
    with pytest.raises(SourceGatherError):
        SourceFacts.from_json_bytes(raw)


def test_b1_duplicate_json_key_inside_a_fact_payload_refused() -> None:
    import json

    doc = _baseline_doc()
    text = json.dumps(doc)
    # inject a duplicate "key" entry inside the workstream payload object,
    # which object_pairs_hook must catch even though it is deeply nested.
    needle = '"key": "OPERATION-ASSURANCE"'
    assert needle in text
    text = text.replace(needle, needle + ', "key": "OPERATION-ASSURANCE"', 1)
    with pytest.raises(SourceGatherError):
        SourceFacts.from_json_bytes(text.encode("utf-8"))


def test_b1_from_json_bytes_rejects_invalid_utf8() -> None:
    with pytest.raises(SourceGatherError):
        SourceFacts.from_json_bytes(b"\xff\xfe\x00\x01")


def test_b1_from_json_bytes_oversized_input_refused() -> None:
    from control_plane.operation_assurance_sources import MAX_SOURCE_FACTS_JSON_BYTES

    with pytest.raises(SourceGatherError):
        SourceFacts.from_json_bytes(b" " * (MAX_SOURCE_FACTS_JSON_BYTES + 1))


# ---------------------------------------------------------------------------
# REPAIR B2 (Sol pre-review): the pinned revision is bound to the checkout
# actually read — pure file reads only, no subprocess. A git checkout
# (loose ref, detached HEAD, packed ref, or a worktree `.git` FILE) whose
# real HEAD disagrees with the caller's asserted revision must be refused;
# a bare directory (no .git) must carry the honest
# CALLER_ASSERTED_UNVERIFIED marker, never a silently promoted one.
# ---------------------------------------------------------------------------

import shutil as _shutil


def _copy_hostile(tmp_path) -> "Path":
    from pathlib import Path

    dest = tmp_path / "checkout"
    _shutil.copytree(FIXTURES / "hostile", dest)
    return dest


def test_b2_bare_directory_no_git_is_caller_asserted_unverified() -> None:
    facts = _gather("hostile")
    assert facts.revision_binding == "CALLER_ASSERTED_UNVERIFIED"


def test_b2_loose_branch_ref_matching_revision_is_git_head_verified(tmp_path) -> None:
    dest = _copy_hostile(tmp_path)
    sha = "b" * 40
    (dest / ".git" / "refs" / "heads").mkdir(parents=True)
    (dest / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (dest / ".git" / "refs" / "heads" / "main").write_text(sha + "\n", encoding="utf-8")

    facts = gather_agent_os_source_facts(dest, repo="r", revision=sha, observed_at="2026-09-02T00:00:00Z")
    assert facts.revision_binding == "GIT_HEAD_VERIFIED"


def test_b2_falsifier_mismatched_checkout_revision_is_refused(tmp_path) -> None:
    """The B2 falsifier: a real git checkout whose HEAD genuinely disagrees
    with the caller's asserted revision must be refused, not silently
    recorded as if the caller's assertion were true."""
    dest = _copy_hostile(tmp_path)
    real_head = "b" * 40
    asserted = "c" * 40
    assert real_head != asserted
    (dest / ".git" / "refs" / "heads").mkdir(parents=True)
    (dest / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (dest / ".git" / "refs" / "heads" / "main").write_text(real_head + "\n", encoding="utf-8")

    with pytest.raises(SourceGatherError) as exc:
        gather_agent_os_source_facts(dest, repo="r", revision=asserted, observed_at="2026-09-02T00:00:00Z")
    assert exc.value.reason_code == "REVISION_MISMATCH"
    assert real_head in str(exc.value)
    assert asserted in str(exc.value)


def test_b2_detached_head_matching_revision_is_git_head_verified(tmp_path) -> None:
    dest = _copy_hostile(tmp_path)
    sha = "d" * 40
    (dest / ".git").mkdir()
    (dest / ".git" / "HEAD").write_text(sha + "\n", encoding="utf-8")

    facts = gather_agent_os_source_facts(dest, repo="r", revision=sha, observed_at="2026-09-02T00:00:00Z")
    assert facts.revision_binding == "GIT_HEAD_VERIFIED"


def test_b2_detached_head_mismatch_refused(tmp_path) -> None:
    dest = _copy_hostile(tmp_path)
    (dest / ".git").mkdir()
    (dest / ".git" / "HEAD").write_text(("e" * 40) + "\n", encoding="utf-8")

    with pytest.raises(SourceGatherError) as exc:
        gather_agent_os_source_facts(dest, repo="r", revision="f" * 40, observed_at="2026-09-02T00:00:00Z")
    assert exc.value.reason_code == "REVISION_MISMATCH"


def test_b2_packed_refs_matching_revision_is_git_head_verified(tmp_path) -> None:
    dest = _copy_hostile(tmp_path)
    sha = "1" * 40
    (dest / ".git").mkdir()
    (dest / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (dest / ".git" / "packed-refs").write_text(
        f"# pack-refs with: peeled fully-peeled sorted\n{sha} refs/heads/main\n", encoding="utf-8"
    )

    facts = gather_agent_os_source_facts(dest, repo="r", revision=sha, observed_at="2026-09-02T00:00:00Z")
    assert facts.revision_binding == "GIT_HEAD_VERIFIED"


def test_b2_worktree_gitfile_pointer_resolves(tmp_path) -> None:
    """A linked worktree's `.git` is a FILE containing `gitdir: <path>`,
    not a directory — real git worktrees (including this very repo's own
    session worktrees) use exactly this shape."""
    dest = _copy_hostile(tmp_path)
    real_gitdir = tmp_path / "real_gitdir"
    (real_gitdir / "refs" / "heads").mkdir(parents=True)
    sha = "2" * 40
    (real_gitdir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (real_gitdir / "refs" / "heads" / "main").write_text(sha + "\n", encoding="utf-8")
    (dest / ".git").write_text(f"gitdir: {real_gitdir}\n", encoding="utf-8")

    facts = gather_agent_os_source_facts(dest, repo="r", revision=sha, observed_at="2026-09-02T00:00:00Z")
    assert facts.revision_binding == "GIT_HEAD_VERIFIED"


def test_b2_unresolvable_git_head_falls_back_to_caller_asserted_unverified(tmp_path) -> None:
    dest = _copy_hostile(tmp_path)
    (dest / ".git").mkdir()
    (dest / ".git" / "HEAD").write_text("ref: refs/heads/nonexistent\n", encoding="utf-8")

    facts = gather_agent_os_source_facts(dest, repo="r", revision="3" * 40, observed_at="2026-09-02T00:00:00Z")
    assert facts.revision_binding == "CALLER_ASSERTED_UNVERIFIED"


def test_b2_revision_binding_round_trips_through_the_closed_wire() -> None:
    import json

    facts = _gather("hostile")
    restored = SourceFacts.from_dict(json.loads(json.dumps(facts.to_dict())))
    assert restored.revision_binding == facts.revision_binding == "CALLER_ASSERTED_UNVERIFIED"


# ---------------------------------------------------------------------------
# REPAIR R1 (Sol CONTINUE): a REALISTIC linked-worktree layout — HEAD lives
# in the PRIVATE per-worktree gitdir, the branch ref exists ONLY in the
# COMMON gitdir (found via the private gitdir's own `commondir` file) — the
# exact shape real git worktrees produce (including this very repo's own
# session worktrees). Sol's binding test law: three falsifiers.
# ---------------------------------------------------------------------------


def _build_linked_worktree(tmp_path, *, branch_sha: str | None, break_commondir: bool = False):
    """Constructs: <tmp_path>/main/.git/{refs/heads/feature, worktrees/wt/{HEAD, commondir}}
    and <tmp_path>/checkout/.git (a FILE pointing at the private gitdir).
    Returns the checkout dir."""
    main_gitdir = tmp_path / "main" / ".git"
    private_gitdir = main_gitdir / "worktrees" / "wt"
    (main_gitdir / "refs" / "heads").mkdir(parents=True)
    private_gitdir.mkdir(parents=True)

    private_gitdir_head = "ref: refs/heads/feature\n"
    (private_gitdir / "HEAD").write_text(private_gitdir_head, encoding="utf-8")
    if not break_commondir:
        (private_gitdir / "commondir").write_text("../..\n", encoding="utf-8")
    # else: no commondir file at all -> unreadable step -> must degrade

    if branch_sha is not None:
        (main_gitdir / "refs" / "heads" / "feature").write_text(branch_sha + "\n", encoding="utf-8")
    # else: the branch ref is deliberately absent from the common gitdir too

    checkout = tmp_path / "checkout"
    import shutil as _sh

    _sh.copytree(FIXTURES / "hostile", checkout)
    (checkout / ".git").write_text(f"gitdir: {private_gitdir}\n", encoding="utf-8")
    return checkout


def test_r1_falsifier_1_linked_worktree_matching_revision_verifies(tmp_path) -> None:
    sha = "4" * 40
    checkout = _build_linked_worktree(tmp_path, branch_sha=sha)
    # sanity: the branch ref lives ONLY in the common gitdir, never the
    # private one — this is the realistic shape Sol's test law requires.
    assert not (checkout.resolve().parent / "main" / ".git" / "worktrees" / "wt" / "refs").exists()

    facts = gather_agent_os_source_facts(checkout, repo="r", revision=sha, observed_at="2026-09-02T00:00:00Z")
    assert facts.revision_binding == "GIT_HEAD_VERIFIED"


def test_r1_falsifier_2_linked_worktree_asserted_mismatch_refuses(tmp_path) -> None:
    real_sha = "5" * 40
    asserted = "6" * 40
    checkout = _build_linked_worktree(tmp_path, branch_sha=real_sha)

    with pytest.raises(SourceGatherError) as exc:
        gather_agent_os_source_facts(checkout, repo="r", revision=asserted, observed_at="2026-09-02T00:00:00Z")
    assert exc.value.reason_code == "REVISION_MISMATCH"
    assert real_sha in str(exc.value)
    assert asserted in str(exc.value)


def test_r1_falsifier_3_linked_worktree_broken_commondir_degrades_unverified(tmp_path) -> None:
    checkout = _build_linked_worktree(tmp_path, branch_sha="7" * 40, break_commondir=True)

    facts = gather_agent_os_source_facts(checkout, repo="r", revision="8" * 40, observed_at="2026-09-02T00:00:00Z")
    assert facts.revision_binding == "CALLER_ASSERTED_UNVERIFIED"


def test_r1_falsifier_3b_linked_worktree_branch_ref_missing_everywhere_degrades_unverified(tmp_path) -> None:
    checkout = _build_linked_worktree(tmp_path, branch_sha=None)

    facts = gather_agent_os_source_facts(checkout, repo="r", revision="9" * 40, observed_at="2026-09-02T00:00:00Z")
    assert facts.revision_binding == "CALLER_ASSERTED_UNVERIFIED"


def test_r1_linked_worktree_packed_refs_in_common_gitdir_verifies(tmp_path) -> None:
    """The branch ref may also be packed in the COMMON gitdir (never the
    private one) — must still resolve."""
    sha = "a1" + "0" * 38
    checkout = _build_linked_worktree(tmp_path, branch_sha=None)
    main_gitdir = tmp_path / "main" / ".git"
    (main_gitdir / "packed-refs").write_text(
        f"# pack-refs with: peeled fully-peeled sorted\n{sha} refs/heads/feature\n", encoding="utf-8"
    )

    facts = gather_agent_os_source_facts(checkout, repo="r", revision=sha, observed_at="2026-09-02T00:00:00Z")
    assert facts.revision_binding == "GIT_HEAD_VERIFIED"  # end of R1 packed-refs-in-common-gitdir test


# ---------------------------------------------------------------------------
# REPAIR R2 (Sol CONTINUE): a serialized GIT_HEAD_VERIFIED is NEVER trusted
# on --from-facts ingest. reestablish_revision_binding() is the ONLY lawful
# upgrade path, and only given a LIVE, matching repo_root in the SAME
# invocation.
# ---------------------------------------------------------------------------


def test_r2_forged_git_head_verified_is_downgraded_on_from_dict_ingest() -> None:
    facts = _gather("hostile")
    doc = facts.to_dict()
    assert doc["revision_binding"] == "CALLER_ASSERTED_UNVERIFIED"
    doc["revision_binding"] = "GIT_HEAD_VERIFIED"  # forged
    restored = SourceFacts.from_dict(doc)
    assert restored.revision_binding == "CALLER_ASSERTED_UNVERIFIED"


def test_r2_forged_git_head_verified_is_downgraded_on_from_json_bytes_ingest() -> None:
    import json

    facts = _gather("hostile")
    doc = facts.to_dict()
    doc["revision_binding"] = "GIT_HEAD_VERIFIED"
    restored = SourceFacts.from_json_bytes(json.dumps(doc).encode("utf-8"))
    assert restored.revision_binding == "CALLER_ASSERTED_UNVERIFIED"


def test_r2_reestablish_with_live_matching_root_upgrades(tmp_path) -> None:
    from control_plane.operation_assurance_sources import reestablish_revision_binding

    dest = _copy_hostile(tmp_path)
    sha = "b3" + "0" * 38
    (dest / ".git").mkdir()
    (dest / ".git" / "HEAD").write_text(sha + "\n", encoding="utf-8")

    facts = gather_agent_os_source_facts(dest, repo="r", revision=sha, observed_at="2026-09-02T00:00:00Z")
    doc = facts.to_dict()
    doc["revision_binding"] = "GIT_HEAD_VERIFIED"  # forged in the serialized document
    ingested = SourceFacts.from_dict(doc)
    assert ingested.revision_binding == "CALLER_ASSERTED_UNVERIFIED"  # downgraded on ingest

    reestablished = reestablish_revision_binding(ingested, dest)
    assert reestablished.revision_binding == "GIT_HEAD_VERIFIED"  # legitimately re-derived


def test_r2_reestablish_with_live_mismatched_root_refuses(tmp_path) -> None:
    from control_plane.operation_assurance_sources import reestablish_revision_binding

    dest = _copy_hostile(tmp_path)
    real_sha = "c4" + "0" * 38
    asserted_sha = "d5" + "0" * 38
    (dest / ".git").mkdir()
    (dest / ".git" / "HEAD").write_text(real_sha + "\n", encoding="utf-8")

    facts = gather_agent_os_source_facts(
        FIXTURES / "hostile", repo="r", revision=asserted_sha, observed_at="2026-09-02T00:00:00Z"
    )
    doc = facts.to_dict()
    doc["revision_binding"] = "GIT_HEAD_VERIFIED"
    ingested = SourceFacts.from_dict(doc)

    with pytest.raises(SourceGatherError) as exc:
        reestablish_revision_binding(ingested, dest)
    assert exc.value.reason_code == "REVISION_MISMATCH"


def test_r2_reestablish_with_unresolvable_root_leaves_unverified(tmp_path) -> None:
    from control_plane.operation_assurance_sources import reestablish_revision_binding

    facts = _gather("hostile")
    reestablished = reestablish_revision_binding(facts, tmp_path)  # tmp_path has no .git at all
    assert reestablished.revision_binding == "CALLER_ASSERTED_UNVERIFIED"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc: doc.__setitem__("source_owner", doc["source_owner"]),  # no-op control
        lambda doc: doc["coverage"][0].__setitem__("glob", doc["coverage"][0]["glob"]),  # no-op control
    ],
)
def test_r2_no_root_case_never_loses_the_downgrade_under_serialized_mutation(mutate) -> None:
    # a lawful, otherwise-harmless mutation to the serialized document must
    # never smuggle GIT_HEAD_VERIFIED back in when no live root is supplied.
    facts = _gather("hostile")
    doc = facts.to_dict()
    doc["revision_binding"] = "GIT_HEAD_VERIFIED"
    mutate(doc)
    restored = SourceFacts.from_dict(doc)
    assert restored.revision_binding == "CALLER_ASSERTED_UNVERIFIED"


# ---------------------------------------------------------------------------
# REPAIR R3 (Sol CONTINUE): the closed path/glob shape applies on BOTH
# sides — gather discovery and serialized ingest. Hostile --from-facts
# mutations for each refusal class, plus real gather cases with an
# escaping symlink and a nested directory.
# ---------------------------------------------------------------------------


def _assert_ingest_refused(doc: dict) -> None:
    with pytest.raises(SourceGatherError):
        SourceFacts.from_dict(doc)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/agentos/workstreams/WS-OPERATION-ASSURANCE.md",  # absolute
        "agentos\\workstreams\\WS-OPERATION-ASSURANCE.md",  # backslash
        "agentos/workstreams/./WS-OPERATION-ASSURANCE.md",  # '.' segment
        "agentos/workstreams/../workstreams/WS-OPERATION-ASSURANCE.md",  # '..' segment
        "agentos/workstreams/nested/WS-OPERATION-ASSURANCE.md",  # nested descendant
        "agentos/handoffs/WS-OPERATION-ASSURANCE.md",  # family/schema mismatch (workstream schema, handoffs path)
        "agentos/workstreams/WS-OPERATION-ASSURANCE.txt",  # wrong extension
        "not-even-under-agentos/WS-OPERATION-ASSURANCE.md",  # wrong root entirely
    ],
)
def test_r3_ingest_path_mutation_refused_for_each_class(bad_path: str) -> None:
    doc = _baseline_doc()
    _ws_fact(doc)["path"] = bad_path
    _assert_ingest_refused(doc)


def test_r3_ingest_coverage_glob_mismatch_refused() -> None:
    doc = _baseline_doc()
    ws_cov = next(c for c in doc["coverage"] if c["record_schema"] == "agentos.workstream.v1")
    ws_cov["glob"] = "agentos/workstreams/**/*.md"  # not the canonical glob
    _assert_ingest_refused(doc)


def test_r3_ingest_swapped_family_glob_refused() -> None:
    # the handoff family's coverage entry claiming the workstream glob
    doc = _baseline_doc()
    ws_cov = next(c for c in doc["coverage"] if c["record_schema"] == "agentos.workstream.v1")
    ho_cov = next(c for c in doc["coverage"] if c["record_schema"] == "agentos.handoff.v1")
    ws_cov["glob"], ho_cov["glob"] = ho_cov["glob"], ws_cov["glob"]
    _assert_ingest_refused(doc)


def test_r3_gather_real_case_escaping_symlink_becomes_source_partial(tmp_path) -> None:
    dest = _copy_hostile(tmp_path)
    outside = tmp_path / "outside_secret.md"
    outside.write_text("secret content outside repo root", encoding="utf-8")
    evil = dest / "agentos" / "workstreams" / "WS-EVIL.md"
    evil.symlink_to(outside)

    facts = gather_agent_os_source_facts(dest, repo="r", revision=REV, observed_at="2026-09-02T00:00:00Z")
    evil_fact = next(f for f in facts.facts if f.path.endswith("WS-EVIL.md"))
    assert evil_fact.status == STATUS_SOURCE_PARTIAL
    assert "escapes repo_root" in evil_fact.reason
    assert evil_fact.payload is None
    # the legitimate target record is unaffected
    ws_fact = next(f for f in facts.facts if f.path.endswith("WS-OPERATION-ASSURANCE.md"))
    assert ws_fact.status == STATUS_OK


def test_r3_gather_real_case_nested_directory_entry_becomes_source_partial(tmp_path) -> None:
    dest = _copy_hostile(tmp_path)
    (dest / "agentos" / "workstreams" / "WS-A-DIRECTORY.md").mkdir()

    facts = gather_agent_os_source_facts(dest, repo="r", revision=REV, observed_at="2026-09-02T00:00:00Z")
    dir_fact = next(f for f in facts.facts if f.path.endswith("WS-A-DIRECTORY.md"))
    assert dir_fact.status == STATUS_SOURCE_PARTIAL
    assert "not a regular file" in dir_fact.reason


def test_r3_gather_real_case_a_true_nested_subdirectory_is_simply_never_matched(tmp_path) -> None:
    # a genuinely nested subdirectory under workstreams/ is excluded by the
    # glob pattern itself (its '*' never crosses '/') -- confirms the
    # one-level closure holds even without needing a refusal path for it.
    dest = _copy_hostile(tmp_path)
    nested_dir = dest / "agentos" / "workstreams" / "nested"
    nested_dir.mkdir()
    (nested_dir / "WS-NESTED.md").write_text("---\nschema: agentos.workstream.v1\n---\n", encoding="utf-8")

    facts = gather_agent_os_source_facts(dest, repo="r", revision=REV, observed_at="2026-09-02T00:00:00Z")
    assert not any("nested" in f.path for f in facts.facts)
