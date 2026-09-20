"""Deterministic exact-scope closure for Session Truth R1.

The source snapshots remain complete immutable observations.  This module only
selects the rows that may affect findings and required-source admission for one
requested scope.  Repository names fence GitHub identities; they do not turn
every PR in a repository into an in-scope carrier.
"""
from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from control_plane.session_truth_contract import SessionTruthContractError


def _available(source: object) -> bool:
    return isinstance(source, Mapping) and source.get("available") is True


def _rows(source: object, key: str) -> tuple[Mapping[str, Any], ...]:
    if not _available(source):
        return ()
    value = source.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(row for row in value if isinstance(row, Mapping))


@dataclass(frozen=True)
class SessionTruthScopeSelection:
    """Exact row identities reachable from the caller's explicit scope."""

    workstreams: frozenset[str]
    linear_issues: frozenset[str]
    repositories: frozenset[str]
    operation_keys: frozenset[str]
    github_pull_requests: frozenset[tuple[str, int]]
    slack_messages: frozenset[tuple[str, str]]
    executive_operations: frozenset[str]
    identity_references: frozenset[tuple[str, str]]
    agentos_context_indexes: frozenset[int]


def select_session_truth_scope(
    inputs: Mapping[str, Any],
) -> SessionTruthScopeSelection:
    """Return the finite exact-identity closure for ``inputs.scope``.

    Workstream, Linear and operation identities are union seeds.  GitHub rows
    must also pass the repository namespace fence.  Expansion follows only
    explicit identifiers: Agent OS PR numbers, PR workstream/Linear/operation
    fields, Linear repository-qualified relations and parent/child identities.
    """

    scope = inputs.get("scope")
    if not isinstance(scope, Mapping):
        raise SessionTruthContractError("scope must be an object")

    requested_workstreams = {
        value
        for value in scope.get("workstreams") or []
        if isinstance(value, str) and value
    }
    workstreams = set(requested_workstreams)
    linear_issues = {
        value
        for value in scope.get("linear") or []
        if isinstance(value, str) and value
    }
    operation = scope.get("operation_key")
    operation_keys = (
        {operation} if isinstance(operation, str) and operation else set()
    )
    if not workstreams and not linear_issues and not operation_keys:
        raise SessionTruthContractError(
            "scope requires a workstream, Linear issue or operation key seed"
        )
    repositories = {
        value
        for value in scope.get("repositories") or []
        if isinstance(value, str) and value
    }

    agentos = inputs.get("agentos")
    state = agentos.get("state") if _available(agentos) else None
    agentos_workstreams: dict[str, Mapping[str, Any]] = {}
    if isinstance(state, Mapping):
        for row in state.get("workstreams") or []:
            if isinstance(row, Mapping):
                key = row.get("key")
                if isinstance(key, str) and key:
                    agentos_workstreams[f"WS:{key}"] = row

    github_rows: dict[tuple[str, int], Mapping[str, Any]] = {}
    for row in _rows(inputs.get("github"), "pull_requests"):
        repository = row.get("repository")
        number = row.get("number")
        if (
            isinstance(repository, str)
            and type(number) is int
            and repository in repositories
        ):
            github_rows[(repository, number)] = row

    linear_rows = {
        row["id"]: row
        for row in _rows(inputs.get("linear"), "issues")
        if isinstance(row.get("id"), str) and row.get("id")
    }

    github_by_workstream: dict[str, list[tuple[str, int]]] = defaultdict(list)
    github_by_linear: dict[str, list[tuple[str, int]]] = defaultdict(list)
    github_by_operation: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for identity, row in github_rows.items():
        for field, target in (
            ("workstream", github_by_workstream),
            ("linear", github_by_linear),
            ("operation_key", github_by_operation),
        ):
            value = row.get(field)
            if isinstance(value, str) and value:
                target[value].append(identity)

    linear_by_workstream: dict[str, list[str]] = defaultdict(list)
    linear_children: dict[str, list[str]] = defaultdict(list)
    for issue_id, row in linear_rows.items():
        workstream = row.get("workstream")
        parent = row.get("parent_id")
        if isinstance(workstream, str) and workstream:
            linear_by_workstream[workstream].append(issue_id)
        if isinstance(parent, str) and parent:
            linear_children[parent].append(issue_id)

    selected_prs: set[tuple[str, int]] = set()
    selected_linear: set[str] = set()
    pr_queue: deque[tuple[str, int]] = deque()
    linear_queue: deque[str] = deque()

    def add_pr(identity: tuple[str, int]) -> None:
        if identity in github_rows and identity not in selected_prs:
            selected_prs.add(identity)
            pr_queue.append(identity)

    def add_linear(issue_id: str) -> None:
        if issue_id and issue_id not in selected_linear:
            selected_linear.add(issue_id)
            linear_queue.append(issue_id)

    for issue_id in linear_issues:
        add_linear(issue_id)
    for workstream_key in requested_workstreams:
        for identity in github_by_workstream.get(workstream_key, ()):
            add_pr(identity)
        for issue_id in linear_by_workstream.get(workstream_key, ()):
            add_linear(issue_id)
    for operation_key in operation_keys:
        for identity in github_by_operation.get(operation_key, ()):
            add_pr(identity)

    # A bare Agent OS PR number is repository-qualified only when the
    # requested scope names one repository (owner-record amendment section 7).
    if len(repositories) == 1:
        repository = next(iter(repositories))
        for workstream_key in requested_workstreams:
            row = agentos_workstreams.get(workstream_key)
            if not isinstance(row, Mapping):
                continue
            for pr in row.get("prs") or []:
                if isinstance(pr, Mapping) and type(pr.get("number")) is int:
                    add_pr((repository, pr["number"]))

    while pr_queue or linear_queue:
        while pr_queue:
            identity = pr_queue.popleft()
            row = github_rows[identity]
            workstream = row.get("workstream")
            linear = row.get("linear")
            operation_key = row.get("operation_key")
            if isinstance(workstream, str) and workstream:
                workstreams.add(workstream)  # context, not a new broad selector
            if isinstance(linear, str) and linear:
                add_linear(linear)
            if (
                isinstance(operation_key, str)
                and operation_key
                and operation_key not in operation_keys
            ):
                operation_keys.add(operation_key)
                for related in github_by_operation.get(operation_key, ()):
                    add_pr(related)

        while linear_queue:
            issue_id = linear_queue.popleft()
            for identity in github_by_linear.get(issue_id, ()):
                add_pr(identity)
            row = linear_rows.get(issue_id)
            if row is None:
                continue
            workstream = row.get("workstream")
            if isinstance(workstream, str) and workstream:
                workstreams.add(workstream)  # ownership context only
            parent_id = row.get("parent_id")
            if isinstance(parent_id, str) and parent_id:
                add_linear(parent_id)
            for child_id in linear_children.get(issue_id, ()):
                add_linear(child_id)
            for relation in row.get("github_relations") or []:
                if not isinstance(relation, Mapping):
                    continue
                identity = (relation.get("repository"), relation.get("number"))
                if relation.get("relation") != "ignored_wrong_id":
                    add_pr(identity)  # exact repository-qualified edge

    linear_issues = selected_linear

    slack_messages: set[tuple[str, str]] = set()
    identity_references: set[tuple[str, str]] = set()
    for row in _rows(inputs.get("slack"), "messages"):
        if row.get("operation_key") not in operation_keys:
            continue
        channel_id = row.get("channel_id")
        timestamp = row.get("ts")
        if isinstance(channel_id, str) and isinstance(timestamp, str):
            slack_messages.add((channel_id, timestamp))
        for field in ("sender_id", "target_principal_id"):
            value = row.get(field)
            if isinstance(value, str) and value:
                identity_references.add(("slack_principal", value))

    executive_operations = {
        row["operation_key"]
        for row in _rows(inputs.get("executive"), "operations")
        if isinstance(row.get("operation_key"), str)
        and row.get("operation_key") in operation_keys
    }
    context_indexes = {
        index
        for index, context in enumerate(
            agentos.get("contexts") or [] if _available(agentos) else []
        )
        if isinstance(context, Mapping)
        and isinstance(context.get("target"), Mapping)
        and context["target"].get("workstream") in requested_workstreams
    }

    return SessionTruthScopeSelection(
        workstreams=frozenset(workstreams),
        linear_issues=frozenset(linear_issues),
        repositories=frozenset(repositories),
        operation_keys=frozenset(operation_keys),
        github_pull_requests=frozenset(selected_prs),
        slack_messages=frozenset(slack_messages),
        executive_operations=frozenset(executive_operations),
        identity_references=frozenset(identity_references),
        agentos_context_indexes=frozenset(context_indexes),
    )


__all__ = ["SessionTruthScopeSelection", "select_session_truth_scope"]
