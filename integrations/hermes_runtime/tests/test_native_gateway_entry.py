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
    monkeypatch.setattr(control, "install_private_control", lambda *args: installed.append(args))
    home = tmp_path / "role-home"
    runner = SimpleNamespace(session_authority=SimpleNamespace(profile_id=str(home), instance_id="i", epoch=7),
                             session_runtime_descriptor=dict(instance_id="i", authority_epoch=7),
                             config=SimpleNamespace(multiplex_profiles=False))
    entry.bind_native_api(module, vendor=vendor, role_home=home, role="mmsecretary",
                          host="127.0.0.2", port=18766)
    assert asyncio.run(module.start_gateway_api(runner)) is handle
    assert calls == [(runner, "127.0.0.2", 18766)]
    assert installed == [(runner, home, "mmsecretary")]
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
