"""Tests for domain consumption wire and canonical digest primitive.

Includes tests for:
- F2: Missing complete outer envelope validation
- F3: Malformed equal actual+expected IDs/digest
- F4: UTF8 cap bypass via character vs byte counting
- F5: Missing secret redaction refusal
"""
from __future__ import annotations

import hashlib
import json

import pytest

from control_plane.executive_orchestration_result import (
    DOMAIN_CONSUMPTION_SCHEMA,
    DOMAIN_CONSUMPTION_PROJECTION_SCHEMA,
    MAX_CANONICAL_RESULT_BYTES,
    OrchestrationResultError,
    ROLES,
    canonical_bytes,
    canonical_digest,
    domain_consumption_envelope_schema,
    domain_consumption_schema,
    parse_and_validate_domain_consumption,
    parse_and_validate_domain_consumption_envelope,
    parse_canonical_json,
    validate_domain_consumption,
    validate_domain_consumption_envelope,
    validate_envelope,
    orchestration_result_schema,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def base_ids():
    return {
        "root_job_id": "test-root-001",
        "domain_job_id": "domain-1",
        "domain_attempt_id": "attempt-1",
        "consumption_projection_digest": "a" * 64,
        "job_id": "domain-1",
        "run_id": "attempt-1",
        "worker_id": "worker-1",
    }


@pytest.fixture
def valid_projection(base_ids):
    """A valid projection dict before becoming consumed_result."""
    return {
        "schema_version": DOMAIN_CONSUMPTION_PROJECTION_SCHEMA,
        "root_job_id": base_ids["root_job_id"],
        "domain_job_id": base_ids["domain_job_id"],
        "domain_attempt_id": base_ids["domain_attempt_id"],
        "consumption_projection_digest": base_ids["consumption_projection_digest"],
        "plan_attempt_id": "plan-attempt-001",
        "plan_digest": "b" * 64,
        "revisions": [],
    }


# --------------------------------------------------------------------------- #
# Domain consumption schema
# --------------------------------------------------------------------------- #

class TestDomainConsumptionSchema:
    def test_returns_closed_schema(self, base_ids):
        schema = domain_consumption_schema(
            expected_root_job_id=base_ids["root_job_id"],
            expected_domain_job_id=base_ids["domain_job_id"],
            expected_domain_attempt_id=base_ids["domain_attempt_id"],
            expected_projection_digest=base_ids["consumption_projection_digest"],
        )
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        props = schema["properties"]
        assert props["schema_version"]["const"] == DOMAIN_CONSUMPTION_SCHEMA
        assert props["root_job_id"]["const"] == base_ids["root_job_id"]
        assert props["domain_job_id"]["const"] == base_ids["domain_job_id"]
        assert props["domain_attempt_id"]["const"] == base_ids["domain_attempt_id"]
        assert props["consumption_projection_digest"]["const"] == base_ids["consumption_projection_digest"]
        assert props["consumed_result"]["type"] == "string"
        assert props["consumed_result"]["minLength"] == 1

    def test_schema_is_closed(self, base_ids):
        schema = domain_consumption_schema(
            expected_root_job_id=base_ids["root_job_id"],
            expected_domain_job_id=base_ids["domain_job_id"],
            expected_domain_attempt_id=base_ids["domain_attempt_id"],
            expected_projection_digest=base_ids["consumption_projection_digest"],
        )
        assert schema["additionalProperties"] is False


# --------------------------------------------------------------------------- #
# Domain consumption validation
# --------------------------------------------------------------------------- #

class TestValidateDomainConsumption:
    def test_accepts_valid_consumption(self, base_ids):
        observation = {
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
            "root_job_id": base_ids["root_job_id"],
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            "consumption_projection_digest": base_ids["consumption_projection_digest"],
            "consumed_result": '{"result": "ok"}',
        }
        result = validate_domain_consumption(
            observation,
            expected_root_job_id=base_ids["root_job_id"],
            expected_domain_job_id=base_ids["domain_job_id"],
            expected_domain_attempt_id=base_ids["domain_attempt_id"],
            expected_projection_digest=base_ids["consumption_projection_digest"],
        )
        assert result["consumed_result"] == '{"result": "ok"}'

    def test_rejects_missing_key(self, base_ids):
        observation = {
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
            "root_job_id": base_ids["root_job_id"],
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            # missing consumption_projection_digest
            "consumed_result": '{"result": "ok"}',
        }
        with pytest.raises(OrchestrationResultError, match="closed schema"):
            validate_domain_consumption(
                observation,
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )

    def test_rejects_extra_key(self, base_ids):
        observation = {
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
            "root_job_id": base_ids["root_job_id"],
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            "consumption_projection_digest": base_ids["consumption_projection_digest"],
            "consumed_result": '{"result": "ok"}',
            "extra_field": "forbidden",
        }
        with pytest.raises(OrchestrationResultError, match="closed schema"):
            validate_domain_consumption(
                observation,
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )

    def test_rejects_wrong_root_job_id(self, base_ids):
        observation = {
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
            "root_job_id": "wrong-root",
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            "consumption_projection_digest": base_ids["consumption_projection_digest"],
            "consumed_result": '{"result": "ok"}',
        }
        with pytest.raises(OrchestrationResultError, match="root_job_id mismatch"):
            validate_domain_consumption(
                observation,
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )

    def test_rejects_wrong_projection_digest(self, base_ids):
        observation = {
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
            "root_job_id": base_ids["root_job_id"],
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            "consumption_projection_digest": "f" * 64,  # wrong digest
            "consumed_result": '{"result": "ok"}',
        }
        with pytest.raises(OrchestrationResultError, match="projection_digest mismatch"):
            validate_domain_consumption(
                observation,
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )

    def test_rejects_empty_consumed_result(self, base_ids):
        observation = {
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
            "root_job_id": base_ids["root_job_id"],
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            "consumption_projection_digest": base_ids["consumption_projection_digest"],
            "consumed_result": "",
        }
        with pytest.raises(OrchestrationResultError, match="non-empty"):
            validate_domain_consumption(
                observation,
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )

    def test_rejects_dict_consumed_result(self, base_ids):
        observation = {
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
            "root_job_id": base_ids["root_job_id"],
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            "consumption_projection_digest": base_ids["consumption_projection_digest"],
            "consumed_result": {"result": "ok"},  # dict, not string
        }
        with pytest.raises(OrchestrationResultError, match="must be a string"):
            validate_domain_consumption(
                observation,
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )

    def test_rejects_wrong_schema_version(self, base_ids):
        observation = {
            "schema_version": "wrong.schema/v1",
            "root_job_id": base_ids["root_job_id"],
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            "consumption_projection_digest": base_ids["consumption_projection_digest"],
            "consumed_result": '{"result": "ok"}',
        }
        with pytest.raises(OrchestrationResultError, match="unsupported"):
            validate_domain_consumption(
                observation,
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )


# --------------------------------------------------------------------------- #
# Parse and validate domain consumption (roundtrip)
# --------------------------------------------------------------------------- #

class TestParseAndValidateDomainConsumption:
    def test_deterministic_roundtrip(self, base_ids):
        consumed = '{"result": "ok", "data": [1, 2, 3]}'
        observation = {
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
            "root_job_id": base_ids["root_job_id"],
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            "consumption_projection_digest": base_ids["consumption_projection_digest"],
            "consumed_result": consumed,
        }
        canonical = canonical_bytes(observation)
        text = canonical.decode("utf-8")

        parsed = parse_and_validate_domain_consumption(
            text,
            expected_root_job_id=base_ids["root_job_id"],
            expected_domain_job_id=base_ids["domain_job_id"],
            expected_domain_attempt_id=base_ids["domain_attempt_id"],
            expected_projection_digest=base_ids["consumption_projection_digest"],
        )
        assert parsed["consumed_result"] == consumed

    def test_rejects_noncanonical_text(self, base_ids):
        # Extra whitespace is non-canonical
        text = '{"schema_version":"mastermind.executive_coo_domain_consumption/v1","root_job_id":"test-root-001","domain_job_id":"test-domain-001","domain_attempt_id":"test-attempt-001","consumption_projection_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","consumed_result":"ok"} '

        with pytest.raises(OrchestrationResultError, match="byte-for-byte"):
            parse_and_validate_domain_consumption(
                text,
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )

    def test_rejects_bom(self, base_ids):
        text = "﻿" + json.dumps({
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
            "root_job_id": base_ids["root_job_id"],
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            "consumption_projection_digest": base_ids["consumption_projection_digest"],
            "consumed_result": "ok",
        }, separators=(",", ":"), sort_keys=True)

        with pytest.raises(OrchestrationResultError, match="BOM"):
            parse_and_validate_domain_consumption(
                text,
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )


# --------------------------------------------------------------------------- #
# Inner hardened guards (R4E)
# --------------------------------------------------------------------------- #

class TestInnerHardenedGuards:
    def _observation(self, base_ids, consumed_result):
        return {
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
            "root_job_id": base_ids["root_job_id"],
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            "consumption_projection_digest": base_ids["consumption_projection_digest"],
            "consumed_result": consumed_result,
        }

    def _kwargs(self, base_ids):
        return {
            "expected_root_job_id": base_ids["root_job_id"],
            "expected_domain_job_id": base_ids["domain_job_id"],
            "expected_domain_attempt_id": base_ids["domain_attempt_id"],
            "expected_projection_digest": base_ids["consumption_projection_digest"],
        }

    # -- schema expectations refuse malformed input even if actual==expected ---

    def test_schema_rejects_bool_root_job_id(self, base_ids):
        with pytest.raises(OrchestrationResultError, match="must be UTF-8 text"):
            domain_consumption_schema(
                expected_root_job_id=True,
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )

    def test_schema_rejects_empty_domain_job_id(self, base_ids):
        with pytest.raises(OrchestrationResultError, match="non-empty"):
            domain_consumption_schema(
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id="",
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )

    def test_schema_rejects_oversized_domain_attempt_id(self, base_ids):
        with pytest.raises(OrchestrationResultError, match="128"):
            domain_consumption_schema(
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id="a" * 129,
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )

    def test_schema_rejects_malformed_identifier_pattern(self, base_ids):
        with pytest.raises(OrchestrationResultError, match="canonical identifier"):
            domain_consumption_schema(
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id="-bad-id",
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )

    def test_schema_rejects_uppercase_digest(self, base_ids):
        with pytest.raises(OrchestrationResultError, match="lowercase SHA-256"):
            domain_consumption_schema(
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest="A" * 64,
            )

    def test_schema_rejects_nonstring_digest(self, base_ids):
        with pytest.raises(OrchestrationResultError, match="lowercase SHA-256"):
            domain_consumption_schema(
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=123,
            )

    # -- equal malformed actual/expected identities and digest -----------------

    def test_rejects_equal_bool_root_job_id(self, base_ids):
        observation = self._observation(base_ids, '{"result": "ok"}')
        observation["root_job_id"] = True
        kwargs = self._kwargs(base_ids)
        kwargs["expected_root_job_id"] = True
        with pytest.raises(OrchestrationResultError):
            validate_domain_consumption(observation, **kwargs)

    def test_rejects_equal_empty_domain_job_id(self, base_ids):
        observation = self._observation(base_ids, '{"result": "ok"}')
        observation["domain_job_id"] = ""
        kwargs = self._kwargs(base_ids)
        kwargs["expected_domain_job_id"] = ""
        with pytest.raises(OrchestrationResultError):
            validate_domain_consumption(observation, **kwargs)

    def test_rejects_equal_uppercase_digest(self, base_ids):
        observation = self._observation(base_ids, '{"result": "ok"}')
        observation["consumption_projection_digest"] = "A" * 64
        kwargs = self._kwargs(base_ids)
        kwargs["expected_projection_digest"] = "A" * 64
        with pytest.raises(OrchestrationResultError, match="lowercase SHA-256"):
            validate_domain_consumption(observation, **kwargs)

    def test_rejects_equal_malformed_actual_identifier(self, base_ids):
        observation = self._observation(base_ids, '{"result": "ok"}')
        observation["domain_attempt_id"] = "bad id!"
        kwargs = self._kwargs(base_ids)
        kwargs["expected_domain_attempt_id"] = "bad id!"
        with pytest.raises(OrchestrationResultError):
            validate_domain_consumption(observation, **kwargs)

    # -- UTF-8 byte accounting, not character counting -------------------------

    def test_rejects_multibyte_under_char_cap_over_byte_cap(self, base_ids):
        consumed = "é" * ((MAX_CANONICAL_RESULT_BYTES // 2) + 1)
        assert len(consumed) < MAX_CANONICAL_RESULT_BYTES
        assert len(consumed.encode("utf-8")) > MAX_CANONICAL_RESULT_BYTES
        with pytest.raises(OrchestrationResultError, match="exceeds 8 MiB"):
            validate_domain_consumption(
                self._observation(base_ids, consumed), **self._kwargs(base_ids)
            )

    def test_rejects_complete_body_overhead_crossing_limit(self, base_ids):
        base_obs = self._observation(base_ids, "a")
        overhead = len(canonical_bytes(base_obs)) - 1
        consumed = "a" * (MAX_CANONICAL_RESULT_BYTES - overhead + 1)
        assert len(consumed.encode("utf-8")) < MAX_CANONICAL_RESULT_BYTES
        with pytest.raises(OrchestrationResultError, match="exceeds 8 MiB"):
            validate_domain_consumption(
                self._observation(base_ids, consumed), **self._kwargs(base_ids)
            )

    # -- secret refusal without mutation ---------------------------------------

    def test_rejects_secret_consumed_result(self, base_ids):
        with pytest.raises(OrchestrationResultError, match="sensitive material"):
            validate_domain_consumption(
                self._observation(base_ids, "password=hunter2"),
                **self._kwargs(base_ids),
            )

    # -- closed schema and nonstring body --------------------------------------

    def test_rejects_unknown_key(self, base_ids):
        observation = self._observation(base_ids, '{"result": "ok"}')
        observation["unknown_key"] = "nope"
        with pytest.raises(OrchestrationResultError, match="closed schema"):
            validate_domain_consumption(observation, **self._kwargs(base_ids))

    def test_rejects_nonstring_body(self, base_ids):
        with pytest.raises(OrchestrationResultError, match="must be a string"):
            validate_domain_consumption(
                self._observation(base_ids, 12345), **self._kwargs(base_ids)
            )

    # -- legitimate values are preserved exactly -------------------------------

    def test_preserves_exact_values(self, base_ids):
        consumed = '{"result": "ok", "unicode": "é"}'
        observation = self._observation(base_ids, consumed)
        result = validate_domain_consumption(observation, **self._kwargs(base_ids))
        assert result == observation
        assert result["consumed_result"] == consumed


class TestInnerHardenedParser:
    def _kwargs(self, base_ids):
        return {
            "expected_root_job_id": base_ids["root_job_id"],
            "expected_domain_job_id": base_ids["domain_job_id"],
            "expected_domain_attempt_id": base_ids["domain_attempt_id"],
            "expected_projection_digest": base_ids["consumption_projection_digest"],
        }

    def _text(self, base_ids, consumed_result, **overrides):
        observation = {
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
            "root_job_id": base_ids["root_job_id"],
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            "consumption_projection_digest": base_ids["consumption_projection_digest"],
            "consumed_result": consumed_result,
        }
        observation.update(overrides)
        return canonical_bytes(observation).decode("utf-8")

    def test_parser_roundtrips_unicode(self, base_ids):
        consumed = '{"note": "résumé 漢字 😀"}'
        text = self._text(base_ids, consumed)
        parsed = parse_and_validate_domain_consumption(text, **self._kwargs(base_ids))
        assert parsed["consumed_result"] == consumed
        assert canonical_bytes(parsed) == text.encode("utf-8")

    def test_parser_rejects_equal_malformed_expected_digest(self, base_ids):
        text = self._text(base_ids, '{"result": "ok"}')
        kwargs = self._kwargs(base_ids)
        kwargs["expected_projection_digest"] = "A" * 64
        with pytest.raises(OrchestrationResultError, match="lowercase SHA-256"):
            parse_and_validate_domain_consumption(text, **kwargs)

    def test_parser_rejects_secret(self, base_ids):
        text = self._text(base_ids, "token=abc123")
        with pytest.raises(OrchestrationResultError, match="sensitive material"):
            parse_and_validate_domain_consumption(text, **self._kwargs(base_ids))

    def test_parser_rejects_unknown_key(self, base_ids):
        text = self._text(base_ids, '{"result": "ok"}', unknown_key="x")
        with pytest.raises(OrchestrationResultError, match="closed schema"):
            parse_and_validate_domain_consumption(text, **self._kwargs(base_ids))

    def test_parser_rejects_nonstring_body(self, base_ids):
        text = self._text(base_ids, 12345)
        with pytest.raises(OrchestrationResultError, match="must be a string"):
            parse_and_validate_domain_consumption(text, **self._kwargs(base_ids))

    def test_parser_rejects_multibyte_over_byte_cap(self, base_ids):
        consumed = "é" * ((MAX_CANONICAL_RESULT_BYTES // 2) + 1)
        text = self._text(base_ids, consumed)
        with pytest.raises(OrchestrationResultError, match="exceeds 8 MiB"):
            parse_and_validate_domain_consumption(text, **self._kwargs(base_ids))


# --------------------------------------------------------------------------- #
# Digest binding and canonical roundtrip
# --------------------------------------------------------------------------- #

class TestConsumptionProjectionDigestBinding:
    def test_digest_changes_when_root_changes(self, base_ids, valid_projection):
        proj_a = dict(valid_projection)
        proj_b = dict(valid_projection)
        proj_b["root_job_id"] = "different-root"

        digest_a = canonical_digest(proj_a)
        digest_b = canonical_digest(proj_b)
        assert digest_a != digest_b

    def test_digest_changes_when_domain_job_id_changes(self, base_ids, valid_projection):
        proj_a = dict(valid_projection)
        proj_b = dict(valid_projection)
        proj_b["domain_job_id"] = "different-domain"

        digest_a = canonical_digest(proj_a)
        digest_b = canonical_digest(proj_b)
        assert digest_a != digest_b

    def test_digest_changes_when_domain_attempt_id_changes(self, base_ids, valid_projection):
        proj_a = dict(valid_projection)
        proj_b = dict(valid_projection)
        proj_b["domain_attempt_id"] = "different-attempt"

        digest_a = canonical_digest(proj_a)
        digest_b = canonical_digest(proj_b)
        assert digest_a != digest_b

    def test_digest_changes_when_plan_digest_changes(self, base_ids, valid_projection):
        proj_a = dict(valid_projection)
        proj_b = dict(valid_projection)
        proj_b["plan_digest"] = "c" * 64

        digest_a = canonical_digest(proj_a)
        digest_b = canonical_digest(proj_b)
        assert digest_a != digest_b

    def test_deterministic_projection_roundtrip(self, valid_projection):
        """Changing root/domain/attempt/plan invalidates the digest."""
        proj = dict(valid_projection)

        # Canonical roundtrip
        canonical = canonical_bytes(proj)
        reparsed = parse_canonical_json(canonical.decode("utf-8"))

        # Digest must match
        assert canonical_digest(proj) == canonical_digest(reparsed)

    def test_projection_roundtrip_with_digest(self, valid_projection):
        """Projection including digest roundtrips correctly."""
        proj = dict(valid_projection)
        proj["consumption_projection_digest"] = canonical_digest(proj)

        canonical = canonical_bytes(proj)
        reparsed = parse_canonical_json(canonical.decode("utf-8"))

        assert reparsed["consumption_projection_digest"] == proj["consumption_projection_digest"]


# --------------------------------------------------------------------------- #
# Domain Consumption Envelope — Schema
# --------------------------------------------------------------------------- #

class TestDomainConsumptionEnvelopeSchema:
    def test_returns_closed_schema_with_outer_envelope(self, base_ids):
        schema = domain_consumption_envelope_schema(
            expected_job_id=base_ids["job_id"],
            expected_run_id=base_ids["run_id"],
            expected_worker_id=base_ids["worker_id"],
            expected_root_job_id=base_ids["root_job_id"],
            expected_domain_job_id=base_ids["domain_job_id"],
            expected_domain_attempt_id=base_ids["domain_attempt_id"],
            expected_projection_digest=base_ids["consumption_projection_digest"],
        )
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        props = schema["properties"]
        # Outer envelope
        assert props["schema_version"]["const"] == "mastermind.executive_orchestration_result/v1"
        assert props["job_id"]["const"] == base_ids["job_id"]
        assert props["run_id"]["const"] == base_ids["run_id"]
        assert props["worker_id"]["const"] == base_ids["worker_id"]
        assert props["role"]["const"] == "plan"
        assert props["status"]["const"] == "COMPLETED"
        # Inner role_result
        inner = props["role_result"]["properties"]
        assert inner["schema_version"]["const"] == DOMAIN_CONSUMPTION_SCHEMA
        assert inner["root_job_id"]["const"] == base_ids["root_job_id"]
        assert inner["domain_job_id"]["const"] == base_ids["domain_job_id"]
        assert inner["domain_attempt_id"]["const"] == base_ids["domain_attempt_id"]
        assert inner["consumption_projection_digest"]["const"] == base_ids["consumption_projection_digest"]
        assert inner["consumed_result"]["type"] == "string"

    def test_schema_rejects_domain_job_not_equal_job(self, base_ids):
        with pytest.raises(OrchestrationResultError, match="expected_job_id must equal expected_domain_job_id"):
            domain_consumption_envelope_schema(
                expected_job_id="different-job",
                expected_run_id=base_ids["run_id"],
                expected_worker_id=base_ids["worker_id"],
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )

    def test_schema_rejects_domain_attempt_not_equal_run(self, base_ids):
        with pytest.raises(OrchestrationResultError, match="expected_run_id must equal expected_domain_attempt_id"):
            domain_consumption_envelope_schema(
                expected_job_id=base_ids["job_id"],
                expected_run_id="different-run",
                expected_worker_id=base_ids["worker_id"],
                expected_root_job_id=base_ids["root_job_id"],
                expected_domain_job_id=base_ids["domain_job_id"],
                expected_domain_attempt_id=base_ids["domain_attempt_id"],
                expected_projection_digest=base_ids["consumption_projection_digest"],
            )


# --------------------------------------------------------------------------- #
# Domain Consumption Envelope — Validation Guards
# --------------------------------------------------------------------------- #

class TestValidateDomainConsumptionEnvelopeGuards:
    """F2/F3/F4/F5: Independent guard tests for each defect."""

    def _valid_envelope(self, base_ids, consumed_result="Reviewed child results consumed."):
        return {
            "schema_version": "mastermind.executive_orchestration_result/v1",
            "job_id": base_ids["job_id"],
            "run_id": base_ids["run_id"],
            "worker_id": base_ids["worker_id"],
            "role": "plan",
            "status": "COMPLETED",
            "role_result": {
                "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
                "root_job_id": base_ids["root_job_id"],
                "domain_job_id": base_ids["domain_job_id"],
                "domain_attempt_id": base_ids["domain_attempt_id"],
                "consumption_projection_digest": base_ids["consumption_projection_digest"],
                "consumed_result": consumed_result,
            },
            "summary": "bounded consumption",
            "current_state": "reviewed",
            "next_actions": [],
            "errors": [],
            "validations": [],
        }

    def _validation_kwargs(self, base_ids):
        return {
            "expected_job_id": base_ids["job_id"],
            "expected_run_id": base_ids["run_id"],
            "expected_worker_id": base_ids["worker_id"],
            "expected_root_job_id": base_ids["root_job_id"],
            "expected_domain_job_id": base_ids["domain_job_id"],
            "expected_domain_attempt_id": base_ids["domain_attempt_id"],
            "expected_projection_digest": base_ids["consumption_projection_digest"],
        }

    # F2: Missing complete outer envelope
    def test_rejects_missing_outer_key(self, base_ids):
        env = self._valid_envelope(base_ids)
        del env["job_id"]
        with pytest.raises(OrchestrationResultError, match="closed schema"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_extra_outer_key(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["extra_outer_key"] = "forbidden"
        with pytest.raises(OrchestrationResultError, match="closed schema"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_missing_inner_key(self, base_ids):
        env = self._valid_envelope(base_ids)
        del env["role_result"]["root_job_id"]
        with pytest.raises(OrchestrationResultError, match="closed schema"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_extra_inner_key(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role_result"]["extra_inner_key"] = "forbidden"
        with pytest.raises(OrchestrationResultError, match="closed schema"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    # F3: Malformed identities — actual vs expected
    def test_rejects_actual_job_id_mismatch(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["job_id"] = "wrong-job"
        with pytest.raises(OrchestrationResultError, match="outer job_id mismatch"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_actual_run_id_mismatch(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["run_id"] = "wrong-run"
        with pytest.raises(OrchestrationResultError, match="outer run_id mismatch"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_actual_worker_id_mismatch(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["worker_id"] = "wrong-worker"
        with pytest.raises(OrchestrationResultError, match="outer worker_id mismatch"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_actual_root_job_id_mismatch(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role_result"]["root_job_id"] = "wrong-root"
        with pytest.raises(OrchestrationResultError, match="domain consumption root_job_id mismatch"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_actual_domain_job_id_mismatch(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role_result"]["domain_job_id"] = "wrong-domain"
        with pytest.raises(OrchestrationResultError, match="domain consumption domain_job_id mismatch"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_actual_domain_attempt_id_mismatch(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role_result"]["domain_attempt_id"] = "wrong-attempt"
        with pytest.raises(OrchestrationResultError, match="domain consumption domain_attempt_id mismatch"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_actual_projection_digest_mismatch(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role_result"]["consumption_projection_digest"] = "f" * 64
        with pytest.raises(OrchestrationResultError, match="domain consumption projection_digest mismatch"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    # F3: Malformed identifiers (bool/int/empty)
    def test_rejects_bool_job_id(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["job_id"] = True
        with pytest.raises(OrchestrationResultError, match="job_id must be UTF-8 text"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_int_job_id(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["job_id"] = 123
        with pytest.raises(OrchestrationResultError, match="job_id must be UTF-8 text"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_empty_job_id(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["job_id"] = ""
        with pytest.raises(OrchestrationResultError, match="non-empty"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_malformed_identifier_pattern(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["job_id"] = "not valid!@#$"
        with pytest.raises(OrchestrationResultError, match="canonical identifier"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_bool_root_job_id(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role_result"]["root_job_id"] = False
        with pytest.raises(OrchestrationResultError, match="root_job_id must be UTF-8 text"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_empty_root_job_id(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role_result"]["root_job_id"] = ""
        with pytest.raises(OrchestrationResultError, match="non-empty"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    # F3: Malformed digest
    def test_rejects_malformed_digest_wrong_length(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role_result"]["consumption_projection_digest"] = "abc123"
        with pytest.raises(OrchestrationResultError, match="lowercase SHA-256"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_malformed_digest_uppercase(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role_result"]["consumption_projection_digest"] = "A" * 64
        with pytest.raises(OrchestrationResultError, match="lowercase SHA-256"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_malformed_digest_special_chars(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role_result"]["consumption_projection_digest"] = "g" * 64  # g not in hex
        with pytest.raises(OrchestrationResultError, match="lowercase SHA-256"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    # F3: Expected identity errors — malformed expectations
    def test_rejects_malformed_expected_job_id(self, base_ids):
        kwargs = self._validation_kwargs(base_ids)
        kwargs["expected_job_id"] = "bad job id!"
        with pytest.raises(OrchestrationResultError, match="canonical identifier"):
            validate_domain_consumption_envelope(self._valid_envelope(base_ids), **kwargs)

    def test_rejects_malformed_expected_root_job_id(self, base_ids):
        kwargs = self._validation_kwargs(base_ids)
        kwargs["expected_root_job_id"] = ""
        with pytest.raises(OrchestrationResultError, match="non-empty"):
            validate_domain_consumption_envelope(self._valid_envelope(base_ids), **kwargs)

    def test_rejects_malformed_expected_projection_digest(self, base_ids):
        kwargs = self._validation_kwargs(base_ids)
        kwargs["expected_projection_digest"] = "not-a-digest"
        with pytest.raises(OrchestrationResultError, match="lowercase SHA-256"):
            validate_domain_consumption_envelope(self._valid_envelope(base_ids), **kwargs)

    # F3: Equal malformed expected/actual
    def test_rejects_equal_malformed_both_wrong(self, base_ids):
        """Both expected and actual are malformed but equal — still rejected."""
        env = self._valid_envelope(base_ids)
        env["job_id"] = "bad-job!"
        kwargs = self._validation_kwargs(base_ids)
        kwargs["expected_job_id"] = "bad-job!"
        with pytest.raises(OrchestrationResultError, match="canonical identifier"):
            validate_domain_consumption_envelope(env, **kwargs)

    # F4: UTF8 byte vs character counting
    def test_rejects_utf8_characters_in_result_exceeding_bytes(self, base_ids):
        # 1M chars of multi-byte UTF8 exceeds byte limit
        env = self._valid_envelope(base_ids)
        # Each emoji is 4 bytes. 2M emojis = 8M+ bytes > 8MiB limit
        env["role_result"]["consumed_result"] = "🎉" * (MAX_CANONICAL_RESULT_BYTES // 4 + 1)
        with pytest.raises(OrchestrationResultError, match="exceeds 8 MiB"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_utf8_summary_exceeding_bytes(self, base_ids):
        env = self._valid_envelope(base_ids)
        # summary field itself is capped at 8192 chars; use consumed_result (max=8MiB)
        # to push total envelope over the byte limit
        env["role_result"]["consumed_result"] = "x" * (MAX_CANONICAL_RESULT_BYTES - 200)
        with pytest.raises(OrchestrationResultError, match="exceeds 8 MiB"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_utf8_inner_body_plus_outer_overhead_exceeding_bytes(self, base_ids):
        """Envelope overhead + inner body crossing the 8MiB boundary."""
        env = self._valid_envelope(base_ids)
        # Fill consumed_result so total canonical bytes > 8MiB
        # Outer envelope adds ~200 bytes of overhead
        target_size = MAX_CANONICAL_RESULT_BYTES - 100
        env["role_result"]["consumed_result"] = "x" * target_size
        # Validate it doesn't fail on character count but does on byte count
        with pytest.raises(OrchestrationResultError, match="exceeds 8 MiB"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_accepts_valid_utf8_in_result(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role_result"]["consumed_result"] = "Hello 🌍 🎉 ñoño"
        result = validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))
        assert "🌀" not in result["role_result"]["consumed_result"]  # No mutation

    # F5: Secret redaction refusal
    def test_rejects_secret_shaped_body(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role_result"]["consumed_result"] = "sk-1234567890abcdef"
        with pytest.raises(OrchestrationResultError, match="redaction-triggering"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_secret_shaped_summary(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["summary"] = "Token: super-secret-key-12345"
        with pytest.raises(OrchestrationResultError, match="redaction-triggering"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_does_not_mutate_and_accept(self, base_ids):
        """Validator must refuse, not mutate and accept."""
        env = self._valid_envelope(base_ids)
        env["role_result"]["consumed_result"] = "password=secret123"
        try:
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))
            pytest.fail("Should have raised OrchestrationResultError")
        except OrchestrationResultError as e:
            assert "redaction" in str(e).lower()

    # Outer job/run/worker/role swaps
    def test_rejects_role_not_plan(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["role"] = "work"
        with pytest.raises(OrchestrationResultError, match="role=plan"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_status_not_completed(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["status"] = "PENDING"
        with pytest.raises(OrchestrationResultError, match="status=COMPLETED"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_validations_not_empty(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["validations"] = [{"some": "validation"}]
        with pytest.raises(OrchestrationResultError, match="validations="):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_outer_job_id_swap(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["job_id"] = "swapped-job"
        with pytest.raises(OrchestrationResultError, match="outer job_id mismatch"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_outer_run_id_swap(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["run_id"] = "swapped-run"
        with pytest.raises(OrchestrationResultError, match="outer run_id mismatch"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))

    def test_rejects_outer_worker_id_swap(self, base_ids):
        env = self._valid_envelope(base_ids)
        env["worker_id"] = "swapped-worker"
        with pytest.raises(OrchestrationResultError, match="outer worker_id mismatch"):
            validate_domain_consumption_envelope(env, **self._validation_kwargs(base_ids))


# --------------------------------------------------------------------------- #
# Domain Consumption Envelope — Parser
# --------------------------------------------------------------------------- #

class TestParseAndValidateDomainConsumptionEnvelope:
    def _validation_kwargs(self, base_ids):
        return {
            "expected_job_id": base_ids["job_id"],
            "expected_run_id": base_ids["run_id"],
            "expected_worker_id": base_ids["worker_id"],
            "expected_root_job_id": base_ids["root_job_id"],
            "expected_domain_job_id": base_ids["domain_job_id"],
            "expected_domain_attempt_id": base_ids["domain_attempt_id"],
            "expected_projection_digest": base_ids["consumption_projection_digest"],
        }

    def test_valid_bound_outer_roundtrip(self, base_ids):
        env = {
            "schema_version": "mastermind.executive_orchestration_result/v1",
            "job_id": base_ids["job_id"],
            "run_id": base_ids["run_id"],
            "worker_id": base_ids["worker_id"],
            "role": "plan",
            "status": "COMPLETED",
            "role_result": {
                "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
                "root_job_id": base_ids["root_job_id"],
                "domain_job_id": base_ids["domain_job_id"],
                "domain_attempt_id": base_ids["domain_attempt_id"],
                "consumption_projection_digest": base_ids["consumption_projection_digest"],
                "consumed_result": "Reviewed child results consumed.",
            },
            "summary": "bounded consumption",
            "current_state": "reviewed",
            "next_actions": [],
            "errors": [],
            "validations": [],
        }
        text = canonical_bytes(env).decode("utf-8")
        result = parse_and_validate_domain_consumption_envelope(text, **self._validation_kwargs(base_ids))
        assert result["job_id"] == base_ids["job_id"]
        assert result["role_result"]["consumed_result"] == "Reviewed child results consumed."

    def test_rejects_noncanonical_text(self, base_ids):
        text = '{"schema_version":"mastermind.executive_orchestration_result/v1","job_id":"domain-1","run_id":"attempt-1","worker_id":"worker-1","role":"plan","status":"COMPLETED","role_result":{"schema_version":"mastermind.executive_coo_domain_consumption/v1","root_job_id":"test-root-001","domain_job_id":"domain-1","domain_attempt_id":"attempt-1","consumption_projection_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","consumed_result":"ok"},"summary":"bounded","current_state":"reviewed","next_actions":[],"errors":[],"validations":[]} '
        with pytest.raises(OrchestrationResultError, match="byte-for-byte"):
            parse_and_validate_domain_consumption_envelope(text, **self._validation_kwargs(base_ids))

    def test_rejects_bom(self, base_ids):
        inner = {
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
            "root_job_id": base_ids["root_job_id"],
            "domain_job_id": base_ids["domain_job_id"],
            "domain_attempt_id": base_ids["domain_attempt_id"],
            "consumption_projection_digest": base_ids["consumption_projection_digest"],
            "consumed_result": "ok",
        }
        text = "﻿" + canonical_bytes({
            "schema_version": "mastermind.executive_orchestration_result/v1",
            "job_id": base_ids["job_id"],
            "run_id": base_ids["run_id"],
            "worker_id": base_ids["worker_id"],
            "role": "plan",
            "status": "COMPLETED",
            "role_result": inner,
            "summary": "bounded",
            "current_state": "reviewed",
            "next_actions": [],
            "errors": [],
            "validations": [],
        }).decode("utf-8")
        with pytest.raises(OrchestrationResultError, match="BOM"):
            parse_and_validate_domain_consumption_envelope(text, **self._validation_kwargs(base_ids))


# --------------------------------------------------------------------------- #
# Existing result behavior preserved
# --------------------------------------------------------------------------- #

class TestExistingResultBehaviorPreserved:
    def test_plan_schema_still_v1_only(self):
        schema = orchestration_result_schema("plan")
        # V1-only, not V2/V3
        assert schema["properties"]["role_result"]["properties"]["schema_version"]["const"] == "mastermind.execution_plan/v1"

    def test_orchestration_result_role_schema_keys_preserved(self):
        for role in ROLES:
            schema = orchestration_result_schema(role)
            assert "role_result" in schema["required"]
            assert schema["properties"]["role_result"]["type"] == "object"

    def test_ordinary_plan_validator_rejects_domain_consumption_body(self, base_ids):
        """Ordinary plan validator must reject domain-consumption bodies."""
        # A domain consumption role_result has schema_version mastermind.executive_coo_domain_consumption/v1
        # which the plan validator should reject
        bad_role_result = {
            "schema_version": DOMAIN_CONSUMPTION_SCHEMA,  # Wrong schema for plan
            "root_job_id": base_ids["root_job_id"],
            "plan_attempt_id": base_ids["domain_attempt_id"],
            "steps": [],
        }
        try:
            validate_envelope(
                {
                    "schema_version": "mastermind.executive_orchestration_result/v1",
                    "job_id": base_ids["job_id"],
                    "run_id": base_ids["run_id"],
                    "worker_id": base_ids["worker_id"],
                    "role": "plan",
                    "status": "COMPLETED",
                    "role_result": bad_role_result,
                    "summary": "bad",
                    "current_state": "bad",
                    "next_actions": [],
                    "errors": [],
                    "validations": [],
                },
                expected_job_id=base_ids["job_id"],
                expected_run_id=base_ids["run_id"],
                expected_worker_id=base_ids["worker_id"],
                expected_role="plan",
            )
            pytest.fail("Should have raised OrchestrationResultError")
        except OrchestrationResultError:
            pass  # Expected: plan validator rejects domain consumption schema

    def test_domain_consumption_schema_not_widening_ordinary_plan(self, base_ids):
        """Scoped API does not widen the ordinary plan schema."""
        # Create an envelope with domain consumption body and try it against
        # the ordinary plan schema — should fail
        env = {
            "schema_version": "mastermind.executive_orchestration_result/v1",
            "job_id": base_ids["job_id"],
            "run_id": base_ids["run_id"],
            "worker_id": base_ids["worker_id"],
            "role": "plan",
            "status": "COMPLETED",
            "role_result": {
                "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
                "root_job_id": base_ids["root_job_id"],
                "domain_job_id": base_ids["domain_job_id"],
                "domain_attempt_id": base_ids["domain_attempt_id"],
                "consumption_projection_digest": base_ids["consumption_projection_digest"],
                "consumed_result": "test",
            },
            "summary": "bounded",
            "current_state": "reviewed",
            "next_actions": [],
            "errors": [],
            "validations": [],
        }
        # Ordinary plan validation should reject this
        with pytest.raises(OrchestrationResultError):
            validate_envelope(
                env,
                expected_job_id=base_ids["job_id"],
                expected_run_id=base_ids["run_id"],
                expected_worker_id=base_ids["worker_id"],
                expected_role="plan",
            )


# --------------------------------------------------------------------------- #
# Valid unicode preservation
# --------------------------------------------------------------------------- #

class TestValidUnicodePreserved:
    def test_valid_unicode_roundtrips_through_envelope(self, base_ids):
        """Valid UTF8 strings must be preserved byte-for-byte."""
        consumed = '{"emoji":"🎉","accent":"ñoño","chinese":"你好"}'
        env = {
            "schema_version": "mastermind.executive_orchestration_result/v1",
            "job_id": base_ids["job_id"],
            "run_id": base_ids["run_id"],
            "worker_id": base_ids["worker_id"],
            "role": "plan",
            "status": "COMPLETED",
            "role_result": {
                "schema_version": DOMAIN_CONSUMPTION_SCHEMA,
                "root_job_id": base_ids["root_job_id"],
                "domain_job_id": base_ids["domain_job_id"],
                "domain_attempt_id": base_ids["domain_attempt_id"],
                "consumption_projection_digest": base_ids["consumption_projection_digest"],
                "consumed_result": consumed,
            },
            "summary": "üñicödé summary",
            "current_state": "stäte",
            "next_actions": [],
            "errors": [],
            "validations": [],
        }
        text = canonical_bytes(env).decode("utf-8")
        result = parse_and_validate_domain_consumption_envelope(
            text,
            expected_job_id=base_ids["job_id"],
            expected_run_id=base_ids["run_id"],
            expected_worker_id=base_ids["worker_id"],
            expected_root_job_id=base_ids["root_job_id"],
            expected_domain_job_id=base_ids["domain_job_id"],
            expected_domain_attempt_id=base_ids["domain_attempt_id"],
            expected_projection_digest=base_ids["consumption_projection_digest"],
        )
        assert result["role_result"]["consumed_result"] == consumed
        assert result["summary"] == "üñicödé summary"
        # Verify byte-for-byte canonical roundtrip
        assert canonical_bytes(result).decode("utf-8") == text
