"""Deterministic read-only context selection over an existing Session Truth receipt.

The resolver is navigation, never authority.  It does not acquire sources, persist state,
dispatch work, select a runtime, or mutate any canonical owner.  It selects exact rows
already admitted into one Session Truth receipt and emits a bounded context bundle that
can be consumed by the existing operating-context projection.

The first release deliberately uses exact identity edges before any semantic retrieval.
Future Project Atlas and live-source adapters must enrich the candidate set without
changing this authority boundary.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.session_truth_contract import canonical_json
from control_plane.session_truth_scope import select_session_truth_scope

CONTEXT_PACK_SCHEMA = "mastermind.context_pack.v1"
MAX_TASK_BYTES = 8 * 1024
MAX_SELECTED_ITEMS = 64
MAX_PACK_BYTES = 128 * 1024
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ContextResolverError(ValueError):
    """Raised when a context pack cannot be produced without guessing."""


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _task(value: object) -> str:
    if type(value) is not str:
        raise ContextResolverError("task must be a string")
    normalized = " ".join(value.split())
    if not normalized:
        raise ContextResolverError("task must not be empty")
    if len(normalized.encode("utf-8")) > MAX_TASK_BYTES:
        raise ContextResolverError("task exceeds byte bound")
    return normalized


def _rows(source: object, key: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(source, Mapping) or source.get("available") is not True:
        return ()
    value = source.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(row for row in value if isinstance(row, Mapping))


def _revision(value: object, fallback: str) -> str:
    if isinstance(value, str) and value:
        return value
    return fallback


def _candidate(
    *,
    priority: int,
    kind: str,
    owner: str,
    identity: str,
    revision: str,
    ref: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "priority": priority,
        "kind": kind,
        "owner": owner,
        "identity": identity,
        "revision": revision,
        "ref": ref,
        "reason": reason,
    }


def _receipt_inputs(receipt: Mapping[str, Any]) -> dict[str, Any]:
    observations = receipt.get("observations")
    if not isinstance(observations, Mapping):
        raise ContextResolverError("receipt observations are missing")
    return {
        "scope": receipt.get("scope"),
        "agentos": observations.get("agentos"),
        "github": observations.get("github"),
        "linear": observations.get("linear"),
        "slack": observations.get("slack"),
        "executive": observations.get("executive"),
        "identities": observations.get("identities"),
    }


def _validate_receipt(receipt: object) -> Mapping[str, Any]:
    if not isinstance(receipt, Mapping):
        raise ContextResolverError("receipt must be an object")
    if receipt.get("schema") != "mastermind.session_truth_receipt.v1":
        raise ContextResolverError("receipt schema is invalid")
    semantic_hash = receipt.get("semantic_hash")
    if not isinstance(semantic_hash, str) or _HEX64.fullmatch(semantic_hash) is None:
        raise ContextResolverError("receipt semantic hash is invalid")
    skillpack = receipt.get("skillpack")
    if not isinstance(skillpack, Mapping) or skillpack.get("available") is not True:
        raise ContextResolverError("available protected Skillpack evidence is required")
    sha = skillpack.get("sha")
    if not isinstance(sha, str) or _HEX40.fullmatch(sha) is None:
        raise ContextResolverError("Skillpack revision is invalid")
    scope = receipt.get("scope")
    if not isinstance(scope, Mapping):
        raise ContextResolverError("receipt scope is missing")
    return receipt


def _selected_source_digests(
    *,
    receipt: Mapping[str, Any],
    selection,
    selected_contexts: Sequence[Mapping[str, Any]],
    selected_prs: Sequence[Mapping[str, Any]],
    selected_linear: Sequence[Mapping[str, Any]],
    selected_slack: Sequence[Mapping[str, Any]],
    selected_executive: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    observations = receipt["observations"]
    skillpack = receipt["skillpack"]
    scoped_agentos_digests = [
        context.get("source_records_digest")
        for context in selected_contexts
        if isinstance(context.get("source_records_digest"), str)
        and context.get("source_records_digest")
    ]
    agentos_digest = (
        _digest(scoped_agentos_digests)
        if len(scoped_agentos_digests) == len(selected_contexts)
        else _digest(selected_contexts)
    )
    return {
        "skillpack": str(skillpack["sha"]),
        "agentos": agentos_digest,
        "github": _digest(selected_prs),
        "linear": _digest(selected_linear),
        "slack": _digest(selected_slack),
        "executive": _digest(selected_executive),
        "scope": _digest(
            {
                "workstreams": sorted(selection.workstreams),
                "linear": sorted(selection.linear_issues),
                "repositories": sorted(selection.repositories),
                "operations": sorted(selection.operation_keys),
            }
        ),
    }


def _collect_candidates(
    receipt: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    inputs = _receipt_inputs(receipt)
    selection = select_session_truth_scope(inputs)
    observations = receipt["observations"]
    skillpack = receipt["skillpack"]
    candidates: list[dict[str, Any]] = []

    repository = str(
        skillpack.get("repository") or "mastermindx-market-intelligence/Mastermind"
    )
    skillpack_sha = str(skillpack["sha"])
    candidates.append(
        _candidate(
            priority=0,
            kind="procedure",
            owner="github",
            identity="skillpack",
            revision=skillpack_sha,
            ref=f"ctx://skillpack/{repository}@{skillpack_sha}",
            reason="current protected procedure pin",
        )
    )

    agentos = observations.get("agentos")
    selected_contexts: list[Mapping[str, Any]] = []
    if isinstance(agentos, Mapping) and agentos.get("available") is True:
        raw_contexts = agentos.get("contexts")
        if isinstance(raw_contexts, Sequence) and not isinstance(
            raw_contexts, (str, bytes)
        ):
            for index in sorted(selection.agentos_context_indexes):
                if index >= len(raw_contexts) or not isinstance(
                    raw_contexts[index], Mapping
                ):
                    continue
                context = raw_contexts[index]
                selected_contexts.append(context)
                target = context.get("target")
                workstream = (
                    target.get("workstream")
                    if isinstance(target, Mapping)
                    else f"context-{index}"
                )
                revision = _revision(
                    context.get("source_records_digest"),
                    _revision(agentos.get("source_sha"), receipt["semantic_hash"]),
                )
                candidates.append(
                    _candidate(
                        priority=10,
                        kind="organizational_context",
                        owner="agentos",
                        identity=f"agentos:{workstream}",
                        revision=revision,
                        ref=f"ctx://agentos/{workstream}@{revision}",
                        reason="exact requested workstream context",
                    )
                )

    selected_prs: list[Mapping[str, Any]] = []
    for row in _rows(observations.get("github"), "pull_requests"):
        identity = (row.get("repository"), row.get("number"))
        if identity not in selection.github_pull_requests:
            continue
        selected_prs.append(row)
        repo, number = identity
        revision = _revision(row.get("head_sha"), receipt["semantic_hash"])
        candidates.append(
            _candidate(
                priority=40,
                kind="source_carrier",
                owner="github",
                identity=f"github-pr:{repo}#{number}",
                revision=revision,
                ref=f"ctx://github/{repo}/pull/{number}@{revision}",
                reason="exact scoped implementation/evidence carrier",
            )
        )

    selected_linear: list[Mapping[str, Any]] = []
    for row in _rows(observations.get("linear"), "issues"):
        issue_id = row.get("id")
        if issue_id not in selection.linear_issues:
            continue
        selected_linear.append(row)
        revision = _revision(
            row.get("projection_revision"),
            _revision(row.get("updated_at"), receipt["semantic_hash"]),
        )
        candidates.append(
            _candidate(
                priority=50,
                kind="projection",
                owner="linear",
                identity=f"linear:{issue_id}",
                revision=revision,
                ref=f"ctx://linear/{issue_id}@{revision}",
                reason="exact scoped portfolio projection",
            )
        )

    selected_executive: list[Mapping[str, Any]] = []
    for row in _rows(observations.get("executive"), "operations"):
        operation_key = row.get("operation_key")
        if operation_key not in selection.executive_operations:
            continue
        selected_executive.append(row)
        revision = _revision(
            row.get("payload_hash"),
            _revision(
                observations.get("executive", {}).get("grounding_sha"),
                receipt["semantic_hash"],
            ),
        )
        candidates.append(
            _candidate(
                priority=55,
                kind="execution_state",
                owner="executive",
                identity=f"executive:{operation_key}",
                revision=revision,
                ref=f"ctx://executive/{operation_key}@{revision}",
                reason="exact scoped execution operation",
            )
        )

    selected_slack: list[Mapping[str, Any]] = []
    for row in _rows(observations.get("slack"), "messages"):
        identity = (row.get("channel_id"), row.get("ts"))
        if identity not in selection.slack_messages:
            continue
        selected_slack.append(row)
        channel_id, timestamp = identity
        revision = _revision(row.get("payload_hash"), str(timestamp))
        candidates.append(
            _candidate(
                priority=70,
                kind="transport",
                owner="slack",
                identity=f"slack:{channel_id}:{timestamp}",
                revision=revision,
                ref=f"ctx://slack/{channel_id}/{timestamp}@{revision}",
                reason="exact operation transport evidence",
            )
        )

    findings = receipt.get("findings")
    if isinstance(findings, Sequence) and not isinstance(findings, (str, bytes)):
        severity_priority = {"FATAL": 20, "BLOCKING": 20, "WARNING": 25, "INFO": 30}
        for index, finding in enumerate(findings):
            if not isinstance(finding, Mapping):
                continue
            code = finding.get("code")
            subject = finding.get("subject")
            severity = finding.get("severity")
            if not isinstance(code, str) or not isinstance(subject, str):
                continue
            revision = _digest(finding)
            candidates.append(
                _candidate(
                    priority=severity_priority.get(str(severity), 30),
                    kind="reconciliation_finding",
                    owner=str(finding.get("canonical_owner") or "unknown"),
                    identity=f"finding:{code}:{subject}",
                    revision=revision,
                    ref=f"ctx://finding/{code}/{revision}",
                    reason=f"{severity or 'UNKNOWN'} cross-plane finding",
                )
            )

    source_digests = _selected_source_digests(
        receipt=receipt,
        selection=selection,
        selected_contexts=selected_contexts,
        selected_prs=selected_prs,
        selected_linear=selected_linear,
        selected_slack=selected_slack,
        selected_executive=selected_executive,
    )
    return candidates, source_digests


def _validate_prior_pack(prior_pack: object) -> Mapping[str, Any] | None:
    if prior_pack is None:
        return None
    if not isinstance(prior_pack, Mapping):
        raise ContextResolverError("prior pack must be an object")
    if prior_pack.get("schema") != CONTEXT_PACK_SCHEMA:
        raise ContextResolverError("prior pack schema is invalid")
    if (
        prior_pack.get("authoritative") is not False
        or prior_pack.get("derived_read_only") is not True
    ):
        raise ContextResolverError("prior pack authority boundary is invalid")
    return prior_pack


def _invalidators(
    prior: Mapping[str, Any] | None,
    current_items: Sequence[Mapping[str, Any]],
    current_sources: Mapping[str, str],
    task_digest: str,
) -> list[dict[str, Any]]:
    if prior is None:
        return []
    result: list[dict[str, Any]] = []
    if prior.get("task_digest") != task_digest:
        result.append(
            {
                "code": "TASK_CHANGED",
                "identity": "task",
                "owner": "caller",
                "before_revision": prior.get("task_digest"),
                "after_revision": task_digest,
            }
        )

    prior_sources = prior.get("selected_source_digests")
    if not isinstance(prior_sources, Mapping):
        prior_sources = {}
    for source in sorted(set(prior_sources) | set(current_sources)):
        before = prior_sources.get(source)
        after = current_sources.get(source)
        if before == after:
            continue
        result.append(
            {
                "code": "SELECTED_SOURCE_CHANGED",
                "identity": f"source:{source}",
                "owner": source,
                "before_revision": before,
                "after_revision": after,
            }
        )

    prior_items_raw = prior.get("selected_items")
    prior_items = (
        {
            item.get("identity"): item
            for item in prior_items_raw
            if isinstance(item, Mapping) and isinstance(item.get("identity"), str)
        }
        if isinstance(prior_items_raw, Sequence)
        and not isinstance(prior_items_raw, (str, bytes))
        else {}
    )
    current_by_id = {str(item["identity"]): item for item in current_items}

    for identity in sorted(set(prior_items) | set(current_by_id)):
        before = prior_items.get(identity)
        after = current_by_id.get(identity)
        if before is None:
            result.append(
                {
                    "code": "CONTEXT_ITEM_ADDED",
                    "identity": identity,
                    "owner": after.get("owner"),
                    "before_revision": None,
                    "after_revision": after.get("revision"),
                }
            )
            continue
        if after is None:
            result.append(
                {
                    "code": "CONTEXT_ITEM_REMOVED",
                    "identity": identity,
                    "owner": before.get("owner"),
                    "before_revision": before.get("revision"),
                    "after_revision": None,
                }
            )
            continue
        if before.get("revision") != after.get("revision"):
            result.append(
                {
                    "code": "CONTEXT_ITEM_CHANGED",
                    "identity": identity,
                    "owner": after.get("owner"),
                    "before_revision": before.get("revision"),
                    "after_revision": after.get("revision"),
                }
            )
    return result


def build_context_pack(
    receipt: Mapping[str, Any],
    *,
    task: str,
    prior_pack: Mapping[str, Any] | None = None,
    max_items: int = MAX_SELECTED_ITEMS,
) -> dict[str, Any]:
    """Build one bounded navigation pack from exact Session Truth scope.

    This function never fetches a source.  Source acquisition and authority remain with
    their existing owners.  Unrelated rows are excluded before the context budget is
    applied, and budget omissions remain explicit.
    """

    receipt = _validate_receipt(receipt)
    normalized_task = _task(task)
    prior_pack = _validate_prior_pack(prior_pack)
    if (
        type(max_items) is not int
        or isinstance(max_items, bool)
        or not 1 <= max_items <= MAX_SELECTED_ITEMS
    ):
        raise ContextResolverError("max_items is outside the closed bound")

    candidates, source_digests = _collect_candidates(receipt)
    deduped: dict[str, dict[str, Any]] = {}
    for item in candidates:
        identity = item["identity"]
        existing = deduped.get(identity)
        if existing is None or (item["priority"], item["ref"]) < (
            existing["priority"],
            existing["ref"],
        ):
            deduped[identity] = item
    ordered = sorted(
        deduped.values(),
        key=lambda item: (item["priority"], item["identity"], item["ref"]),
    )

    selected = ordered[:max_items]
    omitted = [item["identity"] for item in ordered[max_items:]]
    selected_public = [
        {key: value for key, value in item.items() if key != "priority"}
        for item in selected
    ]

    observations = receipt["observations"]
    admission = receipt.get("admission")
    degraded: list[str] = []
    if isinstance(admission, Mapping):
        for key in ("required_sources_unavailable", "optional_sources_unavailable"):
            value = admission.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                degraded.extend(f"{key}:{item}" for item in value)
    agentos = observations.get("agentos")
    if isinstance(agentos, Mapping):
        warnings = agentos.get("warnings")
        if isinstance(warnings, Sequence) and not isinstance(warnings, (str, bytes)):
            degraded.extend(
                f"agentos:{warning}" for warning in warnings if isinstance(warning, str)
            )

    task_digest = hashlib.sha256(normalized_task.encode("utf-8")).hexdigest()
    scope_digest = _digest(receipt["scope"])
    bundle_id = (
        "context-bundle:"
        + hashlib.sha256(f"{task_digest}:{scope_digest}".encode("ascii")).hexdigest()[
            :32
        ]
    )
    selected_revision = _digest(
        {
            "task_digest": task_digest,
            "scope_digest": source_digests["scope"],
            "selected_source_digests": source_digests,
        }
    )
    bundle_core = {
        "context_bundle_id": bundle_id,
        "revision": selected_revision,
        "selected_items": [item["ref"] for item in selected_public],
        "excluded": [],
        "omitted_due_to_budget": omitted,
        "degraded": sorted(set(degraded)),
    }
    context_digest = _digest(bundle_core)
    context_bundle = dict(bundle_core)
    context_bundle["context_digest"] = context_digest

    invalidators = _invalidators(
        prior_pack, selected_public, source_digests, task_digest
    )
    continuation_mode = (
        "FULL_RECOVERY"
        if prior_pack is None
        or any(item["code"] == "TASK_CHANGED" for item in invalidators)
        else "DELTA_RECOVERY"
    )
    pack = {
        "schema": CONTEXT_PACK_SCHEMA,
        "authoritative": False,
        "derived_read_only": True,
        "task": normalized_task,
        "task_digest": task_digest,
        "source_receipt_semantic_hash": receipt["semantic_hash"],
        "scope": receipt["scope"],
        "coverage": "partial" if omitted or degraded else "complete",
        "continuation_mode": continuation_mode,
        "material_change": bool(invalidators),
        "selected_source_digests": source_digests,
        "context_bundle": context_bundle,
        "selected_items": selected_public,
        "invalidators": invalidators,
    }
    if len(canonical_json(pack).encode("utf-8")) > MAX_PACK_BYTES:
        raise ContextResolverError("context pack exceeds byte bound")
    return pack


def render_context_pack(pack: Mapping[str, Any]) -> str:
    if not isinstance(pack, Mapping) or pack.get("schema") != CONTEXT_PACK_SCHEMA:
        raise ContextResolverError("context pack schema is invalid")
    selected = pack.get("selected_items")
    invalidators = pack.get("invalidators")
    if not isinstance(selected, Sequence) or isinstance(selected, (str, bytes)):
        raise ContextResolverError("context pack selected items are invalid")
    if not isinstance(invalidators, Sequence) or isinstance(invalidators, (str, bytes)):
        raise ContextResolverError("context pack invalidators are invalid")
    bundle = pack.get("context_bundle")
    if not isinstance(bundle, Mapping):
        raise ContextResolverError("context bundle is invalid")
    lines = [
        "Mastermind Context Pack",
        f"coverage: {pack.get('coverage')}",
        f"continuation_mode: {pack.get('continuation_mode')}",
        f"material_change: {'true' if pack.get('material_change') else 'false'}",
        f"context_bundle_id: {bundle.get('context_bundle_id')}",
        f"context_digest: {bundle.get('context_digest')}",
        f"selected_items: {len(selected)}",
        f"invalidators: {len(invalidators)}",
    ]
    for item in selected:
        if isinstance(item, Mapping):
            lines.append(
                f"- {item.get('kind')} {item.get('identity')} -> {item.get('ref')}"
            )
    if invalidators:
        lines.append("material_invalidators:")
        for item in invalidators:
            if isinstance(item, Mapping):
                lines.append(f"- {item.get('code')} {item.get('identity')}")
    return "\n".join(lines) + "\n"
