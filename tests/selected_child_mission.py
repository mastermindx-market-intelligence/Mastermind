"""Declared continuation source with real cache, Mission and Runtime owners.

Only the disposable Agent OS source, navigation binding and physical receiver
are fixture premises. Root resolution, owed turn, validity, dispatch evidence
and Mission qualification come from their existing production owners.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import time

from control_plane import chairman_control_room, executive_inbox, surface_bindings
from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.coo_principal_host import CooHostProvider, MISSION_AUTHORITY_VERSION
from control_plane.coo_principal_mandate import (
    _decision_posture, _effect_gate, _mission_state, DecisionPosture, NewEffectGate,
)
from control_plane.workspace_read_service import ExistingControlRoomCache, WorkspaceReadService
from scripts import chairman_control_room as cache_owner
from tests.test_executive_coo_host import setup
from tests.test_workspace_project_git_publisher import git

WORK_REF = "WS:EXECUTIVE-CAPACITY-FABRIC"


def continuation_source(config):
    """Commit the fixture's own source before the service captures its base."""
    relative = "docs/commissions/selected-child-continuation.md"
    content = (
        "# Disposable selected-child continuation\n\n"
        f"Work: {WORK_REF}\n\n"
        "Continue one explicitly selected READ child after the prior planner "
        "return is acknowledged through the original Wake owners. Physical "
        "provider and receiver observations are inert test premises.\n"
    ).encode()
    path = config.proof_source_repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    git(config.proof_source_repository, "add", relative)
    git(config.proof_source_repository, "commit", "-m", "Fixture selected-child continuation source")
    commit = git(config.proof_source_repository, "rev-parse", "HEAD").strip()
    assert git(config.proof_source_repository, "show", f"{commit}:{relative}").encode() == content
    source = {"schema_version": "mastermind.executive_dialogue_source/v1",
        "work_ref": WORK_REF, "watch_mode": "turn_watch_v1",
        "commission_ref": {"repository": "mastermindx-market-intelligence/Mastermind",
            "commit": commit, "path": relative,
            "content_sha256": hashlib.sha256(content).hexdigest()}}
    return replace(config, proof_base_sha=commit), source


def _clock_sample():
    # Explicit coupled-clock fixture; time still advances between observations.
    # This is not an installed Darwin clock-capability claim.
    instant = time.time_ns() // 1_000_000
    return (instant, instant, instant, instant)


class SelectedChildMission:
    def __init__(self, service, root, directory):
        self.service, self.root = service, root
        source_host, self.config, _, _ = setup(directory)
        row = self.config["missions"][0]
        assert row["work_ref"] == WORK_REF
        row.update(authority_version=MISSION_AUTHORITY_VERSION,
            principal_actions=["bounded_intent", "governed_orchestration"])
        self.owner = cache_owner.ServerConfig(repo_root=service.config.proof_source_repository,
            macro_root=None, bindings_path=None, token="inert-selected-child-fixture",
            origin="http://127.0.0.1:0", port=0, validity_sample_fn=_clock_sample)
        self.cache = ExistingControlRoomCache(lambda: self.owner)
        stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.bindings = {"schema": surface_bindings.SCHEMA, "bindings": [
            surface_bindings.new_binding(work_ref=WORK_REF, role="coo", provider="codex",
                locator_kind="codex_session", locator={"session_id": "PROVIDER-SESSION-1",
                    "cwd": str(directory)}, observed_at=stamp)]}
        self.workspace = WorkspaceReadService(cache=self.cache, runtime=service.runtime,
            authorize=None, armed={}, runtime_identity={},
            bounded_runtime=lambda actual: service._namespace_custody.bound_runtime(actual))
        self.provider = CooHostProvider(source_host.source, self.workspace)
        _, principal, authority = self.provider.source.snapshot(WORK_REF)
        self.facts = dict(context=PrincipalAdmissionContext(WORK_REF,
            principal.principal_binding_digest, authority.mission_authority_ref,
            authority.authority_generation_digest), root_job_id=root.job_id,
            capability_profile_digest=authority.capability_profile_digest)
        self.publish()

    def publish(self):
        runtime = self.service.runtime
        anchor = self.owner.validity_sample_fn()
        stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        source = {"schema": "agent_os_state.v1", "generated_at": stamp,
            "workstreams": [{"key": WORK_REF.removeprefix("WS:"),
                "title": "Disposable selected-child continuation",
                "owner": "coo-fable", "status": "active"}]}
        _, jobs, problem = chairman_control_room._read_runtime_jobs_from_runtime(runtime)
        assert problem is None
        inbox = executive_inbox.build_inbox(repo_root=self.service.config.proof_source_repository,
            runtime_root=runtime.store.root, include_boot_packet=False, now=stamp)
        inputs = dict(inbox=inbox, boot_packet=None, active_builds=None,
            agent_os_state=source, runtime_jobs=jobs, bindings=self.bindings, generated_at=stamp)
        precursor = chairman_control_room.compose_control_room(**inputs)
        dispatch = chairman_control_room._gather_dispatch_evidence(runtime.store.root,
            precursor["autonomy"]["responsibilities"], stamp)
        document = chairman_control_room.compose_control_room(**inputs, dispatch_evidence=dispatch)
        sample = self.owner.validity_sample_fn()
        with self.owner.state_lock:
            self.owner.state_published_seq += 1
            self.owner.state_cache.update(doc=document, composed_monotonic=time.monotonic())
            cache_owner._publish_source_validity(self.owner, document, anchor, sample)
        return document

    def require_current(self):
        state = _mission_state(self.workspace.read_mission_for_work_ref(WORK_REF),
            expected_work_ref=WORK_REF)
        _, _, authority = self.provider.source.snapshot(WORK_REF)
        gate, _ = _effect_gate(state, authority)
        decision, _ = _decision_posture(state, gate)
        assert state.qualified and state.root_job_id == self.root.job_id, state
        assert state.accountable_seat == state.owed_seat == "coo", state
        assert gate is NewEffectGate.OPEN and decision is DecisionPosture.DECIDE_CONTINUE, state
        self.provider.guard_dialogue(**self.facts)
        return state
