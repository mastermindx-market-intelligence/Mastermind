"""Supported Hermes v0.23 provider and middleware extension points."""
from __future__ import annotations

from .client import ApplicationBinding, HermesApplicationClient, NativeCall, call_scope, UnsupportedAsyncClient
from .errors import HermesFabricError, CodecError

PROVIDER = "mastermind-fabric"
AUTO_MODEL = f"{PROVIDER}/auto"
AUTH_TYPE = "mastermind_application_session"
INSTALLED_HERMES_SHA = "2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19"


def classify_error(error, **_):
    # This hook is scoped by Hermes to this provider. Watchdog errors can be
    # raised outside facade.create(); none authorize another provider attempt.
    # Native unknown+ValueError/TypeError has a special fallback branch, so a
    # local protocol-shape error uses the existing terminal format taxonomy.
    reason = "format_error" if isinstance(error, (ValueError, TypeError)) else "unknown"
    return {"reason": reason, "retryable": False, "should_compress": False,
            "should_rotate_credential": False, "should_fallback": False}


def build_profile():
    # Import only in the real native host; pure codec/client tests need no Hermes
    # installation. This function installs nothing and opens no socket.
    from providers.base import ProviderProfile

    class Profile(ProviderProfile):
        def create_client(self, **_):
            return HermesApplicationClient()

    profile = Profile(name=PROVIDER, api_mode="chat_completions",
                   display_name="Mastermind Fabric", auth_type=AUTH_TYPE,
                   env_vars=(), base_url="", supports_streaming=False,
                   supports_health_check=False, supports_model_listing=False,
                   supports_vision=False, supports_vision_tool_messages=False,
                   default_max_tokens=4096, classify_api_error=classify_error)
    # The pinned role owner predates the attended catalog field. Its explicit
    # programmatic selection remains supported without advertising a fallback.
    if "static_models" in ProviderProfile.__dataclass_fields__:
        profile.static_models = (AUTO_MODEL,)
    if "host_bound_runtime" in ProviderProfile.__dataclass_fields__:
        profile.host_bound_runtime = True
    return profile


def _resolve_native_client(request):
    """One arm of Hermes's EXISTING auth-type table; no credentials or routing.

    Private v0.23 compatibility seam, qualified at INSTALLED_HERMES_SHA. Primary
    construction sets raw_codex=True; that flag is not a request for another
    provider here. Unsupported async/vision views refuse when invoked.
    """
    if request.async_mode:
        return UnsupportedAsyncClient(), request.model
    unsupported = (request.provider != PROVIDER
        or bool(request.is_vision) or bool(request.explicit_api_key)
        or bool(request.explicit_base_url))
    return HermesApplicationClient(unsupported_use=unsupported), request.model


def register_native_provider():
    """Register before constructing an attended host's agents, never live-swap.

    This extends the incumbent native dispatch table; it is not another router.
    Profile-home config, profile and auth-type collisions must fail closed.
    No CLI runtime-provider ladder, auth store, environment key or pool is added.
    """
    from providers import get_provider_profile, register_provider
    from agent.auxiliary_client_registry import REGISTRY_AUTHTYPE_ARMS
    from hermes_cli.runtime_provider_custom import has_named_custom_provider

    if has_named_custom_provider(PROVIDER):
        raise HermesFabricError("hermes_fabric_custom_provider_collision")
    existing = get_provider_profile(PROVIDER)
    if existing is not None and (
            existing.auth_type != AUTH_TYPE or
            type(existing).create_client.__module__ != __name__):
        raise HermesFabricError("hermes_fabric_profile_collision")
    if REGISTRY_AUTHTYPE_ARMS.get(AUTH_TYPE) not in (None, _resolve_native_client):
        raise HermesFabricError("hermes_fabric_auth_type_collision")
    register_provider(build_profile())
    REGISTRY_AUTHTYPE_ARMS[AUTH_TYPE] = _resolve_native_client


