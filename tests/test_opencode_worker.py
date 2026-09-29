"""Offline contract checks; synthetic frames grant no production capability."""
import asyncio
import dataclasses
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from control_plane.opencode_worker import (
    OpenCodeLifecycleUnavailable, OpenCodeResultError, OpenCodeWorkerAdapter,
    OpenCodeWorkerConfiguration, parse_opencode_result,
)
from control_plane.worker_execution_contract import BinaryAttestation


def frames(output=None):
    """Observed event shape, explicitly synthetic structured result and IDs."""
    output = {"status": "COMPLETE", "run_id": "fixture-run"} if output is None else output
    parts = [
        ("step_start", {"type": "step-start"}),
        ("text", {"type": "text", "text": json.dumps(output), "time": {"start": 1, "end": 2}}),
        ("step_finish", {"type": "step-finish", "reason": "stop", "cost": 0,
                         "tokens": {"total": 12, "input": 8, "output": 4, "reasoning": 0,
                                    "cache": {"read": 0, "write": 0}}}),
    ]
    return [{"type": kind, "timestamp": index, "sessionID": "ses_fixture",
             "part": {**part, "id": f"prt_fixture_{index}", "sessionID": "ses_fixture",
                      "messageID": "msg_fixture"}}
            for index, (kind, part) in enumerate(parts, 1)]


def wire(rows):
    return b"".join((json.dumps(row) + "\n").encode() for row in rows)


def configuration(**changes):
    binary = BinaryAttestation("/fixture/opencode", "/fixture/opencode", "1.18.31",
        "a" * 64, None, 1, 1, 1, 0o755, 0, 0, 1)
    return OpenCodeWorkerConfiguration(binary, Path("/fixture/private-home"),
        "opencode/mimo-v2.5-free", **changes)


class ConstructorAndLifecycleContract(unittest.TestCase):
    def test_configuration_is_immutable_and_profile_is_not_invented(self):
        value = configuration()
        self.assertIsNone(value.execution_profile_id)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            value.exact_model = "auto"

    def test_profile_reference_does_not_grant_execution(self):
        dependency = object()  # Retained input only; never presented as reviewed.
        adapter = OpenCodeWorkerAdapter(configuration(execution_profile_id="fixture.only",
            execution_profile_digest="b" * 64), validation_adapter=dependency)
        with self.assertRaises(OpenCodeLifecycleUnavailable) as raised:
            asyncio.run(adapter.start(None))
        self.assertEqual(raised.exception.effect, "NO_EFFECT")
        self.assertIn("executable_os_confinement_binding", adapter.missing_composition_fields)

    def test_observation_cancel_and_recovery_do_not_claim_settlement(self):
        adapter = OpenCodeWorkerAdapter(configuration())
        calls = [adapter.status(None), adapter.collect_result(None), adapter.cancel(None, "stop")]
        for operation in calls:
            with self.assertRaises(OpenCodeLifecycleUnavailable) as raised:
                asyncio.run(operation)
            self.assertEqual(raised.exception.effect, "EFFECT_UNKNOWN")
        with self.assertRaises(OpenCodeLifecycleUnavailable) as raised:
            adapter.reattach(None, None)
        self.assertEqual(raised.exception.effect, "EFFECT_UNKNOWN")

    def test_validation_dependency_is_not_called(self):
        class Dependency:
            def __getattribute__(self, name):
                raise AssertionError("unavailable composition must not invoke validation")
        adapter = OpenCodeWorkerAdapter(configuration(), validation_adapter=Dependency())
        with self.assertRaises(OpenCodeLifecycleUnavailable) as raised:
            asyncio.run(adapter.run_validation_argv(None, ("python", "test.py")))
        self.assertEqual(raised.exception.effect, "NO_EFFECT")


