"""COO/director/worker project composition over the incumbent T3 harness.

This is a source-plan compiler and read-only projection, NOT a scheduler, task
store, permission/budget issuer or provider router. T3 owns native threads and
children. Executive/Capacity retain company admission, atomic root accounting,
workspace custody and routing. Callers retain receipts in their existing owner.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping

from .t3_mission_brief import MissionBrief, Phase
from .t3_native_client import T3NativeClient
from .t3_project_team_inventory import NativeInventory
from .t3_project_team_results import NativeSettledResult
from .t3_web_client import HandoffBrief, NativeUnavailable, T3CliClient, ThreadReceipt

SCHEMA = "mastermind.t3_project_team.v1"
GRAPH_SCHEMA = "mastermind.t3_project_team_graph.v1"
MAX_ROLES = 128
MAX_DOCUMENT_BYTES = 131_072
MAX_DELEGATION_BYTES = 32_768
_ROLE_ID = re.compile(r"[a-z][a-z0-9-]{0,47}\Z")
_NATIVE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/%+-]{0,511}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_NATIVE_ROLES = {"implementation", "research", "review", "design", "test", "general"}
_LIVE_STATES = {"preparing", "queued", "starting", "running", "waiting"}
_TERMINAL_STATES = {"completed", "failed", "cancelled", "interrupted", "rolled_back"}


class TeamError(ValueError):
    """A bounded diagnostic; never includes prompts, credentials or raw output."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise TeamError(code)


def _text(value: Any, limit: int = 4096) -> str:
    _require(type(value) is str and bool(value.strip()), "TEAM_TEXT_INVALID")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise TeamError("TEAM_TEXT_INVALID") from None
    _require(size <= limit and not any(ord(c) < 32 and c not in "\n\t" for c in value)
             and not any(ord(c) == 127 for c in value), "TEAM_TEXT_INVALID")
    _require(not re.search(r"\bsk-(?:admin-|proj-)?[A-Za-z0-9_-]{20,}|\bBearer\s+\S{16,}", value),
             "TEAM_SECRET_LIKE_INPUT")
    return value


def _role_id(value: Any) -> str:
    _require(type(value) is str and _ROLE_ID.fullmatch(value) is not None,
             "TEAM_ROLE_ID_INVALID")
    return value


def _native_id(value: Any) -> str:
    _require(type(value) is str and _NATIVE_ID.fullmatch(value) is not None,
             "TEAM_NATIVE_ID_INVALID")
    return value


def _tuple(values: Any, *, nonempty: bool = False, maximum: int = MAX_ROLES) -> tuple:
    _require(type(values) is tuple and len(values) <= maximum and
             (bool(values) or not nonempty), "TEAM_LIST_INVALID")
    _require(all(type(value) is str for value in values), "TEAM_LIST_INVALID")
    _require(len(set(values)) == len(values), "TEAM_DUPLICATE_VALUE")
    return values


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _within(path: str, envelope: tuple[str, ...]) -> bool:
    return any(path == allowed or path.startswith(allowed + "/") for allowed in envelope)


