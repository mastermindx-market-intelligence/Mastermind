#!/usr/bin/env python3
"""Fail-closed, OFFLINE qualification for PR #1694's additive Fabric guide release.

This module never publishes or selects a live generation, opens provider accounts,
runs agents or touches the kit's stable ext/ files. Real publication belongs only
to the existing native_generation owner after a protected merge and separate
source, identity, collision, and release approval gates.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
GEN_PATH = HERE.parent / "quota_continuity" / "rollout" / "native_generation.py"
spec = importlib.util.spec_from_file_location("fabric_delegation_native_generation", GEN_PATH)
assert spec and spec.loader
generation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generation)

OPERATOR = "ext/fabric_operator_client.py"
REVIEWED_CANDIDATE_SHA256 = "4bb2c134eb500afe6b5c980abecb8d02092fe1462c6b7fcd7f433ff0370746ba"
REVIEWED_PR_HEAD = "37f00e59c480300c6c44de4a0e04c8d536af6890"
START = b"OPERATOR_INSTRUCTIONS = '''\n"
END = b"\n'''"
REQUIRED_GUIDANCE = (
    b"mastermind.fabric_operator_child_request.v1",
    b"fabric_operator_scope",
    b"fabric_child_request",
    b"fabric_child_status",
    b"fabric_child_result",
    b"fabric_child_acknowledge",
)


class QualificationRefused(ValueError):
    pass


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_regular(path: Path, max_bytes: int = 262144) -> bytes:
    if path.is_symlink():
        raise QualificationRefused("symlinked source refused: " + str(path))
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= max_bytes:
        raise QualificationRefused("source kind/size refused: " + str(path))
    with path.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) != st.st_size or len(raw) > max_bytes:
        raise QualificationRefused("source changed during read: " + str(path))
    return raw


def instruction_span(raw: bytes) -> tuple[int, int]:
    try:
        parsed = ast.parse(raw)
        assignments = [
            x for x in parsed.body
            if isinstance(x, ast.Assign)
            and len(x.targets) == 1
            and isinstance(x.targets[0], ast.Name)
            and x.targets[0].id == "OPERATOR_INSTRUCTIONS"
            and isinstance(x.value, ast.Constant)
            and isinstance(x.value.value, str)
        ]
        if len(assignments) != 1 or raw.count(START) != 1:
            raise QualificationRefused("operator instructions are not one top-level literal")
        begin = raw.index(START)
        finish = raw.index(END, begin + len(START)) + len(END)
        if raw[begin:finish].count(END) != 1:
            raise QualificationRefused("operator literal terminator ambiguous")
        return begin, finish
    except (SyntaxError, ValueError) as exc:
        raise QualificationRefused("operator instructions parsing refused") from exc


def compose_instructions(selected: bytes, candidate: bytes) -> bytes:
    """Only change the literal; do not copy an older operator's code."""
    a, b = instruction_span(selected)
    c, d = instruction_span(candidate)
    if sha(selected) == sha(candidate):
        raise QualificationRefused("no additive operator difference")
    if not all(word in candidate[c:d] for word in REQUIRED_GUIDANCE):
        raise QualificationRefused("candidate does not contain the complete child recipe")
    if b"('grok', 'grok-4.7')" not in selected:
        raise QualificationRefused("selected operator Grok 4.7 binding not established")
    result = selected[:a] + candidate[c:d] + selected[b:]
    if result == selected:
        raise QualificationRefused("new guidance is already selected; no new release")
    ast.parse(result)
    # We can prove byte identity outside the one operator instruction literal.
    p, q = instruction_span(result)
    if selected[:a] != result[:p] or selected[b:] != result[q:]:
        raise QualificationRefused("operator executable changed outside instruction literal")
    if b"('grok', 'grok-4.7')" not in result:
        raise QualificationRefused("qualified Grok 4.7 binding regressed")
    return result


