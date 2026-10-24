#!/usr/bin/env python3
"""Compare the protected Mastermind bootstrap kernel with exported ChatGPT Project instructions.

This is a local read-only conformance check, not a GitHub or ChatGPT Project writer.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "docs" / "sol_skills" / "BOOTSTRAP_KERNEL.md"


def normalized(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip("\n") + "\n"


def extract_kernel(source_text: str) -> str:
    anchor = "## Approved Project instruction text"
    pos = source_text.find(anchor)
    if pos < 0:
        raise ValueError("source is missing Approved Project instruction text heading")
    opening = source_text.find("```text\n", pos)
    if opening < 0:
        raise ValueError("source is missing text fence")
    begin = opening + len("```text\n")
    closing = source_text.find("\n```", begin)
    if closing < 0:
        raise ValueError("source is missing closing fence")
    return normalized(source_text[begin:closing])


def compare(source: Path, project: Path) -> int:
    canonical = extract_kernel(source.read_text(encoding="utf-8"))
    deployed = normalized(project.read_text(encoding="utf-8"))
    for name, data in (("CANONICAL", canonical), ("PROJECT", deployed)):
        print(
            f"{name}: chars={len(data.rstrip(chr(10)))} "
            f"sha256={hashlib.sha256(data.encode()).hexdigest()}"
        )
    if canonical == deployed:
        print("MATCH: exported Project instructions match the protected-source kernel exactly.")
        return 0
    print("DRIFT: exported Project instructions differ from the protected-source kernel.")
    diff = difflib.unified_diff(
        canonical.splitlines(keepends=True),
        deployed.splitlines(keepends=True),
        fromfile="protected/BOOTSTRAP_KERNEL.md:embedded",
        tofile="ChatGPT-Project-instructions:exported",
    )
    print("".join(diff))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="docs/sol_skills/BOOTSTRAP_KERNEL.md",
    )
    parser.add_argument(
        "--project",
        type=Path,
        help="exported Local ChatGPT Project instructions",
    )
    parser.add_argument(
        "--print-kernel",
        action="store_true",
        help="write the approved fenced kernel to stdout for Project-settings paste",
    )
    parser.add_argument(
        "--write-kernel",
        type=Path,
        help="write the approved fenced kernel to PATH for Project-settings paste",
    )
    args = parser.parse_args()
    try:
        kernel = extract_kernel(args.source.read_text(encoding="utf-8"))
        if args.print_kernel:
            sys.stdout.write(kernel)
            return 0
        if args.write_kernel is not None:
            args.write_kernel.write_text(kernel, encoding="utf-8")
            digest = hashlib.sha256(kernel.encode()).hexdigest()
            print(
                f"WROTE {args.write_kernel} chars={len(kernel.rstrip(chr(10)))} sha256={digest}"
            )
            return 0
        if args.project is None:
            parser.error("--project is required unless --print-kernel or --write-kernel is set")
        return compare(args.source, args.project)
    except (ValueError, OSError, UnicodeDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
