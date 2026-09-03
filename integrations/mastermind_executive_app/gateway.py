"""integrations.mastermind_executive_app.gateway — composition primitives.

This module wires together, but never reimplements, three already-reviewed
surfaces:

* :mod:`integrations.business_mcp_auth` (A1) — RS256/JWKS bearer
  verification against an immutable :class:`ResourcePolicy`.
* :mod:`integrations.executive_mcp.adapter` (existing five-tool gateway) —
  reused ONLY for the four read tools.  ``submit_ceo_intent`` is never
  dispatched through :class:`ExecutiveMcpGateway` here: that path calls
  ``ceo_intent.submit_intent`` in-process over the general Executive control
  socket, which is exactly what BSC-E1 is forbidden from using or widening.
* the dedicated PR-A/AD-ID1 CeoIngress wire protocol
  (:mod:`control_plane.executive_ceo_ingress`) — this module is a pure
  NETWORK CLIENT of that already-installed socket.  It never imports
  :mod:`control_plane.executive_service` and never opens a
  ``control_plane.executive_runtime.Runtime`` of its own.

Design laws
-----------
* **No in-process mutation authority.**  This module holds no reference to
  ``control_plane.ceo_intent.submit_intent`` and no ``Runtime``.  The ONLY
  way a ``submit_ceo_intent`` call can have any effect is one bounded JSON
  frame sent to the already-installed dedicated CeoIngress AF_UNIX socket.
* **Two policies, not one.**  The A1 resource-policy contract enforces an
  EXACT match between a token's granted scopes and
  ``ResourcePolicy.required_scopes`` (see
  ``integrations/business_mcp_auth/claims.py:_scope_claim``) — never a
  subset check.  A single caller may therefore need TWO tokens (or one
  two-scope token checked against the wider policy): a
  ``mastermind.executive.read``-only token authenticates against
  :attr:`AppPolicies.read`, and a token carrying BOTH
  ``mastermind.executive.read`` and ``mastermind.executive.intent.submit``
  authenticates against :attr:`AppPolicies.submit`.
* **Fresh grounding, no cache.**  :func:`observe_trusted_grounding` re-reads
  both repository HEAD SHAs on every call; nothing here caches a SHA across
  requests.
* **A frame is sent at most once per call.**  :class:`CeoIngressClient` never
  retries internally.  Retrying belongs to a *new*, separately-confirmed
  caller action, never to library code hiding an ambiguous outcome.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from control_plane import ceo_boot_packet
from control_plane import executive_ceo_ingress as ceo_ingress
from integrations.business_mcp_auth.contracts import (
    AuthError,
    ResourcePolicy,
    VerifiedPrincipal,
    load_resource_policy,
)
from integrations.business_mcp_auth.jwks import BoundedJwksCache, HttpxJwksFetcher
from integrations.business_mcp_auth.jwt_verifier import JwksKeySource, JwtAuthenticator
from integrations.executive_mcp.adapter import ExecutiveMcpGateway, GatewayConfig
from integrations.executive_mcp.schemas import MODIFYING_TOOL, tool_names

__all__ = [
    "APP_POLICY_ENVELOPE_SCHEMA",
    "READ_SCOPE",
    "SUBMIT_SCOPE",
    "READ_TOOL_NAMES",
    "AppPolicies",
    "CeoIngressClient",
    "CeoIngressResponse",
    "GroundingUnavailable",
    "load_app_policies",
    "make_jwt_authenticators",
    "observe_trusted_grounding",
    "read_only_gateway_config",
]


#: The two closed scope strings BSC-E1 checks.  Never a caller-suppliable
#: value: both are literals, and every policy that admits either is loaded
#: from an operator-controlled file, never a request field.
READ_SCOPE = "mastermind.executive.read"
SUBMIT_SCOPE = "mastermind.executive.intent.submit"

#: The four read tools this app ever forwards to :class:`ExecutiveMcpGateway`.
#: ``submit_ceo_intent`` (:data:`MODIFYING_TOOL`) is deliberately excluded —
#: it never reaches ``ExecutiveMcpGateway.call`` from this app.
READ_TOOL_NAMES: tuple[str, ...] = tuple(
    name for name in tool_names() if name != MODIFYING_TOOL
)

#: This app's own example-config envelope schema (config/business_mcp/
#: executive_policy.example.json).  Distinct from, and never confused with,
#: ``integrations.business_mcp_auth.contracts.AUTH_POLICY_SCHEMA`` — that is
#: the schema of each of the two ResourcePolicy OBJECTS nested inside this
#: envelope, unchanged and re-validated through the real parser.
APP_POLICY_ENVELOPE_SCHEMA = "mastermind.executive_app_policy_example.v1"


@dataclasses.dataclass(frozen=True)
class AppPolicies:
    """The two immutable resource policies this app authenticates against."""

    read: ResourcePolicy
    submit: ResourcePolicy

    def __post_init__(self) -> None:
        if tuple(self.read.required_scopes) != (READ_SCOPE,):
            raise ValueError(
                f"read policy must require exactly ({READ_SCOPE!r},)"
            )
        expected_submit = tuple(sorted((READ_SCOPE, SUBMIT_SCOPE)))
        if tuple(self.submit.required_scopes) != expected_submit:
            raise ValueError(
                f"submit policy must require exactly {expected_submit!r}"
            )


def load_app_policies(payload: Mapping[str, Any]) -> AppPolicies:
    """Validate one already-parsed policy-envelope object and return both.

    ``payload`` must contain exactly ``read`` and ``submit`` (this envelope's
    own two keys; the informational ``schema``/``note`` keys are ignored, not
    round-tripped, and never gate anything).  Each of the two nested objects
    is round-tripped through the one real
    :func:`integrations.business_mcp_auth.contracts.load_resource_policy`
    parser — this module holds no independent copy of ResourcePolicy field
    validation.
    """

    if not isinstance(payload, Mapping):
        raise ValueError("policy envelope must be a JSON object")
    missing = {"read", "submit"} - set(payload)
    if missing:
        raise ValueError(f"policy envelope is missing key(s): {sorted(missing)}")
    read_policy = load_resource_policy(payload["read"])
    submit_policy = load_resource_policy(payload["submit"])
    return AppPolicies(read=read_policy, submit=submit_policy)


def load_app_policies_from_file(path: "Path | str") -> AppPolicies:
    """Read+parse one policy-envelope JSON file from disk."""

    raw = Path(path).read_text(encoding="utf-8")
    return load_app_policies(json.loads(raw))


def _default_jwks_cache(policy: ResourcePolicy) -> JwksKeySource:
    import time as _time

    return BoundedJwksCache(
        policy=policy, fetcher=HttpxJwksFetcher(policy=policy), monotonic=_time.monotonic
    )


def make_jwt_authenticators(
    policies: AppPolicies, *, jwks_cache: JwksKeySource | None = None
) -> tuple[JwtAuthenticator, JwtAuthenticator]:
    """Build the (read, submit) :class:`JwtAuthenticator` pair.

    ``integrations.business_mcp_auth.jwks.BoundedJwksCache``/``HttpxJwksFetcher``
    are each bound to exactly ONE :class:`ResourcePolicy` (its own
    ``jwks_uri``/cache TTL), so the default production wiring builds one
    independent cache PER policy even though both name the same authorization
    server in every legal deployment.  A caller-supplied ``jwks_cache`` is a
    single stateless object (e.g. a test fake) reused for BOTH authenticators
    instead — the :class:`JwksKeySource` protocol has no policy-affinity
    requirement, only ``.key_for(kid)``.
    """

    if jwks_cache is None:
        read_cache: JwksKeySource = _default_jwks_cache(policies.read)
        submit_cache: JwksKeySource = _default_jwks_cache(policies.submit)
    else:
        read_cache = submit_cache = jwks_cache
    read_authenticator = JwtAuthenticator(policy=policies.read, jwks_cache=read_cache)
    submit_authenticator = JwtAuthenticator(
        policy=policies.submit, jwks_cache=submit_cache
    )
    return read_authenticator, submit_authenticator


def read_only_gateway_config(repo_root: "Path | str") -> GatewayConfig:
    """The one legal :class:`GatewayConfig` this app ever builds.

    Always ``ServerMode.READONLY`` — there is no fixture/write mode here.
    ``submit_ceo_intent`` is never called through the resulting gateway (see
    module docstring); only the four names in :data:`READ_TOOL_NAMES` are.
    """

    from integrations.executive_mcp.schemas import ServerMode

    return GatewayConfig(mode=ServerMode.READONLY, repo_root=Path(repo_root))


def build_read_gateway(repo_root: "Path | str") -> ExecutiveMcpGateway:
    return ExecutiveMcpGateway(read_only_gateway_config(repo_root))


# ---------------------------------------------------------------------------
# grounding
# ---------------------------------------------------------------------------


class GroundingUnavailable(RuntimeError):
    """Raised when the app cannot form a bounded, well-shaped grounding claim.

    Never raised with the underlying git/filesystem exception attached to
    its message — callers convert this into the same fixed, opaque wire text
    CeoIngress itself uses for ``grounding_unavailable`` (R1 §3.2 parity);
    the ``__cause__`` chain (never logged to a client) is preserved for
    operator diagnosis only.
    """


def observe_trusted_grounding(
    *, mastermind_root: "Path | str", macro_root_flag: str | None, environ: Mapping[str, str]
) -> dict[str, str]:
    """Fresh-read both repository HEAD SHAs, immediately, no cache.

    Reuses the exact primitives ``control_plane.ceo_boot_packet`` already
    uses for the SAME shape of grounding: :func:`ceo_boot_packet.git_sha` for
    both repositories and :func:`ceo_boot_packet.resolve_macro_root` for
    locating the Macro checkout. Never calls
    :func:`ceo_boot_packet.build_packet` (that pulls the Agent OS
    brief/handoffs/strategic-state text this app has no reason to read).
    Returns the exact three-key shape
    ``control_plane.executive_ceo_ingress._coerce_grounding_shape`` accepts;
    the CeoIngress side always re-observes and compares independently, so
    this claim's role is only to be an honest, freshly observed one.
    """

    root = Path(mastermind_root)
    mastermind_sha = ceo_boot_packet.git_sha(root)
    if mastermind_sha is None:
        raise GroundingUnavailable("mastermind checkout HEAD sha unavailable")

    macro_root, _via, _candidates = ceo_boot_packet.resolve_macro_root(
        macro_root_flag, environ, root
    )
    macro_sha = ceo_boot_packet.git_sha(macro_root) if macro_root is not None else None
    if macro_sha is None:
        raise GroundingUnavailable("macro checkout HEAD sha unavailable")

    return {
        "mastermind_sha": mastermind_sha,
        "macro_sha": macro_sha,
        "boot_packet_schema": ceo_ingress.BOOT_PACKET_SCHEMA,
    }


# ---------------------------------------------------------------------------
# dedicated CeoIngress client (network only; no in-process authority)
# ---------------------------------------------------------------------------

#: Mirrors ``control_plane.executive_ceo_ingress.MAX_REQUEST_BYTES`` — checked
#: locally BEFORE opening a connection so an oversized frame never reaches the
#: wire at all (the server would refuse it anyway; refusing first here means
#: zero ambiguity about whether bytes were sent).
MAX_REQUEST_BYTES = ceo_ingress.MAX_REQUEST_BYTES
#: Mirrors ``control_plane.executive_ceo_ingress.MAX_RESPONSE_BYTES``.
MAX_RESPONSE_BYTES = ceo_ingress.MAX_RESPONSE_BYTES
#: StreamReader buffer ceiling — comfortably above MAX_RESPONSE_BYTES so a
#: legal maximum-size response is never itself the cause of a
#: ``LimitOverrunError``.
_STREAM_LIMIT = MAX_RESPONSE_BYTES + 4096

DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
DEFAULT_READ_TIMEOUT_SECONDS = 10.0

#: Closed transport-outcome vocabulary.  ``sent`` is the load-bearing branch:
#: every status at or after it means the frame may have reached the backend
#: and a caller must reconcile, never blindly resend.
TRANSPORT_NOT_SENT = "not_sent"
TRANSPORT_SENT_OK = "sent_ok"
TRANSPORT_SENT_UNKNOWN = "sent_effect_unknown"


@dataclasses.dataclass(frozen=True)
class CeoIngressResponse:
    """One classified outcome of one attempted send to the dedicated ingress.

    ``transport`` is one of :data:`TRANSPORT_NOT_SENT` (the frame is
    provably never reached the backend — safe to treat as zero effect),
    :data:`TRANSPORT_SENT_OK` (a well-formed ``{"ok": ...}`` envelope came
    back), or :data:`TRANSPORT_SENT_UNKNOWN` (the frame was fully written and
    drained, but no trustworthy response followed — EFFECT_UNKNOWN; the
    caller must reconcile via a v2 status frame on the SAME ``request_ref``,
    never resubmit).
    """

    transport: str
    ok: bool | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    detail: str = ""


class CeoIngressClient:
    """A pure network client of the already-installed dedicated CeoIngress
    socket.  Holds no Runtime, no in-process sink, and no retry loop."""

    def __init__(
        self,
        *,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        read_timeout: float = DEFAULT_READ_TIMEOUT_SECONDS,
    ) -> None:
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout

    async def send_frame(
        self, socket_path: "Path | str", frame: Mapping[str, Any]
    ) -> CeoIngressResponse:
        """Send exactly one JSON frame; never retries internally."""

        try:
            encoded = json.dumps(frame, ensure_ascii=False, sort_keys=True).encode(
                "utf-8"
            )
        except (TypeError, ValueError) as exc:
            return CeoIngressResponse(
                transport=TRANSPORT_NOT_SENT, detail=f"frame is not JSON-serializable: {exc}"
            )
        line = encoded + b"\n"
        if len(line) > MAX_REQUEST_BYTES:
            # Refuse locally; never put an oversized frame on the wire.
            return CeoIngressResponse(
                transport=TRANSPORT_NOT_SENT,
                detail=f"frame is {len(line)} bytes, over the {MAX_REQUEST_BYTES}-byte ceiling",
            )

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(socket_path), limit=_STREAM_LIMIT),
                timeout=self._connect_timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            # Never connected: provably zero effect.
            return CeoIngressResponse(
                transport=TRANSPORT_NOT_SENT, detail=f"connect failed: {type(exc).__name__}"
            )

        try:
            try:
                writer.write(line)
                await asyncio.wait_for(writer.drain(), timeout=self._connect_timeout)
            except (OSError, asyncio.TimeoutError) as exc:
                # The write/drain itself failed. A local AF_UNIX write this
                # small either lands in full or the connection never
                # accepted it; treated conservatively as NOT sent only when
                # drain never started, but since we cannot prove that here,
                # ambiguity favors the safer (never-retry) classification.
                return CeoIngressResponse(
                    transport=TRANSPORT_SENT_UNKNOWN,
                    detail=f"send failed after connect: {type(exc).__name__}",
                )
            try:
                writer.write_eof()
            except (OSError, NotImplementedError):
                pass

            try:
                raw = await asyncio.wait_for(
                    reader.readline(), timeout=self._read_timeout
                )
            except asyncio.TimeoutError:
                return CeoIngressResponse(
                    transport=TRANSPORT_SENT_UNKNOWN, detail="read timed out after send"
                )
            except asyncio.LimitOverrunError:
                return CeoIngressResponse(
                    transport=TRANSPORT_SENT_UNKNOWN, detail="response exceeded byte ceiling"
                )
            except OSError as exc:
                return CeoIngressResponse(
                    transport=TRANSPORT_SENT_UNKNOWN,
                    detail=f"connection error while reading: {type(exc).__name__}",
                )

            if not raw:
                return CeoIngressResponse(
                    transport=TRANSPORT_SENT_UNKNOWN, detail="connection closed with no response"
                )
            if len(raw) > MAX_RESPONSE_BYTES:
                return CeoIngressResponse(
                    transport=TRANSPORT_SENT_UNKNOWN, detail="response exceeded byte ceiling"
                )
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return CeoIngressResponse(
                    transport=TRANSPORT_SENT_UNKNOWN, detail="response was not valid JSON"
                )
            if not isinstance(parsed, dict) or "ok" not in parsed or not isinstance(
                parsed.get("ok"), bool
            ):
                return CeoIngressResponse(
                    transport=TRANSPORT_SENT_UNKNOWN,
                    detail="response envelope shape was not the canonical {ok, ...} form",
                )
            if parsed["ok"]:
                result = parsed.get("result")
                if not isinstance(result, dict):
                    return CeoIngressResponse(
                        transport=TRANSPORT_SENT_UNKNOWN,
                        detail="ok response carried no result object",
                    )
                return CeoIngressResponse(
                    transport=TRANSPORT_SENT_OK, ok=True, result=result
                )
            error = parsed.get("error")
            if not isinstance(error, dict) or not isinstance(error.get("code"), str):
                return CeoIngressResponse(
                    transport=TRANSPORT_SENT_UNKNOWN,
                    detail="refusal response carried no well-formed error object",
                )
            # A clean, well-formed refusal: the backend told us, in its own
            # closed vocabulary, that no Job was created. Zero effect, safe.
            return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=False, error=error)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, asyncio.TimeoutError):
                pass
