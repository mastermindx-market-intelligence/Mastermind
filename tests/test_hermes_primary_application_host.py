"""Hermes primary host composition, original admission and credential boundaries.

Native state and secrets are disposable fixtures. These tests prove integration
contracts and refusal behavior; they do not claim a provider/account canary.
"""
import asyncio
import copy
from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace as N
from unittest.mock import Mock
import sys

import pytest

from integrations.hermes_application_fabric import host
from integrations.hermes_application_fabric.client import ApplicationBinding, HermesApplicationClient, NativeCall
from integrations.hermes_application_fabric.errors import HermesFabricError
from integrations.hermes_application_fabric import publication as pub
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime.profile import dump_profile, load_profile_bytes
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.secrets import Secrets
from integrations.hermes_runtime import native_session_control as control
from integrations.hermes_runtime import tcp_sandbox
from integrations.hermes_runtime.tests.test_operator_native_enrollment import enrollment_command


def document(role="mmsecretary"):
    return dict(schema=pub.SCHEMA, role=role, enrollment_request_id="fixture-enrollment",
        principal_id="uid:12345", macro_root="/opt/fixture-application/" + "a" * 40,
        macro_commit_sha="a" * 40, model="deepseek-v4.1-flash", max_tokens=1024,
        package_sha256="b" * 64)


def test_auto_publication_is_explicit_and_not_a_fixed_model_reinterpretation():
    raw = document()
    assert pub.publication_from_document(raw).automatic is False
    raw.update(schema=pub.AUTO_SCHEMA, model=pub.AUTO_MODEL,
               routing={"mode": "auto", "strict_pool": "go"})
    selected = pub.publication_from_document(raw)
    assert selected.automatic is True and selected.strict_pool == "go"
    for changed in ({"model": "deepseek-v4.1-flash"}, {"schema": pub.SCHEMA},
                    {"routing": {"mode": "auto", "strict_pool": "go", "api_key": "foreign"}}):
        with pytest.raises(HermesFabricError): pub.publication_from_document({**raw, **changed})


def test_exact_publication_keeps_concrete_model_and_qualified_pool_constraint():
    raw = document()
    raw.update(schema=pub.EXACT_SCHEMA, routing={"mode": "exact", "strict_pool": "go"})
    selected = pub.publication_from_document(raw)
    assert selected.automatic is True
    assert selected.strict_model == selected.model == raw["model"]
    assert selected.strict_pool == "go"
    for changed in ({"model": pub.AUTO_MODEL}, {"model": None}, {"schema": pub.AUTO_SCHEMA},
                    {"routing": {"mode": "auto", "strict_pool": "go"}},
                    {"routing": {"mode": "exact", "strict_pool": "go", "account": "foreign"}}):
        with pytest.raises(HermesFabricError):
            pub.publication_from_document({**raw, **changed})


def profile(tmp_path, role="mmsecretary"):
    base = compose_profile(role, state_dir=tmp_path / role,
        hermes_home=tmp_path / role / "current/hermes-home", secrets_file=tmp_path / (role + ".env"))
    return replace(base, model_provider=pub.PROVIDER, model_default=document()["model"],
        native_provider_id=None, gateway_backend="native-session-authority",
        gateway_host=pub.ROLE_RELATIONS[role][3], tool_allowlist=frozenset({"clarify"}))


@pytest.mark.parametrize("role", pub.ROLE_RELATIONS)
def test_application_profile_and_config_are_keyless_and_closed(tmp_path, role):
    selected = profile(tmp_path, role)
    raw = dump_profile(selected).encode()
    loaded = load_profile_bytes(raw, source_path=tmp_path / "profile.yaml", hermes_home=selected.hermes_home)
    assert loaded.model_provider == pub.PROVIDER and loaded.native_provider_id is None
    from integrations.hermes_steward.config_guard import _load_unique_yaml
    native = _load_unique_yaml(pub.expected_native_config(selected, document(role)).encode())
    assert native["model"] == {"provider": pub.PROVIDER, "default": selected.model_default,
                               "api_mode": "chat_completions"}
    assert native["fallback_providers"] == []
    assert "providers" not in native and "auxiliary" not in native
    assert native["mcp_servers"]["mastermind_steward"]["enabled"] is False
    for wrong in (replace(selected, gateway_backend="standalone"),
                  replace(selected, native_provider_id="zai.glm-5.3")):
        with pytest.raises(RuntimeRefusal):
            load_profile_bytes(dump_profile(wrong).encode(), source_path=tmp_path / "wrong.yaml")


