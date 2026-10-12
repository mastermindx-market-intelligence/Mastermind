"""Pure candidate-evidence projection from an *already validated* direct answer.

This does not authenticate a transport or claim that a model ran; the caller
must obtain an exact original-operation view through FabricInferenceClient.
Claims are untrusted research hypotheses, never trades, portfolio weights,
calibrated probabilities, independent confirmations, or promotion evidence.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from brain.decision_research import ResearchContextError, _verified_context
from portfolio.decision_snapshot_contracts import content_digest

SCHEMA = "mastermind.bot_research_claims.v1"
OUTPUT_SCHEMA = "mastermind.bot_research_candidate_claim_set.v1"
VIEW_SCHEMA = "mastermind.fabric_service_inference_result_view.v1"
DOCUMENT_SCHEMA = "mastermind.executive_service_inference_result_document.v1"
WORKER_SCHEMA = "mastermind.executive_service_inference_worker_result.v1"
REFERENCE_SCHEMA = "mastermind.executive_service_inference_result_ref.v2"
GENERATION_SCHEMA = "mastermind.runtime_read_observation.v1"
MAX_ANSWER_BYTES = 12_288
MAX_CLAIMS = 12
MAX_REFERENCES = 4
_CLAIM_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


class ResearchClaimError(ValueError):
    """The result cannot be consumed as bounded, cited candidate evidence."""


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise ResearchClaimError(detail)


def _keys(value: Any, expected: set[str], field: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping) and set(value) == expected,
             field + " has missing or unknown fields")
    return value


def _str(value: Any, field: str, *, maximum: int = 1024, minimum: int = 1) -> str:
    _require(isinstance(value, str) and minimum <= len(value.strip()) <= maximum
             and "\x00" not in value, "invalid " + field)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ResearchClaimError("invalid Unicode in " + field) from exc
    return value


def _no_duplicate_keys(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ResearchClaimError("repeated JSON keys are not admissible")
        result[k] = v
    return result


def _nonfinite_constant(_value):
    raise ResearchClaimError("nonfinite JSON values are not admissible")


def _bounded_json_integer(value: str) -> int:
    if len(value) > 20:
        raise ResearchClaimError("JSON integer exceeds the bounded numeric representation")
    return int(value)


def _copies(value: Any) -> Any:
    # JSON roundtrip both closes mutable aliases and prevents a caller from
    # smuggling unserializable objects into the claim projection.
    try:
        return json.loads(json.dumps(value, sort_keys=True, allow_nan=False,
                                    ensure_ascii=False))
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ResearchClaimError("invalid structured answer container") from exc


def _references(value: Any, chosen: Mapping[str, set[str]], name: str,
                *, allow_empty: bool) -> list[str]:
    _require(isinstance(value, list) and (allow_empty or bool(value))
             and len(value) <= MAX_REFERENCES
             and all(isinstance(x, str) for x in value), "invalid " + name)
    _require(len(value) == len(set(value)), "duplicate " + name)
    _require(all(ref in chosen for ref in value), "claim cites unselected evidence")
    return list(value)


def _source_artifacts(context: Mapping[str, Any]) -> tuple[dict[str, set[str]], dict[str, tuple[str, ...]]]:
    by_source = {r["source_id"]: r for r in context["source_receipts"]}
    selected: dict[str, set[str]] = {}
    original_source_ids: dict[str, tuple[str, ...]] = {}
    for domain, section in context["sections"].items():
        if section["withheld_reason"] is not None:
            continue
        for item in section["rows"]:
            ref = item["ref"]
            _require(ref not in selected, "selected evidence reference duplicated")
            sources = list(section["source_ids"])
            # A source_id inside the model-visible raw row is untrusted data,
            # not authenticated row provenance. The existing snapshot owner
            # establishes section-level membership only. Fail closed until it
            # supplies a separate trusted per-row provenance projection.
            _require(len(sources) == 1, "multi-source row lacks trusted provenance")
            _require(bool(sources), "selected row has no identified source")
            artifacts: set[str] = set()
            for source_id in sources:
                receipt = by_source.get(source_id)
                _require(isinstance(receipt, Mapping), "selected source receipt missing")
                _require(receipt["status"] == "AVAILABLE"
                         and receipt["freshness_state"] == "FRESH"
                         and receipt["rights_class"] in {"FIRST_PARTY_INTERNAL", "LICENSED_INTERNAL"}
                         and receipt["clock_basis"] in {"FILE_MTIME_FIRST_PARTY_STATE", "DECLARED_SOURCE_FIELD"}
                         and isinstance(receipt["artifact_digest"], str)
                         and receipt["artifact_digest"].startswith("sha256:"),
                         "selected evidence source is not qualified")
                artifacts.add(receipt["artifact_digest"])
            selected[ref] = artifacts
            original_source_ids[ref] = tuple(sources)
    return selected, original_source_ids


def consume_validated_answer(
    original_context: Mapping[str, Any],
    validated_direct_result: Mapping[str, Any],
    *,
    expected_operation_ref: str,
    expected_request_fingerprint: str,
    expected_reference: Mapping[str, Any],
) -> dict[str, Any]:
    """Produce deterministic *candidate* claims, never a submission or decision.

    The caller must already have authenticated and cryptographically validated
    the direct service result against the original operation with the service
    owner's own validators. Local checks repeat identity/coverage boundaries
    but are not a substitute for that authenticated source.
    """
    try:
        context = _verified_context(original_context)
    except (ResearchContextError, TypeError, ValueError) as exc:
        raise ResearchClaimError("original context is not a valid sealed selection") from exc
    _str(expected_operation_ref, "operation identity", maximum=96)
    _require(isinstance(expected_request_fingerprint, str)
             and re.fullmatch(r"[0-9a-f]{64}", expected_request_fingerprint) is not None,
             "invalid original fingerprint")
    ref = _keys(expected_reference,
                {"schema", "job_id", "attempt_id", "worker_id", "result_sha256", "content_sha256"},
                "expected result reference")
    _require(ref["schema"] == REFERENCE_SCHEMA, "only content-bound direct references are consumable")

    view = _keys(validated_direct_result,
                 {"schema", "operation_ref", "request_fingerprint", "reference", "generation",
                  "availability", "execution_status", "content_complete", "acceptance", "document"},
                 "direct result")
    _require(view["schema"] == VIEW_SCHEMA and view["operation_ref"] == expected_operation_ref
             and view["request_fingerprint"] == expected_request_fingerprint,
             "direct result belongs to a different original operation")
    _require(view["reference"] == ref, "direct result reference differs from original")
    _require(view["availability"] == "AVAILABLE" and view["execution_status"] == "COMPLETED"
             and view["content_complete"] is True and view["acceptance"] == "NOT_PROJECTED",
             "direct result is incomplete or asserts forbidden acceptance")
    generation = _keys(view["generation"],
                       {"schema", "state", "source_identity", "before", "after"},
                       "read generation")
    _require(generation["schema"] == GENERATION_SCHEMA and generation["state"] == "SAME"
             and isinstance(generation["source_identity"], str)
             and re.fullmatch(r"[0-9a-f]{32}", generation["source_identity"]) is not None
             and type(generation["before"]) is int and generation["before"] >= 0
             and type(generation["after"]) is int and generation["after"] == generation["before"],
             "unqualified read generation")
    document = _keys(view["document"], {"schema", "reference", "result"}, "document")
    _require(document["schema"] == DOCUMENT_SCHEMA and document["reference"] == ref,
             "direct answer document reference mismatch")
    result = _keys(document["result"],
                   {"schema_version", "job_id", "run_id", "worker_id", "status", "answer"},
                   "worker answer")
    _require(result["schema_version"] == WORKER_SCHEMA
             and result["job_id"] == ref["job_id"] and result["run_id"] == ref["attempt_id"]
             and result["worker_id"] == ref["worker_id"] and result["status"] == "COMPLETED",
             "returned worker result identity mismatch")
    answer = _str(result["answer"], "answer", maximum=16_384)
    _require(len(answer.encode("utf-8")) <= MAX_ANSWER_BYTES, "answer exceeds byte ceiling")
    try:
        text = json.loads(answer, object_pairs_hook=_no_duplicate_keys,
                          parse_constant=_nonfinite_constant,
                          parse_int=_bounded_json_integer)
    except (TypeError, json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise ResearchClaimError("returned answer is not closed JSON") from exc
    packet = _keys(text, {"schema", "context_id", "snapshot_id", "claims", "unknowns", "coverage_ack"},
                   "claim packet")
    _require(packet["schema"] == SCHEMA and packet["context_id"] == context["context_id"]
             and packet["snapshot_id"] == context["snapshot_id"],
             "claim packet differs from the original decision snapshot")
    ack = _keys(packet["coverage_ack"],
                {"selection_complete", "selected_rows", "unselected_domains"}, "coverage acknowledgement")
    _require(ack["selection_complete"] is context["selection_complete"]
             and type(ack["selected_rows"]) is int
             and ack["selected_rows"] == sum(s["selected_rows"] for s in context["sections"].values())
             and ack["unselected_domains"] == context["unselected_domains"],
             "research answer hides omitted or unselected evidence")
    unknowns = packet["unknowns"]
    _require(isinstance(unknowns, list) and len(unknowns) <= MAX_CLAIMS,
             "invalid unknown-evidence declarations")
    unknowns = [_str(v, "unknown") for v in unknowns]
    _require(len(unknowns) == len(set(unknowns)), "duplicate unknown declarations")
    if not context["selection_complete"] or context["snapshot_coverage"] != "COMPLETE":
        _require(bool(unknowns), "incomplete research requires explicit unknowns")
    raw_claims = packet["claims"]
    _require(isinstance(raw_claims, list) and len(raw_claims) <= MAX_CLAIMS,
             "claim count exceeds bound")
    chosen, sources = _source_artifacts(context)
    claims = []
    ids = set()
    for candidate in raw_claims:
        c = _keys(candidate,
                  {"claim_id", "statement", "kind", "stance", "evidence_refs",
                   "contrary_refs", "uncertainty", "falsifier"}, "claim")
        claim_id = _str(c["claim_id"], "claim id", maximum=64)
        _require(_CLAIM_ID.fullmatch(claim_id) is not None and claim_id not in ids,
                 "duplicate or invalid claim id")
        ids.add(claim_id)
        statement = _str(c["statement"], "statement", maximum=1024)
        falsifier = _str(c["falsifier"], "falsifier", maximum=1024)
        _require(isinstance(c["kind"], str)
                 and c["kind"] in {"OBSERVATION", "INFERENCE", "COUNTEREVIDENCE"}
                 and isinstance(c["stance"], str)
                 and c["stance"] in {"SUPPORT", "CONTRADICT", "NEUTRAL"}
                 and isinstance(c["uncertainty"], str)
                 and c["uncertainty"] in {"UNQUANTIFIED", "LOW", "MEDIUM", "HIGH"},
                 "unsupported kind, stance or uncertainty")
        positive = _references(c["evidence_refs"], chosen, "evidence citations",
                               allow_empty=False)
        contrary = _references(c["contrary_refs"], chosen, "contrary citations",
                               allow_empty=True)
        _require(not (set(positive) & set(contrary)),
                 "evidence cannot simultaneously confirm and contradict itself")
        cited = positive + contrary
        claims.append({
            "claim_id": claim_id, "statement": statement, "kind": c["kind"],
            "stance": c["stance"], "evidence_refs": positive,
            "contrary_refs": contrary, "uncertainty": c["uncertainty"],
            "falsifier": falsifier,
            "source_ids": sorted({v for r in cited for v in sources[r]}),
            "artifact_identities": sorted({v for r in cited for v in chosen[r]}),
        })
    result_packet = {
        "schema": OUTPUT_SCHEMA,
        "candidate_only": True,
        "authority": {"write_permitted": False, "execution_authority": False,
                      "numeric_target_authority": False},
        "operation_ref": expected_operation_ref,
        "request_fingerprint": expected_request_fingerprint,
        "reference": dict(ref),
        "snapshot_id": context["snapshot_id"],
        "context_id": context["context_id"],
        "claim_count": len(claims), "claims": claims,
        "unknowns": unknowns,
        "selection_complete": context["selection_complete"],
        "unselected_domains": list(context["unselected_domains"]),
        "coverage": {
            "snapshot_state": context["snapshot_state"],
            "snapshot_coverage": context["snapshot_coverage"],
            "domain_coverage": dict(context["domain_coverage"]),
            "selection_complete": context["selection_complete"],
            "snapshot_gap_count": context["snapshot_gap_count"],
            "source_omitted_rows": {name: section["source_omitted_rows"]
                                    for name, section in context["sections"].items()},
            "selection_omitted_rows": {name: section["selection_omitted_rows"]
                                       for name, section in context["sections"].items()},
            "section_gap_counts": {name: len(section["gaps"])
                                   for name, section in context["sections"].items()},
        },
        "artifact_independence": "NOT_ESTABLISHED",
        "uncertainty_calibration": "NOT_CALIBRATED",
    }
    output = _copies(result_packet)
    output["claim_set_id"] = content_digest(output)
    return output


async def read_original_candidate_claims(
    trusted_service_client: Any,
    *,
    original_context: Mapping[str, Any],
    operation_key: str,
    objective: str,
    original_operation_ref: str,
    original_request_fingerprint: str,
    original_inference_request: Mapping[str, Any],
) -> dict[str, Any]:
    """Consume one answer using a frozen context and exact retained wire request.

    The caller supplies the original admitted wire bytes, including its output
    ceiling and version. No defaults may reconstruct a different request.
    The actual FabricInferenceClient.answer owns authenticated operation and
    selected-reference checks; a synthetic injected client proves neither.
    No submit/retry, queue, portfolio update or capital authority is created.
    """
    from brain.decision_research import inference_request
    _require(callable(getattr(trusted_service_client, "answer", None)),
             "existing trusted service answer interface required")
    _str(operation_key, "operation key", maximum=96)
    _str(objective, "original objective", maximum=4000)
    _str(original_operation_ref, "original operation ref", maximum=96)
    try:
        # The first local copy is the ONLY context used, both before and after
        # await. Callback-side caller mutations cannot substitute provenance.
        frozen_context = _verified_context(original_context)
        wire = _copies(original_inference_request)
        _require(isinstance(wire, dict), "retained inference request must be an object")
        version = wire.get("schema")
        _require(version in {
            "mastermind.executive_service_inference_request.v1",
            "mastermind.executive_service_inference_request.v2",
        }, "retained inference request schema is unsupported")
        limit = wire.get("max_output_chars")
        _require(type(limit) is int, "retained output limit must be an exact integer")
        expected = inference_request(
            frozen_context, max_output_chars=limit,
            task_aware=(version == "mastermind.executive_service_inference_request.v2"),
        )
        _require(wire == expected, "retained inference request differs from the frozen context")
    except (ResearchContextError, ValueError, TypeError) as exc:
        raise ResearchClaimError("original prepared inference request is invalid") from exc
    # No retry after the async boundary. The source owner's client validates
    # the request/operation/ref against its immutable admitted result.
    validated = await trusted_service_client.answer(operation_key, objective, wire)
    _require(isinstance(validated, Mapping), "service answer is unavailable")
    return consume_validated_answer(
        frozen_context, validated,
        expected_operation_ref=original_operation_ref,
        expected_request_fingerprint=original_request_fingerprint,
        expected_reference=validated.get("reference"),
    )
