"""Same finite installer owner across old successor and Go application ingress."""
import json
import os
from pathlib import Path
import shutil
import sys
from unittest import mock

import pytest

from test_go_native_stage import builds, native_stage, ROOT, g, installer, builder
sys.path.insert(0, str(ROOT.parents[2] / "tests"))
import test_native_launcher_successor_transition as history
from test_native_launcher_successor_transition import source_owners, owner


@pytest.fixture
def go_owner(owner, native_stage):
    history.prepare(owner)
    owner.successor_receipt = installer.apply_successor(owner.successor)
    owner.successor_bytes = {p.name: p.read_bytes() for p in owner.successor.iterdir()}
    owner.go_output = owner.root / "go-source"
    shutil.copytree(native_stage, owner.go_output)
    owner.go_manifest = json.loads((owner.go_output / "native-manifest.json").read_bytes())
    builder.stage_external_go_component(ROOT, owner.go_output, str(owner.ext), staged_manifest=owner.go_manifest)
    (owner.ext / "go_shim").mkdir()
    owner.go_original = owner.ext / "go_shim/go_shim.py"
    owner.go_original.write_bytes((ROOT / "source/go_shim.py").read_bytes())
    owner.go_target = g.publish(owner.go_output / "native-code-stage", owner.ext, owner.go_manifest)
    owner.go_bundle = owner.root / "go-transition"
    owner.go_plan = installer.prepare_go(owner.successor, owner.go_target.name,
        owner.go_output / "external-go-component", owner.go_bundle)
    return owner


def assert_history(owner):
    history.unchanged_history(owner)
    assert {p.name: p.read_bytes() for p in owner.successor.iterdir()} == owner.successor_bytes


def test_real_completed_successor_go_transition_commits_once_and_remote_stays_legacy(go_owner):
    case = go_owner
    with mock.patch.object(g, "_select_locked", wraps=g._select_locked) as selection:
        receipt = installer.apply_go(case.go_bundle)
        assert selection.call_count == 1
    assert receipt["schema"] == installer.GO_SCHEMA
    assert receipt["bridged"] == ["pool", "task", "go"] and receipt["remote"] == "legacy"
    assert receipt["selection"] == g.current(case.store)
    assert receipt["selection"]["sequence"] == case.successor_receipt["selection"]["sequence"] + 1
    assert receipt["to_launcher"] == g.digest(Path(g.__file__).read_bytes())
    for name in ("pool", "task", "go"):
        row = case.go_plan["entries"][name]
        assert g.digest(Path(row["target"]).read_bytes()) == row["bridge"]
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")), \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("completed replay selected")):
        assert installer.apply_go(case.go_bundle) == receipt
        assert installer.reconcile_go(case.go_bundle) == receipt
        assert installer._completed_successor(case.successor)[1]["digest"] == case.successor_receipt["plan_digest"]
    assert_history(case)


@pytest.mark.parametrize("boundary", ["intent", "launcher", "pool", "task", "go", "selection", "receipt"])
def test_original_interrupted_transition_reconciles_without_second_selection(go_owner, boundary):
    case = go_owner
    original = g.atomic_bytes
    seen = []
    def write(path, raw, mode):
        original(path, raw, mode)
        path = Path(path)
        kind = ("intent" if path.name == ".go-application-ingress-v1.json" else
                "launcher" if path.parent.name == "launchers" and path.stem == case.go_plan["to_launcher"] else
                "selection" if path.name == "CURRENT.json" else
                "receipt" if path.name == case.go_plan["digest"] + ".go.json" else
                next((n for n in ("pool", "task", "go") if str(path) == case.go_plan["entries"][n]["target"]), None))
        if kind == boundary and kind not in seen:
            seen.append(kind)
            raise OSError("fixture after original " + kind)
    with mock.patch.object(g, "atomic_bytes", side_effect=write), pytest.raises(OSError, match="fixture"):
        installer.apply_go(case.go_bundle)
    assert seen == [boundary]
    assert installer.read_go(case.go_bundle)[0] == case.go_plan
    assert installer._completed_successor(case.successor)[4] == case.successor_receipt["selection"]
    if boundary in {"selection", "receipt"}:
        with mock.patch.object(g, "_select_locked", side_effect=AssertionError("reconcile selected again")):
            receipt = installer.reconcile_go(case.go_bundle)
            assert receipt["selection"] == g.current(case.store)
    else:
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("precommit reconcile wrote")), \
                mock.patch.object(g, "_select_locked", side_effect=AssertionError("precommit reconcile selected")):
            with pytest.raises(ValueError, match="not committed"):
                installer.reconcile_go(case.go_bundle)
        receipt = installer.apply_go(case.go_bundle)
    assert receipt["selection"]["sequence"] == case.go_plan["expected_selection"]["sequence"] + 1
    assert_history(case)


