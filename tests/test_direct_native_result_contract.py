"""Pure finite wire tests. No Runtime, source acquisition or provider fixtures."""
import copy
import unittest
from unittest.mock import patch

from common import direct_native_result_contract as c


class DirectResultContractTests(unittest.TestCase):
    def setUp(self):
        self.selection = dict(work_ref="WS-H2", job_id="job-h2", attempt_id="attempt-h2")
        self.payload = dict(summary="Retained findings", current_state="Finished",
                            completed_steps=["Read source"], next_actions=["Parent evaluates"])
        self.view = c.available(self.selection, self.payload, "a" * 64,
                                dict(state="UNCONSUMED", receipt_digest=None))

    def test_available_is_detached_and_not_product_acceptance(self):
        self.payload["next_actions"].append("later")
        self.selection["work_ref"] = "changed"
        self.assertEqual(self.view["selection"]["work_ref"], "WS-H2")
        self.assertEqual(self.view["result"]["next_actions"], ["Parent evaluates"])
        self.assertNotIn("PRODUCT_ACCEPTED", str(self.view))
        self.assertEqual(c.decode_response(c.canonical_bytes(self.view)), self.view)

    def test_unavailable_never_invents_consumption(self):
        for reason in c.REASON_CODES:
            with self.subTest(reason=reason):
                result = c.unavailable(self.selection, reason)
                self.assertIsNone(result["result"])
                self.assertIsNone(result["consumption"])
        bad = c.unavailable(self.selection, "EFFECT_UNKNOWN")
        bad["consumption"] = dict(state="UNCONSUMED", receipt_digest=None)
        with self.assertRaises(c.DirectResultContractError):
            c.validate_response(bad)

    def test_exact_keys_reject_identity_path_and_acceptance_injection(self):
        for key in ("principal_scope", "receiver", "worker_id", "path", "PRODUCT_ACCEPTED"):
            for value in (self.selection, self.view, self.view["result"]):
                with self.subTest(key=key, target=list(value)):
                    mutated = copy.deepcopy(value); mutated[key] = "forged"
                    validator = c.validate_selection if value is self.selection else (
                        c.validate_response if value is self.view else
                        lambda x: c.validate_response(dict(self.view, result=x)))
                    with self.assertRaises(c.DirectResultContractError):
                        validator(mutated)

    def test_consumption_states_and_digest_are_closed(self):
        consumed = dict(state="CONSUMED", receipt_digest="b" * 64)
        self.assertEqual(c.validate_consumption(consumed), consumed)
        for value in (dict(state="CONSUMED", receipt_digest=None),
                      dict(state="UNCONSUMED", receipt_digest="a" * 64),
                      dict(state="UNKNOWN", receipt_digest=None),
                      dict(state="PRODUCT_ACCEPTED", receipt_digest="a" * 64)):
            with self.subTest(value=value), self.assertRaises(c.DirectResultContractError):
                c.validate_consumption(value)

    def test_request_is_closed_and_has_no_caller_authority(self):
        request = dict(self.selection, result_digest="c" * 64, operation_key="consume-h2")
        self.assertEqual(c.validate_request(request, consume=True), request)
        with self.assertRaises(c.DirectResultContractError):
            c.validate_request(request)
        for bad in ("", " x", "x/y", "x" * 129, "é", True):
            with self.subTest(bad=bad), self.assertRaises(c.DirectResultContractError):
                c.validate_request(dict(request, operation_key=bad), consume=True)

    def test_current_attempt_discovery_is_read_only_and_owner_selected(self):
        current = dict(self.selection, attempt_id=None)
        self.assertEqual(c.validate_request(current), current)
        self.assertIsNone(c.unavailable(current, "NOT_TERMINAL")["selection"]["attempt_id"])
        with self.assertRaises(c.DirectResultContractError):
            c.available(current, self.payload, "a" * 64, self.view["consumption"])
        with self.assertRaises(c.DirectResultContractError):
            c.validate_request(dict(current, result_digest="a" * 64,
                                    operation_key="consume-h2"), consume=True)

    def test_private_scope_is_shape_only_and_never_public_request_input(self):
        frame = dict(self.selection, schema=c.PRIVATE_SCHEMA,
                     operation="result", principal_scope="d" * 64)
        self.assertEqual(c.validate_private_frame(frame), frame)
        with self.assertRaises(c.DirectResultContractError):
            c.validate_request(frame)
        with self.assertRaises(c.DirectResultContractError):
            c.validate_private_frame(dict(frame, worker_id="codex-01"))

    def test_scalar_list_and_total_byte_boundaries(self):
        for key, value in (("summary", "x" * 4097), ("current_state", "x\x00"),
                           ("next_actions", ["x"] * 33),
                           ("completed_steps", ["x" * 257])):
            with self.subTest(key=key), self.assertRaises(c.DirectResultContractError):
                c.validate_payload(dict(self.payload, **{key: value}))
        allowed = dict(self.payload, summary="x" * 4096,
                       completed_steps=["x" * 256] * 32)
        c.available(self.selection, allowed, "a" * 64, self.view["consumption"])
        # Each Unicode field fits its character bound; the independent total
        # UTF-8 byte cap still refuses the complete response.
        huge = dict(summary="🧪" * 4096, current_state="🧪" * 4096,
                    completed_steps=[], next_actions=[])
        with self.assertRaises(c.DirectResultContractError):
            c.available(self.selection, huge, "a" * 64, self.view["consumption"])

    def test_duplicate_nonfinite_surrogate_and_mixed_schema_refuse(self):
        samples = [b'{"schema":1,"schema":2}', b'{"value":NaN}',
                   b'{"value":Infinity}', b'{"value":"\\ud800"}']
        for raw in samples:
            with self.subTest(raw=raw), self.assertRaises(c.DirectResultContractError):
                c.decode_response(raw)
        for schema in ("mastermind.fabric_role_result_view.v1", "mastermind.product_accepted/v1"):
            with self.assertRaises(c.DirectResultContractError):
                c.validate_response(dict(self.view, schema=schema))

    def test_pure_contract_never_opens_source_or_transport(self):
        with patch("builtins.open", side_effect=AssertionError("source IO")), \
             patch("socket.socket", side_effect=AssertionError("network")), \
             patch("subprocess.Popen", side_effect=AssertionError("process")):
            self.assertEqual(c.validate_response(self.view), self.view)
            self.assertEqual(c.digest(self.view), c.digest(copy.deepcopy(self.view)))


if __name__ == "__main__":
    unittest.main()
