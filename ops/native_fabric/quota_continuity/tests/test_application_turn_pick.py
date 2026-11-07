"""Pure APPLICATION selection seam in the candidate picker; no live effects.

Every input is a synthetic owner projection; the offline boundary denies
network, unguarded subprocess and credential opens for the whole module. The
incumbent worker seams are exercised for exact regression on the same pin.
"""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "candidate"), str(ROOT / "source"), str(ROOT / "tests")]
from _offline_boundary import acquire as offline_acquire, release as offline_release
import lease_broker
import pick
import quota_remote


def setUpModule():
    offline_acquire()


def tearDownModule():
    offline_release()


NOW = datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
NOW_EPOCH = NOW.timestamp()
_UNSET = object()


def policy_document(overrides=None):
    doc = {
        "routing": {
            "execute_order": ["minimax", "glm-flash", "bailian", "grok", "cursor"],
            "judgment_order": ["glm-5.3", "grok", "cursor", "fable"],
            "acceptance_floor": "0.6 over last 20",
        },
        "pools": {
            "go": {"enabled": True, "task_classes": ["mechanical", "review", "build"],
                   "worker_models": ["fixture-model"], "default_model": "fixture-model"},
            "glm": {"enabled": True, "task_classes": ["mechanical", "review"],
                    "models": {"executor": "glm-5.3-flash", "reviewer": "glm-5.3"},
                    "model_capabilities": {"glm-5.3-flash": {"vision": False},
                                           "glm-5.3": {"vision": True}}},
            "grok": {"enabled": True, "task_classes": ["mechanical", "review"],
                     "windows": {"weekly": {}}},
            "minimax": {"enabled": True, "task_classes": ["mechanical", "review"]},
            "bailian": {"enabled": True, "task_classes": ["mechanical", "review"],
                        "worker_models": ["qwen3.8-flash"]},
            "cursor": {"enabled": True, "task_classes": ["mechanical", "review"]},
            "codex-native": {"enabled": True, "task_classes": ["mechanical"]},
            "claude-native": {"enabled": True, "task_classes": ["mechanical"]},
            "ocfree": {"enabled": True, "task_classes": ["mechanical"]},
        },
    }
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(doc.get(key), dict):
            doc[key].update(copy.deepcopy(value))
        else:
            doc[key] = copy.deepcopy(value)
    return doc


def recipe(**overrides):
    base = {"model": "fixture-model", "mode": "go-codex", "protocol": "chat",
            "streaming": False, "driver": "go-codex", "profile": "primary",
            "source": "go-router-owner", "capabilities": {}, "order_rank": 0,
            "max_turn_seconds": 300, "max_steps": 2,
            "qualification_ref": "fixture:controlled-qualification",
            "application_permission_ref": "fixture:ordinary-inference",
            "grant_ref": {"grant_id": "macro-app",
                          "digest": hashlib.sha256(b"grant-bytes").hexdigest()}}
    base.update(overrides)
    return base


def catalogue(**pool_overrides):
    pools = {"go": {"enabled": True, "recipes": [recipe()]}}
    pools.update(copy.deepcopy(pool_overrides))
    return {"schema": "mastermind.fabric_application_catalogue.v1",
            "pool_order": ["go"], "pools": pools}


def observation(**overrides):
    base = {"source": "fixture-broker", "observed_at": NOW_EPOCH, "fresh_s": 600.0,
            "cooldown": False, "model_room": {"fixture-model": 2},
            "host": "vps", "mode": "go-codex"}
    base.update(overrides)
    return base


def observations(**overrides):
    rows = {"go": observation()}
    for name, value in overrides.items():
        if name in pick._APPLICATION_POOL_ORDER:
            rows[name] = copy.deepcopy(value)
        else:
            rows["go"][name] = copy.deepcopy(value)
    return rows


def task(**overrides):
    base = {"task_class": "mechanical", "task_complexity": "C1_ROUTINE_BOUNDED",
            "needs": [], "subject_pool": None,
            "escalation_reason": "fixture application economic witness",
            "route_key": "fabric-app-picker-native-20261105-01"}
    base.update(overrides)
    return base


class ApplicationPickFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.policy_path = self.directory / "pools.yaml"
        self.write_policy(policy_document())
        patcher = patch.object(pick, "POOLS_YAML", str(self.policy_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.policy = pick.read_application_policy()

    def write_policy(self, doc):
        self.policy_path.write_text(yaml.safe_dump(doc, sort_keys=True), encoding="utf-8")

    def select(self, task_value=None, *, pol=None, cat=None, obs=None,
               quality=_UNSET, now=NOW, expected=None):
        return pick.select_application(
            task_value if task_value is not None else task(),
            policy=pol if pol is not None else self.policy,
            catalogue=cat if cat is not None else catalogue(),
            observations=obs if obs is not None else observations(),
            quality_records=[] if quality is _UNSET else quality,
            now=now, expected_identity=expected)

    def select_with_tripwires(self, **kwargs):
        trips = []
        original_clock = pick._glm_now

        def ledger_trip(*args):
            trips.append("ledger")
            return []

        def clock_trip(*args):
            trips.append("clock")
            return original_clock()

        def broker_trip(*args):
            trips.append("broker")
            raise AssertionError("broker constructed during selection")

        def provider_trip(*args):
            trips.append("provider")
            raise AssertionError("provider read during selection")

        with patch.object(pick, "_ledger_records", ledger_trip), \
                patch.object(pick, "_glm_now", clock_trip), \
                patch.object(pick, "_grok_exhausted", provider_trip), \
                patch.object(lease_broker, "default_broker", broker_trip), \
                patch.object(quota_remote, "read_provider", provider_trip):
            return self.select(**kwargs), trips


class ApplicationPolicyReading(ApplicationPickFixture):
    def test_fresh_commitments_and_byte_change(self):
        first = pick.read_application_policy()
        second = pick.read_application_policy()
        for name in ("bytes_sha256", "text_sha256", "parsed_sha256", "critical_sha256"):
            self.assertEqual(getattr(first, name), getattr(second, name))
        self.assertEqual(first.document, policy_document())
        with self.assertRaises(AttributeError):
            first.bytes_sha256 = "x"
        self.write_policy(policy_document({"routing": {"acceptance_floor": "0.5 over last 20"}}))
        third = pick.read_application_policy()
        self.assertNotEqual(first.bytes_sha256, third.bytes_sha256)
        self.assertNotEqual(first.critical_sha256, third.critical_sha256)
        self.assertEqual(first.consumed, False)

    def test_text_mode_commitment_matches_incumbent_normalization(self):
        raw = (b"routing: {acceptance_floor: '0.6 over last 20'}\r\n"
               b"pools:\r\n  grok: {enabled: true, windows: {weekly: {}}}\r\n")
        self.policy_path.write_bytes(raw)
        policy = pick.read_application_policy()
        normalized = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8").read()
        self.assertEqual(policy.text_sha256,
                         hashlib.sha256(normalized.encode("utf-8")).hexdigest())
        self.assertNotEqual(policy.text_sha256, policy.bytes_sha256)

    def test_unavailable_and_unsafe_sources_refuse(self):
        self.policy_path.unlink()
        with self.assertRaises(pick.ApplicationPolicyError) as missing:
            pick.read_application_policy()
        self.assertEqual(missing.exception.code, "policy_source_unavailable")
        link = self.directory / "link.yaml"
        link.symlink_to(self.directory / "elsewhere.yaml")
        with patch.object(pick, "POOLS_YAML", str(link)):
            with self.assertRaises(pick.ApplicationPolicyError):
                pick.read_application_policy()
        with patch.object(pick, "POOLS_YAML", str(self.directory)):
            with self.assertRaises(pick.ApplicationPolicyError):
                pick.read_application_policy()

    def test_duplicate_nonfinite_and_shape_refusal_codes(self):
        duplicate = (yaml.safe_dump(policy_document())
                     .replace("acceptance_floor:", "acceptance_floor:", 1)
                     + "routing: {}\n")
        self.policy_path.write_text(duplicate, encoding="utf-8")
        with self.assertRaises(pick.ApplicationPolicyError) as caught:
            pick.read_application_policy()
        self.assertEqual(caught.exception.code, "policy_parse_invalid")
        self.write_policy(policy_document())
        text = self.policy_path.read_text(encoding="utf-8").replace(
            "acceptance_floor: 0.6 over last 20",
            "acceptance_floor: 0.6 over last 20\nnonfinite: .nan")
        self.policy_path.write_text(text, encoding="utf-8")
        with self.assertRaises(pick.ApplicationPolicyError) as caught:
            pick.read_application_policy()
        self.assertEqual(caught.exception.code, "policy_parse_invalid")
        doc = policy_document()
        doc["pools"] = {}
        self.write_policy(doc)
        with self.assertRaises(pick.ApplicationPolicyError) as caught:
            pick.read_application_policy()
        self.assertEqual(caught.exception.code, "policy_shape_invalid")
        doc = policy_document()
        doc["pools"].pop("grok")
        self.write_policy(doc)
        with self.assertRaises(pick.ApplicationPolicyError) as caught:
            pick.read_application_policy()
        self.assertEqual(caught.exception.code, "policy_critical_invalid")
        self.policy_path.write_text("[]\n", encoding="utf-8")
        with self.assertRaises(pick.ApplicationPolicyError) as caught:
            pick.read_application_policy()
        self.assertEqual(caught.exception.code, "policy_parse_invalid")

    def test_no_cache_fallback_after_owner_disappears(self):
        self.policy_path.unlink()
        with self.assertRaises(pick.ApplicationPolicyError):
            pick.read_application_policy()
        other = self.directory / "other.yaml"
        other.write_text(yaml.safe_dump(policy_document()), encoding="utf-8")
        with patch.object(pick, "POOLS_YAML", str(other)):
            policy = pick.read_application_policy()
        self.assertEqual(policy.critical_sha256, self.policy.critical_sha256)


class ApplicationSelectionInputs(ApplicationPickFixture):
    def test_unknown_task_context_refuses(self):
        for reason, value in (
                ("task_context_invalid", "not-a-context"),
                ("task_context_invalid", {"task_class": "mechanical"}),
                ("task_context_unknown_field", task(prefer="go")),
                ("task_class_unqualified", task(task_class="")),
                ("task_class_unqualified", task(task_class="unknown")),
                ("task_class_unqualified", task(task_class="arbitrary_brain_query")),
                ("unknown_task_complexity", task(task_complexity="C9_NOVEL")),
                ("task_needs_invalid", task(needs=["vision", 7])),
                ("task_subject_invalid", task(subject_pool="   ")),
                ("task_witness_invalid", task(escalation_reason=42)),
                ("task_route_key_invalid", task(route_key="")),
                ("task_requested_model_invalid", task(requested_model="has space")),
                ("task_requested_model_invalid", task(requested_model="bad/model!*"))):
            with self.subTest(reason=reason):
                result = self.select(value)
                self.assertFalse(result["ok"])
                self.assertEqual(result["reason"], reason)
                self.assertFalse(result["execution_authorized"])
                self.assertTrue(result["requires_fresh_admission"])

    def test_clock_policy_quality_and_catalogue_input_refusals(self):
        naive = datetime(2026, 11, 4, 12, 0, 0)
        for reason, kwargs in (
                ("now_unqualified", dict(now=naive)),
                ("now_unqualified", dict(now="soon")),
                ("policy_input_unqualified", dict(pol=self.policy.document)),
                ("catalogue_invalid", dict(cat={"schema": "x"})),
                ("catalogue_schema_unknown", dict(cat={"schema": "other.v1",
                    "pool_order": ["go"], "pools": catalogue()["pools"]})),
                ("catalogue_pool_order_invalid", dict(cat={"schema":
                    "mastermind.fabric_application_catalogue.v1", "pool_order": ["Qwen"],
                    "pools": catalogue()["pools"]})),
                ("catalogue_pool_unknown", dict(cat={"schema":
                    "mastermind.fabric_application_catalogue.v1", "pool_order": ["go"],
                    "pools": {"qwen": catalogue()["pools"]["go"]}})),
                ("observations_invalid", dict(obs=[])),
                ("observation_pool_unknown", dict(obs={"Qwen": observation()})),
                ("quality_history_unavailable", dict(quality=None)),
                ("quality_history_unavailable", dict(quality=["not-a-record"])),
                ("identity_input_invalid", dict(expected="fixture-model")),
                ("identity_field_unknown", dict(expected={"account": "account-a"}))):
            with self.subTest(reason=reason):
                result = self.select(**kwargs)
                self.assertFalse(result["ok"])
                self.assertEqual(result["reason"], reason)
                self.assertIsNone(result["selection"])

    def test_catalogue_entry_defects_are_typed(self):
        broken = catalogue()
        broken["pools"]["go"]["recipes"][0].pop("qualification_ref")
        result = self.select(cat=broken)
        self.assertEqual(result["coverage"]["go"], "catalogue_entry_invalid")
        broken = catalogue()
        broken["pools"]["go"]["recipes"][0]["grant_ref"]["digest"] = "nothex"
        self.assertEqual(self.select(cat=broken)["coverage"]["go"],
                         "catalogue_entry_invalid")
        broken = catalogue()
        broken["pools"]["go"]["streaming_note"] = True
        self.assertEqual(self.select(cat=broken)["coverage"]["go"],
                         "catalogue_entry_invalid")
        broken = catalogue()
        broken["pools"]["go"]["recipes"] = [recipe(), recipe()]
        # Identical duplicated rows are one recipe, not an ambiguity: the
        # picker dedupes exact repeats and selection proceeds.
        self.assertEqual(self.select(cat=broken)["coverage"]["go"], "selected")
        self.assertEqual(self.select(cat=catalogue(**{
            "go": {"enabled": True, "recipes": []}}))["coverage"]["go"],
            "pool_not_offered")


class ApplicationSelectionCoverage(ApplicationPickFixture):
    def test_nine_pool_coverage_with_exact_pool_separation(self):
        cat = catalogue(**{
            "glm": {"enabled": False, "recipes": [recipe(
                model="glm-5.3-flash", mode="glm", driver="glm", profile="primary",
                source="glm-owner", grant_ref={"grant_id": "glm-app",
                                               "digest": "a" * 64})]},
            "grok": {"enabled": True, "recipes": [recipe(
                model="grok-4.7", mode="grok", driver="grok", profile="primary",
                source="grok-owner", grant_ref={"grant_id": "gk-app",
                                                "digest": "0" * 64})]},
            "bailian": {"enabled": True, "recipes": [recipe(
                model="qwen3.8-flash", mode="qwen", driver="qwen", profile="primary",
                source="bailian-owner", grant_ref={"grant_id": "bl-app",
                                                   "digest": "c" * 64})]},
            "cursor": {"enabled": True, "recipes": [recipe(
                model="composer-2.5", mode="cursor", driver="cursor", profile="primary",
                source="cursor-owner", grant_ref={"grant_id": "cu-app",
                                                  "digest": "d" * 64})]},
            "codex-native": {"enabled": True, "recipes": [recipe(
                model="gpt-6.1-sol", mode="codex-native", driver="codex-native",
                profile="primary", source="codex-owner",
                grant_ref={"grant_id": "cx-app", "digest": "e" * 64})]},
            "claude-native": {"enabled": True, "recipes": [recipe(
                model="opus", mode="claude-native", driver="claude-native",
                profile="primary", source="claude-owner",
                grant_ref={"grant_id": "cl-app", "digest": "f" * 64})]},
        })
        obs = observations(**{
            "bailian": observation(source="fixture-broker", observed_at=NOW_EPOCH - 3600,
                                   fresh_s=60.0, model_room={"qwen3.8-flash": 1},
                                   mode="qwen"),
            "cursor": observation(cooldown=True, cooldown_reason="provider-429",
                                  model_room={"composer-2.5": 1}, mode="cursor"),
            "codex-native": observation(model_room={}, mode="codex-native"),
            "claude-native": observation(model_room={}, mode="claude-native"),
            "go": observation(),
        })
        cat["pool_order"] = ["codex-native", "claude-native", "go"]
        result = self.select(cat=cat, obs=obs)
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["selection"]["pool"], "go")
        self.assertEqual(result["coverage"], {
            "go": "selected",
            "glm": "pool_disabled",
            "minimax": "pool_not_in_catalogue",
            "bailian": "observation_stale",
            "grok": "observation_missing",
            "cursor": "cooldown_active",
            "codex-native": "model_room_unknown",
            "claude-native": "model_room_unknown",
            "ocfree": "policy_not_ordered",
        })

    def test_enablement_auto_unresolved_and_disabled_states(self):
        doc = policy_document()
        doc["pools"]["go"]["enabled"] = "auto"
        self.write_policy(doc)
        policy = pick.read_application_policy()
        self.assertEqual(self.select(pol=policy)["coverage"]["go"],
                         "pool_enablement_unresolved")
        doc["pools"]["go"]["enabled"] = False
        self.write_policy(doc)
        policy = pick.read_application_policy()
        self.assertEqual(self.select(pol=policy)["coverage"]["go"], "pool_disabled")
        self.assertEqual(self.select(pol=policy)["reason"],
                         "no_qualified_application_pool")
        cat = catalogue()
        cat["pools"]["go"]["enabled"] = False
        self.assertEqual(self.select(cat=cat)["coverage"]["go"], "pool_disabled")

    def test_noncanonical_and_alias_inputs_are_refused(self):
        result = self.select(cat=catalogue(**{"go": {"enabled": True, "recipes": [
            recipe(profile="primary", source="s")]}}))
        self.assertEqual(result["coverage"]["go"], "selected")
        bad = catalogue()
        bad["pools"] = {"Qwen": bad["pools"]["go"]}
        self.assertEqual(self.select(cat=bad)["reason"], "catalogue_pool_unknown")
        bad = catalogue()
        bad["pool_order"] = ["go", "go"]
        self.assertEqual(self.select(cat=bad)["reason"], "catalogue_pool_order_invalid")

    def test_route_token_meaning_preserved_for_glm_class_models(self):
        doc = policy_document()
        doc["routing"]["execute_order"] = ["glm-flash"]
        doc["pools"]["glm"]["enabled"] = True
        self.write_policy(doc)
        policy = pick.read_application_policy()
        glm_recipe = recipe(model="glm-5.3-flash", mode="glm", driver="glm",
                            profile="primary", source="glm-owner",
                            grant_ref={"grant_id": "glm-app", "digest": "a" * 64})
        cat = catalogue()
        cat["pool_order"] = ["glm"]
        cat["pools"] = {"glm": {"enabled": True, "recipes": [glm_recipe]}}
        obs = observations(**{"glm": observation(model_room={"glm-5.3-flash": 3},
                                                 mode="glm")})
        result = self.select(pol=policy, cat=cat, obs=obs)
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["selection"]["pool"], "glm")
        self.assertEqual(result["selection"]["model"], "glm-5.3-flash")
        self.assertEqual(result["selection"]["order_source"], "task_default_policy")

    def test_requested_model_survives_and_cannot_promote(self):
        two = catalogue(**{"go": {"enabled": True, "recipes": [
            recipe(order_rank=0),
            recipe(model="other-model", order_rank=1)]}})
        obs = observations(model_room={"fixture-model": 2, "other-model": 1})
        result = self.select(task(requested_model="other-model"), cat=two, obs=obs)
        self.assertEqual(result["selection"]["model"], "other-model")
        self.assertEqual(result["selection"]["order_source"], "requested_model")
        self.assertEqual(self.select(task(requested_model="absent-model"),
                                     cat=two, obs=obs)["coverage"]["go"],
                         "requested_model_unqualified")
        # The defaulted model cannot enter through the pool default when its
        # observed room is zero; the qualified ranked alternative is selected.
        blocked = observations(model_room={"fixture-model": 0, "other-model": 1})
        result = self.select(cat=two, obs=blocked)
        self.assertEqual(result["selection"]["model"], "other-model")
        self.assertEqual(result["selection"]["order_source"], "catalogue_order")
        no_room_at_all = observations(model_room={"fixture-model": 0})
        self.assertEqual(self.select(cat=two, obs=no_room_at_all)["coverage"]["go"],
                         "model_room_exhausted")
        # A route token keeps its existing model meaning. A catalogue with
        # only Flash cannot satisfy the explicit Bailian Max request.
        doc = policy_document()
        doc["pools"]["bailian"]["enabled"] = True
        self.write_policy(doc)
        policy = pick.read_application_policy()
        bailian = recipe(model="qwen3.8-flash", mode="qwen", driver="qwen",
                         profile="primary", source="bailian-owner",
                         grant_ref={"grant_id": "bl-app", "digest": "c" * 64})
        cat = catalogue()
        cat["pool_order"] = ["bailian"]
        cat["pools"] = {"bailian": {"enabled": True, "recipes": [bailian]}}
        obs = observations(**{"bailian": observation(model_room={"qwen3.8-flash": 4},
                                                     mode="qwen")})
        result = self.select(task(requested_model="bailian-max"), pol=policy,
                             cat=cat, obs=obs)
        self.assertEqual(result["ok"], False)
        self.assertEqual(result["coverage"]["bailian"], "requested_model_unqualified")
        for name in set(pick._APPLICATION_POOL_ORDER) - {"bailian"}:
            self.assertEqual(result["coverage"][name], "requested_pool_elsewhere")

    def test_within_pool_order_requires_qualified_ranking(self):
        two = catalogue(**{"go": {"enabled": True, "recipes": [
            recipe(model="fixture-model", order_rank=5),
            recipe(model="other-model", order_rank=1)]}})
        obs = observations(model_room={"fixture-model": 1, "other-model": 1})
        doc = policy_document()
        doc["pools"]["go"].pop("default_model")
        self.write_policy(doc)
        policy = pick.read_application_policy()
        result = self.select(pol=policy, cat=two, obs=obs)
        self.assertEqual(result["selection"]["model"], "other-model")
        self.assertEqual(result["selection"]["order_source"], "catalogue_order")
        tied = catalogue(**{"go": {"enabled": True, "recipes": [
            recipe(model="fixture-model", order_rank=1),
            recipe(model="other-model", order_rank=1)]}})
        self.assertEqual(self.select(pol=policy, cat=tied, obs=obs)["coverage"]["go"],
                         "model_order_unqualified")

    def test_grant_and_driver_ambiguity_never_resolved_by_picker(self):
        ambiguous = catalogue(**{"go": {"enabled": True, "recipes": [
            recipe(), recipe(grant_ref={"grant_id": "other-app",
                                        "digest": "9" * 64})]}})
        self.assertEqual(self.select(cat=ambiguous)["coverage"]["go"],
                         "grant_ref_ambiguous")
        ambiguous = catalogue(**{"go": {"enabled": True, "recipes": [
            recipe(), recipe(driver="go-codex-alt", profile="secondary",
                             source="alt-owner")]}})
        self.assertEqual(self.select(cat=ambiguous)["coverage"]["go"],
                         "driver_ambiguous")

    def test_capability_intersection_with_policy_and_transport(self):
        doc = policy_document()
        doc["pools"]["glm"]["enabled"] = True
        self.write_policy(doc)
        policy = pick.read_application_policy()
        glm_recipe = recipe(model="glm-5.3", mode="glm", driver="glm",
                            profile="primary", source="glm-owner",
                            capabilities={"vision": True},
                            grant_ref={"grant_id": "glm-app", "digest": "a" * 64})
        flash_recipe = recipe(model="glm-5.3-flash", mode="glm", driver="glm",
                              profile="primary", source="glm-owner", order_rank=1,
                              grant_ref={"grant_id": "glm-app", "digest": "a" * 64})
        cat = catalogue()
        cat["pool_order"] = ["glm"]
        cat["pools"] = {"glm": {"enabled": True,
                                "recipes": [glm_recipe, flash_recipe]}}
        obs = observations(**{"glm": observation(model_room={"glm-5.3": 1,
                                                             "glm-5.3-flash": 1},
                                                 mode="glm")})
        # Policy capability for the exact selected model: full model has vision,
        # flash does not (R32); the transport must qualify the same capability.
        result = self.select(task(needs=["vision"]), pol=policy, cat=cat, obs=obs)
        self.assertEqual(result["selection"]["model"], "glm-5.3")
        without_transport = catalogue()
        without_transport["pool_order"] = ["glm"]
        without_transport["pools"] = {"glm": {"enabled": True, "recipes": [
            dict(glm_recipe, capabilities={})]}}
        self.assertEqual(self.select(task(needs=["vision"]),
                                     pol=policy, cat=without_transport,
                                     obs=obs)["coverage"]["glm"],
                         "capability_transport_unknown")
        absent = catalogue()
        absent["pool_order"] = ["glm"]
        absent["pools"] = {"glm": {"enabled": True, "recipes": [
            dict(glm_recipe, capabilities={"vision": False})]}}
        self.assertEqual(self.select(task(needs=["vision"]),
                                     pol=policy, cat=absent,
                                     obs=obs)["coverage"]["glm"],
                         "capability_transport_absent")

    def test_review_independence_and_minimax_rules(self):
        result = self.select(task(task_class="review", subject_pool="glm"))
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["selection"]["pool"], "go")
        self.assertEqual(self.select(task(task_class="review", subject_pool="go"),
                                     )["coverage"]["go"], "independence_refused")
        doc = policy_document()
        doc["pools"]["minimax"]["enabled"] = True
        self.write_policy(doc)
        policy = pick.read_application_policy()
        mm = recipe(model="MiniMax-M3", mode="minimax", driver="minimax",
                    profile="primary", source="minimax-owner",
                    grant_ref={"grant_id": "mm-app", "digest": "b" * 64})
        cat = catalogue()
        cat["pool_order"] = ["minimax"]
        cat["pools"] = {"minimax": {"enabled": True, "recipes": [mm]}}
        obs = observations(**{"minimax": observation(model_room={"MiniMax-M3": 1},
                                                     mode="minimax")})
        self.assertEqual(self.select(task(task_class="review"), pol=policy,
                                     cat=cat, obs=obs)["coverage"]["minimax"],
                         "independence_refused")
        self.assertEqual(self.select(task(task_class="architecture"),
                                     pol=policy, cat=cat, obs=obs)
                         ["coverage"]["minimax"], "policy_refused")
        self.assertEqual(self.select(task(task_class="review", subject_pool="glm"),
                                     pol=policy, cat=cat, obs=obs)
                         ["coverage"]["minimax"], "independence_refused")

    def test_exact_minimax_m2_7_protocol_deny_remains_truthful(self):
        doc = policy_document()
        doc["pools"]["minimax"]["enabled"] = True
        self.write_policy(doc)
        policy = pick.read_application_policy()
        denied = recipe(model="minimax-m2.7", mode="minimax", driver="minimax",
                        profile="primary", source="minimax-owner",
                        grant_ref={"grant_id": "mm-app", "digest": "b" * 64})
        cat = catalogue()
        cat["pool_order"] = ["minimax"]
        cat["pools"] = {"minimax": {"enabled": True, "recipes": [denied]}}
        obs = observations(**{"minimax": observation(model_room={"minimax-m2.7": 1},
                                                     mode="minimax")})
        self.assertEqual(self.select(pol=policy, cat=cat, obs=obs)
                         ["coverage"]["minimax"], "model_protocol_unsupported")
        guard = pick.launch_policy("go", "fix_build", "minimax-m2.7")
        self.assertEqual((guard["allowed"], guard["reason"]),
                         (False, "model_protocol_unsupported"))

    def test_go_b_wire_transport_is_enforced_for_go_recipes(self):
        cat = catalogue()
        cat["pools"]["go"]["recipes"] = [dict(recipe(), protocol="responses")]
        self.assertEqual(self.select(cat=cat)["coverage"]["go"],
                         "application_transport_unqualified")


