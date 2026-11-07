"""Offline native text integration: explicit role, one-shot, bounded result.

No provider call, service installation, Slack send, credential read or network.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from integrations.hermes_harness.native_text import (
    MAX_PROMPT_BYTES, NativeTextInference, canonical_text_prompt,
    execute_prepared_text, text_result, _qualified_text,
)
from integrations.hermes_harness.native_turn_evidence import (
    ObservationRefusal, read_native_text,
)
from integrations.hermes_harness.native_turn_runner import _capture_bounded_child
from integrations.hermes_runtime.cli import _text_turn
from integrations.hermes_runtime.errors import NativeTurnEffectUnknown, RuntimeRefusal
from integrations.hermes_secretary.native_dialogue_consumer import _message_prompt


ROLE = "mmsecretary"
MODEL = "glm-5-3-flash-260828"


def _canonical() -> str:
    return _message_prompt(
        {"summary": "Please provide progress.", "body": {"instruction": "Status only",
                                                         "scope_change": False}},
        role=ROLE,
    )


def _native_stream(answer: str = "Progress recorded.", *, extra: dict | None = None) -> bytes:
    session = "native-s1"
    events = [
        {"type": "system", "subtype": "init", "model": "", "session_id": ""},
        {"type": "text", "text": answer},
        {"type": "result", "exit_code": 0, "error": False, "replay_gap": False,
         "text": answer, "tokens": {"input": 12, "output": 4}, "session_id": session},
    ]
    if extra is not None:
        events.insert(2, extra)
    return ("\n".join(json.dumps(event) for event in events) + "\n").encode()


class CanonicalTextTests(unittest.TestCase):
    def test_only_exact_existing_canonical_prompt(self):
        prompt = _canonical()
        self.assertEqual(canonical_text_prompt(prompt, role=ROLE), (ROLE, prompt))
        self.assertEqual(canonical_text_prompt(prompt)[1], prompt)

    def test_role_and_instruction_mutation_refused(self):
        prompt = _canonical()
        for value, role in [
            (prompt, "mmmeta"),
            (prompt.replace("mmsecretary", "mmmeta"), ROLE),
            (prompt.replace("reply_with_bounded_progress", "send_slack"), ROLE),
            (prompt + "\n", ROLE),
        ]:
            with self.subTest(value=value[-16:], role=role):
                with self.assertRaises(RuntimeRefusal):
                    canonical_text_prompt(value, role=role)

    def test_duplicate_json_nonfinite_and_oversize_refused(self):
        for value in ['{"role":"mmsecretary","role":"mmmeta"}',
                      _canonical().replace('"scope_change":false', '"scope_change":NaN'),
                      "z" * (MAX_PROMPT_BYTES + 1), ""]:
            with self.subTest(value=value[:24]):
                with self.assertRaises(RuntimeRefusal):
                    canonical_text_prompt(value, role=ROLE)

    def test_result_effect_disposition_is_not_retry_authority(self):
        self.assertEqual(text_result("REFUSED")["may_have_provider_effect"], False)
        self.assertEqual(text_result("EFFECT_UNKNOWN")["may_have_provider_effect"], True)
        self.assertEqual(text_result("TEXT_READY", text="ready")["text"], "ready")
        with self.assertRaises(ValueError):
            text_result("SUCCESS")

    def test_secret_and_control_text_refused(self):
        self.assertEqual(_qualified_text("Progress recorded."), "Progress recorded.")
        for value in ["", " ", "a" * 701, "api_key=sk-secret", "\x01bad"]:
            with self.subTest(value=value[:15]):
                with self.assertRaises((ValueError, UnicodeError)):
                    _qualified_text(value)


class NativeProtocolTests(unittest.TestCase):
    def test_positive_complete_text_protocol(self):
        self.assertEqual(
            read_native_text(role=ROLE, expected_model=MODEL, stdout=_native_stream(),
                             stderr=b"Session: native-s1\n\nsession_id: native-s1\n", process_exit_code=0),
            "Progress recorded.",
        )

    def test_refuses_tool_event_and_model_mismatch(self):
        for kwargs in [
            {"stdout": _native_stream(extra={"type": "tool", "name": "shell"})},
            {"expected_model": "glm-5.3"},
            {"stderr": b"session_id: different\n"},
            {"process_exit_code": 1},
            {"stdout": _native_stream("a" * 701)},
        ]:
            base = dict(role=ROLE, expected_model=MODEL, stdout=_native_stream(),
                        stderr=b"Session: native-s1\n\nsession_id: native-s1\n", process_exit_code=0)
            base.update(kwargs)
            with self.subTest(keys=kwargs):
                with self.assertRaises(ObservationRefusal):
                    read_native_text(**base)

    def test_executes_one_mock_native_child_or_fails_unknown(self):
        profile = SimpleNamespace(role=ROLE, native_provider_id="example",
                                  hermes_home=Path("/private/tmp"))
        spec = SimpleNamespace(served_model=MODEL, credential_env="MODEL_KEY")
        env = {"MODEL_KEY": "private_model_value"}
        with mock.patch("integrations.hermes_harness.native_text._private_child_environment",
                        return_value=env), mock.patch(
            "integrations.hermes_harness.native_text.native_provider", return_value=spec,
        ), mock.patch(
            "integrations.hermes_harness.native_text._capture_bounded_child",
            return_value=(0, _native_stream(), b"Session: native-s1\n\nsession_id: native-s1\n"),
        ) as capture:
            self.assertEqual(execute_prepared_text(
                profile, hermes_bin=Path("/installed/bin/hermes"),
                model_env=env, prompt=_canonical()), "Progress recorded.")
            capture.assert_called_once()
        with mock.patch("integrations.hermes_harness.native_text._private_child_environment",
                        return_value=env), mock.patch(
            "integrations.hermes_harness.native_text.native_provider", return_value=spec,
        ), mock.patch(
            "integrations.hermes_harness.native_text._capture_bounded_child",
            return_value=(1, b"", b"secret possible"),
        ) as capture:
            with self.assertRaises(NativeTurnEffectUnknown):
                execute_prepared_text(profile, hermes_bin=Path("/installed/bin/hermes"),
                                      model_env=env, prompt=_canonical())
            capture.assert_called_once()


class ChildCaptureTests(unittest.TestCase):
    def test_8192_byte_stdin_is_drained_without_unbounded_capture(self):
        prompt = b"x" * 8192
        script = "import sys; data=sys.stdin.buffer.read(); sys.stdout.write(str(len(data)))"
        with tempfile.TemporaryDirectory() as home:
            rc, stdout, stderr = _capture_bounded_child(
                [sys.executable, "-B", "-c", script], prompt,
                env={"PATH": os.defpath}, cwd=Path(home), timeout_seconds=4.0,
                max_prompt_bytes=8192,
            )
        self.assertEqual((rc, stdout, stderr), (0, b"8192", b""))

    def test_oversized_input_refuses_before_subprocess(self):
        with mock.patch("integrations.hermes_harness.native_turn_runner.subprocess.Popen") as popen:
            with self.assertRaises(RuntimeRefusal):
                _capture_bounded_child(
                    ["nonexistent"], b"x" * 8193, env={}, cwd=Path("/private/tmp"),
                    timeout_seconds=2.0, max_prompt_bytes=8192,
                )
            popen.assert_not_called()


class CliTextTests(unittest.TestCase):
    def _run(self, payload: str):
        out = io.StringIO()
        stream = SimpleNamespace(buffer=io.BytesIO(payload.encode()))
        with mock.patch("sys.stdin", stream), contextlib.redirect_stdout(out):
            rc = _text_turn(Path("/installed/profile.yaml"), Path("/installed/bin/hermes"))
        return rc, json.loads(out.getvalue())

    def test_rejected_prompt_never_loads_credentials(self):
        with mock.patch("integrations.hermes_runtime.cli._prepare_installed_native") as prepare:
            rc, data = self._run("not a canonical prompt")
            self.assertEqual(rc, 2)
            self.assertEqual(data, text_result("REFUSED"))
            prepare.assert_not_called()

    def test_prelaunch_refusal_and_postlaunch_uncertainty_are_distinct(self):
        with mock.patch("integrations.hermes_runtime.cli._prepare_installed_native",
                        side_effect=RuntimeRefusal("CANARY_NOT_INSTALLED_ROLE")):
            rc, data = self._run(_canonical())
            self.assertEqual((rc, data), (2, text_result("REFUSED")))
        with mock.patch("integrations.hermes_runtime.cli._prepare_installed_native",
                        return_value=(SimpleNamespace(role=ROLE), {"MODEL_KEY": "secret"})), mock.patch(
            "integrations.hermes_harness.native_text.execute_prepared_text",
            side_effect=NativeTurnEffectUnknown(),
        ) as native:
            rc, data = self._run(_canonical())
            self.assertEqual((rc, data), (3, text_result("EFFECT_UNKNOWN")))
            native.assert_called_once()

    def test_ready_text_returns_only_bounded_schema(self):
        with mock.patch("integrations.hermes_runtime.cli._prepare_installed_native",
                        return_value=(SimpleNamespace(role=ROLE), {"MODEL_KEY": "secret"})), mock.patch(
            "integrations.hermes_harness.native_text.execute_prepared_text",
            return_value="Progress recorded.",
        ) as native:
            rc, data = self._run(_canonical())
            self.assertEqual((rc, data), (0, text_result("TEXT_READY", text="Progress recorded.")))
            native.assert_called_once()


if __name__ == "__main__":
    unittest.main()
