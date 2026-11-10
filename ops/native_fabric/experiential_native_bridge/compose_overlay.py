#!/usr/bin/env python3
"""compose_overlay.py — source qualification/composition for the native bridge.

Takes a VERIFIED immutable native source release (given explicitly as a
directory plus this module's ``release_manifest.json`` content CAS — never
guessed, never mutated) and composes a DISPOSABLE exact native overlay into a
fresh output directory:

1. fail-closed verification: manifest schema, patch digests, expected git
   head (stale-CAS law), whole-release tree content digest, per-file preimage
   digests;
2. strict unified-diff application (exact context, no fuzz) into the COPY;
3. byte-exact postimage digest verification (the change proof);
4. the host-owned consumer hook (``experiential_bridge.py``) is copied in;
5. an ``OVERLAY_MANIFEST.json`` receipt with every digest and status.

The composition is a DRY RUN by construction: it writes only to the
disposable output directory, never to the release tree, never to the
installed native release, and it is NOT a live install, admission, or
worker start. Any verification failure refuses typed with exit 78 and
performs no writes beyond creating nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA = "mastermind.experiential_native_bridge_release/v1"
BRIDGE_NAME = "experiential_bridge.py"
OWNER_MODULES = ("experiential_pin.py", "experiential_transport.py")

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_HEAD_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")


class CompositionRefused(RuntimeError):
    """Typed, fail-closed composition refusal (stable upper-snake reason)."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason + (f": {detail}" if detail else ""))
        self.reason = reason
        self.detail = detail


def _refuse(reason: str, detail: str = "") -> None:
    raise CompositionRefused(reason, detail)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_owner_modules(root: Path | None, manifest: dict[str, Any]) -> dict[str, bytes]:
    """Copy only immutable owner code from a trusted build-time source.

    The package does not invent provider entitlement, credentials, quota,
    route health or host context. These remain installed host-owner inputs.
    """
    if root is None:
        return {}
    expected = manifest.get("owner_modules_sha256")
    if type(expected) is not dict or set(expected) != set(OWNER_MODULES):
        _refuse("OWNER_MODULE_MANIFEST_MISSING", "exact pin and transport digests required")
    try:
        info = root.lstat()
    except OSError:
        _refuse("OWNER_MODULE_ROOT_MISSING", "source root is unavailable")
    if not stat.S_ISDIR(info.st_mode):
        _refuse("OWNER_MODULE_ROOT_INVALID", "regular source directory required")
    sealed: dict[str, bytes] = {}
    for name in OWNER_MODULES:
        source = root / name
        try:
            fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 2_000_000:
                    _refuse("OWNER_MODULE_SOURCE_INVALID", name)
                data = b""
                while len(data) < info.st_size:
                    chunk = os.read(fd, info.st_size - len(data))
                    if not chunk:
                        _refuse("OWNER_MODULE_SOURCE_CHANGED", name)
                    data += chunk
            finally:
                os.close(fd)
        except OSError:
            _refuse("OWNER_MODULE_SOURCE_INVALID", name)
        if hashlib.sha256(data).hexdigest() != expected[name]:
            _refuse("OWNER_MODULE_DIGEST_MISMATCH", name)
        sealed[name] = data
    return sealed


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _refuse("MANIFEST_UNREADABLE", str(exc))
    if type(manifest) is not dict or manifest.get("schema") != SCHEMA:
        _refuse("MANIFEST_SCHEMA_REFUSED", f"expected {SCHEMA}")
    for key in ("expected_release_head_sha1", "release_tree_manifest_sha256",
                "preimages_sha256", "postimages_sha256", "patches_sha256",
                "owner_modules_sha256"):
        if key not in manifest:
            _refuse("MANIFEST_INCOMPLETE", key)
    owner_digests = manifest["owner_modules_sha256"]
    if type(owner_digests) is not dict or set(owner_digests) != set(OWNER_MODULES) \
            or any(type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
                   for value in owner_digests.values()):
        _refuse("OWNER_MODULE_MANIFEST_INVALID", "two exact 64-hex source digests")
    if not re.fullmatch(r"[0-9a-f]{40}", str(manifest["expected_release_head_sha1"])):
        _refuse("MANIFEST_INVALID_HEAD", "expected_release_head_sha1 must be a 40-hex sha1")
    return manifest