class ApplicationSelectionQualityAndTime(ApplicationPickFixture):
    def rejected_records(self, count=20):
        return [{"run_id": "r%d" % index, "pool": "go", "job_class": "mechanical",
                 "model": "fixture-model", "accepted_by": "reviewer",
                 "review_rejected": True, "ts": index}
                for index in range(count)]

    def test_empty_history_is_healthy_and_failed_history_demotes(self):
        self.assertEqual(self.select(quality=[])["ok"], True)
        result = self.select(quality=self.rejected_records())
        self.assertEqual(result["coverage"]["go"], "quality_floor")
        healthy = [{"run_id": "ok%d" % index, "pool": "go",
                    "job_class": "mechanical", "model": "fixture-model",
                    "accepted_by": "deterministic", "ts": index}
                   for index in range(20)]
        self.assertEqual(self.select(quality=healthy)["ok"], True)

    def test_floor_is_exact_model_and_class_scoped(self):
        other_model = [{"run_id": "m%d" % index, "pool": "go",
                        "job_class": "mechanical", "model": "other-model",
                        "accepted_by": "reviewer", "review_rejected": True,
                        "ts": index} for index in range(20)]
        self.assertEqual(self.select(quality=other_model)["ok"], True)
        other_class = [{"run_id": "c%d" % index, "pool": "go",
                        "job_class": "review", "model": "fixture-model",
                        "accepted_by": "reviewer", "review_rejected": True,
                        "ts": index} for index in range(20)]
        self.assertEqual(self.select(quality=other_class)["ok"], True)

    def test_glm_credit_promo_uses_explicit_records_and_clock(self):
        doc = policy_document()
        doc["routing"]["glm_credit_promo"] = {
            "starts_at": (NOW - timedelta(hours=1)).isoformat(),
            "ends_at": (NOW + timedelta(hours=1)).isoformat(),
            "models": ["glm-5.3-flash"],
            "balance_pools": ["minimax", "bailian", "go", "grok", "cursor"],
            "credit_multiplier": 0.5, "target_share": 0.5,
        }
        doc["routing"]["execute_order"] = ["bailian", "glm-flash"]
        self.write_policy(doc)
        policy = pick.read_application_policy()
        glm_recipe = recipe(model="glm-5.3-flash", mode="glm", driver="glm",
                            profile="primary", source="glm-owner",
                            grant_ref={"grant_id": "glm-app", "digest": "a" * 64})
        bailian = recipe(model="qwen3.8-flash", mode="qwen", driver="qwen",
                         profile="primary", source="bailian-owner", order_rank=1,
                         grant_ref={"grant_id": "bl-app", "digest": "c" * 64})
        cat = catalogue()
        cat["pool_order"] = ["glm", "bailian"]
        cat["pools"] = {"glm": {"enabled": True, "recipes": [glm_recipe]},
                        "bailian": {"enabled": True, "recipes": [bailian]}}
        obs = observations(**{
            "glm": observation(model_room={"glm-5.3-flash": 2}, mode="glm"),
            "bailian": observation(model_room={"qwen3.8-flash": 2}, mode="qwen")})
        records = [{"run_id": "b%d" % index, "kind": "launch", "pool": "bailian",
                    "job_class": "mechanical", "ts": NOW_EPOCH - 30}
                   for index in range(2)]
        result = self.select(pol=policy, cat=cat, obs=obs, quality=records)
        self.assertEqual(result["selection"]["pool"], "glm")
        self.assertEqual(result["selection"]["reason"], "qualified_application_recipe")
        self.assertEqual(self.select(pol=policy, cat=cat, obs=obs, quality=records,
                                     now=NOW_EPOCH), result)
        later = NOW + timedelta(hours=2)
        fresh_later = observations(**{
            "glm": observation(observed_at=later.timestamp(),
                               model_room={"glm-5.3-flash": 2}, mode="glm"),
            "bailian": observation(observed_at=later.timestamp(),
                                   model_room={"qwen3.8-flash": 2}, mode="qwen")})
        outside = self.select(pol=policy, cat=cat, obs=fresh_later, quality=records,
                              now=later)
        self.assertEqual(outside["selection"]["pool"], "bailian")
        empty_ledger = self.select(pol=policy, cat=cat, obs=obs, quality=[])
        self.assertEqual(empty_ledger["selection"]["pool"], "glm")

    def test_minimax_weekly_catchup_over_explicit_windows(self):
        doc = policy_document()
        doc["routing"]["minimax_weekly_catchup"] = {
            "enabled": True, "task_classes": ["mechanical"], "lag_pct_points": 5,
            "min_remaining_pct": 20, "protect_glm_hours": 2}
        doc["routing"]["execute_order"] = ["bailian", "minimax"]
        self.write_policy(doc)
        policy = pick.read_application_policy()
        bailian = recipe(model="qwen3.8-flash", mode="qwen", driver="qwen",
                         profile="primary", source="bailian-owner",
                         grant_ref={"grant_id": "bl-app", "digest": "c" * 64})
        mm = recipe(model="MiniMax-M3", mode="minimax", driver="minimax",
                    profile="primary", source="minimax-owner", order_rank=1,
                    grant_ref={"grant_id": "mm-app", "digest": "b" * 64})
        cat = catalogue()
        cat["pool_order"] = ["bailian", "minimax"]
        cat["pools"] = {"bailian": {"enabled": True, "recipes": [bailian]},
                        "minimax": {"enabled": True, "recipes": [mm]}}
        obs = observations(**{
            "bailian": observation(model_room={"qwen3.8-flash": 2}, mode="qwen"),
            "minimax": observation(model_room={"MiniMax-M3": 2}, mode="minimax",
                                   burn_down_window=[40.0, 30.0])})
        no_witness = task(escalation_reason="")
        result = self.select(no_witness, pol=policy, cat=cat, obs=obs)
        self.assertEqual(result["selection"]["pool"], "minimax")
        protected = dict(obs)
        protected["glm"] = observation(source="fixture-broker", observed_at=NOW_EPOCH,
                                       fresh_s=600.0, cooldown=False,
                                       model_room={}, burn_down_window=[1.0, 60.0])
        self.assertEqual(self.select(no_witness, pol=policy, cat=cat, obs=protected)
                         ["selection"]["pool"], "bailian")
        plain = dict(obs)
        plain["minimax"] = observation(model_room={"MiniMax-M3": 2}, mode="minimax")
        self.assertEqual(self.select(no_witness, pol=policy, cat=cat, obs=plain)
                         ["selection"]["pool"], "bailian")

    def test_burn_down_urgent_promotion_over_explicit_windows(self):
        doc = policy_document()
        doc["routing"]["execute_order"] = ["bailian", "glm-flash"]
        self.write_policy(doc)
        policy = pick.read_application_policy()
        glm_recipe = recipe(model="glm-5.3-flash", mode="glm", driver="glm",
                            profile="primary", source="glm-owner",
                            grant_ref={"grant_id": "glm-app", "digest": "a" * 64})
        bailian = recipe(model="qwen3.8-flash", mode="qwen", driver="qwen",
                         profile="primary", source="bailian-owner", order_rank=1,
                         grant_ref={"grant_id": "bl-app", "digest": "c" * 64})
        cat = catalogue()
        cat["pool_order"] = ["bailian", "glm"]
        cat["pools"] = {"bailian": {"enabled": True, "recipes": [bailian]},
                        "glm": {"enabled": True, "recipes": [glm_recipe]}}
        obs = observations(**{
            "bailian": observation(model_room={"qwen3.8-flash": 2}, mode="qwen"),
            "glm": observation(model_room={"glm-5.3-flash": 2}, mode="glm",
                               burn_down_window=[10.0, 50.0])})
        self.assertEqual(self.select(pol=policy, cat=cat, obs=obs)
                         ["selection"]["pool"], "glm")
        plain = dict(obs)
        plain["glm"] = observation(model_room={"glm-5.3-flash": 2}, mode="glm")
        self.assertEqual(self.select(pol=policy, cat=cat, obs=plain)
                         ["selection"]["pool"], "bailian")

    def test_routine_sampling_reuses_trusted_route_key(self):
        doc = policy_document()
        doc["routing"]["bailian_routine_sampling"] = {
            "enabled": True, "task_classes": ["mechanical"], "percent": 40}
        doc["routing"]["execute_order"] = ["minimax", "bailian"]
        self.write_policy(doc)
        policy = pick.read_application_policy()
        bailian = recipe(model="qwen3.8-flash", mode="qwen", driver="qwen",
                         profile="primary", source="bailian-owner",
                         grant_ref={"grant_id": "bl-app", "digest": "c" * 64})
        mm = recipe(model="MiniMax-M3", mode="minimax", driver="minimax",
                    profile="primary", source="minimax-owner", order_rank=1,
                    grant_ref={"grant_id": "mm-app", "digest": "b" * 64})
        cat = catalogue()
        cat["pool_order"] = ["bailian", "minimax"]
        cat["pools"] = {"bailian": {"enabled": True, "recipes": [bailian]},
                        "minimax": {"enabled": True, "recipes": [mm]}}
        obs = observations(**{
            "bailian": observation(model_room={"qwen3.8-flash": 2}, mode="qwen"),
            "minimax": observation(model_room={"MiniMax-M3": 2}, mode="minimax")})
        # The default fixture routing key hashes inside the 40% sample band;
        # the out-of-sample key keeps the incumbent minimax-first order.
        self.assertEqual(self.select(task(escalation_reason=""), pol=policy,
                                     cat=cat, obs=obs)["selection"]["pool"],
                         "bailian")
        self.assertEqual(self.select(task(escalation_reason="",
                                          route_key="fixture-route-out-of-sample"),
                                    pol=policy, cat=cat, obs=obs)
                         ["selection"]["pool"], "minimax")


