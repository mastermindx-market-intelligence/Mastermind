"""GBL nudge sender — the existing Grok routine Wake fabric, wrapped (GBL-2).

Nothing here rewrites the wake stack: ``GrokBotRoutineWakeDispatcher``
(``integrations/executive_wake/grok_bot_routine.py``) and the
``grok_bot_http.py`` composition are imported as-is and never edited.  The
one GBL difference is the POST body: it is EXACTLY the closed-key
``mastermind.gbl.wake.v1`` wake — ``{schema, ask_id, state}`` and nothing
else (RULING §1, ARCHITECTURE §3, the Sept law B11: no prose, no secrets,
no substance across the webhook; a stolen key can at worst start a run
that fetches nothing).

Laws preserved by the wrap (B3):

* one submission per call, ACCEPTED never DELIVERED, no retry, no failover;
* an in-flight loss is ``WakeEffectUnknownError`` — reconcile by run
  history (``reconcile`` observes; it performs no second POST);
* a non-200 response is a definite no-start (A7: 200 = accepted and
  started, nothing else); no provider-side retry exists, and none is added.

The bearer key lives in the Authorization header, resolved by the injected
credential source at call time; it never appears in the body and this
module never logs it.
"""
from __future__ import annotations

import asyncio
from typing import Any, Mapping, Sequence

from control_plane.wake_dispatcher import (
    TransportOutcome,
    WakeNudge,
    WakePreSubmitError,
    mint_nudge_id,
)
from control_plane.wake_events import canonical_json_bytes
from common.gbl_contract import GBLContractError, build_wake
from integrations.executive_wake.grok_bot_http import (
    MAX_RESPONSE_BYTES,
    POST_TIMEOUT_SECONDS,
    BoundedHttpResult,
    GrokRoutineCredential,
    grok_routine_target_digest,
)
from integrations.executive_wake.grok_bot_routine import (
    GrokBotRoutineWakeDispatcher,
    GrokRoutineWakeObservation,
)

GBL_SESSION_ALIAS = "GBL-BRIDGE"


class GblNudgeClient:
    """:class:`GrokRoutineWakeClient` whose one bounded POST carries exactly
    the closed-key GBL wake body.  The credential separation, digest/generation
    binding, request ceilings and status law are the imported
    ``grok_bot_http.py`` discipline; only the body is GBL's."""

    def __init__(self, credential_source: Any, poster: Any) -> None:
        if credential_source is None or not callable(
                getattr(credential_source, "resolve", None)):
            raise ValueError("GBL nudge client requires a credential source")
        if poster is None or not callable(getattr(poster, "post_json", None)):
            raise ValueError("GBL nudge client requires a poster")
        self.credential_source = credential_source
        self.poster = poster

    async def deliver_wake(
        self,
        *,
        native_handle: str,
        nudge_id: str,
        binding_id: str,
        binding_generation: int,
        opaque_ids: Sequence[str],
    ) -> GrokRoutineWakeObservation:
        # The GBL wake fields ride the dispatcher's opaque ids: exactly
        # (ask_id, state).  Anything else is a wiring error — refuse before
        # the credential is even resolved.
        if (isinstance(opaque_ids, (str, bytes, bytearray))
                or not isinstance(opaque_ids, Sequence)
                or len(opaque_ids) != 2):
            raise WakePreSubmitError("GBL wake requires exactly ask_id and state")
        try:
            wake = build_wake(opaque_ids[0], opaque_ids[1])
        except ValueError:
            raise WakePreSubmitError("GBL wake body is invalid before submission") from None
        target_digest = grok_routine_target_digest(native_handle)

        try:
            credential = self.credential_source.resolve(native_handle)
        except Exception:
            raise WakePreSubmitError(
                "GBL routine credential unavailable before submission") from None
        if not isinstance(credential, GrokRoutineCredential):
            raise WakePreSubmitError(
                "GBL routine credential unavailable before submission")
        if credential.target_digest != target_digest:
            raise WakePreSubmitError(
                "GBL routine credential target mismatch before submission")
        if credential.generation != binding_generation:
            raise WakePreSubmitError(
                "GBL routine credential generation mismatch before submission")

        body = canonical_json_bytes(wake)
        submission_cancelled = False
        result = None
        try:
            result = await self.poster.post_json(
                url=credential.url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {credential.bearer_token}",
                },
                body=body,
                timeout_seconds=POST_TIMEOUT_SECONDS,
                max_response_bytes=MAX_RESPONSE_BYTES,
            )
        except asyncio.CancelledError:
            submission_cancelled = True
        except Exception:
            # The POST began and its result is unavailable: effect unknown.
            # The dispatcher converts this into WakeEffectUnknownError; the
            # only lawful next step is reconcile(), never another POST.
            raise RuntimeError(
                "GBL routine submission result is unavailable after POST began"
            ) from None
        if submission_cancelled:
            raise asyncio.CancelledError()
        if not isinstance(result, BoundedHttpResult):
            raise RuntimeError("GBL routine poster returned an invalid result")
        if result.status_code != 200:
            raise WakePreSubmitError(
                "GBL routine provider reported a definite no-start outcome")
        return GrokRoutineWakeObservation(
            native_handle=native_handle,
            nudge_id=nudge_id,
            accepted=True,
            request_id=result.request_id,
        )


