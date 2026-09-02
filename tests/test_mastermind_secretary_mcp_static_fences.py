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
    canonical_json,
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


def test_advertised_output_schema_matches_runtime_state_and_error_law():
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(TOOL_SPECS[2].output_schema)
    fresh_facts = _required_facts("get_attention")
    fresh_fact = fresh_facts[0]
    stale_fact = {**fresh_fact, "freshness": "STALE"}
    valid_data = (
        {"state": "FACTS", "facts": fresh_facts, "reason_codes": []},
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
    facts = _required_facts("get_attention")
    for fact in facts:
        fact["sources"] = [
            {"owner": "agent_os", "source_ref": source_ref, "observed_at": None}
        ]
    data = {
        "state": "FACTS",
        "facts": facts,
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
    envelope = {
        "schema": "mastermind.secretary_grounding_mcp_result.v1",
        "tool": "get_attention",
        "ok": True,
        "server_version": "1.0.0",
        "data": {
            "state": "FACTS",
            "facts": [
                {
                    "subject_ref": "responsibility:alpha",
                    "predicate": "attention.state",
                    "value": "SOL_REQUIRED",
                    "freshness": "FRESH",
                    "sources": [
                        {
                            "owner": "agent_os",
                            "source_ref": "DEC:" + wrapped_credential,
                            "observed_at": None,
                        }
                    ],
                }
            ],
            "reason_codes": [],
        },
        "error": None,
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(TOOL_SPECS[2].output_schema).validate(envelope)


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


_REQUIRED_FACT_ROWS = {
    "list_responsibilities": (
        ("responsibility.identity", "WS:ALPHA", "agent_os", "WS:ALPHA"),
        ("responsibility.title", "Alpha responsibility", "agent_os", "WS:ALPHA"),
        ("responsibility.state", "ACTIVE", "agent_os", "WS:ALPHA"),
        (
            "responsibility.next_action",
            "Review the current exact gate.",
            "agent_os",
            "WS:ALPHA",
        ),
    ),
    "get_responsibility": (
        ("responsibility.identity", "WS:ALPHA", "agent_os", "WS:ALPHA"),
        ("responsibility.title", "Alpha responsibility", "agent_os", "WS:ALPHA"),
        (
            "responsibility.objective",
            "Preserve truthful public grounding.",
            "agent_os",
            "WS:ALPHA",
        ),
        (
            "responsibility.next_action",
            "Review the current exact gate.",
            "agent_os",
            "WS:ALPHA",
        ),
        ("responsibility.state", "ACTIVE", "agent_os", "WS:ALPHA"),
    ),
    "get_attention": (
        (
            "attention.ref",
            "attention-alpha",
            "executive_inbox",
            "executive-inbox:attention-alpha",
        ),
        (
            "attention.reason",
            "Exact head requires review.",
            "executive_inbox",
            "executive-inbox:attention-alpha",
        ),
        (
            "attention.requested_action",
            "Review the exact release head.",
            "executive_inbox",
            "executive-inbox:attention-alpha",
        ),
        (
            "attention.state",
            "SOL_REQUIRED",
            "executive_inbox",
            "executive-inbox:attention-alpha",
        ),
    ),
    "get_current_runtime": (
        (
            "runtime.job_ref",
            "JOB-001",
            "executive_os",
            "executive-runtime:ATT-alpha",
        ),
        (
            "runtime.attempt_ref",
            "ATT-alpha",
            "executive_os",
            "executive-runtime:ATT-alpha",
        ),
        (
            "runtime.worker_ref",
            "worker-alpha",
            "executive_os",
            "executive-runtime:ATT-alpha",
        ),
        (
            "runtime.binding_ref",
            "binding-alpha",
            "runtime_binding",
            "runtime-binding:ATT-alpha",
        ),
        (
            "runtime.state",
            "RUNNING",
            "executive_os",
            "executive-runtime:ATT-alpha",
        ),
        (
            "runtime.effect_state",
            "none",
            "executive_os",
            "executive-runtime:ATT-alpha",
        ),
    ),
    "explain_blocker": (
        ("blocker.present", True, "agent_os", "WS:ALPHA"),
        ("blocker.kind", "review_required", "agent_os", "WS:ALPHA"),
        (
            "blocker.explanation",
            "Independent review is pending.",
            "agent_os",
            "WS:ALPHA",
        ),
    ),
    "resolve_surface": (
        (
            "surface.ref",
            "11111111-1111-4111-8111-111111111111",
            "surface_bindings",
            "surface-binding:11111111-1111-4111-8111-111111111111",
        ),
        (
            "surface.locator_kind",
            "chatgpt_managed_env",
            "surface_bindings",
            "surface-binding:11111111-1111-4111-8111-111111111111",
        ),
        (
            "surface.review_state",
            "approved",
            "surface_bindings",
            "surface-binding:11111111-1111-4111-8111-111111111111",
        ),
        (
            "surface.health",
            "responsive",
            "surface_bindings",
            "surface-binding:11111111-1111-4111-8111-111111111111",
        ),
    ),
}


def _required_facts(tool_name: str, *, subject: str = "responsibility:alpha"):
    return [
        _producer_fact(
            predicate,
            value,
            owner=owner,
            source_ref=source_ref,
            subject=subject,
        )
        for predicate, value, owner, source_ref in _REQUIRED_FACT_ROWS[tool_name]
    ]


@pytest.mark.parametrize(
    ("tool_name", "missing_predicate"),
    [
        (tool_name, row[0])
        for tool_name, rows in _REQUIRED_FACT_ROWS.items()
        for row in rows
    ],
)
def test_each_tool_runtime_and_advertised_schema_reject_missing_required_predicate(
    tool_name, missing_predicate
):
    """Deleting any frozen useful predicate must fail at both public boundaries."""

    jsonschema = pytest.importorskip("jsonschema")
    complete_facts = _required_facts(tool_name)
    complete = result_envelope(tool_name, data=_producer_data(complete_facts))
    validator = jsonschema.Draft202012Validator(
        next(spec.output_schema for spec in TOOL_SPECS if spec.name == tool_name)
    )
    validator.validate(complete)

    incomplete_facts = [
        fact for fact in complete_facts if fact["predicate"] != missing_predicate
    ]
    with pytest.raises(GatewayError, match="RESPONSE_REFUSED"):
        result_envelope(tool_name, data=_producer_data(incomplete_facts))

    incomplete = copy.deepcopy(complete)
    incomplete["data"]["facts"] = [
        fact
        for fact in incomplete["data"]["facts"]
        if fact["predicate"] != missing_predicate
    ]
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(incomplete)


@pytest.mark.parametrize(
    ("tool_name", "missing_predicate"),
    [
        (tool_name, row[0])
        for tool_name in ("list_responsibilities", "get_attention")
        for row in _REQUIRED_FACT_ROWS[tool_name]
    ],
)
def test_collection_tools_require_useful_predicates_for_each_returned_subject(
    tool_name, missing_predicate
):
    """One complete neighboring bundle must not lend a missing field to another."""

    alpha = _required_facts(tool_name)
    beta = copy.deepcopy(alpha)
    for fact in beta:
        fact["subject_ref"] = "responsibility:beta"
        if fact["predicate"] == "responsibility.identity":
            fact["value"] = "WS:BETA"
        for source in fact["sources"]:
            if source["owner"] == "agent_os":
                source["source_ref"] = "WS:BETA"
            elif source["owner"] == "executive_inbox":
                source["source_ref"] = "executive-inbox:attention-beta"
        if fact["predicate"] == "attention.ref":
            fact["value"] = "attention-beta"

    alpha = [fact for fact in alpha if fact["predicate"] != missing_predicate]
    with pytest.raises(GatewayError, match="RESPONSE_REFUSED"):
        result_envelope(tool_name, data=_producer_data(alpha + beta))


_ENUM_ALIAS_CASES = (
    (
        "get_attention",
        "attention.target_seat",
        ("ceo", "CEO", "SOL"),
        "CEO",
        "executive_inbox",
        "executive-inbox:attention-alpha",
    ),
    (
        "get_current_runtime",
        "runtime.effect_state",
        ("none", "NONE"),
        "NONE",
        "executive_os",
        "executive-runtime:ATT-alpha",
    ),
    (
        "get_current_runtime",
        "runtime.capacity_state",
        ("available", "AVAILABLE"),
        "AVAILABLE",
        "capacity",
        "CAPACITY:realm-alpha",
    ),
    (
        "resolve_surface",
        "surface.review_state",
        ("approved", "APPROVED"),
        "APPROVED",
        "surface_bindings",
        "surface-binding:11111111-1111-4111-8111-111111111111",
    ),
)


def _facts_with_predicate_value(
    tool_name: str,
    predicate: str,
    value,
    *,
    owner: str,
    source_ref: str,
):
    facts = _required_facts(tool_name)
    for fact in facts:
        if fact["predicate"] == predicate:
            fact["value"] = value
            return facts
    facts.append(
        _producer_fact(
            predicate,
            value,
            owner=owner,
            source_ref=source_ref,
        )
    )
    return facts


@pytest.mark.parametrize(
    ("tool_name", "predicate", "aliases", "canonical", "owner", "source_ref"),
    _ENUM_ALIAS_CASES,
)
def test_admitted_source_aliases_collapse_to_one_canonical_output(
    tool_name, predicate, aliases, canonical, owner, source_ref
):
    rendered = []
    for alias in aliases:
        envelope = result_envelope(
            tool_name,
            data=_producer_data(
                _facts_with_predicate_value(
                    tool_name,
                    predicate,
                    alias,
                    owner=owner,
                    source_ref=source_ref,
                )
            ),
        )
        projected = next(
            fact for fact in envelope["data"]["facts"]
            if fact["predicate"] == predicate
        )
        assert projected["value"] == canonical
        rendered.append(canonical_json(envelope))
    assert len(set(rendered)) == 1


@pytest.mark.parametrize(
    ("tool_name", "predicate", "near_match", "canonical", "owner", "source_ref"),
    (
        (
            "get_attention",
            "attention.target_seat",
            "CeO",
            "CEO",
            "executive_inbox",
            "executive-inbox:attention-alpha",
        ),
        (
            "get_current_runtime",
            "runtime.effect_state",
            "effect-unknown",
            "NONE",
            "executive_os",
            "executive-runtime:ATT-alpha",
        ),
        (
            "get_current_runtime",
            "runtime.capacity_state",
            "Available",
            "AVAILABLE",
            "capacity",
            "CAPACITY:realm-alpha",
        ),
        (
            "resolve_surface",
            "surface.review_state",
            "Approved",
            "APPROVED",
            "surface_bindings",
            "surface-binding:11111111-1111-4111-8111-111111111111",
        ),
    ),
)
def test_unadvertised_enum_near_matches_fail_runtime_and_schema(
    tool_name, predicate, near_match, canonical, owner, source_ref
):
    jsonschema = pytest.importorskip("jsonschema")
    invalid_facts = _facts_with_predicate_value(
        tool_name,
        predicate,
        near_match,
        owner=owner,
        source_ref=source_ref,
    )
    with pytest.raises(GatewayError, match="RESPONSE_REFUSED"):
        result_envelope(tool_name, data=_producer_data(invalid_facts))

    valid = result_envelope(
        tool_name,
        data=_producer_data(
            _facts_with_predicate_value(
                tool_name,
                predicate,
                canonical,
                owner=owner,
                source_ref=source_ref,
            )
        ),
    )
    next(
        fact for fact in valid["data"]["facts"]
        if fact["predicate"] == predicate
    )["value"] = near_match
    validator = jsonschema.Draft202012Validator(
        next(spec.output_schema for spec in TOOL_SPECS if spec.name == tool_name)
    )
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(valid)


def _replace_fact_source_ref(facts: list[dict], predicate: str, source_ref: str):
    fact = next(fact for fact in facts if fact["predicate"] == predicate)
    fact["sources"][0]["source_ref"] = source_ref


def test_selected_executive_runtime_facts_require_one_common_receipt():
    facts = _required_facts("get_current_runtime")
    _replace_fact_source_ref(
        facts,
        "runtime.worker_ref",
        "executive-runtime:ATT-beta",
    )

    with pytest.raises(GatewayError, match="RESPONSE_REFUSED"):
        result_envelope("get_current_runtime", data=_producer_data(facts))


def test_runtime_binding_and_continuation_require_one_common_receipt():
    facts = _required_facts("get_current_runtime")
    facts.append(
        _producer_fact(
            "runtime.continuation",
            "ACKNOWLEDGED",
            owner="runtime_binding",
            source_ref="runtime-binding:ATT-beta",
        )
    )

    with pytest.raises(GatewayError, match="RESPONSE_REFUSED"):
        result_envelope("get_current_runtime", data=_producer_data(facts))


def test_executive_runtime_receipt_attempt_must_match_projected_attempt():
    facts = _required_facts("get_current_runtime")
    for predicate in (
        "runtime.job_ref",
        "runtime.attempt_ref",
        "runtime.worker_ref",
        "runtime.state",
        "runtime.effect_state",
    ):
        _replace_fact_source_ref(
            facts,
            predicate,
            "executive-runtime:ATT-beta",
        )

    with pytest.raises(GatewayError, match="RESPONSE_REFUSED"):
        result_envelope("get_current_runtime", data=_producer_data(facts))


def test_capacity_receipt_is_independent_of_executive_and_binding_receipts():
    facts = _required_facts("get_current_runtime")
    facts.append(
        _producer_fact(
            "runtime.capacity_state",
            "available",
            owner="capacity",
            source_ref="capacity:realm-independent",
        )
    )

    envelope = result_envelope(
        "get_current_runtime",
        data=_producer_data(facts),
    )

    capacity = next(
        fact for fact in envelope["data"]["facts"]
        if fact["predicate"] == "runtime.capacity_state"
    )
    assert capacity["value"] == "AVAILABLE"
    assert capacity["sources"][0]["source_ref"] == "capacity:realm-independent"


@pytest.mark.parametrize(
    ("owner", "valid_source_ref", "invalid_source_ref"),
    (
        ("agent_os", "WS:ALPHA", "ws:ALPHA"),
        ("executive_os", "executive-runtime:ATT-alpha", "MAS:216"),
        ("runtime_binding", "runtime-binding:ATT-alpha", "RUNTIME:ATT-alpha"),
        (
            "executive_inbox",
            "executive-inbox:attention-alpha",
            "EIA:attention-alpha",
        ),
        ("capacity", "CAPACITY:realm-alpha", "Capacity:realm-alpha"),
        ("wake", "WAKE:attention-alpha", "Wake:attention-alpha"),
        ("agent_dialogue", "DIALOGUE:edge-alpha", "Dialogue:edge-alpha"),
        ("surface_binding", "SURFACE:control-room", "Surface:control-room"),
        (
            "surface_bindings",
            "surface-binding:11111111-1111-4111-8111-111111111111",
            "surface-bindings:11111111-1111-4111-8111-111111111111",
        ),
        ("provider_control", "POLICY:reviewed-alpha", "Policy:reviewed-alpha"),
        ("unknown", "UNKNOWN:alpha", "Unknown:alpha"),
    ),
)
def test_advertised_and_runtime_source_ref_grammars_are_bidirectionally_equal(
    owner, valid_source_ref, invalid_source_ref
):
    from integrations.mastermind_secretary_mcp import schemas as contract_schemas

    jsonschema = pytest.importorskip("jsonschema")
    fact_schema = TOOL_SPECS[0].output_schema["properties"]["data"]["oneOf"][1][
        "properties"
    ]["facts"]["items"]
    source_schema = fact_schema["properties"]["sources"]["items"]
    validator = jsonschema.Draft202012Validator(source_schema)
    valid = {
        "owner": owner,
        "source_ref": valid_source_ref,
        "observed_at": "2026-09-01T10:00:00Z",
    }
    invalid = {**valid, "source_ref": invalid_source_ref}

    validator.validate(valid)
    assert contract_schemas._validated_source(valid) == valid

    with pytest.raises(jsonschema.ValidationError):
        validator.validate(invalid)
    with pytest.raises(GatewayError, match="RESPONSE_REFUSED"):
        contract_schemas._validated_source(invalid)


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
        "get_current_runtime", data=_producer_data(facts)
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
        "resolve_surface", data=_producer_data(facts)
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
            "resolve_surface", data=_producer_data(facts)
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
            "get_current_runtime", data=_producer_data(facts)
        )


def test_schema_footprint_and_serialization_are_deterministically_bounded():
    from integrations.mastermind_secretary_mcp import schemas as contract_schemas

    assert len(
        contract_schemas.canonical_json(contract_schemas.tool_schema_snapshot())
    ) < 160_000
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
