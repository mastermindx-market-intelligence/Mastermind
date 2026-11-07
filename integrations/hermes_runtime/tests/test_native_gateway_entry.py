"""Source/selection regressions; no host or provider acceptance claims."""
import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.hermes_runtime import native_gateway_entry as entry
from integrations.hermes_runtime import native_session_control as control
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.profile import dump_profile, load_profile
from integrations.hermes_harness.stack import compose_profile


def profile(tmp_path):
    return compose_profile("mmsecretary", state_dir=tmp_path / "state",
                           hermes_home=tmp_path / "state/current/hermes-home",
                           secrets_file=tmp_path / "keys/secret.env")


def test_native_profile_is_explicit_and_legacy_dump_stays_unchanged(tmp_path):
    legacy = profile(tmp_path)
    assert legacy.gateway_backend == "standalone" and "  backend:" not in dump_profile(legacy)
    selected = replace(legacy, gateway_backend=entry.BACKEND, gateway_host="127.0.0.2",
                       gateway_port=18765, backend_port=18766,
                       native_provider_id="byteplus-modelark.glm-5.3-flash")
    path = tmp_path / "profile.yaml"
    path.write_text(dump_profile(selected))
    assert load_profile(path).gateway_backend == entry.BACKEND
    for wrong in (replace(selected, gateway_host="127.0.0.1"),
                  replace(selected, backend_port=0), replace(selected, native_provider_id=None)):
        path.write_text(dump_profile(wrong))
        with pytest.raises(RuntimeRefusal):
            load_profile(path)


def test_fixed_api_uses_original_factory_and_private_control_without_vendor_class_patch(monkeypatch, tmp_path):
    vendor = tmp_path / "vendor"
    calls = []
    native_class = object()
    handle = object()
    async def factory(runner, *, host, port):
        calls.append((runner, host, port))
        return handle
    module = SimpleNamespace(start_gateway_api=factory, GatewayRuntimeAPI=native_class)
    monkeypatch.setattr(entry, "_digest", lambda *a, **k: entry.RUN_API_SHA256)
    installed = []
    monkeypatch.setattr(control, "install_private_control", lambda *args, **kwargs: installed.append((args, kwargs)))
    home = tmp_path / "role-home"
    runner = SimpleNamespace(session_authority=SimpleNamespace(profile_id=str(home), instance_id="i", epoch=7),
                             session_runtime_descriptor=dict(instance_id="i", authority_epoch=7),
                             config=SimpleNamespace(multiplex_profiles=False))
    entry.bind_native_api(module, vendor=vendor, role_home=home, role="mmsecretary",
                          host="127.0.0.2", port=18766)
    assert asyncio.run(module.start_gateway_api(runner)) is handle
    assert calls == [(runner, "127.0.0.2", 18766)]
    assert installed == [((runner, home, "mmsecretary"),
                          {"implementation_sha": None, "session_enrollment": None})]
    assert module.GatewayRuntimeAPI is native_class
    with pytest.raises(TypeError):
        module.start_gateway_api(runner, port=0)
    with pytest.raises(RuntimeRefusal, match="NATIVE_API_ALREADY_BOUND"):
        entry.bind_native_api(module, vendor=vendor, role_home=home, role="mmsecretary",
                              host="127.0.0.2", port=18766)


def test_changed_native_authority_never_enters_factory(monkeypatch, tmp_path):
    async def forbidden(*args, **kwargs):
        raise AssertionError("native listener must not start")
    module = SimpleNamespace(start_gateway_api=forbidden)
    monkeypatch.setattr(entry, "_digest", lambda *a, **k: entry.RUN_API_SHA256)
    entry.bind_native_api(module, vendor=tmp_path, role_home=tmp_path, role="mmsecretary",
                          host="127.0.0.2", port=18766)
    runner = SimpleNamespace(session_authority=None, session_runtime_descriptor={})
    with pytest.raises(RuntimeRefusal, match="NATIVE_PROFILE_AUTHORITY_MISMATCH"):
        asyncio.run(module.start_gateway_api(runner))


def test_missing_custody_refuses_before_any_credential_or_child(tmp_path, monkeypatch):
    from integrations.hermes_runtime import supervisor
    selected = replace(profile(tmp_path), gateway_backend=entry.BACKEND)
    class UnreadableSecrets:
        def __getattribute__(self, name):
            raise AssertionError("credential access before native custody")
    runtime = supervisor.ServiceRuntime(selected, UnreadableSecrets(), Path("/inert/hermes"))
    with pytest.raises(RuntimeRefusal, match="NATIVE_STARTUP_CUSTODY_REQUIRED"):
        runtime.start()
    assert runtime.child_starts == 0 and runtime.gateway is None


