"""OFFLINE unit tests for paid_fabric_bootstrap (scaffold disclosure).

These tests run entirely offline against fixture stand-ins.  The production
parent module ``control_plane.paid_fabric_backend.CanonicalPaidBackend`` is
NOT imported here: the tests monkeypatch the helper's call-time class hook
(``_canonical_backend_class``) and its transport hook (``_build_opener``).
Fixtures here are therefore NOT authenticated production proof, and passing
this suite does NOT claim whole-path qualification -- the parent's final
independent auth/exactly-once integration review owns that.
"""

import io
import json
import os
import socket
import sys
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from control_plane import paid_fabric_bootstrap as mod  # noqa: E402

LABEL = "primary"
KEY = "sk-fixture-secret-ABC"
CLOCK = 1_000_000.0


def quota_body(pct_5h=37.5, pct_week=64.0):
    """One complete same-response pair (5h unit 3 + weekly unit 6)."""
    return json.dumps({
        "code": 200,
        "success": True,
        "data": {
            "limits": [
                {"type": "CREDIT_LIMIT", "unit": 3, "percentage": pct_5h},
                {"type": "TOKENS_LIMIT", "unit": 6, "percentage": pct_week},
            ],
        },
    }).encode("utf-8")


class FakeGateway:

    def __init__(self, accept=True, clock=CLOCK):
        self.accept = accept
        self.clock_value = float(clock)
        self.bridge_calls = []
        self._clock = self._clock_fn

    def _clock_fn(self):
        return self.clock_value

    def require_gateway(self, gateway):
        self.bridge_calls.append(gateway)
        if not self.accept:
            raise RuntimeError("bridge refused by fixture")
        return gateway


class FakeContext:

    def __init__(self, table):
        self.account_table = table


class FakeTable:
    """Duck-typed stand-in mirroring the pinned AccountTable internals."""

    def __init__(self, accounts):
        self._lock = threading.Lock()
        self._accounts = {name: dict(info) for name, info in accounts.items()}
        self._state = {
            name: {
                "exhausted_until_ts": 0.0,
                "last_pct_5h": None,
                "last_pct_week": None,
                "observed_at": None,
                "next_reset_5h": None,
            }
            for name in self._accounts
        }
        self._last_refresh = {name: 0.0 for name in self._accounts}

    def seed(self, name, **fields):
        self._state[name].update(fields)

    def snapshot_state(self, name):
        with self._lock:
            return dict(self._state[name])


class FakeBackend:
    """Stand-in for the exact CanonicalPaidBackend (hook is patched)."""

    def __init__(self, table, gateway):
        self._context = FakeContext(table)
        self._gateway = gateway

    def require_gateway(self, gateway):
        return self._gateway.require_gateway(gateway)


class OtherBackend(FakeBackend):
    """A different exact type, to exercise the strict type check."""


class FakeResponse:

    def __init__(self, body=b"", status=200):
        self.status = status
        self._body = body

    def read(self, limit=-1):
        return self._body[:limit] if limit and limit > 0 else self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class ExplodingResponse(FakeResponse):

    def read(self, limit=-1):
        raise socket.timeout("read timed out")


class FakeOpener:

    def __init__(self, responder):
        self.requests = []
        self._responder = responder

    def open(self, request, timeout=None):
        self.requests.append((request, timeout))
        return self._responder(request)


def ok_opener(body=None, status=200):
    return FakeOpener(lambda request: FakeResponse(
        quota_body() if body is None else body, status=status))


def make_owner(gateway=None, accounts=None):
    gateway = gateway or FakeGateway()
    table = FakeTable(accounts or {LABEL: {"api_key": KEY, "note": "cfg"}})
    return FakeBackend(table, gateway), table, gateway


def patched(owner_class=FakeBackend, opener=None):
    openers = [opener] if opener is not None else []
    return (
        mock.patch.object(mod, "_canonical_backend_class", lambda: owner_class),
        mock.patch.object(mod, "_build_opener", lambda: openers[0] if openers else None),
    )


class HelperBase(unittest.TestCase):

    def run_ok(self, opener, owner_class=FakeBackend, label=LABEL, gateway=None):
        owner, table, gateway = make_owner(gateway=gateway)
        with mock.patch.object(mod, "_canonical_backend_class", lambda: owner_class):
            with mock.patch.object(mod, "_build_opener", lambda: opener):
                result = mod.bootstrap_paid_account(owner, account_label=label)
        return result, owner, table, gateway


