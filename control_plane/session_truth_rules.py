"""Pure deterministic drift classification for Session Truth R1.

This module consumes already-normalized read-only observations. It owns no source
acquisition, persistence, lifecycle, retry, identity inference, fuzzy matching or
network behavior. Every finding is emitted from exact identifiers and the frozen
registry below.
"""
from __future__ import annotations

import copy
from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from control_plane.session_truth_contract import valid_source_records_digest

FINDING_REGISTRY = {
    "AGENTOS_RECORD_IDENTITY_UNAVAILABLE": ("BLOCKING", "agentos", "agentos"),
    "STALE_LINEAR_PROJECTION": ("WARNING", "agentos", "linear"),
    "FALSE_LINEAR_COMPLETION": ("BLOCKING", "declared_completion_owner", "linear"),
    "MISSING_LINEAR_PROJECTION": ("WARNING", "agentos", "linear"),
    "LINEAR_PARENT_CHILD_DIVERGENCE": ("WARNING", "linear_projection", "linear"),
    "ORPHAN_LINEAR_ISSUE": ("WARNING", "agentos", "linear"),
    "BUILD_VISIBILITY_STALE": ("INFO", "github_or_linear", "slack"),
    "GITHUB_PR_UNBOUND": ("WARNING", "github", "github"),
    "GITHUB_MERGE_WITH_PROOF_OPEN": ("BLOCKING", "declared_completion_owner", "linear"),
    "ORPHAN_GITHUB_CARRIER": ("WARNING", "agentos", "github"),
    "MULTIPLE_ACTIVE_CARRIERS": ("FATAL", "github", "github"),
    "CARRIER_HEAD_MOVED": ("BLOCKING", "github", "github"),
    "PR_BINDING_CONFLICT": ("FATAL", "github", "github"),
    "AGENTOS_GITHUB_DISAGREEMENT": ("WARNING", "agentos_or_github_by_fact", "agentos_or_github"),
    "STALE_HANDOFF": ("WARNING", "agentos", "agentos"),
    "SUPERSEDED_NEXT_ACTION": ("WARNING", "agentos", "agentos"),
    "DIRECT_GENERATED_STATE_DIVERGENCE": ("WARNING", "agentos_direct", "agentos_generated"),
    "SLACK_TRANSPORT_WITHOUT_RECEIVER": ("BLOCKING", "executive_or_active_session", "slack"),
    "SLACK_TRANSPORT_WITHOUT_ACK": ("WARNING", "runtime_session", "slack"),
    "CEO_SEAT_USED_AS_WORKER": ("FATAL", "identity_registry", "slack"),
    "DUPLICATE_OPERATION_CARRIER": ("FATAL", "executive_or_carrier_owner", "slack_or_github"),
    "POST_FREEZE_DISPATCH_VIOLATION": ("BLOCKING", "source_law", "slack"),
    "RUNTIME_STATE_UNAVAILABLE": ("BLOCKING", "executive", "executive"),
    "RUNTIME_STATE_STALE": ("BLOCKING", "executive", "executive"),
    "SLACK_ACK_WITHOUT_EXECUTIVE_STATE": ("BLOCKING", "executive", "slack"),
    "EXECUTIVE_GROUNDING_DIVERGED": ("BLOCKING", "executive", "executive"),
    "UNKNOWN_SEAT_IDENTITY": ("WARNING", "identity_registry", "identity_registry"),
    "SERVICE_ACTOR_UNBOUND": ("BLOCKING", "identity_registry", "identity_registry"),
    "ACTOR_ROLE_COLLISION": ("FATAL", "identity_registry", "identity_registry"),
}

_SEVERITY_ORDER = {"FATAL": 0, "BLOCKING": 1, "WARNING": 2, "INFO": 3}
_CONSEQUENCE = {
    "FATAL": "new_modification_refused",
    "BLOCKING": "requested_modification_blocked",
    "WARNING": "repair_debt_visible",
    "INFO": "visibility_only",
}
_TERMINAL_LINEAR = frozenset({"Done", "Canceled", "Cancelled"})
_NONTERMINAL_PROOF = frozenset(
    {"open", "not_built", "spec_only", "partial", "built_not_proven", "blocked"}
)
_RUNNABLE_SLACK_CLASSES = frozenset({"PICKUP", "COMMISSION", "READ_ONLY_COMMISSION"})


