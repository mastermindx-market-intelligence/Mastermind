from __future__ import annotations

import ast
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from integrations.mastermind_surface_probe.probe import (
    HostContextProbeConfig,
    HostContextProbeError,
    inspect_surface_context,
)
from integrations.mastermind_surface_probe.schemas import (
    CONTRACT_DIGEST,
    DEGRADATION_CODES,
    HOST_CONTEXT_KEYS,
    IDENTIFIER_HOST_FIELDS,
    RESULT_SCHEMA,
    SERVER_IDENTITY,
    SERVER_VERSION,
    contract_digest,
)


FIXED_NOW = datetime(2026, 8, 29, 18, 30, tzinfo=UTC)
RAW_META = {
    "openai/session": "session-secret-correlate-001",
    "openai/subject": "subject-secret-correlate-001",
    "openai/organization": "organization-secret-correlate-001",
    "openai/locale": "en-US",
    "openai/userAgent": "ChatGPT-Business-Test/1.0",
    "openai/userLocation": {
        "city": "New York",
        "region": "New York",
        "country": "US",
        "timezone": "America/New_York",
        "longitude": -73.9857,
        "latitude": 40.7484,
    },
}
RAW_VALUES = {
    "session-secret-correlate-001",
    "subject-secret-correlate-001",
    "organization-secret-correlate-001",
    "en-US",
    "ChatGPT-Business-Test/1.0",
    "New York",
    "US",
    "America/New_York",
}


def _config(**overrides: object) -> HostContextProbeConfig:
    values: dict[str, object] = {
        "app_realm": "surface",
        "app_generation": "surface-probe-g1",
        "transport_profile": "secure-mcp-tunnel-dev",
        "fingerprint_key_id": "hc0-cohort-a",
        "fingerprint_key_version": "v1",
        "fingerprint_scope": "probe-cohort",
        "fingerprint_secret": b"0123456789abcdef0123456789abcdef",
    }
    values.update(overrides)
    return HostContextProbeConfig(**values)


def _inspect(
    meta: object = RAW_META,
    *,
    config: HostContextProbeConfig | None = None,
    observed_at: datetime = FIXED_NOW,
) -> dict[str, object]:
    return inspect_surface_context(
        meta,
        config=config or _config(),
        observed_at=observed_at,
    )


def _render(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def test_complete_probe_response_is_exact_bounded_and_correlation_only():
    response = _inspect()

    assert response["schema"] == RESULT_SCHEMA == "mastermind.host_context_probe.v1"
    assert response["server_identity"] == SERVER_IDENTITY == "mastermind-surface-probe-mcp"
    assert response["server_version"] == SERVER_VERSION == "1.0.0"
    assert response["app_realm"] == "surface"
    assert response["app_generation"] == "surface-probe-g1"
    assert response["contract_digest"] == CONTRACT_DIGEST == contract_digest()
    assert re.fullmatch(r"[0-9a-f]{64}", str(response["contract_digest"]))
    assert response["transport_profile"] == "secure-mcp-tunnel-dev"
    assert response["fingerprint_key_id"] == "hc0-cohort-a"
    assert response["fingerprint_key_version"] == "v1"
    assert response["fingerprint_scope"] == "probe-cohort"
    assert response["observed_at"] == "2026-08-29T18:30:00Z"
    assert response["correlation_only"] is True
    assert response["oauth_posture"] == {
        "configured": False,
        "resource": None,
        "scopes": [],
        "principal_fingerprint": None,
    }
    assert response["degradations"] == [
        "OAUTH_NOT_CONFIGURED",
        "TUNNEL_ATTESTATION_UNAVAILABLE",
    ]
    assert set(response["host_context"]) == set(HOST_CONTEXT_KEYS)
    assert len(_render(response).encode("utf-8")) < 16 * 1024


def test_raw_host_values_and_location_details_never_leave_the_probe():
    response = _inspect()
    rendered = _render(response)

    for raw in RAW_VALUES:
        assert raw not in rendered
    assert "city" not in rendered
    assert "longitude" not in rendered
    assert "latitude" not in rendered
    assert "widgetSessionId" not in rendered


def test_only_identifier_fields_receive_keyed_fingerprints():
    response = _inspect()
    rows = response["host_context"]

    for field in HOST_CONTEXT_KEYS:
        row = rows[field]
        assert row["present"] is True
        assert row["usable_for_authorization"] is False
        if field in IDENTIFIER_HOST_FIELDS:
            assert re.fullmatch(r"hmac-sha256:v1:[0-9a-f]{64}", row["fingerprint"])
        else:
            assert row["fingerprint"] is None


def test_fingerprint_is_stable_but_domain_separated_by_field_realm_and_generation():
    first = _inspect()
    second = _inspect()
    assert first["host_context"] == second["host_context"]

    same_raw = {
        "openai/session": "same-opaque-value",
        "openai/subject": "same-opaque-value",
        "openai/organization": "same-opaque-value",
    }
    baseline = _inspect(same_raw)
    fingerprints = {
        baseline["host_context"][field]["fingerprint"]
        for field in IDENTIFIER_HOST_FIELDS
    }
    assert len(fingerprints) == 3

    different_realm = _inspect(same_raw, config=_config(app_realm="steward"))
    different_generation = _inspect(
        same_raw,
        config=_config(app_generation="surface-probe-g2"),
    )
    for field in IDENTIFIER_HOST_FIELDS:
        assert (
            baseline["host_context"][field]["fingerprint"]
            != different_realm["host_context"][field]["fingerprint"]
        )
        assert (
            baseline["host_context"][field]["fingerprint"]
            != different_generation["host_context"][field]["fingerprint"]
        )


def test_missing_meta_is_explicit_null_not_an_empty_string_fingerprint():
    response = _inspect(None)

    assert response["degradations"] == [
        "OAUTH_NOT_CONFIGURED",
        "OPENAI_LOCALE_ABSENT",
        "OPENAI_ORGANIZATION_ABSENT",
        "OPENAI_SESSION_ABSENT",
        "OPENAI_SUBJECT_ABSENT",
        "TUNNEL_ATTESTATION_UNAVAILABLE",
        "USER_AGENT_HINT_ABSENT",
        "USER_LOCATION_HINT_ABSENT",
    ]
    for row in response["host_context"].values():
        assert row == {
            "present": False,
            "fingerprint": None,
            "usable_for_authorization": False,
        }


def test_unknown_request_metadata_is_ignored_without_echoing_key_or_value():
    meta = dict(RAW_META)
    meta["attacker/private-field"] = {"secret_name": "do-not-echo-me"}
    meta["progressToken"] = "opaque-standard-mcp-progress-token"

    response = _inspect(meta)
    rendered = _render(response)

    assert "UNKNOWN_HOST_META_IGNORED" in response["degradations"]
    assert "attacker/private-field" not in rendered
    assert "do-not-echo-me" not in rendered
    assert "progressToken" not in rendered
    assert "opaque-standard-mcp-progress-token" not in rendered


@pytest.mark.parametrize(
    "field,value",
    [
        ("openai/session", ""),
        ("openai/session", " leading-space"),
        ("openai/session", "trailing-space "),
        ("openai/session", "line\nbreak"),
        ("openai/session", "x" * 4097),
        ("openai/session", 42),
        ("openai/subject", ["not", "scalar"]),
        ("openai/organization", {"not": "scalar"}),
        ("openai/locale", "bad\u0000locale"),
        ("openai/userAgent", "x" * 2049),
        ("openai/userLocation", "not-an-object"),
        ("openai/userLocation", {"city": {"nested": "forbidden"}}),
        ("openai/userLocation", {"unexpected": "field"}),
        ("openai/userLocation", {"longitude": float("nan")}),
        ("openai/userLocation", {"longitude": 181}),
        ("openai/userLocation", {"latitude": -91}),
    ],
)
def test_malformed_present_metadata_fails_closed_without_echo(field: str, value: object):
    meta = dict(RAW_META)
    meta[field] = value

    with pytest.raises(HostContextProbeError) as exc_info:
        _inspect(meta)

    assert exc_info.value.code == "INVALID_HOST_METADATA"
    assert str(exc_info.value) == "INVALID_HOST_METADATA"
    assert repr(value) not in str(exc_info.value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_realm": ""},
        {"app_realm": "Surface"},
        {"app_generation": "contains spaces"},
        {"transport_profile": "https://secret.example/mcp?token=value"},
        {"fingerprint_key_id": "key/id"},
        {"fingerprint_key_version": ""},
        {"fingerprint_scope": "*"},
        {"fingerprint_secret": b"too-short"},
        {"fingerprint_secret": "not-bytes"},
    ],
)
def test_configuration_is_closed_and_fail_safe(overrides: dict[str, object]):
    with pytest.raises(HostContextProbeError) as exc_info:
        _config(**overrides)
    assert exc_info.value.code == "INVALID_CONFIGURATION"
    assert str(exc_info.value) == "INVALID_CONFIGURATION"