@pytest.mark.parametrize("key,value", [
    ("schema", "foreign"), ("role", "brain"), ("principal_id", "root"),
    ("macro_root", "/tmp/ambient-checkout"), ("macro_root", "/tmp/../" + "a" * 40),
    ("macro_commit_sha", "c" * 40), ("model", "a\ncredential"),
    ("max_tokens", True), ("max_tokens", 0), ("max_tokens", 4097),
    ("package_sha256", "invalid"), ("enrollment_request_id", ""),
])
def test_publication_rejects_unbound_identity_and_bounds(key, value):
    raw = document()
    raw[key] = value
    with pytest.raises(HermesFabricError):
        pub.publication_from_document(raw)


@pytest.mark.parametrize("key", ["api_key", "token", "base_url", "factory", "credential_ref", "route_scope"])
def test_publication_has_no_secret_or_router_override(key):
    raw = document()
    raw[key] = "untrusted"
    with pytest.raises(HermesFabricError):
        pub.validate_publication(raw)


def test_installation_joins_exact_enrollment_import_root_and_principal():
    raw = document()
    options = dict(role=raw["role"], enrollment={"request_id": raw["enrollment_request_id"]},
                   import_roots=[raw["macro_root"]], principal_id=raw["principal_id"])
    assert pub.qualify_installation(raw, **options) == pub.publication_from_document(raw)
    for key, value in [("role", "mmmeta"), ("enrollment", {"request_id": "other"}),
                       ("import_roots", ["/tmp/other"]), ("principal_id", "uid:23456")]:
        with pytest.raises(HermesFabricError):
            pub.qualify_installation(raw, **{**options, key: value})


@pytest.mark.parametrize("role", pub.ROLE_RELATIONS)
def test_primary_env_forwards_only_exact_internal_role_reference(tmp_path, role):
    selected, raw = profile(tmp_path, role), document(role)
    reference = pub.ROLE_RELATIONS[role][2]
    value = "fixture-internal-application-credential-0123456789"
    secrets = Secrets("front-door-token", "hermes", "dashboard-password",
        {reference: value, "ZAI_API_KEY": "fixture-provider-key-never-forwarded"})
    assert pub.primary_child_env(selected, raw, secrets) == {
        reference: value, "HERMES_STARTUP_WARMUP_TIMEOUT": "0"}
    for values in ({}, {reference: value, "OTHER_KEY": value},
                   {reference: value, pub.ROLE_RELATIONS["mmmeta" if role == "mmsecretary" else "mmsecretary"][2]: "other"}):
        with pytest.raises(HermesFabricError):
            pub.primary_child_env(selected, raw, Secrets("front", "hermes", "dashboard", values))


def test_application_port_is_connect_only_and_requires_qualified_launch(tmp_path, monkeypatch):
    selected = profile(tmp_path)
    with pytest.raises(RuntimeRefusal):
        tcp_sandbox.role_tcp_ports(selected)
    bind, connect = tcp_sandbox.role_tcp_ports(selected, primary_application=document())
    assert pub.APPLICATION_PORT in connect and pub.APPLICATION_PORT not in bind
    assert len(bind) == 2 and len(connect) == 4
    events = []
    launch = N(recipe={"primary_application": document()},
        qualify=lambda *args: events.append("qualified"))
    monkeypatch.setattr(tcp_sandbox, "apply_tcp_port_policy", lambda *args: events.append(args))
    tcp_sandbox.enforce_role_tcp_ports(selected, native_launch=launch)
    assert events == ["qualified", (bind, connect)]
    with pytest.raises(RuntimeRefusal):
        tcp_sandbox.enforce_role_tcp_ports(selected)


