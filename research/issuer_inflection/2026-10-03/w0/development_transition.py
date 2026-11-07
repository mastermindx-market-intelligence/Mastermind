#!/usr/bin/env python3
"""Development-only issuer-state-transition candidate composition over frozen AAPL evidence.

This exercises the W0 candidate schema without registering it.  It deliberately
emits only development reconstruction with rights not admitted and comparison
state NOT_EVALUABLE.  Owner facts/refusals remain authoritative; this module
adds no financial, rights, event, materiality, causal, or trading semantics.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from baseline_replay import canonical, owner_snapshot

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence" / "baseline-replay"
SCHEMA_PATH = ROOT / "issuer_state_transition.candidate.schema.json"
RECONSTRUCTED_AT = "2026-10-05T07:43:48Z"
REFUSAL = "unlinked source vintages require an explicit typed revision lineage"
CELL_SCHEMA = "fundamental_forensics.metric_cell_receipt/v1"
RESPONSE_SCHEMA = "fundamental_forensics.financial_query_response/v1"
RAW_FACT_SELECTOR_SCHEMA = "fundamental_forensics.metric_query/v1#selected_raw_fact"
LOCAL_ARTIFACT_SCHEMA = "mastermind.i3_w0_research_artifact/v1"


class TransitionRefusal(ValueError):
    """Frozen evidence cannot support the requested development transition."""


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise TransitionRefusal(reason)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_ref(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    digest = _sha(raw)
    return {
        "owner_ref": "Mastermind#1195",
        "schema": LOCAL_ARTIFACT_SCHEMA,
        "object_id": path.relative_to(ROOT).as_posix(),
        "revision_id": digest,
        "content_sha256": digest,
        "selector": None,
    }


def _response_ref(snapshot: dict[str, Any], *, selector: str | None = None) -> dict[str, Any]:
    return {
        "owner_ref": "FIF",
        "schema": RESPONSE_SCHEMA,
        "object_id": "financial_query_response:" + snapshot["query_hash"],
        "revision_id": snapshot["query_hash"],
        "content_sha256": snapshot["owner_response_sha256"],
        "selector": selector,
    }


def _cell_ref(snapshot: dict[str, Any], node: dict[str, Any], *, selector: str | None = None) -> dict[str, Any]:
    return {
        "owner_ref": "FIF",
        "schema": CELL_SCHEMA,
        "object_id": node["cell_id"],
        "revision_id": snapshot["query_hash"],
        "content_sha256": snapshot["owner_response_sha256"],
        "selector": selector,
    }


def _source_ref(snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    selected = node["provenance"].get("selected_raw_fact")
    if not isinstance(selected, dict):
        return _response_ref(snapshot, selector=f"/receipt/nodes/{node['cell_id']}/provenance/reason")
    source = selected["source"]
    return {
        "owner_ref": "FIF_RAW_LEDGER",
        "schema": RAW_FACT_SELECTOR_SCHEMA,
        "object_id": selected["occurrence_id"],
        "revision_id": source["accession"],
        "content_sha256": source["body_sha256"],
        "selector": f"source_span:{selected['source_span'][0]}:{selected['source_span'][1]}",
    }


def _clock(value: str | None, name: str, policy_ref: dict[str, Any]) -> dict[str, Any]:
    if value is None:
        return {
            "lower": None,
            "upper": None,
            "precision": "unknown",
            "owner_clock_name": name,
            "policy_ref": deepcopy(policy_ref),
        }
    return {
        "lower": value,
        "upper": value,
        "precision": "exact",
        "owner_clock_name": name,
        "policy_ref": deepcopy(policy_ref),
    }


def _input(role: str, snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    policy_ref = _response_ref(snapshot, selector="/receipt/policy")
    provenance = node["provenance"]
    return {
        "role": role,
        "ref": _cell_ref(snapshot, node),
        "source_refs": [_source_ref(snapshot, node)],
        "period_ref": _cell_ref(snapshot, node, selector="/period"),
        "basis_ref": _cell_ref(snapshot, node, selector="/provenance"),
        "source_available": _clock(provenance.get("source_ready_at"), "source_ready_at", policy_ref),
        "system_admitted": _clock(provenance.get("system_ready_at"), "system_ready_at", policy_ref),
    }


def _node(snapshot: dict[str, Any], metric: str, kind: str) -> dict[str, Any]:
    matches = [node for key, node in snapshot["nodes"].items() if key[0] == metric and key[1] == kind]
    _require(len(matches) == 1, "fixture_node_ambiguity")
    return matches[0]


def _load_snapshots() -> dict[str, dict[str, Any]]:
    method = json.loads((EVIDENCE / "method-before-execution.json").read_text(encoding="utf-8"))
    hashes = {
        row["name"]: row["response_sha256"]
        for row in json.loads((EVIDENCE / "owner-queries.json").read_text(encoding="utf-8"))
    }
    snapshots: dict[str, dict[str, Any]] = {}
    for name in ("before_a1_admission", "after_a1_before_a2_admission", "after_a2_admission"):
        snapshots[name] = owner_snapshot(
            (EVIDENCE / f"{name}.response.json").read_bytes(),
            hashes[name],
            method["requests"][name],
        )
    return snapshots


def _unique_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[bytes] = set()
    out = []
    for ref in refs:
        key = canonical(ref)
        if key not in seen:
            seen.add(key)
            out.append(ref)
    return out


def _development_definition_ref(snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    return _cell_ref(snapshot, node, selector="/provenance/metric_rule_id+/mapping_rule_id")


def _build(
    *,
    case: str,
    before: dict[str, Any],
    after: dict[str, Any],
    before_node: dict[str, Any],
    after_node: dict[str, Any],
    baseline_state: str,
    baseline_reason: str | None,
    comparison_reason: str,
    measurement_shape: str,
    public_clock: str | None,
    system_clock: str | None,
    evidence: list[dict[str, Any]],
    limitations: list[str],
) -> dict[str, Any]:
    before_ref = _cell_ref(before, before_node)
    after_ref = _cell_ref(after, after_node)
    target_policy_ref = _response_ref(after, selector="/receipt/policy")
    value_ref = before_ref if baseline_state in {"available", "unchanged"} else None
    source_refs = _unique_refs([
        _response_ref(before), _response_ref(after), _source_ref(before, before_node), _source_ref(after, after_node)
    ])
    method_ref = _file_ref(Path(__file__).resolve())
    schema_ref = _file_ref(SCHEMA_PATH)
    payload: dict[str, Any] = {
        "schema": "issuer_state_transition.v1",
        "transition_id": "PENDING",
        "issuer_ref": _response_ref(after, selector="/entity"),
        "definition_ref": _development_definition_ref(after, after_node),
        "baseline": {
            "cutoff_ref": _response_ref(before, selector="/receipt/policy"),
            "variables": [{
                "variable_ref": before_ref,
                "state": baseline_state,
                "value_ref": value_ref,
                "reason": baseline_reason,
            }],
        },
        "inputs": [
            _input("before", before, before_node),
            _input("after", after, after_node),
        ],
        "cutoffs": {
            "source_snapshot_at": after["policy"]["source_snapshot_at"],
            "recorded_at": after["policy"]["recorded_at"],
            "selection_policy_ref": target_policy_ref,
        },
        "clocks": {
            "earliest_public_support": _clock(public_clock, "derived_earliest_public_support", target_policy_ref),
            "earliest_system_support": _clock(system_clock, "derived_earliest_system_support", target_policy_ref),
            "reconstructed_at": RECONSTRUCTED_AT,
            "emitted_at": None,
            "reconstruction_mode": "development_reconstruction",
        },
        "comparison": {
            "state": "not_evaluable",
            "before_ref": before_ref,
            "after_ref": after_ref,
            "admission_ref": None,
            "unit_ref": _cell_ref(before if before_node.get("unit") else after, before_node if before_node.get("unit") else after_node, selector="/unit"),
            "before_value": before_node.get("value"),
            "after_value": after_node.get("value"),
            "absolute_change": None,
            "relative_change_exact": None,
            "relative_change_percent": None,
            "percentage_reason": None,
            "refusal_reason": comparison_reason,
        },
        "meaning": {
            "economic_family": "reported_financial_observation",
            "measurement_shape": measurement_shape,
            "interpretation_ref": None,
            "evidence_maturity": "development_golden",
            "lifecycle": "current",
            "limitations": limitations,
        },
        "evidence": evidence,
        "mechanism": [],
        "materiality": [],
        "correction": {
            "relation": "original",
            "previous_derived_refs": [],
            "source_correction_refs": [],
            "reason": None,
        },
        "rights": {
            "state": "not_admitted",
            "decision_refs": [],
            "consumer_purpose_refs": [],
        },
        "authority": {
            "class": "context_only",
            "may_rank": False,
            "may_gate": False,
            "may_size": False,
            "may_originate": False,
            "may_open_entry": False,
            "may_trade": False,
            "may_modify_prophet": False,
        },
        "reproducibility": {
            "source_refs": source_refs,
            "method_sha256": method_ref["content_sha256"],
            "definition_sha256": schema_ref["content_sha256"],
            "semantic_projection_sha256": "0" * 64,
            "canonicalization_ref": method_ref,
            "narrative_ref": None,
        },
    }
    projection = deepcopy(payload)
    projection.pop("transition_id")
    projection["reproducibility"]["semantic_projection_sha256"] = "0" * 64
    projection_hash = _sha(canonical(projection))
    payload["reproducibility"]["semantic_projection_sha256"] = projection_hash
    payload["transition_id"] = f"i3devtransition_{case}_{projection_hash[:24]}"
    return json.loads(canonical(payload))


def build_transitions() -> dict[str, dict[str, Any]]:
    snapshots = _load_snapshots()
    early = snapshots["before_a1_admission"]
    a1 = snapshots["after_a1_before_a2_admission"]
    a2 = snapshots["after_a2_admission"]

    early_revenue = _node(early, "revenue", "duration")
    a1_revenue = _node(a1, "revenue", "duration")
    a2_revenue = _node(a2, "revenue", "duration")
    a1_assets = _node(a1, "total_assets", "instant")
    a2_assets = _node(a2, "total_assets", "instant")

    a1_source = _source_ref(a1, a1_revenue)
    a1_response = _response_ref(a1)
    a2_response = _response_ref(a2)

    return {
        "first_availability_revenue": _build(
            case="first_availability_revenue",
            before=early,
            after=a1,
            before_node=early_revenue,
            after_node=a1_revenue,
            baseline_state="missing",
            baseline_reason=early_revenue["reason"],
            comparison_reason="first system admission changes availability, not economic state",
            measurement_shape="missing_to_available_owner_fact",
            public_clock=a1_revenue["provenance"].get("source_ready_at"),
            system_clock=a1_revenue["provenance"].get("system_ready_at"),
            evidence=[
                {"role": "missing", "ref": None, "dependence_group_ref": None, "limitation": early_revenue["reason"]},
                {"role": "supports", "ref": _cell_ref(a1, a1_revenue), "dependence_group_ref": a1_source, "limitation": "Owner value became system-admitted; this is not an economic increase."},
            ],
            limitations=[
                "Development reconstruction, not a historical emitted alert.",
                "The newly available value must not be compared with a missing baseline as growth.",
                "Rights and transition-schema registration remain unadmitted.",
            ],
        ),
        "unchanged_revenue": _build(
            case="unchanged_revenue",
            before=a1,
            after=a2,
            before_node=a1_revenue,
            after_node=a2_revenue,
            baseline_state="unchanged",
            baseline_reason=None,
            comparison_reason="owner value is unchanged but the I3 comparison definition remains unadmitted",
            measurement_shape="unchanged_same_owner_fact_across_cutoffs",
            public_clock=a2_revenue["provenance"].get("source_ready_at"),
            system_clock=a2_revenue["provenance"].get("system_ready_at"),
            evidence=[
                {"role": "supports", "ref": _cell_ref(a1, a1_revenue), "dependence_group_ref": a1_source, "limitation": "Same underlying SEC occurrence; not independent corroboration."},
                {"role": "supports", "ref": _cell_ref(a2, a2_revenue), "dependence_group_ref": a1_source, "limitation": "Same underlying SEC occurrence; later cutoff does not create a new change."},
            ],
            limitations=[
                "Observed owner value is unchanged across the two recorded cutoffs.",
                "No annual/YoY or economic interpretation is admitted.",
                "Comparison remains fail-closed until owner/source architecture admission.",
            ],
        ),
        "assets_cross_filing_refusal": _build(
            case="assets_cross_filing_refusal",
            before=a1,
            after=a2,
            before_node=a1_assets,
            after_node=a2_assets,
            baseline_state="available",
            baseline_reason=None,
            comparison_reason=REFUSAL,
            measurement_shape="available_to_cross_filing_not_evaluable",
            public_clock=a2_assets["provenance"].get("source_ready_at"),
            system_clock=a2_assets["provenance"].get("system_ready_at"),
            evidence=[
                {"role": "supports", "ref": _cell_ref(a1, a1_assets), "dependence_group_ref": _source_ref(a1, a1_assets), "limitation": "Baseline value remains evidence only; it is not carried forward as current truth."},
                {"role": "missing", "ref": None, "dependence_group_ref": None, "limitation": REFUSAL},
            ],
            limitations=[
                REFUSAL,
                "Merged FIF can resolve a later golden value after its lineage clock, but current lineage disclosure is not trusted for I3 source/correction refs.",
                "No source correction reference is minted by I3.",
            ],
        ),
    }


def main() -> int:
    print(json.dumps(build_transitions(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