def test_configuration_repr_never_contains_secret_material():
    config = _config()
    rendered = repr(config)

    assert "0123456789abcdef" not in rendered
    assert "fingerprint_secret" not in rendered
    assert "<redacted>" in rendered


def test_observation_time_must_be_aware_utc_and_is_canonicalized_once():
    with pytest.raises(HostContextProbeError) as exc_info:
        _inspect(observed_at=datetime(2026, 8, 29, 18, 30))
    assert exc_info.value.code == "INVALID_OBSERVATION_TIME"

    offset = datetime.fromisoformat("2026-08-29T14:30:00-04:00")
    response = _inspect(observed_at=offset)
    assert response["observed_at"] == "2026-08-29T18:30:00Z"


def test_degradation_codes_and_host_rows_are_closed_and_deterministic():
    assert HOST_CONTEXT_KEYS == (
        "openai_session",
        "openai_subject",
        "openai_organization",
        "openai_locale",
        "user_agent_hint",
        "user_location_hint",
    )
    assert IDENTIFIER_HOST_FIELDS == frozenset(
        {"openai_session", "openai_subject", "openai_organization"}
    )
    assert DEGRADATION_CODES == frozenset(
        {
            "OPENAI_SESSION_ABSENT",
            "OPENAI_SUBJECT_ABSENT",
            "OPENAI_ORGANIZATION_ABSENT",
            "OPENAI_LOCALE_ABSENT",
            "USER_AGENT_HINT_ABSENT",
            "USER_LOCATION_HINT_ABSENT",
            "UNKNOWN_HOST_META_IGNORED",
            "TUNNEL_ATTESTATION_UNAVAILABLE",
            "OAUTH_NOT_CONFIGURED",
        }
    )


def test_sdk_free_core_imports_no_runtime_authority_or_persistence_owner():
    root = Path(__file__).resolve().parents[1]
    forbidden_roots = {
        "mcp",
        "fastapi",
        "starlette",
        "uvicorn",
        "psycopg",
        "duckdb",
        "sqlite3",
        "slack_sdk",
        "linear",
        "control_plane",
    }
    for relative in (
        "integrations/mastermind_surface_probe/schemas.py",
        "integrations/mastermind_surface_probe/probe.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        assert not (imported & forbidden_roots), (relative, imported & forbidden_roots)