class TransportTests(HelperBase):

    def test_exactly_one_get_bearer_at_fixed_origin(self):
        opener = ok_opener()
        result, _owner, _table, gateway = self.run_ok(opener)
        self.assertEqual(result["state"], mod.STATE_OBSERVED)
        self.assertEqual(result["request_count"], 1)
        self.assertEqual(len(opener.requests), 1)
        request, timeout = opener.requests[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, mod.QUOTA_URL)
        self.assertTrue(request.full_url.startswith("https://api.z.ai/"))
        self.assertEqual(timeout, mod.TIMEOUT_S)
        self.assertEqual(request.headers.get("Authorization"), "Bearer " + KEY)
        self.assertEqual(gateway.clock_value, result["observed_at"])
        self.assertEqual((result["pct_5h"], result["pct_week"]), (37.5, 64.0))
        self.assertTrue(result["pair_complete"])
        self.assertTrue(result["fresh"])
        self.assertTrue(result["committed"])

    def test_single_attempt_never_falls_back(self):
        # A failing status must NOT trigger a second (e.g. raw-key) attempt.
        opener = FakeOpener(lambda request: FakeResponse(b"{}", status=500))
        result, _owner, _table, _gateway = self.run_ok(opener)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(result["state"], mod.STATE_UNKNOWN)
        self.assertEqual(result["reason"], mod.REASON_BAD_STATUS)

    def test_opener_has_no_proxy_and_no_redirect(self):
        # An ambient proxy from the environment must never be picked up.
        with mock.patch.object(urllib.request, "getproxies",
                               lambda: {"http": "http://ambient.invalid:3128"}):
            opener = mod._build_opener()
        proxy_handlers = [h for h in opener.handlers
                          if isinstance(h, urllib.request.ProxyHandler)]
        for handler in proxy_handlers:
            self.assertEqual(handler.proxies, {})
        self.assertFalse(any(
            "ambient.invalid" in str(getattr(h, "proxies", ""))
            for h in opener.handlers))
        redirect = [h for h in opener.handlers
                    if isinstance(h, urllib.request.HTTPRedirectHandler)]
        self.assertEqual(len(redirect), 1)
        self.assertIsInstance(redirect[0], mod._NoRedirect)
        self.assertIsNone(
            redirect[0].redirect_request(None, None, 302, "x", {}, "https://elsewhere/"))

    def test_redirect_never_followed(self):
        def responder(request):
            raise urllib.error.HTTPError(
                mod.QUOTA_URL, 302, "redirect", None, io.BytesIO(b""))
        opener = FakeOpener(responder)
        result, _owner, _table, _gateway = self.run_ok(opener)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(result["state"], mod.STATE_UNKNOWN)
        self.assertEqual(result["reason"], mod.REASON_REDIRECT_REFUSED)


