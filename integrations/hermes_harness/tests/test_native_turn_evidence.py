"""Synthetic tests for the pinned Hermes JSONL one-shot observation seam."""
import json
import unittest
from pathlib import Path
from integrations.hermes_harness.native_turn_evidence import (
    ObservationRefusal, canary_prompt, native_one_shot_argv, observe_native_turn,
)

MARKER = "MMX-CANARY-1234567890"
SESSION = "session-abc_1"


def sample_events(*, model="glm-5-3-flash-260828", answer=MARKER):
    return [
        {"type": "system", "subtype": "init", "model": model, "session_id": SESSION},
        {"type": "text", "text": answer},
        {"type": "result", "session_id": SESSION, "exit_code": 0, "text": answer,
         "tokens": {"input": 25, "output": 16, "total": 41}},
    ]


def execute(events=None, **kwargs):
    original = sample_events() if events is None else events
    obj = dict(role="mmsecretary", expected_model="glm-5-3-flash-260828",
               challenge_marker=MARKER, stdout=b"".join(
                   json.dumps(ev).encode("utf-8") + b"\n" for ev in original),
               stderr=("\nsession_id: " + SESSION + "\n").encode(), process_exit_code=0)
    obj.update(kwargs)
    return observe_native_turn(**obj)


class TurnEvidenceTests(unittest.TestCase):
    def test_valid_receipt_is_observation_only_and_no_content(self):
        result = execute()
        self.assertEqual(result["status"], "PASS_CHILD_OUTPUT_OBSERVATION_ONLY")
        self.assertEqual(result["issue_codes"], [])
        self.assertNotIn(MARKER, json.dumps(result))
        self.assertFalse(result["provider_authentication_verified"])
        self.assertFalse(result["live_slack_delivery_verified"])

    def test_safe_cli_uses_stdin_and_no_bearer(self):
        argv = native_one_shot_argv(Path("/opt/hermes/bin/hermes"), "mmsecretary")
        self.assertEqual(argv, ["/opt/hermes/bin/hermes", "-p", "mmsecretary",
                                "chat", "-Q", "--query-file", "-", "--format", "stream-json"])
        self.assertNotIn(MARKER, " ".join(argv))
        self.assertEqual(native_one_shot_argv(Path("/x"), "mmmeta")[2], "mmmeta")

    def test_rejects_wrong_role_and_relative_binary(self):
        for role, binary in [("grok", Path("/x")), ("mmmeta", Path("./hermes"))]:
            with self.subTest(role=role):
                with self.assertRaises(ObservationRefusal):
                    native_one_shot_argv(binary, role)

    def test_prompt_rejects_injection_and_accepts_marker(self):
        self.assertIn(MARKER, canary_prompt(MARKER))
        for val in ["foo", "$(evil)", "X\nY", "", "a" * 128]:
            with self.subTest(val=val):
                with self.assertRaises(ObservationRefusal):
                    canary_prompt(val)

    def test_cross_role_model_fails(self):
        r = execute(role="mmmeta")
        self.assertEqual(r["status"], "BLOCKED")
        self.assertIn("ROLE_MODEL_NOT_QUALIFIED", r["issue_codes"])

    def test_alias_model_not_fake_pass(self):
        r = execute(expected_model="attacker-custom")
        self.assertIn("ROLE_MODEL_NOT_QUALIFIED", r["issue_codes"])

    def test_model_mismatch_fails(self):
        arr = sample_events(model="glm-5.3")
        self.assertIn("MODEL_IDENTITY_MISMATCH", execute(arr)["issue_codes"])

    def test_no_response_fails(self):
        arr = sample_events(answer="")
        self.assertIn("CHALLENGE_NOT_SATISFIED", execute(arr)["issue_codes"])

    def test_wrong_challenge_fails(self):
        self.assertIn("CHALLENGE_NOT_SATISFIED", execute(sample_events(answer="hello"))["issue_codes"])

    def test_nonzero_exit_fails(self):
        self.assertIn("PROCESS_FAILED", execute(process_exit_code=1)["issue_codes"])

    def test_terminal_nonzero_fails(self):
        arr = sample_events(); arr[-1]["exit_code"] = 1
        self.assertIn("RESULT_NOT_COMPLETE", execute(arr)["issue_codes"])

    def test_boolean_exit_is_not_a_successful_native_result(self):
        arr = sample_events()
        arr[-1]["exit_code"] = False
        result = execute(arr)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("RESULT_NOT_COMPLETE", result["issue_codes"])

    def test_model_error_fails(self):
        arr = sample_events(); arr[-1]["error"] = "PROVIDER_KEY_MISSING_SECRET_SENTINEL"
        result = execute(arr)
        self.assertIn("RESULT_NOT_COMPLETE", result["issue_codes"])
        self.assertNotIn("SECRET_SENTINEL", json.dumps(result))

    def test_missing_result_fails(self):
        arr = sample_events()[:-1] + [{"type": "text", "text": MARKER}]
        self.assertIn("TERMINAL_RESULT_MISSING", execute(arr)["issue_codes"])

    def test_double_result_fails(self):
        arr = sample_events(); arr.append(arr[-1])
        self.assertIn("RESULT_CARDINALITY_INVALID", execute(arr)["issue_codes"])

    def test_tool_or_other_event_fails(self):
        for kind in ["tool_use", "tool_result", "system"]:
            arr = sample_events(); arr.insert(1, {"type": kind, "name": "terminal"})
            self.assertIn("UNEXPECTED_TOOL_OR_EVENT", execute(arr)["issue_codes"])

    def test_missing_tokens_fails(self):
        arr = sample_events(); arr[-1]["tokens"] = {"input": 0, "output": 0}
        self.assertIn("USAGE_NOT_OBSERVED", execute(arr)["issue_codes"])

    def test_replay_gap_fails(self):
        arr = sample_events(); arr[-1]["replay_gap"] = True
        self.assertIn("RESULT_NOT_COMPLETE", execute(arr)["issue_codes"])

    def test_stderr_extra_content_fails(self):
        self.assertIn("SESSION_STDERR_MISMATCH", execute(stderr=b"WARNING leaked secret\n") ["issue_codes"])

    def test_no_session_fails(self):
        arr = sample_events(); arr[-1]["session_id"] = ""
        self.assertIn("SESSION_IDENTITY_MISSING", execute(arr)["issue_codes"])

    def test_delta_mismatch_fails(self):
        arr = sample_events(); arr[1]["text"] = "other"
        self.assertIn("DELTA_RESULT_MISMATCH", execute(arr)["issue_codes"])

    def test_invalid_json_and_duplicate_key_fail(self):
        for stream in [b"hello", b'{"type":"system","type":"result"}\n{}\n',
                       b'"unstructured"\n"data"\n', b"a" * (64 * 1024 + 1)]:
            with self.subTest(size=len(stream)):
                self.assertIn("STREAM_INVALID", execute(stdout=stream)["issue_codes"])

    def test_meta_role_valid_model(self):
        model = "glm-5.3"
        self.assertEqual(execute(sample_events(model=model), role="mmmeta", expected_model=model)["status"],
                         "PASS_CHILD_OUTPUT_OBSERVATION_ONLY")


if __name__ == "__main__":
    unittest.main()
