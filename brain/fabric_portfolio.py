"""Typed portfolio inference through the incumbent Fabric application owner.

Runlog owns original identity and continuity; registered desk handlers own tools;
Macro owns admission, model/account selection, global usage and close. The paper
account and settlement receipt owners alone accept/execute portfolio targets.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import re
import uuid
from datetime import date
from pathlib import Path

from brain import runlog

LANE = "mastermind-us-portfolio"
WORKLOAD = "portfolio_analysis"
SERVICE = "macro_portfolio_fabric"
SCHEMA = "mastermind.fabric_portfolio.v1"
MAX_STEPS = 32
MAX_TOKENS = 4096
MAX_TOOLS = 128
CFG = {"provider_order": ["fabric"], "workload_profile": WORKLOAD}
_CLOSED = {"disposition": "closed", "closed": True, "effect_unknown": False, "attempted": True}
_LOCAL = {"disposition": "local_only", "closed": False, "effect_unknown": False, "attempted": False}
_UNKNOWN = {"disposition": "effect_unknown", "closed": False, "effect_unknown": True, "attempted": True}
_TYPED_SYSTEM = (
    "\n\nAPPLICATION CONTRACT: this run uses only the declared typed tools for this portfolio. "
    "External web search/fetch, Task/subagents, shell, raw files, media and custom MCP servers "
    "are unavailable. Use the existing dated dashboard/Neural Web evidence and report missing "
    "or stale evidence explicitly. Never invent a source or a tool result. Book, run, status "
    "and execution authority belong to the trusted harness, not tool arguments."
)


def selected() -> bool:
    from brain import cli_bridge
    return "MM_PROVIDER_APPLICATION_MODE" in os.environ or cli_bridge._selected_backend() == "fabric"


def _transport():
    from brain.fabric_inference import _owner
    _owner()
    from engine import fabric_inference_client
    return fabric_inference_client


def lane(book: str = "autonomous") -> str:
    return {"autonomous": LANE, "china": "mastermind-china-portfolio",
            "hk": "mastermind-hk-portfolio"}[runlog.portfolio_book(book)]


def tool_name(book: str, name: str) -> str:
    if name not in {"submit_book", "request_context_upgrade"}:
        raise runlog.PortfolioRunError("fabric_portfolio_effect_kind_invalid")
    server = {"autonomous": "desk", "china": "china", "hk": "hk"}[runlog.portfolio_book(book)]
    return f"mcp__{server}__{name}"


def _book_mcp(book: str):
    import importlib
    return importlib.import_module("brain." + runlog.portfolio_book(book) + "_mcp")


def _book_owner(book: str):
    import importlib
    return importlib.import_module("bot." + runlog.portfolio_book(book))


def _factory(book: str = "autonomous"):
    from brain.fabric_inference import _owner
    owner, shared, root = _owner()
    chosen, factory = owner.configured_application_fabric(
        lane=lane(book), workload_profile=WORKLOAD, root=root, service_mode_id=SERVICE)
    if chosen is not True or type(factory) is not owner.ApplicationFabricFactory:
        raise runlog.PortfolioRunError("fabric_portfolio_policy_unavailable")
    inspection = factory.inspect(CFG)
    transport = _transport()
    inspection = transport.validate_auto_inspection(inspection)
    # This consumer's positive contract is structured HTTP. Native plaintext
    # remains ineligible; no caller flattening or tools=True relabelling occurs.
    if not set(inspection["route_scope"]["pools"]) & {"go", "bailian"}:
        raise runlog.PortfolioRunError("fabric_portfolio_typed_route_unavailable")
    return shared, factory.with_inspection(inspection), inspection


def readiness(book: str = "autonomous") -> dict:
    book = runlog.portfolio_book(book)
    label = "us" if book == "autonomous" else book
    result = {"selected": selected(), "eligible": False,
              "scope": f"typed_{label}_portfolio_policy_only", "live_provider_verified": False}
    if not result["selected"]:
        return result
    try:
        _, _, inspection = _factory(book)
        catalog(book)
        result.update(eligible=True, workload=WORKLOAD, service=SERVICE,
                      output_limit_mode=inspection["output_limit_mode"])
    except Exception:
        result["reason"] = "typed_portfolio_policy_unavailable"
    return result


def available(book: str = "autonomous") -> bool:
    return readiness(book)["eligible"] is True


def caller_kwargs(handle, book: str = "autonomous") -> dict:
    """Keep legacy caller shape; job telemetry never invents a valid original ID."""
    book = runlog.portfolio_book(book)
    if not selected() and runlog.portfolio_lookup(book=book) is None:
        return {}
    value = getattr(handle, "run_id", None)
    return {"run_id": value} if isinstance(value, str) and value != "error" else {}


def catalog(book: str = "autonomous") -> tuple[list[dict], dict]:
    from jsonschema import Draft202012Validator
    book = runlog.portfolio_book(book)
    mcp = _book_mcp(book)
    if book == "autonomous":
        from brain import bot_mcp
        groups = ((bot_mcp.SERVER_NAME, mcp._READ_TOOLS), (mcp.SERVER_NAME, mcp._DESK_TOOLS))
    else:
        groups = ((mcp.SERVER_NAME, mcp._ALL_TOOLS),)
    declarations, handlers = [], {}
    for server, objects in groups:
        for obj in objects:
            name = f"mcp__{server}__{obj.name}"
            if name == "mcp__bot__get_portfolio" or name in handlers:
                raise runlog.PortfolioRunError("fabric_portfolio_roster_invalid")
            schema = copy.deepcopy(obj.input_schema)
            if schema == {}:
                schema = {"type": "object", "properties": {}}
            if type(schema) is not dict or schema.get("type") != "object":
                raise runlog.PortfolioRunError("fabric_portfolio_roster_invalid")
            schema["additionalProperties"] = False
            Draft202012Validator.check_schema(schema)
            declarations.append({"name": name, "description": obj.description, "input_schema": schema})
            handlers[name] = obj.handler
    if not declarations or len(declarations) > MAX_TOOLS:
        raise runlog.PortfolioRunError("fabric_portfolio_roster_invalid")
    return declarations, handlers


def _calls(content: list[dict], roster: list[dict], used_ids: set[str]) -> list[dict]:
    from jsonschema import Draft202012Validator, validators
    checker = Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda _checker, value: type(value) is int).redefine(
        "number", lambda _checker, value: type(value) in {int, float})
    validator = validators.extend(Draft202012Validator, type_checker=checker)
    schemas = {item["name"]: item["input_schema"] for item in roster}
    calls, ids = [], set(used_ids)
    runlog.canonical(content)  # Reject nonfinite nested values before any handler.
    for block in content:
        if type(block) is not dict:
            raise runlog.PortfolioRunError("fabric_portfolio_response_invalid")
        if block.get("type") == "text":
            if set(block) != {"type", "text"} or type(block["text"]) is not str:
                raise runlog.PortfolioRunError("fabric_portfolio_response_invalid")
            continue
        if (set(block) != {"type", "id", "name", "input"} or block.get("type") != "tool_use"
                or type(block["id"]) is not str
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}", block["id"]) is None
                or block["id"] in ids or block["name"] not in schemas
                or type(block["input"]) is not dict):
            raise runlog.PortfolioRunError("fabric_portfolio_tool_invalid")
        if list(validator(schemas[block["name"]]).iter_errors(block["input"])):
            raise runlog.PortfolioRunError("fabric_portfolio_tool_schema_invalid")
        ids.add(block["id"])
        calls.append(copy.deepcopy(block))
    if len(calls) + len(used_ids) > MAX_TOOLS:
        raise runlog.PortfolioRunError("fabric_portfolio_tool_limit")
    return calls


def _request(asof, force, armed, directive):
    value = {"asof": asof, "force": force, "armed": armed, "directive": directive}
    if (asof is not None and (type(asof) is not str or date.fromisoformat(asof).isoformat() != asof)
            or type(force) is not bool or type(armed) is not bool
            or directive is not None and (type(directive) is not str or len(directive) > 16000)):
        raise runlog.PortfolioRunError("fabric_portfolio_input_invalid")
    runlog.canonical(value)
    return value


def _history(state):
    messages = [{"role": "user", "content": state["frozen"]["prompt"]}]
    for step in state["steps"]:
        if step["state"] != "complete":
            break
        # The transport serializes tool inputs into an arguments string without
        # sorting keys. Canonicalize nested inputs before that translation so a
        # durable JSON round-trip cannot change the next request's exact bytes.
        messages.append({"role": "assistant", "content": runlog.strict_json(
            runlog.canonical(step["response"]["content"]))})
        calls = [block for block in step["response"]["content"] if block["type"] == "tool_use"]
        if calls:
            results = []
            for call in calls:
                effect = next((row for row in state["tools"] if row["id"] == call["id"]), None)
                if effect is not None and effect["state"] == "complete":
                    results.append({"type": "tool_result", "tool_use_id": call["id"],
                                    "content": runlog.canonical(effect["result"]).decode("utf-8")})
            messages.append({"role": "user", "content": results})
    return messages


def _normalized_request(kwargs, request_id):
    transport = _transport()
    _, body = transport._request(dict(kwargs, model=None, request_id=request_id), None, False)
    return transport._load_json(body, unknown=False)


def _validate(doc):
    state = doc["state"]
    required = {"schema", "run_id", "book", "request", "asof", "phase", "steps", "tools"}
    optional = {"frozen", "brain", "close", "inference_status", "cost_receipt", "cost_error",
                "business", "out", "error", "binding_intent", "publication", "entry_context", "local_gate", "local_failure"}
    if (type(state) is not dict or not required <= set(state) or set(state) - required - optional
            or state["schema"] != SCHEMA or type(state["book"]) is not str
            or state["book"] not in ("autonomous", "china", "hk")
            or state["phase"] not in {"claimed", "inference", "business_ready", "business",
                                     "settlement_intent", "settlement_observed", "held", "complete"}
            or type(state["steps"]) is not list or len(state["steps"]) > MAX_STEPS
            or type(state["tools"]) is not list or len(state["tools"]) > MAX_TOOLS):
        raise runlog.PortfolioRunError("fabric_portfolio_state_invalid")
    runlog.portfolio_id(state["run_id"])
    if "entry_context" in state:
        entry = state["entry_context"]
        if (type(entry) is not dict
                or not {"portfolio_id", "asof", "ran_at", "trading_day", "inaugural", "feed_health"} <= set(entry)
                or set(entry) - {"portfolio_id", "asof", "ran_at", "trading_day", "inaugural",
                                 "feed_health", "feed_aborted", "cost_capped"}
                or entry["portfolio_id"] != state["book"] or entry["asof"] != state["asof"]
                or type(entry["inaugural"]) is not bool or type(entry["feed_health"]) is not dict
                or entry["trading_day"] is not None and type(entry["trading_day"]) is not bool
                or type(entry["ran_at"]) is not str
                or any(type(entry[key]) is not bool for key in ("feed_aborted", "cost_capped") if key in entry)):
            raise runlog.PortfolioRunError("fabric_portfolio_entry_invalid")
    if (state["book"] in {"china", "hk"} and "entry_context" not in state
            and ({"frozen", "business", "local_gate", "local_failure"} & set(state))):
        raise runlog.PortfolioRunError("fabric_portfolio_entry_missing")
    if "out" in state and (type(state["out"]) is not dict
            or state["out"].get("portfolio_id") != state["book"]
            or state["out"].get("asof") != state["asof"]):
        raise runlog.PortfolioRunError("fabric_portfolio_output_identity_invalid")
    if "local_gate" in state:
        gate = state["local_gate"]
        entry = state.get("entry_context", {})
        expected = ("feed_down" if entry.get("feed_aborted") is True else
                    "cost_capped" if entry.get("cost_capped") is True else None)
        if (state["book"] not in {"china", "hk"} or gate != expected or expected is None
                or state.get("close") != _LOCAL or state.get("inference_status") != "skipped"
                or state["steps"] or state["tools"]
                or any(key in state for key in ("frozen", "binding_intent", "business", "cost_receipt", "cost_error"))
                or state.get("brain") != _local_brain(state, gate)):
            raise runlog.PortfolioRunError("fabric_portfolio_local_gate_invalid")
        if "out" in state and (state["out"].get("decision_effective") is True
                                or state["out"].get("decided") is True):
            raise runlog.PortfolioRunError("fabric_portfolio_local_gate_acceptance")
    if "local_failure" in state:
        if (state["local_failure"] is not True or state.get("close") != _LOCAL
                or state.get("inference_status") != "failed"
                or state["steps"] or state["tools"]
                or any(key in state for key in ("frozen", "binding_intent", "business", "local_gate"))
                or type(state.get("brain")) is not dict or state["brain"].get("ok") is not False
                or state["brain"].get("run_id") != state["run_id"]):
            raise runlog.PortfolioRunError("fabric_portfolio_local_failure_invalid")
        if "out" in state and (state["out"].get("decision_effective") is True
                                or state["out"].get("decided") is True):
            raise runlog.PortfolioRunError("fabric_portfolio_local_failure_acceptance")
    _transport().validate_native_operation_id(state["run_id"])
    if state["request"] != _request(**state["request"]) or date.fromisoformat(state["asof"]).isoformat() != state["asof"]:
        raise runlog.PortfolioRunError("fabric_portfolio_state_invalid")
    if "close" in state:
        from brain.fabric_chat import _valid_close
        if not _valid_close(state["close"]):
            raise runlog.PortfolioRunError("fabric_portfolio_close_invalid")
    if state["phase"] == "complete":
        if ("out" not in state or state["out"].get("run_id") != state["run_id"]
                or state.get("inference_status") == "held" or state.get("cost_error")
                or state.get("publication", {}).get("state", "complete") not in {"complete", "superseded"}
                or any(step["state"] == "pending" for step in state["steps"])
                or any(effect["state"] == "pending" for effect in state["tools"])
                or state.get("close", _LOCAL) not in (_CLOSED, _LOCAL)
                or any(step["state"] != "refused" for step in state["steps"])
                    and state.get("close") != _CLOSED):
            raise runlog.PortfolioRunError("fabric_portfolio_completion_unsettled")
    if "publication" in state:
        _validate_publication(state["publication"], book=state["book"])
        if state["publication"]["state"] == "superseded" and (
                state.get("out", {}).get("settlement_receipt_acknowledged") is not True
                or state.get("out", {}).get("settlement_receipt_finalization", {}).get("transaction_id") !=
                    state["publication"]["superseded_by_receipt"]):
            raise runlog.PortfolioRunError("fabric_publication_supersession_unproved")
    if "frozen" not in state:
        if (state["steps"] or state["tools"] or "business" in state
                or "publication" in state and not ({"local_gate", "local_failure"} & set(state))):
            raise runlog.PortfolioRunError("fabric_portfolio_input_missing")
        return
    frozen = state["frozen"]
    if (type(frozen) is not dict or set(frozen) != {
            "prompt", "system", "prior", "perception_input", "inaugural", "roster",
            "roster_digest", "inspection", "max_turns", "max_tokens", "digest"}
            or type(frozen["prompt"]) is not str or not 0 < len(frozen["prompt"]) <= 100000
            or type(frozen["system"]) is not str or len(frozen["system"]) > 100000
            or type(frozen["max_turns"]) is not int or not 1 <= frozen["max_turns"] <= MAX_STEPS
            or frozen["max_tokens"] != MAX_TOKENS or type(frozen["inaugural"]) is not bool
            or runlog.digest(frozen["roster"]) != frozen["roster_digest"]
            or runlog.digest({k: v for k, v in frozen.items() if k != "digest"}) != frozen["digest"]):
        raise runlog.PortfolioRunError("fabric_portfolio_frozen_invalid")
    if "entry_context" in state and frozen["inaugural"] != state["entry_context"]["inaugural"]:
        raise runlog.PortfolioRunError("fabric_portfolio_entry_frozen_conflict")
    transport = _transport()
    transport.validate_auto_inspection(frozen["inspection"])
    prefixes = (("mcp__bot__", "mcp__desk__") if state["book"] == "autonomous"
                else ("mcp__" + state["book"] + "__",))
    if any(type(row) is not dict or type(row.get("name")) is not str
           or not row["name"].startswith(prefixes) for row in frozen["roster"]):
        raise runlog.PortfolioRunError("fabric_portfolio_roster_book_conflict")
    if len(state["steps"]) > frozen["max_turns"]:
        raise runlog.PortfolioRunError("fabric_portfolio_step_limit")
    route = None
    ids = set()
    ordered_calls = []
    for index, step in enumerate(state["steps"]):
        fields = {"request_id", "request_digest", "request", "state"}
        allowed = {"observation", "routed_digest", "observed_usage", "response", "error"}
        if (type(step) is not dict or not fields <= set(step) or set(step) - fields - allowed
                or step["request_id"] != f'{state["run_id"]}:brain:{index}'
                or step["state"] not in {"pending", "complete", "failed", "rejected", "refused"}
                or step["request_digest"] != transport._auto_request_digest(step["request"])
                or index + 1 < len(state["steps"]) and step["state"] != "complete"):
            raise runlog.PortfolioRunError("fabric_portfolio_step_invalid")
        prior_state = {**state, "steps": state["steps"][:index]}
        expected = _normalized_request({"system": frozen["system"],
            "messages": _history(prior_state), "tools": frozen["roster"], "max_tokens": MAX_TOKENS},
            step["request_id"])
        if step["request"] != expected:
            raise runlog.PortfolioRunError("fabric_portfolio_request_changed")
        if "observation" in step:
            observed = transport.validate_auto_observation(
                step["observation"], frozen["inspection"], operation_id=state["run_id"],
                request_id=step["request_id"], request_digest=step["request_digest"],
                routed_request_digest=step["routed_digest"], max_tokens=MAX_TOKENS,
                expected_route=route, require_success=step["state"] == "complete")
            route = transport.auto_route_identity(observed["routing"])
            if step["routed_digest"] != transport._auto_request_digest(
                    dict(step["request"], model=observed["routing"]["selected_model"])):
                raise runlog.PortfolioRunError("fabric_portfolio_route_invalid")
        elif step["state"] == "complete":
            raise runlog.PortfolioRunError("fabric_portfolio_observation_missing")
        if "observed_usage" in step:
            usage = step["observed_usage"]
            if (type(usage) is not dict
                    or set(usage) != {"request_id", "serving_model", "input_tokens", "output_tokens"}
                    or usage["request_id"] != step["request_id"]
                    or any(usage[key] is not None and (type(usage[key]) is not int or not 0 <= usage[key] <= transport.MAX_NATIVE_TOKENS)
                           for key in ("input_tokens", "output_tokens"))):
                raise runlog.PortfolioRunError("fabric_portfolio_usage_invalid")
            if "observation" in step and usage != {
                    "request_id": step["request_id"], "serving_model": observed["serving_model"],
                    **observed["usage"]}:
                raise runlog.PortfolioRunError("fabric_portfolio_usage_conflict")
        if step["state"] == "complete":
            response = step["response"]
            if (type(response) is not dict or set(response) != {"content", "stop_reason", "model"}
                    or response["model"] != step["observation"]["serving_model"]
                    or response["stop_reason"] not in {"end_turn", "tool_use"}):
                raise runlog.PortfolioRunError("fabric_portfolio_response_invalid")
            calls = _calls(response["content"], frozen["roster"], ids)
            if bool(calls) != (response["stop_reason"] == "tool_use"):
                raise runlog.PortfolioRunError("fabric_portfolio_response_invalid")
            if calls and index + 1 >= frozen["max_turns"]:
                raise runlog.PortfolioRunError("fabric_portfolio_tool_budget_exhausted")
            ids.update(call["id"] for call in calls)
            ordered_calls.extend((step["request_id"], call) for call in calls)
    completed = {step["request_id"]: step for step in state["steps"] if step["state"] == "complete"}
    seen = set()
    for effect_index, effect in enumerate(state["tools"]):
        required_tool = {"id", "name", "input", "input_digest", "request_id", "state"}
        if (type(effect) is not dict or not required_tool <= set(effect)
                or set(effect) - required_tool - {"result", "submission", "submission_receipt"}
                or effect["id"] in seen or effect["request_id"] not in completed
                or effect["state"] not in {"pending", "complete"}
                or runlog.digest(effect["input"]) != effect["input_digest"]):
            raise runlog.PortfolioRunError("fabric_portfolio_tool_receipt_invalid")
        call = {"type": "tool_use", "id": effect["id"], "name": effect["name"], "input": effect["input"]}
        if (effect_index >= len(ordered_calls)
                or (effect["request_id"], call) != ordered_calls[effect_index]
                or effect["state"] == "pending" and effect_index + 1 != len(state["tools"])
                or call not in completed[effect["request_id"]]["response"]["content"]):
            raise runlog.PortfolioRunError("fabric_portfolio_tool_origin_invalid")
        if effect["state"] == "complete" and "result" not in effect:
            raise runlog.PortfolioRunError("fabric_portfolio_tool_result_missing")
        if "submission" in effect:
            prepared = effect["submission"]
            if (effect["name"] != tool_name(state["book"], "submit_book") or type(prepared) is not dict
                    or set(prepared) != {"payload", "payload_digest", "audit", "before_sha256"}
                    or runlog.digest(prepared["payload"]) != prepared["payload_digest"]):
                raise runlog.PortfolioRunError("fabric_portfolio_submission_invalid")
            payload = prepared["payload"]
            if type(payload) is not dict or payload.get("_fabric_submission") != {
                    "schema": "mastermind.submission_origin.v1", "run_id": state["run_id"],
                    "tool_id": effect["id"], "book": state["book"], "asof": state["asof"],
                    "normalized_digest": runlog.digest({k: v for k, v in payload.items()
                                                       if k != "_fabric_submission"})}:
                raise runlog.PortfolioRunError("fabric_portfolio_submission_origin_invalid")
        if "submission_receipt" in effect:
            receipt = effect["submission_receipt"]
            if (type(receipt) is not dict or receipt.get("run_id") != state["run_id"]
                    or receipt.get("tool_id") != effect["id"] or receipt.get("book") != state["book"]
                    or receipt.get("asof") != state["asof"]
                    or receipt.get("payload_digest") != effect.get("submission", {}).get("payload_digest")):
                raise runlog.PortfolioRunError("fabric_portfolio_submission_receipt_invalid")
        seen.add(effect["id"])
    if "business" in state:
        _validate_business(state)
    if state["phase"] == "complete" and "out" not in state:
        raise runlog.PortfolioRunError("fabric_portfolio_result_missing")


def _validate_business(state):
    from bot import decision_rows
    from portfolio import paper_account
    business = state["business"]
    required = {"target", "prices", "submission", "brain", "skipped", "packet_id", "out",
                "asof", "identity", "digest"}
    if (type(business) is not dict or not required <= set(business)
            or set(business) - required - {"result"}
            or business["asof"] != state["asof"]
            or type(business["submission"]) is not dict or type(business["out"]) is not dict
            or "result" in business and type(business["result"]) is not dict
            or business["digest"] != runlog.digest(
                {k: v for k, v in business.items() if k not in {"digest", "result"}})):
        raise runlog.PortfolioRunError("fabric_portfolio_business_invalid")
    entry = state.get("entry_context")
    if (business["out"].get("portfolio_id") != state["book"]
            or business["out"].get("asof") != state["asof"]
            or entry is not None and (not set(entry) <= set(business["out"])
                                      or any(business["out"][key] != value for key, value in entry.items()))):
        raise runlog.PortfolioRunError("fabric_portfolio_business_entry_conflict")
    accepted = _accepted(state)
    if (accepted is None or decision_rows.submission_sha256(business["submission"]) !=
            decision_rows.submission_sha256(accepted)):
        raise runlog.PortfolioRunError("fabric_portfolio_business_origin_invalid")
    target = paper_account.validate_target_weights(business["target"], portfolio_id=state["book"])
    if (target != business["target"] or business["identity"] !=
            decision_rows.accepted_identity_fields(
                state["book"], business["asof"], business["submission"], target, "queued")):
        raise runlog.PortfolioRunError("fabric_portfolio_business_identity_invalid")
    return business["identity"]


def _validate_publication(plan, *, book="autonomous"):
    from bridge import build_portfolio
    if (type(plan) is not dict or not {
            "payload", "paths", "content", "sha256", "before", "state"} <= set(plan)
            or set(plan) - {"payload", "paths", "content", "sha256", "before", "state", "superseded_by_receipt"}
            or type(plan["payload"]) is not dict or type(plan["content"]) is not str
            or type(plan["paths"]) is not dict or type(plan["before"]) is not dict
            or plan["state"] not in {"pending", "complete", "superseded"}
            or (plan["state"] == "superseded") != ("superseded_by_receipt" in plan)
            or "superseded_by_receipt" in plan and (type(plan["superseded_by_receipt"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", plan["superseded_by_receipt"]) is None)):
        raise runlog.PortfolioRunError("fabric_publication_invalid")
    book = runlog.portfolio_book(book)
    paths, encoded = build_portfolio.prepare(plan["payload"], portfolio_id=book)
    if (json.loads(encoded).get("portfolio_id") != book
            or plan["paths"] != paths or plan["content"].encode("utf-8") != encoded
            or plan["sha256"] != hashlib.sha256(encoded).hexdigest()
            or set(plan["before"]) != set(paths)
            or any(value is not None and (type(value) is not str or
                   re.fullmatch(r"[0-9a-f]{64}", value) is None) for value in plan["before"].values())):
        raise runlog.PortfolioRunError("fabric_publication_identity_invalid")
    return paths, encoded


def _publication_receipt(plan, *, book="autonomous", repair=False):
    """Reconcile only these original bytes at the incumbent writer's exact targets."""
    from bridge import build_portfolio
    paths, encoded = _validate_publication(plan, book=book)
    observed = {}
    # Inspect both originals before repairing either: a foreign writer fences all.
    for key, raw_path in paths.items():
        path = Path(raw_path)
        raw = runlog.strict_read(path, absent=True)
        before = hashlib.sha256(raw).hexdigest() if raw is not None else None
        if raw != encoded and (not repair or before != plan["before"][key]):
            raise runlog.PortfolioRunError("fabric_publication_original_conflict")
        observed[key] = raw
    for key, raw_path in paths.items():
        path = Path(raw_path)
        if observed[key] != encoded:
            runlog.sync_directory(path.parent)
            build_portfolio._atomic_write_bytes(path, encoded)
        runlog.durable_existing(path, encoded)
    return copy.deepcopy(paths)


