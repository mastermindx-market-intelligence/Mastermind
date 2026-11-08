import asyncio
import copy
import hashlib
import json
import os

import jsonschema
import pytest

from integrations.executive_mcp import schemas as legacy
from integrations.executive_mcp import web_ceo as v2
from integrations.executive_mcp import web_ceo_v3 as v3
from integrations.mastermind_executive_app.gateway import (
    CeoIngressResponse,
    TRANSPORT_SENT_OK,
)
from integrations.mosyle_mdm.client import MosyleCredential, MosyleTelemetryError
from integrations.mosyle_mdm.executive import WebCeoV3CeoIngressReadGateway
from integrations.mosyle_mdm import credential as credential_file
from integrations.mosyle_mdm.credential import (
    FileMosyleCredentialSource,
    MosyleCredentialFileError,
)


class FakeMdm:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = []

    async def list_macos_devices(self):
        self.calls.append(("fleet", None))
        if self.error:
            raise self.error
        return {
            "schema": "mastermind.mosyle_fleet_snapshot.v1",
            "source": "mosyle_business",
            "generated_at": "2026-09-23T06:00:00Z",
            "coverage": "macos",
            "complete": True,
            "device_count": 1,
            "page_count": 1,
            "devices": [{"serial_number": "S1", "device_name": "mini-01"}],
        }

    async def device(self, *, serial_number=None, hostname=None):
        self.calls.append(("device", serial_number or hostname))
        if self.error:
            raise self.error
        return {
            "schema": "mastermind.mosyle_device.v1",
            "source": "mosyle_business",
            "generated_at": "2026-09-23T06:00:00Z",
            "coverage": "macos",
            "device": {"serial_number": "S1", "device_name": "mini-01"},
        }


class FakeIngressClient:
    def __init__(self):
        self.frames = []

    async def send_frame(self, _path, frame):
        self.frames.append(frame)
        tool = frame["tool"]
        result = legacy.result_envelope(
            tool,
            mode=legacy.ServerMode.READONLY,
            generated_at="2026-09-23T06:00:00Z",
            data={
                "mastermind": {
                    "branch": "HEAD",
                    "root": "/mastermind",
                    "sha": "a" * 40,
                },
                "macro": {"root": "/macro", "sha": "b" * 40, "resolved_via": "flag"},
                "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
                "inbox_schema": "mastermind.executive_inbox.v2",
                "strategic_state": {
            "schema": "mastermind.strategic_state.v1",
            "company_phase": "PRE_REVENUE_MVP_CONVERGENCE",
            "north_star": ["Build a trustworthy product."],
            "p0": [{
                "id": "EXECUTIVE_OS",
                "department": "executive",
                "objective": "Establish durable execution.",
                "status": "active",
            }],
            "constraints": {
                "new_feature_expansion": "constrained",
                "autonomous_production_deploy": "prohibited",
                "autonomous_live_capital_execution": "prohibited",
                "duplicate_control_planes": "prohibited",
                "marketing_org_expansion_before_distribution_proof": "prohibited",
                "unbounded_autonomous_strategic_modification": "prohibited",
            },
        },
                "next_recommended_act": "Review current attention.",
                "runtime_db": {
                    "path": "/runtime/executive.sqlite3",
                    "present": True,
                },
                "runtime_counts": {
            "jobs": {
                "total": 1,
                "by_status": {
                    "QUEUED": 1, "RUNNING": 0, "CHECKPOINTED": 0,
                    "COMPLETED": 0, "FAILED": 0, "CANCEL_REQUESTED": 0,
                    "CANCELLED": 0, "LOST": 0, "RATE_LIMITED": 0,
                },
            },
            "attempts": {
                "total": 0,
                "by_status": {
                    "CLAIMED": 0, "RUNNING": 0, "CHECKPOINTED": 0,
                    "COMPLETED": 0, "FAILED": 0, "CANCEL_REQUESTED": 0,
                    "CANCELLED": 0, "LOST": 0, "RATE_LIMITED": 0,
                },
            },
            "workers": {
                "total": 0,
                "by_status": {
                    "AVAILABLE": 0, "BUSY": 0, "DRAINING": 0,
                    "OFFLINE": 0, "ERROR": 0, "RATE_LIMITED": 0,
                },
            },
        },
                "attention_counts": {
                    "total": 0,
                    "chairman": 0,
                    "ceo": 0,
                    "coo": 0,
                },
                "handoffs": [],
            },
            grounding={
                "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
                "macro": {"root": "/macro", "sha": "b" * 40},
                "mastermind": {
                    "branch": "HEAD",
                    "root": "/mastermind",
                    "sha": "a" * 40,
                },
                "runtime": "readonly:installed-executive-runtime",
                "runtime_db": {
                    "path": "/runtime/executive.sqlite3",
                    "present": True,
                },
            },
        )
        result["server_version"] = v2.WEB_CEO_V2_SERVER_VERSION
        return CeoIngressResponse(
            transport=TRANSPORT_SENT_OK, ok=True, result=result
        )


