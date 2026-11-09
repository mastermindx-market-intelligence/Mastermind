"""Focused boundary tests for the bounded pure root-factory helpers."""

from __future__ import annotations

import json
from typing import Any

import pytest

from control_plane.executive_release_factory import (
    FactoryInputError,
    file_document,
    observed_at,
    registration,
    registry,
)

HEX_A = "a" * 64
HEX_B = "b" * 64
UUID_OK = "3f2504e0-4f89-41d3-9a0c-0305e70d1a8b"
KEY = "mastermind-rel-01"
BASE = {
    "schema": "mastermind.executive_release_owner_registration/v1",
    "owner_installation_id": UUID_OK,
    "target_ref": HEX_A,
    "key_id": KEY,
    "trust_generation": 1,
    "app_generation": 2,
    "registration_generation": 3,
    "enabled": True,
}
STAMP = "2026-09-29T00:00:00Z"
EPOCH = 1_790_640_000


def wire(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8") + b"\n"


def reg(**changes: Any) -> dict[str, Any]:
    return {**BASE, **changes}


def doc(**changes: Any) -> dict[str, Any]:
    rows = [{"transition_digest": HEX_A, "staging_generation": 1, "state": "STAGED"}]
    return {
        "schema": "mastermind.executive_release_owner_staged_registry/v1",
        "registration_generation": 3,
        "registry_generation": 4,
        "transitions": rows,
        **changes,
    }


def rejected(callable_: Any, *args: Any, **kwargs: Any) -> FactoryInputError:
    with pytest.raises(FactoryInputError) as caught:
        callable_(*args, **kwargs)
    return caught.value


# --- file_document -------------------------------------------------------


def test_file_document_accepts_canonical_object() -> None:
    assert file_document(wire({"schema": "x"})) == {"schema": "x"}


def test_file_document_accepts_exact_16kib_with_one_lf() -> None:
    raw = wire({"pad": "p" * (16383 - 10)})
    assert len(raw) == 16384
    assert file_document(raw)["pad"].startswith("ppp")


def test_file_document_rejects_over_16kib() -> None:
    rejected(file_document, wire({"pad": "p" * (16384 - 8)}) + b"\n")


@pytest.mark.parametrize("raw", [b"", b"\n", b"{}", b"{}\n\n", b"{}\n\x0a", b" \n"])
def test_file_document_rejects_line_framing(raw: bytes) -> None:
    rejected(file_document, raw)


@pytest.mark.parametrize(
    "raw",
    [b' {"a":1}\n', b'{"a":1} \n', b'{"a":1}\r\n', b'{\n"a":1\n}\n', b"\xef\xbb\xbf{}\n"],
)
def test_file_document_rejects_whitespace_and_bom(raw: bytes) -> None:
    rejected(file_document, raw)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}\n',
        b'{"b":1,"a":2}\n',
        b'{"a":1.5}\n',
        b'{"a":1e3}\n',
        b'{"a":NaN}\n',
        b'{"a":"\\u00e9"}\n',
        b'[[[[[[[[[1]]]]]]]]]\n',
        b'{"a":12345678901234567890}\n',
        b"[1]\n",
        b"1\n",
        b'"text"\n',
    ],
)
def test_file_document_rejects_typed_payloads(raw: bytes) -> None:
    rejected(file_document, raw)


@pytest.mark.parametrize("raw", ["{}\n", bytearray(b"{}\n"), None, 1])
def test_file_document_rejects_non_bytes(raw: Any) -> None:
    rejected(file_document, raw)


def test_file_document_detached_and_inputs_preserved() -> None:
    source = {"nested": [1, {"deep": True}]}
    raw = wire(source)
    parsed = file_document(raw)
    assert type(parsed) is dict
    parsed["nested"].append("mutated")
    assert source == {"nested": [1, {"deep": True}]}
    assert file_document(raw) == {"nested": [1, {"deep": True}]}
    assert file_document(raw) is not parsed


def test_factory_input_error_never_echoes_rejected_data() -> None:
    error = rejected(file_document, b'{"secret_owner_token":"LEAK-ME","a":1.5}\n')
    assert "LEAK-ME" not in str(error)
    assert error.field == "raw"


# --- registration --------------------------------------------------------


def test_registration_accepts_disabled_and_detaches() -> None:
    value = reg(enabled=False, key_id="a")
    result = registration(value)
    assert result == value
    assert result is not value
    result["key_id"] = "changed"
    assert value["key_id"] == "a"


