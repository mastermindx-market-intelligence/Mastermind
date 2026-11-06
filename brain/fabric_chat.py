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
import sys
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
        lane=_LANE, workload_profile=_PROFILE, root=root,
        service_mode_id="mastermind_chat_fabric")
    if chosen is not True or type(factory) is not owner.ApplicationFabricFactory:
        raise advisor.FabricConversationError("fabric_binding_unavailable")
    provider = shared.build_fabric_provider(factory, request_id=operation_id,
        workload_cfg={"provider_order": ["fabric"], "workload_profile": _PROFILE})
    provider.update(usage_lane=_LANE, usage_stage="advisor", usage_cycle_id=operation_id)
    return shared, provider

_AUTO_TURN_SCHEMA = "mastermind.advisor.fabric_turn.v2"


def _auto_transport_owner():
    # Import the pinned shared owner without inspecting current selection.
    from brain.fabric_inference import _owner
    _owner()
    from engine import fabric_inference_client
    return fabric_inference_client


def _auto_step_request(provider, step, kwargs):
    transport = _auto_transport_owner()
    _, body = transport._request(dict(kwargs, model=None, request_id=step["request_id"]), None, False)
    original = transport._load_json(body, unknown=False)
    step.update(normalized_request_digest=transport._auto_request_digest(original),
                max_tokens=kwargs["max_tokens"])
    return original


def _retain_auto_observation(shared, provider, turn, step, original):
    """Keep only this step's original observation under the conversation lock."""
    if turn.get("schema") != _AUTO_TURN_SCHEMA:
        return
    value = shared._fabric_routed_observation(
        provider, shared.fabric_observation(provider), step["request_id"])
    observed = provider.get("_fabric_last_observation")
    if type(observed) is dict and observed.get("request_id") == step["request_id"]:
        step["observed_usage"] = copy.deepcopy(observed)
    if value is None:
        return
    transport = _auto_transport_owner()
    document = value.document
    routed = transport._auto_request_digest(
        dict(original, model=document["routing"]["selected_model"]))
    prior = next((item["observation"]["routing"] for item in turn["steps"]
                  if item is not step and "observation" in item), None)
    document = transport.validate_auto_observation(document, turn["inspection"],
        operation_id=turn["operation_id"], request_id=step["request_id"],
        request_digest=step["normalized_request_digest"], routed_request_digest=routed,
        max_tokens=step["max_tokens"],
        expected_route=transport.auto_route_identity(prior) if prior is not None else None)
    step.update(observation=document, observation_hash=_digest(document),
                normalized_routed_request_digest=routed)


def _auto_identity(turn, step=None):
    if turn.get("schema") != _AUTO_TURN_SCHEMA:
        return {"provider": turn["provider"], "model": turn["model"]}
    step = step or turn["steps"][-1]
    observation = step.get("observation")
    if observation is None:
        raise advisor.FabricConversationError("fabric_response_route_invalid")
    return {"provider": observation["routing"]["pool"], "model": observation["serving_model"]}


def _valid_close(value):
    return (type(value) is dict
        and set(value) == {"disposition", "closed", "effect_unknown", "attempted"}
        and type(value["disposition"]) is str
        and value["disposition"] in {"local_only", "refused", "pending", "effect_unknown", "closed"}
        and all(type(value[key]) is bool for key in ("closed", "effect_unknown", "attempted"))
        and value["closed"] == (value["disposition"] == "closed")
        and value["effect_unknown"] == (value["disposition"] in {"pending", "effect_unknown"})
        and value["attempted"] == (value["disposition"] != "local_only"))


def _save_chat(doc, provider):
    if provider.get("_fabric_conversation_persistence_failed"):
        raise advisor.FabricConversationError("fabric_conversation_persistence_failed")
    try:
        advisor.save_fabric_conversation(doc)
    except Exception:
        provider["_fabric_conversation_persistence_failed"] = True
        raise