def run(value):
    return asyncio.run(value)


def gateway(mdm=None):
    return WebCeoV3CeoIngressReadGateway(
        "/tmp/ceo.sock", FakeIngressClient(), mdm_reader=mdm or FakeMdm()
    )


def test_v3_is_additive_and_prior_snapshot_hashes_remain_frozen():
    assert legacy.schema_snapshot_sha256() == (
        "546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232"
    )
    assert v2.web_ceo_schema_snapshot_sha256() == (
        "17e052ed734c2c4606094c49b0e9c057382a193fc181d595fc084da10809a5cd"
    )
    assert (
        v2.web_ceo_v2_schema_snapshot_sha256()
        == v2.WEB_CEO_V2_SCHEMA_SNAPSHOT_SHA256
    )
    assert (
        v3.web_ceo_v3_schema_snapshot_sha256()
        == v3.WEB_CEO_V3_SCHEMA_SNAPSHOT_SHA256
    )
    # The current profile adds only the Meta target to its frozen predecessor.
    # Qualify the whole inherited snapshot, not merely the new digest literal.
    prior = copy.deepcopy(v3.web_ceo_v3_schema_snapshot())
    target = next(tool for tool in prior["tools"] if tool["name"] == "session_targets")
    kinds = target["input_schema"]["properties"]["kind"]["enum"]
    assert kinds[-1] == "hermes_meta" and kinds.count("hermes_meta") == 1
    kinds.remove("hermes_meta")
    assert hashlib.sha256(legacy.canonical_json(prior)).hexdigest() == (
        "5c157d1de43d6efef99f6ba9e27e851f0243bbb18d38c23551b94a5c2a4ba2c0"
    )
    from integrations.executive_mcp import web_ceo_sessions as sessions

    assert v3.WEB_CEO_V3_SERVER_VERSION == "1.5.0"
    assert sessions.WEB_CEO_SESSIONS_SERVER_VERSION == "1.4.0"
    assert v3.web_ceo_v3_tool_names()[:-3] == sessions.web_ceo_sessions_tool_names()[:-1]
    assert v3.web_ceo_v3_tool_names()[-3:] == (
        "executive_mdm",
        "reconcile_ceo_request",
        "submit_ceo_intent",
    )


def test_v3_promotes_existing_session_bridge_tools_without_changing_session_profile():
    from integrations.executive_mcp import web_ceo_sessions as sessions

    assert v3.web_ceo_v3_tool_names() == (
        *sessions.web_ceo_sessions_tool_names()[:-1],
        "executive_mdm",
        "reconcile_ceo_request",
        "submit_ceo_intent",
    )
    assert sessions.web_ceo_sessions_tool_names()[-4:] == (
        "session_targets", "session_send", "session_summon", "submit_ceo_intent"
    )
    request = {
        "objective": "Delegate one bounded research task.",
        "execution_profile": "research_only",
        "operation_key": "v3-session-summon-1",
        "department": "executive-infrastructure",
        "priority": 0,
        "workstream": "WS:SESSION-BRIDGE",
    }
    assert v3.validate_web_ceo_v3_tool_arguments("session_summon", request) == (
        sessions.validate_web_ceo_sessions_tool_arguments("session_summon", request)
    )


def test_v3_fabric_transport_schema_is_flat_but_validator_remains_closed():
    schema = v3.FABRIC_V3_TOOL_SPEC.input_schema
    assert set(schema) == {"type", "properties", "required", "additionalProperties"}
    assert schema["properties"] == v2.FABRIC_V2_TOOL_SPEC.input_schema["properties"]
    assert schema["required"] == ["view"]
    assert schema["additionalProperties"] is False
    assert "oneOf" in v2.FABRIC_V2_TOOL_SPEC.input_schema

    valid = (
        {"view": "roots", "limit": 1},
        {"view": "root", "root_job_id": "JOB-001"},
        {
            "view": "result",
            "root_job_id": "JOB-001",
            "job_id": "JOB-004",
            "attempt_id": "ATT-" + "a" * 32,
            "result_envelope_digest": "b" * 64,
        },
    )
    for value in valid:
        jsonschema.validate(value, schema)
        assert v3.validate_web_ceo_v3_tool_arguments("executive_fabric", value) == value

    branch_invalid = {"view": "root", "root_job_id": "JOB-001", "limit": 1}
    jsonschema.validate(branch_invalid, schema)
    with pytest.raises(legacy.GatewayError, match="limit is valid only when view=roots"):
        v3.validate_web_ceo_v3_tool_arguments("executive_fabric", branch_invalid)