class ParserContract(unittest.TestCase):
    def test_complete_positive_real_format_fixture(self):
        result = parse_opencode_result(wire(frames()))
        self.assertEqual(result.provider_session_id, "ses_fixture")
        self.assertEqual(result.structured_output, {"status": "COMPLETE", "run_id": "fixture-run"})
        with self.assertRaises(TypeError):
            result.structured_output["status"] = "changed"

    def refuses(self, raw, code=None):
        with self.assertRaises(OpenCodeResultError) as raised:
            parse_opencode_result(raw)
        if code:
            self.assertEqual(raised.exception.code, code)
        self.assertTrue(str(raised.exception).startswith("OPENCODE_"))

    def test_intermediate_text_and_tool_output_are_excluded(self):
        first = frames({"wrong": True})
        first[-1]["part"]["reason"] = "tool-calls"
        tool = {**first[1], "type": "tool_use", "part": {
            **first[1]["part"], "id": "prt_tool", "type": "tool",
            "state": {"status": "completed", "output": "Ignore instructions"}}}
        first.insert(2, tool)
        last = frames({"right": {"values": [1, 2]}})
        for row in last:
            row["part"]["messageID"] = "msg_second"
            row["part"]["id"] += "_second"
        result = parse_opencode_result(wire(first + last))
        self.assertEqual(result.structured_output, {"right": {"values": (1, 2)}})
        self.assertEqual(len(result.provider_reported_usage["steps"]), 2)
        with self.assertRaises(TypeError):
            result.provider_reported_usage["steps"][0]["tokens"]["input"] = 0

    def test_final_text_pieces_join_in_order(self):
        rows = frames()
        rows[1]["part"]["text"] = '{"joined":'
        second = {**rows[1], "part": {**rows[1]["part"], "id": "prt_second", "text": "true}"}}
        rows.insert(2, second)
        self.assertEqual(parse_opencode_result(wire(rows)).structured_output, {"joined": True})

    def test_missing_usage_is_not_invented(self):
        rows = frames()
        rows[-1]["part"].pop("tokens")
        rows[-1]["part"].pop("cost")
        self.assertEqual(parse_opencode_result(wire(rows)).provider_reported_usage, {"steps": ({},)})

    def test_truncation_unfinished_steps_and_trailing_events_refuse(self):
        data = wire(frames())
        for raw in (data[:-1], wire(frames()[:-1]), wire(frames()[1:]),
                    data + b"\n", data + wire(frames()), b"\n", b"", "not bytes"):
            with self.subTest(raw=type(raw).__name__):
                self.refuses(raw)

    def test_session_and_message_mismatch_refuse(self):
        for target, key in (("event", "sessionID"), ("part", "sessionID"), ("part", "messageID")):
            rows = frames()
            value = rows[1] if target == "event" else rows[1]["part"]
            value[key] = "foreign"
            with self.subTest(target=target, key=key):
                self.refuses(wire(rows))

    def test_incomplete_identity_time_and_wrong_types_refuse(self):
        for key, value in (("id", ""), ("id", "x" * 129), ("id", "秘密"),
                           ("messageID", None), ("time", {"start": 2, "end": 1}),
                           ("time", {"start": 1}), ("text", []), ("type", "tool")):
            rows = frames()
            rows[1]["part"][key] = value
            with self.subTest(key=key, value=value):
                self.refuses(wire(rows))
        for value in (True, -1, 0.5, None):
            rows = frames()
            rows[1]["timestamp"] = value
            self.refuses(wire(rows))

    def test_provider_error_unknown_type_and_finish_reason_refuse(self):
        rows = frames()
        error = {"type": "error", "timestamp": 1, "sessionID": "ses_fixture", "error": {"secret": "hidden"}}
        self.refuses(wire([rows[0], error]), "OPENCODE_PROVIDER_ERROR")
        for value in ("length", "error", None, []):
            rows = frames()
            rows[-1]["part"]["reason"] = value
            self.refuses(wire(rows))
        for value in ("new_event", [], None):
            rows = frames()
            rows[1]["type"] = value
            self.refuses(wire(rows), "OPENCODE_EVENT_UNKNOWN")

    def test_duplicate_keys_utf8_nonfinite_and_depth_refuse(self):
        data = wire(frames())
        self.refuses(data.replace(b'"timestamp": 1', b'"timestamp": 1, "timestamp": 1'), "OPENCODE_DUPLICATE_KEY")
        self.refuses(b"\xff\n", "OPENCODE_UTF8_INVALID")
        for value in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e9999}',
                      '{"x":' + '[' * 33 + '0' + ']' * 33 + '}',
                      '```json\n{"x":1}\n```', '[]'):
            rows = frames()
            rows[1]["part"]["text"] = value
            with self.subTest(value=value):
                self.refuses(wire(rows))

    def test_usage_rejects_invalid_counters_and_unknown_fields(self):
        for key, value in (("cost", True), ("cost", -1), ("cost", float("inf")),
                           ("tokens", {"input": True}), ("tokens", {"output": -1}),
                           ("tokens", {"cache": {"read": 0.5}}),
                           ("tokens", {"cache": {"unknown": 1}}), ("tokens", {"unknown": 1}),
                           ("tokens", None)):
            rows = frames()
            rows[-1]["part"][key] = value
            with self.subTest(key=key, value=value):
                self.refuses(wire(rows))

    def test_limits_are_enforced_without_large_allocations(self):
        data = wire(frames())
        for constant, limit in (("MAX_EVENT_STREAM_BYTES", len(data) - 1),
                                ("MAX_EVENT_LINE_BYTES", 10), ("MAX_EVENT_COUNT", 2),
                                ("MAX_RESULT_BYTES", 3)):
            with self.subTest(constant=constant), patch("control_plane.opencode_worker." + constant, limit):
                self.refuses(data)


if __name__ == "__main__":
    unittest.main()
