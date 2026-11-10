"""Read-only task-tree projection from the existing GitHub-owned Markdown plan.

No database, scheduler, hook registration, task writer, provider call or execution
admission lives here. Native todos are a view; this source plan is not Runtime.
Evidence references are checked for coverage/freshness, NOT authenticated here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any
from urllib.parse import urlparse

# The standalone Hermes plugin bundles the same canonical file beside this
# adapter. Repo/T3 execution imports its normal common owner.
if __package__ == "integrations.session_bridge":
    from common.project_task_contract import (
    SCHEMA, MAX_PLAN_BYTES, MAX_CONTEXT_BYTES, MAX_TASKS, _ID, _SHA, _BLOCK,
    _STATES, PlanContextError, _fail, _unique, _text, _id, _keys, _list,
    _ids, _json, _digest, _path, _reference, parse_plan, validate_plan,
    definition_digests, contract_digest,
    )
else:
    from .project_task_contract import (
    SCHEMA, MAX_PLAN_BYTES, MAX_CONTEXT_BYTES, MAX_TASKS, _ID, _SHA, _BLOCK,
    _STATES, PlanContextError, _fail, _unique, _text, _id, _keys, _list,
    _ids, _json, _digest, _path, _reference, parse_plan, validate_plan,
    definition_digests, contract_digest,
    )


def project_plan(plan: dict, *, source_sha256: str, source_path: str, workstream: str,
                 context_detail: str = "full") -> dict:
    """Suggest one source-level focus; never authorize, dispatch or accept work."""
    validate_plan(plan)
    if context_detail not in ("full", "frontier"):
        _fail("PLAN_CONTEXT_DETAIL_INVALID")
    _path(source_path, plan=True)
    if type(source_sha256) is not str or not _SHA.fullmatch(source_sha256):
        _fail("PLAN_SOURCE_DIGEST_INVALID")
    if plan["workstream"] != workstream:
        _fail("PLAN_WORKSTREAM_MISMATCH")
    digests = definition_digests(plan)
    rows = []
    for task in plan["tasks"]:
        good = {e["criterion_id"] for e in task["evidence"]
                if e["result"] == "pass" and e["definition_sha256"] == digests[task["id"]]}
        missing = [c["id"] for c in task["acceptance"] if c["id"] not in good]
        rows.append({**task, "definition_sha256": digests[task["id"]],
                     "missing_or_stale_evidence": missing,
                     "source_complete": task["state"] == "done" and not missing})
    complete = {r["id"] for r in rows if r["source_complete"]}
    # A claimed completed downstream task does not satisfy a dependency while
    # its ancestors are incomplete, even if its own references look fresh.
    while True:
        revised = {r["id"] for r in rows if r["id"] in complete and set(r["depends_on"]) <= complete}
        if revised == complete:
            break
        complete = revised
    for row in rows:
        row["source_complete"] = row["id"] in complete
    ready = [r for r in rows if r["id"] not in complete and r["state"] != "blocked"
             and set(r["depends_on"]) <= complete]
    delegated = [r for r in rows if r["state"] == "in_progress" and r.get("execution_lane") == "delegated"]
    ready = [r for r in ready if r not in delegated]
    active = next((r for r in rows if r["state"] == "in_progress" and r.get("execution_lane", "principal") == "principal"), None)
    preferred = plan.get("focus_task_id")
    focus = active or next((r for r in ready if r["id"] == preferred), None) or next(iter(ready), None)
    if active and active not in ready:
        reason = "RECONCILE_ACTIVE_DEPENDENCIES"
    elif focus:
        reason = "REVIEW_SOURCE_FOCUS"
    elif len(complete) == len(rows):
        reason = "REVIEW_PARENT_ACCEPTANCE"
    elif delegated:
        reason = "READ_ORIGINAL_DELEGATE"
    else:
        reason = "REVIEW_BLOCKERS"
    result = {
        "schema": "mastermind.project_task_context.v1", "execution_authority": False,
        "evidence_authentication": "NOT_PERFORMED", "mission_accepted": "UNOBSERVED",
        "runtime_revalidation_required": True, "workstream": workstream,
        "source_path": source_path, "source_sha256": source_sha256,
        "contract_sha256": contract_digest(plan),
        "objective": plan["objective"], "requirements": plan["requirements"],
        "allowed_paths": plan["allowed_paths"], "non_goals": plan["non_goals"],
        "focus": focus, "next_action_kind": reason,
        "source_ready_ids": [r["id"] for r in ready],
        "source_complete_ids": [r["id"] for r in rows if r["id"] in complete],
        "task_tree": rows,
        "active_delegated_tasks": [{"id": r["id"], "native_ref": r["native_ref"]} for r in delegated],
        "cautions": [
            "Source status and linked evidence are claims; verify canonical receipts before accepting or acting.",
            "Use native T3 thread/run, provider permissions and existing Executive/Agent OS owners.",
            "Do not restart active or uncertain effects, expand scope, or clear a user stop based on this projection.",
        ],
    }
    if context_detail == "frontier":
        result = compact_context(result)
    if len(_json(result).encode()) > MAX_CONTEXT_BYTES:
        _fail("PLAN_CONTEXT_TOO_LARGE")
    return result


def compact_context(context: dict) -> dict:
    """Retain the full mission and recovery identifiers; omit only off-focus detail."""
    if (context.get("schema") != "mastermind.project_task_context.v1"
            or context.get("execution_authority") is not False):
        raise PlanContextError("GUIDANCE_CONTEXT_INVALID")
    brief = {k: copy.deepcopy(v) for k, v in context.items() if k != "task_tree"}
    fields = ("id", "title", "state", "depends_on", "requirement_ids", "definition_sha256",
              "missing_or_stale_evidence", "source_complete", "evidence", "blocker",
              "next_action", "execution_lane", "native_ref")
    brief["task_tree"] = [{k: copy.deepcopy(row[k]) for k in fields if k in row}
                          for row in context["task_tree"]]
    brief["task_detail_scope"] = "FULL_FOCUS; OFF_FOCUS_ACCEPTANCE_AT_EXACT_SOURCE"
    return brief



def read_plan(workspace_root: Path, relative_path: str, expected_sha256: str | None = None,
              *, expected_contract_sha256: str | None = None) -> tuple[dict, str]:
    """Bounded no-symlink read under the assigned workspace; no ambient path scan."""
    _path(relative_path, plan=True)
    supplied = [v for v in (expected_sha256, expected_contract_sha256) if v is not None]
    if len(supplied) != 1 or type(supplied[0]) is not str or not _SHA.fullmatch(supplied[0]):
        _fail("PLAN_EXPECTED_DIGEST_REQUIRED")
    try:
        root = Path(workspace_root)
        if not root.is_absolute():
            _fail("PLAN_WORKSPACE_INVALID")
        root = root.resolve(strict=True)
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            _fail("PLAN_PLATFORM_UNSUPPORTED")
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        directory = os.open(root, flags | os.O_DIRECTORY)
        try:
            parts = PurePosixPath(relative_path).parts
            for part in parts[:-1]:
                child = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
                os.close(directory)
                directory = child
            fd = os.open(parts[-1], flags, dir_fd=directory)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_PLAN_BYTES:
                    _fail("PLAN_FILE_INVALID")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    raw = stream.read(MAX_PLAN_BYTES + 1)
                after = os.fstat(fd)
                if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                    _fail("PLAN_READ_CHANGED")
            finally:
                os.close(fd)
        finally:
            os.close(directory)
    except (OSError, RuntimeError):
        _fail("PLAN_READ_UNAVAILABLE")
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        _fail("PLAN_REVISION_CHANGED")
    plan = parse_plan(raw)
    if expected_contract_sha256 is not None and contract_digest(plan) != expected_contract_sha256:
        _fail("PLAN_CONTRACT_CHANGED")
    return plan, digest


def load_context(*, workspace_root: Path, relative_path: str, workstream: str,
                 expected_sha256: str | None = None, expected_contract_sha256: str | None = None,
                 context_detail: str = "full") -> dict:
    plan, digest = read_plan(workspace_root, relative_path, expected_sha256,
                             expected_contract_sha256=expected_contract_sha256)
    result = project_plan(plan, source_sha256=digest, source_path=relative_path, workstream=workstream,
                          context_detail=context_detail)
    result["source_binding"] = "EXACT_BYTES" if expected_sha256 is not None else "MATCHED_CONTRACT_CURRENT_PROGRESS"
    if len(_json(result).encode()) > MAX_CONTEXT_BYTES:
        _fail("PLAN_CONTEXT_TOO_LARGE")
    return result


def compare_plans(before: dict, after: dict) -> dict:
    """Report scope drift; a decision link is not an authenticated approval."""
    old, new = definition_digests(before), definition_digests(after)
    before_requirements = {r["id"] for r in before["requirements"]}
    after_requirements = {r["id"] for r in after["requirements"]}
    removed = sorted(before_requirements - after_requirements)
    return {
        "removed_requirement_ids": removed, "removed_task_ids": sorted(old.keys() - new.keys()),
        "changed_task_ids": sorted(k for k in old.keys() & new.keys() if old[k] != new[k]),
        "unchanged_task_ids": sorted(k for k in old.keys() & new.keys() if old[k] == new[k]),
        "scope_decision_ref": after.get("scope_decision_ref"),
        "decision_authentication": "NOT_PERFORMED", "execution_authority": False,
        "scope_review_required": contract_digest(before) != contract_digest(after),
    }


def main(argv=None, *, stdout=None, stderr=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--plan-path", required=True)
    binding = parser.add_mutually_exclusive_group(required=True)
    binding.add_argument("--plan-sha256")
    binding.add_argument("--plan-contract-sha256")
    parser.add_argument("--workstream", required=True)
    parser.add_argument("--format", choices=("json", "prompt"), default="json")
    out, err = stdout or sys.stdout, stderr or sys.stderr
    args = parser.parse_args(argv)
    try:
        result = load_context(workspace_root=args.workspace_root, relative_path=args.plan_path,
                              expected_sha256=args.plan_sha256, workstream=args.workstream,
                              expected_contract_sha256=args.plan_contract_sha256,
                              context_detail="frontier" if args.format == "prompt" else "full")
        if args.format == "prompt":
            from integrations.session_bridge.long_horizon_guidance import render_context, PlanContextError as PromptError
            try:
                text = render_context(result)
            except PromptError as exc:
                # -m executes this file as __main__; the formatter imports its
                # canonical package identity. Normalize the typed CLI boundary.
                raise PlanContextError(str(exc)) from None
            out.write(text + "\n")
        else:
            out.write(_json(result) + "\n")
        return 0
    except PlanContextError as exc:
        err.write(str(exc) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
