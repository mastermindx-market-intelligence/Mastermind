"""Original EVAL artifact/store and native admission input boundaries.

Fixtures are synthetic PUBLIC_SAFE documents. Host custody, enrollment and
provider service are explicit edges; these tests confer no installed grant or
complete EVAL result. Native lifecycle cases execute the pinned owner bodies.
"""
from __future__ import annotations

import asyncio
import ast
import contextlib
from functools import partial
import copy
import hashlib
from urllib.parse import urlparse
import json
import logging
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
import uuid
from types import SimpleNamespace

import pytest
import httpx

from integrations.hermes_runtime import native_eval_inputs as inputs
from integrations.hermes_runtime import native_request_observation as observation
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.tests.test_native_agentos_memory import decoded_fixture, actual_result
from integrations.hermes_harness.tests.test_native_current_agentos_context import (
    lifecycle, current_result, signed, rsa_key, joined, owner, env, isolated_git_env, identity,
)
from integrations.hermes_runtime.tests.test_native_request_observation import native
from integrations.hermes_runtime.tests.test_native_transport_observation import engine, success
from integrations.hermes_models.contract import native_provider
from scripts.agent_eval import contracts
from ops.executive_os.native_gateway_sources import DERIVATION_BASE, EVAL_INPUTS_DERIVATION_PATCH
from scripts.agent_eval.canonical import add_document_digest, canonical_json_bytes, digest_value
from scripts.agent_eval.harness2_native import harness_digest
from scripts.agent_eval.store import ArtifactStore
from tests.agent_eval_factories import (
    REPO_REF_BASE, _configuration_fields, build_baseline_scenario_fields,
    build_two_arm_experiment, fresh_run_id,
)


def documents(profile_id, *, context="Known fixture facts.\n", files=None, record_sources=None):
    files = files or {"AGENTS.md": "Use the original source and preserve uncertainty.\n"}
    text = "Identify the canonical owner for this synthetic fixture."
    fields = build_baseline_scenario_fields()
    fields["scenario_id"] = "scenario:evaluation_contract_integrity:native_warm_inputs"
    fields["input_fixture"]["digest"] = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
    fields["execution_policy"].update(fresh_process_required=False, fresh_workspace_required=False,
        fresh_session_required=False, resume_allowed=True)
    fields["privacy"]["retention_class"] = "DURABLE_SANITIZED"
    fields["capability_policy"]["profile_id"] = profile_id
    config = _configuration_fields(arm_marker="native_fixture")
    config["capabilities"]["profile_id"] = profile_id
    config["execution"].update(execution_surface="hermes-native", provider="custom",
        model_requested="glm-5.3", reasoning_effort="low", execution_surface_version=inputs.producer_descriptor(
            "a" * 40, DERIVATION_BASE, EVAL_INPUTS_DERIVATION_PATCH)["execution_surface_version"])
    config["randomness"]["seed"] = 0
    config["procedure"]["instruction_bundle"]["digest"] = harness_digest({k: v.encode() for k, v in files.items()})
    config["context"]["context_packet"]["digest"] = "sha256:" + hashlib.sha256(context.encode()).hexdigest()
    fields["source_policy"]["allowlist_artifacts"] = sorted(
        [fields["input_fixture"], config["context"]["context_packet"], *(record_sources or [])],
        key=lambda row: row["artifact_ref"])
    fields["privacy"]["model_visible_artifact_refs"] = sorted(
        row["artifact_ref"] for row in fields["source_policy"]["allowlist_artifacts"])
    scenario = contracts.build_scenario(fields, schema=(contracts.SCENARIO_SCHEMA_V2
        if record_sources is not None else contracts.SCENARIO_SCHEMA))
    config["capabilities"]["network_policy_digest"] = contracts.compute_scenario_network_policy_digest(scenario)
    return scenario, contracts.build_configuration(config), text, files, context


def source_owner(root, profile_id, *, scenario=None, configuration=None, context="Known fixture facts.\n", files=None,
                 record_sources=None):
    scenario0, configuration0, text, files, context = documents(
        profile_id, context=context, files=files, record_sources=record_sources)
    scenario, configuration = scenario or scenario0, configuration or configuration0
    store = ArtifactStore(root)
    store.create(scenario)
    store.create(configuration)
    owner = object.__new__(inputs.NativeEvalInputOwner)
    owner.store, owner.release = store, "a" * 40
    owner.profile_id = profile_id
    owner.profile_digest = configuration["capabilities"]["profile_digest"]
    info = store.root.lstat()
    owner.root_identity = (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode))
    owner.producer = inputs.producer_descriptor(owner.release, DERIVATION_BASE, EVAL_INPUTS_DERIVATION_PATCH)
    owner.publication = {"artifact_root": str(store.root), "root_identity": dict(zip(
        ("device", "inode", "uid", "mode"), owner.root_identity))}
    owner.provider_spec = native_provider("mmmeta", "zai.glm-5.3")
    owner.check = lambda: None  # Explicit held-source/host custody edge.
    owner.require_enrollment = lambda *_: None  # Explicit enrollment edge.
    specification = dict(run_id=fresh_run_id(), scenario_id=scenario["scenario_id"],
        scenario_version=scenario["scenario_version"], scenario_digest=scenario["scenario_digest"],
        configuration_id=configuration["configuration_id"], configuration_digest=configuration["configuration_digest"],
        experiment_id=None, experiment_digest=None, arm_id=None, pair_key=None, replicate_index=None,
        candidate_files=files, context_text=context)
    return SimpleNamespace(owner=owner, scenario=scenario, configuration=configuration, text=text,
                           specification=specification, principal="fixture-principal", session="session-1")


@pytest.fixture
def trial(tmp_path):
    return source_owner(tmp_path / "store", str(tmp_path / "profile"))


def select(trial):
    return trial.owner.select(trial.specification, principal=trial.principal, session_id=trial.session,
        submission_id=inputs.submission_id_for_run(trial.specification["run_id"]), text=trial.text)


def marker(trial):
    return json.loads(select(trial).encoded)


def reseal(value):
    value["binding_sha256"] = hashlib.sha256(canonical_json_bytes(
        {key: item for key, item in value.items() if key != "binding_sha256"})).hexdigest()
    return value


def test_existing_store_selection_is_detached_and_exact(trial):
    selected = select(trial)
    before = selected.encoded
    trial.specification["candidate_files"]["AGENTS.md"] = "changed by caller"
    assert selected.encoded == before
    value = inputs.validate_marker(json.loads(before), text=trial.text)
    assert value["configuration"]["randomness"]["seed"] == 0
    assert value["input"]["submission_id"] == inputs.submission_id_for_run(value["run_id"])
    assert value["source"]["release"] == "a" * 40
    assert value["producer"] == trial.owner.producer
    assert value["publication"] == trial.owner.publication
    assert trial.owner.store.resolve_run(value["run_id"]) is None


def test_historical_v1_bytes_remain_readable_without_new_provenance_or_live_store():
    path = Path(__file__).parent / "fixtures/native_eval_inputs/legacy_marker_v1.json"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "c6252ddb43104a4752a9ee8da9a9a1da3576a3b287a95b3a5a1dcb3e9bafbd87"
    payload = json.loads(raw)
    old = payload[inputs.MARKER_KEY]
    assert old["schema"] == inputs.LEGACY_MARKER_SCHEMA
    assert inputs.validate_marker(old, text=payload["text"]) == old
    assert "producer" not in old and "publication" not in old
    assert inputs.retained_admission_payload(payload) == payload


@pytest.mark.parametrize("mutation", ["release", "runner", "surface", "version", "root_relative", "root_parent",
    "root_alias", "mode", "inode", "extra", "legacy_with_new_fields"])
def test_marker_v2_closes_original_producer_and_store_identity(trial, mutation):
    value = marker(trial)
    if mutation == "release":
        value["producer"]["runner_code_ref"] = "git:mastermindx-market-intelligence/Mastermind@" + "b" * 40
    elif mutation == "runner":
        value["producer"]["runner_id"] = "other-runner"
    elif mutation == "surface":
        value["producer"]["execution_surface"] = "configured-label"
    elif mutation == "version":
        value["producer"]["execution_surface_version"] = inputs.producer_descriptor("a" * 40,
            DERIVATION_BASE, "b" * 64)["execution_surface_version"]
    elif mutation.startswith("root_"):
        value["publication"]["artifact_root"] = {"root_relative": "relative", "root_parent": "/tmp/../changed",
                                                   "root_alias": "/tmp//changed"}[mutation]
    elif mutation == "mode":
        value["publication"]["root_identity"]["mode"] = 0o755
    elif mutation == "inode":
        value["publication"]["root_identity"]["inode"] = 0
    elif mutation == "extra":
        value["publication"]["configured_fallback"] = True
    else:
        value["schema"] = inputs.LEGACY_MARKER_SCHEMA
    with pytest.raises(RuntimeRefusal):
        inputs.validate_marker(reseal(value), text=trial.text)


