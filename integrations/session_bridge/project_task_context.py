"""Read-only task-tree projection from the existing GitHub-owned Markdown plan.

No database, scheduler, hook registration, task writer, provider call or execution
admission lives here. Native todos are a view; this source plan is not Runtime.
Evidence references are checked for coverage/freshness, NOT authenticated here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any
from urllib.parse import urlparse

SCHEMA = "mastermind.project_task_tree.v1"
MAX_PLAN_BYTES = 128 * 1024
MAX_CONTEXT_BYTES = 24 * 1024
MAX_TASKS = 128
_ID = re.compile(r"[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_BLOCK = re.compile(r"^```mastermind-plan\s*\n(.*?)^```[ \t]*$", re.M | re.S)
_STATES = frozenset({"pending", "in_progress", "blocked", "done"})


class PlanContextError(ValueError):
    """A bounded, non-sensitive reason suitable for native context diagnostics."""


def _fail(reason: str) -> None:
    raise PlanContextError(reason)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("PLAN_DUPLICATE_KEY")
        result[key] = value
    return result


def _text(value: Any, limit: int = 4096) -> str:
    if type(value) is not str:
        _fail("PLAN_TEXT_INVALID")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        _fail("PLAN_TEXT_INVALID")
    if (not value.strip() or size > limit
            or any(ord(c) < 32 and c not in "\n\t" for c in value)):
        _fail("PLAN_TEXT_INVALID")
    return value


def _id(value: Any) -> str:
    if type(value) is not str or len(value) > 96 or not _ID.fullmatch(value):
        _fail("PLAN_ID_INVALID")
    return value


def _keys(value: Any, required: set[str], optional: set[str] = frozenset()) -> dict:
    if type(value) is not dict or not required <= value.keys() or value.keys() - required - optional:
        _fail("PLAN_SHAPE_INVALID")
    return value


def _list(value: Any, *, nonempty: bool = False, maximum: int = MAX_TASKS) -> list:
    if type(value) is not list or len(value) > maximum or (nonempty and not value):
        _fail("PLAN_LIST_INVALID")
    return value


def _ids(value: Any, *, nonempty: bool = False) -> list[str]:
    values = [_id(x) for x in _list(value, nonempty=nonempty)]
    if len(values) != len(set(values)):
        _fail("PLAN_DUPLICATE_ID")
    return values


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _path(value: Any, *, plan: bool = False) -> str:
    value = _text(value, 512)
    path = PurePosixPath(value)
    if (path.is_absolute() or str(path) != value or value in (".", "")
            or any(x in ("..", ".git") for x in path.parts)
            or any(c in value for c in "\\:*?[]\n\t")):
        _fail("PLAN_PATH_INVALID")
    if plan and (not value.startswith("docs/plans/") or path.suffix != ".md"):
        _fail("PLAN_PATH_INVALID")
    return value


def _reference(value: Any) -> str:
    value = _text(value, 2048)
    # References are never fetched or executed by this module. Keep evidence
    # link syntax narrow and reject executable/file URLs and embedded secrets.
    if value.startswith(("runtime:", "agentos:")):
        if not re.fullmatch(r"(?:runtime|agentos):[A-Za-z0-9][A-Za-z0-9._:/#-]{1,1000}", value):
            _fail("PLAN_EVIDENCE_REF_INVALID")
        return value
    parsed = urlparse(value)
    if (parsed.scheme != "https" or parsed.netloc != "github.com"
            or parsed.username is not None or parsed.query or "%" in value
            or any(ord(c) <= 32 or ord(c) == 127 for c in value)):
        _fail("PLAN_EVIDENCE_REF_INVALID")
    parts = parsed.path.strip("/").split("/")
    if (len(parts) < 4 or any(p in ("", ".", "..") for p in parts)
            or parts[2] not in {"blob", "commit", "pull", "issues", "actions"}):
        _fail("PLAN_EVIDENCE_REF_INVALID")
    if parts[2] in {"blob", "commit"} and not re.fullmatch(r"[0-9a-f]{40}", parts[3]):
        _fail("PLAN_EVIDENCE_REF_INVALID")
    return value


def parse_plan(raw: bytes) -> dict[str, Any]:
    """Parse exactly one machine-readable tree inside its existing Markdown owner."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PLAN_BYTES:
        _fail("PLAN_SIZE_INVALID")
    try:
        text = raw.decode("utf-8")
        blocks = list(_BLOCK.finditer(text))
        if len(blocks) != 1 or text.count("```mastermind-plan") != 1:
            _fail("PLAN_BLOCK_COUNT_INVALID")
        value = json.loads(blocks[0].group(1), object_pairs_hook=_unique,
                           parse_constant=lambda _: _fail("PLAN_NONFINITE_NUMBER"))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        _fail("PLAN_PARSE_INVALID")
    validate_plan(value)
    return value