def _observations(state) -> list[dict]:
    values = []
    for step in state["steps"]:
        if step["state"] == "refused":
            continue
        observed = step.get("observation")
        usage = observed.get("usage", {}) if observed else step.get("observed_usage", {})
        values.append({"request_id": step["request_id"],
                       "model": observed["serving_model"] if observed else usage.get("serving_model"),
                       "pool": observed["routing"]["pool"] if observed else None,
                       "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")})
    return values


def _local_brain(state, reason):
    return {"ok": False, "skipped": True, "error": reason, "backend": "fabric",
            "run_id": state["run_id"], "tools_used": []}


def _brain(state, *, error=None):
    observations = _observations(state)
    known = {key: sum(row[key] for row in observations if row[key] is not None)
             for key in ("input_tokens", "output_tokens")}
    complete = all(row["input_tokens"] is not None and row["output_tokens"] is not None
                   for row in observations)
    identities = {(row["model"], row["pool"]) for row in observations}
    model, pool = next(iter(identities)) if len(identities) == 1 else (None, None)
    text = "".join(block["text"] for step in state["steps"] if step["state"] == "complete"
                   for block in step["response"]["content"] if block["type"] == "text")
    return {"ok": error is None, "error": error, "text": text, "backend": "fabric",
            "run_id": state["run_id"], "model": model, "provider": pool, "cost_usd": None,
            "tools_used": [row["name"] for row in state["tools"] if row["state"] == "complete"],
            "usage": {"input_tokens": known["input_tokens"] if complete else None,
                      "output_tokens": known["output_tokens"] if complete else None,
                      "usage_state": "known" if complete else "unknown",
                      "completed_input_tokens": known["input_tokens"],
                      "completed_output_tokens": known["output_tokens"]},
            "perception_input": copy.deepcopy(state.get("frozen", {}).get("perception_input")),
            "truncated": any(step.get("response", {}).get("stop_reason") == "max_tokens"
                             for step in state["steps"])}