@pytest.mark.parametrize("field,value", [
    ("scenario_id", "scenario:evaluation_contract_integrity:missing"), ("scenario_version", 2),
    ("scenario_digest", "sha256:" + "d" * 64),
    ("configuration_digest", "sha256:" + "d" * 64),
    ("experiment_id", "experiment:8d3f9f9c-57b5-4aa5-bf13-c5b8598e3434"),
    ("experiment_digest", "sha256:" + "e" * 64), ("arm_id", "arm_a"),
    ("pair_key", "pair:unexpected"), ("replicate_index", 1),
])
def test_selector_and_standalone_comparison_refusals(trial, field, value):
    trial.specification[field] = value
    with pytest.raises(RuntimeRefusal):
        select(trial)


@pytest.mark.parametrize("field", ["scenario_id", "scenario_version", "configuration_id"])
def test_resolver_cannot_substitute_a_different_selected_identity(trial, field):
    method = "resolve_configuration" if field == "configuration_id" else "resolve_scenario"
    original = getattr(trial.owner.store, method)
    resolved = original(trial.configuration["configuration_id"]) if field == "configuration_id" else trial.scenario
    setattr(trial.owner.store, method, lambda *_: resolved)  # Broken resolver edge, immutable document unchanged.
    trial.specification[field] = 2 if field == "scenario_version" else trial.specification[field] + "different"
    with pytest.raises(RuntimeRefusal):
        select(trial)


def test_exact_experiment_arm_pair_and_replicate_bindings(trial):
    other = copy.deepcopy(trial.configuration)
    fields = {k: v for k, v in other.items() if k not in {"schema", "configuration_digest"}}
    from tests.agent_eval_factories import fresh_configuration_id
    fields["configuration_id"] = fresh_configuration_id()
    other = contracts.build_configuration(fields)
    trial.owner.store.create(other)
    experiment = build_two_arm_experiment(trial.scenario, trial.configuration, other)
    trial.owner.store.create(experiment)
    trial.specification.update(experiment_id=experiment["experiment_id"], experiment_digest=experiment["experiment_digest"],
        arm_id="arm_a", pair_key=f"pair:{trial.scenario['scenario_id']}:v1:r1", replicate_index=1)
    assert marker(trial)["experiment"] == experiment
    for changes in ({"arm_id": "arm_b"}, {"replicate_index": 2}, {"pair_key": None},
                    {"pair_key": "pair:different"}, {"experiment_digest": "sha256:" + "0" * 64}):
        saved = copy.deepcopy(trial.specification)
        trial.specification.update(changes)
        with pytest.raises(RuntimeRefusal):
            select(trial)
        trial.specification = saved


@pytest.mark.parametrize("change", ["fresh", "resume", "bounded", "hidden", "deny", "visibility", "allowlist", "input_digest"])
def test_retained_marker_refuses_unqualified_data_or_freshness(trial, change):
    value = marker(trial)
    scenario = value["scenario"]
    context_ref = value["configuration"]["context"]["context_packet"]["artifact_ref"]
    if change == "fresh":
        scenario["execution_policy"]["fresh_process_required"] = True
    elif change == "resume":
        scenario["execution_policy"]["resume_allowed"] = False
    elif change == "bounded":
        scenario["privacy"]["retention_class"] = "BOUNDED"
    elif change in {"hidden", "deny"}:
        key = "solution_refs_hidden" if change == "hidden" else "denylist_refs"
        scenario["source_policy"][key] = sorted(set(scenario["source_policy"][key]) | {context_ref})
    elif change == "visibility":
        scenario["privacy"]["model_visible_artifact_refs"].remove(context_ref)
    elif change == "allowlist":
        scenario["source_policy"]["allowlist_artifacts"] = [row for row in scenario["source_policy"]["allowlist_artifacts"]
                                                            if row["artifact_ref"] != context_ref]
    elif change == "input_digest":
        value["input"]["text_sha256"] = "f" * 64
    if change != "input_digest":
        value["scenario"] = add_document_digest(scenario, "scenario_digest")
    reseal(value)
    with pytest.raises(RuntimeRefusal):
        inputs.validate_marker(value)  # No raw input is needed for the retained digest join.


@pytest.mark.parametrize("context", ["", " ", "facts\n\t "])
def test_empty_and_trailing_whitespace_context_survive_native_stripping(tmp_path, context):
    t = source_owner(tmp_path / "store", str(tmp_path / "profile"), context=context)
    value = marker(t)
    rendered = inputs.render_inputs(value["candidate_files"], context)
    assert ("system\n\n" + rendered).strip().endswith(rendered)
    assert inputs.validate_marker(value)["rendered_sha256"] == hashlib.sha256(rendered.encode()).hexdigest()


@pytest.mark.parametrize("value", [None, [], "marker", 7, {"schema": inputs.MARKER_SCHEMA}])
def test_untyped_marker_is_a_closed_refusal(value):
    with pytest.raises(RuntimeRefusal):
        inputs.validate_marker(value)


def test_private_marker_is_not_a_public_payload_or_reusable_request_id(trial):
    value = marker(trial)
    with pytest.raises(RuntimeRefusal, match="PRIVATE_PRODUCER"):
        inputs.private_inputs_payload(None, None, None, value)
    with pytest.raises(RuntimeRefusal):
        inputs._PrivateSelection(trial.owner, value, object())
    with pytest.raises(RuntimeRefusal, match="REQUEST_ID"):
        trial.owner.select(trial.specification, principal=trial.principal, session_id=trial.session,
            submission_id="another-request", text=trial.text)
    trial.owner.store.resolve_run = lambda _: {"already": "retained"}
    with pytest.raises(RuntimeRefusal, match="ALREADY_RETAINED"):
        select(trial)


def test_qualification_patch_preserves_existing_privacy_and_extends_original_admission_owners():
    from integrations.hermes_qualification.native_eval_inputs import qualify
    from integrations.hermes_qualification.workspace_oauth_privacy import qualify as privacy
    root = Path(__file__).resolve().parents[2] / "hermes_qualification/workspace_oauth_privacy/fixtures"
    source = {path: (root / path.replace("/", "__")).with_suffix(".py.source").read_bytes()
              for path in privacy.PATHS}
    source["gateway/session_authority.py"] = (Path(__file__).parent / "fixtures/request_observation/gateway__session_authority.py.source").read_bytes()
    source["hermes_state_mutation_retirement.py"] = (Path(__file__).parent / "fixtures/native_eval_inputs/hermes_state_mutation_retirement.py.source").read_bytes()
    for name in ("hermes_state_common.py", "hermes_state_runtime.py", "hermes_state_schema.py"):
        source[name] = (Path(__file__).parent / "fixtures/native_eval_inputs" / (name + ".source")).read_bytes()
    before = dict(source)
    patched = qualify.prepare_sources(source)
    assert source == before
    old = privacy.prepare_sources({path: source[path] for path in privacy.PATHS})
    assert all(patched[path] == old[path] for path in privacy.PATHS)
    authority = patched["gateway/session_authority.py"].decode()
    assert "_mmx_eval=None" in authority and "private_inputs_payload" in authority
    assert patched["gateway/session_authority.py"] != source["gateway/session_authority.py"]
    assert patched["hermes_state_schema.py"] == source["hermes_state_schema.py"]
    assert b"    eval_publication_json TEXT," in patched["hermes_state_common.py"]
    assert b"result.pop('eval_publication_json', None)" in patched["hermes_state_runtime.py"]
    with pytest.raises(qualify.QualificationError, match="PREIMAGE"):
        qualify.prepare_sources(patched)