def validate_plan(plan: Any) -> None:
    _keys(plan, {"schema", "workstream", "objective", "requirements", "allowed_paths",
                 "non_goals", "tasks"}, {"focus_task_id", "scope_decision_ref"})
    if plan["schema"] != SCHEMA:
        _fail("PLAN_SCHEMA_UNSUPPORTED")
    if type(plan["workstream"]) is not str or not re.fullmatch(r"WS:[A-Z][A-Z0-9-]{0,95}", plan["workstream"]):
        _fail("PLAN_WORKSTREAM_INVALID")
    _text(plan["objective"], 8192)
    requirements = {}
    for item in _list(plan["requirements"], nonempty=True):
        _keys(item, {"id", "text"})
        key = _id(item["id"])
        if key in requirements:
            _fail("PLAN_DUPLICATE_REQUIREMENT")
        requirements[key] = _text(item["text"])
    for p in _list(plan["allowed_paths"]):
        _path(p)
    if len(set(plan["allowed_paths"])) != len(plan["allowed_paths"]):
        _fail("PLAN_DUPLICATE_PATH")
    for text in _list(plan["non_goals"], nonempty=True):
        _text(text)
    tasks = {}
    covered = set()
    for task in _list(plan["tasks"], nonempty=True):
        _keys(task, {"id", "title", "requirement_ids", "depends_on", "acceptance", "state", "evidence"},
              {"blocker", "next_action", "execution_lane", "native_ref"})
        key = _id(task["id"])
        if key in tasks:
            _fail("PLAN_DUPLICATE_TASK")
        tasks[key] = task
        _text(task["title"], 512)
        refs = _ids(task["requirement_ids"], nonempty=True)
        if set(refs) - requirements.keys():
            _fail("PLAN_REQUIREMENT_UNKNOWN")
        covered.update(refs)
        _ids(task["depends_on"])
        if type(task["state"]) is not str or task["state"] not in _STATES:
            _fail("PLAN_STATE_INVALID")
        criteria = set()
        for criterion in _list(task["acceptance"], nonempty=True):
            _keys(criterion, {"id", "text"})
            cid = _id(criterion["id"])
            if cid in criteria:
                _fail("PLAN_DUPLICATE_CRITERION")
            criteria.add(cid)
            _text(criterion["text"])
        evidence_ids = set()
        for evidence in _list(task["evidence"]):
            _keys(evidence, {"criterion_id", "definition_sha256", "ref", "result"})
            cid = _id(evidence["criterion_id"])
            if cid not in criteria or cid in evidence_ids:
                _fail("PLAN_EVIDENCE_CRITERION_INVALID")
            evidence_ids.add(cid)
            if type(evidence["definition_sha256"]) is not str or not _SHA.fullmatch(evidence["definition_sha256"]):
                _fail("PLAN_EVIDENCE_DIGEST_INVALID")
            if evidence["result"] not in ("pass", "fail", "pending"):
                _fail("PLAN_EVIDENCE_RESULT_INVALID")
            _reference(evidence["ref"])
        if task.get("execution_lane", "principal") not in ("principal", "delegated"):
            _fail("PLAN_LANE_INVALID")
        if "native_ref" in task:
            _reference(task["native_ref"])
        if task.get("execution_lane") == "delegated" and task["state"] == "in_progress" and not task.get("native_ref"):
            _fail("PLAN_DELEGATE_REFERENCE_REQUIRED")
        if task["state"] == "blocked" and not task.get("blocker"):
            _fail("PLAN_BLOCKER_REQUIRED")
        for field in ("blocker", "next_action"):
            if field in task:
                _text(task[field])
    if covered != requirements.keys():
        _fail("PLAN_REQUIREMENT_UNCOVERED")
    for key, task in tasks.items():
        if set(task["depends_on"]) - tasks.keys() or key in task["depends_on"]:
            _fail("PLAN_DEPENDENCY_INVALID")
    visiting, visited = set(), set()

    def visit(key: str) -> None:
        if key in visiting:
            _fail("PLAN_DEPENDENCY_CYCLE")
        if key in visited:
            return
        visiting.add(key)
        for parent in tasks[key]["depends_on"]:
            visit(parent)
        visiting.remove(key)
        visited.add(key)

    for key in tasks:
        visit(key)
    if "focus_task_id" in plan and (type(plan["focus_task_id"]) is not str or plan["focus_task_id"] not in tasks):
        _fail("PLAN_FOCUS_UNKNOWN")
    if sum(t["state"] == "in_progress" and t.get("execution_lane", "principal") == "principal" for t in tasks.values()) > 1:
        _fail("PLAN_MULTIPLE_PRINCIPAL_FOCI")
    if "scope_decision_ref" in plan:
        _reference(plan["scope_decision_ref"])


