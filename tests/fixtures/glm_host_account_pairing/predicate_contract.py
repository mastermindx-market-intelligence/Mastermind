"""Standalone unittest coverage for glm_host_account_readiness.

Fake dictionaries and a fake clock only: no live probes, files, config, env,
network or installed runtime state. Run: python3 tests/test_glm_host_account_readiness.py
"""


import copy
import inspect
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import glm_host_account_readiness as readiness

HOST = "host-alpha"
ALIAS = "local"
SHA = "a" * 64
NOW = 1000000.0
AGE = 600

OK = readiness.REASON_OK
MODE = readiness.REASON_MODE
MODEL = readiness.REASON_MODEL
CANDIDATE = readiness.REASON_CANDIDATE_MODEL
UNVERIFIED = readiness.REASON_SOURCE_UNVERIFIED
CLOCK = readiness.REASON_CLOCK_INVALID
PREF_BAD = readiness.REASON_PREFERENCE_INVALID
ROWS_BAD = readiness.REASON_ROWS_INVALID
DOC_BAD = readiness.REASON_DOCUMENT_INVALID
DOC_STALE = readiness.REASON_DOCUMENT_STALE
ENV_BAD = readiness.REASON_ENVELOPE_INVALID
ENV_STALE = readiness.REASON_ENVELOPE_STALE
NONE_READY = readiness.REASON_NO_READY
PREF_UNAVAILABLE = readiness.REASON_PREFERRED_UNAVAILABLE
SCHEMA = readiness.SCHEMA
SCOPE = readiness.CONFIG_SCOPE

_UNSET = object()


def envelope(**overrides):
    base = {
        "schema": SCHEMA,
        "host": HOST,
        "transport_alias": ALIAS,
        "mode": "glm",
        "config_scope": SCOPE,
        "validator_sha256": SHA,
        "observed_at": NOW - 5.0,
        "status": "known",
        "accounts": {"acct-a": True, "acct-b": False, "acct-c": None},
    }
    base.update(overrides)
    return base


def doc_fixture(**overrides):
    base = {
        "host": HOST,
        "reachable": True,
        "ts": NOW - 5.0,
        "unrelated": "unrelated telemetry fields may remain",
        "glm_local_account_readiness": envelope(),
    }
    base.update(overrides)
    return base


def rows(*names):
    return [{"name": name, "pool": "glm"} for name in names]


class FilterCase(unittest.TestCase):
    def call(self, accounts=_UNSET, doc=_UNSET, **kwargs):
        kw = {
            "host": HOST,
            "transport_alias": ALIAS,
            "mode": "glm",
            "model": "glm-5.3",
            "candidate_model": "glm-5.3",
            "validator_sha256": SHA,
            "now": NOW,
            "max_age": AGE,
            "source_verified": True,
        }
        kw.update(kwargs)
        if accounts is _UNSET:
            accounts = rows("acct-a", "acct-b")
        if doc is _UNSET:
            doc = doc_fixture()
        return readiness.filter_glm_host_accounts(accounts, doc, **kw)


class HappyPath(FilterCase):
    def test_fresh_exact_route_returns_ready_row(self):
        out, reason = self.call()
        self.assertEqual(reason, OK)
        self.assertEqual([row["name"] for row in out], ["acct-a"])

    def test_all_ready_rows_in_order_with_identity(self):
        accs = rows("acct-b", "acct-x", "acct-a", "acct-c")
        flags = {"acct-a": True, "acct-b": True, "acct-c": True, "acct-x": False}
        doc = doc_fixture(glm_local_account_readiness=envelope(accounts=flags))
        out, reason = self.call(accounts=accs, doc=doc)
        self.assertEqual(reason, OK)
        self.assertEqual([row["name"] for row in out], ["acct-b", "acct-a", "acct-c"])
        self.assertIs(out[0], accs[0])
        self.assertIs(out[1], accs[2])

    def test_inputs_not_mutated_unrelated_ok(self):
        accs = rows("acct-a", "acct-b")
        accs_before = copy.deepcopy(accs)
        telemetry = doc_fixture()
        telemetry_before = copy.deepcopy(telemetry)
        out, reason = self.call(accounts=accs, doc=telemetry)
        self.assertEqual(reason, OK)
        self.assertEqual(accs, accs_before)
        self.assertEqual(telemetry, telemetry_before)
        self.assertIn("unrelated", telemetry)

    def test_key_readiness_is_model_independent(self):
        doc = doc_fixture(glm_local_account_readiness=envelope(accounts={"acct-a": True}))
        out, reason = self.call(accounts=rows("acct-a"), doc=doc,
                                model="glm-5.3-flash", candidate_model="glm-5.3-flash")
        self.assertEqual((len(out), reason), (1, OK))


