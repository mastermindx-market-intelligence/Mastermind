"""H24-09 source fixtures; no provider, native DB, service or conversation use."""
from concurrent.futures import ThreadPoolExecutor
import ast
import copy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from integrations.hermes_secretary import checkpoint_projection as projection


NOW = 1_793_960_000
BASE = "b54cb10e4abdd3766c62d4088f6a576ecfe80437"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def seal(value):
    value = copy.deepcopy(value)
    value.pop("snapshot_sha256", None)
    value["snapshot_sha256"] = digest(value)
    return value


def request_keys(original):
    if original["kind"] == "HERMES_SECRETARY":
        original["operation_key"] = "session-continue-" + digest({
            "schema": "mastermind.session_bridge.hermes_secretary_operation.v1",
            "target_ref": original["target_ref"]})
    key = digest({"schema": "mastermind.session_bridge.continue_request.v1",
                  "operation_key": original["operation_key"]})
    original["request_ref"] = "session-bridge-continue:" + key
    original["read_ref"] = "session-reply-" + key
    original["submission_id"] = "session-secretary-" + key if original["kind"] == "HERMES_SECRETARY" else None


def facts():
    """Synthetic owner-normalized original request, with no fabricated Attempt."""
    value = {
        "schema": projection.FACTS_SCHEMA,
        "native": {"role": "mmsecretary", "profile_sha256": "1" * 64,
            "session_sha256": "2" * 64, "principal_sha256": "3" * 64,
            "instance_sha256": "4" * 64, "authority_epoch": 7,
            "revision": 12, "execution_generation": 3},
        "runtime": {"root_id": "root-h24-fixture", "root_job_id": "JOB-001",
            "work_ref": "WS:HERMES-H24", "job_id": None, "attempt_id": None,
            "parent_job_id": None, "attempt_status": "NOT_APPLICABLE", "root_status": "RUNNING"},
        "original": {"kind": "HERMES_SECRETARY", "principal_sha256": "5" * 64,
            "target_ref": "hermes_secretary:" + "6" * 64, "operation_key": "pending",
            "request_ref": "pending", "request_revision": "7" * 64, "read_ref": "pending",
            "input_sha256": "8" * 64, "native_input_sha256": "9" * 64,
            "binding_sha256": "a" * 64, "submission_id": "pending", "commit_status": "COMMITTED",
            "admission_id": "native-admission-001", "admission_sequence": 1,
            "admission_epoch": 7, "admission_generation": 3, "admission_status": "terminal"},
        "authority": {"principal_sha256": "5" * 64, "generation": 11,
            "read_permitted": True, "approval_status": "CURRENT"},
        "source": {"repository": "mastermindx-market-intelligence/Mastermind", "ref": BASE,
            "path": "docs/GROK_SECRETARY_TEAM_INTEGRATION.md", "sha256": "b" * 64},
        "context": {"message_checkpoint_ref": "native-message-001",
            "message_checkpoint_sha256": "c" * 64, "compaction_generation": 0},
        "return": {"result_status": "RETAINED", "result_ref": "owner-result-001",
            "result_sha256": "d" * 64, "result_outcome": "SUCCESS", "parent_request_ref": "pending",
            "parent_terminal_ref": "owner-return-001", "parent_terminal_sha256": "e" * 64,
            "consumption_status": "UNKNOWN", "consumption_ref": None,
            "executive_acceptance": "NOT_OBSERVED", "acceptance_ref": None},
        "observation": {"source_identity": "f" * 32, "generation_before": 51,
            "generation_after": 51, "read_state": "CURRENT", "observed_at": NOW - 1,
            "valid_until": NOW + 30, "write_uncertainty": "NONE", "omitted_count": 0,
            "receipt_schema": "mastermind.runtime_read_observation.v1", "receipt_state": "SAME", "finalized": True},
    }
    request_keys(value["original"])
    value["return"]["parent_request_ref"] = value["original"]["request_ref"]
    return seal(value)


def child_facts():
    value = facts()
    value["runtime"].update(job_id="JOB-002", attempt_id="ATT-001", parent_job_id="JOB-001",
                            attempt_status="COMPLETED")
    value["original"].update(kind="NATIVE_CONTINUATION", target_ref="fabric-session-fixture",
        operation_key="hermes-native-return-001", native_input_sha256=None, admission_id=None,
        admission_sequence=None, admission_epoch=None, admission_generation=None, admission_status=None)
    request_keys(value["original"])
    value["return"]["parent_request_ref"] = value["original"]["request_ref"]
    value["return"]["consumption_status"] = "UNCONSUMED"
    return seal(value)


def pending(value=None):
    value = copy.deepcopy(value or facts())
    value["original"]["admission_status"] = "started"
    value["return"].update(result_status="PENDING", result_ref=None, result_sha256=None,
        result_outcome="UNKNOWN", parent_terminal_ref=None, parent_terminal_sha256=None)
    return seal(value)


def restart(value):
    value = copy.deepcopy(value)
    value["native"].update(instance_sha256="0" * 64, authority_epoch=8)
    value["observation"].update(generation_before=52, generation_after=52)
    return seal(value)


def owner_returns(*, status="OBSERVED", admission_status="terminal",
                  answer="Original owner answer.", successful=True, commit_started=True):
    """Exercise real owner value constructors; no reader, DB or native service."""
    from control_plane.executive_runtime import RuntimeReadObservationReceipt
    from integrations.session_bridge.hermes_native import public_result, validate_public_result

    source = facts()
    original = source["original"]
    event_value = {"event_id": 2, "command_id": original["request_ref"]}
    event = SimpleNamespace(command_id=original["request_ref"], to_dict=lambda: event_value)
    binding = {"profile_id": "/fixture/mmsecretary", "session_id": "native-fixture-001"}
    native = None
    if status is not None:
        native = {"schema": "mastermind.hermes_secretary_native_control/v1", "status": status}
        if status in {"OBSERVED", "ADMITTED"}:
            native["admission"] = {"admission_id": original["admission_id"], "ref": binding,
                "sequence": 1, "status": admission_status, "outcome": "completed",
                "authority_epoch": 7, "execution_generation": 3}
            if status == "OBSERVED" and answer is not None:
                native.update(answer=answer, successful=successful)
    returned = public_result(event, {**original, "binding": binding},
                             commit_started=commit_started, native_result=native)
    assert validate_public_result(returned) == returned
    source["original"]["request_revision"] = returned["request_revision"]
    metadata = {"schema": projection.METADATA_SCHEMA,
        **{key: source[key] for key in ("native", "runtime", "authority", "source", "context")},
        "original": {key: source["original"][key] for key in (
            "kind", "principal_sha256", "target_ref", "operation_key", "request_ref",
            "request_revision", "read_ref", "input_sha256", "native_input_sha256",
            "binding_sha256", "submission_id")},
        "parent": None,
        "observation": {"finalized": True, "read_state": "CURRENT", "omitted_count": 0,
            "observed_at": NOW - 1, "valid_until": NOW + 30, "write_uncertainty": "NONE"}}
    receipt = RuntimeReadObservationReceipt(schema="mastermind.runtime_read_observation.v1",
        state="SAME", source_identity="f" * 32, before=51, after=51).to_dict()
    return metadata, returned, receipt


