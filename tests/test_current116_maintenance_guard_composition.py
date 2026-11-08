"""Offline actual-cohort composition only: never import Broker or open runtime state."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from ops.native_fabric.provider_plans import compose

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "current116-maintenance-guard"
GUARDS = {"inspect_qualification_quiescence", "qualification_maintenance_guard"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture(scope="module")
def current_source(tmp_path_factory):
    from provider_plan_fixed_parent import materialize_fixed_parent
    stage = tmp_path_factory.mktemp("sealed-sequence37")
    current = materialize_fixed_parent(stage / "current116")
    profile = json.loads((compose.HERE / "maintenance_guard/profile.json").read_text())
    assert json.loads((current / "FILES.json").read_text()) == profile["base_files"]
    assert json.loads((current / "RELEASE.json").read_text())["digest"] == profile["base_selection"]["generation"]
    return current


@pytest.fixture
def base(current_source, tmp_path):
    target = tmp_path / "base"
    shutil.copytree(current_source, target)
    return target


def dump(node):
    return ast.dump(node, include_attributes=False)


def without_guards(raw):
    tree = ast.parse(raw)
    broker = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Broker")
    added = {n.name: n for n in broker.body if isinstance(n, ast.FunctionDef) and n.name in GUARDS}
    broker.body = [n for n in broker.body if not (isinstance(n, ast.FunctionDef) and n.name in GUARDS)]
    return dump(tree), added


def test_actual116_composition_preserves_every_incumbent_definition_and113_payloads(base, tmp_path):
    target = tmp_path / "guarded"
    result = compose.compose(base, target, profile_name=PROFILE)
    profile = json.loads((compose.HERE / "maintenance_guard/profile.json").read_text())
    before, after = profile["base_files"], profile["files"]
    assert len(before) == len(after) == 116
    assert {p for p in before if before[p] != after[p]} == {"ext/lease_broker.py", "ext/pick.py", "ext/remote_sub_exec.py"}
    for name, expected in after.items():
        assert sha((target / name).read_bytes()) == expected
    old_ast, old_guards = without_guards((base / "ext/lease_broker.py").read_bytes())
    new_ast, new_guards = without_guards((target / "ext/lease_broker.py").read_bytes())
    assert not old_guards and set(new_guards) == GUARDS
    assert old_ast == new_ast  # Includes all module code/main, defaults, SQL and native application methods.
    provenance = json.loads((compose.HERE / "maintenance_guard/provenance.json").read_text())
    # ast.dump representation changes across supported Python versions; compare
    # both real sources with this interpreter, retaining exact reviewed patch SHA.
    patch = (compose.HERE / "maintenance_guard/lease_broker.py.patch").read_bytes()
    assert sha(patch) == profile["patches"]["ext/lease_broker.py"]["patch_sha256"]
    added = "class Broker:\n" + "".join(line[1:] for line in patch.decode().splitlines(True)
                                         if line.startswith("+") and not line.startswith("+++"))
    expected = ast.parse(added).body[0]
    assert {n.name: dump(n) for n in expected.body} == {n: dump(v) for n, v in new_guards.items()}
    assert set(provenance["guard_method_ast_sha256"]) == GUARDS
    compile((target / "ext/lease_broker.py").read_bytes(), "source-only-guarded-broker", "exec")
    old_pick, new_pick = ast.parse((base / "ext/pick.py").read_bytes()), ast.parse((target / "ext/pick.py").read_bytes())
    changed = "_eligible_host_routes"
    old_body = [n for n in old_pick.body if not (isinstance(n, ast.FunctionDef) and n.name == changed)]
    new_body = [n for n in new_pick.body if not (isinstance(n, ast.FunctionDef) and n.name == changed)]
    assert [dump(n) for n in old_body] == [dump(n) for n in new_body]
    compile((target / "ext/pick.py").read_bytes(), "source-only-fixed-picker", "exec")
    assert result["publication_performed"] is result["selection_performed"] is False
    assert not (target / "ext/broker").exists()
    assert not (target / "CURRENT.json").exists()


@pytest.mark.parametrize("name", ["../maintenance_guard", "/tmp/profile.json", "maintenance_guard"])
def test_unregistered_profile_refused_before_output(base, tmp_path, name):
    target = tmp_path / "output"
    with pytest.raises(ValueError, match="unknown native source profile"):
        compose.compose(base, target, profile_name=name)
    assert not target.exists()


@pytest.mark.parametrize("mutation", ["generation", "foreign_files", "changed_payload", "symlink_payload"])
def test_wrong_cohort_or_nonregular_source_refused_before_output(base, tmp_path, mutation):
    descriptor = base / "RELEASE.json"
    value = json.loads(descriptor.read_text())
    if mutation == "generation":
        value["digest"] = "0" * 64
    elif mutation == "foreign_files":
        value["files"].pop("ext/pick.py")
    else:
        file = base / "ext/lease_broker.py"
        if mutation == "changed_payload":
            file.write_bytes(file.read_bytes() + b"\n# changed\n")
        else:
            regular = tmp_path / "broker-source"
            file.rename(regular)
            file.symlink_to(regular)
    descriptor.write_text(json.dumps(value))
    target = tmp_path / "output"
    with pytest.raises(ValueError):
        compose.compose(base, target, profile_name=PROFILE)
    assert not target.exists()


@pytest.mark.parametrize("patch_name", ["maintenance_guard/lease_broker.py.patch", "patches/pick_remote_plan_modes.forward.patch", "maintenance_guard/remote_sub_exec.py.patch"])
def test_changed_patch_refused_before_output(base, tmp_path, monkeypatch, patch_name):
    source = tmp_path / "source"
    shutil.copytree(compose.HERE / "maintenance_guard", source / "maintenance_guard")
    shutil.copytree(compose.HERE / "patches", source / "patches")
    patch = source / patch_name
    patch.write_bytes(patch.read_bytes() + b"\n")
    monkeypatch.setattr(compose, "HERE", source)
    target = tmp_path / "output"
    with pytest.raises(ValueError, match="source patch changed"):
        compose.compose(base, target, profile_name=PROFILE)
    assert not target.exists()


def test_existing_destination_not_overwritten(base, tmp_path):
    target = tmp_path / "output"
    target.mkdir()
    marker = target / "foreign-source"
    marker.write_text("preserve")
    with pytest.raises(ValueError, match="output must be new"):
        compose.compose(base, target, profile_name=PROFILE)
    assert marker.read_text() == "preserve"


def test_actual_combined_picker_retains_remote_eligibility_without_local_plan_authority(base, tmp_path, monkeypatch):
    from test_provider_plan_remote_mode_boundary import router, extract_context
    target = tmp_path / "joined"
    compose.compose(base, target, profile_name=PROFILE)
    raw = (target / "ext/pick.py").read_bytes()
    placement = (target / "ext/placement_view.py").read_bytes()
    fixed, seen = router(raw, placement, monkeypatch)
    line = fixed["format_pick"]("extract", host="auto", task_complexity="C0_MECHANICAL",
        provider_plan_context=extract_context())
    assert line.startswith("POOL=go ") and line.endswith(" HOST=fixture MODE=go-codex")
    assert "byteplus" not in seen and "experiential" not in seen
    for mode in ("byteplus", "experiential"):
        assert fixed["_format_pick_host"]("extract", host="auto", required_modes=[mode]) == \
            "NONE reason=no eligible remote mode satisfying required_modes"