def test_v3_mdm_transport_schema_is_flat_but_validator_remains_closed():
    schema = v3.MDM_TOOL_SPEC.input_schema
    assert set(schema) == {"type", "properties", "required", "additionalProperties"}
    assert schema["required"] == ["view"]
    assert schema["additionalProperties"] is False

    conditionally_invalid = (
        {"view": "fleet", "hostname": "mini-01"},
        {"view": "device"},
        {"view": "device", "hostname": "mini", "serial_number": "S1"},
    )
    for value in conditionally_invalid:
        jsonschema.validate(value, schema)
        with pytest.raises(legacy.GatewayError):
            v3.validate_web_ceo_v3_tool_arguments("executive_mdm", value)

    for value in ({}, {"view": "other"}):
        with pytest.raises(legacy.GatewayError):
            v3.validate_web_ceo_v3_tool_arguments("executive_mdm", value)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(value, schema)


def test_valid_mdm_shapes():
    for value in (
        {"view": "fleet"},
        {"view": "device", "serial_number": "S1"},
        {"view": "device", "hostname": "mini-01"},
    ):
        jsonschema.validate(value, v3.MDM_TOOL_SPEC.input_schema)
        assert (
            v3.validate_web_ceo_v3_tool_arguments("executive_mdm", value)
            == value
        )


def test_mdm_fleet_is_direct_sensor_read_not_ingress():
    client = FakeIngressClient()
    mdm = FakeMdm()
    g = WebCeoV3CeoIngressReadGateway(
        "/tmp/ceo.sock", client, mdm_reader=mdm
    )
    out = run(g.call("executive_mdm", {"view": "fleet"}))
    assert out["ok"] is True
    assert out["server_version"] == "1.5.0"
    assert out["data"]["schema"] == "mastermind.mosyle_fleet_snapshot.v1"
    assert out["grounding"] == {
        "mdm": "mosyle_business",
        "authority": "external_observation_only",
    }
    assert client.frames == []
    assert mdm.calls == [("fleet", None)]


def test_mdm_device_selection():
    mdm = FakeMdm()
    out = run(gateway(mdm).call(
        "executive_mdm", {"view": "device", "hostname": "mini-01"}
    ))
    assert out["ok"] is True
    assert out["data"]["schema"] == "mastermind.mosyle_device.v1"
    assert mdm.calls == [("device", "mini-01")]


@pytest.mark.parametrize(
    "code,public_code",
    [
        ("credential_refused", "backend_refused"),
        ("credential_unavailable", "backend_unavailable"),
        ("provider_unavailable", "backend_unavailable"),
        ("invalid_response", "backend_unavailable"),
        ("output_too_large", "output_too_large"),
        ("not_found", "not_found"),
    ],
)
def test_mdm_failures_are_typed_and_never_host_offline(code, public_code):
    mdm = FakeMdm(error=MosyleTelemetryError(code, "telemetry failed"))
    out = run(gateway(mdm).call("executive_mdm", {"view": "fleet"}))
    assert out["ok"] is False
    assert out["error"]["code"] == public_code
    assert "offline" not in json.dumps(out).lower()


def test_existing_executive_read_still_uses_ceo_ingress_and_is_v3_stamped():
    client = FakeIngressClient()
    g = WebCeoV3CeoIngressReadGateway(
        "/tmp/ceo.sock", client, mdm_reader=FakeMdm()
    )
    out = run(g.call("executive_state", {}))
    assert out["ok"] is True
    assert out["data"]["mastermind"]["sha"] == "a" * 40
    assert out["data"]["runtime_counts"]["jobs"]["total"] == 1
    assert out["server_version"] == v3.WEB_CEO_V3_SERVER_VERSION
    assert client.frames[0]["tool"] == "executive_state"


