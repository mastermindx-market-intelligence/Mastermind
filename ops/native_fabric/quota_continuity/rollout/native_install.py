#!/usr/bin/env python3
"""Two-phase native ingress installation CANDIDATE; no worker/process control.

prepare writes only a review bundle. phase1 changes pool and the fabric_task CLI
branch. phase2 changes the flat remote controller only after an existing owner
supplies a bound legacy-producer reconciliation receipt. The receipt is an
explicit operational prerequisite, not process/lifecycle authority invented here.
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

SCHEMA = "native-ingress-bootstrap.v1"
DRAIN_SCHEMA = "native-ingress-legacy-producers-reconciled.v1"
BRIDGE_MARKER = "NATIVE_GENERATION_CLI_BRIDGE_V1"


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
    for command in ("phase1", "phase2", "rollback"):
        action = sub.add_parser(command)
        action.add_argument("--bundle", type=Path, required=True)
        if command == "phase2":
            action.add_argument("--legacy-receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.store, args.initial, args.pool_path, args.output)
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
