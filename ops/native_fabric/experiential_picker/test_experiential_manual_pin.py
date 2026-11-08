"""Offline, no-provider-effect regression for the manual-only Experiential route.

pool=experiential + model=glm-5.3-uncensored (case-sensitive) is manual-only
with owner-verified witnesses; automatic routing never promotes the pool and
nothing substitutes Z.AI glm or glm-5.3-flash for the exact pin. Nothing here
starts a worker, lease, key, spend or publication: every module under test is
executed in memory from the sealed bytes inside a private temporary kit root.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ROUTE_PATH = HERE / "experiential_manual_route.py"
QUALIFIER_PATH = HERE / "qualify_experiential_current.py"

_rspec = importlib.util.spec_from_file_location("experiential_manual_route_tests", ROUTE_PATH)
route = importlib.util.module_from_spec(_rspec)
assert _rspec.loader is not None
_rspec.loader.exec_module(route)

_qspec = importlib.util.spec_from_file_location("experiential_qualifier_tests", QUALIFIER_PATH)
qualifier = importlib.util.module_from_spec(_qspec)
assert _qspec.loader is not None
_qspec.loader.exec_module(qualifier)

PREIMAGES = json.loads((REPO / "ops/native_fabric/quota_continuity/rollout/"
                        "native-preimages.json").read_text())["files"]

POLICY = {
    "pools": {
        # Registered only inside this fixture to prove the owner-registration
        # dependency; no repo or host pool configuration is touched.
        "experiential": {
            "role": ["operator", "reviewer", "executor"],
            "task_classes": ["mechanical", "fix_build", "review", "audit", "verify", "design",
                             "architecture", "decompose", "adjudicate",
                             "high_level"],
            "default_model": "glm-5.3-uncensored",
            "caps": {"concurrent": 1},
        },
        "glm": {
            "task_classes": ["review", "audit", "verify", "high_level",
                             "fix_build", "build"],
            "models": {"reviewer": "glm-5.3", "operator": "glm-5.3",
                       "executor": "glm-5.3-flash"},
        },
    },
    "routing": {
        "execute_order": ["minimax", "glm-flash", "bailian", "grok"],
        "judgment_order": ["glm-5.3", "grok", "cursor", "fable"],
        "escalation_ladder": ["minimax", "glm-flash", "glm-5.3", "bailian",
                              "grok", "cursor", "claude"],
        "reviewer_not_author": True,
    },
}
ADVERSARIAL_POLICY = json.loads(json.dumps(POLICY))
ADVERSARIAL_POLICY["routing"]["execute_order"] = ["experiential"] + POLICY["routing"]["execute_order"]
ADVERSARIAL_POLICY["routing"]["judgment_order"] = ["experiential"] + POLICY["routing"]["judgment_order"]
BASELINE_POLICY = json.loads(json.dumps(POLICY))

WITNESS_FIELDS = ("entitlement_verified_by_owner", "local_gateway_healthy",
                  "transport_admitted", "cap_authenticated",
                  "provider_retains_data_disclosed", "platform_funded_only")
CONSENT_FIELDS = route.WITNESS_CONSENT_FIELDS


def witness_document(**overrides) -> dict:
    doc = {
        "schema": route.WITNESS_SCHEMA,
        "pool": "experiential",
        "model": "glm-5.3-uncensored",
        "account": "B",
        "witnessed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "witness_ttl_minutes": 60,
    }
    doc.update({field: True for field in WITNESS_FIELDS})
    doc["consent"] = {name: True for name in CONSENT_FIELDS}
    for key, value in overrides.items():
        if key == "consent_replace":
            doc["consent"] = value
        elif key == "consent" and isinstance(value, dict):
            doc["consent"].update(value)
        else:
            doc[key] = value
    return doc


class _Kit:
    """Private temporary kit root with the overlaid (or sealed) picker."""

    def __init__(self, transformed: bool, policy: dict, witness: dict | None,
                 witness_symlink: bool = False, unregister_pool: bool = False):
        self._tmp = tempfile.TemporaryDirectory(prefix="experiential-pin-")
        root = Path(self._tmp.name).resolve()
        (root / "ext").mkdir()
        (root / "orch" / "fabric").mkdir(parents=True)
        raw = route.snapshot_picker("candidate")
        if transformed:
            raw = route.apply_reviewed_hunks(raw, snapshots=("candidate",))
        (root / "ext" / "pick.py").write_bytes(raw)
        tier = PREIMAGES["model_tier.py"]
        tier_bytes = (REPO / "ops/native_fabric/quota_continuity/source/model_tier.py").read_bytes()
        if tier and tier != __import__("hashlib").sha256(tier_bytes).hexdigest():
            raise ValueError("model_tier_preimage_drift")
        (root / "ext" / "model_tier.py").write_bytes(tier_bytes)
        if unregister_pool:
            policy = json.loads(json.dumps(policy))
            policy["pools"].pop("experiential", None)
        (root / "orch" / "fabric" / "pools.yaml").write_text(
            "# synthetic fixture policy; never installed\n")
        self.policy = policy
        if witness is not None:
            target = root / "orch" / "fabric" / "witness-real.json"
            target.write_text(json.dumps(witness))
            link = root / "orch" / "fabric" / "experiential_witnesses.json"
            if witness_symlink:
                link.symlink_to(target)
            else:
                link.write_text(json.dumps(witness))
        sys.path.insert(0, str(root / "ext"))
        spec = importlib.util.spec_from_file_location(
            "experiential_pick_" + os.urandom(6).hex(), root / "ext" / "pick.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.module = module
        self.root = root

    def write_witness(self, witness: dict | None) -> None:
        link = self.root / "orch" / "fabric" / "experiential_witnesses.json"
        if witness is None:
            link.unlink(missing_ok=True)
        else:
            link.write_text(json.dumps(witness))

    def close(self) -> None:
        sys.path.remove(str(self.root / "ext"))
        self._tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


GATES = dict(floor_demotes=False, hard_filter=(True, "admitted"),
             _grok_exhausted=False, _glm_meter_state="")


class SealedPreimageEnforcement(unittest.TestCase):
    def test_stale_and_foreign_preimages_refuse(self):
        sealed = route.snapshot_picker("candidate")
        stale = route.snapshot_picker("source")
        with self.assertRaisesRegex(ValueError, "sealed_picker_preimage_changed"):
            route.patched(stale, route.CURRENT_GENERATION)
        with self.assertRaisesRegex(ValueError, "sealed_picker_preimage_changed"):
            route.patched(b"arbitrary source containing an experiential marker",
                          route.CURRENT_GENERATION)
        with self.assertRaisesRegex(ValueError, "sealed_picker_preimage_changed"):
            route.patched(sealed, "0" * 64)
        older = next(gen for gen in route.SEALED_PREDECESSORS
                     if gen != route.CURRENT_GENERATION)
        with self.assertRaisesRegex(ValueError, "sealed_picker_preimage_changed"):
            route.patched(sealed, older)

    def test_snapshot_seals_and_current_generation_are_preserved(self):
        for name in route.SNAPSHOT_PICKER_SEALS:
            raw = route.snapshot_picker(name)  # raises on drift
            self.assertEqual(route.sha(raw),
                             route.SNAPSHOT_PICKER_SEALS[name][1], name)
        self.assertEqual(route.SNAPSHOT_PICKER_SEALS["candidate"][1],
                         route.SEALED_PREDECESSORS[route.CURRENT_GENERATION])

    def test_source_manifest_preimages_still_seal_the_lineage(self):
        self.assertEqual(PREIMAGES["pick.py"],
                         route.SNAPSHOT_PICKER_SEALS["source"][1])
        self.assertEqual(PREIMAGES["model_tier.py"],
                         route.sha((REPO / "ops/native_fabric/quota_continuity/"
                                    "source/model_tier.py").read_bytes()))
        self.assertEqual(PREIMAGES["fabric_task.py"],
                         route.sha((REPO / "ops/native_fabric/quota_continuity/"
                                    "source/fabric_task.py").read_bytes()))

    def test_transform_is_in_memory_only_and_deterministic(self):
        before = {name: route.snapshot_picker(name)
                  for name in route.SNAPSHOT_PICKER_SEALS}
        outputs = {name: route.apply_reviewed_hunks(raw, snapshots=(name,))
                   for name, raw in before.items()}
        again = {name: route.apply_reviewed_hunks(raw, snapshots=(name,))
                 for name, raw in before.items()}
        self.assertEqual(outputs, again)
        for name, raw in before.items():
            self.assertEqual(route.snapshot_picker(name), raw, name)

    def test_added_block_carries_no_environ_or_key_path(self):
        block = route._EXPERIENTIAL_BLOCK.encode("utf-8")
        lowered = block.lower()
        for marker in (b"environ", b"getenv", b"api_key", b"apikey", b"token"):
            self.assertNotIn(marker, lowered, marker)


class RouteAdmission(unittest.TestCase):
    def pick_line(self, kit: _Kit, task_class="mechanical", pool="experiential",
                  model="glm-5.3-uncensored", **extra):
        pick = kit.module
        with patch.object(pick, "load_pools", return_value=kit.policy), \
             patch.object(pick, "floor_demotes", return_value=GATES["floor_demotes"]), \
             patch.object(pick, "hard_filter", return_value=GATES["hard_filter"]), \
             patch.object(pick, "_grok_exhausted", return_value=False), \
             patch.object(pick, "_glm_meter_state", return_value=""):
            return pick.format_pick(task_class, pool=pool,
                                    requested_model=model, **extra)

    def test_exact_pinned_synthetic_route_admits_with_witnesses(self):
        with _Kit(True, POLICY, witness_document()) as kit:
            line = self.pick_line(kit)
            self.assertTrue(line.startswith(
                "POOL=experiential KEY=- MODEL=glm-5.3-uncensored"), line)
            self.assertNotIn("ESCALATE_TO=experiential", line)
            # Economic guard consumed the same witnesses at emission.
            guard = kit.module.launch_policy(
                "experiential", "mechanical", "glm-5.3-uncensored", doc=kit.policy)
            self.assertTrue(guard["allowed"], guard)
            self.assertEqual(guard["reason"], "experiential_manual_witnessed")

    def test_strict_recheck_witnesses_are_read_fresh_every_call(self):
        with _Kit(True, POLICY, witness_document()) as kit:
            self.assertTrue(self.pick_line(kit).startswith("POOL=experiential"))
            expired = witness_document(
                witnessed_at="2020-01-01T00:00:00+00:00")
            kit.write_witness(expired)
            line = self.pick_line(kit)
            self.assertTrue(line.startswith("NONE reason="), line)
            self.assertIn("witnesses unavailable or stale", line)
            # Restoring the witness restores admission: the recheck is
            # stateless and observes the file, not a cached verdict.
            kit.write_witness(witness_document())
            self.assertTrue(self.pick_line(kit).startswith("POOL=experiential"))

    def test_mode_slug_is_distinct_from_glm(self):
        observed = []
        real_launch = None
        with _Kit(True, POLICY, witness_document()) as kit:
            pick = kit.module
            real_launch = pick.launch_policy

            def spy(mode, task_class, model, **options):
                observed.append(mode)
                return real_launch(mode, task_class, model, **options)

            with patch.object(pick, "load_pools", return_value=kit.policy), \
                 patch.object(pick, "floor_demotes", return_value=False), \
                 patch.object(pick, "hard_filter", return_value=(True, "admitted")), \
                 patch.object(pick, "_grok_exhausted", return_value=False), \
                 patch.object(pick, "_glm_meter_state", return_value=""), \
                 patch.object(pick, "launch_policy", side_effect=spy):
                line = pick.format_pick("mechanical", pool="experiential",
                                        requested_model="glm-5.3-uncensored")
            self.assertTrue(line.startswith("POOL=experiential"), line)
            self.assertNotEqual(observed, [])
            self.assertNotIn(observed[0], ("glm", "glm-codex", "qwen", "grok"))
            self.assertEqual(observed[0], "experiential")

    def test_fail_closed_without_witnesses_before_any_launch(self):
        with _Kit(True, POLICY, witness=None) as kit:
            line = self.pick_line(kit)
            self.assertTrue(line.startswith("NONE reason="), line)
            self.assertIn("witnesses unavailable or stale", line)
            guard = kit.module.launch_policy(
                "experiential", "mechanical", "glm-5.3-uncensored", doc=kit.policy)
            self.assertFalse(guard["allowed"])
            self.assertEqual(guard["reason"],
                             "experiential_owner_witnesses_unavailable")

    def test_each_missing_owner_witness_denies(self):
        for field in WITNESS_FIELDS:
            with _Kit(True, POLICY, witness_document(**{field: False})) as kit:
                line = self.pick_line(kit)
                self.assertTrue(line.startswith("NONE reason="), (field, line))
        for consent in CONSENT_FIELDS:
            with _Kit(True, POLICY, witness_document(consent={consent: False})) as kit:
                line = self.pick_line(kit)
                self.assertTrue(line.startswith("NONE reason="), (consent, line))

    def test_unknown_account_or_contract_witnesses_denied(self):
        cases = [
            {"schema": "someone.else.v9"},
            {"pool": "glm"},
            {"model": "glm-5.3"},
            {"witness_ttl_minutes": 0},
            {"witness_ttl_minutes": 100000},
            {"witnessed_at": "not-a-timestamp"},
            {"witnessed_at": "2100-01-01T00:00:00+00:00"},
            {"consent": None},
            {"consent_replace": {}},
            {"consent_replace": {"retention_opt_in": True}},
        ]
        for override in cases:
            with _Kit(True, POLICY, witness_document(**override)) as kit:
                line = self.pick_line(kit)
                self.assertTrue(line.startswith("NONE reason="), (override, line))
        with _Kit(True, POLICY, witness=None) as kit:
            witness_path = kit.root / "orch" / "fabric" / "experiential_witnesses.json"
            witness_path.write_bytes(b"{not json")
            self.assertTrue(self.pick_line(kit).startswith("NONE reason="))
            witness_path.write_bytes(b"[]")
            self.assertTrue(self.pick_line(kit).startswith("NONE reason="))

    def test_symlinked_witness_file_fails_closed(self):
        with _Kit(True, POLICY, witness_document(), witness_symlink=True) as kit:
            line = self.pick_line(kit)
            self.assertTrue(line.startswith("NONE reason="), line)


class IdentityDiscipline(unittest.TestCase):
    def pick_line(self, kit: _Kit, pool, model, task_class="mechanical"):
        pick = kit.module
        with patch.object(pick, "load_pools", return_value=kit.policy), \
             patch.object(pick, "floor_demotes", return_value=False), \
             patch.object(pick, "hard_filter", return_value=(True, "admitted")), \
             patch.object(pick, "_grok_exhausted", return_value=False), \
             patch.object(pick, "_glm_meter_state", return_value=""):
            return pick.format_pick(task_class, pool=pool,
                                    requested_model=model)

    def test_model_pin_is_case_sensitive_and_exact(self):
        with _Kit(True, POLICY, witness_document()) as kit:
            for wrong in ("GLM-5.3-Uncensored", "glm-5.3-uncensored ",
                          " glm-5.3-uncensored", "glm-5.3-uncens0red",
                          "glm-5.3", "glm-5.3-flash", "zai-glm-5.3-uncensored"):
                line = self.pick_line(kit, "experiential", wrong)
                self.assertTrue(line.startswith("NONE reason="), (wrong, line))
                self.assertIn("requires exact glm-5.3-uncensored pin", line)

    def test_pool_pin_requires_the_exact_model(self):
        with _Kit(True, POLICY, witness_document()) as kit:
            for model in (None, "glm-5.3", "glm-5.3-flash"):
                line = self.pick_line(kit, "experiential", model)
                self.assertTrue(line.startswith("NONE reason="), line)
                self.assertIn("requires exact glm-5.3-uncensored pin", line)

    def test_model_pin_requires_the_experiential_pool(self):
        with _Kit(True, POLICY, witness_document()) as kit:
            for pool in ("glm", "grok", None, "AUTO"):
                line = self.pick_line(kit, pool, "glm-5.3-uncensored")
                self.assertTrue(line.startswith("NONE reason="), (pool, line))
                self.assertIn("requires experiential pool", line)

    def test_unregistered_pool_stays_fail_closed(self):
        with _Kit(True, POLICY, witness_document(), unregister_pool=True) as kit:
            line = self.pick_line(kit, "experiential", "glm-5.3-uncensored")
            self.assertTrue(line.startswith("NONE reason="), line)
            self.assertIn("unknown forced pool", line)

    def test_manual_pin_admits_only_the_web_and_native_approved_labor_classes(self):
        with _Kit(True, POLICY, witness_document()) as kit:
            for admitted in ("mechanical", "fix_build"):
                line = self.pick_line(kit, "experiential",
                                      "glm-5.3-uncensored", task_class=admitted)
                self.assertTrue(line.startswith("POOL=experiential"), (admitted, line))
            for refused in ("review", "audit", "verify", "executor", "census", "extract", "architecture"):
                line = self.pick_line(kit, "experiential",
                                      "glm-5.3-uncensored", task_class=refused)
                self.assertTrue(line.startswith("NONE reason="), (refused, line))
                self.assertIn("only admits mechanical/fix_build", line)

    def test_no_fallback_to_glm_when_route_unavailable(self):
        with _Kit(True, POLICY, witness=None) as kit:
            pick = kit.module
            with patch.object(pick, "load_pools", return_value=kit.policy), \
                 patch.object(pick, "_glm_meter_state", return_value=""):
                line = pick.format_pick("mechanical", pool="experiential",
                                        requested_model="glm-5.3-uncensored")
            self.assertTrue(line.startswith("NONE reason="), line)
            self.assertNotIn("MODEL=glm-5.3-flash", line)
            self.assertNotIn("POOL=glm", line)


class AutomaticRoutingUnchanged(unittest.TestCase):
    def auto_line(self, kit: _Kit, policy: dict, task_class="review"):
        pick = kit.module
        with patch.object(pick, "load_pools", return_value=policy), \
             patch.object(pick, "floor_demotes", return_value=False), \
             patch.object(pick, "hard_filter", return_value=(True, "admitted")), \
             patch.object(pick, "_grok_exhausted", return_value=False), \
             patch.object(pick, "_glm_meter_state", return_value=""):
            return pick.format_pick(task_class)

    def test_auto_never_promotes_experiential_even_when_config_lists_it(self):
        with _Kit(True, ADVERSARIAL_POLICY, witness_document()) as kit:
            for task_class in ("review", "audit", "fix_build"):
                line = self.auto_line(kit, ADVERSARIAL_POLICY, task_class)
                self.assertTrue(line.startswith("POOL="), line)
                self.assertNotIn("POOL=experiential", line)

    def test_auto_output_equals_baseline_without_the_pool(self):
        with _Kit(True, ADVERSARIAL_POLICY, witness_document()) as overlaid, \
             _Kit(False, BASELINE_POLICY, witness_document()) as baseline:
            for task_class in ("review", "audit", "fix_build"):
                guarded = self.auto_line(overlaid, ADVERSARIAL_POLICY, task_class)
                original = self.auto_line(baseline, BASELINE_POLICY, task_class)
                self.assertEqual(guarded, original, task_class)

    def test_implicit_policy_admission_is_removed(self):
        with _Kit(True, POLICY, witness_document()) as kit, \
             _Kit(False, POLICY, witness_document()) as baseline:
            implicit, reason = kit.module.policy_allows(
                "experiential", "review", POLICY)
            self.assertFalse(implicit, reason)
            self.assertIn("requires exact glm-5.3-uncensored pin", reason)
            legacy, _legacy_reason = baseline.module.policy_allows(
                "experiential", "review", POLICY)
            self.assertTrue(legacy)

    def test_escalation_ladder_cannot_reach_the_route(self):
        ladder = ADVERSARIAL_POLICY["routing"]["escalation_ladder"] + ["experiential"]
        adversarial = json.loads(json.dumps(ADVERSARIAL_POLICY))
        adversarial["routing"]["escalation_ladder"] = ladder
        with _Kit(True, adversarial, witness_document()) as kit:
            pick = kit.module
            with patch.object(pick, "load_pools", return_value=adversarial), \
                 patch.object(pick, "_grok_exhausted", return_value=False):
                token = pick.next_escalate("grok", adversarial,
                                           task_class="review")
            self.assertNotIn("experiential", token)


class SubjectRoleIndependence(unittest.TestCase):
    def test_experiential_folds_to_glm_family_for_r33(self):
        with _Kit(True, POLICY, witness_document()) as kit:
            self.assertEqual(kit.module.pool_family("experiential"), "glm")
            self.assertEqual(kit.module.canonical_pool("experiential"),
                             "experiential")

    def test_experiential_never_reviews_glm_authored_work(self):
        with _Kit(True, POLICY, witness_document()) as kit:
            pick = kit.module
            ok, reason = pick._subject_ok("experiential", "review", "glm",
                                          POLICY)
            self.assertFalse(ok, reason)
            ok, reason = pick._subject_ok("glm", "review", "experiential",
                                          POLICY)
            self.assertFalse(ok, reason)
            ok, reason = pick._subject_ok("experiential", "review", "grok",
                                          POLICY)
            self.assertTrue(ok, reason)


class LaunchEconomicGuard(unittest.TestCase):
    def test_other_models_on_experiential_mode_are_refused(self):
        with _Kit(True, POLICY, witness_document()) as kit:
            for model in ("glm-5.3-flash", "glm-5.3", ""):
                guard = kit.module.launch_policy(
                    "experiential", "review", model, doc=POLICY)
                self.assertFalse(guard["allowed"], (model, guard))
                self.assertEqual(guard["reason"],
                                 "experiential_route_requires_exact_pin")

    def test_glm_mode_never_silently_serves_the_uncensored_model(self):
        with _Kit(True, POLICY, witness_document()) as kit:
            pick = kit.module
            # The pool admission path, not the economic guard, owns model
            # identity on glm: the uncensored model is not a glm pool model.
            with patch.object(pick, "load_pools", return_value=POLICY), \
                 patch.object(pick, "_glm_meter_state", return_value=""):
                line = pick.format_pick("review", pool="glm",
                                        requested_model="glm-5.3-uncensored")
            self.assertTrue(line.startswith("NONE reason="), line)
            self.assertNotIn("MODEL=glm-5.3-uncensored", line)
            # The economic guard keeps treating glm-mode judgment classes by
            # existing law only; it never emits the experiential witness.
            guard = pick.launch_policy("glm", "review", "glm-5.3-uncensored",
                                       doc=POLICY)
            self.assertNotEqual(guard.get("reason"),
                                "experiential_manual_witnessed")


class OverlayComposition(unittest.TestCase):
    PARTNER = '''def apply_reviewed_hunks(raw):
    text = raw.decode("utf-8")
    old = 'def _now_sh() -> datetime:\\n'
    new = '# partner reviewed comment (synthetic composition fixture)\\ndef _now_sh() -> datetime:\\n'
    if text.count(old) != 1 or text.count(new) != 0:
        raise ValueError("partner_hunk_identity_mismatch")
    return text.replace(old, new, 1).encode("utf-8")
'''

    def test_hunk_regions_are_pairwise_disjoint_on_sealed_preimage(self):
        text = route.snapshot_picker("candidate").decode("utf-8")
        ranges = []
        for name, _targets, old, _new in route.HUNKS:
            start = text.find(old)
            self.assertGreaterEqual(start, 0, name)
            self.assertEqual(text.count(old), 1, name)
            ranges.append((start, start + len(old), name))
        for i, (a_start, a_end, a_name) in enumerate(ranges):
            for b_start, b_end, b_name in ranges[i + 1:]:
                self.assertTrue(a_end <= b_start or b_end <= a_start,
                                (a_name, b_name))

    def test_both_composition_orders_with_a_sibling_overlay(self):
        sealed = route.snapshot_picker("candidate")
        with tempfile.TemporaryDirectory() as raw:
            partner_path = Path(raw) / "partner_qualifier.py"
            partner_path.write_text(self.PARTNER)
            composed = qualifier.compose_with_partner(sealed, partner_path)
        self.assertEqual(composed["compose_theirs_first"], "PASS")
        self.assertEqual(composed["compose_ours_first"], "PASS")
        self.assertEqual(route.sha(route.apply_reviewed_hunks(sealed)),
                         route.sha(route.apply_reviewed_hunks(sealed)))
        self.assertIn("composed_pick_sha256", composed)

    def test_qualification_runs_source_only_end_to_end(self):
        result = qualifier.run(None, None, None, None)
        self.assertEqual(result["state"], "QUALIFIED_SOURCE_ONLY_NOT_INSTALLED")
        self.assertEqual(result["changed_files"], ["ext/pick.py"])
        self.assertEqual(result["scratch_stale_CAS_refusal"], "PASS")
        self.assertFalse(result["witness_gate"]["witnesses_present"])
        self.assertEqual(result["witness_gate"]["expected_route_state"],
                         "FAIL_CLOSED_BEFORE_ANY_WORKER_LAUNCH")

    def test_qualification_lints_a_draft_witness_without_installing(self):
        with tempfile.TemporaryDirectory() as raw:
            draft = Path(raw) / "draft.json"
            draft.write_text(json.dumps(witness_document()))
            result = qualifier.run(None, None, None, draft)
        self.assertTrue(result["witness_gate"]["witnesses_present"])
        self.assertEqual(result["witness_gate"]["draft_verdict"],
                         "experiential_manual_witnessed")

    def test_no_repo_file_outside_the_child_directory_is_written(self):
        tracked = {}
        for name in route.SNAPSHOT_PICKER_SEALS:
            path = REPO / route.SNAPSHOT_PICKER_SEALS[name][0]
            tracked[str(path)] = path.read_bytes()
        qualifier.run(None, None, None, None)
        for path, expected in tracked.items():
            self.assertEqual(Path(path).read_bytes(), expected, path)


if __name__ == "__main__":
    unittest.main()
