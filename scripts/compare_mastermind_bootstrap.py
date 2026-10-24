#!/usr/bin/env python3
"""Compare the protected Mastermind bootstrap kernel with exported ChatGPT Project instructions.

This is a local read-only conformance check, not a GitHub or ChatGPT Project writer.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "docs" / "sol_skills" / "BOOTSTRAP_KERNEL.md"
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "bootstrap_kernel_project.txt"
DEFAULT_MANIFEST = ROOT / "docs" / "sol_skills" / "BOOTSTRAP_KERNEL_RELEASE.json"
REVISION_RE = re.compile(r"^bootstrap_revision = (\S+)\s*$", re.MULTILINE)
MAJOR_RE = re.compile(r"^bootstrap_major = (\S+)\s*$", re.MULTILINE)
KERNEL_BUDGET = 8000
ARCHIVE_PROJECT = ROOT / "research" / "execution_bureaucracy_20261015" / "WEB_PROJECT_INSTRUCTIONS.txt"


class BootstrapParityError(ValueError):
    """A bootstrap kernel, fixture, or Project export failed a parity invariant."""


def normalized(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip("\n") + "\n"


def extract_kernel(source_text: str) -> str:
    anchor = "## Approved Project instruction text"
    pos = source_text.find(anchor)
    if pos < 0:
        raise BootstrapParityError("source is missing Approved Project instruction text heading")
    opening = source_text.find("```text\n", pos)
    if opening < 0:
        raise BootstrapParityError("source is missing text fence")
    begin = opening + len("```text\n")
    closing = source_text.find("\n```", begin)
    if closing < 0:
        raise BootstrapParityError("source is missing closing fence")
    return normalized(source_text[begin:closing])


def digest(kernel: str) -> str:
    return hashlib.sha256(kernel.encode("utf-8")).hexdigest()


def parse_field(kernel: str, pattern: re.Pattern[str], name: str) -> str:
    matches = pattern.findall(kernel)
    if len(matches) != 1:
        raise BootstrapParityError(f"kernel must contain exactly one {name}")
    return matches[0]


def parse_revision(kernel: str) -> str:
    return parse_field(kernel, REVISION_RE, "bootstrap_revision")


def parse_major(kernel: str) -> str:
    return parse_field(kernel, MAJOR_RE, "bootstrap_major")


def describe(kernel: str) -> str:
    return f"chars={len(kernel.rstrip(chr(10)))} sha256={digest(kernel)} revision={parse_revision(kernel)}"


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BootstrapParityError("manifest must be an object")
    return value


def render_manifest(kernel: str, *, protected_merge_commit: str | None = None) -> dict[str, Any]:
    return {
        "schema": "mastermind.bootstrap_kernel_release/v1",
        "bootstrap_major": int(parse_major(kernel)),
        "bootstrap_revision": parse_revision(kernel),
        "skillpack_version": "1.0.1",
        "kernel_chars": len(kernel.rstrip("\n")),
        "kernel_sha256": digest(kernel),
        "protected_merge_commit": protected_merge_commit,
        "project_sync": "PROJECT_SYNC_PENDING",
        "source": "docs/sol_skills/BOOTSTRAP_KERNEL.md",
        "fixture": "tests/fixtures/bootstrap_kernel_project.txt",
    }


def check_budget(kernel: str) -> None:
    if len(kernel) > KERNEL_BUDGET:
        raise BootstrapParityError(
            f"extracted kernel is {len(kernel)} characters; budget is {KERNEL_BUDGET}"
        )
    if parse_major(kernel) != "1":
        raise BootstrapParityError("bootstrap_major must remain 1")


def check_fixture(kernel: str, fixture: Path) -> None:
    if not fixture.is_file():
        raise BootstrapParityError(f"generated fixture missing: {fixture}")
    deployed = normalized(fixture.read_text(encoding="utf-8"))
    if deployed != kernel:
        raise BootstrapParityError("generated distribution/fixture drifted from the fenced kernel")


def check_manifest(kernel: str, manifest_path: Path) -> None:
    manifest = load_manifest(manifest_path)
    expected = render_manifest(kernel, protected_merge_commit=manifest.get("protected_merge_commit"))
    for key in (
        "schema",
        "bootstrap_major",
        "bootstrap_revision",
        "skillpack_version",
        "kernel_chars",
        "kernel_sha256",
        "source",
        "fixture",
    ):
        if manifest.get(key) != expected[key]:
            raise BootstrapParityError(f"release manifest {key} drifted from the fenced kernel")
    if "master" in kernel.lower() and re.search(r"\b[0-9a-f]{40}\b", kernel):
        raise BootstrapParityError("kernel must not embed a protected-commit SHA")


def check_revision_bump(base_kernel: str, candidate_kernel: str) -> None:
    if normalized(base_kernel) == normalized(candidate_kernel):
        return
    try:
        base_revision = parse_revision(base_kernel)
    except BootstrapParityError:
        base_revision = None
    candidate_revision = parse_revision(candidate_kernel)
    if base_revision == candidate_revision:
        raise BootstrapParityError("kernel content changed without a bootstrap_revision bump")


def base_kernel_from_git(source: Path) -> str | None:
    relative = source.resolve().relative_to(ROOT.resolve()).as_posix()
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"origin/master:{relative}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return extract_kernel(result.stdout)
    except BootstrapParityError:
        return None


def compare(canonical: str, deployed: str, *, deployed_name: str) -> int:
    print(f"CANONICAL: {describe(canonical)}")
    try:
        deployed_desc = describe(deployed)
    except BootstrapParityError:
        deployed_desc = f"chars={len(deployed.rstrip(chr(10)))} sha256={digest(deployed)} revision=MISSING"
    print(f"PROJECT: {deployed_desc}")
    if canonical == deployed:
        print("MATCH: exported Project instructions match the protected-source kernel exactly.")
        return 0
    print("DRIFT: exported Project instructions differ from the protected-source kernel.")
    diff = difflib.unified_diff(
        canonical.splitlines(keepends=True),
        deployed.splitlines(keepends=True),
        fromfile="protected/BOOTSTRAP_KERNEL.md:embedded",
        tofile=deployed_name,
    )
    print("".join(diff))
    return 1


def check_release(
    source: Path,
    fixture: Path,
    manifest: Path,
    *,
    base_source: Path | None = None,
) -> None:
    kernel = extract_kernel(source.read_text(encoding="utf-8"))
    check_budget(kernel)
    check_fixture(kernel, fixture)
    check_manifest(kernel, manifest)
    if ARCHIVE_PROJECT.is_file() and normalized(ARCHIVE_PROJECT.read_text(encoding="utf-8")) == kernel:
        raise BootstrapParityError("archived WEB_PROJECT_INSTRUCTIONS.txt must not be the live kernel")
    if base_source is not None:
        check_revision_bump(extract_kernel(base_source.read_text(encoding="utf-8")), kernel)
        return
    base = base_kernel_from_git(source)
    if base is not None:
        check_revision_bump(base, kernel)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--project", type=Path, help="exported Local ChatGPT Project instructions")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--base-source", type=Path, help="previous BOOTSTRAP_KERNEL.md for revision-bump checks")
    parser.add_argument("--print-kernel", action="store_true")
    parser.add_argument("--write-kernel", type=Path)
    parser.add_argument("--render-fixture", action="store_true")
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--check", action="store_true", help="CI: budget, fixture, manifest, revision bump")
    args = parser.parse_args()
    try:
        if not args.source.is_file():
            raise BootstrapParityError(f"missing source: {args.source}")
        kernel = extract_kernel(args.source.read_text(encoding="utf-8"))
        if args.check:
            check_release(args.source, args.fixture, args.manifest, base_source=args.base_source)
            print(f"CHECK OK: {describe(kernel)}")
            return 0
        if args.print_kernel:
            sys.stdout.write(kernel)
            return 0
        if args.write_kernel is not None:
            args.write_kernel.write_text(kernel, encoding="utf-8")
            print(f"WROTE {args.write_kernel} {describe(kernel)}")
            return 0
        if args.render_fixture:
            args.fixture.parent.mkdir(parents=True, exist_ok=True)
            args.fixture.write_text(kernel, encoding="utf-8")
            print(f"WROTE {args.fixture} {describe(kernel)}")
            return 0
        if args.write_manifest:
            payload = render_manifest(kernel)
            args.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            print(f"WROTE {args.manifest} {describe(kernel)}")
            return 0
        if args.project is None:
            parser.error("--project is required unless --print-kernel, --write-kernel, --render-fixture, --write-manifest or --check is set")
        if not args.project.is_file():
            raise BootstrapParityError(f"missing project export: {args.project}")
        return compare(kernel, normalized(args.project.read_text(encoding="utf-8")), deployed_name="ChatGPT-Project-instructions:exported")
    except (BootstrapParityError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