async def _close_auto_turn(shared, provider, doc, turn):
    """Persist original close while the incumbent conversation lock is held."""
    prior_error = sys.exc_info()[1]
    try:
        if not provider.get("_fabric_closed"):
            await _observe_thread(lambda: _close_binding(shared, provider))
    except BaseException:
        if prior_error is None:
            raise
    finally:
        value = provider.get("_fabric_close")
        turn["close"] = copy.deepcopy(value) if _valid_close(value) else {
            "disposition": "effect_unknown", "closed": False, "effect_unknown": True, "attempted": True}
        if turn["state"] != "complete":
            turn["state"] = "held"
        if not provider.get("_fabric_conversation_persistence_failed"):
            original_error = prior_error or sys.exc_info()[1]
            try:
                _save_chat(doc, provider)
            except BaseException:
                if original_error is None:
                    raise


def validate_auto_turn(turn):
    """Closed new receipt variant; historical fixed-model turns are unchanged."""
    if type(turn) is not dict:
        raise advisor.FabricConversationError("fabric_conversation_invalid")
    if "schema" not in turn:
        if (set(turn) & {"inspection", "close", "held_result"}
                or turn.get("provider") is None or turn.get("model") is None):
            raise advisor.FabricConversationError("fabric_conversation_invalid")
        return
    try:
        required = {"schema", "id", "operation_id", "prompt_hash", "state", "steps",
                    "tool_effects", "provider", "model", "inspection"}
        if (set(turn) - required - {"close", "held_result", "result"} or not required <= set(turn)
                or turn["schema"] != _AUTO_TURN_SCHEMA or turn["provider"] is not None
                or turn["model"] is not None or turn["state"] not in {"active", "held", "complete"}
                or type(turn["steps"]) is not list or len(turn["steps"]) > _MAX_STEPS
                or type(turn["tool_effects"]) is not list or len(turn["tool_effects"]) > _MAX_TOOL_CALLS):
            raise ValueError()
        advisor.validate_conversation_id(turn["id"])
        transport = _auto_transport_owner()
        transport.validate_native_operation_id(turn["operation_id"])
        transport.validate_auto_inspection(turn["inspection"])
        def digest(value):
            return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
        if not digest(turn["prompt_hash"]):
            raise ValueError()
        selection = None
        successful = {}
        pending_seen = False
        for index, step in enumerate(turn["steps"]):
            fields = {"request_id", "request_hash", "state", "normalized_request_digest", "max_tokens"}
            if (type(step) is not dict or not fields <= set(step)
                    or set(step) - fields - {"observation", "observation_hash",
                        "normalized_routed_request_digest", "observed_usage"}
                    or step["request_id"] != f'{turn["operation_id"]}:brain:{index}'
                    or not digest(step["request_hash"]) or not digest(step["normalized_request_digest"])
                    or step["state"] not in {"pending", "complete"}
                    or step["max_tokens"] != _MAX_OUTPUT_TOKENS):
                raise ValueError()
            if pending_seen:
                raise ValueError()
            pending_seen = step["state"] == "pending"
            if "observed_usage" in step:
                observed = step["observed_usage"]
                if (type(observed) is not dict
                        or set(observed) != {"request_id", "serving_model", "input_tokens", "output_tokens"}
                        or observed["request_id"] != step["request_id"]
                        or observed["serving_model"] is not None and not transport._safe_id(observed["serving_model"])
                        or any(observed[key] is not None and (type(observed[key]) is not int
                            or not 0 <= observed[key] <= transport.MAX_NATIVE_TOKENS)
                            for key in ("input_tokens", "output_tokens"))):
                    raise ValueError()
            observation_fields = set(step) & {"observation", "observation_hash", "normalized_routed_request_digest"}
            if observation_fields:
                if len(observation_fields) != 3 or step["observation_hash"] != _digest(step["observation"]):
                    raise ValueError()
                observed = transport.validate_auto_observation(step["observation"], turn["inspection"],
                    operation_id=turn["operation_id"], request_id=step["request_id"],
                    request_digest=step["normalized_request_digest"],
                    routed_request_digest=step["normalized_routed_request_digest"],
                    max_tokens=step["max_tokens"], expected_route=selection,
                    require_success=step["state"] == "complete")
                selection = transport.auto_route_identity(observed["routing"])
                if "observed_usage" in step and step["observed_usage"] != {
                        "request_id": step["request_id"], "serving_model": observed["serving_model"],
                        **observed["usage"]}:
                    raise ValueError()
            elif step["state"] == "complete":
                raise ValueError()
            if step["state"] == "complete":
                successful[step["request_id"]] = step
        ids = set()
        for effect in turn["tool_effects"]:
            if (type(effect) is not dict
                    or set(effect) != {"id", "name", "input_hash", "state", "request_id"}
                    or not transport._safe_id(effect["id"]) or effect["id"] in ids
                    or not transport._safe_id(effect["name"]) or not digest(effect["input_hash"])
                    or effect["request_id"] not in successful or effect["state"] not in {"pending", "complete"}):
                raise ValueError()
            ids.add(effect["id"])
        if "close" in turn and not _valid_close(turn["close"]):
            raise ValueError()
        if "result" in turn and turn["state"] != "complete" or "result" in turn and "held_result" in turn:
            raise ValueError()
        result = turn.get("result", turn.get("held_result"))
        if ("result" in turn or "held_result" in turn) and result is None:
            raise ValueError()
        if result is not None:
            if (not turn["steps"] or len(successful) != len(turn["steps"])
                    or any(effect["state"] != "complete" for effect in turn["tool_effects"])
                    or type(result) is not dict
                    or set(result) != {"text", "tools_used", "papers", "cost_usd", "usage",
                                      "model", "provider", "truncated"}
                    or type(result["text"]) is not str or len(result["text"]) > 1_000_000
                    or type(result["tools_used"]) is not list or type(result["papers"]) is not list
                    or result["cost_usd"] is not None or type(result["truncated"]) is not bool
                    or {key: result[key] for key in ("model", "provider")} != _auto_identity(turn)):
                raise ValueError()
            usages = [item["observation"]["usage"] for item in turn["steps"]]
            complete = all(all(type(value) is int for value in usage.values()) for usage in usages)
            inp = sum(usage["input_tokens"] for usage in usages
                      if all(type(value) is int for value in usage.values()))
            out = sum(usage["output_tokens"] for usage in usages
                      if all(type(value) is int for value in usage.values()))
            expected_usage = {"input_tokens": inp if complete else None,
                "output_tokens": out if complete else None, "usage_state": "known" if complete else "unknown",
                "completed_input_tokens": inp, "completed_output_tokens": out}
            if result["usage"] != expected_usage:
                raise ValueError()
        if turn["state"] == "complete" and ("result" not in turn
                or turn.get("close") != {"disposition": "closed", "closed": True,
                    "effect_unknown": False, "attempted": True}):
            raise ValueError()
    except Exception:
        raise advisor.FabricConversationError("fabric_conversation_invalid") from None


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


