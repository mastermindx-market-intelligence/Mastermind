"""Portfolio chat/research through the loaded Macro Fabric owner and bot tools.

The existing advisor store owns continuity and action intent. The existing
gateway owns provider admission/effects, and llm_auth owns usage/health. This
driver creates no worker job, account inventory, retry queue or SDK session.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import time
import uuid

from brain import advisor

_LANE = "mastermind-chat"
_PROFILE = "site_interactive"
_MAX_STEPS = 32
_MAX_OUTPUT_TOKENS = 4096
_MAX_TOOL_CALLS = 128


def selected() -> bool:
    from brain import cli_bridge

    return ("MM_PROVIDER_APPLICATION_MODE" in os.environ
            or cli_bridge._selected_backend() == "fabric")


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _bind(operation_id):
    from brain.fabric_inference import _owner

    owner, shared, root = _owner()
    chosen, factory = owner.configured_application_fabric(
        lane=_LANE, workload_profile=_PROFILE, root=root)
    if chosen is not True or type(factory) is not owner.ApplicationFabricFactory:
        raise advisor.FabricConversationError("fabric_binding_unavailable")
    provider = shared.build_fabric_provider(factory, request_id=operation_id,
        workload_cfg={"provider_order": ["fabric"], "workload_profile": _PROFILE})
    provider.update(usage_lane=_LANE, usage_stage="advisor", usage_cycle_id=operation_id)
    return shared, provider


def _plain_response(response) -> list[dict]:
    out = []
    for block in response.content:
        if block.type == "text":
            out.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            out.append({"type": "tool_use", "id": block.id,
                        "name": block.name, "input": copy.deepcopy(block.input)})
    return out


def _close_binding(shared, provider) -> None:
    # Compatible with the pinned initial owner and its newer common close hook.
    close = getattr(shared, "close_fabric_provider", None)
    if callable(close):
        close(provider)
    else:
        if provider.get("_fabric_pending"):
            shared.fabric_failure(provider, shared.FabricProviderError(
                "fabric_stream_abandoned", effect_unknown=True))
        provider["_fabric_closed"] = True


async def _observe_thread(call):
    """Observe the original bounded call before propagating cancellation.

    Shield from the first await: cancelling the asyncio waiter must not mark
    the still-running provider thread as settled. Keep its strong reference,
    observe the original outcome, and never start a replacement request.
    """
    def outcome():
        # A cancelled shield may report a late worker exception to the event
        # loop even when a second waiter observes it. Carry that outcome as
        # data until this original waiter can preserve cancellation priority.
        try:
            return True, call()
        except BaseException as exc:
            return False, exc

    worker = asyncio.create_task(asyncio.to_thread(outcome))
    cancelled = None
    while True:
        try:
            result = await asyncio.shield(worker)
            break
        except asyncio.CancelledError as exc:
            if worker.cancelled():
                raise
            cancelled = cancelled or exc
        except BaseException:
            if cancelled is not None:
                raise cancelled from None
            raise
    if cancelled is not None:
        raise cancelled
    succeeded, value = result
    if not succeeded:
        raise value
    return value


async def _step_response(shared, provider, kwargs):
    """Buffer one original completion; validate before delivering any prose."""
    def run():
        try:
            def call(client, model):
                response = client.messages.create(model=model, **kwargs)
                # Tool-only responses are valid. The completed response object
                # is the callback result, not an empty prose placeholder.
                return response, None, response

            response, reason, _ = shared.make_call([provider], call, context=_LANE)
            if response is None or reason:
                failure = provider.get("_fabric_failure")
                raise shared.FabricProviderError("fabric_unavailable", effect_unknown=bool(
                    provider.get("_fabric_pending") or getattr(failure, "effect_unknown", False)))
            return response
        except Exception as exc:
            code = ("fabric_effect_unknown" if not isinstance(exc, shared.FabricProviderError)
                    or exc.effect_unknown else "fabric_unavailable")
            raise advisor.FabricConversationError(code) from None

    return await _observe_thread(run)


def _log_turn(provider, shared, *, prompt, text, error, operation_id, started, role):
    from brain import thinking_log
    from portfolio import registry

    usage = shared.fabric_usage(provider)
    try:
        thinking_log.log_turn_async(question=prompt, answer=text, model=provider["model"],
            provider=provider["provider"], mode="shared_fabric", backend="fabric", seat=role,
            book=registry.DASHBOARD_DEFAULT_ID, role=role, armed=True, run_id=operation_id, key_id=provider["cap_id"],
            input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
            latency_ms=int((time.monotonic()-started)*1000),
            flags={"error": bool(error), "degraded": bool(error)})
    except Exception:
        pass  # No second accounting writer or replay after a logging failure.


async def chat_stream(prompt: str, *, conversation_id: str, turn_id: str | None = None,
                      role: str = "deep", max_turns: int | None = None,
                      scope: str = "portfolio_advisor", recover_only: bool = False):
    """One durable conversation turn; repeated completed IDs return the receipt."""
    from brain import bot_mcp

    shared = provider = doc = turn = None
    text, used, papers, error = "", [], [], None
    operation_id, started = "", time.monotonic()
    try:
        advisor.validate_conversation_id(conversation_id)
        turn_id = turn_id if turn_id is not None else uuid.uuid4().hex
        advisor.validate_conversation_id(turn_id)
        limit = 16 if max_turns is None else max_turns
        if (not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 100_000
                or type(limit) is not int or not 1 <= limit <= _MAX_STEPS
                or not isinstance(role, str) or len(role) > 64
                or scope not in {"portfolio_advisor", "research"}):
            raise advisor.FabricConversationError("fabric_chat_request_invalid")
        digest = _digest({"prompt": prompt, "scope": scope, "role": role, "max_turns": limit})
        operation_id = "mastermind-chat:" + _digest([conversation_id, turn_id])[:48]
        with advisor.fabric_conversation(conversation_id, scope=scope) as doc:
            existing = next((item for item in doc["turns"] if item.get("id") == turn_id), None)
            yield {"type": "start", "conversation_id": conversation_id,
                   "turn_id": turn_id, "backend": "fabric"}
            if existing is not None:
                if existing.get("prompt_hash") != digest:
                    raise advisor.FabricConversationError("fabric_turn_identity_conflict")
                if existing.get("state") != "complete":
                    raise advisor.FabricConversationError("fabric_conversation_unsettled")
                result = existing["result"]
                if result["text"]:
                    yield {"type": "text", "text": result["text"]}
                for paper in result["papers"]:
                    yield {"type": "paper", **paper}
                yield {"type": "done", **result, "session_id": None, "replayed": True,
                       "conversation_id": conversation_id, "turn_id": turn_id, "backend": "fabric"}
                return
            if recover_only:
                # Absence of a durable receipt is not proof that an earlier
                # request was unsent. Recovery never starts a fresh effect.
                raise advisor.FabricConversationError("fabric_turn_receipt_missing")
            if any(item.get("state") != "complete" for item in doc["turns"]):
                raise advisor.FabricConversationError("fabric_conversation_unsettled")
            if len(doc["turns"]) >= advisor._MAX_FABRIC_TURNS:
                raise advisor.FabricConversationError("fabric_conversation_limit")
            tools = bot_mcp.inference_tool_catalog()
            system = advisor.inference_system()
            shared, provider = _bind(operation_id)
            turn = {"id": turn_id, "operation_id": operation_id, "prompt_hash": digest,
                    "state": "active", "steps": [], "tool_effects": [],
                    "provider": provider["provider"], "model": provider["model"]}
            doc["turns"].append(turn)
            doc["messages"].append({"role": "user", "content": prompt})
            doc["rendered"].append(advisor.rendered_turn("user", prompt))
            advisor.save_fabric_conversation(doc)
            prior_ids = {effect["id"] for effect in turn["tool_effects"]}
            for step_number in range(limit):
                kwargs = {"system": system, "messages": copy.deepcopy(doc["messages"]),
                          "tools": tools, "max_tokens": _MAX_OUTPUT_TOKENS}
                step = {"request_id": f"{operation_id}:brain:{step_number}",
                        "request_hash": _digest({"model": provider["model"], **kwargs}), "state": "pending"}
                turn["steps"].append(step)
                advisor.save_fabric_conversation(doc)  # Before any provider bytes.
                response = await _step_response(shared, provider, kwargs)
                calls = bot_mcp.validate_inference_calls(
                    [block for block in response.content if block.type == "tool_use"], used_ids=prior_ids)
                if len(turn["tool_effects"]) + len(calls) > _MAX_TOOL_CALLS:
                    raise advisor.FabricConversationError("fabric_tool_budget_exhausted")
                step_text = "".join(block.text for block in response.content if block.type == "text")
                if len(text) + len(step_text) > 1_000_000:
                    raise advisor.FabricConversationError("fabric_conversation_limit")
                doc["messages"].append({"role": "assistant", "content": _plain_response(response)})
                step["state"] = "complete"
                advisor.save_fabric_conversation(doc)  # Complete terminal response before tools.
                # No last-step tool effects or prose when the driver cannot
                # report the tool result in a following model response.
                if calls and step_number + 1 == limit:
                    raise advisor.FabricConversationError("fabric_tool_budget_exhausted")
                text += step_text
                if not calls:
                    result = {"text": text, "tools_used": [item["name"] for item in used], "papers": papers,
                              "cost_usd": None, "usage": shared.fabric_usage(provider),
                              "model": provider["model"], "provider": provider["provider"],
                              "truncated": response.stop_reason == "max_tokens"}
                    doc["rendered"].append(advisor.rendered_turn("brain", text, tools=used, papers=papers))
                    doc["rendered"] = doc["rendered"][-200:]
                    turn.update(state="complete", result=result)
                    advisor.save_fabric_conversation(doc)
                    if step_text:
                        yield {"type": "text", "text": step_text}
                    yield {"type": "done", **result, "session_id": None, "replayed": False,
                           "conversation_id": conversation_id, "turn_id": turn_id, "backend": "fabric"}
                    return
                if step_text:
                    yield {"type": "text", "text": step_text}
                result_blocks = []
                doc["messages"].append({"role": "user", "content": result_blocks})
                for call in calls:
                    effect = {"id": call["id"], "name": call["name"],
                              "input_hash": _digest(call["input"]), "state": "pending"}
                    turn["tool_effects"].append(effect)
                    advisor.save_fabric_conversation(doc)  # Before the handler can write.
                    yield {"type": "tool", "name": call["name"], "args": call["input"]}
                    # Cancellation at the yielded event cannot run a later tool.
                    result = await bot_mcp.invoke_inference_tool(call, provenance={
                        "provider": provider["provider"], "model": provider["model"], "turn_id": turn_id})
                    raw = json.dumps(result, ensure_ascii=False, allow_nan=False)
                    if len(raw) > 128_000:
                        raise advisor.FabricConversationError("fabric_tool_result_invalid")
                    result_blocks.append({"type": "tool_result", "tool_use_id": call["id"], "content": raw})
                    effect["state"] = "complete"
                    prior_ids.add(call["id"])
                    used.append({"name": call["name"], "args": call["input"]})
                    event = bot_mcp.tool_result_event(result, tool_name=call["name"])
                    if event["type"] == "paper":
                        papers.append({key: value for key, value in event.items() if key != "type"})
                    advisor.save_fabric_conversation(doc)  # Result before continuation.
                    yield event
            raise advisor.FabricConversationError("fabric_tool_budget_exhausted")
    except (asyncio.CancelledError, GeneratorExit):
        error = "fabric_effect_unknown" if turn is not None else "fabric_chat_cancelled"
        # Do not rewrite a pending effect as cancelled or resume it on restart.
        raise
    except Exception as exc:
        if isinstance(exc, (advisor.FabricConversationError, bot_mcp.InferenceToolError)):
            error = str(exc)
        elif shared is not None and isinstance(exc, shared.FabricProviderError):
            error = "fabric_effect_unknown" if exc.effect_unknown else "fabric_unavailable"
        else:
            error = "fabric_effect_unknown" if turn is not None else "fabric_chat_unavailable"
        # The last durable intent is preserved. A write-then-raise tool cannot be
        # converted into a retryable tool result or a successful done event.
        yield {"type": "error", "error": error, "conversation_id": conversation_id,
               "turn_id": turn_id, "backend": "fabric", "unsettled": turn is not None or error in {
                   "fabric_conversation_unsettled", "fabric_conversation_busy",
                   "fabric_effect_unknown", "fabric_turn_receipt_missing"}}
    finally:
        if provider is not None:
            try:
                await _observe_thread(lambda: _close_binding(shared, provider))
            finally:
                _log_turn(provider, shared, prompt=prompt, text=text, error=error,
                          operation_id=operation_id, started=started, role=role)


async def research(prompt: str, *, role="deep", max_turns=None, resume=None,
                   conversation_id=None, turn_id=None, recover_only=False) -> dict:
    """Buffered research uses the same tool loop and conversation protocol."""
    if resume is not None:
        return {"ok": False, "text": None, "error": "fabric_sdk_resume_unsupported",
                "backend": "fabric", "session_id": None}
    if turn_id is not None and not conversation_id:
        return {"ok": False, "text": None, "error": "conversation_id_required_with_turn_id",
                "backend": "fabric", "session_id": None}
    if recover_only and (not turn_id or not conversation_id):
        return {"ok": False, "text": None, "error": "recovery_identity_required",
                "backend": "fabric", "session_id": None}
    conversation_id = conversation_id or advisor.new_conversation_id()
    result = {"ok": False, "text": "", "error": None, "backend": "fabric",
              "session_id": None, "conversation_id": conversation_id, "role": role, "armed": True,
              "tools_used": [], "cost_usd": None, "usage": None}
    async for event in chat_stream(prompt, conversation_id=conversation_id, turn_id=turn_id,
                                  role=role, max_turns=max_turns, scope="research", recover_only=recover_only):
        if event["type"] == "start":
            result["turn_id"] = event["turn_id"]
        elif event["type"] == "text":
            result["text"] += event["text"]
        elif event["type"] == "done":
            result.update({key: value for key, value in event.items() if key != "type"})
            result["ok"] = True
        elif event["type"] == "error":
            result["error"] = event["error"]
    return result
