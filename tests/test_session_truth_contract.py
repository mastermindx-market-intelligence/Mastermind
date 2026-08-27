from __future__ import annotations

import copy
import importlib
import re

import pytest


MODULE = "control_plane.session_truth_contract"


def _contract():
    try:
        return importlib.import_module(MODULE)
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing Session Truth contract module: {exc}")


def _minimal_input(module):
    return {
        "schema": module.INPUT_SCHEMA,
        "scope": {
            "workstreams": ["WS:CHAIRMAN-CONTROL-ROOM"],
            "linear": [],
            "repositories": ["mastermindx-market-intelligence/Mastermind"],
            "operation_key": None,
            "requires_executive": False,
        },
        "skillpack": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "sha": "a" * 40,
            "schema": "mastermind.sol_skillpack.v1",
            "version": "1.0.0",
            "minimum_bootstrap_major": 1,
            "available": True,
        },
        "agentos": {
            "available": True,
            "source_sha": "b" * 40,
            "state": {"schema": "agent_os_state.v1", "workstreams": []},
            "contexts": [],
            "warnings": [],
        },
        "github": {
            "schema": "mastermind.github_observation.v1",
            "available": True,
            "repositories": [],
        },
        "linear": {
            "schema": "mastermind.linear_observation.v1",
            "available": True,
            "issues": [],
        },
        "slack": {
            "schema": "mastermind.slack_observation.v1",
            "available": True,
            "channels": [],
            "messages": [],
        },
        "executive": {
            "schema": "mastermind.executive_observation.v1",
            "available": False,
            "reason": "C1_NOT_PROVEN",
        },
        "identities": {
            "schema": "mastermind.identity_observation.v1",
            "available": True,
            "bindings": [],
        },
    }


def test_contract_constants_are_exact():
    module = _contract()
    assert module.INPUT_SCHEMA == "mastermind.session_truth_inputs.v1"
    assert module.RECEIPT_SCHEMA == "mastermind.session_truth_receipt.v1"
    assert module.ADMISSION_MODES == {
        "GROUNDING_COMPLETE",
        "GROUNDING_PARTIAL",
        "DIALOGUE_ONLY",
        "MODIFICATION_REFUSED",
    }
    assert module.FINDING_SEVERITIES == {"FATAL", "BLOCKING", "WARNING", "INFO"}


def test_canonical_json_and_hash_are_order_independent():
    module = _contract()
    left = {"b": 2, "a": {"d": 4, "c": 3}}
    right = {"a": {"c": 3, "d": 4}, "b": 2}
    assert module.canonical_json(left) == '{"a":{"c":3,"d":4},"b":2}'
    assert module.canonical_json(left) == module.canonical_json(right)
    digest = module.semantic_hash(left)
    assert digest == module.semantic_hash(right)
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    assert digest != module.semantic_hash({"a": {"c": 3, "d": 5}, "b": 2})


def test_validate_returns_defensive_copy_without_mutating_input():
    module = _contract()
    doc = _minimal_input(module)
    before = copy.deepcopy(doc)
    validated = module.validate_input_document(doc)
    assert validated == before
    assert validated is not doc
    assert doc == before
    validated["scope"]["workstreams"].append("WS:OTHER")
    assert doc == before


def test_validate_rejects_unknown_top_level_key():
    module = _contract()
    doc = _minimal_input(module)
    doc["shadow_truth_store"] = {}
    with pytest.raises(module.SessionTruthContractError, match="unknown top-level key"):
        module.validate_input_document(doc)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda d: d["scope"]["workstreams"].__setitem__(0, "CHAIRMAN-CONTROL-ROOM"), "WS:"),
        (lambda d: d["scope"]["linear"].append("MAS-X"), "MAS-"),
        (lambda d: d["scope"]["repositories"].__setitem__(0, "not-a-repo"), "owner/name"),
        (lambda d: d["skillpack"].__setitem__("sha", "short"), "40-hex"),
        (lambda d: d["agentos"].__setitem__("source_sha", "not-a-sha"), "40-hex"),
        (lambda d: d["scope"].__setitem__("requires_executive", "false"), "requires_executive"),
        (lambda d: d["github"].pop("available"), "github.available"),
        (
            lambda d: d.__setitem__(
                "executive",
                {"schema": "mastermind.executive_observation.v1", "available": False},
            ),
            "reason",
        ),
    ],
)
def test_invalid_shapes_fail_closed(mutator, message):
    module = _contract()
    doc = _minimal_input(module)
    mutator(doc)
    with pytest.raises(module.SessionTruthContractError, match=message):
        module.validate_input_document(doc)


def test_unavailable_sources_require_explicit_reason():
    module = _contract()
    doc = _minimal_input(module)
    doc["linear"] = {
        "schema": "mastermind.linear_observation.v1",
        "available": False,
        "reason": "LINEAR_READ_UNAVAILABLE",
    }
    validated = module.validate_input_document(doc)
    assert validated["linear"]["available"] is False
    assert validated["linear"]["reason"] == "LINEAR_READ_UNAVAILABLE"
