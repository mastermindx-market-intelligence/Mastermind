"""Fixed native Responses transport drivers: synthetic source proof only.

These fixtures exercise the driver component with an in-process I/O spy and
synthetic payloads. Compilation is not application admission. MiniMax remains
unjoined; Bailian requires its exact recipe, authenticated credential reference
and current grant through the same broker. The final tests prove that merely
naming either pool cannot authorize a turn. No provider or real credential is
touched. The separate Bailian handler suite proves the actual admitted join.
"""
import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "candidate"), str(ROOT / "source"), str(ROOT / "tests"), str(REPO)]

from _offline_boundary import acquire as offline_acquire, release as offline_release

import application_http_transports as transports
from application_http_transports import (
    AccountBinding,
    BailianResponsesDriver,
    CompiledCall,
    DispatchPermit,
    MiniMaxResponsesDriver,
    TransportRefused,
    TransportRequest,
    TransportResponse,
)

import lease_broker
from control_plane.codex_provider_realm import (
    ALIBABA_TOKEN_PLAN,
    MINIMAX_TOKEN_PLAN,
    REVIEWED_CODEX_PROVIDER_REALMS,
)
from control_plane.provider_protocols import PROVIDER_PROTOCOLS, validate_provider_protocol


def setUpModule():
    offline_acquire()


def tearDownModule():
    offline_release()


MINIMAX_ENDPOINT = MINIMAX_TOKEN_PLAN.base_url + "/responses"
BAILIAN_ENDPOINT = ALIBABA_TOKEN_PLAN.base_url + "/responses"

