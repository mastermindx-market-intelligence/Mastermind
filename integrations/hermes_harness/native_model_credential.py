"""Resolve one primary BYOK model key through the existing WP2 credential owner.

Only the primary role's reviewed key name is materialized. This is *not*
an authorization for an Executive effect, global key export, model call,
provider fallback, or host computer tool.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from functools import wraps
import inspect
from pathlib import Path
from types import ModuleType

from integrations.hermes_models.contract import PROFILE_PRIMARY, native_provider
from integrations.hermes_models.credentials import CredentialUnavailable, load_credential
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.profile import RuntimeProfile


def primary_model_env(
    profile: RuntimeProfile,
    secret_values: Mapping[str, str],
    consumer=None,
) -> dict[str, str]:
    """Resolve one primary BYOK model key through the existing WP2 credential owner.

    When a qualified optional consumer is installed, the Executive connection
    must keep its own OAuth client reference: it never borrows the model's
    provider, its credential name or its client.
    """
    if not isinstance(profile, RuntimeProfile) or profile.role not in PROFILE_PRIMARY:
        raise RuntimeRefusal("NATIVE_MODEL_ROLE_UNQUALIFIED")
    if profile.extension_allowlist:
        raise RuntimeRefusal("NATIVE_EXTENSION_NOT_INSTALLED")
    try:
        spec = native_provider(profile.role, profile.native_provider_id)
    except (ValueError, KeyError):
        raise RuntimeRefusal("NATIVE_MODEL_SELECTION_UNQUALIFIED") from None
    if spec.provider_id == "cursor-pool" or not spec.enabled_in_profile:
        raise RuntimeRefusal("NATIVE_MODEL_PROVIDER_UNQUALIFIED")
    if consumer is not None:
        _assert_consumer_credential_separate(spec, consumer)
    try:
        value = load_credential(spec, secret_values)
    except CredentialUnavailable:
        raise RuntimeRefusal("NATIVE_MODEL_CREDENTIAL_UNAVAILABLE") from None
    return {spec.credential_env: value}


def _assert_consumer_credential_separate(spec, consumer) -> None:
    """The consumer must never borrow the model's provider identity.

    The Executive connection is authenticated by its own OAuth client
    reference, held by the incumbent OAuth owner and its token storage. It is
    never the model's provider, its credential name, or its client.
    """
    from integrations.hermes_harness.native_executive_consumer import (
        publication_from_document,
    )

    publication = publication_from_document(consumer)
    client_id = publication.mcp.client_id
    forbidden = {
        spec.credential_env, spec.provider_id, spec.hermes_name, spec.display_name,
        spec.served_model,
    }
    if client_id in forbidden:
        raise RuntimeRefusal("NATIVE_CONSUMER_MODEL_CREDENTIAL_ALIAS_REFUSED")


# Child-side evidence belongs to this existing credential owner. It observes
# already-performed native reads; it does not resolve, export or refresh a key.
_CREDENTIAL_SOURCES = {
    "hermes_cli/runtime_provider.py": "d60a99f56c55f1d0b41f7d9f0b812625eb0339fe96b6ac19861831ca1c4aaa43",
    "hermes_cli/runtime_provider_custom.py": "bab0e7b68ce96dfd9fdea4aaad4f0e1b697c2e80917195b2d7bc5c5934285972",
    "agent/secret_scope.py": "dce64ce99a6966836108e202e1db41c4be97bd3dad41a79e357f39b8d7e90dec",
    "agent/client_lifecycle.py": "4e8a80556184c415256934c50e6191b840910867fe68d36efc263440ea7b7dd2",
    "agent/agent_runtime_helpers.py": "7725dfa3b5c12e2ec289e86a2f83eb99dc75052687aa9cb4d2e71bc3f770b5d4",
    "gateway/session_worker_construct.py": "360680d541fb91b91d2f16d021f8ac6e2082f1751921bacf63371e0bb8db040d",
}
_AUTH_READ = ContextVar("mastermind_native_original_credential_read", default=None)


def _same_private_key(left, right):
    # This comparison never supplies a digest, length or value to evidence.
    return type(left) is str and type(right) is str and bool(left) and left == right


class _CredentialScope:
    """One private contribution to an existing execution scope, never a store."""

    def __init__(self, installation, scope):
        self.installation, self.scope = installation, scope
        self._key = self._capture = self._pending_route = self._agent = None
        self._resolution_seen = False
        self._status = "unavailable"

    def __repr__(self):
        return "<NativeCredentialObservation>"

    def current(self, agent=None):
        # Caller holds the existing event/scope locks. Transport checks the
        # approval generation outside them; never re-enter _tool_current here.
        scope = self.scope
        return (not scope.closed and scope.current()
            and scope.transport.credential_scope is self
            and self.installation.current()
            and (agent is None or (self._agent is agent and scope.adopted(agent))))

    def _forget(self, *, conflicting=False):
        if self._status != "conflicting":
            self._status = "conflicting" if conflicting else "unavailable"
        self._key = self._capture = self._pending_route = self._agent = None

    def discard(self):
        # Error fallback is negative-only and performs no callbacks or I/O.
        # Close the status first so another observer cannot restore a positive.
        _CredentialScope._forget(self)

    def unavailable(self, *, conflicting=False):
        with self.scope.live.event_stream.lock, self.scope.lock:
            self._forget(conflicting=conflicting)

    def begin_resolution(self, eligible):
        scope = self.scope
        with scope.live.event_stream.lock, scope.lock:
            if not self.current():
                return None
            # A second/unrelated resolution cannot replace the original turn's
            # candidate. The next admission obtains its own existing scope.
            if self._resolution_seen:
                self._forget()
                return None
            self._resolution_seen = True
            self._forget()
            if not eligible:
                return None
            capture = {"owner": self, "key": None, "conflicting": False, "missing": False}
            self._capture = capture
            return capture

    def note_read(self, capture, value):
        scope = self.scope
        with scope.live.event_stream.lock, scope.lock:
            if not self.current() or self._capture is not capture:
                return
            if type(value) is not str or not value.strip():
                capture["missing"] = True
                return
            selected = value.strip()  # The original get_secret_str caller strips.
            if capture["key"] is None:
                capture["key"] = selected
            elif not _same_private_key(capture["key"], selected):
                capture["conflicting"] = True

    def finish_resolution(self, capture, result):
        scope, spec = self.scope, self.installation.spec
        with scope.live.event_stream.lock, scope.lock:
            if not self.current() or self._capture is not capture:
                return
            self._capture = None
            if capture["conflicting"]:
                self._forget(conflicting=True)
                return
            if (capture["missing"] or type(result) is not dict or result.get("provider") != "custom"
                    or result.get("requested_provider") != spec.hermes_name
                    or result.get("api_mode") != "chat_completions"
                    or result.get("base_url") != spec.base_url
                    or result.get("source") != "custom_provider:" + spec.display_name
                    or result.get("credential_pool") is not None
                    or not _same_private_key(capture["key"], result.get("api_key"))):
                self._forget()
                return
            self._key = capture["key"]
            self._status = "resolved"

    def _runtime_matches(self, runtime):
        spec = self.installation.spec
        return (type(runtime) is dict and runtime.get("provider") == "custom"
            and runtime.get("requested_provider") == spec.hermes_name
            and runtime.get("api_mode") == "chat_completions"
            and runtime.get("base_url") == spec.base_url
            and runtime.get("credential_pool") is None
            and _same_private_key(self._key, runtime.get("api_key")))

    def capture_route(self, original, turn, args, kwargs):
        """The actual original resolve-agent arguments, before native use."""
        scope = self.scope
        with scope.live.event_stream.lock, scope.lock:
            if not self.current() or self._status != "resolved" or self._pending_route is not None:
                self._forget()
                return None
            route = inspect.signature(original).bind(turn, *args, **kwargs).arguments["turn_route"]
            if (type(route) is not dict or route.get("model") != self.installation.spec.served_model
                    or not self._runtime_matches(route.get("runtime"))):
                self._forget(conflicting=True)
                return None
            token = object()
            self._pending_route = (token, turn, route)
            return token

    def adopt_route(self, claim, token, original, args, kwargs):
        """Bind after the incumbent memory/turn owner adopts the actual agent."""
        scope = self.scope
        with scope.live.event_stream.lock, scope.lock:
            pending = self._pending_route
            self._pending_route = None
            factory = scope.binding.memory_factory
            actual = inspect.signature(original).bind(claim.turn, claim.agent, *args, **kwargs).arguments["turn_route"]
            if (not self.current() or self._status != "resolved" or pending is None
                    or pending[0] is not token or pending[1] is not claim.turn
                    or claim.scope is not scope or claim.factory is not factory
                    or factory.current_claim() is not claim
                    or not factory.evaluation_history_current(claim, claim.agent)
                    or not self._runtime_matches(pending[2].get("runtime"))
                    or type(actual) is not dict or not self._runtime_matches(actual.get("runtime"))):
                self._forget()
                return
            agent = claim.agent
            spec = self.installation.spec
            if (getattr(agent, "model", None) != spec.served_model
                    or getattr(agent, "provider", None) != "custom"
                    or getattr(agent, "requested_provider", None) != spec.hermes_name
                    or getattr(agent, "api_mode", None) != "chat_completions"
                    or getattr(agent, "base_url", None) != spec.base_url):
                self._forget(conflicting=True)
                return
            self._agent = agent
            self._status = "adopted"

    def dispatch(self, agent):
        return _CredentialDispatch(self, agent)

    def close(self):
        # Original agent/SDK lifetime remains native. Release only our private
        # references; this is not a claim that immutable strings were zeroized.
        self._forget()


class _CredentialDispatch:
    """Private actual request-client join, discarded with the original dispatch."""

    def __init__(self, owner, agent):
        self.owner, self.agent = owner, agent
        self._candidate = self._bound = None
        self._checkout_ticket = self._create_ticket = None
        self._checkout_seen = False
        self._state = "pending"

    def __repr__(self):
        return "<NativeCredentialRequest>"

    def current(self):
        return (self.owner._status == "adopted" and self.owner.current(self.agent)
            and self._state not in {"unavailable", "conflicting"})

    def _forget(self, *, conflicting=False):
        if self._state != "conflicting":
            self._state = "conflicting" if conflicting else "unavailable"
        self._candidate = self._bound = self._checkout_ticket = self._create_ticket = None

    def discard(self):
        # Only removes evidence eligibility and private references.
        _CredentialDispatch._forget(self)

    def fail(self, *, conflicting=False):
        with self.owner.scope.live.event_stream.lock, self.owner.scope.lock:
            self._forget(conflicting=conflicting)

    def _kwargs_match(self, kwargs):
        return (type(kwargs) is dict
            and _same_private_key(self.owner._key, kwargs.get("api_key"))
            and str(kwargs.get("base_url", "")).rstrip("/") == self.owner.installation.spec.base_url)

    def begin_checkout(self, kwargs):
        with self.owner.scope.live.event_stream.lock, self.owner.scope.lock:
            if not self.current() or self._checkout_seen:
                self._forget()
                return None
            self._checkout_seen = True
            if not self._kwargs_match(kwargs):
                self._forget(conflicting=True)
                return None
            self._checkout_ticket = object()
            return self._checkout_ticket

    def checkout(self, ticket, kwargs, returned):
        with self.owner.scope.live.event_stream.lock, self.owner.scope.lock:
            if not self.current() or ticket is None or self._checkout_ticket is not ticket:
                self._forget()
                return
            self._checkout_ticket = None
            if not self._kwargs_match(kwargs):
                self._forget(conflicting=True)
                return
            if type(returned) is not tuple or len(returned) != 2:
                self._forget()
                return
            cached, stale = returned
            if cached is not None:
                if stale is not None:
                    self._forget()
                    return
                self._candidate = cached

    def begin_create(self, kwargs):
        with self.owner.scope.live.event_stream.lock, self.owner.scope.lock:
            if (not self.current() or not self._checkout_seen or self._candidate is not None
                    or self._create_ticket is not None):
                self._forget()
                return None
            if not self._kwargs_match(kwargs):
                self._forget(conflicting=True)
                return None
            self._create_ticket = object()
            return self._create_ticket

    def created(self, ticket, kwargs, client):
        with self.owner.scope.live.event_stream.lock, self.owner.scope.lock:
            if not self.current() or ticket is None or self._create_ticket is not ticket:
                self._forget()
                return
            self._create_ticket = None
            if not self._kwargs_match(kwargs):
                self._forget(conflicting=True)
                return
            self._candidate = client

    def bind(self, client):
        with self.owner.scope.live.event_stream.lock, self.owner.scope.lock:
            if not self.current() or not self._checkout_seen or self._candidate is not client:
                self._forget()
                return
            if type(client) is not self.owner.installation.sdk_class:
                self._forget()
                return
            if not _same_private_key(self.owner._key, getattr(client, "api_key", None)):
                self._forget(conflicting=True)
                return
            self._bound = client
            self._state = "bound"

    def client_status(self):
        with self.owner.scope.live.event_stream.lock, self.owner.scope.lock:
            if self._state == "conflicting" or self.owner._status == "conflicting":
                return "conflicting"
            return "matched" if self.current() and self._state == "bound" else "unavailable"

    def mechanism(self, client, request):
        # Called at the original HTTP-send boundary. Return no header,
        # credential, length, hash, account, client pointer or realm ID.
        with self.owner.scope.live.event_stream.lock, self.owner.scope.lock:
            if not self.current() or self._state != "bound":
                return ("conflicting" if self._state == "conflicting"
                    or self.owner._status == "conflicting" else "unavailable")
            if (getattr(self._bound, "_client", None) is not client
                    or not _same_private_key(self.owner._key, getattr(self._bound, "api_key", None))):
                self._forget(conflicting=True)
                return "conflicting"
            values = request.headers.get_list("authorization")
            if len(values) != 1 or not _same_private_key("Bearer " + self.owner._key, values[0]):
                self._forget(conflicting=True)
                return "conflicting"
            return "API_KEY"

    def close(self):
        with self.owner.scope.live.event_stream.lock, self.owner.scope.lock:
            self._forget()


class NativeCredentialObservation:
    """An optional child-side leaf on the existing transport installation."""

    def __init__(self, binding, *, spec=None, current=None, commit=None, sdk_class=None):
        self.binding, self.spec, self.sdk_class = binding, spec, sdk_class
        self._current, self._commit = current, commit

    def current(self):
        try:
            return self._current is not None and self._current()
        except Exception:
            return False

    def commit(self):
        if self._commit is not None:
            self._commit()

    def scope(self, scope):
        return _CredentialScope(self, scope) if self.current() else None


def prepare_native_credential_observation(binding, vendor, profile):
    """Qualify first; observe original reads/calls without performing another."""
    from integrations.hermes_runtime import native_request_observation as request_owner
    from integrations.hermes_runtime import native_transport_observation as transport_owner
    from integrations.hermes_runtime.native_gateway_entry import _digest, _vendor_module
    from integrations.hermes_harness.native_byok import _expected_providers
    try:
        if (type(profile) is not RuntimeProfile or profile.role != "mmmeta"
                or profile.role != binding.role):
            return NativeCredentialObservation(binding)
        spec = native_provider(profile.role, profile.native_provider_id)
        if spec.provider_id != "zai.glm-5.3":
            return NativeCredentialObservation(binding)
        modules = {}
        for path, digest in _CREDENTIAL_SOURCES.items():
            if _digest(Path(vendor) / path, maximum=512 * 1024) != digest:
                return NativeCredentialObservation(binding)
            module = _vendor_module(path.removesuffix(".py").replace("/", "."), vendor)
            if type(module) is not ModuleType or getattr(module, "_mmx_credential_observation_bound", False):
                return NativeCredentialObservation(binding)
            modules[module.__name__] = module
        core = modules["hermes_cli.runtime_provider"]
        custom = modules["hermes_cli.runtime_provider_custom"]
        secrets = modules["agent.secret_scope"]
        lifecycle = modules["agent.client_lifecycle"]
        helpers = modules["agent.agent_runtime_helpers"]
        worker = modules["gateway.session_worker_construct"]
        original = request_owner._original_function
        resolve = original(custom, "_resolve_named_custom_runtime")
        read = original(secrets, "_environ_or")
        create = original(helpers, "create_openai_client")
        route = original(worker, "route_runtime")
        klass = lifecycle.ClientLifecycleMixin
        checkout = klass._checkout_request_slot
        create_request = klass._create_request_openai_client
        if (core._resolve_named_custom_runtime is not resolve
                or klass.__module__ != lifecycle.__name__
                or any(not inspect.isfunction(fn) or fn.__globals__ is not vars(lifecycle)
                    or Path(fn.__code__.co_filename).resolve() != Path(lifecycle.__file__).resolve()
                    for fn in (checkout, create_request))):
            return NativeCredentialObservation(binding)
        from openai import OpenAI
        expected_entry = _expected_providers()[spec.hermes_name]
    except Exception:
        return NativeCredentialObservation(binding)

    def active():
        try:
            scope = request_owner._current.get()
            if scope is None or scope.binding is not binding or scope.closed:
                return None
            value = getattr(scope.transport, "credential_scope", None)
            return value if type(value) is _CredentialScope and value.installation is installation else None
        except Exception:
            return None

    def dispatch():
        try:
            context = transport_owner._dispatch_context.get()
            owner = active()
            if type(context) is not transport_owner._Dispatch or owner is None:
                return None
            value = context.credential
            return value if (context.contribution is owner.scope.transport
                and type(value) is _CredentialDispatch and value.owner is owner
                and value.agent is context.agent) else None
        except Exception:
            return None

    def current():
        return (binding.transport_installation.credential_installation is installation
            and custom._resolve_named_custom_runtime is observed_resolve
            and core._resolve_named_custom_runtime is observed_resolve
            and secrets._environ_or is observed_read
            and lifecycle.ClientLifecycleMixin is klass
            and klass._checkout_request_slot is observed_checkout
            and klass._create_request_openai_client is create_request
            and helpers.create_openai_client is observed_create
            and worker.route_runtime is route)

    @wraps(read)
    def observed_read(name, default):
        value = read(name, default)
        capture = _AUTH_READ.get()
        if capture is not None and name == spec.credential_env and default == "":
            try:
                capture["owner"].note_read(capture, value)
            except Exception:
                capture["owner"].discard()
        return value

    @wraps(resolve)
    def observed_resolve(*args, **kwargs):
        owner, capture = active(), None
        frame = caller = None
        if owner is not None:
            try:
                frame = inspect.currentframe()
                caller = frame.f_back
                config = kwargs.get("config")
                from gateway.config import Platform
                source = owner.scope.live.source
                eligible = (caller.f_code is route.__code__ and caller.f_globals is vars(worker)
                    and caller.f_locals.get("frozen") is config
                    and source.platform is Platform.LOCAL and source.chat_id == owner.scope.session_id
                    and owner.scope.evaluation is not None
                    and type(config) is dict and type(config.get("providers")) is dict
                    and config["providers"].get(spec.hermes_name) == expected_entry
                    and kwargs.get("requested_provider") == spec.hermes_name
                    and kwargs.get("explicit_api_key") in (None, "")
                    and kwargs.get("explicit_base_url") in (None, "", spec.base_url)
                    and kwargs.get("target_model") == spec.served_model)
                capture = owner.begin_resolution(eligible)
            except Exception:
                owner.discard()
            finally:
                del caller, frame
        token = _AUTH_READ.set(capture)
        try:
            result = resolve(*args, **kwargs)
        except BaseException:
            if capture is not None:
                capture["key"] = None
            if owner is not None:
                owner.discard()
            raise
        finally:
            _AUTH_READ.reset(token)
        if capture is not None:
            try:
                owner.finish_resolution(capture, result)
            except Exception:
                owner.discard()
            finally:
                capture["key"] = None
        return result

    @wraps(checkout)
    def observed_checkout(agent, slot_attr, key):
        witness, ticket = dispatch(), None
        if witness is not None and witness.agent is agent:
            try:
                if (slot_attr != lifecycle._OPENAI_SLOT
                        or getattr(getattr(agent, "_create_request_openai_client", None), "__func__", None)
                        is not create_request):
                    witness.discard()
                else:
                    ticket = witness.begin_checkout(key)
            except Exception:
                witness.discard()
        try:
            value = checkout(agent, slot_attr, key)
        except BaseException:
            if witness is not None:
                witness.discard()
            raise
        if witness is not None and witness.agent is agent:
            try:
                witness.checkout(ticket, key, value)
            except Exception:
                witness.discard()
        return value

    @wraps(create)
    def observed_create(agent, client_kwargs, *, reason, shared):
        witness, ticket = (dispatch() if shared is False else None), None
        if witness is not None and witness.agent is agent and shared is False:
            try:
                ticket = witness.begin_create(client_kwargs)
            except Exception:
                witness.discard()
        try:
            value = create(agent, client_kwargs, reason=reason, shared=shared)
        except BaseException:
            if witness is not None and shared is False:
                witness.discard()
            raise
        if witness is not None and witness.agent is agent and shared is False:
            try:
                witness.created(ticket, client_kwargs, value)
            except Exception:
                witness.discard()
        return value

    def commit():
        # Retain any intervening native owner. A failed optional bind stays
        # unavailable and is never retried over another installer's hooks.
        if (binding.transport_installation.credential_installation is not installation
                or custom._resolve_named_custom_runtime is not resolve
                or core._resolve_named_custom_runtime is not resolve
                or secrets._environ_or is not read
                or lifecycle.ClientLifecycleMixin is not klass
                or klass._checkout_request_slot is not checkout
                or klass._create_request_openai_client is not create_request
                or helpers.create_openai_client is not create
                or worker.route_runtime is not route
                or any(getattr(module, "_mmx_credential_observation_bound", False)
                       for module in modules.values())):
            return
        custom._resolve_named_custom_runtime = observed_resolve
        core._resolve_named_custom_runtime = observed_resolve
        secrets._environ_or = observed_read
        klass._checkout_request_slot = observed_checkout
        helpers.create_openai_client = observed_create
        for module in modules.values():
            module._mmx_credential_observation_bound = True

    installation = NativeCredentialObservation(binding, spec=spec, current=current, commit=commit, sdk_class=OpenAI)
    return installation
