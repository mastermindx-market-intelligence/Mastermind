#!/usr/bin/env python3
"""Finite native ingress installation and paired upgrade; no worker/process control.

prepare writes only a review bundle. phase1 changes pool and the fabric_task CLI
branch. phase2 changes the flat remote controller only after an existing owner
supplies a bound legacy-producer reconciliation receipt. The receipt is an
explicit operational prerequisite, not process/lifecycle authority invented here.
The closed paired upgrade preserves that phase-one epoch and the flat remote entry.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
import uuid

# Reuse the installed Studio Direct consumer census; it is the single owner
# of pin observation, rather than duplicating a private-account registry here.
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from ops.fabric_launch import install as studio_consumer_owner

import native_generation as generation
import build_review_stage as stage_builder

_HISTORICAL_LAUNCHER = Path(__file__).resolve().parent / "preimages/native_generation_75330d.py"

SCHEMA = "native-ingress-bootstrap.v1"
DRAIN_SCHEMA = "native-ingress-legacy-producers-reconciled.v1"
BRIDGE_MARKER = "NATIVE_GENERATION_CLI_BRIDGE_V1"
UPGRADE_SCHEMA = "native-ingress-paired-launcher-upgrade.v1"
UPGRADE_FROM = "8bc1153289914d793264ca5d684eb7206f2b5d38fcbaadc3de9f9cc04a9baa88"
UPGRADE_TO = "d044c24940df13d24ff6241f0da9cec3dc24d90dd60604a08c82e0ad8613586c"
UPGRADE_MANIFEST = "6ac208bbd80f706931b11e8147a879f6e3ced6fe704cde7b9f15e1c098e37ee4"


def _upgrade_pointer(value):
    if (type(value) is not dict or set(value) != {"schema", "generation", "sequence", "previous"}
            or value["schema"] != generation.POINTER_SCHEMA
            or type(value["sequence"]) is not int or value["sequence"] < 1
            or type(value["generation"]) is not str
            or not generation.HEX.fullmatch(value["generation"])
            or (value["previous"] is not None and
                (type(value["previous"]) is not str or not generation.HEX.fullmatch(value["previous"])))):
        raise ValueError("invalid upgrade selection snapshot")


def _upgrade_base(original):
    original = Path(original)
    if not original.is_absolute() or original.resolve(strict=True) != original:
        raise ValueError("canonical original installation bundle required")
    original, base = read_plan(original)
    store = Path(base["store"])
    receipts = store / "bootstrap"
    generation.require(receipts, stat.S_ISDIR, 0o700)
    receipt_path = receipts / (base["digest"] + ".phase1.json")
    generation.require(receipt_path, stat.S_ISREG, 0o600)
    receipt = generation.unique_json(generation.regular_bytes(receipt_path))
    expected = {"schema": SCHEMA, "phase": 1, "plan_digest": base["digest"],
                "initial_generation": base["initial_generation"],
                "bridged": ["pool", "task"], "remote": "legacy"}
    if receipt != expected:
        raise ValueError("original paired installation receipt mismatch")
    if any(os.path.lexists(receipts / (base["digest"] + suffix))
           for suffix in (".rollback.json", ".phase2.json")):
        raise ValueError("original installation is not the legacy-remote phase-one state")
    old_raw = generation.regular_bytes(original / "native_generation.py")
    if base["launcher_digest"] != UPGRADE_FROM or generation.digest(old_raw) != UPGRADE_FROM:
        raise ValueError("unsupported original launcher")
    old_fragment = b'or parts[1] in {"yes", "host_pull_probe.template"})'
    new_fragment = (b'or parts[1] in {"yes", "host_pull_probe.template",\n'
                    b'                        "paid_pyyaml_6_0_3.zip", "paid_pyyaml_provenance.json"})')
    if old_raw.count(old_fragment) != 1:
        raise ValueError("original launcher allowlist differs")
    new_raw = old_raw.replace(old_fragment, new_fragment)
    if (generation.digest(new_raw) != UPGRADE_TO
            or _successor_sources()[0] != new_raw):
        raise ValueError("protected launcher must differ only by the reviewed two names")
    old_launcher = Path(base["launcher_path"])
    generation.require(old_launcher, stat.S_ISREG, 0o555)
    if generation.regular_bytes(old_launcher) != old_raw:
        raise ValueError("original installed launcher differs")
    for name in ("pool", "task"):
        wanted = (shell_bridge(Path(base["python"]), old_launcher, store, "pool")
                  if name == "pool" else task_bridge(
                      generation.regular_bytes(original / "task.original"),
                      Path(base["python"]), old_launcher, store))
        if generation.digest(wanted) != base["entries"][name]["bridge"]:
            raise ValueError("original bridge derivation differs")
    return original, base, new_raw


def _upgrade_plan(original, target, previous):
    original, base, new_raw = _upgrade_base(original)
    _upgrade_pointer(previous)
    store = Path(base["store"])
    _, old_meta = generation.verify(store, previous["generation"])
    # These two names are the ONLY difference between the pinned verifiers.
    if {"ext/paid_pyyaml_6_0_3.zip", "ext/paid_pyyaml_provenance.json"} & set(old_meta["files"]):
        raise ValueError("old launcher cannot verify the prior selection")
    _, target_meta = generation.verify(store, target)
    manifest_raw = (json.dumps(target_meta["files"], sort_keys=True, indent=2) + "\n").encode()
    if len(target_meta["files"]) != 95 or generation.digest(manifest_raw) != UPGRADE_MANIFEST:
        raise ValueError("target is not the reviewed 95-member closure")
    launcher = store / "launchers" / (UPGRADE_TO + ".py")
    payloads = {"native_generation.py": new_raw}
    entries = {}
    for name in ("pool", "task", "remote"):
        entry = base["entries"][name]
        row = {"target": entry["target"], "mode": entry["mode"],
               "previous": entry["preimage"] if name == "remote" else entry["bridge"]}
        if name != "remote":
            raw = (shell_bridge(Path(base["python"]), launcher, store, "pool")
                   if name == "pool" else task_bridge(
                       generation.regular_bytes(original / "task.original"),
                       Path(base["python"]), launcher, store))
            payloads[name + ".bridge"] = raw
            row["bridge"] = generation.digest(raw)
        entries[name] = row
    plan = {"schema": UPGRADE_SCHEMA, "original_bundle": str(original),
            "bootstrap_digest": base["digest"], "store": str(store),
            "expected_selection": previous, "target_generation": target,
            "from_launcher": UPGRADE_FROM, "to_launcher": UPGRADE_TO,
            "manifest_sha256": UPGRADE_MANIFEST, "entries": entries}
    plan["digest"] = generation.digest(generation.canonical(plan))
    return plan, payloads


def _upgrade_entries(plan, *, partial=False, complete=False):
    mutable = {"pool", "task", "go"} if plan["schema"] == GO_SCHEMA else {"pool", "task"}
    for name, entry in plan["entries"].items():
        target = Path(entry["target"])
        if not target.is_absolute() or target.parent.resolve(strict=True) != target.parent:
            raise ValueError("canonical ingress parent required")
        generation.require(target.parent, stat.S_ISDIR)
        generation.require(target, stat.S_ISREG, entry["mode"])
        observed = generation.digest(generation.regular_bytes(target))
        allowed = {entry["previous"]}
        if name in mutable:
            if complete:
                allowed = {entry["bridge"]}
            elif partial:
                allowed.add(entry["bridge"])
        if observed not in allowed:
            raise ValueError("upgrade ingress preimage refused: " + name)


def prepare_upgrade(original, target, output):
    """Prepare one closed 8bc->d044 transition; never rewrite its old epoch."""
    original, base, _ = _upgrade_base(original)
    store = Path(base["store"])
    output = Path(output).absolute()
    generation.require(output.parent, stat.S_ISDIR)
    if (output.parent.resolve(strict=True) != output.parent
            or output.is_relative_to(store.parent) or os.path.lexists(output)):
        raise ValueError("fresh external canonical upgrade bundle required")
    with generation.publication_lock(store):
        plan, payloads = _upgrade_plan(original, target, generation.current(store))
        _upgrade_entries(plan)
        if os.path.lexists(store / "bootstrap/.paired-launcher-upgrade.json"):
            raise ValueError("paired upgrade already has an original transaction")
        output.mkdir(mode=0o700)
        for name, raw in payloads.items():
            generation.atomic_bytes(output / name, raw, 0o600)
        generation.atomic_bytes(output / "PLAN.json", generation.canonical(plan) + b"\n", 0o600)
    return plan


def read_upgrade(bundle):
    bundle = Path(bundle).absolute()
    if bundle.resolve(strict=True) != bundle:
        raise ValueError("canonical upgrade bundle required")
    generation.require(bundle, stat.S_ISDIR, 0o700)
    generation.require(bundle / "PLAN.json", stat.S_ISREG, 0o600)
    plan = generation.unique_json(generation.regular_bytes(bundle / "PLAN.json"))
    fields = {"schema", "original_bundle", "bootstrap_digest", "store",
              "expected_selection", "target_generation", "from_launcher",
              "to_launcher", "manifest_sha256", "entries", "digest"}
    if (type(plan) is not dict or set(plan) != fields or plan.get("schema") != UPGRADE_SCHEMA
            or type(plan["original_bundle"]) is not str):
        raise ValueError("invalid paired upgrade plan")
    expected, payloads = _upgrade_plan(plan["original_bundle"], plan["target_generation"],
                                       plan["expected_selection"])
    if plan != expected or {p.name for p in bundle.iterdir()} != {"PLAN.json", *payloads}:
        raise ValueError("upgrade plan or artifact set differs")
    for name, raw in payloads.items():
        generation.require(bundle / name, stat.S_ISREG, 0o600)
        if generation.regular_bytes(bundle / name) != raw:
            raise ValueError("upgrade payload differs: " + name)
    return plan, payloads


def upgrade(bundle):
    """Finish only this retained transaction; never infer permission to retry work."""
    plan, payloads = read_upgrade(bundle)
    store = Path(plan["store"])
    with generation.publication_lock(store):
        # Requalify the authentic old epoch and target while holding the owner lock.
        expected, _ = _upgrade_plan(plan["original_bundle"], plan["target_generation"],
                                     plan["expected_selection"])
        if expected != plan:
            raise ValueError("upgrade inputs changed")
        intent_path = store / "bootstrap/.paired-launcher-upgrade.json"
        intent = {"schema": UPGRADE_SCHEMA, "plan_digest": plan["digest"],
                  "bootstrap_digest": plan["bootstrap_digest"]}
        exists = os.path.lexists(intent_path)
        if exists:
            generation.require(intent_path, stat.S_ISREG, 0o600)
            if generation.unique_json(generation.regular_bytes(intent_path)) != intent:
                raise ValueError("foreign paired upgrade transaction")
        previous = plan["expected_selection"]
        selected = {"schema": generation.POINTER_SCHEMA,
                    "generation": plan["target_generation"],
                    "previous": previous["generation"], "sequence": previous["sequence"] + 1}
        receipt = {"schema": UPGRADE_SCHEMA, "plan_digest": plan["digest"],
                   "bootstrap_digest": plan["bootstrap_digest"],
                   "previous_selection": previous, "selection": selected,
                   "bridged": ["pool", "task"], "remote": "legacy"}
        receipt_path = store / "bootstrap" / (plan["digest"] + ".upgrade.json")
        current = generation.current(store)
        if os.path.lexists(receipt_path):
            generation.require(receipt_path, stat.S_ISREG, 0o600)
            if (not exists or current != selected
                    or generation.unique_json(generation.regular_bytes(receipt_path)) != receipt):
                raise ValueError("completed upgrade no longer matches current state")
            _upgrade_entries(plan, complete=True)
            launcher = store / "launchers" / (UPGRADE_TO + ".py")
            generation.require(launcher, stat.S_ISREG, 0o555)
            if generation.regular_bytes(launcher) != payloads["native_generation.py"]:
                raise ValueError("completed launcher differs")
            return receipt
        if current != previous and not (exists and current == selected):
            raise ValueError("upgrade selection compare-and-swap refused")
        if current == selected:
            # Selection follows verified launcher and both bridges. Their loss
            # cannot be an interruption of this transaction; never repair it.
            _upgrade_entries(plan, complete=True)
            launcher = store / "launchers" / (UPGRADE_TO + ".py")
            generation.require(launcher, stat.S_ISREG, 0o555)
            if generation.regular_bytes(launcher) != payloads["native_generation.py"]:
                raise ValueError("selected launcher differs")
            _record_once(receipt_path, receipt)
            return receipt
        _upgrade_entries(plan, partial=exists)
        if not exists:
            _record_once(intent_path, intent)  # durable BEFORE any ingress mutation
        directory = store / "launchers"
        generation.require(directory, stat.S_ISDIR, 0o700)
        launcher = directory / (UPGRADE_TO + ".py")
        if os.path.lexists(launcher):
            generation.require(launcher, stat.S_ISREG, 0o555)
            if generation.regular_bytes(launcher) != payloads["native_generation.py"]:
                raise ValueError("published upgrade launcher differs")
        else:
            generation.atomic_bytes(launcher, payloads["native_generation.py"], 0o555)
        for name in ("pool", "task"):
            _upgrade_entries(plan, partial=True)
            entry = plan["entries"][name]
            if generation.digest(generation.regular_bytes(entry["target"])) != entry["bridge"]:
                generation.atomic_bytes(Path(entry["target"]), payloads[name + ".bridge"], entry["mode"])
        _upgrade_entries(plan, complete=True)
        if generation.current(store) == previous:
            actual = generation._select_locked(store, plan["target_generation"], previous["generation"])
            if actual != selected:
                raise ValueError("upgrade selection readback differs")
        elif generation.current(store) != selected:
            raise ValueError("upgrade selection changed during transaction")
        _record_once(receipt_path, receipt)
        return receipt


SUCCESSOR_SCHEMA = "native-ingress-launcher-successor.v1"
SUCCESSOR_FROM = "d044c24940df13d24ff6241f0da9cec3dc24d90dd60604a08c82e0ad8613586c"
SUCCESSOR_TO = "43e814339a16582e2205f12117e1f17c40dce2e42a9c52d815a37c043e772e1b"
SUCCESSOR_MANIFEST = "0be933110a192f3855359eb72bfdfddb38e6dd581ed1d495d0caf7ea8a7a6aec"
SUCCESSOR_MEMBER_COUNT = 102
_SUCCESSOR_PLAN_FIELDS = frozenset({
    "schema", "prior_upgrade_bundle", "prior_upgrade_digest", "bootstrap_digest",
    "store", "expected_selection", "target_generation", "from_launcher",
    "to_launcher", "manifest_sha256", "entries", "digest",
})
GO_SCHEMA = "native-ingress-go-application.v1"
GO_BRIDGE_MARKER = "NATIVE_GENERATION_GO_IN_PROCESS_V1"
_GO_PLAN_FIELDS = frozenset({
    "schema", "prior_successor_bundle", "prior_successor_digest", "bootstrap_digest",
    "store", "expected_selection", "target_generation", "from_launcher",
    "to_launcher", "manifest_sha256", "component_bundle", "component_sha256",
    "entries", "digest",
})


def _successor_directory(path):
    if not isinstance(path, (str, Path)):
        raise ValueError("invalid successor artifact path")
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("canonical successor artifact directory required")
    generation.require(path, stat.S_ISDIR, 0o700)
    return path


def _successor_json(path):
    generation.require(path, stat.S_ISREG, 0o600)
    return generation.unique_json(generation.regular_bytes(path, 65536))


def _successor_sources():
    new = generation.regular_bytes(_HISTORICAL_LAUNCHER)
    addition = (b'    # One vetted flat plist. Not a suffix rule and not a directory walk.\n'
                b'    if relative == "ext/host_pull_launchd.plist.template":\n'
                b'        return\n')
    if generation.digest(new) != SUCCESSOR_TO or new.count(addition) != 1:
        raise ValueError("successor launcher source differs")
    old = new.replace(addition, b"", 1)
    if generation.digest(old) != SUCCESSOR_FROM:
        raise ValueError("successor launcher is not the exact fixed-name extension")
    return old, new


def _successor_origin(prior_upgrade):
    """Authenticate the completed old epoch; never replay or rewrite it."""
    prior_upgrade = _successor_directory(prior_upgrade)
    prior = _successor_json(prior_upgrade / "PLAN.json")
    old_fields = {"schema", "original_bundle", "bootstrap_digest", "store",
                  "expected_selection", "target_generation", "from_launcher",
                  "to_launcher", "manifest_sha256", "entries", "digest"}
    if type(prior) is not dict or set(prior) != old_fields or prior["schema"] != UPGRADE_SCHEMA:
        raise ValueError("invalid predecessor upgrade plan")
    if type(prior["original_bundle"]) is not str:
        raise ValueError("invalid predecessor original bundle")
    original = _successor_directory(prior["original_bundle"])
    _, base = read_plan(original)
    original_fields = {"schema", "bootstrap_epoch", "store", "initial_generation",
                       "stable_ext", "launcher_digest", "launcher_path", "python",
                       "entries", "flat_code_preimages", "flat_code_absent", "digest"}
    if set(base) != original_fields or base["launcher_digest"] != UPGRADE_FROM:
        raise ValueError("successor requires the retained original bootstrap")
    if {p.name for p in original.iterdir()} != {
            "PLAN.json", "native_generation.py", "pool.original", "pool.bridge",
            "task.original", "task.bridge", "remote.original", "remote.bridge"}:
        raise ValueError("original bootstrap artifact set differs")
    for path in original.iterdir():
        generation.require(path, stat.S_ISREG, 0o600)
    old, new = _successor_sources()
    raw = generation.regular_bytes(original / "native_generation.py")
    old_fragment = b'or parts[1] in {"yes", "host_pull_probe.template"})'
    new_fragment = (b'or parts[1] in {"yes", "host_pull_probe.template",\n'
                    b'                        "paid_pyyaml_6_0_3.zip", "paid_pyyaml_provenance.json"})')
    if (generation.digest(raw) != UPGRADE_FROM or raw.count(old_fragment) != 1
            or raw.replace(old_fragment, new_fragment, 1) != old):
        raise ValueError("original launcher lineage differs")
    store = Path(base["store"])
    receipts = store / "bootstrap"
    generation.require(receipts, stat.S_ISDIR, 0o700)
    phase1 = {"schema": SCHEMA, "phase": 1, "plan_digest": base["digest"],
              "initial_generation": base["initial_generation"],
              "bridged": ["pool", "task"], "remote": "legacy"}
    if _successor_json(receipts / (base["digest"] + ".phase1.json")) != phase1:
        raise ValueError("original phase-one receipt differs")
    if any(os.path.lexists(receipts / (base["digest"] + suffix))
           for suffix in (".rollback.json", ".phase2.json")):
        raise ValueError("successor requires the legacy-remote phase-one epoch")
    _, initial_meta = generation.verify(store, base["initial_generation"])
    unsupported_original = {"ext/paid_pyyaml_6_0_3.zip", "ext/paid_pyyaml_provenance.json",
                            "ext/host_pull_launchd.plist.template"}
    if unsupported_original & set(initial_meta["files"]):
        raise ValueError("original bootstrap selection exceeds its original launcher")
    _upgrade_pointer(prior["expected_selection"])
    _, before_meta = generation.verify(store, prior["expected_selection"]["generation"])
    if {"ext/paid_pyyaml_6_0_3.zip", "ext/paid_pyyaml_provenance.json",
            "ext/host_pull_launchd.plist.template"} & set(before_meta["files"]):
        raise ValueError("historical prior selection exceeds its original launcher")
    _, target_meta = generation.verify(store, prior["target_generation"])
    manifest = (json.dumps(target_meta["files"], sort_keys=True, indent=2) + "\n").encode()
    if len(target_meta["files"]) != 95 or generation.digest(manifest) != UPGRADE_MANIFEST:
        raise ValueError("historical target is not the reviewed 95-member closure")
    payloads = {"native_generation.py": old}
    entries = {}
    old_launcher = store / "launchers" / (SUCCESSOR_FROM + ".py")
    for name in ("pool", "task", "remote"):
        entry = base["entries"][name]
        bootstrap_bridge = (shell_bridge(Path(base["python"]), Path(base["launcher_path"]), store, "pool")
                            if name == "pool" else task_bridge(
                                generation.regular_bytes(original / "task.original"),
                                Path(base["python"]), Path(base["launcher_path"]), store))
        if name != "remote" and generation.digest(bootstrap_bridge) != entry["bridge"]:
            raise ValueError("original bridge derivation differs")
        row = {"target": entry["target"], "mode": entry["mode"],
               "previous": entry["preimage"] if name == "remote" else entry["bridge"]}
        if name != "remote":
            bridge = (shell_bridge(Path(base["python"]), old_launcher, store, "pool")
                      if name == "pool" else task_bridge(
                          generation.regular_bytes(original / "task.original"),
                          Path(base["python"]), old_launcher, store))
            payloads[name + ".bridge"] = bridge
            row["bridge"] = generation.digest(bridge)
        entries[name] = row
    expected = {"schema": UPGRADE_SCHEMA, "original_bundle": str(original),
                "bootstrap_digest": base["digest"], "store": str(store),
                "expected_selection": prior["expected_selection"],
                "target_generation": prior["target_generation"],
                "from_launcher": UPGRADE_FROM, "to_launcher": SUCCESSOR_FROM,
                "manifest_sha256": UPGRADE_MANIFEST, "entries": entries}
    expected["digest"] = generation.digest(generation.canonical(expected))
    if prior != expected or {p.name for p in prior_upgrade.iterdir()} != {"PLAN.json", *payloads}:
        raise ValueError("predecessor upgrade derivation differs")
    for name, wanted in payloads.items():
        generation.require(prior_upgrade / name, stat.S_ISREG, 0o600)
        if generation.regular_bytes(prior_upgrade / name) != wanted:
            raise ValueError("predecessor payload differs")
    for path, wanted in ((Path(base["launcher_path"]), raw), (old_launcher, old)):
        generation.require(path, stat.S_ISREG, 0o555)
        if generation.regular_bytes(path) != wanted:
            raise ValueError("retained predecessor launcher differs")
    intent = {"schema": UPGRADE_SCHEMA, "plan_digest": prior["digest"],
              "bootstrap_digest": base["digest"]}
    selected = {"schema": generation.POINTER_SCHEMA, "generation": prior["target_generation"],
                "previous": prior["expected_selection"]["generation"],
                "sequence": prior["expected_selection"]["sequence"] + 1}
    receipt = {"schema": UPGRADE_SCHEMA, "plan_digest": prior["digest"],
               "bootstrap_digest": base["digest"],
               "previous_selection": prior["expected_selection"], "selection": selected,
               "bridged": ["pool", "task"], "remote": "legacy"}
    if (_successor_json(receipts / ".paired-launcher-upgrade.json") != intent
            or _successor_json(receipts / (prior["digest"] + ".upgrade.json")) != receipt):
        raise ValueError("completed predecessor intent or receipt differs")
    return prior_upgrade, prior, original, base, new, selected


def _successor_plan(prior_upgrade, target, previous):
    if type(target) is not str or not generation.HEX.fullmatch(target):
        raise ValueError("invalid successor target identity")
    prior_upgrade, prior, original, base, new, completed = _successor_origin(prior_upgrade)
    _upgrade_pointer(previous)
    if previous["sequence"] < completed["sequence"] or (
            previous["sequence"] == completed["sequence"] and previous != completed):
        raise ValueError("successor selection predates the completed predecessor")
    store = Path(base["store"])
    _, before = generation.verify(store, previous["generation"])
    if "ext/host_pull_launchd.plist.template" in before["files"]:
        raise ValueError("old launcher cannot qualify the current selection")
    _, after = generation.verify(store, target)
    manifest = (json.dumps(after["files"], sort_keys=True, indent=2) + "\n").encode()
    if (len(after["files"]) != SUCCESSOR_MEMBER_COUNT
            or generation.digest(manifest) != SUCCESSOR_MANIFEST
            or "ext/host_pull_launchd.plist.template" not in after["files"]):
        raise ValueError("target is not the reviewed successor closure")
    launcher = store / "launchers" / (SUCCESSOR_TO + ".py")
    entries = {}
    payloads = {"native_generation.py": new}
    for name in ("pool", "task", "remote"):
        entry = prior["entries"][name]
        row = {"target": entry["target"], "mode": entry["mode"],
               "previous": entry["previous"] if name == "remote" else entry["bridge"]}
        if name != "remote":
            bridge = (shell_bridge(Path(base["python"]), launcher, store, "pool")
                      if name == "pool" else task_bridge(
                          generation.regular_bytes(original / "task.original"),
                          Path(base["python"]), launcher, store))
            payloads[name + ".bridge"] = bridge
            row["bridge"] = generation.digest(bridge)
        entries[name] = row
    plan = {"schema": SUCCESSOR_SCHEMA, "prior_upgrade_bundle": str(prior_upgrade),
            "prior_upgrade_digest": prior["digest"], "bootstrap_digest": base["digest"],
            "store": str(store), "expected_selection": previous, "target_generation": target,
            "from_launcher": SUCCESSOR_FROM, "to_launcher": SUCCESSOR_TO,
            "manifest_sha256": SUCCESSOR_MANIFEST, "entries": entries}
    plan["digest"] = generation.digest(generation.canonical(plan))
    return plan, payloads


def prepare_successor(prior_upgrade, target, output):
    _, _, _, base, _, _ = _successor_origin(prior_upgrade)
    store = Path(base["store"])
    output = Path(output).absolute()
    generation.require(output.parent, stat.S_ISDIR)
    if (output.parent.resolve(strict=True) != output.parent
            or output.is_relative_to(store.parent) or os.path.lexists(output)):
        raise ValueError("fresh external canonical successor bundle required")
    with generation.publication_lock(store):
        plan, payloads = _successor_plan(prior_upgrade, target, generation.current(store))
        _upgrade_entries(plan)
        if os.path.lexists(store / "bootstrap/.launcher-successor-v1.json"):
            raise ValueError("successor already has an original transaction")
        output.mkdir(mode=0o700)
        for name, raw in payloads.items():
            generation.atomic_bytes(output / name, raw, 0o600)
        generation.atomic_bytes(output / "PLAN.json", generation.canonical(plan) + b"\n", 0o600)
    return plan


def read_successor(bundle):
    bundle = _successor_directory(bundle)
    plan = _successor_json(bundle / "PLAN.json")
    if type(plan) is not dict or set(plan) != _SUCCESSOR_PLAN_FIELDS or plan["schema"] != SUCCESSOR_SCHEMA:
        raise ValueError("invalid launcher successor plan")
    expected, payloads = _successor_plan(plan["prior_upgrade_bundle"], plan["target_generation"],
                                        plan["expected_selection"])
    if plan != expected or {p.name for p in bundle.iterdir()} != {"PLAN.json", *payloads}:
        raise ValueError("successor plan or artifact set differs")
    for name, raw in payloads.items():
        generation.require(bundle / name, stat.S_ISREG, 0o600)
        if generation.regular_bytes(bundle / name) != raw:
            raise ValueError("successor payload differs")
    return plan, payloads



def _require_successor_launcher(plan, payloads):
    launcher = Path(plan["store"]) / "launchers" / (plan["to_launcher"] + ".py")
    generation.require(launcher, stat.S_ISREG, 0o555)
    if generation.regular_bytes(launcher) != payloads["native_generation.py"]:
        raise ValueError("published successor launcher differs")


def apply_successor(bundle):
    """Advance only this retained source transition; no process or service control."""
    return _apply_ingress_transition(bundle, SUCCESSOR_SCHEMA)


def _transition_records(plan):
    schema = plan["schema"]
    if schema == SUCCESSOR_SCHEMA:
        prior_key = "prior_upgrade_digest"
        intent_name, suffix, mutable = ".launcher-successor-v1.json", ".successor.json", ("pool", "task")
    elif schema == GO_SCHEMA:
        prior_key = "prior_successor_digest"
        intent_name, suffix, mutable = ".go-application-ingress-v1.json", ".go.json", ("pool", "task", "go")
    else:
        raise ValueError("unsupported ingress transition")
    previous = plan["expected_selection"]
    selected = {"schema": generation.POINTER_SCHEMA, "generation": plan["target_generation"],
                "previous": previous["generation"], "sequence": previous["sequence"] + 1}
    intent = {"schema": schema, "plan_digest": plan["digest"],
              prior_key: plan[prior_key], "bootstrap_digest": plan["bootstrap_digest"]}
    receipt = dict(intent, previous_selection=previous, selection=selected,
        from_launcher=plan["from_launcher"], to_launcher=plan["to_launcher"],
        manifest_sha256=plan["manifest_sha256"], bridged=list(mutable), remote="legacy")
    return intent_name, suffix, mutable, intent, selected, receipt


def _apply_ingress_transition(bundle, expected_schema, *, reconcile_only=False):
    # One finite mutation owner for the two CLOSED transition shapes. This is
    # not a generic installer, an execution retry or a new service lifecycle.
    if expected_schema == SUCCESSOR_SCHEMA:
        reader = read_successor
    elif expected_schema == GO_SCHEMA:
        reader = read_go
    else:
        raise ValueError("unsupported ingress transition")
    plan, payloads = reader(bundle)
    if plan["schema"] != expected_schema:
        raise ValueError("ingress transition schema differs")
    store = Path(plan["store"])
    with generation.publication_lock(store):
        # Full retained chain, source and target qualification at the actual write boundary.
        again, checked = reader(bundle)
        if again != plan or checked != payloads:
            raise ValueError("successor inputs changed")
        intent_name, suffix, mutable, intent, selected, receipt = _transition_records(plan)
        intent_path = store / "bootstrap" / intent_name
        exists = os.path.lexists(intent_path)
        if exists and _successor_json(intent_path) != intent:
            raise ValueError("foreign launcher successor transaction")
        previous = plan["expected_selection"]
        receipt_path = store / "bootstrap" / (plan["digest"] + suffix)
        launcher = store / "launchers" / (plan["to_launcher"] + ".py")
        current = generation.current(store)
        completed = os.path.lexists(receipt_path)
        if completed or current == selected:
            if not exists or current != selected or (completed and _successor_json(receipt_path) != receipt):
                raise ValueError("completed successor no longer matches current state")
            _upgrade_entries(plan, complete=True)
            _require_successor_launcher(plan, payloads)
            if not completed:
                _record_once(receipt_path, receipt)
            return receipt
        if current != previous:
            raise ValueError("successor selection compare-and-swap refused")
        _upgrade_entries(plan, partial=exists)
        if reconcile_only:
            raise ValueError("original ingress transition is not committed; reconciliation made no changes")
        _require_studio_consumer_pin(plan, "bridge")
        if not exists:
            _record_once(intent_path, intent)
        directory = store / "launchers"
        generation.require(directory, stat.S_ISDIR, 0o700)
        if os.path.lexists(launcher):
            generation.require(launcher, stat.S_ISREG, 0o555)
            if generation.regular_bytes(launcher) != payloads["native_generation.py"]:
                raise ValueError("published successor launcher differs")
        else:
            generation.atomic_bytes(launcher, payloads["native_generation.py"], 0o555)
        _require_successor_launcher(plan, payloads)
        for name in mutable:
            if reader(bundle) != (plan, payloads):
                raise ValueError("successor inputs changed before ingress replacement")
            _upgrade_entries(plan, partial=True)
            if generation.current(store) != previous:
                raise ValueError("successor selection changed before ingress replacement")
            if name == "pool":
                _require_studio_consumer_pin(plan, "bridge")
            _require_successor_launcher(plan, payloads)
            entry = plan["entries"][name]
            if generation.digest(generation.regular_bytes(entry["target"])) != entry["bridge"]:
                generation.atomic_bytes(Path(entry["target"]), payloads[name + ".bridge"], entry["mode"])
        if reader(bundle) != (plan, payloads):
            raise ValueError("successor inputs changed before commit")
        _upgrade_entries(plan, complete=True)
        if generation.current(store) != previous:
            raise ValueError("successor selection changed before commit")
        _require_successor_launcher(plan, payloads)
        if generation._select_locked(store, plan["target_generation"], previous["generation"]) != selected:
            raise ValueError("successor selection readback differs")
        _record_once(receipt_path, receipt)
        return receipt


def _completed_successor(bundle):
    """Authenticate retained history, independent of CURRENT and live bridges."""
    bundle = _successor_directory(bundle)
    plan, payloads = read_successor(bundle)
    intent_name, suffix, _, intent, selected, receipt = _transition_records(plan)
    receipts = Path(plan["store"]) / "bootstrap"
    if (_successor_json(receipts / intent_name) != intent
            or _successor_json(receipts / (plan["digest"] + suffix)) != receipt):
        raise ValueError("completed successor history differs")
    _require_successor_launcher(plan, payloads)
    _, _, original, base, _, _ = _successor_origin(plan["prior_upgrade_bundle"])
    return bundle, plan, original, base, selected


def _go_file(path):
    info = generation.require(path, stat.S_ISREG)
    if info.st_nlink != 1 or info.st_mode & 0o022:
        raise ValueError("Go component file custody differs")
    return generation.regular_bytes(path)


def _go_component(bundle, stable_ext, target_files):
    bundle = Path(bundle)
    if not bundle.is_absolute() or bundle.resolve(strict=True) != bundle:
        raise ValueError("canonical Go component bundle required")
    generation.require(bundle, stat.S_ISDIR)
    if {p.name for p in bundle.iterdir()} != {"component.json", "source-go_shim.py", "go_shim.py"}:
        raise ValueError("Go component artifact set differs")
    raw = _go_file(bundle / "component.json")
    record = generation.unique_json(raw)
    root = Path(stage_builder.__file__).resolve().parent.parent
    preimage = _go_file(root / "source/go_shim.py")
    handler = _go_file(root / "candidate/go_shim.py")
    entry = _go_file(root / "candidate/native_go_entry.py")
    if generation.digest(preimage) != stage_builder.GO_INSTALLED_PREIMAGE:
        raise ValueError("Go original installed source differs")
    dependencies = {}
    for name in stage_builder.GO_APPLICATION_DEPENDENCIES:
        data = _go_file(root / "candidate" / name)
        dependencies[name] = {"sha256": generation.digest(data), "bytes": len(data), "source": "candidate/" + name}
    expected = {"schema": "native-external-go-component.v1", "component": "go_application_handler",
        "destination_relative_to_stable_ext": "go_shim/go_shim.py", "stable_ext": str(stable_ext),
        "installed_preimage_sha256": stage_builder.GO_INSTALLED_PREIMAGE,
        "candidate_sha256": generation.digest(handler), "candidate_bytes": len(handler),
        "candidate_source": "candidate/go_shim.py", "dependencies": dependencies,
        "native_stage_dependencies": {name: row["sha256"] for name, row in dependencies.items()},
        "preimage_source_ref": "https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6646945527",
        "installation_state": "HELD_REQUIRES_PROTECTED_RELEASE_AND_EXISTING_OWNER_INSTALLATION"}
    if (record != expected or _go_file(bundle / "source-go_shim.py") != preimage
            or _go_file(bundle / "go_shim.py") != handler):
        raise ValueError("Go component is not the exact reviewed source")
    manifest_raw = _go_file(bundle.parent / "native-manifest.json")
    manifest = generation.unique_json(manifest_raw)
    if manifest != target_files:
        raise ValueError("Go target differs from captured native manifest")
    base = {key: value for key, value in manifest.items()
            if key not in {generation.GO_ENTRY, generation.GO_HANDLER}}
    base_raw = (json.dumps(base, sort_keys=True, indent=2) + "\n").encode()
    if (generation.digest(base_raw) != stage_builder.GO_BASE_MANIFEST_SHA256
            or set(manifest) != set(base) | {generation.GO_ENTRY, generation.GO_HANDLER}
            or manifest[generation.GO_HANDLER] != generation.digest(handler)
            or manifest[generation.GO_ENTRY] != generation.digest(entry)
            or any(manifest.get("ext/" + name) != row["sha256"] for name, row in dependencies.items())):
        raise ValueError("Go target is not the closed reviewed B and C composition")
    for relative, wanted in manifest.items():
        if generation.digest(_go_file(bundle.parent / "native-code-stage" / relative)) != wanted:
            raise ValueError("captured Go stage changed")
    return generation.digest(raw), generation.digest(manifest_raw), preimage


def go_bridge(original, launcher, store):
    """Preserve imports and original OS argv; enter verified Go in process."""
    if generation.digest(original) != stage_builder.GO_INSTALLED_PREIMAGE:
        raise ValueError("Go bridge requires the original installed handler")
    launcher = Path(launcher)
    if launcher.suffix != ".py" or not generation.HEX.fullmatch(launcher.stem):
        raise ValueError("Go bridge requires a content-addressed launcher")
    text = original.decode()
    if GO_BRIDGE_MARKER in text:
        raise ValueError("Go source is already bridged")
    module = ast.parse(text)
    first_business_line = 0
    for index, item in enumerate(module.body):
        if ((index == 0 and isinstance(item, ast.Expr)
                and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str))
                or isinstance(item, ast.ImportFrom) and item.module == "__future__"):
            first_business_line = item.end_lineno
            continue
        break
    branch = ("\n# " + GO_BRIDGE_MARKER + "\nif __name__ == '__main__':\n"
        "    import importlib.util as _native_go_import\n"
        "    import sys as _native_go_sys\n"
        "    import os as _native_go_os\n"
        "    import stat as _native_go_stat\n"
        "    import hashlib as _native_go_hash\n"
        f"    _native_go_path = {str(launcher)!r}\n"
        "    _native_go_fd = _native_go_os.open(_native_go_path, _native_go_os.O_RDONLY | _native_go_os.O_NOFOLLOW | _native_go_os.O_NONBLOCK)\n"
        "    try:\n"
        "        _native_go_info = _native_go_os.fstat(_native_go_fd)\n"
        "        if (not _native_go_stat.S_ISREG(_native_go_info.st_mode) or _native_go_info.st_uid != _native_go_os.geteuid()\n"
        "                or _native_go_stat.S_IMODE(_native_go_info.st_mode) != 0o555 or _native_go_info.st_nlink != 1\n"
        "                or not 0 < _native_go_info.st_size <= 16 * 1024 * 1024):\n"
        "            raise SystemExit('native Go launcher custody refused')\n"
        "        with _native_go_os.fdopen(_native_go_os.dup(_native_go_fd), 'rb') as _native_go_file:\n"
        "            _native_go_raw = _native_go_file.read(_native_go_info.st_size + 1)\n"
        "        _native_go_identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)\n"
        "        if (len(_native_go_raw) != _native_go_info.st_size\n"
        "                or _native_go_identity(_native_go_os.fstat(_native_go_fd)) != _native_go_identity(_native_go_info)\n"
        "                or _native_go_identity(_native_go_os.lstat(_native_go_path)) != _native_go_identity(_native_go_info)\n"
        f"                or _native_go_hash.sha256(_native_go_raw).hexdigest() != {launcher.stem!r}):\n"
        "            raise SystemExit('native Go launcher source refused')\n"
        "    finally:\n"
        "        _native_go_os.close(_native_go_fd)\n"
        f"    _native_go_spec = _native_go_import.spec_from_file_location('_native_go_generation', {str(launcher)!r})\n"
        "    if _native_go_spec is None or _native_go_spec.loader is None:\n"
        "        raise SystemExit('native Go launcher unavailable')\n"
        "    _native_go_generation = _native_go_import.module_from_spec(_native_go_spec)\n"
        "    _native_go_sys.modules[_native_go_spec.name] = _native_go_generation\n"
        "    exec(compile(_native_go_raw, _native_go_path, 'exec'), _native_go_generation.__dict__)\n"
        f"    raise SystemExit(_native_go_generation.launch({str(store)!r}, 'go', _native_go_sys.argv[1:]))\n\n")
    lines = text.splitlines(keepends=True)
    result = "".join(lines[:first_business_line]) + branch + "".join(lines[first_business_line:])
    compile(result, "go_shim.bridge.py", "exec")
    return result.encode()


def _go_plan(prior_successor, target, component, previous):
    prior_successor, prior, original, base, completed = _completed_successor(prior_successor)
    _upgrade_pointer(previous)
    if (previous["sequence"] < completed["sequence"]
            or previous["sequence"] == completed["sequence"] and previous != completed):
        raise ValueError("Go selection predates its completed successor")
    store = Path(base["store"])
    _, before = generation.verify(store, previous["generation"])
    target_root, after = generation.verify(store, target)
    if (before["entrypoints"] != generation.ENTRYPOINTS
            or after["entrypoints"] != dict(generation.ENTRYPOINTS, go=generation.GO_ENTRY)):
        raise ValueError("Go entrypoint transition differs")
    component = Path(component)
    if component.is_relative_to(store.parent):
        raise ValueError("Go component must be outside the live owner")
    component_sha, manifest_sha, old_go = _go_component(component, Path(base["stable_ext"]), after["files"])
    new_launcher = _go_file(Path(generation.__file__).resolve())
    launcher_sha = generation.digest(new_launcher)
    if launcher_sha == SUCCESSOR_TO:
        raise ValueError("Go requires its reviewed successor launcher")
    launcher = store / "launchers" / (launcher_sha + ".py")
    payloads = {"native_generation.py": new_launcher}
    entries = {}
    for name in ("pool", "task", "remote"):
        entry = prior["entries"][name]
        row = {"target": entry["target"], "mode": entry["mode"],
               "previous": entry["previous"] if name == "remote" else entry["bridge"]}
        if name != "remote":
            bridge = (shell_bridge(Path(base["python"]), launcher, store, "pool")
                if name == "pool" else task_bridge(generation.regular_bytes(original / "task.original"),
                    Path(base["python"]), launcher, store))
            payloads[name + ".bridge"] = bridge
            row["bridge"] = generation.digest(bridge)
        entries[name] = row
    go_target = Path(base["stable_ext"]) / "go_shim/go_shim.py"
    info = generation.require(go_target, stat.S_ISREG)
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o7022 or info.st_nlink != 1:
        raise ValueError("Go ingress mode or link custody differs")
    bridge = go_bridge(old_go, launcher, store)
    payloads["go.bridge"] = bridge
    entries["go"] = {"target": str(go_target), "mode": mode,
        "previous": stage_builder.GO_INSTALLED_PREIMAGE, "bridge": generation.digest(bridge)}
    plan = {"schema": GO_SCHEMA, "prior_successor_bundle": str(prior_successor),
        "prior_successor_digest": prior["digest"], "bootstrap_digest": base["digest"],
        "store": str(store), "expected_selection": previous, "target_generation": target_root.name,
        "from_launcher": SUCCESSOR_TO, "to_launcher": launcher_sha,
        "manifest_sha256": manifest_sha, "component_bundle": str(component),
        "component_sha256": component_sha, "entries": entries}
    plan["digest"] = generation.digest(generation.canonical(plan))
    return plan, payloads


def prepare_go(prior_successor, target, component, output):
    _, _, _, base, _ = _completed_successor(prior_successor)
    store = Path(base["store"])
    output = Path(output).absolute()
    generation.require(output.parent, stat.S_ISDIR)
    if (output.parent.resolve(strict=True) != output.parent
            or output.is_relative_to(store.parent) or os.path.lexists(output)):
        raise ValueError("fresh external canonical Go bundle required")
    with generation.publication_lock(store):
        plan, payloads = _go_plan(prior_successor, target, component, generation.current(store))
        _upgrade_entries(plan)
        if os.path.lexists(store / "bootstrap/.go-application-ingress-v1.json"):
            raise ValueError("Go ingress already has an original transaction")
        output.mkdir(mode=0o700)
        for name, raw in payloads.items():
            generation.atomic_bytes(output / name, raw, 0o600)
        generation.atomic_bytes(output / "PLAN.json", generation.canonical(plan) + b"\n", 0o600)
    return plan


def read_go(bundle):
    bundle = _successor_directory(bundle)
    plan = _successor_json(bundle / "PLAN.json")
    if type(plan) is not dict or set(plan) != _GO_PLAN_FIELDS or plan["schema"] != GO_SCHEMA:
        raise ValueError("invalid Go ingress plan")
    expected, payloads = _go_plan(plan["prior_successor_bundle"], plan["target_generation"],
        plan["component_bundle"], plan["expected_selection"])
    if plan != expected or {p.name for p in bundle.iterdir()} != {"PLAN.json", *payloads}:
        raise ValueError("Go plan or artifact set differs")
    for name, raw in payloads.items():
        generation.require(bundle / name, stat.S_ISREG, 0o600)
        if _go_file(bundle / name) != raw:
            raise ValueError("Go payload differs")
    return plan, payloads


def apply_go(bundle):
    return _apply_ingress_transition(bundle, GO_SCHEMA)


def reconcile_go(bundle):
    return _apply_ingress_transition(bundle, GO_SCHEMA, reconcile_only=True)


def relocate_pool(raw):
    """Preserve every incumbent subcommand; relocate one fixed KIT_DIR line."""
    text = raw.decode("utf-8")
    matches = list(re.finditer(r'^KIT_DIR="(/[^"\n]*)"$', text, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError("expected one reviewed fixed KIT_DIR assignment")
    match = matches[0]
    replacement = 'KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd -P)"'
    return (text[:match.start()] + replacement + text[match.end():]).encode("utf-8")


def shell_bridge(python, launcher, store, entry):
    args = [str(python), str(launcher), "exec", "--store", str(store), "--entry", entry, "--"]
    return ("#!/bin/bash\n# " + BRIDGE_MARKER + "\nset -u\nexec "
            + " ".join(map(shlex.quote, args)) + ' "$@"\n').encode("utf-8")


def task_bridge(original, python, launcher, store):
    text = original.decode("utf-8")
    if BRIDGE_MARKER in text:
        raise ValueError("task source already contains an ingress bridge")
    module = ast.parse(text)
    first_business_line = 0
    for index, item in enumerate(module.body):
        if ((index == 0 and isinstance(item, ast.Expr)
             and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str))
                or (isinstance(item, ast.ImportFrom) and item.module == "__future__")):
            first_business_line = item.end_lineno
            continue
        break
    # Imports retain the original API body. CLI exec happens before any business
    # import can create mixed flat/generation module identities.
    command = [str(python), str(launcher), "exec", "--store", str(store), "--entry", "task", "--"]
    branch = ("\n# " + BRIDGE_MARKER + "\nif __name__ == '__main__':\n"
              "    import os as _native_ingress_os\n"
              "    import sys as _native_ingress_sys\n"
              f"    _native_ingress_os.execv({str(python)!r}, "
              f"{command!r} + _native_ingress_sys.argv[1:])\n\n")
    lines = text.splitlines(keepends=True)
    result = "".join(lines[:first_business_line]) + branch + "".join(lines[first_business_line:])
    compile(result, "fabric_task.bridge.py", "exec")
    return result.encode("utf-8")


def _bundle_payload(plan):
    return {key: value for key, value in plan.items() if key != "digest"}


def _record_once(path, value):
    raw = generation.canonical(value) + b"\n"
    if os.path.lexists(path):
        if generation.regular_bytes(path) != raw:
            raise ValueError("conflicting installation receipt")
        return
    # Existing artifact lock serializes the finite installer. No broker lock.
    generation.atomic_bytes(path, raw, 0o600)


def prepare(store, initial, pool_path, output, python=None):
    store = generation.check_store(store)
    _, meta = generation.verify(store, initial)
    stable_ext = Path(meta["stable_ext"])
    pool_path = Path(pool_path).absolute()
    generation.require(pool_path.parent, stat.S_ISDIR)
    python = Path(python or sys.executable).resolve(strict=True)
    if not os.access(python, os.X_OK):
        raise ValueError("existing Python executable is required")
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    # This file is the only launcher's dependency; it is versioned by its bytes.
    launcher_raw = generation.regular_bytes(Path(generation.__file__).resolve())
    launcher_digest = generation.digest(launcher_raw)
    launcher = store / "launchers" / (launcher_digest + ".py")
    targets = {"pool": pool_path, "task": stable_ext / "fabric_task.py",
               "remote": stable_ext / "remote_sub.sh"}
    originals = {name: generation.regular_bytes(path) for name, path in targets.items()}
    if BRIDGE_MARKER in originals["pool"].decode("utf-8"):
        raise ValueError("pool is already bridged; use its existing bootstrap plan")
    bridge_bytes = {
        "pool": shell_bridge(python, launcher, store, "pool"),
        "task": task_bridge(originals["task"], python, launcher, store),
        "remote": shell_bridge(python, launcher, store, "remote"),
    }
    plan = {"schema": SCHEMA, "bootstrap_epoch": uuid.uuid4().hex,
            "store": str(store), "initial_generation": initial,
            "stable_ext": str(stable_ext), "launcher_digest": launcher_digest,
            "launcher_path": str(launcher), "python": str(python), "entries": {}}
    for name, path in targets.items():
        observed = generation.require(path, stat.S_ISREG)
        plan["entries"][name] = {"target": str(path),
            "preimage": generation.digest(originals[name]),
            "bridge": generation.digest(bridge_bytes[name]),
            "mode": stat.S_IMODE(observed.st_mode), "bundle_file": name + ".bridge",
            "original_file": name + ".original"}
        generation.atomic_bytes(output / (name + ".bridge"), bridge_bytes[name], 0o600)
        generation.atomic_bytes(output / (name + ".original"), originals[name], 0o600)
    # Anchor old flat code and record new-generation-only names as absent.
    # New generation code may differ; installation never rewrites these files.
    plan["flat_code_preimages"] = {}
    plan["flat_code_absent"] = []
    for name in meta["files"]:
        if name.startswith("ext/"):
            original = stable_ext / name.split("/")[1]
            if os.path.lexists(original):
                plan["flat_code_preimages"][name] = generation.digest(generation.regular_bytes(original))
            else:
                plan["flat_code_absent"].append(name)
    generation.atomic_bytes(output / "native_generation.py", launcher_raw, 0o600)
    plan["digest"] = generation.digest(generation.canonical(plan))
    generation.atomic_bytes(output / "PLAN.json", generation.canonical(plan) + b"\n", 0o600)
    return plan


def read_plan(bundle):
    bundle = Path(bundle).resolve(strict=True)
    plan = generation.unique_json(generation.regular_bytes(bundle / "PLAN.json"))
    if (type(plan) is not dict or plan.get("schema") != SCHEMA
            or not isinstance(plan.get("bootstrap_epoch"), str)
            or re.fullmatch(r"[0-9a-f]{32}", plan["bootstrap_epoch"]) is None
            or plan.get("digest") != generation.digest(generation.canonical(_bundle_payload(plan)))):
        raise ValueError("invalid installation plan identity")
    store = generation.check_store(Path(plan["store"]))
    _, meta = generation.verify(store, plan["initial_generation"])
    if (plan["stable_ext"] != meta["stable_ext"] or set(plan["entries"]) != {"pool", "task", "remote"}
            or plan["entries"]["task"]["target"] != str(Path(meta["stable_ext"]) / "fabric_task.py")
            or plan["entries"]["remote"]["target"] != str(Path(meta["stable_ext"]) / "remote_sub.sh")):
        raise ValueError("installation target binding mismatch")
    expected_launcher = store / "launchers" / (plan["launcher_digest"] + ".py")
    if plan["launcher_path"] != str(expected_launcher):
        raise ValueError("launcher binding mismatch")
    if generation.digest(generation.regular_bytes(bundle / "native_generation.py")) != plan["launcher_digest"]:
        raise ValueError("launcher source mismatch")
    for name, entry in plan["entries"].items():
        if entry["bundle_file"] != name + ".bridge":
            raise ValueError("unexpected bridge source path")
        if generation.digest(generation.regular_bytes(bundle / entry["bundle_file"])) != entry["bridge"]:
            raise ValueError("bridge source mismatch")
        if (entry["original_file"] != name + ".original"
                or generation.digest(generation.regular_bytes(bundle / entry["original_file"])) != entry["preimage"]):
            raise ValueError("rollback preimage mismatch")
        if (type(entry["mode"]) is not int or entry["mode"] & 0o7022
                or not generation.HEX.fullmatch(entry["preimage"])):
            raise ValueError("unsafe ingress preimage or mode")
    if (set(plan["flat_code_preimages"]) & set(plan["flat_code_absent"])
            or set(plan["flat_code_preimages"]) | set(plan["flat_code_absent"]) !=
            {p for p in meta["files"] if p.startswith("ext/")}):
        raise ValueError("incomplete flat dependency inventory")
    for name in plan["flat_code_absent"]:
        generation.file_name(name)
    for name, wanted in plan["flat_code_preimages"].items():
        generation.file_name(name)
        if not generation.HEX.fullmatch(wanted):
            raise ValueError("invalid flat source hash")
    return bundle, plan


def _install_launcher(bundle, plan):
    store = Path(plan["store"])
    directory = store / "launchers"
    directory.mkdir(mode=0o700, exist_ok=True)
    generation.require(directory, stat.S_ISDIR, 0o700)
    target = directory / (plan["launcher_digest"] + ".py")
    if os.path.lexists(target):
        generation.require(target, stat.S_ISREG, 0o555)
        if generation.digest(generation.regular_bytes(target)) != plan["launcher_digest"]:
            raise ValueError("published launcher mismatch")
        return
    # A single content-addressed file needs no mutable final directory. It is
    # fully written, fsynced and sealed under a private temporary name before
    # atomic publication; interruption before rename cannot poison this digest.
    generation.atomic_bytes(target, generation.regular_bytes(bundle / "native_generation.py"), 0o555)
    generation.require(target, stat.S_ISREG, 0o555)
    if generation.digest(generation.regular_bytes(target)) != plan["launcher_digest"]:
        raise ValueError("published launcher mismatch")


def _preimages(plan, permitted_bridges):
    stable_ext = Path(plan["stable_ext"])
    for relative in plan["flat_code_absent"]:
        if os.path.lexists(stable_ext / relative.split("/")[1]):
            raise ValueError("flat namespace changed during bootstrap: " + relative)
    for relative, wanted in plan["flat_code_preimages"].items():
        path = stable_ext / relative.split("/")[1]
        actual = generation.digest(generation.regular_bytes(path))
        allowed = {wanted}
        for entry_name in permitted_bridges:
            entry = plan["entries"][entry_name]
            if str(path) == entry["target"]:
                allowed.add(entry["bridge"])
        if actual not in allowed:
            raise ValueError("flat dependency changed during bootstrap: " + relative)
    for name, entry in plan["entries"].items():
        allowed = {entry["preimage"]}
        if name in permitted_bridges:
            allowed.add(entry["bridge"])
        if generation.digest(generation.regular_bytes(entry["target"])) not in allowed:
            raise ValueError("ingress compare-and-swap refused: " + name)


def _install_entry(bundle, plan, name):
    entry = plan["entries"][name]
    target = Path(entry["target"])
    actual = generation.digest(generation.regular_bytes(target))
    if actual == entry["bridge"]:
        return
    if actual != entry["preimage"]:
        raise ValueError("ingress compare-and-swap refused: " + name)
    generation.atomic_bytes(target, generation.regular_bytes(bundle / entry["bundle_file"]), entry["mode"])
    if generation.digest(generation.regular_bytes(target)) != entry["bridge"]:
        raise ValueError("ingress installation readback failed")


def _receipts_dir(store):
    directory = store / "bootstrap"
    directory.mkdir(mode=0o700, exist_ok=True)
    generation.require(directory, stat.S_ISDIR, 0o700)
    return directory


def _require_studio_consumer_pin(plan, expected_field):
    """Refuse pool ingress drift against the existing bounded Studio census."""
    if expected_field not in ("bridge", "preimage"):
        raise ValueError("STUDIO_CONSUMER_TARGET_INVALID")
    entry = plan["entries"]["pool"]
    try:
        conflicts = studio_consumer_owner.pinned_consumers(
            entry["target"], entry[expected_field],
        )
    except (OSError, ValueError):
        raise ValueError("STUDIO_CONSUMER_CENSUS_REFUSED") from None
    if type(conflicts) is not list:
        raise ValueError("STUDIO_CONSUMER_CENSUS_REFUSED")
    if conflicts:
        # Do not expose private account identities or config filenames.
        raise ValueError("STUDIO_CONSUMER_PIN_MIGRATION_REQUIRED")


def phase1(bundle):
    bundle, plan = read_plan(bundle)
    store = Path(plan["store"])
    with generation.publication_lock(store):
        _require_studio_consumer_pin(plan, "bridge")
        if os.path.lexists(_receipts_dir(store) / (plan["digest"] + ".rollback.json")):
            raise ValueError("bootstrap epoch is terminal after rollback; prepare a fresh plan")
        _preimages(plan, {"pool", "task"})
        selection = generation.current(store)
        if selection is None:
            generation._select_locked(store, plan["initial_generation"], None)
        elif selection["generation"] != plan["initial_generation"]:
            raise ValueError("bootstrap must initially select the reviewed target release")
        _install_launcher(bundle, plan)
        # Re-observe pins immediately before replacing the global pool CLI.
        # Coordinated releases must separately quiesce all Studio writers.
        _require_studio_consumer_pin(plan, "bridge")
        # Each atomic replacement is independently safe: new launches get the
        # reviewed target (which may be V1, without publishing a relocated V0);
        # older processes retain their open old inode and all flat helpers.
        _install_entry(bundle, plan, "pool")
        _install_entry(bundle, plan, "task")
        receipt = {"schema": SCHEMA, "phase": 1, "plan_digest": plan["digest"],
                   "initial_generation": plan["initial_generation"],
                   "bridged": ["pool", "task"], "remote": "legacy"}
        _record_once(_receipts_dir(store) / (plan["digest"] + ".phase1.json"), receipt)
        return receipt


def rollback(bundle):
    """Restore exact future ingress preimages. Running generations stay pinned."""
    bundle, plan = read_plan(bundle)
    store = Path(plan["store"])
    with generation.publication_lock(store):
        _require_studio_consumer_pin(plan, "preimage")
        _preimages(plan, {"pool", "task", "remote"})
        # Restore the flat child first. An old parent will therefore never enter
        # a new flat controller as its future ingress is restored.
        for name in ("remote", "task", "pool"):
            entry = plan["entries"][name]
            actual = generation.digest(generation.regular_bytes(entry["target"]))
            if actual == entry["preimage"]:
                continue
            if actual != entry["bridge"]:
                raise ValueError("rollback ingress compare-and-swap refused")
            generation.atomic_bytes(Path(entry["target"]),
                                    generation.regular_bytes(bundle / entry["original_file"]), entry["mode"])
        receipt = {"schema": SCHEMA, "phase": "rollback", "plan_digest": plan["digest"],
                   "effect": "future ingress restored; attempts and state untouched"}
        _record_once(_receipts_dir(store) / (plan["digest"] + ".rollback.json"), receipt)
        return receipt


def phase2(bundle, legacy_receipt):
    bundle, plan = read_plan(bundle)
    store = Path(plan["store"])
    raw = generation.regular_bytes(Path(legacy_receipt))
    proof = generation.unique_json(raw)
    # This only validates the supplied existing-owner reconciliation record.
    # It does not infer drainage from zero leases, elapsed time or an empty ps.
    expected = {"schema", "plan_digest", "stable_ext", "owner_evidence_ref",
                "legacy_pool_producers", "legacy_task_producers",
                "unresolved_imported_mutating_callers"}
    if (type(proof) is not dict or set(proof) != expected or proof["schema"] != DRAIN_SCHEMA
            or proof["plan_digest"] != plan["digest"] or proof["stable_ext"] != plan["stable_ext"]
            or not isinstance(proof["owner_evidence_ref"], str) or not proof["owner_evidence_ref"].strip()
            or proof["unresolved_imported_mutating_callers"] != []):
        raise ValueError("legacy producer reconciliation is not bound and complete")
    for field in ("legacy_pool_producers", "legacy_task_producers"):
        if type(proof[field]) is not list:
            raise ValueError("explicit legacy producer inventory required")
        for producer in proof[field]:
            if (type(producer) is not dict or set(producer) != {"pid", "start_identity", "disposition", "evidence_ref"}
                    or type(producer["pid"]) is not int or producer["pid"] <= 0
                    or producer["disposition"] != "settled"
                    or not all(isinstance(producer[k], str) and producer[k].strip()
                               for k in ("start_identity", "evidence_ref"))):
                raise ValueError("unsettled or unbound legacy producer")
    with generation.publication_lock(store):
        if os.path.lexists(_receipts_dir(store) / (plan["digest"] + ".rollback.json")):
            raise ValueError("bootstrap epoch is terminal after rollback; prepare a fresh plan")
        receipt_path = _receipts_dir(store) / (plan["digest"] + ".phase1.json")
        phase_one = generation.unique_json(generation.regular_bytes(receipt_path))
        if phase_one.get("plan_digest") != plan["digest"] or phase_one.get("phase") != 1:
            raise ValueError("phase1 receipt missing")
        _preimages(plan, {"pool", "task", "remote"})
        for name in ("pool", "task"):
            if generation.digest(generation.regular_bytes(plan["entries"][name]["target"])) != plan["entries"][name]["bridge"]:
                raise ValueError("phase1 ingress no longer installed")
        _install_entry(bundle, plan, "remote")
        receipt = {"schema": SCHEMA, "phase": 2, "plan_digest": plan["digest"],
                   "legacy_reconciliation_digest": generation.digest(raw),
                   "bridged": ["pool", "task", "remote"]}
        _record_once(_receipts_dir(store) / (plan["digest"] + ".phase2.json"), receipt)
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--store", type=Path, required=True)
    prep.add_argument("--initial", required=True)
    prep.add_argument("--pool-path", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prepare_pair = sub.add_parser("prepare-upgrade")
    prepare_pair.add_argument("--original-bundle", type=Path, required=True)
    prepare_pair.add_argument("--target-generation", required=True)
    prepare_pair.add_argument("--output", type=Path, required=True)
    apply_pair = sub.add_parser("upgrade")
    apply_pair.add_argument("--bundle", type=Path, required=True)
    prepare_next = sub.add_parser("prepare-successor")
    prepare_next.add_argument("--prior-upgrade-bundle", type=Path, required=True)
    prepare_next.add_argument("--target-generation", required=True)
    prepare_next.add_argument("--output", type=Path, required=True)
    apply_next = sub.add_parser("successor")
    apply_next.add_argument("--bundle", type=Path, required=True)
    prepare_app = sub.add_parser("prepare-go")
    prepare_app.add_argument("--prior-successor-bundle", type=Path, required=True)
    prepare_app.add_argument("--target-generation", required=True)
    prepare_app.add_argument("--component-bundle", type=Path, required=True)
    prepare_app.add_argument("--output", type=Path, required=True)
    for command in ("apply-go", "reconcile-go"):
        action = sub.add_parser(command)
        action.add_argument("--bundle", type=Path, required=True)
    for command in ("phase1", "phase2", "rollback"):
        action = sub.add_parser(command)
        action.add_argument("--bundle", type=Path, required=True)
        if command == "phase2":
            action.add_argument("--legacy-receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.store, args.initial, args.pool_path, args.output)
    elif args.command == "prepare-upgrade":
        result = prepare_upgrade(args.original_bundle, args.target_generation, args.output)
    elif args.command == "upgrade":
        result = upgrade(args.bundle)
    elif args.command == "prepare-successor":
        result = prepare_successor(args.prior_upgrade_bundle, args.target_generation, args.output)
    elif args.command == "successor":
        result = apply_successor(args.bundle)
    elif args.command == "prepare-go":
        result = prepare_go(args.prior_successor_bundle, args.target_generation,
                            args.component_bundle, args.output)
    elif args.command == "apply-go":
        result = apply_go(args.bundle)
    elif args.command == "reconcile-go":
        result = reconcile_go(args.bundle)
    elif args.command == "phase1":
        result = phase1(args.bundle)
    elif args.command == "phase2":
        result = phase2(args.bundle, args.legacy_receipt)
    else:
        result = rollback(args.bundle)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print("NATIVE_INGRESS_REFUSED: " + str(exc), file=sys.stderr)
        raise SystemExit(78)
