"""Bounded relationships over an already authorized company read.

Pure projection, not a graph store, roster, grant, dispatcher or recovery owner.
Only the supplied visible records and already disclosed configured joins are
used. Missing targets may be outside pagination/ACL coverage; never fetch them.
"""
from __future__ import annotations

import re

from common.paperclip_contract import KINDS
from .contract import PAGE_SIZE, PaperclipError, identifier

RELATIONS = (
    ("people", "reportsTo", "reports_to", "agent"),
    ("projects", "goalId", "project_goal", "goal"),
    ("projects", "leadAgentId", "project_lead", "agent"),
    ("goals", "parentId", "goal_parent", "goal"),
    ("goals", "ownerAgentId", "goal_owner", "agent"),
    ("work", "parentId", "issue_parent", "issue"),
    ("work", "projectId", "issue_project", "project"),
    ("work", "goalId", "issue_goal", "goal"),
    ("work", "assigneeAgentId", "issue_assignee", "agent"),
)
MAX_RELATIONSHIPS = 550
MAX_FINDINGS = 64
_WORK = re.compile(r"WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _ref(kind, value, owner="paperclip"):
    return {"owner": owner, "kind": kind, "id": value}


def project_connections(snapshot: dict) -> dict:
    """Describe this source window; no permission or execution is inferred.

    The incumbent service authenticates and fences the full read. A caller's
    Python object or a configured profile reference does not establish authority.
    This function must run before that service's final currentness check.
    """
    collections = snapshot["collections"]
    rows, visible, coverage, findings, edges = {}, {}, [], [], []
    finding_count = 0

    def finding(code, relation, refs=()):
        nonlocal finding_count
        finding_count += 1
        if len(findings) < MAX_FINDINGS:
            findings.append({"code": code, "relation": relation, "refs": list(refs)})

    for collection, kind in KINDS.items():
        source = collections.get(collection)
        state = "NOT_REQUESTED" if source is None else source["state"]
        items = [] if state != "CURRENT" else source["items"]
        if type(items) is not list or len(items) > PAGE_SIZE:
            raise PaperclipError("SOURCE_CONNECTIONS_INVALID")
        rows[collection], visible[kind] = items, set()
        coverage.append({"collection": collection, "state": state, "loaded": len(items),
                         "hasMore": bool(source and source["hasMore"]),
                         "restrictedCount": 0 if source is None else source.get("restrictedCount", 0)})
        for row in items:
            native_id = identifier(row["id"])
            if native_id in visible[kind]:
                finding("DUPLICATE_ID", collection, [_ref(kind, native_id)])
            visible[kind].add(native_id)

    for collection, field, relation, target_kind in RELATIONS:
        for row in rows[collection]:
            raw = row.get(field)
            if raw is None:
                continue
            origin = _ref(KINDS[collection], identifier(row["id"]))
            try:
                target = identifier(raw)
            except PaperclipError:
                finding("MALFORMED_REFERENCE", relation, [origin])
                continue
            destination = _ref(target_kind, target)
            edges.append({"relation": relation, "from": origin, "to": destination,
                          "state": "VISIBLE" if target in visible[target_kind] else "OUTSIDE_VISIBLE_WINDOW"})
            if origin == destination:
                finding("SELF_REFERENCE", relation, [origin])

    # Parent relations are containment/reporting, not execution/dependency edges.
    # A cycle is provable only when every traversed record is in this visible read.
    for relation in ("reports_to", "goal_parent", "issue_parent"):
        parent = {edge["from"]["id"]: edge for edge in edges
                  if edge["relation"] == relation and edge["state"] == "VISIBLE"}
        visited = set()
        for start in parent:
            trail, positions, cursor = [], {}, start
            while cursor in parent and cursor not in visited:
                if cursor in positions:
                    cycle = trail[positions[cursor]:]
                    if len(cycle) > 1:
                        finding("VISIBLE_CYCLE", relation, [parent[key]["from"] for key in cycle])
                    break
                positions[cursor] = len(trail)
                trail.append(cursor)
                cursor = parent[cursor]["to"]["id"]
            visited.update(trail)

    for bindings_key, source_kind, target_kind, field, native_field, owner, relation, cap in (
        ("runtimeBindings", "agent", "profile", "profileRef", "agentId", "hermes", "runs_as", 128),
        ("projectBindings", "project", "workstream", "workRef", "projectId", "agentos", "tracks_work", 256),
    ):
        bindings = snapshot[bindings_key]
        if type(bindings) is not list or len(bindings) > cap:
            raise PaperclipError("SOURCE_CONNECTIONS_INVALID")
        sources, targets = set(), set()
        for binding in bindings:
            native_id = identifier(binding[native_field])
            # A configured join is disclosed only after its source record was
            # read. Do not print a hidden profile/project in the finding itself.
            if native_id not in visible[source_kind]:
                continue
            source_ref = _ref(source_kind, native_id)
            target = binding[field]
            valid = (type(target) is str and 0 < len(target) <= 192
                     and not any(ord(char) < 32 for char in target))
            if owner == "agentos":
                valid = valid and _WORK.fullmatch(target) is not None
            else:
                valid = valid and binding.get("runtime") == "hermes" and binding.get("qualification") == "CONFIGURED_NOT_LIVE_VERIFIED"
            if not valid:
                finding("MALFORMED_BINDING", relation, [source_ref])
                continue
            if native_id in sources or target in targets:
                finding("AMBIGUOUS_BINDING", relation, [source_ref])
            sources.add(native_id)
            targets.add(target)
            edges.append({"relation": relation, "from": source_ref,
                          "to": _ref(target_kind, target, owner), "state": "CONFIGURED_NOT_LIVE_VERIFIED"})

    if len(edges) > MAX_RELATIONSHIPS:
        raise PaperclipError("SOURCE_CONNECTIONS_INVALID")
    outside = sum(edge["state"] == "OUTSIDE_VISIBLE_WINDOW" for edge in edges)
    partial = outside > 0 or any(row["state"] != "CURRENT" or row["hasMore"] or row["restrictedCount"] for row in coverage)
    return {
        "state": "WITHHELD" if findings else "PARTIAL" if partial else "CURRENT",
        "coverage": "VISIBLE_SOURCE_WINDOW", "consistency": "SEPARATE_READS_NOT_ATOMIC",
        "collectionCoverage": coverage, "relationships": [] if findings else edges,
        "findings": findings, "findingsOmitted": finding_count - len(findings),
        "outsideWindowCount": outside, "withheldRelationshipCount": len(edges) if findings else 0,
        "dependencies": "NOT_PROJECTED", "executionLineage": "NOT_PROJECTED",
        "parentConsumption": "NOT_OBSERVED",
        "helpAvenues": [
            {"kind": "browse_team", "state": "READ_ROUTE"},
            {"kind": "inspect_runtime", "state": "READ_ROUTE"},
            {"kind": "create_backlog", "state": "COMMAND_BOUND" if "create_backlog" in snapshot["capabilities"] else "NOT_BOUND_IN_THIS_SURFACE"},
            *({"kind": kind, "state": "NOT_BOUND_IN_THIS_SURFACE"} for kind in ("consult", "delegate", "resume")),
        ],
    }
