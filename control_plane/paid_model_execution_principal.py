"""Closed pure-DATA validators for the paid model-only execution principal.

The helpers are strict, detached and inert.  They accept only exact plain
``dict`` DATA, normalize it against the canonical paid sealed-input contract
and return freshly built detached structures.  They perform no host lookup,
filesystem access, provider call, lease check or database write, and they
mint no authority: validated DATA is a normalized claim, not authorization.

The actual Control peer, Runtime pin, current Capacity claim and paid lease
owner must independently authorize consumption of any described execution.
An attestation digest records bytes at build time; a matching digest never
proves origin by itself.  No ``verified`` boolean is accepted or produced,
and no provider home, provider session or secret canary field exists here.
"""
from __future__ import annotations

import re

try:  # canonical repository layout
    from control_plane.paid_model_execution_contract import (
        ADAPTER_ID,
        ATTESTATION_SCHEMA,
        EXECUTION_SURFACE,
        MODELS,
        POLICY,
        PROFILE_ID,
        _DIGEST,
        _ID,
        digest as _contract_digest,
    )
except ImportError:  # flat import layout fallback
    from paid_model_execution_contract import (
        ADAPTER_ID,
        ATTESTATION_SCHEMA,
        EXECUTION_SURFACE,
        MODELS,
        POLICY,
        PROFILE_ID,
        _DIGEST,
        _ID,
        digest as _contract_digest,
    )

try:  # canonical repository layout
    from control_plane.executive_orchestration_principal import (
        OrchestrationPrincipalError as _PlacementError,
        validate_placement_snapshot as _validate_placement_snapshot,
    )
except ImportError:  # flat import layout fallback
    from executive_orchestration_principal import (
        OrchestrationPrincipalError as _PlacementError,
        validate_placement_snapshot as _validate_placement_snapshot,
    )


PRINCIPAL_SCHEMA = "mastermind.paid_model_execution_principal/v1"
PRINCIPAL_KIND = "PAID_MODEL_ONLY"

PROVIDER = "glm"
POOLS = frozenset({"glm", "glm-frontier"})

_MAX_INT = 2 ** 63 - 1
_MAX_TEXT_BYTES = 512

# OS principal names arrive either in the contract identifier shape or in
# the existing placement evidence shape; both closed forms are accepted.
_OS_USER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}\Z")

_BINDING_KEYS = frozenset(
    {"root_id", "job_id", "attempt_id", "effective_grant_digest", "commission_sha256"}
)
_ROUTE_KEYS = frozenset({"provider", "host_ref", "model", "parent_job_id"})
_PROCESS_KEYS = frozenset(
    {
        "pid",
        "pgid",
        "session_id",
        "start_identity",
        "boot_id",
        "observed_user",
        "effective_uid",
        "effective_gid",
        "real_uid",
        "real_gid",
        "launch_nonce",
    }
)
_CONTROLLER_KEYS = frozenset({"pid", "start_identity", "boot_id"})
_LEASE_KEYS = frozenset(
    {
        "lease_id",
        "orchestrator_id",
        "pool",
        "account",
        "host_ref",
        "model",
        "controller_process",
        "runtime_fence_generation",
        "runtime_pin_version",
    }
)
_EVIDENCE_ORDER = (
    "python_sha256",
    "source_manifest_sha256",
    "policy_sha256",
    "prompt_sha256",
    "request_body_sha256",
    "result_schema_sha256",
    "capsule_binding_sha256",
    "physical_binding_sha256",
    "pin_identity_sha256",
    "capture_contract_sha256",
    "control_input_isolation_manifest_sha256",
)
_EVIDENCE_KEYS = frozenset(_EVIDENCE_ORDER)
_ATTESTATION_KEYS = frozenset(
    {
        "schema_version",
        "profile_id",
        "adapter_id",
        "execution_surface",
        "binding",
        "paid_route",
        "worker_id",
        "quota_class",
        "process_identity",
        "lease_binding",
        "evidence",
    }
)
_PRINCIPAL_KEYS = frozenset(
    {
        "schema_version",
        "principal_kind",
        "profile_id",
        "adapter_id",
        "execution_surface",
        "binding",
        "attempt_id",
        "worker_id",
        "quota_class",
        "provider",
        "account_label",
        "placement_snapshot_digest",
        "host_ref",
        "model",
        "os_principal_name",
        "os_principal_uid",
        "process_identity",
        "lease_binding",
        "paid_route",
        "attestation_sha256",
        "evidence",
    }
)


