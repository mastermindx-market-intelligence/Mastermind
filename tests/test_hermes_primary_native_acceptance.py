"""Command boundaries over the incumbent native validators; transport is a double.

No host socket, provider, account, grant, enrollment or live admission is used.
The synthetic harmless tool below is never registered in a real Hermes profile.
"""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from integrations.hermes_application_fabric.client import ApplicationBinding, NativeCall
from integrations.hermes_application_fabric.qualification import native_acceptance as command
from integrations.hermes_runtime import native_request_observation as observations
from integrations.hermes_runtime import native_session_control as sdk
from integrations.hermes_runtime import native_transport_observation as transport

IMPLEMENTATION = "a" * 40
ENROLLMENT = "existing-enrollment-fixture"
SUBMISSION = "original-submission-fixture"
PROMPT = "Use the already qualified harmless tool once and summarize its result."
TOOL = "qualified_harmless_fixture"


def reply(status, **fields):
    return {"schema": sdk.conversation_contract("mmsecretary").native_schema,
            "status": status, **fields}


class RecordingNativeClient:
    def __init__(self):
        self.home = Path("/qualified/secretary-fixture")
        self.target = dict(profile_id=str(self.home), session_id="original-session",
            principal_id=f"uid:{os.getuid()}", instance_id="original-instance",
            authority_epoch=3, revision=4, execution_generation=5)
        self.receipt = dict(admission_id="original-admission",
            ref={"profile_id": str(self.home), "session_id": "original-session"},
            sequence=7, status="queued", outcome=None, authority_epoch=3, execution_generation=None)
        self.calls = []
        self.enrollment = sdk.enrollment_result(IMPLEMENTATION, ENROLLMENT, "ENROLLED", self.target)
        self.observed = reply("TARGET", target=self.target)
        self.submitted = reply("ADMITTED", admission=self.receipt)
        self.read = reply("EFFECT_UNKNOWN")

    def inspect_enrollment(self, implementation_sha, request_id):
        self.calls.append(("inspect", implementation_sha, request_id))
        return deepcopy(self.enrollment)

    def observe(self, session_id):
        self.calls.append(("observe", session_id))
        return deepcopy(self.observed)

    def submit(self, target, submission_id, text):
        self.calls.append(("submit", deepcopy(target), submission_id, text))
        if isinstance(self.submitted, BaseException):
            raise self.submitted
        return deepcopy(self.submitted)

    def read_original(self, **identity):
        self.calls.append(("read_original", deepcopy(identity)))
        if isinstance(self.read, BaseException):
            raise self.read
        return deepcopy(self.read)


def observed_tool(client):
    """Retained v2 metadata accepted by the real SDK validator."""
    identity = dict(agent_session_id="native-agent-session", task_id="native-task",
        turn_id="native-turn", api_request_id="native-request-one",
        tool_call_id="native-tool-call", tool_name=TOOL)
    request = dict(fields=["messages"], content_sha256="b" * 64, content_bytes=42,
        canonicalization=observations.CANONICALIZATION, tools={"status": "absent"},
        agent_session_id=identity["agent_session_id"], turn_id=identity["turn_id"],
        api_request_id=identity["api_request_id"], api_call_count=1, retry_count=0)
    receipt = dict(client.receipt, status="terminal", outcome="success", execution_generation=6)
    document = dict(schema=observations.PREVIOUS_SCHEMA, stage=observations.STAGE,
        scope=dict(role="mmsecretary", session_id=receipt["ref"]["session_id"],
            admission_id=receipt["admission_id"], authority_epoch=receipt["authority_epoch"],
            execution_generation=receipt["execution_generation"], instance_id="historical-instance"),
        observations=[request, dict(request, api_request_id="native-request-two", api_call_count=2)],
        errors=[], overflow=False, coverage="assembly_hooks_only",
        provider_dispatch_proven=False, model_identity_verified=False,
        tools_stage=observations.TOOLS_STAGE, tool_coverage=observations.TOOL_COVERAGE,
        executions=[dict(sequence=1, identity=identity, invalid_fields=[], state="returned")],
        commits=[dict(sequence=2, identity=identity, invalid_fields=[], state="commit_tuple_returned",
            blocked=False, is_error=False, reported_effect_disposition="none",
            correlation={"status": "unique_identity_match", "execution_sequence": 1})],
        tool_overflow=False, metadata_overflow=False)
    return receipt, document


