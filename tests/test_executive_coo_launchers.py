"""Existing entrypoints bind the concrete COO providers without activating hosts."""
from __future__ import annotations
import copy
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tests import test_executive_coo_host as helpers
from tests import test_executive_coo_install_binding as install
from ops.executive_os import executive_mcp_entry as entry
from integrations.executive_mcp.web_ceo import WEB_CEO_V2_PROFILE
from integrations.mastermind_executive_app.app import AppSettings
from integrations.mastermind_executive_app.gateway import load_app_policies
from integrations.mastermind_executive_app.coo_installed import CooFactsClient


def test_mcp_launcher_binds_network_only_fact_providers(tmp_path):
    _, coo, _, _ = helpers.setup(tmp_path)
    raw = install.base_document()
    raw.update(coo=coo, executive_mcp_profile=WEB_CEO_V2_PROFILE)
    source = tmp_path / raw["release_sha"]
    settings = AppSettings(policies=load_app_policies(raw["policies"]), mastermind_root=source,
        macro_root_flag=None, environ={}, ceo_ingress_socket_path=raw["ceo_ingress_socket_path"], read_from_ceo_ingress=True)
    selected = entry.build_installed_coo_settings(raw, source, tmp_path / "mcp.json", settings)
    assert isinstance(selected.authority_provider.__self__, CooFactsClient)
    assert selected.authority_provider.__self__ is selected.mission_provider.__self__
    assert selected.executive is settings
    raw["coo"]["missions"] = []
    assert entry.build_installed_coo_settings(raw, source, tmp_path / "mcp.json", settings) is None


from integrations.executive_mcp.web_ceo_v3 import WEB_CEO_V3_PROFILE
from integrations.executive_mcp.personal_read import PERSONAL_READ_PROFILE


@pytest.mark.parametrize("profile", ["legacy", PERSONAL_READ_PROFILE])
def test_mission_activation_cannot_replace_a_different_ceo_profile(tmp_path, profile):
    _, coo, _, _ = helpers.setup(tmp_path)
    raw = install.base_document(); raw.update(coo=coo, executive_mcp_profile=profile)
    with pytest.raises(ValueError): entry.validate_document(raw)


@pytest.mark.parametrize("profile", [WEB_CEO_V2_PROFILE, WEB_CEO_V3_PROFILE])
def test_mission_activation_accepts_supported_web_ceo_profiles(tmp_path, profile):
    _, coo, _, _ = helpers.setup(tmp_path)
    raw = install.base_document(); raw.update(coo=coo, executive_mcp_profile=profile)
    assert entry.validate_document(raw) == raw
    source = tmp_path / raw["release_sha"]
    settings = AppSettings(policies=load_app_policies(raw["policies"]), mastermind_root=source,
        macro_root_flag=None, environ={}, ceo_ingress_socket_path=raw["ceo_ingress_socket_path"],
        read_from_ceo_ingress=True)
    selected = entry.build_installed_coo_settings(raw, source, tmp_path / "mcp.json", settings)
    assert isinstance(selected.authority_provider.__self__, CooFactsClient)
    assert selected.executive is settings


