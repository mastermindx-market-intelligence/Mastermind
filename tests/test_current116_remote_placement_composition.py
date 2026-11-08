"""Exact sequence-38 forward composition; inert routing, no installed state."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from ops.native_fabric.provider_plans import compose
from provider_plan_fixed_parent import materialize_fixed_parent
from test_provider_plan_remote_mode_boundary import router

PROFILE = "current116-remote-placement"


@pytest.fixture(scope="module")
def current_source(tmp_path_factory):
    root = tmp_path_factory.mktemp("public-sequence38")
    previous = materialize_fixed_parent(root / "sequence37")
    current = root / "sequence38"
    compose.compose(previous, current)
    profile = json.loads((compose.HERE / "remote_placement/profile.json").read_text())
    files = json.loads((current / "FILES.json").read_text())
    assert files == profile["base_files"] and len(files) == 116
    # Inert descriptor over independently hash-qualified public source bytes.
    (current / "RELEASE.json").write_text(json.dumps({
        "digest": profile["base_selection"]["generation"], "files": files}))
    return current


@pytest.fixture
def base(current_source, tmp_path):
    target = tmp_path / "base"
    shutil.copytree(current_source, target)
    return target


def test_forward_current116_changes_only_picker_and_preserves_all_other_owners(base, tmp_path):
    target = tmp_path / "fixed"
    result = compose.compose(base, target, profile_name=PROFILE)
    profile = json.loads((compose.HERE / "remote_placement/profile.json").read_text())
    assert len(profile["base_files"]) == len(profile["files"]) == 116
    assert set(profile["base_files"]) == set(profile["files"])
    assert {p for p in profile["files"] if profile["files"][p] != profile["base_files"][p]} == {"ext/pick.py"}
    assert profile["source_map"] == {} and set(profile["patches"]) == {"ext/pick.py"}
    for name, expected in profile["files"].items():
        assert hashlib.sha256((target / name).read_bytes()).hexdigest() == expected
        if name != "ext/pick.py":
            assert (target / name).read_bytes() == (base / name).read_bytes()
    old, new = (ast.parse((p / "ext/pick.py").read_bytes()) for p in (base, target))
    unaffected = lambda tree: [ast.dump(n, include_attributes=False) for n in tree.body
        if not (isinstance(n, ast.FunctionDef) and n.name == "_eligible_host_routes")]
    assert unaffected(old) == unaffected(new)
    assert result["base_generation"] == "296e522f5f236d764aa4ad1b9fa677d7eea32e6bdfe2fc97c0755c06a857908f"
    assert result["publication_performed"] is result["selection_performed"] is False
    assert not (target / "CURRENT.json").exists() and not (target / "ext/broker").exists()


def test_actual_audit_preview_no_longer_visits_local_plan_modes(base, tmp_path, monkeypatch):
    target = tmp_path / "fixed"
    compose.compose(base, target, profile_name=PROFILE)
    placement = (base / "ext/placement_view.py").read_bytes()
    old, old_seen = router((base / "ext/pick.py").read_bytes(), placement, monkeypatch)
    args = {"host": "auto", "task_complexity": "C1_ROUTINE_BOUNDED", "route_key": "fixture-audit"}
    assert old["format_pick"]("audit", **args) == "NONE reason=host prerequisite unavailable (ValueError)"
    assert "byteplus" in old_seen
    fixed, seen = router((target / "ext/pick.py").read_bytes(), placement, monkeypatch)
    line = fixed["format_pick"]("audit", **args)
    assert line.startswith("POOL=go ") and line.endswith(" HOST=fixture MODE=go-codex")
    assert "byteplus" not in seen and "experiential" not in seen
    # Explicit local-only mode is still no remote-host grant.
    for mode in ("byteplus", "experiential"):
        assert fixed["_format_pick_host"]("audit", host="auto", required_modes=[mode]) == \
            "NONE reason=no eligible remote mode satisfying required_modes"


@pytest.mark.parametrize("mutation", ["previous_generation", "missing_member", "changed_payload", "symlink_payload"])
def test_current_cohort_drift_is_refused_before_output(base, tmp_path, mutation):
    descriptor = base / "RELEASE.json"
    value = json.loads(descriptor.read_text())
    if mutation == "previous_generation":
        value["digest"] = "9c557397a9fbbcb88fa300b20063d6982c82fe5e768da951c74fa14a298d27b4"
    elif mutation == "missing_member":
        value["files"].pop("ext/experiential_bridge.py")
    else:
        member = base / "ext/experiential_bridge.py"
        if mutation == "changed_payload":
            member.write_bytes(member.read_bytes() + b"\n# unrelated source drift\n")
        else:
            retained = tmp_path / "retained-source"
            member.rename(retained)
            member.symlink_to(retained)
    descriptor.write_text(json.dumps(value))
    target = tmp_path / "refused"
    with pytest.raises(ValueError):
        compose.compose(base, target, profile_name=PROFILE)
    assert not target.exists()
