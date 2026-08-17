"""Logical session policy for the Wake Fabric.

Checked-in Git identity is logical only:

- ``session_alias`` — Mastermind's stable executive-target name
- ``target_seat`` — chairman | ceo | coo
- ``reasoning_surface`` — who reasons (chatgpt-sol, codex, workspace-agent, human)
- ``wake_transport`` — how a nudge is delivered (grok-computer, chatgpt-gui, ...)

Native/provider handles, accounts, and Codex App Server thread ids are
*runtime bindings*.  They rotate (OHF-P0 resume/fork) and MUST NOT appear in
this file.  :class:`RuntimeBinding` is the seam; PR-1 does not persist it.

Resolution precedence
---------------------
1. ``root_job_id`` absent → workstream / seat routing may run
2. ``root_job_id`` present + valid + bound → exact root binding wins
3. ``root_job_id`` present + malformed → REFUSE
4. ``root_job_id`` present + valid but unbound → REFUSE
5. root absent + known workstream → workstream default
6. root absent + unknown/malformed workstream → REFUSE
7. root absent + workstream absent → seat default

An explicitly supplied higher-scope identity never falls through silently.

Two-key arming: ``target_enabled`` AND the canonical
``wake_transport.transport_implemented`` bit.  PR-1 keeps every target
disabled and every transport unimplemented.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from control_plane.wake_events import (
    JOB_ID_RE,
    SEATS,
    SourceKind,
    WakeObligation,
    canonical_json_bytes,
)
from control_plane.wake_transport import (
    WAKE_TRANSPORTS,
    wake_transport_descriptor,
)


SCHEMA = "mastermind.wake_session_targets.v2"
DEFAULT_TARGETS_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "wake_session_targets.json"
)
SESSION_ALIAS_RE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")
_WORKSTREAM_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
BINDING_ID_RE = re.compile(r"^bind-[a-z0-9][a-z0-9._-]{7,63}$")

REASONING_SURFACES = frozenset(
    {"chatgpt-sol", "codex", "workspace-agent", "human"}
)


class SessionTargetError(ValueError):
    """The session-target registry is missing, malformed, or resolution refused."""


class RouteRefusalError(SessionTargetError):
    """Route resolution refused.  The obligation itself still exists."""

    def __init__(self, refusal: "RouteRefusal") -> None:
        super().__init__(refusal.reason)
        self.refusal = refusal


@dataclasses.dataclass(frozen=True)
class RouteRefusal:
    obligation_id: str
    reason: str


@dataclasses.dataclass(frozen=True)
class SessionTarget:
    session_alias: str
    target_seat: str
    reasoning_surface: str
    wake_transport: str
    allowed_transports: tuple[str, ...]
    workstream: str | None
    target_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["allowed_transports"] = list(self.allowed_transports)
        return value


@dataclasses.dataclass(frozen=True)
class RuntimeBinding:
    """Rotating provider/runtime address.  Never checked in as Git identity.

    ``binding_id`` is durable and opaque so a post-restart generation 1 cannot
    match a previous life's generation 1 (ABA).  Persistence is deferred.
    """

    session_alias: str
    binding_id: str
    binding_generation: int
    native_handle: str | None = None
    account_label: str | None = None
    reasoning_surface: str | None = None

    def __post_init__(self) -> None:
        alias = str(self.session_alias or "").strip()
        if SESSION_ALIAS_RE.fullmatch(alias) is None:
            raise SessionTargetError("runtime binding session_alias is malformed")
        object.__setattr__(self, "session_alias", alias)
        token = str(self.binding_id or "").strip()
        if BINDING_ID_RE.fullmatch(token) is None:
            raise SessionTargetError("binding_id must be a durable bind-* identity")
        object.__setattr__(self, "binding_id", token)
        if type(self.binding_generation) is not int or isinstance(
            self.binding_generation, bool
        ):
            raise SessionTargetError("binding_generation must be an actual integer")
        if self.binding_generation < 1:
            raise SessionTargetError("concrete RuntimeBinding generation must be >= 1")
        if self.reasoning_surface is not None:
            surface = str(self.reasoning_surface).strip()
            if surface not in REASONING_SURFACES:
                raise SessionTargetError("runtime binding reasoning_surface is unknown")
            object.__setattr__(self, "reasoning_surface", surface)


@dataclasses.dataclass(frozen=True)
class WakeRoute:
    """Resolved delivery snapshot.  Changing this does not change the obligation id."""

    obligation_id: str
    session_alias: str
    target_seat: str
    reasoning_surface: str
    wake_transport: str
    binding_id: str
    binding_generation: int
    route_digest: str
    destination_digest: str
    policy_digest: str
    root_job_id: str | None
    workstream: str | None
    production_armed: bool
    target_enabled: bool
    transport_implemented: bool
    requires_runtime_binding: bool
    binding_ready: bool
    human_required: bool
    policy_version: str
    interface_version: str

    @property
    def delivery_allowed(self) -> bool:
        return evaluate_delivery_allowed(
            production_armed=self.production_armed,
            target_enabled=self.target_enabled,
            transport_implemented=self.transport_implemented,
            binding_ready=self.binding_ready,
            human_required=self.human_required,
            requires_runtime_binding=self.requires_runtime_binding,
        )

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["delivery_allowed"] = self.delivery_allowed
        return value


def evaluate_delivery_allowed(
    *,
    production_armed: bool,
    target_enabled: bool,
    transport_implemented: bool,
    binding_ready: bool,
    human_required: bool,
    requires_runtime_binding: bool,
) -> bool:
    if human_required:
        return False
    if not production_armed or not target_enabled or not transport_implemented:
        return False
    if requires_runtime_binding and not binding_ready:
        return False
    return True


@dataclasses.dataclass(frozen=True)
class SessionTargetRegistry:
    schema: str
    lifecycle_authority: str
    production_armed: bool
    policy_version: str
    default_alias_by_seat: dict[str, str]
    workstream_alias_by_seat: dict[str, dict[str, str]]
    root_job_bindings: dict[str, dict[str, str]]
    targets: dict[str, SessionTarget]

    def get(self, session_alias: str) -> SessionTarget:
        alias = str(session_alias or "").strip()
        try:
            return self.targets[alias]
        except KeyError as exc:
            raise SessionTargetError(f"unknown session_alias {alias!r}") from exc

    def policy_digest(self) -> str:
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    "schema": self.schema,
                    "lifecycle_authority": self.lifecycle_authority,
                    "production_armed": self.production_armed,
                    "policy_version": self.policy_version,
                    "default_alias_by_seat": self.default_alias_by_seat,
                    "workstream_alias_by_seat": self.workstream_alias_by_seat,
                    "targets": {
                        alias: {
                            "target_seat": target.target_seat,
                            "reasoning_surface": target.reasoning_surface,
                            "wake_transport": target.wake_transport,
                            "workstream": target.workstream,
                            "target_enabled": target.target_enabled,
                        }
                        for alias, target in sorted(self.targets.items())
                    },
                }
            )
        ).hexdigest()[:16]

    def with_root_job_bindings(
        self, bindings: Mapping[str, Mapping[str, str]]
    ) -> "SessionTargetRegistry":
        """Runtime overlay.  Checked-in Git bindings stay empty in PR-1."""

        resolved: dict[str, dict[str, str]] = {}
        for job_id, seat_map in bindings.items():
            root = str(job_id).strip()
            if JOB_ID_RE.fullmatch(root) is None:
                raise SessionTargetError(f"invalid root_job_id {job_id!r}")
            if not isinstance(seat_map, Mapping) or not seat_map:
                raise SessionTargetError(
                    f"root_job_id {root} bindings must map seats to aliases"
                )
            bound: dict[str, str] = {}
            for seat, alias in seat_map.items():
                token = str(seat).strip().lower()
                if token not in SEATS:
                    raise SessionTargetError(f"unsupported target_seat {token!r}")
                target = self.get(alias)
                if target.target_seat != token:
                    raise SessionTargetError(
                        f"root binding {root}/{token} is not bound to that seat"
                    )
                bound[token] = target.session_alias
            resolved[root] = bound
        return dataclasses.replace(self, root_job_bindings=resolved)

    def resolve(
        self,
        target_seat: str,
        *,
        workstream: str | None = None,
        root_job_id: str | None = None,
        claimed_session_alias: str | None = None,
        binding: RuntimeBinding | None = None,
        source_kind: str | None = None,
        source_workstream: str | None = None,
        obligation_id: str | None = None,
    ) -> SessionTarget:
        """Resolve a logical target.  Claimed aliases from prose are ignored."""

        _ = claimed_session_alias
        seat = str(target_seat or "").strip().lower()
        if seat not in SEATS:
            raise SessionTargetError(f"unsupported target_seat {seat!r}")
        stream_supplied = workstream is not None and str(workstream).strip() != ""
        root_supplied = root_job_id is not None and str(root_job_id).strip() != ""

        if root_supplied:
            root = str(root_job_id).strip()
            if JOB_ID_RE.fullmatch(root) is None:
                raise _refusal(obligation_id, "root_job_id is malformed")
            seat_map = self.root_job_bindings.get(root)
            if seat_map is None or seat not in seat_map:
                raise _refusal(
                    obligation_id,
                    f"root_job_id {root} has no binding for seat {seat}",
                )
            return _binding_must_match(self.get(seat_map[seat]), binding)

        if stream_supplied:
            stream = str(workstream).strip().lower()
            if _WORKSTREAM_ID_RE.fullmatch(stream) is None:
                raise _refusal(obligation_id, "workstream is malformed")
            seat_map = self.workstream_alias_by_seat.get(stream)
            if seat_map is None:
                raise _refusal(obligation_id, f"unknown workstream {stream!r}")
            alias = seat_map.get(seat)
            if alias is None:
                raise _refusal(
                    obligation_id,
                    f"workstream {stream!r} has no alias for seat {seat!r}",
                )
            return _binding_must_match(self.get(alias), binding)

        if (
            source_workstream
            and source_kind == SourceKind.EXECUTIVE_RUNTIME_EVENT.value
        ):
            raise _refusal(
                obligation_id,
                "runtime source_workstream is not a routing workstream; "
                "refusing seat-default fallback",
            )

        alias = self.default_alias_by_seat.get(seat)
        if alias is None:
            raise SessionTargetError(f"no session alias configured for seat {seat!r}")
        return _binding_must_match(self.get(alias), binding)


def _refusal(obligation_id: str | None, reason: str) -> RouteRefusalError:
    return RouteRefusalError(
        RouteRefusal(obligation_id=str(obligation_id or ""), reason=reason)
    )


def destination_digest(
    *,
    target: SessionTarget,
    binding_id: str,
    binding_generation: int,
) -> str:
    """Identity of the current delivery destination, excluding obligation and policy."""

    return hashlib.sha256(
        canonical_json_bytes(
            {
                "session_alias": target.session_alias,
                "reasoning_surface": target.reasoning_surface,
                "wake_transport": target.wake_transport,
                "binding_id": binding_id,
                "binding_generation": int(binding_generation),
            }
        )
    ).hexdigest()[:16]


def route_digest(
    *,
    obligation_id: str,
    destination: str,
    policy_digest: str,
) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "obligation_id": obligation_id,
                "destination_digest": destination,
                "policy_digest": policy_digest,
            }
        )
    ).hexdigest()[:16]


def route_obligation(
    obligation: WakeObligation,
    registry: SessionTargetRegistry,
    *,
    binding: RuntimeBinding | None = None,
) -> WakeRoute:
    """Public routing API.  Seat / root / routing workstream come from the obligation."""

    if not isinstance(obligation, WakeObligation):
        raise SessionTargetError("route_obligation requires a WakeObligation")
    target = registry.resolve(
        obligation.declared_target_seat,
        workstream=obligation.routing_workstream,
        root_job_id=obligation.root_job_id,
        binding=binding,
        source_kind=obligation.source_kind.value,
        source_workstream=obligation.source_workstream,
        obligation_id=obligation.obligation_id,
    )
    return _build_route(
        obligation_id=obligation.obligation_id,
        target=target,
        registry=registry,
        root_job_id=obligation.root_job_id,
        workstream=obligation.routing_workstream,
        binding=binding,
    )


def _build_route(
    *,
    obligation_id: str,
    target: SessionTarget,
    registry: SessionTargetRegistry,
    root_job_id: str | None,
    workstream: str | None,
    binding: RuntimeBinding | None,
) -> WakeRoute:
    descriptor = wake_transport_descriptor(target.wake_transport)
    human_required = (
        target.target_seat == "chairman"
        or target.reasoning_surface == "human"
        or target.wake_transport == "human"
    )
    if binding is None:
        binding_id = ""
        generation = 0
        binding_ready = False
    else:
        binding_id = binding.binding_id
        generation = binding.binding_generation
        binding_ready = True
    dest = destination_digest(
        target=target, binding_id=binding_id, binding_generation=generation
    )
    policy = registry.policy_digest()
    digest = route_digest(
        obligation_id=obligation_id, destination=dest, policy_digest=policy
    )
    return WakeRoute(
        obligation_id=obligation_id,
        session_alias=target.session_alias,
        target_seat=target.target_seat,
        reasoning_surface=target.reasoning_surface,
        wake_transport=target.wake_transport,
        binding_id=binding_id,
        binding_generation=generation,
        route_digest=digest,
        destination_digest=dest,
        policy_digest=policy,
        root_job_id=root_job_id,
        workstream=workstream,
        production_armed=registry.production_armed,
        target_enabled=target.target_enabled,
        transport_implemented=descriptor.transport_implemented,
        requires_runtime_binding=descriptor.requires_runtime_binding,
        binding_ready=binding_ready,
        human_required=human_required,
        policy_version=registry.policy_version,
        interface_version=descriptor.interface_version,
    )


def load_session_targets(path: Path | None = None) -> SessionTargetRegistry:
    target_path = DEFAULT_TARGETS_PATH if path is None else Path(path)
    try:
        doc = json.loads(target_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SessionTargetError(
            f"{target_path}: session target registry is unreadable"
        ) from exc
    return _validate(doc, target_path)


def _binding_must_match(
    target: SessionTarget, binding: RuntimeBinding | None
) -> SessionTarget:
    if binding is None:
        return target
    if binding.session_alias != target.session_alias:
        raise SessionTargetError("runtime binding session_alias does not match target")
    if (
        binding.reasoning_surface is not None
        and binding.reasoning_surface != target.reasoning_surface
    ):
        raise SessionTargetError("runtime binding reasoning_surface does not match target")
    return target


def _validate(doc: Any, where: Path) -> SessionTargetRegistry:
    if not isinstance(doc, Mapping):
        raise SessionTargetError(f"{where}: top level must be a mapping")
    extra = sorted(
        set(doc)
        - {
            "schema",
            "lifecycle_authority",
            "production_armed",
            "policy_version",
            "notes",
            "default_alias_by_seat",
            "workstream_alias_by_seat",
            "root_job_bindings",
            "targets",
        }
    )
    if extra:
        raise SessionTargetError(f"{where}: unknown field(s): {', '.join(extra)}")
    if doc.get("schema") != SCHEMA:
        raise SessionTargetError(
            f"{where}: unsupported schema {doc.get('schema')!r}; expected {SCHEMA!r}"
        )
    if doc.get("lifecycle_authority") != "executive_os":
        raise SessionTargetError(f"{where}: lifecycle_authority must remain executive_os")
    if doc.get("production_armed") is not False:
        raise SessionTargetError(f"{where}: production_armed must be false")
    policy_version = str(doc.get("policy_version") or "").strip()
    if not policy_version:
        raise SessionTargetError(f"{where}: policy_version is required")
    defaults = doc.get("default_alias_by_seat")
    if not isinstance(defaults, Mapping) or set(defaults) != SEATS:
        raise SessionTargetError(
            f"{where}: default_alias_by_seat must map exactly {sorted(SEATS)}"
        )
    workstream_map = doc.get("workstream_alias_by_seat")
    if not isinstance(workstream_map, Mapping):
        raise SessionTargetError(f"{where}: workstream_alias_by_seat must be a mapping")
    bindings_raw = doc.get("root_job_bindings") or {}
    if not isinstance(bindings_raw, Mapping):
        raise SessionTargetError(f"{where}: root_job_bindings must be a mapping")
    targets_raw = doc.get("targets")
    if not isinstance(targets_raw, Mapping) or not targets_raw:
        raise SessionTargetError(f"{where}: targets must be a non-empty mapping")

    targets: dict[str, SessionTarget] = {}
    for alias, row in targets_raw.items():
        target = _parse_target(alias, row, where)
        targets[target.session_alias] = target

    resolved_defaults: dict[str, str] = {}
    for seat, alias in defaults.items():
        token = str(seat).strip().lower()
        target = _require_alias(targets, alias, where)
        if target.target_seat != token:
            raise SessionTargetError(
                f"{where}: default alias {alias!r} is not bound to {token}"
            )
        resolved_defaults[token] = target.session_alias

    resolved_workstreams: dict[str, dict[str, str]] = {}
    for stream, seat_map in workstream_map.items():
        stream_id = str(stream).strip().lower()
        if _WORKSTREAM_ID_RE.fullmatch(stream_id) is None:
            raise SessionTargetError(f"{where}: invalid workstream {stream!r}")
        if not isinstance(seat_map, Mapping) or not seat_map:
            raise SessionTargetError(
                f"{where}: workstream {stream_id!r} must map seats to aliases"
            )
        bound: dict[str, str] = {}
        for seat, alias in seat_map.items():
            token = str(seat).strip().lower()
            if token not in SEATS:
                raise SessionTargetError(
                    f"{where}: unknown seat {seat!r} under workstream {stream_id}"
                )
            target = _require_alias(targets, alias, where)
            if target.target_seat != token:
                raise SessionTargetError(
                    f"{where}: alias {alias!r} is not bound to {token}"
                )
            bound[token] = target.session_alias
        resolved_workstreams[stream_id] = bound

    resolved_bindings: dict[str, dict[str, str]] = {}
    for job_id, seat_map in bindings_raw.items():
        root = str(job_id).strip()
        if JOB_ID_RE.fullmatch(root) is None:
            raise SessionTargetError(f"{where}: invalid root_job_id {job_id!r}")
        if not isinstance(seat_map, Mapping):
            raise SessionTargetError(
                f"{where}: root_job_bindings[{root}] must map seats to aliases"
            )
        bound: dict[str, str] = {}
        for seat, alias in seat_map.items():
            token = str(seat).strip().lower()
            if token not in SEATS:
                raise SessionTargetError(
                    f"{where}: unknown seat {seat!r} under root {root}"
                )
            target = _require_alias(targets, alias, where)
            if target.target_seat != token:
                raise SessionTargetError(
                    f"{where}: alias {alias!r} is not bound to {token}"
                )
            bound[token] = target.session_alias
        resolved_bindings[root] = bound

    return SessionTargetRegistry(
        schema=SCHEMA,
        lifecycle_authority="executive_os",
        production_armed=False,
        policy_version=policy_version,
        default_alias_by_seat=resolved_defaults,
        workstream_alias_by_seat=resolved_workstreams,
        root_job_bindings=resolved_bindings,
        targets=targets,
    )


def _require_alias(
    targets: Mapping[str, SessionTarget], alias: Any, where: Path
) -> SessionTarget:
    token = str(alias or "").strip()
    try:
        return targets[token]
    except KeyError as exc:
        raise SessionTargetError(f"{where}: unknown session_alias {token!r}") from exc


def _parse_target(alias: Any, row: Any, where: Path) -> SessionTarget:
    if not isinstance(row, Mapping):
        raise SessionTargetError(f"{where}: target {alias!r} must be a mapping")
    extra = sorted(
        set(row)
        - {
            "session_alias",
            "target_seat",
            "reasoning_surface",
            "wake_transport",
            "allowed_transports",
            "workstream",
            "target_enabled",
        }
    )
    if extra:
        raise SessionTargetError(
            f"{where}: target {alias!r} has unknown field(s): {', '.join(extra)}"
        )
    session_alias = str(row.get("session_alias") or "").strip()
    if session_alias != str(alias).strip():
        raise SessionTargetError(
            f"{where}: target key {alias!r} must equal session_alias"
        )
    if SESSION_ALIAS_RE.fullmatch(session_alias) is None:
        raise SessionTargetError(f"{where}: invalid session_alias {session_alias!r}")
    seat = str(row.get("target_seat") or "").strip().lower()
    if seat not in SEATS:
        raise SessionTargetError(f"{where}: unsupported target_seat for {session_alias}")
    surface = str(row.get("reasoning_surface") or "").strip()
    if surface not in REASONING_SURFACES:
        raise SessionTargetError(f"{where}: unknown reasoning_surface {surface!r}")
    transport = str(row.get("wake_transport") or "").strip()
    if transport not in WAKE_TRANSPORTS:
        raise SessionTargetError(f"{where}: unknown wake_transport {transport!r}")
    allowed_raw = row.get("allowed_transports") or [transport]
    if not isinstance(allowed_raw, list) or not allowed_raw:
        raise SessionTargetError(f"{where}: allowed_transports must be a non-empty list")
    allowed: list[str] = []
    for item in allowed_raw:
        token = str(item).strip()
        if token not in WAKE_TRANSPORTS:
            raise SessionTargetError(f"{where}: unknown allowed transport {token!r}")
        if token not in allowed:
            allowed.append(token)
    if transport not in allowed:
        raise SessionTargetError(
            f"{where}: wake_transport {transport!r} is not in allowed_transports"
        )
    workstream_raw = row.get("workstream")
    if workstream_raw is None or workstream_raw == "":
        workstream = None
    else:
        workstream = str(workstream_raw).strip().lower()
        if _WORKSTREAM_ID_RE.fullmatch(workstream) is None:
            raise SessionTargetError(f"{where}: invalid workstream on {session_alias}")
    if row.get("target_enabled") is not False:
        raise SessionTargetError(
            f"{where}: target {session_alias} must remain disabled in PR-1"
        )
    return SessionTarget(
        session_alias=session_alias,
        target_seat=seat,
        reasoning_surface=surface,
        wake_transport=transport,
        allowed_transports=tuple(allowed),
        workstream=workstream,
        target_enabled=False,
    )


__all__ = [
    "BINDING_ID_RE",
    "DEFAULT_TARGETS_PATH",
    "REASONING_SURFACES",
    "SCHEMA",
    "WAKE_TRANSPORTS",
    "RouteRefusal",
    "RouteRefusalError",
    "RuntimeBinding",
    "SessionTarget",
    "SessionTargetError",
    "SessionTargetRegistry",
    "WakeRoute",
    "destination_digest",
    "evaluate_delivery_allowed",
    "load_session_targets",
    "route_digest",
    "route_obligation",
]