def pinned_functions(path, names, values):
    root = Path(__file__).parent / "fixtures/native_eval_inputs"
    manifest = json.loads((root / "provenance.json").read_bytes())
    spec = manifest["files"][path]
    raw = (root / spec["fixture"]).read_bytes()
    assert len(raw) == spec["bytes"] and hashlib.sha256(raw).hexdigest() == spec["sha256"]
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == spec["git_blob"]
    nodes = [node for node in ast.parse(raw).body if names is None or getattr(node, "name", None) in names]
    if names is not None:
        assert {node.name for node in nodes} == set(names)
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    code = raw if names is None else ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    namespace = dict(values)
    exec(compile(code, path, "exec"), namespace)
    return namespace


def provider_route():
    spec = native_provider("mmmeta", "zai.glm-5.3")
    # Config/credential retrieval is the declared edge; the named-provider rung,
    # custom runtime builder and original runtime identity projection execute.
    entry = {"name": spec.hermes_name, "provider_key": spec.hermes_name,
             "base_url": spec.base_url, "api_mode": "chat_completions"}
    rp = SimpleNamespace(_get_named_custom_provider=lambda name: entry if name == spec.hermes_name else None,
        _resolves_to_custom=lambda _: False, has_usable_secret=bool, _get_model_config=lambda: {},
        _detect_api_mode_for_url=lambda _: "chat_completions")
    core = pinned_functions("hermes_cli/runtime_provider.py", {"_runtime", "_tag", "_named_custom_rung"}, {
        "is_actual_route": lambda *_: False, "_get_model_config": rp._get_model_config,
        "_maybe_apply_codex_app_server_runtime": lambda **kw: kw["api_mode"]})
    rp._runtime = core["_runtime"]
    custom = pinned_functions("hermes_cli/runtime_provider_custom.py", {"_custom_runtime", "_resolve_named_custom_runtime"}, {
        "_rp": lambda: rp, "_LLAMACPP_ALIASES": set(),
        "_apply_custom_provider_extras": lambda *_: None,
        "_opencode_family_for_custom": lambda *_: None})
    core["_resolve_named_custom_runtime"] = custom["_resolve_named_custom_runtime"]
    runtime = core["_named_custom_rung"](spec.hermes_name, "synthetic-key", None, spec.served_model)
    assert runtime["provider"] == "custom" and runtime["requested_provider"] == "zai-glm"
    return {"model": spec.served_model, "runtime": runtime}


def native_trial(lifecycle, tmp_path, *, context="Known fixture facts.\n", files=None):
    l, n = lifecycle, lifecycle.native
    receipt = json.loads(l.sdk.content[0].text)["data"]["receipt"]
    sources = inputs.record_source_pairs(receipt["selected_record_sources"], bundle_sha256=receipt["bundle_sha256"])
    t = source_owner(tmp_path / "eval-store", str(n.home), context=context, files=files, record_sources=sources)
    t.principal = l.factory.publication.session.principal_id
    t.owner.binding = n.binding
    n.binding.memory_factory = l.factory
    n.binding.evaluation_owner = t.owner
    del t.owner.require_enrollment  # Actual current native factory/enrollment joins.
    return t


def execute_trial(lifecycle, t, *, admission="eval-admission", generation=3, before_request=None,
                  after_request=None, history=None, before_builder=None):
    l, n = lifecycle, lifecycle.native
    selected = marker(t)
    ref, row, _ = n.claim(admission=admission, generation=generation)
    row.update(principal_id=t.principal, request_id=selected["input"]["submission_id"],
        payload={"text": t.text, "finite": True, inputs.MARKER_KEY: selected})
    n.authority.adopted.pop(ref.session_id, None)
    route = provider_route()
    out = {"marker": selected, "row": row}
    def execute():
        turn = l.turn_for(ref, row)
        original = turn._ctx.AIAgent
        def create(**kwargs):
            agent = original(**kwargs)
            agent._disable_streaming = True  # Native config selection is checked separately.
            agent._current_turn_id = "turn-A"  # Same logical turn used by the original worker fixture.
            return agent
        turn._ctx.AIAgent = create
        agent, reused = turn._resolve_turn_agent(route, "api", "original ephemeral", 3, None, {})
        turn._wire_turn_agent_callbacks(agent, route, None, None, None, False)
        out.update(agent=agent, reused=reused, scope=observation._current.get())
        if before_builder:
            before_builder(out)
        context = l.turn_context._memory_turn_start_and_prefetch(agent, t.text)
        history = copy.deepcopy(history_rows)
        messages, system = l.turn_context.build_api_messages(agent, [*history, {"role": "user", "content": t.text}],
            current_turn_user_idx=len(history), ext_prefetch_cache=context, plugin_user_context="", moa_config=None,
            active_system_prompt="original system")
        kwargs = {"model": agent.model, "messages": messages, "seed": agent.request_overrides["seed"],
                  "reasoning_effort": agent.reasoning_config["effort"], "tools": [], "stream": False}
        out.update(messages=messages, system=system, kwargs=kwargs)
        if before_request:
            before_request(out)
        n.requests._fire_pre_api_request_hook(agent, kwargs, messages, None, turn_id=agent._current_turn_id,
            api_request_id="eval-request", api_call_count=1, retry_count=0, messages=messages,
            original_user_message=t.text, approx_tokens=10, total_chars=100,
            api_start_time=0, effective_task_id="fixture-task")
        if after_request:
            after_request(out)
        return "component result"
    async def handle(event):
        return await n.runner._run_in_executor_with_context(execute)
    history_rows = history or []
    n.runner._handle_message = handle
    out["response"] = asyncio.run(n.finite.execute_finite_admission(n.authority, ref, row))
    out["saved"] = n.authority.pending_results[admission]
    return out


@pytest.mark.parametrize("context", ["", "facts\n "])
def test_original_native_lifecycle_applies_candidate_seed_zero_and_manual_effort(lifecycle, tmp_path, context):
    t = native_trial(lifecycle, tmp_path, context=context)
    out = execute_trial(lifecycle, t)
    assert out["response"] == "component result"
    assert out["agent"].reasoning_config == {"enabled": True, "effort": "low"}
    assert out["kwargs"]["seed"] == 0
    assert out["system"].endswith(inputs.render_inputs(t.specification["candidate_files"], context))
    value = out["saved"][inputs.RESULT_KEY]
    assert len(value["deliveries"]) == len(value["assemblies"]) == 1
    assert value["errors"] == [] and value["complete_evaluation"] is False
    receipt = {"admission_id": "eval-admission", "execution_generation": 3, "authority_epoch": 2}
    sibling = out["saved"][observation.RESULT_KEY]
    assert inputs.validate_observation(value, marker=out["marker"], receipt=receipt, request_observation=sibling) == value
    # Reading an original contribution does not depend on today's live owner.
    lifecycle.native.authority.instance_id = "replacement-instance"
    assert inputs.validate_observation(value, marker=out["marker"], receipt=receipt, request_observation=sibling) == value
    for changed in ({"instance_id": "another-instance"},
                    {"assemblies": [{**value["assemblies"][0], "api_request_id": "another-request"}]}):
        with pytest.raises(RuntimeRefusal):
            inputs.validate_observation({**value, **changed}, marker=out["marker"], receipt=receipt, request_observation=sibling)


@pytest.mark.parametrize("change", ["seed", "effort", "candidate", "stream", "extra_seed", "extra_model", "generation", "attachment"])
def test_post_prompt_drift_refuses_required_execution_outside_observer_catch(lifecycle, tmp_path, change):
    t = native_trial(lifecycle, tmp_path)
    def mutate(out):
        if change == "seed":
            out["kwargs"]["seed"] = 1
        elif change == "effort":
            out["kwargs"]["reasoning_effort"] = "high"
        elif change == "candidate":
            out["kwargs"]["messages"][0]["content"] = "changed"
        elif change == "stream":
            out["kwargs"]["stream"] = True
        elif change.startswith("extra_"):
            out["kwargs"]["extra_body"] = {change.removeprefix("extra_"): 9}
        elif change == "generation":
            lifecycle.native.rows["session-1"]["generation"] += 1  # Durable row changes; live stamp is still old.
        elif change == "attachment":
            out["agent"]._memory_manager = object()
    with pytest.raises(RuntimeRefusal):
        execute_trial(lifecycle, t, before_request=mutate)


