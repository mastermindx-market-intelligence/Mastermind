from __future__ import annotations

import copy
import importlib
import json
import re
import sys

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
    assert module.MAX_JSON_BYTES == 16 * 1024 * 1024
    assert module.MAX_JSON_DEPTH == 128
    assert module.MAX_JSON_NODES == 250_000


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


# --- Owner-record identity amendment falsifiers (2026-08-28, Sol) -----------------
#
# §5: canonical JSON refuses non-finite numbers, non-string keys and non-JSON values
# through the typed R1 error path; no coercion to null/string/zero is permitted.
# §2.1: a present owner digest must be an exact sha256:<64 lowercase hex> value.


@pytest.mark.parametrize(
    "bad_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        {"x": float("nan")},
        [1.0, float("inf")],
        {"nested": {"deep": [float("-inf")]}},
    ],
)
def test_canonical_json_rejects_non_finite_numbers(bad_value):
    module = _contract()
    with pytest.raises(module.SessionTruthContractError):
        module.canonical_json(bad_value)
    with pytest.raises(module.SessionTruthContractError):
        module.semantic_hash(bad_value)


@pytest.mark.parametrize(
    "bad_value",
    [
        {1: "x"},
        {"a": {2: "y"}},
        {"a": [{None: "z"}]},
        {("t",): "w"},
    ],
)
def test_canonical_json_rejects_non_string_keys_without_coercion(bad_value):
    module = _contract()
    with pytest.raises(module.SessionTruthContractError):
        module.canonical_json(bad_value)


@pytest.mark.parametrize(
    "bad_value",
    [
        {"a": {1, 2}},
        {"a": b"bytes"},
        {"a": [object()]},
    ],
)
def test_canonical_json_rejects_non_json_values_with_typed_error(bad_value):
    module = _contract()
    with pytest.raises(module.SessionTruthContractError):
        module.canonical_json(bad_value)


@pytest.mark.parametrize(
    "bad_digest",
    ["sha256:" + "G" * 64, "sha256:" + "9" * 63, "sha1:" + "9" * 64, 9, False],
)
def test_validate_rejects_malformed_agentos_state_digest(bad_digest):
    module = _contract()
    doc = _minimal_input(module)
    doc["agentos"]["state"]["source_records_digest"] = bad_digest
    with pytest.raises(module.SessionTruthContractError):
        module.validate_input_document(doc)


def test_validate_rejects_malformed_agentos_context_digest():
    module = _contract()
    doc = _minimal_input(module)
    doc["agentos"]["contexts"] = [
        {"schema": "context_bundle.v1", "source_records_digest": "not-a-digest"}
    ]
    with pytest.raises(module.SessionTruthContractError):
        module.validate_input_document(doc)


def test_validate_accepts_wellformed_agentos_digests():
    module = _contract()
    doc = _minimal_input(module)
    doc["agentos"]["state"]["source_records_digest"] = "sha256:" + "3" * 64
    doc["agentos"]["contexts"] = [
        {"schema": "context_bundle.v1", "source_records_digest": "sha256:" + "4" * 64}
    ]
    validated = module.validate_input_document(doc)
    assert validated["agentos"]["state"]["source_records_digest"] == "sha256:" + "3" * 64


def test_validate_rejects_non_string_keys_inside_agentos_interior():
    """Invalid Agent OS interior keys fail typed at the contract, not at json.dumps."""

    module = _contract()
    doc = _minimal_input(module)
    doc["agentos"]["state"]["workstreams"] = [{1: "not-a-string-key"}]
    with pytest.raises(module.SessionTruthContractError):
        module.validate_input_document(doc)


def _nested_list(wrappers):
    value = 0
    for _ in range(wrappers):
        value = [value]
    return value


def test_json_tree_depth_boundary_is_inclusive_and_iterative():
    module = _contract()
    # The scalar is one node below each wrapper: 127 wrappers reach depth 128.
    assert module.canonical_json(_nested_list(module.MAX_JSON_DEPTH - 1))
    with pytest.raises(module.SessionTruthContractError, match="maximum JSON depth"):
        module.canonical_json(_nested_list(module.MAX_JSON_DEPTH))


def test_json_tree_node_boundary_is_inclusive():
    module = _contract()
    # The list container is one node and each scalar element is one node.
    module.validate_json_tree([0] * (module.MAX_JSON_NODES - 1))
    with pytest.raises(module.SessionTruthContractError, match="node count"):
        module.validate_json_tree([0] * module.MAX_JSON_NODES)


def test_json_tree_encoded_byte_accounting_matches_canonical_utf8(monkeypatch):
    module = _contract()
    value = {"é": ["line\n", "astral-😀", 'quote-"', "slash-\\"]}
    expected = len(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    )
    monkeypatch.setattr(module, "MAX_JSON_BYTES", expected)
    module.validate_json_tree(value)
    monkeypatch.setattr(module, "MAX_JSON_BYTES", expected - 1)
    with pytest.raises(module.SessionTruthContractError, match="encoded byte"):
        module.validate_json_tree(value)