class PaidModelPrincipalRefused(ValueError):
    """The supplied paid-model DATA is not the closed canonical wire form."""


def _refused(reason: str):
    raise PaidModelPrincipalRefused(f"paid_model_principal_refused: {reason}")


def _exact_dict(value, *, name, keys):
    if (type(value) is not dict or any(type(key) is not str for key in value)
            or set(value) != keys):
        _refused(f"{name} must be an exact closed dict")
    return value


def _identifier(value, *, name):
    if type(value) is not str or _ID.fullmatch(value) is None:
        _refused(f"{name} must be a bounded identifier")
    return value


def _os_principal_text(value, *, name):
    if type(value) is not str or (
        _ID.fullmatch(value) is None and _OS_USER.fullmatch(value) is None
    ):
        _refused(f"{name} must be a bounded os principal name")
    return value


def _digest_text(value, *, name):
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        _refused(f"{name} must be a lowercase sha-256 digest")
    return value


def _bounded_text(value, *, name):
    if type(value) is not str or not value or value != value.strip():
        _refused(f"{name} must be non-empty trimmed text")
    if "\x00" in value:
        _refused(f"{name} must not contain NUL")
    try:
        length = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        _refused(f"{name} must be UTF-8 text")
    if length > _MAX_TEXT_BYTES:
        _refused(f"{name} exceeds its text bound")
    return value


def _bounded_int(value, *, name, minimum):
    if type(value) is not int or not minimum <= value <= _MAX_INT:
        _refused(f"{name} must be an in-range non-boolean integer")
    return value


def _validate_binding(value, *, name="binding"):
    raw = _exact_dict(value, name=name, keys=_BINDING_KEYS)
    return {
        "root_id": _identifier(raw["root_id"], name=f"{name}.root_id"),
        "job_id": _identifier(raw["job_id"], name=f"{name}.job_id"),
        "attempt_id": _identifier(raw["attempt_id"], name=f"{name}.attempt_id"),
        "effective_grant_digest": _digest_text(
            raw["effective_grant_digest"], name=f"{name}.effective_grant_digest"
        ),
        "commission_sha256": _digest_text(
            raw["commission_sha256"], name=f"{name}.commission_sha256"
        ),
    }


def _validate_route(value, *, binding=None, name="paid_route"):
    raw = _exact_dict(value, name=name, keys=_ROUTE_KEYS)
    provider = _identifier(raw["provider"], name=f"{name}.provider")
    if provider != PROVIDER:
        _refused(f"{name}.provider is not the paid provider")
    model = _identifier(raw["model"], name=f"{name}.model")
    if model not in MODELS:
        _refused(f"{name}.model is not a paid model")
    host_ref = _identifier(raw["host_ref"], name=f"{name}.host_ref")
    parent = raw["parent_job_id"]
    if parent is None:
        if binding is not None and binding["job_id"] != binding["root_id"]:
            _refused(f"{name}.parent_job_id is required off the root job")
        resolved_parent = None
    else:
        resolved_parent = _identifier(parent, name=f"{name}.parent_job_id")
        if binding is not None and resolved_parent == binding["job_id"]:
            _refused(f"{name}.parent_job_id must not be the bound job")
    return {
        "provider": provider,
        "host_ref": host_ref,
        "model": model,
        "parent_job_id": resolved_parent,
    }