class GblNudgeSender:
    """Bridge-facing wrapper: builds the WakeNudge for one GBL wake and
    submits it through the EXISTING dispatcher.  The nudge id is the
    canonical wake-fabric mint over (target digest, ask, state), so a
    redelivered nudge keeps its identity and reconcile() observes the same
    submission."""

    def __init__(self, dispatcher: GrokBotRoutineWakeDispatcher, *,
                 binding_id: str, binding_generation: int) -> None:
        if not isinstance(dispatcher, GrokBotRoutineWakeDispatcher):
            raise ValueError("GBL nudge sender wraps the existing dispatcher")
        self.dispatcher = dispatcher
        self._binding_id = binding_id
        self._binding_generation = binding_generation

    def build_wake_nudge(self, ask_id: str, state: str,
                         native_handle: str) -> WakeNudge:
        try:
            wake = build_wake(ask_id, state)  # closed-key validation, GBL-1 law
        except GBLContractError as err:
            # Typed pre-submit refusal (repair LOW): a digest/state rejection
            # happens BEFORE any bytes cross — the dispatcher's own definite
            # no-start shape, never a bare ValueError surfacing as
            # INTERNAL_ERROR at the bridge.
            raise WakePreSubmitError(
                f"gb wake contract refused: {err.code}",
                outcome=TransportOutcome.TARGET_UNAVAILABLE,
                reason_code="target_unavailable") from None
        digest = grok_routine_target_digest(native_handle)
        nudge_id = mint_nudge_id(digest, (f"{ask_id}:{state}",))
        return WakeNudge(
            session_alias=GBL_SESSION_ALIAS,
            reasoning_surface="grok-bot",          # the dispatcher's surface
            wake_transport="grok-computer",        # the dispatcher's transport
            binding_id=self._binding_id,
            binding_generation=self._binding_generation,
            native_handle=native_handle,
            account_label=None,
            destination_digest=digest,
            obligation_ids=(ask_id, state),        # the wake body fields
            attempt_command_ids=(),
            nudge_id=nudge_id,
        )

    def send(self, ask_id: str, state: str, native_handle: str):
        """One submission.  Raises WakeEffectUnknownError when the POST's
        effect is unknown — call reconcile(), never send() again."""
        return asyncio.run(
            self.dispatcher.nudge(self.build_wake_nudge(ask_id, state,
                                                        native_handle)))

    def reconcile(self, ask_id: str, state: str, native_handle: str):
        """Observe the exact attempted nudge (run history) without another
        submission; requires an observation source on the dispatcher."""
        return asyncio.run(
            self.dispatcher.reconcile(self.build_wake_nudge(ask_id, state,
                                                            native_handle)))


__all__ = [
    "GBL_SESSION_ALIAS",
    "GblNudgeClient",
    "GblNudgeSender",
]