class RouteScope(FilterCase):
    def test_only_exact_glm_mode_qualifies(self):
        for mode in ("claude", "GLM", "glm ", "", None, 1, True):
            out, reason = self.call(mode=mode)
            self.assertEqual((out, reason), ([], MODE))

    def test_only_exact_supported_models(self):
        for model in ("GLM-5.3", "glm-5.2", "glm-5.3-turbo", " glm-5.3", 5.3, None):
            self.assertEqual(self.call(model=model)[1], MODEL)

    def test_flash_route_supported_when_exact(self):
        out, reason = self.call(accounts=rows("acct-a"),
                                model="glm-5.3-flash", candidate_model="glm-5.3-flash")
        self.assertEqual((len(out), reason), (1, OK))

    def test_candidate_model_must_equal_model(self):
        self.assertEqual(self.call(candidate_model="glm-5.3-flash")[1], CANDIDATE)
        self.assertEqual(self.call(candidate_model=None)[1], CANDIDATE)


class SourceVerification(FilterCase):
    def test_only_literal_true_qualifies(self):
        for value in (False, None, 1, "yes", [True]):
            out, reason = self.call(source_verified=value)
            self.assertEqual((out, reason), ([], UNVERIFIED))


class ClockArguments(FilterCase):
    def test_giant_integer_clock_arguments_fail_closed(self):
        self.assertEqual(self.call(now=10 ** 400), ([], CLOCK))
        self.assertEqual(self.call(max_age=10 ** 400), ([], CLOCK))

    def test_giant_integer_observation_timestamps_fail_closed(self):
        self.assertEqual(self.call(doc=doc_fixture(ts=10 ** 400)), ([], DOC_STALE))
        telemetry = doc_fixture(glm_local_account_readiness=envelope(observed_at=10 ** 400))
        self.assertEqual(self.call(doc=telemetry), ([], ENV_STALE))

    def test_invalid_now_or_max_age_rejected(self):
        for kwargs in ({"now": True}, {"now": False}, {"now": float("nan")},
                       {"now": float("inf")}, {"now": "1000"}, {"now": None},
                       {"max_age": True}, {"max_age": -1}, {"max_age": -0.5},
                       {"max_age": float("nan")}, {"max_age": float("inf")},
                       {"max_age": None}):
            self.assertEqual(self.call(**kwargs)[1], CLOCK)

    def test_zero_max_age_window_works(self):
        fresh = doc_fixture(ts=NOW, glm_local_account_readiness=envelope(observed_at=NOW))
        out, reason = self.call(accounts=rows("acct-a"), doc=fresh, max_age=0)
        self.assertEqual((len(out), reason), (1, OK))
        self.assertEqual(self.call(doc=doc_fixture(ts=NOW - 0.5), max_age=0)[1], DOC_STALE)


class TelemetryDocument(FilterCase):
    def test_age_boundary_exact_not_floored(self):
        self.assertEqual(self.call(doc=doc_fixture(ts=NOW - AGE))[1], OK)
        self.assertEqual(self.call(doc=doc_fixture(ts=NOW - AGE - 0.5))[1], DOC_STALE)

    def test_future_bound_now_plus_one_second(self):
        self.assertEqual(self.call(doc=doc_fixture(ts=NOW + 1))[1], OK)
        self.assertEqual(self.call(doc=doc_fixture(ts=NOW + 1.25))[1], DOC_STALE)

    def test_invalid_timestamp_values_rejected(self):
        for ts in (True, False, float("nan"), float("inf"), float("-inf"), 0, -5,
                   "1000", None, [NOW]):
            self.assertEqual(self.call(doc=doc_fixture(ts=ts))[1], DOC_STALE)

    def test_document_identity_and_reachable(self):
        self.assertEqual(self.call(host="host-beta")[1], DOC_BAD)
        self.assertEqual(self.call(doc=doc_fixture(host=None))[1], DOC_BAD)
        self.assertEqual(self.call(doc=doc_fixture(host=HOST.upper()))[1], DOC_BAD)
        self.assertEqual(self.call(doc=doc_fixture(reachable=False))[1], DOC_BAD)
        self.assertEqual(self.call(doc=doc_fixture(reachable=1))[1], DOC_BAD)
        self.assertEqual(self.call(doc=doc_fixture(reachable=None))[1], DOC_BAD)
        self.assertEqual(self.call(doc={"host": HOST, "ts": NOW - 5.0})[1], DOC_BAD)
        self.assertEqual(self.call(doc=7)[1], DOC_BAD)


