"""Same-root project-help scope over actual current-C and Runtime owners.

The disposable project is explicitly published as COO-accountable before it
becomes the configured C baseline. An ordinary CEO-v2 COO admission owns its
root and committed continuation commission; no Project Execution admission or
direct-native planning root is substituted. Canonical AgentOS code,
Control Room dispatch gather, cache publication, Mission v3, bounded Runtime,
adopted-plan acquisition and installed enrollment all run. Existing fixture
OAuth/source-seal/physical provider seams remain test-only.
"""
from __future__ import annotations

import copy
import dataclasses
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from pathlib import Path
import sys

import pytest
import yaml

from common import coo_project_help_contract as help_wire
from control_plane import ceo_intent, chairman_control_room, executive_inbox, surface_bindings
from control_plane.coo_principal_host import CooHostProvider
from control_plane.coo_principal_mandate import _mission_state, project_coo_principal_mandate
from control_plane.coo_project_help_read import capture_project_help_authority
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_executive_app.coo_binding import (
    COO_SCOPES, BINDING_SCHEMA, _digest, principal_frame,
)
from integrations.mastermind_workspace_app.contract import workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from tests.fresh_conversation_full_cache import CanonicalFixtureCache
from tests.test_coo_project_help_authority import (
    _adopt_actual_source_plan, _frame, full_joined, owner, env, isolated_git_env, identity,
)
from tests.test_executive_coo_host import setup
from tests.test_fabric_result_projection import _bound_reader, _release
from tests.test_executive_coo_hierarchy_service import _complete, _plan_body
from tests.test_executive_coo_hierarchy_cycle import finish_result
from tests.test_joint_api_contract import enable_joint_profile
from tests.test_project_discovery_installed_plan import actual_child
from tests.test_workspace_project_git_publisher import git
from tests.test_executive_service import _coo_intent, _capture_projection


def publish_coo_accountability(j):
    """Explicit fixture source publication, never a changed projection row."""
    path = j["integrator"] / j["args"]["project_source"]["path"]
    raw = path.read_text()
    assert raw.startswith("---\n")
    front, body = raw[4:].split("\n---", 1)
    metadata = yaml.safe_load(front)
    metadata["owner"] = "coo-fable"
    metadata["status"] = "active"
    from scripts import agentos
    path.write_text(agentos._yaml_frontmatter(metadata) + body)
    git(j["integrator"], "add", str(path.relative_to(j["integrator"])))
    git(j["integrator"], "commit", "-m", "Fixture explicit COO project accountability")
    # The following real plan/adoption commit pushes this prior source change.


def publish_continuation_commission(j):
    """Publish actual ordinary COO source before constructing its new root."""
    relative = "research/executive_commissions/JOINT_API_CONTINUATION.md"
    raw = (
        "# Disposable ordinary COO continuation commission\n\n"
        f"Work: {j['args']['work_ref']}\n\n"
        "Continue the admitted COO plan through its explicitly selected bounded "
        "READ child, observe the original result, and acknowledge that result "
        "through the original API principal. This is test source; the physical "
        "provider and prior dialogue receiver are inert. It does not commission "
        "a Project Execution admission, native-origin claim, or product acceptance.\n"
    ).encode()
    path = j["integrator"] / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    git(j["integrator"], "add", relative)
    git(j["integrator"], "commit", "-m", "Fixture ordinary COO continuation commission")
    commit = git(j["integrator"], "rev-parse", "HEAD").strip()
    assert git(j["integrator"], "show", f"{commit}:{relative}").encode() == raw
    # The subsequent plan/adoption publication pushes this immutable source.
    return {"repository": "mastermindx-market-intelligence/macro", "commit": commit,
            "path": relative, "content_sha256": hashlib.sha256(raw).hexdigest()}


class CurrentProjectCache(CanonicalFixtureCache):
    def __init__(self, *args, runtime, bindings_path, **options):
        self.runtime = runtime
        self.bindings_path = bindings_path
        super().__init__(*args, **options)

    def compile(self, runtime=None):
        runtime = runtime or self.runtime
        precursor = super().compile(runtime)
        cards = precursor["autonomy"]["responsibilities"]
        dispatch = chairman_control_room._gather_dispatch_evidence(
            runtime.store.root, cards, precursor["generated_at"])
        _, jobs, failure = chairman_control_room._read_runtime_jobs_from_runtime(runtime)
        assert failure is None
        inbox = executive_inbox.build_inbox(repo_root=self.root, runtime_root=runtime.store.root,
            boot_packet=self.packet, now=precursor["generated_at"])
        # Same precursor/gather/final composition used by the production owner.
        self.dispatch_evidence = dispatch
        bindings, problems = surface_bindings.load_bindings(self.bindings_path)
        assert not problems
        return chairman_control_room.compose_control_room(inbox=inbox, boot_packet=self.packet,
            active_builds=None, agent_os_state=self.state, runtime_jobs=jobs,
            bindings=bindings, generated_at=precursor["generated_at"], dispatch_evidence=dispatch)


