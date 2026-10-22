"""Test exact UI/Executive compatibility; no inferred product acceptance."""

import dataclasses
import hashlib
import json

import pytest

from control_plane import ceo_request
from control_plane.mission_acceptance_criteria import (
    AcceptanceCriteriaError,
    SCHEMA,
    SECTION,
    CLOSE,
    parse_acceptance_criteria_candidate,
)


def objective(goal="Implement project chat", *items):
    assert items
    return goal.strip() + SECTION + json.dumps(items, ensure_ascii=False, separators=(",", ":")) + CLOSE


def _automated_request(objective_text):
    return {
        "objective": objective_text,
        "department": "executive-infrastructure",
        "priority": 0,
        "execution_profile": "research_only",
    }


def test_round_trip_exact_frontend_one_line_json_suffix():
    text = objective("Implement project chat", "One message is delivered", "Reopening does not duplicate it")
    candidate = parse_acceptance_criteria_candidate(text)
    assert candidate is not None
    assert candidate.schema == SCHEMA
    assert candidate.state == "UNVERIFIED"
    assert candidate.goal == "Implement project chat"
    assert candidate.objective_sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert [(x.ordinal, x.requirement) for x in candidate.criteria] == [
        (1, "One message is delivered"),
        (2, "Reopening does not duplicate it"),
    ]
    assert all(len(x.criterion_digest) == 64 for x in candidate.criteria)
    assert all(x.criterion_digest != candidate.objective_sha256 for x in candidate.criteria)
    assert dataclasses.is_dataclass(candidate)
    assert "\n" not in text and "\r" not in text


def test_plain_and_unversioned_objectives_are_not_imagined_into_acceptance():
    for text in (
        "Ship project chat", "review acceptance criteria carefully",
        "1. A; 2. B", "Goal: Acceptance criteria (verify against the delivered result): 1. A",
    ):
        assert parse_acceptance_criteria_candidate(text) is None


@pytest.mark.parametrize("modified", [
    SECTION + '["One"]]',  # no goal
    ' Goal' + SECTION + '["One"]]',
    'Goal ' + SECTION + '["One"]]',
    'Goal' + SECTION + '[]]',  # zero criteria
    'Goal' + SECTION + '["A"]',  # missing closing bracket
    'Goal' + SECTION + '["A"]] extra',
    'Goal' + SECTION + '["A"]]]',
    'Goal' + SECTION + '["A","B","C","D","E","F","G"]]',
    'Goal' + SECTION + '["A" ,"B"]]',  # noncanonical whitespace
    'Goal' + SECTION + '["\\u0041"]]',  # noncanonical escaped A
    'Goal' + SECTION + '[1]]',
    'Goal' + SECTION + '[true]]',
    'Goal' + SECTION + '{"1":"A"}]',
    'Goal' + SECTION + '[""]]',
    'Goal' + SECTION + '["Trailing "]]',
    'Goal' + SECTION + '[" A"]]',
    'Goal' + SECTION + '["A"],"extra"]',
    'Goal' + SECTION + 'not json]',
    'Goal' + SECTION + '["A"]]' + SECTION + '["B"]]',
    'Goal' + SECTION + json.dumps(["x" * 501]) + CLOSE,
    'Goal' + SECTION + json.dumps(["😀" * 251], ensure_ascii=False) + CLOSE,
    'Goal' + SECTION + '["Back\\tTab"]]',
    'Goal' + SECTION + '["Back\\nNewline"]]',
    'Goal' + SECTION + '["A"]]' + "\x00",
    'Goal' + SECTION + '["A"]]' + "\n",
    'X' * 3980 + SECTION + '["A"]]',  # over total byte ceiling
    'Goal' + SECTION + json.dumps(["\ud800"]) + CLOSE,
])
def test_malformed_or_ambiguous_criteria_never_silently_become_empty(modified):
    with pytest.raises(AcceptanceCriteriaError):
        parse_acceptance_criteria_candidate(modified)