@pytest.mark.parametrize(
    "value",
    [
        reg(),
        reg(enabled=False),
        reg(key_id="A" + "-" * 159),
        reg(trust_generation=2**63 - 1),
        reg(target_ref="0" * 64),
    ],
)
def test_registration_accepts_boundaries(value: dict[str, Any]) -> None:
    assert registration(value) == value


@pytest.mark.parametrize("key", list(BASE))
def test_registration_rejects_missing_key(key: str) -> None:
    rejected(registration, {name: item for name, item in BASE.items() if name != key})


def test_registration_rejects_extra_and_type() -> None:
    rejected(registration, reg(extra=1))
    rejected(registration, [1])
    rejected(registration, None)


def test_registration_rejects_bad_schema() -> None:
    rejected(registration, reg(schema="mastermind.executive_release_owner_registration/v2"))


@pytest.mark.parametrize(
    "owner",
    [
        "00000000-0000-0000-0000-000000000000",
        UUID_OK.upper(),
        UUID_OK.replace("-", ""),
        "{" + UUID_OK + "}",
        "urn:uuid:" + UUID_OK,
        UUID_OK[:-1] + "g",
        1,
        None,
    ],
)
def test_registration_rejects_noncanonical_uuid(owner: Any) -> None:
    rejected(registration, reg(owner_installation_id=owner))


@pytest.mark.parametrize(
    "target", [HEX_A.upper(), HEX_A[:-1], HEX_A + "0", "z" * 64, "", 1])
def test_registration_rejects_target_ref(target: Any) -> None:
    rejected(registration, reg(target_ref=target))


@pytest.mark.parametrize(
    "key_id", ["", "-" + KEY, "_x", "x" * 161, "x/y", "x y", "ünï", 7])
def test_registration_rejects_key_id(key_id: Any) -> None:
    rejected(registration, reg(key_id=key_id))


@pytest.mark.parametrize("field", ["trust_generation", "app_generation", "registration_generation"])
@pytest.mark.parametrize("bad", [True, False, 0, -1, 2**63, 1.0, "1", None])
def test_registration_rejects_generations(field: str, bad: Any) -> None:
    rejected(registration, reg(**{field: bad}))


@pytest.mark.parametrize("bad", ["true", 1, 0, None, [], 1.0])
def test_registration_rejects_non_bool_enabled(bad: Any) -> None:
    rejected(registration, reg(enabled=bad))


# --- registry ------------------------------------------------------------


def test_registry_accepts_empty_transitions_and_detaches_deeply() -> None:
    value = doc(transitions=[])
    result = registry(value, 3)
    assert result == value
    assert result["transitions"] is not value["transitions"]


def test_registry_accepts_max_transitions_and_bound() -> None:
    rows = [
        {"transition_digest": format(index, "064x"), "staging_generation": 1, "state": "STAGED"}
        for index in range(32)
    ]
    value = doc(transitions=rows)
    assert registry(value, 3)["transitions"] == rows


def test_registry_returns_deep_detached_rows() -> None:
    row = {"transition_digest": HEX_A, "staging_generation": 1, "state": "STAGED"}
    value = doc(transitions=[row])
    result = registry(value, 3)
    result["transitions"][0]["state"] = "MUTATED"
    result["registry_generation"] = 99
    assert row == {"transition_digest": HEX_A, "staging_generation": 1, "state": "STAGED"}
    assert value["registry_generation"] == 4


def test_registry_requires_bound_generation_argument() -> None:
    rejected(registry, doc(), 4)
    rejected(registry, doc(registration_generation=True), 1)
    rejected(registry, doc(registration_generation=1), True)
    rejected(registry, doc(registration_generation=1), 0)
    assert registry(doc(registration_generation=1, registry_generation=1), 1) == doc(
        registration_generation=1, registry_generation=1
    )


@pytest.mark.parametrize(
    "value",
    [
        doc(schema="mastermind.executive_release_owner_staged_registry/v2"),
        doc(extra=1),
        {name: item for name, item in doc().items() if name != "transitions"},
        doc(transitions={"a": 1}),
        doc(transitions=[{"transition_digest": HEX_A, "staging_generation": 1}]),
        doc(transitions=[{"transition_digest": HEX_A, "staging_generation": 1, "state": "STAGED", "extra": 1}]),
        doc(registry_generation=True),
        doc(registry_generation=0),
        doc(registry_generation=2**63),
    ],
)
def test_registry_rejects_structure(value: Any) -> None:
    rejected(registry, value, 3)