def _available(source: Any) -> bool:
    """True only for a source that positively reported itself readable."""

    return isinstance(source, Mapping) and source.get("available") is True


def _rows(source: Any, key: str) -> list[dict[str, Any]]:
    if not _available(source):
        return []
    value = source.get(key)
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def build_indexes(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Build exact-key, defensive indexes. Titles/names never participate."""

    agentos = inputs.get("agentos")
    state = (
        agentos.get("state")
        if isinstance(agentos, Mapping) and agentos.get("available")
        else None
    )
    workstreams: dict[str, dict[str, Any]] = {}
    if isinstance(state, Mapping):
        for row in state.get("workstreams") or []:
            if isinstance(row, Mapping) and isinstance(row.get("key"), str) and row["key"]:
                workstreams[f"WS:{row['key']}"] = copy.deepcopy(dict(row))

    linear: dict[str, dict[str, Any]] = {}
    for issue in _rows(inputs.get("linear"), "issues"):
        issue_id = issue.get("id")
        if isinstance(issue_id, str) and issue_id:
            linear[issue_id] = copy.deepcopy(issue)

    github: dict[tuple[str, int], dict[str, Any]] = {}
    github_by_operation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    github_by_linear: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pr in _rows(inputs.get("github"), "pull_requests"):
        repository = pr.get("repository")
        number = pr.get("number")
        if isinstance(repository, str) and type(number) is int:
            stored = copy.deepcopy(pr)
            github[(repository, number)] = stored
            operation_key = stored.get("operation_key")
            if isinstance(operation_key, str) and operation_key:
                github_by_operation[operation_key].append(stored)
            linear_id = stored.get("linear")
            if isinstance(linear_id, str) and linear_id:
                github_by_linear[linear_id].append(stored)

    identities_by_slack: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identities_by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identities_by_github: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identities_by_linear: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identities_by_worker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for binding in _rows(inputs.get("identities"), "bindings"):
        stored = copy.deepcopy(binding)
        for field, target in (
            ("slack_principal", identities_by_slack),
            ("service_actor", identities_by_service),
            ("github_account", identities_by_github),
            ("linear_actor", identities_by_linear),
            ("executive_worker", identities_by_worker),
        ):
            value = stored.get(field)
            if isinstance(value, str) and value:
                target[value].append(stored)

    executive_operations: dict[str, dict[str, Any]] = {}
    for operation in _rows(inputs.get("executive"), "operations"):
        key = operation.get("operation_key")
        if isinstance(key, str) and key:
            executive_operations[key] = copy.deepcopy(operation)

    slack_by_operation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for message in _rows(inputs.get("slack"), "messages"):
        key = message.get("operation_key")
        if isinstance(key, str) and key:
            slack_by_operation[key].append(copy.deepcopy(message))

    return {
        "workstreams": workstreams,
        "linear": linear,
        # An empty index means "no issues"; it never means "Linear said nothing exists".
        "linear_available": _available(inputs.get("linear")),
        "github": github,
        "github_by_operation": dict(github_by_operation),
        "github_by_linear": dict(github_by_linear),
        "slack_by_operation": dict(slack_by_operation),
        "executive_operations": executive_operations,
        "identities_by_slack": dict(identities_by_slack),
        "identities_by_service": dict(identities_by_service),
        "identities_by_github": dict(identities_by_github),
        "identities_by_linear": dict(identities_by_linear),
        "identities_by_worker": dict(identities_by_worker),
    }


def _finding(
    code: str,
    subject: object,
    *,
    source_a: object = None,
    source_b: object = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    severity, canonical_owner, repair_owner = FINDING_REGISTRY[code]
    return {
        "code": code,
        "severity": severity,
        "canonical_owner": canonical_owner,
        "subject": str(subject),
        "source_a": copy.deepcopy(source_a),
        "source_b": copy.deepcopy(source_b),
        "repair_owner": repair_owner,
        "modification_consequence": _CONSEQUENCE[severity],
        "details": copy.deepcopy(dict(details or {})),
    }


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _day(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _is_runnable(message: Mapping[str, Any]) -> bool:
    return message.get("message_class") in _RUNNABLE_SLACK_CLASSES


def _append(
    findings: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    code: str,
    subject: object,
    *,
    source_a: object = None,
    source_b: object = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    key = (code, str(subject))
    if key in seen:
        return
    seen.add(key)
    findings.append(
        _finding(
            code,
            subject,
            source_a=source_a,
            source_b=source_b,
            details=details,
        )
    )


def detect_findings(inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return deterministic drift findings without mutating or consulting any source."""

    indexes = build_indexes(inputs)
    workstreams = indexes["workstreams"]
    linear = indexes["linear"]
    linear_available = indexes["linear_available"]
    github = indexes["github"]
    executive_ops = indexes["executive_operations"]
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    scope = inputs.get("scope") if isinstance(inputs.get("scope"), Mapping) else {}

    for issue_id in scope.get("linear") or []:
        # Absence is testimony only when Linear was actually read.
        if linear_available and isinstance(issue_id, str) and issue_id not in linear:
            _append(
                findings,
                seen,
                "MISSING_LINEAR_PROJECTION",
                issue_id,
                source_a={"scope_workstreams": list(scope.get("workstreams") or [])},
                source_b=None,
            )

    for issue_id, issue in linear.items():
        workstream_key = issue.get("workstream")
        if isinstance(workstream_key, str) and workstream_key and workstream_key not in workstreams:
            _append(
                findings,
                seen,
                "ORPHAN_LINEAR_ISSUE",
                issue_id,
                source_a={"workstream": workstream_key},
                source_b=None,
            )
        workstream = workstreams.get(workstream_key)
        if workstream:
            direct_revision = workstream.get("projection_revision")
            linear_revision = issue.get("projection_revision")
            if (
                type(direct_revision) is int
                and type(linear_revision) is int
                and direct_revision != linear_revision
            ):
                _append(
                    findings,
                    seen,
                    "STALE_LINEAR_PROJECTION",
                    issue_id,
                    source_a={"agentos_projection_revision": direct_revision},
                    source_b={"linear_projection_revision": linear_revision},
                )
        if issue.get("status") == "Done":
            # Linear is only a projection.  A false-completion finding therefore
            # requires exact bound owner evidence that the canonical proof remains
            # nonterminal.  Terminal proof makes Done valid; absent/future proof
            # classifications stay unknown rather than being guessed from the
            # spelling of the completion header.
            relations = {
                (relation.get("repository"), relation.get("number"))
                for relation in (issue.get("github_relations") or [])
                if isinstance(relation, Mapping)
            }
            bound_proof_states = [
                pr.get("proof_state")
                for pr in indexes["github_by_linear"].get(issue_id, [])
                if (pr.get("repository"), pr.get("number")) in relations
            ]
            if any(state in _NONTERMINAL_PROOF for state in bound_proof_states):
                _append(
                    findings,
                    seen,
                    "FALSE_LINEAR_COMPLETION",
                    issue_id,
                    source_a={
                        "completion": issue.get("completion"),
                        "owner_proof_states": sorted(
                            state
                            for state in bound_proof_states
                            if isinstance(state, str)
                        ),
                    },
                    source_b={"linear_status": "Done"},
                )

    for issue_id, issue in linear.items():
        parent_id = issue.get("parent_id")
        parent = linear.get(parent_id) if isinstance(parent_id, str) else None
        if (
            parent
            and parent.get("status") == "Done"
            and issue.get("status") not in _TERMINAL_LINEAR
        ):
            _append(
                findings,
                seen,
                "LINEAR_PARENT_CHILD_DIVERGENCE",
                f"{parent_id}->{issue_id}",
                source_a={"parent_status": parent.get("status")},
                source_b={"child_status": issue.get("status")},
            )

    slack = inputs.get("slack")
    if isinstance(slack, Mapping) and slack.get("available"):
        slack_time = _timestamp(slack.get("observed_at"))
        owner_times: list[tuple[str, datetime, str]] = []
        for source_name in ("github", "linear"):
            source = inputs.get(source_name)
            if isinstance(source, Mapping) and source.get("available"):
                observed = source.get("observed_at")
                parsed = _timestamp(observed)
                if parsed is not None and isinstance(observed, str):
                    owner_times.append((source_name, parsed, observed))
        if slack_time is not None and owner_times:
            newest = max(owner_times, key=lambda row: row[1])
            if slack_time < newest[1]:
                _append(
                    findings,
                    seen,
                    "BUILD_VISIBILITY_STALE",
                    "slack",
                    source_a={"slack_observed_at": slack.get("observed_at")},
                    source_b={f"{newest[0]}_observed_at": newest[2]},
                )

    active_by_workstream_wave: dict[tuple[str, object], list[dict[str, Any]]] = defaultdict(list)
    for (repository, number), pr in github.items():
        subject = f"{repository}#{number}"
        workstream_key = pr.get("workstream")
        if not workstream_key:
            _append(
                findings,
                seen,
                "GITHUB_PR_UNBOUND",
                subject,
                source_a={"portfolio_mode": pr.get("portfolio_mode")},
                source_b={"workstream": None},
            )
        elif workstream_key not in workstreams:
            _append(
                findings,
                seen,
                "ORPHAN_GITHUB_CARRIER",
                subject,
                source_a={"workstream": workstream_key},
                source_b=None,
            )

        if (
            pr.get("state") == "merged"
            and pr.get("completion") != "merge-is-done"
            and pr.get("proof_state") in _NONTERMINAL_PROOF
        ):
            _append(
                findings,
                seen,
                "GITHUB_MERGE_WITH_PROOF_OPEN",
                subject,
                source_a={"completion": pr.get("completion")},
                source_b={"proof_state": pr.get("proof_state")},
            )

        if pr.get("state") == "open" and isinstance(workstream_key, str) and workstream_key:
            active_by_workstream_wave[(workstream_key, pr.get("wave"))].append(pr)

        linear_id = pr.get("linear")
        if isinstance(linear_id, str) and linear_id:
            issue = linear.get(linear_id)
            if issue is None:
                # An unreadable Linear cannot testify that the bound issue is absent.
                if linear_available:
                    _append(
                        findings,
                        seen,
                        "PR_BINDING_CONFLICT",
                        subject,
                        source_a={"pr_linear": linear_id},
                        source_b=None,
                    )
            else:
                relations = issue.get("github_relations") or []
                exact_relation = any(
                    isinstance(relation, Mapping)
                    and relation.get("repository") == repository
                    and relation.get("number") == number
                    for relation in relations
                )
                if not exact_relation:
                    _append(
                        findings,
                        seen,
                        "PR_BINDING_CONFLICT",
                        subject,
                        source_a={"pr_linear": linear_id},
                        source_b={"github_relations": relations},
                    )

    for (workstream_key, wave), carriers in active_by_workstream_wave.items():
        if len(carriers) > 1:
            _append(
                findings,
                seen,
                "MULTIPLE_ACTIVE_CARRIERS",
                f"{workstream_key}#{wave or '-'}",
                source_a=[
                    f"{carrier.get('repository')}#{carrier.get('number')}" for carrier in carriers
                ],
                source_b=None,
            )

    # A bare Agent OS PR number carries no repository. It may be qualified only by
    # a requested scope naming exactly one repository; with several repositories in
    # scope the citation is AMBIGUOUS/UNBOUND and never joins by number, title,
    # workstream similarity or first match (owner-record amendment §7).
    scope_repositories = [
        repository
        for repository in (scope.get("repositories") or [])
        if isinstance(repository, str) and repository
    ]
    qualified_repository = (
        scope_repositories[0] if len(scope_repositories) == 1 else None
    )
    for workstream_key, workstream in workstreams.items():
        for agentos_pr in workstream.get("prs") or []:
            if not isinstance(agentos_pr, Mapping) or type(agentos_pr.get("number")) is not int:
                continue
            number = agentos_pr["number"]
            for (repository, github_number), pr in github.items():
                if github_number != number or pr.get("workstream") != workstream_key:
                    continue
                if repository != qualified_repository:
                    continue
                direct_state = agentos_pr.get("state")
                github_state = pr.get("state")
                if (
                    direct_state not in (None, "unknown")
                    and github_state
                    and direct_state != github_state
                ):
                    _append(
                        findings,
                        seen,
                        "AGENTOS_GITHUB_DISAGREEMENT",
                        f"{workstream_key}#{number}",
                        source_a={"agentos_state": direct_state},
                        source_b={"github_state": github_state, "repository": repository},
                    )

    agentos = inputs.get("agentos")
    # Owner record identity (amendment §3.2): when the requested scope requires
    # Agent OS, a readable observation without a complete set of valid owner
    # ``source_records_digest`` values cannot authorize modification. Absence of
    # the owner digest is typed and blocking, never silently healthy.
    if bool(scope.get("workstreams")) and isinstance(agentos, Mapping) and agentos.get(
        "available"
    ):
        state = agentos.get("state")
        state_digest_valid = isinstance(state, Mapping) and valid_source_records_digest(
            state.get("source_records_digest")
        )
        raw_contexts = agentos.get("contexts")
        contexts_missing: list[int] | None
        if isinstance(raw_contexts, list):
            contexts_missing = [
                index
                for index, context in enumerate(raw_contexts)
                if not (
                    isinstance(context, Mapping)
                    and valid_source_records_digest(context.get("source_records_digest"))
                )
            ]
        else:
            contexts_missing = None
        if not state_digest_valid or contexts_missing is None or contexts_missing:
            _append(
                findings,
                seen,
                "AGENTOS_RECORD_IDENTITY_UNAVAILABLE",
                "agentos",
                source_a={"state_source_records_digest_valid": state_digest_valid},
                source_b={"contexts_missing_source_records_digest": contexts_missing},
            )

    if isinstance(agentos, Mapping) and agentos.get("available"):
        state = agentos.get("state")
        if isinstance(state, Mapping):
            direct_hash = state.get("direct_state_hash")
            generated_hash = state.get("generated_state_hash")
            if direct_hash and generated_hash and direct_hash != generated_hash:
                _append(
                    findings,
                    seen,
                    "DIRECT_GENERATED_STATE_DIVERGENCE",
                    "agentos",
                    source_a={"direct_state_hash": direct_hash},
                    source_b={"generated_state_hash": generated_hash},
                )

        for context in agentos.get("contexts") or []:
            if not isinstance(context, Mapping):
                continue
            target = context.get("target")
            workstream_key = target.get("workstream") if isinstance(target, Mapping) else None
            workstream = workstreams.get(workstream_key)
            direct_updated = _day(workstream.get("updated")) if workstream else None
            for section in context.get("sections") or []:
                if not isinstance(section, Mapping) or section.get("id") != "handoff":
                    continue
                for item in section.get("items") or []:
                    if not isinstance(item, Mapping):
                        continue
                    handoff_updated = _day(item.get("updated"))
                    if (
                        direct_updated is not None
                        and handoff_updated is not None
                        and handoff_updated < direct_updated
                    ):
                        _append(
                            findings,
                            seen,
                            "STALE_HANDOFF",
                            item.get("path") or workstream_key or "handoff",
                            source_a={"handoff_updated": item.get("updated")},
                            source_b={"workstream_updated": workstream.get("updated")},
                        )
            for excluded in context.get("excluded") or []:
                if (
                    isinstance(excluded, Mapping)
                    and excluded.get("reason") == "superseded_next_action"
                ):
                    _append(
                        findings,
                        seen,
                        "SUPERSEDED_NEXT_ACTION",
                        excluded.get("path") or workstream_key or "agentos",
                        source_a=dict(excluded),
                        source_b={"workstream": workstream_key},
                    )

    identities = inputs.get("identities")
    if isinstance(identities, Mapping) and identities.get("available"):
        namespace_fields = (
            "slack_principal",
            "service_actor",
            "github_account",
            "linear_actor",
            "executive_worker",
        )
        namespace_values: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for binding in _rows(identities, "bindings"):
            if binding.get("role") == "sol_ceo" and not binding.get("slack_principal"):
                _append(
                    findings,
                    seen,
                    "UNKNOWN_SEAT_IDENTITY",
                    binding.get("seat") or "unknown",
                    source_a={"role": "sol_ceo"},
                    source_b={"slack_principal": None},
                )
            if binding.get("role") == "service_actor" and not binding.get("service_actor"):
                _append(
                    findings,
                    seen,
                    "SERVICE_ACTOR_UNBOUND",
                    binding.get("seat") or "unknown",
                    source_a={"role": "service_actor"},
                    source_b={"service_actor": None},
                )
            for field in namespace_fields:
                value = binding.get(field)
                if isinstance(value, str) and value:
                    namespace_values[(field, value)].append(binding)
        for (field, value), bindings in namespace_values.items():
            roles = sorted(
                {binding.get("role") for binding in bindings if binding.get("role")}
            )
            if len(roles) > 1:
                _append(
                    findings,
                    seen,
                    "ACTOR_ROLE_COLLISION",
                    f"{field}:{value}",
                    source_a={"roles": roles},
                    source_b={"seats": [binding.get("seat") for binding in bindings]},
                )

    executive = inputs.get("executive")
    requires_executive = bool(scope.get("requires_executive"))
    if requires_executive and (
        not isinstance(executive, Mapping) or not executive.get("available")
    ):
        reason = executive.get("reason") if isinstance(executive, Mapping) else None
        _append(
            findings,
            seen,
            "RUNTIME_STATE_UNAVAILABLE",
            "executive",
            source_a={"reason": reason},
            source_b={"requires_executive": True},
        )
    if (
        requires_executive
        and isinstance(executive, Mapping)
        and executive.get("available")
        and executive.get("fresh") is False
    ):
        _append(
            findings,
            seen,
            "RUNTIME_STATE_STALE",
            "executive",
            source_a={"observed_at": executive.get("observed_at")},
            source_b={"fresh": False},
        )
    skillpack = inputs.get("skillpack")
    if (
        isinstance(executive, Mapping)
        and executive.get("available")
        and isinstance(skillpack, Mapping)
        and skillpack.get("available")
        and executive.get("grounding_sha") != skillpack.get("sha")
    ):
        _append(
            findings,
            seen,
            "EXECUTIVE_GROUNDING_DIVERGED",
            "executive",
            source_a={"grounding_sha": executive.get("grounding_sha")},
            source_b={"protected_skillpack_sha": skillpack.get("sha")},
        )

    if isinstance(slack, Mapping) and slack.get("available"):
        channel_members = {
            channel.get("channel_id"): set(channel.get("member_ids") or [])
            for channel in _rows(slack, "channels")
            if isinstance(channel.get("channel_id"), str)
        }
        for message in _rows(slack, "messages"):
            subject = f"{message.get('channel_id')}@{message.get('ts')}"
            runnable = _is_runnable(message)
            target = message.get("target_principal_id")
            members = channel_members.get(message.get("channel_id"))
            target_missing = (
                runnable
                and isinstance(target, str)
                and bool(target)
                and members is not None
                and target not in members
            )
            receiver_missing = runnable and (
                message.get("receiver_eligible") is False or target_missing
            )
            if receiver_missing:
                _append(
                    findings,
                    seen,
                    "SLACK_TRANSPORT_WITHOUT_RECEIVER",
                    subject,
                    source_a={"target_principal_id": target},
                    source_b={
                        "receiver_eligible": message.get("receiver_eligible"),
                        "channel_member": False if target_missing else None,
                    },
                )

            if (
                message.get("ack_required") is True
                and message.get("delivered") is True
                and message.get("acked") is False
                and not receiver_missing
            ):
                _append(
                    findings,
                    seen,
                    "SLACK_TRANSPORT_WITHOUT_ACK",
                    subject,
                    source_a={"operation_key": message.get("operation_key")},
                    source_b={"acked": False},
                )

            if runnable and isinstance(target, str) and target:
                bindings = indexes["identities_by_slack"].get(target, [])
                if not bindings:
                    _append(
                        findings,
                        seen,
                        "UNKNOWN_SEAT_IDENTITY",
                        target,
                        source_a={"target_principal_id": target},
                        source_b=None,
                    )
                if any(binding.get("role") == "sol_ceo" for binding in bindings):
                    _append(
                        findings,
                        seen,
                        "CEO_SEAT_USED_AS_WORKER",
                        target,
                        source_a={"seats": [binding.get("seat") for binding in bindings]},
                        source_b={"message_class": message.get("message_class")},
                    )

            freeze_at = _timestamp(message.get("freeze_at"))
            created_at = _timestamp(message.get("created_at"))
            if runnable and freeze_at is not None and created_at is not None and created_at > freeze_at:
                _append(
                    findings,
                    seen,
                    "POST_FREEZE_DISPATCH_VIOLATION",
                    subject,
                    source_a={"freeze_at": message.get("freeze_at")},
                    source_b={"created_at": message.get("created_at")},
                )

            operation_key = message.get("operation_key")
            # Amendment §6: only a scope that positively owes Executive state, with
            # Executive itself readable, can testify that an acked operation is
            # absent from Executive observations. An unreadable Executive defers to
            # the required-source path; a read-only/active-session ACK owes nothing.
            if (
                requires_executive
                and isinstance(executive, Mapping)
                and executive.get("available") is True
                and message.get("acked") is True
                and message.get("ack_required") is True
                and isinstance(operation_key, str)
                and operation_key
                and operation_key not in executive_ops
            ):
                _append(
                    findings,
                    seen,
                    "SLACK_ACK_WITHOUT_EXECUTIVE_STATE",
                    operation_key,
                    source_a={"slack_acked": True},
                    source_b={"executive_operation": None},
                )

            if isinstance(operation_key, str) and operation_key in executive_ops:
                operation = executive_ops[operation_key]
                slack_hash = message.get("payload_hash")
                executive_hash = operation.get("payload_hash")
                changed_payload = (
                    slack_hash is not None
                    and executive_hash is not None
                    and slack_hash != executive_hash
                )
                if changed_payload or operation.get("effect_unknown") is True:
                    _append(
                        findings,
                        seen,
                        "DUPLICATE_OPERATION_CARRIER",
                        operation_key,
                        source_a={"slack_payload_hash": slack_hash},
                        source_b={
                            "executive_payload_hash": executive_hash,
                            "effect_unknown": bool(operation.get("effect_unknown")),
                        },
                    )

    for operation_key, carriers in indexes["github_by_operation"].items():
        active = [carrier for carrier in carriers if carrier.get("state") == "open"]
        if len(active) > 1:
            _append(
                findings,
                seen,
                "DUPLICATE_OPERATION_CARRIER",
                operation_key,
                source_a=[
                    f"{carrier.get('repository')}#{carrier.get('number')}" for carrier in active
                ],
                source_b=None,
            )

    for operation_key, messages in indexes["slack_by_operation"].items():
        hashes = {
            message.get("payload_hash")
            for message in messages
            if isinstance(message.get("payload_hash"), str) and message.get("payload_hash")
        }
        if len(hashes) > 1:
            _append(
                findings,
                seen,
                "DUPLICATE_OPERATION_CARRIER",
                operation_key,
                source_a={"slack_payload_hashes": sorted(hashes)},
                source_b=None,
            )

    findings.sort(
        key=lambda item: (
            _SEVERITY_ORDER[item["severity"]],
            item["code"],
            item["subject"],
        )
    )
    return findings
