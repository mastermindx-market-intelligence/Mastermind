"""Actual captured Macro compiler→private/Event owner→temporary bare Git.

Only PR/credential qualification are explicit inert fixtures. No company
publication, JWT enrollment, provider, Job or installed-source proof is claimed.
"""
import base64
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import zlib

import pytest
import yaml

from control_plane.workspace_source_operations import SourceOperationEvents, SourceOperationConflict
from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.workspace_project_git_publisher import PublisherBinding
from control_plane.terminal_original_input_artifacts import TerminalInputError
from integrations.mastermind_workspace_app.project_creation_operation import ProjectCreationRecipeAdapter
from integrations.mastermind_workspace_app.project_creation_service import ProjectCreationSourceOwner
from integrations.mastermind_workspace_app.project_profiles import profile_choices
from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
from tests.test_terminal_original_input_supervisor import empty_owner
from tests.test_workspace_project_authoring_grant import project_bindings, verified
from tests.test_workspace_member_bindings import principal
from tests.test_workspace_read_app import rsa_key
from tests.test_executive_workspace_mount import settings
from tests.test_workspace_project_git_publisher import env, isolated_git_env, git, rev_parse, InertPullRequestOwner


@pytest.fixture
def owner(env, monkeypatch, tmp_path):
    fixture = json.loads((Path(__file__).parent / "fixtures/project-creation-canonical-3a53.json").read_bytes())
    refs = {}
    for item in fixture["files"]:
        raw = zlib.decompress(base64.b64decode(item["zlib_base64"], validate=True))
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        path = env.clone / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        refs[item["path"]] = item["sha256"]
    git(env.clone, "add", "scripts/agentos.py", "scripts/agentos_project_proposal.py", "config/mastermind_programs.yml")
    git(env.clone, "commit", "-m", "Synthetic Git snapshot of actual canonical source")
    git(env.clone, "push", "origin", "main")
    commit = rev_parse(env.clone, "HEAD")
    binding = {role: {"repository": fixture["repository"], "path": path,
                     "commit": commit, "content_sha256": refs[path]}
               for role, path in {"compiler": "scripts/agentos_project_proposal.py", "owner": "scripts/agentos.py",
                                  "programs": "config/mastermind_programs.yml"}.items()}
    # The exact code imports its canonical owner. Bind only that test package
    # dependency and restore it afterwards; never patch compiler source bytes.
    package = importlib.import_module("scripts")
    before_path = list(sys.path)
    for name, path in [("agentos", "scripts/agentos.py"), ("agentos_project_proposal", "scripts/agentos_project_proposal.py")]:
        qualified = "scripts." + name
        spec = importlib.util.spec_from_file_location(qualified, env.clone / path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, qualified, module)
        monkeypatch.setattr(package, name, module, raising=False)
        spec.loader.exec_module(module)
    compiler = sys.modules["scripts.agentos_project_proposal"]
    programmes = frozenset(yaml.safe_load((env.clone / "config/mastermind_programs.yml").read_text())["programs"])
    profiles = json.loads((Path(__file__).parents[1] / "config/workspace_project_authoring_profiles.json").read_bytes())
    adapter = ProjectCreationRecipeAdapter(compiler, programmes, profiles, binding)
    policy, bindings = project_bindings()
    who = verified(policy, principal(bindings))
    runtime, supervisor, execution = empty_owner(tmp_path / "custody")
    events = SourceOperationEvents(runtime.store)
    private = ProjectSourceOriginalInput(supervisor)
    permissions = WorkspaceSourceOperationContextFactory(policy=policy, load_bindings=lambda: bindings)
    publisher_binding = PublisherBinding(worktree=str(env.clone), expected_origin=str(env.origin),
        default_branch="main", publisher_identity="synthetic-fixed-service-identity")
    pr = InertPullRequestOwner(env.origin)
    qualified = {"value": True}
    service = ProjectCreationSourceOwner(events=events, private_inputs=private, permission_factory=permissions,
        adapter=adapter, publisher_binding=publisher_binding, qualify_publisher=lambda b: b == publisher_binding and qualified["value"],
        pr_owner=pr)
    selected = profile_choices(profiles)[0]
    request = {"schema": "mastermind.project_profile_selection.v1", "request_id": "mmos-project-create-" + "a" * 40,
               "goal": "Preserve literal 中文 goal\nand clarify the scope.", "expected_macro_sha": commit,
               "profile_id": selected["id"], "profile_sha256": selected["revision"]}
    yield dict(service=service, adapter=adapter, events=events, runtime=runtime, supervisor=supervisor,
               private=private, bindings=bindings, who=who, request=request, pr=pr, env=env, execution=execution, qualified=qualified)
    sys.path[:] = before_path