class FailureMappingTests(HelperBase):

    def _run_status(self, code):
        def responder(request):
            raise urllib.error.HTTPError(
                mod.QUOTA_URL, code, "status", None, io.BytesIO(b""))
        opener = FakeOpener(responder)
        owner, table, _gateway = make_owner()
        table.seed(LABEL, last_pct_5h=42.0, last_pct_week=88.0, observed_at=123.0)
        with mock.patch.object(mod, "_canonical_backend_class", lambda: FakeBackend):
            with mock.patch.object(mod, "_build_opener", lambda: opener):
                result = mod.bootstrap_paid_account(owner, account_label=LABEL)
        return result, table

    def test_auth_refused_401(self):
        result, table = self._run_status(401)
        self.assertEqual(result["state"], mod.STATE_AUTH_REFUSED)
        self.assertEqual(result["reason"], mod.REASON_AUTH_REFUSED)
        self.assertIsNone(result["observed_at"])
        self.assertFalse(result["fresh"])
        self.assertTrue(result["previous_reading_retained"])
        state = table.snapshot_state(LABEL)
        self.assertEqual(state["last_pct_5h"], 42.0)
        self.assertEqual(state["observed_at"], 123.0)
        self.assertEqual(table._last_refresh[LABEL], CLOCK)

    def test_auth_refused_403(self):
        result, _table = self._run_status(403)
        self.assertEqual(result["state"], mod.STATE_AUTH_REFUSED)
        self.assertIsNone(result["cooldown_until_ts"])

    def test_rate_limited_429_bounded_cooldown(self):
        result, _table = self._run_status(429)
        self.assertEqual(result["state"], mod.STATE_RATE_LIMITED)
        self.assertEqual(
            result["cooldown_until_ts"], CLOCK + mod.RATE_LIMIT_COOLDOWN_S)
        self.assertFalse(result["fresh"])

    def test_other_bad_status_unknown(self):
        result, _table = self._run_status(503)
        self.assertEqual(result["state"], mod.STATE_UNKNOWN)
        self.assertEqual(result["reason"], mod.REASON_BAD_STATUS)

    def test_timeout_maps_unknown(self):
        def responder(request):
            raise urllib.error.URLError(socket.timeout("timed out"))
        opener = FakeOpener(responder)
        result, _owner, _table, _gateway = self.run_ok(opener)
        self.assertEqual(result["state"], mod.STATE_UNKNOWN)
        self.assertEqual(result["reason"], mod.REASON_TIMEOUT)

    def test_read_timeout_maps_unknown(self):
        opener = FakeOpener(lambda request: ExplodingResponse())
        result, _owner, _table, _gateway = self.run_ok(opener)
        self.assertEqual(result["state"], mod.STATE_UNKNOWN)
        self.assertEqual(result["reason"], mod.REASON_TIMEOUT)

    def test_transport_lost_maps_unknown(self):
        def responder(request):
            raise urllib.error.URLError(OSError("conn dropped"))
        opener = FakeOpener(responder)
        result, _owner, _table, _gateway = self.run_ok(opener)
        self.assertEqual(result["state"], mod.STATE_UNKNOWN)
        self.assertEqual(result["reason"], mod.REASON_LOST)

    def test_oversize_body_rejected(self):
        opener = FakeOpener(lambda request: FakeResponse(
            b"x" * (mod.MAX_BODY_BYTES + 1)))
        result, _owner, _table, _gateway = self.run_ok(opener)
        self.assertEqual(result["state"], mod.STATE_UNKNOWN)
        self.assertEqual(result["reason"], mod.REASON_OVERSIZE)
        self.assertEqual(result["request_count"], 1)

    def test_preio_refusals_never_touch_the_network(self):
        boom = FakeOpener(lambda request: (_ for _ in ()).throw(AssertionError("IO!")))

        def run(owner_class=None, owner=None, label=LABEL, gateway=None):
            owner_built, table, gateway_built = make_owner(gateway=gateway)
            owner = owner or owner_built
            with mock.patch.object(
                    mod, "_canonical_backend_class",
                    lambda: owner_class if owner_class else FakeBackend):
                with mock.patch.object(mod, "_build_opener", lambda: boom):
                    return mod.bootstrap_paid_account(owner, account_label=label)

        # fake owner: exact-type check rejects before any IO
        result = run(owner_class=OtherBackend)
        self.assertEqual(result["state"], mod.STATE_UNKNOWN)
        self.assertEqual(result["reason"], mod.REASON_OWNER_NOT_CANONICAL)
        self.assertEqual(result["request_count"], 0)

        # production hook unpatched: offline import cannot qualify, still no IO
        owner, _table, _gateway = make_owner()
        with mock.patch.object(mod, "_build_opener", lambda: boom):
            result = mod.bootstrap_paid_account(owner, account_label=LABEL)
        self.assertEqual(result["reason"], mod.REASON_OWNER_NOT_CANONICAL)
        self.assertEqual(result["request_count"], 0)

        # bridge refused before IO
        gateway = FakeGateway(accept=False)
        result = run(gateway=gateway)
        self.assertEqual(result["reason"], mod.REASON_BRIDGE_REFUSED)
        self.assertEqual(result["request_count"], 0)
        self.assertEqual(len(gateway.bridge_calls), 1)

        # invalid / unknown labels
        for bad in (None, "", "../etc", "a b", "x" * 65, 123):
            result = run(label=bad)
            self.assertEqual(result["reason"], mod.REASON_INVALID_LABEL)
            self.assertIsNone(result["account_label"])
            self.assertEqual(result["request_count"], 0)
        result = run(label="ghost")
        self.assertEqual(result["reason"], mod.REASON_LABEL_UNKNOWN)
        self.assertEqual(result["request_count"], 0)


