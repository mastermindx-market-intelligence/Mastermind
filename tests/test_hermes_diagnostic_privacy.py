"""Synthetic diagnostics and scope-isolation qualification, without a host or socket."""
from __future__ import annotations

import ast
from contextlib import contextmanager, redirect_stdout
import io
import logging
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


import hashlib
import json
import os
import subprocess
import tempfile
from functools import lru_cache

import pytest

from integrations.hermes_qualification.diagnostic_privacy import qualify

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "integrations/hermes_runtime/tests/fixtures/agentos_memory"
PROVENANCE = json.loads((FIXTURES / "provenance.json").read_text())


@lru_cache(maxsize=2)
def _privacy_sources(variant):
    """Reconstruct upstream solely for test comparison; never a runtime loader.

    Complete Python fixtures are the actual derived runtime postimages. Reverse
    the exact held patch in a disposable test tree, then verify original Git,
    SHA-256 and byte identities retained in their upstream provenance.
    """
    assert variant in {"upstream", "derived"}
    policy = qualify.manifest()
    patch_bytes = (qualify.ROOT / "guard.patch").read_bytes()
    assert hashlib.sha256(patch_bytes).hexdigest() == policy["patch_sha256"]
    result = {name: (FIXTURES / PROVENANCE["files"][name]["fixture"]).read_bytes()
              for name in qualify.PATHS}
    for name, data in result.items():
        assert hashlib.sha256(data).hexdigest() == policy["files"][name]["after_sha256"]
    if variant == "upstream":
        with tempfile.TemporaryDirectory(prefix="privacy-test-preimages-") as folder:
            tree = Path(folder)
            for name, data in result.items():
                target = tree / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            subprocess.run(["git", "apply", "--reverse", "--whitespace=error-all", "-"],
                cwd=tree, input=patch_bytes, capture_output=True, check=True, timeout=10,
                env={"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1",
                     "GIT_CONFIG_GLOBAL": os.devnull})
            result = {name: (tree / name).read_bytes() for name in qualify.PATHS}
    for name, data in result.items():
        item = PROVENANCE["files"][name]
        expected = item["upstream"] if variant == "upstream" else item
        assert len(data) == expected["bytes"]
        assert hashlib.sha256(data).hexdigest() == expected["sha256"]
        assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == expected["git_blob"]
    return tuple(result.items())


def privacy_sources(variant):
    return dict(_privacy_sources(variant))


KEY = "CANARY-Q7X9M2V4P6K8R3T5N1Z0C2F4H6J8L0B2D4G6J8N0R2"
HOME_A = "/synthetic-profile-home-canary/owner-A"
HOME_B = "/synthetic-profile-home-canary/owner-B"


def banner(variant):
    path = ROOT / variant / "agent/agent_init.py"
    tree = ast.parse(privacy_sources(variant)["agent/agent_init.py"], filename=str(path))
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_print_key_banner"]
    assert len(selected) == 1
    namespace = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_print_key_banner"]


@contextmanager
def credential_source(label=None):
    agent = ModuleType("agent")
    source = ModuleType("agent.credential_source")
    source.credential_label = lambda key: label
    agent.credential_source = source
    with patch.dict(sys.modules, {"agent": agent, "agent.credential_source": source}):
        yield


@contextmanager
def memory(variant, *, caller=HOME_A, multiplexed=True):
    state = SimpleNamespace(caller=caller, multiplexed=multiplexed)
    agent = ModuleType("agent")
    secrets = ModuleType("agent.secret_scope")
    secrets.current_secret_scope_home = lambda: state.caller
    secrets.is_multiplex_active = lambda: state.multiplexed
    constants = ModuleType("hermes_constants")
    constants.get_hermes_home_override = lambda: None
    constants.get_hermes_home = lambda: HOME_A
    constants.hermes_home_key = lambda value: str(value)
    agent.secret_scope = secrets
    module = ModuleType("s4_diagnostic_qualification")
    path = ROOT / variant / "agent/memory_caller_scope.py"
    stream = io.StringIO()
    log = logging.Logger("s4_diagnostic_qualification")
    log.addHandler(logging.StreamHandler(stream))
    with patch.dict(sys.modules, {"agent": agent, "agent.secret_scope": secrets, "hermes_constants": constants}):
        exec(compile(privacy_sources(variant)["agent/memory_caller_scope.py"], str(path), "exec"), vars(module))
        module.logger = log
        yield module, state, stream