def selection(preview):
    return {"schema": "mastermind.workspace_source_operation_lookup.v1", **preview["selection"]}


def test_actual_compiler_and_private_source_preview_before_any_job_or_git_effect(owner):
    o = owner
    preview = o["service"].prepare(o["request"], o["who"])
    assert preview["preview"]["goal"] == o["request"]["goal"]
    profile = preview["preview"]["profile"]
    assert (profile["classification"], profile["blast_radius"], profile["ambiguity"]) == ("research", "reversible", "open")
    assert profile["waves"][0]["title"] == "Clarify goal and plan scope"
    assert preview["request_sha256"] != preview["recipe_fingerprint_sha256"]
    assert len(o["runtime"].store.list_events()) == 1
    assert o["runtime"].jobs.list_jobs() == [] and o["pr"].create_calls == 0 and o["execution"].spec is None
    encoded = json.dumps([e.to_dict() for e in o["runtime"].store.list_events()])
    assert o["request"]["goal"] not in encoded and "compiler_request" not in encoded
    assert o["service"].prepare(o["request"], o["who"])["preview_witness"] == preview["preview_witness"]


def test_one_actual_source_proposal_then_readonly_get_and_explicit_original_settlement(owner, monkeypatch):
    o = owner; service = o["service"]
    preview = service.prepare(o["request"], o["who"]); lookup = selection(preview)
    first = service.submit(lookup=lookup, preview_witness=preview["preview_witness"], principal=o["who"])
    assert first["disposition"] == "unknown" and first["receipt"]["kind"] == "PROPOSAL_OBSERVED"
    assert o["pr"].create_calls == 1
    again = service.submit(lookup=lookup, preview_witness=preview["preview_witness"], principal=o["who"])
    assert again == first and o["pr"].create_calls == 1
    def compiler_unavailable(*args, **kwargs):
        raise ValueError("source unavailable")
    monkeypatch.setattr(o["adapter"], "_compile_proposal", compiler_unavailable)
    # Already-attempted submit/status and exact original observation do not
    # depend on a current Macro/compiler refresh or re-entering the goal.
    assert service.submit(lookup=lookup, preview_witness=preview["preview_witness"], principal=o["who"]) == first
    branch = first["receipt"]["proposal"]["head_branch"]
    # Simulate the separate normal protected merge in the temporary bare repo.
    integrator = o["env"].tmp_path / "integrator"
    git(o["env"].tmp_path, "clone", str(o["env"].origin), str(integrator))
    git(integrator, "fetch", "origin", branch)
    git(integrator, "merge", "--no-ff", "--no-edit", "FETCH_HEAD")
    git(integrator, "push", "origin", "main")
    before = len(o["runtime"].store.list_events())
    assert service.read_status(lookup, o["who"]) == first
    assert len(o["runtime"].store.list_events()) == before
    final = service.reconcile(lookup, o["who"])
    assert final["disposition"] == "accepted" and final["receipt"]["kind"] == "SOURCE_OBSERVED"
    assert final["receipt"]["sources"][0]["path"] == preview["preview"]["canonical_path"]
    assert service.reconcile(lookup, o["who"]) == final and o["pr"].create_calls == 1
    assert o["runtime"].jobs.list_jobs() == []


def test_same_id_changed_goal_cannot_replace_private_original_and_revocation_blocks_submit(owner):
    o = owner; preview = o["service"].prepare(o["request"], o["who"])
    with pytest.raises(TerminalInputError):
        o["service"].prepare(o["request"] | {"goal": "Different private goal"}, o["who"])
    o["bindings"]["profiles"]["member-0"]["project_authoring"] = None
    with pytest.raises(PermissionError):
        o["service"].submit(lookup=selection(preview), preview_witness=preview["preview_witness"], principal=o["who"])
    assert o["pr"].create_calls == 0 and len(o["runtime"].store.list_events()) == 1


