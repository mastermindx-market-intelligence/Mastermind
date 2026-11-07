"""Hermetic qualification of exact Ubuntu0/3 native picker forward-port."""
from __future__ import annotations
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import types
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("manual_linux_current", HERE / "qualify_linux_installed_picker.py")
q = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(q)
PREIMAGE = HERE / "fixtures" / "linux_ubuntu03_pick_preimage.py.txt"
POLICY = {
    "pools": {
        "experiential": {
            "role": ["executor"],
            "task_classes": ["mechanical", "fix_build"],
            "default_model": "glm-5.3-uncensored",
        },
        "glm": {"task_classes": ["review", "mechanical", "fix_build"],
                "models": {"executor": "glm-5.3-flash", "operator": "glm-5.3"}},
        "bailian": {"task_classes": ["mechanical", "fix_build", "review"]},
    },
    "routing": {
        "execute_order": ["minimax", "glm-flash", "bailian"],
        "judgment_order": ["glm-5.3", "grok", "cursor"],
        "reviewer_not_author": True,
    },
}


def witness(**override):
    d = {
        "schema": q.route.WITNESS_SCHEMA,
        "pool": "experiential", "model": "glm-5.3-uncensored",
        "entitlement_verified_by_owner": True, "local_gateway_healthy": True,
        "transport_admitted": True, "cap_authenticated": True,
        "provider_retains_data_disclosed": True, "platform_funded_only": True,
        "consent": {field: True for field in q.route.WITNESS_CONSENT_FIELDS},
        "witnessed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "witness_ttl_minutes": 60, "account": "B",
    }
    d.update(override)
    return d


class Kit:
    def __init__(self, transformed: bool, doc=POLICY, witness_document=None):
        self.t = tempfile.TemporaryDirectory(prefix="experiential-linux-picker-")
        self.root = Path(self.t.name)
        self.ext = self.root / "ext"
        self.ext.mkdir()
        (self.root / "orch" / "fabric").mkdir(parents=True)
        self.witness_file = self.root / "orch" / "fabric" / "experiential_witnesses.json"
        if witness_document is not None:
            self.witness_file.write_text(json.dumps(witness_document))
        raw = PREIMAGE.read_bytes()
        (self.ext / "pick.py").write_bytes(q.forward_port(raw) if transformed else raw)
        self.original = raw
        self.doc = doc
        # No imported real host state, credentials or remote service.
        self.previous_tier = sys.modules.get("model_tier")
        tier = types.ModuleType("model_tier")
        tier.CLASS_TIER = {"mechanical": "cheap", "fix_build": "standard"}
        sys.modules["model_tier"] = tier
        sys.path.insert(0, str(self.ext))
        sp = importlib.util.spec_from_file_location("pick_under_test", self.ext / "pick.py")
        self.module = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(self.module)

    def line(self, task="mechanical", pool="experiential",
             model="glm-5.3-uncensored", **more):
        with patch.object(self.module, "load_pools", return_value=self.doc), \
             patch.object(self.module, "hard_filter", return_value=(True, "eligible")), \
             patch.object(self.module, "floor_demotes", return_value=False), \
             patch.object(self.module, "_glm_meter_state", return_value=""):
            return self.module.format_pick(task, pool=pool,
                                            requested_model=model, **more)

    def write_witness(self, value):
        if value is None:
            self.witness_file.unlink(missing_ok=True)
        else:
            self.witness_file.write_text(json.dumps(value))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        sys.path.remove(str(self.ext))
        if self.previous_tier is None:
            sys.modules.pop("model_tier", None)
        else:
            sys.modules["model_tier"] = self.previous_tier
        self.t.cleanup()


class Snapshot(unittest.TestCase):
    def test_exact_real_preimage_seal(self):
        self.assertEqual(q.sha(PREIMAGE.read_bytes()), q.OBSERVED_LINUX_PICKER)

    def test_original_source_never_modified(self):
        with Kit(True, witness_document=witness()) as kit:
            result = (kit.ext / "pick.py").read_bytes()
            self.assertNotEqual(q.sha(result), q.sha(kit.original))
            self.assertEqual(q.sha(kit.original), q.OBSERVED_LINUX_PICKER)

    def test_stale_or_random_source_refused(self):
        for source in (b"foreign\n", q.route.snapshot_picker("candidate")):
            with self.assertRaisesRegex(ValueError, "installed_picker_preimage_changed"):
                q.forward_port(source)

    def test_deterministic_exact_forwardport(self):
        raw = PREIMAGE.read_bytes()
        self.assertEqual(q.forward_port(raw), q.forward_port(raw))
        self.assertEqual(q.sha(q.forward_port(raw)),
                         "414e4fc73e865480ea19a52ea96207c400eb9b599fbece28a7063d6de30dfa30")


