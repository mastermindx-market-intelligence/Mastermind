from __future__ import annotations

import copy

import pytest

from control_plane import ceo_intent, ceo_request
from control_plane.coo_principal_request import (
    BOUNDED_ACTION_KIND,
    CooPrincipalRequestError,
    CooPrincipalRequestInternalError,
    CooPrincipalRequestInvalid,
    INTENT_ID_RE,
    ORCHESTRATION_ACTION_KIND,
    ORCHESTRATION_BUSINESS_IMPACTS,
    ORCHESTRATION_REQUIRED_FIELDS,
    REQUEST_REF_RE,
    normalize_principal_orchestration_request,
    normalize_principal_request,
    orchestration_request_fingerprint,
    orchestration_request_ref,
    principal_intent_id,
    principal_request_fingerprint,
    principal_request_ref,
)


WORK_REF = "WS:EXECUTIVE-CAPACITY-FABRIC"


def research_request(**changes):
    value = {
        "operation_key": "claude-exec-integration",
        "objective": "Inspect the current integration and produce grounded findings.",
        "department": "executive-infrastructure",
        "priority": 7,
        "execution_profile": "research_only",
        "workstream": WORK_REF,
    }
    value.update(changes)
    return value


def code_request(**changes):
    value = {
        "operation_key": "claude-exec-code",
        "objective": "Implement the bounded principal integration slice.",
        "department": "executive-infrastructure",
        "priority": 8,
        "execution_profile": "bounded_code_change",
        "workstream": WORK_REF,
        "allowed_write_paths": ["control_plane/example.py"],
        "validation": {
            "pytest_targets": ["tests/test_example.py"],
            "git_diff_check": True,
        },
    }
    value.update(changes)
    return value


def orchestration_request(**changes):
    value = {
        "operation_key": "claude-exec-integration",
        "objective": "Coordinate a governed two-outcome Executive episode.",
        "department": "executive-infrastructure",
        "priority": 7,
        "workstream": WORK_REF,
        "business_impact": "routine",
    }
    value.update(changes)
    return value


def test_orchestration_request_is_narrow_business_intent_only():
    normalized = normalize_principal_orchestration_request(
        orchestration_request(), expected_work_ref=WORK_REF
    )
    assert set(normalized) == set(ORCHESTRATION_REQUIRED_FIELDS)
    assert normalized == orchestration_request()
    assert "execution_profile" not in normalized
    assert "attempt_limit" not in normalized
    assert "allowed_write_paths" not in normalized
    assert "validation" not in normalized
    assert ORCHESTRATION_BUSINESS_IMPACTS == ceo_intent._V2_BUSINESS_IMPACTS


@pytest.mark.parametrize("impact", ["routine", "material", "critical"])
def test_orchestration_business_impact_matches_existing_v2_contract(impact):
    normalized = normalize_principal_orchestration_request(
        orchestration_request(business_impact=impact),
        expected_work_ref=WORK_REF,
    )
    assert normalized["business_impact"] == impact


@pytest.mark.parametrize(
    "impact",
    ["", "ROUTINE", "high", None, True, 1],
)
def test_orchestration_business_impact_refuses_unreviewed_values(impact):
    with pytest.raises(CooPrincipalRequestInvalid, match="business_impact"):
        normalize_principal_orchestration_request(
            orchestration_request(business_impact=impact),
            expected_work_ref=WORK_REF,
        )


@pytest.mark.parametrize(
    "field",
    [
        "execution_profile",
        "attempt_limit",
        "allowed_write_paths",
        "validation",
        "actor",
        "seat",
        "requested_authorities",
        "authority_level",
        "branch",
        "worktree",
        "provider",
        "model",
        "account",
        "host",
        "realm",
        "root_job_id",
        "children",
        "plan",
        "budget",
        "release_class",
        "dispatch",
        "credential",
        "service",
        "session_id",
    ],
)
def test_orchestration_request_refuses_execution_tree_and_placement_fields(field):
    payload = orchestration_request()
    payload[field] = "caller-value"
    with pytest.raises(CooPrincipalRequestInvalid, match="unexpected field"):
        normalize_principal_orchestration_request(
            payload, expected_work_ref=WORK_REF
        )


def test_orchestration_workstream_is_exact_selected_mission():
    with pytest.raises(CooPrincipalRequestInvalid, match="exact selected Mission Workspace"):
        normalize_principal_orchestration_request(
            orchestration_request(workstream="WS:OTHER"),
            expected_work_ref=WORK_REF,
        )