class ApplicationSelectionIdentityAndPurity(ApplicationPickFixture):
    def test_expected_identity_binds_and_conflicts(self):
        result = self.select()
        identity = result["identity"]
        self.assertEqual(self.select(expected={
            "pool": "go", "model": "fixture-model",
            "grant_ref": identity["grant_ref"],
            "task": identity["task"], "policy": identity["policy"]})["ok"], True)
        conflict = self.select(expected={"model": "other-model"})
        self.assertEqual(conflict["reason"], "identity_conflict")
        self.assertEqual(conflict["identity_conflicts"], ["model"])
        self.assertEqual(conflict["identity"]["model"], "fixture-model")
        conflict = self.select(expected={"driver": "go-codex-alt"})
        self.assertEqual(conflict["identity_conflicts"], ["driver"])
        unknown = self.select(expected={"credential_ref": "x"})
        self.assertEqual(unknown["reason"], "identity_field_unknown")

    def test_policy_hash_alone_is_not_identity(self):
        stale = self.policy
        doc = policy_document({"routing": {"acceptance_floor": "0.5 over last 20"}})
        self.write_policy(doc)
        fresh = pick.read_application_policy()
        self.assertNotEqual(stale.critical_sha256, fresh.critical_sha256)
        result = self.select(pol=fresh,
                             expected={"policy": {"parsed_sha256": stale.parsed_sha256,
                                                  "critical_sha256": stale.critical_sha256}})
        self.assertEqual(result["reason"], "identity_conflict")
        self.assertEqual(result["identity_conflicts"], ["policy"])

    def test_selection_is_deterministic_and_effect_free(self):
        result, trips = self.select_with_tripwires()
        self.assertEqual(trips, [])
        self.assertEqual(result["ok"], True)
        again, repeat_trips = self.select_with_tripwires()
        self.assertEqual(repeat_trips, [])
        self.assertEqual(again, result)
        self.assertFalse(result["execution_authorized"])
        self.assertTrue(result["requires_fresh_admission"])
        identity = result["identity"]
        self.assertEqual(identity["streaming"], False)
        self.assertEqual(set(identity), {
            "pool", "model", "mode", "protocol", "streaming", "driver", "profile",
            "source", "capabilities", "grant_ref", "qualification_ref",
            "application_permission_ref", "max_turn_seconds", "max_steps", "host",
            "observation_source", "order_source", "task", "policy"})
        commitments = result["commitments"]
        self.assertEqual(set(commitments), {
            "policy_bytes_sha256", "policy_text_sha256", "policy_parsed_sha256",
            "policy_critical_sha256", "task_digest", "observation_sha256",
            "now_epoch"})
        self.assertEqual(commitments["task_digest"],
                         hashlib.sha256(json.dumps(identity["task"],
                             sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()
                         ).hexdigest())

    def test_input_mutation_cannot_retarget_an_issued_recipe(self):
        result = self.select()
        cat = catalogue()
        obs = observations()
        issued = self.select(cat=cat, obs=obs, expected=result["identity"])
        self.assertEqual(issued["ok"], True)
        cat["pools"]["go"]["recipes"][0]["model"] = "other-model"
        obs["go"]["model_room"] = {"other-model": 9}
        retargeted = self.select(cat=cat, obs=obs, expected=result["identity"])
        self.assertEqual(retargeted["reason"], "identity_conflict")
        self.assertIn("model", retargeted["identity_conflicts"])
        frozen = self.select(cat=copy.deepcopy(cat), obs=copy.deepcopy(obs))
        self.assertEqual(frozen["selection"]["model"], "other-model")
        self.assertEqual(issued["selection"], result["selection"])

    def test_observation_rows_reserve_nothing_and_fail_closed(self):
        no_room = observations(model_room={})
        self.assertEqual(self.select(obs=no_room)["coverage"]["go"],
                         "model_room_unknown")
        exhausted = observations(model_room={"fixture-model": 0})
        self.assertEqual(self.select(obs=exhausted)["coverage"]["go"],
                         "model_room_exhausted")
        stale = observation(observed_at=NOW_EPOCH - 1200, fresh_s=600.0)
        self.assertEqual(self.select(obs={"go": stale})["coverage"]["go"],
                         "observation_stale")
        future = observation(observed_at=NOW_EPOCH + 1)
        self.assertEqual(self.select(obs={"go": future})["coverage"]["go"],
                         "observation_stale")
        invalid = observation(cooldown="maybe")
        self.assertEqual(self.select(obs={"go": invalid})["coverage"]["go"],
                         "observation_invalid")
        missing_reason = observation(cooldown=True)
        self.assertEqual(self.select(obs={"go": missing_reason})["coverage"]["go"],
                         "observation_invalid")
        bad_window = observation(burn_down_window=[0.0, 50.0])
        self.assertEqual(self.select(obs={"go": bad_window})["coverage"]["go"],
                         "observation_invalid")


class WorkerSeamRegressions(ApplicationPickFixture):
    def test_worker_go_lifetime_and_protocol_denies_are_unchanged(self):
        guard = pick.launch_policy("go-codex", "build", "registered-elsewhere",
                                   task_complexity="C2_COMPLEX_BOUNDED")
        self.assertEqual((guard["allowed"], guard["reason"]),
                         (False, "go_short_capability_only_for_c0_c1"))
        guard = pick.launch_policy("go", "fix_build", "minimax-m2.7")
        self.assertEqual((guard["allowed"], guard["reason"]),
                         (False, "model_protocol_unsupported"))
        guard = pick.launch_policy("go", "build", "model-x",
                                   task_complexity="C2_COMPLEX_BOUNDED")
        self.assertEqual(guard["reason"], "go_short_capability_only_for_c0_c1")

    def test_application_lifetime_is_separate_from_worker_lifetime(self):
        allowed = pick._launch_policy_eval(
            "go-codex", "build", "model-x",
            escalation_reason="application bounded complexity witness",
            doc=self.policy.document, task_complexity="C2_COMPLEX_BOUNDED",
            now=NOW, application=True)
        self.assertEqual(allowed["allowed"], True)
        self.assertEqual(allowed["reason"], "leaf_labor_escalation_recorded")
        unproven = pick._launch_policy_eval(
            "go-codex", "build", "model-x", doc=self.policy.document,
            task_complexity="C2_COMPLEX_BOUNDED", now=NOW, application=True)
        self.assertEqual((unproven["allowed"], unproven["reason"]),
                         (False, "leaf_labor_requires_escalation"))
        registered = pick._launch_policy_eval(
            "go-codex", "mechanical", "fixture-model", doc=self.policy.document,
            task_complexity="C1_ROUTINE_BOUNDED", now=NOW, application=True)
        self.assertEqual((registered["allowed"], registered["reason"]),
                         (True, "registered_cheap_worker_model"))

    def test_worker_order_helpers_keep_exact_outputs(self):
        doc = self.policy.document
        self.assertEqual(pick.execute_order(doc),
                         ["minimax", "glm-flash", "bailian", "grok", "cursor"])
        self.assertEqual(pick.judgment_order(doc),
                         ["glm-5.3", "grok", "cursor", "fable"])
        ok, reason = pick.policy_allows("minimax", "architecture", doc)
        self.assertEqual((ok, reason), (False,
            "minimax refused for architecture: labor tier, never judgment (R20)"))
        ok, reason = pick.policy_allows("go", "mechanical", doc)
        self.assertEqual((ok, reason), (True, "ok"))
        ok, reason = pick.policy_allows("go", "orchestration", doc)
        self.assertEqual((ok, reason), (False,
            "orchestration is seat-only; use domain_orchestration for bounded "
            "subsystem coordination"))
        ok, reason = pick.policy_allows("claude", "orchestration", doc)
        self.assertEqual((ok, reason), (True, "ok"))
        self.assertEqual(pick.next_escalate("minimax", doc, model="MiniMax-M3",
                                            task_class="mechanical"), "glm-flash")
        resolved, suffix = pick._selection_model("glm", "mechanical", doc, now=NOW)
        self.assertEqual((resolved, suffix), ("glm-5.3-flash", ""))
        resolved, suffix = pick._selection_model("glm", "review", doc, now=NOW)
        self.assertEqual(resolved, "glm-5.3")
        self.assertEqual(pick.pool_family("cursor-grok-4.6-high"), "grok")
        self.assertEqual(pick.pool_family("remote-glm-codex"), "glm")
        self.assertEqual(pick.canonical_pool("qwen"), "bailian")

    def test_grok_priority_reads_explicit_clock_only(self):
        doc = policy_document()
        doc["routing"]["grok_expiring_priority"] = {"enabled": True}
        doc["pools"]["grok"]["windows"]["weekly"] = {
            "source": "chairman_provider_screenshot", "remaining_pct": 40,
            "observed_at": "2026-11-04T11:00:00+00:00",
            "reset_at": "2026-11-04T16:00:00+00:00"}
        self.write_policy(doc)
        policy = pick.read_application_policy()
        ok, reason = pick.policy_allows("grok", "mechanical", policy.document,
                                        now=NOW)
        self.assertEqual((ok, reason), (True, "grok_expiring_priority_class"))
        ok, _ = pick.policy_allows("grok", "mechanical", policy.document,
                                   now=NOW + timedelta(hours=6))
        self.assertEqual(ok, True)
        stale_window = policy_document()
        stale_window["routing"]["grok_expiring_priority"] = {"enabled": True}
        stale_window["pools"]["grok"]["windows"]["weekly"] = {
            "source": "chairman_provider_screenshot", "remaining_pct": 40}
        self.write_policy(stale_window)
        policy = pick.read_application_policy()
        ok, reason = pick.policy_allows("grok", "mechanical", policy.document,
                                        now=NOW)
        self.assertEqual((ok, reason), (True, "ok"))
        # An explicit observation window governs burn-down urgency directly;
        # a malformed policy screenshot stays inert under its own policy.
        self.assertEqual(pick.burn_down_urgent("grok", policy.document,
                                               windows={"grok": (1.0, 40.0)}),
                         True)
        self.assertEqual(pick.burn_down_urgent("grok", policy.document), False)


class ApplicationOwnerRepairConstraints(ApplicationPickFixture):
    def test_exact_models_and_routing_tokens_never_downgrade(self):
        for token, pool, model, cheaper, mode in [
            ("glm-5.3", "glm", "glm-5.3", "glm-5.3-flash", "glm"),
            ("bailian-max", "bailian", "qwen3.8-max", "qwen3.8-flash", "qwen"),
        ]:
            with self.subTest(token=token):
                recipes = [recipe(model=value, mode=mode, driver=mode, order_rank=i,
                                  source=pool + "-owner")
                           for i, value in enumerate([cheaper, model])]
                cat = {"schema": pick._APPLICATION_CATALOGUE_SCHEMA,
                       "pool_order": [pool],
                       "pools": {pool: {"enabled": True, "recipes": recipes}}}
                obs = {pool: observation(mode=mode, model_room={cheaper: 4, model: 1})}
                result = self.select(task(requested_model=token), cat=cat, obs=obs)
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["selection"]["model"], model)
                self.assertEqual(result["selection"]["pool"], pool)
                self.assertEqual(result["identity"]["task"]["requested_model"], token)
                cat["pools"][pool]["recipes"] = recipes[:1]
                refused = self.select(task(requested_model=token), cat=cat, obs=obs)
                self.assertFalse(refused["ok"])
                self.assertIsNone(refused["selection"])
                self.assertEqual(refused["coverage"][pool], "requested_model_unqualified")

    def test_issued_policy_deeply_owns_input_and_returned_document(self):
        before = self.select()
        mutated = self.policy.document
        mutated["pools"]["go"]["enabled"] = False
        mutated["pools"]["go"]["task_classes"].clear()
        mutated["pools"]["go"]["default_model"] = "other-model"
        mutated["routing"]["execute_order"][:] = ["grok"]
        mutated["routing"]["acceptance_floor"] = "1.0 over last 1"
        self.assertEqual(self.select(), before)
        self.assertEqual(self.policy.document, policy_document())
        # Constructor ownership is separate from getter ownership.
        original = policy_document()
        issued = pick.ApplicationPolicy(self.policy.path, self.policy.bytes_sha256,
            self.policy.text_sha256, self.policy.parsed_sha256,
            self.policy.critical_sha256, original)
        original["pools"]["go"]["enabled"] = False
        self.assertEqual(self.select(pol=issued), before)

    def test_nondefault_model_quality_is_not_replaced_with_default_quality(self):
        cat = catalogue(**{"go": {"enabled": True, "recipes": [recipe(),
                         recipe(model="other-model", order_rank=1)]}})
        obs = observations(model_room={"fixture-model": 1, "other-model": 1})
        def rejected(model):
            return [{"run_id": "rejected-" + str(i), "pool": "go", "job_class": "mechanical",
                     "model": model, "accepted_by": "reviewer", "review_rejected": True,
                     "ts": i} for i in range(20)]
        alternate_bad = rejected("other-model")
        self.assertTrue(pick.floor_demotes("go", "mechanical", records=alternate_bad,
                                          doc=self.policy.document, model="other-model", now=NOW))
        self.assertFalse(pick.floor_demotes("go", "mechanical", records=alternate_bad,
                                           doc=self.policy.document, now=NOW))
        self.assertFalse(self.select(task(requested_model="other-model"), cat=cat,
                                     obs=obs, quality=alternate_bad)["ok"])
        result = self.select(task(requested_model="other-model"), cat=cat,
                             obs=obs, quality=rejected("fixture-model"))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["selection"]["model"], "other-model")
        # The incumbent worker resolver itself keeps its default behavior.
        self.assertEqual(pick._selection_model("go", "mechanical", self.policy.document,
                                               model="other-model", now=NOW)[0], "fixture-model")

    def test_numeric_cooldown_never_masquerades_as_boolean(self):
        for value in (0, 1, 0.0, 1.0):
            with self.subTest(value=repr(value)):
                result = self.select(obs=observations(cooldown=value))
                self.assertFalse(result["ok"])
                self.assertEqual(result["coverage"]["go"], "observation_invalid")
        self.assertTrue(self.select(obs=observations(cooldown=False))["ok"])
        result = self.select(obs=observations(cooldown=True, cooldown_reason="observed_limit"))
        self.assertEqual(result["coverage"]["go"], "cooldown_active")

    def test_grok_priority_urgency_policy_and_economics_only_use_explicit_observation(self):
        doc = policy_document()
        doc["routing"]["execute_order"] = ["go", "grok"]
        doc["routing"]["grok_expiring_priority"] = {"enabled": True}
        doc["pools"]["grok"]["task_classes"] = ["review"]
        doc["pools"]["grok"]["windows"]["weekly"] = {
            "source": "chairman_provider_screenshot", "remaining_pct": 40,
            "observed_at": (NOW - timedelta(hours=1)).isoformat(),
            "reset_at": (NOW + timedelta(hours=2)).isoformat()}
        self.write_policy(doc)
        policy = pick.read_application_policy()
        cat = catalogue(grok={"enabled": True, "recipes": [recipe(model="grok-4.7",
            mode="grok", driver="grok", protocol="harness", source="grok-owner")]})
        cat["pool_order"] = ["go", "grok"]
        for exhausted, expected_pool in [(False, "grok"), (True, "go"), (None, "go")]:
            with self.subTest(exhausted=exhausted), patch.object(pick, "_grok_exhausted",
                    side_effect=AssertionError("ambient exhaustion read")):
                grok = observation(mode="grok", model_room={"grok-4.7": 1},
                                   burn_down_window=[2.0, 40.0])
                if exhausted is not None: grok["grok_exhausted"] = exhausted
                result = self.select(task(escalation_reason=""), pol=policy, cat=cat,
                                     obs=observations(grok=grok))
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["selection"]["pool"], expected_pool)
        with patch.object(pick, "_grok_exhausted", side_effect=AssertionError("ambient exhaustion read")):
            self.assertEqual(self.select(pol=policy, cat=cat)["selection"]["pool"], "go")
            doc["pools"]["grok"]["task_classes"].append("mechanical")
            guard = pick._launch_policy_eval("cursor", "mechanical", "cursor-grok-4.6-high",
                doc=doc, now=NOW, application=True, grok_exhausted=True,
                escalation_reason="fixture explicit economic witness")
            self.assertTrue(guard["allowed"], guard)
            self.assertTrue(pick.policy_allows("cursor", "mechanical", doc,
                model="cursor-grok-4.6-high", now=NOW, grok_exhausted=True)[0])

    def test_worker_default_still_observes_its_incumbent_exhaustion_source(self):
        doc = policy_document()
        doc["routing"]["grok_expiring_priority"] = {"enabled": True}
        doc["pools"]["grok"]["windows"]["weekly"] = {
            "source": "chairman_provider_screenshot", "remaining_pct": 40,
            "observed_at": (NOW - timedelta(hours=1)).isoformat(),
            "reset_at": (NOW + timedelta(hours=2)).isoformat()}
        with patch.object(pick, "_grok_exhausted", return_value=False) as observed:
            self.assertTrue(pick._grok_priority_active(doc, "mechanical", now=NOW))
            observed.assert_called_once_with()

    def test_clock_normalizes_once_for_active_promo_and_daily_windows(self):
        doc = policy_document()
        doc["routing"]["glm_peak_window"] = {"tz": "UTC", "start": "10:00", "end": "14:00"}
        doc["routing"]["glm_flash_campaign"] = {"tz": "UTC", "start": "10:00", "end": "14:00",
            "ends_at": (NOW + timedelta(hours=2)).isoformat()}
        doc["routing"]["glm_credit_promo"] = {
            "starts_at": (NOW - timedelta(hours=1)).isoformat(),
            "ends_at": (NOW + timedelta(hours=1)).isoformat(),
            "models": ["glm-5.3-flash"], "balance_pools": ["go", "bailian"],
            "credit_multiplier": 0.5, "target_share": 0.5}
        self.write_policy(doc)
        policy = pick.read_application_policy()
        glm_recipe = recipe(model="glm-5.3-flash", mode="glm", driver="glm", source="glm-owner")
        cat = catalogue(glm={"enabled": True, "recipes": [glm_recipe]})
        obs = observations(glm=observation(mode="glm", model_room={"glm-5.3-flash": 1}))
        result = self.select(pol=policy, cat=cat, obs=obs)
        self.assertTrue(result["ok"], result)
        for clock in (NOW_EPOCH, int(NOW_EPOCH), NOW.astimezone(timezone(timedelta(hours=5)))):
            with self.subTest(clock=str(clock)):
                self.assertEqual(self.select(pol=policy, cat=cat, obs=obs, now=clock), result)

    def test_invalid_or_unrepresentable_clock_and_numeric_observation_refuse_typed(self):
        for clock in (0, -1, True, False, float("inf"), float("nan"), 1e30, 10**400,
                      datetime(2026, 11, 4), "2026-11-04T12:00:00Z"):
            with self.subTest(clock=repr(clock)):
                self.assertEqual(self.select(now=clock)["reason"], "now_unqualified")
        for values in ({"observed_at": 10**400}, {"fresh_s": 10**400},
                       {"burn_down_window": [10**400, 30]}):
            with self.subTest(values=str(values)):
                self.assertEqual(self.select(obs=observations(**values))["coverage"]["go"],
                                 "observation_invalid")


if __name__ == "__main__":
    unittest.main()
