"""Actual source package/current project owners -> native memory and prompt.

The signed App and original Runtime/DATA/plan readers execute. The established
native fixture runs attributed pinned Hermes lifecycle bodies at explicit
model, PluginManager, credential and service edges. Its package is actually
built/imported; no installed profile, native provider dispatch or Unix socket
service is claimed. Every native RPC below reaches the real authenticated App.
"""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import httpx
from mcp import types
import pytest

from common import coo_agentos_context_contract as context_wire
from common import coo_project_help_contract as wire
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, HERMES_NATIVE_PROJECT_HELP_PROFILE_ID,
    T3_API_PROJECT_HELP_PROFILE_ID,
)
from integrations.hermes_harness import native_executive_consumer as consumer
from integrations.hermes_harness import native_project_help as help_owner
from integrations.hermes_harness.tests.test_native_agentos_context import context_document
from integrations.hermes_runtime import native_agentos_memory as memory
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.tests import test_native_agentos_memory as native_memory
from integrations.hermes_runtime.tests.test_native_request_observation import native
from integrations.mastermind_executive_app.coo import create_coo_app
from integrations.mastermind_executive_app.coo_binding import COO_SCOPES, _digest, principal_frame
from integrations.mastermind_workspace_app.contract import principal_frame as workspace_frame
from scripts.build_hermes_long_horizon_plugin import build
from tests import test_t3_project_help_api as api
from tests.test_coo_project_help_authority import (
    qualified_help, full_joined, owner, env, isolated_git_env, identity, ROOT, _frame,
)
from tests.test_long_horizon_guidance import Lease

rsa_key = api.rsa_key


def _document(frame=None, record=None, workspace=None, *, package_sha="a" * 64, scope=None):
    value = context_document(frame, record)
    if record is None:
        value["principal"].update(resource_ref=consumer._CURRENT_PRIMARY_RESOURCE,
            scopes=consumer._CURRENT_PRIMARY_SCOPE.split())
        bound = dict(value["principal"], permission_digest=value["permission_digest"])
        bound["resource"] = bound.pop("resource_ref")
        value["principal_binding_digest"] = _digest(bound)
    if workspace is None:
        workspace = dict(value["principal"], policy_id="workspace-policy",
            resource_ref=consumer._WORKSPACE_RESOURCE, scopes=[consumer._WORKSPACE_SCOPE])
    else:
        workspace = dict(workspace)
        workspace["resource_ref"] = workspace.pop("resource")
    if scope is None:
        scope = {"schema": wire.SCOPE_SCHEMA, "root_job_id": "JOB-001", "source_plan": {
            "schema": wire.PLAN_SCHEMA, "work_ref": value["work_ref"],
            "source": {"repository": "mastermindx-market-intelligence/macro", "commit": "a" * 40,
                "path": "docs/plans/source.md", "content_sha256": "b" * 64},
            "contract_sha256": "c" * 64}}
    value.update(schema=consumer.PROJECT_HELP_CONSUMER_SCHEMA,
        tools_schema_digest=consumer.PROJECT_HELP_TOOLS_SCHEMA_DIGEST,
        workspace_principal=workspace, project_help=scope,
        project_context_plugin={"name": help_owner.SOURCE_PLUGIN, "source": "user", "digest": package_sha})
    value["context"]["source_mode"] = "CANONICAL_PROJECT_DATA"
    value["mcp"].update(url=consumer._CURRENT_PRIMARY_URL, client_id="inert-client",
        scope=consumer._CURRENT_PRIMARY_SCOPE)
    return value


@pytest.mark.parametrize("fault", ["scope", "workspace", "plugin", "contract", "legacy", "selected_child"])
def test_v6_publication_is_explicit_and_cannot_borrow_legacy_scope(fault):
    value = _document()
    publication = consumer.publication_from_document(value)
    assert type(publication) is consumer.ExecutiveContextConsumerPublication
    assert consumer.validate_consumer_publication(value) == value
    assert publication.project_help.to_dict() == value["project_help"]
    assert consumer.selected_child_publication(publication) is None
    if fault == "scope": value.pop("project_help")
    elif fault == "workspace": value.pop("workspace_principal")
    elif fault == "plugin": value["project_context_plugin"]["name"] = "unrelated-plugin"
    elif fault == "contract": value["project_help"]["source_plan"]["work_ref"] = "WS:FOREIGN"
    elif fault == "legacy": value["schema"] = consumer.CURRENT_CONTEXT_CONSUMER_SCHEMA
    else: value["selected_child"] = {"command": "coo-cycle:ROOT1:dispatch:JOB1:attempt:1",
        "root_job_id": "ROOT1", "job_id": "JOB1", "target_digest": "1" * 64}
    with pytest.raises(RuntimeRefusal):
        consumer.publication_from_document(value)


