import asyncio
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
            data={"preserved": True},
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
    assert v3.WEB_CEO_V3_SERVER_VERSION == "1.3.0"
    assert v3.web_ceo_v3_tool_names()[:-2] == v2.web_ceo_v2_tool_names()[:-1]
    assert v3.web_ceo_v3_tool_names()[-2:] == (
        "executive_mdm",
        "submit_ceo_intent",
    )


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"view": "fleet", "hostname": "mini-01"},
        {"view": "device"},
        {"view": "device", "hostname": "mini", "serial_number": "S1"},
        {"view": "other"},
    ],
)
def test_mdm_schema_and_validator_refuse_same_bad_shapes(bad):
    with pytest.raises(legacy.GatewayError):
        v3.validate_web_ceo_v3_tool_arguments("executive_mdm", bad)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, v3.MDM_TOOL_SPEC.input_schema)


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
    assert out["server_version"] == "1.3.0"
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
    assert out["data"] == {"preserved": True}
    assert out["server_version"] == "1.3.0"
    assert client.frames[0]["tool"] == "executive_state"


def test_mdm_tool_spec_is_static_and_read_only():
    assert v3.MDM_TOOL_SPEC.name == "executive_mdm"
    assert v3.MDM_TOOL_SPEC.annotations["readOnlyHint"] is True
    assert v3.MDM_TOOL_SPEC.annotations["destructiveHint"] is False


def test_current_installed_selector_adds_v3_without_expanding_old_validator():
    assert v3.validate_installed_mcp_profile_current("legacy") == "legacy"
    assert v3.validate_installed_mcp_profile_current("web_ceo_v2") == "web_ceo_v2"
    assert v3.validate_installed_mcp_profile_current("web_ceo_v3") == "web_ceo_v3"
    with pytest.raises(ValueError):
        v2.validate_installed_mcp_profile("web_ceo_v3")


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


def test_service_owned_credential_file_refuses_unsafe_mode(tmp_path, monkeypatch):
    path = tmp_path / "mosyle-readonly.json"
    path.write_text(json.dumps({"auth_mode": "jwt", "access_token": "a" * 32}))
    path.chmod(0o644)
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
