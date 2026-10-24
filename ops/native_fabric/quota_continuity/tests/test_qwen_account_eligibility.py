"""Isolated synthetic tests for the qwen Bailian usage-park eligibility source job
(run qwen-eligibility-source-01a15e3f-v1).

Covers:
  * a fresh, applicable per-account usage row with a literal parked=True reaches
    BOTH pool routing (bailian_keys.usable_names) and exact broker account
    selection (lease_broker.Broker._bailian_effective_cap);
  * stale / expired / future / malformed / wrong-account facts stay explicit
    UNKNOWN and never park an unrelated account or fabricate exhaustion;
  * fake usage documents cannot mutate policy or stores;
  * existing http_429 soft admission (including the soft floor of 3) and the
    non-429 cooldown / actual cap behavior are unchanged.

Runnable from the repository tests location:
    python3 tests/test_qwen_account_eligibility.py
    python3 -m unittest tests.test_qwen_account_eligibility
    pytest tests/test_qwen_account_eligibility.py

No network, provider, credential, live state or installed mutation is used:
the candidate modules are located by walking upward from this file and every
store touch is redirected to per-test temporary fixtures.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_CANDIDATE = None
for _root in (
    _TESTS_DIR,
    os.path.dirname(_TESTS_DIR),
    os.path.dirname(os.path.dirname(_TESTS_DIR)),
    os.path.dirname(os.path.dirname(os.path.dirname(_TESTS_DIR))),
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_TESTS_DIR)))),
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_TESTS_DIR))))
    ),
):
    _cand = os.path.join(_root, "ops", "native_fabric", "quota_continuity", "candidate")
    if os.path.isfile(os.path.join(_cand, "bailian_keys.py")):
        _CANDIDATE = _cand
        break
if _CANDIDATE is None:
    raise unittest.SkipTest(
        "ops/native_fabric/quota_continuity/candidate not found above the tests directory"
    )
if _CANDIDATE not in sys.path:
    sys.path.insert(0, _CANDIDATE)

_SOURCE = os.path.join(os.path.dirname(_CANDIDATE), "source")
if _SOURCE not in sys.path:
    sys.path.append(_SOURCE)

sys.path.insert(0, os.path.dirname(__file__))
from _offline_boundary import acquire as _offline_acquire, release as _offline_release

def setUpModule():
    _offline_acquire()

def tearDownModule():
    _offline_release()

import bailian_keys  # noqa: E402
import lease_broker  # noqa: E402
import pick  # noqa: E402

DATA_KEYS = {"state", "parked", "observed_at", "reset_at"}
# One real-time anchor per test-process import. Pure eligibility boundary
# assertions use NOW explicitly, while integration paths use the production
# real-time read. A fixed historical instant made "fresh" parked accounts stale
# once CI moved beyond the 24-hour eligibility horizon (7 false failures).
# Keep the source's real clock and all expiry assertions unchanged.
NOW_DT = datetime.now(timezone.utc).replace(microsecond=0)
NOW = NOW_DT.timestamp()


def iso(dt):
    return dt.isoformat()


def fresh_row(parked=True, pct=90.0, observed_dt=None, resets_dt=None, now_dt=NOW_DT):
    if observed_dt is None:
        observed_dt = now_dt - timedelta(minutes=10)
    if resets_dt is None:
        resets_dt = now_dt + timedelta(days=3)
    return {
        "parked": parked,
        "pct_7d": pct,
        "observed_at": iso(observed_dt),
        "resets_at": iso(resets_dt),
    }


class UsageEligibilityPure(unittest.TestCase):
    """usage_eligibility: pure closed DATA, timeliness contract, no fabrication."""

    def test_fresh_parked_true_is_current(self):
        info = bailian_keys.usage_eligibility("k", fresh_row(parked=True), NOW)
        self.assertEqual(set(info), DATA_KEYS)
        self.assertEqual(info["state"], "CURRENT")
        self.assertIs(info["parked"], True)
        self.assertIsInstance(info["observed_at"], float)
        self.assertIsInstance(info["reset_at"], float)
        self.assertAlmostEqual(info["observed_at"], (NOW_DT - timedelta(minutes=10)).timestamp())
        self.assertAlmostEqual(info["reset_at"], (NOW_DT + timedelta(days=3)).timestamp())

    def test_fresh_parked_false_is_current_and_not_parked(self):
        info = bailian_keys.usage_eligibility("k", fresh_row(parked=False), NOW)
        self.assertEqual(info["state"], "CURRENT")
        self.assertIs(info["parked"], False)

    def test_parked_must_be_literal_bool(self):
        for bad in ("yes", 1, 0, None, [], {}, 1.0):
            info = bailian_keys.usage_eligibility("k", fresh_row(parked=bad), NOW)
            self.assertEqual(info["state"], "UNKNOWN", repr(bad))
            self.assertIsNone(info["parked"])
        row = fresh_row()
        del row["parked"]
        self.assertEqual(bailian_keys.usage_eligibility("k", row, NOW)["state"], "UNKNOWN")

    def test_missing_row_wrong_account_and_bad_payloads(self):
        for usage in (
            None,
            [],
            "x",
            42,
            {},
            {"keys": {}},
            {"keys": {"other": fresh_row()}},
            {"keys": {"k": "not-a-row"}},
            {"keys": "not-a-map"},
        ):
            info = bailian_keys.usage_eligibility("k", usage, NOW)
            self.assertEqual(info["state"], "UNKNOWN")
            self.assertIsNone(info["parked"])
            self.assertEqual(set(info), DATA_KEYS)

    def test_pct_7d_bounds_and_finiteness(self):
        for good in (0, 0.0, 50, 99.9, 100, 100.0):
            self.assertEqual(
                bailian_keys.usage_eligibility("k", fresh_row(pct=good), NOW)["state"],
                "CURRENT",
                repr(good),
            )
        for bad in (-0.000001, 100.000001, -1, 101, 1e9, "90", True, False, None, float("nan"), float("inf"), float("-inf")):
            info = bailian_keys.usage_eligibility("k", fresh_row(pct=bad), NOW)
            self.assertEqual(info["state"], "UNKNOWN", repr(bad))
            self.assertIsNone(info["parked"])
        row = fresh_row()
        del row["pct_7d"]
        self.assertEqual(bailian_keys.usage_eligibility("k", row, NOW)["state"], "UNKNOWN")

    def test_timestamps_must_be_aware_iso(self):
        base = dict(pct=50.0, parked=False)
        aware = fresh_row(observed_dt=NOW_DT - timedelta(minutes=5), resets_dt=NOW_DT + timedelta(days=1), **{})
        aware.update(base)
        self.assertEqual(bailian_keys.usage_eligibility("k", aware, NOW)["state"], "CURRENT")
        z = dict(aware)
        z["observed_at"] = iso(NOW_DT - timedelta(minutes=5)).replace("+00:00", "Z")
        self.assertEqual(bailian_keys.usage_eligibility("k", z, NOW)["state"], "CURRENT")
        naive = dict(aware)
        naive["observed_at"] = (NOW_DT - timedelta(minutes=5)).replace(tzinfo=None).isoformat()
        self.assertEqual(bailian_keys.usage_eligibility("k", naive, NOW)["state"], "UNKNOWN")
        naive2 = dict(aware)
        naive2["resets_at"] = (NOW_DT + timedelta(days=1)).replace(tzinfo=None).isoformat()
        self.assertEqual(bailian_keys.usage_eligibility("k", naive2, NOW)["state"], "UNKNOWN")
        for bad in ("not-a-date", "2026-13-45T99:00:00+00:00", "", 1234567890, None, "2026-10-22"):
            row = dict(aware)
            row["observed_at"] = bad
            self.assertEqual(
                bailian_keys.usage_eligibility("k", row, NOW)["state"], "UNKNOWN", repr(bad)
            )

    def test_observation_age_window(self):
        edge = fresh_row(observed_dt=NOW_DT - timedelta(seconds=86400))
        self.assertEqual(bailian_keys.usage_eligibility("k", edge, NOW)["state"], "CURRENT")
        stale = fresh_row(observed_dt=NOW_DT - timedelta(seconds=86401))
        info = bailian_keys.usage_eligibility("k", stale, NOW)
        self.assertEqual(info["state"], "UNKNOWN")
        self.assertIsNone(info["parked"])
        future = fresh_row(observed_dt=NOW_DT + timedelta(seconds=1))
        self.assertEqual(bailian_keys.usage_eligibility("k", future, NOW)["state"], "UNKNOWN")

    def test_reset_window(self):
        edge = fresh_row(resets_dt=NOW_DT + timedelta(seconds=8 * 86400))
        self.assertEqual(bailian_keys.usage_eligibility("k", edge, NOW)["state"], "CURRENT")
        past = fresh_row(resets_dt=NOW_DT + timedelta(seconds=8 * 86400 + 1))
        self.assertEqual(bailian_keys.usage_eligibility("k", past, NOW)["state"], "UNKNOWN")
        expired = fresh_row(resets_dt=NOW_DT)
        self.assertEqual(bailian_keys.usage_eligibility("k", expired, NOW)["state"], "UNKNOWN")
        gone = fresh_row(resets_dt=NOW_DT - timedelta(seconds=1))
        self.assertEqual(bailian_keys.usage_eligibility("k", gone, NOW)["state"], "UNKNOWN")

    def test_september_observation_cannot_establish_october_exclusion(self):
        row = fresh_row(
            observed_dt=datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc),
            resets_dt=datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc),
        )
        info = bailian_keys.usage_eligibility("k", row, NOW)
        self.assertEqual(info["state"], "UNKNOWN")
        self.assertIsNone(info["parked"])

    def test_data_is_closed_and_never_fabricates(self):
        cases = [
            fresh_row(parked=True),
            fresh_row(parked=False),
            fresh_row(parked=True, pct=101),
            fresh_row(parked=True, observed_dt=NOW_DT - timedelta(days=2)),
            None,
            {"keys": {}},
        ]
        for usage in cases:
            info = bailian_keys.usage_eligibility("k", usage, NOW)
            self.assertEqual(set(info), DATA_KEYS)
            self.assertIn(info["state"], {"CURRENT", "UNKNOWN"})
            self.assertTrue(info["parked"] is None or isinstance(info["parked"], bool))
            if info["state"] == "UNKNOWN":
                self.assertIsNone(info["parked"])
                self.assertIsNone(info["observed_at"])
                self.assertIsNone(info["reset_at"])

    def test_row_shape_form_is_accepted(self):
        info = bailian_keys.usage_eligibility("k", fresh_row(parked=True), NOW)
        self.assertEqual(info["state"], "CURRENT")
        doc = {"keys": {"k": fresh_row(parked=True)}}
        self.assertEqual(bailian_keys.usage_eligibility("k", doc, NOW)["state"], "CURRENT")


class ReadUsageEligibility(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qwen-elig-read-")
        self.usage_path = os.path.join(self.tmp, "bailian_usage.json")

    def _write(self, doc):
        with open(self.usage_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def test_reads_document_keys_map(self):
        self._write({"keys": {"k": fresh_row(parked=True)}})
        info = bailian_keys.read_usage_eligibility("k", now=NOW, path=self.usage_path)
        self.assertEqual(info["state"], "CURRENT")
        self.assertIs(info["parked"], True)

    def test_default_path_is_here_bailian_usage_json(self):
        self._write({"keys": {"k": fresh_row(parked=True)}})
        with mock.patch.object(bailian_keys, "HERE", self.tmp):
            info = bailian_keys.read_usage_eligibility("k", now=NOW)
        self.assertEqual(info["state"], "CURRENT")
        self.assertIs(info["parked"], True)

    def test_wrong_account_is_unknown(self):
        self._write({"keys": {"other": fresh_row(parked=True)}})
        info = bailian_keys.read_usage_eligibility("k", now=NOW, path=self.usage_path)
        self.assertEqual(info["state"], "UNKNOWN")
        self.assertIsNone(info["parked"])

    def test_missing_and_malformed_files_are_unknown_without_raising(self):
        info = bailian_keys.read_usage_eligibility("k", now=NOW, path=os.path.join(self.tmp, "absent.json"))
        self.assertEqual(info["state"], "UNKNOWN")
        with open(self.usage_path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        info = bailian_keys.read_usage_eligibility("k", now=NOW, path=self.usage_path)
        self.assertEqual(info["state"], "UNKNOWN")
        self.assertIsNone(info["parked"])

    def test_non_document_shapes_are_unknown(self):
        for doc in ([], "x", 5, None, {"keys": 7}):
            with open(self.usage_path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            info = bailian_keys.read_usage_eligibility("k", now=NOW, path=self.usage_path)
            self.assertEqual(info["state"], "UNKNOWN")

    def test_explicit_now_controls_timeliness(self):
        stale_row = fresh_row(
            observed_dt=NOW_DT - timedelta(days=2), resets_dt=NOW_DT + timedelta(days=3)
        )
        self._write({"keys": {"k": stale_row}})
        self.assertEqual(
            bailian_keys.read_usage_eligibility("k", now=NOW, path=self.usage_path)["state"],
            "UNKNOWN",
        )
        earlier = (NOW_DT - timedelta(days=2) + timedelta(minutes=30)).timestamp()
        self.assertEqual(
            bailian_keys.read_usage_eligibility("k", now=earlier, path=self.usage_path)["state"],
            "CURRENT",
        )

    def test_directory_path_is_unknown_not_raise(self):
        info = bailian_keys.read_usage_eligibility("k", now=NOW, path=self.tmp)
        self.assertEqual(info["state"], "UNKNOWN")


class RouterUsableNames(unittest.TestCase):
    """Fresh park reaches pool routing; unknown usage keeps ordinary eligibility."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qwen-elig-router-")
        self.usage_path = os.path.join(self.tmp, "bailian_usage.json")

    def _write(self, doc):
        with open(self.usage_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def _router(self, names, cooldowns, doc, *, now=NOW):
        self._write(doc)
        with mock.patch.object(bailian_keys, "HERE", self.tmp), mock.patch.object(
            bailian_keys, "key_names", return_value=list(names)
        ), mock.patch.object(
            bailian_keys, "cooldown_rank_readonly",
            side_effect=lambda n: (0 if cooldowns.get(n) is None else
                                   (2 if cooldowns[n][1] == "http_429" else 3))
        ), mock.patch.object(
            bailian_keys, "current_per_key_cap", return_value=10
        ), mock.patch.object(bailian_keys.time, "time", return_value=now):
            # Match the implicit production clock to this synthetic usage row.
            return bailian_keys.usable_names()

    def test_fresh_park_excludes_account_from_routing(self):
        got = self._router(
            ["freshpark", "ok"],
            {"freshpark": None, "ok": None},
            {"keys": {"freshpark": fresh_row(parked=True), "ok": fresh_row(parked=False)}},
        )
        self.assertEqual(got, ["ok"])

    def test_same_row_default_clock_preserves_exact_freshness_boundary(self):
        row = fresh_row(parked=True)
        observed = datetime.fromisoformat(row["observed_at"]).timestamp()
        document = {"keys": {"k": row}}
        self.assertEqual(self._router(["k"], {"k": None}, document,
                                      now=observed + 86400), [])
        self.assertEqual(self._router(["k"], {"k": None}, document,
                                      now=observed + 86401), ["k"])

    def test_stale_park_does_not_exclude(self):
        stale = fresh_row(parked=True, observed_dt=NOW_DT - timedelta(days=2))
        got = self._router(
            ["stale", "ok"], {"stale": None, "ok": None}, {"keys": {"stale": stale}}
        )
        self.assertIn("stale", got)

    def test_unknown_usage_stays_eligible(self):
        got = self._router(
            ["norow", "malformed"],
            {"norow": None, "malformed": None},
            {"keys": {"malformed": {"parked": True}}},
        )
        self.assertEqual(got, ["norow", "malformed"])

    def test_unknown_or_unsafe_cooldown_fails_closed_even_with_unparked_usage(self):
        self._write({"keys": {"k": fresh_row(parked=False)}})
        with mock.patch.object(bailian_keys, "HERE", self.tmp), \
             mock.patch.object(bailian_keys, "key_names", return_value=["k"]), \
             mock.patch.object(bailian_keys, "cooldown_rank_readonly", return_value=1):
            self.assertEqual(bailian_keys.usable_names(), [])

    def test_park_reaches_routing_even_for_429_key(self):
        got = self._router(
            ["k429"],
            {"k429": ("t", "http_429")},
            {"keys": {"k429": fresh_row(parked=True)}},
        )
        self.assertEqual(got, [])

    def test_429_key_without_park_stays_usable(self):
        got = self._router(
            ["k429"], {"k429": ("t", "http_429")}, {"keys": {}}
        )
        self.assertEqual(got, ["k429"])

    def test_stale_park_on_429_key_stays_usable(self):
        stale = fresh_row(parked=True, observed_dt=NOW_DT - timedelta(days=2))
        got = self._router(
            ["k429"], {"k429": ("t", "http_429")}, {"keys": {"k429": stale}}
        )
        self.assertEqual(got, ["k429"])

    def test_non_429_cooldown_still_excluded(self):
        got = self._router(
            ["dead", "alive"],
            {"dead": ("t", "http_401"), "alive": None},
            {"keys": {}},
        )
        self.assertEqual(got, ["alive"])

    def test_unrelated_account_not_parked_by_neighbor_row(self):
        got = self._router(
            ["a", "b"],
            {"a": None, "b": None},
            {"keys": {"a": {"parked": "garbage"}, "b": fresh_row(parked=True)}},
        )
        self.assertEqual(got, ["a"])

    def test_helper_failure_does_not_invent_exhaustion(self):
        self._write({"keys": {"k": fresh_row(parked=True)}})
        with mock.patch.object(bailian_keys, "HERE", self.tmp), mock.patch.object(
            bailian_keys, "key_names", return_value=["k"]
        ), mock.patch.object(
            bailian_keys, "cooldown_rank_readonly", return_value=0
        ), mock.patch.object(
            bailian_keys,
            "read_usage_eligibility",
            side_effect=RuntimeError("boom"),
        ):
            self.assertEqual(bailian_keys.usable_names(), ["k"])


class PickParkedKeys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qwen-elig-pick-")
        self.usage_path = os.path.join(self.tmp, "bailian_usage.json")

    def _parked_with(self, doc, *, now=NOW):
        with open(self.usage_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        with mock.patch.object(pick, "BAILIAN_USAGE", self.usage_path), \
             mock.patch.object(bailian_keys.time, "time", return_value=now):
            return pick._parked_bailian_keys()

    def test_fresh_park_is_parked(self):
        got = self._parked_with({"keys": {"k": fresh_row(parked=True)}})
        self.assertEqual(got, {"k"})

    def test_same_row_default_clock_preserves_exact_freshness_boundary(self):
        row = fresh_row(parked=True)
        observed = datetime.fromisoformat(row["observed_at"]).timestamp()
        document = {"keys": {"k": row}}
        self.assertEqual(self._parked_with(document, now=observed + 86400), {"k"})
        self.assertEqual(self._parked_with(document, now=observed + 86401), set())
        with mock.patch.object(bailian_keys.time, "time", return_value=observed + 86401):
            info = bailian_keys.read_usage_eligibility("k", path=self.usage_path)
        self.assertEqual(info["state"], "UNKNOWN")
        self.assertIsNone(info["parked"])

    def test_fresh_not_parked_and_stale_are_not_parked(self):
        stale = fresh_row(parked=True, observed_dt=NOW_DT - timedelta(days=2))
        got = self._parked_with(
            {"keys": {"k": fresh_row(parked=False), "s": stale}}
        )
        self.assertEqual(got, set())

    def test_non_bool_parked_is_unknown_not_parked(self):
        got = self._parked_with({"keys": {"k": fresh_row(parked="yes")}})
        self.assertEqual(got, set())

    def test_unreadable_document_parks_nothing(self):
        with open(self.usage_path, "w", encoding="utf-8") as fh:
            fh.write("{oops")
        with mock.patch.object(pick, "BAILIAN_USAGE", self.usage_path):
            self.assertEqual(pick._parked_bailian_keys(), set())
        with mock.patch.object(pick, "BAILIAN_USAGE", os.path.join(self.tmp, "absent.json")):
            self.assertEqual(pick._parked_bailian_keys(), set())

    def test_malformed_keys_map_parks_nothing(self):
        self.assertEqual(self._parked_with({"keys": 7}), set())
        self.assertEqual(self._parked_with({}), set())

    def test_unrelated_account_not_parked_by_wrong_shape(self):
        got = self._parked_with(
            {"keys": {"a": {"parked": True}, "b": fresh_row(parked=True)}}
        )
        self.assertEqual(got, {"b"})

    def test_helper_raising_per_name_is_skipped(self):
        with open(self.usage_path, "w", encoding="utf-8") as fh:
            json.dump({"keys": {"k": fresh_row(parked=True)}}, fh)
        with mock.patch.object(pick, "BAILIAN_USAGE", self.usage_path), mock.patch.object(
            bailian_keys, "read_usage_eligibility", side_effect=RuntimeError("boom")
        ):
            self.assertEqual(pick._parked_bailian_keys(), set())


class BrokerUsageGate(unittest.TestCase):
    """Fresh park reaches exact broker account selection before cooldown."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qwen-elig-broker-")
        self.usage_path = os.path.join(self.tmp, "bailian_usage.json")
        self.broker = object.__new__(lease_broker.Broker)
        self.broker.external_gates = True
        self.broker.now = lambda: NOW

    def _write(self, doc):
        with open(self.usage_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def _with_usage(self, doc):
        self._write(doc)
        return mock.patch.object(bailian_keys, "HERE", self.tmp)

    def test_fresh_park_blocks_before_cooldown_lookup(self):
        with self._with_usage({"keys": {"k": fresh_row(parked=True)}}), mock.patch.object(
            bailian_keys, "cooldown_rank_readonly", side_effect=RuntimeError("must not be reached")
        ):
            self.assertIsNone(self.broker._bailian_effective_cap("k", 10))

    def test_fresh_park_blocks_429_key_too(self):
        with self._with_usage({"keys": {"k": fresh_row(parked=True)}}), mock.patch.object(
            bailian_keys, "cooldown_rank_readonly", return_value=2
        ), mock.patch.object(bailian_keys, "_effective_cap_for_key", return_value=5):
            self.assertIsNone(self.broker._bailian_effective_cap("k", 10))

    def test_unknown_local_cooldown_is_not_grantable_when_usage_says_unparked(self):
        with self._with_usage({"keys": {"k": fresh_row(parked=False)}}), \
             mock.patch.object(bailian_keys, "cooldown_rank_readonly", return_value=1), \
             mock.patch.object(bailian_keys, "current_per_key_cap", return_value=10):
            self.assertIsNone(self.broker._bailian_effective_cap("k", 10))

    def test_unknown_usage_preserves_cooldown_and_cap_behavior(self):
        with self._with_usage({}), mock.patch.object(
            bailian_keys, "cooldown_rank_readonly", return_value=0
        ), mock.patch.object(bailian_keys, "current_per_key_cap", return_value=10):
            self.assertEqual(self.broker._bailian_effective_cap("k", 4), 4)
            self.assertEqual(self.broker._bailian_effective_cap("k", 25), 10)

    def test_unknown_usage_non_429_cooldown_still_not_grantable(self):
        with self._with_usage({}), mock.patch.object(
            bailian_keys, "cooldown_rank_readonly", return_value=3
        ):
            self.assertIsNone(self.broker._bailian_effective_cap("k", 10))

    def test_unknown_usage_429_cooldown_keeps_soft_cap(self):
        with self._with_usage({}), mock.patch.object(
            bailian_keys, "cooldown_rank_readonly", return_value=2
        ), mock.patch.object(bailian_keys, "_effective_cap_for_key", return_value=3):
            self.assertEqual(self.broker._bailian_effective_cap("k", 10), 3)

    def test_stale_park_does_not_block_429_key(self):
        stale = fresh_row(parked=True, observed_dt=NOW_DT - timedelta(days=2))
        with self._with_usage({"keys": {"k": stale}}), mock.patch.object(
            bailian_keys, "cooldown_rank_readonly", return_value=2
        ), mock.patch.object(bailian_keys, "_effective_cap_for_key", return_value=7):
            self.assertEqual(self.broker._bailian_effective_cap("k", 10), 7)

    def test_no_external_gates_no_usage_gate(self):
        self.broker.external_gates = False
        with self._with_usage({"keys": {"k": fresh_row(parked=True)}}):
            self.assertEqual(self.broker._bailian_effective_cap("k", 6), 6)

    def test_helper_failure_keeps_existing_eligibility(self):
        with self._with_usage({"keys": {"k": fresh_row(parked=True)}}), mock.patch.object(
            bailian_keys, "read_usage_eligibility", side_effect=RuntimeError("boom")
        ), mock.patch.object(bailian_keys, "cooldown_rank_readonly", return_value=0), mock.patch.object(
            bailian_keys, "current_per_key_cap", return_value=10
        ):
            self.assertEqual(self.broker._bailian_effective_cap("k", 9), 9)

    def test_failure_after_gate_cannot_restore_known_parked(self):
        with self._with_usage({"keys": {"k": fresh_row(parked=True)}}), mock.patch.object(
            bailian_keys, "cooldown_rank_readonly", side_effect=RuntimeError("late boom")
        ):
            self.assertIsNone(self.broker._bailian_effective_cap("k", 10))


class Http429SoftUnchanged(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(bailian_keys, "current_per_key_cap", return_value=10)
        p.start()
        self.addCleanup(p.stop)

    def _cd(self, reason):
        # The real broker and CLI now share a non-mutating, fail-closed rank
        # reader. Fixture the rank directly instead of the obsolete mutating
        # cooldown_info helper; 0 healthy, 2 soft-429, 3 hard denial.
        rank = 0 if reason is None else (2 if reason == "http_429" else 3)
        p = mock.patch.object(bailian_keys, "cooldown_rank_readonly", return_value=rank)
        p.start()
        self.addCleanup(p.stop)

    def test_soft_cap_with_floor_three(self):
        self._cd("http_429")
        with mock.patch.object(bailian_keys, "load_policy", return_value={"soft_cap_on_429": True}):
            for soft, want in ((5, 4), (4, 3), (3, 3), (2, 3), (1, 3), (100, 10)):
                with mock.patch.object(bailian_keys, "_read_soft_cap", return_value=soft):
                    self.assertEqual(bailian_keys._effective_cap_for_key("k"), want, repr(soft))
            with mock.patch.object(bailian_keys, "_read_soft_cap", return_value=None):
                self.assertEqual(bailian_keys._effective_cap_for_key("k"), 10)

    def test_soft_cap_disabled_uses_full_cap(self):
        self._cd("http_429")
        with mock.patch.object(bailian_keys, "load_policy", return_value={}), mock.patch.object(
            bailian_keys, "_read_soft_cap", return_value=5
        ):
            self.assertEqual(bailian_keys._effective_cap_for_key("k"), 10)

    def test_non_429_cooldown_contributes_zero_and_no_cooldown_full(self):
        self._cd("http_401")
        with mock.patch.object(bailian_keys, "load_policy", return_value={"soft_cap_on_429": True}):
            self.assertEqual(bailian_keys._effective_cap_for_key("k"), 0)
        self._cd(None)
        with mock.patch.object(bailian_keys, "load_policy", return_value={"soft_cap_on_429": True}):
            self.assertEqual(bailian_keys._effective_cap_for_key("k"), 10)

    def test_router_and_broker_keep_429_soft_admission(self):
        self._cd("http_429")
        tmp = tempfile.mkdtemp(prefix="qwen-elig-soft-")
        usage = os.path.join(tmp, "bailian_usage.json")
        with open(usage, "w", encoding="utf-8") as fh:
            json.dump({"keys": {}}, fh)
        with mock.patch.object(bailian_keys, "HERE", tmp), mock.patch.object(
            bailian_keys, "key_names", return_value=["k"]
        ):
            self.assertEqual(bailian_keys.usable_names(), ["k"])
        broker = object.__new__(lease_broker.Broker)
        broker.external_gates = True
        broker.now = lambda: NOW
        with mock.patch.object(bailian_keys, "HERE", tmp), mock.patch.object(
            bailian_keys, "load_policy", return_value={"soft_cap_on_429": True}
        ), mock.patch.object(bailian_keys, "_read_soft_cap", return_value=5):
            self.assertEqual(broker._bailian_effective_cap("k", 10), 4)
            self.assertEqual(broker._bailian_effective_cap("k", 3), 3)


class FakeUsageCannotMutatePolicyOrStores(unittest.TestCase):
    def test_hostile_usage_document_is_inert(self):
        tmp = tempfile.mkdtemp(prefix="qwen-elig-hostile-")
        usage = os.path.join(tmp, "bailian_usage.json")
        doc = {
            "keys": {"k": fresh_row(parked=True)},
            "parked": True,
            "policy": {"soft_cap_on_429": True, "per_key_cap": 9999},
            "soft_cap_on_429": True,
            "per_key_cap": 9999,
            "cooldown": {"k": None},
            "cooldown_info": {"k": None},
            "k": fresh_row(parked=False),
        }
        with open(usage, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        before = open(usage, "rb").read()

        sentinel_policy = {"soft_cap_on_429": True}
        calls = []

        def recording_load_policy():
            calls.append(1)
            return sentinel_policy

        with mock.patch.object(bailian_keys, "HERE", tmp), mock.patch.object(
            bailian_keys, "key_names", return_value=["k", "ghost"]
        ), mock.patch.object(
            bailian_keys, "cooldown_rank_readonly", return_value=2
        ), mock.patch.object(
            bailian_keys, "current_per_key_cap", return_value=10
        ), mock.patch.object(
            bailian_keys, "load_policy", side_effect=recording_load_policy
        ), mock.patch.object(
            bailian_keys, "_read_soft_cap", return_value=5
        ), mock.patch.object(
            pick, "BAILIAN_USAGE", usage
        ), mock.patch.object(bailian_keys.time, "time", return_value=NOW):
            info = bailian_keys.read_usage_eligibility("k", now=NOW)
            self.assertEqual(info["state"], "CURRENT")
            self.assertIs(info["parked"], True)
            # "k" is fresh-parked (excluded); "ghost" has no applicable row, so
            # unknown usage keeps it eligible rather than inventing exhaustion.
            self.assertEqual(bailian_keys.usable_names(), ["ghost"])
            self.assertEqual(pick._parked_bailian_keys(), {"k"})
            # The eligibility path never consults or rewrites policy.
            self.assertEqual(calls, [])
            self.assertEqual(bailian_keys._effective_cap_for_key("k"), 4)
            self.assertEqual(sentinel_policy, {"soft_cap_on_429": True})

        self.assertEqual(open(usage, "rb").read(), before)
        self.assertEqual(sorted(os.listdir(tmp)), ["bailian_usage.json"])

    def test_usage_facts_cannot_park_unconfigured_or_unrelated_accounts(self):
        tmp = tempfile.mkdtemp(prefix="qwen-elig-unrel-")
        usage = os.path.join(tmp, "bailian_usage.json")
        doc = {
            "keys": {
                "ghost": fresh_row(parked=True),
                "broken": {"parked": True, "pct_7d": "90", "observed_at": "x", "resets_at": "y"},
                "real": fresh_row(parked=True),
            }
        }
        with open(usage, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        with mock.patch.object(bailian_keys, "HERE", tmp), mock.patch.object(
            bailian_keys, "key_names", return_value=["broken", "real"]
        ), mock.patch.object(bailian_keys, "cooldown_rank_readonly", return_value=0), mock.patch.object(
            pick, "BAILIAN_USAGE", usage
        ), mock.patch.object(bailian_keys.time, "time", return_value=NOW):
            self.assertEqual(bailian_keys.usable_names(), ["broken"])
            self.assertEqual(pick._parked_bailian_keys(), {"real", "ghost"})




class ParentIntegrationNegatives(unittest.TestCase):
    """Additional actual-source cases absent from the fragment return."""

    def test_unbound_file_row_cannot_park_every_account(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "bailian_usage.json")
            with open(path, "w") as output:
                json.dump(fresh_row(), output)
            for name in ("k", "foreign"):
                self.assertEqual(bailian_keys.read_usage_eligibility(
                    name, now=NOW, path=path)["state"], "UNKNOWN")

    def test_oversized_usage_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "bailian_usage.json")
            with open(path, "wb") as output:
                output.write(b" " * 1048577)
            self.assertEqual(bailian_keys.read_usage_eligibility(
                "k", now=NOW, path=path)["state"], "UNKNOWN")
            with mock.patch.object(pick, "BAILIAN_USAGE", path):
                self.assertEqual(pick._parked_bailian_keys(), set())

    def test_overflow_and_boolean_clock_are_unknown(self):
        row = fresh_row(pct=10 ** 400)
        self.assertEqual(bailian_keys.usage_eligibility("k", row, NOW)["state"], "UNKNOWN")
        self.assertEqual(bailian_keys.usage_eligibility("k", fresh_row(), True)["state"], "UNKNOWN")

    def test_router_non_object_document_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "bailian_usage.json")
            with open(path, "w") as output:
                json.dump([fresh_row()], output)
            with mock.patch.object(pick, "BAILIAN_USAGE", path):
                self.assertEqual(pick._parked_bailian_keys(), set())


class ActualBrokerSelectionIntegration(unittest.TestCase):
    def test_real_broker_grantable_accounts_joins_fresh_usage_only(self):
        with tempfile.TemporaryDirectory() as directory:
            usage = os.path.join(directory, "bailian_usage.json")
            accounts = os.path.join(directory, "accounts.json")
            with open(accounts, "w") as output:
                json.dump({"providers": {"bailian": {"enabled": True,
                    "concurrency_cap": 14, "accounts": [
                        {"name": "parked", "per_account_cap": 7},
                        {"name": "ready", "per_account_cap": 7}]}}}, output)
            with open(usage, "w") as output:
                json.dump({"keys": {"parked": fresh_row(),
                                    "ready": fresh_row(parked=False)}}, output)
            broker = lease_broker.Broker(
                db_path=os.path.join(directory, "broker.sqlite"),
                lock_path=os.path.join(directory, "broker.lock"),
                accounts_path=accounts, now_fn=lambda: NOW, check_pid=False,
                external_gates=True, this_host="fixture",
                hosts_path=os.path.join(directory, "hosts.json"),
                status_json=os.path.join(directory, "status.json"))
            with mock.patch.object(bailian_keys, "HERE", directory), \
                 mock.patch.object(bailian_keys, "cooldown_rank_readonly", return_value=0), \
                 mock.patch.object(bailian_keys, "current_per_key_cap", return_value=7):
                self.assertEqual([a["name"] for a in broker.grantable_accounts("bailian")],
                                 ["ready"])
                self.assertEqual(broker.pool_cap("bailian"), 7)
                with open(usage, "w") as output:
                    json.dump({"keys": {"parked": fresh_row(
                        observed_dt=NOW_DT-timedelta(days=40),
                        resets_dt=NOW_DT-timedelta(days=33)),
                        "ready": fresh_row(parked=False)}}, output)
                self.assertEqual([a["name"] for a in broker.grantable_accounts("bailian")],
                                 ["parked", "ready"])
                self.assertEqual(broker.pool_cap("bailian"), 14)


if __name__ == "__main__":
    unittest.main()