def _verify_merged_source(repo: Path, merged_ref: str, expected_candidate: bytes) -> str:
    """Stage may be prepared only from protected-master source containing PR bytes."""
    repo = repo.resolve(strict=True)
    if repo.name != "Mastermind" or not (repo / ".git").exists():
        # Linked worktrees carry a .git file rather than a directory.
        if repo.name != "Mastermind" or not (repo / ".git").is_file():
            raise QualificationRefused("source repository identity refused")
    commands = [
        ["git", "-C", str(repo), "rev-parse", "--verify", merged_ref + "^{commit}"],
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", merged_ref, "refs/remotes/origin/master"],
        ["git", "-C", str(repo), "show", merged_ref + ":ops/native_fabric/quota_continuity/candidate/fabric_operator_client.py"],
    ]
    resolved = subprocess.run(commands[0], capture_output=True, check=False)
    if resolved.returncode or len(resolved.stdout.strip()) != 40:
        raise QualificationRefused("protected merged commit not found")
    if subprocess.run(commands[1], capture_output=True, check=False).returncode:
        raise QualificationRefused("candidate commit is not present on protected master")
    candidate_blob = subprocess.run(commands[2], capture_output=True, check=False)
    if candidate_blob.returncode or candidate_blob.stdout != expected_candidate:
        raise QualificationRefused("protected merged candidate bytes mismatch")
    return resolved.stdout.decode().strip()


def _scratch_qualify(
    source_root: Path, baseline_files: dict[str, str], successor_files: dict[str, str],
    scratch_root: Path,
) -> dict[str, object]:
    fake_ext = scratch_root / "fake-owner" / "ext"
    fake_ext.mkdir(parents=True)
    previous = generation.publish(source_root / "baseline", fake_ext, baseline_files)
    scratch_store = fake_ext.parent / "native-code-releases"
    first = generation.select(scratch_store, previous.name, None)
    candidate = generation.publish(source_root / "successor", fake_ext, successor_files)
    root, meta = generation.verify(scratch_store, candidate.name)
    if root != candidate or meta["files"] != successor_files:
        raise QualificationRefused("isolated immutable publication mismatch")
    second = generation.select(scratch_store, candidate.name, previous.name)
    if second["sequence"] != 2 or first["sequence"] != 1 or second["previous"] != previous.name:
        raise QualificationRefused("isolated CAS successor did not select correctly")
    try:
        generation.select(scratch_store, previous.name, previous.name)
    except ValueError as exc:
        if "compare-and-swap refused" not in str(exc):
            raise
    else:
        raise QualificationRefused("stale CAS unexpectedly accepted")
    if generation.current(scratch_store) != second:
        raise QualificationRefused("stale CAS mutated scratch selection")
    return {"scratch_predecessor": previous.name, "scratch_successor": candidate.name,
            "scratch_published_and_verified": True, "scratch_stale_cas_refused": True}


