"""App-only service frames on CeoIngress, using its owner and sole intent sink."""
import inspect
import os
import stat
from collections.abc import Mapping

from control_plane import ceo_intent, ceo_request, executive_ceo_ingress as ingress
from control_plane.executive_inference_contract import PRINCIPAL_ID, derive, intent_id, validate_receipt

SUBMIT_SCHEMA = "mastermind.ceo_ingress.service_inference_submit.v1"
STATUS_SCHEMA = "mastermind.ceo_ingress.service_inference_status.v1"
SCHEMAS = frozenset({SUBMIT_SCHEMA, STATUS_SCHEMA})
# Dedicated service frame ceiling. Historical CEO ingress remains at 8 KiB;
# this larger frame is admitted only for the two closed inference schemas and
# stays below the existing 64 KiB public Executive HTTP request fence.
MAX_FRAME_BYTES = 60 * 1024


async def handle_frame(
    frame, *, runtime, grounding_provider, workspace_root, admission_guard,
    execution_binding_provider=None, result_read_runtime=None,
):
    if not isinstance(frame, Mapping):
        raise ingress.CeoIngressError("invalid_input", "service frame must be an object")
    schema = frame.get("schema")
    if not isinstance(schema, str) or schema not in SCHEMAS:
        raise ingress.CeoIngressError("invalid_input", "unknown service frame")
    is_submit = schema == SUBMIT_SCHEMA
    ingress._exact_top_keys(frame, "service frame", frozenset(
        {"schema", "request", "observed_grounding"} if is_submit else {"schema", "operation_key"}))
    try:
        operation = frame["request"]["operation_key"] if is_submit else frame["operation_key"]
        identity = intent_id(operation)
        if is_submit:
            candidate = derive(frame["request"], frame["observed_grounding"])["envelope"]
    except (KeyError, TypeError, ValueError, ceo_request.CeoRequestError) as exc:
        raise ingress.CeoIngressError("invalid_input", "invalid bounded service request") from exc
    existing = await ingress._backend_call(runtime.store.find_event_by_command_id, ceo_intent.command_id_for(identity))
    if existing is not None:
        payload = existing.get("payload")
        provenance = payload.get("provenance") if isinstance(payload, Mapping) else None
        if (not isinstance(provenance, Mapping)
                or provenance.get("schema") != ceo_intent.INTENT_SCHEMA_SERVICE
                or provenance.get("principal_id") != PRINCIPAL_ID or provenance.get("actor") != PRINCIPAL_ID):
            raise ingress.CeoIngressError("authority_refused", "operation belongs to another principal")
    if not is_submit:
        if result_read_runtime is None:
            # Existing unqualified status behavior remains a truthful null
            # locator. It cannot pretend to know the result of a worker.
            receipt = validate_receipt(
                await ingress._resolve_status_intent(runtime, identity), operation
            )
            return {"receipt": receipt, "terminal_result_ref": None}
        # The host supplies its installed canonical bounded read owner. The
        # original receipt AND its terminal reference must be selected inside
        # that one owner's transaction and observation, never stitched from
        # separate Runtime snapshots which a namespace replacement may cross.
        from control_plane.executive_runtime import Runtime
        from control_plane.executive_inference_runtime_view import terminal_status_from_runtime
        from control_plane.executive_inference_contract import validate_terminal_result_ref
        if not isinstance(result_read_runtime, Runtime):
            raise ingress.CeoIngressError("backend_unavailable", "service result reader unavailable")
        try:
            left, right = runtime.store.path, result_read_runtime.store.path
            if left != right or result_read_runtime.store.read_binding is None:
                raise ValueError("original Runtime and read owner differ")
            before = os.stat(left, follow_symlinks=False)
            other = os.stat(right, follow_symlinks=False)
            if (not stat.S_ISREG(before.st_mode) or
                    (before.st_dev, before.st_ino) != (other.st_dev, other.st_ino)):
                raise ValueError("Runtime file source identity differs")
            observed = await ingress._backend_call(
                terminal_status_from_runtime, result_read_runtime, operation
            )
            after = os.stat(left, follow_symlinks=False)
            if (not stat.S_ISREG(after.st_mode) or
                    (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)):
                raise ValueError("Runtime source changed during service status")
            if observed is None:
                raise ingress.CeoIngressError("not_found", "service operation unavailable")
            # Both values come from one finalized SAME observation of the
            # immutable Job creation and current Runtime Job/Attempt rows.
            receipt = validate_receipt(observed["receipt"], operation)
            reference = validate_terminal_result_ref(
                observed["reference"], receipt, operation
            )
        except ingress.CeoIngressError:
            raise
        except Exception as exc:
            raise ingress.CeoIngressError(
                "backend_unavailable", "service result source unavailable"
            ) from exc
        return {"receipt": receipt, "terminal_result_ref": reference}
    execution_binding = None
    if existing is None:
        trusted = await ingress._observe_trusted_grounding(grounding_provider)
        if trusted != frame["observed_grounding"]:
            raise ingress.CeoIngressError("grounding_mismatch", "service grounding mismatch")
        candidate = derive(frame["request"], trusted)["envelope"]
        if await ingress._observe_trusted_grounding(grounding_provider) != trusted:
            raise ingress.CeoIngressError("grounding_changed", "service grounding changed")
        provider_call = getattr(execution_binding_provider, "__call__", None)
        if (
            not callable(execution_binding_provider)
            or inspect.iscoroutinefunction(execution_binding_provider)
            or inspect.iscoroutinefunction(provider_call)
        ):
            raise ingress.CeoIngressError(
                "backend_unavailable", "service execution binding is unavailable"
            )
        try:
            execution_binding = execution_binding_provider(identity)
        except Exception as exc:
            raise ingress.CeoIngressError(
                "backend_unavailable", "service execution binding is unavailable"
            ) from exc
        if inspect.isawaitable(execution_binding):
            close = getattr(execution_binding, "close", None)
            if callable(close):
                close()
            raise ingress.CeoIngressError(
                "backend_unavailable", "service execution binding is unavailable"
            )
        if not isinstance(execution_binding, Mapping):
            raise ingress.CeoIngressError(
                "backend_unavailable", "service execution binding is unavailable"
            )
    # Canonical sink owns fingerprints, concurrent duplicate resolution and Job creation.
    return validate_receipt(await ingress._submit(
        runtime, candidate, workspace_root,
        service_admission_guard=admission_guard,
        service_execution_binding=execution_binding,
    ), operation)