@pytest.mark.parametrize(
    "digests",
    [
        [HEX_B, HEX_A],
        [HEX_A, HEX_A],
        [HEX_A.upper()],
        ["a" * 63],
        ["g" * 64],
        [1],
    ],
)
def test_registry_rejects_digest_order_or_format(digests: list[Any]) -> None:
    rows = [
        {"transition_digest": item, "staging_generation": 1, "state": "STAGED"}
        for item in digests
    ]
    rejected(registry, doc(transitions=rows), 3)


def test_registry_rejects_over_max_transitions() -> None:
    rows = [
        {"transition_digest": format(index, "064x"), "staging_generation": 1, "state": "STAGED"}
        for index in range(33)
    ]
    rejected(registry, doc(transitions=rows), 3)


@pytest.mark.parametrize("state", ["staged", "STAGING", "APPLIED", "", True, 1])
def test_registry_rejects_unknown_state(state: Any) -> None:
    rejected(
        registry,
        doc(transitions=[{"transition_digest": HEX_A, "staging_generation": 1, "state": state}]),
        3,
    )


@pytest.mark.parametrize("bad", [True, 0, -1, 2**63, 1.5, "1"])
def test_registry_rejects_staging_generation(bad: Any) -> None:
    rejected(
        registry,
        doc(transitions=[{"transition_digest": HEX_A, "staging_generation": bad, "state": "STAGED"}]),
        3,
    )


# --- observed_at ---------------------------------------------------------


def test_observed_at_returns_integer_seconds() -> None:
    assert observed_at(STAMP, EPOCH, admission=False) == EPOCH
    assert observed_at("1970-01-01T00:00:00Z", 0, admission=True) == 0


@pytest.mark.parametrize("age", [0, 1, 86399])
def test_observed_at_admission_accepts_age_below_day(age: int) -> None:
    assert observed_at(STAMP, EPOCH + age, admission=True) == EPOCH


@pytest.mark.parametrize("age", [86400, 86401, 172800])
def test_observed_at_admission_refuses_age_at_or_over_day(age: int) -> None:
    rejected(observed_at, STAMP, EPOCH + age, admission=True)


@pytest.mark.parametrize("age", [86400, 172800, 31_536_000])
def test_observed_at_nonadmission_has_no_age_ceiling(age: int) -> None:
    assert observed_at(STAMP, EPOCH + age, admission=False) == EPOCH


def test_observed_at_refuses_future() -> None:
    rejected(observed_at, STAMP, EPOCH - 1, admission=True)
    rejected(observed_at, STAMP, EPOCH - 1, admission=False)


@pytest.mark.parametrize(
    "value",
    [
        "2026-09-29t00:00:00Z",
        "2026-09-29T00:00:00z",
        "2026-09-29 00:00:00Z",
        "2026-09-29T00:00:00",
        "2026-09-29T00:00:00+00:00",
        "2026-09-29T00:00:00.000Z",
        "2026-9-29T00:00:00Z",
        "2026-09-29T24:00:00Z",
        "2026-09-29T00:00:60Z",
        "2026-02-30T00:00:00Z",
        "2025-02-29T00:00:00Z",
        "2026-13-01T00:00:00Z",
        "0000-01-01T00:00:00Z",
        "٢٠٢٦-٠٩-٢٩T٠٠:٠٠:٠٠Z",
        " 2026-09-29T00:00:00Z",
        "",
        1_793_059_200,
        None,
    ],
)
def test_observed_at_rejects_noncanonical_timestamp(value: Any) -> None:
    rejected(observed_at, value, EPOCH + 10, admission=True)


@pytest.mark.parametrize("now", [-1, True, 1.0, "10", None])
def test_observed_at_rejects_now(now: Any) -> None:
    rejected(observed_at, STAMP, now, admission=False)


@pytest.mark.parametrize("admission", ["", 1, 0, None, True and 1.0])
def test_observed_at_rejects_non_bool_admission(admission: Any) -> None:
    rejected(observed_at, STAMP, EPOCH, admission=admission)


def test_observed_at_admission_is_keyword_only() -> None:
    with pytest.raises(TypeError):
        observed_at(STAMP, EPOCH, True)


def test_observed_at_performs_no_clock_lookup() -> None:
    assert observed_at(STAMP, EPOCH + 5, admission=True) == EPOCH
