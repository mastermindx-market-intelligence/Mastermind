from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest

from brain import improvement_discovery as discovery
from brain import improvement_discovery_cognition as cognition


NOW = "2026-09-24T12:00:00+00:00"
REV = "a" * 40
SHA = "sha256:" + "b" * 64


@pytest.fixture
def report():
    bundle = {
        "schema": discovery.INPUT_SCHEMA,
        "case_id": "prospective-cognition-canary",
        "origin": "PROSPECTIVE",
        "cutoff_at": None,
        "sources": [
            {
                "id": "expectation-contract",
                "owner": "GITHUB",
                "ref": "repo/contracts/improvement",
                "revision": REV,
                "content_sha256": SHA,
                "available_at": "2026-09-24T10:00:00+00:00",
                "observed_at": "2026-09-24T11:00:00+00:00",
                "valid_until": "2026-09-24T13:00:00+00:00",
                "state": "CURRENT",
            },
            {
                "id": "owner-observation",
                "owner": "DOMAIN_OWNER",
                "ref": "owner/current",
                "revision": REV,
                "content_sha256": "sha256:" + "c" * 64,
                "available_at": "2026-09-24T10:15:00+00:00",
                "observed_at": "2026-09-24T11:00:00+00:00",
                "valid_until": "2026-09-24T13:00:00+00:00",
                "state": "CURRENT",
            },
        ],
        "expectations": [
            {
                "id": "context-resolution",
                "scope": "bounded-owner-sample",
                "user_job": "Understand why a monitored subject changed.",
                "consumer": "research workspace",
                "requirement": "Provide evidence-backed mechanism context with explicit unknowns.",
                "expectation_source": "expectation-contract",
            }
        ],
        "observations": [
            {
                "expectation_id": "context-resolution",
                "scope": "bounded-owner-sample",
                "source_refs": ["owner-observation"],
                "scope_complete": True,
                "state": "GAP",
                "finding": "The current owner exposes coverage but not enough mechanism detail for this user job.",
            }
        ],
        "existing_work": [],
    }
    return discovery.evaluate(bundle, now=NOW)


def model_payload(report, **proposal_overrides):
    opportunity = report["opportunities"][0]
    proposal = {
        "opportunity_id": opportunity["id"],
        "next_action_kind": "READ_ONLY_INVESTIGATION",
        "problem": "Mechanism detail may be missing for the bounded research question.",
        "mechanism_hypothesis": "The consumer may receive source coverage without the transmission evidence needed to explain change.",
        "expected_delta": "A read-only comparison could show whether existing evidence already answers the user's mechanism question.",
        "evidence_ids": list(opportunity["source_refs"]),
        "unknowns": ["Whether an existing owner already contains the missing mechanism evidence."],
        "falsifiers": ["Existing lawful evidence answers the same task without new research."],
        "investigation_questions": ["Which existing owner can answer the same question with current evidence?"],
    }
    proposal.update(proposal_overrides)
    return {
        "schema": cognition.MODEL_SCHEMA,
        "proposals": [proposal],
        "hold_reason": None,
    }


def test_prompt_omits_prebaked_hypothesis_targets(report):
    augmented = deepcopy(report)
    augmented["hypotheses"] = [{"target_answer": "DO_NOT_LEAK_THIS_TARGET"}]
    augmented["selection"] = {"winner": "DO_NOT_LEAK_THIS_WINNER"}
    augmented["digest"] = discovery._digest({k: v for k, v in augmented.items() if k != "digest"})
    checked, _ = cognition._validate_report(augmented)
    prompt = cognition._prompt(checked)
    assert "DO_NOT_LEAK_THIS_TARGET" not in prompt
    assert "DO_NOT_LEAK_THIS_WINNER" not in prompt
    assert "hypotheses" not in cognition._packet(checked)
    assert "selection" not in cognition._packet(checked)


def test_generate_uses_one_no_tools_unarmed_no_log_provider_pass(report, monkeypatch):
    seen = {}

    async def fake_reason(prompt, **kwargs):
        seen["prompt"] = prompt
        seen["kwargs"] = kwargs
        return {
            "ok": True,
            "text": json.dumps(model_payload(report)),
            "backend": "fixture",
            "model": "fixture-model",
            "armed": False,
            "tools_used": [],
        }

    from brain import cli_bridge
    monkeypatch.setattr(cli_bridge, "reason", fake_reason)

    result = asyncio.run(cognition.generate(report))

    assert result["state"] == "AVAILABLE"
    assert result["outcome"] == "DRAFTS"
    assert result["selected_proposal"] is None
    assert result["advisory_only"] is True
    assert result["independent_usefulness_proven"] is False
    assert result["strategic_options_created"] == 0
    assert result["execution_authority_granted"] is False
    assert result["jobs_created"] == 0
    assert result["persisted"] is False
    assert seen["kwargs"] == {
        "role": "deep",
        "system": cognition._SYSTEM,
        "allowed_tools": [],
        "add_dirs": [],
        "max_turns": 1,
        "arm": False,
        "log_run": False,
    }


