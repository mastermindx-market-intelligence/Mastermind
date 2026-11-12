"""Closed GLM APPLICATION compiler and transport proof; no provider credentials or calls."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

from test_application_http_realm_projection import _pinned_inputs
from test_application_http_transports import SpyTransport, upstream, permit_for, binding_for
from _offline_boundary import acquire as offline_acquire, release as offline_release
import application_http_realm_projection as projection
import application_http_transports as transports

REPO = Path(__file__).resolve().parents[4]
GLM_PATH = REPO / "ops/native_fabric/paid_canonical_glm/candidate/glm_shim.py"
_spec = importlib.util.spec_from_file_location("qualified_glm_application_adapter", GLM_PATH)
glm_adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(glm_adapter)
GlmChatCompletionsDriver = glm_adapter.GlmChatCompletionsDriver
ENDPOINT = "https://api.z.ai/api/coding/paas/v4/chat/completions"
LOGICAL = {"model": "glm-5.3", "messages": [{"role": "user", "content": "Read the fixture."}], "max_tokens": 256}
CALL = {"id": "call_1", "type": "function", "function": {"name": "read_fixture", "arguments": "{ \"name\": \"sample\" }"}}
REASONING = "  Preserve this provider field exactly.\nSecond line: \u03b1.  "


def setUpModule():
    offline_acquire()


def tearDownModule():
    offline_release()


def projection_bytes():
    legacy = projection.compile_projection_bytes(_pinned_inputs())
    sources = {path: (REPO / path).read_bytes() for path, _sha, _blob in projection.GLM_INPUT_PINS}
    return projection.compile_glm_projection_bytes(
        sources, legacy_projection=legacy,
        legacy_sha256=hashlib.sha256(legacy).hexdigest(),
        source_commit="a" * 40,  # Synthetic test commitment, not a release receipt.
    )


def completed(*, tools=False, model="glm-5.3", usage=True, finish=None):
    message = {"role": "assistant", "content": None if tools else "Fixture checked.", "reasoning_content": REASONING}
    if tools:
        message["tool_calls"] = [copy.deepcopy(CALL)]
    result = {"model": model, "choices": [{"index": 0, "message": message, "finish_reason": finish or ("tool_calls" if tools else "stop")}]}
    if usage:
        result["usage"] = {"prompt_tokens": 11, "completion_tokens": 7}
    return result


class GlmApplicationTransportTests(unittest.TestCase):
    def setUp(self):
        self.payload = projection_bytes()

    def driver(self, transport):
        return GlmChatCompletionsDriver(
            transport=transport, clock=lambda: 1000.0,
            realm_projection=self.payload,
            projection_sha256=hashlib.sha256(self.payload).hexdigest(),
        )

    def test_v2_keeps_exact_legacy_projection_and_closed_glm_identity(self):
        legacy = projection.compile_projection_bytes(_pinned_inputs())
        document = projection.validate_projection(self.payload, expected_sha256=hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(json.loads(self.payload)["legacy_projection"], json.loads(legacy))
        self.assertEqual(len(document["drivers"]), 3)
        driver = self.driver(SpyTransport())
        self.assertEqual(driver.identity.endpoint, ENDPOINT)
        self.assertEqual(driver.identity.protocol, "openai-chat")
        self.assertIsNone(driver.identity.env_key)
        self.assertEqual(driver.identity.allowed_models, frozenset({"glm-5.3", "glm-5.3-flash"}))

    def test_projection_rejects_general_endpoint_keys_cross_pool_and_inventory_drift(self):
        mutations = [
            lambda d: d["drivers"][-1].update(endpoint="https://api.z.ai/api/paas/v4/chat/completions"),
            lambda d: d["drivers"][-1].update(env_key="UNRELATED_KEY"),
            lambda d: d["drivers"][-1].update(pool="bailian"),
            lambda d: d["drivers"][-1].update(protocol="responses"),
            lambda d: d["drivers"][-1].update(credential_owner="bailian_keys._codex_key_value"),
            lambda d: d["glm_sources"][0].update(sha256="0" * 64),
            lambda d: d["glm_sources"].append(dict(d["glm_sources"][0])),
            lambda d: d["drivers"].append(dict(d["drivers"][-1])),
            lambda d: d.update(glm_source_commit="0" * 40),
            lambda d: d["legacy_projection"]["drivers"][0].update(pool="glm"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                document = json.loads(self.payload)
                mutate(document)
                raw = json.dumps(document).encode()
                with self.assertRaises(projection.ProjectionRefused):
                    projection.validate_projection(raw, expected_sha256=hashlib.sha256(raw).hexdigest())
        with self.assertRaises(projection.ProjectionRefused):
            projection.validate_projection(self.payload, expected_sha256="0" * 64)

    def test_compiler_requires_complete_pinned_successor_sources(self):
        legacy = projection.compile_projection_bytes(_pinned_inputs())
        sources = {path: (REPO / path).read_bytes() for path, _sha, _blob in projection.GLM_INPUT_PINS}
        sources[next(iter(sources))] += b"\n# changed\n"
        with self.assertRaises(projection.ProjectionRefused):
            projection.compile_glm_projection_bytes(
                sources, legacy_projection=legacy, legacy_sha256=hashlib.sha256(legacy).hexdigest(), source_commit="a" * 40)

    def test_compiled_wire_bytes_account_and_usage_are_exact(self):
        spy = SpyTransport([upstream(completed(), endpoint=ENDPOINT)])
        driver = self.driver(spy)
        logical = copy.deepcopy(LOGICAL)
        compiled = driver.prepare_request(logical)
        expected = json.dumps({**logical, "stream": False}, ensure_ascii=True, allow_nan=False).encode()
        self.assertEqual(compiled.wire_body, expected)
        self.assertEqual(compiled.wire_body_digest, hashlib.sha256(expected).hexdigest())
        logical["messages"][0]["content"] = "Changed after preparation."
        seen = []
        binding = binding_for(account="glm-account", loader=lambda account: seen.append(account) or "synthetic-glm-key")
        result = driver.send_prepared(compiled, permit_for(compiled, account="glm-account"), binding)
        self.assertEqual(seen, ["glm-account"])
        self.assertEqual(len(spy.requests), 1)
        request = spy.requests[0]
        self.assertEqual(request.body, expected)
        self.assertEqual(request.url, ENDPOINT)
        self.assertFalse(request.allow_redirects)
        self.assertFalse(request.use_environment_proxy)
        self.assertEqual(result.disposition, "complete")
        self.assertEqual(result.result_status, "ok")
        self.assertEqual(result.served_model, "glm-5.3")
        self.assertEqual(result.usage, {"input_tokens": 11, "output_tokens": 7})
        self.assertEqual(result.normalized["reasoning_content"], REASONING)

    def test_tool_continuation_preserves_original_reasoning_ids_and_arguments(self):
        spy = SpyTransport([upstream(completed(tools=True), endpoint=ENDPOINT)])
        driver = self.driver(spy)
        compiled = driver.prepare_request(copy.deepcopy(LOGICAL))
        observation = driver.send_prepared(compiled, permit_for(compiled), binding_for())
        assistant = {"role": "assistant", "content": observation.normalized["text"],
                     "tool_calls": observation.normalized["tool_calls"],
                     "reasoning_content": observation.normalized["reasoning_content"]}
        continuation = copy.deepcopy(LOGICAL)
        continuation["messages"] += [assistant, {"role": "tool", "tool_call_id": "call_1", "content": "fixture value"}]
        wire = json.loads(driver.prepare_request(continuation).wire_body)
        self.assertEqual(wire["messages"][1]["reasoning_content"], REASONING)
        self.assertEqual(wire["messages"][1]["tool_calls"][0], CALL)
        self.assertEqual(wire["messages"][2]["tool_call_id"], CALL["id"])

    def test_unsupported_controls_refuse_before_transport_or_key_selection(self):
        cases = [
            {**LOGICAL, "stream": True},
            {**LOGICAL, "tool_choice": "required"},
            {**LOGICAL, "tool_choice": "none"},
            {**LOGICAL, "temperature": 0.2},
            {**LOGICAL, "model": "glm-4.7"},
            {**LOGICAL, "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.invalid/img"}}]}]},
            {**LOGICAL, "messages": [{"role": "tool", "tool_call_id": "orphan", "content": "bad"}]},
            {**LOGICAL, "messages": [{"role": "user", "content": "text", "reasoning_content": "invalid role"}]},
        ]
        spy = SpyTransport()
        driver = self.driver(spy)
        for logical in cases:
            with self.subTest(logical=logical):
                with self.assertRaises(transports.TransportRefused):
                    driver.prepare_request(logical)
        self.assertEqual(spy.requests, [])

    def test_duplicate_dispatch_never_sends_twice(self):
        spy = SpyTransport([upstream(completed(), endpoint=ENDPOINT)])
        driver = self.driver(spy)
        compiled = driver.prepare_request(LOGICAL)
        permit = permit_for(compiled)
        driver.send_prepared(compiled, permit, binding_for())
        with self.assertRaises(transports.TransportRefused):
            driver.send_prepared(compiled, permit, binding_for())
        self.assertEqual(len(spy.requests), 1)

    def test_incomplete_result_keeps_real_usage_without_delivering_answer(self):
        spy = SpyTransport([upstream(completed(finish="length"), endpoint=ENDPOINT)])
        driver = self.driver(spy)
        compiled = driver.prepare_request(LOGICAL)
        result = driver.send_prepared(compiled, permit_for(compiled), binding_for())
        self.assertEqual(result.disposition, "complete")
        self.assertEqual(result.result_status, "upstream_incomplete_output")
        self.assertIsNone(result.normalized)
        self.assertEqual(result.usage, {"input_tokens": 11, "output_tokens": 7})

    def test_missing_or_malformed_usage_stays_unknown(self):
        for value in [None, {"prompt_tokens": True, "completion_tokens": -1}, {"prompt_tokens": "11"}]:
            response = completed(usage=False)
            if value is not None:
                response["usage"] = value
            driver = self.driver(SpyTransport([upstream(response, endpoint=ENDPOINT)]))
            compiled = driver.prepare_request(LOGICAL)
            result = driver.send_prepared(compiled, permit_for(compiled), binding_for())
            self.assertEqual(result.usage, {"input_tokens": None, "output_tokens": None})

    def test_framing_and_endpoint_mismatch_remain_unknown(self):
        for response in [upstream(completed(), endpoint=ENDPOINT, framing=False),
                         upstream(completed(), endpoint="https://api.z.ai/api/paas/v4/chat/completions")]:
            spy = SpyTransport([response])
            driver = self.driver(spy)
            compiled = driver.prepare_request(LOGICAL)
            result = driver.send_prepared(compiled, permit_for(compiled), binding_for())
            self.assertEqual(result.disposition, "unknown")
            self.assertIsNone(result.normalized)
            self.assertEqual(len(spy.requests), 1)

    def test_driver_requires_projection_and_cannot_be_subclassed(self):
        with self.assertRaises(transports.TransportRefused):
            GlmChatCompletionsDriver(transport=SpyTransport(), realm_projection=None, projection_sha256=None)
        with self.assertRaises(TypeError):
            type("UnsealedGlm", (GlmChatCompletionsDriver,), {})


if __name__ == "__main__":
    unittest.main()
