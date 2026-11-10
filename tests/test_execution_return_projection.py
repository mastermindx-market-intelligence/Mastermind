"""mastermind.execution_return/v1 projection tests (DONE_WHEN row 5).

Covers the honest stage ladder (unknown never green), the typed refusals
(missing original binding / missing seal / namespace mismatch), the
acceptance-forgery law (delivery ≠ acceptance), digest determinism, the
fail-closed record validator, and cross-language vocabulary parity against
the committed fixture."""
import json
from pathlib import Path

import pytest

from control_plane.execution_return_projection import (
    CHECK_CONCLUSIONS,
    CHECKS_STATES,
    EXECUTION_RETURN_ACCEPTANCE_STATES,
    EXECUTION_RETURN_DELIVERY_SCHEMA,
    EXECUTION_RETURN_DELIVERY_STATES,
    EXECUTION_RETURN_ERROR_CODES,
    EXECUTION_RETURN_SCHEMA,
    EXECUTION_RETURN_STAGES,
    INSTALLATION_STATES,
    MERGE_STATES,
    REFUSAL_CODE_PATTERN,
    ExecutionReturnProjectionError,
    canonical_record_bytes,
    project_execution_return,
    validate_execution_return,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "integrations" / "mmos" / "fixtures" / "execution_return_v1"

SEALED = "9" * 64
NAMESPACE = "mastermind.control_plane.t3_execution_adapter/v1:hermes-eng-seat-1"


def facts(**over):
    base = {
        "attempt": {
            "attempt_id": "ATT-000042",
            "root_id": "root-wo19-coding-7",
            "idempotency_key": "t3-launch-abc123",
            "authenticated_namespace": NAMESPACE,
            "t3_thread_id": "th_ready_9",
            "t3_run_id": "run-77",
            "seal": {"digest": SEALED},
        },
        "result": {
            "text": "Implemented and tested the roster join. → union-green.",
            "artifact_refs": ["tests/test_roster_join.py", "control_plane/roster_join.py"],
        },
        "github": {
            "branch": None,
            "pr_number": None,
            "pr_url": None,
            "checks": None,
            "merge_state": None,
        },
        "original_requester": {
            "teammate_id": "hermes-engineering",
            "conversation_id": "sess-3f9c2",
            "project_id": "proj-mmos-v1",
            "authenticated_namespace": NAMESPACE,
        },
    }
    base.update(over)
    return base


def refuse(code, fn):
    with pytest.raises(ExecutionReturnProjectionError) as excinfo:
        fn()
    assert excinfo.value.code == code
    return excinfo.value


# --- stage ladder: only what evidence PROVES -------------------------------

@pytest.mark.parametrize(
    ("github", "installation_claimed", "expected_stage", "expected_checks_state"), [
        # no GitHub evidence at all
        ({"branch": None, "pr_number": None, "pr_url": None, "checks": None,
          "merge_state": None}, False, "result_only", "unknown"),
        # branch only
        ({"branch": "t3/execution-return-path", "pr_number": None, "pr_url": None,
          "checks": None, "merge_state": None}, False, "branch_pushed", "unknown"),
        # PR with no check evidence
        ({"branch": "t3/execution-return-path", "pr_number": 2338,
          "pr_url": "https://github.com/acme/Mastermind/pull/2338",
          "checks": None, "merge_state": None}, False, "pr_open", "unknown"),
        # UNKNOWN check evidence never turns green
        ({"branch": "b", "pr_number": 2338, "pr_url": None,
          "checks": [{"name": "ci", "conclusion": "success"},
                     {"name": "typecheck", "conclusion": "unknown"}],
          "merge_state": None}, False, "pr_open", "unknown"),
        # all observed checks concluded success
        ({"branch": "b", "pr_number": 2338, "pr_url": None,
          "checks": [{"name": "ci", "conclusion": "success"},
                     {"name": "typecheck", "conclusion": "success"},
                     {"name": "lint", "conclusion": "skipped"}],
          "merge_state": None}, False, "checks_green", "green"),
        # green but NOT merged — the honest green-but-unmerged stage
        ({"branch": "b", "pr_number": 2338, "pr_url": None,
          "checks": [{"name": "ci", "conclusion": "success"}],
          "merge_state": "not_merged"}, False, "checks_green", "green"),
        # merge UNOBSERVED stays unknown even with green checks
        ({"branch": "b", "pr_number": 2338, "pr_url": None,
          "checks": [{"name": "ci", "conclusion": "success"}],
          "merge_state": "unknown"}, False, "checks_green", "green"),
        # any observed failure
        ({"branch": "b", "pr_number": 2338, "pr_url": None,
          "checks": [{"name": "ci", "conclusion": "success"},
                     {"name": "e2e", "conclusion": "failure"}],
          "merge_state": None}, False, "checks_failed", "failed"),
        # merged, no installation claim
        ({"branch": "b", "pr_number": 2338, "pr_url": None,
          "checks": [{"name": "ci", "conclusion": "success"}],
          "merge_state": "merged"}, False, "merged", "green"),
        # merged + an installation CLAIM stays installed_unknown, never green
        ({"branch": "b", "pr_number": 2338, "pr_url": None,
          "checks": [{"name": "ci", "conclusion": "success"}],
          "merge_state": "merged"}, True, "installed_unknown", "green"),
        # an installation claim WITHOUT a proven merge never claims beyond proof
        ({"branch": None, "pr_number": None, "pr_url": None,
          "checks": None, "merge_state": "unknown"}, True, "result_only", "unknown"),
    ],
)
def test_stage_ladder_is_proven_only(github, installation_claimed, expected_stage,
                                     expected_checks_state):
    record = project_execution_return(facts(
        github=github,
        result={"text": "done", "artifact_refs": [],
                "installation_claimed": installation_claimed},
    ))
    assert record["schema"] == EXECUTION_RETURN_SCHEMA
    assert record["stage"] == expected_stage
    assert record["github"]["checks_state"] == expected_checks_state
    if installation_claimed:
        assert record["github"]["installation"] == "claimed_unproven"
    assert validate_execution_return(record) == record


def test_empty_checks_list_is_not_green():
    record = project_execution_return(facts(github={
        "branch": "b", "pr_number": 5, "pr_url": None, "checks": [],
        "merge_state": None}))
    assert record["stage"] == "pr_open"
    assert record["github"]["checks_state"] == "unknown"


def test_unknown_thread_and_run_ids_stay_null():
    record = project_execution_return(facts(attempt={
        "attempt_id": "ATT-1", "root_id": "r", "idempotency_key": "k",
        "authenticated_namespace": NAMESPACE, "t3_thread_id": None,
        "t3_run_id": None, "seal": {"digest": SEALED},
    }))
    assert record["attempt"]["t3_thread_id"] is None
    assert record["attempt"]["t3_run_id"] is None


# --- typed refusals ---------------------------------------------------------

def test_missing_original_binding_refuses_whole_projection():
    refuse("ORIGINAL_BINDING_MISSING", lambda: project_execution_return(
        facts(original_requester=None)))
    for field in ("teammate_id", "conversation_id", "project_id",
                  "authenticated_namespace"):
        missing = dict(facts()["original_requester"])
        missing[field] = ""
        refuse("ORIGINAL_BINDING_MISSING", lambda m=missing: project_execution_return(
            facts(original_requester=m)))


def test_missing_seal_refuses():
    attempt = dict(facts()["attempt"])
    del attempt["seal"]
    refuse("SEAL_MISSING", lambda: project_execution_return(facts(attempt=attempt)))
    refuse("SEAL_MISSING", lambda: project_execution_return(facts(attempt={
        **attempt, "seal": {"digest": "not-hex"}})))


def test_namespace_mismatch_refuses():
    # Rev 5 law: (authenticated namespace, key) is the idempotency identity —
    # two namespaces are NEVER the same command, so the facts do not join.
    requester = dict(facts()["original_requester"])
    requester["authenticated_namespace"] = NAMESPACE + ":other-oauth-client"
    refuse("NAMESPACE_MISMATCH", lambda: project_execution_return(
        facts(original_requester=requester)))


def test_github_evidence_vocabulary_is_closed():
    refuse("GITHUB_EVIDENCE_INVALID", lambda: project_execution_return(facts(github={
        "branch": "b", "pr_number": 5, "pr_url": None,
        "checks": [{"name": "ci", "conclusion": "pending"}], "merge_state": None})))
    refuse("GITHUB_EVIDENCE_INVALID", lambda: project_execution_return(facts(github={
        "branch": "b", "pr_number": -3, "pr_url": None, "checks": None,
        "merge_state": None})))
    refuse("GITHUB_EVIDENCE_INVALID", lambda: project_execution_return(facts(github={
        "branch": "b", "pr_number": 5, "pr_url": "http://insecure.example/x",
        "checks": None, "merge_state": None})))
    refuse("GITHUB_EVIDENCE_INVALID", lambda: project_execution_return(facts(github={
        "branch": "b", "pr_number": 5, "pr_url": None, "checks": None,
        "merge_state": "probably"})))


def test_malformed_input_shapes_refuse():
    refuse("INPUT_INVALID", lambda: project_execution_return("not-a-dict"))
    refuse("INPUT_INVALID", lambda: project_execution_return(facts(attempt=None)))


# --- delivery ≠ acceptance --------------------------------------------------

def test_acceptance_forgery_is_refused_not_propagated():
    record = project_execution_return(facts(result={
        "text": "done", "artifact_refs": [], "acceptance": "accepted",
    }))
    assert record["acceptance"] == "not_accepted"
    assert record["acceptance_claim_refused"] is True


def test_no_acceptance_claim_projects_quietly():
    record = project_execution_return(facts())
    assert record["acceptance"] == "not_accepted"
    assert record["acceptance_claim_refused"] is False


# --- digest determinism -----------------------------------------------------

def test_digest_is_deterministic_and_change_sensitive():
    first = project_execution_return(facts())
    second = project_execution_return(facts())
    assert first["digest"] == second["digest"]
    assert first["return_id"] == "execret-" + first["digest"][:32]
    changed = project_execution_return(facts(result={
        "text": "different outcome", "artifact_refs": []}))
    assert changed["digest"] != first["digest"]


def test_projection_does_not_alias_input():
    source = facts()
    record = project_execution_return(source)
    source["result"]["artifact_refs"].append("extra.py")
    source["github"]["branch"] = "mutated"
    assert "extra.py" not in record["result"]["artifact_refs"]
    assert record["github"]["branch"] is None


# --- fail-closed record validator -------------------------------------------

def _valid_record():
    return project_execution_return(facts())


def test_validate_roundtrip_returns_deep_copy():
    record = _valid_record()
    copied = validate_execution_return(record)
    assert copied == record
    assert copied is not record
    record["stage"] = "merged"
    assert copied["stage"] != "merged"


def test_validate_refuses_tampering_and_drift():
    refuse("INPUT_INVALID", lambda: validate_execution_return("not-a-dict"))
    tampered = _valid_record()
    tampered["stage"] = "merged"  # evidence does not prove merge
    refuse("INPUT_INVALID", lambda: validate_execution_return(tampered))
    bad_digest = _valid_record()
    bad_digest["digest"] = "0" * 64
    refuse("INPUT_INVALID", lambda: validate_execution_return(bad_digest))
    forged = _valid_record()
    forged["acceptance"] = "accepted"
    refuse("INPUT_INVALID", lambda: validate_execution_return(forged))
    extra = _valid_record()
    extra["installed"] = True
    refuse("INPUT_INVALID", lambda: validate_execution_return(extra))
    bad_stage = _valid_record()
    bad_stage["stage"] = "shipped"
    refuse("INPUT_INVALID", lambda: validate_execution_return(bad_stage))


def test_stage_exceeding_evidence_is_refused_even_with_matching_digest():
    # Re-forge a fully consistent record whose stage outruns its evidence:
    # the digest law alone must not smuggle a stronger stage through.
    record = _valid_record()
    record["stage"] = "checks_green"
    from control_plane.execution_return_projection import _digest_of, _return_id
    digest = _digest_of(record)
    record["digest"] = digest
    record["return_id"] = _return_id(digest)
    refuse("INPUT_INVALID", lambda: validate_execution_return(record))


def test_record_respects_the_native_text_budget():
    # A lawful record fits the seam's 16 KiB text budget with room to spare…
    record = project_execution_return(facts(result={
        "text": "x" * 8192, "artifact_refs": [f"r{i:03d}" + "r" * 508 for i in range(12)]}))
    assert len(canonical_record_bytes(record)) <= 15 * 1024
    # …and a record that would not fit is refused, never silently oversized
    # (the native submit seam would have to truncate or drop it otherwise).
    refuse("INPUT_INVALID", lambda: project_execution_return(facts(result={
        "text": "x" * 8192, "artifact_refs": [f"r{i:03d}" + "r" * 508 for i in range(16)]})))


# --- cross-language vocabulary fixture parity --------------------------------

def test_vocabulary_fixture_matches_the_python_owner():
    fixture = json.loads((FIXTURE_DIR / "vocabularies.json").read_text("utf-8"))
    assert fixture["record_schema"] == EXECUTION_RETURN_SCHEMA
    assert fixture["delivery_receipt_schema"] == EXECUTION_RETURN_DELIVERY_SCHEMA
    assert tuple(fixture["stages"]) == EXECUTION_RETURN_STAGES
    assert tuple(fixture["acceptance_states"]) == EXECUTION_RETURN_ACCEPTANCE_STATES
    assert tuple(fixture["check_conclusions"]) == CHECK_CONCLUSIONS
    assert tuple(fixture["checks_states"]) == CHECKS_STATES
    assert tuple(fixture["merge_states"]) == MERGE_STATES
    assert tuple(fixture["installation_states"]) == INSTALLATION_STATES
    assert tuple(fixture["delivery_states"]) == EXECUTION_RETURN_DELIVERY_STATES
    assert tuple(fixture["error_codes"]) == EXECUTION_RETURN_ERROR_CODES
    assert fixture["refusal_code_pattern"] == REFUSAL_CODE_PATTERN


def test_committed_sample_record_parses_in_python():
    sample = json.loads((FIXTURE_DIR / "sample_record.json").read_text("utf-8"))
    assert validate_execution_return(sample) == sample


def test_every_stage_is_reachable():
    seen = {
        project_execution_return(facts(github=g, result={"text": "t", "artifact_refs": [],
                                                         "installation_claimed": c}))["stage"]
        for g, c in [
            ({"branch": None, "pr_number": None, "pr_url": None, "checks": None, "merge_state": None}, False),
            ({"branch": "b", "pr_number": None, "pr_url": None, "checks": None, "merge_state": None}, False),
            ({"branch": "b", "pr_number": 1, "pr_url": None, "checks": None, "merge_state": None}, False),
            ({"branch": "b", "pr_number": 1, "pr_url": None,
              "checks": [{"name": "ci", "conclusion": "success"}], "merge_state": None}, False),
            ({"branch": "b", "pr_number": 1, "pr_url": None,
              "checks": [{"name": "ci", "conclusion": "failure"}], "merge_state": None}, False),
            ({"branch": "b", "pr_number": 1, "pr_url": None,
              "checks": [{"name": "ci", "conclusion": "success"}], "merge_state": "merged"}, False),
            ({"branch": "b", "pr_number": 1, "pr_url": None,
              "checks": [{"name": "ci", "conclusion": "success"}], "merge_state": "merged"}, True),
        ]
    }
    assert seen == set(EXECUTION_RETURN_STAGES)
