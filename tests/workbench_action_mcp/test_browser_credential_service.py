"""Actual v5 service acquisition/maintenance; synthetic issuer, no browser launch."""
import asyncio
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import tempfile

import pytest

from integrations.mastermind_browser_plugin import workbench_credentials as credentials
from integrations.workbench_action_mcp import service
from integrations.workbench_action_mcp.acquisition import AcquisitionReceipt, document_fingerprint
from integrations.workbench_action_mcp.readiness import config_fingerprint, encoded
from tests.workbench_action_mcp.test_browser_link_service import configuration
from tests.workbench_action_mcp.test_managed_readiness import expected_for
from tests.test_mastermind_browser_workbench_transport import Host


def configured(tmp_path, short):
    config, _grant, _native, document = configuration(tmp_path, short)
    remote = Host("service-credential")
    route = replace(remote.route, credential_file=tmp_path / "access.json")
    routes = tmp_path / "routes.json"
    routes.write_text(json.dumps({"schema": "mastermind.browser_fabric_routes.v1", "routes": [
        {**asdict(route), "credential_file": str(route.credential_file)}]}))
    routes.chmod(0o600)
    secret = tmp_path / "secret"
    secret.write_text("synthetic-enrolled-secret")
    secret.chmod(0o600)
    enrolled = tmp_path / "credentials.json"
    enrolled.write_text(json.dumps({"schema": credentials.ENROLLMENT_SCHEMA, "credentials": [{
        "host_ref": route.host_ref, "client_id": remote.client_id, "client_secret_file": str(secret),
        "policy": asdict(remote.policy)}]}))
    enrolled.chmod(0o600)
    document.update(schema=service.SERVICE_SCHEMA_V5, browser_fabric_routes_file=str(routes),
                    browser_fabric_credentials_file=str(enrolled))
    return service.parse_service_config(document), remote, route, document


@pytest.mark.parametrize("changed", [False, True])
def test_v5_consumes_enrollment_before_profile_activation_and_uses_current_local_admission(tmp_path, monkeypatch, changed):
    tmp_path.chmod(0o700)
    monkeypatch.setattr(credentials.file_owner, "_user_root", lambda: tmp_path)
    with tempfile.TemporaryDirectory(prefix="mmx-v5-", dir="/tmp") as directory:
        config, remote, route, document = configured(tmp_path, Path(directory))
        expected = expected_for(config)
        acquisition = AcquisitionReceipt(expected)
        activated, issued, created = [], [], []
        actual_publisher = credentials.WorkbenchCredentialPublisher
        def publisher(**kwargs):
            assert tuple(row.route for row in kwargs["enrollments"]) == (route,)
            async def acquire(**request):
                assert acquisition.digest == document_fingerprint(expected)
                assert request["client_id"] == remote.client_id
                issued.append("POST")
                return remote.token
            selected = actual_publisher(**kwargs, authenticator_factory=lambda row: remote.auth, acquire=acquire)
            created.append(selected)
            return selected
        monkeypatch.setattr(credentials, "WorkbenchCredentialPublisher", publisher)
        actual_sibling = service.create_browser_sibling
        def sibling(*args, **kwargs):
            deployed = actual_sibling(*args, **kwargs)
            async def activate(*args):
                assert acquisition.digest == document_fingerprint(expected)
                activated.append(True)
                return ()
            return replace(deployed, activate_configured_profiles=activate)
        monkeypatch.setattr(service, "create_browser_sibling", sibling)
        async def exercise():
            runtime = await service.create_runtime(config, acquisition=acquisition)
            try:
                if changed:
                    path = Path(config.browser_fabric_credentials_file)
                    original = path.read_bytes()
                    value = json.loads(original)
                    alternate = tmp_path / "alternate-secret"
                    alternate.write_text("synthetic-alternate-secret")
                    alternate.chmod(0o600)
                    value["credentials"][0]["client_secret_file"] = str(alternate)
                    # B is independently valid. Only the installed acquisition
                    # binding, not semantic parsing, can reject this change.
                    assert credentials.parse_enrollment(value, routes=(route,), enrollment_file=path)
                    path.write_text(json.dumps(value))
                    secure_read = service._secure_json
                    def acquired_then_restored(selected, **kwargs):
                        acquired = secure_read(selected, **kwargs)
                        if selected == str(path):
                            path.write_bytes(original)
                        return acquired
                    monkeypatch.setattr(service, "_secure_json", acquired_then_restored)
                    with pytest.raises(service.ServiceConfigurationError) as refused:
                        service.build_service_app(runtime, config, service.ServiceState(), acquisition=acquisition)
                    assert str(refused.value.__cause__) == "SERVICE_ACQUISITION_BINDING_CHANGED"
                    assert path.read_bytes() == original
                    assert not activated and not issued and not created
                    return
                state = service.ServiceState(socket_owned=True)
                app = service.build_service_app(runtime, config, state, acquisition=acquisition)
                assert not issued and not activated
                async with app.router.lifespan_context(app):
                    assert state.lifespan_started and service.is_ready(runtime, config, state)
                    assert state.credential_maintenance == ({"host_ref": route.host_ref, "status": "PUBLISHED"},)
                    assert len(activated) == len(issued) == 1
                    original = route.credential_file.read_bytes()
                    runtime.revoke()
                    assert await created[0].refresh() == ({"host_ref": route.host_ref, "status": "INACTIVE"},)
                    assert issued == ["POST"] and route.credential_file.read_bytes() == original
                assert state.lifespan_completed
            finally:
                await runtime.aclose(timeout=5)
        asyncio.run(exercise())


def test_v5_opt_in_is_closed_and_legacy_fingerprint_unchanged(tmp_path):
    with tempfile.TemporaryDirectory(prefix="mmx-v5-config-", dir="/tmp") as directory:
        config, _remote, _route, document = configured(tmp_path, Path(directory))
        assert config_fingerprint(config) == hashlib.sha256(encoded(asdict(config))).hexdigest()
        for schema in (service.SERVICE_SCHEMA_V3, service.SERVICE_SCHEMA_V4):
            with pytest.raises(service.ServiceConfigurationError):
                service.parse_service_config(dict(document, schema=schema))
        legacy_document = dict(document, schema=service.SERVICE_SCHEMA_V4)
        legacy_document.pop("browser_fabric_credentials_file")
        legacy = service.parse_service_config(legacy_document)
        previous_shape = asdict(legacy)
        previous_shape.pop("browser_fabric_credentials_file")
        assert config_fingerprint(legacy) == hashlib.sha256(encoded(previous_shape)).hexdigest()
        assert legacy.browser_fabric_credentials_file is None
        for value in (None, "relative.json"):
            with pytest.raises(service.ServiceConfigurationError):
                service.parse_service_config(dict(document, browser_fabric_credentials_file=value))


def test_enrollment_reader_preserves_cleanup_uncertainty(tmp_path, monkeypatch):
    with tempfile.TemporaryDirectory(prefix="mmx-v5-close-", dir="/tmp") as directory:
        config, _remote, _route, _document = configured(tmp_path, Path(directory))
        original = service.ServiceConfigurationError("SERVICE_STARTUP_CLEANUP_UNCERTAIN")
        def uncertain(*args, **kwargs):
            raise original
        monkeypatch.setattr(service, "_secure_json", uncertain)
        with pytest.raises(service.ServiceConfigurationError) as caught:
            service.create_browser_credential_publisher(object(), config, object())
        assert caught.value is original