@pytest.mark.parametrize("entrypoint", ["validate", "canonical", "receipt"])
@pytest.mark.parametrize("hostile", ["key", "huge_key", "string", "float", "dict", "list"])
def test_json_boundary_never_invokes_rejected_object_hooks(entrypoint, hostile):
    module = _contract()

    def fail(*_args, **_kwargs):
        raise RuntimeError("hostile object hook was invoked")

    class BadKey:
        __repr__ = fail

    class BadString(str):
        __len__ = fail

    class BadFloat(float):
        __repr__ = fail

    class BadDict(dict):
        items = fail

    class BadList(list):
        __iter__ = fail

    values = {
        "key": {BadKey(): None},
        "huge_key": {10**5000: None},
        "string": BadString("value"),
        "float": BadFloat(1.0),
        "dict": BadDict(value=1),
        "list": BadList([1]),
    }
    value = values[hostile]
    with pytest.raises(module.SessionTruthContractError):
        if entrypoint == "validate":
            module.validate_json_tree(value)
        elif entrypoint == "canonical":
            module.canonical_json(value)
        else:
            receipt = importlib.import_module("control_plane.session_truth")
            doc = _minimal_input(module)
            doc["agentos"]["state"]["hostile"] = value
            receipt.build_receipt(
                doc, observed_started_at="2026-08-27T05:00:00Z",
                observed_ended_at="2026-08-27T05:00:00Z",
            )


def test_json_tree_string_precheck_and_multibyte_increment_stop_at_small_ceiling(
    monkeypatch,
):
    module = _contract()
    monkeypatch.setattr(module, "MAX_JSON_BYTES", 8)
    with pytest.raises(module.SessionTruthContractError, match="encoded byte"):
        module.validate_json_tree("x" * 7)  # lower bound is nine bytes with quotes

    monkeypatch.setattr(module, "MAX_JSON_BYTES", 4)
    module.validate_json_tree("é")
    monkeypatch.setattr(module, "MAX_JSON_BYTES", 3)
    with pytest.raises(module.SessionTruthContractError, match="encoded byte"):
        module.validate_json_tree("é")


def test_bounded_json_integer_parser_and_in_memory_boundary_are_explicit():
    module = _contract()
    accepted = "9" * module.MAX_JSON_INTEGER_DIGITS
    assert module.parse_bounded_json_int(accepted) == int(accepted)
    with pytest.raises(ValueError, match="decimal digits"):
        module.parse_bounded_json_int("9" * (module.MAX_JSON_INTEGER_DIGITS + 1))

    previous = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(0)
        huge = int("9" * 5000)
        with pytest.raises(module.SessionTruthContractError, match="integer size"):
            module.validate_json_tree({"huge": huge})
    finally:
        sys.set_int_max_str_digits(previous)


def test_json_tree_rejects_cycles_before_copy_or_hash():
    module = _contract()
    cycle = []
    cycle.append(cycle)
    with pytest.raises(module.SessionTruthContractError, match="container cycle"):
        module.canonical_json(cycle)


def test_json_tree_counts_wide_aliased_values_without_sibling_enqueuing(monkeypatch):
    module = _contract()
    monkeypatch.setattr(module, "MAX_JSON_NODES", 8)
    shared = [0, 1, 2, 3, 4, 5]
    with pytest.raises(module.SessionTruthContractError, match="node count"):
        module.validate_json_tree([shared, shared])


@pytest.mark.parametrize("value", ["\ud800", {"\udfff": "x"}, {"x": "\ud800"}])
def test_json_tree_rejects_lone_surrogates_as_invalid_utf8(value):
    module = _contract()
    with pytest.raises(module.SessionTruthContractError, match="valid UTF-8"):
        module.canonical_json(value)
    with pytest.raises(module.SessionTruthContractError, match="valid UTF-8"):
        module.semantic_hash(value)


def test_agentos_interior_depth_fails_through_contract_error():
    module = _contract()
    doc = _minimal_input(module)
    doc["agentos"]["state"]["workstreams"] = _nested_list(module.MAX_JSON_DEPTH)
    with pytest.raises(module.SessionTruthContractError, match="maximum JSON depth"):
        module.validate_input_document(doc)


def test_build_receipt_rejects_one_agentos_string_over_aggregate_byte_ceiling(monkeypatch):
    module = _contract()
    receipt = importlib.import_module("control_plane.session_truth")
    doc = _minimal_input(module)
    doc["agentos"]["state"]["oversized"] = "x" * (module.MAX_JSON_BYTES + 1)

    def forbid_unbounded_dump(*_args, **_kwargs):
        raise AssertionError("validator attempted an unbounded JSON serialization")

    monkeypatch.setattr(module.json, "dumps", forbid_unbounded_dump)
    with pytest.raises(module.SessionTruthContractError, match="encoded byte"):
        receipt.build_receipt(
            doc,
            observed_started_at="2026-08-27T05:00:00Z",
            observed_ended_at="2026-08-27T05:00:01Z",
        )


def test_build_receipt_rejects_aggregate_of_individually_bounded_sources():
    module = _contract()
    receipt = importlib.import_module("control_plane.session_truth")
    doc = _minimal_input(module)
    chunk = "x" * (module.MAX_JSON_BYTES // 6)
    for source in ("agentos", "github", "linear", "slack", "executive", "identities"):
        doc[source] = {"available": False, "reason": chunk}

    for source in ("agentos", "github", "linear", "slack", "executive", "identities"):
        module.validate_json_tree(doc[source], source)
    with pytest.raises(module.SessionTruthContractError, match="encoded byte"):
        receipt.build_receipt(
            doc,
            observed_started_at="2026-08-27T05:00:00Z",
            observed_ended_at="2026-08-27T05:00:01Z",
        )