def definition_digests(plan: dict) -> dict[str, str]:
    """Invalidate affected downstream evidence, retaining unrelated completed work."""
    validate_plan(plan)
    tasks = {t["id"]: t for t in plan["tasks"]}
    requirements = {r["id"]: r["text"] for r in plan["requirements"]}
    memo = {}

    def build(key: str) -> str:
        if key not in memo:
            task = tasks[key]
            memo[key] = _digest({
                "workstream": plan["workstream"], "objective": plan["objective"],
                "allowed_paths": sorted(plan["allowed_paths"]), "non_goals": plan["non_goals"],
                "id": key, "title": task["title"], "acceptance": task["acceptance"],
                "requirements": {r: requirements[r] for r in task["requirement_ids"]},
                "dependencies": {r: build(r) for r in task["depends_on"]},
            })
        return memo[key]

    for key in tasks:
        build(key)
    return memo


def contract_digest(plan: dict) -> str:
    """Pin scope, not progress: routine evidence/status saves survive compaction."""
    validate_plan(plan)
    return _digest({"workstream": plan["workstream"], "objective": plan["objective"],
                    "requirements": plan["requirements"], "task_definitions": definition_digests(plan),
                    "allowed_paths": sorted(plan["allowed_paths"]), "non_goals": plan["non_goals"]})


def project_plan(plan: dict, *, source_sha256: str, source_path: str, workstream: str) -> dict:
    """Suggest one source-level focus; never authorize, dispatch or accept work."""
    validate_plan(plan)
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
    if len(_json(result).encode()) > MAX_CONTEXT_BYTES:
        _fail("PLAN_CONTEXT_TOO_LARGE")
    return result


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
                 expected_sha256: str | None = None, expected_contract_sha256: str | None = None) -> dict:
    plan, digest = read_plan(workspace_root, relative_path, expected_sha256,
                             expected_contract_sha256=expected_contract_sha256)
    result = project_plan(plan, source_sha256=digest, source_path=relative_path, workstream=workstream)
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
    out, err = stdout or sys.stdout, stderr or sys.stderr
    args = parser.parse_args(argv)
    try:
        result = load_context(workspace_root=args.workspace_root, relative_path=args.plan_path,
                              expected_sha256=args.plan_sha256, workstream=args.workstream,
                              expected_contract_sha256=args.plan_contract_sha256)
        out.write(_json(result) + "\n")
        return 0
    except PlanContextError as exc:
        err.write(str(exc) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
