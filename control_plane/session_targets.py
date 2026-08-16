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
1. exact ``root_job_id`` binding, when that higher-scope identity is present
2. known workstream default for the declared seat
3. seat default, only when workstream and root binding are both absent

An explicit unknown or malformed workstream/root id REFUSES.  It never
silently falls through to the seat default.

Two-key arming: ``target_enabled`` AND ``transport_implemented``.  PR-1 keeps
every target disabled and every transport unimplemented.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from control_plane.wake_events import JOB_ID_RE, SEATS, canonical_json_bytes


SCHEMA = "mastermind.wake_session_targets.v2"
DEFAULT_TARGETS_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "wake_session_targets.json"
)
SESSION_ALIAS_RE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")
_WORKSTREAM_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

REASONING_SURFACES = frozenset(
    {"chatgpt-sol", "codex", "workspace-agent", "human"}
)
WAKE_TRANSPORTS = frozenset(
    {
        "grok-computer",
        "chatgpt-gui",
        "codex-app-server",
        "human",
    }
)

#: PR-1: every transport is a descriptor only.  Flip per-transport in a
#: separately reviewed adapter PR — never by renaming ``implemented``.
TRANSPORT_IMPLEMENTED: dict[str, bool] = {name: False for name in sorted(WAKE_TRANSPORTS)}


def transport_implemented(wake_transport: str) -> bool:
    token = str(wake_transport or "").strip()
    if token not in WAKE_TRANSPORTS:
        raise SessionTargetError(f"unknown wake_transport {token!r}")
    return bool(TRANSPORT_IMPLEMENTED[token])


class SessionTargetError(ValueError):
    """The session-target registry is missing, malformed, or resolution refused."""


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
    """Rotating provider/runtime address.  Never checked in as Git identity."""

    session_alias: str
    binding_generation: int
    native_handle: str | None = None
    account_label: str | None = None
    reasoning_surface: str | None = None


@dataclasses.dataclass(frozen=True)
class WakeRoute:
    """Resolved delivery snapshot.  Changing this does not change the obligation id."""

    obligation_id: str
    session_alias: str
    target_seat: str
    reasoning_surface: str
    wake_transport: str
    binding_generation: int
    route_digest: str
    root_job_id: str | None
    workstream: str | None
    target_enabled: bool
    transport_implemented: bool
    human_required: bool
    policy_version: str

    @property
    def delivery_allowed(self) -> bool:
        return (
            self.target_enabled
            and self.transport_implemented
            and not self.human_required
        )

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["delivery_allowed"] = self.delivery_allowed
        return value


@dataclasses.dataclass(frozen=True)
class SessionTargetRegistry:
    schema: str
    lifecycle_authority: str
    production_armed: bool
    policy_version: str
    default_alias_by_seat: dict[str, str]
    workstream_alias_by_seat: dict[str, dict[str, str]]
    root_job_bindings: dict[str, str]
    targets: dict[str, SessionTarget]

    def get(self, session_alias: str) -> SessionTarget:
        alias = str(session_alias or "").strip()
        try:
            return self.targets[alias]
        except KeyError as exc:
            raise SessionTargetError(f"unknown session_alias {alias!r}") from exc

    def with_root_job_bindings(
        self, bindings: Mapping[str, str]
    ) -> "SessionTargetRegistry":
        """Runtime overlay.  Checked-in Git bindings stay empty in PR-1."""

        resolved: dict[str, str] = {}
        for job_id, alias in bindings.items():
            root = str(job_id).strip()
            if JOB_ID_RE.fullmatch(root) is None:
                raise SessionTargetError(f"invalid root_job_id {job_id!r}")
            target = self.get(alias)
            resolved[root] = target.session_alias
        return dataclasses.replace(self, root_job_bindings=resolved)

    def resolve(
        self,
        target_seat: str,
        *,
        workstream: str | None = None,
        root_job_id: str | None = None,
        claimed_session_alias: str | None = None,
        binding: RuntimeBinding | None = None,
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
                raise SessionTargetError("root_job_id is malformed")
            bound_alias = self.root_job_bindings.get(root)
            if bound_alias is not None:
                target = self.get(bound_alias)
                if target.target_seat != seat:
                    raise SessionTargetError(
                        f"root_job binding {root} is not bound to seat {seat!r}"
                    )
                return _binding_must_match(target, binding)

        if stream_supplied:
            stream = str(workstream).strip().lower()
            if _WORKSTREAM_ID_RE.fullmatch(stream) is None:
                raise SessionTargetError("workstream is malformed")
            seat_map = self.workstream_alias_by_seat.get(stream)
            if seat_map is None:
                raise SessionTargetError(f"unknown workstream {stream!r}")
            alias = seat_map.get(seat)
            if alias is None:
                raise SessionTargetError(
                    f"workstream {stream!r} has no alias for seat {seat!r}"
                )
            return _binding_must_match(self.get(alias), binding)

        alias = self.default_alias_by_seat.get(seat)
        if alias is None:
            raise SessionTargetError(f"no session alias configured for seat {seat!r}")
        return _binding_must_match(self.get(alias), binding)


def route_digest(
    *,
    obligation_id: str,
    target: SessionTarget,
    binding_generation: int,
    policy_version: str,
) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "obligation_id": obligation_id,
                "session_alias": target.session_alias,
                "target_seat": target.target_seat,
                "reasoning_surface": target.reasoning_surface,
                "wake_transport": target.wake_transport,
                "binding_generation": int(binding_generation),
                "policy_version": policy_version,
            }
        )
    ).hexdigest()[:16]


def build_route(
    *,
    obligation_id: str,
    target: SessionTarget,
    registry: SessionTargetRegistry,
    transport_implemented: bool,
    root_job_id: str | None = None,
    workstream: str | None = None,
    binding: RuntimeBinding | None = None,
) -> WakeRoute:
    generation = 0 if binding is None else int(binding.binding_generation)
    human_required = (
        target.target_seat == "chairman"
        or target.reasoning_surface == "human"
        or target.wake_transport == "human"
    )
    digest = route_digest(
        obligation_id=obligation_id,
        target=target,
        binding_generation=generation,
        policy_version=registry.policy_version,
    )
    return WakeRoute(
        obligation_id=obligation_id,
        session_alias=target.session_alias,
        target_seat=target.target_seat,
        reasoning_surface=target.reasoning_surface,
        wake_transport=target.wake_transport,
        binding_generation=generation,
        route_digest=digest,
        root_job_id=root_job_id,
        workstream=workstream,
        target_enabled=target.target_enabled,
        transport_implemented=transport_implemented,
        human_required=human_required,
        policy_version=registry.policy_version,
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

    resolved_bindings: dict[str, str] = {}
    for job_id, alias in bindings_raw.items():
        root = str(job_id).strip()
        if JOB_ID_RE.fullmatch(root) is None:
            raise SessionTargetError(f"{where}: invalid root_job_id {job_id!r}")
        target = _require_alias(targets, alias, where)
        resolved_bindings[root] = target.session_alias

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
    "DEFAULT_TARGETS_PATH",
    "REASONING_SURFACES",
    "SCHEMA",
    "TRANSPORT_IMPLEMENTED",
    "WAKE_TRANSPORTS",
    "RuntimeBinding",
    "SessionTarget",
    "SessionTargetError",
    "SessionTargetRegistry",
    "WakeRoute",
    "build_route",
    "load_session_targets",
    "route_digest",
    "transport_implemented",
]