def test_actual_publisher_qualification_refusal_retains_proven_no_effect(owner):
    o = owner
    preview = o["service"].prepare(o["request"], o["who"])
    o["qualified"]["value"] = False
    refused = o["service"].submit(lookup=selection(preview),
        preview_witness=preview["preview_witness"], principal=o["who"])
    assert refused["disposition"] == "refused" and refused["reason"] == "NOT_DISPATCHED"
    assert refused["receipt"] is None and o["pr"].create_calls == 0
    assert o["runtime"].jobs.list_jobs() == []
    o["qualified"]["value"] = True
    # The original attempt is settled, not recreated after qualification changes.
    assert o["service"].submit(lookup=selection(preview),
        preview_witness=preview["preview_witness"], principal=o["who"]) == refused
    assert o["pr"].create_calls == 0


def test_authorization_loss_after_real_pr_preserves_original_unknown_no_replay(owner, monkeypatch):
    o = owner; service = o["service"]
    preview = service.prepare(o["request"], o["who"])
    original_grant = o["bindings"]["profiles"]["member-0"]["project_authoring"]
    original_create = o["pr"].create
    def create_then_revoke(*args):
        receipt = original_create(*args)
        o["bindings"]["profiles"]["member-0"]["project_authoring"] = None
        return receipt
    monkeypatch.setattr(o["pr"], "create", create_then_revoke)
    with pytest.raises(PermissionError):
        service.submit(lookup=selection(preview), preview_witness=preview["preview_witness"], principal=o["who"])
    assert o["pr"].create_calls == 1
    assert [e.payload["kind"] for e in o["runtime"].store.list_events()] == ["INTENT", "PHASE_ATTEMPTED"]
    o["bindings"]["profiles"]["member-0"]["project_authoring"] = original_grant
    status = service.submit(lookup=selection(preview), preview_witness=preview["preview_witness"], principal=o["who"])
    assert status["disposition"] == "unknown" and status["reason"] == "PHASE_ATTEMPT_UNRESOLVED"
    assert o["pr"].create_calls == 1
    observed = service.reconcile(selection(preview), o["who"])
    assert observed["disposition"] == "unknown" and observed["receipt"]["kind"] == "PROPOSAL_OBSERVED"
    assert o["pr"].create_calls == 1 and o["runtime"].jobs.list_jobs() == []


def test_private_peer_carrier_reuses_exact_verified_creation_identity_and_original(owner):
    from integrations.mastermind_workspace_app.contract import principal_frame
    from integrations.mastermind_workspace_app.source_operation_principal import bind_private_source_principal
    o = owner; service = o["service"]
    original = service.prepare(o["request"], o["who"])
    peer = [True]
    carried = bind_private_source_principal(principal_frame(o["who"]),
        verified_expires_at=o["who"].expires_at, peer_guard=lambda: peer[0])
    assert service.prepare(o["request"], carried) == original
    assert len(o["runtime"].store.list_events()) == 1
    result = service.submit(lookup=selection(original), preview_witness=original["preview_witness"], principal=carried)
    assert result["receipt"]["kind"] == "PROPOSAL_OBSERVED" and o["pr"].create_calls == 1
    peer[0] = False
    with pytest.raises(PermissionError):
        service.read_status(selection(original), carried)
    assert o["pr"].create_calls == 1 and o["runtime"].jobs.list_jobs() == []


@pytest.mark.parametrize("case", ["available", "expired", "read_only"])
def test_actual_private_app_peer_socket_reaches_same_create_owner(owner, short_socket_root, case):
    import asyncio
    import os
    from integrations.mastermind_workspace_app.contract import principal_frame
    from integrations.mastermind_workspace_app.source_operations import WorkspaceSourceOperationService
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    from common.workspace_source_operation_wire import FRAME_SCHEMA
    from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
    from tests.test_executive_ceo_ingress import _FakeGrounding, _config
    o = owner
    async def run():
        service = WorkspaceSourceOperationService(create_owner=o["service"])
        def factory(runtime, supervisor):
            assert runtime is o["runtime"] and supervisor is o["supervisor"]
            return service.installed_binding()
        host = ExecutiveControlService(_config(o["env"].tmp_path / "host", socket_root=short_socket_root, runtime_root=o["runtime"].store.root),
            runtime_factory=lambda _: o["runtime"], supervisor_factory=lambda _: o["supervisor"],
            ceo_ingress_socket_path=short_socket_root / "source.sock", ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(), armed=False,
                grounding_provider=_FakeGrounding(), source_operation_provider_factory=factory))
        await host.start()
        try:
            client = CeoIngressWorkspaceClient(host.ceo_ingress_socket_path)
            request = {"schema": FRAME_SCHEMA, "operation": "prepare", "principal": principal_frame(o["who"]),
                "verified_expires_at": 0 if case == "expired" else o["who"].expires_at,
                "request": {"action": "publish_project_proposal", "request": o["request"]}}
            if case == "read_only": o["bindings"]["profiles"]["member-0"]["project_authoring"] = None
            result = await client.request(request)
            if case != "available":
                assert result["ok"] is False and result["status"] == 403
                assert o["runtime"].store.list_events() == [] and o["pr"].create_calls == 0
                return
            preview = result["result"]
            assert preview["preview"]["goal"] == o["request"]["goal"]
            request["operation"] = "submit"
            request["request"] = preview["selection"] | {"preview_witness": preview["preview_witness"]}
            submitted = await client.request(request)
            assert submitted["result"]["receipt"]["kind"] == "PROPOSAL_OBSERVED"
            assert o["pr"].create_calls == 1
            assert await client.request(request) == submitted
            assert o["pr"].create_calls == 1
            request["operation"] = "read"
            request["request"] = selection(preview)
            assert await client.request(request) == submitted
            assert o["runtime"].jobs.list_jobs() == []
        finally:
            await host.close()
    asyncio.run(run())