def _path_identity(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    # Conservative across shared Mac/Linux checkouts; never use this folding to
    # widen an allowed scope, only to detect potential writer collisions.
    left, right = tuple(map(_path_identity, left)), tuple(map(_path_identity, right))
    return any(_within(path, right) for path in left) or any(_within(path, left) for path in right)


def _acyclic(edges: Mapping[str, tuple[str, ...]], code: str) -> None:
    # Bounded iterative elimination avoids Python recursion limits on bad input.
    remaining = {key: set(values) for key, values in edges.items()}
    while remaining:
        ready = {key for key, values in remaining.items() if not values}
        _require(bool(ready), code)
        remaining = {key: values - ready for key, values in remaining.items() if key not in ready}


def _definition_reference(value: str) -> str:
    # Syntax only. The existing source owner must verify exact bytes/fingerprint.
    HandoffBrief("team-definition", "source", "Exact immutable team definition", value,
                 ("Verify complete team fingerprint",), ("Stop on source mismatch",),
                 ("A source reference grants no execution authority",))
    return value


@dataclass(frozen=True, slots=True)
class TeamRole:
    role_id: str
    kind: str
    parent_id: str | None
    objective: str
    phase_ids: tuple[str, ...]
    allowed_write_paths: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    native_role: str = "implementation"
    isolation: str = "shared"

    def __post_init__(self) -> None:
        _role_id(self.role_id)
        _require(type(self.kind) is str and self.kind in {"coo", "director", "worker"}, "TEAM_ROLE_KIND_INVALID")
        if self.parent_id is not None:
            _role_id(self.parent_id)
        _text(self.objective)
        for value in _tuple(self.phase_ids, nonempty=True, maximum=16):
            _require(type(value) is str and re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", value)
                     is not None, "TEAM_PHASE_ID_INVALID")
        for value in _tuple(self.allowed_write_paths, maximum=16):
            _text(value, 512)
        for value in _tuple(self.depends_on):
            _role_id(value)
        _require(type(self.native_role) is str and self.native_role in _NATIVE_ROLES, "TEAM_NATIVE_ROLE_INVALID")
        _require(type(self.isolation) is str and self.isolation in {"shared", "worktree"},
                 "TEAM_ISOLATION_INVALID")
        _require(self.parent_id is not None or self.isolation == "shared", "TEAM_ROOT_ISOLATION_IS_NATIVE_LAUNCH")

    def document(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("phase_ids", "allowed_write_paths", "depends_on"):
            value[key] = list(value[key])
        return value


@dataclass(frozen=True, slots=True)
class ProjectTeam:
    mission: MissionBrief
    roles: tuple[TeamRole, ...]
    requested_max_live_agents: int = 12
    requested_max_depth: int = 4

    def __post_init__(self) -> None:
        _require(type(self.mission) is MissionBrief, "TEAM_MISSION_REQUIRED")
        _require(type(self.roles) is tuple and 1 <= len(self.roles) <= MAX_ROLES
                 and all(type(role) is TeamRole for role in self.roles), "TEAM_ROLES_INVALID")
        _require(type(self.requested_max_live_agents) is int
                 and 1 <= self.requested_max_live_agents <= 64, "TEAM_AGENT_CEILING_INVALID")
        _require(type(self.requested_max_depth) is int
                 and 1 <= self.requested_max_depth <= 8, "TEAM_DEPTH_CEILING_INVALID")
        by_id = self.by_id
        _require(len(by_id) == len(self.roles), "TEAM_DUPLICATE_ROLE")
        roots = [role for role in self.roles if role.parent_id is None]
        _require(len(roots) == 1 and roots[0].kind == "coo"
                 and sum(role.kind == "coo" for role in self.roles) == 1, "TEAM_ONE_COO_REQUIRED")
        phases = {phase.phase_id for phase in self.mission.phases}
        _require(set(roots[0].phase_ids) == phases, "TEAM_COO_SCOPE_INCOMPLETE")
        _require(set(roots[0].allowed_write_paths) == set(self.mission.allowed_write_paths),
                 "TEAM_COO_PATH_SCOPE_DIFFERS")
        for role in self.roles:
            _require(set(role.phase_ids) <= phases, "TEAM_PHASE_UNKNOWN")
            _require(role.role_id not in role.depends_on and set(role.depends_on) <= by_id.keys(),
                     "TEAM_DEPENDENCY_INVALID")
            if role.parent_id is not None:
                _require(role.parent_id in by_id and role.parent_id != role.role_id,
                         "TEAM_PARENT_INVALID")
                parent = by_id[role.parent_id]
                _require(parent.kind != "worker", "TEAM_WORKER_CANNOT_DELEGATE")
                _require(set(role.phase_ids) <= set(parent.phase_ids), "TEAM_PHASE_SCOPE_ESCALATION")
                _require(all(_within(path, parent.allowed_write_paths)
                             for path in role.allowed_write_paths), "TEAM_PATH_SCOPE_ESCALATION")
            # Reuse the incumbent path/worktree checks, not another path-policy owner.
            HandoffBrief("team-scope-check", "scope-check", role.objective,
                         self.mission.source_ref, ("Validate scoped source",),
                         self.mission.stop_conditions, self.mission.non_goals,
                         role.allowed_write_paths, self.mission.base_sha)
        parent_edges = {role.role_id: (() if role.parent_id is None else (role.parent_id,))
                        for role in self.roles}
        _acyclic(parent_edges, "TEAM_PARENT_CYCLE")
        _require(all(len(self.ancestors(role.role_id)) + 1 <= self.requested_max_depth
                     for role in self.roles), "TEAM_DEPTH_EXCEEDED")
        # Parent completion requires its children. Include those edges when finding
        # dependency cycles; checking only depends_on misses cross-branch deadlocks.
        completion_edges = {role.role_id: tuple(child.role_id for child in self.children(role.role_id))
                            + tuple(self.launch_dependencies(role.role_id)) for role in self.roles}
        _acyclic(completion_edges, "TEAM_COMPLETION_DEPENDENCY_CYCLE")
        for role in self.roles:
            _require(not set(role.depends_on) & set(self.ancestors(role.role_id)),
                     "TEAM_ANCESTOR_DEPENDENCY")
        leaves = [role for role in self.roles if not self.children(role.role_id)]
        _require({phase for role in leaves for phase in role.phase_ids} == phases,
                 "TEAM_LEAF_COVERAGE_INCOMPLETE")
        for owner in self.roles:
            descendants = [role for role in leaves if role.role_id == owner.role_id
                           or owner.role_id in self.ancestors(role.role_id)]
            _require({phase for role in descendants for phase in role.phase_ids}
                     == set(owner.phase_ids), "TEAM_DIRECTOR_COVERAGE_INCOMPLETE")
        for index, left in enumerate(self.roles):
            for right in self.roles[index + 1:]:
                if left.role_id in self.ancestors(right.role_id) or right.role_id in self.ancestors(left.role_id):
                    continue
                if (self.workspace_group(left.role_id) == self.workspace_group(right.role_id)
                        and _overlap(left.allowed_write_paths, right.allowed_write_paths)):
                    ordered = (right.role_id in self.completion_dependencies(left.role_id)
                               or left.role_id in self.completion_dependencies(right.role_id))
                    _require(ordered, "TEAM_SHARED_CHECKOUT_COLLISION")
        _require(len(_json(self.document()).encode()) <= MAX_DOCUMENT_BYTES, "TEAM_DOCUMENT_TOO_LARGE")

    @property
    def by_id(self) -> dict[str, TeamRole]:
        return {role.role_id: role for role in self.roles}

    @property
    def root(self) -> TeamRole:
        return next(role for role in self.roles if role.parent_id is None)

    def children(self, role_id: str) -> tuple[TeamRole, ...]:
        return tuple(role for role in self.roles if role.parent_id == role_id)

    def ancestors(self, role_id: str) -> tuple[str, ...]:
        by_id = self.by_id
        _require(role_id in by_id, "TEAM_ROLE_UNKNOWN")
        result: list[str] = []
        current = by_id[role_id].parent_id
        while current is not None:
            _require(current not in result, "TEAM_PARENT_CYCLE")
            result.append(current)
            current = by_id[current].parent_id
        return tuple(result)

    def workspace_group(self, role_id: str) -> str:
        """Requested native checkout partition; not proof of actual isolation."""
        for key in (role_id, *self.ancestors(role_id)):
            if self.by_id[key].isolation == "worktree" or self.by_id[key].parent_id is None:
                return key
        raise TeamError("TEAM_ROOT_MISSING")

    def completion_dependencies(self, role_id: str) -> frozenset[str]:
        by_id = self.by_id
        found: set[str] = set()
        pending = list(self.launch_dependencies(role_id)) + [x.role_id for x in self.children(role_id)]
        while pending:
            key = pending.pop()
            if key not in found:
                found.add(key)
                pending.extend(self.launch_dependencies(key))
                pending.extend(x.role_id for x in self.children(key))
        return frozenset(found)

    def launch_dependencies(self, role_id: str) -> frozenset[str]:
        return frozenset(dep for key in (role_id, *self.ancestors(role_id))
                         for dep in self.by_id[key].depends_on)

    def document(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "mission": self.mission.document(),
                "roles": [role.document() for role in self.roles],
                "requested_max_live_agents": self.requested_max_live_agents,
                "requested_max_depth": self.requested_max_depth}

    @property
    def fingerprint(self) -> str:
        return _digest(self.document())

    def root_handoff(self, *, request_id: str, project_id: str,
                     definition_ref: str | None = None) -> HandoffBrief:
        # Embed every assignment and phase check. source_ref identifies the
        # governing project brief, not proof that it contains this generated graph.
        # Oversized teams fail explicitly instead of silently dropping scope.
        context = {"mission_id": self.mission.mission_id, "team_sha256": self.fingerprint,
                   "coo_role_id": self.root.role_id,
                   "team_definition": [role.document() for role in self.roles],
                   "phases": [asdict(phase) for phase in self.mission.phases],
                   "notes_ref": self.mission.notes_ref,
                   "execution_envelope_ref": self.mission.execution_envelope_ref,
                   "requested_max_live_agents": self.requested_max_live_agents,
                   "requested_max_depth": self.requested_max_depth}
        if definition_ref is not None:
            _definition_reference(definition_ref)
            context.pop("team_definition")
            context.pop("phases")
            context.update(team_definition_ref=definition_ref, role_count=len(self.roles),
                           direct_child_ids=[role.role_id for role in self.children(self.root.role_id)],
                           phase_ids=[phase.phase_id for phase in self.mission.phases],
                           detail_projection="immutable_source_reference",
                           mission_source_ref=self.mission.source_ref)
        objective = self.mission.objective + "\n" + _TEAM_INSTRUCTIONS + "\n" + _json(context)
        _require(len(objective.encode()) <= 8192, "TEAM_ROOT_BRIEF_TOO_LARGE_USE_DEFINITION_REF")
        return HandoffBrief(request_id, project_id, objective, definition_ref or self.mission.source_ref,
                            self.mission.done_when, self.mission.stop_conditions,
                            self.mission.non_goals, self.mission.allowed_write_paths,
                            self.mission.base_sha)


_TEAM_INSTRUCTIONS = (
    "Lead this project as its COO, retaining the whole original DONE_WHEN. "
    "Use the embedded team definition or read the exact team_definition_ref and "
    "verify its complete team fingerprint before delegation. A linked definition "
    "is progressive disclosure, not permission to omit roles or acceptance. "
    "Use T3's real delegate_task tool for directors and their nested workers; "
    "directors own their slice and return evidence to their immediate parent. "
    "Do not replace child delegation with unrelated top-level launches. "
    "Use task_status and exact native thread/run results, not optimistic summaries. "
    "Follow delegate_task's native next directive: when completion wakes the parent, "
    "end the turn and consume the delivered result on that wake; do not poll. "
    "Do not pass delegated task IDs to t3_background_wait: that tool tracks separate "
    "background commands. An unmatched ID is not proof of a transport failure. "
    "Use native parentThreadId for ancestry, not a model's self-description. "
    "Respect existing Executive/Capacity admission and conserved root budget. "
    "Requested graph ceilings are not grants. Preserve provider/model defaults. "
    "Use each role's requested native isolation, never a custom worktree allocator. "
    "Shared-checkout writers need disjoint scopes; a director must not edit a live "
    "shared child's scope. Worktree children start from committed parent source; "
    "uncommitted edits are not copied. Integrate accepted dependency branches into "
    "the parent and commit those inputs before a dependent worktree starts. "
    "Read actual workspace evidence before parallel "
    "writing and reconcile branches/PRs through the existing source owner. "
    "Record actual child IDs and original effects in the existing shared notes/source plan. "
    "Dependencies require parent-reviewed source evidence, not a child saying done. "
    "On each return, review, persist, reassess the original goal and continue safe work. "
    "After compaction/restart recover the same graph and native receipts; never relaunch "
    "an uncertain or still-running child. Pause/stop/budget and permission boundaries win. "
    "No new scheduler, queue, credential, memory or company task registry. "
    "Native completion and graph projection are not principal acceptance."
)


@dataclass(frozen=True, slots=True)
class RoleBinding:
    """Retained native identity supplied by the incumbent owner, not an admission."""
    role_id: str
    environment_id: str
    root_thread_id: str
    parent_thread_id: str | None
    task_id: str | None
    receipt: ThreadReceipt
    team_sha256: str

    def __post_init__(self) -> None:
        _role_id(self.role_id)
        for value in (self.environment_id, self.root_thread_id):
            _native_id(value)
        for value in (self.parent_thread_id, self.task_id):
            if value is not None:
                _native_id(value)
        _require(type(self.receipt) is ThreadReceipt, "TEAM_NATIVE_RECEIPT_REQUIRED")
        _require(type(self.team_sha256) is str and _SHA256.fullmatch(self.team_sha256) is not None,
                 "TEAM_FINGERPRINT_INVALID")

    def document(self) -> dict[str, Any]:
        return asdict(self)


def validate_bindings(team: ProjectTeam, bindings: tuple[RoleBinding, ...]) -> dict[str, RoleBinding]:
    _require(type(bindings) is tuple and len(bindings) <= len(team.roles)
             and all(type(item) is RoleBinding for item in bindings), "TEAM_BINDINGS_INVALID")
    by_role = {item.role_id: item for item in bindings}
    _require(len(by_role) == len(bindings), "TEAM_DUPLICATE_BINDING")
    _require(set(by_role) <= team.by_id.keys(), "TEAM_BINDING_ROLE_UNKNOWN")
    _require(len({item.receipt.thread_id for item in bindings}) == len(bindings),
             "TEAM_NATIVE_THREAD_REUSED")
    task_ids = [item.task_id for item in bindings if item.task_id is not None]
    _require(len(task_ids) == len(set(task_ids)), "TEAM_NATIVE_TASK_REUSED")
    if not bindings:
        return by_role
    _require(team.root.role_id in by_role, "TEAM_ROOT_BINDING_REQUIRED")
    root = by_role[team.root.role_id]
    _require(root.parent_thread_id is None and root.task_id is None
             and root.root_thread_id == root.receipt.thread_id, "TEAM_ROOT_BINDING_INVALID")
    for item in bindings:
        _require(item.team_sha256 == team.fingerprint, "TEAM_BINDING_STALE_REVISION")
        _require(item.environment_id == root.environment_id
                 and item.receipt.project_id == root.receipt.project_id
                 and item.root_thread_id == root.receipt.thread_id, "TEAM_BINDING_ROOT_DIFFERS")
        parent_id = team.by_id[item.role_id].parent_id
        if parent_id is not None:
            _require(parent_id in by_role and item.task_id is not None
                     and item.parent_thread_id == by_role[parent_id].receipt.thread_id,
                     "TEAM_BINDING_PARENT_DIFFERS")
    return by_role


@dataclass(frozen=True, slots=True)
class DependencyEvidence:
    """Source-owner evidence supplied to planning, not authenticated by this module."""
    role_id: str
    accepted_by_role_id: str
    team_sha256: str
    source_ref: str


def validate_dependency_evidence(team: ProjectTeam, evidence: tuple[DependencyEvidence, ...]) -> frozenset[str]:
    _require(type(evidence) is tuple and len(evidence) <= len(team.roles)
             and all(type(item) is DependencyEvidence for item in evidence), "TEAM_EVIDENCE_INVALID")
    accepted = frozenset(item.role_id for item in evidence)
    _require(len(accepted) == len(evidence) and accepted <= team.by_id.keys(), "TEAM_EVIDENCE_ROLE_INVALID")
    for item in evidence:
        _role_id(item.role_id)
        _role_id(item.accepted_by_role_id)
        role = team.by_id[item.role_id]
        _require(role.parent_id is not None and item.accepted_by_role_id == role.parent_id,
                 "TEAM_PARENT_REVIEW_REQUIRED")
        _require(item.team_sha256 == team.fingerprint, "TEAM_EVIDENCE_STALE_REVISION")
        # Reuse the incumbent immutable GitHub source-reference validation.
        HandoffBrief("team-evidence", "evidence", "Source-owner acceptance evidence",
                     item.source_ref, ("Evidence is verified by its existing owner",),
                     ("Do not self-accept",), ("No execution authority",))
        _require(team.completion_dependencies(item.role_id) <= accepted,
                 "TEAM_EVIDENCE_DEPENDENCIES_INCOMPLETE")
    return accepted


@dataclass(frozen=True, slots=True)
class DelegationOffer:
    """Arguments for the actual native parent's delegate_task, never a dispatch."""
    role_id: str
    parent_role_id: str
    parent_thread_id: str
    parent_run_id: str
    root_thread_id: str
    environment_id: str
    project_id: str
    team_sha256: str
    request_id: str
    title: str
    native_role: str
    isolation: str
    task: str

    def native_arguments(self) -> dict[str, Any]:
        return {"task": self.task, "title": self.title, "role": self.native_role,
                "mode": "async", "clientRequestId": self.request_id, "isolation": self.isolation}

    @property
    def fingerprint(self) -> str:
        return _digest(self.native_arguments())


def _observation(binding: RoleBinding, value: Any) -> dict[str, Any] | None:
    if type(value) is not dict or type(value.get("thread")) is not dict:
        return None
    thread = value["thread"]
    if (thread.get("threadId") != binding.receipt.thread_id
            or thread.get("projectId") != binding.receipt.project_id
            or "parentThreadId" not in thread
            or thread["parentThreadId"] != binding.parent_thread_id
            or thread.get("relationshipToParent") != ("subagent" if binding.parent_thread_id else None)):
        return None
    return thread



def workspace_evidence(team: ProjectTeam, bindings: Mapping[str, RoleBinding],
                       observations: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Observe native checkout paths; never allocate, resolve or trust arbitrary paths."""
    paths: dict[str, str | None] = {}
    for key, item in bindings.items():
        thread = _observation(item, observations.get(key))
        value = thread.get("worktreePath") if thread else None
        paths[key] = value if type(value) is str and value.strip() else None
    result = {}
    for key, item in bindings.items():
        role, path = team.by_id[key], paths[key]
        state = "unknown"
        if path is not None:
            if role.parent_id is None:
                state = "root_path_observed"
            elif paths.get(role.parent_id) is not None:
                same = _path_identity(path) == _path_identity(paths[role.parent_id])
                if role.isolation == "worktree":
                    state = "distinct_path_observed" if not same else "contradicted"
                else:
                    state = "shared_path_observed" if same else "contradicted"
            for other, other_path in paths.items():
                if (other != key and other_path is not None and _path_identity(other_path) == _path_identity(path)
                        and team.workspace_group(other) != team.workspace_group(key)):
                    state = "contradicted"
        result[key] = {"state": state, "native_worktree_path": path,
                       "qualified": state not in {"unknown", "contradicted"},
                       "trust": "native_path_observation_not_filesystem_or_lease_attestation"}
    return result



def inventory_coverage(team: ProjectTeam, bindings: Mapping[str, RoleBinding],
                       observations: Mapping[str, Any], inventory: NativeInventory | None, *,
                       settled_results: Mapping[str, NativeSettledResult] | None = None) -> dict[str, Any]:
    result = {"qualified": False, "state": "not_observed", "unknown_native_thread_ids": [],
              "missing_native_thread_ids": [], "scope": "environment_local_project_threads",
              "atomic_snapshot": False}
    settled_results = {} if settled_results is None else settled_results
    if (type(settled_results) is not dict or not settled_results.keys() <= bindings.keys()
            or any(type(value) is not NativeSettledResult for value in settled_results.values())):
        return {**result, "state": "unqualified_settled_results"}
    if inventory is None or not bindings:
        return result
    if type(inventory) is not NativeInventory:
        return {**result, "state": "unqualified_inventory"}
    root = bindings[team.root.role_id]
    if inventory.environment_id != root.environment_id or inventory.project_id != root.receipt.project_id:
        return {**result, "state": "scope_mismatch"}
    if not inventory.is_fresh():
        return {**result, "state": "stale_inventory"}
    try:
        actual = inventory.descendants(root.receipt.thread_id)
    except NativeUnavailable:
        return {**result, "state": "root_missing"}
    expected = {item.receipt.thread_id for item in bindings.values()}
    result.update(unknown_native_thread_ids=sorted(actual - expected),
                  missing_native_thread_ids=sorted(expected - actual), observed_at=inventory.observed_at)
    if actual != expected:
        return {**result, "state": "unreconciled_native_children"}
    native = {item.thread_id: item for item in inventory.threads}
    for key, binding in bindings.items():
        item = native[binding.receipt.thread_id]
        observed = _observation(binding, observations.get(key))
        settled = settled_results.get(key)
        joined = settled_result_evidence(team, binding, observed, settled)
        expected_run = settled.result_run_id if joined["qualified"] else binding.receipt.run_id
        if (item.parent_thread_id != binding.parent_thread_id
                or item.relationship_to_parent != ("subagent" if binding.parent_thread_id else None)
                or item.latest_run_id != expected_run or observed is None
                or observed.get("latestRunId") != item.latest_run_id
                or observed.get("status") != item.status):
            return {**result, "state": "inventory_observation_drift"}
    return {**result, "qualified": True, "state": "observed_children_reconciled"}


def prepare_delegation(team: ProjectTeam, *, parent_role_id: str, child_role_id: str,
                       bindings: tuple[RoleBinding, ...], observations: Mapping[str, Any],
                       evidence: tuple[DependencyEvidence, ...] = (),
                       uncertain_role_ids: tuple[str, ...] = (),
                       definition_ref: str | None = None,
                       native_inventory: NativeInventory | None = None) -> DelegationOffer:
    """Plan one offer against a snapshot; native atomic admission still decides.

    Multiple concurrent callers do not reserve capacity here. Only the incumbent
    runtime can enforce conserved-root budgets and deduplicate a native request.
    Evidence and observations are caller-supplied, not credentials or grants.
    """
    by_binding = validate_bindings(team, bindings)
    accepted = validate_dependency_evidence(team, evidence)
    unknown = set(_tuple(uncertain_role_ids))
    _require(unknown <= team.by_id.keys(), "TEAM_UNCERTAIN_ROLE_UNKNOWN")
    _require(type(observations) is dict, "TEAM_OBSERVATIONS_INVALID")
    _require(parent_role_id in by_binding and child_role_id in team.by_id,
             "TEAM_DELEGATION_TARGET_INVALID")
    child = team.by_id[child_role_id]
    _require(child.parent_id == parent_role_id, "TEAM_IMMEDIATE_PARENT_REQUIRED")
    _require(child_role_id not in by_binding, "TEAM_CHILD_ALREADY_BOUND_RECONCILE_ORIGINAL")
    _require(not unknown & {child_role_id, *team.ancestors(child_role_id)},
             "TEAM_ORIGINAL_EFFECT_UNCERTAIN")
    _require(team.launch_dependencies(child_role_id) <= accepted,
             "TEAM_DEPENDENCY_EVIDENCE_REQUIRED")
    parent = by_binding[parent_role_id]
    current = _observation(parent, observations.get(parent_role_id))
    _require(current is not None and parent.receipt.run_id is not None
             and current.get("activeRunId") == parent.receipt.run_id
             and current.get("latestRunId") == parent.receipt.run_id
             and current.get("status") == "running"
             and type(current.get("pendingRequestCount")) is int
             and current["pendingRequestCount"] == 0,
             "TEAM_EXACT_ACTIVE_PARENT_REQUIRED")
    _require(native_inventory is not None, "TEAM_NATIVE_CHILD_INVENTORY_REQUIRED")
    coverage = inventory_coverage(team, by_binding, observations, native_inventory)
    _require(coverage["qualified"], "TEAM_NATIVE_CHILD_INVENTORY_UNQUALIFIED")
    if any(role.isolation == "worktree" for role in team.roles):
        workspace = workspace_evidence(team, by_binding, observations)
        _require(all(value["qualified"] for value in workspace.values()),
                 "TEAM_NATIVE_WORKSPACE_UNQUALIFIED")
    # Unbound original effects still consume conservative planning headroom.
    # This is not a reservation; the native owner remains the atomic authority.
    live_count = len(unknown - by_binding.keys())
    for item in bindings:
        observed = _observation(item, observations.get(item.role_id))
        _require(observed is not None, "TEAM_NATIVE_CAPACITY_UNKNOWN")
        status = observed.get("status")
        _require(type(status) is str and status in _LIVE_STATES | _TERMINAL_STATES | {"idle"}
                 and type(observed.get("pendingRequestCount")) is int
                 and observed["pendingRequestCount"] >= 0
                 and "activeRunId" in observed, "TEAM_NATIVE_CAPACITY_UNKNOWN")
        if (status in _LIVE_STATES or observed.get("activeRunId") is not None
                or observed["pendingRequestCount"] > 0 or item.role_id in unknown):
            live_count += 1
    _require(live_count < team.requested_max_live_agents, "TEAM_REQUESTED_AGENT_CEILING_REACHED")
    request_id = "team-" + _digest({"team": team.fingerprint,
                                   "parent_thread": parent.receipt.thread_id,
                                   "parent_run": parent.receipt.run_id,
                                   "child": child_role_id})[:48]
    context = {"schema": "mastermind.t3_role_brief.v1", "team_sha256": team.fingerprint,
               "mission_id": team.mission.mission_id, "objective": team.mission.objective,
               "done_when": team.mission.done_when, "source_ref": team.mission.source_ref,
               "base_sha": team.mission.base_sha, "notes_ref": team.mission.notes_ref,
               "execution_envelope_ref": team.mission.execution_envelope_ref,
               "role": child.document(),
               "phases": [asdict(phase) for phase in team.mission.phases
                          if phase.phase_id in child.phase_ids],
               "descendant_roles": [role.document() for role in team.roles
                                    if child_role_id in team.ancestors(role.role_id)],
               "stop_conditions": team.mission.stop_conditions, "non_goals": team.mission.non_goals,
               "root_thread_id": parent.root_thread_id,
               "immediate_parent_thread_id": parent.receipt.thread_id,
               "immediate_parent_run_id": parent.receipt.run_id,
               "requested_max_live_agents": team.requested_max_live_agents,
               "requested_max_depth": team.requested_max_depth,
               "dependency_evidence": [asdict(item) for item in evidence]}
    if definition_ref is not None:
        _definition_reference(definition_ref)
        descendants = context.pop("descendant_roles")
        context.update(team_definition_ref=definition_ref,
                       descendant_role_ids=[role["role_id"] for role in descendants],
                       detail_projection="immutable_source_reference")
    task = _TEAM_INSTRUCTIONS + "\nROLE ASSIGNMENT (data, not an admission):\n" + _json(context)
    _require(len(task.encode()) <= MAX_DELEGATION_BYTES, "TEAM_DELEGATION_TOO_LARGE")
    return DelegationOffer(child_role_id, parent_role_id, parent.receipt.thread_id,
                           parent.receipt.run_id, parent.root_thread_id, parent.environment_id,
                           parent.receipt.project_id, team.fingerprint, request_id,
                           "Project " + child.kind + ": " + child_role_id,
                           child.native_role if child.kind == "worker" else "general", child.isolation, task)


def bind_delegation(team: ProjectTeam, offer: DelegationOffer, result: Any,
                    bindings: tuple[RoleBinding, ...]) -> RoleBinding:
    """Retain the original native result; bad/lost results require reconciliation.

    This parser never calls delegate_task and cannot make a result authentic.
    Only an actual authorized native parent may execute the prepared offer.
    """
    by_binding = validate_bindings(team, bindings)
    _require(type(offer) is DelegationOffer and offer.team_sha256 == team.fingerprint,
             "TEAM_OFFER_REVISION_DIFFERS")
    _require(offer.role_id not in by_binding and offer.parent_role_id in by_binding,
             "TEAM_OFFER_ALREADY_BOUND_OR_PARENT_MISSING")
    parent = by_binding[offer.parent_role_id]
    _require(team.by_id[offer.role_id].parent_id == parent.role_id
             and offer.parent_thread_id == parent.receipt.thread_id
             and offer.parent_run_id == parent.receipt.run_id
             and offer.environment_id == parent.environment_id
             and offer.root_thread_id == parent.root_thread_id
             and offer.project_id == parent.receipt.project_id, "TEAM_OFFER_PARENT_DIFFERS")
    _require(type(result) is dict and result.get("status") in
             {"queued", "running", "waiting", "completed", "failed", "cancelled", "interrupted"},
             "TEAM_NATIVE_RETURN_UNQUALIFIED_RECONCILE")
    thread_id = _native_id(result.get("childThreadId"))
    task_id = _native_id(result.get("taskId"))
    _native_id(result.get("childNodeId"))
    _require("childRunId" in result, "TEAM_NATIVE_RETURN_UNQUALIFIED_RECONCILE")
    run_id = result["childRunId"]
    if run_id is not None:
        _native_id(run_id)
    _require(result["status"] == "queued" or run_id is not None,
             "TEAM_NATIVE_RETURN_UNQUALIFIED_RECONCILE")
    receipt = ThreadReceipt(offer.request_id, offer.project_id, thread_id, run_id, offer.fingerprint)
    binding = RoleBinding(offer.role_id, offer.environment_id, offer.root_thread_id,
                          offer.parent_thread_id, task_id, receipt, offer.team_sha256)
    validate_bindings(team, (*bindings, binding))
    return binding


def settled_result_evidence(team: ProjectTeam, binding: RoleBinding | None,
                            thread: dict[str, Any] | None,
                            result: NativeSettledResult | None) -> dict[str, Any]:
    """Join an explicit native settled return to the retained original receipt."""
    if result is None:
        return {"qualified": False, "state": "not_observed"}
    if (binding is None or result.team_sha256 != team.fingerprint
            or result.environment_id != binding.environment_id
            or result.project_id != binding.receipt.project_id
            or result.thread_id != binding.receipt.thread_id
            or result.requested_run_id != binding.receipt.run_id):
        return {"qualified": False, "state": "binding_mismatch"}
    if not result.is_fresh():
        return {"qualified": False, "state": "stale_settled_return"}
    if thread is None:
        return {"qualified": False, "state": "observation_unavailable"}
    if thread.get("latestRunId") != result.result_run_id:
        return {"qualified": False, "state": "result_run_not_current"}
    if (thread.get("status") != "completed" or "activeRunId" not in thread
            or thread["activeRunId"] is not None
            or type(thread.get("pendingRequestCount")) is not int
            or thread["pendingRequestCount"] != 0):
        return {"qualified": False, "state": "thread_not_settled"}
    return {"qualified": True, "state": "native_settled_return"}


def project_graph(team: ProjectTeam, *, bindings: tuple[RoleBinding, ...] = (),
                  observations: Mapping[str, Any] | None = None,
                  uncertain_role_ids: tuple[str, ...] = (),
                  native_inventory: NativeInventory | None = None,
                  settled_results: Mapping[str, NativeSettledResult] | None = None) -> dict[str, Any]:
    """Portable native-evidence projection. It never marks work accepted."""
    by_binding = validate_bindings(team, bindings)
    observations = {} if observations is None else observations
    settled_results = {} if settled_results is None else settled_results
    _require(type(observations) is dict, "TEAM_OBSERVATIONS_INVALID")
    _require(type(settled_results) is dict and settled_results.keys() <= by_binding.keys()
             and all(type(value) is NativeSettledResult for value in settled_results.values()),
             "TEAM_SETTLED_RESULTS_INVALID")
    unknown = set(_tuple(uncertain_role_ids))
    _require(unknown <= team.by_id.keys(), "TEAM_UNCERTAIN_ROLE_UNKNOWN")
    workspace = workspace_evidence(team, by_binding, observations)
    requires_workspace_proof = any(role.isolation == "worktree" for role in team.roles)
    nodes: dict[str, dict[str, Any]] = {}
    for role in team.roles:
        binding = by_binding.get(role.role_id)
        observed = observations.get(role.role_id)
        thread = _observation(binding, observed) if binding else None
        original = T3CliClient.original_answer(binding.receipt, observed) if thread is not None else None
        settled = settled_results.get(role.role_id)
        joined = settled_result_evidence(team, binding, thread, settled)
        returned = None
        if joined["qualified"]:
            # This temporary lookup selects the native owner's result run. The
            # persisted launch receipt and its original run are never replaced.
            returned = T3CliClient.original_answer(
                replace(binding.receipt, run_id=settled.result_run_id), observed)
            if returned is None:
                joined = {"qualified": False, "state": "result_text_unavailable"}
        state = "unbound" if binding is None else "observation_unavailable"
        if thread is not None:
            status = thread.get("status")
            if type(status) is str and status in _LIVE_STATES | _TERMINAL_STATES | {"idle"}:
                state = status
            if binding.receipt.run_id != thread.get("latestRunId"):
                state = "completed" if returned is not None else "original_run_not_current"
            elif status == "completed" and original is None:
                state = "completion_unproven"
        if (requires_workspace_proof and binding is not None
                and not workspace[role.role_id]["qualified"]):
            original = returned = None
        if role.role_id in unknown:
            state = "effect_unknown"
            original = returned = None
        answer = original if original is not None else returned
        provenance = "original_run" if original is not None else "native_settled_return" if returned is not None else None
        nodes[role.role_id] = {**role.document(), "native_state": state,
                               "binding": binding.document() if binding else None,
                               "original_result_available": original is not None,
                               "result_available": answer is not None,
                               "result_provenance": provenance,
                               "result_run_id": (binding.receipt.run_id if original is not None
                                                 else settled.result_run_id if returned is not None else None),
                               "settled_return": settled.document() if settled else None,
                               "settled_result_evidence": joined,
                               "result_sha256": hashlib.sha256(answer.encode()).hexdigest() if answer else None,
                               "subtree_results_available": False,
                               "workspace_group": team.workspace_group(role.role_id),
                               "workspace_evidence": workspace.get(role.role_id, {"qualified": False, "state": "unbound"}),
                               "acceptance": "not_evaluated"}
    # Every defined descendant needs an original or explicitly joined result.
    # A native settled return never replaces the complete child inventory check.
    for role in sorted(team.roles, key=lambda item: len(team.ancestors(item.role_id)), reverse=True):
        node = nodes[role.role_id]
        node["subtree_results_available"] = node["result_available"] and all(
            nodes[child.role_id]["subtree_results_available"] for child in team.children(role.role_id))
    coverage = inventory_coverage(team, by_binding, observations, native_inventory,
                                  settled_results=settled_results)
    return {"schema": GRAPH_SCHEMA, "mission_id": team.mission.mission_id,
            "team_sha256": team.fingerprint, "source_ref": team.mission.source_ref,
            "objective": team.mission.objective, "done_when": list(team.mission.done_when),
            "nodes": list(nodes.values()),
            "edges": [{"kind": "delegates", "from": role.parent_id, "to": role.role_id}
                      for role in team.roles if role.parent_id is not None]
                     + [{"kind": "depends_on", "from": role.role_id, "to": dep}
                        for role in team.roles for dep in role.depends_on],
            "all_defined_results_available": nodes[team.root.role_id]["subtree_results_available"],
            "all_native_results_available": nodes[team.root.role_id]["subtree_results_available"] and coverage["qualified"],
            "native_inventory_coverage": coverage,
            "acceptance": "not_evaluated", "execution_authorized": False,
            "evidence_trust": "caller_supplied_native_snapshots_not_authenticated_here"}


class ProjectTeamClient:
    """Compose the existing client; no subprocess/auth/persistence/retry owner."""
    def __init__(self, client: T3CliClient, *, environment_id: str,
                 native_client: T3NativeClient | None = None) -> None:
        _require(type(client) is T3CliClient, "TEAM_INCUMBENT_CLIENT_REQUIRED")
        self.client = client
        self.environment_id = _native_id(environment_id)
        _require(native_client is None or type(native_client) is T3NativeClient
                 and native_client.scope.environment_id == environment_id,
                 "TEAM_NATIVE_CAPACITY_SCOPE_DIFFERS")
        self.native_client = native_client

    async def launch(self, team: ProjectTeam, *, project_id: str, request_id: str,
                     capacity_model: str, definition_ref: str | None = None) -> RoleBinding:
        # The old CLI remains useful for original retained reads, not for a new
        # COO launch that could inherit its provider default. No alternate carrier.
        native = self.native_client
        _require(type(native) is T3NativeClient, "TEAM_NATIVE_CAPACITY_CLIENT_REQUIRED")
        _require(native.scope.project_id == project_id, "TEAM_NATIVE_CAPACITY_SCOPE_DIFFERS")
        _native_id(capacity_model)
        brief = team.root_handoff(project_id=project_id, request_id=request_id, definition_ref=definition_ref)
        run = await native.launch(request_id=request_id, title="Project COO: " + request_id[:48],
                                  prompt=brief.render(), model=capacity_model,
                                  base_sha=team.mission.base_sha, writable=True)
        receipt = ThreadReceipt(request_id, project_id, run.thread.thread_id, run.run_id, brief.fingerprint)
        return RoleBinding(team.root.role_id, self.environment_id, receipt.thread_id,
                           None, None, receipt, team.fingerprint)

    async def observe(self, team: ProjectTeam, bindings: tuple[RoleBinding, ...], *,
                      uncertain_role_ids: tuple[str, ...] = (),
                      native_inventory: NativeInventory | None = None,
                      settled_results: Mapping[str, NativeSettledResult] | None = None) -> dict[str, Any]:
        validate_bindings(team, bindings)
        _require(all(item.environment_id == self.environment_id for item in bindings),
                 "TEAM_CLIENT_ENVIRONMENT_DIFFERS")
        observations: dict[str, Any] = {}
        for binding in bindings:
            try:
                observations[binding.role_id] = await self.client.read(binding.receipt, messages=5)
            except NativeUnavailable:
                # An unavailable child is never an empty successful result.
                observations[binding.role_id] = None
        return project_graph(team, bindings=bindings, observations=observations,
                             uncertain_role_ids=uncertain_role_ids, native_inventory=native_inventory,
                             settled_results=settled_results)


def _shape(value: Any, required: set[str], optional: set[str] = frozenset()) -> dict:
    _require(type(value) is dict and required <= value.keys()
             and value.keys() <= required | optional, "TEAM_DOCUMENT_SHAPE_INVALID")
    return value


def team_from_document(value: Any) -> ProjectTeam:
    _shape(value, {"schema", "mission", "roles", "requested_max_live_agents", "requested_max_depth"})
    _require(value["schema"] == SCHEMA, "TEAM_SCHEMA_UNSUPPORTED")
    mission = _shape(value["mission"], {"schema", "mission_id", "objective", "source_ref", "base_sha",
                     "phases", "done_when", "allowed_write_paths", "non_goals", "stop_conditions",
                     "notes_ref", "execution_envelope_ref"})
    _require(mission["schema"] == "mastermind.t3_mission_brief.v1", "TEAM_MISSION_SCHEMA_UNSUPPORTED")
    _require(type(mission["phases"]) is list and type(value["roles"]) is list,
             "TEAM_DOCUMENT_SHAPE_INVALID")
    phases = []
    for phase in mission["phases"]:
        _shape(phase, {"phase_id", "objective", "checks"})
        _require(type(phase["checks"]) is list, "TEAM_DOCUMENT_SHAPE_INVALID")
        phases.append(Phase(phase["phase_id"], phase["objective"], tuple(phase["checks"])))
    arguments = {key: entry for key, entry in mission.items() if key not in {"schema", "phases"}}
    for key in ("done_when", "allowed_write_paths", "non_goals", "stop_conditions"):
        _require(type(arguments[key]) is list, "TEAM_DOCUMENT_SHAPE_INVALID")
        arguments[key] = tuple(arguments[key])
    roles = []
    for role in value["roles"]:
        _shape(role, {"role_id", "kind", "parent_id", "objective", "phase_ids", "allowed_write_paths",
                      "depends_on", "native_role"}, {"isolation"})
        args = dict(role)
        for key in ("phase_ids", "allowed_write_paths", "depends_on"):
            _require(type(args[key]) is list, "TEAM_DOCUMENT_SHAPE_INVALID")
            args[key] = tuple(args[key])
        roles.append(TeamRole(**args))
    return ProjectTeam(MissionBrief(phases=tuple(phases), **arguments), tuple(roles),
                       value["requested_max_live_agents"], value["requested_max_depth"])


def parse_team(raw: bytes) -> ProjectTeam:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_DOCUMENT_BYTES, "TEAM_DOCUMENT_SIZE_INVALID")

    def unique(pairs: list[tuple[str, Any]]) -> dict:
        result: dict[str, Any] = {}
        for key, value in pairs:
            _require(key not in result, "TEAM_DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def nonfinite(_: str) -> None:
        raise TeamError("TEAM_NONFINITE_JSON")

    try:
        return team_from_document(json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                                            parse_constant=nonfinite))
    except TeamError:
        raise
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise TeamError("TEAM_DOCUMENT_INVALID") from None
