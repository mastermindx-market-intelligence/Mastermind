"""Host-injected, one-shot consumer of existing Secretary mission/control owners.

No listener, OAuth or credential owner, scheduler, retry, broker, model/router,
or durable lifecycle is created. Each actual principal must have a distinct
host-enrolled authenticated httpx client; the server, not this SDK, enforces
the subject/grant and performs the before/after authorization checks.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from common import workspace_project_plan_contract as project_plan_wire
from common.executive_workspace_contract import _check_job_id, v2_selection
from common.executive_workspace_fabric_contract import selection as native_selection
from control_plane.coo_principal_mandate import DecisionPosture, NewEffectGate
from control_plane.coo_principal_request import (
    normalize_principal_request, principal_intent_id, principal_request_ref,
)
from control_plane.principal_ruling_target import PrincipalRulingTarget
from integrations.mastermind_company_mcp.principal_schemas import (
    validate_principal_tool_arguments,
)
from integrations.mastermind_executive_app.gateway import (
    TRANSPORT_NOT_SENT, TRANSPORT_SENT_OK,
)
from integrations.secretary_team_access.mission import summarize_mission
from integrations.secretary_team_access.projection import (
    summarize_native_catalog, summarize_native_status,
)

OUTCOME_SCHEMA = "mastermind.secretary_team_access_outcome.v1"
_READ_MISSION = "/workspace/mission/v3/current"
_READ_PROJECT_PLAN = "/workspace/project-plan/current"
_READ_COMPANY = "/workspace/company/current"
_NATIVE_CATALOG = "/workspace/fabric/catalog/current"
_NATIVE_STATUS = "/workspace/fabric/status/current"
_COO_MANDATE = "/v1/tools/executive_mandate"
_COO_SUBMIT = "/v1/tools/submit_principal_intent"
_COO_STATUS = "/v1/tools/principal_intent_status"
_RULING = "/mcp/principal-ruling"
_RESULT_RULING_SCHEMA = "mastermind.principal_ruling_forward.v1"
_MAX_MISSION = 2_000_000
_MAX_NATIVE_CATALOG = 65_536
_MAX_OTHER = 65_536
_MAX_DEPTH = 32
_MAX_NODES = 5000
_MAX_REQUEST = 8192
_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_REASON = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = item
    return value


def _nonfinite(_value: str) -> None:
    raise ValueError("nonfinite_json")


def _strict_json(raw: bytes) -> Any:
    parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                        parse_constant=_nonfinite)
    stack = [(parsed, 0)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_NODES or depth > _MAX_DEPTH:
            raise ValueError("json_shape_over_budget")
        if type(value) is dict:
            stack.extend((v, depth + 1) for v in value.values())
        elif type(value) is list:
            stack.extend((v, depth + 1) for v in value)
        elif value is None or type(value) in (str, bool, int):
            continue
        elif type(value) is float and math.isfinite(value):
            continue
        else:
            raise ValueError("invalid_json_value")
    return parsed


def _json_bytes(value: Any) -> bytes:
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
                     separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(raw) > _MAX_REQUEST:
        raise ValueError("request_over_budget")
    return raw


def _safe_code(value: Any, default: str) -> str:
    return value if type(value) is str and _CODE.fullmatch(value) else default


def _refusal_code(body: Any) -> str:
    if type(body) is dict and type(body.get("error")) is dict:
        return _safe_code(body["error"].get("code"), "authority_refused")
    return "authority_refused"


def _outcome(operation: str, state: str, *, request_ref: str | None = None,
             reason_code: str | None = None, **data: Any) -> dict[str, Any]:
    return {"schema": OUTCOME_SCHEMA, "operation": operation, "state": state,
            "request_ref": request_ref, "reason_code": reason_code,
            "replay_authorized": False, **data}


class SecretaryAccessClient:
    """One independent principal's fixed, host-bound read/control facade.

    `workspace`, `coo`, `ruling` are already authenticated clients owned
    by the installed host. No method accepts a URL, credential, actor/seat,
    provider, host, dispatch destination, retry policy or arbitrary headers.
    Optional modifying facets are unbound by default, including ruling.
    """

    def __init__(
        self, *, work_ref: str, root_job_id: str,
        workspace: httpx.AsyncClient,
        coo: httpx.AsyncClient | None = None,
        ruling: httpx.AsyncClient | None = None,
        ruling_target: PrincipalRulingTarget | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.selection = v2_selection(
            {"work_ref": work_ref, "root_job_id": root_job_id}, "mission_v3")
        for client in (workspace, coo, ruling):
            if client is not None and (
                not isinstance(client, httpx.AsyncClient) or client.follow_redirects
            ):
                raise ValueError("host_client_must_be_async_no_redirects")
        if not callable(clock):
            raise ValueError("host_clock_required")
        if ruling_target is not None and (
            type(ruling_target) is not PrincipalRulingTarget
            or ruling_target.work_ref != work_ref
        ):
            raise ValueError("host_ruling_target_mismatch")
        if (ruling is None) != (ruling_target is None):
            raise ValueError("ruling_client_and_fixed_target_required")
        self._workspace = workspace
        self._coo = coo
        self._ruling = ruling
        self._ruling_target = ruling_target
        self._clock = clock

    async def _request(
        self, client: httpx.AsyncClient, method: str, path: str, *,
        params: Mapping[str, str] | None = None,
        body: Any = None, max_bytes: int = _MAX_OTHER,
        modifying: bool = False,
    ) -> tuple[str, int | None, Any]:
        """One HTTP attempt; lost/oversized/malformed modifying reply = unknown."""
        encoded = _json_bytes(body) if body is not None else None
        headers = ({"content-type": "application/json"} if encoded is not None else {})
        if path == _RULING:
            headers.update({"accept": "application/json, text/event-stream",
                            "mcp-protocol-version": "2025-06-18"})
        status = None
        try:
            async with client.stream(method, path, params=params, content=encoded,
                                     headers=headers, follow_redirects=False) as response:
                status = response.status_code
                if 300 <= status < 400:
                    return ("EFFECT_UNKNOWN" if modifying else "UNAVAILABLE", status, None)
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        if status in (401, 403):
                            return "REFUSED", status, None
                        return ("EFFECT_UNKNOWN" if modifying else "UNAVAILABLE",
                                status, None)
                    chunks.append(chunk)
                parsed = _strict_json(b"".join(chunks))
                if status in (401, 403):
                    return "REFUSED", status, parsed
                if status in (400, 404, 409, 413, 422):
                    return "REFUSED", status, parsed
                if status >= 500 or status < 200:
                    return ("EFFECT_UNKNOWN" if modifying else "UNAVAILABLE", status, None)
                if status not in (200, 202):
                    return ("EFFECT_UNKNOWN" if modifying else "UNAVAILABLE", status, None)
                return "OK", status, parsed
        except asyncio.CancelledError:
            if modifying:
                raise MutationEffectUnknown("one attempted action has unknown effect") from None
            raise
        except Exception:
            # An observed authorization refusal remains a refusal even if its
            # body is empty, malformed, oversized or interrupted. Do not let an
            # optional second read release earlier facts after revocation.
            if status in (401, 403):
                return "REFUSED", status, None
            return ("EFFECT_UNKNOWN" if modifying else "UNAVAILABLE", None, None)

    async def read_mission(self, *, previous_fingerprint: str | None = None,
                           limit: int = 8) -> dict[str, Any]:
        code, status, payload = await self._request(
            self._workspace, "GET", _READ_MISSION,
            params=self.selection, max_bytes=_MAX_MISSION)
        if code != "OK":
            return _outcome("mission", code, reason_code=(
                _refusal_code(payload) if code == "REFUSED" else "source_unavailable"))
        try:
            return summarize_mission(payload, selection=self.selection,
                                     now=self._clock(),
                                     previous_fingerprint=previous_fingerprint,
                                     limit=limit)
        except (TypeError, ValueError, KeyError):
            return _outcome("mission", "UNAVAILABLE", reason_code="invalid_owner_document")

    async def read_project_plan(self) -> dict[str, Any]:
        """One bounded read for the host's workstream, not caller-chosen scope."""
        try:
            selected = project_plan_wire.validate_selection(
                {"work_ref": self.selection["work_ref"]})
        except (TypeError, ValueError, KeyError):
            return _outcome("project_plan", "UNAVAILABLE",
                            reason_code="invalid_host_selection")
        code, status, payload = await self._request(
            self._workspace, "GET", _READ_PROJECT_PLAN, params=selected,
            max_bytes=project_plan_wire.MAX_RESPONSE_BYTES)
        if code != "OK":
            return _outcome("project_plan", code, reason_code=(
                _refusal_code(payload) if code == "REFUSED" else "source_unavailable"))
        try:
            if status != 200:
                raise ValueError("invalid_read_status")
            value = project_plan_wire.validate_body(payload)
            if (value["selection"] != selected
                    or self.selection["work_ref"] != selected["work_ref"]):
                raise ValueError("source_selection_mismatch")
            return value
        except (TypeError, ValueError, KeyError, OverflowError, RecursionError, UnicodeError):
            return _outcome("project_plan", "UNAVAILABLE",
                            reason_code="invalid_owner_document")

    async def read_company_context(self) -> dict[str, Any]:
        """One fixed read through the same host-authenticated Workspace client.

        No model-selected company, project, role, endpoint or credential. The
        existing wire/node budgets still apply; excess input is unavailable.
        This read supplies discovery, never permission to consult or delegate.
        """
        from integrations.paperclip_control.agent_context import company_context
        selected = dict(self.selection)
        workspace = self._workspace
        code, status, payload = await self._request(
            workspace, "GET", _READ_COMPANY, params={"view": "overview"}, max_bytes=_MAX_MISSION)
        if workspace is not self._workspace or self.selection != selected:
            return _outcome("company_context", "REFUSED", reason_code="host_binding_changed")
        if code != "OK":
            return _outcome("company_context", code, reason_code=(
                _refusal_code(payload) if code == "REFUSED" else "source_unavailable"))
        if status != 200:
            return _outcome("company_context", "UNAVAILABLE", reason_code="invalid_read_status")
        return company_context(payload, work_ref=selected["work_ref"], now=self._clock())

    async def read_native_catalog(self, *,
                                  previous_fingerprint: str | None = None,
                                  limit: int = 8) -> dict[str, Any]:
        code, _, payload = await self._request(
            self._workspace, "GET", _NATIVE_CATALOG,
            max_bytes=_MAX_NATIVE_CATALOG)
        if code != "OK":
            return _outcome("native_catalog", code, reason_code=(
                _refusal_code(payload) if code == "REFUSED" else "source_unavailable"))
        try:
            return summarize_native_catalog(payload,
                                            previous_fingerprint=previous_fingerprint,
                                            limit=limit)
        except (TypeError, ValueError, KeyError):
            return _outcome("native_catalog", "UNAVAILABLE",
                            reason_code="invalid_owner_document")

    async def read_native_status(self, *, root_id: str,
                                 run_id: str) -> dict[str, Any]:
        selected = native_selection({"root_id": root_id, "run_id": run_id})
        code, _, payload = await self._request(
            self._workspace, "GET", _NATIVE_STATUS, params=selected)
        if code != "OK":
            return _outcome("native_status", code, reason_code=(
                _refusal_code(payload) if code == "REFUSED" else "source_unavailable"))
        try:
            return summarize_native_status(payload, **selected)
        except (TypeError, ValueError, KeyError):
            return _outcome("native_status", "UNAVAILABLE",
                            reason_code="invalid_owner_document")

    async def mandate(self) -> dict[str, Any]:
        if self._coo is None:
            return _outcome("mandate", "UNBOUND", reason_code="coo_host_unbound")
        code, _, payload = await self._request(
            self._coo, "POST", _COO_MANDATE,
            body={"arguments": {"work_ref": self.selection["work_ref"]}})
        if code != "OK":
            return _outcome("mandate", code, reason_code=(
                _refusal_code(payload) if code == "REFUSED" else "source_unavailable"))
        try:
            if (type(payload) is not dict or payload.get("ok") is not True
                    or type(payload.get("data")) is not dict):
                raise ValueError("invalid_mandate")
            data = payload["data"]
            mission = data["mission"]
            if (data["schema"] != "mastermind.coo_principal_mandate.v1"
                    or mission["work_ref"] != self.selection["work_ref"]
                    or mission["root_job_id"] not in (None, self.selection["root_job_id"])):
                raise ValueError("wrong_mission")
            gate, decision, reasons = (
                data["new_effect_gate"], data["decision_posture"], data["reason_codes"])
            if (gate not in {entry.value for entry in NewEffectGate}
                    or decision not in {entry.value for entry in DecisionPosture}
                    or type(reasons) is not list or len(reasons) > 32
                    or any(type(reason) is not str or _REASON.fullmatch(reason) is None
                           for reason in reasons)
                    or reasons != sorted(set(reasons))):
                raise ValueError("invalid_mandate_semantics")
            return _outcome("mandate", "OBSERVED", new_effect_gate=gate,
                            decision_posture=decision, reason_codes=list(reasons))
        except (KeyError, TypeError, ValueError):
            return _outcome("mandate", "UNAVAILABLE", reason_code="invalid_owner_document")

    async def submit_intent(self, business_request: Mapping[str, Any]) -> dict[str, Any]:
        """One irreversible-attempt boundary. Preserve req-coo even on loss."""
        normalized = normalize_principal_request(
            business_request, expected_work_ref=self.selection["work_ref"])
        request_ref = principal_request_ref(normalized)
        if self._coo is None:
            return _outcome("submit", "UNBOUND", request_ref=request_ref,
                            reason_code="coo_host_unbound")
        try:
            code, status, response = await self._request(
                self._coo, "POST", _COO_SUBMIT,
                body={"arguments": normalized}, modifying=True)
        except MutationEffectUnknown:
            return _outcome("submit", "EFFECT_UNKNOWN", request_ref=request_ref,
                            reason_code="transport_uncertain")
        if code == "EFFECT_UNKNOWN":
            return _outcome("submit", code, request_ref=request_ref,
                            reason_code="transport_uncertain")
        if code == "REFUSED":
            return _outcome("submit", "REFUSED", request_ref=request_ref,
                            reason_code=_refusal_code(response))
        try:
            if (type(response) is not dict or response.get("request_ref") != request_ref
                    or response.get("status") == "effect_unknown"):
                raise ValueError("unconfirmed_receipt")
            owner_status = response["status"]
            if owner_status == "accepted":
                receipt = response["receipt"]
                if (status != 200 or response["ok"] is not True
                        or type(receipt) is not dict
                        or receipt["request_ref"] != request_ref
                        or type(receipt["accepted"]) is not bool
                        or type(receipt["dispatched"]) is not bool
                        or receipt["accepted"] is not True
                        or not _check_job_id(receipt["job_id"])):
                    raise ValueError("invalid_accepted_receipt")
                return _outcome("submit", "ADMISSION_ACCEPTED", request_ref=request_ref,
                                job_id=receipt["job_id"], dispatched=receipt["dispatched"],
                                job_state=_safe_code(receipt.get("status"), "unknown"))
            if owner_status in ("refused", "operation_conflict"):
                return _outcome("submit", "REFUSED", request_ref=request_ref,
                                reason_code=_refusal_code(response))
        except (KeyError, TypeError, ValueError):
            pass
        return _outcome("submit", "EFFECT_UNKNOWN", request_ref=request_ref,
                        reason_code="unconfirmed_receipt")

    async def reconcile_intent(self, request_ref: str) -> dict[str, Any]:
        """Read *the original* request reference; never creates new work."""
        principal_intent_id(request_ref)
        if self._coo is None:
            return _outcome("reconcile", "UNBOUND", request_ref=request_ref,
                            reason_code="coo_host_unbound")
        code, _, response = await self._request(
            self._coo, "POST", _COO_STATUS,
            body={"arguments": {
                "work_ref": self.selection["work_ref"], "request_ref": request_ref}})
        if code != "OK":
            return _outcome("reconcile", code, request_ref=request_ref,
                            reason_code=_refusal_code(response) if code == "REFUSED"
                            else "source_unavailable")
        if type(response) is not dict or response.get("request_ref") != request_ref:
            return _outcome("reconcile", "UNAVAILABLE", request_ref=request_ref,
                            reason_code="invalid_owner_document")
        if response.get("status") == "accepted" and type(response.get("receipt")) is dict:
            receipt = response["receipt"]
            if (receipt.get("request_ref") == request_ref
                    and receipt.get("accepted") is True
                    and type(receipt.get("dispatched")) is bool
                    and _check_job_id(receipt.get("job_id"))):
                return _outcome("reconcile", "ADMISSION_ACCEPTED",
                                request_ref=request_ref,
                                job_id=receipt["job_id"],
                                job_state=_safe_code(receipt.get("status"), "unknown"),
                                dispatched=receipt["dispatched"])
            return _outcome("reconcile", "UNAVAILABLE", request_ref=request_ref,
                            reason_code="invalid_owner_receipt")
        if response.get("status") == "effect_unknown":
            return _outcome("reconcile", "EFFECT_UNKNOWN", request_ref=request_ref,
                            reason_code="owner_effect_unresolved")
        return _outcome("reconcile", "OBSERVED_NOT_ACCEPTED",
                        request_ref=request_ref, owner_status=_safe_code(
                            response.get("status"), "unknown"))

    async def rule(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Rule once on the sole host-bound obligation; no target in arguments."""
        if self._ruling is None or self._ruling_target is None:
            return _outcome("ruling", "UNBOUND", reason_code="ruling_host_unbound")
        # Validator returns a derived Dialogue body; send the original public shape.
        validate_principal_tool_arguments("ruling", arguments)
        public = dict(arguments)
        target = self._ruling_target
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "ruling", "arguments": public}}
        try:
            code, _, response = await self._request(
                self._ruling, "POST", _RULING, body=payload, modifying=True)
        except MutationEffectUnknown:
            return _outcome("ruling", "EFFECT_UNKNOWN", reason_code="transport_uncertain",
                            obligation_id=target.obligation_id)
        if code != "OK":
            return _outcome("ruling",
                            "EFFECT_UNKNOWN" if code != "REFUSED" else "REFUSED",
                            reason_code=_refusal_code(response) if code == "REFUSED"
                            else "transport_uncertain", obligation_id=target.obligation_id)
        try:
            if (type(response) is not dict or response.get("jsonrpc") != "2.0"
                    or response.get("id") != 1
                    or type(response.get("result")) is not dict):
                raise ValueError("invalid_mcp")
            result = response["result"]
            content = result["content"]
            if (type(content) is not list or len(content) != 1
                    or type(content[0]) is not dict or content[0].get("type") != "text"
                    or type(content[0].get("text")) is not str):
                raise ValueError("invalid_mcp_content")
            inner = _strict_json(content[0]["text"].encode("utf-8"))
            if (type(inner) is not dict
                    or inner.get("schema") != _RESULT_RULING_SCHEMA
                    or inner.get("obligation_id") != target.obligation_id):
                raise ValueError("unqualified_ruling")
            if (inner.get("transport") == TRANSPORT_SENT_OK and inner.get("ok") is True
                    and type(inner.get("result")) is dict
                    and inner["result"].get("ok") is True
                    and result.get("isError") is not True):
                return _outcome("ruling", "RECORDED", obligation_id=target.obligation_id)
            if inner.get("transport") == TRANSPORT_NOT_SENT:
                return _outcome("ruling", "NOT_SENT", obligation_id=target.obligation_id)
        except (TypeError, ValueError, KeyError, UnicodeError):
            pass
        return _outcome("ruling", "EFFECT_UNKNOWN", reason_code="unconfirmed_ruling",
                        obligation_id=target.obligation_id)


class MutationEffectUnknown(RuntimeError):
    """A canceled action may have reached its incumbent owner; never replay it."""
