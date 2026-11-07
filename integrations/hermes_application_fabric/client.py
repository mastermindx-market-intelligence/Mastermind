"""A request view over an existing host-bound APPLICATION client.

The host supplies the authenticated owner handle. This module never constructs
an HTTP client, resolves a credential, admits an account, or invents a turn.
Native request metadata is correlation only; the host guard is independently
required before inference and before returning any executable tool response.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import math
from types import SimpleNamespace
from typing import Callable

from .codec import ID, json_bytes, to_hermes_response, to_owner_request, MAX_REQUEST_BYTES, MAX_RESULT_BYTES
from .errors import HermesFabricError
from .structured import prepare_structured_request


@dataclass(frozen=True)
class NativeCall:
    session_id: str
    task_id: str
    turn_id: str
    api_request_id: str

    def __post_init__(self):
        for value in (self.session_id, self.task_id, self.turn_id, self.api_request_id):
            if type(value) is not str or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
                raise HermesFabricError("hermes_fabric_context_invalid")


class _Record(SimpleNamespace):
    def model_dump(self, **_):
        def plain(value):
            if isinstance(value, _Record):
                return {k: plain(v) for k, v in vars(value).items()}
            if isinstance(value, list):
                return [plain(v) for v in value]
            return value
        return plain(self)

    def model_dump_json(self, **_):
        return json.dumps(self.model_dump(), ensure_ascii=False, allow_nan=False)


def _record(value):
    if type(value) is dict:
        return _Record(**{k: _record(v) for k, v in value.items()})
    if type(value) is list:
        return [_record(v) for v in value]
    return value


class UnsupportedAsyncClient:
    """Awaitable refusal; never allow native async wrapping to create HTTP."""
    HERMES_SKIP_ASYNC_WRAP = True
    api_key = None
    base_url = ""

    def __init__(self):
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **_):
        raise HermesFabricError("hermes_fabric_primary_sync_only")

    async def close(self):
        pass


class ApplicationBinding:
    """Trusted host composition, not an authentication or session registry.

    Retain this SAME binding and original owner client across Hermes facade
    reconstruction. Cross-process restoration belongs to the original owner;
    this adapter supplies no restore-by-ID constructor or replay mechanism.
    ``authorized`` must check the existing current role/session/grant owner.
    """
    def __init__(self, *_, **__):
        # A native transport alone does not prove Hermes service enrollment.
        # In particular, a Brain/Ask client must not become a Hermes identity.
        raise HermesFabricError("hermes_fabric_qualified_factory_required")

    @staticmethod
    def _validate_fields(*, operation_id, session_id, turn_id, model,
                         requested_model, authorized):
        if (type(operation_id) is not str or ID.fullmatch(operation_id) is None
                or type(model) is not str or ID.fullmatch(model) is None
                or type(requested_model) is not str or ID.fullmatch(requested_model) is None
                or type(session_id) is not str or not session_id
                or type(turn_id) is not str or not turn_id or not callable(authorized)):
            raise HermesFabricError("hermes_fabric_binding_invalid")

    @classmethod
    def from_factory(cls, factory, *, profile_id: str, operation_id: str,
                     session_id: str, turn_id: str, requested_model: str,
                     authorized: Callable[[NativeCall], bool],
                     prior_admission_possible: bool,
                     strict_model: str | None = None, strict_pool: str | None = None,
                     max_output_tokens: int = 4096, automatic: bool = False):
        """Existing authenticated role host only; no environment/key bootstrap.

        Role-specific factories must be enrolled by the APPLICATION owner. A
        Brain/Ask/text service identity cannot be borrowed for Hermes. Current
        owner versions without these relations refuse before credentials.
        """
        if prior_admission_possible is not False:
            # Restore/read belongs to the existing owner. Do not reconstruct a
            # fresh owner client from an uncertain or previously admitted ID.
            raise HermesFabricError("hermes_fabric_original_recovery_required")
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 32768:
            raise HermesFabricError("hermes_fabric_output_bound_invalid")
        if type(automatic) is not bool:
            raise HermesFabricError("hermes_fabric_host_selection_invalid")
        if strict_pool is not None and not automatic:
            # cap_id/provider_id is not a physical-account or pool selection
            # receipt. The incumbent owner must expose that qualified constraint.
            raise HermesFabricError("hermes_fabric_strict_pool_owner_extension_required")
        if strict_model is not None and (type(strict_model) is not str or ID.fullmatch(strict_model) is None):
            raise HermesFabricError("hermes_fabric_host_selection_invalid")
        # Validate all consumer fields before the owner resolves its internal
        # credential or constructs a turn. Auth is still checked per native call.
        cls._validate_fields(operation_id=operation_id, session_id=session_id,
            turn_id=turn_id, model=requested_model, requested_model=requested_model,
            authorized=authorized)
        from engine.provider_production_modes import ApplicationFabricFactory
        # Reserved integration relations, NOT enrollment or installed policy.
        # The existing owner's closed service registry must independently accept
        # this exact relation. Today it does not; these paths remain fail-closed.
        relations = {"mmmeta": ("hermes-meta-ceo", "hermes_meta_fabric"),
                     "mmsecretary": ("hermes-secretary", "hermes_secretary_fabric"),
                     "attended": ("hermes-attended", "hermes_attended_fabric")}
        if (type(factory) is not ApplicationFabricFactory or profile_id not in relations
                or (factory.lane, factory.service_mode_id) != relations[profile_id]):
            raise HermesFabricError("hermes_fabric_role_unqualified")
        bind_error = None
        try:
            if automatic and strict_model is not None:
                # Narrow before taking the inspection commitment. The owner's
                # immutable v3 constraint keeps pool/account choice with Fabric.
                factory = factory.with_requested_model(strict_model)
            inspected = factory.inspect()
            if automatic:
                from engine.fabric_inference_client import (
                    AUTO_INSPECTION_SCHEMA, EXACT_INSPECTION_SCHEMA, validate_auto_inspection,
                )
                inspected = validate_auto_inspection(inspected)
                expected_schema = EXACT_INSPECTION_SCHEMA if strict_model is not None else AUTO_INSPECTION_SCHEMA
                if (inspected["schema"] != expected_schema
                        or inspected["requested_model"] != strict_model):
                    raise HermesFabricError("hermes_fabric_strict_model_unavailable")
                if strict_pool is not None and inspected["route_scope"]["pools"] != [strict_pool]:
                    raise HermesFabricError("hermes_fabric_strict_pool_unavailable")
            elif "schema" in inspected or strict_model is not None and inspected["model"] != strict_model:
                raise HermesFabricError("hermes_fabric_strict_model_unavailable")
            # Preserve the exact inspected owner recipe; this is selection
            # narrowing, not an entitlement or an alternate selection policy.
            bound, _ = factory.with_inspection(inspected)._bind_with_workload(
                operation_id=operation_id, prior_admission_possible=False)
        except HermesFabricError as exc:
            bind_error = HermesFabricError(exc.code, effect_unknown=exc.effect_unknown)
        except Exception:
            bind_error = HermesFabricError("hermes_fabric_application_unavailable")
        if bind_error is not None:
            raise bind_error
        from engine.fabric_inference_client import FabricInferenceClient
        if type(bound) is not dict or type(bound.get("client")) is not FabricInferenceClient:
            raise HermesFabricError("hermes_fabric_application_owner_required", effect_unknown=True)
        owner = bound["client"]
        if automatic:
            from engine.fabric_inference_client import AUTO_BINDING_SCHEMA, EXACT_BINDING_SCHEMA
            qualified_shape = (set(bound) == {"schema", "client", "inspection"}
                and bound["schema"] == (EXACT_BINDING_SCHEMA if strict_model is not None else AUTO_BINDING_SCHEMA)
                and bound["inspection"] == inspected and owner.model == strict_model
                and owner.auto_inspection == inspected)
        else:
            qualified_shape = (set(bound) == {"client", "model", "provider", "cost_basis", "cap_id"}
                               and owner.model == bound["model"])
        if (type(owner) is not FabricInferenceClient or owner._native is not True
                or owner.operation_id != operation_id or not qualified_shape):
            # Do not replace, close, or reconstruct an unexpected original owner.
            raise HermesFabricError("hermes_fabric_application_owner_required",
                                    effect_unknown=True)
        instance = object.__new__(cls)
        instance._owner = owner
        instance.operation_id, instance.session_id, instance.turn_id = operation_id, session_id, turn_id
        instance.model, instance.requested_model = owner.model, requested_model
        instance.automatic = automatic
        instance._authorized = authorized
        instance._max_output_tokens = max_output_tokens
        return instance

    def check(self, call: NativeCall):
        try:
            allowed = (type(call) is NativeCall and call.session_id == self.session_id
                       and call.turn_id == self.turn_id and self._owner._closed is False
                       and self._authorized(call) is True)
        except Exception:
            allowed = False
        if not allowed:
            raise HermesFabricError("hermes_fabric_context_not_authorized")

    def request_id(self, call: NativeCall) -> str:
        # Pure wire encoding of the ORIGINAL identity. No timestamp, generation,
        # random suffix, retry count or model/account selector enters this key.
        material = [self.operation_id, call.session_id, call.task_id,
                    call.turn_id, call.api_request_id]
        return "hermes:" + hashlib.sha256(json.dumps(material,
            separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    def close(self):
        """Host-owned turn close, never provider-cancellation or release proof."""
        return self._owner.close()


_SCOPE = ContextVar("mastermind_hermes_application_call", default=None)


@contextmanager
def call_scope(binding: ApplicationBinding | None, call: NativeCall | None):
    # A nested failed/missing scope hides any outer scope instead of inheriting
    # another session's authority. The client performs all fail-closed checks.
    token = _SCOPE.set((binding, call))
    try:
        yield
    finally:
        _SCOPE.reset(token)


class HermesApplicationClient:
    """Always constructible OpenAI-shaped facade, including when unbound.

    Hermes's profile factory falls back to standard HTTP on construction errors.
    Refuse inside create(), never by returning None from profile.create_client.
    Request-client eviction closes this view, not the original APPLICATION turn.
    """
    # Native async conversion otherwise rebuilds AsyncOpenAI from these fields.
    # No async transport may reconstruct or escape this host-bound client.
    HERMES_SKIP_ASYNC_WRAP = True
    api_key = None
    base_url = ""

    def __init__(self, *, unsupported_use=False):
        self.chat = SimpleNamespace(completions=self)
        self.is_closed = False
        self._unsupported_use = unsupported_use

    def close(self):
        self.is_closed = True

    def create(self, **kwargs):
        if self._unsupported_use:
            raise HermesFabricError("hermes_fabric_primary_sync_only")
        if self.is_closed:
            raise HermesFabricError("hermes_fabric_client_closed")
        scope = _SCOPE.get()
        if not scope or type(scope[0]) is not ApplicationBinding or type(scope[1]) is not NativeCall:
            raise HermesFabricError("hermes_fabric_host_binding_required")
        binding, call = scope
        binding.check(call)
        if kwargs.get("model") != binding.requested_model:
            raise HermesFabricError("hermes_fabric_host_selection_mismatch")
        # Freeze the caller payload before the external owner sees it.
        request = json.loads(json_bytes(kwargs, MAX_REQUEST_BYTES))
        consumer_timeout = request.pop("timeout", None)
        if consumer_timeout is not None:
            # Hermes adds its SDK deadline after request-body construction.
            # The existing owner already owns a bounded hard deadline. Accept
            # only a consumer wait at least that long; never mutate its timeout
            # in flight or silently ignore a tighter requested deadline.
            if (type(consumer_timeout) not in (int, float)
                    or not math.isfinite(consumer_timeout) or consumer_timeout <= 0
                    or binding._owner._timeout > consumer_timeout):
                raise HermesFabricError("hermes_fabric_owner_deadline_not_bound")
        # The AUTO native label remains a label. Exact scoped selection carries
        # the original concrete model. Only the owner selects physical capacity.
        label = binding.requested_model if binding.automatic else binding.model
        request["model"] = label
        request, structured = prepare_structured_request(request)
        owner_request = to_owner_request(request, label)
        owner_request["model"] = binding.model
        # Validate the final emitted request, after native request overrides and
        # structured-output conversion. Agent constructor defaults are not a
        # bound on subsequent native kwargs.
        if owner_request["max_tokens"] > binding._max_output_tokens:
            raise HermesFabricError("hermes_fabric_native_output_bound_changed")
        request_id = binding.request_id(call)
        owner_error = None
        try:
            response = binding._owner.messages.create(request_id=request_id, **owner_request)
        except Exception as exc:
            # Native owner retains attempted IDs, active/uncertain state, usage
            # and original close. A new facade must never replace that owner.
            owner_error = HermesFabricError("hermes_fabric_owner_refused",
                effect_unknown=bool(getattr(exc, "effect_unknown", True)))
        if owner_error is not None:
            # Hermes traverses __context__ even when ``from None`` suppresses
            # its display. Raise outside except so no raw HTTP body/status can
            # reopen provider-specific retry, auth rotation or fallback.
            raise owner_error
        binding.check(call)  # Revoked/late results must not execute native tools.
        result_error = None
        try:
            selected_model = binding.model
            observation = None
            if binding.automatic:
                from engine.fabric_inference_client import ApplicationObservation
                observed = getattr(response, "application_observation", None)
                if type(observed) is not ApplicationObservation:
                    raise HermesFabricError("hermes_fabric_route_observation_missing")
                # The incumbent client has already verified the original/routed
                # digests, frozen route, serving model and token observations.
                # Never substitute the owner's possibly stale last observation.
                observation = observed.document
                if (observation["turn_id"] != binding.operation_id
                        or observation["request_id"] != request_id
                        or observation["effect_unknown"] is not False
                        or observation["disposition"] != "terminal"
                        or observation["serving_model"] != response.model):
                    raise HermesFabricError("hermes_fabric_route_observation_mismatch")
                selected_model = response.model
            payload = to_hermes_response(response, request_id=request_id,
                                         selected_model=selected_model)
            permitted_tools = {t["name"] for t in owner_request.get("tools", [])}
            returned_tools = payload["choices"][0]["message"].get("tool_calls", [])
            if any(t["function"]["name"] not in permitted_tools for t in returned_tools):
                raise HermesFabricError("hermes_fabric_unoffered_tool")
            choice = owner_request.get("tool_choice", {})
            if choice.get("type") == "none" and returned_tools:
                raise HermesFabricError("hermes_fabric_tool_choice_violated")
            if choice.get("type") in {"tool", "any"} and not returned_tools:
                raise HermesFabricError("hermes_fabric_tool_choice_violated")
            if choice.get("type") == "tool" and any(
                    t["function"]["name"] != choice["name"] for t in returned_tools):
                raise HermesFabricError("hermes_fabric_tool_choice_violated")
            if structured is not None:
                payload = structured.consume(payload)
            if observation is not None:
                payload["application_observation"] = observation
            json_bytes(payload, MAX_RESULT_BYTES)
        except HermesFabricError:
            # The provider may have completed even when its output is unusable.
            # The original owner still holds the real usage/terminal evidence.
            result_error = HermesFabricError("hermes_fabric_terminal_result_unusable")
        if result_error is not None:
            raise result_error
        payload["choices"][0]["message"].setdefault("tool_calls", None)
        return _record(payload)
