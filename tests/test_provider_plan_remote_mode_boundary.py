"""Fixed public picker/placement join; no installed state or request is used."""
from __future__ import annotations
import ast
import contextvars
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest
from provider_plan_fixed_parent import materialize_fixed_parent, PARENT_PROFILE

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "ops/native_fabric/provider_plans"
META = json.loads((HERE / "router_admission.json").read_text())


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    parent = materialize_fixed_parent(tmp_path_factory.mktemp("router-parent37") / "source")
    old = parent / "ext/pick.py"
    assert hashlib.sha256(old.read_bytes()).hexdigest() == META["before"]
    assert hashlib.sha256(PARENT_PROFILE.read_bytes()).hexdigest() == META["parent_profile_sha256"]
    profile = json.loads(PARENT_PROFILE.read_text())
    for rel, digest in profile["files"].items():
        assert hashlib.sha256((parent / rel).read_bytes()).hexdigest() == digest
    output = tmp_path_factory.mktemp("fixed-plan-router") / "source"
    shutil.copytree(parent, output)
    patch = HERE / META["patch"]
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == META["patch_sha256"]
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=output, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=output, check=True)
    expected = dict(profile["files"], **{"ext/pick.py": META["after"]})
    assert len(expected) == 116
    for rel, digest in expected.items():
        assert hashlib.sha256((output / rel).read_bytes()).hexdigest() == digest
    return SimpleNamespace(old=old.read_bytes(), new=(output / "ext/pick.py").read_bytes(),
                           placement=(output / "ext/placement_view.py").read_bytes(), output=output)


def router(raw, placement_raw, monkeypatch, *, eligible=True, broken=None):
    """Execute the actual public functions with inert owner observations only."""
    tree = ast.parse(raw)
    get_map = lambda t, name: ast.literal_eval(next(n.value for n in t.body if isinstance(n, ast.Assign)
        and any(isinstance(x, ast.Name) and x.id == name for x in n.targets)))
    host_modes = get_map(tree, "_HOST_POOL_MODES")
    placement_tree = ast.parse(placement_raw)
    route_plan = get_map(placement_tree, "RoutePlan")
    def no_read(*args, **kwargs):
        raise AssertionError("no installed/cached source read permitted")
    placement_ns = {"RoutePlan": route_plan, "_default_read_bytes": no_read,
                    "host_pick": SimpleNamespace(choose_host=no_read)}
    compile_defs(placement_tree, {"build_placement_view"}, placement_ns)
    seen = []
    def view(registry, state_dir, mode, **kwargs):
        seen.append(mode)
        if broken == mode:
            raise ValueError("private exception payload must remain hidden")
        if mode not in route_plan:
            # Real fixed owner refuses BEFORE its reader/evaluator is used.
            return placement_ns["build_placement_view"]({}, "/inert", mode,
                                                       state_reader=no_read, plan_reader=no_read)
        return {"host_choice": "fixture" if eligible and mode == "go-codex" else None,
                "host_eligibility": {"hosts": []}}
    connection = SimpleNamespace(close=lambda: None)
    broker = SimpleNamespace(_conn=lambda: connection, grantable_accounts=lambda provider: [],
                             hosts_path="/inert")
    monkeypatch.setitem(sys.modules, "host_pick", SimpleNamespace(
        load_registry=lambda: {"fixture": {"platform": "linux"}}, HOSTS_STATE_DIR="/inert"))
    monkeypatch.setitem(sys.modules, "placement_view", SimpleNamespace(
        _default_read_bytes=no_read, build_placement_view=view))
    monkeypatch.setitem(sys.modules, "lease_broker", SimpleNamespace(default_broker=lambda: broker))
    monkeypatch.setitem(sys.modules, "glm_host_account_source", SimpleNamespace(
        filter_observed_accounts=lambda *args, **kwargs: ([], None)))
    ns = {"re": re, "os": __import__("os"), "datetime": datetime, "timezone": timezone,
          "_HOST_POOL_MODES": host_modes,
          "_SELECTION_OBSERVER": contextvars.ContextVar("inert-router-observer", default=None),
          "_selection_model": lambda *args, **kwargs: ("fixture-model",),
          "load_pools": lambda: {}, "canonical_pool": lambda value: value}
    def policy(task_class, **kwargs):
        return "POOL=go KEY=- MODEL=fixture-model REASON=inert_existing_eligibility" if "go" in (kwargs.get("host_modes") or {}) else "NONE reason=no_pool_available"
    ns["_format_pick"] = policy
    compile_defs(tree, {"_HostRoutes", "_eligible_host_routes", "_format_pick_host", "_plan_auto_pick", "format_pick"}, ns)
    return ns, seen