def _validate_process_identity(value, *, name="process_identity"):
    raw = _exact_dict(value, name=name, keys=_PROCESS_KEYS)
    effective_uid = _bounded_int(
        raw["effective_uid"], name=f"{name}.effective_uid", minimum=0
    )
    effective_gid = _bounded_int(
        raw["effective_gid"], name=f"{name}.effective_gid", minimum=0
    )
    real_uid = _bounded_int(raw["real_uid"], name=f"{name}.real_uid", minimum=0)
    real_gid = _bounded_int(raw["real_gid"], name=f"{name}.real_gid", minimum=0)
    if real_uid != effective_uid or real_gid != effective_gid:
        _refused(f"{name} must describe a non-elevated paid runner")
    return {
        "pid": _bounded_int(raw["pid"], name=f"{name}.pid", minimum=1),
        "pgid": _bounded_int(raw["pgid"], name=f"{name}.pgid", minimum=1),
        "session_id": _bounded_int(
            raw["session_id"], name=f"{name}.session_id", minimum=1
        ),
        "start_identity": _bounded_text(
            raw["start_identity"], name=f"{name}.start_identity"
        ),
        "boot_id": _bounded_text(raw["boot_id"], name=f"{name}.boot_id"),
        "observed_user": _os_principal_text(
            raw["observed_user"], name=f"{name}.observed_user"
        ),
        "effective_uid": effective_uid,
        "effective_gid": effective_gid,
        "real_uid": real_uid,
        "real_gid": real_gid,
        "launch_nonce": _identifier(raw["launch_nonce"], name=f"{name}.launch_nonce"),
    }


def _validate_controller_process(value, *, name="controller_process"):
    raw = _exact_dict(value, name=name, keys=_CONTROLLER_KEYS)
    return {
        "pid": _bounded_int(raw["pid"], name=f"{name}.pid", minimum=1),
        "start_identity": _bounded_text(
            raw["start_identity"], name=f"{name}.start_identity"
        ),
        "boot_id": _bounded_text(raw["boot_id"], name=f"{name}.boot_id"),
    }


def _validate_lease_binding(value, *, route=None, name="lease_binding"):
    raw = _exact_dict(value, name=name, keys=_LEASE_KEYS)
    pool = _identifier(raw["pool"], name=f"{name}.pool")
    if pool not in POOLS:
        _refused(f"{name}.pool is not a paid pool")
    model = _identifier(raw["model"], name=f"{name}.model")
    if model not in MODELS:
        _refused(f"{name}.model is not a paid model")
    host_ref = _identifier(raw["host_ref"], name=f"{name}.host_ref")
    if route is not None and (host_ref != route["host_ref"] or model != route["model"]):
        _refused(f"{name} host/model must agree with the paid route")
    return {
        "lease_id": _identifier(raw["lease_id"], name=f"{name}.lease_id"),
        "orchestrator_id": _identifier(
            raw["orchestrator_id"], name=f"{name}.orchestrator_id"
        ),
        "pool": pool,
        "account": _identifier(raw["account"], name=f"{name}.account"),
        "host_ref": host_ref,
        "model": model,
        "controller_process": _validate_controller_process(
            raw["controller_process"], name=f"{name}.controller_process"
        ),
        "runtime_fence_generation": _bounded_int(
            raw["runtime_fence_generation"],
            name=f"{name}.runtime_fence_generation",
            minimum=1,
        ),
        "runtime_pin_version": _bounded_int(
            raw["runtime_pin_version"], name=f"{name}.runtime_pin_version", minimum=1
        ),
    }


def _validate_evidence(value, *, name="evidence"):
    raw = _exact_dict(value, name=name, keys=_EVIDENCE_KEYS)
    evidence = {
        key: _digest_text(raw[key], name=f"{name}.{key}") for key in _EVIDENCE_ORDER
    }
    if evidence["policy_sha256"] != _contract_digest(POLICY):
        _refused(f"{name}.policy_sha256 does not match the paid policy")
    return evidence


def _validate_expected_evidence(value):
    return _validate_evidence(value, name="expected_evidence")


