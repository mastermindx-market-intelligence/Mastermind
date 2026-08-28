"""OCR-3 Task 1 — closed continuation draft/capsule/ACK contract freeze.

Proves the idempotency amendment's contract split: a semantic draft that cannot
author preparation identity, a finalized capsule whose id content-addresses its
own bytes, and an ACK bound to the exact capsule and provider session.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from control_plane.operator_continuation import (
    ACK_FIELDS,
    ATTEMPT_ID_RE,
    CONTINUATION_KEYS,
    CONTINUATION_ONLY_FIELDS,
    DIGEST_RE,
    DRAFT_FIELDS,
    FORBIDDEN_DRAFT_FIELDS,
    FORBIDDEN_KEY_MARKERS,
    GENERATED_AT_RE,
    GIT_OBJECT_ID_RE,
    JOB_ID_RE,
    MAX_KNOWN_UNKNOWNS,
    MAX_MAPPING_DEPTH,
    MAX_MAPPING_KEYS,
    MAX_REFS,
    MAX_SOURCE_REVISIONS,
    OPERATION_KEY_RE,
    OPERATOR_CONTINUATION_ACK_SCHEMA,
    OPERATOR_CONTINUATION_SCHEMA,
    PROVIDER_SESSION_ID_RE,
    SEATS,
    SECRET_VALUE_MARKERS,
    SESSION_ALIAS_RE,
    ContinuationAck,
    OperatorContinuation,
    OperatorContinuationDraft,
    OperatorContinuationError,
    canonical_bytes,
    finalize_continuation,
    semantic_draft_digest,
    validate_continuation,
    validate_continuation_ack,
)


MODULE_PATH = (
    Path(__file__).resolve().parent.parent / "control_plane" / "operator_continuation.py"
)

SOURCE_ATTEMPT = "ATT-0123456789abcdef0123456789abcdef"
TARGET_ATTEMPT = "ATT-fedcba98765432100123456789abcdef"
GRANT_DIGEST = "a" * 64
PICKUP_SHA = "e2092cb6235519ac7f50fb3aa50ec1c1a6f627c0"
MERGE_SHA = "b901dee0272a99b8a1d60385848b99b7273e8261"
GENERATED_AT = "2026-08-28T04:05:06.789Z"
PROVIDER_SESSION = "provider-session-opaque"


def draft_wire(**overrides: Any) -> dict[str, Any]:
    """The canonical valid draft wire, before any override."""

    wire: dict[str, Any] = {
        "root_job_id": "JOB-001",
        "job_id": "JOB-002",
        "source_attempt_id": SOURCE_ATTEMPT,
        "target_attempt_id": TARGET_ATTEMPT,
        "operation_key": "operator-continuity-ocr3-task1-20260828-sol-001",
        "target_seat": "coo",
        "session_alias": "SOL-EXEC",
        "effective_grant_digest": GRANT_DIGEST,
        "source_authority_refs": [
            "docs/superpowers/plans/2026-08-27-operator-continuity-ocr3-continuation-binding.md",
            "docs/superpowers/specs/2026-08-27-operator-continuation-idempotency-amendment.md",
        ],
        "agentos_refs": ["WS:EXECUTIVE-CAPACITY-FABRIC"],
        "github_state": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "pull_request": 181,
            "head_sha": MERGE_SHA,
        },
        "prior_attempt_receipt": {
            "attempt_id": SOURCE_ATTEMPT,
            "status": "RATE_LIMITED",
            "terminal": True,
        },
        "checkpoint": {"stage": "plan_frozen", "step": 3},
        "slack_dialogue_ref": {"channel_id": "C0BSBM78V1N", "thread_ts": "1787894596.254059"},
        "accepted_ruling_refs": ["DEC:SOL-HOLD-IS-A-MERGE-BARRIER"],
        "next_action": "Hold for Sol acceptance of the Task 1 contract layer.",
        "known_unknowns": ["Executive Event payload ceiling is not asserted by this wave."],
        "source_revisions": {"Mastermind": PICKUP_SHA},
    }
    wire.update(overrides)
    return wire


def build_draft(**overrides: Any) -> OperatorContinuationDraft:
    return OperatorContinuationDraft.from_dict(draft_wire(**overrides))


# ---------------------------------------------------------------------------
# Step 1 — closed draft / finalized shapes
# ---------------------------------------------------------------------------


def test_draft_semantic_fields_are_exactly_the_frozen_eighteen() -> None:
    assert DRAFT_FIELDS == (
        "root_job_id",
        "job_id",
        "source_attempt_id",
        "target_attempt_id",
        "operation_key",
        "target_seat",
        "session_alias",
        "effective_grant_digest",
        "source_authority_refs",
        "agentos_refs",
        "github_state",
        "prior_attempt_receipt",
        "checkpoint",
        "slack_dialogue_ref",
        "accepted_ruling_refs",
        "next_action",
        "known_unknowns",
        "source_revisions",
    )
    declared = tuple(f.name for f in dataclasses.fields(OperatorContinuationDraft))
    assert declared == DRAFT_FIELDS
    assert set(build_draft().to_dict()) == set(DRAFT_FIELDS)


def test_finalized_wire_adds_only_schema_generated_at_and_capsule_id() -> None:
    draft = build_draft()
    capsule = finalize_continuation(draft, generated_at=GENERATED_AT)
    wire = capsule.to_dict()

    assert set(wire) - set(DRAFT_FIELDS) == set(CONTINUATION_ONLY_FIELDS)
    assert set(wire) == CONTINUATION_KEYS
    assert wire["schema"] == OPERATOR_CONTINUATION_SCHEMA == "mastermind.operator_continuation.v1"
    for field in DRAFT_FIELDS:
        assert wire[field] == draft.to_dict()[field]


@pytest.mark.parametrize("field", sorted(FORBIDDEN_DRAFT_FIELDS))
def test_draft_refuses_preparation_identity_fields(field: str) -> None:
    supplied = {
        "schema": OPERATOR_CONTINUATION_SCHEMA,
        "generated_at": GENERATED_AT,
        "capsule_id": "b" * 64,
    }[field]
    with pytest.raises(OperatorContinuationError, match="must not author"):
        OperatorContinuationDraft.from_dict({**draft_wire(), field: supplied})


def test_forbidden_draft_fields_are_exactly_the_finalized_additions() -> None:
    assert FORBIDDEN_DRAFT_FIELDS == frozenset(CONTINUATION_ONLY_FIELDS)


def test_draft_refuses_unknown_and_missing_fields() -> None:
    with pytest.raises(OperatorContinuationError, match="unknown="):
        OperatorContinuationDraft.from_dict({**draft_wire(), "extra": "x"})

    partial = draft_wire()
    partial.pop("next_action")
    with pytest.raises(OperatorContinuationError, match="missing="):
        OperatorContinuationDraft.from_dict(partial)


def test_draft_refuses_a_non_object_wire() -> None:
    with pytest.raises(OperatorContinuationError, match="must be an object"):
        OperatorContinuationDraft.from_dict(["root_job_id"])


@pytest.mark.parametrize(
    "key",
    ["provider_session_id", "native_session_id", "native_handle", "account_label"],
)
def test_draft_refuses_provider_account_and_native_session_authority(key: str) -> None:
    with pytest.raises(OperatorContinuationError, match="provider/credential authority"):
        build_draft(github_state={"repository": "acme/repo", key: "sess-1"})


def test_forbidden_key_markers_cover_the_named_families() -> None:
    for marker in ("provider_session_id", "native_session_id", "account_label", "credential"):
        assert marker in FORBIDDEN_KEY_MARKERS


def credential_shaped(prefix: str, body: str) -> str:
    """Assemble a credential-SHAPED fixture at run time.

    These are fabricated, not real, but GitHub push protection scans source
    text rather than intent: a literal token shape in this file blocks the
    push for the very test that proves the contract rejects it.  Splitting the
    prefix from the body keeps the assertion honest and the file pushable.
    """

    return prefix + body


SECRET_SHAPED_LEAVES: tuple[str, ...] = (
    credential_shaped("ghp" + "_", "16C7e42F292c6912E7710c838347Ae178B4a"),
    credential_shaped("sk-" + "ant-", "api03-AAAAAAAABBBBBBBBCCCCCCCC"),
    credential_shaped("xox" + "b-", "1234567890-abcdefghijklmnop"),
    credential_shaped("", "dGhpc2lzYW5vcGFxdWVzZWNyZXR2YWx1ZTEyMzQ1"),
)


@pytest.mark.parametrize("leaf", SECRET_SHAPED_LEAVES)
def test_draft_refuses_secret_shaped_leaves(leaf: str) -> None:
    with pytest.raises(OperatorContinuationError):
        build_draft(github_state={"repository": "acme/repo", "note": leaf})


@pytest.mark.parametrize("marker", SECRET_VALUE_MARKERS)
def test_nested_leaves_refuse_the_existing_secret_word_family(marker: str) -> None:
    with pytest.raises(OperatorContinuationError, match="secret-shaped material"):
        build_draft(prior_attempt_receipt={"status": f"failed: provider {marker} rejected"})


def test_secret_word_family_mirrors_the_operator_harness_contract_family() -> None:
    # control_plane/operator_harness_contract.py AuthRealmFact.__post_init__
    assert SECRET_VALUE_MARKERS == ("token", "refresh", "secret", "auth.json", "credential")


def test_top_level_citations_may_name_a_credential_boundary_ruling() -> None:
    """Citing a credential ruling is lawful; carrying a credential is not."""

    draft = build_draft(agentos_refs=["DEC:CRED0-CREDENTIAL-BOUNDARY", "WS:OPERATOR-CONTINUITY"])
    assert "DEC:CRED0-CREDENTIAL-BOUNDARY" in draft.agentos_refs

    with pytest.raises(OperatorContinuationError, match="credential-prefixed"):
        build_draft(agentos_refs=[SECRET_SHAPED_LEAVES[0]])


def test_draft_citations_survive_their_own_source_paths() -> None:
    """The long-run rule must not reject a draft for citing its own plan."""

    draft = build_draft()
    assert any("idempotency-amendment" in ref for ref in draft.source_authority_refs)


# ---------------------------------------------------------------------------
# Step 3 — canonical validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("root_job_id", "JOB-01"),
        ("root_job_id", "job-001"),
        ("job_id", "JOB-"),
        ("source_attempt_id", "ATT-target"),
        ("source_attempt_id", "ATT-" + "A" * 32),
        ("target_attempt_id", "ATT-0123456789abcdef"),
        ("operation_key", "Operator-Continuity"),
        ("operation_key", "ab"),
        ("operation_key", "a" * 97),
        ("target_seat", "operator"),
        ("session_alias", "sol-exec"),
        ("session_alias", "SOLEXEC"),
        ("effective_grant_digest", "A" * 64),
        ("effective_grant_digest", "a" * 40),
        ("next_action", ""),
        ("next_action", " leading space"),
        ("next_action", "line\nbreak"),
        ("next_action", "x" * 513),
    ],
)
def test_draft_refuses_out_of_form_scalars(field: str, value: Any) -> None:
    with pytest.raises(OperatorContinuationError):
        build_draft(**{field: value})


def test_draft_refuses_identical_source_and_target_attempts() -> None:
    with pytest.raises(OperatorContinuationError, match="must differ"):
        build_draft(source_attempt_id=TARGET_ATTEMPT)


def test_attempt_ids_use_the_minted_runtime_form() -> None:
    assert ATTEMPT_ID_RE.fullmatch(SOURCE_ATTEMPT)
    # control_plane/executive_runtime.py mints f"ATT-{uuid4().hex}"
    assert ATTEMPT_ID_RE.fullmatch("ATT-" + "0" * 32)
    assert ATTEMPT_ID_RE.fullmatch("ATT-target") is None


@pytest.mark.parametrize(
    "refs",
    [
        ["docs/a.md", "docs/a.md"],
        ["docs/a.md", "docs/b.md", "docs/a.md"],
    ],
)
def test_draft_refuses_repeated_refs(refs: list[str]) -> None:
    with pytest.raises(OperatorContinuationError, match="repeats"):
        build_draft(source_authority_refs=refs)


def test_draft_bounds_ref_and_known_unknown_counts() -> None:
    with pytest.raises(OperatorContinuationError, match=f"exceeds {MAX_REFS} entries"):
        build_draft(agentos_refs=[f"WS:KEY-{index}" for index in range(MAX_REFS + 1)])

    with pytest.raises(
        OperatorContinuationError, match=f"exceeds {MAX_KNOWN_UNKNOWNS} entries"
    ):
        build_draft(known_unknowns=[f"gap {index}" for index in range(MAX_KNOWN_UNKNOWNS + 1)])


def test_draft_refuses_a_string_where_a_ref_sequence_is_required() -> None:
    with pytest.raises(OperatorContinuationError, match="must be a sequence"):
        build_draft(agentos_refs="WS:EXECUTIVE-CAPACITY-FABRIC")


@pytest.mark.parametrize(
    "control",
    ["ref\x00null", "ref\x1fescape", "ref\x7fdelete"],
)
def test_draft_refuses_control_characters_in_refs(control: str) -> None:
    with pytest.raises(OperatorContinuationError, match="unsupported form"):
        build_draft(agentos_refs=[control])


def test_draft_refuses_control_characters_in_nested_leaves() -> None:
    with pytest.raises(OperatorContinuationError, match="control characters"):
        build_draft(checkpoint={"stage": "plan\x00frozen"})


@pytest.mark.parametrize(
    "revisions",
    [
        {},
        {"Mastermind": PICKUP_SHA[:12]},
        {"Mastermind": PICKUP_SHA.upper()},
        {"Mastermind": 1},
        {"Master mind": PICKUP_SHA},
    ],
)
def test_draft_refuses_malformed_source_revisions(revisions: dict[str, Any]) -> None:
    with pytest.raises(OperatorContinuationError):
        build_draft(source_revisions=revisions)


def test_source_revisions_accept_full_sha1_and_sha256_object_ids() -> None:
    draft = build_draft(source_revisions={"Mastermind": PICKUP_SHA, "macro": "c" * 64})
    assert draft.source_revisions["macro"] == "c" * 64
    assert GIT_OBJECT_ID_RE.fullmatch(PICKUP_SHA)
    assert GIT_OBJECT_ID_RE.fullmatch(PICKUP_SHA[:39]) is None


def test_draft_bounds_source_revision_count() -> None:
    revisions = {f"repo{index}": PICKUP_SHA for index in range(MAX_SOURCE_REVISIONS + 1)}
    with pytest.raises(OperatorContinuationError, match=f"exceeds {MAX_SOURCE_REVISIONS}"):
        build_draft(source_revisions=revisions)


def test_draft_refuses_float_leaves() -> None:
    with pytest.raises(OperatorContinuationError, match="unsupported JSON type float"):
        build_draft(checkpoint={"progress": 0.5})


def test_draft_refuses_out_of_range_integers() -> None:
    with pytest.raises(OperatorContinuationError, match="outside the exact range"):
        build_draft(checkpoint={"count": 2**53})


def test_draft_bounds_nested_mapping_width_and_depth() -> None:
    wide = {f"k{index}": index for index in range(MAX_MAPPING_KEYS + 1)}
    with pytest.raises(OperatorContinuationError, match=f"exceeds {MAX_MAPPING_KEYS} keys"):
        build_draft(checkpoint=wide)

    deep: Any = "leaf"
    for _ in range(MAX_MAPPING_DEPTH + 1):
        deep = {"nested": deep}
    with pytest.raises(OperatorContinuationError, match="nests deeper"):
        build_draft(checkpoint=deep)


def test_draft_refuses_unsupported_nested_keys() -> None:
    with pytest.raises(OperatorContinuationError, match="unsupported key"):
        build_draft(checkpoint={"Stage": "plan_frozen"})


def test_nullable_fields_accept_none_and_required_mappings_do_not() -> None:
    draft = build_draft(checkpoint=None, slack_dialogue_ref=None)
    assert draft.checkpoint is None
    assert draft.slack_dialogue_ref is None
    assert draft.to_dict()["checkpoint"] is None

    with pytest.raises(OperatorContinuationError, match="github_state must be an object"):
        build_draft(github_state=None)


def test_to_dict_does_not_alias_nested_state() -> None:
    draft = build_draft()
    wire = draft.to_dict()
    wire["github_state"]["pull_request"] = 999
    assert draft.github_state["pull_request"] == 181


# ---------------------------------------------------------------------------
# Step 3 — semantic digest
# ---------------------------------------------------------------------------


def test_semantic_digest_is_sha256_over_canonical_draft_json() -> None:
    draft = build_draft()
    expected = hashlib.sha256(canonical_bytes(draft.to_dict())).hexdigest()
    assert semantic_draft_digest(draft) == expected
    assert DIGEST_RE.fullmatch(semantic_draft_digest(draft))


def test_semantic_digest_is_stable_across_key_order() -> None:
    wire = draft_wire()
    shuffled = {key: wire[key] for key in reversed(list(wire))}
    assert semantic_draft_digest(
        OperatorContinuationDraft.from_dict(wire)
    ) == semantic_draft_digest(OperatorContinuationDraft.from_dict(shuffled))


#: One materially different value per semantic field.  Every entry must move
#: the semantic digest, and the set must cover DRAFT_FIELDS exactly.
SEMANTIC_MUTATIONS: tuple[tuple[str, Any], ...] = (
    ("root_job_id", "JOB-777"),
    ("job_id", "JOB-778"),
    ("source_attempt_id", "ATT-" + "1" * 32),
    ("target_attempt_id", "ATT-" + "2" * 32),
    ("operation_key", "operator-continuity-ocr3-task1-20260828-sol-002"),
    ("target_seat", "ceo"),
    ("session_alias", "SOL-EXEC2"),
    ("effective_grant_digest", "d" * 64),
    ("source_authority_refs", ["docs/other.md"]),
    ("agentos_refs", ["WS:OTHER"]),
    ("github_state", {"repository": "acme/repo"}),
    ("prior_attempt_receipt", {"status": "LOST"}),
    ("checkpoint", None),
    ("slack_dialogue_ref", None),
    ("accepted_ruling_refs", []),
    ("next_action", "Different next action."),
    ("known_unknowns", []),
    ("source_revisions", {"Mastermind": MERGE_SHA}),
)


@pytest.mark.parametrize(("field", "value"), SEMANTIC_MUTATIONS)
def test_every_semantic_field_change_changes_the_semantic_digest(
    field: str, value: Any
) -> None:
    baseline = semantic_draft_digest(build_draft())
    assert semantic_draft_digest(build_draft(**{field: value})) != baseline


def test_semantic_digest_coverage_is_exactly_the_declared_fields() -> None:
    assert {field for field, _ in SEMANTIC_MUTATIONS} == set(DRAFT_FIELDS)


def test_semantic_digest_refuses_a_non_draft() -> None:
    with pytest.raises(OperatorContinuationError, match="OperatorContinuationDraft"):
        semantic_draft_digest(draft_wire())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Step 4 — trusted finalization
# ---------------------------------------------------------------------------


def test_same_draft_and_same_executive_instant_give_identical_bytes_and_id() -> None:
    first = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    second = finalize_continuation(build_draft(), generated_at=GENERATED_AT)

    assert first.capsule_id == second.capsule_id
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first == second


def test_capsule_id_is_sha256_over_the_capsule_excluding_only_capsule_id() -> None:
    draft = build_draft()
    capsule = finalize_continuation(draft, generated_at=GENERATED_AT)

    without_id = {
        "schema": OPERATOR_CONTINUATION_SCHEMA,
        **draft.to_dict(),
        "generated_at": GENERATED_AT,
    }
    assert capsule.capsule_id == hashlib.sha256(canonical_bytes(without_id)).hexdigest()
    assert set(capsule.to_dict()) - set(without_id) == {"capsule_id"}


def test_generated_at_participates_in_the_capsule_id_but_not_the_semantic_digest() -> None:
    draft = build_draft()
    early = finalize_continuation(draft, generated_at=GENERATED_AT)
    late = finalize_continuation(draft, generated_at="2026-08-28T04:05:06.790Z")

    assert early.capsule_id != late.capsule_id
    assert early.semantic_digest == late.semantic_digest == semantic_draft_digest(draft)


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-08-28T04:05:06Z",
        "2026-08-28T04:05:06.789+00:00",
        "2026-08-28T04:05:06.789012Z",
        "2026-08-28 04:05:06.789Z",
        "2026-13-28T04:05:06.789Z",
        "2026-08-28T24:05:06.789Z",
        "2026-08-00T04:05:06.789Z",
        "",
        None,
    ],
)
def test_finalization_refuses_non_canonical_utc(stamp: Any) -> None:
    with pytest.raises(OperatorContinuationError, match="generated_at"):
        finalize_continuation(build_draft(), generated_at=stamp)


def test_generated_at_pattern_accepts_exactly_one_spelling_per_instant() -> None:
    assert GENERATED_AT_RE.fullmatch(GENERATED_AT)
    assert GENERATED_AT_RE.fullmatch("2026-08-28T04:05:06Z") is None
    assert GENERATED_AT_RE.fullmatch("2026-08-28T04:05:06.789+00:00") is None


def test_finalization_refuses_a_non_draft() -> None:
    with pytest.raises(OperatorContinuationError, match="OperatorContinuationDraft"):
        finalize_continuation(draft_wire(), generated_at=GENERATED_AT)  # type: ignore[arg-type]


def test_capsule_round_trips_through_its_wire() -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    reloaded = validate_continuation(json.loads(capsule.canonical_bytes()))

    assert reloaded == capsule
    assert reloaded.canonical_bytes() == capsule.canonical_bytes()
    assert reloaded.target_attempt_id == TARGET_ATTEMPT
    assert reloaded.source_attempt_id == SOURCE_ATTEMPT


def test_capsule_refuses_a_tampered_body() -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    wire = capsule.to_dict()
    wire["next_action"] = "Do something else entirely."

    with pytest.raises(OperatorContinuationError, match="does not content-address"):
        validate_continuation(wire)


def test_capsule_refuses_a_tampered_generated_at() -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    wire = {**capsule.to_dict(), "generated_at": "2026-08-28T04:05:06.790Z"}

    with pytest.raises(OperatorContinuationError, match="does not content-address"):
        validate_continuation(wire)


def test_capsule_refuses_a_foreign_capsule_id() -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    with pytest.raises(OperatorContinuationError, match="does not content-address"):
        validate_continuation({**capsule.to_dict(), "capsule_id": "f" * 64})


@pytest.mark.parametrize("mutation", ["unknown", "missing", "schema"])
def test_capsule_refuses_wire_drift(mutation: str) -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    wire = capsule.to_dict()
    if mutation == "unknown":
        wire["provider_session_id"] = PROVIDER_SESSION
        match = "unknown="
    elif mutation == "missing":
        wire.pop("known_unknowns")
        match = "missing="
    else:
        wire["schema"] = "mastermind.operator_continuation.v2"
        match = "unsupported continuation schema"

    with pytest.raises(OperatorContinuationError, match=match):
        validate_continuation(wire)


def test_validate_continuation_checks_the_supplied_semantic_draft() -> None:
    draft = build_draft()
    capsule = finalize_continuation(draft, generated_at=GENERATED_AT)

    assert validate_continuation(capsule, draft=draft) is capsule

    with pytest.raises(OperatorContinuationError, match="semantic digest"):
        validate_continuation(capsule, draft=build_draft(next_action="Something else."))


def test_finalized_capsule_stays_within_the_declared_event_payload_bound() -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    assert len(capsule.canonical_bytes()) <= 16384

    # Filler is hyphenated so it stays under the high-entropy-run rule and the
    # size bound is what refuses, not the secret-shape rule.
    filler = ("gap-" * 130)[:500]
    oversized = build_draft(
        known_unknowns=[f"{index:03d}-{filler}" for index in range(MAX_KNOWN_UNKNOWNS)],
        source_authority_refs=[f"docs/{index:03d}-{filler[:240]}" for index in range(MAX_REFS)],
        accepted_ruling_refs=[f"DEC-{index:03d}-{filler[:240]}" for index in range(MAX_REFS)],
    )
    with pytest.raises(OperatorContinuationError, match="canonical bytes"):
        finalize_continuation(oversized, generated_at=GENERATED_AT)


# ---------------------------------------------------------------------------
# Step 5 — closed ACK
# ---------------------------------------------------------------------------


def ack_wire(capsule: OperatorContinuation, **overrides: Any) -> dict[str, Any]:
    wire: dict[str, Any] = {
        "schema": OPERATOR_CONTINUATION_ACK_SCHEMA,
        "target_attempt_id": capsule.target_attempt_id,
        "capsule_id": capsule.capsule_id,
        "provider_session_id": PROVIDER_SESSION,
        "accepted": True,
    }
    wire.update(overrides)
    return wire


def test_ack_wire_is_exactly_five_fields() -> None:
    assert ACK_FIELDS == (
        "schema",
        "target_attempt_id",
        "capsule_id",
        "provider_session_id",
        "accepted",
    )
    assert OPERATOR_CONTINUATION_ACK_SCHEMA == "mastermind.operator_continuation_ack.v1"


def test_ack_binds_the_exact_capsule_and_provider_session() -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    ack = validate_continuation_ack(
        ack_wire(capsule), capsule=capsule, provider_session_id=PROVIDER_SESSION
    )

    assert isinstance(ack, ContinuationAck)
    assert ack.to_dict() == ack_wire(capsule)
    assert ack.accepted is True


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"target_attempt_id": "ATT-" + "9" * 32}, "target Attempt"),
        ({"capsule_id": "e" * 64}, "prepared capsule"),
        ({"provider_session_id": "other-session"}, "bound provider session"),
    ],
)
def test_ack_refuses_a_wrong_binding(override: dict[str, Any], match: str) -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    with pytest.raises(OperatorContinuationError, match=match):
        validate_continuation_ack(
            ack_wire(capsule, **override),
            capsule=capsule,
            provider_session_id=PROVIDER_SESSION,
        )


@pytest.mark.parametrize(
    "override",
    [
        {"accepted": False},
        {"accepted": "true"},
        {"accepted": 1},
        {"accepted": None},
    ],
)
def test_ack_refuses_anything_but_accepted_true(override: dict[str, Any]) -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    with pytest.raises(OperatorContinuationError, match="accepted=true"):
        validate_continuation_ack(ack_wire(capsule, **override))


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"target_attempt_id": ""}, "target_attempt_id"),
        ({"target_attempt_id": "ATT-target"}, "target_attempt_id"),
        ({"capsule_id": ""}, "capsule_id"),
        ({"capsule_id": "E" * 64}, "capsule_id"),
        ({"provider_session_id": ""}, "provider_session_id"),
        ({"provider_session_id": "bad session"}, "provider_session_id"),
        ({"schema": "mastermind.operator_continuation_ack.v2"}, "unsupported continuation ack"),
    ],
)
def test_ack_refuses_blank_or_malformed_fields(
    override: dict[str, Any], match: str
) -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    with pytest.raises(OperatorContinuationError, match=match):
        validate_continuation_ack(ack_wire(capsule, **override))


def test_ack_refuses_unknown_and_missing_fields() -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)

    with pytest.raises(OperatorContinuationError, match="unknown="):
        validate_continuation_ack({**ack_wire(capsule), "semantic_digest": "x"})

    partial = ack_wire(capsule)
    partial.pop("provider_session_id")
    with pytest.raises(OperatorContinuationError, match="missing="):
        validate_continuation_ack(partial)


def test_ack_validation_without_expectations_still_closes_the_wire() -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    ack = validate_continuation_ack(ack_wire(capsule))
    assert ack.capsule_id == capsule.capsule_id


def test_ack_refuses_an_expectation_that_is_not_a_capsule() -> None:
    capsule = finalize_continuation(build_draft(), generated_at=GENERATED_AT)
    with pytest.raises(OperatorContinuationError, match="must be an OperatorContinuation"):
        validate_continuation_ack(ack_wire(capsule), capsule=capsule.to_dict())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# mirrored patterns and production inertness
# ---------------------------------------------------------------------------


def test_identifier_patterns_stay_equal_to_their_canonical_owners() -> None:
    from control_plane import ceo_request, executive_orchestration_principal, wake_events
    from control_plane import session_targets

    assert JOB_ID_RE.pattern == wake_events.JOB_ID_RE.pattern
    assert ATTEMPT_ID_RE.pattern == wake_events.ATTEMPT_ID_RE.pattern
    assert SEATS == wake_events.SEATS
    assert SESSION_ALIAS_RE.pattern == session_targets.SESSION_ALIAS_RE.pattern
    assert OPERATION_KEY_RE.pattern == ceo_request._OPERATION_KEY_RE.pattern
    assert (
        PROVIDER_SESSION_ID_RE.pattern
        == executive_orchestration_principal._ID_RE.pattern
    )


def module_identifiers() -> set[str]:
    """Every name the module's CODE reaches, ignoring prose and comments."""

    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def test_module_imports_only_the_standard_library() -> None:
    """The contract layer must not couple to Runtime, Wake or session targets."""

    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative imports"
            modules.add((node.module or "").split(".")[0])

    assert modules == {
        "__future__",
        "collections",
        "copy",
        "dataclasses",
        "hashlib",
        "json",
        "re",
        "typing",
    }
    assert not any(module.startswith("control_plane") for module in modules)


@pytest.mark.parametrize(
    "forbidden",
    [
        "sqlite3",
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "random",
        "uuid",
        "uuid4",
        "environ",
        "open",
        "Path",
    ],
)
def test_module_reaches_no_side_effecting_surface(forbidden: str) -> None:
    assert forbidden not in module_identifiers()


@pytest.mark.parametrize(
    "clock", ["datetime", "time", "now_ms", "utcnow", "monotonic", "now", "today"]
)
def test_module_reads_no_clock(clock: str) -> None:
    """generated_at is Executive-minted; this module may never mint one."""

    assert clock not in module_identifiers()
