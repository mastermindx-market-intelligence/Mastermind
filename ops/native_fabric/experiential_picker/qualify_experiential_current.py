#!/usr/bin/env python3
"""Offline qualification of the manual-only Experiential picker route overlay.

Publication and selection occur exclusively in a fresh temporary fake owner,
never in the provided installed store. No provider, broker, worker, key or
paid call is started. With ``--installed-store`` the current native generation
is discovered dynamically through read-only verification and must be one of
the sealed predecessors; without it, qualification runs source-only against
the sealed in-repo candidate snapshot (itself the sealed current-generation
picker preimage) and reports the installed-store limitation explicitly.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
NATIVE = HERE.parent / "quota_continuity" / "rollout" / "native_generation.py"
ROUTE = HERE / "experiential_manual_route.py"

_spec = importlib.util.spec_from_file_location("experiential_native_generation", NATIVE)
generation = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(generation)

_rspec = importlib.util.spec_from_file_location("experiential_manual_route_qual", ROUTE)
route = importlib.util.module_from_spec(_rspec)
assert _rspec.loader is not None
_rspec.loader.exec_module(route)

# Synthetic non-picker closure files for the scratch fake-owner composition.
# They are clearly-named placeholders: the only reviewed delta is ext/pick.py.
PLACEHOLDERS = {
    "pool": "#!/bin/sh\n# experiential_picker scratch placeholder (not a CLI)\nexit 9\n",
    "ext/fabric_task.py": '# experiential_picker scratch placeholder (not a CLI)\n',
    "ext/remote_sub.sh": "#!/bin/sh\n# experiential_picker scratch placeholder\nexit 9\n",
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_source(folder: Path, files: dict[str, bytes]) -> Path:
    (folder / "ext").mkdir(parents=True)
    for rel, data in files.items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return folder


def scratch_cas_qualification(candidate_pick: bytes, sealed_pick: bytes) -> dict:
    """Reuse the incumbent CAS publisher in a temporary fake owner only."""
    base = {rel: text.encode("utf-8") for rel, text in PLACEHOLDERS.items()}
    base[route.PICK] = sealed_pick
    successor = dict(base)
    successor[route.PICK] = candidate_pick
    hashes = {rel: sha(raw) for rel, raw in successor.items()}
    with tempfile.TemporaryDirectory(prefix="experiential-picker-qualification-") as tmp:
        temp = Path(tmp).resolve(strict=True)
        fake = temp / "fake-owner" / "ext"
        fake.mkdir(parents=True)
        prior = generation.publish(write_source(temp / "prior-source", base),
                                   fake, {rel: sha(raw) for rel, raw in base.items()})
        scratch = fake.parent / "native-code-releases"
        before = generation.select(scratch, prior.name, None)
        if before["sequence"] != 1:
            raise ValueError("scratch_predecessor_not_selected")
        issued = generation.publish(write_source(temp / "new-source", successor),
                                    fake, hashes)
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
        base_hashes = {rel: sha(raw) for rel, raw in base.items()}
        changed = sorted(rel for rel in hashes if hashes[rel] != base_hashes.get(rel))
        if changed != [route.PICK]:
            raise ValueError("native_generation_delta_not_single_file")
    return {
        "scratch_previous_select": "PASS",
        "scratch_candidate_verify_select": "PASS",
        "scratch_stale_CAS_refusal": "PASS",
        "changed_files": changed,
        "candidate_pick_sha256": hashes[route.PICK],
        "manifest_sha256": sha(generation.canonical(hashes)),
    }


def compose_with_partner(candidate_pick: bytes, partner_path: Path) -> dict:
    """Verify both composition orders with a sibling reviewed overlay.

    The partner module must expose ``apply_reviewed_hunks(raw) -> bytes``.
    Nothing is written; both modules refuse any region overlap by exact-once
    identity, so a successful both-orders composition proves disjointness.
    """
    spec = importlib.util.spec_from_file_location("experiential_compose_partner", partner_path)
    partner = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(partner)
    theirs_first = route.apply_reviewed_hunks(
        partner.apply_reviewed_hunks(candidate_pick))
    ours_first = partner.apply_reviewed_hunks(
        route.apply_reviewed_hunks(candidate_pick))
    if theirs_first != ours_first:
        raise ValueError("composition_order_divergence")
    return {
        "compose_partner": str(partner_path.name),
        "compose_theirs_first": "PASS",
        "compose_ours_first": "PASS",
        "composed_pick_sha256": sha(theirs_first),
    }


def run(store: Path | None, partner: Path | None, stage: Path | None,
        witness_draft: Path | None) -> dict:
    # Sealed snapshot integrity first: every declared lineage fixture must
    # still match its protected digest, and the candidate snapshot must be
    # the exact sealed current-generation picker preimage.
    sealed = {}
    for name in route.SNAPSHOT_PICKER_SEALS:
        sealed[name] = sha(route.snapshot_picker(name))
    if sealed["candidate"] != route.SEALED_PREDECESSORS[route.CURRENT_GENERATION]:
        raise ValueError("current_generation_snapshot_changed")
    preimages = json.loads((HERE.parent / "quota_continuity" / "rollout" /
                            "native-preimages.json").read_text())
    if preimages["files"].get("pick.py") != sealed["source"]:
        raise ValueError("source_manifest_pick_preimage_drift")

    candidate_pick = route.patched(route.snapshot_picker("candidate"),
                                   route.CURRENT_GENERATION)
    result = {
        "schema": "mastermind.fabric_experiential_sealed_prepublication.v1",
        "state": "QUALIFIED_SOURCE_ONLY_NOT_INSTALLED",
        "installed_predecessor": route.CURRENT_GENERATION,
        "snapshot_seals": sealed,
        "lineage_applicability": {
            name: "PASS" for name in route.SNAPSHOT_PICKER_SEALS
        },
        "witness_schema": route.WITNESS_SCHEMA,
        "witness_file": route.WITNESS_FILE,
    }
    for name in route.SNAPSHOT_PICKER_SEALS:
        route.apply_reviewed_hunks(route.snapshot_picker(name), snapshots=(name,))

    if store is not None:
        store = store.resolve(strict=True)
        original_pointer = (store / "CURRENT.json").read_bytes()
        current = generation.current(store)
        if current is None or current["generation"] not in route.SEALED_PREDECESSORS:
            raise ValueError("installed_native_predecessor_changed")
        predecessor = current["generation"]
        sealed_store, incumbent = generation.verify(store, predecessor)
        originals = {rel: (sealed_store / rel).read_bytes() for rel in incumbent["files"]}
        if any(sha(originals[rel]) != expected
               for rel, expected in incumbent["files"].items()):
            raise ValueError("installed_code_manifest_drift")
        if sha(originals[route.PICK]) != route.SEALED_PREDECESSORS[predecessor]:
            raise ValueError("sealed_picker_preimage_changed")
        result["installed_predecessor"] = predecessor
        result["installed_manifest_files"] = len(incumbent["files"])
        if (store / "CURRENT.json").read_bytes() != original_pointer:
            raise ValueError("installed_native_selection_moved_during_qualification")
    else:
        result["installed_store"] = (
            "UNAVAILABLE: host read capability absent; qualified against the "
            "sealed in-repo current-generation preimage with dynamic store "
            "discovery preserved for the native owner run")

    result.update(scratch_cas_qualification(candidate_pick,
                                            route.snapshot_picker("candidate")))
    if partner is not None:
        result.update(compose_with_partner(route.snapshot_picker("candidate"), partner))

    if witness_draft is None:
        result["witness_gate"] = {
            "witnesses_present": False,
            "expected_route_state": "FAIL_CLOSED_BEFORE_ANY_WORKER_LAUNCH",
            "note": "owner-verified entitlement/gateway/transport/cap/consent "
                    "witnesses are required; caller flags can never assert them",
        }
    else:
        import datetime as _dt

        draft = json.loads(witness_draft.read_text())
        verdict = route.validate_witness_document(
            draft, now_epoch=_dt.datetime.now(_dt.timezone.utc).timestamp())
        result["witness_gate"] = {
            "witnesses_present": verdict is not None,
            "draft_verdict": verdict or "FAIL_CLOSED",
            "draft_fingerprint": route.overlay_witness_fingerprint(draft),
            "note": "draft lint only; no host witness file was read or written",
        }

    if stage is not None:
        stage = stage.absolute()
        approved_root = Path("/Volumes/Mastermind/agent-workspaces").resolve(strict=True)
        if (stage.exists() or stage.is_symlink()
                or stage.parent.resolve(strict=True) != approved_root
                or not stage.name.startswith("fabric-experiential-stage-")):
            raise ValueError("release_stage_must_be_new_and_approved_root")
        stage.mkdir(mode=0o700)
        staged_source = stage / "source"
        (staged_source / "ext").mkdir(parents=True, mode=0o700)
        for rel, text in PLACEHOLDERS.items():
            target = staged_source / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        (staged_source / route.PICK).write_bytes(candidate_pick)
        (staged_source / (route.PICK + ".sealed-preimage")).write_bytes(
            route.snapshot_picker("candidate"))
        (stage / "manifest.json").write_bytes(
            generation.canonical({"ext/pick.py": sha(candidate_pick)}) + b"\n")
        (stage / "QUALIFICATION.json").write_bytes(
            generation.canonical(result) + b"\n")
        result["stage_path"] = str(stage)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-store", type=Path, default=None,
                        help="read-only installed native-code-releases store")
    parser.add_argument("--compose-overlay", type=Path, default=None,
                        help="sibling reviewed overlay module to compose with")
    parser.add_argument("--witness-draft", type=Path, default=None,
                        help="draft witness document to lint (never installed)")
    parser.add_argument("--release-stage", type=Path, default=None)
    args = parser.parse_args()
    print(json.dumps(run(args.installed_store, args.compose_overlay,
                         args.release_stage, args.witness_draft), sort_keys=True))


if __name__ == "__main__":
    main()
