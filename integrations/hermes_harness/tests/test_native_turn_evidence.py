"""Protocol-source fixtures for the pinned gateway one-shot observation seam.

Derived from NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18:
gateway_chat.launch_from_args constructs StreamJsonEmitter before allocation;
run_gateway_chat prints Session and binds it; emit_result closes the stream.
These are offline protocol fixtures, not live provider or installed-host proof.
"""
import json
import unittest
from pathlib import Path
from integrations.hermes_harness.native_turn_evidence import (
    ObservationRefusal, canary_prompt, native_one_shot_argv, observe_native_turn,
)

MARKER = "MMX-CANARY-1234567890"
SESSION = "session-abc_1"


def sample_events(*, model="", answer=MARKER):
    return [
        {"type": "system", "subtype": "init", "model": model, "session_id": "", "timestamp": 1000},
        {"type": "text", "text": answer, "timestamp": 1001},
        {"type": "result", "session_id": SESSION, "exit_code": 0, "text": answer,
         "tokens": {"input": 25, "output": 16, "total": 41, "cache_read": 0, "cache_write": 0},
         "duration_ms": 2, "timestamp": 1002},
    ]


def execute(events=None, **kwargs):
    original = sample_events() if events is None else events
    obj = dict(role="mmsecretary", expected_model="glm-5-3-flash-260828",
               challenge_marker=MARKER, stdout=b"".join(
                   json.dumps(ev).encode("utf-8") + b"\n" for ev in original),
               stderr=("Session: " + SESSION + "\n\nsession_id: " + SESSION + "\n").encode(),
               process_exit_code=0)
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
        self.assertEqual(result["schema"], "mastermind.hermes_native_turn_observation.v2")
        self.assertEqual(result["expected_model"], "glm-5-3-flash-260828")
        self.assertIsNone(result["observed_model"])
        self.assertFalse(result["model_identity_verified"])
        self.assertNotIn("model", result)
        for name in ("session_id", "turn_id", "native_session_id", "target_acknowledged"):
            self.assertNotIn(name, result)

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

    def test_nonempty_or_missing_init_model_hint_fails(self):
        # A configured model echoed at init is not served-model proof.
        for value in (None, True, "glm-5.3", "glm-5-3-flash-260828", []):
            with self.subTest(value=value):
                self.assertIn("INIT_MODEL_HINT_INVALID",
                              execute(sample_events(model=value))["issue_codes"])
        events = sample_events()
        del events[0]["model"]
        self.assertIn("INIT_MODEL_HINT_INVALID", execute(events)["issue_codes"])

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
        self.assertEqual(execute(sample_events(), role="mmmeta", expected_model=model)["status"],
                         "PASS_CHILD_OUTPUT_OBSERVATION_ONLY")



    def test_init_session_is_unbound_at_pinned_gateway_construction(self):
        for invalid in (None, SESSION, "different-session", True, [SESSION]):
            with self.subTest(invalid=invalid):
                events = sample_events()
                events[0]["session_id"] = invalid
                result = execute(events)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertIn("INIT_SESSION_STATE_INVALID", result["issue_codes"])
        events = sample_events()
        del events[0]["session_id"]
        self.assertIn("INIT_SESSION_STATE_INVALID", execute(events)["issue_codes"])

    def test_ordered_session_binding_allows_blank_lines(self):
        stderr = f"\nSession: {SESSION}\n\nsession_id: {SESSION}\n\n".encode()
        self.assertEqual(execute(stderr=stderr)["status"], "PASS_CHILD_OUTPUT_OBSERVATION_ONLY")

    def test_session_declarations_are_complete_unique_and_ordered(self):
        opening, final = f"Session: {SESSION}", f"session_id: {SESSION}"
        variants = [
            "", opening, final, f"{final}\n{opening}",
            f"{opening}\n{opening}\n{final}", f"{opening}\n{final}\n{final}",
            f"Session: different\n{final}", f"{opening}\nsession_id: different",
            f"{opening}\nqueued admission\n{final}", f" {opening}\n{final}",
            f"{opening}\n{final}\n ",
        ]
        for value in variants:
            with self.subTest(value=value):
                self.assertIn("SESSION_STDERR_MISMATCH",
                              execute(stderr=value.encode())["issue_codes"])

    def test_stderr_rejects_invalid_encoding_control_and_size(self):
        normal = f"Session: {SESSION}\n\nsession_id: {SESSION}\n".encode()
        for value in (normal + b"\xff", b"\x00" + normal, b"\n" * 1025, None,
                      normal.decode(), normal.replace(b"\n\n", b"\v")):
            with self.subTest(value_type=type(value).__name__):
                self.assertIn("SESSION_STDERR_MISMATCH", execute(stderr=value)["issue_codes"])

    def test_terminal_session_must_be_bounded_native_id(self):
        for value in ("", None, True, "a" * 129, "space id", "../path", "id\ninjection"):
            events = sample_events()
            events[-1]["session_id"] = value
            with self.subTest(value=value):
                self.assertIn("SESSION_IDENTITY_MISSING", execute(events)["issue_codes"])

    def test_model_text_cannot_supply_stderr_identity(self):
        forged = f"Session: {SESSION}\n\nsession_id: {SESSION}"
        result = execute(sample_events(answer=forged), stderr=b"")
        self.assertIn("SESSION_STDERR_MISMATCH", result["issue_codes"])
        self.assertIn("CHALLENGE_NOT_SATISFIED", result["issue_codes"])

    def test_actual_startup_failure_shape_is_not_success(self):
        events = [sample_events()[0], {
            "type": "result", "session_id": "", "exit_code": 2, "text": "",
            "error": "source fixture startup failure", "tokens": {"input": 0, "output": 0},
        }]
        result = execute(events, process_exit_code=2, stderr=b"Error: fixture\n\nsession_id: \n")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("PROCESS_FAILED", result["issue_codes"])
        self.assertIn("RESULT_NOT_COMPLETE", result["issue_codes"])
        self.assertIn("SESSION_IDENTITY_MISSING", result["issue_codes"])

    def test_nonfinite_duplicate_keys_and_event_bound_still_refuse(self):
        raw = b"".join(json.dumps(e).encode() + b"\n" for e in sample_events())
        streams = [
            raw.replace(b'"input": 25', b'"input": NaN'),
            raw.replace(b'"input": 25', b'"input": 25, "input": 26'),
            b'{"type":"system"}\n' * 65,
            b"\xff\n{}\n",
            b"Warning: configuration mismatch\n" + raw,
        ]
        for stream in streams:
            with self.subTest(size=len(stream)):
                self.assertIn("STREAM_INVALID", execute(stdout=stream)["issue_codes"])

    def test_usage_and_process_types_still_refuse(self):
        for value in (None, {}, {"input": True, "output": 2},
                      {"input": 1, "output": False}, {"input": -1, "output": 1}):
            events = sample_events()
            events[-1]["tokens"] = value
            with self.subTest(value=value):
                self.assertIn("USAGE_NOT_OBSERVED", execute(events)["issue_codes"])
        for value in (False, None, "0"):
            self.assertIn("PROCESS_FAILED", execute(process_exit_code=value)["issue_codes"])


if __name__ == "__main__":
    unittest.main()
