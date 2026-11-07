"""Contract tests; real manifest qualification is a separate native receipt."""
from __future__ import annotations
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "effort_config", ROOT / "integrations/hermes_omh/effort_config.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def schema():
    types = {
        "mode": "str", "subagent_mode": "str", "scorer_provider": "str",
        "jev_model": "str", "timeout_s": "float", "prompt_chars": "int",
        "dialogue_context_messages": "int", "use_target_model_context": "bool",
        "continuation_downgrade_votes": "int", "dynamic_trial": "bool",
        "tool_error_escalation": "bool", "scorer_pause_failures": "int",
        "scorer_pause_s": "float", "max_turns": "int",
        "classification_instructions": "str", "effort_models": "str",
    }
    result = {k: {"type": v} for k, v in types.items()}
    for key in ("mode", "subagent_mode"):
        result[key]["choices"] = ["auto", "once", "always", "off"]
    return result


class EffortConfigTests(unittest.TestCase):
    def test_stages_off_without_invented_keys(self):
        value = m.candidate_settings(schema())
        self.assertEqual(value["mode"], "off")
        self.assertFalse(set(value) & m.RETIRED_KEYS)
        self.assertEqual(value["subagent_mode"], "off")

    def test_dynamic_candidate_really_is_per_turn(self):
        self.assertEqual(m.candidate_settings(schema(), "always")["mode"], "always")
        for mode in ("auto", "once", "shadow", "unknown"):
            with self.subTest(mode=mode), self.assertRaises(m.ConfigurationError):
                m.candidate_settings(schema(), mode)

    def test_each_legacy_field_rejected(self):
        for key in m.RETIRED_KEYS:
            with self.subTest(key=key), self.assertRaisesRegex(
                    m.ConfigurationError, "UNSUPPORTED_LEGACY_SETTING"):
                m.validate_settings({key: True}, schema())

    def test_unknown_field_error_does_not_echo_secret(self):
        with self.assertRaises(m.ConfigurationError) as error:
            m.validate_settings({"secret-key-example": "secret-value-example"}, schema())
        self.assertEqual(str(error.exception), "UNKNOWN_SETTING")

    def test_bool_is_not_int_or_float_and_numbers_must_be_finite(self):
        for key, value in [("timeout_s", True), ("timeout_s", float("inf")),
                           ("timeout_s", float("nan")), ("prompt_chars", True),
                           ("mode", False), ("dynamic_trial", "false")]:
            with self.subTest(key=key, value=value), self.assertRaises(m.ConfigurationError):
                m.validate_settings({key: value}, schema())

    def test_no_silent_expansion_of_child_or_data_scope(self):
        for key, value in [("subagent_mode", "once"), ("effort_models", "unknown"),
                           ("dialogue_context_messages", 1),
                           ("use_target_model_context", True),
                           ("continuation_downgrade_votes", 1)]:
            with self.subTest(key=key), self.assertRaises(m.ConfigurationError):
                m.validate_settings({key: value}, schema())

    def test_no_input_mutation(self):
        original = schema()
        before = copy.deepcopy(original)
        m.candidate_settings(original)
        self.assertEqual(original, before)

    def test_empty_or_changed_manifest_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plugin.yaml"
            for text in ("", "id: hermes-adaptive-effort\n", "x" * 65537):
                path.write_text(text)
                with self.subTest(length=len(text)), self.assertRaises(m.ConfigurationError):
                    m.load_schema(path)

    def test_manifest_missing_setting_is_not_ignored(self):
        drift = schema()
        del drift["dynamic_trial"]
        with self.assertRaisesRegex(m.ConfigurationError, "UNKNOWN_SETTING"):
            m.candidate_settings(drift)

    def test_settings_are_not_a_readiness_claim(self):
        result = m.candidate_settings(schema())
        self.assertNotIn("ready", result)
        self.assertNotIn("api_key", result)
        self.assertNotIn("model", result)
        self.assertNotIn("provider", result)


if __name__ == "__main__":
    unittest.main()
