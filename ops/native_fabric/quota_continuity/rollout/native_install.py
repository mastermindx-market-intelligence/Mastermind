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
import contextlib
import fcntl
import importlib.util
import ast
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import stat
import sys
import time
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
    mutable = ({"pool", "task", "go"}
               if plan["schema"] in (GO_SCHEMA, GO_RETAINED_SCHEMA) else {"pool", "task"})
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
# The one closed forward admission that may use a COMPLETED successor whose
# ORIGINAL bootstrap artifact was pruned. It is a distinct, explicit plan
# shape: the intact-history identities above are never relabelled or widened.
GO_RETAINED_SCHEMA = "native-ingress-go-application-retained.v1"
RETAINED_GO_ORIGIN = "retained-completed-successor-after-bootstrap-prune"
_GO_RETAINED_PLAN_FIELDS = frozenset(_GO_PLAN_FIELDS | {"predecessor_origin"})


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


# Frozen, read-only recovery of ONE previously completed historical native
# successor after its ORIGINAL bootstrap *artifact* was pruned. The native
# selection store still retains the original bootstrap/upgrade/successor
# receipts. This is NOT a replacement for read_successor on a new installation,
# a bootstrap reconstruction, a generation selection, or a publishing path.
# Every accepted byte below is a pre-observed, immutable original owner record.
RETAINED_STATUS_PLAN_DIGEST = "77c2c136852a783a1e2572c145af7536ee6cd0d7f443daa4c09795c333fd3dc7"
RETAINED_STATUS_PROOF_SHA256 = {
    "successor": {
        "PLAN.json": "ab4c95241229115b8e2788e27f8eea1e7f7ffd8de90e84eb52a1082d8fea69ca",
        "native_generation.py": "43e814339a16582e2205f12117e1f17c40dce2e42a9c52d815a37c043e772e1b",
        "pool.bridge": "bc0b3559392a07f3d4f7109455765c14dbc4dc946f6cb5a788e547ae179dbf0f",
        "task.bridge": "4fe675e145bbba6935c520d2cbe725c372acc0f41bd593bd6200d5543dc8137f",
    },
    "prior": {
        "PLAN.json": "705599cdfc17658433bbe475117957cefaffa7006199ae92ca319511db26047f",
        "native_generation.py": "d044c24940df13d24ff6241f0da9cec3dc24d90dd60604a08c82e0ad8613586c",
        "pool.bridge": "8533800b5abf8334a1cf6cc081322f16799ac5ef89e4deeea577f3a8217d8d1b",
        "task.bridge": "d8f64831e3d99f45ffd0650fffefa3a64ff0da8df11baa1aaebfafbbdffdea13",
    },
    "receipts": {
        ".launcher-successor-v1.json": "8f3fef59415bb42872dc13451d9b5f179206b5ba437ad1c20769d1eeed25f3d6",
        ".paired-launcher-upgrade.json": "fd16b7f62ab292d551fb326cc7a0934b2ddef95b762b00ba677d60744e6f1f8f",
        "77c2c136852a783a1e2572c145af7536ee6cd0d7f443daa4c09795c333fd3dc7.successor.json":
            "68c671258fde01289e4a141ecb540841350fb0c063b570b145c069d06e1a9af2",
        "b15d3ba1568ab03e2e038f0e2996a7116eecdacda68836acc3ad595f3d212485.upgrade.json":
            "87fff9ed353d6cd2978ee9786cfbafe69fb3d1388921d6c57561923e33de3957",
        "9b66429ef3255460a69c5e76450851e9c24e573acbe1f7670af27dfe513fae5e.phase1.json":
            "66068e045fa3ffd2957358715e682e0145348c2cd278b9367209d2a1e028416f",
    },
}


def _retained_successor_evidence(bundle, *, original_absent, current_bridges):
    """Authenticate ONE byte-pinned COMPLETED successor's retained evidence.

    Pure and read-only: it proves the retained documents, receipts, verified
    generations and the published predecessor launcher. It never writes a file,
    never changes a pointer and grants no mutation admission. Each admitted
    caller states its own distinct boundary conditions:

    ``original_absent`` - True admits only an ACTUALLY absent original
    bootstrap artifact; False refuses a present one so the original strict
    verifier remains the only owner of that history.
    ``current_bridges`` - True requires the installed ingress bridges to still
    be the completed successor's own bridges. A later Go ingress replaces
    them, so a forward admission reads the Go plan's own compare-and-swap
    instead of this historical one.
    """
    def fixed_files(directory, expected, *, exact=True):
        generation.require(directory, stat.S_ISDIR, stat.S_IRWXU)
        if exact and {p.name for p in directory.iterdir()} != set(expected):
            raise ValueError("retained successor artifact set changed")
        raw = {}
        for name, digest in expected.items():
            candidate = directory / name
            generation.require(candidate, stat.S_ISREG, 0o600)
            observed = generation.regular_bytes(candidate, 65536)
            if generation.digest(observed) != digest:
                raise ValueError("retained successor evidence changed")
            raw[name] = observed
        return raw

    bundle = _successor_directory(bundle)
    frozen = fixed_files(bundle, RETAINED_STATUS_PROOF_SHA256["successor"])
    plan = generation.unique_json(frozen["PLAN.json"])
    if (type(plan) is not dict or set(plan) != _SUCCESSOR_PLAN_FIELDS
            or plan["schema"] != SUCCESSOR_SCHEMA
            or plan["digest"] != RETAINED_STATUS_PLAN_DIGEST
            or generation.digest(generation.canonical(
                {k: v for k, v in plan.items() if k != "digest"})) != plan["digest"]):
        raise ValueError("unqualified retained successor plan")

    prior_dir = _successor_directory(plan["prior_upgrade_bundle"])
    predecessor = fixed_files(prior_dir, RETAINED_STATUS_PROOF_SHA256["prior"])
    prior = generation.unique_json(predecessor["PLAN.json"])
    if (type(prior) is not dict or prior.get("schema") != UPGRADE_SCHEMA
            or prior.get("digest") != plan["prior_upgrade_digest"]
            or prior.get("bootstrap_digest") != plan["bootstrap_digest"]
            or prior.get("to_launcher") != plan["from_launcher"]
            or prior.get("store") != plan["store"]
            or generation.digest(generation.canonical(
                {k: v for k, v in prior.items() if k != "digest"})) != prior["digest"]):
        raise ValueError("retained successor predecessor changed")

    original = Path(prior["original_bundle"])
    if (not original.is_absolute() or os.path.lexists(original)
            or original.parent.resolve(strict=True) != original.parent):
        # Original present but malformed? Use the ORIGINAL strict verifier.
        # Original missing at a new/foreign location? The fixed plan hash refuses.
        if original_absent:
            raise ValueError("retained Go predecessor requires an actually absent original bootstrap")
        raise ValueError("strict original bootstrap verifier required")
    generation.require(original.parent, stat.S_ISDIR, stat.S_IRWXU)
    store = Path(plan["store"])
    generation.require(store, stat.S_ISDIR, stat.S_IRWXU)
    receipts_dir = store / "bootstrap"
    evidence = fixed_files(
        receipts_dir, RETAINED_STATUS_PROOF_SHA256["receipts"], exact=False)
    decoded = {key: generation.unique_json(raw) for key, raw in evidence.items()}
    phase = decoded[plan["bootstrap_digest"] + ".phase1.json"]
    upgrade = decoded[prior["digest"] + ".upgrade.json"]
    successor = decoded[plan["digest"] + ".successor.json"]
    if (phase.get("schema") != SCHEMA or phase.get("phase") != 1
            or phase.get("plan_digest") != plan["bootstrap_digest"]
            or upgrade.get("schema") != UPGRADE_SCHEMA
            or upgrade.get("plan_digest") != prior["digest"]
            or upgrade.get("bootstrap_digest") != plan["bootstrap_digest"]
            or successor.get("schema") != SUCCESSOR_SCHEMA
            or successor.get("plan_digest") != plan["digest"]
            or successor.get("prior_upgrade_digest") != prior["digest"]
            or successor.get("bootstrap_digest") != plan["bootstrap_digest"]
            or successor.get("previous_selection") != plan["expected_selection"]
            or successor.get("selection") != {
                "schema": generation.POINTER_SCHEMA,
                "generation": plan["target_generation"],
                "previous": plan["expected_selection"]["generation"],
                "sequence": plan["expected_selection"]["sequence"] + 1,
            }):
        raise ValueError("retained successor receipts disagree")
    if any(os.path.lexists(receipts_dir / (plan["bootstrap_digest"] + suffix))
           for suffix in (".rollback.json", ".phase2.json")):
        raise ValueError("retained historical epoch changed")
    for identity in (
        phase["initial_generation"],
        prior["expected_selection"]["generation"],
        prior["target_generation"],
        plan["expected_selection"]["generation"],
        plan["target_generation"],
    ):
        generation.verify(store, identity)
    if current_bridges:
        _upgrade_entries(plan, complete=True)
    payloads = {name: raw for name, raw in frozen.items() if name != "PLAN.json"}
    _require_successor_launcher(plan, payloads)
    return {"bundle": bundle, "plan": plan, "prior": prior, "original": original,
            "store": store, "payloads": payloads}


def read_retained_successor_after_bootstrap_prune(bundle):
    """Read one byte-pinned COMPLETED selection after its bootstrap was pruned.

    Admitted callers are native-pin status and the closed chatgpt1 gateway
    formatter's artifact check. This is not native apply or reconcile. The
    deleted historical bootstrap is never synthesized. Any unknown chain,
    foreign byte, incomplete transaction or invalid selected generation refuses.
    Callers must separately prove the enrolled account's original pin and actual
    current/native selected state. This helper never writes a file or a pointer.
    """
    evidence = _retained_successor_evidence(
        bundle, original_absent=False, current_bridges=True)
    return evidence["plan"], evidence["payloads"]


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
    elif schema in (GO_SCHEMA, GO_RETAINED_SCHEMA):
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
    elif expected_schema == GO_RETAINED_SCHEMA:
        reader = read_retained_go
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
    staged_dependencies = stage_builder.go_staged_dependency_hashes(target_files,
        {name: row["sha256"] for name, row in dependencies.items()})
    expected = {"schema": "native-external-go-component.v1", "component": "go_application_handler",
        "destination_relative_to_stable_ext": "go_shim/go_shim.py", "stable_ext": str(stable_ext),
        "installed_preimage_sha256": stage_builder.GO_INSTALLED_PREIMAGE,
        "candidate_sha256": generation.digest(handler), "candidate_bytes": len(handler),
        "candidate_source": "candidate/go_shim.py", "dependencies": dependencies,
        "native_stage_dependencies": staged_dependencies,
        "preimage_source_ref": "https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6646945527",
        "installation_state": "HELD_REQUIRES_PROTECTED_RELEASE_AND_EXISTING_OWNER_INSTALLATION"}
    if (record != expected or _go_file(bundle / "source-go_shim.py") != preimage
            or _go_file(bundle / "go_shim.py") != handler):
        raise ValueError("Go component is not the exact reviewed source")
    manifest_raw = _go_file(bundle.parent / "native-manifest.json")
    manifest = generation.unique_json(manifest_raw)
    if manifest != target_files:
        raise ValueError("Go target differs from captured native manifest")
    http_members = stage_builder.HTTP_GENERATION_MEMBERS & set(manifest)
    if http_members:
        if http_members != stage_builder.HTTP_GENERATION_MEMBERS:
            raise ValueError("Go target application HTTP closure incomplete")
        http_sources = stage_builder.application_http_sources(root)
        if any(manifest[relative] != generation.digest(data[0]) for relative, data in http_sources.items()):
            raise ValueError("Go target application HTTP differs from exact reviewed source")
    base = {key: value for key, value in manifest.items()
            if key not in {generation.GO_ENTRY, generation.GO_HANDLER} | http_members}
    stage_builder.validate_go_base_manifest(base, staged_dependencies)
    if (set(manifest) != set(base) | {generation.GO_ENTRY, generation.GO_HANDLER} | http_members
            or manifest[generation.GO_HANDLER] != generation.digest(handler)
            or manifest[generation.GO_ENTRY] != generation.digest(entry)
            or any(manifest.get("ext/" + name) != digest for name, digest in staged_dependencies.items())):
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
    stage_builder.validate_go_source_transition(before["files"], after["files"])
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


def _retained_pool_context(payloads, plan, store):
    """Recover the interpreter, launcher and store from the pinned pool bridge.

    The retained pool bridge is the exact shell bridge this installer wrote for
    the completed successor. Re-deriving it from its own parsed argument vector
    proves the interpreter, the launcher identity and the store without
    reconstructing any deleted historical artifact.
    """
    raw = payloads["pool.bridge"]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("retained Go predecessor pool bridge differs") from None
    prefix = "#!/bin/bash\n# " + BRIDGE_MARKER + "\nset -u\nexec "
    suffix = ' "$@"\n'
    if not text.startswith(prefix) or not text.endswith(suffix):
        raise ValueError("retained Go predecessor pool bridge differs")
    middle = text[len(prefix):-len(suffix)]
    try:
        arguments = shlex.split(middle)
    except ValueError:
        raise ValueError("retained Go predecessor pool bridge differs") from None
    if len(arguments) != 8 or shlex.join(arguments) != middle:
        raise ValueError("retained Go predecessor pool bridge differs")
    python, launcher, command, store_flag, store_path, entry_flag, entry, terminator = arguments
    if (command != "exec" or store_flag != "--store" or entry_flag != "--entry"
            or entry != "pool" or terminator != "--"):
        raise ValueError("retained Go predecessor pool bridge differs")
    if not os.path.isabs(python):
        raise ValueError("retained Go predecessor interpreter differs")
    launcher_path = Path(launcher)
    if (store_path != str(store)
            or launcher_path != store / "launchers" / (SUCCESSOR_TO + ".py")):
        raise ValueError("retained Go predecessor launcher identity differs")
    if shell_bridge(python, launcher_path, store, "pool") != raw:
        raise ValueError("retained Go predecessor pool bridge differs")
    if plan["entries"]["pool"]["bridge"] != generation.digest(raw):
        raise ValueError("retained Go predecessor pool bridge differs")
    return python, launcher_path


