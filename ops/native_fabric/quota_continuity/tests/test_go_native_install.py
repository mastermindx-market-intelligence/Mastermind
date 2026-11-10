"""Same finite installer owner across old successor and Go application ingress."""
import json
import os
from pathlib import Path
import shutil
import stat
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


@pytest.fixture
def retained_go_owner(owner, native_stage):
    """A real disposable owner whose ORIGINAL bootstrap artifact was pruned.

    The bootstrap -> upgrade -> successor chain is produced by the incumbent
    installer in a throwaway kit, so every retained byte, receipt and installed
    bridge is genuine. Only the deleted historical bootstrap artifact is
    absent. Nothing is synthesized and no live path is read.
    """
    history.prepare(owner)
    owner.successor_receipt = installer.apply_successor(owner.successor)
    owner.successor_bytes = {p.name: p.read_bytes() for p in owner.successor.iterdir()}
    owner.predecessor_bytes = {p.name: p.read_bytes() for p in owner.predecessor.iterdir()}
    owner.successor_plan = json.loads((owner.successor / "PLAN.json").read_bytes())
    owner.prior_plan = json.loads((owner.predecessor / "PLAN.json").read_bytes())
    assert owner.successor_plan["prior_upgrade_digest"] == owner.prior_plan["digest"]
    assert owner.successor_plan["bootstrap_digest"] == owner.base["digest"]
    owner.go_output = owner.root / "go-source"
    shutil.copytree(native_stage, owner.go_output)
    owner.go_manifest = json.loads((owner.go_output / "native-manifest.json").read_bytes())
    builder.stage_external_go_component(ROOT, owner.go_output, str(owner.ext), staged_manifest=owner.go_manifest)
    (owner.ext / "go_shim").mkdir()
    owner.go_original = owner.ext / "go_shim/go_shim.py"
    owner.go_original.write_bytes((ROOT / "source/go_shim.py").read_bytes())
    owner.go_target = g.publish(owner.go_output / "native-code-stage", owner.ext, owner.go_manifest)
    # Prune the ORIGINAL bootstrap artifact exactly as the historical owner did.
    shutil.rmtree(owner.original)
    assert not owner.original.exists()
    receipts = owner.store / "bootstrap"
    owner.receipt_names = (
        ".launcher-successor-v1.json",
        ".paired-launcher-upgrade.json",
        owner.successor_plan["digest"] + ".successor.json",
        owner.prior_plan["digest"] + ".upgrade.json",
        owner.base["digest"] + ".phase1.json",
    )
    owner.receipt_bytes = {name: (receipts / name).read_bytes() for name in owner.receipt_names}
    owner.pins = {
        "successor": {name: g.digest(raw) for name, raw in owner.successor_bytes.items()},
        "prior": {name: g.digest(raw) for name, raw in owner.predecessor_bytes.items()},
        "receipts": {name: g.digest(raw) for name, raw in owner.receipt_bytes.items()},
    }
    for name, value in (("RETAINED_STATUS_PROOF_SHA256", owner.pins),
                        ("RETAINED_STATUS_PLAN_DIGEST", owner.successor_plan["digest"])):
        patch = mock.patch.object(installer, name, value)
        patch.start()
        owner.addCleanup(patch.stop)
    owner.retained_bundle = owner.root / "retained-go-transition"
    owner.retained_plan = installer.prepare_retained_go(
        owner.successor, owner.go_target.name,
        owner.go_output / "external-go-component", owner.retained_bundle)
    return owner


def assert_retained_history(owner, pruned=True):
    """The pruned history, its retained payloads and its receipts never change."""
    assert {p.name: p.read_bytes() for p in owner.successor.iterdir()} == owner.successor_bytes
    assert {p.name: p.read_bytes() for p in owner.predecessor.iterdir()} == owner.predecessor_bytes
    for name, raw in owner.receipt_bytes.items():
        assert (owner.store / "bootstrap" / name).read_bytes() == raw
    assert owner.original.exists() is not pruned


