"""Pure bridge from one reduced Web-Sol result into the existing Runtime result wire.

The browser-side reducer is responsible for exposing only one bounded canonical
Executive orchestration result from an exact completed assistant turn.  This
module deliberately creates no result store, browser transport, lifecycle,
retry or Runtime transition.  It revalidates the result through the canonical
Executive result owner and constructs the already-existing raw role-result
observation consumed by provider adapters.
"""
from __future__ import annotations

import hashlib
from typing import Final

from control_plane.executive_orchestration_result import (
    OrchestrationResultError,
    RawRoleResultObservation,
    parse_and_validate_envelope,
)

MAX_WEB_SOL_COGNITION_RESULT_BYTES: Final[int] = 49_152


class WebSolCognitionResultError(ValueError):
    """A Web-Sol cognition result cannot cross the canonical result boundary."""

    def __init__(self, code: str) -> None:
        if code not in {
            "RESULT_REFUSED",
            "RESULT_TOO_LARGE",
            "RESULT_METADATA_REFUSED",
        }:
            raise ValueError("unknown Web-Sol cognition-result error code")
        self.code = code
        super().__init__(code)


def build_raw_role_result_observation(
    assistant_result_text: str,
    *,
    expected_job_id: str,
    expected_run_id: str,
    expected_worker_id: str,
    expected_role: str,
    expected_root_job_id: str,
    session_epoch_id: str,
    process_generation_id: str,
    turn_id: str,
    provider_session_id: str,
    provider_native_turn_id: str,
    provider_turn_artifact_digest: str,
) -> RawRoleResultObservation:
    """Revalidate one reduced assistant result and bind it to existing evidence.

    ``assistant_result_text`` must already be the complete canonical JSON result,
    not a transcript, Markdown block, or arbitrary assistant message.  The
    canonical Executive validator remains authoritative for the complete role
    schema, identity binding, redaction checks and result byte semantics.
    """

    if not isinstance(assistant_result_text, str) or not assistant_result_text:
        raise WebSolCognitionResultError("RESULT_REFUSED")
    try:
        encoded = assistant_result_text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise WebSolCognitionResultError("RESULT_REFUSED") from exc
    if len(encoded) > MAX_WEB_SOL_COGNITION_RESULT_BYTES:
        raise WebSolCognitionResultError("RESULT_TOO_LARGE")
    if not isinstance(expected_root_job_id, str) or not expected_root_job_id:
        raise WebSolCognitionResultError("RESULT_METADATA_REFUSED")

    try:
        parse_and_validate_envelope(
            assistant_result_text,
            expected_job_id=expected_job_id,
            expected_run_id=expected_run_id,
            expected_worker_id=expected_worker_id,
            expected_role=expected_role,
            expected_root_job_id=expected_root_job_id,
        )
    except OrchestrationResultError as exc:
        raise WebSolCognitionResultError("RESULT_REFUSED") from exc

    digest = hashlib.sha256(encoded).hexdigest()
    try:
        return RawRoleResultObservation(
            attempt_id=expected_run_id,
            session_epoch_id=session_epoch_id,
            process_generation_id=process_generation_id,
            turn_id=turn_id,
            provider_session_id=provider_session_id,
            provider_native_turn_id=provider_native_turn_id,
            provider_turn_artifact_digest=provider_turn_artifact_digest,
            canonical_result_json=assistant_result_text,
            canonical_result_digest=digest,
            canonical_result_byte_length=len(encoded),
        )
    except OrchestrationResultError as exc:
        raise WebSolCognitionResultError("RESULT_METADATA_REFUSED") from exc


__all__ = [
    "MAX_WEB_SOL_COGNITION_RESULT_BYTES",
    "WebSolCognitionResultError",
    "build_raw_role_result_observation",
]