def native_owner_returns(*, by_operation=False):
    """Use the real reader with an in-memory read-only transport fixture."""
    import asyncio
    from control_plane.executive_runtime import RuntimeReadObservationReceipt
    from control_plane.principal_projection import neutral_principal_projection
    from integrations.session_bridge.native_read import NativeReplyReader, NativeReplyReadBinding
    from integrations.slack_agent_dialogue.contract_v2 import MESSAGE_SCHEMA_V2, build_message_v2
    from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2

    source = child_facts()
    original = source["original"]
    principal = neutral_principal_projection(policy_id="h24-read", issuer="https://auth.example.test/",
        issuer_digest=hashlib.sha256(b"https://auth.example.test/").hexdigest(),
        resource="https://executive.example.test/mcp", subject_digest="1" * 64, client_ref="2" * 64,
        scopes=("mastermind.executive.read",), issued_at=NOW - 60, expires_at=NOW + 60, jti_digest=None)
    identity = {key: getattr(principal, key) for key in
                ("policy_id", "issuer_digest", "resource", "subject_digest", "client_ref")}
    principal_hash = digest({"field": "executive_principal", "value": identity})
    source["authority"]["principal_sha256"] = original["principal_sha256"] = principal_hash
    request_key = "asd-executive-continue-h24-0001"
    applies = {"kind": "executive_attempt", "job_id": "JOB-002", "attempt_id": "ATT-001", "worker_id": "W-001"}
    context = DialogueContextV2(work_ref=source["runtime"]["work_ref"],
        commission_ref={"repository": source["source"]["repository"], "commit": BASE,
            "path": source["source"]["path"], "content_sha256": source["source"]["sha256"]},
        session_ref="asd-session-h24-continuity-001", operation_key=original["operation_key"],
        watch_mode="turn_watch_v1", actor_ref={**applies, "kind": "worker_attempt"}, applies_to=applies)
    normalized = context.normalized()
    message = build_message_v2({"schema": MESSAGE_SCHEMA_V2,
        "message_key": "asd-native-reply-h24-0001", "message_type": "PROGRESS",
        **{key: normalized[key] for key in ("work_ref", "commission_ref", "session_ref", "actor_ref", "applies_to")},
        "reply_to_message_key": request_key, "summary": "Synthetic original child reply.",
        "body": {"stage": "message_reply", "completed": "Original child evidence \u03b1.",
                 "next": "Await the parent's bounded decision."},
        "evidence_refs": [], "requires_response": False, "created_at": "2026-11-06T00:00:00Z"})
    thread_ts = "1793923200.000001"
    binding = NativeReplyReadBinding(authorized_principal=principal, read_ref=original["read_ref"],
        request_ref=original["request_ref"], request_message_key=request_key, thread_ts=thread_ts,
        reply_message_key=message["message_key"], reply_fingerprint=message["fingerprint"],
        context=context, authorization_revision="authorization-h24-001")
    resolver = SimpleNamespace(resolve_read=lambda **kwargs: binding,
                               resolve_operation_read_ref=lambda **kwargs: original["read_ref"])
    calls = []

    async def read_service(path, payload):
        assert payload["operation"] == "read_thread"
        calls.append(payload["operation"])
        return {"ok": True, "result": {"thread_ts": thread_ts, "historical_messages": [],
            "mutated_count": 0, "messages": [{"message": message, "primary_ts": "1793923201.000001"}]}}

    reader = NativeReplyReader(resolver, socket_path=Path("/fixture/never-opened.sock"),
        service_call=read_service, clock=lambda: NOW, projected_principal=True)
    selector = {"operation_key": original["operation_key"]} if by_operation else {"read_ref": original["read_ref"]}
    returned = asyncio.run(reader(principal, selector))
    metadata = {"schema": projection.METADATA_SCHEMA,
        **{key: source[key] for key in ("native", "runtime", "authority", "source", "context", "original")},
        "parent": None, "observation": {"finalized": True, "read_state": "CURRENT", "omitted_count": 0,
            "observed_at": NOW - 1, "valid_until": NOW + 30, "write_uncertainty": "NONE"}}
    receipt = RuntimeReadObservationReceipt(schema="mastermind.runtime_read_observation.v1",
        state="SAME", source_identity="f" * 32, before=51, after=51).to_dict()
    assert calls == ["read_thread"]
    return metadata, returned, receipt, request_key


