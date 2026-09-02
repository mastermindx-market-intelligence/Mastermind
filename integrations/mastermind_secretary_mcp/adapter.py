"""Pure Secretary adapter over one injected, typed Steward read port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from integrations.mastermind_secretary_mcp.schemas import (
    GatewayError,
    error_envelope,
    result_envelope,
    validate_tool_arguments,
)

FactValue = str | int | bool


class StewardUnavailableError(RuntimeError):
    """The canonical Steward read port is unavailable."""


class GroundingRefusedError(RuntimeError):
    """The Steward refused the grounding question under its authority law."""


@dataclass(frozen=True)
class GroundingSource:
    owner: str
    source_ref: str
    observed_at: str | None


@dataclass(frozen=True)
class GroundingFact:
    subject_ref: str
    predicate: str
    value: FactValue
    freshness: str
    sources: tuple[GroundingSource, ...]


@dataclass(frozen=True)
class StewardGrounding:
    state: str
    facts: tuple[GroundingFact, ...] = ()
    reason_codes: tuple[str, ...] = ()


class StewardReadPort(Protocol):
    """The sole dependency seam; implementations live outside this package."""

    async def list_responsibilities(self) -> StewardGrounding: ...

    async def get_responsibility(self, responsibility_ref: str) -> StewardGrounding: ...

    async def get_attention(self) -> StewardGrounding: ...

    async def get_current_runtime(self, responsibility_ref: str) -> StewardGrounding: ...

    async def explain_blocker(self, responsibility_ref: str) -> StewardGrounding: ...

    async def resolve_surface(self, responsibility_ref: str) -> StewardGrounding: ...


def _source_data(source: GroundingSource) -> dict[str, object]:
    if not isinstance(source, GroundingSource):
        raise GatewayError("RESPONSE_REFUSED")
    return {
        "owner": source.owner,
        "source_ref": source.source_ref,
        "observed_at": source.observed_at,
    }


def _fact_data(fact: GroundingFact) -> dict[str, object]:
    if not isinstance(fact, GroundingFact) or not isinstance(fact.sources, tuple):
        raise GatewayError("RESPONSE_REFUSED")
    return {
        "subject_ref": fact.subject_ref,
        "predicate": fact.predicate,
        "value": fact.value,
        "freshness": fact.freshness,
        "sources": [_source_data(source) for source in fact.sources],
    }


def _grounding_data(grounding: StewardGrounding) -> dict[str, object]:
    if (
        not isinstance(grounding, StewardGrounding)
        or not isinstance(grounding.facts, tuple)
        or not isinstance(grounding.reason_codes, tuple)
    ):
        raise GatewayError("RESPONSE_REFUSED")
    return {
        "state": grounding.state,
        "facts": [_fact_data(fact) for fact in grounding.facts],
        "reason_codes": list(grounding.reason_codes),
    }


class SecretaryGroundingGateway:
    """Validate one question, call one Steward method, return one bounded envelope."""

    def __init__(self, steward: StewardReadPort) -> None:
        self._steward = steward

    async def _read(self, tool_name: str, arguments: dict[str, object]) -> StewardGrounding:
        responsibility_ref = arguments.get("responsibility_ref")
        if tool_name == "list_responsibilities":
            return await self._steward.list_responsibilities()
        if tool_name == "get_responsibility":
            return await self._steward.get_responsibility(str(responsibility_ref))
        if tool_name == "get_attention":
            return await self._steward.get_attention()
        if tool_name == "get_current_runtime":
            return await self._steward.get_current_runtime(str(responsibility_ref))
        if tool_name == "explain_blocker":
            return await self._steward.explain_blocker(str(responsibility_ref))
        if tool_name == "resolve_surface":
            return await self._steward.resolve_surface(str(responsibility_ref))
        raise GatewayError("INVALID_REQUEST")

    async def call(self, tool_name: str, arguments: object) -> dict[str, object]:
        try:
            normalized = validate_tool_arguments(tool_name, arguments)
        except GatewayError as exc:
            code = "INTERNAL_ERROR" if exc.code == "INTERNAL_ERROR" else "INVALID_REQUEST"
            return error_envelope(tool_name, code)
        except Exception:
            return error_envelope(tool_name, "INVALID_REQUEST")
        try:
            grounding = await self._read(tool_name, normalized)
        except StewardUnavailableError:
            return error_envelope(tool_name, "STEWARD_UNAVAILABLE")
        except GroundingRefusedError:
            return error_envelope(tool_name, "GROUNDING_REFUSED")
        except Exception:
            return error_envelope(tool_name, "INTERNAL_ERROR")
        try:
            return result_envelope(
                tool_name,
                data=_grounding_data(grounding),
                responsibility_ref=normalized.get("responsibility_ref"),
            )
        except Exception:
            return error_envelope(tool_name, "RESPONSE_REFUSED")


__all__ = [
    "FactValue",
    "GroundingFact",
    "GroundingRefusedError",
    "GroundingSource",
    "SecretaryGroundingGateway",
    "StewardGrounding",
    "StewardReadPort",
    "StewardUnavailableError",
]