def _retained_task_bridge(payloads, plan, store, python, old_launcher, new_launcher):
    """Derive the forward task bridge from the pinned retained one.

    Only the launcher reference changes. The interpreter, the arguments and
    every original business byte are preserved, and the transformation is
    exact, bounded to one occurrence and reversible.
    """
    raw = payloads["task.bridge"]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("retained Go predecessor task bridge differs") from None
    old_branch = _task_bridge_branch(python, old_launcher, store)
    new_branch = _task_bridge_branch(python, new_launcher, store)
    if text.count(old_branch) != 1:
        raise ValueError("retained Go predecessor task bridge differs")
    if plan["entries"]["task"]["bridge"] != generation.digest(raw):
        raise ValueError("retained Go predecessor task bridge differs")
    return text.replace(old_branch, new_branch, 1).encode("utf-8")


def _retained_go_plan(prior_successor, target, component, previous):
    """Derive one forward Go plan from the retained completed successor.

    The shared evidence proves the retained documents, receipts, verified
    generations and the published predecessor launcher. This admission adds its
    own distinct conditions: the ORIGINAL bootstrap artifact must be actually
    absent, the retained bridges must re-derive exactly from the recovered
    interpreter, and the ordinary Go component, generation, entrypoint,
    selection compare-and-swap and Studio fences still apply unchanged. No
    historical artifact is synthesized and no deleted source is reconstructed.
    """
    evidence = _retained_successor_evidence(
        prior_successor, original_absent=True, current_bridges=False)
    plan = evidence["plan"]
    payloads = evidence["payloads"]
    store = evidence["store"]
    completed = {"schema": generation.POINTER_SCHEMA,
                 "generation": plan["target_generation"],
                 "previous": plan["expected_selection"]["generation"],
                 "sequence": plan["expected_selection"]["sequence"] + 1}
    _upgrade_pointer(previous)
    if (previous["sequence"] < completed["sequence"]
            or previous["sequence"] == completed["sequence"] and previous != completed):
        raise ValueError("Go selection predates its completed successor")
    _, before = generation.verify(store, previous["generation"])
    target_root, after = generation.verify(store, target)
    if (before["entrypoints"] != generation.ENTRYPOINTS
            or after["entrypoints"] != dict(generation.ENTRYPOINTS, go=generation.GO_ENTRY)):
        raise ValueError("Go entrypoint transition differs")
    stage_builder.validate_go_source_transition(before["files"], after["files"])
    component = Path(component)
    if component.is_relative_to(store.parent):
        raise ValueError("Go component must be outside the live owner")
    stable_ext = Path(after["stable_ext"])
    component_sha, manifest_sha, old_go = _go_component(component, stable_ext, after["files"])
    new_launcher = _go_file(Path(generation.__file__).resolve())
    launcher_sha = generation.digest(new_launcher)
    if launcher_sha == SUCCESSOR_TO:
        raise ValueError("Go requires its reviewed successor launcher")
    launcher = store / "launchers" / (launcher_sha + ".py")
    python, old_launcher = _retained_pool_context(payloads, plan, store)
    entries = {}
    forward = {"native_generation.py": new_launcher}
    for name in ("pool", "task", "remote"):
        entry = plan["entries"][name]
        row = {"target": entry["target"], "mode": entry["mode"],
               "previous": entry["previous"] if name == "remote" else entry["bridge"]}
        if name != "remote":
            bridge = (shell_bridge(python, launcher, store, "pool")
                      if name == "pool" else _retained_task_bridge(
                          payloads, plan, store, python, old_launcher, launcher))
            forward[name + ".bridge"] = bridge
            row["bridge"] = generation.digest(bridge)
        entries[name] = row
    go_target = stable_ext / "go_shim/go_shim.py"
    info = generation.require(go_target, stat.S_ISREG)
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o7022 or info.st_nlink != 1:
        raise ValueError("Go ingress mode or link custody differs")
    bridge = go_bridge(old_go, launcher, store)
    forward["go.bridge"] = bridge
    entries["go"] = {"target": str(go_target), "mode": mode,
        "previous": stage_builder.GO_INSTALLED_PREIMAGE, "bridge": generation.digest(bridge)}
    forward_plan = {"schema": GO_RETAINED_SCHEMA,
        "prior_successor_bundle": str(evidence["bundle"]),
        "prior_successor_digest": plan["digest"],
        "bootstrap_digest": plan["bootstrap_digest"],
        "store": str(store), "expected_selection": previous,
        "target_generation": target_root.name,
        "from_launcher": SUCCESSOR_TO, "to_launcher": launcher_sha,
        "manifest_sha256": manifest_sha, "component_bundle": str(component),
        "component_sha256": component_sha, "predecessor_origin": RETAINED_GO_ORIGIN,
        "entries": entries}
    forward_plan["digest"] = generation.digest(generation.canonical(forward_plan))
    return forward_plan, forward


def prepare_retained_go(prior_successor, target, component, output):
    """Prepare one forward Go plan from the retained completed successor.

    Preparation writes only a review bundle. It changes no selection, no
    ingress bridge, no launcher and no service.
    """
    evidence = _retained_successor_evidence(
        prior_successor, original_absent=True, current_bridges=False)
    store = evidence["store"]
    output = Path(output).absolute()
    generation.require(output.parent, stat.S_ISDIR)
    if (output.parent.resolve(strict=True) != output.parent
            or output.is_relative_to(store.parent) or os.path.lexists(output)):
        raise ValueError("fresh external canonical retained Go bundle required")
    with generation.publication_lock(store):
        plan, payloads = _retained_go_plan(prior_successor, target, component,
                                           generation.current(store))
        _upgrade_entries(plan)
        if os.path.lexists(store / "bootstrap/.go-application-ingress-v1.json"):
            raise ValueError("Go ingress already has an original transaction")
        output.mkdir(mode=0o700)
        for name, raw in payloads.items():
            generation.atomic_bytes(output / name, raw, 0o600)
        generation.atomic_bytes(output / "PLAN.json", generation.canonical(plan) + b"\n", 0o600)
    return plan


def read_retained_go(bundle):
    bundle = _successor_directory(bundle)
    plan = _successor_json(bundle / "PLAN.json")
    if (type(plan) is not dict or set(plan) != _GO_RETAINED_PLAN_FIELDS
            or plan["schema"] != GO_RETAINED_SCHEMA
            or plan["predecessor_origin"] != RETAINED_GO_ORIGIN):
        raise ValueError("invalid retained Go ingress plan")
    expected, payloads = _retained_go_plan(plan["prior_successor_bundle"],
                                           plan["target_generation"],
                                           plan["component_bundle"],
                                           plan["expected_selection"])
    if plan != expected or {p.name for p in bundle.iterdir()} != {"PLAN.json", *payloads}:
        raise ValueError("retained Go plan or artifact set differs")
    for name, raw in payloads.items():
        generation.require(bundle / name, stat.S_ISREG, 0o600)
        if _go_file(bundle / name) != raw:
            raise ValueError("retained Go payload differs")
    return plan, payloads


def apply_retained_go(bundle):
    """Advance only this retained forward Go transition; no process or service control."""
    return _apply_ingress_transition(bundle, GO_RETAINED_SCHEMA)


def reconcile_retained_go(bundle):
    """Finish only this original missing receipt; never reinstall or select again."""
    return _apply_ingress_transition(bundle, GO_RETAINED_SCHEMA, reconcile_only=True)


SERVICE_SPEC_SCHEMA = "native-go-service-enrollment-specification.v1"
SERVICE_HTTP_SPEC_SCHEMA = "native-go-service-enrollment-specification.v2"
SERVICE_SELECTED_SPEC_SCHEMA = "native-go-service-enrollment-specification.v3"
SERVICE_ADMIN_SPEC_SCHEMA = "native-go-service-enrollment-specification.v4"
SERVICE_SET_SPEC_SCHEMA = "native-go-service-enrollment-specification.v5"
SERVICE_FAMILY_SPEC_SCHEMA = "native-go-service-enrollment-specification.v6"
SERVICE_ROUTED_SPEC_SCHEMA = "native-go-service-enrollment-specification.v7"
SERVICE_WORKLOAD_SPEC_SCHEMA = "native-go-service-enrollment-specification.v8"
SERVICE_ROLE_SPEC_SCHEMA = "native-go-service-enrollment-specification.v9"
SERVICE_FRESH_FAMILY_SPEC_SCHEMA = "native-go-service-enrollment-specification.v10"
_SERVICE_FAMILY_NAMES = ("admin", "text", "chat", "brain", "ask")
_SERVICE_WORKLOAD_NAMES = _SERVICE_FAMILY_NAMES + ("batch", "analysis", "portfolio")
_SERVICE_PLAN_FIELDS = frozenset({"schema", "operation_id", "go_ingress_bundle", "ingress_digest",
    "source_generation", "store", "selection", "installer_sha256", "entry_sha256", "scope",
    "owners", "owner_identities", "accounts_before", "accounts_after_sha256", "grant_sha256", "digest"})
_SERVICE_PREPARED_FILES = frozenset({"PLAN.json", "specification.json", "accounts.before.yaml", "accounts.after.yaml"})
_SERVICE_PRIVATE = "application-service.private.json"
_SERVICE_PREDECESSOR = "application-service.predecessor.private.json"


def _completed_go_for_service(bundle):
    """Read completed original ingress; never call a transition as inspection."""
    bundle = _successor_directory(bundle)
    envelope = _successor_json(bundle / "PLAN.json")
    schema = envelope.get("schema") if type(envelope) is dict else None
    if schema == GO_SCHEMA:
        plan, payloads = read_go(bundle)
    elif schema == GO_RETAINED_SCHEMA:
        plan, payloads = read_retained_go(bundle)
    else:
        raise ValueError("unsupported completed Go ingress schema")
    intent_name, suffix, _, intent, selected, receipt = _transition_records(plan)
    store = Path(plan["store"])
    if (_successor_json(store / "bootstrap" / intent_name) != intent
            or _successor_json(store / "bootstrap" / (plan["digest"] + suffix)) != receipt
            or generation.current(store) != selected):
        raise ValueError("service enrollment requires the completed selected Go ingress")
    _upgrade_entries(plan, complete=True)
    _require_successor_launcher(plan, payloads)
    root, metadata = generation.verify(store, plan["target_generation"])
    if metadata["entrypoints"].get("go") != generation.GO_ENTRY:
        raise ValueError("service enrollment Go entry differs")
    return plan, selected, root, metadata


@contextlib.contextmanager
def _service_source(go_ingress_bundle):
    """Borrow the already sealed entry/import owner for this finite operation."""
    plan, selected, root, metadata = _completed_go_for_service(go_ingress_bundle)
    path = root / generation.GO_ENTRY
    raw = generation.regular_bytes(path)
    if generation.digest(raw) != metadata["files"][generation.GO_ENTRY]:
        raise ValueError("service entry source changed")
    if "native_go_entry" in sys.modules:
        raise ValueError("service entry module already belongs to another caller")
    names = {Path(name).stem for name in metadata["files"]
             if name.startswith("ext/") and name.endswith(".py")}
    names.add("glm_shim")
    previous = {name: sys.modules[name] for name in names if name in sys.modules}
    path_before = list(sys.path)
    spec = importlib.util.spec_from_file_location("native_go_entry", path)
    if spec is None or spec.loader is None:
        raise ValueError("service entry unavailable")
    entry = importlib.util.module_from_spec(spec)
    sys.modules["native_go_entry"] = entry
    try:
        exec(compile(raw, str(path), "exec"), entry.__dict__)
        startup = entry.inspect(verified_root=root, verified_metadata=metadata)
        if (not hasattr(entry, "load_completed_application_startup")
                or not hasattr(startup, "policy_snapshot")):
            raise ValueError("selected Go entry has no reviewed service enrollment")
        yield plan, selected, metadata, entry, startup
    finally:
        for name in names:
            if name not in previous:
                sys.modules.pop(name, None)
        sys.path[:] = path_before


def _service_snapshot(entry, path, *, read=True, mode=None):
    path = Path(path)
    info = generation.require(path, stat.S_ISREG, mode)
    if info.st_nlink != 1 or info.st_mode & 0o022:
        raise ValueError("service source file custody refused")
    before = entry.application_file_identity(path)
    if read:
        raw = generation.regular_bytes(path, 2 * 1024 * 1024)
    else:
        # Verify the physical owner without reading a provider credential or DB.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            held = os.fstat(fd)
            if (held.st_dev, held.st_ino) != (info.st_dev, info.st_ino):
                raise ValueError("service owner changed")
        finally:
            os.close(fd)
        raw = None
    if entry.application_file_identity(path) != before:
        raise ValueError("service source file changed")
    return raw, before


