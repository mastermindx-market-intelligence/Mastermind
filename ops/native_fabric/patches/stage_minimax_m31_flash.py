#!/usr/bin/env python3
"""Build the MiniMax M3.1 Flash SOURCE-ONLY native candidate from reviewed files.

Consumes the incumbent build_review_stage.py output; never invokes the native
publisher, changes CURRENT.json, touches a credential, or starts a Fabric task.
The exact predecessor and five patched members are pinned for this wave.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROLLOUT = HERE.parent / "quota_continuity" / "rollout"
sys.path.insert(0, str(ROLLOUT))
import native_generation as native  # the incumbent generation descriptor owner

BASE_MANIFEST_SHA256 = "0be933110a192f3855359eb72bfdfddb38e6dd581ed1d495d0caf7ea8a7a6aec"
PREDECESSOR = "28faaf101463bcabef578ab1acabdcd270e301c7ed9cedf294e82fd459ccfcce"
EXPECTED_CANDIDATE = "c66e4744ca788c081cdffc0ed52e559b6261b9914e806abbae28986edb6db7d4"
MEMBER_DIGESTS = {
    "ext/pick.py": (
        "4311200ae485ffd19b2560434e46c0c01899fbb58f0793c198292dba6004503b",
        "bdc8f9ea6484735ef6a9d3b6d94b1d9d30f6bd9079360b8e02928cf0469d5e47",
    ),
    "ext/host_pick.py": (
        "e5a398a0a2178abd9a79c9f9693b2528cf3a6d8b21d5829541e01158f952a092",
        "8e76d4276e4b77b55ea6845de2f0e8d44509cc2e799a1f5818516c09cb161682",
    ),
    "ext/placement_view.py": (
        "315519caa4644f9b6a431153556c5ce2080f921ce9ec4b0ddbff172517e3feb3",
        "51b46fb6160b35fc06b6e18a2e8d1e5a68da043f57882be74b64aef4c9373b88",
    ),
    "ext/sub.sh": (
        "7ceaba75dc4375bb05742b779967ade294afcc969358f610ecdb43041fa2f7d2",
        "9c3db528939245bfaef8c0cb96f10fc529b14b2fb258ce4fb5c3752ad6cbf536",
    ),
    "ext/mm_codex_exec.sh": (
        "0c31ceaa0467e4eb82f5220adb59328677e28e48a9ea7786a09bb0d78f1919f4",
        "b77b36c5aab464ed31988ac90ce09c90f74794a12f8344311a92f2d4de3a94cb",
    ),
}


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_file(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular reviewed source required")
    value = native.unique_json(path.read_bytes())
    if type(value) is not dict:
        raise ValueError("object required")
    return value


def stage(base: Path, output: Path) -> dict:
    """Create a fresh CLOSED source stage. No installed/selected effects."""
    base = base.resolve(strict=True)
    output = output.absolute()
    # This producer is SOURCE-ONLY. A redirected output parent must never
    # turn a scratch stage into a write to the installed native publication
    # store or back into the reviewed input closure.
    real_parent = output.parent.resolve(strict=True)
    if "native-code-releases" in real_parent.parts:
        raise ValueError("source stage cannot target native release store")
    if output.exists() or output.is_symlink():
        raise ValueError("output already exists; never overwrite")
    real_output = real_parent / output.name
    if (output == base or output.is_relative_to(base) or base.is_relative_to(output)
            or real_output == base or real_output.is_relative_to(base)
            or base.is_relative_to(real_output)):
        raise ValueError("source/output overlap")

    inventory = _json_file(base / "native-source-inventory.json")
    manifest_path = base / "native-manifest.json"
    manifest = _json_file(manifest_path)
    if _digest(manifest_path.read_bytes()) != BASE_MANIFEST_SHA256:
        raise ValueError("reviewed historical baseline changed")
    if type(inventory.get("files")) is not dict or set(inventory["files"]) != set(manifest):
        raise ValueError("source inventory differs from manifest")
    native.manifest_files(manifest)
    if len(manifest) != 102 or not set(MEMBER_DIGESTS).issubset(manifest):
        raise ValueError("unexpected source closure")
    if any(manifest[k] != old for k, (old, _) in MEMBER_DIGESTS.items()):
        raise ValueError("native v24 patch predecessor changed")

    predecessor = native.descriptor(manifest, inventory["stable_ext"])
    if _digest(native.canonical(predecessor)) != PREDECESSOR:
        raise ValueError("native code descriptor differs from selected-v24 predecessor")

    original = base / "native-code-stage"
    if original.is_symlink() or not original.is_dir():
        raise ValueError("missing reviewed stage")
    # Validate every existing member *before* the first write.
    for relative, wanted in manifest.items():
        path = original / relative
        if path.is_symlink() or not path.is_file() or _digest(path.read_bytes()) != wanted:
            raise ValueError("baseline file mismatch: " + relative)
    patch = HERE / "minimax_m31_flash_generation24.patch"
    if patch.is_symlink() or not patch.is_file():
        raise ValueError("reviewed source patch missing")

    # create exactly one fresh destination, never mutate the historical stage
    output.mkdir(mode=0o700)
    stage_root = output / "native-code-stage"
    (stage_root / "ext").mkdir(parents=True)
    for relative in manifest:
        dest = stage_root / relative
        shutil.copyfile(original / relative, dest)
    for args in (
        ["git", "apply", "--check", str(patch)],
        ["git", "apply", str(patch)],
    ):
        result = subprocess.run(args, cwd=stage_root, capture_output=True, text=True,
                                timeout=20, check=False)
        if result.returncode:
            raise ValueError("exact reviewed patch cannot apply")

    candidate = {}
    for relative in manifest:
        target = stage_root / relative
        if target.is_symlink() or not target.is_file():
            raise ValueError("candidate member not a regular file")
        candidate[relative] = _digest(target.read_bytes())
    changed = {key for key in manifest if manifest[key] != candidate[key]}
    if changed != set(MEMBER_DIGESTS):
        raise ValueError("candidate changed unreviewed files")
    if any(candidate[k] != new for k, (_, new) in MEMBER_DIGESTS.items()):
        raise ValueError("M3.1 candidate digest mismatch")
    new_desc = native.descriptor(candidate, inventory["stable_ext"])
    candidate_id = _digest(native.canonical(new_desc))
    if candidate_id != EXPECTED_CANDIDATE:
        raise ValueError("candidate identity mismatch")

    (output / "native-manifest.json").write_bytes(
        json.dumps(candidate, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    )
    (output / "SOURCE_STAGE_RECEIPT.json").write_bytes(
        json.dumps({
            "schema": "minimax-m31-source-stage.v1",
            "status": "SOURCE_ONLY_NOT_PUBLISHED",
            "predecessor": PREDECESSOR,
            "candidate": candidate_id,
            "changed_members": sorted(changed),
            "source_manifest_sha256": BASE_MANIFEST_SHA256,
            "patch_sha256": _digest(patch.read_bytes()),
            "members": len(candidate),
        }, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    )
    return {"candidate": candidate_id, "predecessor": PREDECESSOR,
            "members": len(candidate), "status": "SOURCE_ONLY_NOT_PUBLISHED",
            "output": str(output)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-stage", type=Path, required=True,
                        help="incumbent build_review_stage.py --output directory")
    parser.add_argument("--output", type=Path, required=True,
                        help="fresh destination, never the installed native store")
    args = parser.parse_args()
    print(json.dumps(stage(args.base_stage, args.output), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("MINIMAX_M31_SOURCE_STAGE_REFUSED: " + str(exc), file=sys.stderr)
        raise SystemExit(78)
