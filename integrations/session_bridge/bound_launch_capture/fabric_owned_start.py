"""Complete START producer candidate at the existing private original-owner seam.

Contract ``fabric.owned.complete_start.candidate.v1`` assembles the complete
``WorkerProcessRef`` + ``LaunchAttestation`` START receipt for exactly one
already-begun original ``OwnedExecution`` of the incumbent attended-Fabric
owner, and retains the exact START bytes on the handle's prebound original carrier
before anything is returned.

This module is source mechanics only.  It is not an admission, enrollment,
capacity, attendance, isolation, canary or assignment producer; it holds no
signing key, independent lease, reservation, scheduler, registry or store; it never
starts, signals or waits through process uncertainty; it never fabricates a
``provider_session_id``; and it never emits a credential value.  Every
qualified fact it consumes (realm enrollment, attendance, capacity,
isolation, canary, assignment, filesystem identities, pinned binary, capture
ownership) must already exist independently of this module.  Evidence passed
in as arguments does not grant authority, and this module does not
authenticate a dict: the real issuers and the real validators keep their
authority.  Host issuance of any qualified fact is outside this leaf.

Publication is fail-closed and single-shot, with no polling, waiting loop or
re-exec:

1. the exact original reserved request is re-digested and re-checked against
   the authenticated ``ControlStartAuthority`` (exact payload material);
2. the live image of THIS owner handle is observed with the real
   ``observe_owned_process_image(owner)`` -- a caller-supplied pid, image or
   path is never accepted -- and the entire observed executable metadata must
   equal the independently pinned ``BinaryAttestation`` (device, inode, size,
   sha256, file uid/gid, mtime_ns, ``stat.S_IMODE`` permission bits and
   executable bits).  ``version``/``real_path`` come only from the pin, never
   from ``/proc`` or argv.  The image file's uid/gid are matched to the pin
   only; the image file owner is not the process principal.
3. the observed process generation (``linux:<ticks>``, boot id, pid, pgid,
   session, all real/effective uid/gid) must equal the original handle's
   recorded identity, with ``pid == pgid == session``, a live direct child of
   this controller, and a principal equal to the bound physical route and
   spec;
4. the assembled receipt must pass BOTH existing validators --
   ``_complete_start_result`` and ``validate_start_result`` -- not a mirrored
   copy;
5. the fixed original-handle retention primitive must accept the exact
   START bytes before this module returns; the original process is re-observed
   and the command's expiry is rechecked at that boundary.

Any refusal preserves the owner, finisher, admission and O_EXCL reservation,
placing the existing original lease in reconciliation hold: it never retries or releases a
reservation, never aborts the owner and never touches the existing finisher,
signal, capture or exact cancel ownership.  The public/default bound path
stays closed: there is no CLI here and ``main()`` refuses.

Known limitation, stated explicitly: exact direct image identity is required.
An interpreter/chain start (the executed image differing from the pinned
binary because a qualified chain producer attestates each hop) is refused.
No chain producer is composed here, and a
caller-supplied list or flag is explicitly not such qualification.
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import importlib
import json
import os
import pwd
import re
import stat
from types import MappingProxyType
from typing import Any, Mapping

CONTRACT_NAME = "fabric.owned.complete_start.candidate.v1"
RECORD_SCHEMA = "mastermind.fabric_owned_complete_start/v1"
DESCRIPTOR_SCHEMA = "mastermind.fabric_attended_claude_launch/v1"
ADAPTER_ID = "attended-fabric"

_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_IDENT_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SECRET_NAME_RE = re.compile(
    r"(?:^|_)(?:api[-_]?key|authorization|credential|secret|token)(?:$|_)",
    re.IGNORECASE,
)
# The start request envelope keys are excluded from the pinned request
# material by control_plane.fabric_control_start._material and by
# executive_fabric_bridge_broker.start_request_sha256 alike.
_ENVELOPE_KEYS = frozenset({"control_start", "start_request_sha256"})
_BINDING_FIELDS = frozenset({
    "root_id", "job_id", "attempt_id",
    "effective_grant_digest", "commission_sha256",
})
_PATH_IDENTITY_FIELDS = frozenset({
    "path", "device", "inode", "uid", "gid", "mode", "mtime_ns",
})
_WORKER_IDENTITY_FIELDS = frozenset({
    "requested_user", "observed_user", "expected_uid", "expected_gid",
    "effective_uid", "effective_gid", "real_uid", "real_gid",
})
# Independently qualified facts this module requires by name.  Their presence
# here is a structural requirement only; each fact's real issuer keeps its
# authority and none of them can be manufactured from correlation or pass
# flags.  Actual host issuance is outside this leaf.
_EVIDENCE_KEYS = frozenset({
    "realm_enrollment", "attendance", "capacity", "isolation",
    "assignment", "finite_home_tmp",
})
_CAPABILITY_PATH_KEYS = frozenset({"stdout_path", "stderr_path", "result_path"})
_PROCESS_IDENTITY_FIELDS = (
    "pid", "pgid", "session_id", "start_identity", "boot_id",
    "effective_uid", "effective_gid", "real_uid", "real_gid",
)


class OwnedStartRefused(ValueError):
    """Closed refusal codes; never carries prompt, credential or image bytes."""


@dataclasses.dataclass(frozen=True)
class OwnedCompleteStart:
    """Retained complete START: exact result plus its original-carrier digest."""

    start_result: Mapping[str, Any]
    process_ref: Any
    launch_attestation: Any
    start_record_sha256: str


def _refuse(code: str, detail: str = "") -> None:
    raise OwnedStartRefused(f"{code}: {detail}" if detail else code)


def _import(name: str):
    """Lazy production import; tests may supply labeled inert mirrors."""
    return importlib.import_module(name)


def _utc_now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _refuse("input_invalid", label)
    return value


def _require_digest(value: Any, label: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        _refuse("input_invalid", label)
    return value


def _require_ident(value: Any, label: str) -> str:
    if type(value) is not str or _IDENT_RE.fullmatch(value) is None:
        _refuse("input_invalid", label)
    return value


def _require_abs_path(value: Any, label: str) -> str:
    if (
        type(value) is not str or not value or "\x00" in value
        or not value.startswith("/") or ".." in value.split("/")
    ):
        _refuse("input_invalid", label)
    return value


def _require_nonneg_int(value: Any, label: str) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 0:
        _refuse("input_invalid", label)
    return value


def _require_strictly_under(value: Any, root: str, label: str) -> str:
    path = _require_abs_path(value, label)
    root_path = _require_abs_path(root, label + ".root")
    if path == root_path or not path.startswith(root_path.rstrip("/") + "/"):
        _refuse("path_not_under_run", label)
    return path


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        _refuse("record_not_canonical", str(exc))
        raise AssertionError  # unreachable


def _request_material(original: Mapping[str, Any]) -> dict[str, Any]:
    """Exact original request minus the transport-only envelope keys.

    ``start_request_sha256`` and ``control_start`` are excluded from the
    pinned material by both existing digest owners, so the retained request
    bytes and the Control authority describe the same material.  A payload
    that still embeds ``control_start`` is refused outright: with it present,
    ``validate_start_result`` (which hashes ``dict(payload)`` verbatim) and
    ``start_request_sha256`` (which excludes the envelope) could never agree
    on one ``request_sha256``, so no result could honestly pass both.
    """
    if "control_start" in original:
        _refuse("control_start_envelope_not_accepted")
    material = {k: v for k, v in original.items() if k not in _ENVELOPE_KEYS}
    if "start_request_sha256" in original:
        declared = _require_digest(original["start_request_sha256"], "start_request_sha256")
        broker = _import("control_plane.executive_fabric_bridge_broker")
        if declared != broker.start_request_sha256(material):
            _refuse("reserved_request_changed")
    return material


def _require_prepared_descriptor(descriptor: Any, owner: Any, run_id: str) -> None:
    """Structural check that this is the SAME compiled descriptor, unchanged.

    The descriptor is never recompiled or reconstructed here; it must be the
    exact object the private seam retained on the original handle.
    """
    for attribute in (
        "schema", "contract_name", "preparation_only", "start_authorized",
        "run_id", "argv", "stdin_text", "environment", "workspace_path",
        "run_dir", "provider_home", "provider_tmp", "model", "settings_sha256",
    ):
        if not hasattr(descriptor, attribute):
            _refuse("prepared_descriptor_invalid", attribute)
    if (
        descriptor.schema != DESCRIPTOR_SCHEMA
        or descriptor.contract_name != "fabric.attended.claude.bounded.v1"
        or descriptor.preparation_only is not True
        or descriptor.start_authorized is not False
    ):
        _refuse("prepared_descriptor_invalid", "identity")
    if descriptor.run_id != run_id:
        _refuse("prepared_descriptor_run_mismatch")
    argv = descriptor.argv
    if type(argv) not in (tuple, list) or not argv or any(
        type(item) is not str or not item for item in argv
    ):
        _refuse("prepared_descriptor_invalid", "argv")
    if type(descriptor.stdin_text) is not str:
        _refuse("prepared_descriptor_invalid", "stdin_text")
    environment = descriptor.environment
    if type(environment) is not MappingProxyType and not isinstance(environment, Mapping):
        _refuse("prepared_descriptor_invalid", "environment")
    for label, attribute in (("HOME", "provider_home"), ("TMPDIR", "provider_tmp")):
        if environment.get(label) != getattr(descriptor, attribute):
            _refuse("prepared_descriptor_invalid", label.lower())
    if any(_SECRET_NAME_RE.search(key) for key in environment):
        _refuse("prepared_descriptor_invalid", "secret_like_env_key")
    for attribute in ("workspace_path", "run_dir", "provider_home", "provider_tmp"):
        _require_abs_path(getattr(descriptor, attribute), "descriptor." + attribute)
    _require_digest(descriptor.settings_sha256, "descriptor.settings_sha256")
    _require_ident(descriptor.model, "descriptor.model")
    retained = getattr(owner, "_original_preparation", None)
    if retained is not descriptor:
        _refuse("prepared_descriptor_not_retained")


def _require_control_authority(authority: Any, original_material: Mapping[str, Any]) -> None:
    """Recheck the exact original request against the authenticated command.

    The exact ``ControlStartAuthority`` type is required, as at the existing
    seam.  Its ``require`` re-proves the pinned payload digest, pin identity,
    attempt binding and unexpired lease; expiry is a refusal, never a wait.
    """
    control_start = _import("control_plane.fabric_control_start")
    if type(authority) is not control_start.ControlStartAuthority:
        _refuse("authenticated_original_owner_required")
    try:
        authority.require(original_material)
    except control_start.ControlStartRefused as exc:
        _refuse("control_start_authority_unavailable", str(exc))


def _observe_original_image(owner: Any) -> dict[str, Any]:
    """Observe THIS owner handle with the real owned-image observer."""
    lane_runtime = _import("integrations.session_bridge.bound_launch_capture.runtime.lane_runtime")
    try:
        image = lane_runtime.observe_owned_process_image(owner)
    except lane_runtime.LaneRuntimeError as exc:
        _refuse("owned_image_unqualified", str(exc))
    except ImportError as exc:
        _refuse("owned_image_unavailable", str(exc))
    if not isinstance(image, dict):
        _refuse("owned_image_unqualified", "observation_shape")
    return image


def _match_pinned_binary(image: dict[str, Any], binary_pin: Any) -> None:
    """Match the ENTIRE observed executable metadata against the pin.

    ``version`` and ``real_path`` are taken only from the independent pin;
    they are never guessed from /proc or argv.  The image file's uid/gid are
    matched to the pin only: the image file owner is NOT the process uid.
    Permission bits are compared as ``stat.S_IMODE`` so file-type bits in the
    pin never cause a false mismatch.
    """
    mismatched = []
    for field in ("device", "inode", "size", "sha256", "uid", "gid", "mtime_ns"):
        if image.get(field) != getattr(binary_pin, field):
            mismatched.append(field)
    observed_mode = stat.S_IMODE(image.get("mode", 0))
    if observed_mode != stat.S_IMODE(binary_pin.mode):
        mismatched.append("mode")
    if not observed_mode & 0o111:
        mismatched.append("executable_bits")
    if mismatched:
        _refuse("pinned_binary_mismatch", ",".join(sorted(mismatched)))
    if not binary_pin.version or not binary_pin.real_path:
        _refuse("pinned_binary_incomplete")


def _qualified_evidence(qualified_evidence: Any, spec: Mapping[str, Any]) -> None:
    """Require the named independent facts; never manufacture them.

    Presence here is structural only.  Each entry must be a concrete
    digest-shaped record naming its source; a callable, a boolean, a pass
    flag or this module's own result is never such a fact.
    """
    evidence = _require_mapping(qualified_evidence, "qualified_evidence")
    if set(evidence) != _EVIDENCE_KEYS:
        missing = sorted(_EVIDENCE_KEYS - set(evidence))
        _refuse("qualified_evidence_required", ",".join(missing))
    for key in sorted(_EVIDENCE_KEYS - {"isolation", "finite_home_tmp"}):
        entry = _require_mapping(evidence[key], "qualified_evidence." + key)
        _require_digest(entry.get("evidence_sha256"), key + ".evidence_sha256")
        source = entry.get("source")
        if type(source) is not str or not source or len(source) > 256:
            _refuse("input_invalid", key + ".source")
    isolation = _require_mapping(evidence["isolation"], "qualified_evidence.isolation")
    manifest = spec.get("isolation_manifest_sha256")
    if manifest is None:
        _refuse("isolation_manifest_required")
    _require_digest(manifest, "spec.isolation_manifest_sha256")
    if isolation.get("isolation_manifest_sha256") != manifest:
        _refuse("isolation_evidence_mismatch")
    home_tmp = _require_mapping(evidence["finite_home_tmp"], "qualified_evidence.finite_home_tmp")
    _require_digest(home_tmp.get("evidence_sha256"), "finite_home_tmp.evidence_sha256")
    _require_abs_path(home_tmp.get("home_path"), "finite_home_tmp.home_path")
    _require_abs_path(home_tmp.get("tmp_path"), "finite_home_tmp.tmp_path")


def _path_identity(
    value: Any, label: str, expected_path: str, *, allow_git_head: bool = False
) -> dict[str, Any]:
    identity = _require_mapping(value, label)
    allowed = _PATH_IDENTITY_FIELDS | ({"git_head"} if allow_git_head else frozenset())
    if not _PATH_IDENTITY_FIELDS <= set(identity) <= allowed:
        _refuse("filesystem_identity_incomplete", label)
    _require_abs_path(identity["path"], label + ".path")
    if identity["path"] != expected_path:
        _refuse("filesystem_identity_path_mismatch", label)
    for field in ("device", "inode", "uid", "gid", "mode", "mtime_ns"):
        _require_nonneg_int(identity[field], f"{label}.{field}")
    return dict(identity)


def _observed_worker_user(effective_uid: int) -> str:
    try:
        return pwd.getpwuid(effective_uid).pw_name
    except (KeyError, OSError) as exc:
        _refuse("observed_worker_user_unavailable", str(exc))
        raise AssertionError  # unreachable


def _require_live_direct_child(owner: Any, image: dict[str, Any]) -> None:
    process = getattr(owner, "process", None)
    if process is None or process.poll() is not None:
        _refuse("owned_process_not_live")
    if image.get("parent_pid") != os.getpid():
        _refuse("owned_process_not_direct_child")
    if not (image["pid"] == image["pgid"] == image["session_id"]):
        _refuse("owned_process_group_identity_disagrees")


def _require_worker_principal(
    image: dict[str, Any], physical: Any, spec: Mapping[str, Any]
) -> dict[str, int]:
    principal = {
        "effective_uid": image["effective_uid"],
        "effective_gid": image["effective_gid"],
        "real_uid": image["real_uid"],
        "real_gid": image["real_gid"],
    }
    for name, value in principal.items():
        _require_nonneg_int(value, "observed." + name)
    if principal["effective_uid"] != physical.worker_uid or principal["real_uid"] != physical.worker_uid:
        _refuse("worker_principal_mismatch", "uid")
    if principal["effective_gid"] != physical.worker_gid or principal["real_gid"] != physical.worker_gid:
        _refuse("worker_principal_mismatch", "gid")
    for spec_name, principal_name in (
        ("expected_worker_uid", "effective_uid"),
        ("expected_worker_gid", "effective_gid"),
    ):
        expected = spec.get(spec_name)
        if expected is not None and expected != principal[principal_name]:
            _refuse("worker_principal_mismatch", spec_name)
    return principal


def _require_base_binding(
    spec: Mapping[str, Any], workspace_identity: Mapping[str, Any]
) -> str:
    expected_base = spec.get("expected_base_sha")
    if type(expected_base) is not str or re.fullmatch(r'[0-9a-f]{40}', expected_base) is None:
        _refuse('input_invalid', 'spec.expected_base_sha')
    git_head = workspace_identity.get("git_head")
    if git_head != expected_base:
        _refuse("workspace_head_changed")
    return expected_base


def _require_canary(spec: Mapping[str, Any]) -> dict[str, Any]:
    canary = spec.get("secret_canary_verdict")
    if type(canary) is not dict or not canary or canary.get("passed") is not True:
        # _complete_start_result requires a passing canary verdict and
        # validate_start_result requires the attestation to carry exactly the
        # spec's verdict, so a complete START cannot honestly exist without
        # the original spec carrying a passing verdict itself.
        _refuse("passing_secret_canary_required")
    return dict(canary)


def _capture_paths(capture_paths: Any, run_dir: str) -> dict[str, str]:
    """Require the existing capture/result ownership paths; never mint names.

    The opt-in original owner reserves fixed private stdout/stderr/result
    files before spawn. Names supplied here must match that live reservation;
    the pinned FD validator at publication supplies the file observation.
    """
    paths = _require_mapping(capture_paths, "capture_paths")
    if set(paths) != _CAPABILITY_PATH_KEYS or any(paths[key] is None for key in _CAPABILITY_PATH_KEYS):
        _refuse(
            "capture_paths_required",
            "existing original capture/result ownership must be named; "
            "no stdout/stderr/result file producer exists in this leaf",
        )
    return {
        key: _require_strictly_under(paths[key], run_dir, "capture." + key)
        for key in sorted(_CAPABILITY_PATH_KEYS)
    }


def _qualified_generation(image):
    value = image.get('process_start_identity')
    # Legacy Linux owned captures predate this explicit projection. Their
    # observer must still prove an actual Linux image; never infer Darwin.
    if value is None:
        import sys
        if sys.platform.startswith('linux'):
            value = 'linux:' + image['start_identity']
    if (type(value) is not str or
            re.fullmatch(r'(?:linux:[0-9]+|darwin:[0-9]+\.[0-9]{6})', value) is None):
        _refuse('owned_image_generation_unqualified')
    if value.split(':', 1)[1] != image['start_identity']:
        _refuse('owned_image_generation_unqualified')
    return value


def _build_receipt(
    *,
    spec: Mapping[str, Any],
    binding: Mapping[str, Any],
    descriptor: Any,
    image: dict[str, Any],
    principal: dict[str, int],
    binary_pin: Any,
    physical: Any,
    capture: Mapping[str, str],
    launch_nonce: str,
    started_at: str,
    invocation: Mapping[str, Any],
    qualified_evidence: Mapping[str, Any],
    workspace_identity: Mapping[str, Any],
    provider_home_identity: Mapping[str, Any],
    expected_base: str,
    observed_user: str,
    request_sha256: str,
):
    contract = _import("control_plane.worker_execution_contract")
    adapter = _import("control_plane.executive_fabric_adapter")
    process_ref = contract.WorkerProcessRef(
        run_id=spec["run_id"],
        pid=image["pid"],
        pgid=image["pgid"],
        process_start_identity=_qualified_generation(image),
        boot_session_id=image["boot_id"],
        launch_nonce=launch_nonce,
        provider_session_id=None,  # The provider supplies one later; never invented.
        stdout_path=capture["stdout_path"],
        stderr_path=capture["stderr_path"],
        result_path=capture["result_path"],
        started_at=started_at,
        binary=binary_pin,
        base_sha=expected_base,
        session_id=image["session_id"],
        effective_uid=principal["effective_uid"],
        effective_gid=principal["effective_gid"],
        real_uid=principal["real_uid"],
        real_gid=principal["real_gid"],
    )
    worker_identity = {
        "requested_user": spec["worker_user"],
        "observed_user": observed_user,
        "expected_uid": principal["effective_uid"],
        "expected_gid": principal["effective_gid"],
        "effective_uid": principal["effective_uid"],
        "effective_gid": principal["effective_gid"],
        "real_uid": principal["real_uid"],
        "real_gid": principal["real_gid"],
    }
    from control_plane.fabric_attended_claude import compiled_permission_digest
    permission_profile_sha256 = compiled_permission_digest(descriptor)
    if permission_profile_sha256 != physical.permission_profile_sha256:
        _refuse("compiled_permission_profile_mismatch")
    attestation = contract.LaunchAttestation(
        schema_version=contract.LAUNCH_ATTESTATION_SCHEMA_VERSION,
        created_at=_utc_now(),
        executable_path=binary_pin.real_path,
        binary=binary_pin,
        rendered_argv=tuple(invocation['command']),
        environment_keys=tuple(invocation['environment_keys']),
        isolation_manifest_sha256=spec["isolation_manifest_sha256"],
        permission_profile_sha256=permission_profile_sha256,
        prompt_sha256=hashlib.sha256(descriptor.stdin_text.encode("utf-8")).hexdigest(),
        expected_base_sha=expected_base,
        observed_base_sha=expected_base,
        workspace_identity=dict(workspace_identity),
        worker_identity=worker_identity,
        provider_home_identity=dict(provider_home_identity),
        secret_canary_verdict=_require_canary(spec),
        launch_nonce=launch_nonce,
        process_identity={
            "pid": process_ref.pid,
            "pgid": process_ref.pgid,
            "session_id": process_ref.session_id,
            "start_identity": process_ref.process_start_identity,
            "boot_id": process_ref.boot_session_id,
            "effective_uid": process_ref.effective_uid,
            "effective_gid": process_ref.effective_gid,
            "real_uid": process_ref.real_uid,
            "real_gid": process_ref.real_gid,
        },
    )
    claim = spec.get("subscription_canary_claim") or {}
    if claim:
        attestation = dataclasses.replace(
            attestation,
            subscription_canary_observation_digest=_require_digest(
                claim.get("observation_digest"), "claim.observation_digest"),
            subscription_canary_binding_id=_require_ident(
                claim.get("binding_id"), "claim.binding_id"),
            subscription_canary_model=_require_ident(claim.get("model"), "claim.model"),
        )
        if attestation.subscription_canary_model != descriptor.model:
            _refuse("subscription_claim_model_mismatch")
    result = {
        "adapter_id": adapter.ADAPTER_ID,
        "binding": dict(binding),
        "request_sha256": request_sha256,
        "physical_binding_sha256": physical.digest,
        "process_ref": dataclasses.asdict(process_ref),
        "launch_attestation": attestation.to_dict(),
    }
    # The complete receipt never carries a phase marker or a grant digest:
    # PRE_EXEC_HANDSHAKE and early-gate shapes are refused by the validators.
    if "phase" in result["launch_attestation"] or "effective_grant_digest" in result["launch_attestation"]:
        _refuse("pre_exec_receipt_refused")
    return process_ref, attestation, result


def _publish_owned_start(
    *,
    original: Mapping[str, Any],
    owner: Any,
    authority: Any,
    physical: Any,
    binary_pin: Any,
    capture_paths: Mapping[str, Any],
    qualified_evidence: Mapping[str, Any],
    workspace_identity: Mapping[str, Any],
    provider_home_identity: Mapping[str, Any],
) -> OwnedCompleteStart:
    """Assemble, double-validate and durably retain one complete START.

    Every argument is qualified evidence the caller already holds; none of
    them grants authority.  On any refusal the caller keeps its existing
    cleanup, seal, denial and ACK path; nothing here is retried or released.
    """
    lane_runtime = _import('integrations.session_bridge.bound_launch_capture.runtime.lane_runtime')
    # Fixed original owner primitive; a caller callback cannot stand in for
    # durable publication or mint a success result.
    descriptor = getattr(owner, '_original_preparation', None)
    launch_nonce = getattr(owner, 'launch_nonce', None)
    started_at = getattr(owner, 'started_at', None)
    invocation = getattr(owner, 'invocation', None)
    _require_ident(launch_nonce, 'original_owner.launch_nonce')
    if type(started_at) is not str or not started_at:
        _refuse('original_start_time_required')
    original = _require_mapping(original, "original")
    material = _request_material(original)
    request_sha256 = _import(
        "control_plane.executive_fabric_bridge_broker"
    ).start_request_sha256(material)
    binding = _require_mapping(material.get("binding"), "binding")
    if set(binding) != _BINDING_FIELDS:
        _refuse("input_invalid", "binding.fields")
    for key in ("root_id", "job_id", "attempt_id"):
        _require_ident(binding[key], "binding." + key)
    for key in ("effective_grant_digest", "commission_sha256"):
        _require_digest(binding[key], "binding." + key)
    _require_ident(_require_mapping(material.get("launch_spec"), "launch_spec").get("run_id"), "spec.run_id")
    spec = material["launch_spec"]
    run_id = spec["run_id"]
    if binding["attempt_id"] != run_id:
        _refuse("reserved_spec_identity_changed")
    _require_abs_path(spec.get("run_dir"), "spec.run_dir")
    _require_abs_path(spec.get("workspace_path"), "spec.workspace_path")
    if type(spec.get("worker_user")) is not str or not spec["worker_user"]:
        _refuse("input_invalid", "spec.worker_user")

    adapter = _import("control_plane.executive_fabric_adapter")
    if type(physical) is not adapter.FabricHostBinding:
        _refuse("physical_binding_required")
    if material.get("physical_binding_sha256") != physical.digest:
        _refuse("physical_route_changed")

    contract = _import("control_plane.worker_execution_contract")
    if type(binary_pin) is not contract.BinaryAttestation:
        _refuse("independent_binary_pin_required")
    if binary_pin.sha256 != physical.binary_sha256:
        _refuse("pinned_binary_route_mismatch")
    _require_ident(launch_nonce, "launch_nonce")

    _require_prepared_descriptor(descriptor, owner, run_id)
    if (not isinstance(invocation, Mapping)
            or invocation.get('command') != list(descriptor.argv)
            or invocation.get('cwd') != descriptor.workspace_path
            or invocation.get('shell') is not False
            or invocation.get('prompt_sha256') != hashlib.sha256(descriptor.stdin_text.encode()).hexdigest()
            or invocation.get('environment_projection_sha256') !=
                lane_runtime._nonsecret_environment_sha256(descriptor.environment)
            or type(invocation.get('environment_keys')) is not list):
        _refuse('original_invocation_changed')
    label = getattr(owner, "label", None)
    if label != run_id:
        _refuse("original_owner_run_mismatch")

    # Publication boundary, first authority recheck.
    _require_control_authority(authority, material)

    try:
        image = _observe_original_image(owner)
    except OwnedStartRefused:
        raise
    except lane_runtime.LaneRuntimeError as exc:
        _refuse("owned_image_unqualified", str(exc))
    except Exception as exc:
        _refuse("owned_image_unavailable", type(exc).__name__)
    _require_live_direct_child(owner, image)
    _match_pinned_binary(image, binary_pin)
    principal = _require_worker_principal(image, physical, spec)
    observed_user = _observed_worker_user(principal["effective_uid"])
    if observed_user != spec["worker_user"]:
        _refuse("observed_worker_user_differs")

    _qualified_evidence(qualified_evidence, spec)
    home_tmp = qualified_evidence["finite_home_tmp"]
    if home_tmp["home_path"] != descriptor.provider_home or home_tmp["tmp_path"] != descriptor.provider_tmp:
        _refuse("finite_home_tmp_mismatch")
    if descriptor.environment.get("HOME") != descriptor.provider_home or descriptor.environment.get("TMPDIR") != descriptor.provider_tmp:
        _refuse("finite_home_tmp_mismatch")

    expected_base = _require_base_binding(spec, workspace_identity)
    workspace = _path_identity(
        workspace_identity, "workspace_identity", spec["workspace_path"],
        allow_git_head=True)
    try:
        provider_home = adapter._execution_home(spec, physical)
    except adapter.BrokerProtocolError as exc:
        # The existing realm contract refused this home; that refusal is
        # fail-closed here too, never a foreign exception escaping the
        # publication boundary.
        _refuse("provider_home_realm_refused", str(exc))
    provider_home_id = _path_identity(
        provider_home_identity, "provider_home_identity", provider_home)
    if (
        provider_home_id["uid"] != principal["effective_uid"]
        or provider_home_id["gid"] != principal["effective_gid"]
    ):
        _refuse("provider_home_principal_mismatch")
    if descriptor.model != spec.get("model"):
        _refuse("descriptor_model_changed")
    if hashlib.sha256(spec["prompt"].encode("utf-8")).hexdigest() != hashlib.sha256(
        descriptor.stdin_text.encode("utf-8")
    ).hexdigest():
        _refuse("descriptor_prompt_changed")
    if tuple(descriptor.argv)[0] != binary_pin.real_path:
        _refuse("descriptor_executable_mismatch")
    capture = _capture_paths(capture_paths, spec["run_dir"])
    # Caller filenames are correlation only; the live original reservation
    # proves the fixed files and retained FDs at this boundary.
    if getattr(owner, '_original_capture_paths', None) != capture:
        _refuse('original_capture_binding_required')
    try:
        live_capture = lane_runtime.validate_owned_capture_live(owner)
        if {k: v['path'] for k, v in live_capture['files'].items()} != capture:
            _refuse('original_capture_binding_required')
    except lane_runtime.LaneRuntimeError as exc:
        _refuse('original_capture_binding_required', str(exc))

    process_ref, attestation, result = _build_receipt(
        spec=spec, binding=binding, descriptor=descriptor, image=image,
        principal=principal, binary_pin=binary_pin, physical=physical,
        capture=capture, launch_nonce=launch_nonce, started_at=started_at,
        invocation=invocation,
        qualified_evidence=qualified_evidence, workspace_identity=workspace,
        provider_home_identity=provider_home_id, expected_base=expected_base,
        observed_user=observed_user, request_sha256=request_sha256,
    )

    # Both real validators must accept this exact shape; a mirrored copy is
    # never sufficient.  If they cannot even be imported, publication fails.
    broker = _import("control_plane.executive_fabric_bridge_broker")
    try:
        broker._complete_start_result(result, binding, result["request_sha256"], spec)
        adapter.validate_start_result(result, payload=material, physical=physical)
    except (broker.BridgeProtocolError, adapter.BrokerProtocolError) as exc:
        _refuse("validator_refused", str(exc))
    except ImportError as exc:
        _refuse("validators_unavailable", str(exc))

    # Publication boundary, second authority recheck immediately before the
    # original-carrier retention; a slow assembly must not outlive the lease.
    _require_control_authority(authority, material)
    # Re-observe the same live original generation after validation. Never
    # poll through a mismatch or use the stale first image as publication proof.
    final_image = _observe_original_image(owner)
    _require_live_direct_child(owner, final_image)
    if final_image != image:
        _refuse('owned_image_changed_before_publication')
    _require_control_authority(authority, material)
    try:
        if {k: {f: v[f] for f in ('path', 'device', 'inode')} for k, v in
                lane_runtime.validate_owned_capture_live(owner)['files'].items()} != {
                    k: {f: v[f] for f in ('path', 'device', 'inode')}
                    for k, v in live_capture['files'].items()}:
            _refuse('original_capture_changed_before_publication')
    except lane_runtime.LaneRuntimeError as exc:
        _refuse('original_capture_changed_before_publication', str(exc))

    record = {
        "schema": RECORD_SCHEMA,
        "contract_name": CONTRACT_NAME,
        "run_id": run_id,
        "adapter_id": ADAPTER_ID,
        "request_sha256": result["request_sha256"],
        "physical_binding_sha256": physical.digest,
        "start_result": result,
        "retained_at": _utc_now(),
    }
    _reject_secret_shaped_keys(record)
    payload = _canonical_bytes(record)
    try:
        retained_digest = lane_runtime.retain_owned_start_bytes(owner, payload)
    except Exception as exc:  # cancellation keeps its original exception semantics
        raise OwnedStartRefused(
            f"start_retention_failed: {type(exc).__name__}") from exc
    if retained_digest != hashlib.sha256(payload).hexdigest():
        _refuse('start_retention_readback_changed')
    return OwnedCompleteStart(
        start_result=MappingProxyType(dict(result)),
        process_ref=process_ref,
        launch_attestation=attestation,
        start_record_sha256=hashlib.sha256(payload).hexdigest(),
    )


def publish_owned_start(*, original: Mapping[str, Any], owner: Any,
                        authority: Any, physical: Any, binary_pin: Any,
                        capture_paths: Mapping[str, Any],
                        qualified_evidence: Mapping[str, Any],
                        workspace_identity: Mapping[str, Any],
                        provider_home_identity: Mapping[str, Any]) -> OwnedCompleteStart:
    """Join one actual original handle to assembly and fixed retention.

    Validation refusal never releases an already-begun process's original
    lease. Recovery/status must consume the retained original record instead
    of invoking a second publication. No record recreates owner authority.
    """
    lane = _import('integrations.session_bridge.bound_launch_capture.runtime.lane_runtime')
    lane._require_owned_execution(owner)
    if owner._start_assembly_attempted or owner._start_publication_attempted:
        _refuse('start_publication_already_attempted')
    # The original begun handle has exactly one assembly/publication entry.
    # Repairing caller inputs cannot reopen a refused or cancelled attempt.
    # The separate retention flag still fences the actual durable write.
    owner._start_assembly_attempted = True
    try:
        return _publish_owned_start(original=original, owner=owner,
            authority=authority, physical=physical, binary_pin=binary_pin,
            capture_paths=capture_paths, qualified_evidence=qualified_evidence,
            workspace_identity=workspace_identity,
            provider_home_identity=provider_home_identity)
    except BaseException:
        if not owner._start_publication_attempted:
            lease = getattr(owner, '_original_lease', None)
            if lease is not None:
                lease.hold_for_reconciliation('owned_start_validation_unconfirmed')
        raise


# The attestation contract itself names its canary provenance fields; the
# scan refuses every OTHER secret-shaped key and never carries values.
_CONTRACT_SECRET_FIELD_ALLOWLIST = frozenset({
    "secret_canary_verdict",
    "subscription_canary_observation_digest",
    "subscription_canary_binding_id",
    "subscription_canary_model",
})


def _reject_secret_shaped_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if (type(key) is str and _SECRET_NAME_RE.search(key)
                    and key not in _CONTRACT_SECRET_FIELD_ALLOWLIST):
                _refuse("secret_shaped_key_in_record")
            _reject_secret_shaped_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_secret_shaped_keys(item)


def main() -> int:
    """The public/default bound path stays closed; there is no CLI START."""
    print(
        "fabric.owned.complete_start.candidate.v1: complete START has no "
        "public CLI; the bound path remains closed to the original owner seam",
        file=__import__("sys").stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ADAPTER_ID",
    "CONTRACT_NAME",
    "DESCRIPTOR_SCHEMA",
    "OwnedCompleteStart",
    "OwnedStartRefused",
    "RECORD_SCHEMA",
    "main",
    "publish_owned_start",
]
