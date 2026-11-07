"""Typed binding to the incumbent Subagent Fabric-only MCP owner.

This is *not* a new MCP transport/client, account, provider, worker scheduler,
credential reader, result store, or retry loop. The authenticated Hermes host
injects its already-enrolled synchronous, single-owner MCP call function.
Unknown, old, or unauthenticated generations are refused by the caller.
"""
from __future__ import annotations

import hashlib
import inspect
import re
from collections.abc import Callable, Mapping
from typing import Any

from .native import FabricNativeRefusal, FabricPreDispatchRefusal, SessionGrant

FABRIC_SCHEMA = "mastermind.fabric_mcp.v1"
STATUS_SCHEMA = "mastermind.fabric_task_status.v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_PARENT_RESULT_BYTES = 8192


class FabricFacadePort:
    """Read and submit only through the qualified existing Fabric-only facade.

    The host owns `call_tool`, authentication, transport and connection
    lifecycle. This class has no endpoint configuration, token, credential
    fallback, model access or shell execution path.
    """

    def __init__(
        self,
        call_tool: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
        *,
        authorize_new_run: Callable[[SessionGrant, str], bool] | None = None,
        preview_route: Callable[[SessionGrant, str, str, str, str],
                                Mapping[str, Any]] | None = None,
    ) -> None:
        if not callable(call_tool) or inspect.iscoroutinefunction(call_tool):
            raise FabricNativeRefusal("FABRIC_AUTHENTICATED_CLIENT_UNBOUND")
        if preview_route is not None and (
            not callable(preview_route) or inspect.iscoroutinefunction(preview_route)
        ):
            raise FabricNativeRefusal("FABRIC_PREVIEW_OWNER_INVALID")
        if authorize_new_run is not None and (
                not callable(authorize_new_run)
                or inspect.iscoroutinefunction(authorize_new_run)):
            raise FabricNativeRefusal("FABRIC_SUBMISSION_GUARD_INVALID")
        self._call_tool = call_tool
        self._authorize_new_run = authorize_new_run
        self._preview_route = preview_route

    def _call(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        raw = self._call_tool(name, dict(arguments))
        if (not isinstance(raw, Mapping) or raw.get("schema") != FABRIC_SCHEMA
                or raw.get("action") != name):
            raise FabricNativeRefusal("FABRIC_FACADE_RESPONSE_INVALID")
        if raw.get("error") is not None:
            # No error detail, packet or raw stderr is reflected to the model.
            raise FabricNativeRefusal("FABRIC_FACADE_OBSERVATION_REFUSED")
        return raw

    @staticmethod
    def _identity(grant: SessionGrant, run_id: str) -> dict[str, Any]:
        return {"run_id": run_id, "root_id": grant.root_id,
                "parent_id": grant.parent_id}

    def preview(self, grant: SessionGrant, run_id: str, task_class: str,
                complexity: str, reason: str) -> Mapping[str, Any]:
        if self._preview_route is None:
            raise FabricNativeRefusal("FABRIC_PREVIEW_OWNER_UNBOUND")
        raw = self._preview_route(grant, run_id, task_class, complexity, reason)
        if (not isinstance(raw, Mapping) or raw.get("state") != "PREVIEW_ONLY"
                or raw.get("reserved") is not False):
            raise FabricNativeRefusal("FABRIC_PREVIEW_NOT_PROVEN")
        return {**self._identity(grant, run_id), "state": "PREVIEW_ONLY",
                "worker_started": False}

    def status(self, grant: SessionGrant, run_id: str) -> Mapping[str, Any]:
        raw = self._call("fabric_status", {"run_id": run_id,
                                            "root_id": grant.root_id})
        status = raw.get("status")
        if (raw.get("run_id") != run_id or not isinstance(status, Mapping)
                or status.get("schema") != STATUS_SCHEMA
                or type(status.get("state")) is not str):
            raise FabricNativeRefusal("FABRIC_STATUS_INVALID")
        if status.get("state") == "NOT_FOUND":
            # The incumbent facade has only observed absence. This result
            # cannot be used to infer absence after a lost possible write.
            if raw.get("root_verified") is True or status.get("result_available") is not False:
                raise FabricNativeRefusal("FABRIC_STATUS_ABSENCE_INVALID")
            return {**self._identity(grant, run_id), "state": "NOT_FOUND",
                    "reason": "ORIGINAL_ID_OBSERVED_NOT_FOUND",
                    "worker_started": False}
        root, parent = status.get("root_id"), status.get("parent_run_id")
        if root is not None and root != grant.root_id:
            raise FabricNativeRefusal("FABRIC_STATUS_FOREIGN_ROOT")
        if parent is not None and parent != grant.parent_id:
            raise FabricNativeRefusal("FABRIC_STATUS_FOREIGN_PARENT")
        recovery = raw.get("parent_recovery")
        continuation = status.get("continuation")
        if (status["state"] == "REQUEST_REFUSED_BEFORE_LAUNCH"
                and root is None and parent is None
                and raw.get("root_verified") is False
                and status.get("run_id") == run_id
                and raw.get("effective_run_id") == run_id
                and status.get("request_root_id") == grant.root_id
                and status.get("request_parent_run_id") == grant.parent_id
                and status.get("request_retained") is True
                and status.get("execution_absence_proven") is True
                and status.get("result_available") is False
                and status.get("same_run_replay_allowed") is False
                and isinstance(continuation, Mapping)
                and continuation.get("controller_return") == "RECORDED"
                and continuation.get("requested_run_id") == run_id
                and continuation.get("effective_run_id") == run_id
                and isinstance(recovery, Mapping)
                and recovery.get("schema") == "mastermind.fabric_parent_recovery_projection.v1"
                and recovery.get("requested_run_id") == run_id
                and recovery.get("effective_run_id") == run_id
                and recovery.get("request_correlation_only") is True
                and recovery.get("disposition") == "RECONCILE_PRELAUNCH_REFUSAL"):
            # Diagnose the retained ORIGINAL request without upgrading its
            # correlation into ledger lineage, execution or replay authority.
            return {**self._identity(grant, run_id),
                    "state": "REQUEST_REFUSED_BEFORE_LAUNCH",
                    "reason": "PRELAUNCH_REFUSAL_CAUSE_UNRESOLVED",
                    "worker_started": False, "request_correlation_only": True,
                    "root_verified": False, "retry_authorized": False,
                    "result_consumption_authorized": False}
        if (raw.get("root_verified") is not True
                or root != grant.root_id or parent != grant.parent_id):
            # The incumbent native status intentionally has no root/parent
            # projection for many ACTIVE_OR_WAITING runs. Never invent them
            # from the originating request. Return a truthful unverified
            # observation without permitting a replacement submit or result.
            return {**self._identity(grant, run_id), "state": "UNVERIFIED",
                    "reason": "FABRIC_STATUS_LINEAGE_NOT_PROVEN",
                    "worker_started": False}
        effective = raw.get("effective_run_id")
        if type(effective) is not str or not effective:
            raise FabricNativeRefusal("FABRIC_STATUS_EFFECTIVE_ID_INVALID")
        state = status["state"]
        # A status label alone never proves worker START.
        start_proven = (
            status.get("controller_lineage", {}).get("worker_started") is True
            if isinstance(status.get("controller_lineage"), Mapping) else False
        )
        return {**self._identity(grant, run_id), "state": state,
                "reason": None, "worker_started": start_proven,
                "effective_run_id": effective}

    def submit(self, grant: SessionGrant, run_id: str, task_class: str,
               complexity: str, packet: str, reason: str, *,
               pool: str | None = None,
               model: str | None = None) -> Mapping[str, Any]:
        args = {**self._identity(grant, run_id),
                "task_class": task_class, "task_complexity": complexity,
                "work_packet": packet}
        if reason:
            args["escalation_reason"] = reason
        # The incumbent Fabric-only facade owns native strict-pin preview,
        # qualification, exact-model recheck and zero cross-provider fallback.
        # This transport is not permitted to interpret credentials or pools.
        if pool is not None:
            args["pool"] = pool
            if model is not None:
                args["model"] = model
        # Current native session identity is not enough: the original owner
        # must prove this precise run is freshly entitled, with no earlier
        # attempted/unknown dispatch across process or connection generations.
        # This is a callback to EXISTING admission, not a new state ledger.
        if self._authorize_new_run is None:
            raise FabricPreDispatchRefusal("FABRIC_ORIGINAL_ADMISSION_UNBOUND")
        try:
            authorized = self._authorize_new_run(grant, run_id)
        except Exception:
            raise FabricPreDispatchRefusal("FABRIC_ORIGINAL_ADMISSION_UNAVAILABLE") from None
        if authorized is not True:
            raise FabricPreDispatchRefusal("FABRIC_ORIGINAL_ADMISSION_REFUSED")
        raw = self._call("fabric_request", args)
        if (raw.get("run_id") != run_id
                or raw.get("root_id") != grant.root_id
                or raw.get("parent_id") != grant.parent_id):
            raise FabricNativeRefusal("FABRIC_REQUEST_IDENTITY_MISMATCH")
        if (raw.get("delivery") != "CONTROLLER_CREATED"
                or type(raw.get("controller_pid")) is not int
                or raw.get("controller_pid") <= 0
                or raw.get("worker_start_proven") is not False):
            raise FabricNativeRefusal("FABRIC_REQUEST_RECEIPT_UNVERIFIED")
        receipt = {**self._identity(grant, run_id), "state": "CONTROLLER_CREATED",
                   "reason": "WORKER_START_NOT_YET_PROVEN", "worker_started": False}
        if raw.get("response_withheld") is True:
            # The native client retained only a canonical matching control
            # receipt after its permission changed. No result bytes survive.
            receipt.update(response_withheld=True,
                           reason="HERMES_FABRIC_RESPONSE_WITHHELD")
        return receipt

    def result(self, grant: SessionGrant, run_id: str) -> Mapping[str, Any]:
        observed = self.status(grant, run_id)
        # This is only a bounded original-parent *read*; no acceptance,
        # acknowledgement, approval or duplicate worker is triggered.
        if observed["state"] != "TERMINAL":
            raise FabricNativeRefusal("FABRIC_RESULT_NOT_TERMINAL")
        raw = self._call("fabric_result", {"run_id": run_id,
                                          "root_id": grant.root_id,
                                          "max_bytes": MAX_PARENT_RESULT_BYTES})
        if (raw.get("run_id") != run_id
                or raw.get("root_id") != grant.root_id
                or raw.get("effective_run_id") != observed["effective_run_id"]
                or raw.get("accept_run_id") != observed["effective_run_id"]):
            raise FabricNativeRefusal("FABRIC_RESULT_IDENTITY_MISMATCH")
        body, digest, count = (
            raw.get("adapter_response"), raw.get("response_sha256"),
            raw.get("response_bytes"),
        )
        if (type(body) is not str or type(digest) is not str
                or SHA256.fullmatch(digest) is None or type(count) is not int
                or not 0 <= count <= MAX_PARENT_RESULT_BYTES):
            raise FabricNativeRefusal("FABRIC_RESULT_TRANSFER_INVALID")
        data = body.encode("utf-8")
        if len(data) != count or hashlib.sha256(data).hexdigest() != digest:
            raise FabricNativeRefusal("FABRIC_RESULT_DIGEST_MISMATCH")
        current = self.status(grant, run_id)
        if (current["state"] != "TERMINAL"
                or current.get("effective_run_id") != observed["effective_run_id"]):
            raise FabricNativeRefusal("FABRIC_RESULT_LINEAGE_CHANGED")
        # status() re-verifies the original root and parent. The native caller
        # separately rechecks its original grant AFTER this final remote read.
        # These observations do not invent an atomic owner seal or acceptance.
        return {**self._identity(grant, run_id), "state": "TERMINAL",
                "result_digest": digest, "result_text": body,
                "worker_started": False}