def test_original_banner_reproduces_partial_credential_output():
    output = io.StringIO()
    with credential_source(), redirect_stdout(output):
        banner("upstream")(KEY, "synthetic API key")
    assert KEY[:8] in output.getvalue() and KEY[-4:] in output.getvalue()


@pytest.mark.parametrize("size", [0, 1, 12, 13, 64])
@pytest.mark.parametrize("warn", [False, True])
def test_derived_banner_keeps_presence_and_missing_warning_semantics_without_key_output(size, warn):
    key = (KEY * 2)[:size]
    before, after = io.StringIO(), io.StringIO()
    with credential_source(), redirect_stdout(before):
        banner("upstream")(key, "label-canary", warn_missing=warn)
    with credential_source(), redirect_stdout(after):
        banner("derived")(key, "label-canary", warn_missing=warn)
    if size > 12:
        assert after.getvalue() == "🔑 Using credentials\n"
        assert key[:8] not in after.getvalue() and key[-4:] not in after.getvalue()
        assert "label-canary" not in after.getvalue()
    else:
        assert after.getvalue() == before.getvalue()


@pytest.mark.parametrize("source_label", ["nonsecret-source", KEY])
def test_tagged_callable_is_not_invoked_and_its_arbitrary_label_is_not_printed(source_label):
    def credential():
        raise AssertionError("credential resolver must not be called by a diagnostic")
    output = io.StringIO()
    with credential_source(source_label), redirect_stdout(output):
        banner("derived")(credential, KEY, warn_missing=True)
    assert output.getvalue() == "🔑 Using credentials\n"
    assert source_label not in output.getvalue()


def test_unrecognized_object_is_not_formatted_or_invoked():
    class Credential:
        def __str__(self):
            raise AssertionError("must not stringify credential")
        def __repr__(self):
            raise AssertionError("must not repr credential")
    output = io.StringIO()
    with credential_source(), redirect_stdout(output):
        banner("derived")(Credential(), "label-canary", warn_missing=True)
    assert "appears invalid or missing" in output.getvalue()


@pytest.mark.parametrize("variant", ["upstream", "derived"])
@pytest.mark.parametrize("scenario", ["matching", "mismatch", "missing_caller", "missing_bound", "single_fallback"])
def test_scope_decisions_and_identity_are_preserved(variant, scenario):
    caller = None if scenario in ("missing_caller", "single_fallback") else HOME_A
    multiplexed = scenario != "single_fallback"
    with memory(variant, caller=caller, multiplexed=multiplexed) as (module, state, logs):
        home = None if scenario == "missing_bound" else (HOME_B if scenario == "mismatch" else HOME_A)
        bound = module.bound_scope(home, agent_identity="admission-fixture")
        result = module.caller_scope(bound, "hook qualification")
        if scenario in ("matching", "single_fallback"):
            assert result == {"hermes_home": HOME_A, "agent_identity": "admission-fixture"}
            assert logs.getvalue() == ""
        else:
            assert result is None
            assert module.CALLER_PROFILE_REFUSAL in logs.getvalue()
            if variant == "derived":
                assert HOME_A not in logs.getvalue() and HOME_B not in logs.getvalue()


def test_original_scope_diagnostic_reproduces_profile_path_output():
    with memory("upstream") as (module, state, logs):
        assert module.caller_scope(module.bound_scope(HOME_B), "hook qualification") is None
        assert HOME_A in logs.getvalue() and HOME_B in logs.getvalue()


