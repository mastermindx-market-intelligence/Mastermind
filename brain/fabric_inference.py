"""Exclusive text inference through Macro's incumbent Fabric application owner.

The loaded Macro checkout owns configuration, workload/capability checks,
credentials, request fencing, provider health and usage. This consumer adds no
pool, retry, ledger or worker job. Tool-bearing conversations have their own
incumbent chat driver; this adapter accepts and returns text only.
"""
from __future__ import annotations

from pathlib import Path
import time
import uuid

_MAX_OUTPUT_TOKENS = 32768
_LANE = "mastermind-text"
_WORKLOAD = "site_batch"


def _owner():
    import bot  # noqa: F401 — incumbent vendored-Macro bootstrap
    from engine import llm_auth, provider_production_modes

    root = Path(provider_production_modes.__file__).resolve().parent.parent
    if Path(llm_auth.__file__).resolve().parent.parent != root:
        raise ImportError("Fabric owner and shared client source disagree")
    return provider_production_modes, llm_auth, root


def _selection(owner, root):
    return owner.configured_application_fabric(
        lane=_LANE, workload_profile=_WORKLOAD, root=root,
    )


def available() -> bool:
    """Fresh eligible identity, without credentials, clients or admission."""
    try:
        owner, _, root = _owner()
        selected, factory = _selection(owner, root)
        if selected is not True or type(factory) is not owner.ApplicationFabricFactory:
            return False
        factory.inspect()  # The actual turn checks eligibility and binds afresh.
        return True
    except Exception:
        return False


def _record_turn(provider, usage, *, user, text, reason, role, seat, record_book,
                 request_id, latency_ms):
    from brain import thinking_log
    from brain.cli_bridge import _ROLE_BOOK

    thinking_log.log_turn_async(
        question=user, answer=text or "", model=provider["model"],
        provider=provider["provider"], mode="shared_fabric", backend="fabric",
        seat=seat or role, book=record_book or _ROLE_BOOK.get(str(role).lower(), "flagship"),
        role=role, armed=False, run_id=request_id, key_id=provider["cap_id"],
        latency_ms=latency_ms, input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        flags={"error": reason is not None, "degraded": reason is not None},
    )


def call_model(system: str, user: str, *, role: str = "pm", max_tokens: int = 1500,
               seat: str | None = None, record_book: str | None = None):
    """Return the Brain tuple from one fresh binding and one inference attempt."""
    if (not isinstance(system, str) or not isinstance(user, str)
            or type(max_tokens) is not int or not 1 <= max_tokens <= _MAX_OUTPUT_TOKENS):
        return None, "fabric_invalid_request"
    try:
        owner, shared, root = _owner()
        selected, factory = _selection(owner, root)
    except Exception:
        return None, "fabric_owner_unavailable"
    if selected is not True:
        return None, "fabric_not_selected"
    if type(factory) is not owner.ApplicationFabricFactory:
        return None, "fabric_binding_unavailable"

    request_id = "mastermind-text-" + uuid.uuid4().hex
    cfg = {"provider_order": ["fabric"], "workload_profile": _WORKLOAD}
    try:
        providers = shared.build_providers(
            cfg, fabric_selected=True, fabric_provider_factory=factory,
            request_id=request_id,
        )
        if len(providers) != 1 or not shared.is_fabric_selection(providers):
            return None, "fabric_binding_unavailable"
    except Exception:
        return None, "fabric_binding_unavailable"
    provider = providers[0]
    provider.update(usage_lane=_LANE, usage_stage="narration", usage_cycle_id=request_id)

    def invoke(client, model):
        response = client.messages.create(
            model=model, system=system, messages=[{"role": "user", "content": user}],
            max_tokens=max_tokens,
        )
        # The shared wrapper already validates the model and full wire protocol.
        # A text-only caller must also reject unsolicited tools before returning
        # any accompanying prose. There is no hidden tool or repair request.
        if (response.stop_reason not in {"end_turn", "max_tokens"}
                or any(block.type != "text" for block in response.content)):
            raise shared.FabricProviderError("fabric_text_protocol_invalid")
        text = "".join(block.text for block in response.content)
        if not text.strip():
            raise shared.FabricProviderError("fabric_empty_response")
        return text, None, response

    started = time.monotonic()
    text, reason = None, None
    try:
        text, reason, _ = shared.make_call(providers, invoke, context=_LANE)
        if reason is not None or not isinstance(text, str) or not text.strip():
            text, reason = None, "fabric_unavailable"
    except shared.FabricProviderError as exc:
        reason = "fabric_effect_unknown" if exc.effect_unknown else "fabric_unavailable"
    except Exception:
        # A provider call may already have occurred; no fallback or replay.
        reason = "fabric_effect_unknown"
    finally:
        # Invalidate this local operation; close does not claim an uncertain
        # upstream request has settled or release its native account lease.
        shared.close_fabric_provider(provider)
    try:
        _record_turn(
            provider, shared.fabric_usage(provider), user=user, text=text, reason=reason,
            role=role, seat=seat, record_book=record_book, request_id=request_id,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception:
        pass  # Logging failure cannot discard a completed answer or repeat it.
    return text, reason
