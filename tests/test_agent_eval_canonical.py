"""EVAL-R0 Task 1: structured defects and strict canonical JSON.

RED-before-GREEN: every test here asserts either a specific successful
canonicalization/digest, or a specific structured ``ContractError`` defect —
never a bare exception or a silently coerced value.
"""
from __future__ import annotations

import unicodedata

import pytest

from scripts.agent_eval.canonical import (
    add_document_digest,
    canonical_json_bytes,
    digest_document,
    digest_value,
    parse_decimal_string,
    parse_digest_string,
    parse_prefixed_uuid4,
    parse_source_qualified_ref,
    parse_utc_z,
    require_canonical_json_tree,
    verify_document_digest,
)
from scripts.agent_eval.errors import ContractDefect, ContractError


# ---------------------------------------------------------------------------
# ContractDefect / ContractError ordering
# ---------------------------------------------------------------------------


def test_contract_defect_is_frozen_and_sortable() -> None:
    a = ContractDefect("$.b", "CODE_A", "msg")
    b = ContractDefect("$.a", "CODE_B", "msg")
    assert sorted([a, b]) == [b, a]
    with pytest.raises(AttributeError):
        a.path = "$.changed"  # type: ignore[misc]


def test_contract_error_orders_defects_deterministically() -> None:
    defects = [
        ContractDefect("$.z", "CODE_Z", "z"),
        ContractDefect("$.a", "CODE_A", "a"),
        ContractDefect("$.a", "CODE_A", "a"),  # exact duplicate collapses
        ContractDefect("$.m", "CODE_M", "m"),
    ]
    err = ContractError(defects)
    assert [d.path for d in err.defects] == ["$.a", "$.m", "$.z"]
    assert len(err.defects) == 3  # duplicate removed


def test_contract_error_ordering_independent_of_discovery_order() -> None:
    forward = ContractError(
        [ContractDefect("$.a", "C1", "x"), ContractDefect("$.b", "C2", "y")]
    )
    backward = ContractError(
        [ContractDefect("$.b", "C2", "y"), ContractDefect("$.a", "C1", "x")]
    )
    assert forward.defects == backward.defects


# ---------------------------------------------------------------------------
# require_canonical_json_tree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        -1,
        2**63 - 1,
        -(2**63),
        "hello",
        [],
        [1, "two", None],
        {"a": 1, "b": {"c": [True, None]}},
    ],
)
def test_accepted_canonical_primitives(value) -> None:
    require_canonical_json_tree(value)  # must not raise


def test_rejects_float() -> None:
    with pytest.raises(ContractError) as excinfo:
        require_canonical_json_tree(1.5)
    assert excinfo.value.defects[0].code == "FLOAT_NOT_ALLOWED"


def test_rejects_nan_and_infinity_as_float() -> None:
    with pytest.raises(ContractError) as excinfo:
        require_canonical_json_tree(float("nan"))
    assert excinfo.value.defects[0].code == "FLOAT_NOT_ALLOWED"
    with pytest.raises(ContractError) as excinfo:
        require_canonical_json_tree(float("inf"))
    assert excinfo.value.defects[0].code == "FLOAT_NOT_ALLOWED"


def test_rejects_tuple() -> None:
    with pytest.raises(ContractError) as excinfo:
        require_canonical_json_tree((1, 2))
    assert excinfo.value.defects[0].code == "TUPLE_NOT_ALLOWED"


def test_rejects_non_string_key() -> None:
    with pytest.raises(ContractError) as excinfo:
        require_canonical_json_tree({1: "a"})
    assert excinfo.value.defects[0].code == "NON_STRING_KEY"


def test_rejects_bool_is_not_treated_as_int_out_of_range() -> None:
    # bool is a bool, not silently treated as int 0/1 out-of-range checks etc.
    require_canonical_json_tree(True)
    require_canonical_json_tree(False)


def test_rejects_int_out_of_signed_64_bit_range() -> None:
    with pytest.raises(ContractError) as excinfo:
        require_canonical_json_tree(2**63)
    assert excinfo.value.defects[0].code == "INT_OUT_OF_RANGE"
    with pytest.raises(ContractError) as excinfo:
        require_canonical_json_tree(-(2**63) - 1)
    assert excinfo.value.defects[0].code == "INT_OUT_OF_RANGE"


def test_rejects_non_nfc_string() -> None:
    decomposed = unicodedata.normalize("NFD", "café")
    assert decomposed != "café"
    with pytest.raises(ContractError) as excinfo:
        require_canonical_json_tree(decomposed)
    assert excinfo.value.defects[0].code == "STRING_NOT_NFC"


