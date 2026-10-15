"""Fail-closed consumer of the configured authenticated Executive service profile.

Inject the existing authenticated App/MCP tool-call interface. This module never
acquires credentials, selects a host, starts work locally, polls, or retries.
The caller retains its stable operation key in its existing operation record.
"""
import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from control_plane.executive_inference_contract import (
    intent_id, normalize_request, validate_receipt, validate_result,
    validate_status, validate_submission_receipt,
)


class FabricUnavailable(RuntimeError):
    """No usable canonical result. Caller must fail closed."""


class FabricConflict(FabricUnavailable):
    """The canonical owner rejected different content under this operation key."""


class EffectUnknown(FabricUnavailable):
    def __init__(self, operation_key: str):
        self.operation_key = operation_key
        super().__init__('Submission effect unknown; reconcile the original operation_key without resubmission.')


class FabricInferenceClient:
    def __init__(self, authenticated_call: Callable[[str, Mapping[str, Any]], Awaitable[dict]]):
        if not callable(authenticated_call):
            raise ValueError('existing authenticated tool interface required')
        self._call = authenticated_call

    async def submit(
        self, operation_key: str, objective: str, inference_request: Mapping[str, Any]
    ) -> dict:
        args = normalize_request(dict(
            operation_key=operation_key,
            objective=objective,
            inference_request=inference_request,
        ))
        try:
            response = await self._call('submit_service_intent', args)
            if (isinstance(response, dict) and response.get('ok') is False
                    and response.get('status') == 'conflict' and response.get('request_ref') == intent_id(operation_key)
                    and isinstance(response.get('error'), dict) and response['error'].get('code') == 'operation_conflict'):
                raise FabricConflict('Operation conflicts; reconcile the original operation_key.')
            return validate_submission_receipt(self._receipt(response, operation_key), args)
        except FabricConflict:
            raise
        except asyncio.CancelledError:
            # Cancellation can arrive after the authenticated tool transport has
            # crossed its send boundary. Preserve the logical operation and force
            # status-only reconciliation instead of exposing a replayable cancel.
            raise EffectUnknown(operation_key) from None
        except Exception:
            # Even a malformed response can follow a committed effect. No replay.
            raise EffectUnknown(operation_key) from None

    async def reconcile(self, operation_key: str) -> dict:
        intent_id(operation_key)
        args = dict(operation_key=operation_key)
        try:
            response = await self._call('service_intent_status', args)
            return validate_status({"receipt": self._receipt(response, operation_key),
                "terminal_result_ref": response.get("terminal_result_ref")}, operation_key)
        except Exception:
            # not_found after uncertainty is not permission to start another job.
            raise FabricUnavailable('Original service operation unresolved; no resubmission performed.') from None

    async def answer(self, operation_key: str, objective: str,
                     inference_request: Mapping[str, Any]) -> dict:
        """Read a direct answer bound to the caller-retained original request.

        This is a read-only consumer, not a completion producer or a retry. The
        configured service must implement the dedicated read view; an absent or
        older backend fails closed. Generic aggregation result() is unchanged.
        """
        from control_plane.executive_inference_contract import (
            DIRECT_RESULT_REF_SCHEMA, validate_direct_result,
        )
        request = normalize_request(dict(operation_key=operation_key, objective=objective,
                                         inference_request=inference_request))
        try:
            status = await self.reconcile(operation_key)
            receipt = validate_submission_receipt(status["receipt"], request)
            reference = status["terminal_result_ref"]
            if not isinstance(reference, Mapping) or reference.get("schema") != DIRECT_RESULT_REF_SCHEMA:
                raise FabricUnavailable("content-bound direct answer reference unavailable")
            response = await self._call("executive_fabric", {
                "view": "service_inference", "operation_key": operation_key,
                "reference": dict(reference),
            })
            return validate_direct_result(response, operation_key=operation_key,
                receipt=receipt, reference=reference,
                max_output_chars=request["inference_request"]["max_output_chars"])
        except Exception:
            raise FabricUnavailable("Exact original direct inference answer unavailable; no submission performed.") from None

    async def result(self, operation_key: str) -> dict:
        """Discover only the original operation's terminal reference through status."""
        try:
            status = await self.reconcile(operation_key)
            ref = status["terminal_result_ref"]
            if ref is None:
                raise ValueError("terminal reference unavailable")
            selection = {key: ref[key] for key in
                ("root_job_id", "job_id", "attempt_id", "result_envelope_digest")}
            response = await self._call('executive_fabric', dict(
                selection, operation_key=operation_key, view='result'))
            return validate_result(response, selection)
        except Exception:
            raise FabricUnavailable('Exact complete Fabric result unavailable.') from None

    @staticmethod
    def _receipt(response, operation_key):
        if (not isinstance(response, dict) or response.get('ok') is not True
                or response.get('status') != 'accepted' or response.get('request_ref') != intent_id(operation_key)):
            raise FabricUnavailable('Service admission unavailable.')
        return validate_receipt(response.get('receipt'), operation_key)
