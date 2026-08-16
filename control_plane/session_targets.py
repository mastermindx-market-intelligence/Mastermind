"""Provider-neutral session / target identity for the Wake Fabric.

``session_alias`` is Mastermind's stable logical identity (``PROPHET-COO-A``).
``external_handle`` is a provider-specific address (Codex thread id, GUI
conversation handle, process metadata) and is never the canonical identity.

Persistence
-----------
Targets live in checked-in ``config/wake_session_targets.json``, the same
documentation-as-config class as ``config/executive_worker_routes.json``.
That is identity mapping, not lifecycle.  Jobs, Attempts, leases, and events
stay in Executive OS SQLite.  A future provider handle may later be *copied
from* ``attempts.provider_session_id`` or worker metadata; it is not stored
in a second session registry.

This module does not write files, open SQLite, or dispatch.
"""
from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any, Mapping

from control_plane.wake_events import SESSION_ALIAS_RE, SEATS


SCHEMA = "mastermind.wake_session_targets.v1"
DEFAULT_TARGETS_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "wake_session_targets.json"
)
ADAPTER_TYPES = frozenset(
    {
        "codex-app-server",
        "codex-cli",
        "chatgpt-gui",
        "grok-computer",
    }
)
_WORKSTREAM_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class SessionTargetError(ValueError):
    """The session-target registry is missing, malformed, or the alias is unknown."""


@dataclasses.dataclass(frozen=True)
class SessionTarget:
    """One provider-neutral logical session."""

    session_alias: str
    target_seat: str
    adapter_type: str
    workstream: str | None
    external_handle: str | None
    implemented: bool

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SessionTargetRegistry:
    schema: str
    lifecycle_authority: str
    production_armed: bool
    default_alias_by_seat: dict[str, str]
    workstream_alias_by_seat: dict[str, dict[str, str]]
    targets: dict[str, SessionTarget]

    def get(self, session_alias: str) -> SessionTarget:
        alias = str(session_alias or "").strip()
        try:
            return self.targets[alias]
        except KeyError as exc:
            raise SessionTargetError(f"unknown session_alias {alias!r}") from exc

    def resolve(
        self,
        target_seat: str,
        *,
        workstream: str | None = None,
        claimed_session_alias: str | None = None,
    ) -> SessionTarget:
        """Resolve a logical target from seat + optional workstream.

        ``claimed_session_alias`` is accepted so callers can *prove* it is
        inert: worker/model prose never selects the target.
        """

        seat = str(target_seat or "").strip().lower()
        if seat not in SEATS:
            raise SessionTargetError(f"unsupported target_seat {seat!r}")
        _ = claimed_session_alias  # explicitly unused; prose cannot bind identity
        stream = str(workstream or "").strip().lower() or None
        alias: str | None = None
        if stream is not None:
            if _WORKSTREAM_ID_RE.fullmatch(stream) is None:
                raise SessionTargetError("workstream must be a bounded identifier")
            alias = (self.workstream_alias_by_seat.get(stream) or {}).get(seat)
        if alias is None:
            alias = self.default_alias_by_seat.get(seat)
        if alias is None:
            raise SessionTargetError(f"no session alias configured for seat {seat!r}")
        target = self.get(alias)
        if target.target_seat != seat:
            raise SessionTargetError(
                f"session alias {alias!r} is not bound to seat {seat!r}"
            )
        return target


def load_session_targets(path: Path | None = None) -> SessionTargetRegistry:
    """Parse and validate the checked-in registry.  Fail closed."""

    target_path = DEFAULT_TARGETS_PATH if path is None else Path(path)
    try:
        raw = target_path.read_text(encoding="utf-8")
        doc = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SessionTargetError(
            f"{target_path}: session target registry is unreadable"
        ) from exc
    return _validate(doc, target_path)


def _validate(doc: Any, where: Path) -> SessionTargetRegistry:
    if not isinstance(doc, Mapping):
        raise SessionTargetError(f"{where}: top level must be a mapping")
    extra = sorted(
        set(doc)
        - {
            "schema",
            "lifecycle_authority",
            "production_armed",
            "notes",
            "default_alias_by_seat",
            "workstream_alias_by_seat",
            "targets",
        }
    )
    if extra:
        raise SessionTargetError(
            f"{where}: unknown field(s): {', '.join(extra)}"
        )
    if doc.get("schema") != SCHEMA:
        raise SessionTargetError(
            f"{where}: unsupported schema {doc.get('schema')!r}; expected {SCHEMA!r}"
        )
    if doc.get("lifecycle_authority") != "executive_os":
        raise SessionTargetError(
            f"{where}: lifecycle_authority must remain executive_os"
        )
    if doc.get("production_armed") is not False:
        raise SessionTargetError(f"{where}: production_armed must be false")
    defaults = doc.get("default_alias_by_seat")
    if not isinstance(defaults, Mapping) or set(defaults) != SEATS:
        raise SessionTargetError(
            f"{where}: default_alias_by_seat must map exactly {sorted(SEATS)}"
        )
    workstream_map = doc.get("workstream_alias_by_seat")
    if not isinstance(workstream_map, Mapping):
        raise SessionTargetError(f"{where}: workstream_alias_by_seat must be a mapping")
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
        if token not in SEATS:
            raise SessionTargetError(f"{where}: unknown default seat {seat!r}")
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
            if target.workstream not in (None, stream_id):
                raise SessionTargetError(
                    f"{where}: alias {alias!r} workstream does not match {stream_id}"
                )
            bound[token] = target.session_alias
        resolved_workstreams[stream_id] = bound

    return SessionTargetRegistry(
        schema=SCHEMA,
        lifecycle_authority="executive_os",
        production_armed=False,
        default_alias_by_seat=resolved_defaults,
        workstream_alias_by_seat=resolved_workstreams,
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
    extra = sorted(set(row) - {
        "session_alias",
        "target_seat",
        "adapter_type",
        "workstream",
        "external_handle",
        "implemented",
    })
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
    adapter_type = str(row.get("adapter_type") or "").strip()
    if adapter_type not in ADAPTER_TYPES:
        raise SessionTargetError(
            f"{where}: unknown adapter_type {adapter_type!r} for {session_alias}"
        )
    workstream_raw = row.get("workstream")
    workstream: str | None
    if workstream_raw is None or workstream_raw == "":
        workstream = None
    else:
        workstream = str(workstream_raw).strip().lower()
        if _WORKSTREAM_ID_RE.fullmatch(workstream) is None:
            raise SessionTargetError(
                f"{where}: invalid workstream on {session_alias}"
            )
    handle_raw = row.get("external_handle")
    if handle_raw is None or handle_raw == "":
        external_handle = None
    else:
        handle = str(handle_raw).strip()
        if not handle or len(handle) > 256:
            raise SessionTargetError(
                f"{where}: external_handle on {session_alias} is not a bounded address"
            )
        external_handle = handle
    implemented = row.get("implemented")
    if implemented is not False:
        raise SessionTargetError(
            f"{where}: target {session_alias} must remain unimplemented in PR-1"
        )
    return SessionTarget(
        session_alias=session_alias,
        target_seat=seat,
        adapter_type=adapter_type,
        workstream=workstream,
        external_handle=external_handle,
        implemented=False,
    )


__all__ = [
    "ADAPTER_TYPES",
    "DEFAULT_TARGETS_PATH",
    "SCHEMA",
    "SessionTarget",
    "SessionTargetError",
    "SessionTargetRegistry",
    "load_session_targets",
]
