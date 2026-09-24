from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from brain import improvement_cognition as C


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def report():
    item = {
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
    item["digest"] = _digest(item)
    return item


def patch_reasoner(monkeypatch, reasoner):
    from brain import cli_bridge
    monkeypatch.setattr(cli_bridge, "reason_private_ephemeral_sync", reasoner)


def response(*, action="READ_ONLY_RESEARCH", evidence=None):
    return {
        "schema": C.DRAFT_SCHEMA,
        "evidence_digest": report()["digest"],
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


def test_draft_uses_one_no_tools_no_log_turn_and_keeps_advisory_boundary(monkeypatch):
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

    patch_reasoner(monkeypatch, reasoner)
    draft = C.draft_proposals(report())

    assert len(calls) == 1
    prompt, kwargs = calls[0]
    assert "target_answer_disclosed" in prompt
    assert "Does useful context already exist behind another accepted owner?" not in prompt
    assert "Compare reuse with a bounded coverage investigation." not in prompt
    assert "deterministic_scaffolds" not in prompt
    assert kwargs["role"] == "deep"
    assert kwargs["max_turns"] == 1
    assert kwargs["cwd"]
    assert not Path(kwargs["cwd"]).exists()
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
def test_effectful_next_action_is_refused(monkeypatch, action):
    def reasoner(prompt, **kwargs):
        return {"ok": True, "text": json.dumps(response(action=action)), "tools_used": []}

    patch_reasoner(monkeypatch, reasoner)
    with pytest.raises(ValueError, match="effectful_next_action_refused"):
        C.draft_proposals(report())


def test_unknown_evidence_reference_is_refused(monkeypatch):
    def reasoner(prompt, **kwargs):
        return {
            "ok": True,
            "text": json.dumps(response(evidence=["invented-source"])),
            "tools_used": [],
        }

    patch_reasoner(monkeypatch, reasoner)
    with pytest.raises(ValueError, match="uncited_or_unknown_evidence"):
        C.draft_proposals(report())


def test_provider_tool_use_is_refused_even_when_json_is_valid(monkeypatch):
    def reasoner(prompt, **kwargs):
        return {
            "ok": True,
            "text": json.dumps(response()),
            "tools_used": ["Read"],
        }

    patch_reasoner(monkeypatch, reasoner)
    with pytest.raises(ValueError, match="proposal_provider_tool_proof_required"):
        C.draft_proposals(report())


def test_output_must_be_plain_json_not_wrapped_text(monkeypatch):
    def reasoner(prompt, **kwargs):
        return {
            "ok": True,
            "text": "JSON OUTPUT:\n" + json.dumps(response()),
            "tools_used": [],
        }

    patch_reasoner(monkeypatch, reasoner)
    with pytest.raises(ValueError, match="provider_json_required"):
        C.draft_proposals(report())


def test_empty_grounded_report_does_not_call_provider():
    item = report()
    item["opportunities"] = []
    item["hypotheses"] = []
    item["digest"] = _digest({key: value for key, value in item.items() if key != "digest"})

    draft = C.draft_proposals(item)
    assert draft["proposals"] == []
    assert draft["provider"] is None


def test_evaluation_packet_exposes_only_opaque_derived_refs(monkeypatch):
    def reasoner(prompt, **kwargs):
        return {"ok": True, "text": json.dumps(response()), "tools_used": []}

    patch_reasoner(monkeypatch, reasoner)
    draft = C.draft_proposals(report())
    packet = C.evaluation_packet(draft)
    encoded = json.dumps(packet, sort_keys=True)
    assert packet["proposal_count"] == 1
    assert len(packet["proposal_refs"]) == 1
    assert packet["proposal_refs"][0].startswith("proposal:")
    assert packet["evidence_binding_digest"].startswith("sha256:")
    assert packet["draft_digest"].startswith("sha256:")
    assert packet["requires_independent_judge"] is True
    assert packet["same_model_self_grade_is_acceptance"] is False
    assert "PROP.REUSE.001" not in encoded
    assert report()["digest"] not in encoded
    assert "The consumer may not expose context" not in encoded
    assert "Which current owner" not in encoded


def test_evaluation_packet_hashes_valid_private_proposal_id_instead_of_republishing(monkeypatch):
    def reasoner(prompt, **kwargs):
        return {"ok": True, "text": json.dumps(response()), "tools_used": []}

    patch_reasoner(monkeypatch, reasoner)
    draft = C.draft_proposals(report())
    secret_shaped_valid_id = "PRIVATE_HYPOTHESIS_PROSE_MUST_NOT_CROSS"
    draft["proposals"][0]["proposal_id"] = secret_shaped_valid_id
    packet = C.evaluation_packet(draft)
    assert secret_shaped_valid_id not in json.dumps(packet, sort_keys=True)


def test_evaluation_packet_hashes_caller_controlled_evidence_digest(monkeypatch):
    def reasoner(prompt, **kwargs):
        return {"ok": True, "text": json.dumps(response()), "tools_used": []}

    patch_reasoner(monkeypatch, reasoner)
    draft = C.draft_proposals(report())
    caller_digest = "sha256:" + "b" * 64
    draft["evidence_digest"] = caller_digest
    packet = C.evaluation_packet(draft)
    assert caller_digest not in json.dumps(packet, sort_keys=True)


def test_evaluation_packet_refuses_authority_flag_tampering(monkeypatch):
    def reasoner(prompt, **kwargs):
        return {"ok": True, "text": json.dumps(response()), "tools_used": []}

    patch_reasoner(monkeypatch, reasoner)
    draft = C.draft_proposals(report())
    draft["execution_authority_granted"] = True
    with pytest.raises(ValueError, match="invalid_draft_authority"):
        C.evaluation_packet(draft)


def test_stale_or_modified_report_digest_is_refused():
    item = report()
    item["opportunities"][0]["next_evidence"] = "tampered after digest"
    with pytest.raises(ValueError, match="discovery_digest_mismatch"):
        C.draft_proposals(item)


def test_private_ephemeral_sdk_has_zero_settings_tools_and_native_nonpersistence(monkeypatch, tmp_path):
    from brain import cli_bridge as cb

    captured = {}

    class FakeOptions:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            for key, value in kwargs.items():
                setattr(self, key, value)

    async def fake_query(*, prompt, options):
        assert prompt == "private evidence"
        assert options is not None
        yield SimpleNamespace(
            result='{"ok":true}',
            total_cost_usd=0.0,
            session_id="ephemeral-provider-id",
            usage={"input_tokens": 1, "output_tokens": 1},
        )

    monkeypatch.setattr(cb, "_Options", FakeOptions)
    monkeypatch.setattr(cb, "_sdk_query", fake_query)
    monkeypatch.setattr(cb, "_subscription_env", lambda env_name=None: {})

    result = asyncio.run(cb._via_sdk(
        "private evidence", "model-x", "deep", None, None,
        [], [], 1, str(tmp_path), "default", {}, None, False,
        private_ephemeral=True,
    ))

    assert result["ok"] is True
    assert result["tools_used"] == []
    assert captured["allowed_tools"] == []
    assert captured["add_dirs"] == []
    assert captured["setting_sources"] == []
    assert captured["permission_mode"] == "dontAsk"
    assert captured["max_turns"] == 1
    assert captured["extra_args"] == {
        "safe-mode": None,
        "no-chrome": None,
        "no-session-persistence": None,
        "strict-mcp-config": None,
    }


def test_private_ephemeral_sdk_failure_never_falls_through_to_subprocess(monkeypatch, tmp_path):
    from brain import cli_bridge as cb
    from brain import key_rotor

    async def broken_sdk(*args, **kwargs):
        raise RuntimeError("sdk private failure")

    async def forbidden_subprocess(*args, **kwargs):
        raise AssertionError("private evidence must never reach subprocess fallback")

    monkeypatch.setattr(cb, "_SDK", True)
    monkeypatch.setattr(cb, "cli_path", lambda: "/fake/claude")
    monkeypatch.setattr(cb, "_via_sdk", broken_sdk)
    monkeypatch.setattr(cb, "_via_subprocess", forbidden_subprocess)
    monkeypatch.setattr(key_rotor, "candidates", lambda: [])
    monkeypatch.setattr(cb, "_cfg", lambda: {
        "backend": "cli",
        "roles": {"deep": "model-x"},
        "reasoning": {"permission_mode": "default", "max_turns": 1},
    })

    result = asyncio.run(cb._reason(
        "private evidence",
        role="deep",
        allowed_tools=[],
        add_dirs=[],
        max_turns=1,
        cwd=str(tmp_path),
        arm=False,
        resume=None,
        mcp_servers={},
        log_run=False,
        _backend_override="cli",
        _private_ephemeral=True,
    ))

    assert result["ok"] is False
    assert result["backend"] == "none"
    assert "sdk private failure" in result["error"]


@pytest.mark.parametrize("field,value,expected", [
    ("execution_authority_granted", True, "effectful_discovery_report_refused"),
    ("jobs_created", 1, "effectful_discovery_report_refused"),
    ("independent_discovery_proven", True, "unexpected_discovery_claim"),
])
def test_effectful_or_overclaimed_discovery_report_is_refused(field, value, expected):
    item = report()
    item[field] = value
    item["digest"] = _digest({key: val for key, val in item.items() if key != "digest"})
    with pytest.raises(ValueError, match=expected):
        C.draft_proposals(item)
