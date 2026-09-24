from __future__ import annotations

import json

import pytest

from brain import improvement_cognition as C


DIGEST = "sha256:" + "a" * 64


def report():
    return {
        "digest": DIGEST,
        "execution_authority_granted": False,
        "jobs_created": 0,
        "independent_discovery_proven": False,
        "opportunities": [{
            "id": "opportunity:" + "b" * 24,
            "diagnosis": "EVIDENCED_GAP",
            "disposition": "REVIEW_AND_DUPLICATE_CHECK",
            "source_refs": ["nw-coverage-contract", "nw-reflection-snapshot"],
            "next_evidence": "Compare reuse with a bounded coverage investigation.",
            "expectation": {
                "user_job": "Understand the context for monitored subjects.",
                "consumer": "Neural Web context reader",
                "requirement": "Disclose coverage and missingness without claiming semantic quality.",
            },
        }],
        "hypotheses": [{
            "kind": "REUSE_OR_CONNECT",
            "question": "Does useful context already exist behind another accepted owner?",
            "discriminating_check": "Check the accepted context owner before commissioning research.",
            "falsifier": "No accepted owner exposes the needed context for the same subject.",
        }],
    }


def response(*, action="READ_ONLY_RESEARCH", evidence=None):
    return {
        "schema": C.DRAFT_SCHEMA,
        "evidence_digest": DIGEST,
        "proposals": [{
            "proposal_id": "PROP.REUSE.001",
            "problem": "The consumer may not expose context that already exists.",
            "mechanism": "An existing owner may hold reusable context behind a disconnected seam.",
            "delta": "Connect existing context before creating new research.",
            "evidence_ids": evidence or ["nw-coverage-contract", "nw-reflection-snapshot"],
            "unknowns": ["Whether another accepted owner already covers the same subject."],
            "falsifiers": ["No accepted source exposes useful context for this subject."],
            "investigation_questions": ["Which current owner can answer the missing context question?"],
            "next_action": action,
        }],
    }


def test_draft_uses_one_no_tools_no_log_turn_and_keeps_advisory_boundary():
    calls = []

    def reasoner(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return {
            "ok": True,
            "text": json.dumps(response()),
            "tools_used": [],
            "backend": "fake",
            "provider": "fake-provider",
            "model": "fake-model",
        }

    draft = C._draft_with_reasoner(report(), reasoner=reasoner)

    assert len(calls) == 1
    prompt, kwargs = calls[0]
    assert "target_answer_disclosed" in prompt
    assert kwargs["arm"] is False
    assert kwargs["allowed_tools"] == []
    assert kwargs["add_dirs"] == []
    assert kwargs["max_turns"] == 1
    assert kwargs["log_run"] is False
    assert draft["execution_authority_granted"] is False
    assert draft["ranking_authority_granted"] is False
    assert draft["self_evaluation_accepted"] is False
    assert draft["proposals"][0]["next_action"] == "READ_ONLY_RESEARCH"


@pytest.mark.parametrize("action", [
    "SOURCE_BRANCH_WRITE",
    "EXECUTIVE_CHILD_COMMISSION",
    "PRODUCTION_DEPLOY",
    "LIVE_CAPITAL_EXECUTION",
])
def test_effectful_next_action_is_refused(action):
    def reasoner(prompt, **kwargs):
        return {"ok": True, "text": json.dumps(response(action=action)), "tools_used": []}

    with pytest.raises(ValueError, match="effectful_next_action_refused"):
        C._draft_with_reasoner(report(), reasoner=reasoner)


def test_unknown_evidence_reference_is_refused():
    def reasoner(prompt, **kwargs):
        return {
            "ok": True,
            "text": json.dumps(response(evidence=["invented-source"])),
            "tools_used": [],
        }

    with pytest.raises(ValueError, match="uncited_or_unknown_evidence"):
        C._draft_with_reasoner(report(), reasoner=reasoner)


def test_provider_tool_use_is_refused_even_when_json_is_valid():
    def reasoner(prompt, **kwargs):
        return {
            "ok": True,
            "text": json.dumps(response()),
            "tools_used": ["Read"],
        }

    with pytest.raises(ValueError, match="proposal_provider_tool_proof_required"):
        C._draft_with_reasoner(report(), reasoner=reasoner)


def test_output_must_be_plain_json_not_wrapped_text():
    def reasoner(prompt, **kwargs):
        return {
            "ok": True,
            "text": "JSON OUTPUT:\n" + json.dumps(response()),
            "tools_used": [],
        }

    with pytest.raises(ValueError, match="provider_json_required"):
        C._draft_with_reasoner(report(), reasoner=reasoner)


def test_empty_grounded_report_does_not_call_provider():
    item = report()
    item["opportunities"] = []
    item["hypotheses"] = []

    def forbidden(*args, **kwargs):
        raise AssertionError("provider must not be called")

    draft = C.draft_proposals(item)
    assert draft["proposals"] == []
    assert draft["provider"] is None


def test_evaluation_packet_exposes_ids_and_digest_not_private_prose():
    def reasoner(prompt, **kwargs):
        return {"ok": True, "text": json.dumps(response()), "tools_used": []}

    draft = C._draft_with_reasoner(report(), reasoner=reasoner)
    packet = C.evaluation_packet(draft)
    encoded = json.dumps(packet, sort_keys=True)
    assert packet["proposal_ids"] == ["PROP.REUSE.001"]
    assert packet["requires_independent_judge"] is True
    assert packet["same_model_self_grade_is_acceptance"] is False
    assert "The consumer may not expose context" not in encoded
    assert "Which current owner" not in encoded


@pytest.mark.parametrize("field,value", [
    ("execution_authority_granted", True),
    ("jobs_created", 1),
    ("independent_discovery_proven", True),
])
def test_effectful_or_overclaimed_discovery_report_is_refused(field, value):
    item = report()
    item[field] = value
    with pytest.raises(ValueError):
        C.draft_proposals(item)
