"""Static no-side-effect and no-widening fences for GS-1A."""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
from integrations.mastermind_secretary_mcp.adapter import SecretaryGroundingGateway
from integrations.mastermind_secretary_mcp.schemas import (
    PUBLIC_FACT_CONTRACTS,
    TOOL_SCHEMA_DIGEST,
    TOOL_SPECS,
    GatewayError,
)
from integrations.mastermind_secretary_mcp.schemas import (
    error_envelope,
    result_envelope,
    validate_result_data,
)
from integrations.mastermind_secretary_mcp.server import (
    STATIC_CAPABILITIES,
    SecretaryGroundingContractServer,
    build_tools,
)

PACKAGE = Path(__file__).parents[1] / "integrations" / "mastermind_secretary_mcp"
FORBIDDEN_IMPORT_ROOTS = {
    "aiohttp",
    "control_plane",
    "github",
    "httpx",
    "integrations.slack_agent_dialogue",
    "linear",
    "mcp",
    "openclaw",
    "requests",
    "socket",
    "sqlite3",
    "subprocess",
    "urllib",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_sdk_free_static_tool_rows_are_exact_and_read_only():
    tools = build_tools()
    assert [row["name"] for row in tools] == [spec.name for spec in TOOL_SPECS]
    assert len(tools) == 6
    assert all(row["annotations"]["readOnlyHint"] is True for row in tools)
    assert all(row["annotations"]["destructiveHint"] is False for row in tools)
    assert all(row["inputSchema"]["additionalProperties"] is False for row in tools)
    assert all(row["outputSchema"]["additionalProperties"] is False for row in tools)
    assert STATIC_CAPABILITIES == {
        "tools": True,
        "resources": False,
        "prompts": False,
        "roots": False,
        "sampling": False,
        "elicitation": False,
        "dynamic_registration": False,
    }
    assert len(TOOL_SCHEMA_DIGEST) == 64
    observed = {"tools": {row["name"]: row for row in tools}}
    assert observed_mcp_tool_schema_digest(observed) == TOOL_SCHEMA_DIGEST


def _attention_facts(source: dict, subject: str = "responsibility:alpha") -> list[dict]:
    """A complete get_attention bundle under the frozen required field set."""

    def row(predicate, value):
        return {
            "subject_ref": subject,
            "predicate": predicate,
            "value": value,
            "freshness": "FRESH",
            "sources": [dict(source)],
        }

    return [
        row("attention.ref", "EVENT:alpha"),
        row("attention.reason", "The exact head awaits review."),
        row("attention.requested_action", "Review the exact head."),
        row("attention.state", "SOL_REQUIRED"),
    ]


def test_advertised_output_schema_matches_runtime_state_and_error_law():
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(TOOL_SPECS[2].output_schema)
    source = {"owner": "agent_os", "source_ref": "WS:SAFE", "observed_at": None}
    fresh_fact = {
        "subject_ref": "responsibility:alpha",
        "predicate": "attention.state",
        "value": "SOL_REQUIRED",
        "freshness": "FRESH",
        "sources": [source],
    }
    stale_fact = {**fresh_fact, "freshness": "STALE"}
    valid_data = (
        {"state": "FACTS", "facts": _attention_facts(source), "reason_codes": []},
        {"state": "UNKNOWN", "facts": [], "reason_codes": ["NO_SOURCE"]},
        {
            "state": "DEGRADED",
            "facts": [stale_fact],
            "reason_codes": ["STALE_SOURCE"],
        },
        {"state": "REFUSED", "facts": [], "reason_codes": ["POLICY_REFUSAL"]},
    )
    for data in valid_data:
        validator.validate(result_envelope("get_attention", data=data))
    validator.validate(error_envelope("get_attention", "INVALID_REQUEST"))

    contradictory = error_envelope("get_attention", "INVALID_REQUEST")
    contradictory["ok"] = True
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(contradictory)

    mismatched_error = error_envelope("get_attention", "INVALID_REQUEST")
    mismatched_error["error"]["message"] = "INTERNAL_ERROR"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(mismatched_error)

    successful_error = result_envelope("get_attention", data=valid_data[0])
    successful_error["ok"] = False
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(successful_error)

    malformed_state = copy.deepcopy(successful_error)
    malformed_state["ok"] = True
    malformed_state["data"] = {
        "state": "REFUSED",
        "facts": [fresh_fact],
        "reason_codes": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(malformed_state)

    stale_facts_state = result_envelope("get_attention", data=valid_data[0])
    stale_facts_state["data"]["facts"][0]["freshness"] = "STALE"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(stale_facts_state)


def test_advertised_schema_and_runtime_share_one_closed_public_fact_language():
    jsonschema = pytest.importorskip("jsonschema")
    output_schema = TOOL_SPECS[2].output_schema
    validator = jsonschema.Draft202012Validator(output_schema)
    fact_schema = output_schema["properties"]["data"]["oneOf"][1]["properties"][
        "facts"
    ]["items"]
    expected_predicates = set(PUBLIC_FACT_CONTRACTS)
    assert {
        branch["properties"]["predicate"]["const"]
        for branch in fact_schema["allOf"][0]["oneOf"]
    } == expected_predicates

    source = {"owner": "agent_os", "source_ref": "WS:SAFE", "observed_at": None}
    hostile_facts = (
        {
            "subject_ref": "responsibility:alpha",
            "predicate": "runtime.host",
            "value": "Mac Studio",
            "freshness": "FRESH",
            "sources": [source],
        },
        {
            "subject_ref": "responsibility:alpha",
            "predicate": "runtime.state",
            "value": "provider:codex",
            "freshness": "FRESH",
            "sources": [source],
        },
        {
            "subject_ref": "responsibility:alpha",
            "predicate": "surface.id",
            "value": 1_700_000_000_000_000,
            "freshness": "FRESH",
            "sources": [source],
        },
    )
    for fact in hostile_facts:
        data = {"state": "FACTS", "facts": [fact], "reason_codes": []}
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(
                {
                    "schema": "mastermind.secretary_grounding_mcp_result.v1",
                    "tool": "get_attention",
                    "ok": True,
                    "server_version": "1.0.0",
                    "data": data,
                    "error": None,
                }
            )
        with pytest.raises(GatewayError, match="RESPONSE_REFUSED"):
            validate_result_data(data)


@pytest.mark.parametrize("suffix_length", [32, 40, 64, 145])
def test_advertised_and_runtime_input_contract_accept_same_opaque_refs(suffix_length):
    jsonschema = pytest.importorskip("jsonschema")
    schema = TOOL_SPECS[1].input_schema
    responsibility_ref = "responsibility:" + "a" * suffix_length
    jsonschema.Draft202012Validator(schema).validate(
        {"responsibility_ref": responsibility_ref}
    )


@pytest.mark.parametrize(
    "wrapped_credential",
    [
        "safe-ghp_abcdefghijklmnopqrstuvwxyz123456",
        "safe-sb_secret_ZmQ4Yx2Kp1Rt",
        "safe-xoxb-abcdefghijklmnopqrstuvwxyz123456",
        "safe-sk-abcdefghijklmnopqrstuvwxyz123456",
    ],
)
def test_advertised_and_runtime_input_contract_reject_wrapped_credentials(
    wrapped_credential,
):
    jsonschema = pytest.importorskip("jsonschema")
    arguments = {"responsibility_ref": "responsibility:" + wrapped_credential}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(TOOL_SPECS[1].input_schema).validate(arguments)


@pytest.mark.parametrize(
    "source_ref",
    [
        "DEC:CHAIRMAN-CONTROL-ROOM-P0-ARCHITECTURE-ACCEPTED",
        "DSC:ASD-MODEL-VISIBLE-SETTINGS-CAN-EXPOSE-LIVE-CREDENTIALS",
        "WS:" + "A" * 64,
    ],
)
def test_advertised_and_runtime_output_contract_accept_same_canonical_sources(source_ref):
    jsonschema = pytest.importorskip("jsonschema")
    data = {
        "state": "FACTS",
        "facts": _attention_facts(
            {"owner": "agent_os", "source_ref": source_ref, "observed_at": None}
        ),
        "reason_codes": [],
    }
    normalized = validate_result_data(data)
    envelope = result_envelope("get_attention", data=normalized)
    jsonschema.Draft202012Validator(TOOL_SPECS[2].output_schema).validate(envelope)


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
def test_advertised_output_contract_rejects_wrapped_source_credentials(
    wrapped_credential,
):
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(TOOL_SPECS[2].output_schema)

    def envelope_for(source_ref):
        return {
            "schema": "mastermind.secretary_grounding_mcp_result.v1",
            "tool": "get_attention",
            "ok": True,
            "server_version": "1.0.0",
            "data": {
                "state": "FACTS",
                "facts": _attention_facts(
                    {"owner": "agent_os", "source_ref": source_ref, "observed_at": None}
                ),
                "reason_codes": [],
            },
            "error": None,
        }

    # Control: the same complete bundle with a safe source_ref must validate, so
    # the refusal below is attributable to the credential fence and not to the
    # per-tool required-predicate constraints.
    validator.validate(envelope_for("DEC:TOTALLY-SAFE-REF"))
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(envelope_for("DEC:" + wrapped_credential))


def test_static_contract_server_exposes_only_list_and_call():
    public = {
        name
        for name in dir(SecretaryGroundingContractServer)
        if not name.startswith("_")
    }
    assert public == {"call_tool", "list_tools"}
    assert SecretaryGroundingContractServer.__annotations__ == {}
    assert SecretaryGroundingContractServer.__doc__


def test_production_package_has_no_owner_transport_sdk_or_side_effect_imports():
    imports = set().union(*(_imports(path) for path in PACKAGE.glob("*.py")))
    for imported in imports:
        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORT_ROOTS
        ), imported

    rendered = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(PACKAGE.glob("*.py"))
    )
    forbidden_fragments = (
        "FakeSteward",
        "open(",
        ".read_text(",
        ".write_text(",
        "list_resources(",
        "list_prompts(",
        "list_roots(",
        "create_job",
        "requeue_job",
        "send_message",
        "computer_control",
        "shell(command",
        "dynamic_tool",
    )
    for fragment in forbidden_fragments:
        assert fragment not in rendered


