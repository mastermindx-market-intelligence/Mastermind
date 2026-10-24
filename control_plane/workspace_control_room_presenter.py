"""Authenticated READ presentation of the one incumbent Control Room cache.

This is a source-only adapter, not an HTTP server, socket, OAuth verifier or
operator-action grant. The existing Workspace/Executive host has to supply its
already verified principal frame and its sealed membership authorizer. A
READ-only workspace principal can observe current state; candidate discovery
requires a separately selected and revocable action owner. The four mutating
legacy Control Room routes are explicitly unimplemented, not silently mapped
from the Workspace READ permission. No alternative cache or authority is made.
"""
from __future__ import annotations

import asyncio
import copy
from collections.abc import Callable
from dataclasses import dataclass

from control_plane.session_truth_live_acquire import LiveOwnerPorts, LiveScope

from common.executive_workspace_contract import (
    MAX_RESPONSE_BYTES, PRINCIPAL_KEYS, SCOPE, bounded_canonical, permission_stamp,
)
from control_plane.workspace_owned_task import await_owned
from control_plane.workspace_read_service import ExistingControlRoomCache


def _refuse(code: str, status: int) -> dict:
    return {"ok": False, "status": status,
            "error": {"code": code, "message": "control room unavailable"}}


CROSS_PLANE_READ_SCHEMA = "mastermind.control_room_cross_plane_read.v1"


@dataclass(frozen=True)
class CrossPlaneOwnerContext:
    """Trusted host's scoped READ capability, never constructed by HTTP input."""

    scope: LiveScope
    ports: LiveOwnerPorts
    observation_clock: Callable[[], str]
    stale_after_seconds: float | None = None

    def __post_init__(self):
        if (type(self.scope) is not LiveScope or type(self.ports) is not LiveOwnerPorts
                or not callable(self.observation_clock)):
            raise ValueError("exact trusted cross-plane owner context required")


def _cross_plane_unavailable():
    return {"schema": CROSS_PLANE_READ_SCHEMA, "state": "UNAVAILABLE",
            "reason_code": "source_unavailable", "document": None}