class EnvelopeIdentity(FilterCase):
    def override(self, **kwargs):
        return doc_fixture(glm_local_account_readiness=envelope(**kwargs))

    def test_wrong_identity_fields_rejected(self):
        cases = [
            ({"schema": "mastermind.glm_local_account_readiness.v2"}, ENV_BAD),
            ({"schema": None}, ENV_BAD),
            ({"host": "host-beta"}, ENV_BAD),
            ({"host": None}, ENV_BAD),
            ({"transport_alias": "remote"}, ENV_BAD),
            ({"transport_alias": None}, ENV_BAD),
            ({"mode": "claude"}, ENV_BAD),
            ({"config_scope": "user_glm_config.v1"}, ENV_BAD),
            ({"config_scope": None}, ENV_BAD),
            ({"status": "unknown"}, ENV_BAD),
            ({"status": None}, ENV_BAD),
        ]
        for override_kwargs, expected in cases:
            self.assertEqual(self.call(doc=self.override(**override_kwargs))[1], expected)
        self.assertEqual(self.call(transport_alias="other")[1], ENV_BAD)

    def test_validator_sha256_valid_lowerhex_and_equal(self):
        self.assertEqual(self.call(validator_sha256="b" * 64)[1], ENV_BAD)
        for bad in ("A" * 64, "a" * 63, "a" * 65, "g" * 64, "a" * 32, 123, None):
            self.assertEqual(self.call(doc=self.override(validator_sha256=bad))[1], ENV_BAD)

    def test_observed_at_freshness_same_rules(self):
        self.assertEqual(self.call(doc=self.override(observed_at=NOW - AGE))[1], OK)
        self.assertEqual(self.call(doc=self.override(observed_at=NOW - AGE - 0.5))[1], ENV_STALE)
        self.assertEqual(self.call(doc=self.override(observed_at=NOW + 1))[1], OK)
        for value in (True, float("nan"), float("inf"), 0, NOW + 2, "x", None):
            self.assertEqual(self.call(doc=self.override(observed_at=value))[1], ENV_STALE)


class EnvelopeEntries(FilterCase):
    def test_false_unknown_missing_do_not_qualify(self):
        flags = {"acct-a": False, "acct-b": None}
        doc = doc_fixture(glm_local_account_readiness=envelope(accounts=flags))
        self.assertEqual(self.call(doc=doc), ([], NONE_READY))
        self.assertEqual(self.call(accounts=rows("acct-z")), ([], NONE_READY))

    def test_malformed_entries_reject_envelope(self):
        for flags in ({"acct-a": "yes"}, {"acct-a": 1}, {"acct-a": 0}, {"acct-a": 0.0},
                      {7: True}, {"": True}, {"acct-a": []}):
            doc = doc_fixture(glm_local_account_readiness=envelope(accounts=flags))
            self.assertEqual(self.call(doc=doc)[1], ENV_BAD)

    def test_non_dict_envelope_rejected(self):
        self.assertEqual(self.call(doc=doc_fixture(glm_local_account_readiness=None))[1], ENV_BAD)
        self.assertEqual(self.call(doc=doc_fixture(glm_local_account_readiness=[]))[1], ENV_BAD)
        telemetry = doc_fixture()
        del telemetry["glm_local_account_readiness"]
        self.assertEqual(self.call(doc=telemetry)[1], ENV_BAD)

    def test_flags_container_and_bounds(self):
        env = envelope()
        del env["accounts"]
        self.assertEqual(self.call(doc=doc_fixture(glm_local_account_readiness=env))[1], ENV_BAD)
        too_big = {("acct-%02d" % i): True for i in range(65)}
        doc = doc_fixture(glm_local_account_readiness=envelope(accounts=too_big))
        self.assertEqual(self.call(doc=doc)[1], ENV_BAD)
        full = {("acct-%02d" % i): (i == 0) for i in range(64)}
        doc = doc_fixture(glm_local_account_readiness=envelope(accounts=full))
        out, reason = self.call(accounts=rows("acct-00", "acct-01"), doc=doc)
        self.assertEqual((len(out), reason), (1, OK))