def test_rejects_non_nfc_dict_key() -> None:
    decomposed_key = unicodedata.normalize("NFD", "café")
    with pytest.raises(ContractError) as excinfo:
        require_canonical_json_tree({decomposed_key: "value"})
    assert excinfo.value.defects[0].code == "KEY_NOT_NFC"


def test_nested_defects_carry_json_path() -> None:
    with pytest.raises(ContractError) as excinfo:
        require_canonical_json_tree({"a": [1, {"b": 1.5}]})
    assert excinfo.value.defects[0].path == "$.a[1].b"


def test_defect_ordering_is_deterministic_regardless_of_dict_iteration() -> None:
    value_one = {"z": 1.1, "a": 2.2}
    value_two = {"a": 2.2, "z": 1.1}
    err_one = None
    err_two = None
    try:
        require_canonical_json_tree(value_one)
    except ContractError as exc:
        err_one = exc
    try:
        require_canonical_json_tree(value_two)
    except ContractError as exc:
        err_two = exc
    assert err_one is not None and err_two is not None
    assert err_one.defects == err_two.defects


# ---------------------------------------------------------------------------
# canonical_json_bytes / digest_value
# ---------------------------------------------------------------------------


def test_canonical_json_bytes_is_sorted_and_compact() -> None:
    value = {"b": 1, "a": [1, 2, 3], "c": None}
    raw = canonical_json_bytes(value)
    assert raw == b'{"a":[1,2,3],"b":1,"c":null}'


def test_canonical_json_bytes_is_key_order_independent() -> None:
    assert canonical_json_bytes({"a": 1, "b": 2}) == canonical_json_bytes({"b": 2, "a": 1})


def test_canonical_json_bytes_rejects_noncanonical_value() -> None:
    with pytest.raises(ContractError):
        canonical_json_bytes({"a": 1.5})


def test_digest_value_is_deterministic_sha256() -> None:
    digest = digest_value({"a": 1})
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64
    assert digest == digest_value({"a": 1})


def test_digest_value_changes_with_content() -> None:
    assert digest_value({"a": 1}) != digest_value({"a": 2})


# ---------------------------------------------------------------------------
# digest_document / add_document_digest / verify_document_digest
# ---------------------------------------------------------------------------


def test_digest_document_excludes_its_own_digest_field() -> None:
    doc_without = {"a": 1, "b": 2}
    doc_with_any_digest = {"a": 1, "b": 2, "the_digest": "sha256:" + "0" * 64}
    assert digest_document(doc_without, "the_digest") == digest_document(doc_with_any_digest, "the_digest")


def test_add_document_digest_round_trips_with_verify() -> None:
    doc = add_document_digest({"a": 1, "b": 2}, "my_digest")
    assert doc["my_digest"] == digest_document(doc, "my_digest")
    verify_document_digest(doc, "my_digest")  # must not raise


def test_verify_document_digest_rejects_missing_digest_field() -> None:
    with pytest.raises(ContractError) as excinfo:
        verify_document_digest({"a": 1}, "my_digest")
    assert excinfo.value.defects[0].code == "DIGEST_MISSING"


def test_verify_document_digest_rejects_mutated_document() -> None:
    doc = add_document_digest({"a": 1}, "my_digest")
    mutated = dict(doc)
    mutated["a"] = 2
    with pytest.raises(ContractError) as excinfo:
        verify_document_digest(mutated, "my_digest")
    assert excinfo.value.defects[0].code == "DIGEST_MISMATCH"


