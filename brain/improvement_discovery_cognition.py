"""Private model proposal drafts for improvement discovery.

This module is an advisory adapter over the existing brain.cli_bridge.
It creates no scheduler, queue, priority engine, strategic option, source mutation,
worker admission, or execution authority. The model receives a bounded evidence
packet, has no tools, and may return only read-only investigation drafts or HOLD.

The returned object is intentionally ephemeral. Callers that need durable evidence
must use an existing approved owner and must never publish private hypothesis prose
through the public Improvement Agenda or mastermind_ai review mirror.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain import improvement_discovery as discovery

OUTPUT_SCHEMA = "mastermind.improvement_proposal_drafts.v1"
MODEL_SCHEMA = "mastermind.improvement_model_response.v1"

MAX_REPORT_BYTES = 2_000_000
MAX_PROMPT_BYTES = 120_000
MAX_MODEL_BYTES = 48_000
MAX_PROPOSALS = 3
MAX_LIST = 6
MAX_TEXT = 1600

_ACTIONS = {"READ_ONLY_INVESTIGATION", "HOLD"}
_PROPOSAL_KEYS = {
    "opportunity_id",
    "next_action_kind",
    "problem",
    "mechanism_hypothesis",
    "expected_delta",
    "evidence_ids",
    "unknowns",
    "falsifiers",
    "investigation_questions",
}
_MODEL_KEYS = {"schema", "proposals", "hold_reason"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")

_SYSTEM = """You draft private, evidence-bound improvement hypotheses for later Chairman Cognition review.

