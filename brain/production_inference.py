"""Exclusive no-tools inference through Macro's existing production-mode owner.

This is a consumer adapter, not Fabric admission or a subscription pool. Macro
owns mode eligibility, pinned destinations/models, credentials, provider health
and usage accounting. An absent owner or failed mode never invokes another
backend. The existing owner has no durable operation/idempotency contract; this
adapter must not manufacture one or treat its telemetry as an execution claim.
"""
from __future__ import annotations

import os

_MAX_OUTPUT_TOKENS = 32768


def _configured_mode() -> str | None:
    # Presence is intentional: an empty override must not select another mode.
    if "BOT_LLM_PRODUCTION_MODE" in os.environ:
        mode = os.environ["BOT_LLM_PRODUCTION_MODE"]
    else:
        from brain import cli_bridge

        mode = cli_bridge._cfg().get("production_mode")
    return mode if isinstance(mode, str) and mode else None


def _owner():
    import bot  # noqa: F401 — incumbent vendored-Macro import bootstrap
    from engine import provider_production_modes

    return provider_production_modes


def available() -> bool:
    """Configuration readiness only; no provider probe or capacity reservation."""
    try:
        mode = _configured_mode()
        return bool(mode and _owner().resolve_mode(mode).state == "configured")
    except Exception:
        return False


def _record_turn(receipt, *, user: str, role: str, seat, record_book) -> None:
    """Preserve caller attribution in the incumbent response log, not a cost ledger."""
    from brain import thinking_log
    from brain.cli_bridge import _ROLE_BOOK

    thinking_log.log_turn_async(
        question=user,
        answer=receipt.text if receipt.ok else "",
        model=receipt.model,
        mode=receipt.mode_id,
        backend="production_mode",
        seat=seat or role,
        book=record_book or _ROLE_BOOK.get(str(role).lower(), "flagship"),
        role=role,
        armed=False,
        latency_ms=receipt.latency_ms,
        input_tokens=receipt.input_tokens or 0,
        output_tokens=receipt.output_tokens or 0,
        flags={"error": not receipt.ok, "degraded": not receipt.ok},
    )


def call_model(system: str, user: str, *, role: str = "pm", max_tokens: int = 1500,
               seat: str | None = None, record_book: str | None = None):
    """Return the existing Brain tuple through exactly one configured mode.

No client, credential, model or endpoint override is accepted here. Macro's
owner emits its existing health/usage receipts, including unavailable modes.
Failures are bounded labels; provider exception text is never returned.
"""
    if (not isinstance(system, str) or not isinstance(user, str)
            or type(max_tokens) is not int or not 1 <= max_tokens <= _MAX_OUTPUT_TOKENS):
        return None, "production_mode_invalid_request"
    try:
        mode = _configured_mode()
    except Exception:
        return None, "production_mode_invalid_config"
    if not mode:
        return None, "production_mode_not_selected"
    try:
        owner = _owner()
    except Exception:
        return None, "production_mode_owner_unavailable"
    try:
        receipt = owner.call_mode(mode, system, user, max_tokens=max_tokens)
    except owner.ProductionModeConfigError:
        return None, "production_mode_invalid_config"
    except Exception:
        # May follow dispatch: preserve the original failure; never replay it.
        return None, "production_mode_error"

    try:
        _record_turn(receipt, user=user, role=role, seat=seat, record_book=record_book)
    except Exception:
        # Response logging cannot cause another inference or discard its result.
        pass
    if receipt.ok and receipt.text:
        return receipt.text, None
    reason = receipt.state if receipt.state != "configured" else receipt.error_class
    return None, "production_mode_" + reason