class NativeAcceptanceBoundaries(unittest.TestCase):
    def setUp(self):
        self.client = RecordingNativeClient()
        self.written = []

    def submit(self, **overrides):
        options = dict(implementation_sha=IMPLEMENTATION, enrollment_request_id=ENROLLMENT,
            submission_id=SUBMISSION, text=PROMPT, writer=self.written.append)
        options.update(overrides)
        return command.submit_once(self.client, sdk, **options)

    def read(self, **overrides):
        options = dict(session_id="original-session", submission_id=SUBMISSION,
            input_sha256=sdk.input_digest(PROMPT), expected_tool=TOOL, writer=self.written.append)
        options.update(overrides)
        return command.read_original(self.client, sdk, **options)

    def test_single_admission_emits_original_identity_before_attempt(self):
        original = self.client.submit
        def check(*args):
            self.assertEqual(len(self.written), 1)
            self.assertEqual(self.written[0]["status"], "PREPARED")
            self.assertTrue(self.written[0]["original_read_required_if_interrupted"])
            self.assertEqual(self.written[0]["original"]["input_sha256"], sdk.input_digest(PROMPT))
            self.assertNotIn("text", self.written[0])
            return original(*args)
        self.client.submit = check
        report = self.submit()
        self.assertEqual([x[0] for x in self.client.calls], ["inspect", "observe", "submit"])
        self.assertEqual(report["original"]["admission_id"], "original-admission")
        self.assertFalse(report["live_acceptance"])
        self.assertFalse(report["provider_dispatch_proven"])

    def test_changed_target_refuses_before_submission(self):
        for field, value in [("principal_id", "uid:other"), ("profile_id", "/other"),
                             ("revision", 99), ("execution_generation", 99)]:
            with self.subTest(field=field):
                self.client = RecordingNativeClient()
                self.client.observed = deepcopy(self.client.observed)
                self.client.observed["target"][field] = value
                with self.assertRaises(Exception):
                    self.submit()
                self.assertNotIn("submit", [x[0] for x in self.client.calls])

    def test_enrollment_uses_actual_uid_and_original_identifiers(self):
        for field, value in [("implementation_sha", "c" * 40), ("request_id", "other-enrollment")]:
            with self.subTest(field=field):
                self.client = RecordingNativeClient()
                self.client.enrollment[field] = value
                with self.assertRaises(Exception):
                    self.submit()
                self.assertEqual([x[0] for x in self.client.calls], ["inspect"])
        self.client = RecordingNativeClient()
        self.client.enrollment["target"]["principal_id"] = "uid:other"
        with self.assertRaises(Exception):
            self.submit()
        self.assertEqual([x[0] for x in self.client.calls], ["inspect"])

    def test_absent_enrollment_does_not_create_one(self):
        self.client.enrollment = sdk.enrollment_result(IMPLEMENTATION, ENROLLMENT, "ABSENT")
        with self.assertRaises(command.EvidenceRefusal):
            self.submit()
        self.assertEqual([x[0] for x in self.client.calls], ["inspect"])

    def test_prompt_limits_apply_before_transport(self):
        for text in ["", " ", "x" * (sdk.MAX_INPUT_BYTES + 1)]:
            with self.subTest(length=len(text)):
                with self.assertRaises(Exception):
                    self.submit(text=text)
        self.assertEqual(self.client.calls, [])

    def test_prepared_output_failure_prevents_attempt(self):
        def fail(_):
            raise OSError("output unavailable")
        with self.assertRaises(OSError):
            self.submit(writer=fail)
        self.assertNotIn("submit", [x[0] for x in self.client.calls])

    def test_timeout_and_interrupt_preserve_unknown_without_retry(self):
        for error in [TimeoutError("private detail"), KeyboardInterrupt()]:
            with self.subTest(error=type(error).__name__):
                self.client = RecordingNativeClient()
                self.client.submitted = error
                report = self.submit()
                self.assertEqual(report["status"], "EFFECT_UNKNOWN")
                self.assertEqual([x[0] for x in self.client.calls], ["inspect", "observe", "submit"])
                self.assertNotIn("private detail", json.dumps(report))

    def test_malformed_responses_cannot_claim_safe_refusal(self):
        examples = [None, {}, {"status": "NOT_SUBMITTED"}, reply("unexpected"),
            reply("ADMITTED", admission={}), reply("ADMITTED", admission=dict(self.client.receipt,
                ref={"profile_id": "/other", "session_id": "original-session"})),
            reply([], reason="MALFORMED"), reply("REFUSED", reason={"private": "detail"}),
            reply("ADMITTED", admission=self.client.receipt, unexpected=True)]
        for result in examples:
            with self.subTest(result=result):
                self.client = RecordingNativeClient()
                self.client.submitted = result
                report = self.submit()
                self.assertEqual(report["status"], "EFFECT_UNKNOWN")
                self.assertTrue(report["native_submit_attempted"])
                self.assertEqual(report["original"]["submission_id"], SUBMISSION)
                self.assertEqual(sum(x[0] == "submit" for x in self.client.calls), 1)

    def test_original_refusal_is_preserved_without_fallback(self):
        for status in ["REFUSED", "NOT_SUBMITTED", "EFFECT_UNKNOWN"]:
            with self.subTest(status=status):
                self.client = RecordingNativeClient()
                self.client.submitted = reply(status, reason="ORIGINAL_OWNER_REASON")
                self.assertEqual(self.submit()["status"], status)
                self.assertEqual(sum(x[0] == "submit" for x in self.client.calls), 1)

    def test_lost_final_output_preserves_emitted_recovery_identity(self):
        def writer(document):
            if self.written:
                raise OSError("lost final output")
            self.written.append(document)
        with self.assertRaises(OSError):
            self.submit(writer=writer)
        self.assertEqual(sum(x[0] == "submit" for x in self.client.calls), 1)
        self.assertEqual(self.written[0]["original"]["submission_id"], SUBMISSION)
        self.assertNotIn("admission_id", self.written[0]["original"])

    def test_original_read_after_renewal_does_not_inspect_new_owner(self):
        receipt, document = observed_tool(self.client)
        self.client.read = reply("OBSERVED", admission=receipt, request_observation=document,
                                successful=True, answer="private final answer")
        self.client.target.update(authority_epoch=100, execution_generation=200, instance_id="new-owner")
        report = self.read(admission_id="original-admission")
        self.assertEqual([x[0] for x in self.client.calls], ["read_original"])
        self.assertEqual(report["admission"]["authority_epoch"], 3)
        self.assertTrue(report["native_tool"]["native_callback_and_commit_observed"])
        self.assertTrue(report["native_tool"]["later_native_request_observed"])
        self.assertFalse(report["native_tool"]["tool_history_content_verified"])
        self.assertFalse(report["native_tool"]["application_correlation"]["verified"])
        self.assertFalse(report["live_acceptance"])
        self.assertFalse(report["account_and_budget_verified"])
        self.assertEqual(report["answer"]["sha256"], hashlib.sha256(b"private final answer").hexdigest())
        self.assertNotIn("private final answer", json.dumps(report))

    def test_unknown_or_unavailable_read_never_resubmits(self):
        for result in [reply("EFFECT_UNKNOWN"), reply("UNAVAILABLE"), TimeoutError("private detail")]:
            with self.subTest(result=type(result).__name__):
                self.client = RecordingNativeClient()
                self.client.read = result
                report = self.read()
                self.assertIn(report["status"], {"EFFECT_UNKNOWN", "UNAVAILABLE", "READ_UNAVAILABLE"})
                self.assertEqual([x[0] for x in self.client.calls], ["read_original"])
                self.assertFalse(report["native_submit_attempted"])

    def test_wrong_original_session_admission_or_scope_is_rejected(self):
        for mismatch in ["session", "admission", "scope"]:
            with self.subTest(mismatch=mismatch):
                self.client = RecordingNativeClient()
                receipt, document = observed_tool(self.client)
                if mismatch == "session":
                    receipt["ref"] = dict(receipt["ref"], session_id="other")
                elif mismatch == "admission":
                    receipt["admission_id"] = "other"
                else:
                    document["scope"]["admission_id"] = "other"
                self.client.read = reply("OBSERVED", admission=receipt, request_observation=document)
                with self.assertRaises(Exception):
                    self.read(admission_id="original-admission")
                self.assertEqual([x[0] for x in self.client.calls], ["read_original"])

    def test_oversized_answer_is_not_printed(self):
        receipt, _ = observed_tool(self.client)
        self.client.read = reply("OBSERVED", admission=receipt,
            answer="x" * (sdk.MAX_ANSWER_BYTES + 1), successful=True)
        with self.assertRaises(command.EvidenceRefusal):
            self.read()
        self.assertEqual(self.written, [])

    def test_missing_observation_remains_incomplete(self):
        receipt, _ = observed_tool(self.client)
        self.client.read = reply("OBSERVED", admission=receipt,
                                request_observation_error="INVALID_RETAINED_OBSERVATION")
        report = self.read()
        self.assertTrue(report["native_observation_unavailable"])
        self.assertNotIn("native_tool", report)
        self.assertFalse(report["live_acceptance"])

    def test_native_validator_rejects_forged_unique_correlation(self):
        receipt, document = observed_tool(self.client)
        document["commits"][0]["correlation"]["execution_sequence"] = 99
        self.client.read = reply("OBSERVED", admission=receipt, request_observation=document)
        with self.assertRaises(ValueError):
            self.read()

    def test_uncertain_error_duplicate_or_overflow_tools_do_not_count(self):
        _, original = observed_tool(self.client)
        variants = []
        for key, value in [("blocked", True), ("is_error", True), ("reported_effect_disposition", "unknown")]:
            item = deepcopy(original)
            item["commits"][0][key] = value
            variants.append(item)
        for flag in ["overflow", "tool_overflow", "metadata_overflow"]:
            item = deepcopy(original)
            item[flag] = True
            variants.append(item)
        item = deepcopy(original)
        item["executions"].append(deepcopy(item["executions"][0]))
        variants.append(item)
        item = deepcopy(original)
        item["errors"] = ["tool_observation_failed"]
        variants.append(item)
        for document in variants:
            with self.subTest(document=document):
                result = command.native_tool_evidence(document, expected_tool=TOOL, admission_id="original-admission")
                self.assertFalse(result["native_callback_and_commit_observed"])

    def test_later_request_requires_same_turn_and_different_request(self):
        _, document = observed_tool(self.client)
        for second in [dict(document["observations"][0]), dict(document["observations"][1], turn_id="other")]:
            with self.subTest(second=second):
                document["observations"][1] = second
                result = command.native_tool_evidence(document, expected_tool=TOOL, admission_id="original-admission")
                self.assertFalse(result["later_native_request_observed"])
                self.assertFalse(result["tool_history_content_verified"])

    def test_wire_hash_matches_actual_binding_without_constructing_factory(self):
        _, document = observed_tool(self.client)
        identity = document["executions"][0]["identity"]
        call = NativeCall(identity["agent_session_id"], identity["task_id"], identity["turn_id"], identity["api_request_id"])
        expected = ApplicationBinding.request_id(SimpleNamespace(operation_id="original-admission"), call)
        self.assertEqual(command.application_request_id("original-admission", identity), expected)
        self.assertNotEqual(command.application_request_id("other-admission", identity), expected)

    def test_output_limit_is_checked_before_partial_document(self):
        output = io.StringIO()
        with patch("sys.stdout", output):
            with self.assertRaises(command.EvidenceRefusal):
                command.emit({"oversized": "x" * command.MAX_DOCUMENT_BYTES})
        self.assertEqual(output.getvalue(), "")

    def test_terminal_evidence_is_rejected_on_nonterminal_admission(self):
        for status in ["queued", "started", "unknown"]:
            with self.subTest(status=status):
                receipt, document = observed_tool(self.client)
                receipt["status"] = status
                self.client.read = reply("OBSERVED", admission=receipt, request_observation=document,
                                        answer="answer", successful=True)
                with self.assertRaises(command.EvidenceRefusal):
                    self.read()
        self.assertEqual(self.written, [])

    def test_observation_and_observation_error_are_mutually_exclusive(self):
        receipt, document = observed_tool(self.client)
        self.client.read = reply("OBSERVED", admission=receipt, request_observation=document,
                                request_observation_error="INVALID_RETAINED_OBSERVATION")
        with self.assertRaises(command.EvidenceRefusal):
            self.read()

    def test_unrecognized_observation_error_is_rejected(self):
        receipt, _ = observed_tool(self.client)
        self.client.read = reply("OBSERVED", admission=receipt, request_observation_error="unexpected")
        with self.assertRaises(command.EvidenceRefusal):
            self.read()

    def test_answer_and_success_form_one_terminal_pair(self):
        receipt, _ = observed_tool(self.client)
        for extra in [{"successful": True}, {"answer": "answer"}, {"answer": None, "successful": True},
                      {"answer": "answer", "successful": 1}]:
            with self.subTest(extra=extra):
                self.client.read = reply("OBSERVED", admission=receipt, **extra)
                with self.assertRaises((command.EvidenceRefusal, KeyError)):
                    self.read()
        self.assertEqual(self.written, [])

    def test_existing_terminal_projector_binds_answer_digest(self):
        receipt, document = observed_tool(self.client)
        metadata = sdk._terminal_metadata({"completed": True, "model": "unverified-label"}, "answer")
        self.client.read = reply("OBSERVED", admission=receipt, request_observation=document,
                                terminal_metadata=metadata, answer="answer", successful=True)
        report = self.read()
        self.assertNotIn("unverified-label", json.dumps(report))
        self.assertFalse(report["model_identity_verified"])
        self.client.read["terminal_metadata"]["output"]["sha256"] = "c" * 64
        with self.assertRaises(command.EvidenceRefusal):
            self.read()

    def test_terminal_metadata_cannot_invent_fields_or_promote_model(self):
        receipt, _ = observed_tool(self.client)
        for mutate in [
            lambda m: m.update(model_identity_verified=True),
            lambda m: m["reported"].update(extra=True),
            lambda m: m["reported"].update(completed=1),
            lambda m: m["invalid_fields"].append("completed"),
        ]:
            with self.subTest(mutate=mutate):
                metadata = sdk._terminal_metadata({"completed": True}, None)
                mutate(metadata)
                self.client.read = reply("OBSERVED", admission=receipt, terminal_metadata=metadata)
                with self.assertRaises(command.EvidenceRefusal):
                    self.read()

    def test_derived_application_identity_requires_one_matching_assembly(self):
        _, original = observed_tool(self.client)
        for requests in [[], [original["observations"][0], original["observations"][0]]]:
            with self.subTest(requests=requests):
                document = dict(original, observations=requests)
                report = command.native_tool_evidence(document, expected_tool=TOOL, admission_id="original-admission")
                self.assertTrue(report["native_callback_and_commit_observed"])
                self.assertNotIn("application_correlation", report)
                self.assertFalse(report["later_native_request_observed"])

    def test_unknown_result_cannot_smuggle_terminal_answer(self):
        self.client.read = reply("EFFECT_UNKNOWN", answer="not an original result", successful=True)
        with self.assertRaises(command.EvidenceRefusal):
            self.read()
        self.assertEqual([x[0] for x in self.client.calls], ["read_original"])

    def test_v3_unsupported_httpx_does_not_erase_valid_native_tool_observation(self):
        receipt, document = observed_tool(self.client)
        document["schema"] = observations.SCHEMA
        document["transport"] = dict(schema=transport.SCHEMA, coverage=transport.COVERAGE,
            http_stage=transport.HTTP_STAGE,
            installation={"status": "qualified", "httpx_client_source_sha256": transport.HTTPX_SOURCE_SHA256},
            complete_evaluation=False, provider_delivery_proven=False, model_identity_verified=False,
            execution=dict(stage=transport.EXECUTION_STAGE, outcome="unobserved",
                started_at_ms=None, finished_at_ms=None, duration_ms=None,
                process_start={"status": "unavailable"}, process_end={"status": "unavailable"}, same_process=None),
            calls=[], dispatches=[], attempts=[], errors=["process_observation_unavailable", "unsupported_client"],
            overflow=False)
        self.client.read = reply("OBSERVED", admission=receipt, request_observation=document)
        report = self.read()
        self.assertTrue(report["native_tool"]["native_callback_and_commit_observed"])
        self.assertFalse(report["provider_dispatch_proven"])
        self.assertFalse(report["live_acceptance"])


if __name__ == "__main__":
    unittest.main()