def test_supervisor_application_branch_does_not_resolve_provider_keys(tmp_path, monkeypatch):
    from integrations.hermes_runtime import supervisor
    from integrations.hermes_harness import native_model_credential
    selected, raw = profile(tmp_path), document()
    native = selected.hermes_home / "profiles" / selected.role / "config.yaml"
    native.parent.mkdir(parents=True)
    native.write_text(pub.expected_native_config(selected, raw))
    native.chmod(0o600)
    reference = pub.ROLE_RELATIONS[selected.role][2]
    secret = "fixture-internal-application-credential-0123456789"
    secrets = Secrets("front-door-token", "hermes", "dashboard-password", {reference: secret})
    launch = N(recipe={"primary_application": raw, "vendor_root": "/opt/fixture-hermes"},
               qualify=Mock())
    monkeypatch.setattr(native_model_credential, "primary_model_env",
                        lambda *args: pytest.fail("provider key owner entered"))
    runtime = supervisor.ServiceRuntime(selected, secrets, selected.state_dir / "current/bin/hermes",
                                        native_launch=launch)
    env = runtime._model_child_env()
    assert env[reference] == secret and env["HERMES_STARTUP_WARMUP_TIMEOUT"] == "0"
    assert not any(key.endswith("_API_KEY") for key in env)


def _module(monkeypatch, name, **values):
    module = ModuleType(name)
    module.__dict__.update(values)
    monkeypatch.setitem(sys.modules, name, module)
    return module


async def claim_fixture(monkeypatch, tmp_path, *, exact=False):
    raw = document()
    if exact:
        raw.update(schema=pub.EXACT_SCHEMA, routing={"mode": "exact", "strict_pool": "go"})
    role_home = tmp_path / "role-home"
    owner = N(root=tmp_path / ("d" * 40), source=lambda path: ("held:" + path).encode())
    raw["package_sha256"] = pub.held_package_digest(owner)
    manager = N(scope_key=str(role_home), _middleware={"llm_execution": []})
    _module(monkeypatch, "hermes_cli.plugins", get_plugin_manager=lambda: manager)
    authority = N(profile_id=str(role_home), instance_id="instance-one", epoch=7, retired=False,
                  sessions={}, executing={"logical": 3}, adopted={}, db=object())
    execution = dict(authority_epoch=7, execution_generation=3, admission_id="original-admission")
    live = N(event_stream=N(execution=execution))
    authority.sessions["logical"] = live
    runner = N(session_authority=authority, _draining=False,
               session_runtime_descriptor=dict(state="ready", instance_id="instance-one", authority_epoch=7))
    rows = {"original-admission": dict(admission_id="original-admission", request_id="original-command",
        principal_id=raw["principal_id"], target_session_id="logical", intent="queue", status="started",
        owner_epoch=7, generation=3)}
    _module(monkeypatch, "gateway.session_authorities", active_authority=lambda runner: authority,
            admission_owner=lambda authority, sid: "logical" if sid == "physical" else None)
    _module(monkeypatch, "hermes_state_runtime", get_session_admission=lambda db, admission_id: rows.get(admission_id))
    target = dict(profile_id=str(role_home), principal_id=raw["principal_id"], session_id="logical",
                  instance_id="instance-one", authority_epoch=7)
    enrolled = dict(status="ENROLLED", target=target, route={"fixture": "original-route"})
    monkeypatch.setattr(control, "current_runtime_owner", lambda: owner.root.name)
    monkeypatch.setattr(control, "read_enrolled_session", lambda *args, **kwargs: copy.deepcopy(enrolled))
    factory = N(inspect=Mock(return_value={"model": raw["model"]}))
    factory_calls = []
    factory.with_requested_model = lambda model: (factory_calls.append(("model", model)), factory)[1]
    factory.with_inspection = lambda inspection: (factory_calls.append(("inspection", inspection)), factory)[1]
    _module(monkeypatch, "engine.provider_production_modes", make_application_fabric_factory=lambda **kwargs: factory)
    launch = N(owner=owner, recipe={"primary_application": raw}, check=Mock())
    native = host._NativeHost(runner, launch, role_home, raw, manager)
    setattr(runner, host._HOST, native)
    native.middleware = object()
    manager._middleware["llm_execution"].append(native.middleware)
    source = N(platform=N(value="local"), chat_id="logical", user_id=raw["principal_id"])
    ctx = N(source=source, inbound_message_id="original-admission", session_id="physical",
            _run_still_current=lambda: True, agent_holder=[None])
    turn = N(_approval_owner=(authority, "logical", 3))
    cap = native.capture(ctx, turn)
    agent = N(provider=pub.PROVIDER, model=raw["model"], api_mode="chat_completions",
        api_key=None, base_url=None, credential_pool=None, _fallback_chain=[],
        _fallback_activated=False, client=HermesApplicationClient(), session_id="physical",
        _current_task_id="physical", _current_turn_id="native-turn", _current_api_request_id="native-api")
    cap.agent, ctx.agent_holder[0] = agent, agent
    authority.adopted["logical"] = (3, agent)
    call = NativeCall("physical", "physical", "native-turn", "native-api")
    return N(raw=raw, native=native, runner=runner, authority=authority, live=live, rows=rows,
             factory=factory, factory_calls=factory_calls, ctx=ctx, turn=turn, cap=cap,
             agent=agent, call=call, enrolled=enrolled)