@pytest.mark.parametrize("failure", ["no-owner", "no-scope", "unknown-version", "retained-run"])
def test_marked_admission_never_falls_back_to_ordinary_execution(lifecycle, tmp_path, failure):
    l, n = lifecycle, lifecycle.native
    t = native_trial(l, tmp_path)
    value = marker(t)
    ref, row, _ = n.claim()
    row.update(principal_id=t.principal, request_id=value["input"]["submission_id"],
        payload={"text": t.text, "finite": True, inputs.MARKER_KEY: value})
    if failure == "no-owner":
        n.binding.evaluation_owner = None
    elif failure == "no-scope":
        n.authority.retiring = True
    elif failure == "unknown-version":
        row["payload"]["mastermind_eval_inputs_v99"] = row["payload"].pop(inputs.MARKER_KEY)
    elif failure == "retained-run":
        t.owner.store.resolve_run = lambda _: {"already": "published"}
    called = []
    async def handle(event):
        called.append(event)
    n.runner._handle_message = handle
    with pytest.raises(RuntimeRefusal):
        asyncio.run(n.finite.execute_finite_admission(n.authority, ref, row))
    assert called == []


def selected_recipe(role="mmmeta"):
    from integrations.hermes_harness.tests.test_native_current_agentos_context import current_document
    from integrations.hermes_harness.tests.test_native_executive_consumer import _installation
    from integrations.hermes_runtime.constants import conversation_contract
    from ops.executive_os.native_gateway_sources import EVAL_INPUTS_DERIVATION_PATCH, DERIVATION_BASE
    document = current_document()
    document["session"].update(role=role, principal_id="uid:993" if role == "mmmeta" else "uid:994")
    installation = _installation(consumer=document, role=role)
    native = next(row["native_gateway"] for row in installation["roles"] if row["role"] == role)
    native["session_enrollment"]["schema"] = conversation_contract(role).enrollment_schema
    native["vendor_derivation"] = dict(kind="native_eval_inputs", base_sha=DERIVATION_BASE,
        patch_sha256=EVAL_INPUTS_DERIVATION_PATCH, source_root="/opt/hermes/pristine")
    native["evaluation_inputs"] = dict(schema=inputs.RECIPE_SCHEMA, artifact_root="/var/lib/mastermind/eval")
    return installation, native, document


@pytest.mark.parametrize("change", ["removed", "replaced", "historical-copy", "snapshot-copy", "expired",
    "input", "system", "instructions", "extra-input", "extra-system", "extra-instructions", "new-builder-failed"])
def test_source_delivery_requires_original_current_user_and_snapshot(lifecycle, tmp_path, monkeypatch, change):
    from dataclasses import replace
    t = native_trial(lifecycle, tmp_path)
    seen = {}
    def mutate(out):
        seen["scope"] = out["scope"]
        evaluation = out["scope"].evaluation
        proof = evaluation.delivery_proof
        assert proof is not None
        index = proof["anchor"]["row_index"]
        if change in {"removed", "replaced", "historical-copy"}:
            original = copy.deepcopy(out["kwargs"]["messages"][index]["content"])
            out["kwargs"]["messages"][index]["content"] = t.text if change != "replaced" else "another memory body"
            if change == "historical-copy":
                out["kwargs"]["messages"][index - 1]["content"] = original
        elif change == "snapshot-copy":
            proof["provider"]._snapshot = replace(proof["snapshot"])
        elif change == "expired":
            monkeypatch.setattr(proof["provider"], "_clock", lambda: proof["snapshot"].expires_at + 1)
        elif change == "new-builder-failed":
            # A fresh construction fails before note_prompt can run. The old
            # exact request must not borrow its surviving prior anchor.
            with pytest.raises(TypeError):
                lifecycle.turn_context.build_api_messages(out["agent"], [])
        elif change.startswith("extra-"):
            out["kwargs"]["extra_body"] = {change.removeprefix("extra-"): None}
        else:
            out["kwargs"][change] = None
    with pytest.raises(RuntimeRefusal):
        execute_trial(lifecycle, t, before_request=mutate,
            history=[{"role": "user", "content": "An earlier user turn"}])
    # Native ingress creates a pending result only after a returned execution.
    # A required-input refusal must not invent a terminal result or assembly.
    assert "eval-admission" not in lifecycle.native.authority.pending_results
    assert seen["scope"].closed and seen["scope"].events == []
    assert seen["scope"].evaluation.assemblies == []


def test_legitimate_message_metadata_changes_preserve_anchor_and_separate_digests(lifecycle, tmp_path):
    t = native_trial(lifecycle, tmp_path)
    def sanitize(out):
        # Same native current-user text/position, different harmless metadata.
        row = out["kwargs"]["messages"][-1]
        row["content"] = [{"type": "text", "text": row["content"], "cache_control": {"type": "ephemeral"}}]
    out = execute_trial(lifecycle, t, before_request=sanitize)
    value = out["saved"][inputs.RESULT_KEY]
    assert value["schema"] == inputs.RESULT_SCHEMA and len(value["source_snapshots"]) == 1
    delivery, assembly = value["deliveries"][0], value["assemblies"][0]
    assert delivery["messages_sha256"] != assembly["messages_sha256"]
    assert assembly["messages_sha256"] == assembly["content_sha256"]
    assert assembly["delivery_sha256"] == hashlib.sha256(canonical_json_bytes(delivery)).hexdigest()
    original = inputs.validate_observation(value, marker=out["marker"],
        receipt={"admission_id": "eval-admission", "execution_generation": 3, "authority_epoch": 2},
        request_observation=out["saved"][observation.RESULT_KEY])
    sources = inputs.observed_record_sources(original)
    assert sources and all("git:mastermindx-market-intelligence/macro@" in row["artifact_ref"] for row in sources)
    assert all("#agentos/" in row["artifact_ref"] for row in sources)
    assert t.text.encode() not in canonical_json_bytes(value)


def test_actual_record_capture_overflow_refuses_before_request_assembly(lifecycle, tmp_path, monkeypatch):
    from control_plane import agentos_context_bundle as contract
    t = native_trial(lifecycle, tmp_path)
    # The next actual installed capture overflows while preserving its full
    # original bundle. No injected inventory replaces the native provider.
    monkeypatch.setattr(contract, "MAX_RECORD_SOURCE_BYTES", 1)
    seen = {}
    with pytest.raises(RuntimeRefusal, match="SOURCE_INVENTORY_INCOMPLETE"):
        execute_trial(lifecycle, t, before_builder=lambda out: seen.update(scope=out["scope"]))
    assert "eval-admission" not in lifecycle.native.authority.pending_results
    assert seen["scope"].closed and seen["scope"].events == []
    value = seen["scope"].evaluation.document()
    assert value["source_snapshots"][0]["retention"] == "OVERFLOW"
    assert value["source_snapshots"][0]["omitted_items"] > 0
    assert value["assemblies"] == []


def test_old_current_receipt_cannot_invent_new_source_delivery(lifecycle, tmp_path, monkeypatch):
    from control_plane import agentos_context_bundle as contract
    from mcp import types
    t = native_trial(lifecycle, tmp_path)
    original = lifecycle.session.call_tool
    async def legacy(*args, **kwargs):
        response = await original(*args, **kwargs)
        body = json.loads(response.content[0].text)
        receipt = body["data"]["receipt"]
        receipt["schema"] = contract.CURRENT_RECEIPT_SCHEMA
        receipt.pop("selected_record_sources")
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(body))], isError=False)
    monkeypatch.setattr(lifecycle.session, "call_tool", legacy)
    seen = {}
    with pytest.raises(RuntimeRefusal, match="DELIVERY_UNAVAILABLE"):
        execute_trial(lifecycle, t, before_builder=lambda out: seen.update(scope=out["scope"]))
    assert "eval-admission" not in lifecycle.native.authority.pending_results
    assert seen["scope"].closed and seen["scope"].events == []
    value = seen["scope"].evaluation.document()
    assert value["deliveries"] == value["assemblies"] == value["source_snapshots"] == []


def test_observation_budget_loss_does_not_invent_sources_or_an_execution_failure(lifecycle, tmp_path):
    t = native_trial(lifecycle, tmp_path)
    def fill(out):
        out["scope"].metadata_bytes = observation.MAX_METADATA_BYTES - 2
    def inspect(out):
        proof = out["scope"].evaluation.require_request(out["agent"], out["kwargs"])
        assert proof["sequence"] is None and proof["inventory"]["retention"] == "COMPLETE"
    out = execute_trial(lifecycle, t, before_builder=fill, after_request=inspect)
    assert out["response"] == "component result"
    value = out["saved"][inputs.RESULT_KEY]
    assert "metadata_overflow" in value["errors"]
    assert value["deliveries"] == value["assemblies"] == value["source_snapshots"] == []
    assert inputs.observed_record_sources(value) == []