LOGICAL = {
    "model": "MiniMax-M3",
    "messages": [
        {"role": "system", "content": "be exact"},
        {"role": "user", "content": [{"type": "text", "text": "list two files"}]},
        {"role": "assistant", "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "list_files", "arguments": "{\"dir\":\"a\"}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "a.txt"},
        {"role": "assistant", "content": "done"},
    ],
    "tools": [{"type": "function", "function": {
        "name": "list_files", "description": "list", "strict": True,
        "parameters": {"type": "object", "properties": {"dir": {"type": "string"}}}}}],
    "tool_choice": "auto",
    "max_tokens": 512,
}


class SpyTransport:
    """In-process I/O spy. A second invocation is a failure, not a retry."""

    def __init__(self, responses=None, error=None):
        self.requests = []
        self.responses = list(responses or [])
        self.error = error

    def __call__(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if not self.responses:
            raise AssertionError("transport invoked more times than expected")
        return self.responses.pop(0)


def upstream(body, status=200, endpoint=MINIMAX_ENDPOINT, framing=True, content_length=None):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    return TransportResponse(status=status, headers={}, body=raw, final_url=endpoint,
                              framing_complete=framing, declared_content_length=content_length)


def complete_responses(text="hello", model="MiniMax-M3", usage=(11, 7)):
    return {
        "id": "resp_fixture", "status": "completed", "model": model,
        "output": [{"type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": text}]}],
        "usage": {"input_tokens": usage[0], "output_tokens": usage[1]},
    }


def permit_for(compiled, *, dispatch_id="dispatch-1", account="acct-a", model=None,
               expires_at=2000.0, logical_digest=None, wire_digest=None,
               lease_id="lease-1", permitted=True, clock=1000.0):
    """A fixture permit. NOT application admission: root's join must bind the
    compiled logical digest and the exact expected native wire digest into the
    same original A request record that holds ``request_digest``."""
    return DispatchPermit(
        dispatch_id=dispatch_id,
        request_digest="a" * 64,
        logical_payload_digest=logical_digest or compiled.logical_payload_digest,
        wire_body_digest=wire_digest or compiled.wire_body_digest,
        account=account,
        model=model or compiled.model,
        lease_id=lease_id,
        expires_at=expires_at,
        dispatch_permitted=permitted,
    )


def binding_for(account="acct-a", loader=None, eligibility=None):
    return AccountBinding(account=account,
                          credential_loader=loader or (lambda _account: "fixture-key"),
                          eligibility=eligibility)


class DriverFixture(unittest.TestCase):
    def setUp(self):
        self.clock = [1000.0]
        self.spy = SpyTransport()
        self.minimax = MiniMaxResponsesDriver(transport=self.spy, clock=lambda: self.clock[0])
        self.bailian = BailianResponsesDriver(transport=self.spy, clock=lambda: self.clock[0])

    def compiled(self, logical=None):
        return self.minimax.prepare_request(dict(logical if logical is not None else LOGICAL))

    def send(self, response, error=None, logical=None):
        compiled = self.compiled(logical)
        self.spy.responses.append(response)
        self.spy.error = error
        self._sends = getattr(self, "_sends", 0) + 1
        permit = permit_for(compiled, dispatch_id=f"dispatch-{self._sends}")
        return self.minimax.send_prepared(compiled, permit, binding_for())


class IdentityTest(DriverFixture):
    def test_identity_is_fixed_from_the_shared_owners(self):
        self.assertEqual(self.minimax.identity.realm_id, "minimax-token-plan")
        self.assertEqual(self.minimax.identity.provider, "minimax")
        self.assertEqual(self.minimax.identity.pool, "minimax")
        self.assertEqual(self.minimax.identity.endpoint, MINIMAX_ENDPOINT)
        self.assertEqual(self.minimax.identity.protocol, "responses")
        self.assertEqual(self.bailian.identity.realm_id, "alibaba-token-plan-sg")
        self.assertEqual(self.bailian.identity.provider, "alibaba")
        self.assertEqual(self.bailian.identity.pool, "bailian")
        self.assertEqual(self.bailian.identity.endpoint, BAILIAN_ENDPOINT)
        for driver, realm in ((self.minimax, MINIMAX_TOKEN_PLAN),
                              (self.bailian, ALIBABA_TOKEN_PLAN)):
            self.assertEqual(driver.identity.base_url, realm.base_url)
            self.assertEqual(driver.identity.endpoint, realm.base_url + "/responses")
            self.assertEqual(driver.identity.protocol, realm.wire_api)

    def test_shared_protocol_vocabulary_is_used_and_retired_name_is_absent(self):
        self.assertEqual(PROVIDER_PROTOCOLS, frozenset({"anthropic", "openai-chat", "responses"}))
        self.assertNotIn("openai-compatible", PROVIDER_PROTOCOLS)
        self.assertEqual(validate_provider_protocol(MINIMAX_TOKEN_PLAN.wire_api), "responses")
        with self.assertRaises(ValueError):
            validate_provider_protocol("openai-compatible")
        self.assertEqual(set(REVIEWED_CODEX_PROVIDER_REALMS), {"minimax-token-plan", "alibaba-token-plan-sg"})

    def test_constructor_offers_no_endpoint_pool_model_or_key_selection(self):
        import inspect
        for driver in (MiniMaxResponsesDriver, BailianResponsesDriver):
            parameters = set(inspect.signature(driver.__init__).parameters)
            self.assertEqual(parameters, {"self", "transport", "clock", "max_timeout_seconds",
                                          "realm_projection", "projection_sha256"})
            for forbidden in ("endpoint", "url", "pool", "provider", "model", "account",
                              "api_key", "credential", "key", "realm", "protocol"):
                self.assertNotIn(forbidden, parameters)

    def test_protected_anthropic_profiles_are_not_application_authorization(self):
        # The protected profiles describe a different Anthropic binding. The
        # driver neither borrows nor widens them; it does not read them at all.
        source = Path(REPO / "config/subscription_provider_profiles.v1.json")
        self.assertTrue(source.exists())
        document = json.loads(source.read_text(encoding="utf-8"))
        profiles = document["profiles"]
        for key in ("minimax-token-plan", "alibaba-token-plan-personal"):
            profile = profiles[key]
            policy = profile["usage_policy"]
            self.assertEqual(profile["protocol"], "anthropic")
            self.assertTrue(policy["supported_harness_required"])
            self.assertTrue(policy["interactive_only"])
            self.assertFalse(policy["unattended_background_allowed"])
            self.assertFalse(policy["production_backend_allowed"])
            self.assertNotEqual(profile["protocol"], self.minimax.identity.protocol)
            self.assertNotEqual(profile["base_url"], self.minimax.identity.base_url)
        self.assertTrue(profiles["alibaba-token-plan-personal"]["usage_policy"]["single_user_only"])
        self.assertNotEqual(self.minimax.identity.realm_id, "alibaba-token-plan-personal")


class CompileTest(DriverFixture):
    def test_conversion_preserves_roles_tools_calls_and_results(self):
        compiled = self.compiled()
        body = json.loads(compiled.wire_body.decode("utf-8"))
        self.assertEqual(body["model"], "MiniMax-M3")
        self.assertFalse(body["stream"])
        self.assertEqual(body["max_output_tokens"], 512)
        self.assertEqual(body["tool_choice"], "auto")
        self.assertEqual(body["tools"], [{"type": "function", "name": "list_files",
                                          "description": "list",
                                          "parameters": {"type": "object",
                                                         "properties": {"dir": {"type": "string"}}},
                                          "strict": True}])
        self.assertEqual(body["input"], [
            {"role": "system", "content": [{"type": "input_text", "text": "be exact"}]},
            {"role": "user", "content": [{"type": "input_text", "text": "list two files"}]},
            {"type": "function_call", "call_id": "call_1", "name": "list_files",
             "arguments": "{\"dir\":\"a\"}"},
            {"type": "function_call_output", "call_id": "call_1", "output": "a.txt"},
            {"role": "assistant", "content": [{"type": "output_text", "text": "done"}]},
        ])

    def test_digests_are_deterministic_and_never_conflated(self):
        first = self.compiled()
        second = self.compiled()
        self.assertEqual(first.wire_body, second.wire_body)
        self.assertEqual(first.wire_body_digest, second.wire_body_digest)
        self.assertEqual(first.logical_payload_digest, second.logical_payload_digest)
        self.assertEqual(first.wire_body_digest, hashlib.sha256(first.wire_body).hexdigest())
        self.assertEqual(first.logical_payload_digest,
                         hashlib.sha256(json.dumps(LOGICAL, sort_keys=True, separators=(",", ":"),
                                                   ensure_ascii=False).encode("utf-8")).hexdigest())
        self.assertNotEqual(first.logical_payload_digest, first.wire_body_digest)

    def test_compiled_call_is_immutable(self):
        compiled = self.compiled()
        self.assertIsInstance(compiled, CompiledCall)
        with self.assertRaises(Exception):
            compiled.wire_body = b"tampered"

    def test_bailian_preserves_explicit_model_and_defaults_like_the_native_owner(self):
        import bailian_keys
        self.assertEqual(BailianResponsesDriver.default_model, bailian_keys.effective_model(""))
        explicit = self.bailian.prepare_request({"model": "qwen3.8-max", "messages": [
            {"role": "user", "content": "hi"}]})
        self.assertEqual(explicit.model, "qwen3.8-max")
        defaulted = self.bailian.prepare_request({"messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(defaulted.model, "qwen3.8-flash")

    def test_model_spelling_is_never_folded_or_substituted(self):
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.prepare_request({"model": "minimax-m3", "messages": [
                {"role": "user", "content": "hi"}]})
        self.assertEqual(caught.exception.code, "model_not_qualified")
        with self.assertRaises(TransportRefused) as caught:
            self.bailian.prepare_request({"model": "qwen3.8-max".upper(), "messages": [
                {"role": "user", "content": "hi"}]})
        self.assertEqual(caught.exception.code, "model_not_qualified")

    def test_minimax_requires_an_explicit_model(self):
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.prepare_request({"messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(caught.exception.code, "model_required")


class RefusalTest(DriverFixture):
    def refuse(self, logical, code):
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.prepare_request(logical)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.spy.requests, [])

    def test_unsupported_and_ambiguous_shapes_refuse_before_intent(self):
        base = {"model": "MiniMax-M3", "messages": [{"role": "user", "content": "hi"}]}
        self.refuse({**base, "stream": True}, "streaming_unsupported")
        self.refuse({**base, "temperature": 0.2}, "unsupported_output_control")
        self.refuse({**base, "max_completion_tokens": 10}, "unsupported_output_control")
        self.refuse({**base, "reasoning": {"effort": "high"}}, "unsupported_output_control")
        self.refuse({**base, "vendor_flag": True}, "unsupported_request_field")
        self.refuse({**base, "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "https://x/y.png"}}]}]},
            "unsupported_content_part")
        self.refuse({**base, "messages": [{"role": "user", "content": [
            {"type": "input_image", "image_url": "data:image/png;base64,AA"}]}]},
            "unsupported_content_part")
        self.refuse({**base, "messages": [{"role": "user", "content": [
            {"type": "image", "text": "not a text part"}]}]},
            "unsupported_content_part")
        self.refuse({**base, "messages": [{"role": "user", "content": [
            {"type": "text", "text": 5}]}]},
            "unsupported_content_part")
        self.refuse({**base, "messages": [{"role": "developer", "content": "hi"}]},
                    "unsupported_message_role")
        self.refuse({**base, "messages": [{"role": "user", "content": "hi",
                                           "extra": 1}]}, "unsupported_message_field")
        self.refuse({**base, "max_tokens": 0}, "invalid_max_tokens")
        self.refuse({**base, "max_tokens": 10 ** 9}, "invalid_max_tokens")

    def test_tool_call_identity_defects_are_refused(self):
        base = {"model": "MiniMax-M3"}
        call = {"id": "call_1", "type": "function",
                "function": {"name": "f", "arguments": "{}"}}
        self.refuse({**base, "messages": [
            {"role": "assistant", "tool_calls": [call, dict(call)]}]}, "tool_call_duplicate")
        self.refuse({**base, "messages": [
            {"role": "tool", "tool_call_id": "call_x", "content": "r"}]},
            "tool_call_unpaired")
        self.refuse({**base, "messages": [
            {"role": "assistant", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": "call_1", "content": "r"},
            {"role": "tool", "tool_call_id": "call_1", "content": "r"}]}, "tool_call_replayed")
        self.refuse({**base, "messages": [
            {"role": "assistant", "tool_calls": [
                {"id": "c", "type": "function",
                 "function": {"name": "f", "arguments": "not json"}}]}]},
            "invalid_tool_arguments")
        self.refuse({**base, "messages": [
            {"role": "assistant", "tool_calls": [
                {"id": "c", "type": "function",
                 "function": {"name": "f", "arguments": "[1]"}}]}]},
            "invalid_tool_arguments")

    def test_nonfinite_and_oversize_values_are_refused(self):
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.prepare_request({"model": "MiniMax-M3", "messages": [
                {"role": "user", "content": "hi"}], "max_tokens": float("inf")})
        self.assertEqual(caught.exception.code, "nonfinite_value")
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.prepare_request({"model": "MiniMax-M3", "messages": [
                {"role": "user", "content": "x" * 70000}]})
        self.assertEqual(caught.exception.code, "message_too_large")

    def test_duplicate_tool_names_and_unknown_tool_choice_are_refused(self):
        base = {"model": "MiniMax-M3", "messages": [{"role": "user", "content": "hi"}]}
        tool = {"type": "function", "function": {"name": "f"}}
        self.refuse({**base, "tools": [tool, dict(tool)]}, "tool_duplicate")
        self.refuse({**base, "tools": [tool], "tool_choice": {
            "type": "function", "function": {"name": "other"}}}, "tool_choice_unknown")

    def test_malformed_tool_and_message_shapes_are_refused(self):
        base = {"model": "MiniMax-M3", "messages": [{"role": "user", "content": "hi"}]}
        self.refuse({**base, "tools": [{"type": "function", "function": {"name": 5}}]},
                    "invalid_tool_name")
        self.refuse({**base, "tools": [{"type": "function", "function": {"name": ""}}]},
                    "invalid_tool_name")
        self.refuse({**base, "tools": [{"type": "function", "function": {
            "name": "f", "parameters": "not-an-object"}}]}, "invalid_tool_schema")
        self.refuse({**base, "tools": [{"type": "function", "function": {
            "name": "f", "strict": "yes"}}]}, "invalid_tool_schema")
        self.refuse({**base, "tools": [{"type": "function", "function": {
            "name": "f", "unknown": 1}}]}, "invalid_tool_schema")
        self.refuse({**base, "tools": [{"type": "code_interpreter"}]}, "invalid_tool_schema")
        self.refuse({**base, "tools": [{"type": "code_interpreter",
                                       "function": {"name": "f"}}]}, "unsupported_tool_type")
        self.refuse({**base, "tool_choice": "maybe"}, "unsupported_tool_choice")
        self.refuse({**base, "messages": [{"role": "assistant", "tool_calls": [
            {"id": "c", "type": "function", "function": {"name": 5, "arguments": "{}"}}]}]},
            "invalid_tool_name")
        self.refuse({**base, "messages": [{"role": "assistant", "tool_calls": [
            {"id": "c", "type": "function", "function": {"name": "f", "arguments": "{}",
                                                         "extra": 1}}]}]},
            "invalid_tool_call")
        self.refuse({**base, "messages": [{"role": "assistant", "tool_calls": [
            {"id": "c!", "type": "function", "function": {"name": "f", "arguments": "{}"}}]}]},
            "invalid_tool_call_id")
        self.refuse({**base, "messages": [{"role": "assistant", "tool_calls": {}}]},
                    "invalid_tool_calls")
        self.refuse({**base, "messages": [{"role": "tool", "tool_call_id": "c",
                                           "content": "r", "extra": 1}]},
                    "invalid_tool_message")
        self.refuse({**base, "messages": []}, "invalid_messages")
        self.refuse({"model": "MiniMax-M3"}, "invalid_messages")
        self.refuse({"model": "MiniMax-M3", "messages": [{"role": "user", "content": "hi"}],
                     "tools": [{"type": "function", "function": {"name": "f"}}] * 65},
                    "too_many_tools")

    def test_a_non_object_or_duplicate_key_logical_request_is_refused(self):
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.prepare_request(b"[]")
        self.assertEqual(caught.exception.code, "invalid_logical_request")
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.prepare_request(b'{"model": "MiniMax-M3", "model": "MiniMax-M3"}')
        self.assertEqual(caught.exception.code, "closed_json_refused")
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.prepare_request(b'{"model": "MiniMax-M3", "max_tokens": NaN}')
        self.assertEqual(caught.exception.code, "nonfinite_value")
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.prepare_request(42)
        self.assertEqual(caught.exception.code, "invalid_logical_request")


class SendBoundaryTest(DriverFixture):
    def test_one_send_for_a_valid_call_and_none_before_it(self):
        compiled = self.compiled()
        self.assertEqual(self.spy.requests, [])
        self.minimax.preflight_account(compiled, binding_for())
        self.assertEqual(self.spy.requests, [])
        permit = permit_for(compiled)
        self.spy.responses.append(upstream(complete_responses()))
        observation = self.minimax.send_prepared(compiled, permit, binding_for())
        self.assertEqual(len(self.spy.requests), 1)
        self.assertEqual(self.spy.requests[0].method, "POST")
        self.assertEqual(self.spy.requests[0].url, MINIMAX_ENDPOINT)
        self.assertEqual(self.spy.requests[0].body, compiled.wire_body)
        self.assertFalse(self.spy.requests[0].allow_redirects)
        self.assertFalse(self.spy.requests[0].use_environment_proxy)
        self.assertEqual(observation.disposition, "complete")
        self.assertEqual(observation.upstream_status, 200)
        self.assertEqual(observation.result_status, "ok")
        self.assertEqual(observation.normalized["text"], "hello")
        self.assertEqual(observation.usage, {"input_tokens": 11, "output_tokens": 7})
        self.assertEqual(observation.served_model, "MiniMax-M3")
        self.assertTrue(observation.served_model_known)
        self.assertNotEqual(observation.upstream_body_sha256, observation.normalized_sha256)

    def test_a_second_send_of_the_same_dispatch_is_refused(self):
        compiled = self.compiled()
        permit = permit_for(compiled)
        self.spy.responses.append(upstream(complete_responses()))
        self.minimax.send_prepared(compiled, permit, binding_for())
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(compiled, permit, binding_for())
        self.assertEqual(caught.exception.code, "dispatch_already_consumed")
        self.assertEqual(len(self.spy.requests), 1)

    def test_send_requires_the_frozen_original_permit_context(self):
        compiled = self.compiled()
        cases = [
            ("dispatch_not_permitted", permit_for(compiled, permitted=False)),
            ("logical_digest_mismatch", permit_for(compiled, logical_digest="b" * 64)),
            ("model_mismatch", permit_for(compiled, model="other-model")),
            ("account_mismatch", permit_for(compiled, account="acct-b")),
            ("permit_expired", permit_for(compiled, expires_at=999.0)),
        ]
        for code, permit in cases:
            with self.assertRaises(TransportRefused) as caught:
                self.minimax.send_prepared(compiled, permit, binding_for())
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.spy.requests, [])

    def test_a_mutated_body_is_refused_without_a_second_effect(self):
        compiled = self.compiled()
        tampered = CompiledCall(**{**compiled.__dict__, "wire_body": b"{}"})
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(tampered, permit_for(compiled), binding_for())
        self.assertEqual(caught.exception.code, "wire_body_mutated")
        self.assertEqual(self.spy.requests, [])

    def test_timeout_is_bounded_by_the_remaining_expiry(self):
        compiled = self.compiled()
        self.spy.responses.append(upstream(complete_responses()))
        self.minimax.send_prepared(compiled, permit_for(compiled, expires_at=1010.0), binding_for())
        self.assertAlmostEqual(self.spy.requests[0].timeout_seconds, 10.0)
        self.assertLessEqual(self.spy.requests[0].timeout_seconds,
                             permit_for(compiled, expires_at=1010.0).expires_at - self.clock[0])


class OriginalExpiryTest(DriverFixture):
    """Correction 1: the original expiry survives every pre-send callback."""

    def test_slow_callbacks_past_expiry_refuse_with_zero_transport_calls(self):
        compiled = self.compiled()

        def slow_eligibility(_account):
            self.clock[0] += 900.0

        def slow_loader(_account):
            self.clock[0] += 900.0
            return "fixture-key"

        permit = permit_for(compiled, expires_at=1100.0)
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(
                compiled, permit, binding_for(loader=slow_loader,
                                              eligibility=slow_eligibility))
        self.assertEqual(caught.exception.code, "permit_expired")
        self.assertEqual(self.spy.requests, [])
        # The original permit is immutable: no renewed timeout, no replacement.
        self.assertEqual(permit.expires_at, 1100.0)

    def test_timeout_is_bounded_by_the_remaining_lifetime_after_callback_work(self):
        compiled = self.compiled()

        def eligibility(_account):
            self.clock[0] += 30.0

        def loader(_account):
            self.clock[0] += 30.0
            return "fixture-key"

        self.spy.responses.append(upstream(complete_responses()))
        self.minimax.send_prepared(compiled, permit_for(compiled, expires_at=1100.0),
                                   binding_for(loader=loader, eligibility=eligibility))
        # 40s of the original lifetime remained after the callback work.
        self.assertAlmostEqual(self.spy.requests[0].timeout_seconds, 40.0)
        self.assertAlmostEqual(self.spy.requests[0].deadline_seconds, 1100.0)

    def test_an_already_expired_permit_is_refused_before_any_owner_callback(self):
        compiled = self.compiled()
        calls = []

        def loader(_account):
            calls.append("credential")
            return "fixture-key"

        def eligibility(_account):
            calls.append("eligibility")

        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(compiled, permit_for(compiled, expires_at=999.0),
                                       binding_for(loader=loader, eligibility=eligibility))
        self.assertEqual(caught.exception.code, "permit_expired")
        self.assertEqual(calls, [])
        self.assertEqual(self.spy.requests, [])

    def test_the_expiry_recheck_after_callbacks_performs_zero_transport_calls(self):
        compiled = self.compiled()
        credential_calls = []

        def slow_loader(_account):
            credential_calls.append(_account)
            self.clock[0] += 5000.0
            return "fixture-key"

        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(compiled, permit_for(compiled, expires_at=1100.0),
                                       binding_for(loader=slow_loader))
        self.assertEqual(caught.exception.code, "permit_expired")
        self.assertEqual(credential_calls, ["acct-a"])
        self.assertEqual(self.spy.requests, [])


class PermitWireBindingTest(DriverFixture):
    """Correction 2: expected wire material is bound to the original permit."""

    def test_a_changed_body_with_recomputed_self_digest_still_refuses(self):
        compiled = self.compiled()
        other = self.minimax.prepare_request({"model": "MiniMax-M3", "messages": [
            {"role": "user", "content": "evil"}]})
        forged = CompiledCall(**{**compiled.__dict__,
                                 "wire_body": other.wire_body,
                                 "wire_body_digest": other.wire_body_digest})
        self.assertNotEqual(forged.wire_body, compiled.wire_body)
        self.assertEqual(forged.wire_body_digest,
                         hashlib.sha256(forged.wire_body).hexdigest())
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(forged, permit_for(compiled), binding_for())
        self.assertEqual(caught.exception.code, "wire_digest_mismatch")
        self.assertEqual(self.spy.requests, [])

    def test_a_mismatched_owner_recorded_wire_digest_refuses(self):
        compiled = self.compiled()
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(compiled, permit_for(compiled, wire_digest="c" * 64),
                                       binding_for())
        self.assertEqual(caught.exception.code, "wire_digest_mismatch")
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(compiled, permit_for(compiled, wire_digest="z" * 64),
                                       binding_for())
        self.assertEqual(caught.exception.code, "invalid_permit")
        self.assertEqual(caught.exception.detail, "wire_body_digest")
        self.assertEqual(self.spy.requests, [])

    def test_mismatched_fixed_identity_refuses_without_credentials_or_io(self):
        compiled = self.compiled()
        credential_calls = []

        def loader(_account):
            credential_calls.append(_account)
            return "fixture-key"

        for field, value in (("realm_id", "other-realm"), ("provider", "other-provider"),
                             ("pool", "other-pool"), ("protocol", "openai-chat"),
                             ("endpoint", "https://other.invalid/v1/responses")):
            forged = CompiledCall(**{**compiled.__dict__, field: value})
            with self.assertRaises(TransportRefused) as caught:
                self.minimax.send_prepared(forged, permit_for(compiled),
                                           binding_for(loader=loader))
            self.assertEqual(caught.exception.code, "driver_mismatch", field)
        other = self.bailian.prepare_request({"model": "qwen3.8-max", "messages": [
            {"role": "user", "content": "hi"}]})
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(other, permit_for(other), binding_for(loader=loader))
        self.assertEqual(caught.exception.code, "driver_mismatch")
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(compiled, permit_for(compiled, lease_id="bad lease"),
                                       binding_for(loader=loader))
        self.assertEqual(caught.exception.code, "invalid_permit")
        self.assertEqual(caught.exception.detail, "lease_id")
        self.assertEqual(credential_calls, [])
        self.assertEqual(self.spy.requests, [])

    def test_the_three_digest_identities_stay_separate_values(self):
        compiled = self.compiled()
        permit = permit_for(compiled)
        self.assertNotEqual(permit.request_digest, permit.logical_payload_digest)
        self.assertNotEqual(permit.request_digest, permit.wire_body_digest)
        self.assertNotEqual(permit.logical_payload_digest, permit.wire_body_digest)
        self.assertEqual(permit.wire_body_digest, compiled.wire_body_digest)
        self.assertNotEqual(permit.logical_payload_digest, compiled.wire_body_digest)


class UpstreamOutcomeTest(DriverFixture):
    def test_complete_upstream_errors_are_terminal_and_never_retried(self):
        for status in (401, 429, 500, 503):
            spy = SpyTransport([upstream({"error": "nope"}, status=status)])
            driver = MiniMaxResponsesDriver(transport=spy, clock=lambda: self.clock[0])
            compiled = driver.prepare_request(dict(LOGICAL))
            observation = driver.send_prepared(compiled, permit_for(compiled), binding_for())
            self.assertEqual(len(spy.requests), 1)
            self.assertEqual(observation.disposition, "complete")
            self.assertEqual(observation.result_status, "upstream_error")
            self.assertEqual(observation.upstream_status, status)
            self.assertIsNone(observation.normalized)

    def test_ambiguous_effects_become_unknown_with_no_fabricated_status(self):
        cases = [
            ("transport_exception", None, OSError("reset")),
            ("upstream_incomplete", upstream(b"partial", framing=False), None),
            ("upstream_no_final_status", upstream(b"{}", status=100), None),
            ("upstream_redirect_refused", upstream(complete_responses(),
                                                   endpoint="https://elsewhere/x"), None),
            ("upstream_incomplete", upstream(b"abc", content_length=99), None),
        ]
        for reason, response, error in cases:
            spy = SpyTransport([response] if response is not None else [], error=error)
            driver = MiniMaxResponsesDriver(transport=spy, clock=lambda: self.clock[0])
            compiled = driver.prepare_request(dict(LOGICAL))
            observation = driver.send_prepared(compiled, permit_for(compiled), binding_for())
            self.assertEqual(observation.disposition, "unknown", reason)
            self.assertEqual(observation.result_status, "ambiguous")
            self.assertEqual(observation.reason, reason)
            self.assertIsNone(observation.upstream_status)
            self.assertIsNone(observation.upstream_body_sha256)
            self.assertIsNone(observation.normalized)
            self.assertEqual(len(spy.requests), 1)

    def test_missing_usage_and_model_stay_unknown(self):
        body = {"id": "r", "status": "completed",
                "output": [{"type": "message", "role": "assistant",
                            "content": [{"type": "output_text", "text": "hi"}]}]}
        observation = self.send(upstream(body))
        self.assertEqual(observation.disposition, "complete")
        self.assertEqual(observation.usage, {"input_tokens": None, "output_tokens": None})
        self.assertIsNone(observation.served_model)
        self.assertFalse(observation.served_model_known)
        self.assertEqual(observation.normalized["text"], "hi")

    def test_an_incomplete_or_errored_responses_output_does_not_become_an_answer(self):
        incomplete = {"id": "r", "status": "incomplete",
                      "incomplete_details": {"reason": "max_output_tokens"},
                      "output": [{"type": "message", "role": "assistant",
                                  "content": [{"type": "output_text", "text": "partial"}]}]}
        errored = {"id": "r", "status": "failed", "error": {"code": "server_error"},
                   "output": []}
        for body, label in ((incomplete, "upstream_incomplete_output"),
                            (errored, "upstream_error")):
            observation = self.send(upstream(body))
            self.assertEqual(observation.disposition, "complete")
            self.assertEqual(observation.result_status, label)
            self.assertIsNone(observation.normalized)
            self.assertEqual(observation.upstream_status, 200)
            self.assertEqual(observation.upstream_body_sha256,
                             hashlib.sha256(json.dumps(body).encode("utf-8")).hexdigest())

    def test_a_body_without_a_proven_completed_status_is_not_normalized(self):
        for body in ({"id": "r", "output": []},
                     {"id": "r", "status": "queued", "output": []},
                     {"id": "r", "status": "completed", "output": "not-a-list"}):
            observation = self.send(upstream(body))
            self.assertEqual(observation.result_status, "upstream_incomplete_output")
            self.assertIsNone(observation.normalized)

    def test_an_unparseable_complete_body_is_a_protocol_error_not_an_answer(self):
        observation = self.send(upstream(b"not json"))
        self.assertEqual(observation.disposition, "complete")
        self.assertEqual(observation.result_status, "upstream_protocol_error")
        self.assertEqual(observation.upstream_status, 200)
        self.assertIsNone(observation.normalized)

    def test_an_unproven_output_shape_does_not_become_an_answer(self):
        body = {"id": "r", "status": "completed",
                "output": [{"type": "reasoning", "content": [{"type": "text", "text": "x"}]}]}
        observation = self.send(upstream(body))
        self.assertEqual(observation.disposition, "complete")
        self.assertEqual(observation.result_status, "upstream_incomplete_output")
        self.assertIsNone(observation.normalized)
        self.assertEqual(observation.upstream_status, 200)

    def test_tool_calls_are_observed_but_never_executed(self):
        body = {"id": "r", "status": "completed", "model": "MiniMax-M3",
                "output": [{"type": "function_call", "call_id": "call_9", "name": "list_files",
                            "arguments": "{\"dir\":\"a\"}"}],
                "usage": {"input_tokens": 3, "output_tokens": 1}}
        observation = self.send(upstream(body))
        self.assertEqual(observation.normalized["tool_calls"], [
            {"id": "call_9", "type": "function",
             "function": {"name": "list_files", "arguments": "{\"dir\":\"a\"}"}}])
        self.assertEqual(observation.normalized["text"], "")


class ModelUsageEvidenceTest(DriverFixture):
    """Correction 4: serving model and usage survive non-answer outcomes."""

    def assert_no_answer(self, observation):
        self.assertIsNone(observation.normalized)
        self.assertIsNone(observation.normalized_sha256)

    def test_a_known_http_error_preserves_declared_model_and_usage(self):
        body = {"error": {"code": "rate_limited"}, "model": "MiniMax-M3",
                "usage": {"input_tokens": 41, "output_tokens": 2}}
        observation = self.send(upstream(body, status=429))
        self.assertEqual(observation.disposition, "complete")
        self.assertEqual(observation.result_status, "upstream_error")
        self.assertEqual(observation.upstream_status, 429)
        self.assert_no_answer(observation)
        self.assertEqual(observation.served_model, "MiniMax-M3")
        self.assertTrue(observation.served_model_known)
        self.assertEqual(observation.usage, {"input_tokens": 41, "output_tokens": 2})

    def test_a_server_error_preserves_partial_usage(self):
        body = {"error": "boom", "model": "MiniMax-M3",
                "usage": {"input_tokens": 9, "output_tokens": None}}
        observation = self.send(upstream(body, status=503))
        self.assertEqual(observation.result_status, "upstream_error")
        self.assert_no_answer(observation)
        self.assertEqual(observation.served_model, "MiniMax-M3")
        self.assertEqual(observation.usage, {"input_tokens": 9, "output_tokens": None})
        self.assertIsNone(observation.normalized)

    def test_non_answer_outcomes_preserve_model_and_usage(self):
        incomplete = {"id": "r", "status": "incomplete",
                      "incomplete_details": {"reason": "max_output_tokens"},
                      "model": "MiniMax-M3",
                      "output": [{"type": "message", "role": "assistant",
                                  "content": [{"type": "output_text", "text": "partial"}]}],
                      "usage": {"input_tokens": 12, "output_tokens": 4}}
        reasoning = {"id": "r", "status": "completed", "model": "MiniMax-M3",
                     "output": [{"type": "reasoning", "summary": []}],
                     "usage": {"input_tokens": 7, "output_tokens": 3}}
        for body in (incomplete, reasoning):
            observation = self.send(upstream(body))
            self.assertEqual(observation.disposition, "complete")
            self.assertEqual(observation.upstream_status, 200)
            self.assert_no_answer(observation)
            self.assertEqual(observation.served_model, "MiniMax-M3")
            self.assertEqual(observation.usage,
                             {"input_tokens": body["usage"]["input_tokens"],
                              "output_tokens": body["usage"]["output_tokens"]})

    def test_requested_model_and_served_model_stay_distinct_and_missing_stays_unknown(self):
        observation = self.send(upstream(complete_responses(model="some-other-served-name")))
        self.assertEqual(observation.result_status, "ok")
        self.assertEqual(observation.model, "MiniMax-M3")
        self.assertEqual(observation.served_model, "some-other-served-name")
        self.assertTrue(observation.served_model_known)
        body = complete_responses()
        del body["model"]
        observation = self.send(upstream(body))
        self.assertEqual(observation.result_status, "ok")
        self.assertIsNone(observation.served_model)
        self.assertFalse(observation.served_model_known)
        self.assertEqual(observation.usage, {"input_tokens": 11, "output_tokens": 7})

    def test_token_boundaries_exclude_bool_float_negative_and_out_of_range(self):
        cases = [
            ({"input_tokens": 10 ** 12, "output_tokens": 10 ** 12},
             {"input_tokens": 10 ** 12, "output_tokens": 10 ** 12}),
            ({"input_tokens": 10 ** 12 + 1, "output_tokens": -1},
             {"input_tokens": None, "output_tokens": None}),
            ({"input_tokens": True, "output_tokens": 5.0},
             {"input_tokens": None, "output_tokens": None}),
            ({"input_tokens": None, "output_tokens": 3},
             {"input_tokens": None, "output_tokens": 3}),
        ]
        for declared, expected in cases:
            body = complete_responses()
            body["usage"] = dict(declared)
            observation = self.send(upstream(body))
            self.assertEqual(observation.result_status, "ok", repr(declared))
            self.assertEqual(observation.usage, expected, repr(declared))
            self.assertEqual(observation.normalized["usage"], expected, repr(declared))

    def test_an_out_of_range_usage_value_does_not_poison_the_answer(self):
        body = complete_responses(usage=(10 ** 12 + 1, 5))
        observation = self.send(upstream(body))
        self.assertEqual(observation.result_status, "ok")
        self.assertEqual(observation.normalized["text"], "hello")
        self.assertEqual(observation.usage, {"input_tokens": None, "output_tokens": 5})

    def test_evidence_stays_unknown_when_the_body_fails_the_strict_parse(self):
        duplicate = (b'{"model": "MiniMax-M3", "model": "MiniMax-M3",'
                     b' "usage": {"input_tokens": 1}}')
        first = self.send(upstream(duplicate))
        self.assertEqual(first.result_status, "upstream_protocol_error")
        self.assert_no_answer(first)
        self.assertIsNone(first.served_model)
        self.assertFalse(first.served_model_known)
        self.assertEqual(first.usage, {"input_tokens": None, "output_tokens": None})
        self.assertEqual(first.upstream_body_sha256, hashlib.sha256(duplicate).hexdigest())
        nonfinite = b'{"model": "MiniMax-M3", "usage": {"input_tokens": NaN}}'
        second = self.send(upstream(nonfinite))
        self.assertEqual(second.result_status, "upstream_protocol_error")
        self.assertEqual(second.usage, {"input_tokens": None, "output_tokens": None})
        self.assertNotEqual(second.upstream_body_sha256, first.upstream_body_sha256)


class OwnerAuthorityTest(DriverFixture):
    def test_bailian_uses_the_owner_exact_account_lookup_and_never_picks(self):
        import bailian_keys
        calls = {"pick": 0, "key": 0}

        def fake_pick(*_args, **_kwargs):
            calls["pick"] += 1
            raise AssertionError("the driver must never select or reserve an account")

        def fake_key_value(_name):
            calls["key"] += 1
            return "fixture-key"

        compiled = self.bailian.prepare_request({"model": "qwen3.8-max", "messages": [
            {"role": "user", "content": "hi"}]})
        self.spy.responses.append(upstream(complete_responses(model="qwen3.8-max"),
                                           endpoint=BAILIAN_ENDPOINT))
        outer = {"LANE_LEASED": "1", "POOL_ACCOUNT": "acct-a"}
        with mock.patch.dict(os.environ, outer), \
             mock.patch.object(bailian_keys, "pick", fake_pick), \
             mock.patch.object(bailian_keys, "_key_value", fake_key_value):
            binding = AccountBinding(account="acct-a",
                                     credential_loader=bailian_keys._codex_key_value)
            observation = self.bailian.send_prepared(compiled, permit_for(compiled), binding)
        self.assertEqual(calls["pick"], 0)
        self.assertEqual(calls["key"], 1)
        self.assertEqual(observation.disposition, "complete")

    def test_the_credential_loader_is_the_only_credential_channel(self):
        lookups = []

        def loader(account):
            lookups.append(account)
            return "fixture-key"

        compiled = self.compiled()
        self.assertEqual(lookups, [])
        self.spy.responses.append(upstream(complete_responses()))
        self.minimax.send_prepared(compiled, permit_for(compiled), binding_for(loader=loader))
        self.assertEqual(lookups, ["acct-a"])

    def test_an_account_specific_preflight_refusal_stops_before_the_send(self):
        compiled = self.compiled()

        def eligibility(account):
            raise RuntimeError("account cooling")

        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(compiled, permit_for(compiled),
                                       binding_for(eligibility=eligibility))
        self.assertEqual(caught.exception.code, "account_not_eligible")
        self.assertEqual(self.spy.requests, [])


class AtomicOnceOnlyClaimTest(DriverFixture):
    """Correction 3: the same-dispatch claim is atomic and pre-callback."""

    def test_simultaneous_same_dispatch_sends_produce_exactly_one_effect(self):
        compiled = self.compiled()
        permit = permit_for(compiled)
        credential_calls = []
        outcomes = {}
        start = threading.Barrier(2)

        def loader(_account):
            credential_calls.append(permit.dispatch_id)
            return "fixture-key"

        def run(index):
            binding = binding_for(loader=loader)
            start.wait(5)
            try:
                outcomes[index] = ("ok", self.minimax.send_prepared(compiled, permit, binding))
            except TransportRefused as refused:
                outcomes[index] = ("refused", refused.code)

        self.spy.responses.append(upstream(complete_responses()))
        threads = [threading.Thread(target=run, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertEqual(sorted(label for label, _ in outcomes.values()), ["ok", "refused"])
        self.assertEqual([value for label, value in outcomes.values() if label == "refused"],
                         ["dispatch_already_consumed"])
        self.assertEqual(len(self.spy.requests), 1)
        self.assertEqual(len(credential_calls), 1)

    def test_a_reentrant_eligibility_callback_cannot_reach_credential_or_post(self):
        compiled = self.compiled()
        permit = permit_for(compiled)
        events = []

        def reentrant(_account):
            events.append("eligibility")
            try:
                self.minimax.send_prepared(compiled, permit, binding_for())
            except TransportRefused as refused:
                events.append("inner:" + refused.code)

        def loader(_account):
            events.append("credential")
            return "fixture-key"

        self.spy.responses.append(upstream(complete_responses()))
        observation = self.minimax.send_prepared(
            compiled, permit, binding_for(loader=loader, eligibility=reentrant))
        self.assertEqual(events, ["eligibility", "inner:dispatch_already_consumed",
                                  "credential"])
        self.assertEqual(observation.disposition, "complete")
        self.assertEqual(len(self.spy.requests), 1)

    def test_a_reentrant_credential_callback_cannot_produce_a_second_post(self):
        compiled = self.compiled()
        permit = permit_for(compiled)
        events = []

        def reentrant_loader(_account):
            events.append("credential")
            try:
                self.minimax.send_prepared(compiled, permit, binding_for())
            except TransportRefused as refused:
                events.append("inner:" + refused.code)
            return "fixture-key"

        self.spy.responses.append(upstream(complete_responses()))
        observation = self.minimax.send_prepared(compiled, permit,
                                                 binding_for(loader=reentrant_loader))
        self.assertEqual(events, ["credential", "inner:dispatch_already_consumed"])
        self.assertEqual(observation.disposition, "complete")
        self.assertEqual(len(self.spy.requests), 1)

    def test_a_callback_failure_does_not_release_the_claim(self):
        compiled = self.compiled()
        permit = permit_for(compiled)
        attempts = []

        def failing_loader(_account):
            attempts.append(_account)
            raise RuntimeError("backend down")

        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(compiled, permit, binding_for(loader=failing_loader))
        self.assertEqual(caught.exception.code, "credential_unavailable")
        with self.assertRaises(TransportRefused) as caught:
            self.minimax.send_prepared(compiled, permit, binding_for())
        self.assertEqual(caught.exception.code, "dispatch_already_consumed")
        self.assertEqual(attempts, ["acct-a"])
        self.assertEqual(self.spy.requests, [])

    def test_distinct_original_dispatches_stay_independent(self):
        first = self.compiled()
        second = self.compiled()
        self.spy.responses.append(upstream(complete_responses()))
        self.spy.responses.append(upstream(complete_responses()))
        first_observation = self.minimax.send_prepared(
            first, permit_for(first, dispatch_id="d-1"), binding_for())
        second_observation = self.minimax.send_prepared(
            second, permit_for(second, dispatch_id="d-2"), binding_for())
        self.assertEqual(first_observation.dispatch_id, "d-1")
        self.assertEqual(second_observation.dispatch_id, "d-2")
        self.assertEqual(len(self.spy.requests), 2)


class JoinOrderTest(DriverFixture):
    """The required incumbent join order. This is an order contract, not admission."""

    def run_join(self, recovered, spy):
        steps = []
        steps.append("authenticate")
        steps.append("recover:" + recovered)
        if recovered != "absent":
            steps.append("no_send")
            return steps, None
        compiled = self.minimax.prepare_request(dict(LOGICAL))
        steps.append("compile")
        steps.append("begin")
        binding = binding_for()
        self.minimax.preflight_account(compiled, binding)
        steps.append("account_preflight")
        permit = permit_for(compiled)
        steps.append("prepare")
        spy.responses.append(upstream(complete_responses()))
        observation = self.minimax.send_prepared(compiled, permit, binding)
        steps.append("send")
        steps.append("complete" if observation.disposition == "complete" else "mark_unknown")
        return steps, observation

    def test_required_order_is_compile_then_prepare_then_one_send(self):
        spy = SpyTransport()
        driver = MiniMaxResponsesDriver(transport=spy, clock=lambda: self.clock[0])
        self.minimax = driver
        steps, observation = self.run_join("absent", spy)
        self.assertEqual(steps, ["authenticate", "recover:absent", "compile", "begin",
                                  "account_preflight", "prepare", "send", "complete"])
        self.assertEqual(len(spy.requests), 1)
        self.assertEqual(observation.disposition, "complete")

    def test_a_recovered_pending_or_unknown_request_never_sends(self):
        for recovered in ("terminal", "pending", "effect_unknown"):
            spy = SpyTransport()
            driver = MiniMaxResponsesDriver(transport=spy, clock=lambda: self.clock[0])
            self.minimax = driver
            steps, observation = self.run_join(recovered, spy)
            self.assertEqual(steps, ["authenticate", "recover:" + recovered, "no_send"])
            self.assertIsNone(observation)
            self.assertEqual(spy.requests, [])

    def test_a_send_without_the_prepared_intent_is_refused(self):
        spy = SpyTransport()
        driver = MiniMaxResponsesDriver(transport=spy, clock=lambda: self.clock[0])
        compiled = driver.prepare_request(dict(LOGICAL))
        with self.assertRaises(TransportRefused) as caught:
            driver.send_prepared(compiled, permit_for(compiled, permitted=False), binding_for())
        self.assertEqual(caught.exception.code, "dispatch_not_permitted")
        self.assertEqual(spy.requests, [])


class UnqualifiedJoinTest(unittest.TestCase):
    """The actual owner refuses unjoined or unauthenticated pool requests."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.document = {
            "schema": "mastermind.provider_accounts.v1",
            "providers": {
                "go": {"enabled": True, "accounts": [{"name": "account-a", "per_account_cap": 2}]},
                "minimax": {"enabled": True, "accounts": [{"name": "mm", "per_account_cap": 2}]},
                "bailian": {"enabled": True, "accounts": [{"name": "bl", "per_account_cap": 2}]},
            },
            "application_grants": [{
                "grant_id": "macro-app", "purpose": "APPLICATION", "enabled": True,
                "principal_id": "macro", "credential_ref": "MACRO_APPLICATION_TOKEN",
                "admission_root": "service:macro", "caller_hosts": ["vps"],
                "workloads": ["site_interactive"], "pool": "go", "accounts": ["account-a"],
                "models": ["fixture-model"], "route": "/v1/chat/completions", "stream": False,
                "expires_at": 2000, "max_turn_seconds": 300, "max_steps": 2,
                "qualification_ref": "fixture:controlled-qualification",
                "application_permission_ref": "fixture:ordinary-inference"}],
        }
        self.accounts = self.directory / "accounts.json"
        self.save()
        self.broker = lease_broker.Broker(
            db_path=str(self.directory / "leases.sqlite"),
            lock_path=str(self.directory / "leases.lock"),
            accounts_path=str(self.accounts), now_fn=lambda: 1000.0,
            check_pid=False, external_gates=False, this_host="vps",
            status_json=str(self.directory / "status.json"))

    def save(self):
        self.accounts.write_text(json.dumps(self.document))

    def test_the_broker_refuses_unjoined_or_unauthenticated_pool_requests(self):
        for pool, model in (("minimax", "MiniMax-M3"), ("bailian", "qwen3.8-max")):
            with self.assertRaises(lease_broker.ApplicationAdmissionError) as caught:
                self.broker.begin_application_turn(
                    principal_id="macro", caller_host="vps", workload="site_interactive",
                    turn_id="turn-1", pool=pool, model=model)
            self.assertEqual(caught.exception.code,
                "unsupported_application_pool" if pool == "minimax" else "invalid_identity")
        with self.broker._conn() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM application_turns").fetchone()[0], 0)

    def test_an_application_grant_for_these_pools_is_refused_by_the_account_owner(self):
        for pool in ("minimax", "bailian"):
            self.document["application_grants"][0]["pool"] = pool
            self.save()
            with self.assertRaises(lease_broker.ApplicationAdmissionError) as caught:
                self.broker.begin_application_turn(
                    principal_id="macro", caller_host="vps", workload="site_interactive",
                    turn_id="turn-1", pool="go", model="fixture-model")
            self.assertEqual(caught.exception.code, "invalid_application_grant")


if __name__ == "__main__":
    unittest.main()