def test_mdm_tool_spec_is_static_and_read_only():
    assert v3.MDM_TOOL_SPEC.name == "executive_mdm"
    assert v3.MDM_TOOL_SPEC.annotations["readOnlyHint"] is True
    assert v3.MDM_TOOL_SPEC.annotations["destructiveHint"] is False


def test_current_installed_selector_adds_v3_without_expanding_old_validator():
    assert v3.validate_installed_mcp_profile_current("legacy") == "legacy"
    assert v3.validate_installed_mcp_profile_current("web_ceo_v2") == "web_ceo_v2"
    assert v3.validate_installed_mcp_profile_current("web_ceo_v3") == "web_ceo_v3"
    assert v3.validate_installed_mcp_profile_current("personal_read") == "personal_read"
    with pytest.raises(ValueError):
        v2.validate_installed_mcp_profile("web_ceo_v3")
    with pytest.raises(ValueError):
        v2.validate_installed_mcp_profile("personal_read")


def test_service_owned_session_credential_resolves_without_secret_repr(
    tmp_path, monkeypatch
):
    path = tmp_path / "mosyle-readonly.json"
    path.write_text(
        json.dumps(
            {
                "auth_mode": "session_login",
                "access_token": "a" * 32,
                "email": "api-user@example.com",
                "password": "secret123",
            }
        )
    )
    path.chmod(0o600)
    # Some macOS temp roots inherit group wheel even when the test process runs
    # as staff. Model the service-owned contract explicitly instead of relying
    # on filesystem inheritance so the positive case is portable.
    os.chown(path, -1, os.getegid())
    monkeypatch.setattr(credential_file, "_validate_parent", lambda _path: None)
    monkeypatch.setattr(
        credential_file, "_has_acl", lambda _path, _identity, _descriptor: False
    )
    source = FileMosyleCredentialSource(
        path=path, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )
    credential = run(source.resolve())
    assert isinstance(credential, MosyleCredential)
    assert credential.auth_mode == "session_login"
    assert credential.access_token == "a" * 32
    assert credential.email == "api-user@example.com"
    assert credential.password == "secret123"
    shown = repr(credential)
    assert "a" * 8 not in shown
    assert "api-user@example.com" not in shown
    assert "secret123" not in shown


@pytest.mark.parametrize("axis", ["uid", "gid"])
def test_service_owned_credential_file_refuses_identity_mismatch(
    tmp_path, monkeypatch, axis
):
    path = tmp_path / "mosyle-readonly.json"
    path.write_text(json.dumps({"auth_mode": "jwt", "access_token": "a" * 32}))
    path.chmod(0o600)
    os.chown(path, -1, os.getegid())
    monkeypatch.setattr(credential_file, "_validate_parent", lambda _path: None)
    monkeypatch.setattr(
        credential_file, "_has_acl", lambda _path, _identity, _descriptor: False
    )
    expected_uid = os.geteuid() + (1 if axis == "uid" else 0)
    expected_gid = os.getegid() + (1 if axis == "gid" else 0)
    source = FileMosyleCredentialSource(
        path=path, expected_uid=expected_uid, expected_gid=expected_gid
    )
    with pytest.raises(MosyleCredentialFileError):
        run(source.resolve())


def test_service_owned_credential_file_refuses_unsafe_mode(tmp_path, monkeypatch):
    path = tmp_path / "mosyle-readonly.json"
    path.write_text(json.dumps({"auth_mode": "jwt", "access_token": "a" * 32}))
    path.chmod(0o644)
    os.chown(path, -1, os.getegid())
    monkeypatch.setattr(credential_file, "_validate_parent", lambda _path: None)
    monkeypatch.setattr(
        credential_file, "_has_acl", lambda _path, _identity, _descriptor: False
    )
    source = FileMosyleCredentialSource(
        path=path, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )
    with pytest.raises(MosyleCredentialFileError):
        run(source.resolve())


@pytest.mark.parametrize(
    "value",
    [
        b"",
        b"not-json",
        json.dumps({"auth_mode": "jwt", "access_token": "short"}).encode(),
        json.dumps(
            {
                "auth_mode": "jwt",
                "access_token": "a" * 32,
                "bearer_token": "b" * 32,
            }
        ).encode(),
        json.dumps(
            {"auth_mode": "session_login", "access_token": "a" * 32}
        ).encode(),
        json.dumps(
            {
                "auth_mode": "jwt",
                "access_token": "a" * 32,
                "password": "nope",
            }
        ).encode(),
    ],
)
def test_credential_parser_refuses_invalid_or_dynamic_bearer_shape(value):
    with pytest.raises(MosyleCredentialFileError):
        credential_file._parse_credential(value)