def _apply_expectations(attestation, expectations):
    if expectations["binding"] is not None:
        expected = _validate_binding(expectations["binding"], name="expected_binding")
        if expected != attestation["binding"]:
            _refused("binding does not match expected_binding")
    if expectations["route"] is not None:
        expected = _validate_route(expectations["route"], name="expected_paid_route")
        if expected != attestation["paid_route"]:
            _refused("paid_route does not match expected_route")
    if expectations["worker_id"] is not None:
        expected = _identifier(expectations["worker_id"], name="expected_worker_id")
        if expected != attestation["worker_id"]:
            _refused("worker_id does not match expected_worker_id")
    if expectations["quota_class"] is not None:
        expected = _identifier(
            expectations["quota_class"], name="expected_quota_class"
        )
        if expected != attestation["quota_class"]:
            _refused("quota_class does not match expected_quota_class")
    if expectations["process"] is not None:
        expected = _validate_process_identity(
            expectations["process"], name="expected_process"
        )
        if expected != attestation["process_identity"]:
            _refused("process_identity does not match expected_process")
    if expectations["lease_binding"] is not None:
        expected = _validate_lease_binding(
            expectations["lease_binding"], name="expected_lease_binding"
        )
        if expected != attestation["lease_binding"]:
            _refused("lease_binding does not match expected_lease_binding")
    if expectations["evidence"] is not None:
        expected = _validate_expected_evidence(expectations["evidence"])
        for key, digest_value in expected.items():
            if attestation["evidence"][key] != digest_value:
                _refused(f"evidence.{key} does not match expected_evidence")


def _normalized_attestation(value, *, expectations):
    raw = _exact_dict(value, name="attestation", keys=_ATTESTATION_KEYS)
    if type(raw["schema_version"]) is not str or raw["schema_version"] != ATTESTATION_SCHEMA:
        _refused("attestation.schema_version is not the paid launch attestation schema")
    if type(raw["profile_id"]) is not str or raw["profile_id"] != PROFILE_ID:
        _refused("attestation.profile_id is not the paid profile")
    if type(raw["adapter_id"]) is not str or raw["adapter_id"] != ADAPTER_ID:
        _refused("attestation.adapter_id is not the paid adapter")
    if type(raw["execution_surface"]) is not str or raw["execution_surface"] != EXECUTION_SURFACE:
        _refused("attestation.execution_surface is not the paid execution surface")
    binding = _validate_binding(raw["binding"])
    route = _validate_route(raw["paid_route"], binding=binding)
    process = _validate_process_identity(raw["process_identity"])
    lease = _validate_lease_binding(raw["lease_binding"], route=route)
    evidence = _validate_evidence(raw["evidence"])
    attestation = {
        "schema_version": ATTESTATION_SCHEMA,
        "profile_id": PROFILE_ID,
        "adapter_id": ADAPTER_ID,
        "execution_surface": EXECUTION_SURFACE,
        "binding": binding,
        "paid_route": route,
        "worker_id": _identifier(raw["worker_id"], name="worker_id"),
        "quota_class": _identifier(raw["quota_class"], name="quota_class"),
        "process_identity": process,
        "lease_binding": lease,
        "evidence": evidence,
    }
    _apply_expectations(attestation, expectations)
    return attestation


def validate_paid_model_attestation(
    value,
    *,
    expected_binding,
    expected_route,
    expected_worker_id,
    expected_quota_class,
    expected_process,
    expected_lease_binding,
    expected_evidence,
):
    """Normalize one paid launch attestation, or raise.

    The attestation must be the exact closed DATA shape of the canonical paid
    sealed-input surface; no supplied ``verified`` boolean or extra authority
    field is accepted.  All owner expectations are required, strictly normalized,
    and compared for exact equality against the attested source.  This is DATA validation only: a returned attestation grants
    nothing and authenticates no observation.
    """
    if any(item is None for item in (
        expected_binding, expected_route, expected_worker_id, expected_quota_class,
        expected_process, expected_lease_binding, expected_evidence,
    )):
        _refused("all actual owner expectations are required")
    return _normalized_attestation(
        value,
        expectations={
            "binding": expected_binding,
            "route": expected_route,
            "worker_id": expected_worker_id,
            "quota_class": expected_quota_class,
            "process": expected_process,
            "lease_binding": expected_lease_binding,
            "evidence": expected_evidence,
        },
    )