@pytest.mark.parametrize("source_available", [True, False])
def test_control_factory_wires_existing_workspace_into_guard(tmp_path, monkeypatch, source_available):
    from scripts import executive_os_phase1c as cli
    from tests.test_c1_ceo_ingress_composition import _raw
    from tests.test_workspace_read_app import _workspace_policy
    from control_plane import executive_worker_broker, workspace_source_join
    from control_plane.coo_principal_host import CooHostProvider
    raw = _raw(tmp_path)
    host, _, _, _ = helpers.setup(tmp_path)
    authority = {"schema": "mastermind.workspace_acquisition_bindings.v1", "profiles": {
        key: {"enabled": False, "binding": None} for key in ("web", "mac")}}
    raw.update(ceo_ingress_app_peer_uid=458, ceo_ingress_app_armed=False,
        ceo_ingress_app_macro_root=tmp_path / "macro", workspace_control_room={"port": 8787},
        workspace_acquisition={}, workspace_resource_policy=json.loads(json.dumps(dataclasses.asdict(_workspace_policy()))),
        ceo_ingress_app_boot_python=tmp_path / "sealed-python", executive_mcp_profile=WEB_CEO_V2_PROFILE,
        coo_principal_armed=True)
    monkeypatch.setattr(cli, "_attest_app_boot_runtime", lambda p: p)
    monkeypatch.setattr(cli, "activate_launchd_socket", lambda name: object())
    monkeypatch.setattr(executive_worker_broker, "WorkerBrokerClient", lambda *a, **k: object())
    captured = {}
    def composer(**kwargs):
        captured.update(kwargs)
        return lambda stamp: {}
    monkeypatch.setattr(workspace_source_join, "build_workspace_composer", composer)
    class Service:
        def __init__(self, config, **kwargs):
            self.kwargs = kwargs
    monkeypatch.setattr(cli, "ExecutiveControlService", Service)
    if not source_available:
        with pytest.raises(cli.ServiceError, match="sealed source"):
            cli._service_from_config(raw, workspace_acquisition_loader=lambda: authority)
        return
    service = cli._service_from_config(raw, workspace_acquisition_loader=lambda: authority,
        coo_source=host.source)
    binding = service.kwargs["ceo_ingress_app_binding"]
    assert binding.armed is False and binding.principal_admission_armed is True
    actual_runtime = object()
    service._require_runtime = lambda: actual_runtime
    service._namespace_custody = SimpleNamespace(bound_runtime=lambda actual: actual)
    provider = binding.principal_facts_factory(actual_runtime)
    assert type(provider) is CooHostProvider and provider.source is host.source
    assert provider.workspace.runtime is actual_runtime
    assert callable(binding.principal_admission_guard)


def test_control_policy_and_grant_projection_are_stdlib_only(tmp_path):
    import subprocess
    import sys
    _, coo, _, registry = helpers.setup(tmp_path)
    raw = install.base_document(); raw.update(coo=coo, executive_mcp_profile=WEB_CEO_V2_PROFILE)
    root = str(Path(__file__).resolve().parents[1])
    code = (
        "import sys,json;sys.path.insert(0," + repr(root) + ");"
        "from ops.executive_os import executive_mcp_entry as e;"
        "from ops.executive_os.coo_principal_host import CooInstalledSource;"
        "from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry;"
        "raw=json.loads(sys.stdin.read());e.validate_document(raw);"
        "assert 'integrations.mastermind_executive_app.os_commission_client' not in sys.modules;"
        "source=CooInstalledSource(lambda:raw['coo'],lambda:ExecutionCapabilityRegistry.load("
        + repr(str(registry)) + ",source_root=" + repr(root) + "));"
        "source.snapshot('WS:EXECUTIVE-CAPACITY-FABRIC');"
        "assert not {'mcp','httpx','jwt'}.intersection(sys.modules);print('STDLIB_CONTROL_OK')"
    )
    run = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code],
        input=json.dumps(raw), capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "STDLIB_CONTROL_OK"


@pytest.mark.parametrize("enabled", [False, True])
def test_release_only_profile_rejects_dormant_coo_configuration(tmp_path, enabled):
    """A role-isolated release listener must not carry an unused COO binding."""
    from integrations.executive_mcp.release_control import RELEASE_CONTROL_PROFILE
    _, coo, _, _ = helpers.setup(tmp_path)
    coo["missions"] = []
    coo["binding"]["enabled"] = enabled
    raw = install.base_document()
    raw.update(coo=coo, executive_mcp_profile=RELEASE_CONTROL_PROFILE)
    with pytest.raises(ValueError, match="Release control profile refuses optional mounts"):
        entry.validate_document(raw)


@pytest.mark.parametrize("profile", ["release-control-v1", "web-ceo-release-v1"])
def test_release_profiles_do_not_select_coo_mission_builder(tmp_path, profile):
    from integrations.executive_mcp.release_control import RELEASE_CONTROL_PROFILE
    from integrations.executive_mcp.web_ceo_release import WEB_CEO_RELEASE_PROFILE
    selected = {"release-control-v1": RELEASE_CONTROL_PROFILE,
                "web-ceo-release-v1": WEB_CEO_RELEASE_PROFILE}[profile]
    _, coo, _, _ = helpers.setup(tmp_path)
    raw = install.base_document()
    raw.update(coo=coo, executive_mcp_profile=selected)
    with pytest.raises(ValueError):
        entry.validate_document(raw)