def _verify_patch_digests(patch_dir: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    expected: dict[str, str] = manifest["patches_sha256"]
    if type(expected) is not dict or not expected:
        _refuse("MANIFEST_INVALID_PATCHES", "patches_sha256 must be a non-empty mapping")
    resolved: dict[str, Path] = {}
    for name, digest in sorted(expected.items()):
        candidate = patch_dir / name
        if not candidate.is_file():
            _refuse("PATCH_FILE_MISSING", name)
        if sha256_file(candidate) != digest:
            _refuse("PATCH_DIGEST_MISMATCH", name)
        resolved[name] = candidate
    return resolved


def _release_head(release_root: Path, expected: str) -> str:
    """Stale-CAS head law. Returns a typed head status or refuses."""
    probe = release_root
    marker = probe / ".git"
    while not marker.exists() and probe != probe.parent:
        probe = probe.parent
        marker = probe / ".git"
    if not marker.exists():
        # The installed kit layout is content-addressed without a checkout;
        # the tree content digest below remains the binding identity.
        return "not_a_git_checkout"
    try:
        head = subprocess.run(
            ["git", "-C", str(release_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "git_unavailable"
    if head.returncode != 0:
        return "git_unavailable"
    actual = head.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", actual):
        return "git_unavailable"
    if actual != expected:
        _refuse(
            "STALE_RELEASE_HEAD_REFUSED",
            f"release checkout head {actual} != manifest-qualified head "
            f"{expected}; re-qualify the manifest against the exact release "
            "before composing (content CAS alone does not clear a moved head)",
        )
    return "verified"


def _verify_release_tree(release_root: Path, manifest: dict[str, Any]) -> dict[str, str]:
    entries = sorted(p for p in release_root.iterdir())
    if not entries:
        _refuse("RELEASE_TREE_EMPTY", str(release_root))
    digests: dict[str, str] = {}
    for path in entries:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            _refuse("RELEASE_TREE_NONREGULAR", path.name)
        digests[path.name] = sha256_file(path)
    binding = hashlib.sha256(
        "".join(f"{name}:{digests[name]}\n" for name in sorted(digests)).encode()
    ).hexdigest()
    if binding != manifest["release_tree_manifest_sha256"]:
        _refuse(
            "RELEASE_TREE_MISMATCH",
            "the release tree content digest does not match the manifest; "
            "refusing stale or tampered source (content CAS)",
        )
    preimages: dict[str, str] = manifest["preimages_sha256"]
    for name, digest in sorted(preimages.items()):
        if digests.get(name) != digest:
            _refuse("RELEASE_PREIMAGE_MISMATCH", name)
    return digests


def _parse_patch(text: str, patch_name: str) -> tuple[str, list[dict[str, Any]]]:
    lines = text.splitlines()
    index = 0
    target: str | None = None
    hunks: list[dict[str, Any]] = []
    while index < len(lines):
        line = lines[index]
        match = _HEAD_RE.match(line)
        if match:
            target = match.group(1)
            index += 1
            continue
        if line.startswith(("--- ", "+++ ")):
            index += 1
            continue
        match = _HUNK_RE.match(line)
        if match:
            if target is None:
                _refuse("PATCH_STRUCTURE_INVALID", patch_name)
            old_start = int(match.group(1))
            old_count = int(match.group(2) or "1")
            new_count = int(match.group(4) or "1")
            consumed_old = 0
            consumed_new = 0
            body: list[str] = []
            index += 1
            while index < len(lines) and (consumed_old < old_count or consumed_new < new_count):
                raw = lines[index]
                if raw.startswith("@@") or raw.startswith("diff --git ") or raw.startswith("--- ") or raw.startswith("+++ "):
                    _refuse("PATCH_STRUCTURE_INVALID",
                            f"{patch_name}: hunk counts exhausted early")
                if raw.startswith("\\"):
                    _refuse("PATCH_MARKER_UNSUPPORTED",
                            f"{patch_name}: \\ newline markers are not supported")
                tag = raw[:1] if raw else " "
                if tag not in {" ", "-", "+"}:
                    _refuse("PATCH_STRUCTURE_INVALID", f"{patch_name}: {raw!r}")
                if tag == " ":
                    consumed_old += 1
                    consumed_new += 1
                elif tag == "-":
                    consumed_old += 1
                else:
                    consumed_new += 1
                body.append(raw if raw else " ")
                index += 1
            if consumed_old != old_count or consumed_new != new_count:
                _refuse("PATCH_STRUCTURE_INVALID",
                        f"{patch_name}: hunk line counts do not match header")
            hunks.append({"old_start": old_start, "lines": body})
            continue
        index += 1
    if target is None or not hunks:
        _refuse("PATCH_STRUCTURE_INVALID", patch_name)
    return target, hunks


def _apply_patch(data: bytes, patch_name: str, patch_text: str) -> bytes:
    target, hunks = _parse_patch(patch_text, patch_name)
    if target.startswith("/") or ".." in target.split("/"):
        _refuse("PATCH_PATH_REFUSED", target)
    plain = data.decode("utf-8").split("\n")
    if plain and plain[-1] == "":
        plain.pop()  # trailing EOL is reconstructed on write
    else:
        _refuse("PATCH_PREIMAGE_NO_EOL", patch_name)
    offset = 0  # line shift applied by earlier hunks
    for hunk in hunks:
        old_start = hunk["old_start"] - 1 + offset
        old_lines: list[str] = []
        new_lines: list[str] = []
        for body in hunk["lines"]:
            tag, content = body[:1], body[1:]
            if tag == " ":
                old_lines.append(content)
                new_lines.append(content)
            elif tag == "-":
                old_lines.append(content)
            else:
                new_lines.append(content)
        if old_start < 0 or old_start + len(old_lines) > len(plain):
            _refuse("PATCH_APPLICATION_REFUSED",
                    f"{patch_name}: hunk out of range for {target}")
        if plain[old_start:old_start + len(old_lines)] != old_lines:
            _refuse("PATCH_APPLICATION_REFUSED",
                    f"{patch_name}: exact preimage context not found in {target}")
        plain[old_start:old_start + len(old_lines)] = new_lines
        offset += len(new_lines) - len(old_lines)
    return ("\n".join(plain) + "\n").encode("utf-8")


def compose(
    *,
    release_root: Path,
    output: Path,
    manifest_path: Path,
    patch_dir: Path,
    verify_only: bool = False,
    owner_module_root: Path | None = None,
) -> dict[str, Any]:
    release_root = release_root.resolve()
    output = output.resolve()
    manifest = _load_manifest(manifest_path)
    tree_name = str(manifest.get("release_tree", "")).strip()
    if tree_name and release_root.name != Path(tree_name).name:
        _refuse("RELEASE_TREE_IDENTITY_REFUSED",
                f"expected release tree {tree_name}, got {release_root.name}")
    patches = _verify_patch_digests(patch_dir, manifest)
    owner_modules = _verified_owner_modules(owner_module_root, manifest)
    if output == release_root or output in release_root.parents or release_root in output.parents:
        _refuse("OUTPUT_OVERLAP_REFUSED",
                "the overlay output must be a disjoint disposable directory")
    if output.exists() and any(output.iterdir()):
        _refuse("OUTPUT_NOT_DISPOSABLE", f"{output} exists and is not empty")
    head_status = _release_head(release_root, str(manifest["expected_release_head_sha1"]))
    digests = _verify_release_tree(release_root, manifest)
    if verify_only:
        return {"verified": True, "release_head_status": head_status,
                "release_tree_manifest_sha256": manifest["release_tree_manifest_sha256"],
                "patch_count": len(patches),
                "owner_module_count": len(owner_modules)}

    overlay = output
    overlay.mkdir(parents=True, exist_ok=True)
    postimages: dict[str, str] = {}
    try:
        for name in sorted(digests):
            data = (release_root / name).read_bytes()
            (overlay / name).write_bytes(data)
        for patch_name, patch_path in patches.items():
            target, _ = _parse_patch(patch_path.read_text(encoding="utf-8"), patch_name)
            patched = _apply_patch((overlay / target).read_bytes(), patch_name,
                                   patch_path.read_text(encoding="utf-8"))
            (overlay / target).write_bytes(patched)
            expected_post = manifest["postimages_sha256"].get(target)
            actual_post = hashlib.sha256(patched).hexdigest()
            if expected_post is None or actual_post != expected_post:
                _refuse("POSTIMAGE_DIGEST_MISMATCH",
                        f"{target} does not match the manifest change proof")
            postimages[target] = actual_post
        bridge_source = Path(__file__).resolve().parent / BRIDGE_NAME
        if not bridge_source.is_file():
            _refuse("BRIDGE_SOURCE_MISSING", str(bridge_source))
        (overlay / BRIDGE_NAME).write_bytes(bridge_source.read_bytes())
        policy_source = Path(__file__).resolve().parents[3] / "control_plane" / "experiential_plan_policy.py"
        if not policy_source.is_file():
            _refuse("PLAN_POLICY_SOURCE_MISSING")
        (overlay / "experiential_plan_policy.py").write_bytes(policy_source.read_bytes())
        if owner_modules:
            module_dir = overlay / "experiential53"
            module_dir.mkdir(mode=0o700)
            for name, contents in owner_modules.items():
                (module_dir / name).write_bytes(contents)
        # Host-owned experiential_host_context.py is deliberately NOT copied.
        # The installed owner must supply validated entitlement, cap and
        # gateway attestation; a source bundle is never runtime admission.
    except CompositionRefused:
        shutil.rmtree(overlay, ignore_errors=True)
        raise
    receipt = {
        "schema": "mastermind.experiential_native_bridge_overlay/v1",
        "status": "source_candidate_not_installed",
        "admission_granted": False,
        "worker_started": False,
        "live_install_authorized": False,
        "dry_run": True,
        "expected_release_head_sha1": manifest["expected_release_head_sha1"],
        "release_head_status": head_status,
        "release_tree": manifest.get("release_tree", ""),
        "release_tree_manifest_sha256": manifest["release_tree_manifest_sha256"],
        "preimages_sha256": manifest["preimages_sha256"],
        "postimages_sha256": postimages,
        "patches_sha256": manifest["patches_sha256"],
        "bridge": {BRIDGE_NAME: sha256_file(overlay / BRIDGE_NAME),
                   "experiential_plan_policy.py": sha256_file(overlay / "experiential_plan_policy.py")},
        "owner_modules": {name: hashlib.sha256(data).hexdigest()
                          for name, data in owner_modules.items()},
        "host_context_owner_required": True,
        "overlay_root": str(overlay),
    }
    (overlay / "OVERLAY_MANIFEST.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-root", required=True,
                        help="path to the verified immutable native source release tree")
    parser.add_argument("--output", required=True,
                        help="disposable output directory (must be new or empty)")
    parser.add_argument("--manifest", default=None,
                        help="release manifest (default: release_manifest.json beside this module)")
    parser.add_argument("--patch-dir", default=None,
                        help="patch directory (default: overlay_patches/ beside this module)")
    parser.add_argument("--owner-modules-root", default=None,
                        help="optional exact digest-sealed owner pin+transport source "
                             "directory; no host credentials or context accepted")
    parser.add_argument("--verify-only", action="store_true",
                        help="verify only; compose nothing")
    args = parser.parse_args(argv)
    here = Path(__file__).resolve().parent
    manifest_path = Path(args.manifest) if args.manifest else here / "release_manifest.json"
    patch_dir = Path(args.patch_dir) if args.patch_dir else here / "overlay_patches"
    try:
        receipt = compose(
            release_root=Path(args.release_root), output=Path(args.output),
            manifest_path=manifest_path, patch_dir=patch_dir,
            verify_only=args.verify_only,
            owner_module_root=(Path(args.owner_modules_root)
                               if args.owner_modules_root else None))
    except CompositionRefused as exc:
        print(str(exc), file=sys.stderr)
        return 78
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