def _accepted(state):
    accepted = [row for row in state["tools"] if "submission_receipt" in row]
    return copy.deepcopy(accepted[-1]["submission"]["payload"]) if accepted else None


def _held(state=None, reason="fabric_portfolio_unsettled", *, book="autonomous"):
    state = state or {}
    submission = _accepted(state) if "tools" in state else None
    prior = copy.deepcopy(state.get("out") or {})
    return {**prior, "portfolio_id": state.get("book", book), "asof": state.get("asof"), "paper_only": True,
            "run_id": state.get("run_id"), "fabric_held": True,
            "skipped": reason, "mark_skipped": "fabric_original_unsettled",
            "brain": copy.deepcopy(state.get("brain") or
                {"ok": False, "error": reason, "run_id": state.get("run_id"), "backend": "fabric"}),
            "decided": bool(submission and isinstance(submission.get("holdings"), list)),
            "decision_effective": bool(prior.get("decision_effective")),
            "target_status": prior.get("target_status", "rejected_fabric_unsettled")}


class Session:
    def __init__(self, doc, *, factory=None, shared=None, before_provider_start=None):
        self.doc = doc
        self.factory = factory
        self.shared = shared
        self.before_provider_start = before_provider_start
        self.provider = None
        self.persistence_failed = False
        self.recovered = factory is None

    @property
    def state(self):
        return self.doc["state"]

    @property
    def book(self):
        return runlog.portfolio_book(self.state["book"])

    def save(self):
        if self.persistence_failed:
            raise runlog.PortfolioRunError("fabric_portfolio_persistence_unsettled")
        _validate(self.doc)
        try:
            runlog.portfolio_save(self.doc)
        except BaseException:
            self.persistence_failed = True
            raise

    def stop_locally(self, reason):
        """Persist an existing feed/cost gate without creating provider authority."""
        self.state.update(local_gate=reason, brain=_local_brain(self.state, reason),
                          close=copy.deepcopy(_LOCAL), inference_status="skipped")
        self.save()

    def stop_unstarted(self, brain):
        """Retain a source-proven pre-provider failure as the same local original."""
        if (self.provider is not None or self.state["steps"] or self.state["tools"]
                or any(key in self.state for key in ("frozen", "binding_intent", "business", "local_gate"))):
            raise runlog.PortfolioRunError("fabric_portfolio_provider_absence_unproved")
        self.state.update(local_failure=True, close=copy.deepcopy(_LOCAL), inference_status="failed",
                          brain=_brain(self.state, error=brain.get("error") or "fabric_portfolio_unstarted"))
        self.save()

    def submission(self):
        if self.persistence_failed:
            return None
        return _accepted(self.state)

    def _guard(self, *, veto=True):
        from brain import cli_bridge
        try:
            if veto and self.before_provider_start is not None:
                self.before_provider_start()
        except cli_bridge.ProviderStartRefused as exc:
            cli_bridge._bind_provider_refusal_run(exc, self.state["run_id"], self.book, "deep")
            raise
        # Re-evaluate after the veto, using the same immutable service/inspection.
        if not selected():
            raise runlog.PortfolioRunError("fabric_portfolio_selection_removed")
        _, current, inspection = _factory(self.book)
        if inspection != self.state["frozen"]["inspection"]:
            raise runlog.PortfolioRunError("fabric_portfolio_identity_changed")
        current.inspect(CFG)

    def reason(self, prompt, system, *, prior, inaugural, perception_input, max_turns):
        if self.recovered:
            if "brain" not in self.state:
                raise runlog.PortfolioRunError("fabric_portfolio_original_unsettled")
            return copy.deepcopy(self.state["brain"])
        return _book_owner(self.book)._run_coro(self._reason(prompt, system, prior=prior, inaugural=inaugural,
            perception_input=perception_input, max_turns=max_turns))

    async def _reason(self, prompt, system, *, prior, inaugural, perception_input, max_turns):
        from brain import cli_bridge, cost_guard
        from brain.fabric_chat import _observe_thread, _plain_response, _valid_close
        error = None
        try:
            roster, _ = catalog(self.book)
            if (type(max_turns) is not int or not 1 <= max_turns <= MAX_STEPS
                    or type(prompt) is not str or not prompt.strip()):
                raise runlog.PortfolioRunError("fabric_portfolio_contract_invalid")
            inspection = self.factory.inspect(CFG)
            frozen = {"prompt": prompt, "system": system + _TYPED_SYSTEM, "prior": copy.deepcopy(prior),
                      "inaugural": inaugural, "perception_input": copy.deepcopy(perception_input),
                      "roster": roster, "roster_digest": runlog.digest(roster),
                      "inspection": inspection, "max_turns": max_turns, "max_tokens": MAX_TOKENS}
            frozen["digest"] = runlog.digest(frozen)
            self.state.update(frozen=frozen, phase="inference", binding_intent=True)
            self.save()  # Original complete input/roster/inspection before credential access.
            self._guard(veto=False)
            self.provider = self.shared.build_fabric_provider(
                self.factory.with_inspection(inspection), request_id=self.state["run_id"], workload_cfg=CFG)
            self.provider.update(usage_lane=lane(self.book), usage_stage=self.book + "_brain",
                                 usage_cycle_id=self.state["run_id"])
            if self.provider.get("_fabric_auto_inspection") is None:
                raise runlog.PortfolioRunError("fabric_portfolio_auto_contract_required")
            for index in range(max_turns):
                kwargs = {"system": frozen["system"], "messages": _history(self.state),
                          "tools": roster, "max_tokens": MAX_TOKENS}
                request_id = f'{self.state["run_id"]}:brain:{index}'
                original = _normalized_request(kwargs, request_id)
                step = {"request_id": request_id, "request": original,
                        "request_digest": _transport()._auto_request_digest(original), "state": "pending"}
                self.state["steps"].append(step)
                self.save()  # Durable provider intent before the actual buffered send.
                attempted = {"provider_boundary": False}
                try:
                    def invoke():
                        self._guard()  # Last veto and selector read, outside make_call's wrapper.
                        attempted["provider_boundary"] = True
                        def create(client, model):
                            response = client.messages.create(model=model, **kwargs)
                            return response, None, response
                        response, reason, _ = self.shared.make_call([self.provider], create, context=lane(self.book))
                        if response is None or reason:
                            raise runlog.PortfolioRunError("fabric_portfolio_provider_unavailable")
                        return response
                    response = await _observe_thread(invoke)
                except BaseException:
                    if not attempted["provider_boundary"]:
                        step.update(state="refused", error="provider_start_refused")
                    raise
                finally:
                    self._retain_observation(step)
                    self.save()  # Known usage survives later semantic rejection.
                content = _plain_response(response)
                prior_ids = {row["id"] for row in self.state["tools"]}
                try:
                    calls = _calls(content, roster, prior_ids)
                    if calls and index + 1 == max_turns:
                        raise runlog.PortfolioRunError("fabric_portfolio_tool_budget_exhausted")
                    if response.stop_reason == "max_tokens":
                        raise runlog.PortfolioRunError("fabric_portfolio_response_truncated")
                except Exception as exc:
                    step.update(state="rejected", error=str(exc))
                    self.save()
                    raise
                step.update(state="complete", response={
                    "content": content, "stop_reason": response.stop_reason, "model": response.model})
                self.save()  # The whole validated response is durable before its first handler.
                for call in calls:
                    await self.invoke_tool(step, call)
                if not calls:
                    self.state["inference_status"] = "complete"
                    break
            else:
                raise runlog.PortfolioRunError("fabric_portfolio_tool_budget_exhausted")
        except (asyncio.CancelledError, GeneratorExit):
            error = "fabric_portfolio_cancelled_original_observed"
            self.state["inference_status"] = "held"
            raise
        except Exception as exc:
            error = (str(exc) if isinstance(exc, (runlog.PortfolioRunError, cli_bridge.ProviderStartRefused))
                     else "fabric_portfolio_unsettled")
            self.state["inference_status"] = ("held" if any(
                step["state"] == "pending" for step in self.state["steps"]) else "failed")
        finally:
            if self.provider is not None:
                try:
                    if not self.provider.get("_fabric_closed"):
                        await _observe_thread(lambda: self.shared.close_fabric_provider(self.provider))
                finally:
                    close = self.provider.get("_fabric_close")
                    self.state["close"] = copy.deepcopy(close) if _valid_close(close) else dict(_UNKNOWN)
            else:
                self.state["close"] = dict(_LOCAL)
            if self.state["close"] not in (_CLOSED, _LOCAL):
                error = error or "fabric_portfolio_close_unsettled"
                self.state["inference_status"] = "held"
            if not self.persistence_failed:
                self.state["brain"] = _brain(self.state, error=error)
                if "frozen" not in self.state:
                    self.state["local_failure"] = True
                self.state["phase"] = "business_ready"
                try:
                    self.state["cost_receipt"] = cost_guard.record_fabric(
                        self.book, self.state["run_id"], self.state["asof"], _observations(self.state))
                except Exception:
                    self.state["cost_error"] = "fabric_book_cost_unsettled"
                self.save()
        return copy.deepcopy(self.state.get("brain") or _brain(self.state, error="fabric_portfolio_unsettled"))

    def _retain_observation(self, step):
        observed_usage = self.provider.get("_fabric_last_observation")
        if type(observed_usage) is dict and observed_usage.get("request_id") == step["request_id"]:
            step["observed_usage"] = copy.deepcopy(observed_usage)
        value = self.shared._fabric_routed_observation(
            self.provider, self.shared.fabric_observation(self.provider), step["request_id"])
        if value is None:
            return
        transport = _transport()
        observation = value.document
        routed = transport._auto_request_digest(
            dict(step["request"], model=observation["routing"]["selected_model"]))
        prior = next((row["observation"]["routing"] for row in self.state["steps"]
                      if row is not step and "observation" in row), None)
        observation = transport.validate_auto_observation(
            observation, self.state["frozen"]["inspection"], operation_id=self.state["run_id"],
            request_id=step["request_id"], request_digest=step["request_digest"],
            routed_request_digest=routed, max_tokens=MAX_TOKENS,
            expected_route=transport.auto_route_identity(prior) if prior is not None else None)
        step.update(observation=observation, routed_digest=routed)
        failure = self.provider.get("_fabric_failure")
        if (observation["effect_unknown"] is False and failure is not None
                and getattr(failure, "effect_unknown", True) is False):
            step["state"] = "failed"

    async def invoke_tool(self, step, call):
        from brain import autonomous_mcp
        roster, handlers = catalog(self.book)
        if roster != self.state["frozen"]["roster"]:
            raise runlog.PortfolioRunError("fabric_portfolio_roster_changed")
        effect = {"id": call["id"], "name": call["name"], "input": copy.deepcopy(call["input"]),
                  "input_digest": runlog.digest(call["input"]), "request_id": step["request_id"],
                  "state": "pending"}
        self.state["tools"].append(effect)
        self.save()
        context = {"run_id": self.state["run_id"], "tool_id": call["id"], "asof": self.state["asof"],
                   "book": self.book,
                   "prepare_submission": lambda payload, audit: self.prepare_submission(effect, payload, audit),
                   "accept_submission": lambda receipt: self.accept_submission(effect, receipt)}
        with autonomous_mcp.fabric_invocation(context):
            result = await handlers[call["name"]](copy.deepcopy(call["input"]))
        raw = runlog.canonical(result)
        if len(raw) > 128000:
            raise runlog.PortfolioRunError("fabric_portfolio_tool_result_limit")
        effect.update(state="complete", result=copy.deepcopy(result))
        self.save()

    def prepare_submission(self, effect, payload, audit):
        mcp = _book_mcp(self.book)
        payload = copy.deepcopy(payload)
        payload["_fabric_submission"] = {
            "schema": "mastermind.submission_origin.v1", "run_id": self.state["run_id"],
            "tool_id": effect["id"], "book": self.book, "asof": self.state["asof"],
            "normalized_digest": runlog.digest(payload)}
        raw = runlog.strict_read(mcp.submission_path(), absent=True)
        effect["submission"] = {"payload": payload, "payload_digest": runlog.digest(payload),
                                "audit": copy.deepcopy(audit),
                                "before_sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None}
        self.save()
        return payload, {"run_id": self.state["run_id"], "tool_id": effect["id"]}

    def accept_submission(self, effect, receipt):
        effect["submission_receipt"] = copy.deepcopy(receipt)
        self.save()

    def settle(self, call, *, target, prices, submission, brain, skipped, packet_id, out):
        from bot import decision_rows
        if self.persistence_failed or "business" in self.state:
            raise runlog.PortfolioRunError("fabric_portfolio_settlement_already_owned")
        business = {"target": copy.deepcopy(target), "prices": copy.deepcopy(prices),
                    "submission": copy.deepcopy(submission), "brain": copy.deepcopy(brain),
                    "skipped": copy.deepcopy(skipped), "packet_id": packet_id,
                    "out": copy.deepcopy(out), "asof": self.state["asof"],
                    "identity": decision_rows.accepted_identity_fields(
                        self.book, self.state["asof"], submission, target, "queued")}
        business["digest"] = runlog.digest(business)
        self.state.update(business=business, phase="settlement_intent")
        self.save()
        result = call()
        business["result"] = copy.deepcopy(result)
        self.state["phase"] = "settlement_observed"
        self.save()
        return result

    def publish(self, payload):
        from bridge import build_portfolio
        from portfolio import paper_account
        if self.persistence_failed or "publication" in self.state:
            raise runlog.PortfolioRunError("fabric_publication_already_owned")
        # Stable dict order matters because the existing writer preserves JSON order.
        payload = runlog.strict_json(runlog.canonical(payload))
        paths, encoded = build_portfolio.prepare(payload, portfolio_id=self.book)
        with paper_account._paper_transaction_lock(self.book):
            before = {}
            for key, path in paths.items():
                raw = runlog.strict_read(Path(path), absent=True)
                before[key] = hashlib.sha256(raw).hexdigest() if raw is not None else None
            self.state["publication"] = {
                "payload": payload, "paths": paths, "content": encoded.decode("utf-8"),
                "sha256": hashlib.sha256(encoded).hexdigest(), "before": before, "state": "pending"}
            self.save()  # The original exact publication, before either existing target changes.
            returned = build_portfolio.write(payload, portfolio_id=self.book)
            if returned != paths:
                raise runlog.PortfolioRunError("fabric_publication_paths_changed")
            result = _publication_receipt(self.state["publication"], book=self.book)
            self.state["publication"]["state"] = "complete"
            self.save()
            return result

    def finish(self, result):
        result = copy.deepcopy(result)
        if result.get("portfolio_id", self.book) != self.book:
            raise runlog.PortfolioRunError("fabric_portfolio_result_book_conflict")
        result.setdefault("portfolio_id", self.book)
        result["run_id"] = self.state["run_id"]
        boundary = self.state.get("business", {}).get("result", {})
        unknown = (self.persistence_failed or self.state.get("inference_status") == "held"
                   or self.state.get("cost_error")
                   or any(row["state"] == "pending" for row in self.state["tools"])
                   or self.state.get("publication", {}).get("state", "complete") not in {"complete", "superseded"}
                   or result.get("settlement_receipt_retained")
                   or not (result.get("fabric_reconciled") is True and result.get("decision_effective") is True)
                      and (boundary.get("recovery_error") or boundary.get("retry_queue_error")
                           or boundary.get("error") and not _known_refusal(boundary)
                           or boundary.get("skipped") in {
                               "settle_failed", "settlement_receipt_unreadable", "settlement_recovery_failed"}))
        result.pop("fabric_held", None)
        if unknown:
            result["fabric_held"] = True
        self.state["out"] = result
        self.state["phase"] = "held" if unknown else "complete"
        self.save()
        return result


def _recover_tools(session):
    from brain import bot_mcp, decision_submission, portfolio_learning
    mcp = _book_mcp(session.book)
    for effect in session.state["tools"]:
        if effect["state"] != "pending":
            continue
        correlation = {"run_id": session.state["run_id"], "tool_id": effect["id"]}
        if effect["name"] == tool_name(session.book, "submit_book") and "submission" in effect:
            receipt = decision_submission.reconcile_submission(mcp.submission_path(), correlation)
            session.accept_submission(effect, receipt)
            result = bot_mcp._json({"ok": True, "reconciled": True, "submission_receipt": receipt})
        elif effect["name"] == tool_name(session.book, "request_context_upgrade"):
            result = bot_mcp._json(portfolio_learning.reconcile_context_request(correlation, book=session.book))
        else:
            raise runlog.PortfolioRunError("fabric_portfolio_tool_effect_unsettled")
        effect.update(state="complete", result=result)
        session.save()
    # Only a fully saved, validated response can authorize its still-unstarted tools.
    _run_coro = _book_owner(session.book)._run_coro
    for step in session.state["steps"]:
        if step["state"] != "complete":
            continue
        calls = _calls(step["response"]["content"], session.state["frozen"]["roster"], set())
        existing = {effect["id"] for effect in session.state["tools"]}
        for call in calls:
            if call["id"] not in existing:
                _run_coro(session.invoke_tool(step, call))
                existing.add(call["id"])


def _known_refusal(boundary):
    """Only explicit incumbent pre-write refusals prove no own acceptance."""
    return (type(boundary) is dict
            and boundary.get("skipped") in {"invalid_target_weights", "pending_target_cas_conflict"}
            and boundary.get("queued") is False and not boundary.get("settlement_receipt_id")
            and not boundary.get("receipt_retained") and not boundary.get("recovery_error")
            and not boundary.get("retry_queue_error"))


def _same_submission(snapshot, intent, *, book="autonomous"):
    from bot import decision_rows
    return (type(snapshot) is dict and snapshot.get("portfolio_id") == book
            and snapshot.get("accepted_asof") == intent["asof"]
            and type(snapshot.get("submission")) is dict
            and decision_rows.submission_sha256(snapshot["submission"]) ==
                intent["identity"]["submission_sha256"]
            and decision_rows.decision_id(book, intent["asof"], snapshot["submission"]) ==
                intent["identity"]["decision_id"])


def _snapshot_target(snapshot, target, intent, *, book="autonomous"):
    """Bind this accepted root through only the incumbent deterministic rewrite chain."""
    from bot import decision_rows
    from portfolio import paper_account
    original = intent["identity"]["target_sha256"]
    current = decision_rows.target_sha256(
        paper_account.validate_target_weights(target, portfolio_id=book))
    if (not _same_submission(snapshot, intent, book=book)
            or snapshot.get("schema_version") != paper_account.PENDING_DECISION_SCHEMA_V1
            or snapshot.get("decision_log_required") is not True
            or snapshot.get("accepted_target_sha256") != original
            or snapshot.get("target_sha256") != current):
        raise runlog.PortfolioRunError("fabric_settlement_original_target_conflict")
    lineage = snapshot.get("target_lineage", [])
    if type(lineage) is not list or len(lineage) > 20:
        raise runlog.PortfolioRunError("fabric_settlement_lineage_invalid")
    previous = original
    for index, transition in enumerate(lineage):
        if type(transition) is not dict:
            raise runlog.PortfolioRunError("fabric_settlement_lineage_invalid")
        reason = transition.get("reason")
        destination = transition.get("to_target_sha256")
        if (transition.get("from_target_sha256") != previous
                or type(destination) is not str or re.fullmatch(r"[0-9a-f]{64}", destination) is None
                or reason not in {"deterministic_risk_rewrite", "deterministic_risk_rewrite_compacted"}
                or reason == "deterministic_risk_rewrite_compacted" and (
                    index != 0 or type(transition.get("compacted_transitions")) is not int
                    or transition["compacted_transitions"] < 2)):
            raise runlog.PortfolioRunError("fabric_settlement_lineage_invalid")
        previous = destination
    if previous != current or not decision_rows._target_lineage_matches(snapshot, original, current):
        raise runlog.PortfolioRunError("fabric_settlement_lineage_invalid")
    return current


def _archive_proof(receipt, fills, intent, *, book="autonomous"):
    from bot import decision_rows
    from portfolio import registry
    snapshot = receipt["decision_snapshot"]
    current = _snapshot_target(snapshot, receipt["target"], intent, book=book)
    identity = intent["identity"]
    rows = runlog.strict_rows(registry.data_dir(book) / "decisions.jsonl")
    matches = [row for row in rows if row.get("settlement_transaction_id") == receipt["transaction_id"]]
    if len(matches) != 1:
        raise runlog.PortfolioRunError("fabric_settlement_archive_projection_missing")
    row = matches[0]
    if (row.get("accepted_asof") != intent["asof"]
            or row.get("decision_id") != identity["decision_id"]
            or row.get("submission_sha256") != identity["submission_sha256"]
            or row.get("decision_effective") is not True or row.get("target_status") != "executed"
            or row.get("target_sha256") != current
            or row.get("settled_asof") != str(receipt["settlement_asof"])[:10]
            or row.get("settlement_receipt_sha256") != decision_rows._canonical_sha256(receipt)
            or row.get("settlement_fill_ids") != [str(fill["fill_id"]) for fill in fills]
            or current != identity["target_sha256"] and (
                row.get("accepted_target_sha256") != identity["target_sha256"]
                or row.get("target_lineage") != snapshot.get("target_lineage"))):
        raise runlog.PortfolioRunError("fabric_settlement_archive_projection_conflict")


def _recover_publication(session):
    plan = session.state.get("publication")
    if plan is None:
        return None
    if plan["state"] == "complete":
        return copy.deepcopy(plan["paths"])
    if plan["state"] == "superseded":
        raise runlog.PortfolioRunError("fabric_publication_superseded")
    # Caller retains the incumbent paper lock. Claim the current revision before
    # repairing only absent/preimage components of this original exact output.
    session.save()
    paths = _publication_receipt(plan, book=session.book, repair=True)
    plan["state"] = "complete"
    session.save()
    return paths


def _recover_settlement(session):
    """Reconcile queue/outbox/archive originals; never enter execute_or_queue again."""
    from bot import decision_rows, settle
    from portfolio import paper_account, registry
    state, intent = session.state, session.state["business"]
    identity = _validate_business(state)
    pid = session.book
    owner = _book_owner(pid)
    book_kwargs = ({"feed_health": copy.deepcopy(intent["out"].get("feed_health"))}
                   if pid != "autonomous" else {})
    boundary = intent.get("result", {})
    known_id = boundary.get("settlement_receipt_id")
    if known_id is not None and (type(known_id) is not str or
                                 re.fullmatch(r"[0-9a-f]{64}", known_id) is None):
        raise runlog.PortfolioRunError("fabric_settlement_known_receipt_invalid")
    with paper_account._paper_transaction_lock(pid):
        session.save()  # Stale recoverers fail before WAL, callback or projection repair.
        paper_account.recover_paper_transaction(pid)
        saved = copy.deepcopy(state.get("out") or {})
        if saved.get("decision_effective") is False and _known_refusal(boundary):
            paths = _recover_publication(session)
            if paths is not None:
                saved["paths"] = paths
                saved.pop("write_error", None)
            return session.finish(saved)
        if (saved.get("decision_effective") is False
                and saved.get("outstanding_settlement_receipt_acknowledged") is True
                and not known_id):
            # An older transaction was finalized; this run remains its original rejection.
            return session.finish(saved)
        receipt_dir = paper_account._settlement_receipt_dir(pid)
        candidates = []
        for directory, active in ((receipt_dir, True), (receipt_dir / "acknowledged", False)):
            paths = ([directory / (known_id + ".json")] if known_id else
                     sorted(directory.glob("*.json")) if directory.exists() else [])
            if len(paths) > 4096:
                raise runlog.PortfolioRunError("fabric_settlement_receipt_limit")
            for path in paths:
                raw = runlog.strict_read(path, absent=known_id is not None)
                if raw is None:
                    continue
                receipt = runlog.strict_json(raw)
                snapshot = receipt.get("decision_snapshot") if type(receipt) is dict else None
                if not _same_submission(snapshot, intent, book=pid):
                    if known_id:
                        raise runlog.PortfolioRunError("fabric_settlement_known_receipt_conflict")
                    continue
                transaction = receipt.get("transaction_id")
                if (receipt.get("schema") != paper_account.PAPER_SETTLEMENT_RECEIPT_SCHEMA
                        or receipt.get("portfolio_id") != pid or type(transaction) is not str
                        or re.fullmatch(r"[0-9a-f]{64}", transaction) is None
                        or path.name != transaction + ".json"):
                    raise runlog.PortfolioRunError("fabric_settlement_receipt_invalid")
                current = _snapshot_target(snapshot, receipt.get("target"), intent, book=pid)
                if receipt.get("target_sha256") != current:
                    raise runlog.PortfolioRunError("fabric_settlement_receipt_target_conflict")
                candidates.append((receipt, active, raw))
        transactions = {row["transaction_id"] for row, _active, _raw in candidates}
        if len(transactions) > 1 or candidates and len({raw for _row, _active, raw in candidates}) > 1:
            raise runlog.PortfolioRunError("fabric_settlement_identity_conflict")
        if known_id and not candidates:
            raise runlog.PortfolioRunError("fabric_settlement_known_receipt_missing")
        if candidates:
            receipt, active, _raw = next(((r, a, raw) for r, a, raw in candidates if a), candidates[0])
            fills = paper_account.validated_settlement_receipt_fills(receipt)
            paper_account.validated_settlement_receipt_prices(receipt)
            if not paper_account.settlement_receipt_fills_are_durable(receipt, pid):
                raise runlog.PortfolioRunError("fabric_settlement_fills_unsettled")
            transaction_id = receipt["transaction_id"]
            if active:
                # The incumbent paper lock is reentrant. Keep receipt inspection and
                # active finalization within it so another finalizer cannot race to ACK.
                finalized = settle.finalize_direct_settlement_receipt(pid, transaction_id)
                if finalized.get("ok") is not True or finalized.get("receipt_acknowledged") is not True:
                    raise runlog.PortfolioRunError("fabric_settlement_finalization_unsettled")
            else:
                _archive_proof(receipt, fills, intent, book=pid)
                finalized = {"ok": True, "receipt_acknowledged": True, "archived_original": True,
                             "transaction_id": transaction_id}
            result = {**(saved or intent["out"]), "decided": True, "decision_effective": True,
                      "target_status": "executed", "queued_for_open": False, "executed": fills,
                      "run_id": state["run_id"], "paper_only": True, "fabric_reconciled": True,
                      "brain": copy.deepcopy(state["brain"]), "holdings": len(receipt["target"]),
                      "settlement_receipt_acknowledged": True,
                      "settlement_receipt_finalization": finalized}
            for key in ("settlement_receipt_retained", "settlement_state_blocked",
                        "settlement_state_block_reason", "settlement_receipt_error", "write_error"):
                result.pop(key, None)
            # The receipt finalizer owns the later executed publication. A pending
            # older queued projection must never overwrite that acknowledged output.
            if "publication" in state and state["publication"]["state"] == "pending":
                state["publication"]["state"] = "superseded"
                state["publication"]["superseded_by_receipt"] = transaction_id
            return session.finish(result)

        raw = runlog.strict_read(paper_account._pending_target_path(pid), absent=True)
        queued = runlog.strict_json(raw) if raw is not None else None
        if queued is None or paper_account.pending_target_contract_error(queued, pid):
            raise runlog.PortfolioRunError("fabric_settlement_effect_unsettled")
        snapshot = queued.get("decision_snapshot")
        _snapshot_target(snapshot, queued["target"], intent, book=pid)
        try:
            partner = decision_rows.validate_queued_decision_snapshot(pid, snapshot)
        except decision_rows.DecisionSettlementConflict:
            rows = runlog.strict_rows(registry.data_dir(pid) / "decisions.jsonl", absent=True)
            if any(row.get("decision_id") == identity["decision_id"]
                   or row.get("asof") == intent["asof"] and (
                       row.get("decision_effective") is True or row.get("target_status") in {"queued", "executed"})
                   for row in rows):
                raise runlog.PortfolioRunError("fabric_settlement_decision_conflict")
            owner._append_decision_log(intent["asof"], intent["submission"], [],
                intent["skipped"], intent["brain"], packet_id=intent["packet_id"],
                target_status="queued", effective_target=intent["target"], _locked=True, **book_kwargs)
            partner = decision_rows.validate_queued_decision_snapshot(pid, snapshot)
        if partner.get("ok") is not True or partner.get("required") is not True:
            raise runlog.PortfolioRunError("fabric_settlement_required_partner_missing")
        result = {**(saved or intent["out"]), "decided": True, "decision_effective": True,
                  "target_status": "queued", "queued_for_open": True, "executed": [],
                  "run_id": state["run_id"], "paper_only": True, "fabric_reconciled": True,
                  "brain": copy.deepcopy(state["brain"]), "holdings": len(queued["target"])}
        paths = _recover_publication(session)
        if paths is None:
            # No publication intent ever existed, so this is its first write.
            # Freeze that first projection before calling the same owner.
            payload = owner._build_payload(intent["asof"], intent["submission"],
                intent["prices"], [], intent["skipped"], intent["brain"], target_status="queued", **book_kwargs)
            paths = session.publish(payload)
        result["paths"] = paths
        result.pop("write_error", None)
        return session.finish(result)


def _recover(doc, runner):
    _validate(doc)
    state = doc["state"]
    if state["phase"] == "complete":
        return copy.deepcopy(state["out"])
    session = Session(doc)
    if state.get("cost_error") and "close" in state:
        from brain import cost_guard
        state["cost_receipt"] = cost_guard.record_fabric(
            state["book"], state["run_id"], state["asof"], _observations(state))
        state.pop("cost_error", None)
        session.save()
    if "local_gate" in state or "local_failure" in state:
        if "out" in state:
            from portfolio import paper_account
            with paper_account._paper_transaction_lock(state["book"]):
                result = copy.deepcopy(state["out"])
                paths = _recover_publication(session)
                if paths is not None:
                    result["paths"] = paths
                    result.pop("write_error", None)
                return session.finish(result)
        request = state["request"]
        result = runner(state["asof"], force=request["force"], armed=request["armed"],
                        directive=request["directive"], _fabric_session=session)
        return session.finish(result)
    if "business" in state:
        return _recover_settlement(session)
    provider_pending = any(step["state"] == "pending" for step in state["steps"])
    independent_submission = (_accepted(state) is not None and "brain" in state and "close" in state
                              and not any(tool["state"] == "pending" for tool in state["tools"]))
    if provider_pending and not independent_submission:
        return _held(state, "fabric_provider_original_unsettled")
    if "frozen" not in state or "close" not in state:
        return _held(state)
    if not provider_pending:
        _recover_tools(session)
    if (state.get("out", {}).get("skipped") == "fabric_portfolio_tool_effect_unsettled"
            and not any(effect["state"] == "pending" for effect in state["tools"])):
        state.pop("out", None)  # Business never started while its tool custody was unknown.
    if "out" in state:
        from portfolio import paper_account
        with paper_account._paper_transaction_lock(state["book"]):
            session.save()
            paths = _recover_publication(session)
            result = copy.deepcopy(state["out"])
            if paths is not None:
                result["paths"] = paths
                result.pop("write_error", None)
            return session.finish(result)
    if "brain" not in state:
        state["brain"] = _brain(state, error="fabric_original_not_resumed")
        state["inference_status"] = "held"
    state["phase"] = "business_ready"
    session.save()
    request = state["request"]
    result = runner(state["asof"], force=request["force"], armed=request["armed"],
                    directive=request["directive"], _fabric_session=session)
    return session.finish(result)


def route(*, asof=None, force=False, armed=True, directive=None, run_id=None,
          runner, before_provider_start=None, book="autonomous"):
    """Return (handled, result); original custody always precedes mutable routing."""
    original = None
    try:
        book = runlog.portfolio_book(book)
        original = runlog.portfolio_lookup(run_id, book=book)
        if original is not None:
            _validate(original)
            if run_id == original["state"]["run_id"] and original["state"]["request"] != _request(
                    asof, force, armed, directive):
                return True, _held(original["state"], "fabric_run_input_conflict")
            return True, _recover(original, runner)
        if not selected() or not armed:
            return False, None
        request = _request(asof, force, armed, directive)
        label = "us" if book == "autonomous" else book
        ident = runlog.portfolio_id(run_id if run_id is not None else label + "-portfolio-" + uuid.uuid4().hex)
        _transport().validate_native_operation_id(ident)
        shared, factory, _ = _factory(book)
        catalog(book)
        state = {"schema": SCHEMA, "run_id": ident, "book": book, "request": request,
                 "asof": asof or date.today().isoformat(), "phase": "claimed", "steps": [], "tools": []}
        original = runlog.portfolio_claim(state)
        session = Session(original, factory=factory, shared=shared, before_provider_start=before_provider_start)
        result = runner(state["asof"], force=force, armed=armed, directive=directive, _fabric_session=session)
        return True, session.finish(result)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, runlog.PortfolioRunError) else "fabric_portfolio_unsettled"
        return True, _held(original["state"] if original is not None else None, reason, book=book)