def test_retained_completed_successor_prepares_one_truthful_forward_go_plan(retained_go_owner):
    case = retained_go_owner
    plan = case.retained_plan
    assert plan["schema"] == installer.GO_RETAINED_SCHEMA
    assert plan["predecessor_origin"] == installer.RETAINED_GO_ORIGIN
    assert plan["prior_successor_bundle"] == str(case.successor)
    assert plan["prior_successor_digest"] == case.successor_plan["digest"]
    assert plan["bootstrap_digest"] == case.successor_plan["bootstrap_digest"]
    assert plan["from_launcher"] == installer.SUCCESSOR_TO
    assert plan["expected_selection"] == case.successor_receipt["selection"]
    assert plan["target_generation"] == case.go_target.name
    for name in ("pool", "task"):
        assert plan["entries"][name]["previous"] == case.successor_plan["entries"][name]["bridge"]
    # The forward bridges change only the launcher reference. The interpreter,
    # the arguments and every original business byte are preserved.
    python = case.base["python"]
    launcher = case.store / "launchers" / (plan["to_launcher"] + ".py")
    assert (case.retained_bundle / "pool.bridge").read_bytes() == installer.shell_bridge(
        python, launcher, case.store, "pool")
    old_task = case.successor_bytes["task.bridge"]
    new_task = (case.retained_bundle / "task.bridge").read_bytes()
    assert old_task != new_task
    marker = b"# " + installer.BRIDGE_MARKER.encode()
    assert old_task.split(marker)[0] == new_task.split(marker)[0]
    assert new_task.count(installer._task_bridge_branch(python, launcher, case.store).encode()) == 1
    # Preparation changes no selection, no ingress bridge and no service.
    assert g.current(case.store) == case.successor_receipt["selection"]
    for name in ("pool", "task"):
        row = plan["entries"][name]
        assert g.digest(Path(row["target"]).read_bytes()) == row["previous"]
    assert (case.ext / "go_shim/go_shim.py").read_bytes() == (ROOT / "source/go_shim.py").read_bytes()
    assert not (case.store / "bootstrap/.go-application-ingress-v1.json").exists()
    assert_retained_history(case)


def test_pruned_history_is_never_relabelled_as_an_intact_successor(retained_go_owner):
    case = retained_go_owner
    # The strict intact readers still refuse: the deleted bootstrap is not rebuilt.
    with pytest.raises(FileNotFoundError):
        installer.read_successor(case.successor)
    with pytest.raises(FileNotFoundError):
        installer.prepare_go(case.successor, case.go_target.name,
                             case.go_output / "external-go-component", case.root / "intact-go")
    assert not (case.root / "intact-go").exists()
    # The frozen status route still reads the same retained evidence.
    status_plan, status_payloads = installer.read_retained_successor_after_bootstrap_prune(case.successor)
    assert status_plan == case.successor_plan
    assert status_payloads["pool.bridge"] == case.successor_bytes["pool.bridge"]
    # Neither owner accepts the other owner's plan shape.
    with pytest.raises(ValueError, match="invalid launcher successor plan"):
        installer.read_successor(case.retained_bundle)
    with pytest.raises(ValueError, match="invalid Go ingress plan"):
        installer.read_go(case.retained_bundle)
    with pytest.raises(ValueError, match="invalid Go ingress plan"):
        installer.apply_go(case.retained_bundle)
    assert_retained_history(case)


def test_retained_go_transition_commits_once_and_keeps_the_original_transaction(retained_go_owner):
    case = retained_go_owner
    with mock.patch.object(g, "_select_locked", wraps=g._select_locked) as selection:
        receipt = installer.apply_retained_go(case.retained_bundle)
        assert selection.call_count == 1
    assert receipt["schema"] == installer.GO_RETAINED_SCHEMA
    assert receipt["bridged"] == ["pool", "task", "go"] and receipt["remote"] == "legacy"
    assert receipt["selection"] == g.current(case.store)
    assert receipt["selection"]["sequence"] == case.retained_plan["expected_selection"]["sequence"] + 1
    assert receipt["selection"]["generation"] == case.go_target.name
    for name in ("pool", "task", "go"):
        row = case.retained_plan["entries"][name]
        assert g.digest(Path(row["target"]).read_bytes()) == row["bridge"]
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")), \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("completed replay selected")):
        assert installer.apply_retained_go(case.retained_bundle) == receipt
        assert installer.reconcile_retained_go(case.retained_bundle) == receipt
    assert_retained_history(case)


@pytest.mark.parametrize("target", ["successor-plan", "successor-payload", "prior-payload",
                                    "receipt", "launcher", "bridge"])
