#!/usr/bin/env python3
"""Validate this documentation packet, not the product or upstream research.

Run locally: python3 validate_packet.py
Read-only GitHub source checks: python3 validate_packet.py --verify-sources
The latter requires the existing gh connection; it never writes to GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
REQUIRED = [
    "README.md", "01_CENSUS.md", "02_MASTERPLAN.md", "03_WORK_PACKAGES.md",
    "04_LOCAL_PRINCIPAL_HANDOFF.md", "05_ACCEPTANCE_AND_RED_TEAM.md",
    "06_SOURCE_REGISTER.md", "07_CHECKPOINT.md", "PR_SNAPSHOT.json",
]
ALLOWED_REPOS = {"Mastermind", "macro", "mastermind-terminal"}
OWNER = "mastermindx-market-intelligence"
LINK = re.compile(r"\[[^\]]*\]\(([^\s)]+)\)")
BLOB = re.compile(r"https://github\.com/([^/]+)/([^/]+)/blob/([0-9a-f]{40})/([^\s)]+)")


def run(args: list[str], timeout: int = 45) -> str:
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:600] or f"exit {result.returncode}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-sources", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    checks: list[dict] = []
    sources: list[dict] = []
    hashes: dict[str, str] = {}
    texts: dict[str, str] = {}
    local_links = 0
    for name in REQUIRED:
        path = ROOT / name
        if not path.is_file():
            failures.append(f"missing required file: {name}")
            continue
        raw = path.read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        text = raw.decode("utf-8")
        texts[name] = text
        if not text.endswith("\n") or "\r" in text:
            failures.append(f"noncanonical line endings: {name}")
        if any(line.rstrip() != line for line in text.splitlines()):
            failures.append(f"trailing whitespace: {name}")
        if name.endswith(".md"):
            for target in LINK.findall(text):
                if target.startswith(("https://", "http://", "#", "mailto:")):
                    continue
                local_links += 1
                candidate = (ROOT / unquote(target.split("#", 1)[0])).resolve()
                if not candidate.is_relative_to(ROOT) or not candidate.is_file():
                    failures.append(f"broken or escaping local link: {name}: {target}")
    checks.append({"name": "required_files_utf8_line_endings_local_links", "local_links_checked": local_links})
    if "PR_SNAPSHOT.json" in texts:
        snapshot = json.loads(texts["PR_SNAPSHOT.json"])
        rows = snapshot["pull_requests"]
        seen = set()
        for row in rows:
            key = (row["repository"], row["number"])
            if key in seen:
                failures.append(f"duplicate PR snapshot: {key}")
            seen.add(key)
            if row["repository"] not in {f"{OWNER}/{r}" for r in ALLOWED_REPOS}:
                failures.append(f"unexpected repository: {key}")
            for field in ("head_sha", "base_sha"):
                if not re.fullmatch(r"[0-9a-f]{40}", row[field]):
                    failures.append(f"invalid {field}: {key}")
        checks.append({"name": "snapshot_unique_and_sha_valid", "records": len(rows)})
    expectations = {
        "04_LOCAL_PRINCIPAL_HANDOFF.md": [
            "RECEIVER_MODE: OPEN_PICKUP", "RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE",
            "req-4a8daf76317cfe92f436991444c58281", "1cfdf816924d2c2ab58110c9ec0a5d57b1758bb4",
        ],
        "03_WORK_PACKAGES.md": ["## N", "## E", "## F", "## R", "## L", "## V", "## I", "## S"],
        "07_CHECKPOINT.md": ["LOCAL_PRINCIPAL_PICKUP_NOT_PROVEN", "NO NEW WORKER START", "PRODUCT_MISSION_INCOMPLETE"],
        "01_CENSUS.md": ["normalized_baseline.value = null", "C1-NULL", "NOT_CANONICALLY_PERSISTED"],
    }
    for name, required in expectations.items():
        for term in required:
            if term not in texts.get(name, ""):
                failures.append(f"required boundary missing: {name}: {term}")
    checks.append({"name": "required_packet_boundaries_present", "assertions": sum(map(len, expectations.values()))})
    try:
        repo_root = Path(run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"]).strip())
        prefix = ROOT.relative_to(repo_root).as_posix() + "/"
        changed = set(run(["git", "-C", str(repo_root), "diff", "--name-only", "HEAD"]).splitlines())
        changed.update(run(["git", "-C", str(repo_root), "ls-files", "--others", "--exclude-standard"]).splitlines())
        outside = sorted(p for p in changed if not p.startswith(prefix))
        if outside:
            failures.append(f"out-of-scope local changes: {outside}")
        checks.append({"name": "workspace_change_scope", "changed_paths": len(changed), "outside": outside})
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        failures.append(f"workspace scope check failed: {exc}")
    urls = set(BLOB.findall("\n".join(texts.values())))
    if args.verify_sources:
        for owner, repo, sha, path in sorted(urls):
            url = f"https://github.com/{owner}/{repo}/blob/{sha}/{path}"
            if owner != OWNER or repo not in ALLOWED_REPOS or ".." in Path(path).parts:
                failures.append(f"unapproved source URL: {url}")
                continue
            try:
                data = json.loads(run(["gh", "api", f"repos/{owner}/{repo}/contents/{path}?ref={sha}", "--jq", "{sha,size,path,type}"]))
                if data.get("type") != "file" or not re.fullmatch(r"[0-9a-f]{40}", data.get("sha", "")):
                    raise RuntimeError("not a GitHub file/blob response")
                sources.append({"url": url, "blob_sha": data["sha"], "size": data["size"]})
            except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
                failures.append(f"source check failed: {url}: {exc}")
    checks.append({"name": "immutable_source_links", "requested": args.verify_sources, "unique_urls": len(urls), "verified": len(sources)})
    hashes[Path(__file__).name] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    receipt = {
        "scope": "Author-side documentation/link/scope validation only; not independent review or product proof.",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "checks": checks, "file_sha256": hashes, "source_files": sources, "failures": failures,
    }
    target = ROOT / "PACKET_VALIDATION.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    print(json.dumps({"status": receipt["status"], "checks": checks, "failures": failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
