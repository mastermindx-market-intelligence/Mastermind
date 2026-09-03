"""Dedicated PR-A CeoIngress plus the R0 diagnostic hot-state read.

This module preserves the closed submit/status validator, trusted-grounding/
replay/admission law, and dedicated response/error law for the future Slack
transport's local ingress, while adding R0's no-input diagnostic state read
and AD-ID1's separately versioned transport-neutral automated request frames
(adjudication §3, §7-§14; R1 security correction; R2 lifecycle correction).
It is deliberately narrow:

* **No generic dispatcher.**  There is no ``command/version/args`` shape here
  (unlike the broad Operator control protocol).  PR-A's submit/status schemas
  remain unchanged; R0 adds exactly one no-input diagnostic state schema.
* **Never opens its own Runtime, socket, or Git/Agent OS root.**  Every call
  here receives an already-open ``Runtime`` and an opaque, already-injected
  grounding provider; this module discovers nothing (§8.1, §10).  It therefore
  MUST NOT import :mod:`control_plane.executive_service` (that is the
  composition/transport layer that owns the socket, peer credentials, and
  process lifecycle — see that module's ``ExecutiveControlService`` dedicated
  ingress connection wrapper), :mod:`integrations.executive_mcp`,
  :mod:`control_plane.ceo_boot_packet`, ``subprocess``, or any Slack/MCP SDK.
* **The v1 mutation authority stays exactly one sink.**  Every accepted
  submission still reaches ``control_plane.ceo_intent.submit_intent`` and
  ``resolve_intent`` — this module adds admission/replay/error law around that
  existing sink, never a second one, and no new SQLite table/store/queue.
* **Errors are typed and closed (§12, R1 §3/§4).**  :class:`CeoIngressError`
  carries one of :data:`ERROR_CODES` plus a message.  For the four dependency-
  failure codes named in the R1 security correction, the wire message is a
  FIXED, reviewed literal — never the underlying exception's text — because
  ``common.redaction.sanitize_external_text`` deliberately preserves
  filesystem paths and URLs and is therefore not a sufficient guarantee at
  this boundary (R1 §3.1).  A caller-validation refusal derived entirely from
  the caller's OWN already-bounded request fields (e.g. "objective must be a
  non-empty string") may remain specific — that text originates from the
  caller's own submission, never from a grounding/backend/internal dependency.
* **Replay/grounding/status order is load-bearing (§11).**  See
  :func:`_handle_submit` and :func:`_handle_status`; the order of operations
  there is not incidental and must not be reordered.

Usage
-----
    from control_plane import executive_ceo_ingress as ceo_ingress
    result = await ceo_ingress.handle_frame(
        parsed_json_object,
        runtime=runtime,             # already-open control_plane.executive_runtime.Runtime
        grounding_provider=provider, # opaque object with a sync .observe() -> {...}
        workspace_root=workspace_root,
    )
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from control_plane import ceo_intent
from control_plane import ceo_request
from control_plane import executive_hot_state as hot_state
from control_plane.executive_authority import AuthorityPolicyError
from control_plane.executive_runtime import (
    StateConflict,
    normalize_executive_dialogue_source,
)

__all__ = [
    "BOOT_PACKET_SCHEMA",
    "CeoIngressError",
    "ERROR_CODES",
    "GroundingProvider",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "STATE_SCHEMA",
    "STATUS_ID_RE",
    "STATUS_SCHEMA",
    "STATUS_SCHEMA_V2",
    "SUBMIT_SCHEMA",
    "SUBMIT_SCHEMA_V2",
    "handle_frame",
]


# ---------------------------------------------------------------------------
# wire schema/bounds (adjudication §7)
# ---------------------------------------------------------------------------

#: §7.1.
SUBMIT_SCHEMA = "mastermind.executive_ceo_ingress_submit.v1"
#: §7.2.
STATUS_SCHEMA = "mastermind.executive_ceo_ingress_status.v1"
#: AD-ID1 separately versioned, transport-neutral automated admission.
SUBMIT_SCHEMA_V2 = "mastermind.executive_ceo_ingress_submit.v2"
STATUS_SCHEMA_V2 = "mastermind.executive_ceo_ingress_status.v2"
#: R0 §3 — the only post-PR-A additive diagnostic frame.
STATE_SCHEMA = hot_state.STATE_REQUEST_SCHEMA

#: §7.3 — request line maximum, including frame/newline budget.  Separate from
#: (far below) the broad Operator ``ServiceConfig.max_request_bytes`` ceiling.
MAX_REQUEST_BYTES = 8192
#: §7.3/§7.4 — response line maximum.  A successful canonical receipt above
#: this bound is a protocol/backend defect and must refuse, never truncate.
MAX_RESPONSE_BYTES = 32768

#: §7.2 — exact status id validation.
STATUS_ID_RE = re.compile(r"^slack-[0-9a-f]{32}$")

#: §10 — the one legal boot-packet schema string a grounding observation may
#: name.  A literal here (never an import of ``ceo_boot_packet.SCHEMA``) is
#: deliberate: this module must not depend on, or be able to discover, that
#: module (§10 bullet "does not import ... ceo_boot_packet.build_packet").
BOOT_PACKET_SCHEMA = "mastermind.ceo_boot_packet.v1"

_SUBMIT_TOP_KEYS = frozenset({"schema", "observed_grounding", "request"})
_STATUS_TOP_KEYS = frozenset({"schema", "intent_id"})
_SUBMIT_V2_TOP_KEYS = frozenset(
    {"schema", "request_ref", "observed_grounding", "request"}
)
_SUBMIT_V2_TOP_KEYS_WITH_SOURCE = _SUBMIT_V2_TOP_KEYS | frozenset(
    {"dialogue_source"}
)
_STATUS_V2_TOP_KEYS = frozenset({"schema", "request_ref"})
_STATE_TOP_KEYS = frozenset({"schema"})
_GROUNDING_KEYS = frozenset({"mastermind_sha", "macro_sha", "boot_packet_schema"})


# ---------------------------------------------------------------------------
# closed error vocabulary (adjudication §12; R1 §3/§4)
# ---------------------------------------------------------------------------

ERROR_CODES = frozenset(
    {
        "peer_credentials_unavailable",
        "peer_denied",
        "ingress_unavailable",
        "unsupported_ingress_schema",
        "request_too_large",
        "response_too_large",
        "invalid_json",
        "invalid_input",
        "invalid_intent_id",
        "not_found",
        "grounding_unavailable",
        "grounding_mismatch",
        "grounding_changed",
        "operation_conflict",
        "authority_refused",
        "backend_unavailable",
        "backend_refused",
        "internal_error",
    }
)

#: R1 §3.2 — FIXED, code-specific wire text for the four dependency-failure
#: codes.  Never derived from the triggering exception: an exception carrying
#: a host path, URL, or secret-shaped value must never reach the wire, and
#: ``sanitize_external_text`` alone does not guarantee that (it intentionally
#: preserves paths/URLs — R1 §3.1).  A mutation that replaces one of these
#: literals with ``sanitize_external_text(str(exc))`` must be caught by
#: ``tests/test_executive_ceo_ingress.py``'s no-path/no-secret tests.
_FIXED_DEPENDENCY_MESSAGES: dict[str, str] = {
    "grounding_unavailable": "trusted grounding is unavailable",
    "backend_unavailable": "Executive CEO ingress backend is unavailable",
    "backend_refused": "Executive CEO ingress backend refused the request",
    "internal_error": "Executive CEO ingress failed",
}

#: Additional fixed, reviewed text for the remaining classification codes that
#: are not raw dependency-failure forwarding but must still never echo a
#: backend/provider value.  Kept separate from the R1-minimum table above so
#: that table stays a literal transcription of the R1 text.
_FIXED_CLASSIFICATION_MESSAGES: dict[str, str] = {
    "authority_refused": "the requested execution authority was refused",
    "operation_conflict": "intent_id was already accepted with a different request",
    "grounding_mismatch": "observed grounding does not match current trusted grounding",
    "grounding_changed": "trusted grounding changed immediately before submission",
}


class CeoIngressError(Exception):
    """One typed CeoIngress refusal: a closed ``code`` plus its wire ``message``.

    ``executive_service.ExecutiveControlService``'s dedicated ingress
    connection handler reads only ``.code``/``.message`` to build the wire
    envelope — never ``str(exc)`` of some other underlying cause — which is
    what keeps a forwarded dependency exception's text off the wire.
    """

    def __init__(self, code: str, message: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown CeoIngress error code {code!r}")
        super().__init__(message)
        self.code = code
        self.message = message


def _dependency_failure(code: str) -> CeoIngressError:
    return CeoIngressError(code, _FIXED_DEPENDENCY_MESSAGES[code])


def _classification_failure(code: str) -> CeoIngressError:
    return CeoIngressError(code, _FIXED_CLASSIFICATION_MESSAGES[code])


# ---------------------------------------------------------------------------
# trusted grounding provider (adjudication §10)
# ---------------------------------------------------------------------------


class GroundingProvider(Protocol):
    """Opaque, injected grounding source.

    ``observe()`` is synchronous business code (called via ``asyncio.to_thread``
    so a real, possibly-blocking observation never stalls the event loop); its
    return value is validated by :func:`_coerce_grounding_shape` below and
    never trusted structurally.  Exact class/function name implementing this
    protocol is builder-owned (§10) — this is a structural ``Protocol``, not a
    base class a provider must inherit.
    """

    def observe(self) -> Mapping[str, str]: ...


def _coerce_grounding_shape(value: Any) -> dict[str, str] | None:
    """Return the exact three-string grounding shape, or ``None`` if invalid.

    Never raises: callers decide the error code (caller-supplied
    ``observed_grounding`` refuses ``invalid_input``; a malformed *provider*
    observation refuses ``grounding_unavailable`` — same shape check, two
    different codes depending on WHO supplied the malformed value).
    """

    if not isinstance(value, Mapping):
        return None
    if {str(key) for key in value} != _GROUNDING_KEYS:
        return None
    mastermind_sha = value.get("mastermind_sha")
    macro_sha = value.get("macro_sha")
    schema = value.get("boot_packet_schema")
    if not isinstance(mastermind_sha, str) or ceo_intent.SHA_RE.fullmatch(mastermind_sha) is None:
        return None
    if not isinstance(macro_sha, str) or ceo_intent.SHA_RE.fullmatch(macro_sha) is None:
        return None
    if not isinstance(schema, str) or schema != BOOT_PACKET_SCHEMA:
        return None
    return {
        "mastermind_sha": mastermind_sha,
        "macro_sha": macro_sha,
        "boot_packet_schema": schema,
    }


def _validate_observed_grounding(value: Any) -> dict[str, str]:
    """Validate the caller-claimed ``observed_grounding`` (§7.1).

    Caller-supplied and already bounded by the 8 KiB frame ceiling, so naming
    the field is fine (R1 §3.2); the actual value is never echoed.
    """

    shape = _coerce_grounding_shape(value)
    if shape is None:
        raise CeoIngressError(
            "invalid_input",
            "observed_grounding must contain exactly mastermind_sha, macro_sha "
            "(each 40 lowercase hex characters), and boot_packet_schema "
            f"({BOOT_PACKET_SCHEMA!r})",
        )
    return shape


async def _observe_trusted_grounding(provider: GroundingProvider) -> dict[str, str]:
    """Call the injected provider once; malformed output/failure -> opaque refusal.

    Never logs or forwards the provider's own exception text (§10, R1 §3.2):
    whatever went wrong inside an opaque first-party grounding source could
    itself carry a host path or other sensitive detail.
    """

    try:
        raw = await asyncio.to_thread(provider.observe)
    except Exception as exc:  # dependency boundary: opaque by design (R1 §3)
        raise _dependency_failure("grounding_unavailable") from exc
    shape = _coerce_grounding_shape(raw)
    if shape is None:
        raise _dependency_failure("grounding_unavailable")
    return shape


# ---------------------------------------------------------------------------
# backend/runtime call wrappers
# ---------------------------------------------------------------------------


async def _backend_call(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run one blocking RuntimeStore read off the event loop.

    Any non-:class:`ceo_intent.CeoIntentError` failure here is an
    infrastructure-level backend problem, never a caller mistake and never
    something this module can classify further -> opaque ``backend_unavailable``.
    """

    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except Exception as exc:
        raise _dependency_failure("backend_unavailable") from exc