def test_verify_document_digest_rejects_tampered_digest_field() -> None:
    doc = add_document_digest({"a": 1}, "my_digest")
    tampered = dict(doc)
    tampered["my_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ContractError) as excinfo:
        verify_document_digest(tampered, "my_digest")
    assert excinfo.value.defects[0].code == "DIGEST_MISMATCH"


# ---------------------------------------------------------------------------
# parse_utc_z
# ---------------------------------------------------------------------------


def test_parse_utc_z_accepts_whole_second_utc() -> None:
    parsed = parse_utc_z("2026-09-01T12:00:00Z")
    assert parsed.year == 2026 and parsed.hour == 12


@pytest.mark.parametrize(
    "value",
    [
        "2026-09-01T12:00:00.000Z",  # fractional seconds forbidden
        "2026-09-01T12:00:00+00:00",  # offset form forbidden
        "2026-09-01 12:00:00Z",  # missing T
        "not-a-timestamp",
        12345,
        None,
    ],
)
def test_parse_utc_z_rejects_non_whole_second_or_non_utc(value) -> None:
    with pytest.raises(ContractError):
        parse_utc_z(value)


def test_parse_utc_z_rejects_impossible_calendar_date() -> None:
    with pytest.raises(ContractError) as excinfo:
        parse_utc_z("2026-02-30T00:00:00Z")
    assert excinfo.value.defects[0].code == "TIMESTAMP_INVALID"


# ---------------------------------------------------------------------------
# parse_prefixed_uuid4
# ---------------------------------------------------------------------------


def test_parse_prefixed_uuid4_accepts_canonical_lowercase() -> None:
    value = "run:5b1f6a2e-7c3d-4e1a-9b2c-1234567890ab"
    parsed = parse_prefixed_uuid4(value, "run")
    assert str(parsed) == "5b1f6a2e-7c3d-4e1a-9b2c-1234567890ab"


def test_parse_prefixed_uuid4_rejects_wrong_prefix() -> None:
    with pytest.raises(ContractError) as excinfo:
        parse_prefixed_uuid4("configuration:5b1f6a2e-7c3d-4e1a-9b2c-1234567890ab", "run")
    assert excinfo.value.defects[0].code == "ID_PREFIX_MISMATCH"


def test_parse_prefixed_uuid4_rejects_uppercase() -> None:
    with pytest.raises(ContractError) as excinfo:
        parse_prefixed_uuid4("run:5B1F6A2E-7C3D-4E1A-9B2C-1234567890AB", "run")
    assert excinfo.value.defects[0].code == "ID_NOT_LOWERCASE"


def test_parse_prefixed_uuid4_rejects_non_uuid4_version() -> None:
    # a well-formed uuid1-shaped value (version nibble != 4)
    with pytest.raises(ContractError) as excinfo:
        parse_prefixed_uuid4("run:5b1f6a2e-7c3d-1e1a-9b2c-1234567890ab", "run")
    assert excinfo.value.defects[0].code == "ID_NOT_UUID4"


def test_parse_prefixed_uuid4_rejects_malformed_uuid_body() -> None:
    with pytest.raises(ContractError) as excinfo:
        parse_prefixed_uuid4("run:not-a-uuid", "run")
    assert excinfo.value.defects[0].code == "ID_NOT_UUID"


# ---------------------------------------------------------------------------
# parse_source_qualified_ref
# ---------------------------------------------------------------------------


def test_parse_source_qualified_ref_accepts_git_form() -> None:
    ref = "git:mastermindx-market-intelligence/Mastermind@" + "a" * 40
    assert parse_source_qualified_ref(ref) == ref


@pytest.mark.parametrize(
    "value",
    [
        "a" * 40,  # bare commit hash, no repository identity
        "mastermindx-market-intelligence/Mastermind@" + "a" * 40,  # missing scheme
        "git:mastermindx-market-intelligence/Mastermind@" + "a" * 39,  # short sha
        "git:mastermindx-market-intelligence/Mastermind@" + "A" * 40,  # uppercase sha
        "git:onlyrepo@" + "a" * 40,  # missing owner
        123,
    ],
)
def test_parse_source_qualified_ref_rejects_bad_shapes(value) -> None:
    with pytest.raises(ContractError):
        parse_source_qualified_ref(value)


# ---------------------------------------------------------------------------
# parse_digest_string / parse_decimal_string
# ---------------------------------------------------------------------------


def test_parse_digest_string_accepts_canonical_sha256() -> None:
    value = "sha256:" + "a" * 64
    assert parse_digest_string(value) == value


@pytest.mark.parametrize("value", ["sha256:" + "a" * 63, "sha1:" + "a" * 64, "sha256:" + "A" * 64, 5])
def test_parse_digest_string_rejects_bad_shapes(value) -> None:
    with pytest.raises(ContractError):
        parse_digest_string(value)


@pytest.mark.parametrize("value", ["0", "1", "1.5", "-1.5", "1234567890"])
def test_parse_decimal_string_accepts_canonical_decimals(value) -> None:
    assert parse_decimal_string(value) == value


@pytest.mark.parametrize("value", ["01", "1.", ".5", "1e10", "+1", "1,000", 1.5, None])
def test_parse_decimal_string_rejects_noncanonical_decimals(value) -> None:
    with pytest.raises(ContractError):
        parse_decimal_string(value)
