"""Bind the native admitted gateway turn to the original APPLICATION owner."""
from __future__ import annotations

from contextlib import contextmanager

from .attended_host import AttendedHost
from .errors import HermesFabricError
from .native import AUTO_MODEL, PROVIDER, _require_native_provider
from .source_context import attended_package_digest, open_attended_source_context


def _original_factory(sources):
    return sources.factory()


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


def available_models(sources):
    """An eligibility observation only; never bind, acquire credentials or admit."""
    with sources.operation() as operation:
        automatic, model = _owner_variant(_original_factory(operation))
        operation.check()
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
def _gateway_scope(host, sources, home_current, runner, context, route, admitted):
    from gateway.config import Platform
    from gateway.session_provider_context import AdmittedProviderTurn
    if (type(admitted) is not AdmittedProviderTurn
            or admitted.context is not context or admitted.authority.runner is not runner
            or context.source.platform != Platform.LOCAL or not admitted.current()
            or not home_current()):
        raise HermesFabricError("hermes_fabric_native_admission_required")
    if runner._refresh_fallback_model() not in (None, {}, []):
        raise HermesFabricError("hermes_fabric_host_runtime_override")
    # The operation retains the original source owner through original close,
    # even if native plugin unload releases the plugin's own reference.
    with sources.operation() as operation:
        try:
            factory = _original_factory(operation)
            automatic, strict_model = _routing_selection(factory, route["model"])
        except HermesFabricError:
            raise
        except Exception:
            raise HermesFabricError("hermes_fabric_application_unavailable") from None

        def authorized(call=None):
            try:
                operation.check()
                return home_current() and admitted.current(call)
            except Exception:
                return False

        turn = host.admitted_turn(factory=factory, operation_id=admitted.operation_id,
            session_id=context.session_id, task_id=context.session_id,
            requested_model=route["model"], strict_model=strict_model, automatic=automatic,
            authorized=authorized, prior_admission_possible=False)
        turn.attach_gateway_context(context)
        with host.activate(turn):
            yield turn


def register(ctx):
    """The native PluginManager owns registration and unload; no alternate host."""
    from providers import bound_profile_resolver
    from providers.base import ProviderProfile
    from gateway.session_authority import LiveSession
    from hermes_cli.plugins import VALID_HOOKS
    from hermes_constants import get_hermes_home, hermes_home_key
    if ("host_bound_runtime" not in ProviderProfile.__dataclass_fields__
            or "host_provider_claim" not in LiveSession.__dataclass_fields__
            or "provide_gateway_turn_context" not in VALID_HOOKS):
        raise HermesFabricError("hermes_fabric_gateway_extension_required")
    profile, _ = bound_profile_resolver()(PROVIDER)
    home_key = ctx._manager.scope_key
    if (profile is None or _require_native_provider() is not profile
            or profile.host_bound_runtime is not True
            or hermes_home_key(get_hermes_home()) != home_key):
        raise HermesFabricError("hermes_fabric_home_provider_required")
    sources = open_attended_source_context(adapter_package_sha256=attended_package_digest())
    host = None
    prior_catalog = profile.picker_catalog

    def home_current():
        return (host is not None and not host._retired
                and hermes_home_key(get_hermes_home()) == home_key
                and bound_profile_resolver()(PROVIDER)[0] is profile)

    def catalog(_force_refresh=False):
        try:
            return available_models(sources) if home_current() else []
        except Exception:
            return []

    def dispose():
        try:
            if host is not None:
                host.dispose()
        finally:
            if profile.picker_catalog is catalog:
                profile.picker_catalog = prior_catalog
            sources.close()

    def provide(*, provider, runner, turn_context, turn_route, admitted, **_):
        if provider == PROVIDER:
            return _gateway_scope(host, sources, home_current, runner, turn_context, turn_route, admitted)
        return None

    try:
        host = AttendedHost(ctx)
        profile.picker_catalog = catalog
        ctx.register_hook("provide_gateway_turn_context", provide)
        ctx.on_unload(dispose)
    except Exception:
        dispose()
        raise
    return host