def test_fixed_private_binding_rejects_foreign_runtime_or_replaced_context_before_any_source_io(owner, monkeypatch):
    from integrations.mastermind_workspace_app.source_operations import WorkspaceSourceOperationService
    from control_plane.workspace_source_operation_binding import invoke_source_operation
    from control_plane.executive_runtime import Runtime
    o = owner
    service = WorkspaceSourceOperationService(create_owner=o["service"])
    binding = service.installed_binding()
    foreign = Runtime.at(o["env"].tmp_path / "foreign-runtime")
    with pytest.raises(PermissionError):
        invoke_source_operation(binding, {}, runtime=foreign, supervisor=o["supervisor"], host_guard=lambda: True)
    def forbidden(*args): pytest.fail("replaced context callback invoked")
    monkeypatch.setattr(WorkspaceSourceOperationService, "_context_binding", forbidden)
    with pytest.raises(PermissionError):
        invoke_source_operation(binding, {}, runtime=o["runtime"], supervisor=o["supervisor"], host_guard=lambda: True)
    assert o["runtime"].store.list_events() == [] and o["pr"].create_calls == 0


@pytest.mark.parametrize("case", ["available", "available_outer", "post_pr_expiry", "read_only", "unsigned", "duplicate_body", "query_on_post"])
def test_actual_signed_http_socket_canonical_create_owner(owner, rsa_key, short_socket_root, settings, case):
    import asyncio
    import os
    import httpx
    from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
    from integrations.mastermind_workspace_app.contract import principal_frame, workspace_authorizers
    from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
    from integrations.mastermind_workspace_app.source_operations import WorkspaceSourceOperationService
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
    from tests.test_executive_ceo_ingress import _FakeGrounding, _config
    from tests.test_workspace_read_app import _authenticator, _workspace_token, NOW
    o = owner
    async def run():
        auth, token = _authenticator(rsa_key), _workspace_token(rsa_key)
        who = await auth.verify_authorization_header("Bearer " + token, now=NOW)
        _, document = project_bindings(selected=None)
        for slot in document["profiles"].values():
            slot["enabled"], slot["binding"] = False, None
        slot = document["profiles"][document["primary_profile"]]
        slot["enabled"] = True
        slot["binding"] = dict(principal_frame(who), permission_digest="a" * 64)
        slot["project_authoring"] = None if case == "read_only" else "b" * 64
        o["bindings"].clear(); o["bindings"].update(document)
        clock = [NOW]
        permissions = WorkspaceSourceOperationContextFactory(policy=auth.policy,
            load_bindings=lambda: o["bindings"], now=lambda: clock[0])
        o["service"]._permissions = permissions
        service = WorkspaceSourceOperationService(create_owner=o["service"])
        host = ExecutiveControlService(_config(o["env"].tmp_path / "http-host", socket_root=short_socket_root,
                runtime_root=o["runtime"].store.root), runtime_factory=lambda _: o["runtime"],
            supervisor_factory=lambda _: o["supervisor"], ceo_ingress_socket_path=short_socket_root / "source-http.sock",
            ceo_ingress_peer_uid=os.geteuid() + 1000, ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(), armed=False,
                grounding_provider=_FakeGrounding(), source_operation_provider_factory=lambda rt, su: service.installed_binding()))
        await host.start()
        try:
            peer = CeoIngressWorkspaceClient(host.ceo_ingress_socket_path)
            gate, _ = workspace_authorizers(policy=auth.policy,
                load_bindings=lambda: legacy_workspace_document(o["bindings"], auth.policy))
            app = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: clock[0],
                authorize_principal=gate, client=peer, source_operation_context=permissions))
            if case == "available_outer":
                from integrations.executive_mcp import server
                from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
                from tests.test_executive_mcp_app_composition import Sink
                sink = Sink()
                verifier = MastermindTokenVerifier(authenticator=auth, policy=auth.policy, now=lambda: NOW, audit_sink=sink)
                app = server.build_executive_mcp_app(settings, audit_sink=sink,
                    workspace_app=server.AuditedWorkspaceApp(app, verifier))
            headers = {"Content-Type": "application/json"}
            if case != "unsigned": headers["Authorization"] = "Bearer " + token
            body = json.dumps({"action": "publish_project_proposal", "request": o["request"]}, ensure_ascii=False)
            if case == "duplicate_body": body = body.replace('"action":', '"action":"publish_project_proposal","action":', 1)
            path = "/workspace/source-operation/prepare" + ("?actor=fake" if case == "query_on_post" else "")
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://mcp.mastermind-x.com") as client:
                response = await client.post(path, headers=headers, content=body.encode())
                assert response.headers["cache-control"] == "no-store"
                if case not in {"available", "available_outer", "post_pr_expiry"}:
                    assert response.status_code == {"read_only":403,"unsigned":401,"duplicate_body":400,"query_on_post":400}[case]
                    assert o["runtime"].store.list_events() == [] and o["pr"].create_calls == 0
                    return
                assert response.status_code == 200, response.text
                preview = response.json()
                assert preview["preview"]["goal"] == o["request"]["goal"]
                if case == "post_pr_expiry":
                    original_create = o["pr"].create
                    def expires_after_real_pr(*args):
                        receipt = original_create(*args)
                        clock[0] = who.expires_at
                        return receipt
                    o["pr"].create = expires_after_real_pr
                submitted = await client.post("/workspace/source-operation/submit", headers=headers,
                    json=preview["selection"] | {"preview_witness": preview["preview_witness"]})
                if case == "post_pr_expiry":
                    assert submitted.status_code == 403
                    assert o["pr"].create_calls == 1
                    assert [e.payload["kind"] for e in o["runtime"].store.list_events()] == ["INTENT", "PHASE_ATTEMPTED"]
                    assert o["runtime"].jobs.list_jobs() == []
                    return
                assert submitted.status_code == 200, submitted.text
                assert submitted.json()["receipt"]["kind"] == "PROPOSAL_OBSERVED" and o["pr"].create_calls == 1
                before = len(o["runtime"].store.list_events())
                status = await client.get("/workspace/source-operation/operation", headers=headers, params=preview["selection"])
                assert status.status_code == 200 and status.json() == submitted.json()
                assert len(o["runtime"].store.list_events()) == before and o["pr"].create_calls == 1
                if case == "available_outer":
                    for method, path, extra in [
                        ("GET", "/workspace/source-operation/prepare", {}),
                        ("POST", "/workspace/source-operation/submit?x=1", {}),
                        ("POST", "/workspace/source-operation/operation", {}),
                        ("POST", "/workspace/source-operation/submit", {"Origin": "https://foreign.example"}),
                    ]:
                        denied = await client.request(method, path, headers=headers | extra, json={})
                        assert denied.status_code in {403,404}, denied.text
                    assert len(o["runtime"].store.list_events()) == before
                assert o["runtime"].jobs.list_jobs() == []
        finally: await host.close()
    asyncio.run(run())


