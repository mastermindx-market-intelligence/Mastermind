"""Durable paid-model recovery coordinates for the canonical paid adapter.

This module is the paid model-only recovery contract.  It is deliberately
separate from the legacy :mod:`worker_execution_contract` recovery bindings:
legacy ``v1``/``v2`` keep their exact schema, field set, and process coercion,
and nothing here downgrades paid material to a legacy binding or coerces a
legacy ``WorkerProcessRef`` into paid form.

The binding retains only closed, hash-bound launch coordinates for one
already-started paid worker process.  The private control-owned prompt is
re-read through the exact existing permission, symlink, and ownership
boundaries of :func:`_recovery_prompt_bytes`; no provider, lease, route,
profile, or secret authority enters this material.
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from control_plane.worker_execution_contract import (
    DURABLE_COLLECTION_CONTRACT_VERSION,
    OrchestrationLaunchSpec,
    PaidModelProcessRef,
    WorkerLaunchSpec,
    WorkerRecoveryContractError,
    _canonical_sha256,
    _control_recovery_digest,
    _freeze,
    _jsonable,
    _recovery_prompt_bytes,
    _validate_control_recovery_context,
    worker_launch_spec_sha256,
)

PAID_MODEL_RECOVERY_BINDING_VERSION = "mastermind.paid_model_recovery_binding/v1"
PAID_MODEL_ADAPTER_ID = "canonical-paid-fabric"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BINDING_WIRE_FIELDS = frozenset({
    "schema_version",
    "adapter_id",
    "collection_contract_version",
    "launch_spec_sha256",
    "launch_spec",
    "process_ref",
    "launch_attestation_sha256",
    "launch_identity_sha256",
    "capture_root",
})
_LAUNCH_SPEC_FIELDS = frozenset({
    "fields",
    "prompt_path",
    "prompt_sha256",
    "control_recovery",
    "control_recovery_sha256",
})


class PaidModelRecoveryRefused(WorkerRecoveryContractError):
    """Paid model recovery evidence is malformed, drifted, or not paid-owned."""


@dataclasses.dataclass(frozen=True)
class PaidModelRecoveryBinding:
    """Closed, hash-bound recovery coordinates for one paid worker process.

    ``adapter_id`` is the exact canonical paid adapter, the launch material is
    the closed five-field Control-bound shape, and the process identity is a
    paid model process ref.  There is no legacy coercion and no fallback.
    """

    schema_version: str
    adapter_id: str
    collection_contract_version: str
    launch_spec_sha256: str
    launch_spec: Mapping[str, Any] = dataclasses.field(repr=False)
    process_ref: PaidModelProcessRef
    launch_attestation_sha256: str
    launch_identity_sha256: str
    capture_root: str

    def __post_init__(self) -> None:
        if not isinstance(self.launch_spec, Mapping):
            raise PaidModelRecoveryRefused(
                "paid model recovery launch material is invalid"
            )
        object.__setattr__(self, "launch_spec", _freeze(self.launch_spec))
        if self.schema_version != PAID_MODEL_RECOVERY_BINDING_VERSION:
            raise PaidModelRecoveryRefused(
                "paid model recovery schema is unsupported"
            )
        if (
            self.collection_contract_version
            != DURABLE_COLLECTION_CONTRACT_VERSION
        ):
            raise PaidModelRecoveryRefused(
                "paid model recovery collection contract is unsupported"
            )
        if self.adapter_id != PAID_MODEL_ADAPTER_ID:
            raise PaidModelRecoveryRefused(
                "paid model recovery requires the canonical paid adapter"
            )
        if not isinstance(self.process_ref, PaidModelProcessRef):
            raise PaidModelRecoveryRefused(
                "paid model recovery requires a paid model process ref"
            )
        root = self.capture_root
        try:
            encoded_root = root.encode("utf-8") if type(root) is str else b""
        except UnicodeEncodeError as exc:
            raise PaidModelRecoveryRefused("paid model capture root is invalid") from exc
        if (type(root) is not str or not root.startswith("/") or root == "/"
                or str(Path(root)) != root or ".." in Path(root).parts
                or "\x00" in root or len(encoded_root) > 4096):
            raise PaidModelRecoveryRefused("paid model capture root is invalid")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", self.process_ref.run_id) is None:
            raise PaidModelRecoveryRefused("paid model capture attempt is invalid")
        for name in (
            "launch_spec_sha256",
            "launch_attestation_sha256",
            "launch_identity_sha256",
        ):
            digest = getattr(self, name)
            if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
                raise PaidModelRecoveryRefused(
                    f"paid model recovery {name} is invalid"
                )
        if set(self.launch_spec) != _LAUNCH_SPEC_FIELDS:
            raise PaidModelRecoveryRefused(
                "paid model recovery launch fields are invalid"
            )
        fields = self.launch_spec.get("fields")
        if not isinstance(fields, Mapping):
            raise PaidModelRecoveryRefused(
                "paid model recovery launch fields are invalid"
            )
        if (
            fields.get("run_id") != self.process_ref.run_id
            or fields.get("worker_id") != self.process_ref.worker_id
        ):
            raise PaidModelRecoveryRefused(
                "paid model recovery run identity is inconsistent"
            )
        prompt_digest = self.launch_spec.get("prompt_sha256")
        if (
            not isinstance(prompt_digest, str)
            or _SHA256_RE.fullmatch(prompt_digest) is None
        ):
            raise PaidModelRecoveryRefused(
                "paid model recovery prompt digest is invalid"
            )
        prompt_path = self.launch_spec.get("prompt_path")
        if (
            not isinstance(prompt_path, str)
            or not Path(prompt_path).is_absolute()
            or ".." in Path(prompt_path).parts
        ):
            raise PaidModelRecoveryRefused(
                "paid model recovery prompt path is invalid"
            )
        try:
            _validate_control_recovery_context(
                self.launch_spec.get("control_recovery")
            )
        except WorkerRecoveryContractError as exc:
            raise PaidModelRecoveryRefused(str(exc)) from exc
        if self.launch_spec.get("control_recovery_sha256") != _control_recovery_digest(
            self.launch_spec_sha256, self.launch_spec,
        ):
            raise PaidModelRecoveryRefused(
                "Control recovery context digest has drifted"
            )

    @property
    def control_recovery(self) -> Mapping[str, str]:
        """Integrity-bound Control coordinates, not a filesystem grant."""
        return self.launch_spec.get("control_recovery")


    @classmethod
    def bind(
        cls,
        *,
        adapter_id: str,
        spec: WorkerLaunchSpec,
        process_ref: PaidModelProcessRef,
        prompt_path: str | Path,
        control_recovery: Mapping[str, str],
        launch_attestation_sha256: str,
        launch_identity_sha256: str,
        capture_root: str,
    ) -> "PaidModelRecoveryBinding":
        """Bind one live paid process to its closed launch material.

        Verifies the private Control-owned prompt bytes against the launch
        specification, keeps the prompt inside the Control input root, and
        records the exact Control coordinates and their digest.  The Control
        source workspace is retained verbatim and is never cross-checked
        against the remote ``spec.workspace_path``; the caller owns the job,
        attempt, source, route, profile, lease, and capture origin.
        """
        for name, digest in (
            ("launch_attestation_sha256", launch_attestation_sha256),
            ("launch_identity_sha256", launch_identity_sha256),
        ):
            if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
                raise PaidModelRecoveryRefused(
                    f"paid model recovery {name} is invalid"
                )
        if (
            process_ref.run_id != spec.run_id
            or process_ref.worker_id != spec.worker_id
        ):
            raise PaidModelRecoveryRefused(
                "paid model recovery run identity is inconsistent"
            )
        try:
            _validate_control_recovery_context(control_recovery)
        except WorkerRecoveryContractError as exc:
            raise PaidModelRecoveryRefused(str(exc)) from exc
        path = Path(prompt_path)
        if not path.is_absolute():
            raise PaidModelRecoveryRefused(
                "recovery prompt path must be absolute"
            )
        try:
            resolved = path.resolve(strict=True)
            input_root = Path(control_recovery["input_root"]).resolve(strict=True)
            resolved.relative_to(input_root)
        except (OSError, ValueError) as exc:
            raise PaidModelRecoveryRefused(
                "recovery prompt path escapes the Control input root"
            ) from exc
        payload = _recovery_prompt_bytes(resolved)
        if payload != spec.prompt.encode("utf-8"):
            raise PaidModelRecoveryRefused(
                "recovery prompt bytes differ from the launch specification"
            )
        fields = {
            field.name: _jsonable(getattr(spec, field.name))
            for field in dataclasses.fields(spec)
            if field.name != "prompt"
        }
        material = {
            "fields": fields,
            "prompt_path": str(resolved),
            "prompt_sha256": hashlib.sha256(payload).hexdigest(),
        }
        spec_digest = worker_launch_spec_sha256(spec)
        material["control_recovery"] = dict(control_recovery)
        material["control_recovery_sha256"] = _control_recovery_digest(
            spec_digest, material,
        )
        return cls(
            schema_version=PAID_MODEL_RECOVERY_BINDING_VERSION,
            adapter_id=str(adapter_id),
            collection_contract_version=DURABLE_COLLECTION_CONTRACT_VERSION,
            launch_spec_sha256=spec_digest,
            launch_spec=material,
            process_ref=process_ref,
            launch_attestation_sha256=launch_attestation_sha256,
            launch_identity_sha256=launch_identity_sha256,
            capture_root=capture_root,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "collection_contract_version": self.collection_contract_version,
            "launch_spec_sha256": self.launch_spec_sha256,
            "launch_spec": _jsonable(self.launch_spec),
            "process_ref": self.process_ref.to_dict(),
            "launch_attestation_sha256": self.launch_attestation_sha256,
            "launch_identity_sha256": self.launch_identity_sha256,
            "capture_root": self.capture_root,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PaidModelRecoveryBinding":
        if type(value) is not dict or set(value) != _BINDING_WIRE_FIELDS:
            raise PaidModelRecoveryRefused(
                "paid model recovery binding fields are invalid"
            )
        launch_spec = value.get("launch_spec")
        if not isinstance(launch_spec, Mapping):
            raise PaidModelRecoveryRefused(
                "paid model recovery launch material is invalid"
            )
        raw_ref = value.get("process_ref")
        if not isinstance(raw_ref, Mapping):
            raise PaidModelRecoveryRefused(
                "paid model recovery process ref is invalid"
            )
        try:
            process_ref = PaidModelProcessRef.from_dict(dict(raw_ref))
        except (TypeError, ValueError) as exc:
            raise PaidModelRecoveryRefused(str(exc)) from exc
        return cls(
            schema_version=value.get("schema_version"),
            adapter_id=value.get("adapter_id"),
            collection_contract_version=value.get("collection_contract_version"),
            launch_spec_sha256=value.get("launch_spec_sha256"),
            launch_spec=dict(launch_spec),
            process_ref=process_ref,
            launch_attestation_sha256=value.get("launch_attestation_sha256"),
            launch_identity_sha256=value.get("launch_identity_sha256"),
            capture_root=value.get("capture_root"),
        )


    def validate_wire(self) -> "PaidModelRecoveryBinding":
        """Validate retained launch material without opening its private prompt.

        This proves the wire digest, closed launch shape, and coordinates only.
        Recovery still verifies the actual prompt file before reattaching an
        execution.  The prompt is anchored under the Control input root while
        the process output paths stay under the source-bound remote capture namespace.
        """
        fields = self.launch_spec["fields"]
        spec_type = (
            OrchestrationLaunchSpec
            if "effective_grant_digest" in fields else WorkerLaunchSpec
        )
        expected_keys = {
            field.name for field in dataclasses.fields(spec_type) if field.name != "prompt"
        }
        if set(fields) != expected_keys:
            raise PaidModelRecoveryRefused(
                "paid model recovery launch fields are invalid"
            )
        if _canonical_sha256({
            **fields, "prompt_sha256": self.launch_spec["prompt_sha256"],
        }) != self.launch_spec_sha256:
            raise PaidModelRecoveryRefused(
                "paid model recovery launch digest has drifted"
            )
        try:
            raw = dict(_jsonable(fields))
            for name in ("workspace_path", "run_dir", "result_schema_path"):
                if (
                    not isinstance(raw[name], str)
                    or not Path(raw[name]).is_absolute()
                    or ".." in Path(raw[name]).parts
                ):
                    raise PaidModelRecoveryRefused(
                        "paid model recovery launch path is invalid"
                    )
                raw[name] = Path(raw[name])
            # Instantiation reuses the canonical value owner, including grant
            # and subscription-claim validation; the prompt never leaves disk.
            spec_type(prompt="", **raw)
            prompt_path = self.launch_spec["prompt_path"]
            if (
                not isinstance(prompt_path, str)
                or not Path(prompt_path).is_absolute()
                or ".." in Path(prompt_path).parts
            ):
                raise PaidModelRecoveryRefused(
                    "paid model recovery prompt path is invalid"
                )
            Path(prompt_path).relative_to(Path(self.control_recovery["input_root"]))
            for name in ("stdout_path", "stderr_path", "result_path"):
                path = getattr(self.process_ref, name)
                if not isinstance(path, str) or ".." in Path(path).parts:
                    raise PaidModelRecoveryRefused(
                        "paid model recovery process path is invalid"
                    )
                if Path(path).parent != Path(self.capture_root) / (self.process_ref.run_id + ".paid"):
                    raise PaidModelRecoveryRefused("paid model recovery capture path is invalid")
        except (KeyError, TypeError, ValueError) as exc:
            raise PaidModelRecoveryRefused(
                "paid model recovery launch wire is invalid"
            ) from exc
        return self

    def recover_launch_spec(
        self,
        spec_type: type[WorkerLaunchSpec] = WorkerLaunchSpec,
    ) -> WorkerLaunchSpec:
        """Reattach the launch specification from its private owned prompt."""
        if not isinstance(spec_type, type) or not issubclass(
            spec_type, WorkerLaunchSpec
        ):
            raise PaidModelRecoveryRefused(
                "paid model recovery launch type is invalid"
            )
        self.validate_wire()
        fields = self.launch_spec["fields"]
        if not isinstance(fields, Mapping):
            raise PaidModelRecoveryRefused(
                "paid model recovery launch fields are invalid"
            )
        raw = dict(_jsonable(fields))
        prompt_path = Path(str(self.launch_spec["prompt_path"]))
        input_root = Path(self.control_recovery["input_root"])
        try:
            prompt_path.resolve(strict=True).relative_to(
                input_root.resolve(strict=True)
            )
        except (OSError, ValueError) as exc:
            raise PaidModelRecoveryRefused(
                "recovery prompt path escapes the Control input root"
            ) from exc
        payload = _recovery_prompt_bytes(prompt_path)
        digest = hashlib.sha256(payload).hexdigest()
        if digest != self.launch_spec["prompt_sha256"]:
            raise PaidModelRecoveryRefused(
                "paid model recovery prompt digest has drifted"
            )
        try:
            prompt = payload.decode("utf-8", errors="strict")
            for name in (
                "workspace_path",
                "run_dir",
                "result_schema_path",
            ):
                raw[name] = Path(raw[name])
            for name in (
                "isolation_roots",
                "isolation_denied_paths",
                "forbidden_paths",
            ):
                raw[name] = tuple(Path(item) for item in raw[name])
            for name in ("authorities", "allowed_artifact_paths"):
                raw[name] = tuple(raw[name])
            spec = spec_type(prompt=prompt, **raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise PaidModelRecoveryRefused(
                "paid model recovery launch specification is invalid"
            ) from exc
        if (
            spec.run_id != self.process_ref.run_id
            or worker_launch_spec_sha256(spec) != self.launch_spec_sha256
        ):
            raise PaidModelRecoveryRefused(
                "paid model recovery launch specification digest or run identity "
                "has drifted"
            )
        return spec


__all__ = [
    "PAID_MODEL_ADAPTER_ID",
    "PAID_MODEL_RECOVERY_BINDING_VERSION",
    "PaidModelRecoveryBinding",
    "PaidModelRecoveryRefused",
]