class PayloadValidationTests(HelperBase):

    def _body_case(self, body):
        opener = FakeOpener(lambda request: FakeResponse(body))
        owner, table, _gateway = make_owner()
        with mock.patch.object(mod, "_canonical_backend_class", lambda: FakeBackend):
            with mock.patch.object(mod, "_build_opener", lambda: opener):
                result = mod.bootstrap_paid_account(owner, account_label=LABEL)
        return result, table

    def test_duplicate_keys_rejected(self):
        body = (b'{"data":{"limits":['
                b'{"type":"CREDIT_LIMIT","unit":3,"percentage":1.0,"percentage":2.0},'
                b'{"type":"TOKENS_LIMIT","unit":6,"percentage":5.0}]}}')
        result, table = self._body_case(body)
        self.assertEqual(result["reason"], mod.REASON_PAYLOAD_REJECTED)
        self.assertIsNone(table.snapshot_state(LABEL)["last_pct_5h"])

    def test_nan_rejected(self):
        body = (b'{"data":{"limits":['
                b'{"type":"CREDIT_LIMIT","unit":3,"percentage":NaN},'
                b'{"type":"TOKENS_LIMIT","unit":6,"percentage":50.0}]}}')
        result, _table = self._body_case(body)
        self.assertEqual(result["reason"], mod.REASON_PAYLOAD_REJECTED)

    def test_huge_and_overflowing_numbers_rejected(self):
        for raw in (b"1e308", b"1e400"):
            body = (b'{"data":{"limits":['
                    b'{"type":"CREDIT_LIMIT","unit":3,"percentage":' + raw + b'},'
                    b'{"type":"TOKENS_LIMIT","unit":6,"percentage":50.0}]}}')
            result, _table = self._body_case(body)
            self.assertEqual(result["reason"], mod.REASON_PAYLOAD_REJECTED)

    def test_boolean_percentage_rejected(self):
        body = (b'{"data":{"limits":['
                b'{"type":"CREDIT_LIMIT","unit":3,"percentage":true},'
                b'{"type":"TOKENS_LIMIT","unit":6,"percentage":50.0}]}}')
        result, _table = self._body_case(body)
        self.assertEqual(result["reason"], mod.REASON_PAYLOAD_REJECTED)

    def test_deep_input_rejected(self):
        node = {"limits": [{"type": "CREDIT_LIMIT", "unit": 3, "percentage": 10.0}]}
        for _ in range(mod.MAX_JSON_DEPTH + 5):
            node = {"data": node}
        result, _table = self._body_case(json.dumps(node).encode("utf-8"))
        self.assertEqual(result["reason"], mod.REASON_PAYLOAD_REJECTED)

    def test_partial_pair_keeps_old_weekly_stale(self):
        opener = FakeOpener(lambda request: FakeResponse(json.dumps({
            "code": 200,
            "data": {"limits": [
                {"type": "CREDIT_LIMIT", "unit": 3, "percentage": 12.5},
            ]},
        }).encode("utf-8")))
        owner, table, _gateway = make_owner()
        table.seed(LABEL, last_pct_5h=1.0, last_pct_week=40.0, observed_at=7.0)
        with mock.patch.object(mod, "_canonical_backend_class", lambda: FakeBackend):
            with mock.patch.object(mod, "_build_opener", lambda: opener):
                result = mod.bootstrap_paid_account(owner, account_label=LABEL)
        self.assertEqual(result["reason"], mod.REASON_PAYLOAD_REJECTED)
        self.assertIsNone(result["pct_week"])
        self.assertIsNone(result["observed_at"])
        self.assertFalse(result["fresh"])
        state = table.snapshot_state(LABEL)
        # old weekly must stay OLD, never reused as if fresh
        self.assertEqual(state["last_pct_week"], 40.0)
        self.assertEqual(state["observed_at"], 7.0)

    def test_ambiguous_units_rejected(self):
        for unit in (5, "3", 3.0, True, None):
            body = json.dumps({
                "data": {"limits": [
                    {"type": "CREDIT_LIMIT", "unit": unit, "percentage": 10.0},
                    {"type": "TOKENS_LIMIT", "unit": 6, "percentage": 20.0},
                ]},
            }).encode("utf-8")
            result, _table = self._body_case(body)
            self.assertEqual(result["reason"], mod.REASON_PAYLOAD_REJECTED)

    def test_duplicate_window_across_kinds_rejected(self):
        body = json.dumps({
            "data": {"limits": [
                {"type": "CREDIT_LIMIT", "unit": 3, "percentage": 10.0},
                {"type": "TOKENS_LIMIT", "unit": 3, "percentage": 20.0},
                {"type": "TOKENS_LIMIT", "unit": 6, "percentage": 30.0},
            ]},
        }).encode("utf-8")
        result, _table = self._body_case(body)
        self.assertEqual(result["reason"], mod.REASON_PAYLOAD_REJECTED)

    def test_out_of_bounds_percentages_rejected(self):
        for lo, hi in ((-1.0, 50.0), (0.0, 100.5)):
            body = quota_body(pct_5h=lo, pct_week=hi)
            result, _table = self._body_case(body)
            self.assertEqual(result["reason"], mod.REASON_PAYLOAD_REJECTED)

    def test_explicit_failure_envelopes_rejected(self):
        variants = [
            {"code": 400, "data": {"limits": []}},
            {"success": False, "data": {"limits": []}},
            {"error": "quota backend down", "data": {"limits": []}},
            {"code": 200, "success": True, "error": "late error",
             "data": {"limits": []}},
        ]
        for payload in variants:
            result, _table = self._body_case(json.dumps(payload).encode("utf-8"))
            self.assertEqual(result["reason"], mod.REASON_PAYLOAD_REJECTED)

    def test_pure_validator_accepts_and_rejects(self):
        pair = mod.validate_quota_payload(json.loads(quota_body()))
        self.assertEqual(pair, (37.5, 64.0))
        bad = {"data": {"limits": [
            {"type": "CREDIT_LIMIT", "unit": 5, "percentage": 1.0},
            {"type": "TOKENS_LIMIT", "unit": 6, "percentage": 2.0},
        ]}}
        with self.assertRaises(mod._PayloadRejected):
            mod.validate_quota_payload(bad)


