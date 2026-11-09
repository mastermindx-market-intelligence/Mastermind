"""Runs in the installed Hermes dependency environment, including jsonschema."""
import copy
import json
import unittest
from unittest.mock import patch

import test_owner_integration as fixtures
from integrations.hermes_application_fabric.errors import HermesFabricError


class StructuredOutputTests(unittest.TestCase):
    setUp = fixtures.OwnerLoopbackTests.setUp
    tearDown = fixtures.OwnerLoopbackTests.tearDown
    invoke = fixtures.OwnerLoopbackTests.invoke

    def format(self, schema=None):
        return {"type": "json_schema", "json_schema": {"name": "answer", "strict": True,
            "schema": schema if schema is not None else {"type": "object",
                "properties": {"answer": {"type": "integer"}}, "required": ["answer"],
                "additionalProperties": False}}}

    def test_schema_result_is_validated_json_never_an_executable_tool(self):
        self.mode = "structured"
        fmt = self.format()
        before = copy.deepcopy(fmt)
        result = self.invoke(response_format=fmt)
        self.assertEqual(json.loads(result.choices[0].message.content), {"answer": 42})
        self.assertIsNone(result.choices[0].message.tool_calls)
        self.assertEqual(result.choices[0].finish_reason, "stop")
        self.assertEqual((result.model, result.usage.total_tokens), ("model-1", 18))
        self.assertEqual(fmt, before)
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn("response_format", self.calls[0]["payload"])
        self.assertEqual(self.calls[0]["payload"]["tool_choice"]["function"]["name"],
                         "mmx_hermes_structured_result")

    def test_json_object_mode(self):
        self.mode, self.structured_value = "structured", {"values": [1, "世界", None]}
        result = self.invoke(response_format={"type": "json_object"})
        self.assertEqual(json.loads(result.choices[0].message.content), self.structured_value)

    def test_invalid_output_is_terminal_without_repair_or_replay(self):
        self.mode, self.structured_value = "structured", {"answer": "wrong type"}
        for _ in range(2):
            with self.assertRaises(HermesFabricError):
                self.invoke(response_format=self.format())
        self.assertEqual(len(self.calls), 1)

    def test_extra_fields_are_rejected_by_schema(self):
        self.mode, self.structured_value = "structured", {"answer": 42, "unexpected": True}
        with self.assertRaises(HermesFabricError):
            self.invoke(response_format=self.format())
        self.assertEqual(len(self.calls), 1)

    def test_multiple_structured_calls_are_not_silently_joined(self):
        self.mode = "structured-many"
        with self.assertRaises(HermesFabricError):
            self.invoke(response_format=self.format())
        self.assertEqual(len(self.calls), 1)

    def test_text_preamble_is_not_silently_discarded(self):
        self.mode = "structured-preamble"
        with self.assertRaises(HermesFabricError):
            self.invoke(response_format=self.format())

    def test_unknown_reference_regex_and_recursive_vocabulary_refuse_before_call(self):
        schemas = [{"type": "object", "$ref": "https://untrusted.invalid/schema"},
            {"type": "object", "$defs": {"loop": {"$ref": "#"}}},
            {"type": "object", "$schema": "https://json-schema.org/draft-07/schema#"},
            {"type": "object", "properties": {"x": {"type": "string", "pattern": "(a+)+$"}}},
            {"type": "object", "unevaluatedProperties": False}, {"type": "array"},
            {"type": "object", "required": "wrong"}]
        for schema in schemas:
            with self.subTest(schema=schema), self.assertRaises(HermesFabricError):
                self.invoke(response_format=self.format(schema))
        self.assertEqual(self.calls, [])

    def test_user_tool_mixture_is_explicitly_refused(self):
        with self.assertRaises(HermesFabricError):
            self.invoke(response_format=self.format(), tools=[{"type": "function", "function": {
                "name": "read", "parameters": {}}}])
        self.assertEqual(self.calls, [])

    def test_missing_validator_is_not_a_permissive_fallback(self):
        with patch.dict("sys.modules", {"jsonschema": None}), self.assertRaises(HermesFabricError):
            self.invoke(response_format=self.format())
        self.assertEqual(self.calls, [])