def test_completed_history_survives_later_current_but_stale_go_plan_cannot_select(go_owner):
    case = go_owner
    before = g.current(case.store)
    later = g.select(case.store, before["generation"], before["generation"])
    assert installer._completed_successor(case.successor)[4] == case.successor_receipt["selection"]
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("stale plan wrote")):
        with pytest.raises(ValueError, match="compare-and-swap"):
            installer.apply_go(case.go_bundle)
    assert g.current(case.store) == later
    assert_history(case)


@pytest.mark.parametrize("boundary", ["pool", "go"])
def test_different_valid_bundle_between_bridges_or_before_cas_is_not_adopted(go_owner, boundary):
    case = go_owner
    alternative = case.root / "alternative-source"
    shutil.copytree(case.go_output, alternative)
    other, payloads = installer._go_plan(case.successor, case.go_target.name,
        alternative / "external-go-component", case.go_plan["expected_selection"])
    assert other != case.go_plan
    assert payloads == installer.read_go(case.go_bundle)[1]
    original = g.atomic_bytes
    swapped = []
    def write(path, raw, mode):
        original(path, raw, mode)
        if str(path) == case.go_plan["entries"][boundary]["target"] and not swapped:
            (case.go_bundle / "PLAN.json").write_bytes(g.canonical(other) + b"\n")
            # It remains an internally valid source bundle, so merely calling
            # reader again without comparing the result would miss this.
            assert installer.read_go(case.go_bundle)[0] == other
            swapped.append(True)
    with mock.patch.object(g, "atomic_bytes", side_effect=write), \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("changed bundle selected")):
        with pytest.raises(ValueError, match="inputs changed"):
            installer.apply_go(case.go_bundle)
    assert swapped and g.current(case.store) == case.go_plan["expected_selection"]
    intent = json.loads((case.store / "bootstrap/.go-application-ingress-v1.json").read_bytes())
    assert intent["plan_digest"] == case.go_plan["digest"]
    assert_history(case)


@pytest.mark.parametrize("fault", ["component", "payload-symlink", "ingress-hardlink", "launcher-source", "foreign-intent"])
def test_changed_sources_or_custody_refuse_without_installing(go_owner, fault):
    case = go_owner
    context = mock.patch.object(g, "_select_locked", side_effect=AssertionError("bad custody selected"))
    with context:
        if fault == "component":
            (case.go_output / "external-go-component/go_shim.py").write_bytes(b"wrong")
        elif fault == "payload-symlink":
            path = case.go_bundle / "go.bridge"
            twin = case.root / "payload-twin"
            path.rename(twin)
            path.symlink_to(twin)
        elif fault == "ingress-hardlink":
            os.link(case.go_original, case.root / "other-go.py")
        elif fault == "foreign-intent":
            path = case.store / "bootstrap/.go-application-ingress-v1.json"
            g.atomic_bytes(path, b"{}\n", 0o600)
        else:
            path = case.root / "changed-launcher.py"
            path.write_bytes(Path(g.__file__).read_bytes() + b"\n# source drift\n")
            with mock.patch.object(g, "__file__", str(path)), pytest.raises(ValueError):
                installer.apply_go(case.go_bundle)
            return
        with pytest.raises((ValueError, OSError)):
            installer.apply_go(case.go_bundle)
    assert g.current(case.store) == case.go_plan["expected_selection"]
    assert_history(case)


def test_selected_missing_go_launcher_is_not_repaired_by_reconciliation(go_owner):
    case = go_owner
    installer.apply_go(case.go_bundle)
    launcher = case.store / "launchers" / (case.go_plan["to_launcher"] + ".py")
    launcher.unlink()
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("reconcile repaired launcher")), \
            pytest.raises(OSError):
        installer.reconcile_go(case.go_bundle)
    assert_history(case)
