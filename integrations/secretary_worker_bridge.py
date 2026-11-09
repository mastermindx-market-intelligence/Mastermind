"""Composition bridge between bounded Secretary requests and existing worker receipts.

This module does not own worker lifecycle, provider selection, process launch,
collection, schema-file I/O, or execution admission.  It only binds already
constructed provider-neutral worker contracts to the Secretary request and
correlates already-collected worker evidence back to the current snapshot.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any

from control_plane.worker_execution_contract import (
    CollectionReceipt,
    WorkerLaunchSpec,
    WorkerRunStatus,
    worker_launch_spec_sha256,
)
from integrations.mastermind_secretary_mcp.decision_provider_contract import (
    PROVIDER_REQUEST_SCHEMA_V2,
    PROVIDER_REQUEST_SCHEMA_V3,
    SecretaryProviderRequest,
    build_secretary_provider_request,
    validate_secretary_provider_request,
    validate_secretary_provider_return,
)

LAUNCH_BINDING_SCHEMA = "mastermind.secretary_worker_launch_binding/v1"
LAUNCH_BINDING_SCHEMA_V2 = "mastermind.secretary_worker_launch_binding/v2"
LAUNCH_BINDING_SCHEMA_V3 = "mastermind.secretary_worker_launch_binding/v3"
COLLECTION_VALIDATION_SCHEMA = "mastermind.secretary_worker_collection_validation/v1"
COLLECTION_VALIDATION_SCHEMA_V2 = "mastermind.secretary_worker_collection_validation/v2"
COLLECTION_VALIDATION_SCHEMA_V3 = "mastermind.secretary_worker_collection_validation/v3"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_CHARS = 256


@dataclasses.dataclass(frozen=True)
class SecretaryWorkerLaunchBinding:
    status: str
    refusal_code: str | None
    snapshot_digest: str | None
    prompt_sha256: str | None
    output_schema_sha256: str | None
    worker_launch_spec_sha256: str | None
    run_id: str | None
    job_id: str | None
    worker_id: str | None
    basis_material_sha256: str | None = None
    cognition_budget_ms: int | None = None
    cognition_deadline_ms: int | None = None
    worker_started: bool = False
    execution_authorized: bool = False
    schema_version: str = LAUNCH_BINDING_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SecretaryWorkerCollectionValidation:
    status: str
    refusal_code: str | None
    return_refusal_code: str | None
    semantic_refusal_code: str | None
    snapshot_digest: str | None
    worker_launch_spec_sha256: str | None
    result_sha256: str | None
    structured_output_digest: str | None
    action: str | None
    reason_code: str | None
    requested_mode: str | None
    fanout_candidate_ids: tuple[str, ...]
    worker_collection_correlated: bool
    basis_material_sha256: str | None = None
    execution_material_sha256: str | None = None
    current_snapshot_digest: str | None = None
    request_integrity_sha256: str | None = None
    cognition_deadline_ms: int | None = None
    provider_result_attested: bool = False
    execution_authorized: bool = False
    requires_owner_admission: bool = True
    schema_version: str = COLLECTION_VALIDATION_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["fanout_candidate_ids"] = list(self.fanout_candidate_ids)
        return value


def _valid_id(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= _MAX_ID_CHARS
        and not any(ord(character) < 32 for character in value)
    )


def _valid_hex64(value: object) -> bool:
    return type(value) is str and _HEX64_RE.fullmatch(value) is not None


def _launch_refusal(code: str) -> SecretaryWorkerLaunchBinding:
    return SecretaryWorkerLaunchBinding(
        status="REFUSED",
        refusal_code=code,
        snapshot_digest=None,
        prompt_sha256=None,
        output_schema_sha256=None,
        worker_launch_spec_sha256=None,
        run_id=None,
        job_id=None,
        worker_id=None,
    )


def _request_is_ready(value: object) -> bool:
    if type(value) is not SecretaryProviderRequest:
        return False
    if (
        value.status != "READY"
        or value.refusal_code is not None
        or value.prompt is None
        or value.output_schema_json is None
        or not _valid_hex64(value.snapshot_digest)
        or not _valid_hex64(value.prompt_sha256)
        or value.provider_selected
        or value.model_selected
        or value.worker_started
        or value.execution_authorized
    ):
        return False
    if value.schema_version in {PROVIDER_REQUEST_SCHEMA_V2, PROVIDER_REQUEST_SCHEMA_V3}:
        return validate_secretary_provider_request(value)
    return hashlib.sha256(value.prompt.encode("utf-8")).hexdigest() == value.prompt_sha256


def _launch_budget_ms(timeout_seconds: object) -> int | None:
    if type(timeout_seconds) not in (int, float):
        return None
    try:
        timeout = float(timeout_seconds)
        budget_ms = timeout * 1000
    except (OverflowError, TypeError, ValueError):
        return None
    if not math.isfinite(timeout) or not math.isfinite(budget_ms) or timeout <= 0:
        return None
    return math.ceil(budget_ms)


def bind_secretary_worker_launch(
    provider_request: object,
    worker_launch_spec: object,
    output_schema_json: object,
) -> SecretaryWorkerLaunchBinding:
    """Bind one exact Secretary request to an existing READ-only launch spec."""

    if not _request_is_ready(provider_request):
        return _launch_refusal("PROVIDER_REQUEST_INVALID")
    assert isinstance(provider_request, SecretaryProviderRequest)
    request_is_v3 = provider_request.schema_version == PROVIDER_REQUEST_SCHEMA_V3
    if not isinstance(worker_launch_spec, WorkerLaunchSpec):
        return _launch_refusal("WORKER_LAUNCH_SPEC_INVALID")
    request_is_timestamped = provider_request.schema_version in {
        PROVIDER_REQUEST_SCHEMA_V2,
        PROVIDER_REQUEST_SCHEMA_V3,
    }
    if request_is_timestamped:
        required_budget = _launch_budget_ms(worker_launch_spec.timeout_seconds)
        if required_budget is None or required_budget != provider_request.cognition_budget_ms:
            return _launch_refusal("COGNITION_BUDGET_MISMATCH")
    if type(output_schema_json) is not str:
        return _launch_refusal("LAUNCH_SCHEMA_INVALID")
    if worker_launch_spec.prompt != provider_request.prompt:
        return _launch_refusal("LAUNCH_PROMPT_MISMATCH")
    if output_schema_json != provider_request.output_schema_json:
        return _launch_refusal("LAUNCH_SCHEMA_MISMATCH")

    effective_authorities = set(worker_launch_spec.authorities)
    if worker_launch_spec.authority is not None:
        effective_authorities.add(worker_launch_spec.authority)
    if effective_authorities != {"READ"}:
        return _launch_refusal("LAUNCH_AUTHORITY_INVALID")
    if worker_launch_spec.allowed_artifact_paths:
        return _launch_refusal("LAUNCH_ARTIFACT_PATHS_FORBIDDEN")
    if not all(
        _valid_id(value)
        for value in (
            worker_launch_spec.run_id,
            worker_launch_spec.job_id,
            worker_launch_spec.worker_id,
        )
    ):
        return _launch_refusal("LAUNCH_IDENTITY_INVALID")

    try:
        schema_value = json.loads(output_schema_json)
        if not isinstance(schema_value, dict):
            return _launch_refusal("LAUNCH_SCHEMA_INVALID")
        launch_digest = worker_launch_spec_sha256(worker_launch_spec)
    except (TypeError, ValueError):
        return _launch_refusal("WORKER_LAUNCH_SPEC_INVALID")

    return SecretaryWorkerLaunchBinding(
        status="READY",
        refusal_code=None,
        snapshot_digest=provider_request.snapshot_digest,
        prompt_sha256=provider_request.prompt_sha256,
        output_schema_sha256=hashlib.sha256(
            output_schema_json.encode("utf-8")
        ).hexdigest(),
        worker_launch_spec_sha256=launch_digest,
        run_id=worker_launch_spec.run_id,
        job_id=worker_launch_spec.job_id,
        worker_id=worker_launch_spec.worker_id,
        basis_material_sha256=(
            provider_request.basis_material_sha256 if request_is_timestamped else None
        ),
        cognition_budget_ms=(
            provider_request.cognition_budget_ms if request_is_timestamped else None
        ),
        cognition_deadline_ms=(
            provider_request.request_created_at_ms + provider_request.cognition_budget_ms
            if request_is_timestamped
            else None
        ),
        schema_version=(
            LAUNCH_BINDING_SCHEMA_V3 if request_is_v3 else LAUNCH_BINDING_SCHEMA_V2 if request_is_timestamped else LAUNCH_BINDING_SCHEMA
        ),
    )


def _plain_json(value: object) -> object:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("non-string JSON key")
            result[key] = _plain_json(item)
        return result
    if isinstance(value, (tuple, list)):
        return [_plain_json(item) for item in value]
    raise ValueError("non-JSON value")


def _snapshot_v2_material(snapshot: dict[str, object]) -> dict[str, object]:
    material_keys = frozenset(snapshot) - {"observed_at_ms", "expires_at_ms"}
    return {key: snapshot[key] for key in sorted(material_keys)}


def _snapshot_v2_material_digest(snapshot: dict[str, object]) -> str:
    encoded = json.dumps(
        _snapshot_v2_material(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _collection_receipt(
    *,
    status: str,
    refusal_code: str | None,
    binding: SecretaryWorkerLaunchBinding | None = None,
    result_sha256: str | None = None,
    structured_output_digest: str | None = None,
    return_refusal_code: str | None = None,
    semantic_refusal_code: str | None = None,
    action: str | None = None,
    reason_code: str | None = None,
    requested_mode: str | None = None,
    fanout_candidate_ids: tuple[str, ...] = (),
    basis_material_sha256: str | None = None,
    execution_material_sha256: str | None = None,
    current_snapshot_digest: str | None = None,
    request_integrity_sha256: str | None = None,
    cognition_deadline_ms: int | None = None,
    worker_collection_correlated: bool = False,
    request_is_v3: bool = False,
) -> SecretaryWorkerCollectionValidation:
    return SecretaryWorkerCollectionValidation(
        status=status,
        refusal_code=refusal_code,
        return_refusal_code=return_refusal_code,
        semantic_refusal_code=semantic_refusal_code,
        snapshot_digest=binding.snapshot_digest if binding is not None else None,
        worker_launch_spec_sha256=(
            binding.worker_launch_spec_sha256 if binding is not None else None
        ),
        result_sha256=result_sha256,
        structured_output_digest=structured_output_digest,
        action=action,
        reason_code=reason_code,
        requested_mode=requested_mode,
        fanout_candidate_ids=fanout_candidate_ids,
        basis_material_sha256=basis_material_sha256,
        execution_material_sha256=execution_material_sha256,
        current_snapshot_digest=current_snapshot_digest,
        request_integrity_sha256=request_integrity_sha256,
        cognition_deadline_ms=cognition_deadline_ms,
        worker_collection_correlated=worker_collection_correlated,
        schema_version=(
            COLLECTION_VALIDATION_SCHEMA_V3
            if request_is_v3 and request_integrity_sha256 is not None
            else COLLECTION_VALIDATION_SCHEMA_V2
            if request_integrity_sha256 is not None
            else COLLECTION_VALIDATION_SCHEMA
        ),
    )


def _binding_matches_request(
    binding: SecretaryWorkerLaunchBinding,
    request: SecretaryProviderRequest,
) -> bool:
    if binding.status != "READY" or binding.refusal_code is not None:
        return False
    if (
        binding.snapshot_digest != request.snapshot_digest
        or binding.prompt_sha256 != request.prompt_sha256
        or binding.output_schema_sha256
        != hashlib.sha256(request.output_schema_json.encode("utf-8")).hexdigest()
        or not _valid_hex64(binding.worker_launch_spec_sha256)
        or not all(_valid_id(value) for value in (binding.run_id, binding.job_id, binding.worker_id))
    ):
        return False
    if binding.worker_started or binding.execution_authorized:
        return False
    if request.schema_version not in {
        PROVIDER_REQUEST_SCHEMA_V2,
        PROVIDER_REQUEST_SCHEMA_V3,
    }:
        return True
    return (
        binding.basis_material_sha256 == request.basis_material_sha256
        and binding.cognition_budget_ms == request.cognition_budget_ms
    )


def _binding_matches_launch(
    binding: SecretaryWorkerLaunchBinding,
    request: SecretaryProviderRequest,
    worker_launch_spec: WorkerLaunchSpec,
) -> bool:
    required_budget = _launch_budget_ms(worker_launch_spec.timeout_seconds)
    if required_budget is None or required_budget != request.cognition_budget_ms:
        return False
    expected = bind_secretary_worker_launch(
        request,
        worker_launch_spec,
        request.output_schema_json,
    )
    return expected == binding


def validate_secretary_worker_collection(
    current_snapshot: object,
    provider_request: object,
    launch_binding: object,
    collection_receipt: object,
    *,
    now_ms: int,
    worker_launch_spec: object | None = None,
) -> SecretaryWorkerCollectionValidation:
    """Correlate one existing worker collection with the current Secretary request."""

    request_is_timestamped = (
        type(provider_request) is SecretaryProviderRequest
        and provider_request.schema_version
        in {PROVIDER_REQUEST_SCHEMA_V2, PROVIDER_REQUEST_SCHEMA_V3}
    )
    request_is_v3 = (
        type(provider_request) is SecretaryProviderRequest
        and provider_request.schema_version == PROVIDER_REQUEST_SCHEMA_V3
    )
    current_request = build_secretary_provider_request(
        current_snapshot,
        now_ms=now_ms,
        cognition_budget_ms=(
            provider_request.cognition_budget_ms if request_is_timestamped else None
        ),
    )
    if type(provider_request) is not SecretaryProviderRequest:
        return _collection_receipt(
            status="REFUSED",
            refusal_code="PROVIDER_REQUEST_MISMATCH",
            request_is_v3=request_is_v3,
        )
    if current_request.status != "READY":
        if (
            request_is_timestamped
            and isinstance(current_snapshot, dict)
        ):
            current_material = None
            if isinstance(current_snapshot, dict):
                try:
                    current_material = _snapshot_v2_material_digest(current_snapshot)
                except (TypeError, ValueError):
                    current_material = None
            if (
                current_material is not None
                and current_material != provider_request.basis_material_sha256
            ):
                return _collection_receipt(
                    status="REFUSED",
                    refusal_code="SECRETARY_RETURN_REFUSED",
                    return_refusal_code="PROVIDER_MATERIAL_DRIFT",
                    binding=launch_binding if type(launch_binding) is SecretaryWorkerLaunchBinding else None,
                    basis_material_sha256=provider_request.basis_material_sha256,
                    execution_material_sha256=current_material,
                    current_snapshot_digest=current_request.snapshot_digest,
                    request_integrity_sha256=provider_request.request_integrity_sha256,
                    request_is_v3=request_is_v3,
                )
        return _collection_receipt(
            status="REFUSED",
            refusal_code="CURRENT_PROVIDER_REQUEST_NOT_READY",
            request_is_v3=request_is_v3,
            request_integrity_sha256=(
                provider_request.request_integrity_sha256
                if request_is_timestamped
                else None
            ),
        )
    if not request_is_timestamped and provider_request != current_request:
        return _collection_receipt(
            status="REFUSED",
            refusal_code="PROVIDER_REQUEST_MISMATCH",
        )
    if request_is_timestamped and not validate_secretary_provider_request(provider_request):
        return _collection_receipt(
            status="REFUSED",
            refusal_code="PROVIDER_REQUEST_MISMATCH",
        )
    if type(launch_binding) is not SecretaryWorkerLaunchBinding or not _binding_matches_request(
        launch_binding, provider_request
    ):
        return _collection_receipt(
            status="REFUSED",
            refusal_code="LAUNCH_BINDING_MISMATCH",
            binding=launch_binding if type(launch_binding) is SecretaryWorkerLaunchBinding else None,
        )
    assert isinstance(launch_binding, SecretaryWorkerLaunchBinding)
    if request_is_timestamped:
        if not isinstance(worker_launch_spec, WorkerLaunchSpec):
            return _collection_receipt(
                status="REFUSED",
                refusal_code="LAUNCH_SPEC_MISMATCH",
                binding=launch_binding,
            )
        if not _binding_matches_launch(
            launch_binding,
            provider_request,
            worker_launch_spec,
        ):
            return _collection_receipt(
                status="REFUSED",
                refusal_code="LAUNCH_SPEC_MISMATCH",
                binding=launch_binding,
            )
        assert launch_binding.cognition_deadline_ms is not None
        if now_ms > launch_binding.cognition_deadline_ms:
            return _collection_receipt(
                status="REFUSED",
                refusal_code="COGNITION_BUDGET_EXPIRED",
                binding=launch_binding,
            )
    if type(collection_receipt) is not CollectionReceipt:
        return _collection_receipt(
            status="REFUSED",
            refusal_code="COLLECTION_RECEIPT_INVALID",
            binding=launch_binding,
        )

    result = collection_receipt.result
    process_ref = collection_receipt.process_ref
    if (
        process_ref.run_id != launch_binding.run_id
        or result.run_id != launch_binding.run_id
        or result.job_id != launch_binding.job_id
        or result.worker_id != launch_binding.worker_id
    ):
        return _collection_receipt(
            status="REFUSED",
            refusal_code="COLLECTION_IDENTITY_MISMATCH",
            binding=launch_binding,
        )
    if (
        result.status is not WorkerRunStatus.SUCCEEDED
        or result.exit_code != 0
        or result.error is not None
        or result.structured_output is None
    ):
        return _collection_receipt(
            status="REFUSED",
            refusal_code="COLLECTION_NOT_SUCCEEDED",
            binding=launch_binding,
        )
    if not all(
        _valid_hex64(value)
        for value in (
            collection_receipt.stdout_sha256,
            collection_receipt.stderr_sha256,
            collection_receipt.result_sha256,
        )
    ):
        return _collection_receipt(
            status="REFUSED",
            refusal_code="COLLECTION_HASH_INVALID",
            binding=launch_binding,
        )
    if result.artifact_manifest:
        return _collection_receipt(
            status="REFUSED",
            refusal_code="COLLECTION_WRITE_EVIDENCE",
            binding=launch_binding,
            result_sha256=collection_receipt.result_sha256,
        )
    changed_paths = result.git_manifest.get("changed_paths")
    if not isinstance(changed_paths, (tuple, list)) or len(changed_paths) != 0:
        return _collection_receipt(
            status="REFUSED",
            refusal_code="COLLECTION_WRITE_EVIDENCE",
            binding=launch_binding,
            result_sha256=collection_receipt.result_sha256,
        )

    try:
        structured_output = _plain_json(result.structured_output)
        if type(structured_output) is not dict:
            raise ValueError("structured output root must be object")
        structured_output_digest = hashlib.sha256(
            json.dumps(
                structured_output,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
    except (TypeError, ValueError):
        return _collection_receipt(
            status="REFUSED",
            refusal_code="COLLECTION_STRUCTURED_OUTPUT_INVALID",
            binding=launch_binding,
            result_sha256=collection_receipt.result_sha256,
            worker_collection_correlated=True,
        )

    secretary_return = validate_secretary_provider_return(
        current_snapshot,
        provider_request,
        structured_output,
        now_ms=now_ms,
    )
    if secretary_return.status != "ACCEPTED":
        return _collection_receipt(
            status="REFUSED",
            refusal_code="SECRETARY_RETURN_REFUSED",
            return_refusal_code=secretary_return.refusal_code,
            semantic_refusal_code=secretary_return.semantic_refusal_code,
            binding=launch_binding,
            result_sha256=collection_receipt.result_sha256,
            structured_output_digest=structured_output_digest,
            basis_material_sha256=secretary_return.basis_material_sha256,
            execution_material_sha256=secretary_return.execution_material_sha256,
            current_snapshot_digest=secretary_return.current_snapshot_digest,
            request_integrity_sha256=secretary_return.request_integrity_sha256,
            cognition_deadline_ms=(
                launch_binding.cognition_deadline_ms if request_is_timestamped else None
            ),
            worker_collection_correlated=True,
            request_is_v3=request_is_v3,
        )

    return _collection_receipt(
        status="ACCEPTED",
        refusal_code=None,
        binding=launch_binding,
        result_sha256=collection_receipt.result_sha256,
        structured_output_digest=structured_output_digest,
        action=secretary_return.action,
        reason_code=secretary_return.reason_code,
        requested_mode=secretary_return.requested_mode,
        fanout_candidate_ids=secretary_return.fanout_candidate_ids,
        basis_material_sha256=secretary_return.basis_material_sha256,
        execution_material_sha256=secretary_return.execution_material_sha256,
        current_snapshot_digest=secretary_return.current_snapshot_digest,
        request_integrity_sha256=secretary_return.request_integrity_sha256,
        cognition_deadline_ms=(
            launch_binding.cognition_deadline_ms if request_is_timestamped else None
        ),
        worker_collection_correlated=True,
        request_is_v3=request_is_v3,
    )


__all__ = [
    "COLLECTION_VALIDATION_SCHEMA",
    "COLLECTION_VALIDATION_SCHEMA_V2",
    "COLLECTION_VALIDATION_SCHEMA_V3",
    "LAUNCH_BINDING_SCHEMA",
    "LAUNCH_BINDING_SCHEMA_V2",
    "LAUNCH_BINDING_SCHEMA_V3",
    "SecretaryWorkerCollectionValidation",
    "SecretaryWorkerLaunchBinding",
    "bind_secretary_worker_launch",
    "validate_secretary_worker_collection",
]