def _log_turn(provider, shared, *, prompt, text, error, operation_id, started, role, turn=None):
    from brain import thinking_log
    from portfolio import registry

    usage = shared.fabric_usage(provider)
    model, pool = provider["model"], provider["provider"]
    if provider.get("_fabric_auto_inspection") is not None:
        identities = set()
        for step in (turn or {}).get("steps", []):
            observation = step.get("observation")
            observed_usage = step.get("observed_usage")
            if observation is not None:
                identities.add((observation["serving_model"], observation["routing"]["pool"]))
            elif observed_usage is not None:
                identities.add((observed_usage["serving_model"], "unknown"))
        model, pool = next(iter(identities)) if len(identities) == 1 else (None, "unknown")
    try:
        thinking_log.log_turn_async(question=prompt, answer=text, model=model,
            provider=pool, mode="shared_fabric", backend="fabric", seat=role,
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
            if provider.get("_fabric_auto_inspection") is not None:
                turn.update(schema=_AUTO_TURN_SCHEMA,
                            inspection=json.loads(provider["_fabric_auto_inspection"]))
            try:
                doc["turns"].append(turn)
                doc["messages"].append({"role": "user", "content": prompt})
                doc["rendered"].append(advisor.rendered_turn("user", prompt))
                _save_chat(doc, provider)
                prior_ids = {effect["id"] for effect in turn["tool_effects"]}
                for step_number in range(limit):
                    kwargs = {"system": system, "messages": copy.deepcopy(doc["messages"]),
                              "tools": tools, "max_tokens": _MAX_OUTPUT_TOKENS}
                    step = {"request_id": f"{operation_id}:brain:{step_number}",
                            "request_hash": _digest({"model": provider["model"], **kwargs}), "state": "pending"}
                    original = (_auto_step_request(provider, step, kwargs)
                                if turn.get("schema") == _AUTO_TURN_SCHEMA else None)
                    turn["steps"].append(step)
                    _save_chat(doc, provider)  # Before any provider bytes.
                    try:
                        response = await _step_response(shared, provider, kwargs)
                    finally:
                        if turn.get("schema") == _AUTO_TURN_SCHEMA:
                            original_error = sys.exc_info()[1]
                            try:
                                _retain_auto_observation(shared, provider, turn, step, original)
                                _save_chat(doc, provider)
                            except BaseException:
                                if original_error is None:
                                    raise
                    calls = bot_mcp.validate_inference_calls(
                        [block for block in response.content if block.type == "tool_use"], used_ids=prior_ids)
                    if len(turn["tool_effects"]) + len(calls) > _MAX_TOOL_CALLS:
                        raise advisor.FabricConversationError("fabric_tool_budget_exhausted")
                    step_text = "".join(block.text for block in response.content if block.type == "text")
                    if len(text) + len(step_text) > 1_000_000:
                        raise advisor.FabricConversationError("fabric_conversation_limit")
                    doc["messages"].append({"role": "assistant", "content": _plain_response(response)})
                    step["state"] = "complete"
                    _save_chat(doc, provider)  # Complete terminal response before tools.
                    # No last-step tool effects or prose when the driver cannot
                    # report the tool result in a following model response.
                    if calls and step_number + 1 == limit:
                        raise advisor.FabricConversationError("fabric_tool_budget_exhausted")
                    text += step_text
                    if not calls:
                        result = {"text": text, "tools_used": [item["name"] for item in used], "papers": papers,
                                  "cost_usd": None, "usage": shared.fabric_usage(provider),
                                  **_auto_identity(turn, step),
                                  "truncated": response.stop_reason == "max_tokens"}
                        if turn.get("schema") == _AUTO_TURN_SCHEMA:
                            turn["held_result"] = result
                            await _close_auto_turn(shared, provider, doc, turn)
                            if not turn["close"]["closed"]:
                                raise advisor.FabricConversationError("fabric_close_unsettled")
                            del turn["held_result"]
                        doc["rendered"].append(advisor.rendered_turn("brain", text, tools=used, papers=papers))
                        doc["rendered"] = doc["rendered"][-200:]
                        turn.update(state="complete", result=result)
                        _save_chat(doc, provider)
                        published_text = text if turn.get("schema") == _AUTO_TURN_SCHEMA else step_text
                        if published_text:
                            yield {"type": "text", "text": published_text}
                        yield {"type": "done", **result, "session_id": None, "replayed": False,
                               "conversation_id": conversation_id, "turn_id": turn_id, "backend": "fabric"}
                        return
                    if step_text and turn.get("schema") != _AUTO_TURN_SCHEMA:
                        yield {"type": "text", "text": step_text}
                    result_blocks = []
                    doc["messages"].append({"role": "user", "content": result_blocks})
                    for call in calls:
                        effect = {"id": call["id"], "name": call["name"],
                                  "input_hash": _digest(call["input"]), "state": "pending"}
                        if turn.get("schema") == _AUTO_TURN_SCHEMA:
                            effect["request_id"] = step["request_id"]
                        turn["tool_effects"].append(effect)
                        _save_chat(doc, provider)  # Before the handler can write.
                        yield {"type": "tool", "name": call["name"], "args": call["input"]}
                        # Cancellation at the yielded event cannot run a later tool.
                        result = await bot_mcp.invoke_inference_tool(call, provenance={
                            **_auto_identity(turn, step), "turn_id": turn_id})
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
                        _save_chat(doc, provider)  # Result before continuation.
                        yield event
                raise advisor.FabricConversationError("fabric_tool_budget_exhausted")
            finally:
                if turn.get("schema") == _AUTO_TURN_SCHEMA and "close" not in turn:
                    await _close_auto_turn(shared, provider, doc, turn)

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
                if not provider.get("_fabric_closed"):
                    await _observe_thread(lambda: _close_binding(shared, provider))
            finally:
                _log_turn(provider, shared, prompt=prompt, text=text, error=error,
                          operation_id=operation_id, started=started, role=role, turn=turn)


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