def _require_native_provider():
    """Agent construction validates startup registration; it never replaces it."""
    from providers import get_provider_profile
    from agent.auxiliary_client_registry import REGISTRY_AUTHTYPE_ARMS
    from hermes_cli.runtime_provider_custom import has_named_custom_provider
    profile = get_provider_profile(PROVIDER)
    if (has_named_custom_provider(PROVIDER) or profile is None
            or profile.auth_type != AUTH_TYPE
            or type(profile).create_client.__module__ != __name__
            or REGISTRY_AUTHTYPE_ARMS.get(AUTH_TYPE) is not _resolve_native_client):
        raise HermesFabricError("hermes_fabric_native_startup_required")
    return profile


def create_primary_agent(*, model: str, **options):
    """Programmatic native host startup, using its existing session lifecycle.

    The host separately registers execution middleware with its authenticated
    binding resolver. A missing resolver is an unbound facade and cannot infer.
    Naked CLI runtime/auth resolution is not this integration entrypoint.
    """
    forbidden = {"provider", "requested_provider", "api_mode", "api_key", "base_url",
        "credential_pool", "fallback_model", "acp_command", "acp_args", "command", "args"}
    if set(options) & forbidden:
        raise HermesFabricError("hermes_fabric_host_runtime_override")
    _require_native_provider()
    from run_agent import AIAgent
    agent = AIAgent(model=model, provider=PROVIDER, requested_provider=PROVIDER,
        api_mode="chat_completions", api_key=None, base_url=None,
        credential_pool=None, fallback_model={}, **options)
    if (agent.provider != PROVIDER or agent.api_mode != "chat_completions"
            or type(agent.client) is not HermesApplicationClient
            or agent.api_key not in (None, "") or agent.base_url not in (None, "")):
        raise HermesFabricError("hermes_fabric_native_startup_mismatch")
    return agent


def execution_middleware(resolve_binding):
    """Compose only with the existing authenticated host/session resolver.

    This callback does no model inference. Hermes skips failed middleware, so
    resolver failures install an empty scope and still call next_call; the client
    then refuses. On an authorized native abort, the SAME owner's close() fences
    further use and retains its original close result. It does not prove provider
    cancellation or lease release. Native request threads propagate ContextVars.
    """
    def middleware(*, request, next_call, **context):
        binding = call = None
        is_fabric = context.get("provider") == PROVIDER
        if is_fabric:
            try:
                call = NativeCall(**{key: context[key] for key in
                    ("session_id", "task_id", "turn_id", "api_request_id")})
                binding = resolve_binding(call)
                if type(binding) is not ApplicationBinding:
                    binding = None
            except Exception:
                binding = call = None
        error, may_close = None, False
        if binding is not None and call is not None:
            try:
                binding.check(call)
                may_close = True
            except HermesFabricError:
                pass  # The facade remains the mandatory authorization check.
        with call_scope(binding, call):
            try:
                result = next_call(request)
            except Exception as exc:
                if not is_fabric:
                    raise
                original = exc
                # The installed native chain wraps downstream exceptions. Only
                # its exact wrapper and our own types may carry a known effect
                # disposition; arbitrary error attributes are not receipts.
                try:
                    from hermes_cli.middleware import _DownstreamExecutionError
                except ImportError:
                    _DownstreamExecutionError = None  # Pure local unit tests.
                for _ in range(8):
                    if type(original) is not _DownstreamExecutionError:
                        break
                    original = original.original
                known = type(original) in (HermesFabricError, CodecError)
                error = HermesFabricError(original.code if known else "hermes_fabric_native_execution_failed",
                    effect_unknown=original.effect_unknown if known else True)
        if error is not None:
            if may_close:
                # Invalidate via the incumbent owner before native redirect or
                # recovery can use a fresh api_request_id after a late result.
                # close() is once-only and preserves its own unknown outcome.
                try:
                    binding.close()
                except Exception:
                    # Preserve the bounded original failure if an incompatible
                    # owner ever violates its non-throwing close contract.
                    pass
            # ``from None`` leaves __context__ populated; native recovery reads
            # it. Raising here detaches raw status/body and watchdog exceptions.
            raise error
        return result
    return middleware


def register_middleware(ctx, resolve_binding):
    """Host-authorized plugin setup; returned native handle owns removal."""
    return ctx.register_middleware("llm_execution", execution_middleware(resolve_binding))
