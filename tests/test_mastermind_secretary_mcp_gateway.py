"""Typed Steward-port and bounded-result tests for GS-1A."""

from __future__ import annotations

import asyncio
import json

import pytest

from integrations.mastermind_secretary_mcp.adapter import (
    GroundingFact,
    GroundingRefusedError,
    GroundingSource,
    SecretaryGroundingGateway,
    StewardGrounding,
    StewardReadPort,
    StewardUnavailableError,
)
from integrations.mastermind_secretary_mcp.schemas import (
    MAX_FACTS,
    MAX_FACT_VALUE_CHARS,
    MAX_RESPONSE_BYTES,
    RESULT_SCHEMA,
    TOOL_SPECS,
    canonical_json,
)


def _source() -> GroundingSource:
    return GroundingSource(
        owner="agent_os",
        source_ref="WS:EXECUTIVE-CAPACITY-FABRIC",
        observed_at="2026-08-29T05:00:00Z",
    )


def _fact(*, value="needs_sol", freshness="FRESH") -> GroundingFact:
    return GroundingFact(
        subject_ref="responsibility:alpha",
        predicate="attention.state",
        value=value,
        freshness=freshness,
        sources=(_source(),),
    )


def _run(coroutine):
    return asyncio.run(coroutine)


class FakeSteward(StewardReadPort):
    """Strictly test-only port; it has no canonical-owner imports or access."""

    def __init__(self, result: StewardGrounding | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, str | None]] = []

    async def _return(self, name: str, responsibility_ref: str | None = None):
        self.calls.append((name, responsibility_ref))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def list_responsibilities(self):
        return await self._return("list_responsibilities")

    async def get_responsibility(self, responsibility_ref: str):
        return await self._return("get_responsibility", responsibility_ref)

    async def get_attention(self):
        return await self._return("get_attention")

    async def get_current_runtime(self, responsibility_ref: str):
        return await self._return("get_current_runtime", responsibility_ref)

    async def explain_blocker(self, responsibility_ref: str):
        return await self._return("explain_blocker", responsibility_ref)

    async def resolve_surface(self, responsibility_ref: str):
        return await self._return("resolve_surface", responsibility_ref)


@pytest.mark.parametrize("tool_name", [spec.name for spec in TOOL_SPECS])
def test_each_tool_calls_exactly_one_typed_steward_read(tool_name):
    steward = FakeSteward(StewardGrounding(state="FACTS", facts=(_fact(),)))
    gateway = SecretaryGroundingGateway(steward)
    arguments = (
        {}
        if tool_name in {"list_responsibilities", "get_attention"}
        else {"responsibility_ref": "responsibility:alpha"}
    )

    envelope = _run(gateway.call(tool_name, arguments))

    assert steward.calls == [
        (
            tool_name,
            None if not arguments else "responsibility:alpha",
        )
    ]
    assert envelope == {
        "schema": RESULT_SCHEMA,
        "tool": tool_name,
        "ok": True,
        "server_version": "1.0.0",
        "data": {
            "state": "FACTS",
            "facts": [
                {
                    "subject_ref": "responsibility:alpha",
                    "predicate": "attention.state",
                    "value": "needs_sol",
                    "freshness": "FRESH",
                    "sources": [
                        {
                            "owner": "agent_os",
                            "source_ref": "WS:EXECUTIVE-CAPACITY-FABRIC",
                            "observed_at": "2026-08-29T05:00:00Z",
                        }
                    ],
                }
            ],
            "reason_codes": [],
        },
        "error": None,
    }


@pytest.mark.parametrize(
    ("result", "expected_state", "expected_reasons"),
    [
        (
            StewardGrounding(state="UNKNOWN", reason_codes=("AMBIGUOUS_JOIN",)),
            "UNKNOWN",
            ["AMBIGUOUS_JOIN"],
        ),
        (
            StewardGrounding(
                state="DEGRADED",
                facts=(_fact(freshness="STALE"),),
                reason_codes=("STALE_SOURCE",),
            ),
            "DEGRADED",
            ["STALE_SOURCE"],
        ),
        (
            StewardGrounding(state="REFUSED", reason_codes=("EFFECT_UNKNOWN",)),
            "REFUSED",
            ["EFFECT_UNKNOWN"],
        ),
    ],
)
def test_unknown_degraded_and_refused_states_are_preserved(
    result, expected_state, expected_reasons
):
    gateway = SecretaryGroundingGateway(FakeSteward(result))
    envelope = _run(gateway.call("get_attention", {}))
    assert envelope["ok"] is True
    assert envelope["data"]["state"] == expected_state
    assert envelope["data"]["reason_codes"] == expected_reasons