async def _resolve_or_refuse(runtime: Any, intent_id: str) -> dict[str, Any]:
    """``ceo_intent.resolve_intent`` off the event loop; corrupt event -> refusal.

    §11.1 step 5 / §17.3: "corrupted durable event is backend/integrity
    refusal, not not_found, never silent repair."  A durable event is already
    known to exist by the time this is called; any :class:`CeoIntentError`
    reaching here is therefore an integrity defect in that record, not a
    lookup miss.
    """

    try:
        return await asyncio.to_thread(ceo_intent.resolve_intent, runtime, intent_id)
    except ceo_intent.CeoIntentError as exc:
        raise _dependency_failure("backend_refused") from exc
    except Exception as exc:
        raise _dependency_failure("backend_unavailable") from exc


def _classify_authority_or_backend(exc: "ceo_intent.CeoIntentError") -> CeoIngressError:
    """§12.1 — traverse the typed cause chain; never match English text.

    ``CeoIntentError`` caused by ``StateConflict`` caused by
    ``AuthorityDenied``/``AuthorityPolicyError`` classifies as
    ``authority_refused``.  Everything else with no durable sibling event is a
    bounded ``backend_refused`` according to its actual type.
    """

    cause = exc.__cause__
    if isinstance(cause, StateConflict) and isinstance(cause.__cause__, AuthorityPolicyError):
        return _classification_failure("authority_refused")
    return _dependency_failure("backend_refused")


