"""Offline actual-cohort composition only: never import Broker or open runtime state."""
from __future__ import annotations

import ast
import base64
import hashlib
import json
from pathlib import Path
import shutil
import zlib

import pytest

from ops.native_fabric.provider_plans import compose

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "current116-maintenance-guard"
GUARDS = {"inspect_qualification_quiescence", "qualification_maintenance_guard"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture(scope="module")
def current_source(tmp_path_factory):
    stage = tmp_path_factory.mktemp("actual-source116")
    fixture = json.loads((ROOT / "tests/fixtures/provider-plan-auto-predecessor.json").read_text())
    predecessor = json.loads((compose.HERE / "profile.json").read_text())
    assert fixture["files"] == predecessor["base_files"]
    base = stage / "predecessor"
    for relative, spec in fixture["sources"].items():
        raw = ((ROOT / spec["source"]).read_bytes() if "source" in spec else
               zlib.decompress(base64.b64decode(spec["zlib_base64"], validate=True)))
        assert sha(raw) == fixture["files"][relative]
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (base / "RELEASE.json").write_text(json.dumps({
        "digest": predecessor["base_selection"]["generation"], "files": fixture["files"]}))
    current = stage / "current116"
    result = compose.compose(base, current)
    assert result["publication_performed"] is False
    profile = json.loads((compose.HERE / "maintenance_guard/profile.json").read_text())
    assert json.loads((current / "FILES.json").read_text()) == profile["base_files"]
    # Explicit inert source descriptor; not an installed/selected generation receipt.
    (current / "RELEASE.json").write_text(json.dumps({
        "digest": profile["base_selection"]["generation"], "files": profile["base_files"]}))
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


def test_actual116_composition_preserves_every_incumbent_definition_and115_payloads(base, tmp_path):
    target = tmp_path / "guarded"
    result = compose.compose(base, target, profile_name=PROFILE)
    profile = json.loads((compose.HERE / "maintenance_guard/profile.json").read_text())
    before, after = profile["base_files"], profile["files"]
    assert len(before) == len(after) == 116
    assert {p for p in before if before[p] != after[p]} == {"ext/lease_broker.py"}
    for name, expected in after.items():
        assert sha((target / name).read_bytes()) == expected
    old_ast, old_guards = without_guards((base / "ext/lease_broker.py").read_bytes())
    new_ast, new_guards = without_guards((target / "ext/lease_broker.py").read_bytes())
    assert not old_guards and set(new_guards) == GUARDS
    assert old_ast == new_ast  # Includes all module code/main, defaults, SQL and native application methods.
    provenance = json.loads((compose.HERE / "maintenance_guard/provenance.json").read_text())
    assert {name: sha(dump(node).encode()) for name, node in new_guards.items()} == provenance["guard_method_ast_sha256"]
    compile((target / "ext/lease_broker.py").read_bytes(), "source-only-guarded-broker", "exec")
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


def test_changed_patch_refused_before_output(base, tmp_path, monkeypatch):
    source = tmp_path / "source"
    shutil.copytree(compose.HERE / "maintenance_guard", source / "maintenance_guard")
    patch = source / "maintenance_guard/lease_broker.py.patch"
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