def test_actual_creation_child_capture_uses_original_git_code_and_programmes(owner):
    from control_plane.agentos_project_creation_recipe import capture_creation_recipe
    o = owner
    prepared = o["adapter"].prepare(o["request"], o["who"])
    request = prepared.private_payload()["initial_snapshot"]["compiler_request"]
    commit = o["request"]["expected_macro_sha"]
    kwargs = dict(macro_root=o["env"].clone, expected_macro_sha=commit, code_commit=commit)
    captured = capture_creation_recipe(**kwargs, request=request)
    assert captured["recipe"] == o["adapter"].proposal_recipe(prepared)
    assert captured["source_binding"] == prepared.private_payload()["source_binding"]
    assert captured["programs"] == prepared.private_payload()["initial_snapshot"]["programs"]
    # Working imports cannot substitute a different compiler or programme list.
    (o["env"].clone / "scripts/agentos_project_proposal.py").write_text('raise RuntimeError("unqualified worktree import")\n')
    assert capture_creation_recipe(**kwargs, request=request) == captured
    git(o["env"].clone, "checkout", "--", "scripts/agentos_project_proposal.py")
    (o["env"].clone / "unrelated.txt").write_text("new source head\n")
    git(o["env"].clone, "add", "unrelated.txt"); git(o["env"].clone, "commit", "-m", "Advance unrelated source")
    current = rev_parse(o["env"].clone, "HEAD")
    assert capture_creation_recipe(**(kwargs | {"expected_macro_sha": current}), request=request) == captured
    with pytest.raises(ValueError, match="source_changed"):
        capture_creation_recipe(**kwargs, request=request)
    assert o["runtime"].store.list_events() == [] and o["runtime"].jobs.list_jobs() == []