def _finalize_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """§17.6 — a receipt claiming ``dispatched`` true is a backend contract
    defect and must never be presented as success."""

    if receipt.get("dispatched") is not False:
        raise _dependency_failure("backend_refused")
    return dict(receipt)


async def _submit(
    runtime: Any,
    envelope: Mapping[str, Any],
    workspace_root: "Path | str",
    submitter: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Call the one v1 mutation sink; classify a raised refusal per §11.3/§12.1."""

    try:
        if submitter is not None:
            return dict(await asyncio.to_thread(submitter, envelope))
        return await asyncio.to_thread(
            ceo_intent.submit_intent,
            runtime,
            envelope,
            workspace_root=str(workspace_root),
        )
    except ceo_intent.CeoIntentConflict as exc:
        # A durable sibling with the same request fingerprint may still carry
        # different immutable admission provenance.  That is a real identity
        # conflict, never a concurrency winner that can be reconciled by the
        # envelope fingerprint alone.
        raise _classification_failure("operation_conflict") from exc
    except ceo_intent.CeoIntentError as exc:
        # §11.3 concurrent winner: repeat the exact command-id lookup and
        # canonical resolve; classify from the DURABLE fingerprint, never from
        # the raised exception's text.
        intent_id = str(envelope["intent_id"])
        command_id = ceo_intent.command_id_for(intent_id)
        settled = await _backend_call(runtime.store.find_event_by_command_id, command_id)
        if settled is not None:
            resolved = await _resolve_or_refuse(runtime, intent_id)
            candidate_fingerprint = ceo_intent.intent_fingerprint(envelope)
            if resolved.get("fingerprint") != candidate_fingerprint:
                raise _classification_failure("operation_conflict") from exc
            resolved = dict(resolved)
            resolved["duplicate"] = True
            return resolved
        raise _classify_authority_or_backend(exc) from exc
    except Exception as exc:
        raise _dependency_failure("backend_unavailable") from exc


def _build_envelope(
    normalized: Mapping[str, Any],
    *,
    intent_id: str,
    workspace_root: "Path | str",
    grounding: Mapping[str, str],
    strict_v2: bool = False,
    dialogue_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        strict_v2 = strict_v2 or dialogue_source is not None
        envelope = ceo_request.build_trusted_envelope(
            normalized,
            intent_id=intent_id,
            workspace_root=str(workspace_root),
            grounding=grounding,
        )
        if strict_v2:
            envelope["schema"] = ceo_intent.INTENT_SCHEMA_V2
            envelope["intent_kind"] = "executive_coo_cycle"
            envelope["business_impact"] = "routine"
            if dialogue_source is not None:
                envelope["dialogue_source"] = dict(dialogue_source)
        return ceo_intent.validate_intent(envelope)
    except ceo_intent.CeoIntentError as exc:
        raise CeoIngressError("invalid_input", str(exc)) from exc
    except ceo_request.CeoRequestError as exc:
        # Input was already normalized/validated above; reaching here is a
        # defect in trusted derivation itself, never the caller's fault.
        raise _dependency_failure("internal_error") from exc


# ---------------------------------------------------------------------------
# submit frame (adjudication §7.1, §11.2)
# ---------------------------------------------------------------------------


async def _handle_submit(
    parsed: Mapping[str, Any],
    *,
    runtime: Any,
    grounding_provider: GroundingProvider,
    workspace_root: "Path | str",
    submitter: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """§11.2 submit pre-reconciliation — this order is load-bearing."""

    # 1. validate outer frame (caller) and normalize the high-level request.
    observed = _validate_observed_grounding(parsed["observed_grounding"])
    try:
        normalized = ceo_request.normalize_high_level_request(parsed["request"])
    except ceo_request.CeoRequestInvalid as exc:
        # Derived entirely from the caller's own bounded request fields.
        raise CeoIngressError("invalid_input", exc.message) from exc
    except ceo_request.CeoRequestInternalError as exc:
        raise _dependency_failure("internal_error") from exc

    # 2. derive the deterministic Slack intent id.
    try:
        intent_id = ceo_request.slack_intent_id(normalized["operation_key"])
    except ceo_request.CeoRequestError as exc:
        raise _dependency_failure("internal_error") from exc

    return await _handle_normalized_submit(
        normalized,
        observed=observed,
        intent_id=intent_id,
        runtime=runtime,
        grounding_provider=grounding_provider,
        workspace_root=workspace_root,
        submitter=submitter,
    )


async def _handle_submit_v2(
    parsed: Mapping[str, Any],
    *,
    runtime: Any,
    grounding_provider: GroundingProvider,
    workspace_root: "Path | str",
    submitter: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """AD-ID1 automated submit with the same load-bearing v1 order."""

    # 1. validate the caller frame and semantic request before deriving the
    #    canonical request-instance identity.
    observed = _validate_observed_grounding(parsed["observed_grounding"])
    try:
        normalized = ceo_request.normalize_automated_request(parsed["request"])
        intent_id = ceo_request.automated_intent_id(parsed["request_ref"])
    except ceo_request.CeoRequestInvalid as exc:
        raise CeoIngressError("invalid_input", exc.message) from exc
    except ceo_request.CeoRequestInternalError as exc:
        raise _dependency_failure("internal_error") from exc

    dialogue_source = None
    if "dialogue_source" in parsed:
        try:
            dialogue_source = normalize_executive_dialogue_source(
                parsed["dialogue_source"],
                work_ref=str(normalized.get("workstream") or ""),
            ).to_dict()
        except StateConflict as exc:
            raise CeoIngressError("invalid_input", str(exc)) from exc

    return await _handle_normalized_submit(
        normalized,
        observed=observed,
        intent_id=intent_id,
        runtime=runtime,
        grounding_provider=grounding_provider,
        workspace_root=workspace_root,
        submitter=submitter,
        # The automated ingress schema predates strict-v2 COO admission.
        # Preserve its existing v1 sink unless an admission-owned dialogue
        # source explicitly opts this request into the strict-v2 root.
        strict_v2=dialogue_source is not None,
        dialogue_source=dialogue_source,
    )


async def _handle_normalized_submit(
    normalized: Mapping[str, Any],
    *,
    observed: Mapping[str, str],
    intent_id: str,
    runtime: Any,
    grounding_provider: GroundingProvider,
    workspace_root: "Path | str",
    submitter: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    strict_v2: bool = False,
    dialogue_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Shared replay/grounding/sink law after version-specific validation."""

    # 3. construct the candidate envelope/fingerprint using the CALLER's
    #    observed_grounding claim ONLY for comparison (never for submission).
    candidate_envelope = _build_envelope(
        normalized,
        intent_id=intent_id,
        workspace_root=workspace_root,
        grounding=observed,
        strict_v2=strict_v2,
        dialogue_source=dialogue_source,
    )
    candidate_fingerprint = ceo_intent.intent_fingerprint(candidate_envelope)

    # 4. exact command-id lookup.
    command_id = ceo_intent.command_id_for(intent_id)
    existing = await _backend_call(runtime.store.find_event_by_command_id, command_id)

    # 5. a durable event already exists: resolve it canonically BEFORE any
    #    current grounding-provider call.
    if existing is not None:
        resolved = await _resolve_or_refuse(runtime, intent_id)
        if resolved.get("fingerprint") != candidate_fingerprint:
            raise _classification_failure("operation_conflict")
        # Durable fingerprint matches: this is a reconciliation, not a new
        # grounding-authorized creation.  Call the existing sink again to
        # obtain the normal canonical duplicate receipt.
        receipt = await _submit(
            runtime,
            candidate_envelope,
            workspace_root,
            submitter,
        )
        return _finalize_receipt(receipt)

    # 6. only when no canonical event exists, observe current trusted grounding.
    trusted = await _observe_trusted_grounding(grounding_provider)

    # 7. require exact equality with the caller's claim -> else grounding_mismatch.
    if trusted != observed:
        raise _classification_failure("grounding_mismatch")

    # 8. derive/revalidate the canonical envelope from TRUSTED grounding (never
    #    silently reuse the caller's claimed envelope for the actual submit).
    trusted_envelope = _build_envelope(
        normalized,
        intent_id=intent_id,
        workspace_root=workspace_root,
        grounding=trusted,
        strict_v2=strict_v2,
        dialogue_source=dialogue_source,
    )

    # 9. call the SAME provider again immediately before the first canonical
    #    submit; identity movement -> grounding_changed, zero Job.
    reobserved = await _observe_trusted_grounding(grounding_provider)
    if reobserved != trusted:
        raise _classification_failure("grounding_changed")

    # 11. call the existing v1 mutation sink.
    receipt = await _submit(runtime, trusted_envelope, workspace_root, submitter)
    return _finalize_receipt(receipt)


# ---------------------------------------------------------------------------
# status frame (adjudication §7.2, §11.1)
# ---------------------------------------------------------------------------


async def _handle_status(parsed: Mapping[str, Any], *, runtime: Any) -> dict[str, Any]:
    """§11.1 exact status lookup — this order is load-bearing."""

    intent_id = parsed["intent_id"]
    if not isinstance(intent_id, str) or STATUS_ID_RE.fullmatch(intent_id) is None:
        raise CeoIngressError(
            "invalid_intent_id", f"intent_id must match {STATUS_ID_RE.pattern!r}"
        )
    return await _resolve_status_intent(runtime, intent_id)


async def _handle_status_v2(parsed: Mapping[str, Any], *, runtime: Any) -> dict[str, Any]:
    """Resolve status from trusted request identity, never a caller intent id."""

    try:
        intent_id = ceo_request.automated_intent_id(parsed["request_ref"])
    except ceo_request.CeoRequestInvalid as exc:
        raise CeoIngressError("invalid_input", exc.message) from exc
    except ceo_request.CeoRequestInternalError as exc:
        raise _dependency_failure("internal_error") from exc
    return await _resolve_status_intent(runtime, intent_id)


async def _resolve_status_intent(runtime: Any, intent_id: str) -> dict[str, Any]:
    """Shared exact command-id lookup and canonical durable resolution."""

    # 1-2. derive command_id; use existing RuntimeStore API for that one id.
    command_id = ceo_intent.command_id_for(intent_id)
    event = await _backend_call(runtime.store.find_event_by_command_id, command_id)
    # 3. no event -> true not_found.
    if event is None:
        raise CeoIngressError("not_found", f"no accepted CEO intent named {intent_id!r}")
    # 4-5. event exists -> resolve canonically; resolution failure despite an
    #      event is a bounded backend_refused/integrity defect, never not_found.
    resolved = await _resolve_or_refuse(runtime, intent_id)
    return _finalize_receipt(resolved)


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------


def _exact_top_keys(value: Any, name: str, expected: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CeoIngressError("invalid_input", f"{name} must be a JSON object")
    keys = {str(key) for key in value}
    if keys != expected:
        raise CeoIngressError(
            "invalid_input", f"{name} must contain exactly {sorted(expected)}"
        )
    return value


def _require_v2_admission(*, service_state: Any, ceo_ingress_armed: bool) -> None:
    """Reassert the existing host-owned gate for additive v2 schemas.

    The composition service's historical schema discriminator is byte-frozen
    outside AD-ID1's authorized files, so v2 fails closed here using the same
    host-supplied arming/state values.  Invocation already occurs only after
    the service startup-ready latch has opened.
    """

    if not ceo_ingress_armed or service_state not in {"READY", "AWAITING_CANARY"}:
        raise CeoIngressError(
            "ingress_unavailable",
            "Executive CEO ingress is not currently admitting requests",
        )


async def handle_frame(
    parsed: Any,
    *,
    runtime: Any,
    grounding_provider: GroundingProvider,
    workspace_root: "Path | str",
    service_state: Any = None,
    ceo_ingress_armed: bool = False,
    submitter: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate and dispatch one already-parsed JSON frame (§7).

    There is no generic dispatcher: exactly five closed ``schema`` values are
    legal.  The caller applies PR-A's full admission predicate to v1 submit/
    status before invoking this function; AD-ID1 reasserts that same predicate
    for v2 inside this authorized module, while the R0 state branch is read-only
    and uses only current in-process values supplied by the same service.
    Everything else — including a recognized schema whose object shape is
    wrong — refuses via :class:`CeoIngressError` with a code from
    :data:`ERROR_CODES`.  The caller (``executive_service``'s dedicated ingress
    connection handler) owns the raw socket framing (newline/oversize/UTF-8/
    JSON-syntax) and peer authentication; this function receives an already
    UTF-8-decoded, already ``json.loads``-parsed Python object.
    """

    if not isinstance(parsed, Mapping):
        raise CeoIngressError("invalid_input", "request frame must be a JSON object")
    schema = parsed.get("schema")
    if schema == SUBMIT_SCHEMA:
        _exact_top_keys(parsed, "submit frame", _SUBMIT_TOP_KEYS)
        return await _handle_submit(
            parsed,
            runtime=runtime,
            grounding_provider=grounding_provider,
            workspace_root=workspace_root,
            submitter=submitter,
        )
    if schema == STATUS_SCHEMA:
        _exact_top_keys(parsed, "status frame", _STATUS_TOP_KEYS)
        return await _handle_status(parsed, runtime=runtime)
    if schema == SUBMIT_SCHEMA_V2:
        _require_v2_admission(
            service_state=service_state, ceo_ingress_armed=ceo_ingress_armed
        )
        parsed_keys = frozenset(parsed)
        if parsed_keys not in {
            _SUBMIT_V2_TOP_KEYS,
            _SUBMIT_V2_TOP_KEYS_WITH_SOURCE,
        }:
            allowed = (
                _SUBMIT_V2_TOP_KEYS_WITH_SOURCE
                if "dialogue_source" in parsed
                else _SUBMIT_V2_TOP_KEYS
            )
            _exact_top_keys(parsed, "submit v2 frame", allowed)
        return await _handle_submit_v2(
            parsed,
            runtime=runtime,
            grounding_provider=grounding_provider,
            workspace_root=workspace_root,
            submitter=submitter,
        )
    if schema == STATUS_SCHEMA_V2:
        _require_v2_admission(
            service_state=service_state, ceo_ingress_armed=ceo_ingress_armed
        )
        _exact_top_keys(parsed, "status v2 frame", _STATUS_V2_TOP_KEYS)
        return await _handle_status_v2(parsed, runtime=runtime)
    if schema == STATE_SCHEMA:
        _exact_top_keys(parsed, "state frame", _STATE_TOP_KEYS)
        try:
            return await hot_state.build_hot_state(
                runtime=runtime,
                grounding_provider=grounding_provider,
                service_state=service_state,
                ceo_ingress_armed=ceo_ingress_armed,
            )
        except hot_state.HotStateTooLarge as exc:
            raise CeoIngressError(
                "response_too_large", "Executive hot-state exceeds byte limit"
            ) from exc
    raise CeoIngressError(
        "unsupported_ingress_schema",
        "schema must be one of "
        f"{sorted([STATE_SCHEMA, STATUS_SCHEMA, STATUS_SCHEMA_V2, SUBMIT_SCHEMA, SUBMIT_SCHEMA_V2])}",
    )