@pytest.mark.parametrize("deferred", [False, True])
def test_release_constructor_requires_original_workspace_privacy_derivation(deferred):
    from integrations.hermes_harness.tests.test_native_executive_consumer import _installation
    from ops.executive_os import release_manifest as release
    from ops.executive_os.native_gateway_sources import _derivation_policy, DERIVATION_BASE
    def derivation(kind):
        patch, _, _ = _derivation_policy(kind)
        return {"kind": kind, "base_sha": DERIVATION_BASE, "patch_sha256": patch,
                "source_root": "/opt/hermes/pristine"}
    document = _document()
    installation = _installation(consumer=document)
    selection = next(row["native_gateway"] for row in installation["roles"] if row["role"] == "mmsecretary")
    selection["vendor_derivation"] = derivation("workspace_oauth_privacy")
    result = release.validate_hermes_runtime_installation(installation, _defer_consumer=deferred)
    retained = next(row["native_gateway"] for row in result["roles"] if row["role"] == "mmsecretary")
    assert retained["executive_consumer"] == document
    for wrong in (None, "diagnostic_privacy", "computer_env_guard"):
        if wrong is None:
            selection.pop("vendor_derivation", None)
        else:
            selection["vendor_derivation"] = derivation(wrong)
        with pytest.raises(release.ReleaseManifestError):
            release.validate_hermes_runtime_installation(installation, _defer_consumer=deferred)