def test_six_items_and_unicode_round_trip_without_control_bytes():
    values = ["é", "😀", "Proof 3", "Proof 4", "Proof 5", "Proof 6"]
    parsed = parse_acceptance_criteria_candidate(objective("Goal", *values))
    assert parsed is not None and len(parsed.criteria) == 6
    assert len({x.criterion_digest for x in parsed.criteria}) == 6
    assert parse_acceptance_criteria_candidate(objective("Goal", "😀" * 250)) is not None


def test_real_typescript_composer_golden_cross_language_objective_digest():
    # Generated from the actual TypeScript LaunchOrchestrator composer via
    # Vite SSR on the same candidate; not a hand-invented backend payload.
    text = objective(
        "Plan first\u2028Implement second",
        "Message delivered once",
        "Exact reopen verified",
    )
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == (
        "245fcd9c261906827df1785dacf32589d99a1e15eec7117832c87479b76dcdab"
    )
    normalized = ceo_request.normalize_automated_request(_automated_request(text))
    assert normalized["objective"] == text
    candidate = parse_acceptance_criteria_candidate(normalized["objective"])
    assert candidate is not None and candidate.state == "UNVERIFIED"
    assert [x.requirement for x in candidate.criteria] == [
        "Message delivered once", "Exact reopen verified",
    ]


def test_newline_paragraphs_from_browser_use_non_control_unicode_separator():
    text = objective("Plan first\u2028Implement second", "Both phases proven")
    parsed = parse_acceptance_criteria_candidate(text)
    assert parsed is not None
    assert parsed.goal == "Plan first\u2028Implement second"
    assert ceo_request.normalize_automated_request(_automated_request(text))["objective"] == text


def test_modified_requirements_change_objective_and_criterion_digests():
    first = parse_acceptance_criteria_candidate(objective("Goal", "Evidence A"))
    second = parse_acceptance_criteria_candidate(objective("Goal", "Evidence B"))
    assert first and second
    assert first.objective_sha256 != second.objective_sha256
    assert first.criteria[0].criterion_digest != second.criteria[0].criterion_digest
    assert first.state == second.state == "UNVERIFIED"


def test_ingress_preserves_exact_v1_requirements_in_existing_objective():
    text = objective("Ship project chat", "Verify message delivery", "Prove exact reopen recovery")
    normalized = ceo_request.normalize_automated_request(_automated_request(text))
    assert normalized["objective"] == text
    parsed = parse_acceptance_criteria_candidate(normalized["objective"])
    assert parsed is not None and len(parsed.criteria) == 2
    assert parsed.state == "UNVERIFIED"
    assert "acceptance" not in normalized and "operation_key" not in normalized


def test_automated_ingress_refuses_malformed_reserved_section_before_dispatch():
    forged = objective("Goal", "Actual criterion").replace('["Actual criterion"]', '["Actual criterion",10]')
    with pytest.raises(ceo_request.CeoRequestInvalid, match="malformed acceptance-criteria"):
        ceo_request.normalize_automated_request(_automated_request(forged))
    ordinary = "Summarize: Acceptance criteria (verify against the delivered result)"
    assert ceo_request.normalize_automated_request(_automated_request(ordinary))["objective"] == ordinary


def test_v1_legacy_normalizer_remains_unmodified_for_reserved_syntax():
    malformed = "Goal" + SECTION + '["One",1]'
    legacy = {**_automated_request(malformed), "operation_key": "same-key-20261010"}
    # The historical v1 law is unchanged. This additive guard lives in the
    # later automated ingress used by the OS app, never in v1 Slack/MCP.
    old = ceo_request.normalize_high_level_request(legacy)
    assert old["objective"] == malformed
    with pytest.raises(ceo_request.CeoRequestInvalid):
        ceo_request.normalize_automated_request(_automated_request(malformed))


def test_identical_objectives_are_not_mistaken_for_same_job_or_accepted_work():
    text = objective("Goal", "Must be demonstrated")
    first = parse_acceptance_criteria_candidate(text)
    second = parse_acceptance_criteria_candidate(text)
    assert first == second
    assert not hasattr(first, "root_job_id")
    assert not hasattr(first, "review_verdict")
    assert not hasattr(first, "accepted")
