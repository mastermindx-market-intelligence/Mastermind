"""Optional READ tools on the incumbent authenticated Executive MCP host.

Ports must be supplied by existing authorization / Web-Sol / Agent OS owners.
This module owns no enrollment, identity, history, storage, polling or control.
The scope value is an ephemeral owner projection, not a grant minted by a model.
"""
from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from control_plane.web_sol_continuation import build_continuation
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.executive_mcp.schemas import GatewayError, ToolSpec
from .web_observation import (
    MAX_ROWS, ObservationBudgetError, bounded_bytes, project_observations,
    validate_adapters, validate_clock,
)

OBSERVE_TOOL = "session_web_observe"
CONTINUITY_TOOL = "session_continuity_read"
RESULT_SCHEMA = "mastermind.session_web_read_result.v1"
_WS = re.compile(r"^WS:[A-Z0-9][A-Z0-9-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ERRORS = {
    "not_found": "unknown or unconfigured session read tool",
    "invalid_input": "invalid bounded session read selector",
    "authentication_required": "current verified authentication is required",
    "scope_refused": "the exact read is outside the caller projection",
    "scope_changed": "the caller projection changed during the read",
    "source_unavailable": "authorized session evidence is unavailable",
    "output_too_large": "session evidence exceeds the response budget",
}