def test_actual_source_package_is_isolated_and_missing_or_changed_parser_cannot_match(tmp_path):
    package = tmp_path / "source-package"
    manifest = build(package)
    assert manifest["installed"] is False
    assert set(manifest["files"]) == set(help_owner.PACKAGE_FILES)
    expected = help_owner.package_digest(package)
    parser = package / "project_task_contract.py"
    assert parser.read_bytes() == (ROOT / "common/project_task_contract.py").read_bytes()
    program = """import importlib.util, pathlib, sys
p = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('actual_horizon', p/'__init__.py', submodule_search_locations=[str(p)])
m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)
assert m.PLUGIN_NAME == 'mastermind-long-horizon'
assert m.load_context.__module__ == 'actual_horizon.project_task_context'
from actual_horizon.project_task_context import parse_plan
assert parse_plan.__module__ == 'actual_horizon.project_task_contract'
assert not any(k == 'common' or k.startswith('control_plane') for k in sys.modules)
"""
    result = subprocess.run([sys.executable, "-I", "-B", "-c", program, str(package)],
        cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    original = parser.read_bytes()
    parser.write_bytes(original + b"\n# changed dependency\n")
    assert help_owner.package_digest(package) != expected
    parser.unlink()
    with pytest.raises((OSError, RuntimeRefusal)):
        help_owner.package_digest(package)
    result = subprocess.run([sys.executable, "-I", "-B", "-c", program, str(package)],
        cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0


@pytest.mark.parametrize("fault", [None, "missing_wire", "changed_parser"])
def test_v6_constructor_and_new_dependencies_use_original_held_source_importer(tmp_path, fault):
    # The held importer and semantic v6 constructor are actual source. As in
    # the incumbent release bootstrap test, OS/root descriptor custody is an
    # explicit double; no installed release or permissions are asserted.
    program = r'''
import hashlib, json, pathlib, runpy, sys
p = json.load(sys.stdin); root = pathlib.Path(p['source'])
ns = runpy.run_path(str(root/'ops/executive_os/release_manifest.py'))
entry = ns['_held_release_imports']; owners = ns
paths = ('common/coo_project_help_contract.py', 'common/project_task_contract.py',
         'integrations/hermes_harness/native_project_help.py')
expected = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in paths}
class Owner:
    def __init__(self):
        self.root = root; self.entries = {}; self.reads = []; self.changed = False
        for prefix in owners['_FIRST_PARTY']:
            self.entries[prefix] = {'type':'directory'}
            for path in (root/prefix).rglob('*.py'):
                relative = path.relative_to(root)
                self.entries[str(relative)] = {'type':'file'}
                for parent in relative.parents:
                    if str(parent) != '.': self.entries[str(parent)] = {'type':'directory'}
        if p['fault'] == 'missing_wire': self.entries.pop(paths[0])
    def check(self):
        if self.changed: raise RuntimeError('ORIGINAL_DEPENDENCY_CHANGED')
    def source(self, name):
        self.check(); self.reads.append(name)
        raw = (root/name).read_bytes()
        if name == paths[1] and p['fault'] == 'changed_parser': raw += b'\n# changed bytes\n'
        if name in expected and hashlib.sha256(raw).hexdigest() != expected[name]:
            self.changed = True; self.check()
        return raw
    def directory(self, name):
        self.check(); assert self.entries[name]['type'] == 'directory'
owner = Owner(); outcome = None
try:
    with entry(owner):
        from integrations.hermes_harness.native_executive_consumer import publication_from_document
        from integrations.hermes_harness.native_project_help import NativeProjectHelpRead
        from common.project_task_contract import parse_plan
        value = publication_from_document(p['document'])
        assert value.project_help.to_dict() == p['document']['project_help']
        assert NativeProjectHelpRead.__module__ == 'integrations.hermes_harness.native_project_help'
        outcome = 'QUALIFIED'
except Exception as error: outcome = type(error).__name__
assert not any(name == prefix or name.startswith(prefix+'.') for name in sys.modules for prefix in owners['_FIRST_PARTY'])
print(json.dumps({'outcome':outcome, 'read_dependencies':[name for name in paths if name in owner.reads]}))
'''
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", program],
        input=json.dumps({"source": str(ROOT), "document": _document(), "fault": fault}),
        text=True, capture_output=True, cwd=tmp_path, timeout=30)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    if fault is None:
        assert observed["outcome"] == "QUALIFIED", observed
        assert len(observed["read_dependencies"]) == 3
    else:
        assert observed["outcome"] != "QUALIFIED", observed


@pytest.fixture
def hermes_signed(qualified_help, rsa_key, tmp_path, monkeypatch):
    f = qualified_help
    from tests.test_installed_current_agentos_context import context_child
    # Execute the real isolated current-context child using the incumbent
    # fixture's explicit CF2/source-seal runtime boundary.
    _, context_calls = context_child(f.j, monkeypatch)
    factory = f.j["factory"]
    def public(policy):
        return replace(policy, resource=consumer._CURRENT_PRIMARY_RESOURCE,
            resource_metadata_url=consumer._CURRENT_PRIMARY_RESOURCE + "/.well-known/oauth-protected-resource")
    factory.policies = replace(factory.policies, read=public(factory.policies.read), submit=public(factory.policies.submit))
    policy = replace(factory.policies.read, policy_id="project-help-coo", required_scopes=COO_SCOPES)
    f.principal = replace(f.principal, resource=policy.resource)
    f.coo["policy"] = json.loads(json.dumps(asdict(policy)))
    f.coo["binding"]["binding"].update(principal_frame(f.principal))
    f.coo["missions"][0]["principal_binding_digest"] = _digest(f.coo["binding"]["binding"])
    f.frame = _frame(f)
    signed = api.signed_help.__wrapped__(f, rsa_key, tmp_path)
    # The actual fixture selects Hermes again through the registry, rather
    # than claiming that the distinct T3 grant is a native enrollment.
    raw = json.loads(f.policy_path.read_bytes())
    raw["profiles"][T3_API_PROJECT_HELP_PROFILE_ID]["enabled"] = False
    raw["profiles"][HERMES_NATIVE_PROJECT_HELP_PROFILE_ID]["enabled"] = True
    f.policy_path.write_text(json.dumps(raw))
    profile = ExecutionCapabilityRegistry.load(f.policy_path, source_root=ROOT).profiles[HERMES_NATIVE_PROJECT_HELP_PROFILE_ID]
    f.coo["missions"][0].update(capability_profile_id=profile.profile_id,
        capability_profile_digest=profile.profile_digest,
        principal_actions=sorted([wire.ACTION, context_wire.CURRENT_ACTION]))
    f.frame = _frame(f)
    context_failures = []
    def current_context(who, workspace, context, digest):
        frame = {"schema": context_wire.HELP_CONTEXT_FRAME_SCHEMA, "principal": principal_frame(who),
            "workspace_principal": workspace_frame(workspace), "principal_context": asdict(context),
            "capability_profile_digest": digest}
        try:
            return f.provider.read_project_help_agentos_context(frame)
        except Exception as error:
            import traceback
            context_failures.append((type(error).__name__, [(row.name, row.lineno)
                for row in traceback.extract_tb(error.__traceback__)[-6:]]))
            raise
    signed.settings = replace(signed.settings, project_help_context_provider=current_context)
    signed.context_failures = context_failures
    signed.context_calls = context_calls
    signed.core = create_coo_app(signed.settings, audit_sink=signed.sink, workspace_app=signed.workspace_app)
    return signed


async def _rpc(signed, tool, arguments):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=signed.core), base_url="http://127.0.0.1") as client:
        response = await client.post("/v1/tools/" + tool, json={"arguments": arguments},
            headers={"authorization": "Bearer " + signed.token,
                "x-mastermind-workspace-authorization": "Bearer " + signed.second})
    return types.CallToolResult(content=[types.TextContent(type="text", text=response.text)],
        isError=response.status_code != 200)