class ExactManualPin(unittest.TestCase):
    def test_positive_mechanical_and_fix_build_with_owner_witness(self):
        with Kit(True, witness_document=witness()) as kit:
            for task in ("mechanical", "fix_build"):
                line = kit.line(task=task)
                self.assertTrue(line.startswith("POOL=experiential "), (task, line))
                self.assertIn("MODEL=glm-5.3-uncensored", line)
                self.assertNotIn("ESCALATE_TO=experiential", line)

    def test_unqualified_witness_no_selection(self):
        with Kit(True, witness_document=None) as kit:
            self.assertIn("witness", kit.line().lower())

    def test_expired_and_future_dated_witnesses_refused(self):
        with Kit(True, witness_document=witness()) as kit:
            for stamp in ("2020-01-01T00:00:00Z",
                          "2100-01-01T00:00:00Z"):
                kit.write_witness(witness(witnessed_at=stamp))
                self.assertTrue(kit.line().startswith("NONE reason="), stamp)

    def test_no_judgment_or_other_labor_task(self):
        with Kit(True, witness_document=witness()) as kit:
            for task in ("review", "audit", "verify", "architecture", "executor", "census"):
                self.assertTrue(kit.line(task=task).startswith("NONE reason="), task)

    def test_case_sensitive_model_and_pool(self):
        with Kit(True, witness_document=witness()) as kit:
            cases = [
                ("experiential", "GLM-5.3-Uncensored"),
                ("experiential", "glm-5.3-uncensored "),
                ("EXPERIENTIAL", "glm-5.3-uncensored"),
                ("glm", "glm-5.3-uncensored"),
                (None, "glm-5.3-uncensored"),
                ("experiential", "glm-5.3-flash"),
                ("experiential", None),
            ]
            for pool, model in cases:
                self.assertTrue(kit.line(pool=pool, model=model).startswith("NONE reason="),
                                (pool, model))

    def test_implicit_experiential_policy_never_true(self):
        with Kit(True, witness_document=witness()) as kit:
            allowed, reason = kit.module.policy_allows("experiential", "mechanical", kit.doc)
            self.assertFalse(allowed, reason)

    def test_economic_guard_direct_call_never_unqualified(self):
        with Kit(True, witness_document=witness()) as kit:
            for model in ("GLM-5.3-Uncensored", "glm-5.3-flash", ""):
                guard = kit.module.launch_policy("experiential", "mechanical",
                                                  model, doc=kit.doc)
                self.assertFalse(guard["allowed"], model)
            self.assertTrue(kit.module.launch_policy("experiential", "mechanical",
                                                      "glm-5.3-uncensored",
                                                      doc=kit.doc)["allowed"])
            kit.write_witness(None)
            self.assertFalse(kit.module.launch_policy("experiential", "mechanical",
                                                       "glm-5.3-uncensored",doc=kit.doc)["allowed"])

    def test_glm_reviewer_family_fold(self):
        with Kit(True, witness_document=witness()) as kit:
            self.assertEqual(kit.module.pool_family("experiential"), "glm")
            self.assertFalse(kit.module._subject_ok("experiential","review","glm",kit.doc)[0])

    def test_never_escalation_origin(self):
        with Kit(True, witness_document=witness()) as kit:
            self.assertEqual(kit.module.next_escalate("experiential", kit.doc,
                                                       "glm-5.3-uncensored","mechanical"), "")


class AutoParity(unittest.TestCase):
    def test_auto_never_promotes_experiential(self):
        doc=json.loads(json.dumps(POLICY))
        doc["routing"]["execute_order"]=["experiential"]+doc["routing"]["execute_order"]
        doc["routing"]["judgment_order"]=["experiential"]+doc["routing"]["judgment_order"]
        with Kit(True, doc=doc, witness_document=witness()) as kit:
            for task in ("mechanical","fix_build","review"):
                line=kit.line(task=task,pool=None,model=None)
                self.assertNotIn("POOL=experiential",line, (task,line))

    def test_other_pool_literal_no_manual_default(self):
        with Kit(True, witness_document=witness()) as kit:
            self.assertEqual(kit.module._selection_model("experiential",
                                       "mechanical",kit.doc)[0], "")
            self.assertEqual(kit.module._selection_model("experiential",
                                       "mechanical",kit.doc,
                                       model="glm-5.3-uncensored")[0],
                             "glm-5.3-uncensored")


if __name__ == "__main__":
    unittest.main()
