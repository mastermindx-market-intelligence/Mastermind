"""Closed entrypoint composition of the rich Claude provider, without dispatch."""
from __future__ import annotations

import asyncio
import dataclasses
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from scripts import executive_os_phase1c_worker as worker
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from test_executive_agent_capabilities import _claude_candidate_policy, _write
from test_executive_operator_broker import _reviewed_codex_adapter
from test_native_worker_factory import native_config


def config(root):
    value = native_config(root)
    value.update(native_provider="claude", operator_harness_armed=True,
                 control_uid=os.geteuid()+1000, allowed_supplementary_gids=[],
                 claude_sdk_python=str(Path(sys.executable).resolve()))
    for key in ("binary", "attestation_receipt"):
        value["claude_"+key] = value.pop("codex_"+key)
    value["allowed_claude_versions"] = ["2.1.275"]
    del value["allowed_codex_versions"], value["required_team_identifier"]
    return value


def prepared(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    value = config(root)
    for field in ("workspace_root", "run_root", "provider_home"):
        Path(value[field]).mkdir(mode=0o700)
    attestation = dataclasses.replace(_reviewed_codex_adapter(root/"binary").binary,
                                     version="2.1.275")
    value["claude_binary"] = attestation.path
    monkeypatch.setattr(worker, "_load_native_claude_binary", lambda c: attestation)
    monkeypatch.setattr(worker, "_build_autonomy_canary_factory", lambda c: lambda p: {})
    registry = ExecutionCapabilityRegistry.load(_write(root, _claude_candidate_policy()))
    # This is a construction fixture, never a parser-admitted production profile.
    profile = dataclasses.replace(registry.profiles["operator.claude.readonly.v1"], enabled=True)
    profiles = {"candidate": profile}
    monkeypatch.setattr(worker.ExecutionCapabilityRegistry, "load", lambda: SimpleNamespace(profiles=profiles))
    calls = []
    class Adapter:
        def __init__(self, **kwargs):
            calls.append(kwargs)
    monkeypatch.setattr(worker, "_native_claude_adapter_types", lambda: (Adapter, dict))
    requested = SimpleNamespace(
        provider="claude", harness_kind="claude-agent-sdk",
        harness_binary_digest=attestation.sha256,
        capabilities=profile.capability_manifest(harness_binary_digest=attestation.sha256),
        sandbox_policy=profile.sandbox_policy, approval_policy=profile.approval_policy,
        network_policy=profile.network_policy, write_capable=profile.write_capable,
        native_helper_policy=profile.native_helper_policy,
        expected_config_digest=profile.expected_config_digest,
    )
    return value, profiles, profile, requested, calls


def test_factory_uses_the_exact_claude_dependencies_without_a_flat_provider(tmp_path, monkeypatch):
    value, _, profile, requested, calls = prepared(tmp_path, monkeypatch)
    broker = worker._build_broker(value, autonomy_guard=lambda: None)
    assert broker.adapter is None and broker.validation_adapter is None
    workspace = Path(value["workspace_root"])
    loader = lambda turn: "actual admitted input"
    broker.operator_adapter_factory(workspace, loader, requested)
    assert len(calls) == 1
    assert calls[0]["provider_home"] == Path(value["provider_home"])
    assert calls[0]["binary_path"] == Path(value["claude_binary"])
    assert calls[0]["sdk_python"] == Path(value["claude_sdk_python"])
    assert calls[0]["turn_input_loader"] is loader
    assert calls[0]["policy_observer"] == profile.claude_sdk_config_projection()


@pytest.mark.parametrize("mutation", ["disabled", "duplicate", "provider", "digest", "capabilities"])
def test_factory_refuses_unadmitted_ambiguous_or_drifted_policy_before_constructor(tmp_path, monkeypatch, mutation):
    value, profiles, profile, requested, calls = prepared(tmp_path, monkeypatch)
    if mutation == "disabled": profiles["candidate"] = dataclasses.replace(profile, enabled=False)
    elif mutation == "duplicate": profiles["duplicate"] = profile
    elif mutation == "provider": requested.provider = "openai-codex"
    elif mutation == "digest": requested.expected_config_digest = "f" * 64
    else: requested.capabilities = None
    broker = worker._build_broker(value, autonomy_guard=lambda: None)
    with pytest.raises(worker.WorkerConfigError, match="one reviewed policy"):
        broker.operator_adapter_factory(Path(value["workspace_root"]), lambda t: "", requested)
    assert calls == []


def test_receipt_reader_receives_only_explicit_installer_contract_and_sanitizes_refusal(tmp_path, monkeypatch):
    value = config(tmp_path.resolve())
    module = ModuleType("control_plane.native_provider_attestation")
    calls = []
    def reader(path, **kwargs):
        calls.append((path, kwargs))
        raise ValueError("private attestation diagnostic")
    module.load_native_claude_attestation = reader
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with pytest.raises(worker.WorkerConfigError, match="^native Claude binary/SDK attestation refused$"):
        worker._load_native_claude_binary(value)
    assert calls == [(Path(value["claude_attestation_receipt"]), {
        "expected_binary_path": Path(value["claude_binary"]),
        "expected_owner_gid": value["worker_gid"],
        "allowed_versions": frozenset(["2.1.275"]),
        "sdk_python": Path(value["claude_sdk_python"]),
    })]


def test_claude_serve_uses_owned_rich_broker_without_opening_codex_credentials(tmp_path, monkeypatch):
    value = config(tmp_path.resolve())
    events = []
    marker = object()
    def forbidden(*a, **kw): pytest.fail("Claude opened a Codex account")
    monkeypatch.setattr(worker, "native_codex_account_scope", forbidden)
    monkeypatch.setattr(worker, "_build_broker", lambda c, **kw: marker)
    async def serve(broker, name):
        assert broker is marker and name == value["launchd_socket_name"]
        events.append("serve")
    monkeypatch.setattr(worker, "_serve_broker", serve)
    asyncio.run(worker._serve(value))
    assert events == ["serve"]


def test_claude_factory_refuses_borrowed_codex_scope_before_other_dependencies(tmp_path):
    with pytest.raises(worker.WorkerConfigError, match="cannot borrow a Codex"):
        worker._build_broker(config(tmp_path.resolve()), native_account=object())


def test_composed_factory_constructs_real_claude_adapter_without_starting_provider(tmp_path, monkeypatch):
    native = pytest.importorskip("control_plane.claude_operator_adapter",
                                reason="separate native adapter PR is not yet composed")
    value, _, _, requested, _ = prepared(tmp_path, monkeypatch)
    workspace = Path(value["workspace_root"])
    (workspace / "README.md").write_text("bounded factory construction fixture\n")
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True)
    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "factory fixture"], cwd=workspace, check=True)
    monkeypatch.setattr(worker, "_native_claude_adapter_types",
                        lambda: (native.ClaudeOperatorAdapter, native.ClaudeReadbackPolicyObserver))
    broker = worker._build_broker(value, autonomy_guard=lambda: None)
    adapter = broker.operator_adapter_factory(workspace, lambda turn: "not dispatched", requested)
    assert type(adapter) is native.ClaudeOperatorAdapter
    assert adapter.sdk_python == Path(value["claude_sdk_python"])
    assert adapter.binary_digest == requested.harness_binary_digest
    assert adapter._generations == {}
    assert broker.adapter is None and broker.validation_adapter is None