class CheckpointProjectionTests(unittest.TestCase):
    def setUp(self):
        self.saved = facts()
        self.manifest = projection.build_checkpoint(self.saved)

    def recover(self, current=None, *, before=None, manifest=None, now=NOW):
        current = self.saved if current is None else current
        manifest = self.manifest if manifest is None else manifest
        return projection.project_recovery(manifest, expected_sha256=manifest.sha256,
            before=current if before is None else before, after=current, now=now)

    def refused(self, changed, reason):
        outcome = self.recover(seal(changed))
        self.assertEqual((outcome.state, outcome.reason), ("REFUSED", reason))
        self.assertIsNone(outcome.result_ref)
        self.assertIsNone(outcome.read_ref)
        self.assertFalse(outcome.can_write)
        self.assertFalse(outcome.can_resume_execution)

    def test_recovers_original_reference_without_attempt_fabrication(self):
        outcome = self.recover()
        self.assertEqual(outcome.state, "RECOVER_ORIGINAL_RESULT")
        self.assertEqual(outcome.read_ref, self.saved["original"]["read_ref"])
        self.assertIsNone(outcome.attempt_id)
        self.assertEqual(outcome.executive_acceptance, "NOT_OBSERVED")

    def test_resume_after_clean_gateway_restart_preserves_original_admission_epoch(self):
        current = restart(self.saved)
        outcome = self.recover(current)
        self.assertEqual(outcome.state, "RECOVER_ORIGINAL_RESULT")
        self.assertTrue(outcome.gateway_restarted)
        self.assertEqual(current["original"]["admission_epoch"], 7)
        self.assertEqual(outcome.request_ref, self.saved["original"]["request_ref"])
        self.assertFalse(outcome.can_resume_execution)

    def test_retained_original_does_not_require_live_target_or_writer(self):
        current = copy.deepcopy(self.saved)
        current["native"].update(instance_sha256=None, authority_epoch=None, revision=None, execution_generation=None)
        current = seal(current)
        outcome = self.recover(current)
        self.assertEqual(outcome.state, "RECOVER_ORIGINAL_RESULT")
        self.assertIsNone(outcome.gateway_restarted)
        self.assertIn("NATIVE_CURRENT_TARGET", projection.build_checkpoint(current).as_dict()["omissions"]["metadata_unavailable"])

    def test_stale_native_epoch_is_refused(self):
        current = copy.deepcopy(self.saved)
        current["native"]["authority_epoch"] = 6
        self.refused(current, "STALE_NATIVE_EPOCH")

    def test_epoch_change_without_instance_change_is_refused(self):
        current = copy.deepcopy(self.saved)
        current["native"]["authority_epoch"] = 8
        self.refused(current, "NATIVE_EPOCH_INSTANCE_CONFLICT")

    def test_instance_change_without_epoch_change_is_refused(self):
        current = copy.deepcopy(self.saved)
        current["native"]["instance_sha256"] = "0" * 64
        self.refused(current, "NATIVE_EPOCH_INSTANCE_CONFLICT")

    def test_native_revision_regression_is_refused(self):
        current = copy.deepcopy(self.saved)
        current["native"]["revision"] -= 1
        self.refused(current, "STALE_NATIVE_GENERATION")

    def test_foreign_profile_session_role_and_principal_refuse(self):
        for key in ("profile_sha256", "session_sha256", "principal_sha256", "role"):
            with self.subTest(key=key):
                current = copy.deepcopy(self.saved)
                current["native"][key] = "mmmeta" if key == "role" else "0" * 64
                self.refused(current, "FOREIGN_NATIVE_SCOPE")

    def test_foreign_read_principal_refuses(self):
        current = copy.deepcopy(self.saved)
        current["authority"]["principal_sha256"] = "0" * 64
        self.refused(current, "FOREIGN_PRINCIPAL")

    def test_pending_original_result_has_no_retry_or_new_request(self):
        original = pending()
        outcome = self.recover(original, manifest=projection.build_checkpoint(original))
        self.assertEqual(outcome.state, "AWAIT_ORIGINAL_RESULT")
        self.assertEqual(outcome.read_ref, original["original"]["read_ref"])
        self.assertIsNone(outcome.result_ref)
        self.assertFalse(outcome.can_write)

    def test_pending_result_can_become_retained_on_original_request(self):
        original = pending()
        outcome = self.recover(self.saved, manifest=projection.build_checkpoint(original))
        self.assertEqual(outcome.state, "RECOVER_ORIGINAL_RESULT")

    def test_pending_result_after_restart_stays_same_original(self):
        original = pending()
        outcome = self.recover(restart(original), manifest=projection.build_checkpoint(original))
        self.assertEqual(outcome.state, "AWAIT_ORIGINAL_RESULT")
        self.assertTrue(outcome.gateway_restarted)

    def test_ambiguous_submit_only_reconciles_original(self):
        for status in ("PENDING_SUBMIT", "EFFECT_UNKNOWN"):
            with self.subTest(status=status):
                current = copy.deepcopy(self.saved)
                current["observation"]["write_uncertainty"] = status
                outcome = self.recover(seal(current))
                self.assertEqual((outcome.state, outcome.reason), ("RECONCILE_ORIGINAL", "WRITE_EFFECT_UNCERTAIN"))
                self.assertEqual(outcome.operation_key, self.saved["original"]["operation_key"])
                self.assertFalse(outcome.can_resume_execution)

    def test_missing_admission_is_uncertainty_not_nonexecution(self):
        original = pending()
        original["original"].update(admission_id=None, admission_sequence=None,
            admission_epoch=None, admission_generation=None, admission_status=None)
        original = seal(original)
        outcome = self.recover(original, manifest=projection.build_checkpoint(original))
        self.assertEqual(outcome.reason, "ORIGINAL_ADMISSION_UNPROVEN")
        self.assertEqual(outcome.state, "RECONCILE_ORIGINAL")

    def test_unknown_admission_cannot_be_treated_as_pending(self):
        original = pending()
        original["original"]["admission_status"] = "unknown"
        original = seal(original)
        outcome = self.recover(original, manifest=projection.build_checkpoint(original))
        self.assertEqual(outcome.state, "RECONCILE_ORIGINAL")

    def test_uncommitted_original_never_permits_submission(self):
        original = pending()
        original["original"].update(commit_status="NOT_COMMITTED", admission_id=None,
            admission_sequence=None, admission_epoch=None, admission_generation=None, admission_status=None)
        original = seal(original)
        outcome = self.recover(original, manifest=projection.build_checkpoint(original))
        self.assertEqual(outcome.reason, "ORIGINAL_COMMIT_UNPROVEN")
        self.assertFalse(outcome.can_write)

    def test_retained_result_cannot_return_to_pending(self):
        self.refused(pending(), "ORIGINAL_ADMISSION_REGRESSED")

    def test_changed_admission_is_not_original(self):
        current = copy.deepcopy(self.saved)
        current["original"]["admission_id"] = "native-admission-replacement"
        self.refused(current, "ORIGINAL_ADMISSION_CHANGED")

    def test_invalid_manifest_digest_refuses_without_reference_disclosure(self):
        outcome = projection.project_recovery(self.manifest, expected_sha256="0" * 64,
            before=self.saved, after=self.saved, now=NOW)
        self.assertEqual(outcome.reason, "MANIFEST_DIGEST_MISMATCH")
        self.assertIsNone(outcome.read_ref)

    def test_invalid_owner_snapshot_digest_refuses(self):
        current = copy.deepcopy(self.saved)
        current["runtime"]["root_status"] = "CANCELLED"
        outcome = self.recover(current)
        self.assertEqual(outcome.reason, "SNAPSHOT_DIGEST_MISMATCH")

    def test_partial_snapshot_refuses_even_when_result_is_present(self):
        for state in ("PARTIAL", "HISTORICAL", "UNAVAILABLE"):
            with self.subTest(state=state):
                current = copy.deepcopy(self.saved)
                current["observation"]["read_state"] = state
                self.refused(current, "PARTIAL_OR_NONCURRENT_SNAPSHOT")

    def test_omitted_rows_prevent_currentness(self):
        current = copy.deepcopy(self.saved)
        current["observation"]["omitted_count"] = 1
        self.refused(current, "PARTIAL_OR_NONCURRENT_SNAPSHOT")

    def test_snapshot_expiry_and_future_observation(self):
        self.assertEqual(self.recover(now=NOW + 31).reason, "STALE_OR_FUTURE_SNAPSHOT")
        self.assertEqual(self.recover(now=NOW - 2).reason, "STALE_OR_FUTURE_SNAPSHOT")

    def test_source_revision_and_blob_change_refuse(self):
        for key, value in (("ref", "0" * 40), ("sha256", "0" * 64)):
            with self.subTest(key=key):
                current = copy.deepcopy(self.saved)
                current["source"][key] = value
                self.refused(current, "SOURCE_REVISION_CHANGED")

    def test_new_read_namespace_is_not_a_durable_store_identity(self):
        current = copy.deepcopy(self.saved)
        current["observation"]["source_identity"] = "0" * 32
        current["observation"].update(generation_before=1, generation_after=1)
        self.assertEqual(self.recover(seal(current), before=self.saved).state, "RECOVER_ORIGINAL_RESULT")

    def test_replaced_original_binding_refuses_even_when_other_content_matches(self):
        current = copy.deepcopy(self.saved)
        current["original"]["binding_sha256"] = "0" * 64
        self.refused(current, "ORIGINAL_REQUEST_CHANGED")

    def test_aba_generation_change_with_same_content_refuses(self):
        current = copy.deepcopy(self.saved)
        current["observation"].update(generation_before=53, generation_after=53)
        outcome = self.recover(seal(current), before=self.saved)
        self.assertEqual(outcome.reason, "SOURCE_CHANGED_WITHIN_OBSERVATION")

    def test_changed_same_connection_owner_read_refuses(self):
        current = copy.deepcopy(self.saved)
        current["observation"]["generation_after"] += 1
        self.refused(current, "SOURCE_CHANGED_DURING_READ")

    def test_unfinalized_owner_read_refuses(self):
        current = copy.deepcopy(self.saved)
        current["observation"]["finalized"] = False
        self.refused(current, "OBSERVATION_NOT_FINALIZED")

    def test_unknown_or_conflicting_owner_receipt_refuses(self):
        for state in ("UNKNOWN", "CONFLICT"):
            with self.subTest(state=state):
                current = copy.deepcopy(self.saved)
                current["observation"]["receipt_state"] = state
                self.refused(current, "RUNTIME_OBSERVATION_UNQUALIFIED")

    def test_authority_generation_unavailable_is_not_invented(self):
        current = copy.deepcopy(self.saved)
        current["authority"]["generation"] = None
        current = seal(current)
        self.assertIn("AUTHORITY_GENERATION", projection.build_checkpoint(current).as_dict()["omissions"]["metadata_unavailable"])
        self.refused(current, "AUTHORITY_GENERATION_UNAVAILABLE")

    def test_aba_authority_generation_with_same_grant_refuses(self):
        current = copy.deepcopy(self.saved)
        current["authority"]["generation"] += 2
        self.refused(current, "AUTHORITY_GENERATION_CHANGED")

    def test_parent_changes_during_read_refuse(self):
        current = copy.deepcopy(self.saved)
        current["return"]["consumption_status"] = "DELIVERED"
        outcome = self.recover(seal(current), before=self.saved)
        self.assertEqual(outcome.reason, "OWNER_FACTS_CHANGED_BETWEEN_READS")

    def test_wrong_parent_is_refused(self):
        current = copy.deepcopy(self.saved)
        current["return"]["parent_request_ref"] = "session-bridge-continue:" + "0" * 64
        self.refused(current, "WRONG_PARENT")

    def test_wrong_original_result_digest_is_refused(self):
        current = copy.deepcopy(self.saved)
        current["return"]["result_sha256"] = "0" * 64
        self.refused(current, "ORIGINAL_RESULT_CHANGED")

    def test_child_completed_without_parent_consumption_remains_unaccepted(self):
        original = child_facts()
        outcome = self.recover(original, manifest=projection.build_checkpoint(original))
        self.assertEqual(outcome.state, "RECOVER_ORIGINAL_RESULT")
        self.assertEqual(outcome.consumption_status, "UNCONSUMED")
        self.assertEqual(outcome.executive_acceptance, "NOT_OBSERVED")
        self.assertEqual(outcome.attempt_id, "ATT-001")

    def test_latest_attempt_substitution_is_refused(self):
        original = child_facts()
        changed = copy.deepcopy(original)
        changed["runtime"]["attempt_id"] = "ATT-002"
        outcome = self.recover(seal(changed), manifest=projection.build_checkpoint(original))
        self.assertEqual(outcome.reason, "ORIGINAL_RUNTIME_IDENTITY_CHANGED")

    def test_native_continuation_cannot_omit_its_original_attempt(self):
        original = child_facts()
        original["runtime"].update(job_id=None, attempt_id=None, parent_job_id=None,
                                    attempt_status="NOT_APPLICABLE")
        with self.assertRaisesRegex(projection.CheckpointError, "ORIGINAL_ATTEMPT_SCOPE_MISMATCH"):
            projection.build_checkpoint(seal(original))

    def test_hermes_root_cannot_invent_a_child_attempt(self):
        current = copy.deepcopy(self.saved)
        current["runtime"].update(job_id="JOB-002", attempt_id="ATT-001", parent_job_id="JOB-001",
                                  attempt_status="COMPLETED")
        self.refused(current, "ORIGINAL_ATTEMPT_SCOPE_MISMATCH")

    def test_pending_result_cannot_claim_terminal_return_or_consumption(self):
        for updates in (
            {"parent_terminal_ref": "owner-return-001", "parent_terminal_sha256": "e" * 64},
            {"parent_terminal_ref": "owner-return-001", "parent_terminal_sha256": "e" * 64,
             "consumption_status": "CONSUMED", "consumption_ref": "owner-consumption-001"},
        ):
            with self.subTest(updates=updates):
                original = pending()
                original["return"].update(updates)
                with self.assertRaisesRegex(projection.CheckpointError, "PENDING_TERMINAL_CONTRADICTION"):
                    projection.build_checkpoint(seal(original))

    def test_consumed_terminal_history_survives_result_retention_loss(self):
        current = copy.deepcopy(self.saved)
        current["return"].update(result_status="UNAVAILABLE", result_ref=None, result_sha256=None,
            result_outcome="UNKNOWN", consumption_status="CONSUMED", consumption_ref="owner-consumption-001")
        outcome = self.recover(seal(current))
        self.assertEqual(outcome.state, "EVIDENCE_ONLY")
        self.assertEqual(outcome.consumption_status, "CONSUMED")
        self.assertEqual(outcome.parent_terminal_ref, "owner-return-001")

    def test_delivery_is_neither_consumption_nor_acceptance(self):
        current = copy.deepcopy(self.saved)
        current["return"]["consumption_status"] = "DELIVERED"
        outcome = self.recover(seal(current))
        self.assertEqual(outcome.state, "RECOVER_ORIGINAL_RESULT")
        self.assertEqual(outcome.consumption_status, "DELIVERED")
        self.assertEqual(outcome.executive_acceptance, "NOT_OBSERVED")

    def test_parent_consumption_requires_independent_receipt(self):
        current = copy.deepcopy(self.saved)
        current["return"].update(consumption_status="CONSUMED", consumption_ref="owner-consumption-001")
        outcome = self.recover(seal(current))
        self.assertEqual(outcome.state, "ALREADY_CONSUMED")
        self.assertEqual(outcome.executive_acceptance, "NOT_OBSERVED")

    def test_consumption_claim_without_receipt_refuses(self):
        current = copy.deepcopy(self.saved)
        current["return"]["consumption_status"] = "CONSUMED"
        self.refused(current, "CONSUMPTION_WITHOUT_RECEIPT")

    def test_executive_acceptance_is_only_copied_with_its_receipt(self):
        current = copy.deepcopy(self.saved)
        current["return"].update(executive_acceptance="ACCEPTED", acceptance_ref="executive-acceptance-001")
        outcome = self.recover(seal(current))
        self.assertEqual(outcome.executive_acceptance, "ACCEPTED")
        self.assertEqual(outcome.consumption_status, "UNKNOWN")

    def test_acceptance_claim_without_receipt_refuses(self):
        current = copy.deepcopy(self.saved)
        current["return"]["executive_acceptance"] = "ACCEPTED"
        self.refused(current, "ACCEPTANCE_WITHOUT_RECEIPT")

    def test_read_approval_revoked_refuses_all_result_disclosure(self):
        current = copy.deepcopy(self.saved)
        current["authority"].update(read_permitted=False, approval_status="REVOKED")
        self.refused(current, "READ_AUTHORITY_UNAVAILABLE")

    def test_execution_approval_revoked_preserves_separately_readable_evidence_only(self):
        current = copy.deepcopy(self.saved)
        current["authority"]["approval_status"] = "REVOKED"
        outcome = self.recover(seal(current))
        self.assertEqual(outcome.state, "EVIDENCE_ONLY")
        self.assertIsNone(outcome.read_ref)
        self.assertEqual(outcome.result_ref, self.saved["return"]["result_ref"])
        self.assertFalse(outcome.can_resume_execution)

    def test_revocation_during_read_bracket_refuses(self):
        current = copy.deepcopy(self.saved)
        current["authority"]["read_permitted"] = False
        outcome = self.recover(seal(current), before=self.saved)
        self.assertEqual(outcome.reason, "READ_AUTHORITY_UNAVAILABLE")

    def test_cancelled_root_keeps_terminal_evidence_without_resume(self):
        for status in ("CANCEL_REQUESTED", "CANCELLED"):
            with self.subTest(status=status):
                current = copy.deepcopy(self.saved)
                current["runtime"]["root_status"] = status
                outcome = self.recover(seal(current))
                self.assertEqual((outcome.state, outcome.reason), ("EVIDENCE_ONLY", "ROOT_CANCELLED"))
                self.assertIsNone(outcome.read_ref)
                self.assertEqual(outcome.result_sha256, "d" * 64)
                self.assertEqual(outcome.parent_terminal_ref, "owner-return-001")

    def test_failed_result_remains_original_evidence_not_retry(self):
        original = facts()
        original["return"]["result_outcome"] = "FAILED"
        original = seal(original)
        outcome = self.recover(original, manifest=projection.build_checkpoint(original))
        self.assertEqual(outcome.state, "RECOVER_ORIGINAL_RESULT")
        self.assertFalse(outcome.can_resume_execution)

    def test_unavailable_terminal_result_is_not_reconstructed(self):
        current = copy.deepcopy(self.saved)
        current["return"].update(result_status="UNAVAILABLE", result_ref=None,
            result_sha256=None, result_outcome="UNKNOWN")
        outcome = self.recover(seal(current))
        self.assertEqual((outcome.state, outcome.reason), ("EVIDENCE_ONLY", "RETAINED_RESULT_UNAVAILABLE"))
        self.assertIsNone(outcome.result_ref)
        self.assertEqual(self.manifest.as_dict()["facts"]["return"]["result_sha256"], "d" * 64)

    def test_compaction_changes_context_not_original_request_or_acceptance(self):
        current = copy.deepcopy(self.saved)
        current["context"].update(compaction_generation=1, message_checkpoint_ref="native-message-002",
                                  message_checkpoint_sha256="0" * 64)
        current["native"]["revision"] += 1
        current["observation"].update(generation_before=52, generation_after=52)
        outcome = self.recover(seal(current))
        self.assertEqual(outcome.state, "RECOVER_ORIGINAL_RESULT")
        self.assertTrue(outcome.context_compacted)
        self.assertEqual(outcome.request_ref, self.saved["original"]["request_ref"])
        self.assertEqual(outcome.executive_acceptance, "NOT_OBSERVED")

    def test_checkpoint_reference_change_without_compaction_revision_refuses(self):
        current = copy.deepcopy(self.saved)
        current["context"]["message_checkpoint_sha256"] = "0" * 64
        self.refused(current, "CONTEXT_REFERENCE_CHANGED")

    def test_summary_truncation_keeps_all_required_identity_and_omission_counts(self):
        full = projection.build_checkpoint(self.saved).as_dict()
        for limit in (0, 1, 16, 63):
            with self.subTest(limit=limit):
                manifest = projection.build_checkpoint(self.saved, summary_limit_bytes=limit)
                value = manifest.as_dict()
                self.assertEqual(value["facts"], self.saved)
                self.assertEqual(len(value["summary"]["text"].encode()), limit)
                self.assertEqual(value["summary"]["omitted_bytes"], len(full["summary"]["text"]) - limit)
                self.assertTrue(value["summary"]["truncated"])
                self.assertEqual(self.recover(manifest=manifest).state, "RECOVER_ORIGINAL_RESULT")

    def test_context_over_budget_refuses_whole_manifest(self):
        size = len(self.manifest.canonical_json)
        self.assertEqual(projection.build_checkpoint(self.saved, context_budget_bytes=size), self.manifest)
        with self.assertRaisesRegex(projection.CheckpointError, "CONTEXT_BUDGET_EXCEEDED"):
            projection.build_checkpoint(self.saved, context_budget_bytes=size - 1)

    def test_summary_and_numeric_budgets_reject_bool_and_unbounded_values(self):
        for kwargs in ({"summary_limit_bytes": True}, {"summary_limit_bytes": 1025},
                       {"context_budget_bytes": 0}, {"context_budget_bytes": 16385}):
            with self.subTest(kwargs=kwargs), self.assertRaises(projection.CheckpointError):
                projection.build_checkpoint(self.saved, **kwargs)

    def test_raw_secret_and_transcript_fields_are_not_accepted(self):
        for field in ("prompt", "transcript", "answer", "secret"):
            with self.subTest(field=field):
                current = copy.deepcopy(self.saved)
                current[field] = "private-content-must-never-appear"
                outcome = self.recover(seal(current))
                self.assertEqual(outcome.state, "REFUSED")
                self.assertNotIn("private-content", repr(outcome))

    def test_multibyte_and_control_text_do_not_enter_summary(self):
        for value in ("中文原始提示", "raw\ntranscript", "Bearer secret", "sk-private-value"):
            with self.subTest(value=value):
                current = copy.deepcopy(self.saved)
                current["original"]["operation_key"] = value
                outcome = self.recover(seal(current))
                self.assertEqual(outcome.state, "REFUSED")
                self.assertNotIn(value, repr(outcome))

    def test_summary_forgery_fails_even_with_recomputed_hash(self):
        value = self.manifest.as_dict()
        value["summary"]["text"] = "Replay the old prompt to a new Job."
        with self.assertRaisesRegex(projection.CheckpointError, "UNQUALIFIED_SUMMARY"):
            projection.validate_checkpoint(value, expected_sha256=digest(value))

    def test_omission_forgery_fails_even_with_recomputed_hash(self):
        value = self.manifest.as_dict()
        value["omissions"]["event_history_included"] = True
        with self.assertRaisesRegex(projection.CheckpointError, "UNQUALIFIED_OMISSIONS"):
            projection.validate_checkpoint(value, expected_sha256=digest(value))

    def test_summary_and_omission_booleans_reject_integer_equivalents(self):
        value = self.manifest.as_dict()
        value["summary"]["truncated"] = 0
        with self.assertRaisesRegex(projection.CheckpointError, "UNQUALIFIED_SUMMARY"):
            projection.validate_checkpoint(value, expected_sha256=digest(value))
        value = self.manifest.as_dict()
        value["omissions"]["event_history_included"] = 0
        with self.assertRaisesRegex(projection.CheckpointError, "UNQUALIFIED_OMISSIONS"):
            projection.validate_checkpoint(value, expected_sha256=digest(value))

    def test_missing_required_field_and_bool_counter_refuse(self):
        value = copy.deepcopy(self.saved)
        value["runtime"].pop("attempt_id")
        self.refused(value, "INVALID_FIELDS")
        value = copy.deepcopy(self.saved)
        value["native"]["authority_epoch"] = True
        self.refused(value, "INVALID_COUNTER")

    def test_partial_native_target_and_partial_digest_reference_refuse(self):
        value = copy.deepcopy(self.saved)
        value["native"]["authority_epoch"] = None
        self.refused(value, "PARTIAL_NATIVE_TARGET")
        value = copy.deepcopy(self.saved)
        value["context"]["message_checkpoint_sha256"] = None
        self.refused(value, "PARTIAL_REFERENCE")

    def test_duplicate_json_keys_and_noncanonical_encoding_refuse(self):
        encoded = self.manifest.canonical_json
        duplicate = b'{"schema":"other",' + encoded[1:]
        with self.assertRaises(projection.CheckpointError):
            projection.validate_checkpoint(duplicate, expected_sha256=hashlib.sha256(duplicate).hexdigest())
        with self.assertRaisesRegex(projection.CheckpointError, "NONCANONICAL_MANIFEST"):
            projection.validate_checkpoint(encoded + b"\n", expected_sha256=self.manifest.sha256)

    def test_oversized_and_recursive_input_fail_closed(self):
        value = copy.deepcopy(self.saved)
        value["context"]["message_checkpoint_ref"] = "x" * 2049
        self.refused(value, "INVALID_TEXT")
        recursive = {}
        recursive["cycle"] = recursive
        with self.assertRaisesRegex(projection.CheckpointError, "INPUT_OVER_BUDGET"):
            projection.build_checkpoint(recursive)

    def test_unavailable_metadata_is_explicit_without_fake_attempt(self):
        value = copy.deepcopy(self.saved)
        value["context"].update(message_checkpoint_ref=None, message_checkpoint_sha256=None, compaction_generation=None)
        manifest = projection.build_checkpoint(seal(value))
        missing = manifest.as_dict()["omissions"]["metadata_unavailable"]
        self.assertIn("MESSAGE_CHECKPOINT", missing)
        self.assertIn("COMPACTION_GENERATION", missing)
        self.assertIn("PARENT_CONSUMPTION", missing)
        self.assertIn("EXECUTIVE_ACCEPTANCE", missing)
        self.assertNotIn("RUNTIME_ATTEMPT", missing)  # direct root: not applicable

    def test_manifest_and_result_are_immutable_and_detached(self):
        with self.assertRaises(FrozenInstanceError):
            self.manifest.canonical_json = b"{}"
        detached = self.manifest.as_dict()
        detached["facts"]["runtime"]["root_status"] = "CANCELLED"
        self.assertEqual(self.manifest.as_dict()["facts"]["runtime"]["root_status"], "RUNNING")
        outcome = self.recover()
        with self.assertRaises(FrozenInstanceError):
            outcome.state = "WRITABLE"
        self.assertIs(outcome.as_dict()["can_write"], False)
        self.assertIs(outcome.as_dict()["can_resume_execution"], False)

    def test_direct_value_constructors_reject_mutable_payloads(self):
        with self.assertRaises(projection.CheckpointError):
            projection.CheckpointManifest(bytearray(self.manifest.canonical_json))
        with self.assertRaises(projection.CheckpointError):
            projection.RecoveryProjection("REFUSED", "INVALID", operation_key={})

    def test_duplicate_event_delivery_is_a_repeatable_original_read_projection(self):
        first = self.recover()
        self.assertEqual(first, self.recover())
        self.assertEqual(first, self.recover())
        self.assertEqual(first.read_ref, self.saved["original"]["read_ref"])
        self.assertEqual(self.saved, facts())

    def test_parallel_resume_attempts_share_one_original_without_a_claim_or_lock(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(lambda _: self.recover(), range(24)))
        self.assertEqual(len(set(outcomes)), 1)
        self.assertTrue(all(not value.can_write and not value.can_resume_execution for value in outcomes))
        self.assertEqual(self.saved, facts())

    def test_repeat_evaluation_invokes_no_io(self):
        # Import the test-only modules before blocking their effect entry points.
        import os
        import socket
        import sqlite3
        import subprocess
        before = copy.deepcopy(self.saved)
        with patch("builtins.open", side_effect=AssertionError("file I/O")), \
             patch.object(os, "open", side_effect=AssertionError("file I/O")), \
             patch.object(socket, "socket", side_effect=AssertionError("network")), \
             patch.object(sqlite3, "connect", side_effect=AssertionError("state DB")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("process")):
            for _ in range(3):
                manifest = projection.build_checkpoint(before)
                checked = projection.validate_checkpoint(manifest, expected_sha256=manifest.sha256)
                self.assertEqual(self.recover(before, manifest=checked).state, "RECOVER_ORIGINAL_RESULT")
        self.assertEqual(before, self.saved)

    def test_module_has_only_pure_stdlib_dependencies_and_no_write_surface(self):
        tree = ast.parse(Path(projection.__file__).read_text())
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        imports |= {name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names}
        self.assertEqual(imports, {"__future__", "dataclasses", "hashlib", "hmac", "json", "re"})
        names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertFalse(names & {"write", "send", "submit", "restore", "resume", "retry", "create_job",
                                  "ack", "accept", "consume", "save", "load", "dispatch"})

    def test_runtime_status_vocabulary_matches_incumbent_enum(self):
        root = Path(projection.__file__).resolve().parents[2]
        tree = ast.parse((root / "control_plane/executive_runtime.py").read_text())
        values = {}
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in {"JobStatus", "AttemptStatus"}:
                values[node.name] = {item.value.value for item in node.body
                    if isinstance(item, ast.Assign) and isinstance(item.value, ast.Constant)}
        self.assertEqual(projection._JOB_STATUSES - {"UNAVAILABLE"}, values["JobStatus"])
        self.assertEqual(projection._ATTEMPT_STATUSES - {"UNAVAILABLE", "NOT_APPLICABLE"}, values["AttemptStatus"])

    def test_actual_original_request_derivations_and_public_result_contract(self):
        from control_plane.native_continuation import _hermes_operation_key, _request_key
        from integrations.session_bridge.hermes_native import public_result, validate_public_result

        original = self.saved["original"]
        self.assertEqual(_hermes_operation_key(original["target_ref"]), original["operation_key"])
        self.assertEqual("session-reply-" + _request_key(original["operation_key"]), original["read_ref"])
        event_value = {"event_id": 2, "command_id": original["request_ref"]}
        event = SimpleNamespace(command_id=original["request_ref"], to_dict=lambda: event_value)
        binding = {"profile_id": "/fixture/mmsecretary", "session_id": "native-fixture-001"}
        request = {**original, "binding": binding}
        native = {"schema": "mastermind.hermes_secretary_native_control/v1", "status": "OBSERVED",
            "admission": {"admission_id": original["admission_id"], "ref": binding,
                "sequence": original["admission_sequence"], "status": "terminal", "outcome": "completed",
                "authority_epoch": 7, "execution_generation": 3},
            "answer": "Synthetic original retained answer.", "successful": True}
        owner_result = public_result(event, request, commit_started=True, native_result=native)
        self.assertEqual(validate_public_result(owner_result), owner_result)
        self.assertIs(owner_result["parent_consumed"], False)
        normalized = copy.deepcopy(self.saved)
        normalized["original"]["request_revision"] = owner_result["request_revision"]
        normalized["return"]["result_sha256"] = digest(owner_result)
        normalized["return"]["consumption_status"] = "UNKNOWN"  # false is not a proof of nonconsumption
        normalized = seal(normalized)
        manifest = projection.build_checkpoint(normalized)
        self.assertNotIn(native["answer"].encode(), manifest.canonical_json)
        self.assertNotIn(binding["profile_id"].encode(), manifest.canonical_json)
        self.assertEqual(self.recover(normalized, manifest=manifest).state, "RECOVER_ORIGINAL_RESULT")


