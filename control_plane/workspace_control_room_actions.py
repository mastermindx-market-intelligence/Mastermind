"""Effect-aware actions on the existing hosted Control Room owner.

Admission is request scoped. This module creates no cache, listener, Runtime
job, effect ledger, retry path or replacement provider owner.
"""
from __future__ import annotations

import asyncio
import re
import time
from types import MappingProxyType

from common.executive_workspace_contract import error, permission_stamp
from common import workspace_control_room_action_contract as wire
from control_plane.workspace_control_room_lifecycle import (
    HostedControlRoom, _workspace_instance_locked,
)
from control_plane.workspace_owned_task import await_owned


class _AdmissionRefused(RuntimeError):
    def __init__(self, code, status):
        self.code, self.status = code, status


class ExistingControlRoomActions:
    def __init__(self, control_room, *, authorize, authorize_actions, now=None):
        if (type(control_room) is not HostedControlRoom or not callable(authorize)
                or type(authorize_actions) is not dict
                or set(authorize_actions) != wire.OPERATIONS
                or any(not callable(value) for value in authorize_actions.values())
                or (now is not None and not callable(now))):
            raise ValueError("exact existing Control Room action owners required")
        self._control_room = control_room
        self._authorize = authorize
        self._authorize_actions = MappingProxyType(dict(authorize_actions))
        self._now = now if now is not None else lambda: int(time.time())

    def _current_owner(self):
        from scripts.chairman_control_room import ServerConfig
        owner = self._control_room.current_owner()
        if type(owner) is not ServerConfig:
            raise _AdmissionRefused("source_unavailable", 503)
        with owner.state_lock:
            if owner.state_stopping:
                raise _AdmissionRefused("source_unavailable", 503)
            instance = _workspace_instance_locked(owner)
            if type(instance) is not str or re.fullmatch(r"[0-9a-f]{64}", instance) is None:
                raise _AdmissionRefused("source_unavailable", 503)
        return owner, instance

    @staticmethod
    def _permission(authorizers, principal):
        stamps = []
        try:
            for authorize in authorizers:
                if authorize(principal) is not True:
                    raise ValueError("access_denied")
                stamp = permission_stamp(authorize, principal)
                if stamp is None:
                    raise ValueError("access_denied")
                stamps.append(stamp)
        except Exception:
            raise _AdmissionRefused("access_denied", 403) from None
        return tuple(stamps)

    def _run(self, frame, host_ready):
        from scripts import chairman_control_room as owner_api

        operation, principal, payload = frame["operation"], frame["principal"], frame["payload"]
        admitted = False
        try:
            authorizers = (self._authorize, self._authorize_actions[operation])
            expected_owner, expected_instance = self._current_owner()
            initial_permission = self._permission(authorizers, principal)

            def check_admission(*, check_permission):
                if (self._authorize is not authorizers[0]
                        or self._authorize_actions[operation] is not authorizers[1]):
                    raise _AdmissionRefused("access_denied", 403)
                if (check_permission
                        and self._permission(authorizers, principal) != initial_permission):
                    raise _AdmissionRefused("access_denied", 403)
                try:
                    ready = callable(host_ready) and host_ready() is True
                except Exception:
                    ready = False
                if not ready:
                    raise _AdmissionRefused("source_unavailable", 503)
                # Resolve after potentially blocking sealed-permission checks.
                # Do not hold the state lock during permission or provider work.
                owner, instance = self._current_owner()
                if owner is not expected_owner or instance != expected_instance:
                    raise _AdmissionRefused("source_unavailable", 503)
                try:
                    now = self._now()
                except Exception:
                    raise _AdmissionRefused("access_denied", 403) from None
                if type(now) is not int or not 0 <= now < frame["admission_expires_at"]:
                    raise _AdmissionRefused("access_denied", 403)

            check_admission(check_permission=False)

            def before_effect():
                nonlocal admitted
                check_admission(check_permission=True)
                # This is the first-effect admission fact for this invocation.
                # It cannot be reset by later refusal, expiry or owner movement.
                admitted = True

            if operation == "open":
                result = owner_api.open_surface(
                    expected_owner, binding_id=payload["binding_id"],
                    target_surface=payload.get("target_surface"),
                    owed_context=(payload["owed_context"] if "owed_context" in payload
                                  else owner_api._NO_OWED_CONTEXT),
                    before_effect=before_effect,
                )
                if type(result) is not owner_api.OpenBindingResult:
                    raise ValueError("source_unavailable")
                if result.source_precondition_failed:
                    # The original owner explicitly proves no provider was reached,
                    # including an owed-source change during permission admission.
                    return wire.action_result(
                        operation, result.outcome, status=409, disposition="NOT_DISPATCHED",
                    )
                outcome = result.outcome
            elif operation == "bind":
                outcome = owner_api.bind_surface(
                    expected_owner, work_ref=payload["work_ref"], role=payload["role"],
                    provider=payload["provider"], locator=payload["locator"],
                    seat_ref=payload.get("seat_ref"), before_effect=before_effect,
                )
            elif operation == "unbind":
                outcome = owner_api.unbind_surface(
                    expected_owner, binding_id=payload["binding_id"], before_effect=before_effect,
                )
            else:
                outcome = owner_api.refresh_builds(expected_owner, before_effect=before_effect)
            # A normal owner outcome survives later admission changes. Even
            # ok:false is not a statement that no effect occurred.
            return wire.action_result(
                operation, outcome, status=200, disposition="OWNER_RETURNED",
            )
        except _AdmissionRefused as exc:
            if admitted:
                return wire.unknown_result(operation)
            return wire.refused_result(operation, code=exc.code, status=exc.status)
        except Exception:
            if admitted:
                return wire.unknown_result(operation)
            return wire.refused_result(operation, code="source_unavailable", status=503)

    async def handle_frame(self, frame, *, host_ready=None):
        try:
            request = wire.validate_frame(frame)
        except (TypeError, ValueError):
            return error("invalid_input", 400)
        # Repeated cancellation retains custody until the actual operation
        # reaches a terminal state. The existing ingress owns this request task.
        task = asyncio.create_task(asyncio.to_thread(self._run, request, host_ready))
        return {"ok": True, "result": await await_owned(task)}
