"""GBL-2 nudge sender tests (lane GBL, BUILD_PLAN).

nudge.py wraps the EXISTING ``GrokBotRoutineWakeDispatcher`` and the
``grok_bot_http.py`` composition (imported as-is, never edited) and sends
the closed-key ``mastermind.gbl.wake.v1`` body ONLY — no prose, no secrets
across the webhook (RULING §1, the Sept law B11).  The routine URL, bearer
key and poster are fakes; no request leaves the process.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from control_plane.wake_dispatcher import (
    TransportOutcome,
    WakeEffectUnknownError,
    WakeNudge,
)
from control_plane.wake_events import canonical_json_bytes
from integrations.executive_wake.grok_bot_http import (
    BoundedHttpResult,
    GrokRoutineCredential,
    grok_routine_target_digest,
)
from integrations.executive_wake.grok_bot_routine import (
    GrokBotRoutineWakeDispatcher,
    GrokRoutineWakeObservation,
)
from integrations.gbl.nudge import GblNudgeClient, GblNudgeSender

ASK_ID = "gb-" + "1" * 32
NATIVE_HANDLE = "routine-handle-fixture"
URL = "https://routine.example.invalid/hook"     # .invalid: never routable
BINDING_ID = "bind-gbl-fixture-1"
GENERATION = 3


class FakeCredentialSource:
    def __init__(self, generation=GENERATION):
        self.generation = generation

    def resolve(self, native_handle):
        return GrokRoutineCredential(
            url=URL,
            bearer_token="bearer-fixture-words",
            generation=self.generation,
            target_digest=grok_routine_target_digest(native_handle),
        )


class RecordingPoster:
    """BoundedJsonPoster fake; records the exact call, never does network."""

    def __init__(self, status_code=200, exception=None):
        self.status_code = status_code
        self.exception = exception
        self.calls: list[dict] = []

    async def post_json(self, *, url, headers, body, timeout_seconds,
                        max_response_bytes):
        self.calls.append({"url": url, "headers": dict(headers), "body": body,
                           "timeout_seconds": timeout_seconds,
                           "max_response_bytes": max_response_bytes})
        if self.exception is not None:
            raise self.exception
        return BoundedHttpResult(status_code=self.status_code, body=b"{}")


class FakeObservationSource:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.calls = 0

    async def observe_wake(self, *, native_handle, nudge_id):
        self.calls += 1
        return GrokRoutineWakeObservation(
            native_handle=native_handle, nudge_id=nudge_id,
            accepted=self.accepted)


def sender(poster, *, observation_source=None) -> GblNudgeSender:
    client = GblNudgeClient(FakeCredentialSource(), poster)
    dispatcher = GrokBotRoutineWakeDispatcher(
        client, observation_source=observation_source)
    return GblNudgeSender(dispatcher, binding_id=BINDING_ID,
                          binding_generation=GENERATION)


# ── The closed-key body is the only thing that crosses ──────────────────────


class TestClosedKeyBody:
    def test_posted_body_is_exactly_schema_ask_id_state(self):
        poster = RecordingPoster()
        receipt = sender(poster).send(ASK_ID, "ANSWERED", NATIVE_HANDLE)
        assert receipt.outcome is TransportOutcome.ACCEPTED
        assert len(poster.calls) == 1
        body = json.loads(poster.calls[0]["body"].decode("utf-8"))
        assert body == {"schema": "mastermind.gbl.wake.v1",
                        "ask_id": ASK_ID,
                        "state": "ANSWERED"}

    def test_body_bytes_are_canonical_and_secret_free(self):
        poster = RecordingPoster()
        sender(poster).send(ASK_ID, "QUESTION_AVAILABLE", NATIVE_HANDLE)
        expected = canonical_json_bytes(
            {"schema": "mastermind.gbl.wake.v1", "ask_id": ASK_ID,
             "state": "QUESTION_AVAILABLE"})
        assert poster.calls[0]["body"] == expected
        assert b"bearer-fixture-words" not in poster.calls[0]["body"]
        assert b"Bearer" not in poster.calls[0]["body"]

    def test_credential_rides_headers_only(self):
        poster = RecordingPoster()
        sender(poster).send(ASK_ID, "ANSWERED", NATIVE_HANDLE)
        headers = poster.calls[0]["headers"]
        assert headers["Authorization"] == "Bearer bearer-fixture-words"
        assert headers["Content-Type"] == "application/json"
        assert poster.calls[0]["url"] == URL

    def test_sender_validates_wake_before_any_post(self):
        poster = RecordingPoster()
        with pytest.raises(ValueError):
            sender(poster).send("not-an-ask-id", "ANSWERED", NATIVE_HANDLE)
        with pytest.raises(ValueError):
            sender(poster).send(ASK_ID, "OPEN", NATIVE_HANDLE)
        assert poster.calls == []


# ── The dispatcher law, wrapped not rewritten ───────────────────────────────


class TestDispatcherLaw:
    def test_deterministic_nudge_id_per_ask_and_state(self):
        first = sender(RecordingPoster()).send(ASK_ID, "ANSWERED", NATIVE_HANDLE)
        second = sender(RecordingPoster()).send(ASK_ID, "ANSWERED", NATIVE_HANDLE)
        other = sender(RecordingPoster()).send(ASK_ID, "QUESTION_AVAILABLE",
                                               NATIVE_HANDLE)
        first_id = dict(first.details)["nudge_id"]
        assert first_id.startswith("NUDGE-")
        assert dict(second.details)["nudge_id"] == first_id
        assert dict(other.details)["nudge_id"] != first_id

    def test_non_200_is_definite_no_start(self):
        poster = RecordingPoster(status_code=404)
        receipt = sender(poster).send(ASK_ID, "ANSWERED", NATIVE_HANDLE)
        assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
        assert len(poster.calls) == 1          # no provider-side retry, none ours

    def test_in_flight_loss_is_effect_unknown_never_resent(self):
        poster = RecordingPoster(exception=RuntimeError("connection lost mid-POST"))
        observation = FakeObservationSource(accepted=True)
        transport = sender(poster, observation_source=observation)
        with pytest.raises(WakeEffectUnknownError):
            transport.send(ASK_ID, "ANSWERED", NATIVE_HANDLE)
        assert len(poster.calls) == 1
        # Reconciliation observes run history; it performs no second POST.
        receipt = transport.reconcile(ASK_ID, "ANSWERED", NATIVE_HANDLE)
        assert receipt.outcome is TransportOutcome.ACCEPTED
        assert len(poster.calls) == 1
        assert observation.calls == 1

    def test_reconcile_without_observation_source_is_typed(self):
        transport = sender(RecordingPoster())
        with pytest.raises(WakeEffectUnknownError):
            transport.reconcile(ASK_ID, "ANSWERED", NATIVE_HANDLE)

    def test_wraps_the_existing_dispatcher_not_a_copy(self):
        from integrations.executive_wake.grok_bot_routine import (
            GrokBotRoutineWakeDispatcher as RealDispatcher,
        )
        dispatcher = RealDispatcher(GblNudgeClient(FakeCredentialSource(),
                                                   RecordingPoster()))
        transport = GblNudgeSender(dispatcher, binding_id=BINDING_ID,
                                   binding_generation=GENERATION)
        assert isinstance(transport.dispatcher, RealDispatcher)


class TestWakeNudgeShape:
    def test_built_nudge_targets_grok_transport_only(self):
        poster = RecordingPoster()
        transport = sender(poster)
        wake = transport.build_wake_nudge(ASK_ID, "ANSWERED", NATIVE_HANDLE)
        assert isinstance(wake, WakeNudge)
        assert wake.wake_transport == "grok-computer"
        assert wake.reasoning_surface == "grok-bot"
        assert wake.native_handle == NATIVE_HANDLE
        assert wake.obligation_ids == (ASK_ID, "ANSWERED")
        transport.send(ASK_ID, "ANSWERED", NATIVE_HANDLE)
        assert wake.nudge_id.startswith("NUDGE-")


# ── Repair round 1: a digest refusal is a TYPED pre-submit refusal ──────────
# Panel A LOW: build_wake's ValueError ("OPEN" is not a chain state) escapes
# untyped — at the bridge it would surface as INTERNAL_ERROR. Pre-submit
# means nothing was sent, so the caller must see WakePreSubmitError, the
# dispatcher's own definite no-start shape.


class TestRepairTypedPreSubmit:
    def test_invalid_state_is_typed_pre_submit_refusal(self):
        from control_plane.wake_dispatcher import WakePreSubmitError
        transport = sender(RecordingPoster())
        with pytest.raises(WakePreSubmitError):
            transport.build_wake_nudge(ASK_ID, "OPEN", NATIVE_HANDLE)

    def test_invalid_ask_id_is_typed_pre_submit_refusal(self):
        from control_plane.wake_dispatcher import WakePreSubmitError
        transport = sender(RecordingPoster())
        with pytest.raises(WakePreSubmitError):
            transport.build_wake_nudge("not-an-ask-id", "ANSWERED",
                                       NATIVE_HANDLE)