def test_native_git_trust_is_exact_and_process_scoped(tmp_path, monkeypatch):
    from integrations.hermes_runtime import supervisor
    from integrations.hermes_runtime.secrets import Secrets
    vendor = tmp_path / "qualified-vendor"
    selected = replace(profile(tmp_path), gateway_backend=entry.BACKEND)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "safe.directory")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "*")
    launch = SimpleNamespace(recipe={"vendor_root": str(vendor)})
    secrets = Secrets("health-credential-value", "hermes", "dashboard-credential-value",
                      {"PROVIDER_KEY": "model-credential-value"})
    runtime = supervisor.ServiceRuntime(selected, secrets, Path("/inert/hermes"), native_launch=launch)
    actual = runtime._registry_env()
    assert all(actual[key] == value for key, value in entry.native_git_environment(vendor).items())
    assert actual["GIT_CONFIG_VALUE_0"] == str(vendor)
    assert actual["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert actual["GIT_OPTIONAL_LOCKS"] == "0"
    assert "model-credential-value" not in actual.values()
    assert "dashboard-credential-value" not in actual.values()
    assert "health-credential-value" not in actual.values()
    assert __import__("os").environ["GIT_CONFIG_VALUE_0"] == "*"


def test_native_installer_pin_check_uses_selected_command_environment(tmp_path, monkeypatch):
    from integrations.hermes_runtime import install as installer
    seen = []
    def run(argv, **kwargs):
        seen.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=entry.PINNED_UPSTREAM_SHA + "\n")
    monkeypatch.setattr(installer.subprocess, "run", run)
    chosen = entry.native_git_environment(tmp_path)
    installer.assert_checkout_sha(tmp_path, native_environment=chosen)
    assert seen[0][1]["env"] == chosen
    assert seen[0][0] == ["git", "-C", str(tmp_path), "rev-parse", "HEAD"]


def test_qualified_dependency_preload_precedes_native_bootstrap(monkeypatch, tmp_path):
    from integrations.hermes_runtime import profile as profiles, supervisor, system_service, role_isolation, tcp_sandbox
    selected = replace(profile(tmp_path), gateway_backend=entry.BACKEND, gateway_host="127.0.0.2",
                       gateway_port=18765, backend_port=18766)
    selected.hermes_home.mkdir(parents=True)
    role_home = selected.hermes_home.resolve() / "profiles/mmsecretary"
    vendor = tmp_path / "qualified-vendor"
    order = []
    launch = SimpleNamespace(row={"role": "mmsecretary", "state_dir": str(selected.state_dir)},
                             recipe={"vendor_root": str(vendor)}, launcher=Path("/inert/hermes"),
                             qualify=lambda *args: order.append("qualify"),
                             check=lambda: order.append("source-check"))
    monkeypatch.setattr(profiles, "load_profile", lambda path: selected)
    monkeypatch.setattr(system_service, "assert_root_service_cgroup", lambda role: order.append("cgroup"))
    monkeypatch.setattr(system_service, "assert_role_network_profile", lambda p: order.append("network"))
    monkeypatch.setattr(role_isolation, "assert_role_credential_isolation", lambda p: order.append("credentials"))
    monkeypatch.setattr(tcp_sandbox, "enforce_role_tcp_ports", lambda p: order.append("ports"))
    monkeypatch.setattr(supervisor, "expected_disabled_mcp", lambda p: {})
    monkeypatch.setattr(entry, "prepare_vendor", lambda p: order.append("vendor"))
    monkeypatch.setenv("HERMES_HOME", str(selected.hermes_home.resolve()))
    for key, value in entry.native_git_environment(vendor).items():
        monkeypatch.setenv(key, value)
    original_import = entry.importlib.import_module
    def import_module(name, *args, **kwargs):
        if name == "urllib3.util.connection":
            order.append("qualified-dependency")
            return object()
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(entry.importlib, "import_module", import_module)
    def native_module(name, vendor):
        order.append(name)
        if name == "hermes_cli.main":
            return SimpleNamespace(explicit_cli_profile=lambda: "mmsecretary",
                                   main=lambda: order.append("native-main"))
        return SimpleNamespace(get_process_hermes_home=lambda: role_home)
    monkeypatch.setattr(entry, "_vendor_module", native_module)
    monkeypatch.setattr(entry.sys, "argv", ["original"])
    assert entry.run(launch, ["-p", "mmsecretary", "tools", "list", "--platform", "cli"]) == 0
    assert order.index("ports") < order.index("qualified-dependency") < order.index("hermes_cli.main")
    assert order.index("qualified-dependency") < order.index("source-check") < order.index("native-main")
