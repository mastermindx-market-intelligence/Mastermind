"""The frozen selected-child source producer, its publication and both consumers.

Real disposable Runtime with a real admitted plan, the real
WorkspaceReadService, the real CooInstalledSource with the real
ExecutionCapabilityRegistry, and the existing publication Host fixture.
Only the unavoidable privileged ownership and platform seams are mocked:
the root-owned sealed installation and the not-yet-composed C29 target class.

The C29 target class is owned by a sibling commission. When it is absent
this file falls back to a LOCAL stand-in that carries only the interface
the commission declares, so the injection wiring is still exercised. The
stand-in is a test fixture; it is never a production substitute, and the
real class is used whenever it is importable.
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from control_plane import executive_runtime as er
from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.coo_principal_host import (
    CooHostProvider,
    build_selected_child_publication,
    selected_child_material,
    selected_child_material_digest,
    validate_selected_child_target,
)
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.workspace_read_service import (
    ExistingControlRoomCache,
    WorkspaceReadService,
)
from integrations.mastermind_executive_app.coo_binding import _digest
from ops.executive_os import executive_mcp_entry as entry
from ops.executive_os import mcp_component_update as m
from ops.executive_os.coo_principal_host import (
    CooInstalledSource,
    prepare_selected_child_target,
    write_selected_child_target_input,
)
from scripts import chairman_control_room as ccr

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_coo_principal_mandate as mandate
    import test_executive_coo_install_binding as install
    import test_executive_finite_guards as finite
    import test_executive_service_control as service_control
    import test_mcp_component_update as component
finally:
    sys.path.pop(0)

ROOT = Path(__file__).resolve().parents[1]
PRINCIPAL_PROFILE = "principal.claude-code.executive-coo.v1"
WORK_REF = "WS:EXECUTIVE-CAPACITY-FABRIC"
OLD_RELEASE = component.OLD_RELEASE
NEW_RELEASE = component.NEW_RELEASE
SEALED_BASE = Path("/run/mmx-c30-selected-child")
CCR_STAMP = "2026-09-21T00:00:00Z"


# --- the real Control Room owner -------------------------------------------------
#
# The published Control Room document is the real Workspace source of the
# responsibility row: the root selection, the root ambiguity and the
# qualification all live there.  The cache is the incumbent
# ``ExistingControlRoomCache`` over a real ``ServerConfig`` owner, so the
# bracket observes a real owner, a real instance, a real publication and
# real source validity.  Nothing here is a lambda or a stub.


def _control_room(tmp_path, *, root_job_id, work_ref=WORK_REF):
    """A real published Control Room over one resolved responsibility row."""

    epoch = int(datetime.fromisoformat(CCR_STAMP.replace("Z", "+00:00")).timestamp() * 1000)
    clock = [1000, epoch, 1000, epoch]
    meta = {"schema": "mastermind.autonomy_validity.v1",
            "policy": "mapper-inclusive-48h-future-1h.v1",
            "qualified_at": CCR_STAMP, "proof_ref": "a" * 64,
            "valid_for_ms": 60000}
    validity = {}
    for key in ("card", "decision_current", "dispatch", "owed_open_age"):
        validity[key] = dict(meta, sources=[{"observed_at": CCR_STAMP,
                                              "freshness": "current"}])
    responsibility = {
        "responsibility_ref": work_ref, "root_job_id": root_job_id,
        "freshness": "current", "root_job_candidates": [root_job_id],
        "root_job_ambiguous": False, "runtime_root_state": "RESOLVED",
        "is_actionable": True,
        "owed_turn": {"seat": "coo", "reason": "blocker_targets_seat"},
        "validity": validity,
    }
    document = {
        "schema": "mastermind.chairman_control_room.v1", "generated_at": CCR_STAMP,
        "degraded": [], "work": [{"work_ref": work_ref,
                                  "agent_os": {"title": "Executive Capacity Fabric"}}],
        "autonomy": {"schema": "mastermind.autonomy_control_room.v1",
                     "generated_at": CCR_STAMP, "responsibilities": [responsibility]},
    }
    owner = ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
                              token="fixture", origin="http://127.0.0.1:0", port=0,
                              validity_sample_fn=lambda: tuple(clock))
    owner.state_published_seq = 1
    owner.state_cache.update(doc=document, composed_monotonic=10.0)
    with owner.state_lock:
        ccr._publish_source_validity(owner, document, tuple(clock), tuple(clock))
    current = [owner]
    cache = ExistingControlRoomCache(lambda: current[0], monotonic=lambda: 10.1)
    return current, clock, cache, document


# --- the C29 target owner --------------------------------------------------------


def _real_target_class():
    """The composed C29 target class, or None when it is not composed yet."""

    try:
        from integrations.hermes_delegate.executive import ExecutiveSelectedChildTarget
    except ImportError:
        return None
    return ExecutiveSelectedChildTarget


@dataclasses.dataclass(frozen=True)
class _LocalSelectedChild:
    """A stand-in for the C29 selected child, used only by this test file."""

    selection: object
    attempt_ordinal: int

    @property
    def command_id(self) -> str:
        return (
            f"coo-cycle:{self.selection.root_job_id}:dispatch:"
            f"{self.selection.job_id}:attempt:{self.attempt_ordinal}"
        )


@dataclasses.dataclass(frozen=True)
class _LocalSelectedChildTarget:
    """A stand-in for the C29 target, carrying only its declared interface."""

    work_ref: str
    children: tuple
    currentness_guard: object = dataclasses.field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.children:
            raise ValueError("stand-in target needs children")
        if not callable(self.currentness_guard):
            raise ValueError("stand-in target needs a currentness guard")

    def child_for(self, command_id):
        matches = [child for child in self.children if child.command_id == command_id]
        return matches[0] if len(matches) == 1 else None

    def material_digest(self) -> str:
        payload = {
            "work_ref": self.work_ref,
            "children": [
                {
                    "command_id": child.command_id,
                    "attempt_ordinal": child.attempt_ordinal,
                    "root_job_id": child.selection.root_job_id,
                    "parent_job_id": child.selection.parent_job_id,
                    "job_id": child.selection.job_id,
                    "plan_attempt_id": child.selection.plan_attempt_id,
                    "plan_digest": child.selection.plan_digest,
                    "plan_step_id": child.selection.plan_step_id,
                    "repair_round": child.selection.repair_round,
                    "expected_current_attempt_id": child.selection.expected_current_attempt_id,
                }
                for child in self.children
            ],
        }
        return hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()

    def require_current(self) -> None:
        outcome = self.currentness_guard()
        if outcome is not None:
            raise ValueError("selected child target is not current")


REAL_TARGET_CLASS = _real_target_class()


@pytest.fixture
def target_owner(monkeypatch):
    """The C29 target owner, or a local stand-in when it is not composed yet.

    The stand-in carries ONLY the interface the commission declares. The
    children are always the real C29-owned ExecutiveSelectedChild values.
    """

    if REAL_TARGET_CLASS is not None:
        yield REAL_TARGET_CLASS
        return
    import integrations.hermes_delegate.executive as hermes
    monkeypatch.setattr(hermes, "ExecutiveSelectedChildTarget",
                        _LocalSelectedChildTarget, raising=False)
    yield _LocalSelectedChildTarget


# --- the disposable Runtime with an admitted plan --------------------------------


@pytest.fixture
def admitted(tmp_path):
    """A real Runtime whose root carries one admitted plan and one work child."""

    clock = finite.MutableClock(1_800_000_000_000)
    state = finite._drive_to_admitted(
        tmp_path / "runtime", clock, steps=1, review_required=True,
        intent_id="CEO-C30-CAPTURE-001")
    state.control_room_root = tmp_path
    return state


def _coo_source(work_ref=WORK_REF):
    path = ROOT / "config/executive_claude_principal_capabilities.json"
    registry = ExecutionCapabilityRegistry.load(path, source_root=ROOT)
    coo = install.coo_block()
    coo["missions"] = [dict(
        enabled=True, work_ref=work_ref,
        principal_binding_digest=_digest(coo["binding"]["binding"]),
        mission_authority_ref="authority:coo-test", outcome_ref="outcome:coo-test",
        proof_contract_ref="proof:coo-test", capability_profile_id=PRINCIPAL_PROFILE,
        capability_profile_digest=registry.profiles[PRINCIPAL_PROFILE].profile_digest,
        execution_profiles=["research_only"], allowed_write_paths=[])]
    return coo, path


def _host(state, *, work_ref=WORK_REF, control_room=None):
    """The installed COO host over the real Workspace and the real Runtime.

    The mission is NOT a lambda and the cache is NOT None: the host reads
    the real Mission v3 document over the real published Control Room, so
    the production path of the capture is the one under test.
    """

    coo, path = _coo_source(work_ref)
    source = CooInstalledSource(
        lambda: copy.deepcopy(coo),
        lambda: ExecutionCapabilityRegistry.load(path, source_root=ROOT))
    owners, clock, cache, document = _control_room(
        state.control_room_root, root_job_id=state.root.job_id, work_ref=work_ref)
    if control_room is not None:
        control_room(document)
    workspace = WorkspaceReadService(cache=cache, runtime=state.runtime, authorize=None,
                                     armed={}, runtime_identity={})
    host = CooHostProvider(source, workspace)
    row, fact, authority = source.snapshot(work_ref)
    principal = {key: value for key, value in coo["binding"]["binding"].items()
                 if key != "permission_digest"}
    context = PrincipalAdmissionContext(
        row["work_ref"], fact.principal_binding_digest,
        authority.mission_authority_ref, authority.authority_generation_digest)
    return host, principal, context, coo


def _capture(state, *, child_job_ids=None, work_ref=WORK_REF, control_room=None):
    host, principal, context, _ = _host(state, work_ref=work_ref,
                                        control_room=control_room)
    work = state.work(0)
    return host.capture_selected_child_target(
        principal=principal, context=context, work_ref=work_ref,
        root_job_id=state.root.job_id,
        child_job_ids=[work.job_id] if child_job_ids is None else child_job_ids)


def _publication(capture):
    return build_selected_child_publication(
        work_ref=capture["work_ref"], root_job_id=capture["root_job_id"],
        children=capture["children"], source=capture["source"])


def _runtime_snapshot(runtime):
    with runtime.store.read() as connection:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: [dict(row) for row in connection.execute(f"SELECT * FROM {name}")]
                for name in tables}


# --- A. the capture ---------------------------------------------------------------


def test_capture_freezes_the_selected_child_and_its_initial_ordinal(admitted):
    capture = _capture(admitted)
    work = admitted.work(0)
    child = capture["children"][0]
    assert len(capture["children"]) == 1
    assert child["job_id"] == work.job_id
    assert child["root_job_id"] == admitted.root.job_id
    assert child["parent_job_id"] == admitted.root.job_id
    assert child["plan_step_id"] == work.plan_step_id
    assert child["plan_attempt_id"] == work.plan_attempt_id
    assert child["plan_digest"] == work.plan_digest
    assert child["repair_round"] == 0
    # The intended NEXT Attempt of this child, frozen once.
    assert child["attempt_ordinal"] == 1
    assert child["expected_current_attempt_id"] is None
    assert child["command_id"] == (
        f"coo-cycle:{admitted.root.job_id}:dispatch:{work.job_id}:attempt:1")
    assert capture["source"]["plan_attempt_id"] == child["plan_attempt_id"]
    assert capture["source"]["plan_digest"] == child["plan_digest"]
    assert capture["source"]["observation_state"] in {"SAME", "UNKNOWN"}


def test_capture_material_digest_is_deterministic_and_covers_every_coordinate(admitted):
    capture = _capture(admitted)
    publication = _publication(capture)
    assert publication["material_digest"] == selected_child_material_digest(
        selected_child_material(capture["work_ref"], capture["children"]))
    assert validate_selected_child_target(publication) == publication
    for field in ("root_job_id", "parent_job_id", "job_id", "plan_attempt_id",
                  "plan_digest", "plan_step_id", "repair_round",
                  "attempt_ordinal", "expected_current_attempt_id", "command_id"):
        mutated = copy.deepcopy(publication)
        mutated["children"][0][field] = "OTHER"
        with pytest.raises(ValueError):
            validate_selected_child_target(mutated)


def test_capture_refuses_a_missing_unadmitted_or_foreign_child(admitted, tmp_path):
    work = admitted.work(0)
    # A Job that does not exist.
    with pytest.raises(Exception):
        _capture(admitted, child_job_ids=["JOB-999999"])
    # The root itself is not a selectable child.
    with pytest.raises(Exception):
        _capture(admitted, child_job_ids=[admitted.root.job_id])
    # An empty or duplicated selection is refused.
    with pytest.raises(ValueError):
        _capture(admitted, child_job_ids=[])
    with pytest.raises(ValueError):
        _capture(admitted, child_job_ids=[work.job_id, work.job_id])


def test_capture_refuses_a_superseded_child(admitted):
    finite._complete_work(admitted, 0)
    review, seal = finite._complete_review(admitted, 0, verdict="reject", identity_seed=9451)
    repair = admitted.runtime.jobs.create_cycle_repair(
        admitted.root.job_id, admitted.work(0).job_id, review.job_id,
        command_id=(f"coo-cycle:{admitted.root.job_id}:create-repair:"
                    f"{admitted.work(0).job_id}:{review.job_id}:"
                    f"{seal['role_result_digest']}:1"))
    # The original child is now superseded: it is no longer the current
    # revision of its step, so it is refused.
    with pytest.raises(er.StateConflict, match="superseded"):
        _capture(admitted, child_job_ids=[admitted.work(0).job_id])
    # The repair revision itself is the current child and captures cleanly.
    capture = _capture(admitted, child_job_ids=[repair.job_id])
    assert capture["children"][0]["job_id"] == repair.job_id
    assert capture["children"][0]["repair_round"] == 1
    assert capture["children"][0]["command_id"].endswith(":attempt:1")


def test_capture_refuses_an_ambiguous_or_foreign_root(admitted):
    """The published Control Room owns the root selection; the capture follows it."""

    def ambiguous(document):
        document["autonomy"]["responsibilities"][0]["root_job_ambiguous"] = True

    def foreign_root(document):
        row = document["autonomy"]["responsibilities"][0]
        row["root_job_id"] = "JOB-424242"
        row["root_job_candidates"] = ["JOB-424242"]

    def foreign_work(document):
        document["work"][0]["work_ref"] = "WS:FOREIGN"

    for change in (ambiguous, foreign_root, foreign_work):
        with pytest.raises(Exception):
            _capture(admitted, control_room=change)


def test_capture_refuses_a_revoked_principal_or_disabled_mission(admitted):
    coo, path = _coo_source()
    source = CooInstalledSource(
        lambda: copy.deepcopy(coo),
        lambda: ExecutionCapabilityRegistry.load(path, source_root=ROOT))
    owners, clock, cache, document = _control_room(
        admitted.control_room_root, root_job_id=admitted.root.job_id)
    workspace = WorkspaceReadService(cache=cache, runtime=admitted.runtime, authorize=None,
                                     armed={}, runtime_identity={})
    host = CooHostProvider(source, workspace)
    row, fact, authority = source.snapshot(WORK_REF)
    principal = {key: value for key, value in coo["binding"]["binding"].items()
                 if key != "permission_digest"}
    context = PrincipalAdmissionContext(
        row["work_ref"], fact.principal_binding_digest,
        authority.mission_authority_ref, authority.authority_generation_digest)
    # A foreign principal is not the installed one.
    with pytest.raises(ValueError):
        host.capture_selected_child_target(
            principal={**principal, "client_ref": "someone-else"}, context=context,
            work_ref=WORK_REF, root_job_id=admitted.root.job_id,
            child_job_ids=[admitted.work(0).job_id])
    # A foreign authority context is refused before any read.
    with pytest.raises(ValueError):
        host.capture_selected_child_target(
            principal=principal,
            context=dataclasses.replace(context, mission_authority_ref="authority:foreign"),
            work_ref=WORK_REF, root_job_id=admitted.root.job_id,
            child_job_ids=[admitted.work(0).job_id])


def test_capture_dispatches_no_job_and_mutates_no_runtime_row(admitted, monkeypatch):
    from control_plane import executive_coo_cycle

    def forbidden(self, *args, **kwargs):
        raise AssertionError("the capture must never run a CooCycle")

    monkeypatch.setattr(executive_coo_cycle.CooCycle, "run_once", forbidden)
    before = _runtime_snapshot(admitted.runtime)
    capture = _capture(admitted)
    after = _runtime_snapshot(admitted.runtime)
    assert after == before
    work = admitted.work(0)
    assert admitted.runtime.jobs.get_job(work.job_id).attempt_count == 0
    assert admitted.runtime.jobs.get_job(work.job_id).current_attempt_id is None
    assert capture["children"][0]["expected_current_attempt_id"] is None


def test_capture_of_a_child_that_already_claimed_freezes_the_next_ordinal(admitted):
    work = admitted.work(0)
    admitted.runtime.attempts.dispatch_cycle_job(
        work.job_id,
        command_id=f"coo-cycle:{admitted.root.job_id}:dispatch:{work.job_id}:attempt:1",
        worker_id="worker-a")
    capture = _capture(admitted)
    child = capture["children"][0]
    assert child["expected_current_attempt_id"] is not None
    # The intended NEXT Attempt, frozen once from the coherent observation.
    assert child["attempt_ordinal"] == 2
    assert child["command_id"].endswith(":attempt:2")


# --- B. the publication -----------------------------------------------------------


def _coo_block_for(document):
    """A COO block that shares the installed Executive resource and JWKS."""

    from integrations.mastermind_executive_app.coo_binding import BINDING_SCHEMA, COO_SCOPES
    read = document["policies"]["read"]
    policy = dict(read)
    policy["policy_id"] = "executive-coo"
    policy["required_scopes"] = list(COO_SCOPES)
    binding = {
        "schema": BINDING_SCHEMA,
        "enabled": True,
        "binding": {
            "policy_id": "executive-coo",
            "issuer_digest": hashlib.sha256(read["issuer"].encode("utf-8")).hexdigest(),
            "subject_digest": read["allowed_subject_digests"][0],
            "client_ref": "c" * 64,
            "resource": read["resource"],
            "scopes": list(COO_SCOPES),
            "permission_digest": "d" * 64,
        },
    }
    return {"policy": policy, "binding": binding}


def _installed_document(publication=None, *, work_ref=WORK_REF):
    document = component.prior_mcp_document()
    document["executive_mcp_profile"] = "web_ceo_v3"
    coo = _coo_block_for(document)
    coo["missions"] = [dict(
        enabled=True, work_ref=work_ref,
        principal_binding_digest=_digest(coo["binding"]["binding"]),
        mission_authority_ref="authority:coo-test", outcome_ref="outcome:coo-test",
        proof_contract_ref="proof:coo-test", capability_profile_id=PRINCIPAL_PROFILE,
        capability_profile_digest=ExecutionCapabilityRegistry.load(
            ROOT / "config/executive_claude_principal_capabilities.json",
            source_root=ROOT).profiles[PRINCIPAL_PROFILE].profile_digest,
        execution_profiles=["research_only"], allowed_write_paths=[])]
    document["coo"] = coo
    if publication is not None:
        document["selected_child_target"] = publication
    return document


def _publication_host(publication=None, *, work_ref=WORK_REF):
    document = _installed_document(publication, work_ref=work_ref)
    host = component.FakeHost(
        config=json.dumps(document, sort_keys=True).encode("utf-8") + b"\n",
        plist=component.plist_bytes(component.prior_plist_document(release=OLD_RELEASE)))
    # The TARGET release registry is the only source of a mission's
    # capability-profile digest. Here it is the current source, so the
    # derived digest equals the installed one.
    host.capability_registry = (
        ROOT / "config/executive_claude_principal_capabilities.json")
    return host


def _staged_input(tmp_path, publication, name="selected-child-target.json"):
    path = Path(tmp_path) / name
    raw = json.dumps(publication, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8") + b"\n"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def test_publication_installs_the_frozen_target_through_the_incumbent_transaction(
        admitted, tmp_path):
    publication = _publication(_capture(admitted))
    path, digest = _staged_input(tmp_path, publication)
    host = _publication_host()
    planned = m.plan(host, release_sha=NEW_RELEASE, set_public=False,
                     selected_child_input=str(path), selected_child_sha256=digest)
    assert planned["ok"] is True and planned["outcome"] == "PLANNED"
    assert planned["plan"]["selected_child_target"] == {
        "work_ref": publication["work_ref"],
        "root_job_id": publication["root_job_id"],
        "material_digest": publication["material_digest"],
    }
    applied = m.apply(host, release_sha=NEW_RELEASE, set_public=False,
                      plan_sha256=planned["plan_sha256"],
                      selected_child_input=str(path), selected_child_sha256=digest)
    assert applied["ok"] is True and applied["outcome"] == "COMPLETE"
    installed = json.loads(host.config)
    assert installed["selected_child_target"] == publication
    # The unrelated installed fields survive the publication.
    assert installed["coo"] == _installed_document()["coo"]
    assert installed["port"] == 8443
    assert installed["release_sha"] == NEW_RELEASE
    (receipt,) = host.receipts.values()
    assert receipt["selected_child_target"]["material_digest"] == publication["material_digest"]


def test_publication_refuses_an_incomplete_or_unqualified_pair(admitted, tmp_path):
    publication = _publication(_capture(admitted))
    path, digest = _staged_input(tmp_path, publication)
    host = _publication_host()
    # Exactly one coordinate is a refusal, never an absent selection.
    with pytest.raises(m.UpdateRefused) as caught:
        m.plan(host, release_sha=NEW_RELEASE, set_public=False,
               selected_child_input=str(path), selected_child_sha256=None)
    assert caught.value.code == "SELECTED_CHILD_INPUT_INCOMPLETE"
    with pytest.raises(m.UpdateRefused) as caught:
        m.plan(host, release_sha=NEW_RELEASE, set_public=False,
               selected_child_input=None, selected_child_sha256=digest)
    assert caught.value.code == "SELECTED_CHILD_INPUT_INCOMPLETE"
    # A digest that does not match the bytes is refused.
    with pytest.raises(m.UpdateRefused) as caught:
        m.plan(host, release_sha=NEW_RELEASE, set_public=False,
               selected_child_input=str(path), selected_child_sha256="0" * 64)
    assert caught.value.code == "SELECTED_CHILD_INPUT_DIGEST_MISMATCH"
    # Content that is not a closed publication is refused.
    bad = Path(tmp_path) / "bad.json"
    raw = json.dumps({"schema": "other", "children": []}).encode("utf-8")
    bad.write_bytes(raw)
    with pytest.raises(m.UpdateRefused) as caught:
        m.plan(host, release_sha=NEW_RELEASE, set_public=False,
               selected_child_input=str(bad),
               selected_child_sha256=hashlib.sha256(raw).hexdigest())
    assert caught.value.code == "SELECTED_CHILD_INPUT_INVALID"
    assert host.log == []


def test_publication_refuses_a_target_without_the_exact_installed_mission(admitted, tmp_path):
    publication = _publication(_capture(admitted))
    path, digest = _staged_input(tmp_path, publication)
    # The installed document carries a different mission scope.
    document = _installed_document()
    document["coo"]["missions"][0]["work_ref"] = "WS:OTHER-SCOPE"
    host = component.FakeHost(
        config=json.dumps(document, sort_keys=True).encode("utf-8") + b"\n",
        plist=component.plist_bytes(component.prior_plist_document(release=OLD_RELEASE)))
    host.capability_registry = (
        ROOT / "config/executive_claude_principal_capabilities.json")
    with pytest.raises(m.UpdateRefused) as caught:
        m.plan(host, release_sha=NEW_RELEASE, set_public=False,
               selected_child_input=str(path), selected_child_sha256=digest)
    assert "CANDIDATE_REFUSED" in caught.value.code
    assert host.log == []


def test_publication_never_recomputes_the_ordinal_after_the_claim_advances(
        admitted, tmp_path):
    publication = _publication(_capture(admitted))
    assert publication["children"][0]["attempt_ordinal"] == 1
    path, digest = _staged_input(tmp_path, publication)
    # The original child claims its Attempt and the Runtime advances.
    work = admitted.work(0)
    admitted.runtime.attempts.dispatch_cycle_job(
        work.job_id,
        command_id=f"coo-cycle:{admitted.root.job_id}:dispatch:{work.job_id}:attempt:1",
        worker_id="worker-a")
    assert admitted.runtime.jobs.get_job(work.job_id).attempt_count == 1
    # The publication and its reload still carry the FROZEN ordinal.
    host = _publication_host()
    planned = m.plan(host, release_sha=NEW_RELEASE, set_public=False,
                     selected_child_input=str(path), selected_child_sha256=digest)
    m.apply(host, release_sha=NEW_RELEASE, set_public=False,
            plan_sha256=planned["plan_sha256"],
            selected_child_input=str(path), selected_child_sha256=digest)
    installed = json.loads(host.config)["selected_child_target"]
    assert installed["children"][0]["attempt_ordinal"] == 1
    assert installed["children"][0]["command_id"].endswith(":attempt:1")
    assert installed["children"][0]["expected_current_attempt_id"] is None
    assert installed["material_digest"] == publication["material_digest"]


def test_reconcile_recovers_the_original_captured_candidate_and_never_a_new_input(
        admitted, tmp_path):
    publication = _publication(_capture(admitted))
    path, digest = _staged_input(tmp_path, publication)
    host = _publication_host()
    planned = m.plan(host, release_sha=NEW_RELEASE, set_public=False,
                     selected_child_input=str(path), selected_child_sha256=digest)
    # The transaction is interrupted after the recorded stop, before the
    # installed configuration was replaced.
    host.fail_at[("replace", 1)] = OSError("rename failed")
    with pytest.raises(m.TransactionEffectUnknown):
        m.apply(host, release_sha=NEW_RELEASE, set_public=False,
                plan_sha256=planned["plan_sha256"],
                selected_child_input=str(path), selected_child_sha256=digest)
    host.fail_at.clear()
    assert host.state == "ABSENT"
    assert host.marker is not None
    assert host.marker["selected_child_target"] == publication
    reads_before = host.events.count("read_selected_child_input")
    # A reconciliation takes NO replacement input.
    reconciled = m.reconcile(host, release_sha=NEW_RELEASE)
    assert reconciled["ok"] is True and reconciled["outcome"] == "COMPLETE"
    assert host.events.count("read_selected_child_input") == reads_before
    assert json.loads(host.config)["selected_child_target"] == publication
    assert host.count("stop_service") == 1 and host.count("start_service") == 1


def test_the_capability_profile_digest_is_re_derived_from_the_target_release_registry(
        admitted, tmp_path):
    """A legitimate tool-projection change moves the mission's digest with it.

    The replacement comes from the TARGET sealed release registry, never
    from a hand-authored grant and never from the prior six-tool digest.
    Every other mission field, action and binding is preserved.
    """

    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    publication = _publication(_capture(admitted))
    document = _installed_document(publication)
    prior_mission = document["coo"]["missions"][0]
    # The target release carries a changed COO tool projection, so its
    # sealed registry declares a different tool-schema digest.
    release_root = tmp_path / "release" / NEW_RELEASE
    (release_root / "config").mkdir(parents=True)
    registry = json.loads(
        (ROOT / "config/executive_claude_principal_capabilities.json").read_text())
    registry["mcp_servers"]["mastermind-executive-coo-v1"]["tool_schema_digest"] = "f" * 64
    registry_path = release_root / "config" / "executive_claude_principal_capabilities.json"
    registry_path.write_text(json.dumps(registry))
    expected = ExecutionCapabilityRegistry.load(
        registry_path, source_root=release_root).profiles[PRINCIPAL_PROFILE].profile_digest
    assert expected != prior_mission["capability_profile_digest"]
    host = _publication_host(publication)
    host.capability_registry = registry_path
    planned = m.plan(host, release_sha=NEW_RELEASE, set_public=False)
    assert planned["ok"] is True
    applied = m.apply(host, release_sha=NEW_RELEASE, set_public=False,
                      plan_sha256=planned["plan_sha256"])
    assert applied["ok"] is True
    installed = json.loads(host.config)
    mission = installed["coo"]["missions"][0]
    assert mission["capability_profile_digest"] == expected
    # Every other mission field, action and binding is preserved exactly.
    for key, value in prior_mission.items():
        if key == "capability_profile_digest":
            continue
        assert mission[key] == value
    assert installed["coo"]["policy"] == document["coo"]["policy"]
    assert installed["coo"]["binding"] == document["coo"]["binding"]
    # The publication itself is untouched by the digest re-derivation.
    assert installed["selected_child_target"] == publication


def test_a_source_only_release_update_carries_the_installed_publication_forward(
        admitted, tmp_path):
    publication = _publication(_capture(admitted))
    path, digest = _staged_input(tmp_path, publication)
    host = _publication_host(publication)
    # The publication is installed first.
    planned = m.plan(host, release_sha=NEW_RELEASE, set_public=False,
                     selected_child_input=str(path), selected_child_sha256=digest)
    m.apply(host, release_sha=NEW_RELEASE, set_public=False,
            plan_sha256=planned["plan_sha256"],
            selected_child_input=str(path), selected_child_sha256=digest)
    installed = json.loads(host.config)
    assert installed["selected_child_target"] == publication
    # A later source-only release update carries the publication forward
    # byte for byte and never withdraws it.
    host.config = json.dumps(installed, sort_keys=True).encode("utf-8") + b"\n"
    host.running = host.config
    host.plist = component.plist_bytes(component.prior_plist_document(release=NEW_RELEASE))
    later = m.plan(host, release_sha="d" * 40, set_public=False)
    assert later["ok"] is True
    # The operator still sees the exact publication identity the release
    # update carries forward.
    assert later["plan"]["selected_child_target"] == {
        "work_ref": publication["work_ref"],
        "root_job_id": publication["root_job_id"],
        "material_digest": publication["material_digest"],
    }
    applied = m.apply(host, release_sha="d" * 40, set_public=False,
                      plan_sha256=later["plan_sha256"])
    assert applied["ok"] is True
    assert json.loads(host.config)["selected_child_target"] == publication


def test_a_marker_without_the_optional_publication_still_validates(admitted, tmp_path):
    """Old markers keep their exact shape: the publication key is optional."""

    host = _publication_host()
    marker = {
        "schema": m.MARKER_SCHEMA, "plan_sha256": "a" * 64,
        "release_sha": NEW_RELEASE, "prior_release_sha": OLD_RELEASE,
        "set_public_mcp_resource": False, "phase": "INTENT", "dispatched": [],
        "config_before_sha256": "b" * 64, "config_after_sha256": "c" * 64,
        "plist_before_sha256": "d" * 64, "plist_after_sha256": "e" * 64,
        "manifest_sha256": "f" * 64, "closure_sha256": "0" * 64,
        "started_at": "2026-10-25T00:00:00Z", "last_verify": [],
    }
    m._validate_marker(marker)
    marker["selected_child_target"] = None
    m._validate_marker(marker)
    marker["selected_child_target"] = {"schema": "other"}
    with pytest.raises(m.TransactionEffectUnknown) as caught:
        m._validate_marker(marker)
    assert caught.value.code == "MARKER_MALFORMED"


def test_service_control_accepts_only_the_paired_selected_child_target_input(tmp_path):
    """The closed CLI carries exactly one paired publication input."""

    if os.geteuid() == 0:
        # The disposable controller harness refuses a root process ("service
        # lifecycle changes require root"); this proof runs in the ordinary
        # non-root suite, exactly like the incumbent component-verb proofs.
        pytest.skip("the disposable service-control harness requires a non-root process")
    path = "/var/lib/mastermind-executive/selected-child.json"
    digest = "a" * 64
    sha = service_control.COMPONENT_SHA

    def run(name, verb, args):
        # Each case gets its own disposable controller so the recorded argv
        # of one case is never the argv of another.
        case = tmp_path / name
        case.mkdir(parents=True, exist_ok=True)
        return service_control._component_run(case, verb, args)

    result, argv, _ = run(
        "paired", "plan-mcp-component",
        ("--expected-sha", sha,
         "--selected-child-target-input", path,
         "--selected-child-target-sha256", digest))
    assert result[0] == 0, result[2]
    assert argv[-4:] == ["--selected-child-target-input", path,
                         "--selected-child-target-sha256", digest]
    # Exactly one coordinate is a refusal, never an absent selection.
    for index, extra in enumerate((("--selected-child-target-input", path),
                                   ("--selected-child-target-sha256", digest))):
        result, argv, _ = run(
            f"half{index}", "plan-mcp-component", ("--expected-sha", sha, *extra))
        assert result[0] == 64
        assert argv is None
    # A reconciliation never carries the selection.
    result, argv, _ = run(
        "reconcile", "reconcile-mcp-component",
        ("--expected-sha", sha,
         "--selected-child-target-input", path,
         "--selected-child-target-sha256", digest))
    assert result[0] == 64
    assert argv is None
    # An arbitrary destination, label, account, port or authority boolean is
    # still refused.
    for index, extra in enumerate((("--output", "/tmp/x"), ("--account", "x"),
                                   ("--port", "1"), ("--armed", "true"))):
        result, argv, _ = run(
            f"open{index}", "plan-mcp-component", ("--expected-sha", sha, *extra))
        assert result[0] == 64
        assert argv is None


# --- C. the installed consumers ---------------------------------------------------


def _sealed_installation(document, name="release"):
    """A root-owned sealed installation; the privileged ownership seam."""

    if os.geteuid() != 0:
        pytest.skip("the sealed installation requires root ownership")
    SEALED_BASE.mkdir(parents=True, exist_ok=True)
    os.chmod(SEALED_BASE, 0o755)
    source = SEALED_BASE / f"{document['release_sha']}"
    if source.exists():
        shutil.rmtree(source)
    (source / "config").mkdir(parents=True)
    os.chmod(source, 0o755)
    os.chmod(source / "config", 0o755)
    config = source / "config" / "executive-mcp.json"
    config.write_text(json.dumps(document, sort_keys=True) + "\n")
    os.chmod(config, 0o644)
    return source, config


def test_absent_target_preserves_the_legacy_installed_construction():
    """An absent publication keeps the legacy COO settings exactly as before."""

    from integrations.mastermind_executive_app.coo import CooAppSettings
    document = _installed_document()
    assert entry.validate_document(document) == document
    assert entry.build_installed_selected_child_target(document) is None
    # The App settings still carry the target field, and an absent
    # publication leaves it UNBOUND.  This is the legacy construction.
    assert "selected_child_target" in {
        field.name for field in dataclasses.fields(CooAppSettings)}
    source, config = _sealed_installation(document)
    try:
        installed = CooInstalledSource.from_path(config, source, expected_uid=os.geteuid())
        assert installed.selected_child_target() is None
    finally:
        shutil.rmtree(source, ignore_errors=True)


def test_installed_app_and_control_inject_the_same_frozen_target(admitted, target_owner):
    publication = _publication(_capture(admitted))
    document = _installed_document(publication)
    # The installed document validates the closed publication against its
    # exact installed COO mission.
    assert entry.validate_document(document) == document
    assert entry.build_installed_selected_child_target(document) == publication
    # The target's OWN material digest equals the published digest.
    target = entry.build_selected_child_target(publication, lambda: None)
    assert target.material_digest() == publication["material_digest"]
    assert target.work_ref == publication["work_ref"]
    child = target.children[0]
    assert child.selection.job_id == publication["children"][0]["job_id"]
    assert child.attempt_ordinal == publication["children"][0]["attempt_ordinal"]
    assert child.command_id == publication["children"][0]["command_id"]
    # The same frozen command is reachable by its exact command id.
    assert target.child_for(child.command_id) is child
    assert target.child_for("coo-cycle:other") is None


def test_the_control_reader_serves_the_same_frozen_target(admitted, target_owner):
    publication = _publication(_capture(admitted))
    document = _installed_document(publication)
    source, config = _sealed_installation(document)
    try:
        installed = CooInstalledSource.from_path(config, source, expected_uid=os.geteuid())
        target = installed.selected_child_target()
        assert target is not None
        assert target.material_digest() == publication["material_digest"]
        assert target.children[0].command_id == publication["children"][0]["command_id"]
        # A second read returns the SAME frozen target.
        assert installed.selected_child_target() is target
    finally:
        shutil.rmtree(source, ignore_errors=True)


def test_the_sealed_reader_refuses_a_replaced_publication(admitted, target_owner):
    publication = _publication(_capture(admitted))
    document = _installed_document(publication)
    source, config = _sealed_installation(document)
    try:
        installed = CooInstalledSource.from_path(config, source, expected_uid=os.geteuid())
        target = installed.selected_child_target()
        assert target is not None
        # A replacement publication is refused by the fixed reader.
        replacement = copy.deepcopy(document)
        replacement["selected_child_target"]["children"][0]["attempt_ordinal"] = 9
        replacement["selected_child_target"]["children"][0]["command_id"] = (
            f"coo-cycle:{replacement['selected_child_target']['root_job_id']}:dispatch:"
            f"{replacement['selected_child_target']['children'][0]['job_id']}:attempt:9")
        replacement["selected_child_target"]["material_digest"] = (
            selected_child_material_digest(selected_child_material(
                replacement["selected_child_target"]["work_ref"],
                replacement["selected_child_target"]["children"])))
        config.write_text(json.dumps(replacement, sort_keys=True) + "\n")
        os.chmod(config, 0o644)
        with pytest.raises(ValueError):
            installed.selected_child_target()
    finally:
        shutil.rmtree(source, ignore_errors=True)


def test_the_sealed_reader_refuses_a_symlinked_or_multilinked_publication(admitted, target_owner):
    publication = _publication(_capture(admitted))
    document = _installed_document(publication)
    source, config = _sealed_installation(document)
    try:
        installed = CooInstalledSource.from_path(config, source, expected_uid=os.geteuid())
        assert installed.selected_child_target() is not None
        # A second link on the installed document is a custody failure.
        os.link(config, config.parent / "second-link.json")
        try:
            with pytest.raises(ValueError):
                installed.selected_child_target()
        finally:
            (config.parent / "second-link.json").unlink()
        # A symlinked document is refused by the sealed path check.
        moved = config.parent / "moved.json"
        config.rename(moved)
        os.symlink(moved, config)
        try:
            with pytest.raises(ValueError):
                installed.selected_child_target()
        finally:
            config.unlink()
            moved.rename(config)
    finally:
        shutil.rmtree(source, ignore_errors=True)


def test_the_preparation_hook_writes_the_exact_publication_and_reads_it_back(admitted):
    publication = _publication(_capture(admitted))
    host, principal, context, _ = _host(admitted)
    if os.geteuid() != 0:
        pytest.skip("the publication input must be a root-owned object")
    SEALED_BASE.mkdir(parents=True, exist_ok=True)
    os.chmod(SEALED_BASE, 0o755)
    destination = SEALED_BASE / f"selected-child-{os.getpid()}.json"
    try:
        result = prepare_selected_child_target(
            host, principal=principal, context=context, work_ref=WORK_REF,
            root_job_id=admitted.root.job_id,
            child_job_ids=[admitted.work(0).job_id], destination=destination)
        assert result["publication"] == publication
        raw = destination.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == result["sha256"]
        assert json.loads(raw) == publication
        info = destination.lstat()
        assert stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_gid == 0
        assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
        # The hook never overwrites an existing file.
        with pytest.raises(ValueError):
            prepare_selected_child_target(
                host, principal=principal, context=context, work_ref=WORK_REF,
                root_job_id=admitted.root.job_id,
                child_job_ids=[admitted.work(0).job_id], destination=destination)
    finally:
        if destination.exists():
            destination.unlink()


# --- D. original status versus fresh admission ------------------------------------


def test_mandate_closure_blocks_fresh_admission_but_keeps_the_original_read(admitted, target_owner):
    publication = _publication(_capture(admitted))
    host, principal, context, _ = _host(admitted)
    # The currentness guard of the frozen target never calls the dialogue
    # guard, so the original command stays readable after the mandate closed.
    target = entry.build_selected_child_target(publication, lambda: None)
    target.require_current()
    # The fresh-admission guard refuses while the new-effect mandate is closed.
    with pytest.raises(ValueError):
        host.guard_dialogue(
            context=context, root_job_id=admitted.root.job_id,
            capability_profile_digest=host.source.snapshot(WORK_REF)[2].capability_profile_digest)
    # The frozen target still carries its exact original command.
    assert target.children[0].command_id == publication["children"][0]["command_id"]
    assert target.material_digest() == publication["material_digest"]


def test_a_revoked_read_principal_still_refuses(admitted):
    host, principal, context, _ = _host(admitted)
    coo, path = _coo_source()
    revoked = copy.deepcopy(coo)
    revoked["binding"]["binding"]["client_ref"] = "rotated-client"
    source = CooInstalledSource(
        lambda: copy.deepcopy(revoked),
        lambda: ExecutionCapabilityRegistry.load(path, source_root=ROOT))
    with pytest.raises(ValueError):
        source.for_principal(principal, WORK_REF)


# --- E. the Workspace bracket around the capture ---------------------------------
#
# The capture observes the Runtime between TWO published Control Room
# snapshots.  A missing, unqualified or changing Workspace source refuses
# the capture even when the COO row itself is unchanged, so a CCR
# responsibility or root publication change can never freeze an old root.


class _BoundaryRuntime:
    """The real Runtime behind an observation that changes the source.

    The change lands INSIDE the observation window: after the first
    published snapshot and before the second one.
    """

    def __init__(self, runtime, mutate):
        self._runtime = runtime
        self._mutate = mutate

    def observe_bounded_read(self):
        runtime, mutate = self._runtime, self._mutate

        @contextlib.contextmanager
        def observation():
            with runtime.observe_bounded_read() as inner:
                mutate()
                yield inner
        return observation()


def _capture_with_boundary(admitted, mutate):
    """The production capture over a source that changes at the boundary."""

    coo, path = _coo_source()
    source = CooInstalledSource(
        lambda: copy.deepcopy(coo),
        lambda: ExecutionCapabilityRegistry.load(path, source_root=ROOT))
    owners, clock, cache, document = _control_room(
        admitted.control_room_root, root_job_id=admitted.root.job_id)
    workspace = WorkspaceReadService(
        cache=cache, runtime=admitted.runtime, authorize=None, armed={},
        runtime_identity={}, bounded_runtime=_BoundaryRuntime(admitted.runtime, mutate))
    host = CooHostProvider(source, workspace)
    row, fact, authority = source.snapshot(WORK_REF)
    principal = {key: value for key, value in coo["binding"]["binding"].items()
                 if key != "permission_digest"}
    context = PrincipalAdmissionContext(
        row["work_ref"], fact.principal_binding_digest,
        authority.mission_authority_ref, authority.authority_generation_digest)
    return host.capture_selected_child_target(
        principal=principal, context=context, work_ref=WORK_REF,
        root_job_id=admitted.root.job_id, child_job_ids=[admitted.work(0).job_id])


def test_a_stable_workspace_source_freezes_every_material_field_once(admitted):
    """The stable source brackets the capture and freezes the ten fields."""

    capture = _capture(admitted)
    child = capture["children"][0]
    material = ("command_id", "attempt_ordinal", "root_job_id", "parent_job_id",
                "job_id", "plan_attempt_id", "plan_digest", "plan_step_id",
                "repair_round", "expected_current_attempt_id")
    assert len(material) == 10
    for field in material:
        assert field in child
    assert capture["source"]["observation_state"] in {"SAME", "UNKNOWN"}
    assert capture["source"]["plan_attempt_id"] == child["plan_attempt_id"]
    # The frozen coordinates are stable: a second capture of the same
    # unchanged source produces exactly the same material.
    again = _capture(admitted)
    assert again["children"] == capture["children"]
    assert again["source"] == capture["source"]


def test_a_changed_root_selection_at_the_boundary_refuses(admitted):
    def change(document_holder):
        pass
    # The published responsibility row names a different root inside the
    # observation window.
    def mutate():
        owners[0].state_cache["doc"]["autonomy"]["responsibilities"][0]["root_job_id"] = "JOB-424242"
        owners[0].state_cache["doc"]["autonomy"]["responsibilities"][0]["root_job_candidates"] = ["JOB-424242"]
    coo, path = _coo_source()
    source = CooInstalledSource(
        lambda: copy.deepcopy(coo),
        lambda: ExecutionCapabilityRegistry.load(path, source_root=ROOT))
    owners, clock, cache, document = _control_room(
        admitted.control_room_root, root_job_id=admitted.root.job_id)
    workspace = WorkspaceReadService(
        cache=cache, runtime=admitted.runtime, authorize=None, armed={},
        runtime_identity={}, bounded_runtime=_BoundaryRuntime(admitted.runtime, mutate))
    host = CooHostProvider(source, workspace)
    row, fact, authority = source.snapshot(WORK_REF)
    principal = {key: value for key, value in coo["binding"]["binding"].items()
                 if key != "permission_digest"}
    context = PrincipalAdmissionContext(
        row["work_ref"], fact.principal_binding_digest,
        authority.mission_authority_ref, authority.authority_generation_digest)
    with pytest.raises(Exception):
        host.capture_selected_child_target(
            principal=principal, context=context, work_ref=WORK_REF,
            root_job_id=admitted.root.job_id, child_job_ids=[admitted.work(0).job_id])


@pytest.mark.parametrize("change", ["publication", "owner", "document", "unqualified"])
def test_a_changing_workspace_source_refuses_the_capture(admitted, change):
    coo, path = _coo_source()
    source = CooInstalledSource(
        lambda: copy.deepcopy(coo),
        lambda: ExecutionCapabilityRegistry.load(path, source_root=ROOT))
    owners, clock, cache, document = _control_room(
        admitted.control_room_root, root_job_id=admitted.root.job_id)

    def mutate():
        if change == "publication":
            owners[0].state_published_seq += 1
        elif change == "owner":
            replacement, _clock, _cache, _doc = _control_room(
                admitted.control_room_root, root_job_id=admitted.root.job_id)
            owners[0] = replacement[0]
        elif change == "document":
            owners[0].state_cache["doc"]["work"][0]["agent_os"]["title"] = "Changed"
        else:
            owners[0].state_refresh_error = "private failure"

    workspace = WorkspaceReadService(
        cache=cache, runtime=admitted.runtime, authorize=None, armed={},
        runtime_identity={}, bounded_runtime=_BoundaryRuntime(admitted.runtime, mutate))
    host = CooHostProvider(source, workspace)
    row, fact, authority = source.snapshot(WORK_REF)
    principal = {key: value for key, value in coo["binding"]["binding"].items()
                 if key != "permission_digest"}
    context = PrincipalAdmissionContext(
        row["work_ref"], fact.principal_binding_digest,
        authority.mission_authority_ref, authority.authority_generation_digest)
    with pytest.raises(Exception):
        host.capture_selected_child_target(
            principal=principal, context=context, work_ref=WORK_REF,
            root_job_id=admitted.root.job_id, child_job_ids=[admitted.work(0).job_id])


def test_a_changed_mission_association_at_the_boundary_refuses(admitted):
    """The mission/root association is proven before AND after the capture."""

    host, principal, context, _ = _host(admitted)
    reads = {"count": 0}
    original = host.workspace.read_mission_for_work_ref

    def read(work_ref):
        reads["count"] += 1
        if reads["count"] == 1:
            return original(work_ref)
        mission = copy.deepcopy(original(work_ref))
        mission["mission"]["root_job_id"] = "JOB-424242"
        return mission

    host.workspace.read_mission_for_work_ref = read
    with pytest.raises(ValueError, match="mission"):
        host.capture_selected_child_target(
            principal=principal, context=context, work_ref=WORK_REF,
            root_job_id=admitted.root.job_id, child_job_ids=[admitted.work(0).job_id])
    assert reads["count"] == 2


# --- F. the shared generation-bound target reader -------------------------------


def _unsealed_installation(document, base):
    """The same installation without the privileged ownership seam.

    Only the ROOT-OWNERSHIP assertion is unavailable to an ordinary
    process.  Every other check of the sealed reader - the path identity,
    the descriptor custody, the generation and the content - still runs.
    """

    source = Path(base) / document["release_sha"]
    (source / "config").mkdir(parents=True, exist_ok=True)
    config = source / "config" / "executive-mcp.json"
    config.write_text(json.dumps(document, sort_keys=True) + "\n")
    return source, config


@pytest.fixture
def unsealed(monkeypatch):
    """A sealed installation whose ROOT OWNERSHIP seam is unavailable here.

    Only the ROOT OWNERSHIP assertion is relaxed.  Every other law of the
    incumbent sealed path - the symlink refusal, the type refusal, the
    single-link refusal and the group/other write refusal - still runs.
    """

    def sealed_without_root(path, *, directory=False):
        for node in (Path(path), *Path(path).parents):
            info = node.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_mode & 0o022:
                raise ValueError('sealed path ownership or permissions differ')
            is_dir = node != Path(path) or directory
            if not (stat.S_ISDIR(info.st_mode) if is_dir else stat.S_ISREG(info.st_mode)):
                raise ValueError('sealed path type differs')
            if not is_dir and info.st_nlink != 1:
                raise ValueError('sealed configuration must have one link')

    # A sealed tree cannot descend from pytest's ordinary writable /tmp.
    # Validate the canonical home ancestry before creating this disposable
    # private tree; do not relax any symlink, type, link-count or mode check.
    parent = Path.home().resolve(strict=True)
    sealed_without_root(parent, directory=True)
    monkeypatch.setattr(entry, "require_sealed_path", sealed_without_root)
    with tempfile.TemporaryDirectory(prefix="mmx-selected-child-test-", dir=parent) as directory:
        base = Path(directory).resolve(strict=True)
        sealed_without_root(base, directory=True)
        yield base


def _installed_consumers(document, source, config):
    """The REAL installed App settings and the REAL installed Control source."""

    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import load_app_policies
    installed = CooInstalledSource.from_path(config, source, expected_uid=os.geteuid())
    settings = AppSettings(
        policies=load_app_policies(document["policies"]),
        mastermind_root=source, macro_root_flag=None, environ={},
        ceo_ingress_socket_path=document["ceo_ingress_socket_path"],
        read_from_ceo_ingress=True)
    coo_settings = entry.build_installed_coo_settings(
        document, source, config, settings, expected_uid=os.geteuid())
    return installed, coo_settings


def test_the_app_and_control_installed_consumers_share_one_frozen_generation(
        admitted, target_owner, unsealed):
    """Both installed consumers prove the SAME publication generation."""

    # The joint proof uses the ACTUAL composed C29 class.  A local stand-in
    # is never counted as joint proof.
    assert target_owner is not _LocalSelectedChildTarget
    publication = _publication(_capture(admitted))
    document = _installed_document(publication)
    source, config = _unsealed_installation(document, unsealed)
    installed, coo_settings = _installed_consumers(document, source, config)
    control_target = installed.selected_child_target()
    app_target = coo_settings.selected_child_target
    assert control_target is not None and app_target is not None
    # The same frozen material, command and ordinal identity.
    assert app_target.material_digest() == control_target.material_digest()
    assert app_target.material_digest() == publication["material_digest"]
    assert app_target.work_ref == control_target.work_ref == publication["work_ref"]
    assert (app_target.children[0].command_id
            == control_target.children[0].command_id
            == publication["children"][0]["command_id"])
    assert (app_target.children[0].attempt_ordinal
            == control_target.children[0].attempt_ordinal
            == publication["children"][0]["attempt_ordinal"])
    assert (app_target.children[0].selection.job_id
            == control_target.children[0].selection.job_id)


def test_the_shared_reader_refuses_a_same_byte_replacement(admitted, target_owner, unsealed):
    publication = _publication(_capture(admitted))
    document = _installed_document(publication)
    source, config = _unsealed_installation(document, unsealed)
    installed, coo_settings = _installed_consumers(document, source, config)
    target = installed.selected_child_target()
    assert target is not None
    # A SAME BYTE replacement of the installation is invisible to a
    # rotatable projection loader and must still refuse here.
    replacement = config.parent / "replacement.json"
    replacement.write_text(config.read_text())
    os.replace(replacement, config)
    with pytest.raises(ValueError):
        installed.selected_child_target()
    with pytest.raises(ValueError):
        coo_settings.selected_child_target.require_current()


def test_the_shared_reader_refuses_an_in_place_rewrite(admitted, target_owner, unsealed):
    publication = _publication(_capture(admitted))
    document = _installed_document(publication)
    source, config = _unsealed_installation(document, unsealed)
    installed, coo_settings = _installed_consumers(document, source, config)
    assert installed.selected_child_target() is not None
    # An in-place A -> B -> A rewrite keeps the same bytes and the same
    # inode.  Only the generation proves that it happened.
    original = config.read_bytes()
    with open(config, "r+b") as handle:
        handle.write(b" ")
        handle.flush()
        handle.seek(0)
        handle.truncate()
        handle.write(original)
        handle.flush()
    with pytest.raises(ValueError):
        installed.selected_child_target()


def test_the_shared_reader_refuses_a_relinked_or_symlinked_installation(
        admitted, target_owner, unsealed):
    publication = _publication(_capture(admitted))
    document = _installed_document(publication)
    source, config = _unsealed_installation(document, unsealed)
    installed, _coo_settings = _installed_consumers(document, source, config)
    assert installed.selected_child_target() is not None
    link = config.parent / "second-link.json"
    os.link(config, link)
    try:
        with pytest.raises(ValueError):
            installed.selected_child_target()
    finally:
        link.unlink()
    moved = config.parent / "moved.json"
    config.rename(moved)
    os.symlink(moved, config)
    try:
        with pytest.raises(ValueError):
            installed.selected_child_target()
    finally:
        config.unlink()
        moved.rename(config)


def test_the_shared_reader_refuses_a_forked_process(admitted, target_owner, unsealed, monkeypatch):
    publication = _publication(_capture(admitted))
    document = _installed_document(publication)
    source, config = _unsealed_installation(document, unsealed)
    installed, _coo_settings = _installed_consumers(document, source, config)
    assert installed.selected_child_target() is not None
    # A forked child is a different process and never inherits the
    # generation of its parent.
    forked = os.getpid() + 1
    monkeypatch.setattr(entry.os, "getpid", lambda: forked)
    with pytest.raises(ValueError):
        installed.selected_child_target()


def test_a_new_qualified_construction_binds_the_new_generation(
        admitted, target_owner, unsealed):
    publication = _publication(_capture(admitted))
    document = _installed_document(publication)
    source, config = _unsealed_installation(document, unsealed)
    installed, _coo_settings = _installed_consumers(document, source, config)
    assert installed.selected_child_target() is not None
    replacement = config.parent / "replacement.json"
    replacement.write_text(config.read_text())
    os.replace(replacement, config)
    with pytest.raises(ValueError):
        installed.selected_child_target()
    # A NEW qualified construction binds the new generation.
    fresh = CooInstalledSource.from_path(config, source, expected_uid=os.geteuid())
    assert fresh.selected_child_target() is not None


def test_a_revoked_read_principal_refuses_the_shared_reader(
        admitted, target_owner, unsealed):
    publication = _publication(_capture(admitted))
    document = _installed_document(publication)
    source, config = _unsealed_installation(document, unsealed)
    installed, _coo_settings = _installed_consumers(document, source, config)
    assert installed.selected_child_target() is not None
    # The installed read principal is revoked: the installation changed.
    revoked = copy.deepcopy(document)
    revoked["coo"]["binding"]["binding"]["client_ref"] = "rotated-client"
    config.write_text(json.dumps(revoked, sort_keys=True) + "\n")
    with pytest.raises(ValueError):
        installed.selected_child_target()