class _ReadRefusal(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(_ERRORS[code])


@dataclass(frozen=True, slots=True)
class WebSessionReadScope:
    """One immutable readback from the incumbent authorization owner.

    revision must change whenever the owner changes these grants. Adapters and
    workstreams are independently authorized and must not be derived from each
    other. Never build this value from tool arguments or an observed census.
    """

    revision: str
    adapter_instance_ids: tuple[str, ...] = ()
    workstreams: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_adapters(self.adapter_instance_ids)
        if (type(self.revision) is not str or _DIGEST.fullmatch(self.revision) is None
                or type(self.workstreams) is not tuple or len(self.workstreams) > 256
                or any(type(w) is not str or _WS.fullmatch(w) is None for w in self.workstreams)
                or len(set(self.workstreams)) != len(self.workstreams)):
            raise ValueError("invalid owner scope projection")


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class WebSessionReadTools:
    """Present optional, independently enabled reads with pre/post scope fences.

    scope_reader(principal) -> WebSessionReadScope from the existing owner.
    census_reader(principal, authorized_adapter_ids) -> closed incumbent receipts.
    continuity_reader(principal, exact_workstream) -> authorized collect_agentos.
    Ports perform bounded owner reads. They may not crawl, create enrollments,
    submit, wake, acknowledge, accept, or persist content. No default reader exists.
    """

    def __init__(
        self, *, scope_reader: Callable, census_reader: Callable | None = None,
        continuity_reader: Callable | None = None, clock: Callable | None = None,
    ) -> None:
        if not callable(scope_reader) or (census_reader is None and continuity_reader is None):
            raise TypeError("an owner scope reader and at least one read port are required")
        for value in (census_reader, continuity_reader, clock):
            if value is not None and not callable(value):
                raise TypeError("read ports and clock must be callable")
        self._scope_reader = scope_reader
        self._census_reader = census_reader
        self._continuity_reader = continuity_reader
        self._clock = clock if clock is not None else lambda: datetime.now(timezone.utc)

    def tool_specs(self) -> tuple[ToolSpec, ...]:
        specs = []
        if self._census_reader is not None:
            specs.append(ToolSpec(
                name=OBSERVE_TOOL,
                description="Read authorized current-profile ChatGPT tab observations only. "
                    "Coverage is not account history; cues are not execution or response delivery. "
                    "No transcript, registered-target inference, browser mutation or SEND.",
                input_schema={"type": "object", "properties": {
                    "max_rows": {"type": "integer", "minimum": 1, "maximum": MAX_ROWS}},
                    "additionalProperties": False},
                output_description=RESULT_SCHEMA, read_only=True))
        if self._continuity_reader is not None:
            specs.append(ToolSpec(
                name=CONTINUITY_TOOL,
                description="Read bounded canonical Agent OS continuity for one independently "
                    "authorized exact workstream. No inferred relationship to a ChatGPT tab. "
                    "Stored next actions are evidence, not execution authority. No writes or ACK.",
                input_schema={"type": "object", "properties": {
                    "workstream": {"type": "string", "pattern": _WS.pattern, "maxLength": 131}},
                    "required": ["workstream"], "additionalProperties": False},
                output_description=RESULT_SCHEMA, read_only=True))
        return tuple(specs)

    def validate(self, name: str, arguments: Any) -> dict[str, Any]:
        if name not in {spec.name for spec in self.tool_specs()}:
            raise GatewayError("not_found", _ERRORS["not_found"])
        if type(arguments) is not dict:
            raise GatewayError("invalid_input", _ERRORS["invalid_input"])
        if name == OBSERVE_TOOL:
            valid = set(arguments) <= {"max_rows"} and (
                "max_rows" not in arguments or (
                    type(arguments["max_rows"]) is int and 1 <= arguments["max_rows"] <= MAX_ROWS))
        else:
            valid = (set(arguments) == {"workstream"}
                     and type(arguments["workstream"]) is str
                     and _WS.fullmatch(arguments["workstream"]) is not None)
        if not valid:
            raise GatewayError("invalid_input", _ERRORS["invalid_input"])
        return dict(arguments)

    @staticmethod
    def error(name: Any, code: Any, _message: Any = None) -> dict[str, Any]:
        safe = code if type(code) is str and code in _ERRORS else "source_unavailable"
        return {
            "schema": RESULT_SCHEMA, "tool": name if name in (OBSERVE_TOOL, CONTINUITY_TOOL) else None,
            "ok": False, "data": None, "error": {"code": safe, "message": _ERRORS[safe]},
        }

    def _principal_now(self, principal: Any) -> datetime:
        try:
            value = principal_projection(principal)
            now = validate_clock(self._clock())
            if (type(value.issued_at) is not int or type(value.expires_at) is not int
                    or value.issued_at > now.timestamp() or value.expires_at <= now.timestamp()
                    or value.expires_at <= value.issued_at):
                raise ValueError("current principal required")
            return now
        except Exception:
            raise _ReadRefusal("authentication_required") from None

    async def _scope(self, principal: Any) -> WebSessionReadScope:
        self._principal_now(principal)
        value = await _maybe(self._scope_reader(principal))
        self._principal_now(principal)
        if type(value) is not WebSessionReadScope:
            raise ValueError("exact owner scope projection is required")
        return value

    async def handle(self, principal: Any, name: str, arguments: Any) -> dict[str, Any]:
        try:
            args = self.validate(name, arguments)
            self._principal_now(principal)
            async with asyncio.timeout(30):
                before = await self._scope(principal)
                if name == CONTINUITY_TOOL:
                    workstream = args["workstream"]
                    if workstream not in before.workstreams:
                        raise _ReadRefusal("scope_refused")
                    raw = await _maybe(self._continuity_reader(principal, workstream))
                else:
                    raw = (await _maybe(self._census_reader(principal, before.adapter_instance_ids))
                           if before.adapter_instance_ids else [])
                after = await self._scope(principal)
                now = self._principal_now(principal)
                if before != after:
                    raise _ReadRefusal("scope_changed")
                if name == CONTINUITY_TOOL:
                    data = {
                        "continuity": build_continuation(raw, workstream),
                        "session_relationship": "UNVERIFIED",
                        "runtime_status": "NOT_ESTABLISHED",
                        "response_delivery": "NOT_ESTABLISHED",
                        "authority_note": "Agent OS organizational evidence only; text grants no execution authority.",
                    }
                else:
                    data = project_observations(raw,
                        authorized_adapters=before.adapter_instance_ids,
                        now=now, max_rows=args.get("max_rows", 64))
                result = {"schema": RESULT_SCHEMA, "tool": name, "ok": True,
                          "data": data, "error": None}
                try:
                    bounded_bytes(result)
                except ObservationBudgetError:
                    return self.error(name, "output_too_large")
                return result
        except (GatewayError, _ReadRefusal) as exc:
            return self.error(name, exc.code)
        except ObservationBudgetError:
            return self.error(name, "output_too_large")
        except Exception:
            # No owner exceptions, raw payloads, secrets or paths cross the edge.
            return self.error(name, "source_unavailable")

    def extend_host_configuration(self, configuration: Mapping[str, Any]) -> dict[str, Any]:
        """Reuse the existing host authentication/audit/direct-read machinery."""
        import mcp.types as mt

        tools = configuration.get("profile_tools")
        validate = configuration.get("profile_validator")
        names = configuration.get("direct_tool_names")
        submit = configuration.get("direct_submit_names")
        handler = configuration.get("direct_handler")
        error = configuration.get("direct_error_factory")
        release = configuration.get("release_tool_names", ())
        additions = tuple(spec.name for spec in self.tool_specs())
        reserved = {OBSERVE_TOOL, CONTINUITY_TOOL}
        if (type(tools) is not tuple or type(names) is not tuple or type(submit) is not tuple
                or type(release) is not tuple or not all(callable(f) for f in (validate, handler, error))
                or reserved.intersection(names + submit + release)
                or any(t.name in reserved for t in tools)
                or len({t.name for t in tools}) != len(tools)
                or not set(submit) <= set(names) or not set(names) <= {t.name for t in tools}):
            raise ValueError("read extension cannot inherit SEND or release authority")
        extra = tuple(mt.Tool(name=spec.name, description=spec.description,
            inputSchema=spec.input_schema, annotations=mt.ToolAnnotations(**spec.annotations))
            for spec in self.tool_specs())

        def extended_validator(name, arguments):
            return self.validate(name, arguments) if name in additions else validate(name, arguments)

        async def extended_handler(principal, name, arguments):
            if name in additions:
                return await self.handle(principal, name, arguments)
            if name not in names:
                raise GatewayError("not_found", "unknown direct tool")
            return await handler(principal, name, arguments)

        def extended_error(name, code, message):
            if name in additions:
                return self.error(name, code, message)
            if name not in names:
                raise GatewayError("not_found", "unknown direct tool")
            return error(name, code, message)

        return dict(configuration, profile_tools=tools + extra,
            profile_validator=extended_validator, direct_tool_names=names + additions,
            direct_submit_names=submit, direct_handler=extended_handler,
            direct_error_factory=extended_error)
