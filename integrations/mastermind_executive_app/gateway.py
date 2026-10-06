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
from typing import Any, TYPE_CHECKING

from control_plane import ceo_boot_packet
from control_plane import executive_ceo_ingress as ceo_ingress
from integrations.business_mcp_auth.contracts import (
    AuthError,
    ResourcePolicy,
    VerifiedPrincipal,
    load_resource_policy,
)
if TYPE_CHECKING:
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
    "make_shared_jwks_cache",
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
    from integrations.business_mcp_auth.jwks import BoundedJwksCache, HttpxJwksFetcher
    import time as _time

    return BoundedJwksCache(
        policy=policy, fetcher=HttpxJwksFetcher(policy=policy), monotonic=_time.monotonic
    )


def _jwks_cache_contract(policy: ResourcePolicy) -> tuple[object, ...]:
    """Return the authority and refresh controls that make a JWKS cache shareable."""

    return (
        policy.resource,
        policy.issuer,
        policy.authorization_servers,
        policy.jwks_uri,
        policy.allowed_algorithms,
        policy.jwks_cache_ttl_seconds,
        policy.unknown_kid_refresh_cooldown_seconds,
        policy.fetch_failure_backoff_seconds,
    )


def make_shared_jwks_cache(policies: AppPolicies) -> JwksKeySource | None:
    """Build one cache only when both policies have the same JWKS contract.

    The cache contains public signing keys and bounded refresh state only; it
    carries no authorization decision.  Scope, subject, audience, lifetime, and
    tool authority stay inside the separate JwtAuthenticator instances.
    """

    if _jwks_cache_contract(policies.read) != _jwks_cache_contract(policies.submit):
        return None
    return _default_jwks_cache(policies.read)


def make_jwt_authenticators(
    policies: AppPolicies, *, jwks_cache: JwksKeySource | None = None
) -> tuple[JwtAuthenticator, JwtAuthenticator]:
    """Build the (read, submit) :class:`JwtAuthenticator` pair.

    Read and submit remain separate authorization policies.  When they bind
    the same OAuth resource/JWKS authority and the same cache safety controls,
    they share one process-memory JWKS cache.  This prevents a wider-scope
    token from performing two independent JWKS refreshes while preserving
    separate scope, subject, audience, lifetime, and tool-authority checks.
    Policies with different JWKS authority or refresh controls keep independent
    caches.  A caller-supplied ``jwks_cache`` is reused for both as before.
    """

    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    if jwks_cache is None:
        shared_cache = make_shared_jwks_cache(policies)
        if shared_cache is None:
            read_cache: JwksKeySource = _default_jwks_cache(policies.read)
            submit_cache: JwksKeySource = _default_jwks_cache(policies.submit)
        else:
            read_cache = submit_cache = shared_cache
    else:
        read_cache = submit_cache = jwks_cache
    read_authenticator = JwtAuthenticator(policy=policies.read, jwks_cache=read_cache)
    submit_authenticator = JwtAuthenticator(
        policy=policies.submit, jwks_cache=submit_cache
    )
    return read_authenticator, submit_authenticator


def read_only_gateway_config(
    repo_root: "Path | str",
    *,
    macro_root_flag: str | None = None,
    runtime_root: "Path | str | None" = None,
) -> GatewayConfig:
    """The one legal :class:`GatewayConfig` this app ever builds.

    Always ``ServerMode.READONLY`` — there is no fixture/write mode here.
    ``submit_ceo_intent`` is never called through the resulting gateway (see
    module docstring); only the four names in :data:`READ_TOOL_NAMES` are.
    """

    from integrations.executive_mcp.schemas import ServerMode

    return GatewayConfig(
        mode=ServerMode.READONLY,
        repo_root=Path(repo_root),
        macro_root_flag=macro_root_flag,
        read_runtime_root=runtime_root,
    )


def build_read_gateway(
    repo_root: "Path | str",
    *,
    macro_root_flag: str | None = None,
    runtime_root: "Path | str | None" = None,
) -> ExecutiveMcpGateway:
    return ExecutiveMcpGateway(
        read_only_gateway_config(
            repo_root,
            macro_root_flag=macro_root_flag,
            runtime_root=runtime_root,
        )
    )


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

        request_ceiling = MAX_REQUEST_BYTES
        response_ceiling = MAX_RESPONSE_BYTES
        stream_limit = _STREAM_LIMIT
        # Only the separately versioned, closed release frame can use the
        # larger token envelope; every historical schema retains its limits.
        from control_plane import executive_release_ingress as release_ingress
        if isinstance(frame, Mapping) and frame.get("schema") == release_ingress.FRAME_SCHEMA:
            try:
                release_ingress.validate_frame(frame)
            except release_ingress.ReleaseIngressError:
                return CeoIngressResponse(
                    transport=TRANSPORT_NOT_SENT, detail="release frame is invalid"
                )
            request_ceiling = release_ingress.MAX_FRAME_BYTES
            response_ceiling = release_ingress.MAX_RESPONSE_BYTES
            stream_limit = response_ceiling + 4096
        try:
            encoded = json.dumps(frame, ensure_ascii=False, sort_keys=True).encode(
                "utf-8"
            )
        except (TypeError, ValueError) as exc:
            return CeoIngressResponse(
                transport=TRANSPORT_NOT_SENT, detail=f"frame is not JSON-serializable: {exc}"
            )
        line = encoded + b"\n"
        if len(line) > request_ceiling:
            # Refuse locally; never put an oversized frame on the wire.
            return CeoIngressResponse(
                transport=TRANSPORT_NOT_SENT,
                detail=f"frame is {len(line)} bytes, over the {request_ceiling}-byte ceiling",
            )

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(socket_path), limit=stream_limit),
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
            except (asyncio.LimitOverrunError, ValueError):
                # StreamReader.readline converts an over-limit readuntil
                # failure to ValueError. Bytes were sent: never report absence.
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
            if len(raw) > response_ceiling:
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
            try:
                writer.close()
                # A reply/read timeout must not acquire an unbounded teardown
                # wait. Reuse this connection's existing transport budget.
                await asyncio.wait_for(
                    writer.wait_closed(), timeout=self._connect_timeout
                )
            except asyncio.CancelledError:
                self._abort_transport(writer)
                raise
            except Exception:
                # Teardown cannot erase an already classified backend receipt
                # or mask the original error. Never reconnect or resend here.
                self._abort_transport(writer)

    @staticmethod
    def _abort_transport(writer: asyncio.StreamWriter) -> None:
        try:
            writer.transport.abort()
        except Exception:
            # Preserve the original result/cancellation even if local abort
            # fails. This is a close attempt, not proof of backend nonexecution.
            pass


