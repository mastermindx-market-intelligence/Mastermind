"""Source-only regression of the original Macro Fabric native Codex runner.

No installed source, app sessions, native provider accounts, model turns, or
process reservations are touched by these tests.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "ops/native_fabric/patches/codex_native_message_isolation_20261018.patch"
MANIFEST = ROOT / "ops/native_fabric/patches/codex_native_message_isolation_20261018.manifest.json"
SOURCE_NAME = "native_remote.py"
ALL_MODELS = frozenset(("gpt-6-astra", "gpt-6.1-sol"))
DISABLED = {
    "features.multi_agent=false",
    "features.multi_agent_v2.enabled=false",
    "features.multi_agent_v2.disable_direct_message=true",
    "agents.enabled=false",
}


def load_remote(path: Path, monkeypatch):
    stub = types.ModuleType("fabric_client_projection")
    def projection(*a, **kw):
        return types.SimpleNamespace(url="https://example.invalid/native-studio",
                                     config_text="")
    stub.project_fabric_client = projection
    monkeypatch.setitem(sys.modules, "fabric_client_projection", stub)
    spec = importlib.util.spec_from_file_location(
        "mmx_source_only_native_remote_test", str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def exact_source(request):
    path = os.environ.get("MMX_NATIVE_CODEX_SOURCE_TEST")
    if path is None:
        pytest.skip("exact non-Git installed source is not in hosted CI")
    target = Path(path)
    assert target.is_file()
    return target


@pytest.mark.parametrize("model", sorted(ALL_MODELS))
def test_worker_does_not_inherit_native_subagent_chat_or_direct_messages(
    monkeypatch, exact_source, model
):
    module = load_remote(exact_source, monkeypatch)
    argv = module.command("codex-native", model, "bounded-work", "/private/tmp",validated=True)
    assert argv[:2] == ["codex", "exec"]
    assert "--ignore-user-config" in argv
    pairs=[argv[i+1] for i,v in enumerate(argv[:-1]) if v=="-c"]
    assert DISABLED.issubset(set(pairs))
    assert "multi_agent_v2.enabled=true" not in pairs
    assert "agents.enabled=true" not in pairs
    assert "features.multi_agent=true" not in pairs
    assert not any("send_message_to_thread" in item for item in argv)
    assert "-m" in argv and argv[argv.index("-m")+1] == model


@pytest.mark.parametrize("model", ("gpt-6-unauthorized", "grok-4.7", ""))
def test_unreviewed_codex_model_still_refused(monkeypatch, exact_source, model):
    module = load_remote(exact_source, monkeypatch)
    with pytest.raises(ValueError, match="native_remote_model_refused"):
        module.command("codex-native", model, "bounded-work", "/private/tmp",validated=True)


def test_caller_cannot_supply_account_credentials_through_worker_environment(
    monkeypatch, exact_source
):
    module=load_remote(exact_source, monkeypatch)
    raw={"HOME":"/private/tmp/existing-native-home",
         "CODEX_HOME":"/private/tmp/hostile",
         "CODEX_ACCESS_TOKEN":"PRIVATE-CANARY",
         "OPENAI_API_KEY":"PRIVATE-CANARY",
         "ANTHROPIC_API_KEY":"PRIVATE-CANARY"}
    value=module.environment("codex-native","gpt-6.1-sol","one",Path("/private/tmp"),raw)
    assert "CODEX_HOME" not in value
    assert "CODEX_ACCESS_TOKEN" not in value
    assert "OPENAI_API_KEY" not in value
    assert "ANTHROPIC_API_KEY" not in value
    assert value["HOME"]==raw["HOME"]


def test_normal_worker_launch_still_invokes_existing_preflight_not_direct_exec(
    monkeypatch, exact_source
):
    module=load_remote(exact_source, monkeypatch)
    argv=module.command("codex-native","gpt-6-astra","bounded-work","/private/tmp")
    assert Path(argv[1]) == exact_source.resolve()
    assert argv[2] == "launch"
    assert argv[3] == "codex-native"


def test_bundle_has_expected_digest_and_no_real_enrollment():
    manifest=json.loads(MANIFEST.read_text())
    assert manifest["schema"] == "mastermind.codex_native_message_isolation_source/v1"
    assert manifest["status"] == "candidate_not_installed"
    assert manifest["runtime_modified"] is False
    assert manifest["worker_launched"] is False
    assert manifest["provider_turn"] is False
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["source_preimage_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["source_postimage_sha256"])
    assert hashlib.sha256(PATCH.read_bytes()).hexdigest() == manifest["patch_sha256"]
    changes=PATCH.read_text()
    assert changes.count("diff --git a/native_remote.py b/native_remote.py") == 1
    for override in DISABLED:
        assert "+" in changes and override in changes


def test_runner_patch_does_not_modify_existing_broker_or_native_account_owner():
    content=PATCH.read_text()
    assert "a/lease_broker.py" not in content
    assert "a/codex_pool_policy.py" not in content
    assert "a/codex_native_profile.py" not in content
    assert "a/hosts.json" not in content
    assert "a/accounts.yaml" not in content
    assert "a/auth.json" not in content
    assert "a/AGENTS.md" not in content
    assert "a/config.toml" not in content
