"""Bind the native admitted gateway turn to the original APPLICATION owner."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from .attended_host import AttendedHost
from .errors import HermesFabricError
from .native import AUTO_MODEL, PROVIDER


def _original_factory():
    from engine import provider_production_modes as owner
    return owner.make_application_fabric_factory(
        mode_id="shared_fabric", lane="hermes-attended",
        service_mode_id="hermes_attended_fabric",
        workload_cfg={"workload_profile": "hermes_attended", "provider_order": ["fabric"]},
        root=Path(owner.__file__).resolve().parent.parent)


def _owner_variant(factory):
    """Read the current credential-free selection from the one APPLICATION owner."""
    from .codec import ID
    from engine.fabric_inference_client import AUTO_INSPECTION_SCHEMA, validate_auto_inspection
    inspected = factory.inspect()
    if type(inspected) is not dict:
        raise HermesFabricError("hermes_fabric_application_unavailable")
    if "schema" not in inspected:
        model = inspected.get("model")
        if type(model) is not str or ID.fullmatch(model) is None:
            raise HermesFabricError("hermes_fabric_host_selection_invalid")
        return False, model
    inspected = validate_auto_inspection(inspected)
    if (inspected["schema"] != AUTO_INSPECTION_SCHEMA
            or inspected["requested_model"] is not None):
        raise HermesFabricError("hermes_fabric_host_selection_invalid")
    return True, None


def available_models():
    """An eligibility observation only; never bind, acquire credentials or admit."""
    automatic, model = _owner_variant(_original_factory())
    return [AUTO_MODEL if automatic else model]


def _routing_selection(factory, requested_model):
    """The binding narrows AUTO before freezing its own current inspection."""
    from .codec import ID
    if type(requested_model) is not str or ID.fullmatch(requested_model) is None:
        raise HermesFabricError("hermes_fabric_host_selection_invalid")
    automatic, _ = _owner_variant(factory)
    if not automatic and requested_model == AUTO_MODEL:
        raise HermesFabricError("hermes_fabric_auto_owner_required")
    return automatic, None if requested_model == AUTO_MODEL else requested_model


@contextmanager
def _gateway_scope(host, runner, context, route, admitted):
    from gateway.config import Platform
    from gateway.session_provider_context import AdmittedProviderTurn
    if (type(admitted) is not AdmittedProviderTurn
            or admitted.context is not context or admitted.authority.runner is not runner
            or context.source.platform != Platform.LOCAL or not admitted.current()):
        raise HermesFabricError("hermes_fabric_native_admission_required")
    if runner._refresh_fallback_model() not in (None, {}, []):
        raise HermesFabricError("hermes_fabric_host_runtime_override")
    try:
        factory = _original_factory()
        automatic, strict_model = _routing_selection(factory, route["model"])
    except HermesFabricError:
        raise
    except Exception:
        raise HermesFabricError("hermes_fabric_application_unavailable") from None
    turn = host.admitted_turn(factory=factory, operation_id=admitted.operation_id,
        session_id=context.session_id, task_id=context.session_id,
        requested_model=route["model"], strict_model=strict_model, automatic=automatic,
        authorized=admitted.current, prior_admission_possible=False)
    turn.attach_gateway_context(context)
    with host.activate(turn):
        yield turn


def register(ctx):
    """The native PluginManager owns registration and unload; no alternate host."""
    from providers.base import ProviderProfile
    from gateway.session_authority import LiveSession
    from hermes_cli.plugins import VALID_HOOKS
    if ("host_bound_runtime" not in ProviderProfile.__dataclass_fields__
            or "host_provider_claim" not in LiveSession.__dataclass_fields__
            or "provide_gateway_turn_context" not in VALID_HOOKS):
        raise HermesFabricError("hermes_fabric_gateway_extension_required")
    host = AttendedHost(ctx)

    def provide(*, provider, runner, turn_context, turn_route, admitted, **_):
        if provider == PROVIDER:
            return _gateway_scope(host, runner, turn_context, turn_route, admitted)
        return None

    try:
        ctx.register_hook("provide_gateway_turn_context", provide)
        ctx.on_unload(host.dispose)
    except Exception:
        host.dispose()
        raise
    return host