def test_invalid_or_smuggled_input_refuses_before_steward_call():
    steward = FakeSteward(StewardGrounding(state="FACTS", facts=(_fact(),)))
    gateway = SecretaryGroundingGateway(steward)
    envelope = _run(
        gateway.call(
            "resolve_surface",
            {"responsibility_ref": "responsibility:alpha", "browser_profile": "Chairman"},
        )
    )
    assert steward.calls == []
    assert envelope["ok"] is False
    assert envelope["error"] == {
        "code": "INVALID_REQUEST",
        "message": "INVALID_REQUEST",
    }


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (StewardUnavailableError(), "STEWARD_UNAVAILABLE"),
        (GroundingRefusedError(), "GROUNDING_REFUSED"),
        (RuntimeError("provider account secret"), "INTERNAL_ERROR"),
    ],
)
def test_steward_failures_map_to_fixed_secret_free_errors(error, code):
    envelope = _run(
        SecretaryGroundingGateway(FakeSteward(error)).call("get_attention", {})
    )
    assert envelope["ok"] is False
    assert envelope["error"] == {"code": code, "message": code}
    assert "provider account secret" not in json.dumps(envelope).lower()


@pytest.mark.parametrize(
    "secret_value",
    [
        "ghp_abcdefghijklmnopqrstuvwxyz123456",
        "Bearer abcdefghijklmnopqrstuvwxyz123456",
        "-----BEGIN PRIVATE KEY-----",
        "api_key=abcdefghijklmnopqrstuv",
    ],
)
def test_secret_shaped_steward_output_is_refused(secret_value):
    result = StewardGrounding(state="FACTS", facts=(_fact(value=secret_value),))
    envelope = _run(
        SecretaryGroundingGateway(FakeSteward(result)).call("get_attention", {})
    )
    assert envelope["ok"] is False
    assert envelope["error"] == {
        "code": "RESPONSE_REFUSED",
        "message": "RESPONSE_REFUSED",
    }
    assert secret_value not in json.dumps(envelope)


def test_oversize_steward_output_is_refused():
    facts = tuple(
        GroundingFact(
            subject_ref=f"responsibility:r{index}",
            predicate="responsibility.summary",
            value="x" * MAX_FACT_VALUE_CHARS,
            freshness="FRESH",
            sources=(_source(),),
        )
        for index in range(MAX_FACTS)
    )
    envelope = _run(
        SecretaryGroundingGateway(
            FakeSteward(StewardGrounding(state="FACTS", facts=facts))
        ).call("list_responsibilities", {})
    )
    assert len(canonical_json(envelope)) < MAX_RESPONSE_BYTES
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "RESPONSE_REFUSED"


@pytest.mark.parametrize(
    "malformed",
    [
        StewardGrounding(state="FACTS"),
        StewardGrounding(state="UNKNOWN"),
        StewardGrounding(state="REFUSED", facts=(_fact(),), reason_codes=("DENIED",)),
        StewardGrounding(state="DEGRADED", facts=(_fact(),)),
    ],
)
def test_malformed_steward_state_law_refuses_response(malformed):
    envelope = _run(
        SecretaryGroundingGateway(FakeSteward(malformed)).call("get_attention", {})
    )
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "RESPONSE_REFUSED"


@pytest.mark.parametrize(
    "malformed",
    [
        object(),
        StewardGrounding(state="FACTS", facts=("not-a-fact",)),
        StewardGrounding(
            state="FACTS",
            facts=(
                GroundingFact(
                    subject_ref="responsibility:alpha",
                    predicate="attention.state",
                    value="needs_sol",
                    freshness="FRESH",
                    sources=("not-a-source",),
                ),
            ),
        ),
    ],
)
def test_runtime_type_violations_from_steward_fail_closed(malformed):
    envelope = _run(
        SecretaryGroundingGateway(FakeSteward(malformed)).call("get_attention", {})
    )
    assert envelope["ok"] is False
    assert envelope["error"] == {
        "code": "RESPONSE_REFUSED",
        "message": "RESPONSE_REFUSED",
    }
