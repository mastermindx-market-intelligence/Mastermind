#!/usr/bin/env python3
"""Offline-only qualification of one Cursor 4.6 selector edit over sealed native code.

This does not publish or select anything in the installed store, run paid
models, acquire leases, or edit installed source or provider state.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
NATIVE = HERE.parent / "quota_continuity" / "rollout" / "native_generation.py"
spec = importlib.util.spec_from_file_location("cursor46_native_generation", NATIVE)
generation = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(generation)

SEALED_PREDECESSORS = {
    "9eec6f73903fabfdd6d15bfe6f815f652f0946b5838cef6d40e96ca5b7e7f185":
        "4311200ae485ffd19b2560434e46c0c01899fbb58f0793c198292dba6004503b",
    "8cefc4b27b2036f86bcec1d626e864f45f792e2c290ab8de56fbde89f78ac94a":
        "747a55a50fb1ae579d18ae4decc6e3b077eb4b927a3968b61abaeeeb6292f132",
}
PICK = "ext/pick.py"
HISTORICAL_OVERLAY = HERE / "overlay" / "pick.py"
CHANGES = (
    (
        'return (model == "cursor-grok-4.6-high" and _grok_exhausted()\n'
        '            and policy_allows("grok", task_class, doc)[0])',
        '''if model != "cursor-grok-4.6-high":
        return False
    if not policy_allows("grok", task_class, doc)[0]:
        return False
    if _grok_exhausted():
        return True
    tc = task_class.lower()
    # R30's fixed labor boundary must not be reclassified away by YAML.
    if tc in LABOR_CLASSES_R30:
        return False
    if tc not in ("review", "audit") and (
            tc in EXECUTE_CLASSES_DEFAULT or is_execute_class(tc, doc)):
        return False
    return (tc == "review" or is_judgment_class(tc, doc)
            or tc in operator_classes(doc))''',
    ),
    (
        "    # Chairman's quota-only exception follows this exact Grok model's class\n"
        "    # capability. Composer and ordinary Cursor routes retain R30 unchanged.",
        "    # Exact Cursor Grok 4.6-high manual judgment inherits Grok role eligibility.\n"
        "    # Labor retains the old Grok-exhausted-only exception (R30);\n"
        "    # ordinary Cursor and automatic fallback remain unchanged.",
    ),
    (
        'return "NONE reason=Cursor Grok alias requires exhausted weekly Grok and eligible Grok task"',
        'return "NONE reason=Cursor Grok 4.6 alias requires eligible Grok task"',
    ),
    (
        '        # grok_before_cursor: if grok not exhausted and fits, prefer it\n'
        '        tc = task_class.lower()\n'
        '        if tc in ("fix_build", "high_level"):\n'
        '            if not _grok_exhausted() and _slot_concurrent("grok") < _pool_cap("grok"):\n'
        '                return False, "grok_before_cursor policy"',
        '        # Grok-first is an AUTO preference, not a veto of the one exact\n'
        '        # manually pinned Cursor Grok 4.6 review/judgment route.\n'
        '        # Labor still needs Grok exhaustion through the affinity gate.\n'
        '        tc = task_class.lower()\n'
        '        if tc in ("fix_build", "high_level") and model != "cursor-grok-4.6-high":\n'
        '            if not _grok_exhausted() and _slot_concurrent("grok") < _pool_cap("grok"):\n'
        '                return False, "grok_before_cursor policy"',
    ),
)

# Exact current APPLICATION-aware picker, separate from the immutable installed
# predecessors above. Only the offline legacy-role transform changes; explicit
# APPLICATION observations keep their existing quota-only semantics.
APPLICATION_PICKER_SHA256 = "5d37967731337fa6d49a6a119d415c66fcc35802c167b16de7e8a1751f950892"
# A separate closed AUTO prelease fallback adds pool-exclusion selector code.
# Its exact full-source SHA is admitted here without treating an arbitrary
# caller-edited picker as a qualified installed/manual Cursor predecessor.
BROKER_BUSY_PICKER_SHA256 = "c433384faab5862a05dcc4bd84273ee1b5aa9293271166079c2874375e46a057"
APPLICATION_AFFINITY_BEFORE = '''    if model != "cursor-grok-4.6-high":
        return False
    if exhausted is None:
        if application:
            return False
        exhausted = _grok_exhausted()
    if not exhausted:
        return False
    if application:
        return policy_allows("grok", task_class, doc, now=now,
                             grok_exhausted=exhausted)[0]
    return policy_allows("grok", task_class, doc)[0]'''
APPLICATION_AFFINITY_AFTER = '''    if model != "cursor-grok-4.6-high":
        return False
    if application:
        if exhausted is None or not exhausted:
            return False
        return policy_allows("grok", task_class, doc, now=now,
                             grok_exhausted=exhausted)[0]
    if not policy_allows("grok", task_class, doc)[0]:
        return False
    if exhausted is None:
        exhausted = _grok_exhausted()
    if exhausted:
        return True
    tc = task_class.lower()
    if tc in LABOR_CLASSES_R30:
        return False
    if tc not in ("review", "audit") and (
            tc in EXECUTE_CLASSES_DEFAULT or is_execute_class(tc, doc)):
        return False
    return (tc == "review" or is_judgment_class(tc, doc)
            or tc in operator_classes(doc))'''


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def apply_reviewed_hunks(raw: bytes) -> bytes:
    """Pure source transform. No historical release or installed file is mutated."""
    text = raw.decode("utf-8")
    original_overlay = HISTORICAL_OVERLAY.read_text(encoding="utf-8")
    changes = CHANGES
    if sha(raw) in (APPLICATION_PICKER_SHA256, BROKER_BUSY_PICKER_SHA256):
        # Only two fully hash-bound application source epochs may take the
        # closed affinity-specific transform; unrelated drift still refuses.
        old, new = APPLICATION_AFFINITY_BEFORE, APPLICATION_AFFINITY_AFTER
        if text.count(old) != 1 or text.count(new) != 0:
            raise ValueError("reviewed_application_selector_hunk_identity_mismatch")
        text = text.replace(old, new, 1)
        changes = CHANGES[1:]
    for old, new in changes:
        if (text.count(old) != 1 or text.count(new) != 0
                or original_overlay.count(old) != 1):
            raise ValueError("reviewed_selector_hunk_identity_mismatch")
        text = text.replace(old, new, 1)
    ast.parse(text, filename="qualified-native-cursor46-pick.py")
    output = text.encode("utf-8")
    if output == raw:
        raise ValueError("no_candidate_change")
    return output


def patched(raw: bytes, predecessor: str) -> bytes:
    expected = SEALED_PREDECESSORS.get(predecessor)
    if expected is None or sha(raw) != expected:
        raise ValueError("sealed_picker_preimage_changed")
    return apply_reviewed_hunks(raw)


def run(store: Path, stage: Path | None) -> dict:
    store = store.resolve(strict=True)
    original_pointer = (store / "CURRENT.json").read_bytes()
    current = generation.current(store)
    if current is None or current["generation"] not in SEALED_PREDECESSORS:
        raise ValueError("installed_native_predecessor_changed")
    predecessor = current["generation"]
    sealed, incumbent = generation.verify(store, predecessor)
    originals = {rel: (sealed / rel).read_bytes() for rel in incumbent["files"]}
    if set(originals) != set(incumbent["files"]):
        raise ValueError("installed_code_manifest_incomplete")
    if any(sha(originals[rel]) != expected for rel, expected in incumbent["files"].items()):
        raise ValueError("installed_code_manifest_drift")
    successor = dict(originals)
    successor[PICK] = patched(originals[PICK], predecessor)
    hashes = {rel: sha(raw) for rel, raw in successor.items()}
    changed = sorted(rel for rel in hashes if hashes[rel] != incumbent["files"][rel])
    if changed != [PICK]:
        raise ValueError("native_generation_delta_not_single_file")
    stable_ext = (store.parent / "ext").resolve(strict=True)
    predicted = generation.digest(generation.canonical(
        generation.descriptor(hashes, stable_ext)))
    with tempfile.TemporaryDirectory(prefix="cursor46-qualification-") as tmp:
        temp = Path(tmp).resolve(strict=True)
        fake = temp / "fake-owner" / "ext"
        fake.mkdir(parents=True)
        def write_source(folder: Path, files: dict[str, bytes]) -> Path:
            (folder / "ext").mkdir(parents=True)
            for rel, data in files.items():
                target = folder / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            return folder
        prior = generation.publish(write_source(temp / "prior-source", originals),
                                   fake, incumbent["files"])
        scratch = fake.parent / "native-code-releases"
        before = generation.select(scratch, prior.name, None)
        if before["sequence"] != 1:
            raise ValueError("scratch_predecessor_not_selected")
        issued = generation.publish(write_source(temp / "new-source", successor), fake, hashes)
        _, qualified = generation.verify(scratch, issued.name)
        if qualified["files"] != hashes:
            raise ValueError("scratch_manifest_changed")
        chosen = generation.select(scratch, issued.name, prior.name)
        if chosen["sequence"] != 2 or chosen["previous"] != prior.name:
            raise ValueError("scratch_CAS_success_unqualified")
        try:
            generation.select(scratch, prior.name, prior.name)
        except ValueError as exc:
            if "compare-and-swap" not in str(exc):
                raise
        else:
            raise ValueError("scratch_stale_CAS_not_refused")
    if ((store / "CURRENT.json").read_bytes() != original_pointer
            or generation.current(store) != current):
        raise ValueError("installed_native_selection_moved_during_qualification")
    result = {
        "schema": "mastermind.fabric_cursor46_sealed_prepublication.v2",
        "state": "QUALIFIED_SOURCE_ONLY_NOT_INSTALLED",
        "installed_predecessor": predecessor,
        "candidate_generation_expected": predicted,
        "file_count": len(hashes),
        "changed_files": changed,
        "candidate_pick_sha256": hashes[PICK],
        "manifest_sha256": sha(generation.canonical(hashes)),
        "scratch_previous_select": "PASS",
        "scratch_candidate_verify_select": "PASS",
        "scratch_stale_CAS_refusal": "PASS",
        "installed_selection_unchanged": True,
        "protected_merge_review_and_current_CAS_required": True,
    }
    if stage is not None:
        stage = stage.absolute()
        approved_root = Path("/Volumes/Mastermind/agent-workspaces").resolve(strict=True)
        if (stage.exists() or stage.is_symlink()
                or stage.parent.resolve(strict=True) != approved_root
                or not stage.name.startswith("fabric-cursor46-stage-")):
            raise ValueError("release_stage_must_be_new_and_approved_root")
        stage.mkdir(mode=0o700)
        staged_source = stage / "source"
        (staged_source / "ext").mkdir(parents=True, mode=0o700)
        for rel, data in successor.items():
            target = staged_source / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (stage / "manifest.json").write_bytes(generation.canonical(hashes) + b"\n")
        (stage / "QUALIFICATION.json").write_bytes(
            generation.canonical(result) + b"\n")
        result["stage_path"] = str(stage)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-store", type=Path, required=True)
    parser.add_argument("--release-stage", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.installed_store, args.release_stage), sort_keys=True))


if __name__ == "__main__":
    main()