def build_paid_model_principal(attestation, placement_snapshot, attempt_id):
    """Build the strict detached paid model-only principal DATA, or raise.

    The supplied attestation is structurally validated even when no external
    expectation is available, the placement snapshot is validated through the
    owning placement validator, and the common placement, route and lease
    fields are cross-checked.  This pure builder does not authenticate any
    expected observation, lease status or runtime pin, and it grants nothing:
    the caller must apply the owner validators and the actual Control peer,
    Runtime pin, Capacity claim and paid lease owner first.  The returned
    digests are canonical digests of the supplied DATA, not proof of origin.
    """
    principal_attempt = _identifier(attempt_id, name="attempt_id")
    attested = _normalized_attestation(
        attestation,
        expectations={
            "binding": None,
            "route": None,
            "worker_id": None,
            "quota_class": None,
            "process": None,
            "lease_binding": None,
            "evidence": None,
        },
    )
    # Reject custom DATA before entering the existing v1 placement validator,
    # whose broader Mapping acceptance is left byte-for-byte unchanged.
    _exact_dict(placement_snapshot, name="placement_snapshot", keys=frozenset({
        "schema_version", "worker_id", "quota_class", "provider",
        "account_label", "observed_at_ms",
    }))
    for key in ("schema_version", "worker_id", "quota_class", "provider", "account_label"):
        if type(placement_snapshot[key]) is not str:
            _refused("placement snapshot text must be plain DATA")
    _bounded_int(placement_snapshot["observed_at_ms"], name="observed_at_ms", minimum=0)
    try:
        placement = _validate_placement_snapshot(placement_snapshot)
    except _PlacementError:
        _refused("placement snapshot is not the closed placement wire")
    if placement["worker_id"] != attested["worker_id"]:
        _refused("placement worker does not match the attested worker")
    if placement["quota_class"] != attested["quota_class"]:
        _refused("placement quota class does not match the attested quota class")
    if placement["provider"] != attested["paid_route"]["provider"]:
        _refused("placement provider does not match the attested paid route")
    if placement["account_label"] != attested["lease_binding"]["account"]:
        _refused("placement account does not match the attested lease account")
    if principal_attempt != attested["binding"]["attempt_id"]:
        _refused("requested attempt does not match the attested binding attempt")
    return {
        "schema_version": PRINCIPAL_SCHEMA,
        "principal_kind": PRINCIPAL_KIND,
        "profile_id": PROFILE_ID,
        "adapter_id": ADAPTER_ID,
        "execution_surface": EXECUTION_SURFACE,
        "binding": dict(attested["binding"]),
        "attempt_id": principal_attempt,
        "worker_id": attested["worker_id"],
        "quota_class": attested["quota_class"],
        "provider": attested["paid_route"]["provider"],
        "account_label": attested["lease_binding"]["account"],
        "placement_snapshot_digest": _contract_digest(placement),
        "host_ref": attested["paid_route"]["host_ref"],
        "model": attested["paid_route"]["model"],
        "os_principal_name": attested["process_identity"]["observed_user"],
        "os_principal_uid": attested["process_identity"]["effective_uid"],
        "process_identity": dict(attested["process_identity"]),
        "lease_binding": {
            key: (
                dict(attested["lease_binding"][key])
                if type(attested["lease_binding"][key]) is dict
                else attested["lease_binding"][key]
            )
            for key in attested["lease_binding"]
        },
        "paid_route": dict(attested["paid_route"]),
        "attestation_sha256": _contract_digest(attested),
        "evidence": dict(attested["evidence"]),
    }