class ExistingControlRoomPresenter:
    """A view of one existing, live Workspace cache, not a second publisher.

    The caller must be the enrolled private App-peer source: a decoded JWT or
    arbitrary email/role string has no standing at this boundary. Every read
    is permission-stamped before/after source work; publication, owner,
    payload and auth changes all refuse release rather than leak stale state.
    """

    READS = frozenset({"state", "discover"})
    MUTATIONS = frozenset({"open", "bind", "unbind", "refresh-builds"})

    def __init__(self, cache: ExistingControlRoomCache, *,
                 authorize: Callable[[dict], bool],
                 authorize_discovery: Callable[[dict], bool] | None = None,
                 cross_plane_context: Callable[[dict, object], CrossPlaneOwnerContext] | None = None):
        if type(cache) is not ExistingControlRoomCache or not callable(authorize):
            raise ValueError("existing workspace owner required")
        if authorize_discovery is not None and not callable(authorize_discovery):
            raise ValueError("discovery authority must be a callback")
        if cross_plane_context is not None and not callable(cross_plane_context):
            raise ValueError("cross-plane owner context must be a trusted callback")
        self._cache = cache
        self._authorize = authorize
        self._authorize_discovery = authorize_discovery
        self._cross_plane_context = cross_plane_context

    async def _read_cross_plane(self, principal: dict, source: object) -> dict:
        """One canonical live-owner read; no extra clients, polling or local cache."""
        try:
            context = self._cross_plane_context(principal, source)
            if type(context) is not CrossPlaneOwnerContext:
                raise ValueError("invalid trusted cross-plane context")
            from control_plane.executive_cross_plane_live import acquire_live_cross_plane_view
            from control_plane.executive_cross_plane_view import SCHEMA, OUTPUT_KEYS
            document = await await_owned(asyncio.create_task(acquire_live_cross_plane_view(
                scope=context.scope, ports=context.ports,
                observation_clock=context.observation_clock,
                stale_after_seconds=context.stale_after_seconds,
            )))
            if (type(document) is not dict or set(document) != OUTPUT_KEYS
                    or document.get("schema") != SCHEMA
                    or document.get("state") not in {"CONSUMED", "DEGRADED"}
                    or document.get("capability") != {"read_only": True, "effect": "NONE"}):
                raise ValueError("unqualified cross-plane result")
            return {"schema": CROSS_PLANE_READ_SCHEMA, "state": "AVAILABLE",
                    "reason_code": None, "document": document}
        except Exception:
            # Never release source exceptions or substitute an empty green card.
            return _cross_plane_unavailable()

    @staticmethod
    def _shape(principal: object) -> bool:
        return (type(principal) is dict and set(principal) == PRINCIPAL_KEYS
                # Exact READ principal shape from the existing sealed owner.
                # Unknown scopes cannot become authority through a callback
                # that checks only account identity.
                and principal.get("scopes") == [SCOPE])

    def _permit(self, principal: dict, *, operation: str) -> tuple[str, str | None]:
        if not self._shape(principal) or self._authorize(principal) is not True:
            raise ValueError("access_denied")
        stamp = permission_stamp(self._authorize, principal)
        if stamp is None:
            # An unsigned/unstamped test lambda is not production authority.
            raise ValueError("access_denied")
        discovery = None
        if operation == "discover":
            owner = self._authorize_discovery
            if owner is None or owner(principal) is not True:
                raise ValueError("access_denied")
            discovery = permission_stamp(owner, principal)
            if discovery is None:
                raise ValueError("access_denied")
        return stamp, discovery

    async def read(self, principal: object, operation: str) -> dict:
        if operation in self.MUTATIONS:
            # No READ->WRITE promotion. The existing per-action installer
            # has not yet granted bind/open/unbind/refresh-builds authority.
            return _refuse("access_denied", 403)
        if operation not in self.READS:
            return _refuse("invalid_input", 400)
        try:
            first = self._permit(principal, operation=operation)
        except Exception:
            return _refuse("access_denied", 403)
        try:
            before = self._cache.snapshot()
            source = before.owner
            if operation == "state":
                from scripts.chairman_control_room import (
                    _cached_state_snapshot, _ensure_capabilities_cached,
                )
                # The original CCR source computes capabilities once; this
                # runs only after the authenticated permission check.
                await await_owned(asyncio.create_task(asyncio.to_thread(
                    _ensure_capabilities_cached, source,
                )))
                body = copy.deepcopy(_cached_state_snapshot(source))
                body["control_room"] = body.pop("doc")
                body["live_builds_active"] = source.live_cache.get("active_builds") is not None
                if self._cross_plane_context is not None:
                    # This is within the same owner/permission snapshot as the
                    # incumbent READ. Only a trusted installed host can arm it.
                    body["cross_plane"] = await self._read_cross_plane(principal, source)
            else:
                from scripts.chairman_control_room import _discover_document
                body = await await_owned(asyncio.create_task(asyncio.to_thread(
                    _discover_document, source,
                )))
            after = self._cache.snapshot()
            second = self._permit(principal, operation=operation)
            if (first != second or source is not after.owner
                    or before.instance != after.instance
                    or before.publication != after.publication
                    or before.document != after.document):
                return _refuse("source_unavailable", 503)
            # Never surface arbitrary oversized local-session discovery or
            # private dependency exceptions to an authenticated browser.
            bounded_canonical(body, limit=MAX_RESPONSE_BYTES)
            return {"ok": True, "result": body}
        except ValueError as exc:
            if str(exc) == "access_denied":
                return _refuse("access_denied", 403)
            return _refuse("source_unavailable", 503)
        except Exception:
            return _refuse("source_unavailable", 503)