def test_test_fake_is_not_reachable_from_production_package():
    assert not any("fake" in path.name.lower() for path in PACKAGE.glob("*.py"))
    assert not any(
        imported == "tests" or imported.startswith("tests.")
        for path in PACKAGE.glob("*.py")
        for imported in _imports(path)
    )
    assert SecretaryGroundingGateway.__module__.startswith(
        "integrations.mastermind_secretary_mcp"
    )


# GS-1A R3 producer-parity RED: native identity and provenance are related but
# distinct, and selection may not borrow authority from a different receipt.


def _producer_source(owner: str, source_ref: str):
    return {
        "owner": owner,
        "source_ref": source_ref,
        "observed_at": "2026-09-01T10:00:00Z",
    }


def _producer_fact(
    predicate: str,
    value,
    *,
    owner: str,
    source_ref: str,
    subject: str = "responsibility:alpha",
):
    return {
        "subject_ref": subject,
        "predicate": predicate,
        "value": value,
        "freshness": "FRESH",
        "sources": [_producer_source(owner, source_ref)],
    }


def _producer_data(facts: list[dict]):
    return {"state": "FACTS", "facts": facts, "reason_codes": []}


def test_producer_native_runtime_identity_and_provenance_are_distinct():
    from integrations.mastermind_secretary_mcp import schemas as contract_schemas

    executive_receipt = "executive-runtime:ATT-aabbccddeeff00112233445566778899"
    binding_receipt = "runtime-binding:ATT-aabbccddeeff00112233445566778899"
    facts = [
        _producer_fact(
            "runtime.job_ref",
            "JOB-001",
            owner="executive_os",
            source_ref=executive_receipt,
        ),
        _producer_fact(
            "runtime.attempt_ref",
            "ATT-aabbccddeeff00112233445566778899",
            owner="executive_os",
            source_ref=executive_receipt,
        ),
        _producer_fact(
            "runtime.worker_ref",
            "worker-sol-2",
            owner="executive_os",
            source_ref=executive_receipt,
        ),
        _producer_fact(
            "runtime.binding_ref",
            "bind-ocr6-sol-0001",
            owner="runtime_binding",
            source_ref=binding_receipt,
        ),
        _producer_fact(
            "runtime.state",
            "RUNNING",
            owner="executive_os",
            source_ref=executive_receipt,
        ),
        _producer_fact(
            "runtime.effect_state",
            "none",
            owner="executive_os",
            source_ref=executive_receipt,
        ),
        _producer_fact(
            "runtime.continuation",
            "ACKNOWLEDGED",
            owner="runtime_binding",
            source_ref=binding_receipt,
        ),
        _producer_fact(
            "runtime.capacity_state",
            "available",
            owner="capacity",
            source_ref="CAPACITY:realm-a",
        ),
    ]

    envelope = contract_schemas.result_envelope(
        "get_current_runtime", responsibility_ref="responsibility:alpha", data=_producer_data(facts)
    )

    assert [row["value"] for row in envelope["data"]["facts"][:4]] == [
        "JOB-001",
        "ATT-aabbccddeeff00112233445566778899",
        "worker-sol-2",
        "bind-ocr6-sol-0001",
    ]
    assert envelope["data"]["facts"][0]["sources"][0]["source_ref"] == executive_receipt


