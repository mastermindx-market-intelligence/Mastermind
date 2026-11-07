#!/usr/bin/env python3
"""Fail-closed, no-install profile for the M2 selected native Fabric generation.

A manifest binds four exact generation-source preimages from the sealed M2
store, a generation selection receipt, four no-fuzz patches and postimages. The
result is always a disposable source candidate, never a live kit or install.
Existing native generation publisher/selector remains the only install owner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

MODULE_DIR = Path(__file__).resolve().parent
PARENT = MODULE_DIR.parent
sys.path.insert(0, str(PARENT))
import compose_overlay as compose  # noqa: E402

NAMES = ("fabric_task.py", "remote_sub.sh", "sub.sh", "slot.py")
SCHEMA = "mastermind.experiential_m2_installed_profile.v1"
MAX_FILE_BYTES = 2_000_000


def refuse(reason: str, detail: str = "") -> None:
    raise compose.CompositionRefused(reason, detail)


def sealed_regular(path: Path, *, expected_sha: str) -> bytes:
    if type(expected_sha) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        refuse("PROFILE_DIGEST_INVALID", path.name)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FILE_BYTES:
                refuse("PROFILE_PREIMAGE_INVALID", path.name)
            content = b""
            while len(content) < info.st_size:
                part = os.read(fd, info.st_size - len(content))
                if not part:
                    refuse("PROFILE_PREIMAGE_CHANGED", path.name)
                content += part
            if os.fstat(fd).st_size != info.st_size:
                refuse("PROFILE_PREIMAGE_CHANGED", path.name)
        finally:
            os.close(fd)
    except OSError:
        refuse("PROFILE_PREIMAGE_UNAVAILABLE", path.name)
    if hashlib.sha256(content).hexdigest() != expected_sha:
        refuse("PROFILE_PREIMAGE_MISMATCH", path.name)
    return content


def manifest_read(path: Path, *, expected_profile_id: str = "m2-9691-20261104-exact-selected-code") -> dict:
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        refuse("PROFILE_MANIFEST_UNREADABLE")
    if type(m) is not dict or m.get("schema") != SCHEMA:
        refuse("PROFILE_SCHEMA_REFUSED")
    for key in ("preimages_sha256", "postimages_sha256", "patches_sha256"):
        if type(m.get(key)) is not dict:
            refuse("PROFILE_MANIFEST_INCOMPLETE", key)
    if set(m["preimages_sha256"]) != set(NAMES):
        refuse("PROFILE_PREIMAGE_SET_REFUSED")
    if set(m["postimages_sha256"]) != set(NAMES):
        refuse("PROFILE_POSTIMAGE_SET_REFUSED")
    if set(m["patches_sha256"]) != {name + ".patch" for name in NAMES}:
        refuse("PROFILE_PATCH_SET_REFUSED")
    if m.get("profile") != expected_profile_id:
        refuse("PROFILE_IDENTITY_REFUSED")
    if (type(m.get("selected_generation")) is not str
            or re.fullmatch(r"[0-9a-f]{64}", m["selected_generation"]) is None
            or type(m.get("selected_sequence")) is not int
            or m["selected_sequence"] < 0
            or type(m.get("current_selection_sha256")) is not str
            or re.fullmatch(r"[0-9a-f]{64}", m["current_selection_sha256"]) is None):
        refuse("PROFILE_SELECTION_PROOF_INVALID")
    return m


def _root_is_directory(root: Path) -> None:
    try:
        info = root.lstat()
    except OSError:
        refuse("PROFILE_ROOT_UNAVAILABLE")
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        refuse("PROFILE_ROOT_INVALID")


def qualify(*, installed_ext: Path, output: Path,
            owner_modules_root: Path, verify_only: bool = False,
            profile_dir: Path = MODULE_DIR,
            expected_profile_id: str = "m2-9691-20261104-exact-selected-code") -> dict:
    _root_is_directory(installed_ext)
    _root_is_directory(owner_modules_root)
    profile = manifest_read(profile_dir / "profile_manifest.json",
                            expected_profile_id=expected_profile_id)
    # The M2 publisher reads CURRENT once and executes one immutable generation.
    # Bind the same original selection instead of replacing a newer generation.
    store = installed_ext.parent.parent
    if (installed_ext.name != "ext" or store.name != "native-code-releases"
            or installed_ext.parent.name != profile["selected_generation"]):
        refuse("PROFILE_GENERATION_IDENTITY_REFUSED")
    try:
        selected = json.loads(sealed_regular(
            store / "CURRENT.json",
            expected_sha=profile["current_selection_sha256"]))
    except (ValueError, UnicodeError):
        refuse("PROFILE_SELECTION_UNREADABLE")
    if (type(selected) is not dict
            or selected.get("schema") != "native-code-selection.v1"
            or selected.get("generation") != profile["selected_generation"]
            or selected.get("sequence") != profile["selected_sequence"]):
        refuse("PROFILE_SELECTION_MOVED")
    # No writes into, above, or below an installed runtime, source or manifest.
    installed_path = installed_ext.resolve(strict=True)
    owner_path = owner_modules_root.resolve(strict=True)
    destination = output.resolve()
    for source in (installed_path, owner_path, profile_dir.resolve()):
        if destination == source or destination in source.parents or source in destination.parents:
            refuse("PROFILE_OUTPUT_OVERLAP_REFUSED")
    if output.is_symlink() or output.exists():
        refuse("PROFILE_OUTPUT_EXISTS_REFUSED", "use an unused disposable path")

    # Bind all input bytes once, and verify the host independently of the
    # source branch. No credential/key, ledger, state or arbitrary host file.
    preimages = {name: sealed_regular(installed_ext / name,
                      expected_sha=profile["preimages_sha256"][name])
                 for name in NAMES}
    patches = {name: sealed_regular(profile_dir / "patches" / (name + ".patch"),
                    expected_sha=profile["patches_sha256"][name + ".patch"])
               for name in NAMES}
    postimages: dict[str, bytes] = {}
    for name in NAMES:
        target, _ = compose._parse_patch(patches[name].decode("utf-8"), name)
        if target != name:
            refuse("PROFILE_PATCH_TARGET_REFUSED", name)
        modified = compose._apply_patch(preimages[name], name, patches[name].decode("utf-8"))
        if hashlib.sha256(modified).hexdigest() != profile["postimages_sha256"][name]:
            refuse("PROFILE_POSTIMAGE_MISMATCH", name)
        postimages[name] = modified
    # The owner modules are digest-sealed too; the native owner supplies
    # runtime cap/entitlement/host context separately after real verification.
    modules = compose._verified_owner_modules(owner_modules_root, profile)
    bridge = sealed_regular(PARENT / "experiential_bridge.py",
                            expected_sha=profile["bridge_sha256"])
    proof = {
        "schema": "mastermind.experiential_m2_installed_qualification.v1",
        "profile": profile["profile"],
        "source_generation": profile["selected_generation"],
        "source_sequence": profile["selected_sequence"],
        "state": "QUALIFIED_SOURCE_ONLY_NOT_INSTALLED",
        "admission_granted": False,
        "worker_started": False,
        "host_context_owner_required": True,
        "installed_preimage_sha256": profile["preimages_sha256"],
        "candidate_postimage_sha256": profile["postimages_sha256"],
        "owner_modules_sha256": profile["owner_modules_sha256"],
        "bridge_sha256": profile["bridge_sha256"],
        "changed_files": list(NAMES) + ["experiential_bridge.py",
                           "experiential_pin.py", "experiential_transport.py"],
        "verify_only": verify_only,
    }
    if not verify_only:
        output.mkdir(mode=0o700, parents=False, exist_ok=False)
        try:
            for name, data in postimages.items():
                (output / name).write_bytes(data)
            (output / "experiential_bridge.py").write_bytes(bridge)
            # The signed M2 publisher admits only flat ext/*.py source paths.
            for name, data in modules.items():
                (output / name).write_bytes(data)
            (output / "PROFILE_PROOF.json").write_text(
                json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except Exception:
            # Never leave a misleading partial qualification directory.
            import shutil
            shutil.rmtree(output)
            raise
    return proof


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-ext", required=True,
                        help="read-only exact M2 selected native generation ext")
    parser.add_argument("--output", required=True,
                        help="new disposable candidate directory; never native kit")
    parser.add_argument("--owner-modules-root", required=True,
                        help="digest-sealed owner source: experiential_pin+transport")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = qualify(installed_ext=Path(args.installed_ext),
                         output=Path(args.output),
                         owner_modules_root=Path(args.owner_modules_root),
                         verify_only=args.verify_only)
    except compose.CompositionRefused as exc:
        print(str(exc), file=sys.stderr)
        return 78
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