@pytest.fixture
def lifecycle(native, hermes_signed, monkeypatch, tmp_path):
    s = hermes_signed
    package = tmp_path / "actual-source-package"
    build(package)
    document = _document(s.f.frame, s.f.coo["binding"]["binding"], s.f.frame["workspace_principal"],
        package_sha=help_owner.package_digest(package), scope=s.f.scope)
    publication = consumer.publication_from_document(document)
    sdk = asyncio.run(_rpc(s, context_wire.CURRENT_TOOL, {"work_ref": s.f.work}))
    assert sdk.isError is False, (sdk, s.context_failures,
        [{key: row[1].get(key) for key in ("returncode", "stderr", "timed_out", "invalid_utf8")}
            for row in s.context_calls])
    monkeypatch.setattr(native_memory, "context_document", lambda *_a, **_k: deepcopy(document))
    selection = dict(kind=memory.WORKSPACE_OAUTH_DERIVATION_KIND, base_sha=memory.DERIVATION_BASE,
        patch_sha256=memory.WORKSPACE_OAUTH_DERIVATION_PATCH, source_root="/opt/hermes/pristine")
    monkeypatch.setattr(native_memory, "privacy_selection", lambda: deepcopy(selection))
    monkeypatch.setattr(native_memory, "privacy_receipt", lambda vendor: dict(
        kind=selection["kind"], base_sha=selection["base_sha"], patch_sha256=selection["patch_sha256"],
        postimages=dict(memory.WORKSPACE_OAUTH_DERIVATION_POSTIMAGES),
        license_sha256=memory.PRIVACY_LICENSE_SHA256, vendor_root=str(vendor)))
    generator = native_memory.lifecycle.__wrapped__(native, (publication, sdk, {"coo": s.f.coo}), monkeypatch)
    value = next(generator)
    async def actual_rpc(name, arguments=None, **kwargs):
        value.session.calls.append((name, dict(arguments)))
        return await _rpc(s, name, arguments)
    monkeypatch.setattr(value.session, "call_tool", actual_rpc)

    # Retain the existing explicitly controlled native PluginManager edge,
    # using its nominal PluginContext and the actual packaged registration.
    manager = value.manager
    manager.home_path = native.home
    value.cfg["plugins"]["enabled"].append(help_owner.SOURCE_PLUGIN)
    bindings = {"physical-session-1": {"workspace_root": str(s.f.j["integrator"]),
        "plan_path": s.f.source_plan["source"]["path"], "workstream": s.f.work,
        "plan_contract_sha256": s.f.source_plan["contract_sha256"]}}
    entries, hooks, sections, leases = {}, {}, {}, []
    registry = SimpleNamespace(get_entry=lambda name, *, scope: entries.get((scope, name)))
    monkeypatch.setattr(sys.modules["tools.registry"], "registry", registry, raising=False)
    native_memory.edge(monkeypatch, "registration_lifecycle", replacement_coordinator=SimpleNamespace(transaction=nullcontext))
    native_memory.edge(monkeypatch, "hermes_cli.plugins_loader", _plugin_home_scope=lambda home: nullcontext())
    manifest = SimpleNamespace(name=help_owner.SOURCE_PLUGIN, source="user", path=package)
    ctx = sys.modules["hermes_cli.plugins"].PluginContext(manifest, manager)
    ctx.profile_name, ctx.plugin_id = value.slot.profile_id, help_owner.SOURCE_PLUGIN
    ctx.get_config = lambda key, default=None: bindings if key == "session_bindings" else default
    ctx._mcp_allowlist = lambda plugin: [publication.mcp.server]
    def lease():
        item = Lease(); leases.append(item); return item
    def register_tool(**kwargs):
        assert kwargs["override"] is False
        entries[(manager.scope_key, kwargs["name"])] = SimpleNamespace(
            handler=kwargs["handler"], schema=kwargs["schema"])
        return lease()
    def register_hook(name, fn):
        hooks[name] = fn; return lease()
    def register_section(name, fn, **kwargs):
        sections[name] = fn; return lease()
    ctx.register_tool, ctx.register_hook = register_tool, register_hook
    ctx.register_system_prompt_section = register_section
    ctx.register_skill = lambda name, path, **kwargs: lease()
    spec = importlib.util.spec_from_file_location("actual_native_horizon", package / "__init__.py",
        submodule_search_locations=[str(package)])
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    module.register(ctx)
    manager._plugins[help_owner.SOURCE_PLUGIN] = SimpleNamespace(manifest=manifest, enabled=True, error=None)
    assert value.slot.project_help_context.current() is True
    value.signed, value.package, value.source_ctx = s, package, ctx
    value.source_bindings, value.source_leases, value.source_hooks = bindings, leases, hooks
    value.source_tool = entries[(manager.scope_key, help_owner.SOURCE_TOOL)].handler
    try:
        yield value
    finally:
        with pytest.raises(StopIteration):
            next(generator)