def test_producer_native_attention_owner_and_vocabulary_are_preserved():
    from integrations.mastermind_secretary_mcp import schemas as contract_schemas

    attention_ref = "eia-aabbccddeeff00112233445566778899"
    receipt = f"executive-inbox:{attention_ref}"
    facts = [
        _producer_fact(
            "attention.ref",
            attention_ref,
            owner="executive_inbox",
            source_ref=receipt,
        ),
        _producer_fact(
            "attention.target_seat",
            "ceo",
            owner="executive_inbox",
            source_ref=receipt,
        ),
        _producer_fact(
            "attention.kind",
            "review_required",
            owner="executive_inbox",
            source_ref=receipt,
        ),
        _producer_fact(
            "attention.reason",
            "Exact head requires Sol review.",
            owner="executive_inbox",
            source_ref=receipt,
        ),
        _producer_fact(
            "attention.requested_action",
            "Review the exact release head.",
            owner="executive_inbox",
            source_ref=receipt,
        ),
        _producer_fact(
            "attention.state",
            "SOL_REQUIRED",
            owner="executive_inbox",
            source_ref=receipt,
        ),
    ]

    assert contract_schemas.result_envelope(
        "get_attention", data=_producer_data(facts)
    )["ok"] is True


def test_producer_native_surface_identity_is_not_its_provenance_receipt():
    from integrations.mastermind_secretary_mcp import schemas as contract_schemas

    surface_ref = "11111111-1111-4111-8111-111111111111"
    receipt = f"surface-binding:{surface_ref}"
    facts = [
        _producer_fact(
            "surface.ref", surface_ref, owner="surface_bindings", source_ref=receipt
        ),
        _producer_fact(
            "surface.locator_kind",
            "chatgpt_managed_env",
            owner="surface_bindings",
            source_ref=receipt,
        ),
        _producer_fact(
            "surface.review_state",
            "approved",
            owner="surface_bindings",
            source_ref=receipt,
        ),
        _producer_fact(
            "surface.health",
            "responsive",
            owner="surface_bindings",
            source_ref=receipt,
        ),
    ]

    envelope = contract_schemas.result_envelope(
        "resolve_surface", responsibility_ref="responsibility:alpha", data=_producer_data(facts)
    )
    assert envelope["data"]["facts"][0]["value"] == surface_ref
    assert envelope["data"]["facts"][0]["sources"][0]["source_ref"] == receipt