@pytest.mark.parametrize("no_site", [False, True])
@pytest.mark.parametrize("installed_runtime", [True, False])
def test_real_isolated_creation_recipe_entry_closed_output(owner, no_site, installed_runtime, monkeypatch):
    import subprocess
    from ops.executive_os import capacity_source_contract
    if not installed_runtime:
        # Simulate the absent native installation with a real dependency-complete
        # project interpreter. On this Mac the qualified boot Python supplies
        # that capability; hosted CI uses its actual project Python. The child
        # still executes -I and its real captured compiler, with -S as a negative.
        project_python = (capacity_source_contract.PYTHON_BINARY
                          if capacity_source_contract.PYTHON_BINARY.is_file()
                          else Path(sys.executable))
        monkeypatch.setattr(sys, "executable", str(project_python))
        monkeypatch.setattr(capacity_source_contract, "PYTHON_BINARY",
                            owner["env"].clone / "absent-installed-python")
    from ops.executive_os.capacity_source_contract import PYTHON_BINARY
    o = owner
    prepared = o["adapter"].prepare(o["request"], o["who"])
    request = prepared.private_payload()["initial_snapshot"]["compiler_request"]
    commit = o["request"]["expected_macro_sha"]
    # Native qualification uses the installed boot environment; hosted source
    # CI uses its dependency-complete project interpreter. Both remain isolated.
    interpreter = PYTHON_BINARY if PYTHON_BINARY.is_file() else Path(sys.executable)
    command = [str(interpreter), "-I", "-B"] + (["-S"] if no_site else [])
    command += [str(Path(__file__).parents[1] / "scripts/agentos_project_creation_recipe_entry.py"),
        "--macro-root", str(o["env"].clone), "--expected-macro-sha", commit, "--timeout", "10"]
    raw = json.dumps({"schema": "mastermind.project_creation_recipe_capture_request.v1", "code_commit": commit,
                      "request": request}, ensure_ascii=False).encode()
    result = subprocess.run(command, input=raw, capture_output=True, timeout=15)
    assert result.stderr == b"", result.stderr
    body = json.loads(result.stdout)
    if no_site:
        assert result.returncode == 1 and body == {"schema": "mastermind.project_creation_recipe_unavailable.v1"}
    else:
        assert result.returncode == 0 and body["recipe"] == o["adapter"].proposal_recipe(prepared)
        assert body["source_binding"] == prepared.private_payload()["source_binding"]


def test_source_restore_failure_before_any_publisher_call_retains_actual_no_effect(owner, monkeypatch):
    o = owner; service = o["service"]
    preview = service.prepare(o["request"], o["who"])
    def unavailable(*args, **kwargs): raise ValueError("source unavailable")
    monkeypatch.setattr(o["adapter"], "_compile_proposal", unavailable)
    body = service.submit(lookup=selection(preview), preview_witness=preview["preview_witness"], principal=o["who"])
    assert body["disposition"] == "refused" and body["reason"] == "NOT_DISPATCHED"
    assert [event.payload["kind"] for event in o["runtime"].store.list_events()] == ["INTENT", "PHASE_ATTEMPTED", "NOT_DISPATCHED"]
    assert o["pr"].create_calls == 0 and o["runtime"].jobs.list_jobs() == []