def _service_owner_identities(entry, startup, profile, *, application_http=False):
    paths = entry.application_enrollment_paths(startup)
    directory_paths = {"go": startup.paths["go"], "broker": startup.paths["db_path"].parent,
        "accounts": startup.paths["accounts_path"].parent, "profile": profile.parent,
        "bootstrap": paths["intent"].parent, "store": paths["intent"].parent.parent}
    provider_profile = entry.application_http_profile(startup) if application_http else None
    if provider_profile is not None:
        directory_paths["provider_profile"] = provider_profile.parent
    identities = {}
    for name, path in directory_paths.items():
        entry._directory(path)
        info = path.lstat()
        if name in {"go", "profile", "provider_profile", "bootstrap", "store"} and stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("service private parent custody refused")
        identities["directory:" + name] = {"dev": info.st_dev, "ino": info.st_ino,
            "uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode)}
    for name in ("db_path", "lock_path"):
        _, identity = _service_snapshot(entry, startup.paths[name], read=False)
        identities[name] = {key: identity[key] for key in ("dev", "ino", "uid", "gid", "mode", "nlink")}
    _, identities["account_profile"] = _service_snapshot(entry, profile, read=False, mode=0o600)
    if provider_profile is not None:
        _, identities["provider_profile"] = _service_snapshot(entry, provider_profile, read=False, mode=0o600)
    return identities


def _service_specification(entry, specification, startup=None, *, allow_inactive_grant=False):
    if isinstance(specification, (str, Path)):
        specification = _successor_json(Path(specification))
    fields = {"schema", "operation_id", "scope", "grant"}
    if type(specification) is dict and specification.get("schema") == SERVICE_FRESH_FAMILY_SPEC_SCHEMA:
        specification = generation.unique_json(generation.canonical(specification))
        _validate_service_workload_specification(entry, specification, startup, fresh_family=True)
        return specification
    if type(specification) is dict and specification.get("schema") == SERVICE_WORKLOAD_SPEC_SCHEMA:
        specification = generation.unique_json(generation.canonical(specification))
        _validate_service_workload_specification(entry, specification, startup)
        return specification
    if type(specification) is dict and specification.get("schema") == SERVICE_ROUTED_SPEC_SCHEMA:
        specification = generation.unique_json(generation.canonical(specification))
        _validate_service_routed_specification(entry, specification, startup)
        return specification
    if type(specification) is dict and specification.get("schema") == SERVICE_FAMILY_SPEC_SCHEMA:
        specification = generation.unique_json(generation.canonical(specification))
        _validate_service_family_specification(entry, specification, startup)
        return specification
    service_set = type(specification) is dict and specification.get("schema") == SERVICE_SET_SPEC_SCHEMA
    if service_set:
        specification = generation.unique_json(generation.canonical(
            _successor_json(Path(specification)) if isinstance(specification, (str, Path)) else specification))
        _validate_service_set_specification(entry, specification, startup)
        return specification
    http = type(specification) is dict and specification.get("schema") == SERVICE_HTTP_SPEC_SCHEMA
    admin = type(specification) is dict and specification.get("schema") == SERVICE_ADMIN_SPEC_SCHEMA
    role = type(specification) is dict and specification.get("schema") == SERVICE_ROLE_SPEC_SCHEMA
    routed_role = role and type(specification.get("scope")) is dict and "route_scope" in specification["scope"]
    if routed_role:
        fields = fields - {"grant"} | {"grants"}
    selected = type(specification) is dict and specification.get("schema") in (SERVICE_SELECTED_SPEC_SCHEMA, SERVICE_ADMIN_SPEC_SCHEMA, SERVICE_ROLE_SPEC_SCHEMA)
    if http:
        fields.add("application_recipe")
    if (type(specification) is not dict or set(specification) != fields
            or specification["schema"] != (SERVICE_ROLE_SPEC_SCHEMA if role else SERVICE_HTTP_SPEC_SCHEMA if http else
                SERVICE_ADMIN_SPEC_SCHEMA if admin else
                SERVICE_SELECTED_SPEC_SCHEMA if selected else SERVICE_SPEC_SCHEMA)
            or type(specification["operation_id"]) is not str
            or entry.IDENTITY.fullmatch(specification["operation_id"]) is None):
        raise ValueError("invalid service enrollment specification")
    # Freeze an owned JSON value, rejecting nonfinite numbers and aliases.
    specification = generation.unique_json(generation.canonical(specification))
    scope = specification["scope"]
    grants = specification["grants"] if routed_role else [specification["grant"]]
    if type(grants) is not list or not 1 <= len(grants) <= 128 or any(type(g) is not dict for g in grants):
        raise ValueError("invalid service enrollment grants")
    scope_fields = entry.SERVICE_SCOPE_FIELDS | {"selection_purpose"} if selected else entry.SERVICE_SCOPE_FIELDS
    if admin:
        scope_fields |= {"admin_pool_view"}
    if role:
        scope_fields |= {"service_profile"}
    if routed_role:
        scope_fields |= {"route_scope"}
    if type(scope) is not dict or set(scope) != scope_fields:
        raise ValueError("invalid service enrollment scope")
    if admin and type(scope["admin_pool_view"]) is not bool:
        raise ValueError("invalid service metadata permission")
    if selected:
        if startup is None:
            raise ValueError("selected service requires verified startup")
        startup.broker_module._application_selection_purpose(scope["selection_purpose"])
    for name in ("principal_id", "caller_host", "native_host", "workload", "credential_ref"):
        if type(scope[name]) is not str or entry.IDENTITY.fullmatch(scope[name]) is None:
            raise ValueError("invalid service enrollment identity")
    if role:
        entry.validate_application_role_scope(scope)
    if routed_role:
        startup.handler.ApplicationRouteScope(scope["route_scope"])
    text = scope["capability_lane"] == "mastermind-text"
    for grant in grants:
        if ((text and (selected is not True or admin or scope["workload_profile"] != "site_batch"
                       or scope["credential_ref"] != entry.SERVICE_TEXT_CREDENTIAL_REF))
                or not text and not role and (scope["capability_lane"] != "admin-orchestrator"
                or scope["workload_profile"] != "site_interactive"
                or scope["credential_ref"] != entry.SERVICE_CREDENTIAL_REF)
                or type(scope["account_profile"]) is not str
                or not Path(scope["account_profile"]).is_absolute() or ".." in Path(scope["account_profile"]).parts
                or grant.get("principal_id") != scope["principal_id"]
                or grant.get("credential_ref") != scope["credential_ref"]
                or grant.get("caller_hosts") != [scope["caller_host"]]
                or grant.get("workloads") != [scope["workload"]]
                or grant.get("purpose") != "APPLICATION"
                or (grant.get("enabled") is not True and not (allow_inactive_grant and grant.get("enabled") is False))
                or grant.get("pool") not in (scope["route_scope"]["pools"] if routed_role else ["bailian" if http else "go"])
                or grant.get("route") != "/v1/chat/completions"
                or grant.get("stream") is not False or type(grant.get("models")) is not list
                or not routed_role and len(grant["models"]) != 1):
            raise ValueError("service enrollment mapping differs")
    if http:
        recipe = specification["application_recipe"]
        if (startup is None or type(recipe) is not dict or scope["workload"] != "site_interactive"
                or recipe != entry.application_http_recipe(startup, grant["models"][0])):
            raise ValueError("service enrollment HTTP source recipe differs")
        _, digest = startup.broker_module._application_http_recipe(recipe, pool="bailian", model=grant["models"][0])
        if grant.get("recipe_digest") != digest:
            raise ValueError("service enrollment HTTP grant commitment differs")
    return specification


def _service_candidate(startup, specification, before):
    document = startup.policy_snapshot.parse_policy(before)
    old = document.get("application_grants", [])
    if type(old) is not list:
        raise ValueError("existing application grants are invalid")
    grant = specification["grant"]
    for existing in old:
        if not isinstance(existing, dict):
            raise ValueError("existing application grants are invalid")
        if (existing.get("grant_id") == grant.get("grant_id")
                or existing.get("principal_id") == grant["principal_id"]
                and existing.get("pool") == grant["pool"]
                and set(existing.get("caller_hosts", ())) & set(grant["caller_hosts"])
                and set(existing.get("workloads", ())) & set(grant["workloads"])
                and set(existing.get("models", ())) & set(grant["models"])):
            raise ValueError("service enrollment overlaps an existing grant")
    if not any(existing == grant for existing in old):
        document["application_grants"] = [*old, grant]
    return generation.canonical(document) + b"\n", document


def _service_grant_value(specification):
    """The existing commitment slot; v9's closed routed form commits a list."""
    return (specification["grants"] if specification["schema"] == SERVICE_ROLE_SPEC_SCHEMA
            and "route_scope" in specification["scope"] else specification["grant"])


def _service_grant_expiry(specification):
    grants = _service_grant_value(specification)
    return min(g["expires_at"] for g in grants) if type(grants) is list else grants["expires_at"]


def _service_enrollment_candidate(startup, specification, before):
    grants = _service_grant_value(specification)
    if type(grants) is not list:
        return _service_candidate(startup, specification, before)
    after = before
    for grant in grants:
        after, document = _service_candidate(startup, {"grant": grant}, after)
    return after, document


def _validate_service_set_specification(entry, specification, startup):
    fields = {"schema", "operation_id", "admin", "text"}
    if (type(specification) is not dict or set(specification) != fields
            or type(specification["operation_id"]) is not str
            or entry.IDENTITY.fullmatch(specification["operation_id"]) is None):
        raise ValueError("invalid service-set enrollment specification")
    roles = []
    for name, spec_schema, binding_schema in (("admin", SERVICE_ADMIN_SPEC_SCHEMA, entry.SERVICE_ADMIN_SCHEMA),
                                               ("text", SERVICE_SELECTED_SPEC_SCHEMA, entry.SERVICE_SELECTED_SCHEMA)):
        original = specification[name]
        role = _service_specification(entry, original, startup, allow_inactive_grant=(name == "admin"))
        expected = ({SERVICE_SPEC_SCHEMA, SERVICE_SELECTED_SPEC_SCHEMA, SERVICE_ADMIN_SPEC_SCHEMA}
                    if name == "admin" else {SERVICE_SELECTED_SPEC_SCHEMA})
        if type(original) is not dict or original.get("schema") not in expected or role["schema"] != original["schema"]:
            raise ValueError("service-set nested role schema refused")
        scope = role["scope"]
        if (scope["capability_lane"] != ("admin-orchestrator" if name == "admin" else "mastermind-text")
                or scope["workload_profile"] != ("site_interactive" if name == "admin" else "site_batch")
                or scope["credential_ref"] != (entry.SERVICE_CREDENTIAL_REF if name == "admin"
                                               else entry.SERVICE_TEXT_CREDENTIAL_REF)):
            raise ValueError("service-set role mapping differs")
        roles.append(role)
    admin, text = roles
    tuples = {(role["scope"]["principal_id"], role["scope"]["caller_host"], role["scope"]["workload"])
              for role in roles}
    if (len(tuples) != 2 or admin["scope"]["native_host"] != text["scope"]["native_host"]
            or admin["scope"]["account_profile"] != text["scope"]["account_profile"]):
        raise ValueError("service-set distinct roles or common owners required")
    return roles



def _service_family_retained(schema):
    """Only an authenticated completed Go predecessor determines retained roles."""
    if schema is None:
        return 0
    if type(schema) is not str:
        raise ValueError("service family predecessor schema refused")
    if schema in ("mastermind.native_go_application_service.v1",
                  "mastermind.native_go_application_service.v3",
                  "mastermind.native_go_application_service.v4"):
        return 1
    if schema == "mastermind.native_go_application_service.v5":
        return 2
    raise ValueError("service family predecessor schema refused")


def _validate_service_family_specification(entry, specification, startup):
    if (type(specification) is not dict
            or set(specification) != {"schema", "operation_id", *_SERVICE_FAMILY_NAMES}
            or specification["schema"] != SERVICE_FAMILY_SPEC_SCHEMA
            or type(specification["operation_id"]) is not str
            or entry.IDENTITY.fullmatch(specification["operation_id"]) is None
            or startup is None):
        raise ValueError("invalid service family enrollment specification")
    scopes = []
    for name in _SERVICE_FAMILY_NAMES:
        role = specification[name]
        if type(role) is not dict or set(role) not in ({"scope"}, {"scope", "grant"}):
            raise ValueError("invalid service family role fields")
        scope = role["scope"]
        entry._service_family_scope_binding(startup, scope, "review-scope-" + name + "-" + "x" * 32, name)
        scopes.append(scope)
        if "grant" not in role:
            continue
        if name == "text" and "selection_purpose" not in scope:
            raise ValueError("new Text service requires an explicit selection purpose")
        if name == "admin" and "admin_pool_view" in scope and "selection_purpose" not in scope:
            raise ValueError("new Admin metadata permission requires an explicit selection purpose")
        grant = role["grant"]
        if (type(grant) is not dict
                or grant.get("principal_id") != scope["principal_id"]
                or grant.get("credential_ref") != scope["credential_ref"]
                or grant.get("caller_hosts") != [scope["caller_host"]]
                or grant.get("workloads") != [scope["workload"]]
                or grant.get("purpose") != "APPLICATION" or grant.get("enabled") is not True
                or grant.get("pool") != "go" or grant.get("route") != "/v1/chat/completions"
                or grant.get("stream") is not False
                or type(grant.get("models")) is not list or len(grant["models"]) != 1):
            raise ValueError("service family grant mapping differs")
    if (len({(scope["principal_id"], scope["caller_host"], scope["workload"]) for scope in scopes}) != 5
            or any(scope["native_host"] != scopes[0]["native_host"]
                or scope["account_profile"] != scopes[0]["account_profile"] for scope in scopes)):
        raise ValueError("service family distinct roles or common owners required")
    return [specification[name] for name in _SERVICE_FAMILY_NAMES]


def _service_routed_retained(schema):
    if schema != "mastermind.native_go_application_service.v6":
        raise ValueError("routed service requires completed v6 predecessor")
    return 5


def _service_routed_scopes_preserved(previous, scopes):
    """Only add explicit route scope and, when absent, a validated purpose."""
    if type(previous) is not list or type(scopes) is not list or len(previous) != 5 or len(scopes) != 5:
        return False
    for old, new in zip(previous, scopes):
        if type(old) is not dict or type(new) is not dict or "route_scope" not in new:
            return False
        retained = {key: value for key, value in new.items() if key != "route_scope"}
        allowed = set(old) | ({"selection_purpose"} if "selection_purpose" in retained else set())
        if set(retained) != allowed or any(retained.get(key) != value for key, value in old.items()):
            return False
    return True


def _validate_service_routed_specification(entry, specification, startup):
    if (type(specification) is not dict
            or set(specification) != {"schema", "operation_id", *_SERVICE_FAMILY_NAMES}
            or specification["schema"] != SERVICE_ROUTED_SPEC_SCHEMA or startup is None
            or type(specification["operation_id"]) is not str
            or entry.IDENTITY.fullmatch(specification["operation_id"]) is None):
        raise ValueError("invalid routed service enrollment specification")
    scopes, count = [], 0
    for name in _SERVICE_FAMILY_NAMES:
        role = specification[name]
        if (type(role) is not dict or set(role) != {"scope", "new_grants"}
                or type(role["new_grants"]) is not list):
            raise ValueError("invalid routed service role fields")
        scope = role["scope"]
        entry._service_routed_scope_binding(startup, scope, "review-scope-" + name + "-" + "x" * 32, name)
        scopes.append(scope)
        count += len(role["new_grants"])
        for grant in role["new_grants"]:
            if (type(grant) is not dict
                    or grant.get("principal_id") != scope["principal_id"]
                    or grant.get("credential_ref") != scope["credential_ref"]
                    or grant.get("caller_hosts") != [scope["caller_host"]]
                    or grant.get("workloads") != [scope["workload"]]
                    or grant.get("purpose") != "APPLICATION" or grant.get("enabled") is not True
                    or grant.get("pool") not in scope["route_scope"]["pools"]
                    or grant.get("route") != "/v1/chat/completions" or grant.get("stream") is not False):
                raise ValueError("routed service new grant mapping differs")
    if (count > 128
            or len({(scope["principal_id"], scope["caller_host"], scope["workload"]) for scope in scopes}) != 5
            or any(scope["native_host"] != scopes[0]["native_host"]
                or scope["account_profile"] != scopes[0]["account_profile"] for scope in scopes)):
        raise ValueError("routed service distinct roles or common owners required")
    return [specification[name] for name in _SERVICE_FAMILY_NAMES]


def _service_routed_after(startup, specification, before, predecessor_schema):
    _service_routed_retained(predecessor_schema)
    document = startup.policy_snapshot.parse_policy(before)
    after = before
    # Existing order and every inactive/narrowed row remain untouched. Only
    # full, explicit additions enter the incumbent overlap/parser checks.
    for name in _SERVICE_FAMILY_NAMES:
        for grant in specification[name]["new_grants"]:
            after, document = _service_candidate(startup, {"grant": grant},
                                                 generation.canonical(document) + b"\n")
    return after, document


def _service_routed_candidate(entry, startup, specification, before, completed):
    if completed is None:
        raise ValueError("routed service requires completed v6 predecessor")
    raw, _ = _service_snapshot(entry, entry.application_enrollment_paths(startup)["binding"], mode=0o600)
    previous = entry._service_json(raw)
    count = _service_routed_retained(previous["schema"])
    old_scopes, credentials = previous["scopes"], previous["credentials"]
    scopes = [specification[name]["scope"] for name in _SERVICE_FAMILY_NAMES]
    projected = tuple(entry._service_family_scope_binding(startup, scope, credential, name)
        for name, scope, credential in zip(_SERVICE_FAMILY_NAMES, old_scopes, credentials))
    if (len(completed[0]) != count or len(credentials) != count
            or not _service_routed_scopes_preserved(old_scopes, scopes) or projected != completed[0]
            or completed[1] != scopes[0]["native_host"]
            or completed[2] != Path(scopes[0]["account_profile"])):
        raise ValueError("routed service completed predecessor authentication differs")
    after, document = _service_routed_after(startup, specification, before, previous["schema"])
    return after, document, credentials, previous["schema"]


def _service_workload_retained(schema):
    if schema != "mastermind.native_go_application_service.v7":
        raise ValueError("workload service requires completed v7 predecessor")
    return 5


def _validate_service_workload_specification(entry, specification, startup, *, fresh_family=False):
    if (type(specification) is not dict
            or set(specification) != {"schema", "operation_id", *_SERVICE_WORKLOAD_NAMES}
            or specification["schema"] != (SERVICE_FRESH_FAMILY_SPEC_SCHEMA if fresh_family else SERVICE_WORKLOAD_SPEC_SCHEMA) or startup is None
            or type(specification["operation_id"]) is not str
            or entry.IDENTITY.fullmatch(specification["operation_id"]) is None):
        raise ValueError("invalid workload service enrollment specification")
    scopes, count = [], 0
    for index, name in enumerate(_SERVICE_WORKLOAD_NAMES):
        role = specification[name]
        expected = {"scope"} if index < 5 and not fresh_family else {"scope", "new_grants"}
        if (type(role) is not dict or set(role) != expected
                or (index >= 5 or fresh_family) and type(role["new_grants"]) is not list):
            raise ValueError("invalid workload service role fields")
        scope = role["scope"]
        if fresh_family and (type(scope) is not dict or "selection_purpose" not in scope):
            raise ValueError("fresh application family requires explicit selection purposes")
        entry._service_workload_scope_binding(startup, scope, "review-scope-" + name + "-" + "x" * 32, name)
        scopes.append(scope)
        if index < 5 and not fresh_family:
            continue
        count += len(role["new_grants"])
        for grant in role["new_grants"]:
            if (type(grant) is not dict
                    or grant.get("principal_id") != scope["principal_id"]
                    or grant.get("credential_ref") != scope["credential_ref"]
                    or grant.get("caller_hosts") != [scope["caller_host"]]
                    or grant.get("workloads") != [scope["workload"]]
                    or grant.get("purpose") != "APPLICATION" or grant.get("enabled") is not True
                    or grant.get("pool") not in scope["route_scope"]["pools"]
                    or grant.get("route") != "/v1/chat/completions" or grant.get("stream") is not False):
                raise ValueError("workload service new grant mapping differs")
    if (count > 128
            or len({(scope["principal_id"], scope["caller_host"], scope["workload"]) for scope in scopes}) != 8
            or any(scope["native_host"] != scopes[0]["native_host"]
                or scope["account_profile"] != scopes[0]["account_profile"] for scope in scopes)):
        raise ValueError("workload service distinct roles or common owners required")
    return [specification[name] for name in _SERVICE_WORKLOAD_NAMES]


def _service_workload_after(startup, specification, before, predecessor_schema, *, fresh_family=False):
    if fresh_family:
        _service_fresh_family_retained(predecessor_schema)
    else:
        _service_workload_retained(predecessor_schema)
    document = startup.policy_snapshot.parse_policy(before)
    after = before
    for name in (_SERVICE_WORKLOAD_NAMES if fresh_family else _SERVICE_WORKLOAD_NAMES[5:]):
        for grant in specification[name]["new_grants"]:
            after, document = _service_candidate(startup, {"grant": grant},
                                                 generation.canonical(document) + b"\n")
    return after, document


def _service_workload_candidate(entry, startup, specification, before, completed):
    if completed is None:
        raise ValueError("workload service requires completed v7 predecessor")
    raw, _ = _service_snapshot(entry, entry.application_enrollment_paths(startup)["binding"], mode=0o600)
    previous = entry._service_json(raw)
    count = _service_workload_retained(previous["schema"])
    old_scopes, credentials = previous["scopes"], previous["credentials"]
    scopes = [specification[name]["scope"] for name in _SERVICE_WORKLOAD_NAMES]
    projected = tuple(entry._service_routed_scope_binding(startup, scope, credential, name)
        for name, scope, credential in zip(_SERVICE_FAMILY_NAMES, old_scopes, credentials))
    if (len(completed[0]) != count or len(credentials) != count
            or old_scopes != scopes[:count] or projected != completed[0]
            or completed[1] != scopes[0]["native_host"]
            or completed[2] != Path(scopes[0]["account_profile"])):
        raise ValueError("workload service completed predecessor authentication differs")
    after, document = _service_workload_after(startup, specification, before, previous["schema"])
    return after, document, credentials, previous["schema"]


def _service_family_roles(specification, retained):
    roles = [specification[name] for name in _SERVICE_FAMILY_NAMES]
    for index, role in enumerate(roles):
        if set(role) != ({"scope"} if index < retained else {"scope", "grant"}):
            raise ValueError("service family retained authority must be scope-only")
    return roles


def _service_family_after(startup, specification, before, predecessor_schema):
    count = _service_family_retained(predecessor_schema)
    roles = _service_family_roles(specification, count)
    document = startup.policy_snapshot.parse_policy(before)
    after = before
    for role in roles[count:]:
        if role["grant"].get("enabled") is not True:
            raise ValueError("new service grant must be enabled")
        after, document = _service_candidate(startup, role, generation.canonical(document) + b"\n")
    return after, document


def _service_family_candidate(entry, startup, specification, before, completed):
    scopes = [specification[name]["scope"] for name in _SERVICE_FAMILY_NAMES]
    predecessor_schema, credentials = None, None
    if completed is not None:
        raw, _ = _service_snapshot(entry, entry.application_enrollment_paths(startup)["binding"], mode=0o600)
        predecessor = entry._service_json(raw)
        predecessor_schema = predecessor["schema"]
        count = _service_family_retained(predecessor_schema)
        retained_scopes = predecessor["scopes"] if count == 2 else [predecessor["scope"]]
        credentials = predecessor["credentials"] if count == 2 else [predecessor["credential"]]
        projected = tuple(entry._service_family_scope_binding(startup, scope, credential, name)
            for name, scope, credential in zip(_SERVICE_FAMILY_NAMES, retained_scopes, credentials))
        if (len(completed[0]) != count or retained_scopes != scopes[:count]
                or projected != completed[0]
                or completed[1] != scopes[0]["native_host"]
                or completed[2] != Path(scopes[0]["account_profile"])):
            raise ValueError("service family completed predecessor authentication differs")
    after, document = _service_family_after(startup, specification, before, predecessor_schema)
    return after, document, credentials, predecessor_schema


def _service_fresh_family_retained(schema):
    """Only authenticated completed family source determines retained identities."""
    if schema is None:
        return 0
    counts = {
        "mastermind.native_go_application_service.v1": 1,
        "mastermind.native_go_application_service.v3": 1,
        "mastermind.native_go_application_service.v4": 1,
        "mastermind.native_go_application_service.v5": 2,
        "mastermind.native_go_application_service.v6": 5,
        "mastermind.native_go_application_service.v7": 5,
        "mastermind.native_go_application_service.v8": 8,
        "mastermind.native_go_application_service.v10": 8,
    }
    if type(schema) is not str or schema not in counts:
        raise ValueError("fresh family predecessor schema refused")
    return counts[schema]


def _service_fresh_family_scopes_preserved(previous, scopes):
    """Add missing routing/purpose only; preserve every retained authority field."""
    if type(previous) is not list or type(scopes) is not list or len(previous) != len(scopes):
        return False
    for old, new in zip(previous, scopes):
        if (type(old) is not dict or type(new) is not dict
                or "route_scope" not in new or "selection_purpose" not in new
                or set(new) != set(old) | {"route_scope", "selection_purpose"}
                or any(new.get(key) != value for key, value in old.items())):
            return False
    return True


def _service_fresh_family_siblings(entry, startup, scopes):
    """The existing v9 readers authenticate siblings under the publication lock."""
    for profile in entry.SERVICE_ROLE_PROFILES:
        peer = entry.load_completed_application_startup(startup, profile)
        if not peer[0]:
            continue
        if (peer[1] != scopes[0]["native_host"]
                or peer[2] != Path(scopes[0]["account_profile"])
                or any(binding.principal_id == scope["principal_id"]
                       or binding.credential_ref == scope["credential_ref"]
                       for binding in peer[0] for scope in scopes)):
            raise ValueError("fresh family conflicts with completed role owners")


def _service_fresh_family_candidate(entry, startup, specification, before, completed):
    scopes = [specification[name]["scope"] for name in _SERVICE_WORKLOAD_NAMES]
    predecessor_schema, credentials = None, None
    if completed is not None:
        raw, _ = _service_snapshot(entry, entry.application_enrollment_paths(startup)["binding"], mode=0o600)
        previous = entry._service_json(raw)
        predecessor_schema = previous["schema"]
        count = _service_fresh_family_retained(predecessor_schema)
        plural = predecessor_schema in {
            entry.SERVICE_SET_SCHEMA, entry.SERVICE_FAMILY_SCHEMA, entry.SERVICE_ROUTED_SCHEMA,
            entry.SERVICE_WORKLOAD_SCHEMA, entry.SERVICE_FRESH_FAMILY_SCHEMA}
        old_scopes = previous["scopes"] if plural else [previous["scope"]]
        credentials = previous["credentials"] if plural else [previous["credential"]]
        if (len(completed[0]) != count or len(credentials) != count
                or entry.validate_application_service_document(startup, previous) != completed
                or not _service_fresh_family_scopes_preserved(old_scopes, scopes[:count])
                or completed[1] != scopes[0]["native_host"]
                or completed[2] != Path(scopes[0]["account_profile"])):
            raise ValueError("fresh family completed predecessor authentication differs")
    _service_fresh_family_siblings(entry, startup, scopes)
    after, document = _service_workload_after(
        startup, specification, before, predecessor_schema, fresh_family=True)
    return after, document, credentials, predecessor_schema


def _service_set_contract(entry, plan):
    if plan["schema"] == entry.SERVICE_FRESH_FAMILY_ENROLLMENT_SCHEMA:
        return (_SERVICE_WORKLOAD_NAMES, SERVICE_FRESH_FAMILY_SPEC_SCHEMA, entry.SERVICE_FRESH_FAMILY_SCHEMA,
                entry.SERVICE_FRESH_FAMILY_ENROLLMENT_SCHEMA, entry.SERVICE_FRESH_FAMILY_RECEIPT_SCHEMA,
                _service_fresh_family_retained(plan["predecessor_schema"]))
    if plan["schema"] == entry.SERVICE_WORKLOAD_ENROLLMENT_SCHEMA:
        return (_SERVICE_WORKLOAD_NAMES, SERVICE_WORKLOAD_SPEC_SCHEMA, entry.SERVICE_WORKLOAD_SCHEMA,
                entry.SERVICE_WORKLOAD_ENROLLMENT_SCHEMA, entry.SERVICE_WORKLOAD_RECEIPT_SCHEMA,
                _service_workload_retained(plan["predecessor_schema"]))
    if plan["schema"] == entry.SERVICE_ROUTED_ENROLLMENT_SCHEMA:
        return (_SERVICE_FAMILY_NAMES, SERVICE_ROUTED_SPEC_SCHEMA, entry.SERVICE_ROUTED_SCHEMA,
                entry.SERVICE_ROUTED_ENROLLMENT_SCHEMA, entry.SERVICE_ROUTED_RECEIPT_SCHEMA,
                _service_routed_retained(plan["predecessor_schema"]))
    if plan["schema"] == entry.SERVICE_SET_ENROLLMENT_SCHEMA:
        if type(plan["predecessor"]) is not bool:
            raise ValueError("service-set predecessor discriminator refused")
        return (("admin", "text"), SERVICE_SET_SPEC_SCHEMA, entry.SERVICE_SET_SCHEMA,
                entry.SERVICE_SET_ENROLLMENT_SCHEMA, entry.SERVICE_SET_RECEIPT_SCHEMA,
                int(plan["predecessor"]))
    if plan["schema"] == entry.SERVICE_FAMILY_ENROLLMENT_SCHEMA:
        return (_SERVICE_FAMILY_NAMES, SERVICE_FAMILY_SPEC_SCHEMA, entry.SERVICE_FAMILY_SCHEMA,
                entry.SERVICE_FAMILY_ENROLLMENT_SCHEMA, entry.SERVICE_FAMILY_RECEIPT_SCHEMA,
                _service_family_retained(plan["predecessor_schema"]))
    raise ValueError("service-set enrollment schema refused")


def _service_set_grants(specification, retained):
    if specification["schema"] == SERVICE_FRESH_FAMILY_SPEC_SCHEMA:
        return [grant for name in _SERVICE_WORKLOAD_NAMES for grant in specification[name]["new_grants"]]
    if specification["schema"] == SERVICE_WORKLOAD_SPEC_SCHEMA:
        return [grant for name in _SERVICE_WORKLOAD_NAMES[5:] for grant in specification[name]["new_grants"]]
    if specification["schema"] == SERVICE_ROUTED_SPEC_SCHEMA:
        return [grant for name in _SERVICE_FAMILY_NAMES for grant in specification[name]["new_grants"]]
    if specification["schema"] == SERVICE_FAMILY_SPEC_SCHEMA:
        return [role["grant"] for role in _service_family_roles(specification, retained)[retained:]]
    return [specification[name]["grant"] for name in ("admin", "text")]


def _service_set_credentials_match(plan, credentials, *, predecessor=False):
    if plan["schema"] == "native-go-service-enrollment.v10":
        count = _service_fresh_family_retained(plan["predecessor_schema"])
        expected = plan.get("predecessor_credential_sha256s", [])
        return (type(credentials) is list and len(credentials) == (count if predecessor else 8)
                and all(type(value) is str for value in credentials)
                and type(expected) is list and len(expected) == count
                and [generation.digest(value.encode("utf-8")) for value in credentials[:count]] == expected)
    if plan["schema"] == "native-go-service-enrollment.v8":
        count = _service_workload_retained(plan["predecessor_schema"])
        expected = plan.get("predecessor_credential_sha256s")
        return (type(credentials) is list and len(credentials) == (count if predecessor else 8)
                and all(type(value) is str for value in credentials)
                and type(expected) is list and len(expected) == count
                and [generation.digest(value.encode("utf-8")) for value in credentials[:count]] == expected)
    if plan["schema"] == "native-go-service-enrollment.v7":
        count = _service_routed_retained(plan["predecessor_schema"])
        expected = plan.get("predecessor_credential_sha256s")
        return (type(credentials) is list and len(credentials) == count
                and all(type(value) is str for value in credentials)
                and type(expected) is list and len(expected) == count
                and [generation.digest(value.encode("utf-8")) for value in credentials] == expected)
    if plan["schema"] == "native-go-service-enrollment.v6":
        count = _service_family_retained(plan["predecessor_schema"])
        expected = plan.get("predecessor_credential_sha256s", [])
        return [generation.digest(value.encode("utf-8")) for value in credentials[:count]] == expected
    return not plan["predecessor"] or generation.digest(credentials[0].encode("utf-8")) == plan["predecessor_credential_sha256"]


def _service_set_after(startup, specification, before, *, predecessor, predecessor_schema=None):
    if specification["schema"] == SERVICE_FRESH_FAMILY_SPEC_SCHEMA:
        return _service_workload_after(startup, specification, before, predecessor_schema, fresh_family=True)
    if specification["schema"] == SERVICE_WORKLOAD_SPEC_SCHEMA:
        return _service_workload_after(startup, specification, before, predecessor_schema)
    if specification["schema"] == SERVICE_ROUTED_SPEC_SCHEMA:
        return _service_routed_after(startup, specification, before, predecessor_schema)
    if specification["schema"] == SERVICE_FAMILY_SPEC_SCHEMA:
        return _service_family_after(startup, specification, before, predecessor_schema)
    """Derive reviewed accounts bytes without consulting mutable enrollment files."""
    roles = _validate_service_set_specification_entry(startup, specification)
    selected_roles = roles[1:] if predecessor else roles
    document = startup.policy_snapshot.parse_policy(before)
    after = before
    for role in selected_roles:
        if role["grant"].get("enabled") is not True:
            raise ValueError("new service grant must be enabled")
        after, document = _service_candidate(startup, role, generation.canonical(document) + b"\n")
    return after, document


def _service_set_candidate(entry, startup, specification, before, completed=None):
    """Preserve completed Admin authentication; only new roles add grant authority."""
    roles = _validate_service_set_specification_entry(startup, specification)
    scopes = [role["scope"] for role in roles]
    credentials = None
    if completed is not None:
        if (len(completed[0]) != 1 or completed[1] != scopes[0]["native_host"]
                or completed[2] != Path(scopes[0]["account_profile"])):
            raise ValueError("service-set requires one completed Admin predecessor")
        raw, _ = _service_snapshot(entry, entry.application_enrollment_paths(startup)["binding"], mode=0o600)
        document = entry._service_json(raw)
        if (document["schema"] not in {entry.SERVICE_SCHEMA, entry.SERVICE_SELECTED_SCHEMA, entry.SERVICE_ADMIN_SCHEMA}
                or document["scope"] != scopes[0]):
            raise ValueError("service-set completed Admin authentication differs")
        projected = entry._service_scope_binding(startup, scopes[0], document["credential"], admin=True)
        if projected != completed[0][0]:
            raise ValueError("service-set completed Admin authentication differs")
        credentials = [projected.credential]
    after, document = _service_set_after(startup, specification, before, predecessor=completed is not None)
    return after, document, credentials


def _validate_service_set_specification_entry(startup, specification):
    # The native source itself validates the private projection at publication;
    # installer validation has already checked the closed role mapping.
    return [specification["admin"], specification["text"]]


def _service_set_payload(entry, startup, plan, specification, scopes, credentials):
    return {"schema": (entry.SERVICE_FRESH_FAMILY_SCHEMA if plan["schema"] == entry.SERVICE_FRESH_FAMILY_ENROLLMENT_SCHEMA
                       else entry.SERVICE_WORKLOAD_SCHEMA if plan["schema"] == entry.SERVICE_WORKLOAD_ENROLLMENT_SCHEMA
                       else entry.SERVICE_ROUTED_SCHEMA if plan["schema"] == entry.SERVICE_ROUTED_ENROLLMENT_SCHEMA
                       else entry.SERVICE_FAMILY_SCHEMA if plan["schema"] == entry.SERVICE_FAMILY_ENROLLMENT_SCHEMA
                       else entry.SERVICE_SET_SCHEMA), "operation_id": plan["operation_id"],
        "plan_digest": plan["digest"], "source_generation": plan["source_generation"],
        "ingress_digest": plan["ingress_digest"], "scopes": scopes, "owners": plan["owners"],
        "credentials": credentials}


def _service_set_public(payload):
    return {key: value for key, value in payload.items() if key != "credentials"}


def _service_set_expiry(specification, *, predecessor=False, predecessor_schema=None):
    if specification["schema"] == SERVICE_FRESH_FAMILY_SPEC_SCHEMA:
        _service_fresh_family_retained(predecessor_schema)
        additions = _service_set_grants(specification, 0)
        return min(grant["expires_at"] for grant in additions) if additions else None
    if specification["schema"] == SERVICE_WORKLOAD_SPEC_SCHEMA:
        _service_workload_retained(predecessor_schema)
        additions = _service_set_grants(specification, 5)
        return min(grant["expires_at"] for grant in additions) if additions else None
    if specification["schema"] == SERVICE_ROUTED_SPEC_SCHEMA:
        _service_routed_retained(predecessor_schema)
        additions = _service_set_grants(specification, 5)
        return min(grant["expires_at"] for grant in additions) if additions else None
    names = (_SERVICE_FAMILY_NAMES[_service_family_retained(predecessor_schema):]
             if specification["schema"] == SERVICE_FAMILY_SPEC_SCHEMA
             else ("text",) if predecessor else ("admin", "text"))
    return min(specification[name]["grant"]["expires_at"] for name in names)


def _service_set_fresh_service(entry, startup, plan, specification, scopes):
    credentials = [secrets.token_urlsafe(48), secrets.token_urlsafe(48)]
    return _service_set_payload(entry, startup, plan, specification, scopes, credentials)



def _service_enrollment_accounts(startup, path, document, specification):
    # A legacy owner without application_grants conveys no APPLICATION authority.
    # Identity-only v10 may retain those exact bytes; every existing grant list
    # and every addition still goes through A's complete application parser.
    identity_only = (specification["schema"] == SERVICE_FRESH_FAMILY_SPEC_SCHEMA
        and all(not specification[name]["new_grants"] for name in _SERVICE_WORKLOAD_NAMES))
    if identity_only and "application_grants" not in document:
        if (document.get("schema") != "mastermind.provider_accounts.v1"
                or type(document.get("providers")) is not dict):
            raise ValueError("invalid identity-only account owner")
        return startup.policy_snapshot.parse_policy(generation.regular_bytes(path))
    return startup.broker_module._read_application_accounts(path)


def _service_role_peers(entry, startup, scope):
    peers = entry.load_all_completed_application_startup(startup)
    if (peers[0] and (peers[1] != scope["native_host"]
            or peers[2] != Path(scope["account_profile"]))
            or any(binding.principal_id == scope["principal_id"]
                   or binding.credential_ref == scope["credential_ref"] for binding in peers[0])):
        raise ValueError("role service conflicts with completed physical owners")


def prepare_go_service_enrollment(go_ingress_bundle, specification, output):
    go_ingress_bundle = _successor_directory(go_ingress_bundle)
    first, _, _, _ = _completed_go_for_service(go_ingress_bundle)
    store = Path(first["store"])
    output = Path(output).absolute()
    if (output.parent.resolve(strict=True) != output.parent or output.is_relative_to(store.parent)
            or os.path.lexists(output)):
        raise ValueError("fresh external service review bundle required")
    generation.require(output.parent, stat.S_ISDIR)
    with generation.publication_lock(store), _service_source(go_ingress_bundle) as context:
        ingress, selection, metadata, entry, startup = context
        specification = _service_specification(entry, specification, startup)
        fresh_family = specification["schema"] == SERVICE_FRESH_FAMILY_SPEC_SCHEMA
        workloads = specification["schema"] == SERVICE_WORKLOAD_SPEC_SCHEMA
        routed = specification["schema"] == SERVICE_ROUTED_SPEC_SCHEMA
        family = specification["schema"] in (SERVICE_FAMILY_SPEC_SCHEMA, SERVICE_ROUTED_SPEC_SCHEMA, SERVICE_WORKLOAD_SPEC_SCHEMA, SERVICE_FRESH_FAMILY_SPEC_SCHEMA)
        service_set = specification["schema"] in (SERVICE_SET_SPEC_SCHEMA, SERVICE_FAMILY_SPEC_SCHEMA, SERVICE_ROUTED_SPEC_SCHEMA, SERVICE_WORKLOAD_SPEC_SCHEMA, SERVICE_FRESH_FAMILY_SPEC_SCHEMA)
        role_names = _SERVICE_WORKLOAD_NAMES if workloads or fresh_family else _SERVICE_FAMILY_NAMES if family else ("admin", "text")
        predecessor_schema = None
        http = specification["schema"] == SERVICE_HTTP_SPEC_SCHEMA
        admin = specification["schema"] == SERVICE_ADMIN_SPEC_SCHEMA
        role = specification["schema"] == SERVICE_ROLE_SPEC_SCHEMA
        selected = specification["schema"] in (SERVICE_SELECTED_SPEC_SCHEMA, SERVICE_ADMIN_SPEC_SCHEMA, SERVICE_ROLE_SPEC_SCHEMA)
        paths = entry.application_enrollment_paths(startup,
            specification["scope"]["service_profile"] if role else None)
        if role:
            _service_role_peers(entry, startup, specification["scope"])
        if service_set:
            scopes = [specification[name]["scope"] for name in role_names]
            profile = Path(scopes[0]["account_profile"])
            completed = entry.load_completed_application_startup(startup) if any(os.path.lexists(path) for path in paths.values()) else None
        else:
            if any(os.path.lexists(path) for path in paths.values()):
                raise ValueError("service enrollment already has an original artifact")
            profile = Path(specification["scope"]["account_profile"])
        owners = _service_owner_identities(entry, startup, profile, application_http=http)
        before, identity = _service_snapshot(entry, startup.paths["accounts_path"])
        with startup.yaml_runtime.held_yaml(startup.yaml_archive, startup.yaml_provenance, startup.yaml_check):
            if fresh_family:
                after, document, credentials, predecessor_schema = _service_fresh_family_candidate(
                    entry, startup, specification, before, completed)
            elif workloads:
                after, document, credentials, predecessor_schema = _service_workload_candidate(
                    entry, startup, specification, before, completed)
            elif routed:
                after, document, credentials, predecessor_schema = _service_routed_candidate(
                    entry, startup, specification, before, completed)
            elif family:
                after, document, credentials, predecessor_schema = _service_family_candidate(
                    entry, startup, specification, before, completed)
            elif service_set:
                after, document, credentials = _service_set_candidate(entry, startup, specification, before, completed)
            else:
                after, document = _service_enrollment_candidate(startup, specification, before)
                credentials = None
            output.mkdir(mode=0o700)
            generation.atomic_bytes(output / "accounts.before.yaml", before, 0o600)
            generation.atomic_bytes(output / "accounts.after.yaml", after, 0o600)
            if _service_enrollment_accounts(startup, output / "accounts.after.yaml", document, specification) != document:
                raise ValueError("service candidate parser disagreement")
        expires = (_service_set_expiry(specification, predecessor=completed is not None,
                                      predecessor_schema=predecessor_schema)
                   if service_set else _service_grant_expiry(specification))
        if expires is not None and expires <= time.time():
            raise ValueError("service grant is already expired")
        if (_service_snapshot(entry, startup.paths["accounts_path"]) != (before, identity)
                or _service_owner_identities(entry, startup, profile, application_http=http) != owners):
            raise ValueError("service owners changed during preparation")
        plan = {"schema": entry.SERVICE_FRESH_FAMILY_ENROLLMENT_SCHEMA if fresh_family else entry.SERVICE_ROLE_ENROLLMENT_SCHEMA if role else entry.SERVICE_WORKLOAD_ENROLLMENT_SCHEMA if workloads else entry.SERVICE_ROUTED_ENROLLMENT_SCHEMA if routed else entry.SERVICE_FAMILY_ENROLLMENT_SCHEMA if family else entry.SERVICE_SET_ENROLLMENT_SCHEMA if service_set else
                entry.SERVICE_HTTP_ENROLLMENT_SCHEMA if http else entry.SERVICE_ADMIN_ENROLLMENT_SCHEMA if admin else
                entry.SERVICE_SELECTED_ENROLLMENT_SCHEMA if selected else entry.SERVICE_ENROLLMENT_SCHEMA,
            "operation_id": specification["operation_id"], "go_ingress_bundle": str(go_ingress_bundle),
            "ingress_digest": ingress["digest"], "source_generation": startup.generation,
            "store": str(store), "selection": selection,
            "installer_sha256": generation.digest(generation.regular_bytes(__file__)),
            "entry_sha256": metadata["files"][generation.GO_ENTRY],
            "owners": entry.application_service_owners(startup, application_http=http), "owner_identities": owners,
            "accounts_before": {"sha256": generation.digest(before), "identity": identity},
            "accounts_after_sha256": generation.digest(after)}
        if service_set:
            retained_count = (_service_fresh_family_retained(predecessor_schema) if fresh_family else
                              _service_workload_retained(predecessor_schema) if workloads else
                              _service_routed_retained(predecessor_schema) if routed else
                              _service_family_retained(predecessor_schema) if family else int(completed is not None))
            plan.update(scopes=scopes, grant_sha256=generation.digest(generation.canonical(
                _service_set_grants(specification, retained_count))))
            if family:
                plan["predecessor_schema"] = predecessor_schema
            else:
                plan["predecessor"] = completed is not None
            if credentials is not None:
                if family:
                    plan["predecessor_credential_sha256s"] = [generation.digest(value.encode()) for value in credentials]
                else:
                    plan["predecessor_credential_sha256"] = generation.digest(credentials[0].encode())
                custody, retained = {}, {}
                for name in ("binding", "intent", "receipt"):
                    raw, identity = _service_snapshot(entry, paths[name], mode=0o600)
                    custody[name] = {"sha256": generation.digest(raw), "identity": identity}
                    retained[name] = raw.decode("utf-8")
                verified = entry.validate_completed_application_records(startup,
                    retained["binding"].encode(), custody["binding"]["identity"],
                    retained["intent"].encode(), retained["receipt"].encode())
                if verified != completed:
                    raise ValueError("service-set predecessor changed during preparation")
                private_predecessor = output / _SERVICE_PREDECESSOR
                generation.atomic_bytes(private_predecessor, generation.canonical(retained) + b"\n", 0o600)
                private_raw, private_identity = _service_snapshot(entry, private_predecessor, mode=0o600)
                plan["predecessor_custody"] = custody
                plan["predecessor_private"] = {"sha256": generation.digest(private_raw), "identity": private_identity}
        else:
            plan.update(scope=specification["scope"], grant_sha256=generation.digest(generation.canonical(_service_grant_value(specification))))
        if http:
            plan.update(application_recipe=specification["application_recipe"],
                application_accounts=specification["grant"]["accounts"])
        plan["digest"] = generation.digest(generation.canonical(plan))
        generation.atomic_bytes(output / "specification.json", generation.canonical(specification) + b"\n", 0o600)
        generation.atomic_bytes(output / "PLAN.json", generation.canonical(plan) + b"\n", 0o600)
        if service_set and completed is not None:
            # Private predecessor bytes stay in this finite review owner. New
            # service credentials are minted only by the original apply.
            _service_set_predecessor(entry, startup, bundle=output, plan=plan, require_live=True)
        return plan


def _read_service_plan(bundle):
    bundle = _successor_directory(bundle)
    plan = _successor_json(bundle / "PLAN.json")
    http = type(plan) is dict and plan.get("schema") == "native-go-service-enrollment.v2"
    fresh_family = type(plan) is dict and plan.get("schema") == "native-go-service-enrollment.v10"
    workloads = type(plan) is dict and plan.get("schema") == "native-go-service-enrollment.v8"
    routed = type(plan) is dict and plan.get("schema") == "native-go-service-enrollment.v7"
    family = type(plan) is dict and plan.get("schema") in ("native-go-service-enrollment.v6", "native-go-service-enrollment.v7", "native-go-service-enrollment.v8", "native-go-service-enrollment.v10")
    service_set = type(plan) is dict and plan.get("schema") in ("native-go-service-enrollment.v5", "native-go-service-enrollment.v6", "native-go-service-enrollment.v7", "native-go-service-enrollment.v8", "native-go-service-enrollment.v10")
    retained_count = (_service_fresh_family_retained(plan.get("predecessor_schema")) if fresh_family else
                      _service_workload_retained(plan.get("predecessor_schema")) if workloads else
                      _service_routed_retained(plan.get("predecessor_schema")) if routed else
                      _service_family_retained(plan.get("predecessor_schema")) if family else
                      int(bool(plan.get("predecessor"))) if service_set else 0)
    fields = (_SERVICE_PLAN_FIELDS - {"scope"} | {"scopes", "predecessor_schema" if family else "predecessor"}) if service_set else _SERVICE_PLAN_FIELDS
    fields = fields | {"application_recipe", "application_accounts"} if http else fields
    if retained_count:
        fields |= {"predecessor_credential_sha256s" if family else "predecessor_credential_sha256",
                   "predecessor_custody", "predecessor_private"}
    if type(plan) is not dict or set(plan) != fields:
        raise ValueError("service enrollment plan shape differs")
    if generation.digest(generation.canonical({k: v for k, v in plan.items() if k != "digest"})) != plan["digest"]:
        raise ValueError("service enrollment plan digest differs")
    names = {p.name for p in bundle.iterdir()}
    retained = {_SERVICE_PREDECESSOR} if retained_count else set()
    required = _SERVICE_PREPARED_FILES | retained
    if not required <= names or names - required - {_SERVICE_PRIVATE}:
        raise ValueError("service enrollment bundle set differs")
    for path in bundle.iterdir():
        info = generation.require(path, stat.S_ISREG, 0o600)
        if info.st_nlink != 1:
            raise ValueError("service enrollment artifact has another link")
    specification = _successor_json(bundle / "specification.json")
    before = generation.regular_bytes(bundle / "accounts.before.yaml", 2 * 1024 * 1024)
    after = generation.regular_bytes(bundle / "accounts.after.yaml", 2 * 1024 * 1024)
    if (generation.digest(before) != plan["accounts_before"]["sha256"]
            or generation.digest(after) != plan["accounts_after_sha256"]
            or generation.digest(generation.regular_bytes(__file__)) != plan["installer_sha256"]):
        raise ValueError("service enrollment source commitment differs")
    return bundle, plan, specification, before, after


@contextlib.contextmanager
def _service_broker_lock(entry, startup, expected):
    """Same physical A flock, without constructing its schema-owning Broker."""
    path = startup.paths["lock_path"]
    _service_snapshot(entry, path, read=False)
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        held = os.fstat(fd)
        if (held.st_dev, held.st_ino) != (expected["dev"], expected["ino"]):
            raise ValueError("service broker lock identity differs")
        deadline = time.monotonic() + 2
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ValueError("service broker lock is busy") from None
                time.sleep(0.02)
        if entry.application_file_identity(path)["ino"] != held.st_ino or path.lstat().st_dev != held.st_dev:
            raise ValueError("service broker lock was replaced")
        yield
    finally:
        os.close(fd)


def _service_prepared(entry, path, raw, prepared, plan_digest):
    """Authenticate the inode reserved by this original publication intent."""
    record = _successor_json(prepared)
    stage = path.parent / (".application-service-" + plan_digest + "." + path.name)
    if (type(record) is not dict or set(record) != {"plan_digest", "target", "stage", "sha256", "identity"}
            or record["plan_digest"] != plan_digest or record["target"] != str(path)
            or record["stage"] != str(stage) or record["sha256"] != generation.digest(raw)
            or type(record["identity"]) is not dict
            or set(record["identity"]) != entry.SERVICE_IDENTITY_FIELDS
            or any(type(v) is not int or v < 0 for v in record["identity"].values())):
        raise ValueError("service prepared publication differs")
    return stage, record["identity"]


def _service_target(entry, path, raw, before, progress, prepared, plan_digest):
    """Observe original publication; a settled identical-byte inode is not adopted."""
    exists = os.path.lexists(path)
    mode = 0o600 if before is None else before["identity"]["mode"]
    observed = _service_snapshot(entry, path, mode=mode) if exists else None
    if os.path.lexists(progress):
        receipt = _successor_json(progress)
        if (observed is None or receipt != {"sha256": generation.digest(raw), "identity": observed[1]}
                or observed[0] != raw):
            raise ValueError("service committed target identity differs")
        return "committed", observed[1]
    # An unchanged payload is still the exact original preimage until this
    # operation publishes its staged inode. Equal bytes alone prove no effect.
    if (before is not None and observed is not None and observed[1] == before["identity"]
            and generation.digest(observed[0]) == before["sha256"]):
        return "preimage", observed[1]
    if observed is not None and observed[0] == raw:
        # Bytes alone cannot attribute a lost-ack write to this operation.
        # The original prepared inode must have moved, not been copied or
        # replaced with another identical file. Rename may advance ctime.
        if not os.path.lexists(prepared):
            raise ValueError("service target has no original publication commitment")
        stage, identity = _service_prepared(entry, path, raw, prepared, plan_digest)
        if (os.path.lexists(stage)
                or any(observed[1][key] != identity[key] for key in identity if key != "ctime_ns")
                or observed[1]["ctime_ns"] < identity["ctime_ns"]):
            raise ValueError("service target is not the original prepared inode")
        return "committed_receipt_missing", observed[1]
    if before is None and observed is None:
        return "absent", None
    raise ValueError("service target preimage or original effect differs")


def _publish_service_target(entry, path, raw, before, progress, prepared, plan_digest, mode):
    """Prepare/commit inode custody before one same-directory atomic rename."""
    stage = path.parent / (".application-service-" + plan_digest + "." + path.name)
    if os.path.lexists(prepared):
        stage, identity = _service_prepared(entry, path, raw, prepared, plan_digest)
        observed, current = _service_snapshot(entry, stage, mode=mode)
        if observed != raw or current != identity:
            raise ValueError("service original publication stage changed")
    else:
        if os.path.lexists(stage):
            raise ValueError("service publication stage lacks its original commitment")
        generation.atomic_bytes(stage, raw, mode)
        observed, identity = _service_snapshot(entry, stage, mode=mode)
        if observed != raw:
            raise ValueError("service publication stage readback differs")
        _record_once(prepared, {"plan_digest": plan_digest, "target": str(path),
            "stage": str(stage), "sha256": generation.digest(raw), "identity": identity})
    state, _ = _service_target(entry, path, raw, before, progress, prepared, plan_digest)
    if state not in {"absent", "preimage"}:
        raise ValueError("service target changed before original rename")
    if _service_snapshot(entry, stage, mode=mode) != (raw, identity):
        raise ValueError("service publication stage changed before original rename")
    os.replace(stage, path)
    generation.fsync_directory(path.parent)
    state, identity = _service_target(entry, path, raw, before, progress, prepared, plan_digest)
    if state != "committed_receipt_missing":
        raise ValueError("service original rename readback differs")
    return identity


def _service_set_predecessor(entry, startup, *, bundle, plan, require_live=False):
    """Authenticate retained predecessor bytes without exposing credentials in a plan."""
    _, _, _, _, _, retained_count = _service_set_contract(entry, plan)
    if not retained_count:
        return None
    custody = plan["predecessor_custody"]
    commitment = plan["predecessor_private"]
    if type(custody) is not dict or set(custody) != {"binding", "intent", "receipt"}:
        raise ValueError("service-set predecessor custody refused")
    for record in (commitment, *custody.values()):
        if (type(record) is not dict or set(record) != {"sha256", "identity"}
                or type(record["sha256"]) is not str or not generation.HEX.fullmatch(record["sha256"])
                or type(record["identity"]) is not dict
                or set(record["identity"]) != entry.SERVICE_IDENTITY_FIELDS
                or any(type(value) is not int or value < 0 for value in record["identity"].values())
                or record["identity"]["mode"] != 0o600 or record["identity"]["nlink"] != 1):
            raise ValueError("service-set predecessor commitment refused")
    raw, identity = _service_snapshot(entry, bundle / _SERVICE_PREDECESSOR, mode=0o600)
    if commitment != {"sha256": generation.digest(raw), "identity": identity}:
        raise ValueError("service-set private predecessor custody changed")
    retained = entry._service_json(raw)
    if (type(retained) is not dict or set(retained) != set(custody)
            or any(type(value) is not str for value in retained.values())):
        raise ValueError("service-set private predecessor shape refused")
    for name, value in retained.items():
        if generation.digest(value.encode("utf-8")) != custody[name]["sha256"]:
            raise ValueError("service-set retained predecessor differs")
    completed = entry.validate_completed_application_records(startup,
        retained["binding"].encode("utf-8"), custody["binding"]["identity"],
        retained["intent"].encode("utf-8"), retained["receipt"].encode("utf-8"))
    document = entry._service_json(retained["binding"].encode("utf-8"))
    fresh_family = plan["schema"] == entry.SERVICE_FRESH_FAMILY_ENROLLMENT_SCHEMA
    routed = plan["schema"] == entry.SERVICE_ROUTED_ENROLLMENT_SCHEMA
    family = plan["schema"] in (entry.SERVICE_FAMILY_ENROLLMENT_SCHEMA, entry.SERVICE_ROUTED_ENROLLMENT_SCHEMA, entry.SERVICE_WORKLOAD_ENROLLMENT_SCHEMA, entry.SERVICE_FRESH_FAMILY_ENROLLMENT_SCHEMA)
    if family:
        if document["schema"] != plan["predecessor_schema"]:
            raise ValueError("service family completed predecessor authentication differs")
        plural = document["schema"] in {
            entry.SERVICE_SET_SCHEMA, entry.SERVICE_FAMILY_SCHEMA, entry.SERVICE_ROUTED_SCHEMA,
            entry.SERVICE_WORKLOAD_SCHEMA, entry.SERVICE_FRESH_FAMILY_SCHEMA}
        scopes = document["scopes"] if plural else [document["scope"]]
        credential = document["credentials"] if plural else [document["credential"]]
        preserved = (_service_fresh_family_scopes_preserved(scopes, plan["scopes"][:retained_count]) if fresh_family
                     else _service_routed_scopes_preserved(scopes, plan["scopes"]) if routed
                     else scopes == plan["scopes"][:retained_count])
        if (document["schema"] != plan["predecessor_schema"]
                or len(completed[0]) != retained_count or not preserved
                or completed[1] != plan["scopes"][0]["native_host"]
                or completed[2] != Path(plan["scopes"][0]["account_profile"])
                or not _service_set_credentials_match(plan, credential, predecessor=True)):
            raise ValueError("service family completed predecessor authentication differs")
    else:
        if (document["schema"] not in {entry.SERVICE_SCHEMA, entry.SERVICE_SELECTED_SCHEMA, entry.SERVICE_ADMIN_SCHEMA}
                or len(completed[0]) != 1 or document["scope"] != plan["scopes"][0]
                or completed[1] != plan["scopes"][0]["native_host"]
                or completed[2] != Path(plan["scopes"][0]["account_profile"])
                or generation.digest(document["credential"].encode("utf-8")) != plan["predecessor_credential_sha256"]):
            raise ValueError("service-set completed predecessor authentication differs")
        credential = document["credential"]
    if require_live:
        paths = entry.application_enrollment_paths(startup)
        for name in custody:
            if _service_snapshot(entry, paths[name], mode=0o600) != (
                    retained[name].encode("utf-8"), custody[name]["identity"]):
                raise ValueError("service-set live predecessor changed")
    return credential


def _service_set_before(entry, path, commitment):
    """Require an exact preimage, including absence for a fresh enrollment."""
    if commitment is None:
        if os.path.lexists(path):
            raise ValueError("service-set has an unowned enrollment artifact")
        return
    raw, identity = _service_snapshot(entry, path, mode=commitment["identity"]["mode"])
    if commitment != {"sha256": generation.digest(raw), "identity": identity}:
        raise ValueError("service-set predecessor or accounts preimage changed")


def _service_set_transaction(bundle, plan, specification, before, after, *, reconcile_only=False):
    """Complete one closed v5/v6/v7/v8/v10 transition using the incumbent publication owners."""
    store = Path(plan["store"])
    original_ingress, _, _, _ = _completed_go_for_service(plan["go_ingress_bundle"])
    if original_ingress["store"] != str(store):
        raise ValueError("service publication owner differs from original ingress")
    with generation.publication_lock(store), _service_source(plan["go_ingress_bundle"]) as context:
        ingress, selection, metadata, entry, startup = context
        specification = _service_specification(entry, specification, startup)
        role_names, spec_schema, binding_schema, enrollment_schema, receipt_schema, retained_count = _service_set_contract(entry, plan)
        scopes = [specification[name]["scope"] for name in role_names]
        profile = Path(scopes[0]["account_profile"])
        if (specification["schema"] != spec_schema
                or ingress["digest"] != plan["ingress_digest"]
                or startup.generation != plan["source_generation"] or selection != plan["selection"]
                or plan["store"] != ingress["store"]
                or metadata["files"][generation.GO_ENTRY] != plan["entry_sha256"]
                or specification["operation_id"] != plan["operation_id"] or scopes != plan["scopes"]
                or entry.application_service_owners(startup) != plan["owners"]
                or _service_owner_identities(entry, startup, profile) != plan["owner_identities"]
                or generation.digest(generation.canonical(
                    _service_set_grants(specification, retained_count))) != plan["grant_sha256"]):
            raise ValueError("service-set plan no longer binds its original owners")
        with startup.yaml_runtime.held_yaml(startup.yaml_archive, startup.yaml_provenance, startup.yaml_check):
            expected_after, document = _service_set_after(startup, specification, before,
                predecessor=bool(retained_count), predecessor_schema=plan.get("predecessor_schema"))
            if (after != expected_after
                    or _service_enrollment_accounts(startup, bundle / "accounts.after.yaml", document, specification) != document):
                raise ValueError("service-set enrollment candidate differs")
        paths = entry.application_enrollment_paths(startup)
        previous = plan.get("predecessor_custody", {})
        intent = {"schema": enrollment_schema, "operation_id": plan["operation_id"],
            "plan_digest": plan["digest"], "source_generation": plan["source_generation"],
            "ingress_digest": plan["ingress_digest"], "bundle": str(bundle)}
        intent_raw = generation.canonical(intent) + b"\n"
        private = bundle / _SERVICE_PRIVATE
        names = ("intent", "binding", "accounts", "receipt")
        target_paths = dict(paths, accounts=startup.paths["accounts_path"])
        progress = {name: store / "bootstrap" / (plan["digest"] + ".service-" + name + ".json")
                    for name in names}
        prepared = {name: store / "bootstrap" / (plan["digest"] + ".service-" + name + "-prepared.json")
                    for name in names}
        stages = {name: path.parent / (".application-service-" + plan["digest"] + "." + path.name)
                  for name, path in target_paths.items()}
        private_receipt = store / "bootstrap" / (plan["digest"] + ".service-private.json")
        public = {"schema": enrollment_schema, "operation_id": plan["operation_id"],
                  "plan_digest": plan["digest"]}
        expected_public = {"schema": binding_schema, "operation_id": plan["operation_id"],
            "plan_digest": plan["digest"], "source_generation": plan["source_generation"],
            "ingress_digest": plan["ingress_digest"], "scopes": scopes, "owners": plan["owners"]}

        def original_private():
            raw, identity = _service_snapshot(entry, private, mode=0o600)
            if (not os.path.lexists(private_receipt)
                    or _successor_json(private_receipt) != {"sha256": generation.digest(raw), "identity": identity}):
                raise ValueError("original service credential commitment differs; adoption refused")
            payload = entry._service_json(raw)
            entry.validate_application_service_document(startup, payload)
            if (_service_set_public(payload) != expected_public
                    or not _service_set_credentials_match(plan, payload["credentials"])):
                raise ValueError("original service-set credential payload differs")
            return raw, identity

        def custody(raw, identity, *, intent_started):
            if (_read_service_plan(bundle) != (bundle, plan, specification, before, after)
                    or _completed_go_for_service(plan["go_ingress_bundle"])[1] != selection
                    or _service_owner_identities(entry, startup, profile) != plan["owner_identities"]
                    or original_private() != (raw, identity)):
                raise ValueError("service-set original custody changed before publication")
            _service_set_predecessor(entry, startup, bundle=bundle, plan=plan)
            state, _ = _service_target(entry, paths["intent"], intent_raw, previous.get("intent"),
                progress["intent"], prepared["intent"], plan["digest"])
            if intent_started and not state.startswith("committed"):
                raise ValueError("service-set original intent changed before publication")

        def settle(name, path, data, old, mode, *, publish):
            state, identity = _service_target(entry, path, data, old, progress[name], prepared[name], plan["digest"])
            if not state.startswith("committed"):
                if not publish:
                    return state, identity
                identity = _publish_service_target(entry, path, data, old, progress[name],
                    prepared[name], plan["digest"], mode)
            elif state == "committed_receipt_missing":
                generation.fsync_directory(path.parent)
                if _service_target(entry, path, data, old, progress[name], prepared[name],
                        plan["digest"]) != (state, identity):
                    raise ValueError("service-set recovered target changed before receipt")
            _record_once(progress[name], {"sha256": generation.digest(data), "identity": identity})
            return "committed", identity

        with _service_broker_lock(entry, startup, plan["owner_identities"]["lock_path"]):
            if _service_owner_identities(entry, startup, profile) != plan["owner_identities"]:
                raise ValueError("service owners changed before publication")
            retained_credential = _service_set_predecessor(entry, startup, bundle=bundle, plan=plan)
            retained_credentials = (retained_credential if plan["schema"] in (
                                     entry.SERVICE_FAMILY_ENROLLMENT_SCHEMA, entry.SERVICE_ROUTED_ENROLLMENT_SCHEMA,
                                     entry.SERVICE_WORKLOAD_ENROLLMENT_SCHEMA, entry.SERVICE_FRESH_FAMILY_ENROLLMENT_SCHEMA)
                                    else [retained_credential] if retained_count else []) or []
            state, _ = _service_target(entry, paths["intent"], intent_raw, previous.get("intent"),
                progress["intent"], prepared["intent"], plan["digest"])
            started = state.startswith("committed")
            if not started:
                if plan["schema"] == entry.SERVICE_FRESH_FAMILY_ENROLLMENT_SCHEMA:
                    _service_fresh_family_siblings(entry, startup, scopes)
                # Until this original intent is published all live predecessors
                # must still be present, even when private preparation resumed.
                _service_set_predecessor(entry, startup, bundle=bundle, plan=plan, require_live=True)
                for name in ("binding", "receipt"):
                    _service_set_before(entry, paths[name], previous.get(name))
                _service_set_before(entry, startup.paths["accounts_path"], plan["accounts_before"])
                if any(os.path.lexists(path) for name in ("binding", "accounts", "receipt")
                        for path in (progress[name], prepared[name], stages[name])):
                    raise ValueError("service-set publication precedes its original intent")
                if not os.path.lexists(private):
                    if any(os.path.lexists(path) for path in (
                            private_receipt, progress["intent"], prepared["intent"], stages["intent"])):
                        raise ValueError("service-set original credential is missing; regeneration refused")
                    if reconcile_only:
                        return dict(public, disposition="prepared")
                    expires = _service_set_expiry(specification, predecessor=bool(retained_count),
                            predecessor_schema=plan.get("predecessor_schema"))
                    if expires is not None and expires <= time.time():
                        raise ValueError("service grant expired before its original intent")
                    credentials = retained_credentials + [
                        secrets.token_urlsafe(48) for _ in range(len(role_names) - retained_count)]
                    payload = _service_set_payload(entry, startup, plan, specification, scopes, credentials)
                    entry.validate_application_service_document(startup, payload)
                    # Commit private custody before replacing working Admin
                    # enrollment. An uncommitted private write is never adopted.
                    generation.atomic_bytes(private, generation.canonical(payload) + b"\n", 0o600)
                    raw, identity = _service_snapshot(entry, private, mode=0o600)
                    _record_once(private_receipt, {"sha256": generation.digest(raw), "identity": identity})
                raw, private_identity = original_private()
                if reconcile_only:
                    return dict(public, disposition="staged")
                expires = _service_set_expiry(specification, predecessor=bool(retained_count),
                            predecessor_schema=plan.get("predecessor_schema"))
                if expires is not None and expires <= time.time():
                    raise ValueError("service grant expired before its original intent")
                custody(raw, private_identity, intent_started=False)
                _service_set_predecessor(entry, startup, bundle=bundle, plan=plan, require_live=True)
                _service_set_before(entry, startup.paths["accounts_path"], plan["accounts_before"])
                settle("intent", paths["intent"], intent_raw, previous.get("intent"), 0o600, publish=True)
            else:
                if not os.path.lexists(private):
                    raise ValueError("original service credential is missing; regeneration refused")
                raw, private_identity = original_private()
                custody(raw, private_identity, intent_started=True)
                settle("intent", paths["intent"], intent_raw, previous.get("intent"), 0o600, publish=False)

            targets = (("binding", paths["binding"], raw, previous.get("binding"), 0o600),
                ("accounts", startup.paths["accounts_path"], after, plan["accounts_before"],
                    plan["accounts_before"]["identity"]["mode"]))
            states = {name: _service_target(entry, path, data, old, progress[name], prepared[name], plan["digest"])
                      for name, path, data, old, _ in targets}
            if (states["accounts"][0].startswith("committed")
                    and not states["binding"][0].startswith("committed")):
                raise ValueError("service-set original publication order differs")
            all_committed = all(state.startswith("committed") for state, _ in states.values())
            if not all_committed:
                _service_set_before(entry, paths["receipt"], previous.get("receipt"))
                if any(os.path.lexists(path) for path in (
                        progress["receipt"], prepared["receipt"], stages["receipt"])):
                    raise ValueError("service-set completion precedes its targets")
                if reconcile_only:
                    return dict(public, disposition="partial" if states["binding"][0].startswith("committed") else "staged")
            for name, path, data, old, mode in targets:
                custody(raw, private_identity, intent_started=True)
                state, _ = settle(name, path, data, old, mode, publish=not reconcile_only)
                if state != "committed":
                    raise ValueError("service-set target changed during reconciliation")
            final = {name: _service_target(entry, path, data, old, progress[name], prepared[name], plan["digest"])[1]
                     for name, path, data, old, _ in targets}
            custody(raw, private_identity, intent_started=True)
            receipt = {"schema": receipt_schema, "operation_id": plan["operation_id"],
                "plan_digest": plan["digest"], "source_generation": plan["source_generation"],
                "ingress_digest": plan["ingress_digest"], "scopes": scopes,
                "binding_sha256": generation.digest(raw), "binding_identity": final["binding"],
                "accounts_sha256": generation.digest(after), "accounts_identity": final["accounts"]}
            receipt_raw = generation.canonical(receipt) + b"\n"
            # Completion is a receipt of already committed targets. Reconcile
            # may publish it, but cannot publish missing binding/accounts effects.
            settle("receipt", paths["receipt"], receipt_raw, previous.get("receipt"), 0o600, publish=True)
            entry.validate_completed_application_records(startup, raw, final["binding"], intent_raw, receipt_raw)
            return receipt


def _service_transaction(bundle, *, reconcile_only=False):
    bundle, plan, specification, before, after = _read_service_plan(bundle)
    if plan["schema"] in ("native-go-service-enrollment.v5", "native-go-service-enrollment.v6", "native-go-service-enrollment.v7", "native-go-service-enrollment.v8", "native-go-service-enrollment.v10"):
        return _service_set_transaction(bundle, plan, specification, before, after, reconcile_only=reconcile_only)
    store = Path(plan["store"])
    # Derive the lock owner from authenticated original lineage before opening
    # any plan-nominated lock path. Recheck the chain again under that lock.
    original_ingress, _, _, _ = _completed_go_for_service(plan["go_ingress_bundle"])
    if original_ingress["store"] != str(store):
        raise ValueError("service publication owner differs from original ingress")
    with generation.publication_lock(store), _service_source(plan["go_ingress_bundle"]) as context:
        ingress, selection, metadata, entry, startup = context
        specification = _service_specification(entry, specification, startup)
        http = specification["schema"] == SERVICE_HTTP_SPEC_SCHEMA
        admin = specification["schema"] == SERVICE_ADMIN_SPEC_SCHEMA
        role = specification["schema"] == SERVICE_ROLE_SPEC_SCHEMA
        selected = specification["schema"] in (SERVICE_SELECTED_SPEC_SCHEMA, SERVICE_ADMIN_SPEC_SCHEMA, SERVICE_ROLE_SPEC_SCHEMA)
        enrollment_schema = (entry.SERVICE_ROLE_ENROLLMENT_SCHEMA if role else entry.SERVICE_HTTP_ENROLLMENT_SCHEMA if http else
            entry.SERVICE_ADMIN_ENROLLMENT_SCHEMA if admin else
            entry.SERVICE_SELECTED_ENROLLMENT_SCHEMA if selected else entry.SERVICE_ENROLLMENT_SCHEMA)
        service_schema = (entry.SERVICE_ROLE_SCHEMA if role else entry.SERVICE_HTTP_SCHEMA if http else
            entry.SERVICE_ADMIN_SCHEMA if admin else
            entry.SERVICE_SELECTED_SCHEMA if selected else entry.SERVICE_SCHEMA)
        receipt_schema = (entry.SERVICE_ROLE_RECEIPT_SCHEMA if role else entry.SERVICE_HTTP_RECEIPT_SCHEMA if http else
            entry.SERVICE_ADMIN_RECEIPT_SCHEMA if admin else
            entry.SERVICE_SELECTED_RECEIPT_SCHEMA if selected else entry.SERVICE_RECEIPT_SCHEMA)
        projection = ({"application_recipe": specification["application_recipe"],
            "application_accounts": specification["grant"]["accounts"]} if http else {})
        paths = entry.application_enrollment_paths(startup,
            specification["scope"]["service_profile"] if role else None)
        profile = Path(specification["scope"]["account_profile"])
        if (plan["schema"] != enrollment_schema or ingress["digest"] != plan["ingress_digest"]
                or startup.generation != plan["source_generation"] or selection != plan["selection"]
                or plan["store"] != ingress["store"]
                or metadata["files"][generation.GO_ENTRY] != plan["entry_sha256"]
                or specification["operation_id"] != plan["operation_id"]
                or specification["scope"] != plan["scope"]
                or entry.application_service_owners(startup, application_http=http) != plan["owners"]
                or _service_owner_identities(entry, startup, profile, application_http=http) != plan["owner_identities"]
                or any(plan[key] != value for key, value in projection.items())
                or generation.digest(generation.canonical(_service_grant_value(specification))) != plan["grant_sha256"]):
            raise ValueError("service enrollment plan no longer binds its original owners")
        with startup.yaml_runtime.held_yaml(startup.yaml_archive, startup.yaml_provenance, startup.yaml_check):
            expected_after, document = _service_enrollment_candidate(startup, specification, before)
            if (after != expected_after
                    or startup.broker_module._read_application_accounts(bundle / "accounts.after.yaml") != document):
                raise ValueError("service enrollment candidate differs")
        intent = {"schema": enrollment_schema, "operation_id": plan["operation_id"],
            "plan_digest": plan["digest"], "source_generation": plan["source_generation"],
            "ingress_digest": plan["ingress_digest"], "bundle": str(bundle)}
        private = bundle / _SERVICE_PRIVATE
        progress = {name: store / "bootstrap" / (plan["digest"] + ".service-" + name + ".json")
                    for name in ("binding", "accounts")}
        prepared = {name: store / "bootstrap" / (plan["digest"] + ".service-" + name + "-prepared.json")
                    for name in ("binding", "accounts")}
        private_receipt = store / "bootstrap" / (plan["digest"] + ".service-private.json")
        public = {"schema": enrollment_schema, "operation_id": plan["operation_id"],
                  "plan_digest": plan["digest"]}
        with _service_broker_lock(entry, startup, plan["owner_identities"]["lock_path"]):
            if _service_owner_identities(entry, startup, profile, application_http=http) != plan["owner_identities"]:
                raise ValueError("service owners changed before publication")
            original = os.path.lexists(paths["intent"])
            if original:
                if _successor_json(paths["intent"]) != intent:
                    raise ValueError("foreign service enrollment intent")
                if not os.path.lexists(private):
                    raise ValueError("original service credential is missing; regeneration refused")
            else:
                if role:
                    # A prepared peer may have entered its original transaction
                    # since preparation. Do not publish across partial custody.
                    _service_role_peers(entry, startup, specification["scope"])
                stages = [path.parent / (".application-service-" + plan["digest"] + "." + path.name)
                          for path in (paths["binding"], startup.paths["accounts_path"])]
                if any(os.path.lexists(path) for path in (private, private_receipt, paths["binding"],
                        paths["receipt"], *progress.values(), *prepared.values(), *stages)):
                    raise ValueError("service enrollment has unowned effects")
                observed, identity = _service_snapshot(entry, startup.paths["accounts_path"])
                if identity != plan["accounts_before"]["identity"] or observed != before:
                    raise ValueError("service accounts preimage changed")
                if reconcile_only:
                    return dict(public, disposition="prepared")
                if _service_grant_expiry(specification) <= time.time():
                    raise ValueError("service grant expired before its original intent")
                _record_once(paths["intent"], intent)
                # The first intent owns the only credential generation. Any
                # interrupted intent without this payload requires reconciliation.
                payload = {"schema": service_schema, "operation_id": plan["operation_id"],
                    "plan_digest": plan["digest"], "source_generation": plan["source_generation"],
                    "ingress_digest": plan["ingress_digest"], "scope": plan["scope"],
                    "owners": plan["owners"], "credential": secrets.token_urlsafe(48), **projection}
                entry.validate_application_service_document(startup, payload)
                generation.atomic_bytes(private, generation.canonical(payload) + b"\n", 0o600)
                private_raw, private_identity = _service_snapshot(entry, private, mode=0o600)
                _record_once(private_receipt, {"sha256": generation.digest(private_raw), "identity": private_identity})
            raw, private_identity = _service_snapshot(entry, private, mode=0o600)
            if (not os.path.lexists(private_receipt)
                    or _successor_json(private_receipt) != {"sha256": generation.digest(raw), "identity": private_identity}):
                raise ValueError("original service credential commitment differs; adoption refused")
            payload = entry._service_json(raw)
            entry.validate_application_service_document(startup, payload)
            expected_public = {"schema": service_schema, "operation_id": plan["operation_id"],
                "plan_digest": plan["digest"], "source_generation": plan["source_generation"],
                "ingress_digest": plan["ingress_digest"], "scope": plan["scope"], "owners": plan["owners"], **projection}
            if {key: value for key, value in payload.items() if key != "credential"} != expected_public:
                raise ValueError("original service credential payload differs")
            targets = (("binding", paths["binding"], raw, None, 0o600),
                       ("accounts", startup.paths["accounts_path"], after, plan["accounts_before"],
                        plan["accounts_before"]["identity"]["mode"]))
            states = {name: _service_target(entry, path, data, old, progress[name], prepared[name], plan["digest"])
                      for name, path, data, old, _ in targets}
            if (states["accounts"][0].startswith("committed")
                    and not states["binding"][0].startswith("committed")):
                raise ValueError("service original publication order differs")
            all_committed = all(state.startswith("committed") for state, _ in states.values())
            if os.path.lexists(paths["receipt"]) and not all_committed:
                raise ValueError("service completion receipt conflicts with its targets")
            if reconcile_only and not all_committed:
                return dict(public, disposition="partial" if states["binding"][0].startswith("committed") else "staged")
            for name, path, data, old, mode in targets:
                if _read_service_plan(bundle) != (bundle, plan, specification, before, after):
                    raise ValueError("service bundle changed before target publication")
                if (_completed_go_for_service(plan["go_ingress_bundle"])[1] != selection
                        or _service_owner_identities(entry, startup, profile, application_http=http) != plan["owner_identities"]
                        or _successor_json(paths["intent"]) != intent
                        or _service_snapshot(entry, private, mode=0o600) != (raw, private_identity)
                        or _successor_json(private_receipt) != {"sha256": generation.digest(raw), "identity": private_identity}):
                    raise ValueError("service original custody changed before target publication")
                state, identity = _service_target(entry, path, data, old, progress[name], prepared[name], plan["digest"])
                if not state.startswith("committed"):
                    if reconcile_only:
                        raise ValueError("service target changed during reconciliation")
                    identity = _publish_service_target(entry, path, data, old, progress[name],
                                                       prepared[name], plan["digest"], mode)
                elif state == "committed_receipt_missing":
                    # The original rename may have completed before its parent
                    # fsync. Make that target durable before a bootstrap receipt
                    # can certify it; never rewrite or re-rename the target.
                    generation.fsync_directory(path.parent)
                    if _service_target(entry, path, data, old, progress[name], prepared[name],
                                       plan["digest"]) != (state, identity):
                        raise ValueError("service recovered target changed before receipt")
                _record_once(progress[name], {"sha256": generation.digest(data), "identity": identity})
            final = {name: _service_target(entry, path, data, old, progress[name], prepared[name], plan["digest"])[1]
                     for name, path, data, old, _ in targets}
            if (_service_owner_identities(entry, startup, profile, application_http=http) != plan["owner_identities"]
                    or _completed_go_for_service(plan["go_ingress_bundle"])[1] != selection
                    or _successor_json(paths["intent"]) != intent):
                raise ValueError("service original custody changed before completion")
            receipt = {"schema": receipt_schema, "operation_id": plan["operation_id"],
                "plan_digest": plan["digest"], "source_generation": plan["source_generation"],
                "ingress_digest": plan["ingress_digest"], "scope": plan["scope"],
                "binding_sha256": generation.digest(raw), "binding_identity": final["binding"],
                "accounts_sha256": generation.digest(after), "accounts_identity": final["accounts"]}
            if http:
                receipt.update(application_recipe_digest=specification["grant"]["recipe_digest"],
                    source_projection_sha256=specification["application_recipe"]["source_projection_sha256"],
                    provider_profile_identity=plan["owner_identities"]["provider_profile"])
            _record_once(paths["receipt"], receipt)
            return receipt



def apply_go_service_enrollment(bundle):
    return _service_transaction(bundle)


def reconcile_go_service_enrollment(bundle):
    return _service_transaction(bundle, reconcile_only=True)


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


def _task_bridge_branch(python, launcher, store):
    """The exact bridge branch this installer appends to the original task source.

    The retained forward admission reuses these exact bytes, so the interpreter,
    the arguments and every original business byte are preserved and only the
    launcher reference is transformed.
    """
    command = [str(python), str(launcher), "exec", "--store", str(store), "--entry", "task", "--"]
    return ("\n# " + BRIDGE_MARKER + "\nif __name__ == '__main__':\n"
            "    import os as _native_ingress_os\n"
            "    import sys as _native_ingress_sys\n"
            f"    _native_ingress_os.execv({str(python)!r}, "
            f"{command!r} + _native_ingress_sys.argv[1:])\n\n")


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
    branch = _task_bridge_branch(python, launcher, store)
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
    prepare_retained = sub.add_parser("prepare-go-retained")
    prepare_retained.add_argument("--prior-successor-bundle", type=Path, required=True)
    prepare_retained.add_argument("--target-generation", required=True)
    prepare_retained.add_argument("--component-bundle", type=Path, required=True)
    prepare_retained.add_argument("--output", type=Path, required=True)
    for command in ("apply-go-retained", "reconcile-go-retained"):
        action = sub.add_parser(command)
        action.add_argument("--bundle", type=Path, required=True)
    prepare_service = sub.add_parser("prepare-go-service")
    prepare_service.add_argument("--go-ingress-bundle", type=Path, required=True)
    prepare_service.add_argument("--specification", type=Path, required=True)
    prepare_service.add_argument("--output", type=Path, required=True)
    for command in ("apply-go-service", "reconcile-go-service"):
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
    elif args.command == "prepare-go-retained":
        result = prepare_retained_go(args.prior_successor_bundle, args.target_generation,
                                     args.component_bundle, args.output)
    elif args.command == "apply-go-retained":
        result = apply_retained_go(args.bundle)
    elif args.command == "reconcile-go-retained":
        result = reconcile_retained_go(args.bundle)
    elif args.command == "prepare-go-service":
        result = prepare_go_service_enrollment(args.go_ingress_bundle, args.specification, args.output)
    elif args.command == "apply-go-service":
        result = apply_go_service_enrollment(args.bundle)
    elif args.command == "reconcile-go-service":
        result = reconcile_go_service_enrollment(args.bundle)
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