@pytest.mark.parametrize("variant", ["upstream", "derived"])
def test_shared_instance_is_still_refused_without_profile_path_output(variant):
    class Provider:
        name = "fixture-provider"
    provider = Provider()
    with memory(variant) as (module, state, logs):
        assert module.claim_instance(provider, HOME_A)
        assert not module.claim_instance(provider, HOME_B)
        assert module.SHARED_INSTANCE_REFUSAL in logs.getvalue()
        if variant == "derived":
            assert HOME_A not in logs.getvalue() and HOME_B not in logs.getvalue()


@pytest.mark.parametrize("variant", ["upstream", "derived"])
@pytest.mark.parametrize("multiplexed", [False, True])
def test_untrackable_instance_policy_is_unchanged(variant, multiplexed):
    with memory(variant, multiplexed=multiplexed) as (module, state, logs):
        assert module.claim_instance(object(), HOME_A) is (not multiplexed)
        if multiplexed:
            assert module.SHARED_INSTANCE_REFUSAL in logs.getvalue()
            if variant == "derived":
                assert HOME_A not in logs.getvalue()


def test_memory_module_executable_ast_is_identical_except_logging_arguments():
    class WithoutDiagnostics(ast.NodeTransformer):
        def visit_Expr(self, node):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return None
            if (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                and isinstance(value.func.value, ast.Name) and value.func.value.id == "logger"
                and value.func.attr == "warning"):
                return ast.copy_location(ast.Pass(), node)
            return self.generic_visit(node)
    trees = []
    for variant in ("upstream", "derived"):
        tree = ast.parse(privacy_sources(variant)["agent/memory_caller_scope.py"])
        trees.append(ast.dump(WithoutDiagnostics().visit(tree), include_attributes=False))
    assert trees[0] == trees[1]


def test_agent_init_executable_ast_is_identical_outside_key_banner():
    trees = []
    for variant in ("upstream", "derived"):
        tree = ast.parse(privacy_sources(variant)["agent/agent_init.py"])
        tree.body = [n for n in tree.body if getattr(n, "name", None) != "_print_key_banner"]
        trees.append(ast.dump(tree, include_attributes=False))
    assert trees[0] == trees[1]



def test_pinned_forward_patch_produces_complete_derived_fixtures():
    original = privacy_sources("upstream")
    snapshot = dict(original)
    assert qualify.prepare_sources(original) == privacy_sources("derived")
    assert original == snapshot
    from ops.executive_os import native_gateway_sources as source
    assert qualify.manifest()["patch_sha256"] == source.PRIVACY_DERIVATION_PATCH
    assert {name: hashlib.sha256(data).hexdigest() for name, data in privacy_sources("derived").items()} == source.PRIVACY_DERIVATION_POSTIMAGES
    assert hashlib.sha256((qualify.ROOT / "UPSTREAM_LICENSE").read_bytes()).hexdigest() == source.PRIVACY_LICENSE_SHA256


@pytest.mark.parametrize("change", ["missing", "extra", "text", "changed", "derived", "oversized"])
def test_qualifier_refuses_nonexact_preimages(change):
    original = privacy_sources("upstream")
    name = qualify.PATHS[0]
    if change == "missing":
        original.pop(name)
    elif change == "extra":
        original["arbitrary.py"] = b"x"
    elif change == "text":
        original[name] = original[name].decode()
    elif change == "changed":
        original[name] += b"\n"
    elif change == "derived":
        original = privacy_sources("derived")
    else:
        original[name] = b"x" * (qualify.MAX_SOURCE_BYTES + 1)
    with pytest.raises(qualify.QualificationError):
        qualify.prepare_sources(original)


def test_qualifier_refuses_changed_patch_bytes(tmp_path, monkeypatch):
    original = privacy_sources("upstream")
    for name in ("manifest.json", "guard.patch"):
        (tmp_path / name).write_bytes((qualify.ROOT / name).read_bytes())
    with (tmp_path / "guard.patch").open("ab") as stream:
        stream.write(b"\n")
    monkeypatch.setattr(qualify, "ROOT", tmp_path)
    with pytest.raises(qualify.QualificationError, match="PATCH_DIGEST_MISMATCH"):
        qualify.prepare_sources(original)
