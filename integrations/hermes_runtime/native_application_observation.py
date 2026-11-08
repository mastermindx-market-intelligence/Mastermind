"""Bounded APPLICATION return evidence for the incumbent native observer.

This pure projection is not a transport, authority, retry owner or store.
Owner-wire commitments stay distinct from the native assembly commitment.
Historical shape validation does not independently authenticate the producer.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path
from types import ModuleType

CLIENT_SHA256 = "9b0fc0441e2ed5360253a2a320e1a8376fef9709c9f6a3caf7eb91912b6cf500"
SUPPORT_SHA256 = {
    "codec.py": "62005182643a5e6312ca6c2169898839ebc15e49a1aefe6ddaf0f39f75f5de27",
    "structured.py": "b6f69c02cfb6eeaccba563d28b46fc471a35686c2879d6ddad5f03f1acd089be",
}
STAGE = "source_qualified_application_create_return"
PROJECTION_SCHEMA = "mastermind.hermes_application_return/v1"
MAX_RETURN_BYTES = 2048
UPDATE_RESERVE_BYTES = MAX_RETURN_BYTES + 256
_NATIVE = ("session_id", "task_id", "turn_id", "api_request_id")
_ROUTE_FIELDS = {
    "schema", "requested_model", "route_scope", "route_scope_digest",
    "selection_digest", "request_digest", "routed_request_digest", "pool",
    "selected_model", "mode", "protocol", "driver", "profile", "source",
    "recipe_digest", "output_contract",
}


def _transport():
    from . import native_transport_observation
    return native_transport_observation


class Source:
    def __init__(self, module, support):
        self.module = module
        self.client = module.HermesApplicationClient
        self.binding = module.ApplicationBinding
        self.call = module.NativeCall
        self.record = module._Record
        self.scope = module._SCOPE
        self.create = self.client.create
        self.check = self.binding.check
        self.request_id = self.binding.request_id
        self.convert = module._record
        self.globals, self.methods, self.functions = [], [], []
        for owner in (module, *support):
            self.globals.append((owner, {k: v for k, v in vars(owner).items() if not k.startswith("__")}))
            functions = []
            for value in vars(owner).values():
                if inspect.isfunction(value) and value.__globals__ is vars(owner):
                    functions.append(value)
                elif inspect.isclass(value) and value.__module__ == owner.__name__:
                    for key, member in vars(value).items():
                        function = member.__func__ if isinstance(member, (classmethod, staticmethod)) else member
                        if inspect.isfunction(function):
                            if not (value is self.client and key == "create"):
                                self.methods.append((value, key, member))
                            functions.append(function)
            for function in functions:
                self.functions.append((function, function.__code__,
                    copy.deepcopy(function.__defaults__), copy.deepcopy(function.__kwdefaults__)))

    def current(self, wrapper):
        m = self.module
        return (all(all(vars(owner).get(key) is value for key, value in selected.items())
                    for owner, selected in self.globals)
            and all(vars(owner).get(key) is value for owner, key, value in self.methods)
            and all(function.__code__ is code and function.__defaults__ == defaults
                    and function.__kwdefaults__ == kwdefaults for function, code, defaults, kwdefaults in self.functions)
            and m.HermesApplicationClient is self.client
            and m.ApplicationBinding is self.binding and m.NativeCall is self.call
            and m._Record is self.record and m._SCOPE is self.scope
            and m._record is self.convert and self.client.create is wrapper
            and self.binding.check is self.check
            and self.binding.request_id is self.request_id)

    def client_current(self, client, wrapper):
        return (type(client) is self.client and self.current(wrapper)
            and getattr(getattr(client, "create", None), "__func__", None) is wrapper
            and getattr(getattr(client, "chat", None), "completions", None) is client)

    def snapshot(self, context, kwargs):
        scope = self.scope.get()
        if (type(scope) is not tuple or len(scope) != 2
                or type(scope[0]) is not self.binding or type(scope[1]) is not self.call):
            raise ValueError("application scope unavailable")
        binding, call = scope
        identity = {key: getattr(call, key) for key in _NATIVE}
        t = _transport()
        for value in identity.values():
            t._text(value)
        expected = {"agent_session_id": identity["session_id"],
                    "turn_id": identity["turn_id"], "api_request_id": identity["api_request_id"]}
        if (context.span is None or context.span.record["identity"] != expected
                or context.task_id != identity["task_id"] or binding.automatic is not True):
            raise ValueError("application original call mismatch")
        values = (binding.operation_id, binding.session_id, binding.turn_id,
                  binding.model, binding.requested_model, binding.automatic,
                  binding._max_output_tokens, binding._owner, binding._authorized)
        operation, session, turn, model, requested, _, limit, _, _ = values
        t._text(operation)
        if session != identity["session_id"] or turn != identity["turn_id"] or kwargs.get("model") != requested:
            raise ValueError("application binding mismatch")
        t._integer(limit, positive=True)
        if limit > 32768:
            raise ValueError("application output bound")
        content = t._observation()._content_digest(kwargs)
        material = [operation, *(identity[key] for key in _NATIVE)]
        request_id = "hermes:" + hashlib.sha256(json.dumps(
            material, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        entry = {"operation_id": operation, "request_id": request_id,
                 "native_identity": identity, "content_sha256": content["content_sha256"],
                 "content_fields": content["fields"], "model": t._scalar(requested, "model"),
                 "owner_model": t._scalar(model, "model"), "output_limit": limit}
        return scope, values, entry

    def unchanged(self, snapshot):
        scope, values, entry = snapshot
        binding, call = scope
        return (self.scope.get() is scope
            and all(getattr(call, key) == entry["native_identity"][key] for key in _NATIVE)
            and binding._owner is values[7] and binding._authorized is values[8]
            and (binding.operation_id, binding.session_id, binding.turn_id,
                 binding.model, binding.requested_model, binding.automatic,
                 binding._max_output_tokens) == values[:7])

    def project(self, response, snapshot):
        t = _transport()
        if type(response) is not self.record:
            raise ValueError("application response type")
        nodes = 0
        def detach(value, depth=0):
            nonlocal nodes
            nodes += 1
            if nodes > 128 or depth > 8:
                raise ValueError("application receipt bound")
            if type(value) is self.record:
                if len(vars(value)) > 32:
                    raise ValueError("application receipt fields")
                return {k: detach(v, depth + 1) for k, v in vars(value).items()}
            if type(value) is list:
                if len(value) > 32:
                    raise ValueError("application receipt list")
                return [detach(v, depth + 1) for v in value]
            if value is None or type(value) in (bool, int):
                return value
            if type(value) is str:
                if len(value) > 256:
                    raise ValueError("application receipt text")
                value.encode("utf-8", "strict")
                return value
            raise ValueError("application receipt value")
        # Never serialize the answer, tools, headers or the entire response.
        receipt = detach(vars(response).get("application_observation"))
        t._shape(receipt, ("schema", "disposition", "effect_unknown", "turn_id",
                          "request_id", "routing", "serving_model", "usage"))
        entry = snapshot[2]
        if (receipt["schema"] != "mastermind.fabric_application_observation.v2"
                or receipt["disposition"] != "terminal" or receipt["effect_unknown"] is not False
                or receipt["turn_id"] != entry["operation_id"]
                or receipt["request_id"] != entry["request_id"]):
            raise ValueError("application original receipt mismatch")
        route = receipt["routing"]
        t._shape(route, _ROUTE_FIELDS)
        t._enum(route["schema"], {"mastermind.fabric_application_route.v1", "mastermind.fabric_application_route.v2"})
        for key in ("route_scope_digest", "selection_digest", "request_digest"):
            t._digest(route[key])
        t._enum(route["protocol"], {"chat", "responses", "harness"})
        t._digest(route["recipe_digest"], optional=route["pool"] == "go")
        expected_protocol = "chat" if route["pool"] == "go" else ("responses" if route["pool"] in {"bailian", "deepseek"} else "harness")
        if route["protocol"] != expected_protocol or route["pool"] == "go" and route["recipe_digest"] is not None:
            raise ValueError("application route protocol commitment")
        exact = route["schema"].endswith(".v2")
        t._digest(route["routed_request_digest"], optional=exact)
        if (exact and (route["routed_request_digest"] is not None
                       or route["requested_model"] != route["selected_model"])
                or not exact and route["requested_model"] is not None
                or t._scalar(route["requested_model"], "model") != entry["owner_model"]
                or receipt["serving_model"] != route["selected_model"]
                or vars(response).get("model") != receipt["serving_model"]):
            raise ValueError("application model commitment mismatch")
        for key in ("selected_model", "pool", "mode", "protocol", "driver", "profile", "source"):
            t._text(route[key])
        t._shape(route["route_scope"], ("schema", "pools"))
        if (route["route_scope"]["schema"] != "mastermind.application_route_scope.v1"
                or type(route["route_scope"]["pools"]) is not list
                or not 1 <= len(route["route_scope"]["pools"]) <= 32):
            raise ValueError("application route scope")
        for value in route["route_scope"]["pools"]:
            t._text(value)
        if (route["route_scope"]["pools"] != sorted(set(route["route_scope"]["pools"]))
                or route["pool"] not in route["route_scope"]["pools"]
                or t._hash(route["route_scope"]) != route["route_scope_digest"]):
            raise ValueError("application route scope commitment")
        output = route["output_contract"]
        t._shape(output, ("mode", "max_tokens"))
        t._integer(output["max_tokens"], positive=True)
        if output["mode"] != "hard_maximum" or output["max_tokens"] > entry["output_limit"]:
            raise ValueError("application output commitment")
        projected = {
            "schema": PROJECTION_SCHEMA, "receipt_sha256": t._hash(receipt),
            "routing_sha256": t._hash(route), "route_schema": route["schema"],
            "protocol": route["protocol"],
            "disposition": "terminal", "effect_unknown": False,
            "owner_request_sha256": route["request_digest"],
            "owner_routed_request_sha256": route["routed_request_digest"],
            "route_scope_sha256": route["route_scope_digest"],
            "selection_sha256": route["selection_digest"], "recipe_sha256": route["recipe_digest"],
            "requested_model": t._scalar(route["requested_model"], "model"),
            "selected_model": t._scalar(route["selected_model"], "model"),
            "serving_model": t._scalar(receipt["serving_model"], "model"),
            "output_max_tokens": output["max_tokens"], "usage": receipt["usage"],
        }
        validate_return(projected, entry)
        return projected


def qualify():
    """An unavailable optional seam cannot disable the historical HTTPX leaf."""
    try:
        from integrations.hermes_application_fabric import client as module, codec, structured
        path = Path(__file__).resolve().parent.parent / "hermes_application_fabric/client.py"
        if (type(module) is not ModuleType or Path(module.__file__).resolve() != path
                or hashlib.sha256(path.read_bytes()).hexdigest() != CLIENT_SHA256):
            return None
        for support in (codec, structured):
            selected = Path(support.__file__).resolve()
            if (type(support) is not ModuleType or selected.parent != path.parent
                    or selected.name not in SUPPORT_SHA256
                    or hashlib.sha256(selected.read_bytes()).hexdigest() != SUPPORT_SHA256[selected.name]):
                return None
        for name in ("to_owner_request", "to_hermes_response", "json_bytes", "MAX_REQUEST_BYTES", "MAX_RESULT_BYTES"):
            if getattr(module, name) is not getattr(codec, name):
                return None
        if module.prepare_structured_request is not structured.prepare_structured_request:
            return None
        source = Source(module, (codec, structured))
        for function in (source.create, source.check, source.request_id, source.convert):
            if (not inspect.isfunction(function) or function.__globals__ is not vars(module)
                    or Path(function.__code__.co_filename).resolve() != path):
                return None
        return source
    except Exception:
        return None


def validate_entry(entry):
    t = _transport()
    t._shape(entry, ("operation_id", "request_id", "native_identity", "content_sha256",
                     "content_fields", "model", "owner_model", "output_limit"))
    t._text(entry["operation_id"])
    t._text(entry["request_id"])
    t._shape(entry["native_identity"], _NATIVE)
    for value in entry["native_identity"].values():
        t._text(value)
    material = [entry["operation_id"], *(entry["native_identity"][key] for key in _NATIVE)]
    expected = "hermes:" + hashlib.sha256(json.dumps(
        material, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    if entry["request_id"] != expected:
        raise ValueError("application request identity commitment")
    t._digest(entry["content_sha256"])
    fields = entry["content_fields"]
    if (type(fields) is not list or len(fields) != len(set(fields))
            or any(type(key) is not str or key not in t._observation().CONTENT_FIELDS for key in fields)):
        raise ValueError("application content projection")
    for key in ("model", "owner_model"):
        t._validate_scalar(entry[key], "model")
    if entry["model"]["status"] != "observed_digest" or entry["owner_model"]["status"] not in {"null", "observed_digest"}:
        raise ValueError("application model unavailable")
    t._integer(entry["output_limit"], positive=True)
    if entry["output_limit"] > 32768:
        raise ValueError("application output bound")


def validate_return(value, entry):
    t = _transport()
    t._shape(value, ("schema", "receipt_sha256", "routing_sha256", "route_schema",
        "protocol", "disposition", "effect_unknown", "owner_request_sha256", "owner_routed_request_sha256",
        "route_scope_sha256", "selection_sha256", "recipe_sha256", "requested_model",
        "selected_model", "serving_model", "output_max_tokens", "usage"))
    if (value["schema"] != PROJECTION_SCHEMA or value["disposition"] != "terminal"
            or value["effect_unknown"] is not False):
        raise ValueError("application return disposition")
    t._enum(value["route_schema"], {"mastermind.fabric_application_route.v1", "mastermind.fabric_application_route.v2"})
    exact = value["route_schema"].endswith(".v2")
    for key in ("receipt_sha256", "routing_sha256", "owner_request_sha256",
                "route_scope_sha256", "selection_sha256"):
        t._digest(value[key])
    t._enum(value["protocol"], {"chat", "responses", "harness"})
    t._digest(value["recipe_sha256"], optional=value["protocol"] == "chat")
    if value["protocol"] == "chat" and value["recipe_sha256"] is not None:
        raise ValueError("application recipe commitment")
    t._digest(value["owner_routed_request_sha256"], optional=exact)
    for key in ("requested_model", "selected_model", "serving_model"):
        t._validate_scalar(value[key], "model")
    if (value["requested_model"] != entry["owner_model"]
            or value["selected_model"] != value["serving_model"]
            or value["selected_model"]["status"] != "observed_digest"
            or exact and (value["owner_routed_request_sha256"] is not None
                          or value["requested_model"] != value["selected_model"])
            or not exact and value["requested_model"] != {"status": "null"}):
        raise ValueError("application returned model commitment")
    t._integer(value["output_max_tokens"], positive=True)
    if value["output_max_tokens"] > entry["output_limit"]:
        raise ValueError("application returned output bound")
    t._shape(value["usage"], ("input_tokens", "output_tokens"))
    for count in value["usage"].values():
        if count is not None and (type(count) is not int or not 0 <= count <= 10**12):
            raise ValueError("application usage bound")
    if t._observation()._encoded_size(value) > MAX_RETURN_BYTES:
        raise ValueError("application return metadata bound")