def test_unscoped_late_prefetch_cannot_erase_current_admission_anchor(lifecycle, tmp_path):
    t = native_trial(lifecycle, tmp_path)
    def late(out):
        proof = out["scope"].evaluation.delivery_proof
        token = observation._current.set(None)
        try:
            assert proof["provider"].prefetch("late other request", session_id=out["agent"].session_id) == ""
        finally:
            observation._current.reset(token)
        assert proof["claim"].prompt_anchor is proof["anchor"]
        assert proof["claim"].returned == proof["delivery"]
    out = execute_trial(lifecycle, t, before_request=late)
    assert len(out["saved"][inputs.RESULT_KEY]["assemblies"]) == 1


@pytest.mark.parametrize("change", ["delivery-sequence", "delivery-digest", "retry", "request-duplicate",
                                     "inventory-data", "inventory-use", "anchor", "unknown-field"])
def test_historical_source_join_cannot_substitute_original_evidence(lifecycle, tmp_path, change):
    from control_plane import agentos_context_bundle as contract
    t = native_trial(lifecycle, tmp_path)
    out = execute_trial(lifecycle, t)
    value = copy.deepcopy(out["saved"][inputs.RESULT_KEY])
    sibling = copy.deepcopy(out["saved"][observation.RESULT_KEY])
    if change == "delivery-sequence":
        other = copy.deepcopy(value["deliveries"][0])
        other["sequence"] = 2
        other["current_user"]["text_sha256"] = "d" * 64
        value["deliveries"].append(other)
        value["assemblies"][0]["delivery_sequence"] = 2
    elif change == "delivery-digest":
        value["assemblies"][0]["delivery_sha256"] = "d" * 64
    elif change == "retry":
        value["assemblies"][0]["retry_count"] += 1
    elif change == "request-duplicate":
        sibling["observations"].append(copy.deepcopy(sibling["observations"][0]))
    elif change.startswith("inventory-"):
        inventory = value["source_snapshots"][0]
        if change == "inventory-data":
            inventory["data_commit"] = "d" * 40
        else:
            inventory["entries"][0]["uses"].append(inventory["entries"][0]["uses"][0])
        inventory["inventory_sha256"] = contract.canonical_digest(
            {key: item for key, item in inventory.items() if key != "inventory_sha256"})
        value["deliveries"][0]["source_inventory_sha256"] = inventory["inventory_sha256"]
    elif change == "anchor":
        value["deliveries"][0]["current_user"]["row_index"] = True
    else:
        value["assemblies"][0]["complete_sources"] = True
    with pytest.raises(RuntimeRefusal):
        inputs.validate_observation(value, marker=out["marker"],
            receipt={"admission_id": "eval-admission", "execution_generation": 3, "authority_epoch": 2},
            request_observation=sibling)


def test_historical_v1_observation_stays_exact_and_source_unobserved(lifecycle, tmp_path):
    t = native_trial(lifecycle, tmp_path)
    out = execute_trial(lifecycle, t)
    old = copy.deepcopy(out["saved"][inputs.RESULT_KEY])
    # Historical structural contract: explicitly remove every new v2 field;
    # no newer inventory is inferred into old evidence at readback.
    old["schema"] = inputs.LEGACY_RESULT_SCHEMA
    old.pop("source_snapshots")
    for row in old["deliveries"]:
        for key in ("sequence", "source_inventory_sha256", "current_user"):
            row.pop(key)
    for row in old["assemblies"]:
        for key in ("agent_session_id", "api_call_count", "retry_count", "messages_sha256", "delivery_sequence", "delivery_sha256"):
            row.pop(key)
    receipt = {"admission_id": "eval-admission", "execution_generation": 3, "authority_epoch": 2}
    assert inputs.validate_observation(old, marker=out["marker"], receipt=receipt,
        request_observation=out["saved"][observation.RESULT_KEY]) == old
    assert inputs.observed_record_sources(old) == []
    old["source_snapshots"] = []
    with pytest.raises(RuntimeRefusal):
        inputs.validate_observation(old, marker=out["marker"], receipt=receipt,
            request_observation=out["saved"][observation.RESULT_KEY])


@pytest.mark.parametrize("change,reason", [("allowed", None), ("alias", "UNAUTHORIZED_SOURCE"),
    ("digest", "SOURCE_DIGEST_MISMATCH"), ("hidden", "HIDDEN_SOLUTION_SOURCE"),
    ("denied", "UNAUTHORIZED_SOURCE"), ("private", "SOURCE_NOT_MODEL_VISIBLE")])
def test_native_policy_keeps_each_equal_byte_record_reference(trial, change, reason):
    from control_plane import agentos_context_bundle as contract
    raw = b"Identical PUBLIC_SAFE fixture content\n"
    entries = [{"path": "agentos/workstreams/WS-" + name + ".md", "mode": "100644",
        "git_blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
        "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "uses": [[0, index]]}
        for index, name in enumerate(("ONE", "TWO"))]
    inventory = contract.record_source_inventory(bundle_sha256="b" * 64, data_commit="c" * 40,
        selected_items=2, entries=entries)
    pairs = inputs.record_source_pairs(inventory, bundle_sha256="b" * 64)
    assert len(pairs) == 2 and pairs[0]["digest"] == pairs[1]["digest"]
    assert pairs[0]["artifact_ref"] != pairs[1]["artifact_ref"]
    value = marker(trial)
    policy = value["scenario"]["source_policy"]
    policy["allowlist_artifacts"] += copy.deepcopy(pairs)
    visible = value["scenario"]["privacy"]["model_visible_artifact_refs"]
    visible.extend(pair["artifact_ref"] for pair in pairs)
    if change == "alias":
        policy["allowlist_artifacts"].pop()
    elif change == "digest":
        policy["allowlist_artifacts"][-1]["digest"] = "sha256:" + "d" * 64
    elif change == "private":
        visible.pop()
    elif change in {"hidden", "denied"}:
        policy["solution_refs_hidden" if change == "hidden" else "denylist_refs"] = [pairs[1]["artifact_ref"]]
    if reason is None:
        assert inputs._require_record_policy(value, inventory, bundle_sha256="b" * 64) == pairs
    else:
        with pytest.raises(RuntimeRefusal, match=reason):
            inputs._require_record_policy(value, inventory, bundle_sha256="b" * 64)


def test_selected_recipe_and_config_refuse_unsupported_role_and_streaming_downgrade(tmp_path):
    from dataclasses import replace
    from integrations.hermes_harness.stack import compose_profile
    from integrations.hermes_harness.native_byok import expected_native_config, render_qualified_native_byok
    from integrations.hermes_harness.native_executive_consumer import publication_from_document
    from integrations.hermes_steward.config_guard import _load_unique_yaml
    from integrations.hermes_runtime.supervisor import expected_disabled_mcp
    from ops.executive_os import release_manifest as release
    installation, recipe, document = selected_recipe()
    assert release.validate_hermes_runtime_installation(installation)["roles"][0]["native_gateway"] == recipe
    profile = replace(compose_profile("mmmeta", state_dir=tmp_path / "state", secrets_file=tmp_path / "uncreated.env"),
                      tool_allowlist=frozenset({"clarify"}), hermes_home=tmp_path / "native-home")
    legacy = render_qualified_native_byok(profile, publication_from_document(document))
    assert expected_native_config(profile, document) == legacy
    selected = expected_native_config(profile, document, evaluation_inputs=recipe["evaluation_inputs"])
    old, new = _load_unique_yaml(legacy.encode()), _load_unique_yaml(selected.encode())
    assert new["model"].pop("streaming") is False and new == old
    for selected_role in ("mmsecretary",):
        wrong, _, _ = selected_recipe(selected_role)
        with pytest.raises(release.ReleaseManifestError):
            release.validate_hermes_runtime_installation(wrong, _defer_consumer=True)
    # The existing config qualifier cannot accept its early legacy alternative
    # when the recipe requires explicit nonstreaming.
    config = profile.hermes_home / "profiles" / profile.role / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(selected)
    config.chmod(0o600)
    assert expected_disabled_mcp(profile, document, evaluation_inputs=recipe["evaluation_inputs"]) is not None
    config.write_text(legacy)
    with pytest.raises(RuntimeRefusal, match="CONFIG_DRIFT"):
        expected_disabled_mcp(profile, document, evaluation_inputs=recipe["evaluation_inputs"])


def qualified_sources():
    from integrations.hermes_qualification.native_eval_inputs import qualify
    root = Path(__file__).resolve().parents[2] / "hermes_qualification/workspace_oauth_privacy/fixtures"
    fixtures = Path(__file__).parent / "fixtures"
    values = {}
    for path in qualify.PATHS:
        source_root = (fixtures / "request_observation" if path == "gateway/session_authority.py" else
            fixtures / "native_eval_inputs" if path.startswith("hermes_state_") else root)
        values[path] = (source_root / (path.replace("/", "__") + ".source")).read_bytes()
    return qualify.prepare_sources(values)


def compile_selected(raw, names, namespace, path):
    nodes = [node for node in ast.parse(raw).body if getattr(node, "name", None) in names]
    assert {node.name for node in nodes} == set(names)
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[])), path, "exec"), namespace)
    return namespace


