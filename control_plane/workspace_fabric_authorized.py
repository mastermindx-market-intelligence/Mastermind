"""Read-only, exact-run Fabric status behind existing Executive/Agent OS authority.

The trusted installed composition supplies three *incumbent owner* methods:
  executive_binding(root_id, run_id) -> verified current Executive Job/Attempt
      and original M2 Fabric run association (never a machine catalog);
  agent_permission(principal_frame, work_ref) -> current, revocable Agent OS
      visibility permission for this exact signed-in Workspace principal;
  status_reader(root_id, run_id) -> existing M2 Fabric status-only reader.

None of these methods may derive authority from user query selectors or an M2
status. This module stores no grants and issues none. Missing owner inputs refuse.
"""
from __future__ import annotations

import inspect
import re
from collections.abc import Mapping

from common.executive_workspace_contract import PRINCIPAL_KEYS

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_WORK = re.compile(r"^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$")
_JOB = re.compile(r"^JOB-[0-9]{1,9}$")
_ATTEMPT = re.compile(r"^ATT-[0-9a-f]{32}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset({
    "schema", "work_ref", "root_job_id", "job_id", "attempt_id",
    "fabric_root_id", "fabric_run_id", "effective_grant_digest",
    "authority_generation_digest", "current",
})
_PERMISSION_FIELDS = frozenset({
    "schema", "work_ref", "principal_binding_digest",
    "permission_revision", "enabled", "actions",
})
_STATUS_FIELDS = (
    "schema", "run_id", "root_id", "parent_run_id", "state", "rc", "signal",
    "result_available", "result_bytes", "accepted", "accepted_by",
    "acceptance_state", "acceptance_reason",
)
_STATES = frozenset({
    "NOT_FOUND", "STATUS_UNREADABLE", "ACTIVE_OR_WAITING", "EFFECT_UNKNOWN",
    "RESULT_UNAVAILABLE", "TERMINAL_FAILURE", "TERMINAL", "SETTLING",
})


class FabricScopeDenied(Exception):
    """No current principal/workstream/Job/Attempt/run authorization."""


class FabricSourceUnavailable(Exception):
    """Owner binding, current generation or exact M2 source unqualified."""


def selection(root_id, run_id):
    if not all(type(v) is str and _IDENTIFIER.fullmatch(v) for v in (root_id, run_id)):
        raise ValueError("invalid_input")
    return {"root_id": root_id, "run_id": run_id}


def _binding(value, selected):
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise FabricScopeDenied()
    if (value["schema"] != "mastermind.executive_fabric_attempt_binding.v1"
            or value["current"] is not True
            or not all(type(value[k]) is str and p.fullmatch(value[k])
                       for k, p in (
                           ("work_ref", _WORK), ("root_job_id", _JOB),
                           ("job_id", _JOB), ("attempt_id", _ATTEMPT),
                           ("fabric_root_id", _IDENTIFIER),
                           ("fabric_run_id", _IDENTIFIER),
                           ("effective_grant_digest", _DIGEST),
                           ("authority_generation_digest", _DIGEST),
                       ))
            or value["fabric_root_id"] != selected["root_id"]
            or value["fabric_run_id"] != selected["run_id"]):
        raise FabricScopeDenied()
    return dict(value)


def _permission(value, principal_digest, work_ref):
    if not isinstance(value, Mapping) or set(value) != _PERMISSION_FIELDS:
        raise FabricScopeDenied()
    if (value["schema"] != "mastermind.agentos_fabric_visibility.v1"
            or value["enabled"] is not True
            or value["work_ref"] != work_ref
            or value["principal_binding_digest"] != principal_digest
            or type(value["permission_revision"]) is not str
            or not _DIGEST.fullmatch(value["permission_revision"])
            or value["actions"] != ["fabric_status"]):
        raise FabricScopeDenied()
    return dict(value)