def test_selected_surface_cannot_borrow_review_from_another_receipt():
    from integrations.mastermind_secretary_mcp import schemas as contract_schemas

    surface_ref = "11111111-1111-4111-8111-111111111111"
    receipt = f"surface-binding:{surface_ref}"
    facts = [
        _producer_fact(
            "surface.ref", surface_ref, owner="surface_bindings", source_ref=receipt
        ),
        _producer_fact(
            "surface.locator_kind",
            "chatgpt_managed_env",
            owner="surface_bindings",
            source_ref=receipt,
        ),
        _producer_fact(
            "surface.review_state",
            "approved",
            owner="surface_bindings",
            source_ref="surface-binding:22222222-2222-4222-8222-222222222222",
        ),
        _producer_fact(
            "surface.health",
            "responsive",
            owner="surface_bindings",
            source_ref=receipt,
        ),
    ]

    with pytest.raises(GatewayError, match="RESPONSE_REFUSED"):
        contract_schemas.result_envelope(
            "resolve_surface", responsibility_ref="responsibility:alpha", data=_producer_data(facts)
        )


def test_selected_runtime_refuses_its_own_effect_unknown_fact():
    from integrations.mastermind_secretary_mcp import schemas as contract_schemas

    receipt = "executive-runtime:ATT-aabbccddeeff00112233445566778899"
    facts = [
        _producer_fact(
            "runtime.job_ref", "JOB-001", owner="executive_os", source_ref=receipt
        ),
        _producer_fact(
            "runtime.effect_state",
            "effect_unknown",
            owner="executive_os",
            source_ref=receipt,
        ),
    ]

    with pytest.raises(GatewayError, match="RESPONSE_REFUSED"):
        contract_schemas.result_envelope(
            "get_current_runtime", responsibility_ref="responsibility:alpha", data=_producer_data(facts)
        )


def test_schema_footprint_and_serialization_are_deterministically_bounded():
    from integrations.mastermind_secretary_mcp import schemas as contract_schemas

    assert len(
        contract_schemas.canonical_json(contract_schemas.tool_schema_snapshot())
    ) < 176_000
    with pytest.raises(GatewayError, match="INVALID_REQUEST"):
        contract_schemas.canonical_json({"unordered": {"a", "b"}})


def test_invalid_calendar_timestamp_is_refused():
    from integrations.mastermind_secretary_mcp import schemas as contract_schemas

    malformed = _producer_fact(
        "attention.state",
        "SOL_REQUIRED",
        owner="agent_os",
        source_ref="WS:SAFE",
    )
    malformed["sources"][0]["observed_at"] = "2026-02-30T10:00:00Z"

    with pytest.raises(GatewayError, match="RESPONSE_REFUSED"):
        contract_schemas.result_envelope(
            "get_attention", data=_producer_data([malformed])
        )
