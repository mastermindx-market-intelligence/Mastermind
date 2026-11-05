"""Source-only publisher composition; no PID1, provider or installed admission."""
from __future__ import annotations

import argparse
import dataclasses
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from common import hermes_role_status_contract as wire
from common import workspace_byok_read_contract as workspace
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime import cli, secrets, supervisor
from integrations.hermes_runtime import role_status_publisher as publisher
from integrations.hermes_runtime.constants import CONFIG_EXIT
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.system_service import render_host_unit

SHA = "a" * 40
BOOT = "12345678-1234-1234-1234-123456789abc"
INVOCATION = "1" * 32


def _profile(tmp_path, role="mmmeta"):
    return compose_profile(role, state_dir=tmp_path / (role + "-state"),
                           hermes_home=tmp_path / (role + "-home"),
                           secrets_file=tmp_path / (role + ".env"))


def _metadata(role="mmmeta", state="ABSENT"):
    return {"schema": wire.METADATA_SCHEMA, "role": role, "state": state,
            "reason": "INSTALL_MANIFEST_ABSENT" if state == "ABSENT" else "METADATA_READ_FAILED",
            "source_binding": "NOT_ATTESTED", "proof": workspace.proof()}


def _context(profile, address="/tmp/fixture-notify"):
    return publisher.RoleStatusPublisher(profile.role, profile.state_dir, SHA, BOOT,
                                         INVOCATION, os.getpid(), address)


def _environment(monkeypatch):
    monkeypatch.setattr(publisher.sys, "platform", "linux")
    monkeypatch.setenv(publisher.IMPLEMENTATION_ENV, SHA)
    monkeypatch.setenv("INVOCATION_ID", INVOCATION)
    monkeypatch.setenv("NOTIFY_SOCKET", "/run/systemd/notify")
    monkeypatch.setenv("SYSTEMD_EXEC_PID", str(os.getpid()))
    monkeypatch.setattr(publisher, "_read_boot_id", lambda: BOOT)