def current_project_workspace(j, *, runtime, monkeypatch, tmp_path):
    bindings_path = tmp_path / "navigation" / "surface-bindings.json"
    surface_bindings.save_bindings({"schema": surface_bindings.SCHEMA, "bindings": [
        surface_bindings.new_binding(work_ref=j["args"]["work_ref"], role="coo",
            provider="codex", locator_kind="codex_session",
            locator={"session_id": "PROVIDER-SESSION-1", "cwd": str(tmp_path)},
            observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    ]}, bindings_path)
    cache = CurrentProjectCache(j["integrator"], tmp_path / "current-project-cache",
        mastermind_revision=j["factory"].service.config.proof_base_sha, runtime=runtime,
        bindings_path=bindings_path)
    _, authorize = workspace_authorizers(policy=j["factory"].workspace_policy,
        load_bindings=lambda: legacy_workspace_document(j["document"], j["factory"].workspace_policy))
    keeper, namespace, binding, reader = _bound_reader(runtime)
    workspace = WorkspaceReadService(cache=cache.cache, runtime=runtime,
        authorize=authorize, armed={}, runtime_identity={},
        bounded_runtime=lambda actual: reader if actual is runtime else None,
        canonical_project_data=j["data"].installed_binding())
    return workspace, cache, (keeper, binding)


def configure_current_project_data(j, monkeypatch):
    """A new installed fixture reader on the genuinely published new C.

    The original CREATE reader's C predates this project and therefore cannot
    use unchanged-DATA proof after its published owner field was changed. A
    separately constructed current-C fixture is explicit; no live collector
    pin, publication receipt or original operation is relabeled.
    """
    from integrations.executive_mcp import installed
    from integrations.mastermind_workspace_app.canonical_project_data import InstalledCanonicalProjectData
    collector = installed.InstalledBootPacketCollector(source_root=j["source_root"],
        macro_root=j["integrator"], code_root=Path(__file__).parents[1],
        python_executable=Path(sys.executable),
        expected_source_sha=j["factory"].service.config.proof_base_sha)

    def captured_source(env, *, deadline=None, snapshot_capture=None):
        observed = installed._clean_git_snapshot(j["integrator"], runner=collector._runner,
            env=env, label="Macro source", content_scope="macro_brief", include_seal=True,
            deadline=deadline, snapshot_capture=snapshot_capture, _allow_synthetic_fixture=True)
        return j["factory"].service.config.proof_base_sha, observed[0], "synthetic-test-Root-seal", observed[1]

    monkeypatch.setattr(collector, "_snapshot_pair", captured_source)
    owner = j["data"]
    configured = {**j, "collector": collector, "code_root": j["integrator"], "code": j["current"]}
    actual_child(configured, monkeypatch)
    configured["data"] = InstalledCanonicalProjectData(collector=collector, policy=owner.policy,
        load_bindings=owner.loader, git_identity=owner.identity, events=owner.events,
        runtime_guard=owner.runtime_guard)
    return configured


def admit_selected_child(service, root):
    runtime = service.runtime
    planner = runtime.jobs.create_cycle_planner(root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0")
    dispatched = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id=service.config.worker_id)
    body = _plan_body(dispatched, root)
    _complete(runtime, dispatched, body)
    children = runtime.jobs.admit_cycle_plan(root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{dispatched.attempt.attempt_id}")
    return runtime.jobs.get_job(planner.job_id), children[0]


def publish_planner_return(service, planner):
    return asyncio.run(publish_planner_return_async(service, planner))


async def publish_planner_return_async(service, planner):
    """Original planner's phase/Wake owners; physical Relay/receiver are inert.

    This is a continuation fixture: a previously delivered planner turn has
    an explicit current OHF receiver ACK. It is not first-child bootstrap,
    native T3 origin, or the API-principal result acknowledgment under test.
    """
    from control_plane.executive_terminal_return import reduce_terminal_return
    from control_plane.wake_events import mint_obligation
    from control_plane.wake_ledger import requested_record
    from control_plane.wake_persist import WakeLedgerRepository
    runtime = service.runtime
    await service._project_terminal_return(planner.job_id,
        expected_attempt_id=planner.current_attempt_id)
    assert service._terminal_return_last_diagnostic == "terminal-return:APPLIED"
    candidate = reduce_terminal_return(material=runtime.validated_role_completion(
        planner.job_id, expected_attempt_id=planner.current_attempt_id))
    obligation = mint_obligation(wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention",
        source_ref="agent_dialogue_attention:" + hashlib.sha256(candidate.message_key.encode()).hexdigest(),
        declared_target_seat="coo", job_id=candidate.job_id, attempt_id=candidate.attempt_id,
        root_job_id=candidate.root_job_id, source_workstream=candidate.dialogue_source.work_ref,
        source_created_at=candidate.terminal_at, emitted_at=candidate.terminal_at)
    WakeLedgerRepository(runtime).append_record(requested_record(obligation), obligation=obligation)
    _acknowledge_prior_planner_turn(runtime, obligation)
    return candidate


def _acknowledge_prior_planner_turn(runtime, obligation):
    from tests.test_wake_ack_ingress import _admitted_runtime
    from control_plane.runtime_binding_projection import project_runtime_binding
    from control_plane.session_targets import SCHEMA, SessionTarget, SessionTargetRegistry, route_obligation
    from control_plane.wake_ack_ingress import (
        TrustedWorkerWakeAckProjection, WakeAckClaim, acknowledge_consumed_wakes,
    )
    from control_plane.wake_dispatcher import mint_nudge_id
    from control_plane.wake_ledger import LedgerPhase, attempt_record, make_delivery_attempt
    from control_plane.wake_persist import WakeLedgerRepository
    # The incumbent source fixture seals a separate current receiver through
    # actual OHF owners. Its unassociated root does not change this project's
    # sole admitted root. Only the physical process/native turn is modeled.
    receiver_runtime, sealed, generation = _admitted_runtime(runtime.store.root, runtime=runtime)
    assert receiver_runtime is runtime
    target = SessionTarget(session_alias="COO-CODEX", target_seat="coo",
        reasoning_surface="codex", wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",), workstream=None, target_enabled=False)
    registry = SessionTargetRegistry(schema=SCHEMA, lifecycle_authority="executive_os",
        production_armed=False, policy_version="joint-api-prior-return-fixture",
        default_alias_by_seat={"coo": target.session_alias}, workstream_alias_by_seat={},
        root_job_bindings={}, targets={target.session_alias: target})
    registry = registry.with_root_job_bindings({obligation.root_job_id: {"coo": target.session_alias}})
    binding = project_runtime_binding(receiver_runtime, sealed.attempt_id, target)
    route = route_obligation(obligation, registry, binding=binding)
    attempt = make_delivery_attempt(obligation, route, attempt_n=1)
    commands = (attempt.attempt_command_id,)
    nudge_id = mint_nudge_id(route.destination_digest, commands)
    attempt = dataclasses.replace(attempt, nudge_id=nudge_id,
        nudge_attempt_command_ids=commands)
    WakeLedgerRepository(runtime).append_records_atomic(tuple(
        (attempt_record(attempt, phase), obligation)
        for phase in (LedgerPhase.DELIVERY_ATTEMPT, LedgerPhase.DELIVERED)))
    trusted = TrustedWorkerWakeAckProjection(target_attempt_id=sealed.attempt_id,
        process_generation_id=generation.process_generation_id,
        binding_id=binding.binding_id, binding_generation=binding.binding_generation,
        provider_session_id=str(binding.native_handle), provider_native_turn_id="TURN-ACK-1",
        nudge_id=nudge_id, obligation_ids=(obligation.obligation_id,), terminal_ack_trailer=True)
    result = acknowledge_consumed_wakes(receiver_runtime, registry,
        claim=WakeAckClaim(trusted.obligation_ids), trusted=trusted)
    assert len(result) == 1 and result[0].inserted is True


@pytest.fixture
def current_joint_project(full_joined, monkeypatch, tmp_path, request):
    j = full_joined
    assert j["runtime"].jobs.list_jobs() == []
    actual_child(j, monkeypatch)
    publish_coo_accountability(j)
    commission = publish_continuation_commission(j)
    source_plan, raw_plan = _adopt_actual_source_plan(j)
    j = configure_current_project_data(j, monkeypatch)
    # This fixture's source setup advances its protected source commit before
    # admission. Construct a new owner on that exact configuration; never
    # rewrite a running service's retained execution binding.
    from control_plane.executive_service import ExecutiveControlService
    original_service = j["factory"].service
    service = ExecutiveControlService(dataclasses.replace(original_service.config,
        coo_operator_harness_armed=False, coo_foreground_only=False,
        coo_tick_interval_seconds=3600.0),
        autonomy_guard=original_service._autonomy_guard,
        ceo_submit_admission_guard=original_service._ceo_submit_admission_guard,
        terminal_return_projector=lambda candidate: _capture_projection([], candidate))
    service.runtime = j["runtime"]
    service._register_worker()
    intent = _coo_intent(service.config, "joint-api-project")
    intent["workstream"] = j["args"]["work_ref"]
    source = {"schema_version": "mastermind.executive_dialogue_source/v1",
        "work_ref": intent["workstream"], "watch_mode": "turn_watch_v1",
        "commission_ref": commission}
    receipt = ceo_intent.submit_intent(j["runtime"], intent,
        workspace_root=service.config.proof_workspace_root,
        execution_binding=service._require_current_coo_binding(), dialogue_source=source)
    root = j["runtime"].jobs.get_job(receipt["job_id"])
    from control_plane.project_execution_admission import read_source
    # An ordinary COO root must not advertise the reserved Project Execution
    # family without that owner's original issuer/input receipt. Check the
    # canonical discriminator before creating or consuming any child.
    assert read_source(j["runtime"], root) is None
    event = j["runtime"].store.unique_root_created_event(root.job_id)
    assert event.payload["provenance"]["dialogue_source"] == source
    assert service._coo_binding_for_root(root) == service._require_current_coo_binding()
    planner, work_child = admit_selected_child(service, root)
    workspace, cache, lease = current_project_workspace(j, runtime=j["runtime"],
        monkeypatch=monkeypatch, tmp_path=tmp_path)
    try:
        initial_mission = workspace.read_mission_for_work_ref(intent["workstream"])
        assert _mission_state(initial_mission, expected_work_ref=intent["workstream"]).qualified is False
        assert initial_mission["transport"]["historical"] is True
        prior_return = publish_planner_return(service, planner)
        cache.publish(runtime=j["runtime"])
        source_dir = tmp_path / "joint-api-enrollment"
        source_dir.mkdir()
        source_host, config, _, policy_path = setup(source_dir)
        scope = {"schema": help_wire.SCOPE_SCHEMA, "root_job_id": root.job_id,
                 "source_plan": source_plan}
        family = getattr(request, "param", "t3")
        profile = enable_joint_profile(config, policy_path, family=family, scope=scope)
        policy = dataclasses.replace(j["factory"].policies.read,
            policy_id="project-help-coo", required_scopes=COO_SCOPES)
        principal = dataclasses.replace(j["workspace"], policy_id=policy.policy_id,
            resource=policy.resource, scopes=policy.required_scopes)
        config["policy"] = json.loads(json.dumps(dataclasses.asdict(policy)))
        config["binding"] = {"schema": BINDING_SCHEMA, "enabled": True,
            "binding": {**principal_frame(principal), "permission_digest": "a" * 64}}
        config["missions"][0].update(work_ref=j["args"]["work_ref"],
            principal_binding_digest=_digest(config["binding"]["binding"]))
        provider = CooHostProvider(source_host.source, workspace)
        f = SimpleNamespace(j=j, work=j["args"]["work_ref"], root=root.job_id,
            root_job=root, work_child=work_child, workspace=workspace, cache=cache,
            provider=provider, coo=config, source_plan=source_plan, raw_plan=raw_plan,
            scope=scope, principal=principal, policy_path=policy_path, profile=profile,
            family=family, service_config=service.config, service=service,
            continuation_commission=commission)
        f.initial_mission, f.prior_return = initial_mission, prior_return
        f.frame = _frame(f)
        yield f
    finally:
        _release(*lease)


def test_joint_help_uses_genuine_current_mission_and_admitted_coo_root(current_joint_project):
    f = current_joint_project
    mission = f.workspace.read_mission_for_work_ref(f.work)
    state = _mission_state(mission, expected_work_ref=f.work)
    if not state.qualified:
        snapshot = f.workspace.cache.snapshot()
        card = next(row for row in snapshot.document["autonomy"]["responsibilities"] if row["responsibility_ref"] == f.work)
        receipt = next(row for row in snapshot.validity["cards"] if row["responsibility_ref"] == f.work)
        pytest.fail(json.dumps({"state": dataclasses.asdict(state),
            "read_state": mission["read_state"], "degraded": mission["degraded"],
            "transport": mission["transport"],
            "dispatch": f.cache.dispatch_evidence,
            "card_validity": card["validity"], "receipt": receipt,
            "cache": snapshot.currentness, "missingness": mission["missingness"]}, sort_keys=True))
    _, principal, authority = f.provider.source.for_principal(principal_frame(f.principal), f.work)
    projection = project_coo_principal_mandate(principal=principal, authority=authority,
                                             mission_workspace=mission)
    assert projection["new_effect_gate"] == "OPEN", projection
    assert projection["decision_posture"] == "DECIDE_CONTINUE", projection
    captured = capture_project_help_authority(f.provider, f.frame)
    assert captured.scope == f.scope
    assert captured.mission_read["qualification"] == "CURRENT_MISSION"
    assert captured.mission_read["mission_read_state"] == "CURRENT"
    assert f.root_job.orchestration_role == "aggregation"
    assert f.work_child.root_job_id == f.root and f.work_child.parent_job_id == f.root
    assert f.workspace.runtime.jobs.get_job(f.root).job_id == f.root_job.job_id


def test_reserved_project_execution_commission_requires_its_original_owner(current_joint_project):
    """The original bad fixture premise remains a canonical refusal."""
    from control_plane.executive_runtime import StateConflict
    from control_plane.project_execution_admission import COMMISSION_PATH, read_source
    f, runtime = current_joint_project, current_joint_project.j["runtime"]
    intent = _coo_intent(f.service.config, "reserved-project-source-negative")
    intent["workstream"] = f.work
    source = {"schema_version": "mastermind.executive_dialogue_source/v1",
        "work_ref": f.work, "watch_mode": "turn_watch_v1",
        "commission_ref": {"repository": "mastermindx-market-intelligence/Mastermind",
            "commit": f.service.config.proof_base_sha, "path": COMMISSION_PATH,
            "content_sha256": hashlib.sha256(
                (f.service.config.proof_source_repository / COMMISSION_PATH).read_bytes()).hexdigest()}}
    receipt = ceo_intent.submit_intent(runtime, intent,
        workspace_root=f.service.config.proof_workspace_root,
        execution_binding=f.service._require_current_coo_binding(), dialogue_source=source)
    root = runtime.jobs.get_job(receipt["job_id"])
    before = [event.to_dict() for event in runtime.events.list_events()]
    with pytest.raises(StateConflict, match="^PROJECT_EXECUTION_ORIGINAL_SOURCE_INVALID$"):
        read_source(runtime, root)
    with pytest.raises(StateConflict, match="^PROJECT_EXECUTION_ORIGINAL_SOURCE_INVALID$"):
        f.service._coo_binding_for_root(root)
    assert root.attempt_count == 0 and root.current_attempt_id is None
    assert not [job for job in runtime.jobs.list_jobs() if job.parent_job_id == root.job_id]
    assert [event.to_dict() for event in runtime.events.list_events()] == before


@pytest.mark.parametrize("change", ["foreign_root", "source_generation", "foreign_contract", "revoked"])
def test_joint_current_owner_refuses_changed_original_scope(current_joint_project, change):
    from control_plane.coo_principal_envelope import PrincipalAdmissionContext
    f = current_joint_project
    original_frame = copy.deepcopy(f.frame)
    row = f.coo["missions"][0]
    context = PrincipalAdmissionContext(**original_frame["principal_context"])
    captured = f.provider.capture_selected_child_target(principal=original_frame["principal"],
        context=context, work_ref=f.work, root_job_id=f.root, child_job_ids=[f.work_child.job_id])
    assert captured["root_job_id"] == f.root
    if change == "foreign_root":
        foreign = next(job for job in f.j["runtime"].jobs.list_jobs()
            if job.depth == 0 and job.job_id != f.root)
        row["project_help"]["root_job_id"] = foreign.job_id
    elif change == "source_generation":
        row["project_help"]["source_plan"]["source"]["commit"] = "f" * 40
    elif change == "foreign_contract":
        row["project_help"]["source_plan"]["contract_sha256"] = "f" * 64
    else:
        row["enabled"] = False
    before = [event.to_dict() for event in f.j["runtime"].events.list_events()]
    with pytest.raises(ValueError):
        capture_project_help_authority(f.provider, original_frame)
    with pytest.raises(ValueError):
        f.provider.capture_selected_child_target(principal=original_frame["principal"],
            context=context, work_ref=f.work, root_job_id=f.root, child_job_ids=[f.work_child.job_id])
    if change != "revoked":
        current = _frame(f)
        with pytest.raises((ValueError, LookupError)):
            capture_project_help_authority(f.provider, current)
        if change == "foreign_root":
            with pytest.raises(ValueError, match="scope"):
                f.provider.capture_selected_child_target(principal=current["principal"],
                    context=PrincipalAdmissionContext(**current["principal_context"]),
                    work_ref=f.work, root_job_id=f.root, child_job_ids=[f.work_child.job_id])
    assert [event.to_dict() for event in f.j["runtime"].events.list_events()] == before
