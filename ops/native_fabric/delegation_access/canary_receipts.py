#!/usr/bin/env python3
"""Fail-closed *receipt consistency* assertions for post-merge Fabric canaries.

No workers, retries, acknowledgments, acceptances, provider accounts or native
code changes. Supplied JSON is UNTRUSTED until independently read from the
canonical Fabric owner. Successful shape validation does NOT prove live runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

SCHEMA = "mastermind.fabric_access_canary_receipts.v1"
# Fixed, harmless C0 worker inputs. The return must contain ONLY the computed
# digest (surrounding whitespace permitted), not a prompt echo or claim of rc=0.
CANARY_INPUTS = {
    "claude": "MMX_FABRIC_CLAUDE_CANARY_V1",
    "codex": "MMX_FABRIC_CODEX_CANARY_V1",
    "operator.child": "MMX_FABRIC_OPERATOR_CHILD_CANARY_V1",
}
EXPECTED_COMPUTATIONS = {
    case: hashlib.sha256(payload.encode("utf-8")).hexdigest()
    for case, payload in CANARY_INPUTS.items()
}
HEX40 = re.compile(r"^[a-f0-9]{40}$")
HEX64 = re.compile(r"^[a-f0-9]{64}$")
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


def _require(ok: bool, issues: list[str], label: str) -> None:
    if not ok:
        issues.append(label)


def _good_id(value: object) -> bool:
    return isinstance(value, str) and ID.fullmatch(value) is not None


def _good_sha(value: object, pattern=HEX64) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _status_envelope(value: object) -> tuple[dict, bool]:
    """Unwrap typed Fabric status without inventing root verification."""
    if not isinstance(value, dict):
        return {}, False
    if value.get("action") == "fabric_status":
        sub = value.get("status")
        return sub if isinstance(sub, dict) else {}, value.get("root_verified") is True
    return value, False


def _check_run(
    record: object, issues: list[str], prefix: str, *,
    expected_root: str, expected_parent: str, expected_generation: str,
    expected_computation: str | None = None,
) -> tuple[str | None, str | None]:
    if not isinstance(record, dict):
        issues.append(prefix + ".missing")
        return None, None
    run_id = record.get("run_id")
    _require(_good_id(run_id), issues, prefix + ".run_id")
    start = record.get("start_receipt")
    _require(isinstance(start, dict) and start.get("run_id") == run_id
             and start.get("root_id") == expected_root
             and start.get("parent_run_id") == expected_parent
             and start.get("state") in ("STARTED", "RUNNING")
             and isinstance(start.get("host"), str) and bool(start.get("host"))
             and _good_sha(start.get("support_sha256")),
             issues, prefix + ".canonical_start_receipt")
    status, root_verified = _status_envelope(record.get("status"))
    _require(root_verified and status.get("root_id") == expected_root,
             issues, prefix + ".root_verified")
    _require(status.get("run_id") == run_id, issues, prefix + ".status_run_id")
    _require(status.get("parent_run_id") == expected_parent, issues, prefix + ".parent")
    _require(status.get("state") == "TERMINAL"
             and type(status.get("rc")) is int and status["rc"] == 0
             and status.get("result_available") is True, issues, prefix + ".terminal_result")
    result = record.get("result")
    if not isinstance(result, dict):
        result = {}
    digest = result.get("response_sha256")
    _require(result.get("root_id") == expected_root and
             result.get("accept_run_id", result.get("run_id")) == run_id,
             issues, prefix + ".result_lineage")
    _require(_good_sha(digest) and type(result.get("response_bytes")) is int
             and result.get("response_bytes") > 0
             and isinstance(result.get("adapter_response"), str)
             and len(result["adapter_response"].encode("utf-8")) > 0,
             issues, prefix + ".result_payload")
    # The adapter can hash a framed CLI response; do not infer that response_sha256
    # equals SHA256 of adapter_response's human-facing text preview.
    # C0 answers, in contrast, are constrained to an exact SHA256 calculation.
    # Checking the returned answer's *content* prevents receipt-only success.
    if expected_computation is not None:
        _require(
            isinstance(result.get("adapter_response"), str)
            and result["adapter_response"].strip() == expected_computation,
            issues, prefix + ".computed_task_result",
        )
    parent_return = record.get("parent_return")
    if not isinstance(parent_return, dict):
        parent_return = {}
    _require(parent_return.get("run_id") == run_id
             and parent_return.get("principal_parent_id") == expected_parent
             and parent_return.get("result_sha256") == digest
             and parent_return.get("reviewed") is True,
             issues, prefix + ".returned_to_immediate_parent")
    accepted = record.get("acceptance")
    if not isinstance(accepted, dict):
        accepted = {}
    _require(accepted.get("accepted") is True
             and accepted.get("accepted_by") in ("reviewer", "deterministic")
             and accepted.get("reviewed_response_sha256") == digest,
             issues, prefix + ".principal_acceptance")
    _require(record.get("observed_generation") == expected_generation,
             issues, prefix + ".observed_native_generation")
    return run_id if _good_id(run_id) else None, digest if _good_sha(digest) else None


def evaluate(report: object) -> dict[str, object]:
    issues: list[str] = []
    if not isinstance(report, dict):
        return {"state": "REFUSED", "issues": ["report.not_an_object"],
                "live_proven": False, "launches": 0}
    _require(report.get("schema") == SCHEMA, issues, "schema")
    merged = report.get("merged_source_sha")
    generation = report.get("selected_generation")
    _require(_good_sha(merged, HEX40), issues, "merged_source_sha")
    _require(_good_sha(generation), issues, "selected_generation")
    _require(report.get("source_merge_provenance") == "verified_protected_master_readback",
             issues, "source_merge_provenance")
    _require(report.get("runtime_generation_provenance") == "verified_selected_runtime_readback",
             issues, "runtime_generation_provenance")
    cases = report.get("cases")
    if not isinstance(cases, dict):
        cases = {}
    all_runs: list[str] = []
    session_ids: list[str] = []
    case_roots: list[str] = []
    case_parents: list[str] = []
    for kind in ("claude", "codex"):
        c = cases.get(kind)
        if not isinstance(c, dict):
            issues.append(kind + ".missing")
            continue
        root = c.get("root_id")
        parent = c.get("immediate_parent_id")
        _require(_good_id(root) and _good_id(parent)
                 and c.get("parent_identity_verified") is True,
                 issues, kind + ".verified_original_root_and_parent")
        if _good_id(root):
            case_roots.append(root)
        if _good_id(parent):
            case_parents.append(parent)
        loaded = c.get("skill_session")
        if not isinstance(loaded, dict):
            loaded = {}
        _require(loaded.get("principal") == kind
                 and loaded.get("loaded") is True
                 and _good_id(loaded.get("session_id"))
                 and _good_sha(loaded.get("skill_sha256")),
                 issues, kind + ".real_session_skill_load")
        if _good_id(loaded.get("session_id")):
            session_ids.append(loaded["session_id"])
        run, _ = _check_run(c.get("worker"), issues, kind,
                            expected_root=root, expected_parent=parent,
                            expected_generation=generation,
                            expected_computation=EXPECTED_COMPUTATIONS[kind])
        if run:
            all_runs.append(run)

    nested = cases.get("operator")
    if not isinstance(nested, dict):
        issues.append("operator.missing")
        nested = {}
    op_root = nested.get("root_id")
    op_parent = nested.get("immediate_parent_id")
    _require(_good_id(op_root) and _good_id(op_parent)
             and nested.get("parent_identity_verified") is True,
             issues, "operator.verified_original_root_and_parent")
    if _good_id(op_root):
        case_roots.append(op_root)
    if _good_id(op_parent):
        case_parents.append(op_parent)
    scope = nested.get("scope")
    if not isinstance(scope, dict):
        scope = {}
    opid = scope.get("operator_run")
    _require(scope.get("root") == op_root and _good_id(opid)
             and type(scope.get("child_budget_at_admission")) is int
             and scope.get("child_budget_at_admission") > 0
             and scope.get("grant_verified") is True,
             issues, "operator.admitted_scope")
    operator, _ = _check_run(nested.get("operator_run"), issues, "operator",
                              expected_root=op_root, expected_parent=op_parent,
                              expected_generation=generation)
    if operator:
        all_runs.append(operator)
    _require(operator == opid, issues, "operator.scope_parent_identity")
    child, child_digest = _check_run(nested.get("child_run"), issues, "operator.child",
                                       expected_root=op_root, expected_parent=opid,
                                       expected_generation=generation,
                                       expected_computation=EXPECTED_COMPUTATIONS["operator.child"])
    # The operator must return the *child transport digest* to the original
    # principal, not merely a claim of having delegated. This still requires
    # canonical Fabric readback; the JSON report itself is not authenticated.
    operator_record = nested.get("operator_run")
    operator_result = operator_record.get("result") if isinstance(operator_record, dict) else {}
    operator_response = operator_result.get("adapter_response") if isinstance(operator_result, dict) else None
    _require(isinstance(operator_response, str) and _good_sha(child_digest)
             and re.search(r"(?<![0-9a-f])" + re.escape(child_digest) + r"(?![0-9a-f])",
                           operator_response) is not None,
             issues, "operator.child_digest_returned_to_principal")
    # The digest of the framed Fabric response and the digest computed by a
    # worker over the fixed literal represent different evidence domains.
    # A fabricated receipt cannot equate them and still pass.
    _require(_good_sha(child_digest)
             and child_digest != EXPECTED_COMPUTATIONS["operator.child"],
             issues, "operator.distinct_child_transport_digest")
    if child:
        all_runs.append(child)
    ack = nested.get("child_acknowledgment")
    if not isinstance(ack, dict):
        ack = {}
    _require(ack.get("run_id") == child
             and ack.get("acknowledged") is True
             and ack.get("sha256") == child_digest
             and ack.get("parent_run_id") == operator,
             issues, "operator.same_parent_child_ack")
    _require(nested.get("principal_adjudicated_operator_result") is True,
             issues, "operator.return_to_original_principal")
    # These three independently commissioned canaries must not borrow another
    # principal's root or immediate parent. Distinct run/session IDs alone are
    # insufficient evidence of independent session lineage.
    _require(len(case_roots) == 3 and len(set(case_roots)) == 3
             and len(case_parents) == 3 and len(set(case_parents)) == 3,
             issues, "distinct_case_identities")
    _require(len(all_runs) == 4 and len(set(all_runs)) == 4,
             issues, "four_distinct_run_ids")
    _require(len(session_ids) == 2 and len(set(session_ids)) == 2,
             issues, "distinct_claude_codex_sessions")
    return {"state": "ASSERTIONS_PASS_PROVENANCE_NOT_VERIFIED" if not issues else "REFUSED",
            "issues": issues, "live_proven": False,
            "launches": 0, "run_ids_inspected": all_runs,
            "warning": "Only source-authoritative independent live readback proves execution."}


def _no_duplicate_keys(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate receipt JSON key: " + key)
        output[key] = value
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts", type=Path, required=True)
    args = parser.parse_args()
    if args.receipts.is_symlink() or not args.receipts.is_file():
        print(json.dumps({"state": "REFUSED", "issues":["receipt.file_kind"],
                          "live_proven": False}))
        return 78
    if args.receipts.stat().st_size > 64000:
        print(json.dumps({"state": "REFUSED", "issues":["receipt.oversize"],
                          "live_proven": False}))
        return 78
    try:
        payload = json.loads(args.receipts.read_text(), object_pairs_hook=_no_duplicate_keys)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        print(json.dumps({"state":"REFUSED", "issues":["receipt.unreadable_or_ambiguous"],
                          "live_proven": False, "reason":str(exc)}))
        return 78
    result = evaluate(payload)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["state"] == "ASSERTIONS_PASS_PROVENANCE_NOT_VERIFIED" else 78


if __name__ == "__main__":
    sys.exit(main())
