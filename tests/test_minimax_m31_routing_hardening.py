"""Model and host-selection hardening for the existing MiniMax Fabric pool.

No provider calls, new lease/admission mechanism, credential reads, installed
native mutation or change to the signed M3 default. Runs only against the
exact reviewed five-member native patch applied to historical source.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROLLOUT = ROOT / "ops/native_fabric/quota_continuity/rollout"
PATCHES = ROOT / "ops/native_fabric/patches"
SOURCE = ROOT / "ops/native_fabric/quota_continuity/source"


class MiniMaxM31RoutingHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix="m31-routing-hardening-")
        cls.base = Path(cls.scratch.name) / "historical"
        cls.base.mkdir()
        cls.candidate = Path(cls.scratch.name) / "candidate"
        for command in (
            [sys.executable, str(ROLLOUT / "build_review_stage.py"),
             "--output", str(cls.base)],
            [sys.executable, str(PATCHES / "stage_minimax_m31_flash.py"),
             "--base-stage", str(cls.base), "--output", str(cls.candidate)],
        ):
            outcome = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                                     timeout=25)
            if outcome.returncode:
                cls.scratch.cleanup()
                raise AssertionError(outcome.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def run_candidate(self, code: str):
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((
            str(self.candidate / "native-code-stage/ext"),
            str(SOURCE),
        ))
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                env=env, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_minimax_keyed_capacity_distribution_without_cross_pool_change(self):
        result = self.run_candidate(r"""
import collections, host_pick, math
rows = [dict(host=name, score=score, capacity_remaining=slots,
             eligible=True, seat=False) for name, score, slots in [
             ("ubuntu0", 0.953, 11), ("ubuntu1", 0.768, 17),
             ("ubuntu2", 0.786, 7), ("ubuntu3", 0.999, 12)]]
baseline = collections.Counter()
balanced = collections.Counter()
for i in range(120):
    key = f"mini-flash-{i:03d}"
    legacy = host_pick.choose_host(rows, prefer_remote=True, placement_key=key)
    picked = host_pick.choose_host(rows, prefer_remote=True,
                                   placement_key=key, near_equal_score_gap=0.08)
    assert picked == host_pick.choose_host(rows, prefer_remote=True,
                         placement_key=key, near_equal_score_gap=0.08)
    baseline[legacy["host"]] += 1
    balanced[picked["host"]] += 1
assert baseline == {"ubuntu3": 120}
assert balanced["ubuntu0"] >= 30 and balanced["ubuntu3"] >= 30
assert set(balanced) == {"ubuntu0", "ubuntu3"}
# An unqualified host, even with a stellar score, can never be selected.
unqualified = [dict(x) for x in rows]
unqualified[3]["eligible"] = False
unqualified.append(dict(host="stale", score=math.nan,
                        capacity_remaining=100, eligible=True, seat=False))
for i in range(20):
    picked = host_pick.choose_host(unqualified, prefer_remote=True,
                placement_key=f"quarantine-{i}", near_equal_score_gap=0.08)
    assert picked["host"] == "ubuntu0"
try:
    host_pick.choose_host(rows, placement_key="bad-gap",
                          near_equal_score_gap=0.5)
except ValueError as exc:
    assert str(exc) == "host_pick_near_equal_gap_invalid"
else:
    raise AssertionError("invalid score window was admitted")
print("BALANCED", dict(balanced))
""")
        self.assertIn("BALANCED", result)

    def test_signed_per_task_model_selection_only_opt_in(self):
        result = self.run_candidate(r"""
import pick
from unittest.mock import patch
doc={"pools":{"minimax":{
    "default_model":"MiniMax-M3",
    "task_models":{"mechanical":"MiniMax-M3.1-Flash","fix_build":"MiniMax-M3.1-Flash"},
    "role":["executor"],"task_classes":["mechanical","fix_build","extract"]}},
    "routing":{}}
assert pick._minimax_signed_model_policy(doc) == (True,"ok")
assert pick._selection_model("minimax","mechanical",doc)[0] == "MiniMax-M3.1-Flash"
assert pick._selection_model("minimax","extract",doc)[0] == "MiniMax-M3"
assert pick._selection_model("minimax","mechanical",doc,model="MiniMax-M3")[0] == "MiniMax-M3"
with (patch.object(pick,"load_pools",return_value=doc),
      patch.object(pick,"_needs_ok",return_value=(True,"ok")),
      patch.object(pick,"_subject_ok",return_value=(True,"ok")),
      patch.object(pick,"hard_filter",return_value=(True,"ok")),
      patch.object(pick,"floor_demotes",return_value=False),
      patch.object(pick,"launch_policy",return_value={"allowed":True})):
    line=pick._format_pick("mechanical",pool="minimax",
                           host_modes={"minimax":"minimax"})
    assert "MODEL=MiniMax-M3.1-Flash " in line, line
    legacy=pick._format_pick("extract",pool="minimax",
                             host_modes={"minimax":"minimax"})
    assert "MODEL=MiniMax-M3 " in legacy, legacy
    pinned=pick._format_pick("mechanical",pool="minimax",
                             host_modes={"minimax":"minimax"},requested_model="MiniMax-M3")
    assert "MODEL=MiniMax-M3 " in pinned, pinned