def test_current_source_help_reaches_actual_native_tool_memory_and_prompt(lifecycle):
    l = lifecycle
    before = [event.to_dict() for event in l.signed.f.j["runtime"].events.list_events()]
    observations = {}
    def reached(agent):
        value = json.loads(l.source_tool({}, session_id=agent.session_id))
        assert value["ok"] is True, value
        observations["tool"] = value["context"]["project_help"]
        observations["hook"] = l.source_hooks["pre_llm_call"](session_id=agent.session_id)["context"]
    result = native_memory.exercise(l, before_prefetch=reached)
    assert observations["tool"]["scope"] == l.signed.f.scope
    assert wire.RESULT_SCHEMA in observations["hook"]
    assert wire.RESULT_SCHEMA in result["context"]
    assert result["context"] in result["built"][0][-1]["content"]
    assert result["live_readback"]["schema"] == memory.PROJECT_HELP_READBACK_SCHEMA
    observed = result["live_readback"]["context"]["last_delivery"]
    assert observed["project_help"]["state"] == "AVAILABLE"
    assert observed["prompt"]["boundary"] == "build_api_messages"
    assert l.slot.project_help_context.package_sha256 == help_owner.package_digest(l.package)
    assert l.stores == [] and l.slot.startup is None and l.slot.registration is None
    assert all(args == {"work_ref": l.signed.f.work} for _, args in l.session.calls)
    assert {name for name, _ in l.session.calls} == {wire.TOOL, context_wire.CURRENT_TOOL}
    assert memory.validate_consumer_readback(result["settled_readback"], publication=l.slot.publication,
        expected_binding=result["settled_readback"]["binding"]) == result["settled_readback"]
    assert [event.to_dict() for event in l.signed.f.j["runtime"].events.list_events()] == before


@pytest.mark.parametrize("fault", ["source", "lease", "grant", "package"])
def test_original_current_help_is_withheld_after_source_or_authority_changes(lifecycle, fault):
    l = lifecycle
    def drift(agent, context, messages):
        assert wire.RESULT_SCHEMA in context
        if fault == "source":
            path = l.signed.f.j["integrator"] / l.signed.f.source_plan["source"]["path"]
            path.write_bytes(path.read_bytes() + b"\nChanged actual source bytes.\n")
        elif fault == "lease": l.source_leases[0].dispose()
        elif fault == "grant": l.signed.f.coo["missions"][0]["enabled"] = False
        else:
            path = l.package / "project_task_contract.py"
            path.write_bytes(path.read_bytes() + b"\n# dependency changed\n")
    with pytest.raises(RuntimeRefusal):
        native_memory.exercise(l, before_build=drift)
    assert l.factory.last_delivery["prompt"] is None