def test_native_host_narrows_exact_model_before_freezing_original_inspection(monkeypatch, tmp_path):
    async def check():
        case = await claim_fixture(monkeypatch, tmp_path, exact=True)
        assert case.factory_calls == [("model", case.raw["model"]),
                                      ("inspection", {"model": case.raw["model"]})]
        seen = []
        original = object.__new__(ApplicationBinding)
        original._owner = N(close=lambda: None)
        monkeypatch.setattr(ApplicationBinding, "from_factory",
            lambda factory, **kwargs: (seen.append(kwargs), original)[1])
        assert case.cap.resolve(case.call) is original
        assert seen[0]["strict_model"] == case.raw["model"]
        assert seen[0]["strict_pool"] == "go" and seen[0]["automatic"] is True
        assert seen[0]["operation_id"] == "original-admission"
    asyncio.run(check())


def test_current_native_claim_joins_every_identity_before_first_binding(monkeypatch, tmp_path):
    async def check():
        case = await claim_fixture(monkeypatch, tmp_path)
        assert case.cap.authorized(case.call) is True
        seen = []
        original = object.__new__(ApplicationBinding)
        original._owner = N(close=lambda: None)
        monkeypatch.setattr(ApplicationBinding, "from_factory", lambda factory, **kwargs: (seen.append(kwargs), original)[1])
        assert case.cap.resolve(case.call) is original
        assert case.cap.resolve(case.call) is original
        assert len(seen) == 1 and seen[0]["operation_id"] == "original-admission"
        assert seen[0]["session_id"] == "physical" and seen[0]["turn_id"] == "native-turn"
        assert seen[0]["prior_admission_possible"] is False
        case.cap.close()
        with pytest.raises(HermesFabricError):
            case.cap.resolve(case.call)
        assert len(seen) == 1
    asyncio.run(check())


@pytest.mark.parametrize("mutation", ["principal", "submission", "epoch", "generation", "unknown",
    "execution", "adopted", "api_id", "task_id", "session_id", "route", "drain", "fallback", "grant"])