def compile_defs(tree, names, namespace):
    body = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    body += [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), "fixed_public_router.py", "exec"), namespace)


def extract_context():
    return {"schema": "mastermind.provider_plan_auto_context.v1",
            "root_id": "fixture-root", "parent_run_id": "fixture-child",
            "response_only": True, "consents": {"retention_acknowledged": False,
                "sensitive_data_opt_in": False, "proprietary_code": False, "code_exposure_opt_in": False}}


def test_original116_reproduces_exact_opaque_failure_without_io(pair, monkeypatch):
    old, seen = router(pair.old, pair.placement, monkeypatch)
    line = old["format_pick"]("extract", host="auto", task_complexity="C0_MECHANICAL",
        provider_plan_context=extract_context())
    assert line == "NONE reason=host prerequisite unavailable (ValueError)"
    assert "go-codex" in seen and "byteplus" in seen


def test_existing_eligible_remote_route_is_not_lost_to_local_plan_modes(pair, monkeypatch):
    raw = pair.old if __import__("os").environ.get("MMX_ROUTER_BOUNDARY_RED") == "1" else pair.new
    fixed, seen = router(raw, pair.placement, monkeypatch)
    line = fixed["format_pick"]("extract", host="auto", task_complexity="C0_MECHANICAL",
        provider_plan_context=extract_context())
    assert line.startswith("POOL=go ") and line.endswith(" HOST=fixture MODE=go-codex")
    assert "byteplus" not in seen and "experiential" not in seen


def test_no_eligible_remote_host_remains_refused(pair, monkeypatch):
    fixed, seen = router(pair.new, pair.placement, monkeypatch, eligible=False)
    assert fixed["format_pick"]("extract", host="auto", task_complexity="C0_MECHANICAL",
        provider_plan_context=extract_context()).startswith(
        "NONE reason=no eligible remote mode on requested host")
    assert "byteplus" not in seen and "experiential" not in seen


@pytest.mark.parametrize("mode", ["byteplus", "experiential"])
def test_plan_only_required_mode_is_not_a_remote_grant(pair, monkeypatch, mode):
    fixed, seen = router(pair.new, pair.placement, monkeypatch)
    assert fixed["_format_pick_host"]("extract", host="auto", required_modes=[mode]) == \
        "NONE reason=no eligible remote mode satisfying required_modes"
    assert seen == []


@pytest.mark.parametrize("mode", ["go-codex", "minimax", "glm-codex", "cursor", "grok", "oc-free"])
def test_ordinary_remote_eligibility_input_and_result_unchanged(pair, monkeypatch, mode):
    old, old_seen = router(pair.old, pair.placement, monkeypatch)
    before = old["_format_pick_host"]("extract", host="auto", required_modes=[mode])
    new, new_seen = router(pair.new, pair.placement, monkeypatch)
    assert new["_format_pick_host"]("extract", host="auto", required_modes=[mode]) == before
    assert new_seen == old_seen == [mode]


def test_other_placement_valueerror_still_refuses_and_suppresses_prose(pair, monkeypatch):
    new, _ = router(pair.new, pair.placement, monkeypatch, broken="go-codex")
    line = new["_format_pick_host"]("extract", host="auto")
    assert line == "NONE reason=host prerequisite unavailable (ValueError)"
    assert "private" not in line


def test_unknown_future_remote_mode_is_not_generically_silenced(pair, monkeypatch):
    new, _ = router(pair.new, pair.placement, monkeypatch)
    new["_HOST_POOL_MODES"]["unknown"] = ("unknown-mode",)
    assert new["_format_pick_host"]("extract", host="auto") == \
        "NONE reason=host prerequisite unavailable (ValueError)"


def test_all_other_functions_including_auto_classes_and_consent_are_exact(pair):
    old, new = ast.parse(pair.old), ast.parse(pair.new)
    defs = lambda tree: {n.name: ast.dump(n, include_attributes=False) for n in tree.body
                        if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    a, b = defs(old), defs(new)
    assert {k for k in a if a[k] != b[k]} == {"_eligible_host_routes"}
    assert a.keys() == b.keys()


def test_fixed_postimage_cannot_be_claimed_for_unrelated_drift(pair, tmp_path):
    output = tmp_path / "source"; (output / "ext").mkdir(parents=True)
    target = output / "ext/pick.py"; target.write_bytes(pair.old + b"\n# unrelated byte\n")
    assert hashlib.sha256(target.read_bytes()).hexdigest() != META["before"]
    subprocess.run(["git", "apply", str(HERE / META["patch"])], cwd=output, check=True)
    assert hashlib.sha256(target.read_bytes()).hexdigest() != META["after"]