def test_changed_retained_evidence_refuses_without_installing(retained_go_owner, target):
    case = retained_go_owner
    if target == "successor-plan":
        path = case.successor / "PLAN.json"
    elif target == "successor-payload":
        path = case.successor / "native_generation.py"
    elif target == "prior-payload":
        path = case.predecessor / "native_generation.py"
    elif target == "receipt":
        path = case.store / "bootstrap" / (case.prior_plan["digest"] + ".upgrade.json")
    elif target == "launcher":
        path = case.store / "launchers" / (installer.SUCCESSOR_TO + ".py")
    else:
        path = case.successor / "pool.bridge"
    original = path.read_bytes()
    mode = stat.S_IMODE(path.stat().st_mode)
    output = case.root / "retained-retry"
    try:
        path.chmod(0o600)
        path.write_bytes(original + b" ")
        path.chmod(mode)
        with pytest.raises((ValueError, OSError)):
            installer.prepare_retained_go(case.successor, case.go_target.name,
                                          case.go_output / "external-go-component", output)
    finally:
        path.chmod(0o600)
        path.write_bytes(original)
        path.chmod(mode)
    assert not output.exists()
    assert g.current(case.store) == case.successor_receipt["selection"]
    assert_retained_history(case)


def test_restored_original_bootstrap_refuses_the_retained_admission(retained_go_owner):
    case = retained_go_owner
    case.original.mkdir(mode=0o700)
    (case.original / "PLAN.json").write_bytes(b"{}\n")
    output = case.root / "retained-restored"
    with pytest.raises(ValueError, match="absent original bootstrap"):
        installer.prepare_retained_go(case.successor, case.go_target.name,
                                      case.go_output / "external-go-component", output)
    assert not output.exists()
    assert_retained_history(case, pruned=False)


def test_foreign_or_mixed_retained_chain_refuses(retained_go_owner):
    case = retained_go_owner
    output = case.root / "retained-foreign"
    with pytest.raises(ValueError, match="retained successor evidence changed"):
        installer.prepare_retained_go(case.predecessor, case.go_target.name,
                                      case.go_output / "external-go-component", output)
    assert not output.exists()
    assert g.current(case.store) == case.successor_receipt["selection"]
    assert_retained_history(case)


def test_partial_target_or_changed_component_refuses(retained_go_owner):
    case = retained_go_owner
    partial = case.root / "retained-partial"
    with pytest.raises(ValueError, match="entrypoint transition differs"):
        installer.prepare_retained_go(case.successor, case.new_target.name,
                                      case.go_output / "external-go-component", partial)
    component = case.go_output / "external-go-component/go_shim.py"
    original = component.read_bytes()
    drift = case.root / "retained-drift"
    try:
        component.write_bytes(original + b"\n# drift\n")
        with pytest.raises(ValueError, match="reviewed source"):
            installer.prepare_retained_go(case.successor, case.go_target.name,
                                          case.go_output / "external-go-component", drift)
    finally:
        component.write_bytes(original)
    assert not partial.exists() and not drift.exists()
    assert g.current(case.store) == case.successor_receipt["selection"]
    assert_retained_history(case)


def test_stale_retained_plan_cannot_select_a_later_current(retained_go_owner):
    case = retained_go_owner
    before = g.current(case.store)
    later = g.select(case.store, before["generation"], before["generation"])
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("stale plan wrote")):
        with pytest.raises(ValueError, match="compare-and-swap"):
            installer.apply_retained_go(case.retained_bundle)
    assert g.current(case.store) == later
    assert_retained_history(case)


def test_studio_consumer_conflict_refuses_before_any_ingress_write(retained_go_owner):
    case = retained_go_owner
    with mock.patch.object(installer.studio_consumer_owner, "pinned_consumers",
                           return_value=["private"]):
        with pytest.raises(ValueError, match="STUDIO_CONSUMER_PIN_MIGRATION_REQUIRED"):
            installer.apply_retained_go(case.retained_bundle)
    assert g.current(case.store) == case.retained_plan["expected_selection"]
    assert not (case.store / "bootstrap/.go-application-ingress-v1.json").exists()
    assert_retained_history(case)