class CeoIngressReadGateway:
    """Network-only access to one statically admitted installed read profile."""

    _READ_TOOL_NAMES = READ_TOOL_NAMES
    _READ_SCHEMA = ceo_ingress.APP_READ_SCHEMA
    _RESULT_FIELDS = frozenset(
        {
            "schema",
            "tool",
            "ok",
            "server_version",
            "mode",
            "generated_at",
            "grounding",
            "data",
            "degraded",
            "bounded",
            "error",
        }
    )
    _UNAVAILABLE_UPSTREAM_CODES = frozenset(
        {
            "peer_credentials_unavailable",
            "peer_denied",
            "ingress_unavailable",
            "unsupported_ingress_schema",
            "backend_unavailable",
            "grounding_unavailable",
            "internal_error",
            "timeout",
        }
    )

    def __init__(self, socket_path: Path | str, client: CeoIngressClient) -> None:
        self._socket_path = socket_path
        self._client = client

    def _validate_arguments(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        from integrations.executive_mcp.schemas import validate_tool_arguments

        return validate_tool_arguments(name, arguments)

    async def aclose(self) -> None:
        # Each request owns and closes its socket. No local state to drain.
        return None

    def _result_server_version(self) -> str:
        from integrations.executive_mcp.schemas import SERVER_VERSION

        return SERVER_VERSION

    @staticmethod
    def _valid_generated_at(value: object) -> bool:
        from datetime import datetime, timezone

        if type(value) is not str or not value or len(value) > 64:
            return False
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        except ValueError:
            return False
        return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)

    @staticmethod
    def _valid_bounding_receipts(value: object) -> bool:
        if not isinstance(value, list):
            return False
        fields: set[str] = set()
        for receipt in value:
            if (
                type(receipt) is not dict
                or set(receipt) != {"bounded", "original_bytes", "returned_bytes", "field"}
                or receipt["bounded"] is not True
                or type(receipt["original_bytes"]) is not int
                or type(receipt["returned_bytes"]) is not int
                or receipt["original_bytes"] <= 0
                or receipt["returned_bytes"] < 0
                or receipt["returned_bytes"] > receipt["original_bytes"]
                or type(receipt["field"]) is not str
                or not receipt["field"]
                or len(receipt["field"]) > 512
                or receipt["field"] in fields
            ):
                return False
            fields.add(receipt["field"])
        return True

    @staticmethod
    def _valid_bounded_text(
        value: object,
        *,
        field: str,
        receipts: Mapping[str, Mapping[str, Any]],
        consumed: set[str],
        allow_empty: bool = True,
    ) -> bool:
        from integrations.executive_mcp.schemas import BOUND_PREVIEW_CHARS

        if type(value) is str:
            return allow_empty or bool(value)
        if (
            type(value) is not dict
            or set(value) != {
                "bounded", "original_bytes", "returned_bytes", "field", "preview"
            }
            or value.get("bounded") is not True
            or value.get("field") != field
            or type(value.get("original_bytes")) is not int
            or type(value.get("returned_bytes")) is not int
            or value["original_bytes"] <= 0
            or value["returned_bytes"] < 0
            or value["returned_bytes"] > value["original_bytes"]
            or type(value.get("preview")) is not str
            or len(value["preview"]) > BOUND_PREVIEW_CHARS
            or (not allow_empty and not value["preview"])
            or len(value["preview"].encode("utf-8")) != value["returned_bytes"]
        ):
            return False
        receipt = receipts.get(field)
        if (
            type(receipt) is not dict
            or receipt != {
                "bounded": True,
                "original_bytes": value["original_bytes"],
                "returned_bytes": value["returned_bytes"],
                "field": field,
            }
        ):
            return False
        consumed.add(field)
        return True

    @staticmethod
    def _valid_grounding(value: object, *, tool: str) -> bool:
        if type(value) is not dict:
            return False
        if tool in {"executive_state", "executive_inbox"}:
            if set(value) != {
                "boot_packet_schema", "macro", "mastermind", "runtime", "runtime_db"
            }:
                return False
            mastermind = value["mastermind"]
            macro = value["macro"]
            runtime_db = value["runtime_db"]
            return (
                type(mastermind) is dict
                and set(mastermind) == {"branch", "root", "sha"}
                and type(mastermind["branch"]) is str
                and type(mastermind["root"]) is str
                and type(mastermind["sha"]) is str
                and len(mastermind["sha"]) == 40
                and type(macro) is dict
                and set(macro) == {"root", "sha"}
                and (macro["root"] is None or type(macro["root"]) is str)
                and (macro["sha"] is None or (type(macro["sha"]) is str and len(macro["sha"]) == 40))
                and (value["boot_packet_schema"] is None or type(value["boot_packet_schema"]) is str)
                and value["runtime"] == "readonly:installed-executive-runtime"
                and type(runtime_db) is dict
                and set(runtime_db) == {"path", "present"}
                and type(runtime_db["path"]) is str
                and type(runtime_db["present"]) is bool
            )
        return (
            set(value) == {"runtime", "source"}
            and value["runtime"] == "readonly:installed-executive-runtime"
            and type(value["source"]) is str
            and bool(value["source"])
            and len(value["source"]) <= 256
        )

    @staticmethod
    def _valid_strategic_summary(value: object) -> bool:
        import re
        from control_plane import strategic_state

        if value is None:
            return True
        if type(value) is not dict or set(value) != {
            "schema", "company_phase", "north_star", "p0", "constraints"
        }:
            return False
        if (
            value["schema"] != strategic_state.SCHEMA
            or type(value["company_phase"]) is not str
            or not value["company_phase"].strip()
            or type(value["north_star"]) is not list
            or not value["north_star"]
            or not all(type(item) is str and item.strip() for item in value["north_star"])
            or type(value["p0"]) is not list
            or not value["p0"]
            or type(value["constraints"]) is not dict
        ):
            return False
        seen: set[str] = set()
        for row in value["p0"]:
            if type(row) is not dict or set(row) != {
                "id", "department", "objective", "status"
            }:
                return False
            if not all(type(row[key]) is str and row[key].strip() for key in row):
                return False
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", row["id"]) is None or row["id"] in seen:
                return False
            seen.add(row["id"])
        current_constraint_keys = set(strategic_state.REQUIRED_CONSTRAINTS) | {
            "unbounded_autonomous_strategic_modification"
        }
        return (
            set(value["constraints"]) == current_constraint_keys
            and all(
                type(name) is str
                and name
                and type(level) is str
                and level
                for name, level in value["constraints"].items()
            )
        )

    @staticmethod
    def _valid_runtime_counts(value: object) -> bool:
        from control_plane.executive_runtime import (
            AttemptStatus, JobStatus, WorkerStatus,
        )

        if value is None:
            return True
        if type(value) is not dict or set(value) != {"jobs", "attempts", "workers"}:
            return False
        for name, enum_type in (
            ("jobs", JobStatus),
            ("attempts", AttemptStatus),
            ("workers", WorkerStatus),
        ):
            section = value[name]
            if section is None:
                continue
            if type(section) is not dict or set(section) != {"total", "by_status"}:
                return False
            by_status = section["by_status"]
            expected = {member.value for member in enum_type}
            if (
                type(section["total"]) is not int
                or section["total"] < 0
                or type(by_status) is not dict
                or set(by_status) != expected
                or any(type(count) is not int or count < 0 for count in by_status.values())
                or section["total"] != sum(by_status.values())
            ):
                return False
        return True

    @staticmethod
    def _valid_attention_counts(value: object) -> bool:
        from control_plane import executive_inbox

        expected = set(executive_inbox.TARGETS) | {"total"}
        return (
            type(value) is dict
            and set(value) == expected
            and all(type(count) is int and count >= 0 for count in value.values())
            and value["total"] == sum(
                value[target] for target in executive_inbox.TARGETS
            )
        )

    @staticmethod
    def _valid_handoffs(value: object) -> bool:
        from control_plane import ceo_boot_packet

        if type(value) is not list or len(value) > ceo_boot_packet.HANDOFF_LIMIT:
            return False
        for row in value:
            if (
                type(row) is not dict
                or set(row) != {"name", "path"}
                or type(row["name"]) is not str
                or not row["name"]
                or len(row["name"]) > 255
                or type(row["path"]) is not str
                or not row["path"].startswith("agentos/handoffs/")
                or not row["path"].endswith(".md")
                or row["path"].startswith("/")
                or ".." in Path(row["path"]).parts
            ):
                return False
        return True

    @staticmethod
    def _valid_state_data(value: object) -> bool:
        import re
        from control_plane import ceo_boot_packet, executive_inbox

        keys = {
            "mastermind", "macro", "boot_packet_schema", "inbox_schema",
            "strategic_state", "next_recommended_act", "runtime_db",
            "runtime_counts", "attention_counts", "handoffs",
        }
        if type(value) is not dict or set(value) != keys:
            return False
        mastermind = value["mastermind"]
        macro = value["macro"]
        runtime_db = value["runtime_db"]
        return (
            type(mastermind) is dict
            and set(mastermind) == {"branch", "root", "sha"}
            and type(mastermind["branch"]) is str
            and type(mastermind["root"]) is str
            and type(mastermind["sha"]) is str
            and re.fullmatch(r"[0-9a-f]{40}", mastermind["sha"]) is not None
            and type(macro) is dict
            and set(macro) == {"root", "sha", "resolved_via"}
            and (macro["root"] is None or type(macro["root"]) is str)
            and (
                macro["sha"] is None
                or (
                    type(macro["sha"]) is str
                    and re.fullmatch(r"[0-9a-f]{40}", macro["sha"]) is not None
                )
            )
            and (macro["resolved_via"] is None or type(macro["resolved_via"]) is str)
            and value["boot_packet_schema"] == ceo_boot_packet.SCHEMA
            and value["inbox_schema"] == executive_inbox.SCHEMA
            and CeoIngressReadGateway._valid_strategic_summary(value["strategic_state"])
            and (
                value["next_recommended_act"] is None
                or (
                    type(value["next_recommended_act"]) is str
                    and bool(value["next_recommended_act"].strip())
                )
            )
            and type(runtime_db) is dict
            and set(runtime_db) == {"path", "present"}
            and type(runtime_db["path"]) is str
            and type(runtime_db["present"]) is bool
            and CeoIngressReadGateway._valid_runtime_counts(value["runtime_counts"])
            and CeoIngressReadGateway._valid_attention_counts(value["attention_counts"])
            and CeoIngressReadGateway._valid_handoffs(value["handoffs"])
        )

    @staticmethod
    def _valid_inbox_grounding(
        value: object,
        *,
        receipts: Mapping[str, Mapping[str, Any]],
        consumed: set[str],
    ) -> bool:
        import re
        from control_plane import ceo_boot_packet

        if type(value) is not dict or set(value) != {
            "mastermind", "macro", "boot_packet_schema", "runtime_db"
        }:
            return False
        mastermind = value["mastermind"]
        macro = value["macro"]
        runtime_db = value["runtime_db"]
        return (
            type(mastermind) is dict
            and set(mastermind) == {"branch", "root", "sha"}
            and type(mastermind["branch"]) is str
            and type(mastermind["root"]) is str
            and type(mastermind["sha"]) is str
            and re.fullmatch(r"[0-9a-f]{40}", mastermind["sha"]) is not None
            and type(macro) is dict
            and set(macro) == {"root", "sha"}
            and (macro["root"] is None or type(macro["root"]) is str)
            and (
                macro["sha"] is None
                or (
                    type(macro["sha"]) is str
                    and re.fullmatch(r"[0-9a-f]{40}", macro["sha"]) is not None
                )
            )
            and (
                value["boot_packet_schema"] is None
                or value["boot_packet_schema"] == ceo_boot_packet.SCHEMA
            )
            and type(runtime_db) is dict
            and set(runtime_db) == {"path", "present"}
            and type(runtime_db["path"]) is str
            and type(runtime_db["present"]) is bool
        )

    @staticmethod
    def _valid_inbox_attention_item(
        value: object,
        *,
        index: int,
        receipts: Mapping[str, Mapping[str, Any]],
        consumed: set[str],
    ) -> bool:
        import re
        from control_plane import executive_inbox
        from control_plane.executive_runtime import JobStatus

        base_keys = {
            "attention_id", "target", "kind", "source", "job_id", "workstream",
            "status", "reason", "evidence", "existing_next_actions",
        }
        runtime_keys = {
            "parent_job_id", "root_job_id", "depth", "owner_seat",
            "escalation_target", "business_impact", "review_required",
            "reviews_job_id",
        }
        if type(value) is not dict:
            return False
        source = value.get("source")
        expected_keys = (
            base_keys | runtime_keys if source == "runtime"
            else base_keys if source == "agent_os"
            else None
        )
        if expected_keys is None or set(value) != expected_keys:
            return False
        evidence = value["evidence"]
        next_actions = value["existing_next_actions"]
        if not (
            type(value["attention_id"]) is str
            and re.fullmatch(r"eia-[0-9a-f]{12}", value["attention_id"]) is not None
            and value["target"] in executive_inbox.TARGETS
            and type(value["kind"]) is str
            and bool(value["kind"])
            and (value["job_id"] is None or type(value["job_id"]) is str)
            and (value["workstream"] is None or type(value["workstream"]) is str)
            and (value["status"] is None or type(value["status"]) is str)
            and CeoIngressReadGateway._valid_bounded_text(
                value["reason"],
                field=f"attention[{index}].reason",
                receipts=receipts,
                consumed=consumed,
                allow_empty=False,
            )
            and type(evidence) is list
            and all(
                type(item) is dict
                and set(item) == {"ref", "field", "value"}
                and type(item["ref"]) is str
                and type(item["field"]) is str
                and CeoIngressReadGateway._valid_bounded_text(
                    item["value"],
                    field=f"attention[{index}].evidence[{evidence_index}].value",
                    receipts=receipts,
                    consumed=consumed,
                )
                for evidence_index, item in enumerate(evidence)
            )
            and type(next_actions) is list
            and all(
                CeoIngressReadGateway._valid_bounded_text(
                    item,
                    field=f"attention[{index}].existing_next_actions[{action_index}]",
                    receipts=receipts,
                    consumed=consumed,
                )
                for action_index, item in enumerate(next_actions)
            )
        ):
            return False
        if source == "agent_os":
            return (
                value["target"] == "ceo"
                and value["kind"] == "ceo_decision_pending"
                and value["job_id"] is None
                and value["status"] is None
                and value["existing_next_actions"] == []
            )
        statuses = {member.value for member in JobStatus}
        return (
            type(value["job_id"]) is str
            and bool(value["job_id"])
            and value["status"] in statuses
            and (value["parent_job_id"] is None or type(value["parent_job_id"]) is str)
            and type(value["root_job_id"]) is str
            and bool(value["root_job_id"])
            and type(value["depth"]) is int
            and value["depth"] >= 0
            and type(value["owner_seat"]) is str
            and bool(value["owner_seat"])
            and type(value["escalation_target"]) is str
            and bool(value["escalation_target"])
            and type(value["business_impact"]) is str
            and bool(value["business_impact"])
            and type(value["review_required"]) is bool
            and (value["reviews_job_id"] is None or type(value["reviews_job_id"]) is str)
        )

    @staticmethod
    def _valid_inbox_suppressed(value: object) -> bool:
        from control_plane import executive_inbox

        if value is None:
            return True
        expected = set(executive_inbox._SUPPRESSION_KEYS)
        return (
            type(value) is dict
            and set(value) == expected
            and all(type(count) is int and count >= 0 for count in value.values())
        )

    @staticmethod
    def _valid_inbox_data(value: object, *, bounded: object) -> bool:
        from control_plane import executive_inbox

        keys = {
            "schema", "generated_at", "grounding", "attention",
            "runtime_counts", "suppressed", "degraded",
        }
        if (
            type(value) is not dict
            or set(value) != keys
            or value["schema"] != executive_inbox.SCHEMA
            or not CeoIngressReadGateway._valid_generated_at(value["generated_at"])
            or not CeoIngressReadGateway._valid_bounding_receipts(bounded)
        ):
            return False
        receipts = {receipt["field"]: receipt for receipt in bounded}
        consumed: set[str] = set()
        if not (
            CeoIngressReadGateway._valid_inbox_grounding(
                value["grounding"], receipts=receipts, consumed=consumed
            )
            and type(value["attention"]) is list
            and all(
                CeoIngressReadGateway._valid_inbox_attention_item(
                    item,
                    index=index,
                    receipts=receipts,
                    consumed=consumed,
                )
                for index, item in enumerate(value["attention"])
            )
            and CeoIngressReadGateway._valid_runtime_counts(value["runtime_counts"])
            and CeoIngressReadGateway._valid_inbox_suppressed(value["suppressed"])
            and type(value["degraded"]) is list
            and all(
                CeoIngressReadGateway._valid_bounded_text(
                    item,
                    field=f"degraded[{index}]",
                    receipts=receipts,
                    consumed=consumed,
                )
                for index, item in enumerate(value["degraded"])
            )
        ):
            return False
        # Every outer bounding receipt for an inbox must bind one accepted
        # replacement object at exactly the same data path; no orphan receipt
        # may make an otherwise foreign replacement look canonical.
        return consumed == set(receipts)

    @staticmethod
    def _valid_job_data(value: object, *, arguments: Mapping[str, Any]) -> bool:
        if type(value) is not dict or set(value) != {
            "job", "attempts", "attempt_count", "attempt_limit", "latest_attempt"
        }:
            return False
        job = value["job"]
        return (
            type(job) is dict
            and job.get("job_id") == arguments.get("job_id")
            and type(value["attempts"]) is list
            and type(value["attempt_count"]) is int
            and value["attempt_count"] >= 0
            and type(value["attempt_limit"]) is int
            and value["attempt_limit"] >= 1
            and (value["latest_attempt"] is None or type(value["latest_attempt"]) is dict)
        )

    @classmethod
    def _fabric_schema_family(cls) -> str:
        return "none"

    @staticmethod
    def _valid_fabric_root_row(value: object) -> bool:
        from control_plane import fabric_job_view
        from control_plane.executive_runtime import JobStatus

        return (
            type(value) is dict
            and set(value) == fabric_job_view.ROOT_ROW_KEYS
            and type(value["job_id"]) is str
            and bool(value["job_id"])
            and value["status"] in {member.value for member in JobStatus}
            and type(value["depth"]) is int
            and value["depth"] == 0
            and value["parent_job_id"] is None
            and (
                value["orchestration_role"] is None
                or (
                    type(value["orchestration_role"]) is str
                    and bool(value["orchestration_role"])
                )
            )
        )

    @staticmethod
    def _valid_fabric_root_list_v2(
        value: object, *, arguments: Mapping[str, Any]
    ) -> bool:
        import re
        from control_plane import fabric_job_view

        if (
            type(value) is not dict
            or value.get("schema") != fabric_job_view.ROOT_LIST_SCHEMA_V2
            or set(value) != fabric_job_view.ROOT_LIST_KEYS
            or not CeoIngressReadGateway._valid_generated_at(value.get("generated_at"))
        ):
            return False
        runtime = value.get("runtime")
        roots = value.get("roots")
        count = value.get("count")
        total = value.get("total")
        truncated = value.get("truncated")
        degraded = value.get("degraded")
        limit = arguments.get("limit")
        if not (
            type(runtime) is dict
            and set(runtime) == {"root", "db_present", "identity", "acquisition"}
            # Production V2/V3 binds this exact public runtime identity in
            # scripts/executive_os_phase1c.py.  Do not accept a foreign/private
            # readiness object in the otherwise schema-valid root list.
            and runtime["root"] is None
            and runtime["db_present"] is True
            and runtime["identity"] is None
            and type(roots) is list
            and all(CeoIngressReadGateway._valid_fabric_root_row(row) for row in roots)
            and len({row["job_id"] for row in roots}) == len(roots)
            and type(count) is int
            and count >= 0
            and count == len(roots)
            and (total is None or (type(total) is int and total >= count))
            and type(truncated) is bool
            and type(degraded) is list
            and all(type(item) is str for item in degraded)
            and type(limit) is int
            and limit > 0
            and count <= limit
        ):
            return False

        acquisition = runtime["acquisition"]
        template = fabric_job_view._acquisition_receipt(kind="root_discovery")
        if type(acquisition) is not dict or set(acquisition) != set(template):
            return False
        query = acquisition.get("query")
        budgets = acquisition.get("budgets")
        truncation = acquisition.get("truncation")
        provenance = acquisition.get("provenance")
        generation = acquisition.get("generation")
        snapshot_digest = acquisition.get("snapshot_digest")
        if not (
            acquisition.get("schema") == template["schema"]
            and query == {"kind": "root_discovery", "root_job_id": None}
            and acquisition.get("owner") == "executive_runtime"
            and budgets == template["budgets"]
            and (
                snapshot_digest is None
                or (
                    type(snapshot_digest) is str
                    and re.fullmatch(r"[0-9a-f]{64}", snapshot_digest) is not None
                )
            )
            and type(truncation) is dict
            and set(truncation) == {"jobs", "attempt_job_ids", "roots", "projection"}
            and truncation["jobs"] is False
            and truncation["attempt_job_ids"] == []
            and type(truncation["roots"]) is bool
            and type(truncation["projection"]) is bool
            and type(provenance) is dict
            and set(provenance) == {"state", "unjoined_job_ids"}
            and provenance["state"] in {"COMPLETE", "PARTIAL"}
            and type(provenance["unjoined_job_ids"]) is list
            and all(type(item) is str and item for item in provenance["unjoined_job_ids"])
            and provenance["unjoined_job_ids"]
            == sorted(set(provenance["unjoined_job_ids"]))
            and fabric_job_view._qualified_generation(generation) is not None
        ):
            return False

        projected_ids = {row["job_id"] for row in roots}
        unjoined_ids = set(provenance["unjoined_job_ids"])
        if provenance["state"] == "COMPLETE":
            if unjoined_ids:
                return False
        elif not projected_ids <= unjoined_ids:
            return False

        expected_truncated = bool(truncation["roots"] or truncation["projection"])
        if truncated is not expected_truncated:
            return False
        if snapshot_digest is None:
            return (
                count == 0
                and total is None
                and not truncation["roots"]
                and not truncation["projection"]
            )
        if truncation["roots"]:
            if total is not None:
                return False
        elif total is None:
            return False
        if truncation["projection"]:
            if count != limit or (total is not None and total <= count):
                return False
        elif not truncation["roots"] and total != count:
            return False
        return True

    @classmethod
    def _valid_fabric_data(
        cls, value: object, *, arguments: Mapping[str, Any]
    ) -> bool:
        from control_plane import fabric_job_view, fabric_result_projection

        if type(value) is not dict:
            return False
        view = arguments.get("view")
        family = cls._fabric_schema_family()
        if view == "roots":
            if family == "v2":
                return cls._valid_fabric_root_list_v2(
                    value, arguments=arguments
                )
            if family != "v1":
                return False
            # Preserve the frozen historical V1 reader exactly; acquisition-
            # bound row validation is a V2/V3 contract only.
            return (
                value.get("schema") == fabric_job_view.ROOT_LIST_SCHEMA
                and set(value) == fabric_job_view.ROOT_LIST_KEYS
                and type(value.get("roots")) is list
                and type(value.get("count")) is int
                and value["count"] == len(value["roots"])
                and type(value.get("truncated")) is bool
            )
        if view == "root":
            schema = value.get("schema")
            expected_schema = (
                fabric_job_view.SCHEMA
                if family == "v1"
                else fabric_job_view.SCHEMA_V2
                if family == "v2"
                else None
            )
            if (
                expected_schema is None
                or schema != expected_schema
                or set(value) != fabric_job_view.OUTPUT_KEYS
                or type(value.get("children")) is not list
                or type(value.get("unjoined_job_ids")) is not list
            ):
                return False
            requested = arguments.get("root_job_id")
            root = value.get("root")
            if root is not None and (
                type(root) is not dict
                or root.get("job_id") != requested
                or root.get("root_job_id") != requested
            ):
                return False
            if any(
                type(child) is not dict or child.get("root_job_id") != requested
                for child in value["children"]
            ):
                return False
            if family == "v2":
                runtime = value.get("runtime")
                acquisition = runtime.get("acquisition") if type(runtime) is dict else None
                query = acquisition.get("query") if type(acquisition) is dict else None
                if query != {"kind": "root_detail", "root_job_id": requested}:
                    return False
            return True
        if view == "result":
            if family != "v2":
                return False
            keys = {
                "schema", "selection", "role", "execution_status", "acceptance",
                "role_result_digest", "generation", "availability",
                "content_complete", "review", "counts", "content", "omitted",
            }
            selection = value.get("selection")
            return (
                value.get("schema")
                == fabric_result_projection.FABRIC_ROLE_RESULT_VIEW_SCHEMA
                and set(value) == keys
                and type(selection) is dict
                and set(selection) == {
                    "root_job_id", "job_id", "attempt_id", "result_envelope_digest"
                }
                and all(
                    selection.get(key) == arguments.get(key)
                    for key in (
                        "root_job_id", "job_id", "attempt_id", "result_envelope_digest"
                    )
                )
                and value.get("availability") in {
                    "AVAILABLE", "CONTENT_OVER_BUDGET"
                }
                and type(value.get("content_complete")) is bool
                and type(value.get("omitted")) is list
            )
        return False

    @staticmethod
    def _valid_intent_receipt(
        value: object, *, arguments: Mapping[str, Any]
    ) -> bool:
        import re
        from control_plane import ceo_intent

        if type(value) is not dict:
            return False
        schema = value.get("schema")
        base_keys = {
            "schema", "intent_id", "fingerprint", "job_id", "status",
            "accepted", "duplicate", "dispatched", "authority",
            "grounding", "created_at_ms",
        }
        keys = set(value)
        if schema in {ceo_intent.RECEIPT_SCHEMA, ceo_intent.RECEIPT_SCHEMA_SERVICE}:
            if keys != base_keys:
                return False
        elif schema == ceo_intent.RECEIPT_SCHEMA_V2:
            if keys not in (base_keys, base_keys | {"work_ref"}):
                return False
        elif schema == ceo_intent.RECEIPT_SCHEMA_PRINCIPAL:
            if keys != base_keys | {"principal", "request_ref"}:
                return False
        else:
            return False
        authority = value.get("authority")
        grounding = value.get("grounding")
        if not (
            type(value.get("intent_id")) is str
            and value["intent_id"] == arguments.get("intent_id")
            and ceo_intent.INTENT_ID_RE.fullmatch(value["intent_id"]) is not None
            and type(value.get("fingerprint")) is str
            and re.fullmatch(r"[0-9a-f]{64}", value["fingerprint"]) is not None
            and type(value.get("job_id")) is str
            and re.fullmatch(r"JOB-[0-9]{1,9}", value["job_id"]) is not None
            and type(value.get("status")) is str
            and value.get("accepted") is True
            and type(value.get("duplicate")) is bool
            and value.get("dispatched") is False
            and type(value.get("created_at_ms")) is int
            and value["created_at_ms"] >= 0
            and type(authority) is dict
            and set(authority) == {"requested", "policy_sha256", "authority_level"}
            and type(authority["requested"]) is list
            and all(type(item) is str for item in authority["requested"])
            and type(authority["policy_sha256"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", authority["policy_sha256"]) is not None
            and type(authority["authority_level"]) is str
            and re.fullmatch(r"A[0-7]", authority["authority_level"]) is not None
            and type(grounding) is dict
            and set(grounding) <= {"mastermind_sha", "macro_sha", "boot_packet_schema"}
            and {"mastermind_sha", "macro_sha"} <= set(grounding)
            and all(
                type(grounding[key]) is str
                and ceo_intent.SHA_RE.fullmatch(grounding[key]) is not None
                for key in ("mastermind_sha", "macro_sha")
            )
            and (
                "boot_packet_schema" not in grounding
                or (
                    type(grounding["boot_packet_schema"]) is str
                    and bool(grounding["boot_packet_schema"])
                    and len(grounding["boot_packet_schema"]) <= 128
                )
            )
        ):
            return False
        if schema == ceo_intent.RECEIPT_SCHEMA_V2:
            work_ref = value.get("work_ref")
            return (
                work_ref is None
                or (
                    type(work_ref) is str
                    and re.fullmatch(r"WS:[A-Z0-9][A-Za-z0-9._-]{1,63}", work_ref)
                    is not None
                )
            )
        if schema == ceo_intent.RECEIPT_SCHEMA_PRINCIPAL:
            from control_plane.coo_principal_envelope import PrincipalAdmissionContext
            from control_plane.coo_principal_request import principal_intent_id

            principal = value["principal"]
            request_ref = value["request_ref"]
            if type(principal) is not dict or set(principal) != {
                "seat", "work_ref", "principal_binding_digest",
                "mission_authority_ref", "authority_generation_digest",
            }:
                return False
            if principal.get("seat") != "coo":
                return False
            try:
                PrincipalAdmissionContext(
                    work_ref=principal["work_ref"],
                    principal_binding_digest=principal["principal_binding_digest"],
                    mission_authority_ref=principal["mission_authority_ref"],
                    authority_generation_digest=principal["authority_generation_digest"],
                )
                return principal_intent_id(request_ref) == value["intent_id"]
            except (KeyError, TypeError, ValueError):
                return False
        return True

    @classmethod
    def _valid_success_data(
        cls,
        value: object,
        *,
        tool: str,
        arguments: Mapping[str, Any],
        bounded: object,
    ) -> bool:
        if tool == "executive_state":
            return cls._valid_state_data(value)
        if tool == "executive_inbox":
            return cls._valid_inbox_data(value, bounded=bounded)
        if tool == "executive_job":
            return cls._valid_job_data(value, arguments=arguments)
        if tool == "executive_fabric":
            return cls._valid_fabric_data(value, arguments=arguments)
        if tool == "ceo_intent_status":
            return cls._valid_intent_receipt(value, arguments=arguments)
        return False

    def _is_canonical_read_result(
        self, result: object, *, tool: str, arguments: Mapping[str, Any]
    ) -> bool:
        from integrations.executive_mcp.schemas import (
            ERROR_CODES,
            RESULT_SCHEMA,
            ServerMode,
            canonical_json,
        )

        if not isinstance(result, dict) or set(result) != self._RESULT_FIELDS:
            return False
        try:
            canonical_json(result)
        except (TypeError, ValueError):
            return False
        if (
            result["schema"] != RESULT_SCHEMA
            or result["tool"] != tool
            or type(result["ok"]) is not bool
            or result["server_version"] != self._result_server_version()
            or result["mode"] != ServerMode.READONLY.value
            or not self._valid_generated_at(result["generated_at"])
            or (
                result["ok"]
                and not self._valid_grounding(result["grounding"], tool=tool)
            )
            or (
                not result["ok"]
                and result["grounding"] != {}
            )
            or not isinstance(result["degraded"], list)
            or not all(isinstance(item, str) for item in result["degraded"])
            or not self._valid_bounding_receipts(result["bounded"])
        ):
            return False
        if result["ok"]:
            return (
                result["error"] is None
                and self._valid_success_data(
                    result["data"],
                    tool=tool,
                    arguments=arguments,
                    bounded=result["bounded"],
                )
            )
        error = result["error"]
        return (
            result["data"] is None
            and isinstance(error, dict)
            and set(error).issubset({"code", "message", "intent_id"})
            and {"code", "message"}.issubset(error)
            and isinstance(error["code"], str)
            and error["code"] in ERROR_CODES
            and isinstance(error["message"], str)
            and (
                "intent_id" not in error
                or isinstance(error["intent_id"], str)
            )
        )

    @classmethod
    def _classified_upstream_failure(
        cls, upstream_code: str
    ) -> tuple[str, str]:
        code = "backend_unavailable"
        if upstream_code in cls._UNAVAILABLE_UPSTREAM_CODES:
            message = "Executive reader is unavailable in the installed backend."
        else:
            code = "backend_refused"
            if upstream_code == "authority_refused":
                message = (
                    "Executive reader permission was refused by the installed backend."
                )
            else:
                message = "Executive reader request was refused by the installed backend."
        return code, (
            message + " Read-only describes this read operation; submission and "
            "execution readiness were not observed."
        )

    @staticmethod
    def _read_failure(response: CeoIngressResponse) -> tuple[str, str]:
        """Classify one read boundary without exposing backend text or arm state."""
        code = "backend_unavailable"
        message = "Executive reader returned an invalid response."
        unanswered = (
            response.ok is None and response.result is None and response.error is None
        )
        if response.transport == TRANSPORT_NOT_SENT and unanswered:
            message = "Executive reader request was not sent."
        elif response.transport == TRANSPORT_SENT_UNKNOWN and unanswered:
            message = (
                "A trustworthy Executive reader response was unavailable "
                "after the read request was attempted."
            )
        elif (
            response.transport == TRANSPORT_SENT_OK and response.ok is False
            and response.result is None and isinstance(response.error, dict)
            and isinstance(response.error.get("code"), str)
            and response.error["code"] in ceo_ingress.ERROR_CODES
        ):
            return CeoIngressReadGateway._classified_upstream_failure(
                response.error["code"]
            )
        return code, (
            message + " Read-only describes this read operation; submission and "
            "execution readiness were not observed."
        )

    async def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        from datetime import datetime, timezone
        from integrations.executive_mcp.schemas import (
            GatewayError, ServerMode, error_envelope,
        )
        try:
            if name not in self._READ_TOOL_NAMES:
                raise GatewayError("authority_refused", "installed reader is read-only")
            validated = self._validate_arguments(name, arguments)
            response = await self._client.send_frame(self._socket_path, {
                "schema": self._READ_SCHEMA,
                "tool": name, "arguments": validated,
            })
            result = response.result
            if (
                response.transport == TRANSPORT_SENT_OK
                and response.ok is True
                and self._is_canonical_read_result(
                    result, tool=name, arguments=validated
                )
            ):
                if result["ok"]:
                    return result
                raise GatewayError(
                    *self._classified_upstream_failure(result["error"]["code"])
                )
            raise GatewayError(*self._read_failure(response))
        except GatewayError as exc:
            return error_envelope(
                name, mode=ServerMode.READONLY,
                generated_at=datetime.now(timezone.utc).isoformat(),
                code=exc.code, message=exc.message,
            )


class WebCeoCeoIngressReadGateway(CeoIngressReadGateway):
    """Versioned Web-CEO installed reader; legacy v1 remains unchanged."""

    @classmethod
    def _fabric_schema_family(cls) -> str:
        return "v1"

    def _result_server_version(self) -> str:
        from integrations.executive_mcp.web_ceo import WEB_CEO_SERVER_VERSION

        return WEB_CEO_SERVER_VERSION

    _READ_TOOL_NAMES = (
        "executive_state",
        "executive_inbox",
        "executive_job",
        "executive_fabric",
        "ceo_intent_status",
    )
    _READ_SCHEMA = ceo_ingress.APP_READ_SCHEMA_V2

    def _validate_arguments(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        from integrations.executive_mcp.web_ceo import (
            validate_web_ceo_tool_arguments,
        )

        return validate_web_ceo_tool_arguments(name, arguments)


class WebCeoV2CeoIngressReadGateway(WebCeoCeoIngressReadGateway):
    """Static Web-CEO v2 installed reader (App-read v3); earlier readers frozen."""

    @classmethod
    def _fabric_schema_family(cls) -> str:
        return "v2"

    _READ_SCHEMA = ceo_ingress.APP_READ_SCHEMA_V3

    def _result_server_version(self) -> str:
        from integrations.executive_mcp.web_ceo import WEB_CEO_V2_SERVER_VERSION

        return WEB_CEO_V2_SERVER_VERSION

    def _validate_arguments(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        from integrations.executive_mcp.web_ceo import (
            validate_web_ceo_v2_tool_arguments,
        )

        return validate_web_ceo_v2_tool_arguments(name, arguments)


async def observe_ingress_grounding(
    client: CeoIngressClient, socket_path: Path | str,
) -> dict[str, str]:
    """Read the host-bound source identities from the existing trusted ingress."""
    response = await client.send_frame(socket_path, {"schema": ceo_ingress.APP_GROUNDING_SCHEMA})
    if response.transport != TRANSPORT_SENT_OK or response.ok is not True:
        raise GroundingUnavailable("installed grounding is unavailable")
    result = ceo_ingress._coerce_grounding_shape(response.result)
    if result is None:
        raise GroundingUnavailable("installed grounding is unavailable")
    return result


def make_jwt_authenticator_variants(
    primary: AppPolicies,
    alternates: tuple[AppPolicies, ...] = (),
    *,
    primary_jwks_cache: JwksKeySource | None = None,
) -> tuple[tuple[JwtAuthenticator, JwtAuthenticator], ...]:
    """Build exact per-resource authenticator pairs for one Executive service.

    Every resource keeps its own immutable ResourcePolicy pair and therefore
    retains exact JWT audience validation. This helper groups those exact
    pairs for one app composition; it never turns the resource claim into a
    wildcard or list-valued policy. A caller-supplied JWKS cache belongs only
    to the primary resource. Alternate resources build their own bounded
    caches so the existing cache-sharing contract is not widened across OAuth
    resources.
    """

    if type(primary) is not AppPolicies:
        raise TypeError("primary must be AppPolicies")
    if type(alternates) is not tuple or any(
        type(item) is not AppPolicies for item in alternates
    ):
        raise TypeError("alternates must be a tuple of AppPolicies")
    pairs = [make_jwt_authenticators(primary, jwks_cache=primary_jwks_cache)]
    pairs.extend(make_jwt_authenticators(item) for item in alternates)
    return tuple(pairs)
