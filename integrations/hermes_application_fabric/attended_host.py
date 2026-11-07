"""Turn-scoped composition for an already authenticated attended Hermes host.

The native gateway owns sessions, admissions and execution generations. The
APPLICATION owner owns credentials, eligibility, leases and settlement. This
module retains their existing handles; it does not enroll a service, allocate an
operation, resolve CLI credentials or run a replacement gateway.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from threading import RLock

from .client import ApplicationBinding, NativeCall
from .codec import ID
from .errors import HermesFabricError
from .native import PROVIDER, create_primary_agent, register_middleware

ATTENDED_PROFILE = "attended"


def _identity(value):
    return type(value) is str and ID.fullmatch(value) is not None


class AttendedHost:
    """One native middleware registration owned by the existing host/plugin.

    Create once per native plugin context. The caller activates each admitted
    turn around the gateway's existing executor invocation. ContextVars follow
    the native copied execution context; they are correlation, never authority.
    The separately supplied current-authorization callback is always required.
    """
    def __init__(self, registration_context):
        self._scope = ContextVar("mastermind_hermes_attended_turn", default=None)
        self._retired = False
        self._registration = register_middleware(registration_context, self._resolve)

    def _resolve(self, call):
        turn = self._scope.get()
        if self._retired or type(turn) is not AttendedTurn or turn._host is not self:
            return None
        return turn._resolve(call)

    def admitted_turn(self, *, factory, operation_id, session_id, task_id,
                      requested_model, strict_model, authorized,
                      prior_admission_possible, automatic=False, strict_pool=None,
                      max_output_tokens=4096):
        """All identities/authorization come from the ORIGINAL admitted host.

        A prior/unknown admission is recovered by its owner, not reconstructed
        here. A service name or a native request's metadata cannot grant access.
        """
        if self._retired:
            raise HermesFabricError("hermes_fabric_host_retired")
        return AttendedTurn(self, factory=factory, operation_id=operation_id,
            session_id=session_id, task_id=task_id, requested_model=requested_model,
            strict_model=strict_model, authorized=authorized,
            prior_admission_possible=prior_admission_possible, automatic=automatic,
            strict_pool=strict_pool, max_output_tokens=max_output_tokens)

    @contextmanager
    def activate(self, turn):
        if (self._retired or type(turn) is not AttendedTurn or turn._host is not self
                or turn._closed or self._scope.get() is not None):
            raise HermesFabricError("hermes_fabric_host_scope_invalid")
        token = self._scope.set(turn)
        try:
            yield turn
        finally:
            # Revoke locally before the original close can block. Retain that
            # close result verbatim, including uncertainty; never claim release.
            try:
                turn.close()
            finally:
                self._scope.reset(token)

    def dispose(self):
        """Native plugin unload revokes late results; it is not cancellation."""
        self._retired = True
        self._registration.dispose()


class AttendedTurn:
    """One retained original binding across native agent/facade reconstruction."""
    def __init__(self, host, *, factory, operation_id, session_id, task_id,
                 requested_model, strict_model, authorized,
                 prior_admission_possible, automatic=False, strict_pool=None,
                 max_output_tokens=4096):
        if prior_admission_possible is not False:
            raise HermesFabricError("hermes_fabric_original_recovery_required")
        if (not all(_identity(value) for value in
                    (operation_id, session_id, task_id, requested_model))
                or not callable(authorized)):
            raise HermesFabricError("hermes_fabric_host_identity_invalid")
        if (type(automatic) is not bool
                or strict_model is None and not automatic
                or strict_model is not None and not _identity(strict_model)
                or strict_pool is not None and (not automatic or not _identity(strict_pool))):
            raise HermesFabricError("hermes_fabric_host_selection_invalid")
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 32768:
            raise HermesFabricError("hermes_fabric_output_bound_invalid")
        self._host, self._factory = host, factory
        self.operation_id, self.session_id, self.task_id = operation_id, session_id, task_id
        self.requested_model, self.strict_model = requested_model, strict_model
        # Capture the original host selection once; the existing binding freezes
        # its inspected owner recipe before any credential or admission effect.
        self._routing = (automatic, strict_pool, max_output_tokens)
        self._authorized = authorized
        self._binding = self._failure = self._close_result = None
        self._closed, self._lock = False, RLock()
        self._gateway_context = self._gateway_original = self._gateway_factory = None

    @property
    def refusal(self):
        """Bounded local diagnostic, never a fabricated admission receipt."""
        with self._lock:
            return self._failure

    @property
    def close_result(self):
        return self._close_result

    def _allowed(self, call):
        if (self._closed or self._host._retired or type(call) is not NativeCall
                or call.session_id != self.session_id or call.task_id != self.task_id):
            return False
        try:
            return self._authorized(call) is True
        except Exception:
            return False

    def _resolve(self, call):
        with self._lock:
            if self._failure is not None:
                raise HermesFabricError(self._failure[0], effect_unknown=self._failure[1])
            if not self._allowed(call):
                # Wrong-session traffic cannot consume this turn's factory.
                raise HermesFabricError("hermes_fabric_context_not_authorized")
            if self._binding is None:
                error = None
                try:
                    binding = ApplicationBinding.from_factory(self._factory,
                        profile_id=ATTENDED_PROFILE, operation_id=self.operation_id,
                        session_id=self.session_id, turn_id=call.turn_id,
                        requested_model=self.requested_model, strict_model=self.strict_model,
                        automatic=self._routing[0], strict_pool=self._routing[1],
                        max_output_tokens=self._routing[2],
                        authorized=self._allowed, prior_admission_possible=False)
                    if type(binding) is not ApplicationBinding:
                        raise HermesFabricError("hermes_fabric_application_owner_required",
                                                effect_unknown=True)
                    self._binding = binding
                except HermesFabricError as exc:
                    error = (exc.code, exc.effect_unknown)
                except Exception:
                    error = ("hermes_fabric_binding_failed", True)
                if error is not None:
                    # A later request/facade cannot retry a failed bind. Never
                    # retain an exception carrying owner secrets or raw bodies.
                    self._failure = error
                    raise HermesFabricError(error[0], effect_unknown=error[1])
            self._binding.check(call)
            return self._binding

    def create_agent(self, *, model, **options):
        if (self._host._scope.get() is not self or self._closed
                or self._host._retired or model != self.requested_model
                or options.get("session_id") != self.session_id):
            raise HermesFabricError("hermes_fabric_host_agent_mismatch")
        return create_primary_agent(model=model, **options)

    def create_gateway_agent(self, *, model, **options):
        """The exact native TurnContext.AIAgent construction seam.

        Existing gateway code supplies runtime fields. Accept only the keyless
        Fabric route, remove its empty transport fields, and preserve all native
        conversation/tool/UI options. Never silently clear a configured fallback.
        """
        required = {"provider": PROVIDER, "requested_provider": PROVIDER,
                    "api_mode": "chat_completions"}
        if any(options.get(key) != value for key, value in required.items()):
            raise HermesFabricError("hermes_fabric_gateway_route_mismatch")
        for key in ("api_key", "base_url", "acp_command", "command"):
            if options.get(key) not in (None, ""):
                raise HermesFabricError("hermes_fabric_host_runtime_override")
        for key in ("credential_pool", "fallback_model", "acp_args", "args"):
            if options.get(key) not in (None, {}, []):
                raise HermesFabricError("hermes_fabric_host_runtime_override")
        stripped = set(required) | {"api_key", "base_url", "acp_command", "command",
            "credential_pool", "fallback_model", "acp_args", "args"}
        return self.create_agent(model=model,
            **{key: value for key, value in options.items() if key not in stripped})

    def attach_gateway_context(self, context):
        """Called by the original gateway host BEFORE its turn executor starts.

        The current M2 CLI uses GatewayAgent RPC; changing a CLI-side AIAgent
        alias does not attach this hook. This method neither starts a gateway nor
        changes its route. The enrolled host must supply the Fabric runtime and
        activate this same turn in the executor's copied context.
        """
        from gateway.turn_context import TurnContext
        from run_agent import AIAgent
        if (type(context) is not TurnContext or context.session_id != self.session_id
                or context.AIAgent is not AIAgent or self._gateway_context is not None
                or self._closed or self._host._retired):
            raise HermesFabricError("hermes_fabric_gateway_context_mismatch")
        self._gateway_context, self._gateway_original = context, context.AIAgent
        self._gateway_factory = self.create_gateway_agent
        context.AIAgent = self._gateway_factory

    def close(self):
        """Once-only original close; its receipt is not provider cancellation."""
        with self._lock:
            if self._closed:
                return self._close_result
            self._closed = True
            context = self._gateway_context
            if context is not None and context.AIAgent is self._gateway_factory:
                context.AIAgent = self._gateway_original
            if self._binding is not None:
                self._close_result = self._binding.close()
            return self._close_result