def test_bounded_and_orchestration_kinds_share_one_logical_operation_identity():
    bounded = normalize_principal_request(
        research_request(), expected_work_ref=WORK_REF
    )
    orchestration = normalize_principal_orchestration_request(
        orchestration_request(), expected_work_ref=WORK_REF
    )
    bounded_ref = principal_request_ref(bounded)
    orchestration_ref = orchestration_request_ref(orchestration)
    assert bounded_ref == orchestration_ref
    assert REQUEST_REF_RE.fullmatch(orchestration_ref)

    # The future sink must therefore see one intent identity for the logical
    # operation; action kind/fingerprint difference is what makes cross-kind
    # reuse a conflict instead of a second durable root.
    assert principal_intent_id(bounded_ref) == principal_intent_id(orchestration_ref)
    assert principal_request_fingerprint(bounded) != orchestration_request_fingerprint(
        orchestration
    )
    assert BOUNDED_ACTION_KIND != ORCHESTRATION_ACTION_KIND


def test_orchestration_semantic_change_preserves_request_ref_but_changes_fingerprint():
    first = normalize_principal_orchestration_request(
        orchestration_request(), expected_work_ref=WORK_REF
    )
    changed = normalize_principal_orchestration_request(
        orchestration_request(
            objective="Coordinate the same logical operation with changed semantics.",
            priority=9,
            business_impact="material",
        ),
        expected_work_ref=WORK_REF,
    )
    assert orchestration_request_ref(first) == orchestration_request_ref(changed)
    assert orchestration_request_fingerprint(first) != orchestration_request_fingerprint(
        changed
    )


def test_orchestration_different_operation_or_workstream_changes_request_ref():
    first = normalize_principal_orchestration_request(
        orchestration_request(), expected_work_ref=WORK_REF
    )
    other_key = normalize_principal_orchestration_request(
        orchestration_request(operation_key="claude-exec-integration-two"),
        expected_work_ref=WORK_REF,
    )
    other_work = normalize_principal_orchestration_request(
        orchestration_request(workstream="WS:OTHER"),
        expected_work_ref="WS:OTHER",
    )
    assert orchestration_request_ref(first) != orchestration_request_ref(other_key)
    assert orchestration_request_ref(first) != orchestration_request_ref(other_work)


def test_reuses_existing_research_normalization_and_requires_workstream():
    normalized = normalize_principal_request(
        research_request(), expected_work_ref=WORK_REF
    )
    assert normalized["execution_profile"] == "research_only"
    assert normalized["workstream"] == WORK_REF
    assert normalized["attempt_limit"] == 2
    assert normalized["allowed_write_paths"] == []
    assert normalized["validation"] == {}

    missing = research_request()
    del missing["workstream"]
    with pytest.raises(CooPrincipalRequestError, match="missing required field"):
        normalize_principal_request(missing, expected_work_ref=WORK_REF)


def test_reuses_existing_bounded_code_profile_without_widening_authority():
    normalized = normalize_principal_request(
        code_request(), expected_work_ref=WORK_REF
    )
    assert normalized["execution_profile"] == "bounded_code_change"
    assert normalized["allowed_write_paths"] == ["control_plane/example.py"]
    assert normalized["validation"]["pytest_targets"] == ["tests/test_example.py"]
    assert normalized["validation"]["git_diff_check"] is True
    assert normalized["attempt_limit"] == 2


@pytest.mark.parametrize(
    "field",
    [
        "actor",
        "seat",
        "requested_authorities",
        "authority_level",
        "branch",
        "worktree",
        "provider",
        "model",
        "account",
        "host",
        "realm",
        "release_class",
        "dispatch",
        "service",
        "credential",
        "session_id",
    ],
)
def test_privileged_caller_fields_are_refused(field):
    payload = research_request()
    payload[field] = "caller-value"
    with pytest.raises(CooPrincipalRequestError, match="unexpected field"):
        normalize_principal_request(payload, expected_work_ref=WORK_REF)


def test_workstream_must_match_selected_mission():
    with pytest.raises(CooPrincipalRequestError, match="exact selected Mission Workspace"):
        normalize_principal_request(
            research_request(workstream="WS:OTHER"),
            expected_work_ref=WORK_REF,
        )


def test_strict_coo_root_attempt_limit_is_one_or_two_only():
    for limit in (1, 2):
        normalized = normalize_principal_request(
            research_request(attempt_limit=limit), expected_work_ref=WORK_REF
        )
        assert normalized["attempt_limit"] == limit

    with pytest.raises(CooPrincipalRequestError, match="between 1 and 2"):
        normalize_principal_request(
            research_request(attempt_limit=3), expected_work_ref=WORK_REF
        )