def test_original_declarative_schema_upgrades_nullable_publication_and_hides_it(tmp_path, monkeypatch):
    from integrations.hermes_runtime.tests.test_native_request_observation import module
    patched = qualified_sources()
    root = Path(__file__).parent / "fixtures/native_eval_inputs"

    def schema_sql(raw):
        tree = ast.parse(raw)
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "SCHEMA_SQL" for target in node.targets))
        # Only the incumbent unrelated cron-principal constant is a fixture
        # edge. Actual complete SQL and column-reconciliation bodies execute.
        values = {"CRON_PRINCIPAL_ID": "fixture:cron"}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[assignment], type_ignores=[])),
                     "hermes_state_common.py", "exec"), values)
        return values["SCHEMA_SQL"]

    old_sql = schema_sql((root / "hermes_state_common.py.source").read_bytes())
    new_sql = schema_sql(patched["hermes_state_common.py"])
    module(monkeypatch, "hermes_constants", get_hermes_home=lambda: tmp_path / "native-home")
    values = dict(contextlib=contextlib, hashlib=hashlib, json=json, os=os, sqlite3=sqlite3,
                  tempfile=tempfile, logger=logging.getLogger(__name__), SCHEMA_SQL=new_sql)
    compile_selected(patched["hermes_state_schema.py"], {"_q"}, values, "hermes_state_schema.py")
    cls = next(node for node in ast.parse(patched["hermes_state_schema.py"]).body
               if isinstance(node, ast.ClassDef) and node.name == "SessionSchemaMixin")
    cls.body = [node for node in cls.body if getattr(node, "name", None) in {"_parse_schema_columns", "_reconcile_columns"}]
    assert len(cls.body) == 2
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                 "hermes_state_schema.py", "exec"), values)
    owner = values["SessionSchemaMixin"]()
    # The old cached DDL must not hide the new column.
    assert "eval_publication_json" not in owner._parse_schema_columns(old_sql)["session_admissions"]
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript(old_sql)
        conn.execute("INSERT INTO sessions(id,source,started_at) VALUES('old-session','fixture',0)")
        conn.execute("""INSERT INTO session_admissions(admission_id,request_id,principal_id,target_session_id,
            lineage_json,payload_json,payload_digest,intent,status,outcome,owner_epoch)
            VALUES('old-admission','old-request','fixture','old-session','[]','{}','original-digest',
                   'queue','terminal','cancelled',2)""")
        original = dict(conn.execute("SELECT * FROM session_admissions").fetchone())
        trace = []
        conn.set_trace_callback(trace.append)
        owner._reconcile_columns(conn.cursor())
        owner._reconcile_columns(conn.cursor())
        after = dict(conn.execute("SELECT * FROM session_admissions").fetchone())
        assert after == {**original, "eval_publication_json": None}
        additions = [sql for sql in trace if sql.startswith('ALTER TABLE "session_admissions"')]
        assert len(additions) == 1 and "eval_publication_json" in additions[0]
        public = compile_selected(patched["hermes_state_runtime.py"], {"_row"}, {"json": json},
                                  "hermes_state_runtime.py")["_row"]
        after["eval_publication_json"] = '{"fixture":"private-publication"}'
        assert "eval_publication_json" not in public(after)
        assert "eval_publication_json" not in public({**after, "retired_at": 1})
    cache = json.loads((tmp_path / "native-home/cache/schema_columns.json").read_text())
    assert cache["schema_hash"] == hashlib.sha256(new_sql.encode()).hexdigest()
    assert cache["tables"]["session_admissions"]["eval_publication_json"] == "TEXT"


