import hashlib
import json
import pytest
from common import native_authorization_identity_contract as wire


def test_domain_framing_is_comparable_only_for_the_same_verified_identity():
    values = ("a" * 64, "b" * 64, "c" * 64)
    frame = {"schema": wire.SUBJECT_SCHEMA, "issuer_digest": values[0],
             "subject_digest": values[1], "client_ref": values[2]}
    expected = hashlib.sha256(json.dumps(frame, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    digest = wire.comparable_account_digest(*values)
    assert digest == expected
    for index in range(3):
        changed = list(values); changed[index] = "d" * 64
        assert wire.comparable_account_digest(*changed) != digest
    a = {"schema": wire.SCHEMA, "resource": "ACQUISITION", "account_digest": digest, "expires_at_ms": 5000}
    c = {**a, "resource": "CONTENT"}
    assert wire.validate_body(a, "ACQUISITION") == a
    assert wire.validate_body(a, "ACQUISITION") is not a
    assert wire.validate_body(c, "CONTENT")["account_digest"] == digest
    with pytest.raises(ValueError): wire.validate_body(c, "ACQUISITION")


@pytest.mark.parametrize("value", [None, [], {}, {"schema": wire.SCHEMA}])
def test_closed_body_rejects_nonrecords_and_missing_fields(value):
    with pytest.raises(ValueError, match="IDENTITY_INVALID"): wire.validate_body(value, "CONTENT")


@pytest.mark.parametrize("field,value", [("schema", "other"), ("resource", "EXECUTIVE"),
    ("account_digest", "A" * 64), ("account_digest", "a" * 64 + "\n"),
    ("account_digest", "a" * 63), ("account_digest", "中" * 64),
    ("expires_at_ms", True), ("expires_at_ms", 1.0), ("expires_at_ms", 0),
    ("expires_at_ms", 8_640_000_000_000_001), ("extra", "not-authority")])
def test_exact_body_negatives(field, value):
    body = {"schema": wire.SCHEMA, "resource": "CONTENT", "account_digest": "a" * 64, "expires_at_ms": 5000}
    body[field] = value
    with pytest.raises(ValueError, match="IDENTITY_INVALID"): wire.validate_body(body, "CONTENT")
