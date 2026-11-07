#!/usr/bin/env python3
"""Install the existing M2 Claude/Parall isolation block without another guard.

Read-only by default. The only effectful mode uses a known baseline, preflight
CAS, private backups and atomic file replacement. It never opens or stops an
application, edits authentication or credentials, or installs a background job.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAGMENTS = ROOT / "ops/claude_parall_isolation"
TARGETS = {
    "guard": Path(".claude/hooks/mastermind_fabric_routing_guard.py"),
    "codex": Path(".codex/AGENTS.md"),
    "claude": Path(".claude/CLAUDE.md"),
}
TEMPLATES = {
    "guard": "guard_block.txt",
    "codex": "codex_instructions.md",
    "claude": "claude_instructions.md",
}
KNOWN_PRE_ISOLATION_GUARD_SHA256 = (
    "1b39013fa1770ab9447a822513dfc8cc0810a79a8f133761165b79996794e736"
)
GUARD_ANCHOR = "    # A push or explicit GitHub mutation is a material invalidator"
GUARD_START = "    # A generic Claude Desktop launch uses"
# Exact M2 observed block after the previous incremental guard repair. This
# digest fences migration of that installed prefix: any other local edits
# require explicit reconciliation, not replacement.
KNOWN_INSTALLED_V1_BLOCK_SHA256 = (
    "4b12401dcd7a62755e318df00da603f13e8bb091deac0bcb4b72c760d8af38d3"
)
KNOWN_INSTALLED_V2_BLOCK_SHA256 = (
    "ed05652cb4316438b48eeedf1957a62d96f96e24906dc9878d0275f04e87d82d"
)
# Exact guard block from protected merge PR #1647; also observed live on M2.
KNOWN_INSTALLED_V3_BLOCK_SHA256 = (
    "5f6dec8c7d95444410c3cde497f65cfa6985cada00ef1e0fd5366059d818aeea"
)
# Exact previous global-scope GUI block at PR #1653 commit 55175433.
KNOWN_INSTALLED_V4_BLOCK_SHA256 = (
    "01be9d86be6ab803fb68ded8b28f5f8f6f02a491f8aad4d8ce259e577e84ba80"
)
LEGACY_WORKSPACE_ROOT = '        "/Volumes/Mastermind/agent-workspaces",\n'
NEW_WORKSPACE_ROOT = '        "/Volumes/Mastermind 2/agent-workspaces",\n'
DOC_ANCHORS = {
    "codex": "<!-- pinned-session-delivery-reset-20261017 -->",
    "claude": "<!-- chris-proportionate-execution-20261015 -->",
}
DOC_MARKER = "<!-- claude-parall-launch-isolation-20261019 -->"

# The incumbent guard historically returned before checking non-Mastermind
# working directories. Account-safe Desktop launch denial must run first, but
# the unrelated Fabric/CI routing policy must remain Mastermind-scoped.
SCOPED_GUARD_START = (
    'def guard_bash(payload, ti):\n'
    '    if not is_mastermind_scope(payload):\n'
    '        return\n'
    '    cmd = str(ti.get("command") or "")\n'
)
GLOBAL_GUI_GUARD_START = (
    'def guard_bash(payload, ti):\n'
    '    cmd = str(ti.get("command") or "")\n'
)
REMAINING_SCOPE_GATE = (
    '    if not is_mastermind_scope(payload):\n'
    '        return\n\n'
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def template(kind: str) -> str:
    # Source fragments have one final newline; the installed blocks must retain
    # their existing blank separator before the following hook/instruction.
    return (FRAGMENTS / TEMPLATES[kind]).read_text(encoding="utf-8").rstrip("\n") + "\n\n"


def render(kind: str, before: str) -> str:
    block = template(kind)
    if not block:
        raise ValueError("empty installation fragment")
    if before.count(block) == 1:
        after = before
    elif kind == "guard":
        # Unknown hook versions or edits require reconciliation. Do not
        # normalize or overwrite a partially modified guard by guessing.
        if (before.count(GUARD_START) == 1 and
                before.count(GUARD_ANCHOR) == 1 and
                before.index(GUARD_START) < before.index(GUARD_ANCHOR)):
            start = before.index(GUARD_START)
            end = before.index(GUARD_ANCHOR)
            installed_block = before[start:end]
            # After global GUI scope hardening, the original Mastermind-only
            # return is deliberately *after* this fragment. Preserve that exact
            # suffix when upgrading a known fragment; otherwise the migration
            # would remove the guard of unrelated CI/Fabric rules.
            scoped_tail = (
                REMAINING_SCOPE_GATE
                if installed_block.endswith(REMAINING_SCOPE_GATE)
                else ""
            )
            normalized_block = (
                installed_block[:-len(scoped_tail)] if scoped_tail
                else installed_block
            )
            if sha(normalized_block.encode()) not in (
                KNOWN_INSTALLED_V1_BLOCK_SHA256,
                KNOWN_INSTALLED_V2_BLOCK_SHA256,
                KNOWN_INSTALLED_V3_BLOCK_SHA256,
                KNOWN_INSTALLED_V4_BLOCK_SHA256,
            ):
                raise ValueError("unrecognized guard block: preserve existing owner edits")
            after = before[:start] + block + scoped_tail + before[end:]
        elif sha(before.encode()) == KNOWN_PRE_ISOLATION_GUARD_SHA256:
            if before.count(GUARD_ANCHOR) != 1 or "unmanaged_desktop" in before:
                raise ValueError("guard insertion location ambiguous")
            after = before.replace(GUARD_ANCHOR, block + GUARD_ANCHOR, 1)
        else:
            raise ValueError("unrecognized guard: preserve existing owner edits")
    else:
        if DOC_MARKER in before or before.count(DOC_ANCHORS[kind]) != 1:
            raise ValueError("instruction marker drift or ambiguous anchor")
        after = before.replace(DOC_ANCHORS[kind], block + DOC_ANCHORS[kind], 1)
    if kind == "guard":
        # The active SSD workspace is now Mastermind 2. A shell guard that
        # protects only the original Mastermind volume is ineffective there.
        if NEW_WORKSPACE_ROOT not in after:
            if after.count(LEGACY_WORKSPACE_ROOT) != 1:
                raise ValueError("missing or ambiguous workspace-root anchor")
            after = after.replace(
                LEGACY_WORKSPACE_ROOT,
                LEGACY_WORKSPACE_ROOT + NEW_WORKSPACE_ROOT,
                1,
            )
        if after.count(NEW_WORKSPACE_ROOT) != 1:
            raise ValueError("duplicate workspace-root policy")
        if after.count(SCOPED_GUARD_START) == 1:
            # Move only this exact known early return. Preserve all other
            # rules, even while expanding GUI safety to every covered shell.
            if (after.count(GUARD_ANCHOR) != 1 or
                    after.count(REMAINING_SCOPE_GATE + GUARD_ANCHOR)):
                raise ValueError("unknown scoped guard layout")
            after = after.replace(SCOPED_GUARD_START, GLOBAL_GUI_GUARD_START, 1)
            after = after.replace(
                GUARD_ANCHOR, REMAINING_SCOPE_GATE + GUARD_ANCHOR, 1
            )
        elif (after.count(GLOBAL_GUI_GUARD_START) != 1 or
              after.count(REMAINING_SCOPE_GATE + GUARD_ANCHOR) != 1):
            raise ValueError("unrecognized host guard scope layout")
        ast.parse(after)
    return after


def prepare(home: Path) -> list[dict]:
    result = []
    for kind, rel in TARGETS.items():
        path = home / rel
        if path.is_symlink() or not path.is_file():
            raise ValueError("missing/symlink target: " + str(path))
        original = path.read_bytes()
        try:
            source = original.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("non-UTF8 installation target") from exc
        proposed = render(kind, source).encode("utf-8")
        result.append({
            "kind": kind, "path": path, "before": original, "after": proposed,
            "mode": stat.S_IMODE(path.stat().st_mode),
        })
    return result


def assert_unchanged(item: dict) -> None:
    path = item["path"]
    if (path.is_symlink() or path.read_bytes() != item["before"]
            or stat.S_IMODE(path.stat().st_mode) != item["mode"]):
        raise ValueError("target changed after preflight: " + str(path))


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".parall-isolation-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def summary(plan: list[dict]) -> list[dict]:
    return [
        {"kind": item["kind"], "path": str(item["path"]),
         "old_sha256": sha(item["before"]), "new_sha256": sha(item["after"]),
         "changed": item["before"] != item["after"]}
        for item in plan
    ]


def apply(plan: list[dict], evidence: Path) -> dict:
    for item in plan:
        assert_unchanged(item)
    if evidence.exists():
        raise ValueError("evidence directory already exists")
    evidence.mkdir(mode=0o700, parents=True)
    report = {"status": "PREPARED", "files": summary(plan), "written": [],
              "live_app_proof": False}
    receipt = evidence / "install.json"
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    try:
        for item in plan:
            if item["before"] == item["after"]:
                continue
            dest = evidence / (item["kind"] + ".before")
            with dest.open("xb") as file:
                file.write(item["before"])
            dest.chmod(0o600)
        for item in plan:
            assert_unchanged(item)
            if item["before"] == item["after"]:
                continue
            atomic_write(item["path"], item["after"], item["mode"])
            report["written"].append(str(item["path"]))
            receipt.write_text(json.dumps(report, indent=2) + "\n")
        report["status"] = "INSTALLED"
    except Exception as exc:
        report["status"] = "PARTIAL_FAILURE"
        report["error"] = str(exc)
        raise
    finally:
        receipt.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.apply and not args.evidence:
        parser.error("--apply requires --evidence")
    plan = prepare(args.home)
    report = apply(plan, args.evidence) if args.apply else {
        "status": "DRY_RUN", "files": summary(plan),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
