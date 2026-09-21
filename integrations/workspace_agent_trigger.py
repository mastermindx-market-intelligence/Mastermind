"""Effect-safe one-shot Workspace Agent trigger transport; source-only and dark.

This module owns no Runtime lifecycle, queue, retry controller, credential store,
Wake acknowledgement, result acceptance, or Workspace Agent registration. It is
an effectful provider transport primitive for a later reviewed Executive owner.

Important boundary: a provider 202 means only that the trigger was accepted by
the provider. The supported API contract returns no run id or response body and
does not expose the agent response. Acceptance therefore does not prove that the
agent consumed the prompt, produced a useful candidate, returned anything to
Mastermind, or satisfied a canonical Wake acknowledgement.

The caller must create and durably reconcile one WorkspaceAgentTriggerPlan
through the existing Executive operation/event owner before production use.
This module deliberately keeps no operation registry of its own.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import math
import re
import ssl
from dataclasses import dataclass, field
from typing import Callable

from integrations.workspace_agent_api import (
    HOST,
    InvalidObservation,
    TriggerObservation,
    decode_trigger,
    validate_channel_id,
)

MAX_TRIGGER_BODY_BYTES = 32_768
BETA_HEADER = "workspace_agent_runs=v1"
_OPERATION_KEY = re.compile(r"[a-z0-9][a-z0-9-]{2,95}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_IDEMPOTENCY_KEY = re.compile(r"mmx-wa-v1-[0-9a-f]{64}\Z", re.ASCII)


@dataclass(frozen=True)
class WorkspaceAgentTriggerPlan:
    """Frozen exact pre-effect material for one Workspace Agent trigger.

    The request body is intentionally excluded from repr so a log of the plan
    cannot turn the potentially sensitive prompt into a second data surface.
    """

    channel_id: str
    operation_key: str
    payload_sha256: str
    idempotency_key: str
    _body: bytes = field(repr=False)

    def __post_init__(self) -> None:
        validate_channel_id(self.channel_id)
        if (
            type(self.operation_key) is not str
            or _OPERATION_KEY.fullmatch(self.operation_key) is None
        ):
            raise InvalidObservation("INVALID_OPERATION_KEY")
        if (
            type(self.payload_sha256) is not str
            or _SHA256.fullmatch(self.payload_sha256) is None
        ):
            raise InvalidObservation("INVALID_PAYLOAD_DIGEST")
        if type(self._body) is not bytes or not self._body:
            raise InvalidObservation("INVALID_TRIGGER_BODY")
        if len(self._body) > MAX_TRIGGER_BODY_BYTES:
            raise InvalidObservation("TRIGGER_BODY_TOO_LARGE")
        actual_digest = hashlib.sha256(self._body).hexdigest()
        if actual_digest != self.payload_sha256:
            raise InvalidObservation("PAYLOAD_FINGERPRINT_MISMATCH")
        expected_key = _derive_idempotency_key(
            channel_id=self.channel_id,
            operation_key=self.operation_key,
            payload_sha256=self.payload_sha256,
        )
        if (
            type(self.idempotency_key) is not str
            or _IDEMPOTENCY_KEY.fullmatch(self.idempotency_key) is None
            or self.idempotency_key != expected_key
        ):
            raise InvalidObservation("IDEMPOTENCY_KEY_MISMATCH")


def _canonical_body(input_text: str, conversation_key: str | None) -> bytes:
    if type(input_text) is not str or not input_text:
        raise InvalidObservation("INVALID_TRIGGER_INPUT")
    try:
        input_text.encode("utf-8", errors="strict")
    except UnicodeError:
        raise InvalidObservation("INVALID_TRIGGER_INPUT") from None
    if "\x00" in input_text:
        raise InvalidObservation("INVALID_TRIGGER_INPUT")

    value: dict[str, str] = {"input": input_text}
    if conversation_key is not None:
        if (
            type(conversation_key) is not str
            or not 1 <= len(conversation_key) <= 256
            or not conversation_key.isascii()
            or any(ord(char) < 33 or ord(char) > 126 for char in conversation_key)
        ):
            raise InvalidObservation("INVALID_CONVERSATION_KEY")
        value["conversation_key"] = conversation_key
    try:
        body = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise InvalidObservation("INVALID_TRIGGER_INPUT") from None
    if len(body) > MAX_TRIGGER_BODY_BYTES:
        raise InvalidObservation("TRIGGER_BODY_TOO_LARGE")
    return body


def _derive_idempotency_key(
    *, channel_id: str, operation_key: str, payload_sha256: str
) -> str:
    material = json.dumps(
        {
            "channel_id": channel_id,
            "operation_key": operation_key,
            "payload_sha256": payload_sha256,
            "schema": "mastermind.workspace_agent_trigger_plan.v1",
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return "mmx-wa-v1-" + hashlib.sha256(material).hexdigest()


def build_trigger_plan(
    *,
    channel_id: str,
    operation_key: str,
    input_text: str,
    conversation_key: str | None = None,
) -> WorkspaceAgentTriggerPlan:
    """Build one exact immutable trigger plan without network or durable effects."""

    channel_id = validate_channel_id(channel_id)
    if type(operation_key) is not str or _OPERATION_KEY.fullmatch(operation_key) is None:
        raise InvalidObservation("INVALID_OPERATION_KEY")
    body = _canonical_body(input_text, conversation_key)
    payload_sha256 = hashlib.sha256(body).hexdigest()
    return WorkspaceAgentTriggerPlan(
        channel_id=channel_id,
        operation_key=operation_key,
        payload_sha256=payload_sha256,
        idempotency_key=_derive_idempotency_key(
            channel_id=channel_id,
            operation_key=operation_key,
            payload_sha256=payload_sha256,
        ),
        _body=body,
    )


def _validate_token(value: str) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 8192
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
    ):
        raise InvalidObservation("INVALID_TOKEN")
    return value


def _validate_timeout(value: float) -> float:
    if (
        type(value) not in {int, float}
        or not math.isfinite(value)
        or not 0 < value <= 30
    ):
        raise InvalidObservation("INVALID_TIMEOUT")
    return float(value)


def trigger_once(
    *,
    plan: WorkspaceAgentTriggerPlan,
    token: str,
    timeout_seconds: float = 10.0,
    connection_factory: Callable = http.client.HTTPSConnection,
) -> TriggerObservation:
    """Submit exactly one POST and never retry, redirect, or infer no effect.

    Any transport failure after the effect boundary becomes TRIGGER_EFFECT_UNKNOWN.
    A received 202 establishes provider queue acceptance only. The supported
    contract exposes no response body/run id, so this path never reads a success
    body and never grants company acceptance or Wake acknowledgement.
    """

    if type(plan) is not WorkspaceAgentTriggerPlan:
        raise InvalidObservation("INVALID_TRIGGER_PLAN")
    plan.__post_init__()
    token = _validate_token(token)
    timeout = _validate_timeout(timeout_seconds)

    connection = None
    observation = TriggerObservation("unknown", "TRIGGER_EFFECT_UNKNOWN")
    try:
        connection = connection_factory(
            HOST,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        connection.request(
            "POST",
            f"/v1/workspace_agents/{plan.channel_id}/trigger",
            body=plan._body,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Cache-Control": "no-cache",
                "OpenAI-Beta": BETA_HEADER,
                "Idempotency-Key": plan.idempotency_key,
            },
        )
        response = connection.getresponse()
        status = response.status
        if status == 202:
            # Current supported contract: 202 has no response body or run id.
            # Never read or trust correlation bytes from an intermediary/old beta.
            observation = decode_trigger(202, b"")
        else:
            observation = decode_trigger(status, b"")
    except (OSError, http.client.HTTPException, ValueError, RecursionError):
        observation = TriggerObservation("unknown", "TRIGGER_EFFECT_UNKNOWN")
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                pass
    return observation


__all__ = [
    "BETA_HEADER",
    "MAX_TRIGGER_BODY_BYTES",
    "WorkspaceAgentTriggerPlan",
    "build_trigger_plan",
    "trigger_once",
]