def test_truthful_hold_is_valid_output(report, monkeypatch):
    async def fake_reason(*args, **kwargs):
        return {
            "ok": True,
            "text": json.dumps({
                "schema": cognition.MODEL_SCHEMA,
                "proposals": [],
                "hold_reason": "The evidence does not yet discriminate a useful investigation.",
            }),
            "backend": "fixture",
            "model": "fixture-model",
            "armed": False,
            "tools_used": [],
        }

    from brain import cli_bridge
    monkeypatch.setattr(cli_bridge, "reason", fake_reason)
    result = asyncio.run(cognition.generate(report))
    assert result["state"] == "AVAILABLE"
    assert result["outcome"] == "HOLD"
    assert result["proposals"] == []
    assert result["hold_reason"].startswith("The evidence")
    assert result["jobs_created"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["proposals"][0].update(priority=1),
        lambda payload: payload["proposals"][0].update(evidence_ids=["invented-source"]),
        lambda payload: payload["proposals"][0].update(next_action_kind="IMPLEMENT"),
        lambda payload: payload.update(hold_reason="also choose this"),
    ],
)
def test_model_cannot_launder_authority_or_unknown_evidence(report, monkeypatch, mutation):
    payload = model_payload(report)
    mutation(payload)

    async def fake_reason(*args, **kwargs):
        return {
            "ok": True,
            "text": json.dumps(payload),
            "backend": "fixture",
            "model": "fixture-model",
            "armed": False,
            "tools_used": [],
        }

    from brain import cli_bridge
    monkeypatch.setattr(cli_bridge, "reason", fake_reason)
    result = asyncio.run(cognition.generate(report))
    assert result["state"] == "UNAVAILABLE"
    assert result["reason_code"] == "MODEL_OUTPUT_INVALID"
    assert result["jobs_created"] == 0
    assert result["execution_authority_granted"] is False


def test_any_tool_use_refuses_otherwise_valid_model_output(report, monkeypatch):
    async def fake_reason(*args, **kwargs):
        return {
            "ok": True,
            "text": json.dumps(model_payload(report)),
            "backend": "fixture",
            "model": "fixture-model",
            "armed": False,
            "tools_used": ["Read"],
        }

    from brain import cli_bridge
    monkeypatch.setattr(cli_bridge, "reason", fake_reason)
    result = asyncio.run(cognition.generate(report))
    assert result["state"] == "UNAVAILABLE"
    assert result["reason_code"] == "MODEL_TOOL_USE_REFUSED"
    assert result["proposals"] == []


def test_provider_failure_does_not_echo_private_error(report, monkeypatch):
    secretish = "provider exploded with PRIVATE_OWNER_PROSE and credential-shaped detail"

    async def fake_reason(*args, **kwargs):
        return {
            "ok": False,
            "text": None,
            "backend": "fixture",
            "model": "fixture-model",
            "armed": False,
            "tools_used": [],
            "error": secretish,
        }

    from brain import cli_bridge
    monkeypatch.setattr(cli_bridge, "reason", fake_reason)
    result = asyncio.run(cognition.generate(report))
    serialized = json.dumps(result)
    assert result["state"] == "UNAVAILABLE"
    assert result["reason_code"] == "PROVIDER_UNAVAILABLE"
    assert "PRIVATE_OWNER_PROSE" not in serialized
    assert "credential-shaped" not in serialized


def test_tampered_report_refuses_before_provider_call(report, monkeypatch):
    tampered = deepcopy(report)
    tampered["opportunities"][0]["diagnosis"] = "SATISFIED"
    called = False

    async def fake_reason(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider must not be called")

    from brain import cli_bridge
    monkeypatch.setattr(cli_bridge, "reason", fake_reason)
    result = asyncio.run(cognition.generate(tampered))
    assert called is False
    assert result["state"] == "UNAVAILABLE"
    assert result["reason_code"] == "INPUT_INVALID"


def test_parser_rejects_more_than_three_proposals(report):
    payload = model_payload(report)
    payload["proposals"] = payload["proposals"] * 4
    with pytest.raises(cognition.ProposalDraftError):
        cognition._parse_model_text(
            json.dumps(payload),
            {report["opportunities"][0]["id"]: set(report["opportunities"][0]["source_refs"])},
        )


def test_parser_rejects_non_json_wrappers(report):
    payload = json.dumps(model_payload(report))
    with pytest.raises(cognition.ProposalDraftError):
        cognition._parse_model_text(
            "Here is the JSON:\n" + payload,
            {report["opportunities"][0]["id"]: set(report["opportunities"][0]["source_refs"])},
        )


def test_load_report_rejects_non_object(tmp_path):
    path = tmp_path / "report.json"
    path.write_text("[]")
    with pytest.raises(cognition.ProposalDraftError):
        cognition.load_report(path)