def _status(value, selected):
    """Closed, content-free transport projection. Never expose source extras."""
    if not isinstance(value, Mapping) or not set(_STATUS_FIELDS) <= set(value):
        raise FabricSourceUnavailable()
    try:
        if (value["schema"] != "mastermind.fabric_task_status.v1"
                or value["run_id"] != selected["run_id"]
                or value["root_id"] != selected["root_id"]
                or not all(type(value[k]) is str and _IDENTIFIER.fullmatch(value[k])
                           for k in ("run_id", "root_id", "acceptance_reason"))
                or not (value["parent_run_id"] is None or
                        type(value["parent_run_id"]) is str and _IDENTIFIER.fullmatch(value["parent_run_id"]))
                or value["state"] not in _STATES
                or not (value["rc"] is None or type(value["rc"]) is int and 0 <= value["rc"] <= 255)
                or not (value["signal"] is None or type(value["signal"]) is str
                        and _IDENTIFIER.fullmatch(value["signal"]))
                or type(value["result_available"]) is not bool
                or not (value["result_bytes"] is None or type(value["result_bytes"]) is int
                        and 0 <= value["result_bytes"] <= 1_000_000_000)
                or (not value["result_available"] and value["result_bytes"] is not None)
                or value["accepted"] not in (True, False, None)
                or value["accepted_by"] not in (None, "deterministic", "reviewer", "none")
                or value["acceptance_state"] not in ("UNVERIFIED", "NOT_ACCEPTED", "ACCEPTED")):
            raise FabricSourceUnavailable()
        state = ("ACCEPTED" if value["accepted"] is True else
                 "NOT_ACCEPTED" if value["accepted"] is False else "UNVERIFIED")
        if (value["acceptance_state"] != state
                or value["accepted"] is None and value["accepted_by"] is not None
                or value["accepted"] is True and (
                    value["state"] != "TERMINAL" or value["rc"] != 0
                    or value["signal"] != "ok" or not value["result_available"]
                    or value["accepted_by"] not in ("deterministic", "reviewer"))):
            raise FabricSourceUnavailable()
        return {key: value[key] for key in _STATUS_FIELDS}
    except (KeyError, TypeError, ValueError) as exc:
        raise FabricSourceUnavailable() from exc


class WorkspaceFabricAuthorizedStatus:
    """A read-only join over injected *existing* owner methods; no new authority.

    The Executive owner must verify its current stored Job/Attempt lineage and
    original Fabric association. The Agent OS owner must resolve a signed-in
    principal's current workstream visibility and revocable permission revision.
    Both reads occur before M2 acquisition and again after it. The HTTP caller
    can select only the exact root/run; no catalog, shell, paths or raw results.
    """

    def __init__(self, *, executive_binding, agent_permission, status_reader):
        if (not callable(executive_binding) or not callable(agent_permission)
                or not inspect.iscoroutinefunction(status_reader)):
            raise ValueError("trusted existing source owners are required")
        self._executive_binding = executive_binding
        self._agent_permission = agent_permission
        self._status_reader = status_reader

    def _current(self, principal_frame, stamp, selected):
        try:
            binding = _binding(self._executive_binding(
                selected["root_id"], selected["run_id"]), selected)
            permission = _permission(self._agent_permission(
                dict(principal_frame), binding["work_ref"]), stamp, binding["work_ref"])
            return binding, permission
        except FabricScopeDenied:
            raise
        except Exception as exc:
            raise FabricScopeDenied() from exc

    async def read(self, *, principal_frame, principal_stamp, root_id, run_id):
        selected = selection(root_id, run_id)
        if (type(principal_frame) is not dict or set(principal_frame) != PRINCIPAL_KEYS
                or type(principal_stamp) is not str or not _DIGEST.fullmatch(principal_stamp)):
            raise FabricScopeDenied()
        before = self._current(principal_frame, principal_stamp, selected)
        try:
            observed = await self._status_reader(root_id, run_id)
        except Exception as exc:
            raise FabricSourceUnavailable() from exc
        # Do not return *any* M2 metadata when either incumbent owner revoked,
        # rehomed or revised permission during the asynchronous acquisition.
        after = self._current(principal_frame, principal_stamp, selected)
        if before != after:
            raise FabricScopeDenied()
        return _status(observed, selected)