def validate_paid_model_principal(value):
    """Normalize one detached paid model-only principal, or raise.

    The principal must be the exact closed plain-dict shape with the fixed
    schema and kind; dict subclasses and custom mappings are refused for
    untrusted DATA.  Every duplicated derived field is cross-checked against
    its source group.  ``attestation_sha256`` and
    ``placement_snapshot_digest`` are checked for digest shape only: a valid
    principal DATA never claims that a digest proves origin, and it grants
    no authority by itself.
    """
    raw = _exact_dict(value, name="principal", keys=_PRINCIPAL_KEYS)
    if type(raw["schema_version"]) is not str or raw["schema_version"] != PRINCIPAL_SCHEMA:
        _refused("principal.schema_version is not the paid principal schema")
    if type(raw["principal_kind"]) is not str or raw["principal_kind"] != PRINCIPAL_KIND:
        _refused("principal.principal_kind is not the paid model-only kind")
    if type(raw["profile_id"]) is not str or raw["profile_id"] != PROFILE_ID:
        _refused("principal.profile_id is not the paid profile")
    if type(raw["adapter_id"]) is not str or raw["adapter_id"] != ADAPTER_ID:
        _refused("principal.adapter_id is not the paid adapter")
    if type(raw["execution_surface"]) is not str or raw["execution_surface"] != EXECUTION_SURFACE:
        _refused("principal.execution_surface is not the paid execution surface")
    binding = _validate_binding(raw["binding"])
    route = _validate_route(raw["paid_route"], binding=binding)
    process = _validate_process_identity(raw["process_identity"])
    lease = _validate_lease_binding(raw["lease_binding"], route=route)
    evidence = _validate_evidence(raw["evidence"])
    attempt_id = _identifier(raw["attempt_id"], name="attempt_id")
    worker_id = _identifier(raw["worker_id"], name="worker_id")
    quota_class = _identifier(raw["quota_class"], name="quota_class")
    provider = _identifier(raw["provider"], name="provider")
    account_label = _identifier(raw["account_label"], name="account_label")
    host_ref = _identifier(raw["host_ref"], name="host_ref")
    model = _identifier(raw["model"], name="model")
    os_principal_name = _os_principal_text(
        raw["os_principal_name"], name="os_principal_name"
    )
    os_principal_uid = _bounded_int(
        raw["os_principal_uid"], name="os_principal_uid", minimum=0
    )
    placement_digest = _digest_text(
        raw["placement_snapshot_digest"], name="placement_snapshot_digest"
    )
    attestation_digest = _digest_text(
        raw["attestation_sha256"], name="attestation_sha256"
    )
    if attempt_id != binding["attempt_id"]:
        _refused("principal.attempt_id does not match the binding attempt")
    if provider != route["provider"]:
        _refused("principal.provider does not match the paid route")
    if host_ref != route["host_ref"] or host_ref != lease["host_ref"]:
        _refused("principal.host_ref does not match the common route and lease")
    if model != route["model"] or model != lease["model"]:
        _refused("principal.model does not match the common route and lease")
    if account_label != lease["account"]:
        _refused("principal.account_label does not match the lease account")
    if os_principal_name != process["observed_user"]:
        _refused("principal.os_principal_name does not match the observed process user")
    if os_principal_uid != process["effective_uid"]:
        _refused("principal.os_principal_uid does not match the effective process uid")
    return {
        "schema_version": PRINCIPAL_SCHEMA,
        "principal_kind": PRINCIPAL_KIND,
        "profile_id": PROFILE_ID,
        "adapter_id": ADAPTER_ID,
        "execution_surface": EXECUTION_SURFACE,
        "binding": binding,
        "attempt_id": attempt_id,
        "worker_id": worker_id,
        "quota_class": quota_class,
        "provider": provider,
        "account_label": account_label,
        "placement_snapshot_digest": placement_digest,
        "host_ref": host_ref,
        "model": model,
        "os_principal_name": os_principal_name,
        "os_principal_uid": os_principal_uid,
        "process_identity": process,
        "lease_binding": lease,
        "paid_route": route,
        "attestation_sha256": attestation_digest,
        "evidence": evidence,
    }


__all__ = [
    "PRINCIPAL_KIND",
    "PRINCIPAL_SCHEMA",
    "PaidModelPrincipalRefused",
    "build_paid_model_principal",
    "validate_paid_model_attestation",
    "validate_paid_model_principal",
]