Return JSON only, with exactly the supplied response schema. You have no tools and must not claim
that you searched, executed, changed source, created work, or verified facts beyond the evidence packet.
Do not rank proposals, choose a winner, assign priority, allocate budget, prescribe trades, or turn a
draft into an implementation/strategic option. next_action_kind is only READ_ONLY_INVESTIGATION or HOLD.
Every non-HOLD proposal must cite exact evidence ids from its opportunity. Missing evidence stays unknown.
Competing explanations are valuable. A truthful no-proposal HOLD is acceptable.
"""


class ProposalDraftError(ValueError):
    """Fixed-code refusal for invalid local/model inputs."""


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise ProposalDraftError("invalid_text")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        raise ProposalDraftError("invalid_text")
    return value.strip()


def _id(value: Any) -> str:
    value = _text(value)
    if not _SAFE_ID.fullmatch(value):
        raise ProposalDraftError("invalid_id")
    return value


def _text_list(value: Any, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_LIST or (not value and not allow_empty):
        raise ProposalDraftError("invalid_list")
    return [_text(item) for item in value]


def _validate_report(report: Any) -> tuple[dict, dict[str, set[str]]]:
    if not isinstance(report, dict) or report.get("schema") != discovery.REPORT_SCHEMA:
        raise ProposalDraftError("invalid_report")
    if report.get("execution_authority_granted") is not False or report.get("jobs_created") != 0:
        raise ProposalDraftError("report_authority_invalid")
    digest = report.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ProposalDraftError("report_digest_invalid")
    expected = discovery._digest({k: v for k, v in report.items() if k != "digest"})
    if digest != expected:
        raise ProposalDraftError("report_digest_mismatch")

    sources = report.get("sources")
    opportunities = report.get("opportunities")
    if not isinstance(sources, list) or not isinstance(opportunities, list):
        raise ProposalDraftError("report_shape_invalid")
    if len(opportunities) > discovery.MAX_ROWS:
        raise ProposalDraftError("report_too_large")

    source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ProposalDraftError("report_source_invalid")
        sid = _id(source.get("id"))
        if sid in source_ids:
            raise ProposalDraftError("duplicate_source_id")
        source_ids.add(sid)

    evidence_by_opportunity: dict[str, set[str]] = {}
    for row in opportunities:
        if not isinstance(row, dict):
            raise ProposalDraftError("report_opportunity_invalid")
        oid = _id(row.get("id"))
        refs = row.get("source_refs")
        if not isinstance(refs, list) or not refs:
            raise ProposalDraftError("report_evidence_invalid")
        refs_set = {_id(ref) for ref in refs}
        if len(refs_set) != len(refs) or not refs_set <= source_ids:
            raise ProposalDraftError("report_evidence_invalid")
        if oid in evidence_by_opportunity:
            raise ProposalDraftError("duplicate_opportunity_id")
        evidence_by_opportunity[oid] = refs_set

    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    if len(encoded.encode()) > MAX_REPORT_BYTES:
        raise ProposalDraftError("report_too_large")
    return report, evidence_by_opportunity


def _packet(report: dict) -> dict:
    """Project only evidence needed for ideation; omit deterministic target scaffolds."""
    rows = []
    for row in report.get("opportunities") or []:
        expectation = row.get("expectation") if isinstance(row.get("expectation"), dict) else {}
        observations = row.get("observations") if isinstance(row.get("observations"), list) else []
        rows.append({
            "opportunity_id": row.get("id"),
            "diagnosis": row.get("diagnosis"),
            "disposition": row.get("disposition"),
            "user_job": expectation.get("user_job"),
            "consumer": expectation.get("consumer"),
            "expected_capability": expectation.get("requirement"),
            "observations": [
                {
                    "state": obs.get("state"),
                    "scope_complete": obs.get("scope_complete"),
                    "finding": obs.get("finding"),
                    "evidence_ids": obs.get("source_refs"),
                }
                for obs in observations if isinstance(obs, dict)
            ],
            "evidence_ids": row.get("source_refs"),
            "existing_work": row.get("existing_work"),
        })
    return {
        "source_report_digest": report["digest"],
        "origin": report.get("origin"),
        "evaluation_use": report.get("evaluation_use"),
        "opportunities": rows,
    }


def _prompt(report: dict) -> str:
    packet = _packet(report)
    response_schema = {
        "schema": MODEL_SCHEMA,
        "proposals": [{
            "opportunity_id": "<exact opportunity id>",
            "next_action_kind": "READ_ONLY_INVESTIGATION | HOLD",
            "problem": "<bounded problem statement>",
            "mechanism_hypothesis": "<causal/mechanistic explanation to test, not a fact>",
            "expected_delta": "<observable user or machine benefit if true>",
            "evidence_ids": ["<exact source id from that opportunity>"],
            "unknowns": ["<material unknown>"],
            "falsifiers": ["<observation that would reject this proposal>"],
            "investigation_questions": ["<read-only question>"],
        }],
        "hold_reason": None,
    }
    prompt = (
        "Generate zero to three competing advisory proposal drafts from the evidence packet. "
        "Do not expose or invent implementation authority. If no grounded proposal is useful, "
        "return an empty proposals list and a concise hold_reason.\n\n"
        "RESPONSE_SCHEMA\n" + json.dumps(response_schema, ensure_ascii=True, separators=(",", ":")) +
        "\n\nEVIDENCE_PACKET\n" + json.dumps(packet, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    )
    if len(prompt.encode()) > MAX_PROMPT_BYTES:
        raise ProposalDraftError("prompt_too_large")
    return prompt


def _parse_model_text(text: Any, evidence_by_opportunity: dict[str, set[str]]) -> tuple[list[dict], str | None]:
    if not isinstance(text, str) or not text.strip() or len(text.encode()) > MAX_MODEL_BYTES:
        raise ProposalDraftError("model_output_invalid")
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProposalDraftError("model_output_invalid") from exc
    if not isinstance(payload, dict) or set(payload) != _MODEL_KEYS or payload.get("schema") != MODEL_SCHEMA:
        raise ProposalDraftError("model_output_invalid")

    proposals = payload.get("proposals")
    if not isinstance(proposals, list) or len(proposals) > MAX_PROPOSALS:
        raise ProposalDraftError("model_output_invalid")
    hold_reason = payload.get("hold_reason")
    if proposals:
        if hold_reason is not None:
            raise ProposalDraftError("model_output_invalid")
    else:
        hold_reason = _text(hold_reason)

    normalized: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for raw in proposals:
        if not isinstance(raw, dict) or set(raw) != _PROPOSAL_KEYS:
            raise ProposalDraftError("model_output_invalid")
        oid = _id(raw["opportunity_id"])
        action = raw["next_action_kind"]
        if oid not in evidence_by_opportunity or action not in _ACTIONS:
            raise ProposalDraftError("model_output_invalid")
        evidence_ids = [_id(item) for item in raw["evidence_ids"]] if isinstance(raw["evidence_ids"], list) else []
        if not evidence_ids or len(evidence_ids) > MAX_LIST or len(set(evidence_ids)) != len(evidence_ids):
            raise ProposalDraftError("model_output_invalid")
        if not set(evidence_ids) <= evidence_by_opportunity[oid]:
            raise ProposalDraftError("unknown_evidence_id")
        key = (oid, action)
        if key in seen:
            raise ProposalDraftError("duplicate_proposal")
        seen.add(key)
        normalized.append({
            "opportunity_id": oid,
            "next_action_kind": action,
            "problem": _text(raw["problem"]),
            "mechanism_hypothesis": _text(raw["mechanism_hypothesis"]),
            "expected_delta": _text(raw["expected_delta"]),
            "evidence_ids": evidence_ids,
            "unknowns": _text_list(raw["unknowns"]),
            "falsifiers": _text_list(raw["falsifiers"]),
            "investigation_questions": _text_list(raw["investigation_questions"]),
        })
    return normalized, hold_reason


def _unavailable(report_digest: str | None, reason_code: str, result: dict | None = None) -> dict:
    out = {
        "schema": OUTPUT_SCHEMA,
        "state": "UNAVAILABLE",
        "reason_code": reason_code,
        "source_report_digest": report_digest,
        "proposals": [],
        "hold_reason": None,
        "selected_proposal": None,
        "advisory_only": True,
        "independent_usefulness_proven": False,
        "strategic_options_created": 0,
        "execution_authority_granted": False,
        "jobs_created": 0,
        "persisted": False,
    }
    if isinstance(result, dict):
        if isinstance(result.get("backend"), str):
            out["provider_backend"] = result["backend"][:80]
        if isinstance(result.get("model"), str):
            out["provider_model"] = result["model"][:120]
    return out


async def generate(report: Any) -> dict:
    """Generate one ephemeral, no-tools advisory model draft pass."""
    try:
        checked, evidence = _validate_report(report)
        prompt = _prompt(checked)
    except (ProposalDraftError, ValueError, TypeError, KeyError, OverflowError):
        return _unavailable(report.get("digest") if isinstance(report, dict) else None, "INPUT_INVALID")

    from brain import cli_bridge
    try:
        result = await cli_bridge.reason(
            prompt,
            role="deep",
            system=_SYSTEM,
            allowed_tools=[],
            add_dirs=[],
            max_turns=1,
            arm=False,
            log_run=False,
        )
    except Exception:
        return _unavailable(checked["digest"], "PROVIDER_UNAVAILABLE")

    if not isinstance(result, dict) or result.get("ok") is not True:
        return _unavailable(checked["digest"], "PROVIDER_UNAVAILABLE", result if isinstance(result, dict) else None)
    tools_used = result.get("tools_used") or []
    if tools_used:
        return _unavailable(checked["digest"], "MODEL_TOOL_USE_REFUSED", result)
    if result.get("armed") not in (False, None):
        return _unavailable(checked["digest"], "MODEL_ARMED_STATE_REFUSED", result)

    try:
        proposals, hold_reason = _parse_model_text(result.get("text"), evidence)
    except ProposalDraftError:
        return _unavailable(checked["digest"], "MODEL_OUTPUT_INVALID", result)

    body = {
        "schema": OUTPUT_SCHEMA,
        "state": "AVAILABLE",
        "source_report_digest": checked["digest"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider_backend": str(result.get("backend") or "unknown")[:80],
        "provider_model": str(result.get("model") or "unknown")[:120],
        "outcome": "DRAFTS" if proposals else "HOLD",
        "proposals": proposals,
        "hold_reason": hold_reason,
        "selected_proposal": None,
        "advisory_only": True,
        "independent_usefulness_proven": False,
        "strategic_options_created": 0,
        "execution_authority_granted": False,
        "jobs_created": 0,
        "persisted": False,
    }
    body["digest"] = discovery._digest(body)
    return body


def load_report(path: str | Path) -> dict:
    """Read one bounded private report for the CLI consumer."""
    target = Path(path)
    if target.stat().st_size > MAX_REPORT_BYTES:
        raise ProposalDraftError("report_too_large")
    value = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProposalDraftError("invalid_report")
    return value