def test_stable_identity_depends_only_on_work_ref_and_operation_key():
    first = normalize_principal_request(
        research_request(), expected_work_ref=WORK_REF
    )
    changed_semantics = normalize_principal_request(
        research_request(
            objective="A changed objective that must conflict at the sink.",
            priority=9,
        ),
        expected_work_ref=WORK_REF,
    )

    first_ref = principal_request_ref(first)
    second_ref = principal_request_ref(changed_semantics)
    assert first_ref == second_ref
    assert REQUEST_REF_RE.fullmatch(first_ref)
    assert ceo_request.AUTOMATED_REQUEST_REF_RE.fullmatch(first_ref)

    first_intent = principal_intent_id(first_ref)
    second_intent = principal_intent_id(second_ref)
    assert first_intent == second_intent
    assert INTENT_ID_RE.fullmatch(first_intent)
    assert ceo_intent.INTENT_ID_RE.fullmatch(first_intent)


def test_existing_bounded_request_and_intent_identity_vectors_remain_byte_stable():
    normalized = normalize_principal_request(
        research_request(), expected_work_ref=WORK_REF
    )
    request_ref = principal_request_ref(normalized)
    assert request_ref == "req-coo-f28ca5b9a8314c4864d5a291bdcd3ee2"
    assert principal_intent_id(request_ref) == "coo-437296240d71874a477e0c7c6d93e7bb"


def test_same_operation_key_under_different_workstream_is_a_different_request():
    first = normalize_principal_request(
        research_request(), expected_work_ref=WORK_REF
    )
    other = normalize_principal_request(
        research_request(workstream="WS:OTHER"),
        expected_work_ref="WS:OTHER",
    )
    assert principal_request_ref(first) != principal_request_ref(other)


def test_different_operation_key_is_a_different_request():
    first = normalize_principal_request(
        research_request(), expected_work_ref=WORK_REF
    )
    other = normalize_principal_request(
        research_request(operation_key="claude-exec-integration-two"),
        expected_work_ref=WORK_REF,
    )
    assert principal_request_ref(first) != principal_request_ref(other)


def test_identity_helper_refuses_noncanonical_internal_mapping():
    normalized = normalize_principal_request(
        research_request(), expected_work_ref=WORK_REF
    )
    malformed = copy.deepcopy(normalized)
    malformed["attempt_limit"] = 3
    with pytest.raises(CooPrincipalRequestError):
        principal_request_ref(malformed)

    malformed = copy.deepcopy(normalized)
    malformed["operation_key"] = "UPPERCASE"
    with pytest.raises(CooPrincipalRequestError):
        principal_request_ref(malformed)


def test_request_and_intent_namespaces_are_visibly_coo_specific():
    normalized = normalize_principal_request(
        research_request(), expected_work_ref=WORK_REF
    )
    request_ref = principal_request_ref(normalized)
    intent_id = principal_intent_id(request_ref)
    assert request_ref.startswith("req-coo-")
    assert intent_id.startswith("coo-")


def test_identity_does_not_depend_on_token_session_or_clock_fields():
    normalized = normalize_principal_request(
        research_request(), expected_work_ref=WORK_REF
    )
    request_ref = principal_request_ref(normalized)
    for forbidden in ("jti", "expires_at", "session_id", "provider_session_id", "timestamp"):
        mutated = dict(normalized)
        mutated[forbidden] = "not-authorized"
        with pytest.raises(CooPrincipalRequestError):
            principal_request_ref(mutated)
    assert principal_request_ref(normalized) == request_ref


def test_error_boundary_preserves_caller_vs_internal_policy_failure(monkeypatch):
    with pytest.raises(CooPrincipalRequestInvalid) as caller:
        normalize_principal_request(
            research_request(workstream="WS:OTHER"),
            expected_work_ref=WORK_REF,
        )
    assert caller.value.caller_fault is True

    def broken(_payload):
        raise ceo_request.CeoRequestInternalError("internal policy detail must not leak")

    monkeypatch.setattr(ceo_request, "normalize_high_level_request", broken)
    with pytest.raises(CooPrincipalRequestInternalError) as internal:
        normalize_principal_request(
            research_request(),
            expected_work_ref=WORK_REF,
        )
    assert internal.value.caller_fault is False
    assert str(internal.value) == "COO request policy is internally inconsistent"
    assert "internal policy detail" not in str(internal.value)