def test_revoked_or_changed_claim_cannot_return_executable_tool_response(monkeypatch, tmp_path, mutation):
    async def check():
        case = await claim_fixture(monkeypatch, tmp_path)
        assert case.cap.authorized(case.call)
        row = case.rows["original-admission"]
        if mutation == "principal": row["principal_id"] = "uid:23456"
        elif mutation == "submission": row["request_id"] = "replacement-command"
        elif mutation == "epoch": row["owner_epoch"] += 1
        elif mutation == "generation": row["generation"] += 1
        elif mutation == "unknown": row["status"] = "unknown"
        elif mutation == "execution": case.live.event_stream.execution["admission_id"] = "other"
        elif mutation == "adopted": case.authority.adopted["logical"] = (3, object())
        elif mutation == "api_id": case.agent._current_api_request_id = "other"
        elif mutation == "task_id": case.agent._current_task_id = "other"
        elif mutation == "session_id": case.agent.session_id = "other"
        elif mutation == "route": case.enrolled["route"] = {"fixture": "replacement"}
        elif mutation == "drain": case.runner._draining = True
        elif mutation == "fallback": case.agent._fallback_chain = [{"provider": "foreign"}]
        elif mutation == "grant": case.factory.inspect.side_effect = ValueError("revoked")
        assert case.cap.authorized(case.call) is False
        with pytest.raises(HermesFabricError): case.cap.resolve(case.call)
        assert case.cap.bind_attempted is False
    asyncio.run(check())


@pytest.mark.parametrize("active,uncertain,admission_possible,result", [
    (False, True, True, {"effect_unknown": True}),
    (True, False, True, {"disposition": "refused", "closed": False, "effect_unknown": False}),
    (False, False, True, {"disposition": "refused", "closed": False, "effect_unknown": False}),
    (True, False, True, {"disposition": "closed", "closed": True, "effect_unknown": False}),
    (False, False, True, {"disposition": "local_only", "attempted": False, "effect_unknown": False}),
    (False, False, True, None),
])
def test_repeated_builder_and_unresolved_binding_never_create_replacement(
        monkeypatch, tmp_path, active, uncertain, admission_possible, result):
    async def check():
        case = await claim_fixture(monkeypatch, tmp_path)
        with pytest.raises(HermesFabricError, match="original_recovery_required"):
            case.native.capture(case.ctx, case.turn)
        original = object.__new__(ApplicationBinding)
        original._owner = N(_active=active, _uncertain=uncertain,
            _admission_possible=admission_possible, _close_result=result, close=lambda: None)
        case.cap.binding = original
        case.cap.close()
        case.rows["original-admission"]["status"] = "terminal"
        next_row = {**case.rows["original-admission"], "admission_id": "next-admission",
                    "request_id": "next-command", "status": "started", "generation": 4}
        case.rows["next-admission"] = next_row
        case.ctx.inbound_message_id = "next-admission"
        case.turn._approval_owner = (case.authority, "logical", 4)
        with pytest.raises(HermesFabricError, match="previous_effect_unresolved"):
            case.native.capture(case.ctx, case.turn)
        assert getattr(case.live, host._CAPABILITY) is case.cap
    asyncio.run(check())


@pytest.mark.parametrize("admitted,result", [
    (True, {"disposition": "closed", "closed": True, "effect_unknown": False, "attempted": True}),
    (False, {"disposition": "local_only", "closed": False, "effect_unknown": False, "attempted": False}),
])
def test_new_admission_after_original_proven_close_preserves_native_owner(monkeypatch, tmp_path, admitted, result):
    async def check():
        case = await claim_fixture(monkeypatch, tmp_path)
        original = object.__new__(ApplicationBinding)
        original._owner = N(_active=False, _uncertain=False, _admission_possible=admitted,
                            _close_result=result, close=lambda: result)
        case.cap.binding = original
        case.cap.close()
        case.rows["original-admission"]["status"] = "terminal"
        case.rows["next-admission"] = {**case.rows["original-admission"],
            "admission_id": "next-admission", "request_id": "next-command", "status": "started", "generation": 4}
        case.ctx.inbound_message_id = "next-admission"
        case.turn._approval_owner = (case.authority, "logical", 4)
        case.authority.executing["logical"] = 4
        case.live.event_stream.execution = dict(authority_epoch=7, execution_generation=4, admission_id="next-admission")
        successor = case.native.capture(case.ctx, case.turn)
        assert successor.admission_id == "next-admission" and successor.binding is None
        assert case.cap.binding is original
    asyncio.run(check())