def test_absent_optional_label_reads_no_boot_metadata_or_socket(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    monkeypatch.delenv(publisher.IMPLEMENTATION_ENV, raising=False)
    forbidden = Mock(side_effect=AssertionError("optional publication is disabled"))
    monkeypatch.setattr(publisher, "_read_boot_id", forbidden)
    monkeypatch.setattr(publisher, "role_metadata", forbidden)
    monkeypatch.setattr(publisher, "socket", SimpleNamespace(socket=forbidden))
    assert publisher.publisher_from_process(profile) is None
    forbidden.assert_not_called()


@pytest.mark.parametrize("bad", ["sha", "empty-sha", "invocation", "zero-invocation",
                                  "missing-notify", "relative-notify", "long-notify",
                                  "newline-notify", "boot", "other-pid", "platform"])
def test_explicit_malformed_context_is_refused_before_credentials(tmp_path, monkeypatch, bad):
    profile = _profile(tmp_path)
    _environment(monkeypatch)
    if bad == "sha": monkeypatch.setenv(publisher.IMPLEMENTATION_ENV, "wrong")
    elif bad == "empty-sha": monkeypatch.setenv(publisher.IMPLEMENTATION_ENV, "")
    elif bad == "invocation": monkeypatch.delenv("INVOCATION_ID")
    elif bad == "zero-invocation": monkeypatch.setenv("INVOCATION_ID", "0" * 32)
    elif bad == "missing-notify": monkeypatch.delenv("NOTIFY_SOCKET")
    elif bad == "relative-notify": monkeypatch.setenv("NOTIFY_SOCKET", "relative/socket")
    elif bad == "long-notify": monkeypatch.setenv("NOTIFY_SOCKET", "/" + "x" * 108)
    elif bad == "newline-notify": monkeypatch.setenv("NOTIFY_SOCKET", "/run/notify\nREADY=1")
    elif bad == "boot": monkeypatch.setattr(publisher, "_read_boot_id", lambda: "invalid")
    elif bad == "other-pid": monkeypatch.setenv("SYSTEMD_EXEC_PID", str(os.getpid() + 1))
    else: monkeypatch.setattr(publisher.sys, "platform", "darwin")
    with pytest.raises(RuntimeRefusal, match="ROLE_STATUS_CONTEXT_INVALID"):
        publisher.publisher_from_process(profile)


def test_context_uses_actual_process_and_explicit_implementation_label(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    _environment(monkeypatch)
    context = publisher.publisher_from_process(profile)
    assert context.role == profile.role and context.state_dir == profile.state_dir
    assert context.implementation_sha == SHA and context.implementation_sha != profile.sha
    assert context.host_boot_id == BOOT and context.invocation_id == INVOCATION
    assert context.process_pid == os.getpid()
    assert publisher._notification_address("@systemd-notify") == "\0systemd-notify"
    from ops.executive_os.hermes_role_metadata_observer import _installed_source_identity
    assert _installed_source_identity(SHA) is None


def test_real_unix_datagrams_reread_metadata_and_preserve_original_observation(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    reader = Mock(side_effect=[_metadata(), _metadata(state="UNAVAILABLE")])
    monkeypatch.setattr(publisher, "role_metadata", reader)
    stamps = iter([1_800_000_000_000_000_000, 1_800_000_005_000_000_000])
    mono = iter([100_000_000_000, 105_000_000_000])
    monkeypatch.setattr(publisher, "time", SimpleNamespace(time_ns=lambda: next(stamps),
                                                         monotonic_ns=lambda: next(mono)))
    with tempfile.TemporaryDirectory(prefix="mm-role-status-", dir="/tmp") as directory:
        address = str(Path(directory) / "notify")
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
            receiver.bind(address)
            receiver.settimeout(0.5)
            context = _context(profile, address)
            documents = []
            for _ in range(2):
                assert context.publish() is True
                data = receiver.recv(4096)
                assert data.startswith(b"STATUS=") and b"\n" not in data
                assert len(data) <= 7 + wire.MAX_STATUS_BYTES
                documents.append(wire.decode_status_text(data[7:].decode(), expected_role=profile.role))
    assert reader.call_args_list[0] == reader.call_args_list[1]
    assert reader.call_args_list[0].args == (profile.state_dir, profile.role)
    assert [doc["metadata"]["state"] for doc in documents] == ["ABSENT", "UNAVAILABLE"]
    assert [doc["observed_at_ms"] for doc in documents] == [1_800_000_000_000, 1_800_000_005_000]
    assert all(doc["metadata"]["proof"] == workspace.proof() for doc in documents)


@pytest.mark.parametrize("failure", ["reader", "proof", "extra", "oversize", "send", "other-pid"])
def test_failed_publication_has_no_retry_or_stale_replay(tmp_path, monkeypatch, failure):
    profile = _profile(tmp_path)
    value = _metadata()
    if failure == "proof": value["proof"]["credential_enrollment"] = "VERIFIED"
    if failure == "extra": value["credential"] = "synthetic-must-never-send"
    if failure == "oversize": value["reason"] = "X" * 3000
    read = Mock(return_value=value)
    if failure == "reader": read.side_effect = RuntimeError("synthetic-private-error")
    monkeypatch.setattr(publisher, "role_metadata", read)
    socket_factory = Mock(side_effect=OSError("synthetic socket refusal"))
    monkeypatch.setattr(publisher, "socket", SimpleNamespace(AF_UNIX=1, SOCK_DGRAM=2,
                                                           socket=socket_factory))
    context = _context(profile)
    if failure == "other-pid": context = dataclasses.replace(context, process_pid=os.getpid() + 1)
    assert context.publish() is False
    assert read.call_count == (0 if failure == "other-pid" else 1)
    assert socket_factory.call_count == (1 if failure == "send" else 0)


@pytest.mark.parametrize("interval", [0.01, 300.0])
def test_actual_supervisor_loop_publication_cadence_is_independent_of_memory(tmp_path, monkeypatch, interval):
    profile = dataclasses.replace(_profile(tmp_path), memory_sample_interval_sec=interval)
    values = secrets.Secrets("fixture-token-0123456789", "fixture", "fixture-password-012345", {})
    clock = [0.0]
    published = []
    context = SimpleNamespace(publish=lambda: published.append(clock[0]))
    runtime = supervisor.ServiceRuntime(profile, values, Path("/fixture/hermes"), role_status_publisher=context)
    class Stop:
        def is_set(self): return clock[0] >= 10.5
        def wait(self, seconds):
            clock[0] += seconds
            return self.is_set()
    runtime._stop = Stop()
    runtime.memory = Mock()
    monkeypatch.setattr(runtime, "_model_child_env", lambda: {})
    monkeypatch.setattr(supervisor, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(supervisor, "reserve_loopback_port", lambda _host: 32123)
    monkeypatch.setattr(supervisor, "read_rss_kib", lambda _pid: None)
    monkeypatch.setattr(supervisor, "_backend_health_ready", lambda *_args: False)
    monkeypatch.setattr(supervisor, "_terminate", lambda _proc: None)
    process = SimpleNamespace(pid=321, poll=lambda: None)
    monkeypatch.setattr(supervisor, "subprocess", SimpleNamespace(
        Popen=Mock(return_value=process), DEVNULL=-3))
    runtime._loop()
    assert len(published) == 3
    assert published[0] == 0.0
    assert all(5.0 <= later - earlier <= 5.3 for earlier, later in zip(published, published[1:]))
    assert runtime.failed is False


def test_publication_failure_does_not_mark_runtime_failed_or_retry_early(tmp_path):
    context = Mock()
    context.publish.side_effect = RuntimeError("synthetic error")
    values = secrets.Secrets("fixture-token-0123456789", "fixture", "fixture-password-012345", {})
    runtime = supervisor.ServiceRuntime(_profile(tmp_path), values, Path("/fixture/hermes"),
                                        role_status_publisher=context)
    runtime._publish_role_status_if_due(100.0)
    runtime._publish_role_status_if_due(101.0)
    runtime._publish_role_status_if_due(105.0)
    assert context.publish.call_count == 2
    assert runtime.failed is False and runtime.refusal_code == ""


@pytest.mark.parametrize("name", ["NOTIFY_SOCKET", "INVOCATION_ID", "SYSTEMD_EXEC_PID",
                                publisher.IMPLEMENTATION_ENV])
def test_notification_context_never_enters_any_child_environment(tmp_path, monkeypatch, name):
    secrets.clear_child_secret_env()
    try:
        with pytest.raises(RuntimeRefusal, match="SUPERVISOR_NOTIFICATION_ENV_REFUSED"):
            secrets.register_child_secret_env([name])
        # Also protect the final boundary against pre-existing registration.
        monkeypatch.setattr(secrets, "_CHILD_SECRET_ENV", set(secrets.child_secret_env_names()) | {name})
        monkeypatch.setenv(name, "synthetic-parent-context")
        values = secrets.Secrets("fixture-token-0123456789", "fixture", "fixture-password-012345",
                                 {name: "synthetic-registered-context"})
        assert name not in secrets.child_env(values, home=tmp_path)
    finally:
        secrets.clear_child_secret_env()


@pytest.mark.parametrize("late_merge", ["model", "egress"])
@pytest.mark.parametrize("name", ["NOTIFY_SOCKET", "INVOCATION_ID", "SYSTEMD_EXEC_PID",
                                publisher.IMPLEMENTATION_ENV])
def test_final_model_environment_refuses_notification_keys_after_late_merges(tmp_path, monkeypatch, late_merge, name):
    from integrations.hermes_harness import native_byok, native_model_credential
    from integrations.hermes_runtime import egress
    profile = dataclasses.replace(_profile(tmp_path), tool_allowlist=frozenset({"clarify"}))
    native = profile.hermes_home / "profiles" / profile.role / "config.yaml"
    native.parent.mkdir(parents=True)
    native.write_text(native_byok.render_disarmed_native_byok(profile), encoding="utf-8")
    native.chmod(0o600)
    values = secrets.Secrets("fixture-token-0123456789", "fixture", "fixture-password-012345", {
        "ZAI_API_KEY": "test-zai-key-local-fixture-not-live-123456",
        "HERMES_NATIVE_EGRESS_ROLE": "mmmeta",
        "HERMES_NATIVE_HTTPS_PROXY": "http://127.0.0.3:18652",
    })
    runtime = supervisor.ServiceRuntime(profile, values, Path("/fixture/hermes"))
    if late_merge == "model":
        monkeypatch.setattr(native_model_credential, "primary_model_env", lambda *_args: {name: "synthetic-notification"})
    else:
        monkeypatch.setattr(egress, "native_egress_child_env", lambda *_args: {name: "synthetic-notification"})
    with pytest.raises(RuntimeRefusal, match="SUPERVISOR_NOTIFICATION_ENV_REFUSED"):
        runtime._model_child_env()


def test_supervise_context_refusal_precedes_secret_read_and_child_start(tmp_path, monkeypatch, capsys):
    profile = _profile(tmp_path)
    monkeypatch.setattr(cli, "load_profile", lambda *_args, **_kw: profile)
    from integrations.hermes_runtime import system_service, role_isolation, tcp_sandbox
    monkeypatch.setattr(system_service, "assert_root_service_cgroup", lambda _role: None)
    monkeypatch.setattr(system_service, "assert_role_network_profile", lambda _profile: None)
    monkeypatch.setattr(role_isolation, "assert_role_credential_isolation", lambda _profile: None)
    monkeypatch.setattr(tcp_sandbox, "enforce_role_tcp_ports", lambda _profile: None)
    monkeypatch.setattr(publisher, "publisher_from_process", Mock(side_effect=RuntimeRefusal("ROLE_STATUS_CONTEXT_INVALID")))
    read_secrets = Mock(side_effect=AssertionError("credential read before context validation"))
    start = Mock(side_effect=AssertionError("child started before context validation"))
    monkeypatch.setattr(cli, "load_secrets", read_secrets)
    monkeypatch.setattr(cli, "ServiceRuntime", start)
    args = argparse.Namespace(profile=tmp_path / "profile.yaml", state=None,
                              secrets_file=None, hermes_bin=Path("/fixture/hermes"))
    assert cli._supervise(args) == CONFIG_EXIT
    assert capsys.readouterr().err.strip() == "ROLE_STATUS_CONTEXT_INVALID"
    read_secrets.assert_not_called()
    start.assert_not_called()


def test_root_unit_only_adds_main_process_notification_and_explicit_source_label(tmp_path):
    profile = _profile(tmp_path)
    kwargs = dict(runtime_user=profile.role, runtime_group=profile.role,
                  python_executable="/usr/bin/python3.12",
                  repo_root=Path("/opt/mastermind-executive/releases") / SHA)
    legacy = render_host_unit(profile, **kwargs)
    enabled = render_host_unit(profile, **kwargs, implementation_sha=SHA)
    assert "NotifyAccess=main\n" in legacy and "Type=simple\n" in legacy
    assert "MM_HERMES_IMPLEMENTATION_SHA" not in legacy
    assert enabled.replace("Environment=MM_HERMES_IMPLEMENTATION_SHA=" + SHA + "\n", "") == legacy
    for invalid in ("", "A" * 40, "a" * 40 + "\nNotifyAccess=all", True):
        with pytest.raises(RuntimeRefusal, match="ROOT_UNIT_IMPLEMENTATION_LABEL_INVALID"):
            render_host_unit(profile, **kwargs, implementation_sha=invalid)


def test_root_unit_refuses_label_for_another_release(tmp_path):
    profile = _profile(tmp_path)
    with pytest.raises(RuntimeRefusal, match="ROOT_UNIT_IMPLEMENTATION_LABEL_MISMATCH"):
        render_host_unit(profile, runtime_user=profile.role, runtime_group=profile.role,
                         python_executable="/usr/bin/python3.12",
                         repo_root=Path("/opt/mastermind-executive/releases") / SHA,
                         implementation_sha=("b" * 40 if SHA != "b" * 40 else "c" * 40))
