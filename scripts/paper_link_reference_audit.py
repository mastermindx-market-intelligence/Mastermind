#!/usr/bin/env python3
"""Read-only tracked-file impact inventory for retiring an old Paper file link.

Scans only explicitly named local Git repositories. No links are rewritten,
no Paper API is contacted, and no Git writes occur. Historical refs need review.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

DEFAULT_FILE_ID = "01M2WGNCX9475G79JRKJTCM08P"
TEXT_EXTENSIONS = {".md", ".json", ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx",
                   ".css", ".html", ".yml", ".yaml", ".txt", ".toml", ".sh"}
MAX_BYTES = 2_000_000
PAGE_PATTERN = re.compile(r"p-[A-Za-z0-9]+-[0-9]+")


class AuditError(ValueError):
    pass


def scan_repo(label: str, root: Path, file_id: str, known_pages: set[str]) -> dict:
    root = root.resolve(strict=True)
    check = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, check=False)
    if check.returncode or Path(check.stdout.strip()).resolve() != root:
        raise AuditError(f"{label}: root must be the exact top of an existing Git repository")
    index = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached"],
                           capture_output=True, check=False)
    if index.returncode:
        raise AuditError(f"{label}: could not list tracked files")
    refs = []
    skipped = []
    scanned = 0
    for rel_raw in index.stdout.split(b"\0"):
        if not rel_raw:
            continue
        rel = rel_raw.decode("utf-8", errors="surrogateescape")
        if Path(rel).suffix.lower() not in TEXT_EXTENSIONS:
            continue
        candidate = root / rel
        if candidate.is_symlink():
            skipped.append({"path": rel, "reason": "SYMLINK"})
            continue
        if not candidate.is_file():
            skipped.append({"path": rel, "reason": "NOT_REGULAR_FILE"})
            continue
        if candidate.stat().st_size > MAX_BYTES:
            skipped.append({"path": rel, "reason": "TOO_LARGE_FOR_BOUNDED_SCAN"})
            continue
        try:
            data = candidate.read_bytes()
            if b"\0" in data:
                raise UnicodeError("binary")
            lines = data.decode("utf-8").splitlines()
        except (UnicodeError, OSError):
            skipped.append({"path": rel, "reason": "NON_UTF8_OR_UNREADABLE"})
            continue
        scanned += 1
        for line_no, line in enumerate(lines, start=1):
            if file_id not in line:
                continue
            for match in re.finditer(re.escape(file_id), line):
                # Window is deliberately limited so an unrelated page reference
                # elsewhere in a large line cannot be treated as an exact match.
                window = line[max(0, match.start() - 160):min(len(line), match.end() + 160)]
                pages = sorted(set(PAGE_PATTERN.findall(window)))
                if not pages:
                    classification = "FILE_ID_ONLY_REVIEW_REQUIRED"
                elif "p-19-0" in pages:
                    classification = "UNRESOLVED_PAGE_HISTORY_REVIEW_REQUIRED"
                elif any(x not in known_pages for x in pages):
                    classification = "UNKNOWN_OR_HISTORICAL_PAGE_REVIEW_REQUIRED"
                else:
                    classification = "KNOWN_PAGE_REVIEW_REQUIRED"
                refs.append({"path": rel, "line": line_no,
                             "page_ids_near_reference": pages,
                             "classification": classification,
                             "excerpt": line[max(0, match.start() - 90):min(len(line), match.end() + 120)]})
    refs.sort(key=lambda x: (x["path"], x["line"], x["excerpt"]))
    return {"repo_label": label, "root": str(root), "files_scanned": scanned,
            "skipped_files": skipped, "references": refs,
            "counts_by_classification": dict(sorted(Counter(x["classification"] for x in refs).items()))}


def run(inventory: dict, roots: list[str]) -> dict:
    if inventory.get("source_file_id") != DEFAULT_FILE_ID:
        raise AuditError("Inventory is not the expected original Paper file")
    known_pages = {x["source_page_id"] for x in inventory.get("pages", [])}
    if len(known_pages) != inventory.get("inventory_count") or not known_pages:
        raise AuditError("Invalid observed page-ID inventory")
    repo_specs = []
    labels = set()
    for item in roots:
        if "=" not in item:
            raise AuditError("--root must have form LABEL=/absolute/git/repo")
        label, location = item.split("=", 1)
        if not label or not location or label in labels:
            raise AuditError("Empty or duplicate repository label")
        labels.add(label)
        repo_specs.append((label, Path(location)))
    repo_specs.sort()
    scanned = [scan_repo(label, path, DEFAULT_FILE_ID, known_pages)
               for label, path in repo_specs]
    return {"schema": "mastermind.paper-reference-impact-readonly.v1",
            "classification": "READ_ONLY_LINK_INVENTORY_NOT_REWRITE_AUTHORITY",
            "source_file_id": DEFAULT_FILE_ID,
            "input_repositories": [x["repo_label"] for x in scanned],
            "total_references": sum(len(x["references"]) for x in scanned),
            "files_skipped_total": sum(len(x["skipped_files"]) for x in scanned),
            "repositories": scanned,
            "note": "Tracked UTF-8 text matches only. Inspect skipped files, historical branches and active owners before cutover; never blindly replace an old link."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--root", action="append", required=True,
                        help="Explicit Git repository root as NAME=/absolute/path; repeat as needed")
    parser.add_argument("--out", type=Path, help="Write offline JSON report (never edit source files)")
    args = parser.parse_args(argv)
    try:
        result = run(json.loads(args.inventory.read_text(encoding="utf-8")), args.root)
        serialized = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.out:
            destination = args.out.resolve()
            if any(destination.is_relative_to(Path(spec.split("=", 1)[1]).resolve()) for spec in args.root):
                raise AuditError("Report output must be outside scanned Git repositories")
            with args.out.open("x", encoding="utf-8") as handle:
                handle.write(serialized)
            print(f"Wrote read-only link inventory: {args.out}")
        else:
            print(serialized, end="")
        return 0
    except (AuditError, OSError, json.JSONDecodeError) as exc:
        print(f"PAPER_LINK_AUDIT_REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