class OwnerReturnCompositionTests(unittest.TestCase):
    def compose(self, metadata, returned, receipt):
        return projection.project_hermes_owner_facts(metadata, original_result=returned,
                                                    runtime_receipt=receipt)

    def recover(self, metadata, returned, receipt):
        current = self.compose(metadata, returned, receipt)
        manifest = projection.build_checkpoint_from_hermes_returns(metadata,
            original_result=returned, runtime_receipt=receipt)
        return projection.project_recovery(manifest, expected_sha256=manifest.sha256,
                                           before=current, after=current, now=NOW)

    def test_actual_owner_returns_construct_checkpoint_without_manual_sealing(self):
        metadata, returned, receipt = owner_returns()
        value = self.compose(metadata, returned, receipt)
        self.assertEqual(value["return"]["result_ref"], returned["read_ref"])
        self.assertEqual(value["return"]["result_sha256"], digest(returned))
        self.assertEqual(value["snapshot_sha256"], seal(value)["snapshot_sha256"])
        self.assertEqual(value["return"]["consumption_status"], "UNKNOWN")
        self.assertEqual(value["return"]["executive_acceptance"], "NOT_OBSERVED")
        self.assertEqual(self.recover(metadata, returned, receipt).state, "RECOVER_ORIGINAL_RESULT")

    def test_consumed_hermes_wire_contract_matches_existing_owner(self):
        from integrations.session_bridge import hermes_native
        self.assertEqual(projection._HERMES_RESULT_SCHEMA, hermes_native.RESULT_SCHEMA)
        self.assertEqual(projection._HERMES_RESULT_KEYS, hermes_native._RESULT_FIELDS)
        self.assertEqual(projection._ADMISSION_KEYS, hermes_native._ADMISSION_FIELDS)
        self.assertEqual(projection._HERMES_RESULT_BYTES, hermes_native.MAX_PUBLIC_RESULT_BYTES)

    def test_raw_unicode_answer_and_freeform_outcome_never_enter_manifest(self):
        metadata, returned, receipt = owner_returns(answer="Private answer \u03b1\n\t\U0001f600")
        returned["admission"]["outcome"] = "private-outcome-\u03b2"
        manifest = projection.build_checkpoint_from_hermes_returns(metadata,
            original_result=returned, runtime_receipt=receipt)
        text = manifest.canonical_json.decode()
        for fragment in ("Private answer", "private-outcome", "/fixture/mmsecretary", "successful"):
            self.assertNotIn(fragment, text)
        self.assertEqual(manifest.as_dict()["facts"]["return"]["result_sha256"], digest(returned))

    def test_empty_answer_is_retained_and_false_success_is_failed_evidence(self):
        for answer, successful in (("", True), ("failure evidence", False)):
            with self.subTest(answer=answer, successful=successful):
                metadata, returned, receipt = owner_returns(answer=answer, successful=successful)
                value = self.compose(metadata, returned, receipt)
                self.assertEqual(value["return"]["result_status"], "RETAINED")
                self.assertEqual(value["return"]["result_outcome"], "SUCCESS" if successful else "FAILED")
                self.assertEqual(self.recover(metadata, returned, receipt).state, "RECOVER_ORIGINAL_RESULT")

    def test_queued_and_started_result_remain_pending_original_reads(self):
        for status in ("ADMITTED", "OBSERVED"):
            for admission_status in ("queued", "started"):
                with self.subTest(status=status, admission_status=admission_status):
                    inputs = owner_returns(status=status, admission_status=admission_status, answer=None)
                    value = self.compose(*inputs)
                    self.assertEqual(value["return"]["result_status"], "PENDING")
                    self.assertIsNone(value["return"]["result_sha256"])
                    self.assertEqual(self.recover(*inputs).state, "AWAIT_ORIGINAL_RESULT")

    def test_terminal_without_retained_answer_does_not_fabricate_result(self):
        inputs = owner_returns(answer=None)
        value = self.compose(*inputs)
        self.assertEqual(value["return"]["result_status"], "UNAVAILABLE")
        self.assertIsNone(value["return"]["result_ref"])
        self.assertEqual(self.recover(*inputs).reason, "RETAINED_RESULT_UNAVAILABLE")

    def test_unknown_or_missing_admission_is_original_reconciliation(self):
        cases = [owner_returns(status=None),
                 owner_returns(admission_status="unknown", answer=None)]
        for inputs in cases:
            self.assertEqual(self.compose(*inputs)["return"]["result_status"], "UNKNOWN")
            self.assertEqual(self.recover(*inputs).state, "RECONCILE_ORIGINAL")

    def test_owner_uncertainty_cannot_be_cleared_by_metadata(self):
        inputs = owner_returns(status="EFFECT_UNKNOWN")
        self.assertEqual(self.compose(*inputs)["observation"]["write_uncertainty"], "EFFECT_UNKNOWN")
        self.assertEqual(self.recover(*inputs).reason, "WRITE_EFFECT_UNCERTAIN")
        for uncertainty in ("PENDING_SUBMIT", "EFFECT_UNKNOWN"):
            metadata, returned, receipt = owner_returns()
            metadata["observation"]["write_uncertainty"] = uncertainty
            self.assertEqual(self.compose(metadata, returned, receipt)["observation"]["write_uncertainty"],
                             uncertainty)
            self.assertEqual(self.recover(metadata, returned, receipt).state, "RECONCILE_ORIGINAL")

    def test_uncommitted_or_refused_return_cannot_authorize_resubmission(self):
        cases = [owner_returns(status=None, commit_started=False)]
        cases += [owner_returns(status=status) for status in ("NOT_SUBMITTED", "REFUSED", "UNAVAILABLE")]
        for inputs in cases:
            outcome = self.recover(*inputs)
            self.assertEqual(outcome.state, "RECONCILE_ORIGINAL")
            self.assertFalse(outcome.can_write)
            self.assertFalse(outcome.can_resume_execution)

    def test_all_original_result_joins_are_checked(self):
        for key in ("target_ref", "operation_key", "read_ref", "request_ref",
                    "request_revision", "native_input_sha256"):
            with self.subTest(key=key):
                metadata, returned, receipt = owner_returns()
                returned[key] = "foreign"
                with self.assertRaisesRegex(projection.CheckpointError, "OWNER_RESULT_ORIGINAL_MISMATCH"):
                    self.compose(metadata, returned, receipt)

    def test_parent_consumption_requires_separate_owner_metadata(self):
        metadata, returned, receipt = owner_returns()
        metadata["parent"] = {"parent_request_ref": returned["request_ref"],
            "parent_terminal_ref": "existing-terminal", "parent_terminal_sha256": "e" * 64,
            "consumption_status": "CONSUMED", "consumption_ref": "existing-consumption",
            "executive_acceptance": "NOT_OBSERVED", "acceptance_ref": None}
        self.assertIs(returned["parent_consumed"], False)
        self.assertEqual(self.recover(metadata, returned, receipt).state, "ALREADY_CONSUMED")
        metadata["parent"]["parent_request_ref"] = "foreign"
        with self.assertRaisesRegex(projection.CheckpointError, "WRONG_PARENT"):
            self.compose(metadata, returned, receipt)

    def test_incomplete_or_invented_parent_receipt_is_refused(self):
        metadata, returned, receipt = owner_returns()
        metadata["parent"] = {"consumption_status": "CONSUMED"}
        with self.assertRaisesRegex(projection.CheckpointError, "INVALID_FIELDS"):
            self.compose(metadata, returned, receipt)
        returned["parent_consumed"] = True
        metadata["parent"] = None
        with self.assertRaisesRegex(projection.CheckpointError, "INVALID_OWNER_RESULT_FLAGS"):
            self.compose(metadata, returned, receipt)

    def test_no_authority_generation_or_receipt_is_invented(self):
        metadata, returned, receipt = owner_returns()
        metadata["authority"]["generation"] = None
        self.assertIsNone(self.compose(metadata, returned, receipt)["authority"]["generation"])
        self.assertEqual(self.recover(metadata, returned, receipt).reason, "AUTHORITY_GENERATION_UNAVAILABLE")
        metadata["authority"]["generation"] = 11
        receipt.update(state="UNKNOWN", source_identity=None, before=None, after=None)
        self.assertEqual(self.recover(metadata, returned, receipt).reason, "RUNTIME_OBSERVATION_UNQUALIFIED")

    def test_same_receipt_does_not_prove_physical_finalization(self):
        metadata, returned, receipt = owner_returns()
        metadata["observation"]["finalized"] = False
        self.assertEqual(self.recover(metadata, returned, receipt).reason, "OBSERVATION_NOT_FINALIZED")

    def test_read_revocation_and_policy_fingerprint_difference_are_not_erased(self):
        metadata, returned, receipt = owner_returns()
        metadata["authority"]["read_permitted"] = False
        outcome = self.recover(metadata, returned, receipt)
        self.assertEqual(outcome.reason, "READ_AUTHORITY_UNAVAILABLE")
        self.assertIsNone(outcome.result_ref)
        metadata["authority"]["read_permitted"] = True
        metadata["authority"]["principal_sha256"] = "0" * 64
        self.assertEqual(self.recover(metadata, returned, receipt).reason, "FOREIGN_PRINCIPAL")

    def test_actual_owner_returns_support_restart_and_compaction_without_new_request(self):
        metadata, returned, receipt = owner_returns()
        saved = projection.build_checkpoint_from_hermes_returns(metadata,
            original_result=returned, runtime_receipt=receipt)
        metadata["native"].update(instance_sha256="0" * 64, authority_epoch=8)
        metadata["context"].update(message_checkpoint_ref="native-message-002",
            message_checkpoint_sha256="d" * 64, compaction_generation=1)
        receipt.update(source_identity="0" * 32, before=0, after=0)
        current = self.compose(metadata, returned, receipt)
        outcome = projection.project_recovery(saved, expected_sha256=saved.sha256,
            before=current, after=current, now=NOW)
        self.assertEqual(outcome.state, "RECOVER_ORIGINAL_RESULT")
        self.assertTrue(outcome.gateway_restarted)
        self.assertTrue(outcome.context_compacted)
        self.assertEqual(outcome.request_ref, returned["request_ref"])
        self.assertEqual(current["original"]["admission_epoch"], 7)

    def test_changed_owner_answer_after_checkpoint_is_not_the_retained_original(self):
        metadata, returned, receipt = owner_returns()
        saved = projection.build_checkpoint_from_hermes_returns(metadata,
            original_result=returned, runtime_receipt=receipt)
        returned["answer"] = "Different answer."
        current = self.compose(metadata, returned, receipt)
        outcome = projection.project_recovery(saved, expected_sha256=saved.sha256,
            before=current, after=current, now=NOW)
        self.assertEqual(outcome.reason, "ORIGINAL_RESULT_CHANGED")

    def test_native_reply_wire_schema_cannot_be_mislabeled_as_hermes_result(self):
        metadata, returned, receipt = owner_returns()
        returned["schema"] = "mastermind.native_reply_read.v1"
        with self.assertRaisesRegex(projection.CheckpointError, "UNSUPPORTED_OWNER_RESULT_SCHEMA"):
            self.compose(metadata, returned, receipt)
        metadata["original"]["kind"] = "NATIVE_CONTINUATION"
        with self.assertRaisesRegex(projection.CheckpointError, "UNSUPPORTED_OWNER_RETURN_KIND"):
            self.compose(metadata, returned, receipt)

    def test_owner_result_unknown_fields_and_coerced_flags_fail_closed(self):
        mutations = [("extra", "transcript"), ("commit_started", 1), ("parent_consumed", 0),
                     ("successful", 1), ("admission", None),
                     ("admission", {str(i): None for i in range(1000)})]
        for key, value in mutations:
            with self.subTest(key=key):
                metadata, returned, receipt = owner_returns()
                returned[key] = value
                with self.assertRaises(projection.CheckpointError):
                    self.compose(metadata, returned, receipt)

    def test_malformed_or_oversized_text_returns_only_closed_error(self):
        for answer in ("private\x00secret", "\ud800", "s" * (64 * 1024 + 1)):
            metadata, returned, receipt = owner_returns()
            returned["answer"] = answer
            with self.assertRaisesRegex(projection.CheckpointError, "^INVALID_OWNER_TEXT$"):
                self.compose(metadata, returned, receipt)
        metadata, returned, receipt = owner_returns()
        returned["answer"] = "x" * (23 * 1024)
        with self.assertRaisesRegex(projection.CheckpointError, "^OWNER_RESULT_OVER_BUDGET$"):
            self.compose(metadata, returned, receipt)

    def test_plain_inputs_and_context_budget_are_still_required(self):
        metadata, returned, receipt = owner_returns()
        with self.assertRaisesRegex(projection.CheckpointError, "CONTEXT_BUDGET_EXCEEDED"):
            projection.build_checkpoint_from_hermes_returns(metadata, original_result=returned,
                runtime_receipt=receipt, context_budget_bytes=100)
        with self.assertRaises(projection.CheckpointError):
            self.compose(metadata, returned, object())
        metadata["observation"]["finalized"] = 1
        with self.assertRaises(projection.CheckpointError):
            self.compose(metadata, returned, receipt)

    def test_composition_is_detached_deterministic_and_has_no_io(self):
        import os
        import socket
        import sqlite3
        import subprocess
        metadata, returned, receipt = owner_returns()
        inputs = copy.deepcopy((metadata, returned, receipt))
        with patch("builtins.open", side_effect=AssertionError("file I/O")), \
             patch.object(os, "open", side_effect=AssertionError("file I/O")), \
             patch.object(socket, "socket", side_effect=AssertionError("network")), \
             patch.object(sqlite3, "connect", side_effect=AssertionError("state DB")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("process")):
            first = self.compose(metadata, returned, receipt)
            for _ in range(3):
                self.assertEqual(self.compose(metadata, returned, receipt), first)
                self.assertEqual(self.recover(metadata, returned, receipt).state, "RECOVER_ORIGINAL_RESULT")
        self.assertEqual((metadata, returned, receipt), inputs)
        first["native"]["profile_sha256"] = "0" * 64
        self.assertEqual(metadata["native"]["profile_sha256"], "1" * 64)