class CandidateRows(FilterCase):
    def test_rows_bounded_unique_named_dicts(self):
        self.assertEqual(self.call(accounts=7)[1], ROWS_BAD)
        self.assertEqual(self.call(accounts={"name": "acct-a"})[1], ROWS_BAD)
        self.assertEqual(self.call(accounts=[])[1], NONE_READY)
        self.assertEqual(self.call(accounts=[{"pool": "glm"}])[1], ROWS_BAD)
        self.assertEqual(self.call(accounts=rows("acct-a", "acct-a"))[1], ROWS_BAD)
        for bad_name in ("", 7, None, "x\ny", "x\ry", "x\0y", "a" * 129):
            self.assertEqual(self.call(accounts=[{"name": bad_name}])[1], ROWS_BAD)
        self.assertEqual(self.call(accounts=[{"name": "a" * 128}])[1], NONE_READY)
        self.assertEqual(self.call(accounts=[{"name": "acct-a"}, "row"])[1], ROWS_BAD)
        many = rows(*("n%02d" % i for i in range(65)))
        self.assertEqual(self.call(accounts=many)[1], ROWS_BAD)

    def test_other_characters_in_names_allowed(self):
        name = "svc/glm.worker-01 [pool:2]"
        doc = doc_fixture(glm_local_account_readiness=envelope(accounts={name: True}))
        out, reason = self.call(accounts=rows(name), doc=doc)
        self.assertEqual((len(out), reason), (1, OK))


class Preference(FilterCase):
    def test_preferred_ready_returns_same_row(self):
        accs = rows("acct-b", "acct-a")
        out, reason = self.call(accounts=accs, preferred="acct-a")
        self.assertEqual((len(out), reason), (1, OK))
        self.assertIs(out[0], accs[1])

    def test_preferred_unavailable_never_falls_back(self):
        self.assertEqual(self.call(preferred="acct-z"), ([], PREF_UNAVAILABLE))
        self.assertEqual(self.call(accounts=rows("acct-b"), preferred="acct-b"),
                         ([], PREF_UNAVAILABLE))
        self.assertEqual(self.call(accounts=rows("acct-z", "acct-a"), preferred="acct-z"),
                         ([], PREF_UNAVAILABLE))

    def test_empty_string_follows_no_preference_truthiness(self):
        out, reason = self.call(preferred="")
        self.assertEqual((len(out), reason), (1, OK))

    def test_invalid_preference_types_rejected(self):
        for value in (5, 5.0, ["acct-a"], {"name": "acct-a"}, b"acct-a", True):
            out, reason = self.call(preferred=value)
            self.assertEqual((out, reason), ([], PREF_BAD))

    def test_static_reasons_never_echo_worker_values(self):
        _, unavailable = self.call(preferred="acct-z")
        self.assertNotIn("acct-z", unavailable)
        _, none_ready = self.call(accounts=rows("acct-z"))
        self.assertNotIn("acct-z", none_ready)
        _, bad_host = self.call(host="host-beta")
        self.assertNotIn(HOST, bad_host)
        self.assertNotIn("host-beta", bad_host)


class Purity(unittest.TestCase):
    def test_module_imports_and_effect_tokens_pure(self):
        source = inspect.getsource(readiness)
        imports = set(re.findall(r"(?m)^\s*(?:import|from)\s+([A-Za-z_][A-Za-z_0-9.]*)", source))
        self.assertEqual(imports, {"math"})
        for token in ("open(", "print(", "subprocess", "socket", "getenv", "environ",
                      "datetime", "time.time", "eval(", "exec(", "urllib", "Path(",
                      "__import__", "importlib", "input("):
            self.assertNotIn(token, source)

    def test_no_io_with_io_hooks_poisoned(self):
        accs = rows("acct-a", "acct-b")
        telemetry = doc_fixture()
        with mock.patch("builtins.open", side_effect=AssertionError("file IO attempted")), \
                mock.patch("builtins.input", side_effect=AssertionError("stdin read")), \
                mock.patch("os.environ", {}):
            out, reason = readiness.filter_glm_host_accounts(
                accs, telemetry, host=HOST, transport_alias=ALIAS, mode="glm",
                model="glm-5.3", candidate_model="glm-5.3", validator_sha256=SHA,
                now=NOW, max_age=AGE, source_verified=True)
        self.assertEqual((len(out), reason), (1, OK))


if __name__ == "__main__":
    unittest.main()
