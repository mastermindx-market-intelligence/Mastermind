"""Typed Steward-port and bounded-result tests for GS-1A."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator, Mapping

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
    MAX_RESPONSE_BYTES,
    RESULT_SCHEMA,
    TOOL_SPECS,
    canonical_json,
)


def _source(*, source_ref="WS:EXECUTIVE-CAPACITY-FABRIC") -> GroundingSource:
    return GroundingSource(
        owner="agent_os",
        source_ref=source_ref,
        observed_at="2026-08-29T05:00:00Z",
    )


def _fact(*, value="SOL_REQUIRED", freshness="FRESH") -> GroundingFact:
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
    # Subject: routing and envelope shape, not field-set completeness. DEGRADED is
    # the contract's legal partial state, so one fact stays valid now that FACTS
    # enforces the frozen per-tool required predicates.
    steward = FakeSteward(
        StewardGrounding(
            state="DEGRADED",
            facts=(_fact(),),
            reason_codes=("STEWARD_DEGRADED",),
        )
    )
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
            "state": "DEGRADED",
            "facts": [
                {
                    "subject_ref": "responsibility:alpha",
                    "predicate": "attention.state",
                    "value": "SOL_REQUIRED",
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
            "reason_codes": ["STEWARD_DEGRADED"],
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
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.signature",
        "sb_secret_ZmQ4Yx2Kp1Rt",
        "a3f19c8e5d7b402168fa9c3e5d7b8021a3f19c8e5d7b4021",
        "pQ7vNz2XmKdR8sLbWjY4tHcAeGf6UiOp",
        "token=hunter2xy",
        "secret=not-for-model",
        "postgres://user:password@private-db.example/main",
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


@pytest.mark.parametrize(
    "private_value",
    [
        "https://chatgpt.com/c/private-conversation",
        "/Users/operator/private/browser-profile.json",
        "chairman@example.com",
        "provider:codex",
        "account:chairman",
        "host:Mac-Studio.local",
        "native_session:session-123",
        "browser_profile:Chairman",
        "channel:C123/thread:1700000000.000000",
        "coordinates:120,300",
        "action:send target:production",
    ],
)
def test_private_locator_or_identity_shaped_fact_values_are_refused(private_value):
    envelope = _run(
        SecretaryGroundingGateway(
            FakeSteward(StewardGrounding(state="FACTS", facts=(_fact(value=private_value),)))
        ).call("get_attention", {})
    )
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "RESPONSE_REFUSED"
    assert private_value not in json.dumps(envelope)


@pytest.mark.parametrize(
    "private_source_ref",
    [
        "https://linear.app/private/issue/MAS-199",
        "/Users/operator/private/runtime.json",
        "provider:codex",
        "THREAD:1700000000.000000",
    ],
)
def test_private_or_unreviewed_source_references_are_refused(private_source_ref):
    fact = GroundingFact(
        subject_ref="responsibility:alpha",
        predicate="attention.state",
        value="needs_sol",
        freshness="FRESH",
        sources=(_source(source_ref=private_source_ref),),
    )
    envelope = _run(
        SecretaryGroundingGateway(
            FakeSteward(StewardGrounding(state="FACTS", facts=(fact,)))
        ).call("get_attention", {})
    )
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "RESPONSE_REFUSED"


@pytest.mark.parametrize(
    "wrapped_credential",
    [
        "SAFE-ghp_abcdefghijklmnopqrstuvwxyz123456",
        "SAFE-eyJabcdefghijklmnopqrstuvwxyz123456",
        "SAFE-sb_secret_ZmQ4Yx2Kp1Rt",
        "SAFE-xoxb-abcdefghijklmnopqrstuvwxyz123456",
        "SAFE-sk-abcdefghijklmnopqrstuvwxyz123456",
        "SAFE-AKIAIOSFODNN7EXAMPLE",
    ],
)
def test_canonical_source_ref_rejects_delimiter_wrapped_credentials(
    wrapped_credential,
):
    fact = GroundingFact(
        subject_ref="responsibility:alpha",
        predicate="attention.state",
        value="SOL_REQUIRED",
        freshness="FRESH",
        sources=(_source(source_ref="DEC:" + wrapped_credential),),
    )
    envelope = _run(
        SecretaryGroundingGateway(
            FakeSteward(StewardGrounding(state="FACTS", facts=(fact,)))
        ).call("get_attention", {})
    )
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "RESPONSE_REFUSED"


@pytest.mark.parametrize(
    "private_predicate",
    [
        "provider.account",
        "runtime.host",
        "native_session.id",
        "browser_profile.name",
        "channel.thread",
        "action.target",
        "credential.token",
    ],
)
def test_identity_locator_and_secret_predicates_are_not_public_projection_fields(
    private_predicate,
):
    fact = GroundingFact(
        subject_ref="responsibility:alpha",
        predicate=private_predicate,
        value="opaque",
        freshness="FRESH",
        sources=(_source(),),
    )
    envelope = _run(
        SecretaryGroundingGateway(
            FakeSteward(StewardGrounding(state="FACTS", facts=(fact,)))
        ).call("get_attention", {})
    )
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "RESPONSE_REFUSED"


@pytest.mark.parametrize(
    ("predicate", "private_value"),
    [
        ("runtime.identity", "Codex Account 4"),
        ("runtime.realm", "Mac Studio Personal Pro 02"),
        ("surface.binding", "Private Conversation c-12345"),
        ("surface.id", "1700000000.000000"),
        ("surface.id", 1_700_000_000_000_000),
        ("responsibility.owner", "Chairman Chris"),
    ],
)
def test_semantically_private_predicate_value_pairs_are_unrepresentable(
    predicate, private_value
):
    fact = GroundingFact(
        subject_ref="responsibility:alpha",
        predicate=predicate,
        value=private_value,
        freshness="FRESH",
        sources=(_source(),),
    )
    envelope = _run(
        SecretaryGroundingGateway(
            FakeSteward(StewardGrounding(state="FACTS", facts=(fact,)))
        ).call("get_attention", {})
    )
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "RESPONSE_REFUSED"


@pytest.mark.parametrize(
    "canonical_source_ref",
    [
        "DEC:CHAIRMAN-CONTROL-ROOM-P0-ARCHITECTURE-ACCEPTED",
        "DSC:ASD-MODEL-VISIBLE-SETTINGS-CAN-EXPOSE-LIVE-CREDENTIALS",
        "WS:" + "A" * 64,
    ],
)
def test_long_canonical_source_references_remain_source_attributable(
    canonical_source_ref
):
    fact = GroundingFact(
        subject_ref="responsibility:alpha",
        predicate="attention.state",
        value="SOL_REQUIRED",
        freshness="FRESH",
        sources=(_source(source_ref=canonical_source_ref),),
    )
    envelope = _run(
        SecretaryGroundingGateway(
            FakeSteward(
                StewardGrounding(
                    state="DEGRADED",
                    facts=(fact,),
                    reason_codes=("STEWARD_DEGRADED",),
                )
            )
        ).call("get_attention", {})
    )
    assert envelope["ok"] is True
    assert envelope["data"]["facts"][0]["sources"][0]["source_ref"] == canonical_source_ref


def test_oversize_steward_output_is_refused():
    sources = tuple(
        GroundingSource(
            owner="agent_os",
            source_ref="DEC:" + "A" * 223,
            observed_at="2026-08-29T05:00:00Z",
        )
        for _ in range(8)
    )
    facts = tuple(
        GroundingFact(
            subject_ref=f"responsibility:r{index}",
            predicate="attention.state",
            value="SOL_REQUIRED",
            freshness="FRESH",
            sources=sources,
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
        StewardGrounding(state="FACTS", facts=(_fact(freshness="STALE"),)),
        StewardGrounding(state="FACTS", facts=(_fact(freshness="UNKNOWN"),)),
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


def test_unhashable_malformed_steward_reason_codes_fail_closed():
    malformed = StewardGrounding(
        state="UNKNOWN",
        reason_codes=(["SENSITIVE_INTERNAL_VALUE"],),  # type: ignore[arg-type]
    )
    envelope = _run(
        SecretaryGroundingGateway(FakeSteward(malformed)).call("get_attention", {})
    )
    assert envelope["ok"] is False
    assert envelope["error"] == {
        "code": "RESPONSE_REFUSED",
        "message": "RESPONSE_REFUSED",
    }


class ExplodingMapping(Mapping):
    def __iter__(self) -> Iterator[str]:
        raise RuntimeError("sensitive backend path /tmp/private")

    def __len__(self) -> int:
        return 1

    def __getitem__(self, key):
        raise KeyError(key)


def test_malformed_runtime_inputs_return_fixed_invalid_request_without_steward_call():
    steward = FakeSteward(StewardGrounding(state="FACTS", facts=(_fact(),)))
    gateway = SecretaryGroundingGateway(steward)
    cyclic: list[object] = []
    cyclic.append(cyclic)

    for tool_name, arguments in (
        ([], {}),
        ("get_attention", ExplodingMapping()),
        ("get_attention", {"extra": cyclic}),
    ):
        envelope = _run(gateway.call(tool_name, arguments))  # type: ignore[arg-type]
        assert envelope["ok"] is False
        assert envelope["tool"] in {"get_attention", "unknown"}
        assert envelope["error"] == {
            "code": "INVALID_REQUEST",
            "message": "INVALID_REQUEST",
        }
    assert steward.calls == []
