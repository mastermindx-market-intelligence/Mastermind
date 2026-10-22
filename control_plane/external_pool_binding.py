"""Prepare one hash-pinned route qualification receipt as registration identity facts.

This module is pure and fail-closed. It combines exactly one of four closed,
SHA-256-pinned bounded-route qualification receipts with explicit canonical
owner inputs, and returns immutable prepared facts: existing Worker/Quota
registration descriptors, a :class:`CapacityJoin` and a reviewed
:class:`AdapterDescriptor` reference.

It deliberately makes no decision the existing owners already make: no routing,
transport, registry, admission, availability, ranking, retry, enrollment or
lifecycle decision. It never opens a Runtime/store, never calls a pool command
and never registers anything. Registration is the caller's own effect, made with
an explicit status the caller chooses and owns.

Receipt success or cleanup proves a past bounded route only; it never asserts
current capacity. Served model and billed usage remain unattested.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from control_plane.executive_agent_capabilities import CapabilityPolicyError
from control_plane.executive_capacity_join import (
    JOIN_SCHEMA,
    PROVIDER_CAPACITY_SCHEMA,
    CapacityJoin,
    CapacityJoinError,
    validate_capacity_join,
)
from control_plane.executive_host_pressure import HOST_REF_RE
from control_plane.executive_runtime import (
    StateConflict,
    WorkerStatus,
    _WORKER_ID_RE,
    _quota_specifications,
)
from control_plane.model_router import (
    ModelAlias,
    ModelRouter,
    RoutingPolicyError,
)
from control_plane.worker_adapter import (
    AdapterBindingError,
    AdapterDescriptor,
    adapter_descriptor,
    bind_reviewed_adapter,
)

MAX_RECEIPT_BYTES = 65_536
MAX_CAPABILITIES = 16
EXECUTE_ROLE = "execute"
OPERATOR_ROLE = "operator"
_ACCEPTED_RECEIPT_STATE = "BOUNDED_ROUTE_ACCEPTED"
_TERMINAL_SCHEMA = "mastermind.native.remote-terminal.v1"
_CODEX_NATIVE_MODE = "codex-native"
_CODEX_CLI_ADAPTER_ID = "codex-cli"

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_CANONICAL_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_ROLES = frozenset({EXECUTE_ROLE, OPERATOR_ROLE})


class PoolBindingRefusal(ValueError):
    """A closed preparation refusal; raw validator errors are never projected."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _refuse(code: str) -> None:
    raise PoolBindingRefusal(code)