for bad in [
 {"default_model":"MiniMax-M3.1-Unknown"},
 {"default_model":"MiniMax-M3","task_models":{"review":"MiniMax-M3.1-Flash"}},
 {"default_model":"MiniMax-M3","task_models":{"mechanical":"MiniMax-M9"}},
 {"default_model":"MiniMax-M3","task_models":["MiniMax-M3.1-Flash"]},
]:
    modified={"pools":{"minimax":bad}}
    ok,reason=pick.policy_allows("minimax","mechanical",modified)
    assert not ok and reason=="invalid MiniMax signed model policy"
# REVIEW #5732561118: absent, incomplete and wrong-typed signed pool
# documents must refuse rather than default to M3 or raise AttributeError.
for missing in [
 {},
 {"pools":{}},
 {"pools":[]},
 {"pools":42},
 {"pools":{"minimax":[]}},
 {"pools":{"minimax":{}}},
 {"pools":{"minimax":{"role":["executor"]}}},
 {"pools":{"minimax":{"default_model":None}}},
]:
    ok,why=pick.policy_allows("minimax","mechanical",missing)
    assert (ok,why)==(False,"invalid MiniMax signed model policy"), (missing,ok,why)
# A signed default with no optional class overrides remains valid M3.
assert pick._minimax_signed_model_policy({"pools":{"minimax":{"default_model":"MiniMax-M3"}}})==(True,"ok")
# No unreviewed or implicit default-model promotion.
assert pick._selection_model("minimax","mechanical",
       {"pools":{"minimax":{"default_model":"MiniMax-M3"}}})[0] == "MiniMax-M3"
print("SIGNED_MODEL_POLICY_PASS")
""")
        self.assertIn("SIGNED_MODEL_POLICY_PASS", result)

    def test_minimax_host_readiness_rejects_older_telemetry_only_for_this_pool(self):
        result = self.run_candidate(r"""
import pick,host_pick,placement_view
from unittest.mock import patch
registry={"ubuntu0":{"roles":["lanes"],"platform":"linux"}}
calls=[]
def recorded_view(registry, state_dir, mode, **kwargs):
    calls.append((mode, kwargs.get("max_age", 600)))
    return {"host_choice":"ubuntu0","host_eligibility":{"hosts":[]}}
with (patch.object(host_pick,"load_registry",return_value=registry),
      patch.object(placement_view,"build_placement_view",side_effect=recorded_view),
      patch.object(pick,"_HOST_POOL_MODES",
                   {"minimax":("minimax",),"grok":("grok",)})):
    routes=pick._eligible_host_routes("auto",route_key="m31-freshness")
assert calls == [("minimax",180),("grok",600)], calls
assert routes["minimax"]==("ubuntu0","minimax")
assert routes["grok"]==("ubuntu0","grok")
print("STRICT_MINIMAX_FRESHNESS_PASS")
""")
        self.assertIn("STRICT_MINIMAX_FRESHNESS_PASS", result)

    def test_placement_view_targets_minimax_only(self):
        result = self.run_candidate(r"""
from unittest.mock import patch
from datetime import datetime, timezone
import placement_view
registry={"ubuntu0":{"roles":["lanes"],"allowed_modes":["minimax","glm"]},
          "ubuntu3":{"roles":["lanes"],"allowed_modes":["minimax","glm"]}}
rows=[{"host":name, "score":score, "eligible":True, "seat":False,
       "capacity_remaining":10,"gates":[]}
      for name,score in (("ubuntu0",.953),("ubuntu3",.999))]
observed=[]
def chooser(rows,**kwargs):
    observed.append(kwargs)
    return rows[0]
with (patch.object(placement_view,"_telemetry_snapshot",return_value={}),
      patch.object(placement_view,"_candidate_exclusions",return_value=[]),
      patch.object(placement_view,"_identity_findings",return_value=([],{}))):
    for mode in ("minimax","glm"):
        view=placement_view.build_placement_view(registry,"/dev/null",mode,
            now=datetime.now(timezone.utc),selection_key="m31-placement-test",
            evaluator=lambda *a,**kw:[dict(row) for row in rows],chooser=chooser)
        assert view["reservation"]=="NONE"
assert observed[0]["near_equal_score_gap"] == 0.08
assert "near_equal_score_gap" not in observed[1]
assert observed[0]["placement_key"]=="m31-placement-test"
print("MINIMAX_ONLY_WINDOW_PASS")
""")
        self.assertIn("MINIMAX_ONLY_WINDOW_PASS", result)


if __name__ == "__main__":
    unittest.main()