def test_installed_network_config_accepts_exact_v3_profile():
    from ops.executive_os import executive_mcp_entry as entry

    raw = {
        "schema": "mastermind.executive_mcp_install.v1",
        "release_sha": "a" * 40,
        "service_uid": 458,
        "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
        "port": 8443,
        "policies": {},
        "audit_root": "/var/log/mastermind-executive/mcp-auth",
        "executive_mcp_profile": "web_ceo_v3",
    }
    assert entry.validate_document(raw) == raw


# Reader failures are fixture responses; these tests open no socket and do not
# invoke an installed provider, credential source, or MDM client.
_DIAGNOSTIC_PRIVATE_DETAIL = "UNTRUSTED_READER_DETAIL /private/fixture-only"


class _FailedReadIngressClient:
    def __init__(self, response):
        self.response = response
        self.frames = []

    async def send_frame(self, _path, frame):
        self.frames.append(frame)
        return self.response


def _reader_failure_response(reason, boundary="outer"):
    if boundary == "inner":
        result = legacy.error_envelope(
            "executive_state",
            mode=legacy.ServerMode.READONLY,
            generated_at="2026-09-23T06:00:00Z",
            code=reason,
            message=_DIAGNOSTIC_PRIVATE_DETAIL,
        )
        result["server_version"] = v2.WEB_CEO_V2_SERVER_VERSION
        return CeoIngressResponse(
            transport=TRANSPORT_SENT_OK, ok=True, result=result,
            detail=_DIAGNOSTIC_PRIVATE_DETAIL,
        )
    return CeoIngressResponse(
        transport=TRANSPORT_SENT_OK, ok=False,
        error={"code": reason, "message": _DIAGNOSTIC_PRIVATE_DETAIL},
        detail=_DIAGNOSTIC_PRIVATE_DETAIL,
    )


def _diagnostic_reader(response):
    client = _FailedReadIngressClient(response)
    mdm = FakeMdm()
    reader = WebCeoV3CeoIngressReadGateway(
        "/tmp/fixture-only.sock", client, mdm_reader=mdm
    )
    return reader, client, mdm


@pytest.mark.parametrize(
    "boundary,reason",
    [
        ("outer", "peer_credentials_unavailable"),
        ("outer", "peer_denied"),
        ("outer", "ingress_unavailable"),
        ("outer", "unsupported_ingress_schema"),
        ("outer", "backend_unavailable"),
        ("outer", "grounding_unavailable"),
        ("outer", "internal_error"),
        ("inner", "backend_unavailable"),
        ("inner", "grounding_unavailable"),
        ("inner", "internal_error"),
        ("inner", "timeout"),
    ],
)
def test_reader_diagnostic_preserves_only_a_qualified_reason(boundary, reason):
    reader, client, mdm = _diagnostic_reader(
        _reader_failure_response(reason, boundary)
    )
    result = run(reader.call("executive_state", {}))
    assert result["ok"] is False
    assert result["mode"] == "readonly"
    assert result["server_version"] == "1.5.0"
    assert result["data"] is None
    assert result["grounding"] == {}
    assert set(result["error"]) == {"code", "message"}
    assert result["error"]["code"] == "backend_unavailable"
    assert result["error"]["message"] == (
        "Executive reader is unavailable in the installed backend. "
        "Read-only describes this read operation; submission and "
        "execution readiness were not observed. "
        f"Upstream reason: {reason}."
    )
    assert "UNTRUSTED_READER_DETAIL" not in json.dumps(result)
    assert "/private/fixture-only" not in json.dumps(result)
    assert len(client.frames) == 1
    assert client.frames[0]["tool"] == "executive_state"
    assert client.frames[0]["arguments"] == {}
    assert mdm.calls == []