def qualify(
    store: Path, candidate_path: Path, expected_selected: str, *,
    expected_candidate_sha: str = REVIEWED_CANDIDATE_SHA256,
    stage_dir: Path | None = None, stage_parent: Path | None = None,
    merged_repo: Path | None = None, merged_ref: str | None = None,
) -> dict[str, object]:
    store = store.resolve(strict=True)
    before = read_regular(store / "CURRENT.json", max_bytes=4096)
    pointer = generation.current(store)
    if pointer is None or pointer["generation"] != expected_selected:
        raise QualificationRefused("selected generation differs from expected; requalify")
    selected_root, verified = generation.verify(store, expected_selected)
    if len(verified["files"]) != 85 or OPERATOR not in verified["files"]:
        raise QualificationRefused("selected manifest closure differs from reviewed 85 files")
    candidate = read_regular(candidate_path, max_bytes=32768)
    if sha(candidate) != expected_candidate_sha:
        raise QualificationRefused("unreviewed candidate operator digest")
    old = read_regular(selected_root / OPERATOR, max_bytes=32768)
    if sha(old) != verified["files"][OPERATOR]:
        raise QualificationRefused("selected operator differs from sealed manifest")
    patched = compose_instructions(old, candidate)
    protected_merged_sha: str | None = None
    if stage_dir is not None:
        if not (stage_parent and merged_repo and merged_ref):
            raise QualificationRefused("staging requires workspace parent and protected merged source")
        protected_merged_sha = _verify_merged_source(merged_repo, merged_ref, candidate)
        if not (isinstance(protected_merged_sha, str)
                and len(protected_merged_sha) == 40
                and all(ch in "0123456789abcdef" for ch in protected_merged_sha)):
            raise QualificationRefused("protected merged source identifier invalid")
        stage_parent = stage_parent.resolve(strict=True)
        stage_dir = stage_dir.absolute()
        if (stage_dir.parent != stage_parent or stage_dir.exists()
                or stage_dir.is_symlink() or stage_parent.is_relative_to(store.parent)):
            raise QualificationRefused("release stage must be a fresh approved sibling workspace")
    elif any(x is not None for x in (stage_parent, merged_repo, merged_ref)):
        raise QualificationRefused("merge/stage options require explicit fresh release-stage")
    baseline: dict[str, str] = {}
    successor: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="fabric-delegation-qualification-") as dirname:
        scratch = Path(dirname).resolve(strict=True)
        source = scratch / "source"
        for rel, wanted in sorted(verified["files"].items()):
            raw = read_regular(selected_root / rel, max_bytes=2_000_000)
            if sha(raw) != wanted:
                raise QualificationRefused("sealed code digest changed: " + rel)
            for sub, payload in (("baseline", raw), ("successor", patched if rel == OPERATOR else raw)):
                target = source / sub / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            baseline[rel] = wanted
            successor[rel] = sha(patched) if rel == OPERATOR else wanted
        if {key for key in baseline if baseline[key] != successor[key]} != {OPERATOR}:
            raise QualificationRefused("release contains a change outside operator guidance")
        test = _scratch_qualify(source, baseline, successor, scratch)
        if read_regular(store / "CURRENT.json", max_bytes=4096) != before:
            raise QualificationRefused("live selection changed during qualification")
        result: dict[str, object] = {
            "state": "QUALIFIED_ISOLATED_ONLY", "live_published": False,
            "live_selected": False, "live_canaries_proven": False,
            "base_generation": expected_selected, "current_sequence": pointer["sequence"],
            "selected_pointer_sha256": sha(before),
            "selected_operator_sha256": sha(old),
            "reviewed_candidate_sha256": sha(candidate),
            "qualified_operator_sha256": sha(patched),
            "release_manifest_sha256": sha(generation.canonical(successor)),
            "native_file_count": len(successor), "changed_files": [OPERATOR],
            "no_credentials_or_provider_access": True,
            "protected_merged_source_sha": protected_merged_sha,
            **test,
        }
        if stage_dir is not None:
            assert stage_parent is not None
            pending = Path(tempfile.mkdtemp(prefix=".fabric-guide-pending-", dir=stage_parent))
            try:
                shutil.copytree(source / "successor", pending / "source")
                (pending / "manifest.json").write_bytes(generation.canonical(successor) + b"\n")
                (pending / "qualification.json").write_text(
                    json.dumps(result, sort_keys=True, indent=2) + "\n")
                for rel, digest in successor.items():
                    if sha(read_regular(pending / "source" / rel, max_bytes=2_000_000)) != digest:
                        raise QualificationRefused("staged release bytes do not match manifest")
                if read_regular(store / "CURRENT.json", max_bytes=4096) != before:
                    raise QualificationRefused("live selected generation changed before staging")
                if stage_dir.exists() or stage_dir.is_symlink():
                    raise QualificationRefused("release stage destination was acquired concurrently")
                os.rename(pending, stage_dir)
                result["review_stage"] = str(stage_dir)
            finally:
                if pending.exists():
                    shutil.rmtree(pending)
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--installed-store", type=Path, required=True)
    p.add_argument("--candidate-file", type=Path, required=True)
    p.add_argument("--expected-selected", required=True)
    p.add_argument("--release-stage", type=Path)
    p.add_argument("--stage-parent", type=Path)
    p.add_argument("--merged-repo", type=Path)
    p.add_argument("--merged-ref")
    args = p.parse_args()
    try:
        result = qualify(
            args.installed_store, args.candidate_file, args.expected_selected,
            stage_dir=args.release_stage, stage_parent=args.stage_parent,
            merged_repo=args.merged_repo, merged_ref=args.merged_ref,
        )
    except (QualificationRefused, ValueError, OSError) as exc:
        print(json.dumps({"state":"REFUSED", "reason":str(exc)}, sort_keys=True))
        return 78
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