def _text(value: object, code: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _refuse(code)
    return value


def _canonical(value: object, field: str) -> str:
    return _text(value, f"OWNER_{field.upper()}_INVALID", _CANONICAL_TOKEN_RE)


def _digest(value: object, field: str) -> str:
    return _text(value, f"OWNER_{field.upper()}_INVALID", _DIGEST_RE)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _detach(value: Any) -> Any:
    """Fresh mutable copy of one frozen prepared structure, never a shared alias."""

    if isinstance(value, Mapping):
        return {str(key): _detach(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_detach(item) for item in value]
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class RouteQualificationEvidence:
    """Pinned bounded-route facts only: hash, run, mode, host and requested model."""

    evidence_sha256: str
    run_id: str
    mode: str
    host: str
    requested_model: str

    def __post_init__(self) -> None:
        _text(self.evidence_sha256, "EVIDENCE_HASH_INVALID", _DIGEST_RE)
        _text(self.run_id, "EVIDENCE_RUN_INVALID", _TOKEN_RE)
        _text(self.mode, "EVIDENCE_MODE_INVALID", _TOKEN_RE)
        _text(self.host, "EVIDENCE_HOST_INVALID", _TOKEN_RE)
        _text(self.requested_model, "EVIDENCE_MODEL_INVALID", _TOKEN_RE)

    def to_dict(self) -> dict[str, str]:
        return _detach(dataclasses.asdict(self))


_PINNED_ROUTES: Mapping[str, tuple[RouteQualificationEvidence, str]] = MappingProxyType(
    {
        # Embedded evidence facts, not a routing registry: the only receipts this
        # preparation accepts. There is no caller-supplied replacement set.
        "704c901e08dcca99169be588d6f578b516b673994c28ceec1c96c3d244798066": (
            RouteQualificationEvidence(
                evidence_sha256="704c901e08dcca99169be588d6f578b516b673994c28ceec1c96c3d244798066",
                run_id="rs_20260929T063139Z_52100",
                mode="grok",
                host="ubuntu2",
                requested_model="grok-4.6",
            ),
            OPERATOR_ROLE,
        ),
        "94c35a335b79c8167feef1284d0c436659ccbce98ae3ce777b31289d182cee54": (
            RouteQualificationEvidence(
                evidence_sha256="94c35a335b79c8167feef1284d0c436659ccbce98ae3ce777b31289d182cee54",
                run_id="rs_20260929T065559Z_48026",
                mode="cursor",
                host="ubuntu1",
                requested_model="composer-2.5",
            ),
            OPERATOR_ROLE,
        ),
        "e184530a3ab6b86cb78145e485cc007a0fb134403d5203629f0aeeae3aaaa62a": (
            RouteQualificationEvidence(
                evidence_sha256="e184530a3ab6b86cb78145e485cc007a0fb134403d5203629f0aeeae3aaaa62a",
                run_id="rs_20260929T065623Z_48949",
                mode="oc-free",
                host="ubuntu1",
                requested_model="mimo-v2.5-free",
            ),
            EXECUTE_ROLE,
        ),
        "38c832a5302edfc8f68e85c00e77a1170310fba6db579c8d51075db7b676bc77": (
            RouteQualificationEvidence(
                evidence_sha256="38c832a5302edfc8f68e85c00e77a1170310fba6db579c8d51075db7b676bc77",
                run_id="rs_20260929T070048Z_59320",
                mode=_CODEX_NATIVE_MODE,
                host="mb",
                requested_model="gpt-6-sol",
            ),
            OPERATOR_ROLE,
        ),
    }
)


def _pinned_receipt(receipt: object) -> tuple[RouteQualificationEvidence, str]:
    if type(receipt) is not bytes or not 0 < len(receipt) <= MAX_RECEIPT_BYTES:
        _refuse("RECEIPT_BYTES_INVALID")
    pinned = _PINNED_ROUTES.get(hashlib.sha256(receipt).hexdigest())
    if pinned is None:
        # Covers altered, truncated, re-encoded and unregistered receipts: a
        # semantically equal but re-serialised document is still not pinned.
        _refuse("RECEIPT_UNPINNED")
    return pinned


def _verify_pinned_document(
    document: object, pinned: tuple[RouteQualificationEvidence, str]
) -> None:
    """Re-check the accepted bytes against the nested terminal identity."""

    evidence, _role = pinned
    if type(document) is not dict:
        _refuse("RECEIPT_MALFORMED")
    terminal = document.get("terminal")
    if type(terminal) is not dict:
        _refuse("RECEIPT_TERMINAL_MALFORMED")
    for field, expected in (
        ("host", evidence.host),
        ("requested_model", evidence.requested_model),
        ("run_id", evidence.run_id),
    ):
        if document.get(field) != expected:
            _refuse("RECEIPT_FACT_MISMATCH")
    # The accepted Grok receipt carries its mode only in the terminal record.
    if "mode" in document and document["mode"] != evidence.mode:
        _refuse("RECEIPT_FACT_MISMATCH")
    for field, expected in (
        ("host", evidence.host),
        ("mode", evidence.mode),
        ("model", evidence.requested_model),
        ("run_id", evidence.run_id),
        ("schema", _TERMINAL_SCHEMA),
    ):
        if terminal.get(field) != expected:
            _refuse("RECEIPT_TERMINAL_IDENTITY_MISMATCH")
    if "state" in document and document["state"] != _ACCEPTED_RECEIPT_STATE:
        _refuse("RECEIPT_STATE_UNACCEPTED")


def _read_receipt(receipt: object) -> tuple[RouteQualificationEvidence, str]:
    pinned = _pinned_receipt(receipt)
    try:
        document = json.loads(bytes(receipt).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise PoolBindingRefusal("RECEIPT_MALFORMED") from None
    _verify_pinned_document(document, pinned)
    return pinned


@dataclasses.dataclass(frozen=True, slots=True)
class PoolBindingOwnerInputs:
    """Explicit canonical owner facts. Nothing is inferred from a host nickname."""

    worker_id: str
    quota_class: str
    account_label: str
    provider: str
    model_alias: str
    model: str
    adapter_id: str
    routing_policy_version: str
    execution_profile_id: str
    execution_profile_digest: str
    capability_policy_version: str
    capability_policy_digest: str
    effort: str
    cost_class: str
    role: str
    host_alias: str
    host_ref: str
    capacity_capability_id: str
    worker_source_config_digest: str
    capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        # The existing Worker registration grammar, including its 64-character cap.
        _text(self.worker_id, "OWNER_WORKER_ID_INVALID", _WORKER_ID_RE)
        _canonical(self.quota_class, "quota_class")
        _text(self.quota_class, "OWNER_QUOTA_CLASS_INVALID", _WORKER_ID_RE)
        _text(self.account_label, "OWNER_ACCOUNT_LABEL_INVALID", _TOKEN_RE)
        _canonical(self.provider, "provider")
        _canonical(self.model_alias, "model_alias")
        _canonical(self.model, "model")
        _canonical(self.adapter_id, "adapter_id")
        _canonical(self.routing_policy_version, "routing_policy_version")
        _canonical(self.execution_profile_id, "execution_profile_id")
        _digest(self.execution_profile_digest, "execution_profile_digest")
        _canonical(self.capability_policy_version, "capability_policy_version")
        _digest(self.capability_policy_digest, "capability_policy_digest")
        _canonical(self.effort, "effort")
        _canonical(self.cost_class, "cost_class")
        if type(self.role) is not str or self.role not in _ROLES:
            _refuse("OWNER_ROLE_INVALID")
        _text(self.host_alias, "OWNER_HOST_ALIAS_INVALID", _TOKEN_RE)
        _text(self.host_ref, "OWNER_HOST_REF_INVALID", HOST_REF_RE)
        _canonical(self.capacity_capability_id, "capacity_capability_id")
        _digest(self.worker_source_config_digest, "worker_source_config_digest")
        capabilities = self.capabilities
        if type(capabilities) is not tuple or not 1 <= len(capabilities) <= MAX_CAPABILITIES:
            _refuse("OWNER_CAPABILITIES_INVALID")
        for capability in capabilities:
            _canonical(capability, "capabilities")
        if list(capabilities) != sorted(set(capabilities)):
            _refuse("OWNER_CAPABILITIES_NOT_CANONICAL")


def _pin_agreement(pinned: tuple[RouteQualificationEvidence, str], owner: PoolBindingOwnerInputs) -> None:
    evidence, role = pinned
    if owner.role != role:
        # An operator-qualified receipt is never a build/execute receipt under a
        # renamed alias, and vice versa.
        _refuse("ROLE_NOT_PINNED")
    if owner.host_alias != evidence.host:
        _refuse("HOST_ALIAS_MISMATCH")
    if owner.model != evidence.requested_model:
        _refuse("QUALIFIED_MODEL_MISMATCH")
    if evidence.mode == _CODEX_NATIVE_MODE:
        if owner.adapter_id != _CODEX_CLI_ADAPTER_ID:
            _refuse("MODE_ADAPTER_MISMATCH")
    elif owner.adapter_id == _CODEX_CLI_ADAPTER_ID:
        _refuse("MODE_ADAPTER_MISMATCH")


def _review_adapter(adapter_id: str) -> AdapterDescriptor:
    try:
        descriptor = adapter_descriptor(adapter_id)
    except ValueError:
        _refuse("ADAPTER_UNKNOWN")
    if descriptor.implemented is not True or not descriptor.implementation:
        # Unarmed external seams stay refused under current canonical source.
        _refuse("ADAPTER_NOT_IMPLEMENTED")
    return descriptor


def _route_agreement(
    router: ModelRouter, owner: PoolBindingOwnerInputs
) -> ModelAlias:
    registry = router.capability_registry
    try:
        alias = router.resolve_model_alias(owner.model_alias)
    except (RoutingPolicyError, TypeError):
        _refuse("MODEL_ALIAS_NOT_WORKER_ELIGIBLE")
    provider = router.providers.get(owner.provider)
    if provider is None or provider.enabled is not True or provider.autonomous_allowed is not True:
        _refuse("PROVIDER_NOT_ENABLED")
    try:
        profile = registry.resolve(owner.execution_profile_id)
    except (CapabilityPolicyError, TypeError):
        _refuse("EXECUTION_PROFILE_UNRESOLVED")
    if profile.enabled is not True:
        _refuse("EXECUTION_PROFILE_DISABLED")
    agreements = (
        (provider.provider_alias, owner.provider, "PROVIDER_MISMATCH"),
        (provider.adapter_id, owner.adapter_id, "ADAPTER_MISMATCH"),
        (alias.model_alias, owner.model_alias, "MODEL_ALIAS_MISMATCH"),
        (alias.provider_alias, owner.provider, "PROVIDER_MISMATCH"),
        (alias.adapter_id, owner.adapter_id, "ADAPTER_MISMATCH"),
        (alias.model, owner.model, "MODEL_MISMATCH"),
        (alias.effort, owner.effort, "EFFORT_MISMATCH"),
        (alias.cost_class, owner.cost_class, "COST_CLASS_MISMATCH"),
        (alias.execution_profile_id, owner.execution_profile_id, "EXECUTION_PROFILE_ID_MISMATCH"),
        (alias.execution_profile_digest, owner.execution_profile_digest, "EXECUTION_PROFILE_DIGEST_MISMATCH"),
        (alias.capability_policy_version, owner.capability_policy_version, "CAPABILITY_POLICY_VERSION_MISMATCH"),
        (alias.capability_policy_digest, owner.capability_policy_digest, "CAPABILITY_POLICY_DIGEST_MISMATCH"),
        (profile.profile_digest, owner.execution_profile_digest, "EXECUTION_PROFILE_DIGEST_MISMATCH"),
        (profile.profile_id, owner.execution_profile_id, "EXECUTION_PROFILE_ID_MISMATCH"),
        (registry.policy_version, owner.capability_policy_version, "CAPABILITY_POLICY_VERSION_MISMATCH"),
        (registry.policy_digest, owner.capability_policy_digest, "CAPABILITY_POLICY_DIGEST_MISMATCH"),
        (router.policy_version, owner.routing_policy_version, "ROUTING_POLICY_VERSION_MISMATCH"),
    )
    for expected, supplied, code in agreements:
        if expected != supplied:
            _refuse(code)
    if not set(owner.capabilities).issubset(alias.capabilities):
        _refuse("CAPABILITY_WIDENED")
    return alias


def _capacity_join(owner: PoolBindingOwnerInputs) -> CapacityJoin:
    try:
        return validate_capacity_join(
            {
                "schema": JOIN_SCHEMA,
                "host_ref": owner.host_ref,
                "capacity_capability_id": owner.capacity_capability_id,
                "provider_capacity_schema": PROVIDER_CAPACITY_SCHEMA,
                "worker_source_config_digest": owner.worker_source_config_digest,
            }
        )
    except (CapacityJoinError, TypeError):
        _refuse("CAPACITY_JOIN_INVALID")


def _quota_registration(
    owner: PoolBindingOwnerInputs, metadata: Mapping[str, Any]
) -> Mapping[str, Any]:
    declared = {
        "capabilities": list(owner.capabilities),
        "provider": owner.provider,
        "model": owner.model,
        "effort": owner.effort,
        "cost_class": owner.cost_class,
        "metadata": _detach(metadata),
    }
    try:
        specifications = _quota_specifications(
            owner.provider, list(owner.capabilities), {owner.quota_class: declared}
        )
    except StateConflict:
        _refuse("QUOTA_SPECIFICATION_INVALID")
    specification = specifications.get(owner.quota_class)
    if specification is None or _detach(specification) != declared:
        # The existing validator normalises; drift is a refusal, not a rewrite.
        _refuse("QUOTA_SPECIFICATION_DRIFT")
    return _freeze(specification)


@dataclasses.dataclass(frozen=True, slots=True)
class ExternalPoolBinding:
    """Validated immutable identity facts. Carries no availability or state."""

    owner: PoolBindingOwnerInputs
    evidence: RouteQualificationEvidence
    adapter: AdapterDescriptor
    capacity_join: CapacityJoin
    metadata: Mapping[str, Any]
    quota_registration: Mapping[str, Any]

    @staticmethod
    def _require_status(status: object) -> WorkerStatus:
        if type(status) not in (str, WorkerStatus):
            _refuse("STATUS_REQUIRED")
        try:
            worker_status = WorkerStatus(status)
        except ValueError:
            _refuse("STATUS_UNSUPPORTED")
        if worker_status is WorkerStatus.BUSY:
            _refuse("STATUS_BUSY_FORBIDDEN")
        return worker_status

    def registration_kwargs(self, *, status: WorkerStatus | str) -> dict[str, dict[str, Any]]:
        """Fresh detached kwargs for the existing registration APIs.

        Nothing is registered here and no default status exists: a caller
        choosing an explicit status owns that subsequent effect. BUSY is
        refused because it requires an assigned Attempt, which is not this
        module's decision.
        """

        worker_status = self._require_status(status)
        owner = self.owner
        capabilities = list(owner.capabilities)
        quota = self.quota_registration
        return {
            "worker": {
                "worker_id": owner.worker_id,
                "provider": owner.provider,
                "account_label": owner.account_label,
                "worker_type": self.adapter.adapter_id,
                "capabilities": list(capabilities),
                "quota_classes": {
                    owner.quota_class: {
                        "capabilities": list(quota["capabilities"]),
                        "provider": quota["provider"],
                        "model": quota["model"],
                        "effort": quota["effort"],
                        "cost_class": quota["cost_class"],
                        "metadata": _detach(quota["metadata"]),
                    }
                },
                "status": worker_status,
                "metadata": {},
            },
            "quota": {
                "worker_id": owner.worker_id,
                "quota_class": owner.quota_class,
                "provider": quota["provider"],
                "model": quota["model"],
                "effort": quota["effort"],
                "cost_class": quota["cost_class"],
                "capabilities": list(quota["capabilities"]),
                "metadata": _detach(quota["metadata"]),
                "status": worker_status,
            },
        }


def prepare_pool_binding(
    receipt: bytes,
    *,
    owner: PoolBindingOwnerInputs,
    router: ModelRouter,
    adapter: object,
) -> ExternalPoolBinding:
    """Prepare one pinned receipt plus canonical owner inputs. Side-effect free.

    ``adapter`` must be an actual caller-constructed reviewed adapter instance;
    it is bound for identity, never constructed, started or status-called here.
    """

    if type(owner) is not PoolBindingOwnerInputs:
        _refuse("OWNER_INPUTS_REQUIRED")
    if type(router) is not ModelRouter:
        _refuse("MODEL_ROUTER_REQUIRED")
    pinned = _read_receipt(receipt)
    _pin_agreement(pinned, owner)
    reviewed_adapter = _review_adapter(owner.adapter_id)
    _route_agreement(router, owner)
    try:
        bound = bind_reviewed_adapter(adapter, owner.adapter_id)
    except (AdapterBindingError, ValueError):
        _refuse("ADAPTER_NOT_REVIEWED")
    if bound.adapter_id != owner.adapter_id or bound.implemented is not True:
        _refuse("ADAPTER_MISMATCH")
    join = _capacity_join(owner)
    metadata = _freeze(
        {
            "model_alias": owner.model_alias,
            "routing_policy_version": owner.routing_policy_version,
            "execution_profile_id": owner.execution_profile_id,
            "execution_profile_digest": owner.execution_profile_digest,
            "capability_policy_version": owner.capability_policy_version,
            "capability_policy_digest": owner.capability_policy_digest,
            "capacity_join": join.to_dict(),
            # Provenance only: a past bounded route, never current capacity.
            "route_qualification_evidence_sha256": pinned[0].evidence_sha256,
            "qualified_route_role": owner.role,
            "qualified_route_mode": pinned[0].mode,
        }
    )
    quota_registration = _quota_registration(owner, metadata)
    return ExternalPoolBinding(
        owner=owner,
        evidence=pinned[0],
        adapter=reviewed_adapter,
        capacity_join=join,
        metadata=metadata,
        quota_registration=quota_registration,
    )


__all__ = [
    "EXECUTE_ROLE",
    "ExternalPoolBinding",
    "MAX_CAPABILITIES",
    "MAX_RECEIPT_BYTES",
    "OPERATOR_ROLE",
    "PoolBindingOwnerInputs",
    "PoolBindingRefusal",
    "RouteQualificationEvidence",
    "prepare_pool_binding",
]
