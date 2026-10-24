"""Installed Control Room source selection through its existing member owner.

This creates no connection, credential, enrollment file, user registry, transport,
cache, retry or publication plane. The sealed Executive host must already own
six qualified read ports and an explicit member-scoped LiveScope selector.
Unselected hosts keep the legacy seven-field response and report NOT_INSTALLED.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from common.executive_workspace_contract import PRINCIPAL_KEYS, SCOPE, permission_stamp
from control_plane.session_truth_live_acquire import LiveScope, LiveOwnerPorts
from control_plane.workspace_control_room_presenter import CrossPlaneOwnerContext


def _clock() -> str:
    # Sampled on demand by the canonical compositor, AFTER awaited owner reads.
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class InstalledCrossPlaneEnrollment:
    """Attested host reader functions, not a request- or config-selected grant.

    These must originate in already-authorized installed GitHub/Linear/Slack/
    Executive/identity owners. An absent port/scope is a refusal, never a
    borrowed ChatGPT account, guessed link or fallback source.
    """

    member_scope: Callable[[dict[str, Any]], LiveScope | None]
    member_ports: Callable[[dict[str, Any], LiveScope], LiveOwnerPorts | None]
    stale_after_seconds: float | None = None

    def __post_init__(self) -> None:
        if not callable(self.member_scope) or not callable(self.member_ports):
            raise ValueError("installed source reader selection required")
        if self.stale_after_seconds is not None and (
            type(self.stale_after_seconds) not in (int, float)
            or not 0 < self.stale_after_seconds <= 86400
        ):
            raise ValueError("bounded source staleness required")


def select_installed_cross_plane(
    *, control_room: object, authorize: Callable[[dict], bool],
    enrollment: InstalledCrossPlaneEnrollment,
    clock: Callable[[], str] = _clock,
) -> Callable[[dict, object], CrossPlaneOwnerContext]:
    """Bind to one AF_UNIX-hosted original owner and the existing membership.

    The LiveScope cannot originate in an HTTP parameter, PR title, guessed
    Linear link, client role or unverified cache. It comes ONLY from a current
    sealed installed owner reader, evaluated for the actual member frame.
    """
    from control_plane.workspace_control_room_lifecycle import HostedControlRoom
    if (type(control_room) is not HostedControlRoom
            or not callable(authorize)
            or type(enrollment) is not InstalledCrossPlaneEnrollment
            or not callable(clock)):
        raise ValueError("installed cross-plane source owner unavailable")
    source_owner = control_room.config

    def select(principal: dict, source: object) -> CrossPlaneOwnerContext:
        if (type(principal) is not dict or set(principal) != PRINCIPAL_KEYS
                or principal.get("scopes") != [SCOPE]
                or source is not source_owner
                or authorize(principal) is not True):
            raise ValueError("access_denied")
        stamp = permission_stamp(authorize, principal)
        if stamp is None:
            raise ValueError("access_denied")
        # Detach member frames before calling installed readers. Neither
        # callback receives mutable cache state, user-supplied query or raw JWT.
        member = {key: (list(value) if type(value) is list else value)
                  for key, value in principal.items()}
        scope = enrollment.member_scope(member)
        if type(scope) is not LiveScope:
            raise ValueError("source_scope_unavailable")
        ports = enrollment.member_ports(member, scope)
        if type(ports) is not LiveOwnerPorts:
            raise ValueError("source_ports_unavailable")
        if (source is not source_owner or authorize(principal) is not True
                or permission_stamp(authorize, principal) != stamp):
            raise ValueError("access_denied")
        return CrossPlaneOwnerContext(
            scope=scope, ports=ports, observation_clock=clock,
            stale_after_seconds=enrollment.stale_after_seconds,
        )

    return select