class CommitTests(HelperBase):

    def test_complete_pair_commits_atomically_with_gateway_clock(self):
        opener = ok_opener()
        owner, table, gateway = make_owner()
        table.seed(LABEL, last_pct_5h=99.0, observed_at=999.0)
        with mock.patch.object(mod, "_canonical_backend_class", lambda: FakeBackend):
            with mock.patch.object(mod, "_build_opener", lambda: opener):
                result = mod.bootstrap_paid_account(owner, account_label=LABEL)
        state = table.snapshot_state(LABEL)
        self.assertEqual(state["last_pct_5h"], 37.5)
        self.assertEqual(state["last_pct_week"], 64.0)
        self.assertEqual(state["observed_at"], CLOCK)
        self.assertEqual(table._last_refresh[LABEL], CLOCK)
        self.assertFalse(result["exhausted_5h"])
        self.assertIsNone(result["cooldown_until_ts"])

    def test_exhaustion_derived_from_complete_response(self):
        opener = FakeOpener(lambda request: FakeResponse(
            quota_body(pct_5h=100.0, pct_week=100.0)))
        result, _owner, table, _gateway = self.run_ok(opener)
        self.assertTrue(result["exhausted_5h"])
        self.assertEqual(
            result["cooldown_until_ts"], CLOCK + mod.EXHAUST_COOLDOWN_CAP_S)
        state = table.snapshot_state(LABEL)
        self.assertEqual(
            state["exhausted_until_ts"], CLOCK + mod.EXHAUST_COOLDOWN_CAP_S)

    def test_still_valid_owner_hold_never_cleared(self):
        opener = ok_opener()
        owner, table, _gateway = make_owner()
        hold = CLOCK + 5000.0
        table.seed(LABEL, exhausted_until_ts=hold)
        with mock.patch.object(mod, "_canonical_backend_class", lambda: FakeBackend):
            with mock.patch.object(mod, "_build_opener", lambda: opener):
                result = mod.bootstrap_paid_account(owner, account_label=LABEL)
        self.assertTrue(result["committed"])
        self.assertFalse(result["exhausted_5h"])
        self.assertEqual(table.snapshot_state(LABEL)["exhausted_until_ts"], hold)

    def test_credential_generation_change_during_io_blocks_commit(self):
        owner, table, _gateway = make_owner()

        def responder(request):
            table._accounts[LABEL]["api_key"] = "sk-rotated-during-io"
            return FakeResponse(quota_body())

        opener = FakeOpener(responder)
        with mock.patch.object(mod, "_canonical_backend_class", lambda: FakeBackend):
            with mock.patch.object(mod, "_build_opener", lambda: opener):
                result = mod.bootstrap_paid_account(owner, account_label=LABEL)
        self.assertEqual(result["state"], mod.STATE_UNKNOWN)
        self.assertEqual(result["reason"], mod.REASON_GENERATION_CHANGED)
        self.assertEqual(result["request_count"], 1)
        state = table.snapshot_state(LABEL)
        self.assertIsNone(state["last_pct_5h"])
        self.assertIsNone(state["observed_at"])
        self.assertEqual(table._last_refresh[LABEL], 0.0)

    def test_account_config_change_during_io_blocks_commit(self):
        owner, table, _gateway = make_owner()

        def responder(request):
            table._accounts[LABEL]["note"] = "changed"
            return FakeResponse(quota_body())

        opener = FakeOpener(responder)
        with mock.patch.object(mod, "_canonical_backend_class", lambda: FakeBackend):
            with mock.patch.object(mod, "_build_opener", lambda: opener):
                result = mod.bootstrap_paid_account(owner, account_label=LABEL)
        self.assertEqual(result["reason"], mod.REASON_GENERATION_CHANGED)
        self.assertIsNone(table.snapshot_state(LABEL)["last_pct_5h"])

    def test_bridge_refused_after_read_blocks_commit(self):
        gateway = FakeGateway(accept=True)
        owner, table, _gateway = make_owner(gateway=gateway)

        def responder(request):
            gateway.accept = False
            return FakeResponse(quota_body())

        opener = FakeOpener(responder)
        with mock.patch.object(mod, "_canonical_backend_class", lambda: FakeBackend):
            with mock.patch.object(mod, "_build_opener", lambda: opener):
                result = mod.bootstrap_paid_account(owner, account_label=LABEL)
        self.assertEqual(result["state"], mod.STATE_UNKNOWN)
        self.assertEqual(result["reason"], mod.REASON_BRIDGE_REFUSED)
        self.assertEqual(len(gateway.bridge_calls), 2)
        self.assertIsNone(table.snapshot_state(LABEL)["last_pct_5h"])
        self.assertTrue(result["previous_reading_retained"])