class NativeOwnerReturnCompositionTests(unittest.TestCase):
    def compose(self, metadata, returned, receipt, request_key):
        return projection.project_native_owner_facts(metadata, original_result=returned,
            runtime_receipt=receipt, request_message_key=request_key)

    def recover(self, metadata, returned, receipt, request_key):
        current = self.compose(metadata, returned, receipt, request_key)
        manifest = projection.build_checkpoint_from_native_returns(metadata,
            original_result=returned, runtime_receipt=receipt, request_message_key=request_key)
        return projection.project_recovery(manifest, expected_sha256=manifest.sha256,
            before=current, after=current, now=NOW)

    def test_actual_native_reader_result_builds_metadata_only_checkpoint(self):
        metadata, returned, receipt, request_key = native_owner_returns()
        value = self.compose(metadata, returned, receipt, request_key)
        self.assertEqual(value["return"]["result_ref"], returned["read_ref"])
        self.assertEqual(value["return"]["result_sha256"], returned["fingerprint"])
        self.assertEqual(value["return"]["result_outcome"], "UNKNOWN")
        self.assertEqual(value["return"]["consumption_status"], "UNKNOWN")
        self.assertIsNone(value["return"]["parent_terminal_ref"])
        self.assertEqual(self.recover(metadata, returned, receipt, request_key).state, "RECOVER_ORIGINAL_RESULT")
        manifest = projection.build_checkpoint_from_native_returns(metadata,
            original_result=returned, runtime_receipt=receipt, request_message_key=request_key)
        for text in ("Original child evidence", "bounded decision", "primary_ts", "message_key"):
            self.assertNotIn(text.encode(), manifest.canonical_json)

    def test_operation_lookup_echo_does_not_change_original_result_digest(self):
        by_operation = native_owner_returns(by_operation=True)
        by_reference = native_owner_returns()
        self.assertIn("operation_key", by_operation[1])
        self.assertNotIn("operation_key", by_reference[1])
        self.assertNotEqual(digest(by_operation[1]), digest(by_reference[1]))
        first, second = self.compose(*by_operation), self.compose(*by_reference)
        self.assertEqual(first, second)
        manifest = projection.build_checkpoint(first)
        outcome = projection.project_recovery(manifest, expected_sha256=manifest.sha256,
            before=second, after=second, now=NOW)
        self.assertEqual(outcome.state, "RECOVER_ORIGINAL_RESULT")

    def test_progress_reply_does_not_complete_a_running_attempt_or_accept_product(self):
        metadata, returned, receipt, request_key = native_owner_returns()
        metadata["runtime"]["attempt_status"] = "RUNNING"
        value = self.compose(metadata, returned, receipt, request_key)
        self.assertEqual(value["runtime"]["attempt_status"], "RUNNING")
        self.assertEqual(value["return"]["executive_acceptance"], "NOT_OBSERVED")
        self.assertIsNone(value["return"]["parent_terminal_ref"])
        self.assertFalse(self.recover(metadata, returned, receipt, request_key).can_resume_execution)

    def test_original_job_attempt_and_commit_still_require_runtime_evidence(self):
        for group, key, change in (("runtime", "attempt_id", None),
                                   ("original", "commit_status", "UNKNOWN"),
                                   ("original", "admission_id", "fabricated-native-admission")):
            metadata, returned, receipt, request_key = native_owner_returns()
            metadata[group][key] = change
            with self.assertRaises(projection.CheckpointError):
                self.compose(metadata, returned, receipt, request_key)

    def test_wrong_parent_and_optional_operation_echo_are_refused(self):
        for key in ("read_ref", "request_ref", "in_reply_to", "operation_key"):
            metadata, returned, receipt, request_key = native_owner_returns(by_operation=True)
            returned[key] = "foreign-reference"
            with self.assertRaisesRegex(projection.CheckpointError, "OWNER_RESULT_ORIGINAL_MISMATCH"):
                self.compose(metadata, returned, receipt, request_key)

    def test_changed_native_fingerprint_is_not_the_retained_original(self):
        metadata, returned, receipt, request_key = native_owner_returns()
        manifest = projection.build_checkpoint(self.compose(metadata, returned, receipt, request_key))
        returned["fingerprint"] = "0" * 64
        current = self.compose(metadata, returned, receipt, request_key)
        outcome = projection.project_recovery(manifest, expected_sha256=manifest.sha256,
            before=current, after=current, now=NOW)
        self.assertEqual(outcome.reason, "ORIGINAL_RESULT_CHANGED")

    def test_native_source_result_is_not_a_parent_consumption_receipt(self):
        metadata, returned, receipt, request_key = native_owner_returns()
        metadata["parent"] = {"parent_request_ref": returned["request_ref"],
            "parent_terminal_ref": "existing-child-terminal", "parent_terminal_sha256": "a" * 64,
            "consumption_status": "CONSUMED", "consumption_ref": "existing-parent-consumption",
            "executive_acceptance": "ACCEPTED", "acceptance_ref": "existing-product-acceptance"}
        outcome = self.recover(metadata, returned, receipt, request_key)
        self.assertEqual(outcome.state, "ALREADY_CONSUMED")
        self.assertEqual(outcome.executive_acceptance, "ACCEPTED")
        self.assertIs(returned["parent_consumed"], False)

    def test_native_read_revocation_and_uncertainty_remain_effective(self):
        metadata, returned, receipt, request_key = native_owner_returns()
        metadata["authority"]["read_permitted"] = False
        outcome = self.recover(metadata, returned, receipt, request_key)
        self.assertEqual(outcome.reason, "READ_AUTHORITY_UNAVAILABLE")
        self.assertIsNone(outcome.result_ref)
        metadata["authority"]["read_permitted"] = True
        metadata["observation"]["write_uncertainty"] = "EFFECT_UNKNOWN"
        self.assertEqual(self.recover(metadata, returned, receipt, request_key).state, "RECONCILE_ORIGINAL")

    def test_native_schema_flags_digest_timestamp_and_budget_are_closed(self):
        mutations = [("schema", "foreign"), ("reply_committed", 1), ("parent_consumed", 0),
                     ("fingerprint", "invalid"), ("primary_ts", "invalid"),
                     ("prompt", "must not be retained"), ("text", "x" * (16 * 1024))]
        for key, value in mutations:
            with self.subTest(key=key):
                metadata, returned, receipt, request_key = native_owner_returns()
                returned[key] = value
                with self.assertRaises(projection.CheckpointError):
                    self.compose(metadata, returned, receipt, request_key)

    def test_native_repeat_and_parallel_composition_have_no_effect_entrypoint(self):
        import os
        import socket
        import sqlite3
        import subprocess
        inputs = native_owner_returns()
        retained = copy.deepcopy(inputs)
        with patch("builtins.open", side_effect=AssertionError("file I/O")), \
             patch.object(os, "open", side_effect=AssertionError("file I/O")), \
             patch.object(socket, "socket", side_effect=AssertionError("network")), \
             patch.object(sqlite3, "connect", side_effect=AssertionError("state DB")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("process")):
            with ThreadPoolExecutor(max_workers=4) as pool:
                outcomes = list(pool.map(lambda _: self.recover(*inputs), range(24)))
        self.assertEqual(len(set(outcomes)), 1)
        self.assertEqual(inputs, retained)


if __name__ == "__main__":
    unittest.main()