@pytest.mark.parametrize(
    "case",
    [
        "not_sent",
        "sent_unknown",
        "not_sent_with_error",
        "sent_unknown_with_error",
        "outer_timeout",
        "unknown_code",
        "non_string_code",
        "outer_result_and_error",
        "outer_non_boolean_ok",
        "inner_extra_error_field",
        "inner_wrong_version",
    ],
)
def test_reader_diagnostic_does_not_qualify_an_untrusted_response(case):
    from integrations.mastermind_executive_app.gateway import (
        TRANSPORT_NOT_SENT,
        TRANSPORT_SENT_UNKNOWN,
    )

    if case in {"not_sent", "sent_unknown"}:
        response = CeoIngressResponse(
            transport=(
                TRANSPORT_NOT_SENT if case == "not_sent"
                else TRANSPORT_SENT_UNKNOWN
            ),
            detail=_DIAGNOSTIC_PRIVATE_DETAIL,
        )
    elif case in {"not_sent_with_error", "sent_unknown_with_error"}:
        response = CeoIngressResponse(
            transport=(
                TRANSPORT_NOT_SENT if case == "not_sent_with_error"
                else TRANSPORT_SENT_UNKNOWN
            ),
            ok=False,
            error={"code": "ingress_unavailable", "message": _DIAGNOSTIC_PRIVATE_DETAIL},
        )
    elif case in {"outer_timeout", "unknown_code", "non_string_code"}:
        reason = {
            "outer_timeout": "timeout",  # Not admitted by the outer wire.
            "unknown_code": "ingress_unavailable UNTRUSTED_READER_DETAIL",
            "non_string_code": ["ingress_unavailable"],
        }[case]
        response = _reader_failure_response(reason)
    elif case in {"outer_result_and_error", "outer_non_boolean_ok"}:
        response = CeoIngressResponse(
            transport=TRANSPORT_SENT_OK,
            ok=False if case == "outer_result_and_error" else 0,
            result={} if case == "outer_result_and_error" else None,
            error={"code": "ingress_unavailable", "message": _DIAGNOSTIC_PRIVATE_DETAIL},
        )
    else:
        response = _reader_failure_response("backend_unavailable", "inner")
        if case == "inner_extra_error_field":
            response.result["error"]["upstream_reason"] = "ingress_unavailable"
        else:
            response.result["server_version"] = "unqualified"

    reader, client, mdm = _diagnostic_reader(response)
    result = run(reader.call("executive_state", {}))
    assert result["ok"] is False
    assert result["error"]["code"] == "backend_unavailable"
    assert "Upstream reason:" not in result["error"]["message"]
    assert "UNTRUSTED_READER_DETAIL" not in json.dumps(result)
    assert "/private/fixture-only" not in json.dumps(result)
    assert len(client.frames) == 1
    assert mdm.calls == []


@pytest.mark.parametrize(
    "reason,public_code",
    [
        ("authority_refused", "backend_refused"),
        ("backend_refused", "backend_refused"),
        ("response_too_large", "output_too_large"),
    ],
)
def test_reader_diagnostic_preserves_existing_refusal_classification(reason, public_code):
    reader, client, mdm = _diagnostic_reader(_reader_failure_response(reason))
    result = run(reader.call("executive_state", {}))
    assert result["error"]["code"] == public_code
    assert "Upstream reason:" not in result["error"]["message"]
    assert "UNTRUSTED_READER_DETAIL" not in json.dumps(result)
    assert len(client.frames) == 1
    assert mdm.calls == []


@pytest.mark.parametrize("profile", ["legacy", "web_ceo", "web_ceo_v2"])
def test_reader_diagnostic_keeps_prior_profile_messages_frozen(profile):
    from integrations.mastermind_executive_app.gateway import (
        CeoIngressReadGateway,
        WebCeoCeoIngressReadGateway,
        WebCeoV2CeoIngressReadGateway,
    )

    cls = {
        "legacy": CeoIngressReadGateway,
        "web_ceo": WebCeoCeoIngressReadGateway,
        "web_ceo_v2": WebCeoV2CeoIngressReadGateway,
    }[profile]
    response = _reader_failure_response("ingress_unavailable")
    expected = (
        "Executive reader is unavailable in the installed backend. "
        "Read-only describes this read operation; submission and "
        "execution readiness were not observed."
    )
    # Direct class invocation remains compatible with the prior static helper.
    assert cls._read_failure(response) == ("backend_unavailable", expected)
    client = _FailedReadIngressClient(response)
    result = run(cls("/tmp/fixture-only.sock", client).call("executive_state", {}))
    assert result["error"] == {"code": "backend_unavailable", "message": expected}
    assert len(client.frames) == 1


def test_reader_diagnostic_invalid_arguments_do_not_send():
    reader, client, mdm = _diagnostic_reader(
        _reader_failure_response("ingress_unavailable")
    )
    result = run(reader.call("executive_state", {"unexpected": True}))
    assert result["error"]["code"] == "invalid_input"
    assert "Upstream reason:" not in result["error"]["message"]
    assert client.frames == []
    assert mdm.calls == []