def test_accepted_primary_profile_refuses_mixed_eval_before_credentials(tmp_path, monkeypatch):
    from integrations.hermes_runtime.tests.test_native_eval_inputs import selected_recipe
    from dataclasses import replace
    from integrations.hermes_harness.stack import compose_profile
    from integrations.hermes_runtime import install as installer
    from integrations.hermes_runtime.profile import dump_profile

    _, recipe, _ = selected_recipe()
    selected = replace(compose_profile("mmmeta", state_dir=tmp_path / "uncreated-state",
        secrets_file=tmp_path / "unread-secrets.env"),
        model_provider="mastermind-fabric", native_provider_id=None,
        gateway_backend="native-session-authority")
    path = tmp_path / "primary-profile.yaml"
    path.write_text(dump_profile(selected))
    monkeypatch.setattr(installer, "load_secrets",
        lambda *a, **kw: pytest.fail("unsupported profile reached credentials"))
    with pytest.raises(RuntimeRefusal) as refused:
        installer.install(profile_path=path, state_dir=selected.state_dir,
            systemd_user_dir=tmp_path / "uncreated-units", secrets_file=selected.secrets_file,
            hermes_bin=tmp_path / "unread-launcher", upstream_source=Path(recipe["vendor_root"]),
            native_installation=recipe)
    # The APPLICATION composition accepts the primary profile. Its explicit
    # mixed-EVAL guard must still refuse before any credential or state access.
    assert refused.value.code == "NATIVE_EVAL_INPUTS_UNQUALIFIED"
    assert not selected.state_dir.exists()


@pytest.mark.parametrize("application_profile,with_primary", [(True, False), (True, True), (False, True)])
@pytest.mark.parametrize("empty_inputs", [False, True])
def test_mixed_eval_config_refuses_before_filesystem_read(
        tmp_path, monkeypatch, application_profile, with_primary, empty_inputs):
    from integrations.hermes_runtime.tests.test_native_eval_inputs import selected_recipe
    from dataclasses import replace
    from integrations.hermes_harness.stack import compose_profile
    from integrations.hermes_runtime.supervisor import expected_disabled_mcp

    _, recipe, consumer = selected_recipe()
    selected = compose_profile("mmmeta", state_dir=tmp_path / "uncreated-state",
        secrets_file=tmp_path / "unread-secrets.env")
    if application_profile:
        selected = replace(selected, model_provider="mastermind-fabric", native_provider_id=None)
    primary = {"schema": "unaccepted-primary-fixture"} if with_primary else None
    evaluation_inputs = {} if empty_inputs else recipe["evaluation_inputs"]
    with monkeypatch.context() as fence:
        fence.setattr(Path, "exists", lambda *_: pytest.fail("mixed selection inspected config"))
        fence.setattr(Path, "is_symlink", lambda *_: pytest.fail("mixed selection inspected config"))
        with pytest.raises(RuntimeRefusal, match="NATIVE_EVAL_INPUTS_UNQUALIFIED"):
            expected_disabled_mcp(selected, consumer, primary, evaluation_inputs=evaluation_inputs)


@pytest.mark.parametrize("with_primary", [False, True])
def test_shared_enrollment_attaches_tcp_policy_once_before_asyncio(
    enrollment_command, monkeypatch, capsys, with_primary,
):
    import asyncio
    import json
    from integrations.hermes_runtime import cli
    enforce = tcp_sandbox.enforce_role_tcp_ports
    world = enrollment_command(
        role="mmmeta", primary_application=document("mmmeta") if with_primary else None)
    calls = []
    expected_ports = tcp_sandbox.role_tcp_ports(
        world.profile, primary_application=world.launch.recipe.get("primary_application"))

    def policy(bind_ports, connect_ports):
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        calls.append((bind_ports, connect_ports))

    # Exercise the real launch-aware qualifier; replace only kernel attachment.
    monkeypatch.setattr(tcp_sandbox, "enforce_role_tcp_ports", enforce)
    monkeypatch.setattr(tcp_sandbox, "apply_tcp_port_policy", policy)
    assert cli._enroll_meta_session(world.path, world.binary, native_launch=world.launch) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ENROLLED"
    assert calls == [expected_ports]
    assert world.state.creations == 1 and world.state.qualifications >= 4
