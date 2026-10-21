"""Cross-source candidate-claim consumption; no model/worker/trading execution.

Run only from an explicitly exported source tree with a frozen manifest. A
synthetic direct result and service admission receipt are in-memory fixtures,
NOT installed provider output or completed Supervisor/Runtime evidence.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile


def run(root: Path):
    manifest = json.loads((root / ".source-proof.json").read_text())
    for relative, digest in manifest["files"].items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
    sys.path[:0] = [str(root), str(root / "tests")]

    from brain.decision_research import prepare_context, inference_request
    from brain.decision_research_result import (
        consume_validated_answer, read_original_candidate_claims, ResearchClaimError,
    )
    from brain.fabric_inference_client import FabricInferenceClient, FabricUnavailable
    from control_plane import executive_inference_io as io
    from control_plane import executive_inference_ingress as ingress
    from control_plane.executive_inference_execution import build_execution_binding
    from control_plane.executive_inference_contract import (
        intent_id, validate_direct_result,
    )
    from control_plane.executive_runtime import Runtime
    from integrations.executive_mcp import schemas
    from tests.test_vps_inference_service import GROUND, host_execution_binding
    from test_decision_research import fixture

    snapshot = fixture(rows=2)
    context = prepare_context(
        snapshot, question="What contradicts the preserved thesis?",
        purpose="compare", section_ids=["book_truth", "risk_truth"],
    )
    wire = inference_request(context, task_aware=True)
    assert io.normalize_request(wire) == wire

    operation = "bot-claim-consumer-source-fixture"
    objective = "Read the selected preserved evidence; do not size any trade."
    request = {"operation_key": operation, "objective": objective,
               "inference_request": wire}
    with tempfile.TemporaryDirectory(prefix="bot-claims-source-canary-") as directory:
        root_path = Path(directory)
        runtime = Runtime.at(root_path / "runtime")
        class Grounding:
            def observe(self): return GROUND
        receipt = asyncio.run(ingress.handle_frame(
            {"schema": ingress.SUBMIT_SCHEMA, "request": request,
             "observed_grounding": GROUND},
            runtime=runtime, grounding_provider=Grounding(),
            workspace_root=root_path, admission_guard=lambda _: None,
            execution_binding_provider=lambda identity: build_execution_binding(
                intent_id=identity, workspace_root=root_path, base_sha="a" * 40,
                eligible_quota_classes=("fixture",), inference_request=wire),
        ))
        assert len(runtime.jobs.list_jobs()) == 1
        assert not runtime.attempts.list_attempts(job_id=receipt["job_id"])

        evidence = {
            "schema": "mastermind.bot_research_claims.v1",
            "context_id": context["context_id"],
            "snapshot_id": context["snapshot_id"],
            "claims": [{
                "claim_id": "synthetic-1",
                "statement": "Synthetic account evidence shows a cash entry.",
                "kind": "OBSERVATION", "stance": "NEUTRAL",
                "evidence_refs": ["book_truth:0"], "contrary_refs": ["risk_truth:0"],
                "uncertainty": "UNQUANTIFIED",
                "falsifier": "An independently verified account correction contradicts this row.",
            }],
            "unknowns": ["All uncovered domains and true market outcomes are unknown."],
            "coverage_ack": {
                "selection_complete": context["selection_complete"],
                "selected_rows": sum(s["selected_rows"] for s in context["sections"].values()),
                "unselected_domains": context["unselected_domains"],
            },
        }
        worker = "synthetic-worker"
        attempt = "ATT-" + "a" * 32
        def project(parsed):
            worker_result = {
                "schema_version": io.WORKER_RESULT_SCHEMA,
                "job_id": receipt["job_id"], "run_id": attempt, "worker_id": worker,
                "status": "COMPLETED", "answer": json.dumps(parsed, sort_keys=True),
            }
            reference = io.result_reference(
                job_id=receipt["job_id"], attempt_id=attempt,
                worker_id=worker, result_sha256="c" * 64,
                content_sha256=hashlib.sha256(io.canonical_bytes(worker_result)).hexdigest(),
            )
            document = io.result_document(
                reference=reference, result=worker_result,
                raw_result_sha256="c" * 64, max_output_chars=wire["max_output_chars"],
            )
            view = {
                "schema": "mastermind.fabric_service_inference_result_view.v1",
                "operation_ref": intent_id(operation),
                "reference": reference,
                "request_fingerprint": receipt["fingerprint"],
                "generation": {"schema": "mastermind.runtime_read_observation.v1",
                               "state": "SAME", "source_identity": "b" * 32,
                               "before": 1, "after": 1},
                "availability": "AVAILABLE", "execution_status": "COMPLETED",
                "content_complete": True, "acceptance": "NOT_PROJECTED",
                "document": document,
            }
            envelope = schemas.result_envelope(
                "executive_fabric", mode=schemas.ServerMode.READONLY,
                generated_at="2026-10-12T00:00:00Z", data=view,
                grounding={"source": "SYNTHETIC TEST ONLY"}, degraded=[],
            )
            # Pure validator used against a synthetic read envelope. This
            # cannot establish installed authentication or real completion.
            validated = validate_direct_result(
                envelope, operation_key=operation, receipt=receipt,
                reference=reference, max_output_chars=wire["max_output_chars"],
            )
            return validated, reference

        good, reference = project(evidence)
        consumed = consume_validated_answer(
            context, good,
            expected_operation_ref=intent_id(operation),
            expected_request_fingerprint=receipt["fingerprint"],
            expected_reference=reference,
        )
        assert consumed["candidate_only"] is True
        assert consumed["authority"] == {
            "write_permitted": False, "execution_authority": False,
            "numeric_target_authority": False,
        }
        assert consumed["claims"][0]["evidence_refs"] == ["book_truth:0"]
        assert consumed["artifact_independence"] == "NOT_ESTABLISHED"

        # Exercise the original service client's actual status -> direct read
        # consumer. Only the transport and result producer are fixtures.
        envelope = schemas.result_envelope(
            "executive_fabric", mode=schemas.ServerMode.READONLY,
            generated_at="2026-10-12T00:00:00Z", data=good,
            grounding={"source": "SYNTHETIC TEST ONLY"}, degraded=[],
        )
        calls = []
        async def already_authenticated_fixture(name, args):
            calls.append(name)
            if name == "service_intent_status":
                return {"ok": True, "status": "accepted",
                        "request_ref": intent_id(operation),
                        "receipt": receipt, "terminal_result_ref": reference}
            if name == "executive_fabric":
                assert args == {"view": "service_inference", "operation_key": operation,
                                "reference": reference}
                return envelope
            raise AssertionError("read-only client performed an unexpected action")
        authenticated_fixture_client = FabricInferenceClient(already_authenticated_fixture)
        completed = asyncio.run(read_original_candidate_claims(
            authenticated_fixture_client, original_context=context,
            operation_key=operation, objective=objective,
            original_operation_ref=intent_id(operation),
            original_request_fingerprint=receipt["fingerprint"],
            original_inference_request=wire,
        ))
        assert completed == consumed
        assert calls == ["service_intent_status", "executive_fabric"]

        cases = [{"case": "original_context_to_validated_synthetic_result_to_candidate_claims", "passed": True},
                 {"case": "real_client_status_then_exact_direct_read_consumed_without_submit", "passed": True}]
        for mutation, label in [
            ({"snapshot_id": "sha256:" + "f" * 64}, "changed_snapshot"),
            ({"context_id": "sha256:" + "f" * 64}, "changed_context"),
        ]:
            forged = json.loads(json.dumps(evidence)); forged.update(mutation)
            validated, changed_ref = project(forged)
            try:
                consume_validated_answer(
                    context, validated,
                    expected_operation_ref=intent_id(operation),
                    expected_request_fingerprint=receipt["fingerprint"],
                    expected_reference=changed_ref,
                )
            except ResearchClaimError:
                pass
            else:
                raise AssertionError(label + " was accepted")
            cases.append({"case": label + "_refused_even_with_new_canonical_content_hash", "passed": True})
        for extra, label in [
            ({"target_weight": 0.5}, "numeric_target"),
            ({"execution_authority": True}, "worker_execution_grant"),
        ]:
            forged = json.loads(json.dumps(evidence))
            forged["claims"][0].update(extra)
            validated, changed_ref = project(forged)
            try:
                consume_validated_answer(
                    context, validated,
                    expected_operation_ref=intent_id(operation),
                    expected_request_fingerprint=receipt["fingerprint"],
                    expected_reference=changed_ref,
                )
            except ResearchClaimError:
                pass
            else:
                raise AssertionError(label + " was accepted")
            cases.append({"case": label + "_refused_despite_self_consistent_answer_hash", "passed": True})
        assert len(runtime.jobs.list_jobs()) == 1
        assert not runtime.attempts.list_attempts(job_id=receipt["job_id"])
        cases.append({"case": "claim_consumption_creates_no_worker_attempt_or_portfolio_action", "passed": True})
        return {
            "scope": "Source-only synthetic claim consumption, not provider execution, installed auth, or Runtime direct completion",
            "source_tree": manifest.get("integration_tree", "LOCAL_UNCOMMITTED_SOURCE"),
            "passed": len(cases), "cases": cases,
            "original_job_id": receipt["job_id"],
            "snapshot_id": snapshot["snapshot_id"],
            "context_id": context["context_id"],
            "candidate_id": consumed["claim_set_id"],
        }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: bot_research_claim_consumption_canary.py INTEGRATED_SOURCE_ROOT")
    print(json.dumps(run(Path(sys.argv[1]).resolve()), indent=2))