class RedactionTests(HelperBase):

    def test_result_is_closed_non_secret_fixed_shape(self):
        opener = ok_opener()
        result, _owner, _table, _gateway = self.run_ok(opener)
        self.assertEqual(
            set(result), {
                "schema", "state", "reason", "account_label", "request_count",
                "observed_at", "pct_5h", "pct_week", "pair_complete", "fresh",
                "committed", "exhausted_5h", "cooldown_until_ts",
                "previous_reading_retained",
            })
        self.assertEqual(result["schema"], mod.SCHEMA)
        self.assertIn(result["state"], mod.STATES)

    def test_no_secret_url_or_error_text_leaks_into_result(self):
        def responder(request):
            raise urllib.error.URLError(
                OSError("boom " + KEY + " https://secret-host.example/x"))

        opener = FakeOpener(responder)
        result, _owner, _table, _gateway = self.run_ok(opener)
        rendered = json.dumps(result)
        self.assertNotIn(KEY, rendered)
        self.assertNotIn("api.z.ai", rendered)
        self.assertNotIn("boom", rendered)
        self.assertNotIn("secret-host", rendered)
        self.assertNotIn("Bearer", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# Parent integration checks use the real AccountTable implementation. Kernel
# authority/transport remain explicit offline seams; this is not host proof.
def test_real_account_table_none_return_guard_and_complete_pair(monkeypatch):
    import importlib.util
    from pathlib import Path
    path=Path(__file__).parents[1]/'ops/native_fabric/paid_canonical_glm/candidate/glm_shim.py'
    spec=importlib.util.spec_from_file_location('_paid_bootstrap_real_table',path)
    shim=importlib.util.module_from_spec(spec);spec.loader.exec_module(shim)
    table=shim.AccountTable({LABEL:{'api_key':KEY}},live_reader=lambda *_: (_ for _ in ()).throw(AssertionError('manual refresh forbidden')))
    gateway=FakeGateway()
    owner=FakeBackend(table,gateway)
    # Real CanonicalPaidBackend.require_gateway is raise-on-refusal / None on
    # success; no boolean verdict may be required or substituted as authority.
    owner.require_gateway=lambda value: None
    monkeypatch.setattr(mod,'_canonical_backend_class',lambda:FakeBackend)
    opener=ok_opener();monkeypatch.setattr(mod,'_build_opener',lambda:opener)
    result=mod.bootstrap_paid_account(owner,account_label=LABEL)
    assert result['state']=='OBSERVED' and len(opener.requests)==1
    state=table.state(LABEL)
    assert state['canonical_status_state']=='OBSERVED'
    assert state['canonical_status_observed_at']==state['observed_at']==CLOCK
    assert state['last_pct_5h']==37.5 and state['last_pct_week']==64.0


def test_refusal_invalidates_canonical_provenance_without_freshening_old_pair(monkeypatch):
    owner,table,_=make_owner()
    table.seed(LABEL,last_pct_5h=1.0,last_pct_week=2.0,observed_at=CLOCK-1,
               canonical_status_state='OBSERVED',canonical_status_observed_at=CLOCK-1)
    def refuse(_):raise urllib.error.HTTPError(mod.QUOTA_URL,429,'fixture',{},io.BytesIO(b''))
    opener=FakeOpener(refuse)
    monkeypatch.setattr(mod,'_canonical_backend_class',lambda:FakeBackend)
    monkeypatch.setattr(mod,'_build_opener',lambda:opener)
    result=mod.bootstrap_paid_account(owner,account_label=LABEL)
    state=table.snapshot_state(LABEL)
    assert result['state']=='RATE_LIMITED' and state['canonical_status_state']=='RATE_LIMITED'
    assert state['canonical_status_observed_at'] is None
    assert state['observed_at']==CLOCK-1 and state['last_pct_week']==2.0
    assert state['exhausted_until_ts']>=CLOCK+mod.RATE_LIMIT_COOLDOWN_S


def test_concurrent_status_read_never_issues_second_request(monkeypatch):
    owner,table,_=make_owner();entered=threading.Event();release=threading.Event()
    def blocked(_):
        entered.set();assert release.wait(2);return FakeResponse(quota_body())
    opener=FakeOpener(blocked)
    monkeypatch.setattr(mod,'_canonical_backend_class',lambda:FakeBackend)
    monkeypatch.setattr(mod,'_build_opener',lambda:opener)
    first=[]
    thread=threading.Thread(target=lambda:first.append(mod.bootstrap_paid_account(owner,account_label=LABEL)))
    thread.start();assert entered.wait(2)
    try:
        second=mod.bootstrap_paid_account(owner,account_label=LABEL)
        assert second['request_count']==0 and second['reason']=='status_read_pending'
        assert table.snapshot_state(LABEL)['canonical_status_state']=='PENDING'
        assert len(opener.requests)==1
    finally:release.set();thread.join(2)
    assert first[0]['state']=='OBSERVED' and len(opener.requests)==1


def test_late_complete_payload_cannot_publish_observed(monkeypatch):
    owner,table,gateway=make_owner();clock=[0.0]
    monkeypatch.setattr(mod,'_canonical_backend_class',lambda:FakeBackend)
    monkeypatch.setattr(mod.time,'monotonic',lambda:clock[0])
    before=dict(table._state[LABEL])
    def delayed(key):
        assert table._state[LABEL]['canonical_status_state']=='PENDING'
        clock[0]=mod.TIMEOUT_S+0.01
        return 'PAYLOAD',json.loads(quota_body())
    monkeypatch.setattr(mod,'_read_quota_once',delayed)
    result=mod.bootstrap_paid_account(owner,account_label=LABEL)
    assert result['state']==mod.STATE_UNKNOWN and result['reason']==mod.REASON_TIMEOUT
    assert not result['committed'] and table._state[LABEL]['canonical_status_state']=='UNKNOWN'
    assert table._state[LABEL]['observed_at']==before['observed_at']
    assert table._state[LABEL]['last_pct_5h']==before['last_pct_5h']
    assert table._state[LABEL]['last_pct_week']==before['last_pct_week']


def test_late_open_does_not_read_or_accept_a_body(monkeypatch):
    clock=[0.0];calls=[]
    class LateResponse(FakeResponse):
        def read(self,*args):raise AssertionError('body after deadline')
    class LateOpener:
        def open(self,request,timeout):
            calls.append(1);clock[0]=mod.TIMEOUT_S+0.01;return LateResponse(quota_body())
    monkeypatch.setattr(mod.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(mod,'_build_opener',lambda:LateOpener())
    assert mod._read_quota_once(KEY)==('REASON',mod.REASON_TIMEOUT)
    assert calls==[1]
