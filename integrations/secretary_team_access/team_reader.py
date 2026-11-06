"""One-shot H24 team reads through an existing host-bound Secretary client.

This additive consumer reuses the incumbent client's bounded transport and
outcomes without changing its auth, lifecycle or modifying facets. The host
owns a distinct client per principal and revalidates each Workspace request.
No document, result, credential, permission or fingerprint is cached here.
"""
from __future__ import annotations

from typing import Any

import httpx

from common import executive_workspace_mission_result_contract as pair_contract
from common import product_acceptance_read_contract as acceptance_contract
from common.executive_workspace_contract import MAX_RESPONSE_BYTES, v2_selection
from control_plane.mission_workspace import (
    FABRIC_V3_ORCHESTRATION_ROLES, FABRIC_V3_REF_KEYS,
)
from integrations.secretary_team_access.client import (
    SecretaryAccessClient, _outcome, _refusal_code,
)
from integrations.secretary_team_access.team_projection import (
    DEFAULT_CARDS, MAX_CARDS, project_team,
)

_MISSION = "/workspace/mission/v3/current"
_RESULT = "/workspace/mission-result/current"
_ACCEPTANCE = "/workspace/mission/v4/current"


def _options(previous_fingerprint, limit, suppress_unchanged_details):
    # Validate caller-controlled display options before any request. These are
    # view comparisons, never authorization or a server continuation cursor.
    if (previous_fingerprint is not None and (
            type(previous_fingerprint) is not str
            or len(previous_fingerprint) != 64
            or any(c not in "0123456789abcdef" for c in previous_fingerprint))):
        raise ValueError("invalid_previous_fingerprint")
    if type(limit) is not int or not 0 <= limit <= MAX_CARDS:
        raise ValueError("invalid_limit")
    if type(suppress_unchanged_details) is not bool:
        raise ValueError("invalid_detail_policy")
    return {"previous_fingerprint": previous_fingerprint, "limit": limit,
            "suppress_unchanged_details": suppress_unchanged_details}


class SecretaryTeamReader:
    """A read-only view of one existing SecretaryAccessClient's fixed mission.

    The incumbent host retains ownership of transport, credentials, clock and
    client lifetime. Create a new host client and reader on principal/selection
    replacement; never rebind a live client or reuse its private view cache.
    Each method performs exactly one existing Workspace GET, with no fallback,
    result fan-out, polling or command. Unchanged reads keep cards by default.
    """

    __slots__ = ("_client", "_workspace", "_selection")

    def __init__(self, client: SecretaryAccessClient) -> None:
        if not isinstance(client, SecretaryAccessClient):
            raise ValueError("host_secretary_client_required")
        if (not isinstance(client._workspace, httpx.AsyncClient)
                or client._workspace.follow_redirects):
            raise ValueError("host_client_must_be_async_no_redirects")
        self._client = client
        self._workspace = client._workspace
        self._selection = v2_selection(client.selection, "mission_v3")

    def _bound(self) -> bool:
        return (self._client._workspace is self._workspace
                and self._client.selection == self._selection
                and not self._workspace.follow_redirects)

    async def _read(self, operation: str, route: str, selected: dict,
                    options: dict, *, reference: dict | None = None,
                    request_message_key: str | None = None) -> dict[str, Any]:
        if not self._bound():
            return _outcome(operation, "REFUSED", reason_code="host_binding_changed")
        code, status, payload = await self._client._request(
            self._workspace, "GET", route, params=selected,
            max_bytes=MAX_RESPONSE_BYTES, modifying=False)
        # A host selection/client replacement during the await invalidates the
        # response. This identity fence does not replace the owner's two auth
        # checks or authorize in-place credential/principal replacement.
        if not self._bound():
            return _outcome(operation, "REFUSED", reason_code="host_binding_changed")
        if code != "OK":
            return _outcome(operation, code, reason_code=(
                _refusal_code(payload) if code == "REFUSED" else "source_unavailable"))
        if status != 200:
            return _outcome(operation, "UNAVAILABLE", reason_code="invalid_owner_status")
        try:
            extra: dict[str, Any] = {}
            mission = payload
            if reference is not None:
                pair_contract.validate_body(payload)
                if payload["selection"] != selected:
                    raise ValueError("foreign_result")
                if payload["availability"] == "UNAVAILABLE":
                    # The owner deliberately discarded both documents. A
                    # separate Mission read would invent association/freshness.
                    return _outcome(operation, "UNAVAILABLE",
                        reason_code="compound_unavailable",
                        source_reason_codes=sorted(payload["reason_codes"]))
                mission = payload["mission"]
                if reference not in mission["result_refs"]["refs"]:
                    raise ValueError("result_reference_changed")
                extra["result_pairs"] = (payload,)
            elif request_message_key is not None:
                mission = payload["mission"]
                extra.update(acceptance_companion=payload,
                             request_message_key=request_message_key)
            return project_team(mission, selection=self._selection,
                                now=self._client._clock(), **options, **extra)
        except (TypeError, ValueError, KeyError, OverflowError):
            # No unvalidated response fields, content or raw errors are exposed.
            return _outcome(operation, "UNAVAILABLE", reason_code="invalid_owner_document")

    async def read_team(self, *, previous_fingerprint: str | None = None,
                        limit: int = DEFAULT_CARDS,
                        suppress_unchanged_details: bool = False) -> dict[str, Any]:
        """Read Mission v3; result references remain explicitly unvalidated."""
        options = _options(previous_fingerprint, limit, suppress_unchanged_details)
        return await self._read("team", _MISSION, dict(self._selection), options)

    async def read_result(self, reference: dict, *,
                          previous_fingerprint: str | None = None,
                          limit: int = DEFAULT_CARDS,
                          suppress_unchanged_details: bool = False) -> dict[str, Any]:
        """Qualify one displayed reference with its atomically paired Mission.

        Pass the exact six-field ``card['result']['reference']``. The existing
        five-field owner selector is derived with this reader's fixed work/root.
        The returned view replaces the previous view; it is never merged into it.
        """
        options = _options(previous_fingerprint, limit, suppress_unchanged_details)
        if (type(reference) is not dict or set(reference) != FABRIC_V3_REF_KEYS
                or reference.get("root_job_id") != self._selection["root_job_id"]
                or type(reference.get("validation")) is not str
                or reference.get("validation") != "UNVALIDATED"
                or type(reference.get("orchestration_role")) is not str
                or reference["orchestration_role"] not in FABRIC_V3_ORCHESTRATION_ROLES):
            raise ValueError("invalid_result_reference")
        selected = pair_contract.selection({"work_ref": self._selection["work_ref"],
            **{key: reference[key] for key in (
                "root_job_id", "job_id", "attempt_id", "result_envelope_digest")}})
        # Copy before await; callers cannot change the requested reference while
        # the owner is acquiring the associated Mission/result observation.
        return await self._read("team_result", _RESULT, selected, options,
                                reference=dict(reference))

    async def read_acceptance(self, request_message_key: str, *,
                              previous_fingerprint: str | None = None,
                              limit: int = DEFAULT_CARDS,
                              suppress_unchanged_details: bool = False) -> dict[str, Any]:
        """Read Mission v4 for the original host-held request message key.

        This read consumes the existing acceptance owner; it neither accepts a
        result nor infers acceptance from a terminal Attempt, review or CI.
        """
        options = _options(previous_fingerprint, limit, suppress_unchanged_details)
        selected = acceptance_contract.selection({**self._selection,
            "request_message_key": request_message_key})
        return await self._read("team_acceptance", _ACCEPTANCE, selected, options,
                                request_message_key=selected["request_message_key"])