@pytest.fixture
def admission_db(monkeypatch):
    from integrations.hermes_runtime.tests.test_native_request_observation import module
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE runtime_epoch(singleton INTEGER PRIMARY KEY, epoch INTEGER, instance_id TEXT);
        INSERT INTO runtime_epoch VALUES(1,2,'instance');
        CREATE TABLE sessions(id TEXT PRIMARY KEY);
        INSERT INTO sessions VALUES('session-a'),('session-b');
        CREATE TABLE state_meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE worker_executions(execution_id TEXT PRIMARY KEY, session_id TEXT, status TEXT);
        CREATE TABLE session_admissions(
            seq INTEGER PRIMARY KEY AUTOINCREMENT, admission_id TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL, principal_id TEXT NOT NULL, target_session_id TEXT NOT NULL,
            lineage_json TEXT NOT NULL, payload_json TEXT NOT NULL, payload_digest TEXT NOT NULL,
            intent TEXT NOT NULL, status TEXT NOT NULL, outcome TEXT, owner_epoch INTEGER, generation INTEGER,
            eval_publication_json TEXT,
            UNIQUE(principal_id,target_session_id,request_id));
    """)
    class DB:
        def _read_ctx(self):
            return contextlib.nullcontext(conn)
        def _execute_write(self, write):
            with conn:
                return write(conn)
    db = DB()
    # SessionDB locking/inode custody is an explicit edge; actual SQLite
    # transaction, native replay-before-guard and INSERT bodies execute.
    fingerprint = lambda **kw: digest_value(kw)
    patched = qualified_sources()
    core = compile_selected(patched["hermes_state_runtime.py"], {"RuntimeStoreError", "_one_line", "_text", "_json",
        "_epoch", "_session", "_admission", "_row", "admit_session_input"},
        {"json": json, "uuid": uuid, "ADMISSION_QUEUE_MAX": 32, "admission_fingerprint": fingerprint},
        "hermes_state_runtime.py")
    terminal_path = Path(__file__).parent / "fixtures/request_observation/hermes_state_terminal.py.source"
    prefixes = {"ADMISSION_PREFIX": "gateway.terminal_admission.v1.", "RESULT_PREFIX": "gateway.admission.result.v1.",
        "WORKER_PREFIX": "gateway.terminal_worker.v1.", "IDENTITY_PREFIX": "gateway.terminal_identity.v1."}
    terminal = module(monkeypatch, "hermes_state_terminal", _STORED="_stored", **prefixes)
    vars(terminal).update({"json": json, **{k: core[k] for k in (
        "RuntimeStoreError", "_epoch", "_json", "_row", "_text")}, "admission_fingerprint": fingerprint})
    compile_selected(terminal_path.read_bytes(), {"identity_key", "terminal_admission", "retry_terminal_admission",
                                                 "encode_result", "load_result"},
                     vars(terminal), str(terminal_path))
    media_calls = []
    module(monkeypatch, "hermes_state_media", retire_media=lambda conn, payload, request: media_calls.append((payload, request)))
    retirement = module(monkeypatch, "hermes_state_mutation_retirement", RETIRED_PREFIX="gateway.retired.v1.",
        ROUTE_FENCE_PREFIX="gateway.route_fence.v1.", RETRY_HORIZON_S=604800,
        _EXPIRED="json_valid(value) AND json_extract(value, '$.retired_at') < ?", json=json,
        time=SimpleNamespace(time=lambda: 2000000), _json=core["_json"], RuntimeStoreError=core["RuntimeStoreError"],
        _TRANSCRIPT_FIELDS=frozenset({"messages", "last_reasoning", "tools", "_turn_user_row"}))
    compile_selected(patched["hermes_state_mutation_retirement.py"], {"_reclaim_expired", "prune_retired_tombstones",
        "_compact_result", "retire_terminal_receipts"},
                     vars(retirement), "hermes_state_mutation_retirement.py")
    yield SimpleNamespace(conn=conn, db=db, core=core, terminal=terminal, retirement=retirement,
                          patched=patched, media_calls=media_calls)
    conn.close()


def test_original_transaction_replays_and_never_inserts_another_run_carrier(trial, admission_db, monkeypatch):
    a, value = admission_db, marker(trial)
    original = []
    monkeypatch.setattr(inputs, "private_inputs_payload", lambda *_: copy.deepcopy(value))  # Producer custody edge.
    guard = inputs.private_inputs_admission_guard(None, None, None, None, lambda conn: original.append(conn))
    payload = {"text": trial.text, "finite": True, inputs.MARKER_KEY: value}
    def admit(principal="one", session="session-a", body=payload):
        return a.core["admit_session_input"](a.db, epoch=2, principal_id=principal, session_id=session,
            request_id=value["input"]["submission_id"], payload=body, _authorize_write=guard)
    first = admit()
    assert admit()["admission_id"] == first["admission_id"] and original == [a.conn]
    with pytest.raises(a.core["RuntimeStoreError"], match="admission_conflict"):
        admit(body={**payload, "text": "changed"})
    for principal, session in (("one", "session-b"), ("two", "session-a"), ("two", "session-b")):
        with pytest.raises(RuntimeRefusal, match="ORIGINAL_CARRIER"):
            admit(principal, session)
    raw = dict(a.conn.execute("SELECT * FROM session_admissions").fetchone())
    raw.update(status="terminal", retired_at=1)
    prefix = a.terminal.ADMISSION_PREFIX
    with a.conn:
        a.conn.execute("DELETE FROM session_admissions")
        a.conn.execute("INSERT INTO state_meta VALUES(?,?)", (prefix + raw["admission_id"], json.dumps(raw)))
        # No retired session marker: simulate a re-created textual session ID.
    with pytest.raises(RuntimeRefusal, match="ORIGINAL_CARRIER"):
        admit()
    assert a.conn.execute("SELECT COUNT(*) FROM session_admissions").fetchone()[0] == 0


@pytest.mark.parametrize("marked", [True, False, "malformed-marker"])
def test_native_pruner_keeps_only_eval_identity_beyond_retry_horizon(trial, admission_db, marked):
    a, value = admission_db, marker(trial)
    payload = {"text": trial.text, "finite": True}
    if marked:
        payload[inputs.MARKER_KEY] = value if marked is True else "old-uninterpretable-marker"
    row = dict(admission_id="old-admission", request_id=value["input"]["submission_id"], principal_id="one",
        target_session_id="session-a", retired_at=1, payload_json=json.dumps(payload))
    keys = (a.terminal.ADMISSION_PREFIX + row["admission_id"],
        a.terminal.identity_key("one", "session-a", row["request_id"]),
        a.terminal.RESULT_PREFIX + row["admission_id"])
    for key, body in zip(keys, (row, "old-admission", {"result": "output with separate retention"})):
        a.conn.execute("INSERT INTO state_meta VALUES(?,?)", (key, json.dumps(body)))
    a.retirement.prune_retired_tombstones(a.conn)
    exists = [a.conn.execute("SELECT 1 FROM state_meta WHERE key=?", (key,)).fetchone() is not None for key in keys]
    assert exists == ([True, True, False] if marked else [False, False, False])


@pytest.mark.parametrize("kind", ["safe", "ordinary", "malformed", "unsafe"])
def test_real_terminal_retirement_preserves_safe_input_and_only_fences_uninterpretable_markers(
        trial, admission_db, monkeypatch, kind):
    a, value = admission_db, marker(trial)
    payload = {"text": trial.text, "finite": True}
    if kind != "ordinary":
        payload[inputs.MARKER_KEY] = value if kind != "malformed" else "unknown-historical-marker"
    if kind == "unsafe":
        payload["extra_user_history"] = "not an admitted evaluation input"
    row = a.core["admit_session_input"](a.db, epoch=2, principal_id="one", session_id="session-a",
        request_id=value["input"]["submission_id"], payload=payload)
    admission_id = row["admission_id"]
    persisted = dict(a.conn.execute("SELECT * FROM session_admissions WHERE admission_id=?", (admission_id,)).fetchone())
    a.conn.execute("UPDATE session_admissions SET status='terminal',outcome='completed' WHERE admission_id=?", (admission_id,))
    publication = json.dumps({"fixture": "original-frozen-publication"})
    a.conn.execute("UPDATE session_admissions SET eval_publication_json=? WHERE admission_id=?", (publication, admission_id))
    result_key = a.terminal.RESULT_PREFIX + admission_id
    original_result = {"result": {"final_response": "retained answer", "messages": [
        {"role": "user", "content": "expired transcript"}, {"role": "assistant", "content": "retained answer"}],
        "last_reasoning": "expired reasoning", "tools": ["expired tool transcript"]}, "usage": {"input_tokens": 3}}
    a.conn.execute("INSERT INTO state_meta VALUES(?,?)", (result_key, json.dumps(a.terminal.encode_result(original_result))))
    a.db._execute_write(lambda conn: a.retirement.retire_terminal_receipts(conn, ("session-a",)))
    assert a.media_calls == [(payload, row["request_id"])]
    assert a.conn.execute("SELECT COUNT(*) FROM session_admissions").fetchone()[0] == 0
    admission_key = a.terminal.ADMISSION_PREFIX + admission_id
    retired = json.loads(a.conn.execute("SELECT value FROM state_meta WHERE key=?", (admission_key,)).fetchone()[0])
    kept = json.loads(retired["payload_json"])
    assert kept == (payload if kind == "safe" else {} if kind == "ordinary" else {inputs.MARKER_KEY: None})
    assert retired["payload_digest"] == persisted["payload_digest"]
    assert retired["lineage_json"] == "[]"
    assert retired["eval_publication_json"] == publication
    assert "eval_publication_json" not in a.core["_row"](retired)
    compacted = a.terminal.load_result(a.conn.execute("SELECT value FROM state_meta WHERE key=?", (result_key,)).fetchone()[0])
    assert compacted["result"] == {"final_response": "retained answer", "messages": []}
    assert compacted["usage"] == original_result["usage"]
    # The original native serializer, retirement transition, and horizon
    # pruning all execute; no preconstructed tombstone can hide input loss.
    a.retirement.time.time = lambda: 3000000
    a.db._execute_write(lambda conn: a.retirement.prune_retired_tombstones(conn))
    identity_key = a.terminal.identity_key("one", "session-a", row["request_id"])
    remaining = [a.conn.execute("SELECT 1 FROM state_meta WHERE key=?", (key,)).fetchone() is not None
                 for key in (admission_key, identity_key, result_key)]
    assert remaining == ([False, False, False] if kind == "ordinary" else [True, True, False])
    if kind != "ordinary":
        assert json.loads(a.conn.execute("SELECT value FROM state_meta WHERE key=?", (admission_key,)).fetchone()[0])["eval_publication_json"] == publication
        monkeypatch.setattr(inputs, "private_inputs_payload", lambda *_: copy.deepcopy(value))
        guard = inputs.private_inputs_admission_guard(None, None, None, None, None)
        with pytest.raises(RuntimeRefusal, match="ORIGINAL_CARRIER"):
            a.core["admit_session_input"](a.db, epoch=2, principal_id="two", session_id="session-b",
                request_id=value["input"]["submission_id"], payload=payload, _authorize_write=guard)
        assert a.conn.execute("SELECT COUNT(*) FROM session_admissions").fetchone()[0] == 0


def test_private_donor_always_composes_the_original_transaction_guard(trial, admission_db, monkeypatch):
    from integrations.hermes_runtime.tests.test_native_request_observation import module
    a = admission_db
    tree = ast.parse(admission_db.patched["gateway/session_authority.py"])
    authority = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SessionAuthority")
    authority.body = [node for node in authority.body if getattr(node, "name", None) in {"submit", "_submit", "_admission_gate"}]
    namespace = {"__name__": "gateway.session_authority", "partial": partial,
        "RuntimeStoreError": a.core["RuntimeStoreError"], "admit_session_input": a.core["admit_session_input"]}
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, authority], type_ignores=[])),
                 "gateway/session_authority.py", "exec"), namespace)
    owner = namespace["SessionAuthority"]()
    owner.profile_id, owner.epoch, owner.db = trial.owner.profile_id, 2, a.db
    owner.authorize = lambda *_: None  # Original actor authentication is a declared edge.
    owner._require_admission_open = lambda **_: None
    owner._release_refused_capture = lambda *_: None
    owner._admitted = lambda ref, unused, row: row
    owner._schedule_admitted = lambda *_: None
    owner.sessions = {sid: SimpleNamespace(source=SimpleNamespace(user_id=trial.principal), mutation_lock=asyncio.Lock())
                      for sid in ("session-a", "session-b")}
    trial.owner.binding = SimpleNamespace(authority=owner)
    module(monkeypatch, "gateway", __path__=[])
    module(monkeypatch, "gateway.session_ingress_media", capture_lease=contextlib.nullcontext,
        admit_attachments=lambda *args, **kw: {})
    module(monkeypatch, "gateway.session_finite", admit_finite=lambda payload: {"finite": payload["finite"]})
    for name, function in (("surface", "admit_surface"), ("display", "admit_display"), ("cli_turn", "admit_cli_turn")):
        module(monkeypatch, "gateway.session_" + name, **{function: lambda payload: {}})
    async def tracked_write(authority, write, *, then, after, ordered):
        assert authority is owner and ordered is True
        row = then(write())
        after()
        return row
    module(monkeypatch, "gateway.session_runtime_workers", tracked_write=tracked_write)
    def request(sid):
        trial.session = sid
        selected = select(trial)
        value = json.loads(selected.encoded)
        req = SimpleNamespace(ref=SimpleNamespace(profile_id=trial.owner.profile_id, session_id=sid),
            request_id=value["input"]["submission_id"], intent="queue", payload={"text": trial.text, "finite": True})
        return selected, req
    actor = SimpleNamespace(subject=trial.principal)
    selected, req = request("session-a")
    first = asyncio.run(owner.submit(actor, req, _mmx_eval=selected))  # No optional caller guard.
    assert asyncio.run(owner.submit(actor, req, _mmx_eval=selected))["admission_id"] == first["admission_id"]
    next_selected, next_req = request("session-b")
    with pytest.raises(RuntimeRefusal, match="ORIGINAL_CARRIER"):
        asyncio.run(owner.submit(actor, next_req, _mmx_eval=next_selected))
    public = copy.copy(req)
    public.payload = {**req.payload, inputs.MARKER_KEY: json.loads(selected.encoded)}
    with pytest.raises(a.core["RuntimeStoreError"], match="invalid_params"):
        asyncio.run(owner.submit(actor, public))
    assert a.conn.execute("SELECT COUNT(*) FROM session_admissions").fetchone()[0] == 1


def test_plain_input_bytes_are_privacy_checked_even_when_the_hash_matches(trial):
    value = marker(trial)
    text = "Bearer " + "synthetic0123456789"
    value["input"]["text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    value["scenario"]["input_fixture"]["digest"] = "sha256:" + value["input"]["text_sha256"]
    for pair in value["scenario"]["source_policy"]["allowlist_artifacts"]:
        if pair["artifact_ref"] == value["scenario"]["input_fixture"]["artifact_ref"]:
            pair["digest"] = value["scenario"]["input_fixture"]["digest"]
    value["scenario"] = add_document_digest(value["scenario"], "scenario_digest")
    reseal(value)
    with pytest.raises(RuntimeRefusal, match="RETENTION"):
        inputs.validate_marker(value, text=text)


def test_evaluation_records_share_original_budget_and_seal(lifecycle, tmp_path):
    t = native_trial(lifecycle, tmp_path)
    def fill(out):
        scope = out["scope"]
        scope.metadata_bytes = observation.MAX_METADATA_BYTES - 2
        scope.evaluation.record_assembly(out["agent"], out["kwargs"], scope.events[0])
        assert "metadata_overflow" in scope.evaluation.errors
    out = execute_trial(lifecycle, t, after_request=fill)
    scope = out["scope"]
    before = copy.deepcopy(scope.evaluation.assemblies)
    scope.evaluation._append(out["agent"], scope.evaluation.assemblies, {}, "assembly_overflow")
    assert scope.closed and scope.evaluation.assemblies == before
    assert len(canonical_json_bytes(out["saved"][inputs.RESULT_KEY])) + len(
        canonical_json_bytes(out["saved"][observation.RESULT_KEY])) <= observation.MAX_METADATA_BYTES


@pytest.mark.parametrize("change", ["seed", "extra_body", "generation", "memory", "extra_input"])
def test_execution_middleware_drift_refuses_before_original_client(lifecycle, engine, tmp_path, monkeypatch, change):
    t = native_trial(lifecycle, tmp_path)
    factories = []
    def downstream(out):
        def middleware(payload, next_call, **kw):
            if change == "generation":
                engine.rows["session-1"]["generation"] += 1
            elif change == "extra_body":
                payload["extra_body"] = {"seed": 2}
            elif change == "extra_input":
                payload["extra_body"] = {"input": None}
            elif change == "memory":
                payload["messages"][-1]["content"] = "memory was removed after the hook"
            else:
                payload["seed"] = 2
            return next_call(payload)
        monkeypatch.setattr(engine.middleware, "run_llm_execution_middleware", middleware)
        engine.invoke(out["agent"], out["kwargs"], lambda: factories.append("created"))
    with pytest.raises(RuntimeRefusal):
        execute_trial(lifecycle, t, after_request=downstream)
    assert factories == []


def actual_custom_effort(effort):
    vocabulary = pinned_functions("agent/reasoning_effort.py", None, {})
    profile = pinned_functions("plugins/model-providers/custom/__init__.py", {"CustomProfile", "_looks_like_ollama_endpoint"}, {
        "ProviderProfile": object, "urlparse": urlparse,
        "base_url_host_matches": lambda url, host: urlparse(url).hostname == host,
        "clamp_effort": vocabulary["clamp_effort"], "OPENAI_COMPAT_WIRE_EFFORTS": vocabulary["OPENAI_COMPAT_WIRE_EFFORTS"]})
    return profile["CustomProfile"]().build_api_kwargs_extras(
        reasoning_config={"enabled": True, "effort": effort}, base_url="https://api.z.ai/api/paas/v4")


@pytest.mark.parametrize("effort", ["low", "high"])
def test_actual_named_custom_profile_emits_the_supported_native_effort(effort):
    route = provider_route()
    extra, top = actual_custom_effort(effort)
    assert route["runtime"]["provider"] == "custom"
    assert route["runtime"]["requested_provider"] == "zai-glm"
    assert extra == {} and top == {"reasoning_effort": effort}


def test_actual_sdk_serialization_and_original_worker_receive_trial_inputs(lifecycle, engine, tmp_path):
    openai = pytest.importorskip("openai")
    t = native_trial(lifecycle, tmp_path)
    bodies = []
    def handler(request):
        assert str(request.url).startswith("https://api.z.ai/api/paas/v4/")
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=success("glm-5.3"))
    def downstream(out):
        extra, top = actual_custom_effort(out["agent"].reasoning_config["effort"])
        assert extra == {}
        out["kwargs"].update(top)
        response = engine.invoke(out["agent"], out["kwargs"], lambda: openai.OpenAI(
            api_key="synthetic-fixture", base_url="https://api.z.ai/api/paas/v4/", max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(handler))), request_id="eval-request")
        assert response.model == "glm-5.3"  # Reported response label, not model identity proof.
    out = execute_trial(lifecycle, t, after_request=downstream)
    assert len(bodies) == 1 and bodies[0]["seed"] == 0 and bodies[0]["reasoning_effort"] == "low"
    assert bodies[0]["messages"][0]["content"].endswith(inputs.render_inputs(
        t.specification["candidate_files"], t.specification["context_text"]))
    transport = out["saved"][observation.RESULT_KEY]["transport"]
    assert len(transport["attempts"]) == 1
    assert transport["attempts"][0]["request"]["content_sha256"] == observation._content_digest(bodies[0])["content_sha256"]
    assert transport["provider_delivery_proven"] is transport["model_identity_verified"] is False


def test_eval_owner_requires_current_original_dispatch_installation(engine, monkeypatch):
    owner = object.__new__(inputs.NativeEvalInputOwner)
    owner.binding = engine.binding
    owner.require_transport()
    monkeypatch.setattr(engine.helpers, "_dispatch_nonstreaming_api_request", lambda *_a, **_kw: None)
    with pytest.raises(RuntimeRefusal, match="DISPATCH_FENCE"):
        owner.require_transport()