@pytest.mark.parametrize("boundary", ["intent", "launcher", "pool", "task", "go", "selection", "receipt"])
def test_interrupted_retained_transition_reconciles_without_second_selection(retained_go_owner, boundary):
    case = retained_go_owner
    original = g.atomic_bytes
    seen = []
    def write(path, raw, mode):
        original(path, raw, mode)
        path = Path(path)
        kind = ("intent" if path.name == ".go-application-ingress-v1.json" else
                "launcher" if path.parent.name == "launchers" and path.stem == case.retained_plan["to_launcher"] else
                "selection" if path.name == "CURRENT.json" else
                "receipt" if path.name == case.retained_plan["digest"] + ".go.json" else
                next((n for n in ("pool", "task", "go") if str(path) == case.retained_plan["entries"][n]["target"]), None))
        if kind == boundary and kind not in seen:
            seen.append(kind)
            raise OSError("fixture after original " + kind)
    with mock.patch.object(g, "atomic_bytes", side_effect=write), pytest.raises(OSError, match="fixture"):
        installer.apply_retained_go(case.retained_bundle)
    assert seen == [boundary]
    assert installer.read_retained_go(case.retained_bundle)[0] == case.retained_plan
    if boundary in {"selection", "receipt"}:
        with mock.patch.object(g, "_select_locked", side_effect=AssertionError("reconcile selected again")):
            receipt = installer.reconcile_retained_go(case.retained_bundle)
            assert receipt["selection"] == g.current(case.store)
    else:
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("precommit reconcile wrote")), \
                mock.patch.object(g, "_select_locked", side_effect=AssertionError("precommit reconcile selected")):
            with pytest.raises(ValueError, match="not committed"):
                installer.reconcile_retained_go(case.retained_bundle)
        receipt = installer.apply_retained_go(case.retained_bundle)
    assert receipt["selection"]["sequence"] == case.retained_plan["expected_selection"]["sequence"] + 1
    assert_retained_history(case)


def test_completed_retained_go_proof_is_available_to_service_owner(retained_go_owner):
    case = retained_go_owner
    with pytest.raises((ValueError, OSError)):
        installer._completed_go_for_service(case.retained_bundle)
    installer.apply_retained_go(case.retained_bundle)
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("inspection wrote")), \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("inspection selected")):
        plan, selected, root, metadata = installer._completed_go_for_service(case.retained_bundle)
    assert plan == case.retained_plan
    assert selected == g.current(case.store)
    assert root == case.go_target
    assert metadata["entrypoints"]["go"] == g.GO_ENTRY
    assert_retained_history(case)


@pytest.mark.parametrize("fault", ["receipt", "intent", "pointer", "bridge", "launcher"])
def test_completed_retained_go_service_proof_keeps_all_native_fences(retained_go_owner, fault):
    case = retained_go_owner
    installer.apply_retained_go(case.retained_bundle)
    if fault == "receipt":
        (case.store / "bootstrap" / (case.retained_plan["digest"] + ".go.json")).unlink()
    elif fault == "intent":
        (case.store / "bootstrap/.go-application-ingress-v1.json").write_bytes(b"{}\n")
    elif fault == "pointer":
        current = g.current(case.store)
        g.select(case.store, current["generation"], current["generation"])
    elif fault == "bridge":
        Path(case.retained_plan["entries"]["pool"]["target"]).write_bytes(b"foreign\n")
    else:
        (case.store / "launchers" / (case.retained_plan["to_launcher"] + ".py")).unlink()
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("inspection repaired")), \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("inspection selected")), \
            pytest.raises((ValueError, OSError)):
        installer._completed_go_for_service(case.retained_bundle)


def test_completed_go_service_owner_refuses_unknown_schema_before_reader(go_owner):
    case = go_owner
    path = case.go_bundle / "PLAN.json"
    plan = json.loads(path.read_bytes())
    plan["schema"] = "foreign.ingress.v1"
    path.write_text(json.dumps(plan))
    with mock.patch.object(installer, "read_go", side_effect=AssertionError("unknown strict reader")), \
            mock.patch.object(installer, "read_retained_go", side_effect=AssertionError("unknown retained reader")), \
            pytest.raises(ValueError, match="unsupported completed Go ingress schema"):
        installer._completed_go_for_service(case.go_bundle)


def test_completed_go_service_owner_never_falls_back_from_invalid_intact_plan(go_owner):
    case = go_owner
    path = case.go_bundle / "PLAN.json"
    plan = json.loads(path.read_bytes())
    del plan["target_generation"]
    path.write_text(json.dumps(plan))
    with mock.patch.object(installer, "read_retained_go", side_effect=AssertionError("invalid strict plan fell back")), \
            pytest.raises(ValueError, match="invalid Go ingress plan"):
        installer._completed_go_for_service(case.go_bundle)
