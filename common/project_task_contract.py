"""Canonical pure source-plan grammar and contract identity.

Extracted unchanged from the existing session source-plan reader. Runtime,
Hermes and T3 use this one parser; no I/O, authority or execution owner lives here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re
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
