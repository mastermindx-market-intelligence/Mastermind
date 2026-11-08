"""Installed COO facts and final guard; no new store, token or runtime owner.

Delegations are explicit root-published data in the existing Executive MCP
installation. Workspace retains mission/currentness ownership. This capability
admits bounded Jobs only; it grants no direct source release or deployment.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from pathlib import PurePosixPath

from common.executive_workspace_contract import canonical, _check_job_id, _check_work_ref
from control_plane import ceo_intent, ceo_request
from control_plane.coo_principal_envelope import (
    PrincipalAdmissionContext,
    validate_principal_orchestration_bundle,
)
from control_plane.coo_principal_mandate import (
    DEFAULT_PRINCIPAL_ACTIONS,
    PRINCIPAL_ACTIONS,
    AuthorityFact,
    PrincipalFact,
    ReleaseClass,
    project_coo_principal_mandate,
)

FACT_SCHEMA = "mastermind.ceo_ingress.principal_facts.v1"
#: The closed, explicitly tagged PREPARATION variant of the existing mission
#: fact request.  It is the SAME closed four-key frame with ONE extra tag
#: block, so the Control's own admission-arming gate (which applies to
#: ``operation == "mission"``) still governs it without any edit to the
#: Executive Service.  It is not a new operation and it is not unguarded:
#: the App peer, the exact provider, the ready service, the owned Runtime
#: and the owned bounded task are all still required by the incumbent
#: handler.
FACT_PREPARATION_SCHEMA = "mastermind.ceo_ingress.selected_child_preparation.v1"
FACT_FRAME_KEYS = frozenset({"schema", "operation", "work_ref", "principal"})
FACT_PREPARATION_FRAME_KEYS = FACT_FRAME_KEYS | {"preparation"}
FACT_PREPARATION_KEYS = frozenset({"schema", "root_job_id", "child_job_ids"})
MAX_FACT_SELECTED_CHILDREN = 16
MISSION_AUTHORITY_VERSION = 2
MISSION_KEYS_V1 = frozenset({"enabled", "work_ref", "principal_binding_digest",
    "mission_authority_ref", "outcome_ref", "proof_contract_ref",
    "capability_profile_id", "capability_profile_digest",
    "execution_profiles", "allowed_write_paths"})
MISSION_KEYS_V2 = MISSION_KEYS_V1 | frozenset({"authority_version", "principal_actions"})
MISSION_KEYS = MISSION_KEYS_V1

# --- the frozen selected-child target -------------------------------------------
#
# One trusted host freezes a bounded set of already admitted child Jobs for
# one work scope. The frozen coordinates and the frozen Attempt ordinal are
# captured ONCE from the canonical Runtime, published as one closed
# non-secret projection, and reloaded by both installed consumers. Nothing
# here recomputes an ordinal, selects a replacement child, or derives a
# child from a model argument.

SELECTED_CHILD_TARGET_SCHEMA = "mastermind.executive.selected_child_target.v1"
SELECTED_CHILD_SOURCE_SCHEMA = "mastermind.executive.selected_child_source.v1"
MAX_SELECTED_CHILDREN = 16

SELECTED_CHILD_KEYS = frozenset({
    "command_id", "attempt_ordinal", "root_job_id", "parent_job_id", "job_id",
    "plan_attempt_id", "plan_digest", "plan_step_id", "repair_round",
    "expected_current_attempt_id",
})
SELECTED_CHILD_TARGET_KEYS = frozenset({
    "schema", "work_ref", "root_job_id", "children", "material_digest", "source",
})
SELECTED_CHILD_SOURCE_KEYS = frozenset({
    "schema", "plan_attempt_id", "plan_digest", "policy_sha", "reservation_digest",
    "observation_state", "observation_source_identity",
})
_HEX64 = re.compile(r"[0-9a-f]{64}")


def selected_child_command_id(root_job_id, job_id, attempt_ordinal):
    """The incumbent deterministic coo-cycle dispatch command for one child."""

    return f"coo-cycle:{root_job_id}:dispatch:{job_id}:attempt:{attempt_ordinal}"


def selected_child_material(work_ref, children):
    """The canonical material of one frozen selected-child set.

    This is byte-for-byte the payload the selected-child target's own
    material digest is computed over: the work reference and, for every
    child, its deterministic dispatch command, its frozen Attempt ordinal
    and every ExecutiveChildSelection coordinate. The callable currentness
    guard is deliberately excluded -- it proves currentness, not identity.
    """

    return {
        "work_ref": work_ref,
        "children": [
            {
                "command_id": child["command_id"],
                "attempt_ordinal": child["attempt_ordinal"],
                "root_job_id": child["root_job_id"],
                "parent_job_id": child["parent_job_id"],
                "job_id": child["job_id"],
                "plan_attempt_id": child["plan_attempt_id"],
                "plan_digest": child["plan_digest"],
                "plan_step_id": child["plan_step_id"],
                "repair_round": child["repair_round"],
                "expected_current_attempt_id": child["expected_current_attempt_id"],
            }
            for child in children
        ],
    }


def selected_child_material_digest(material):
    """The deterministic digest of one canonical selected-child material."""

    return hashlib.sha256(canonical(material)).hexdigest()


def validate_selected_child_target(raw):
    """Validate one closed published selected-child target projection.

    Absence preserves every existing installed document. A present
    projection must carry the exact frozen coordinates, the deterministic
    command identity of every child, and the material digest over exactly
    those coordinates. The source block is bounded provenance: its hashes
    are equality and provenance checks, never independent admission tokens.
    """

    if type(raw) is not dict or set(raw) != SELECTED_CHILD_TARGET_KEYS:
        _refuse()
    if raw["schema"] != SELECTED_CHILD_TARGET_SCHEMA:
        _refuse()
    if not _check_work_ref(raw["work_ref"]) or not _check_job_id(raw["root_job_id"]):
        _refuse()
    children = raw["children"]
    if type(children) is not list or not 1 <= len(children) <= MAX_SELECTED_CHILDREN:
        _refuse()
    commands = set()
    for child in children:
        if type(child) is not dict or set(child) != SELECTED_CHILD_KEYS:
            _refuse()
        if child["root_job_id"] != raw["root_job_id"]:
            _refuse()
        if child["parent_job_id"] != child["root_job_id"]:
            _refuse()
        if not _check_job_id(child["job_id"]):
            _refuse()
        for key in ("plan_attempt_id", "plan_digest", "plan_step_id"):
            if type(child[key]) is not str or not 0 < len(child[key]) <= 128:
                _refuse()
        if type(child["repair_round"]) is not int or child["repair_round"] not in {0, 1, 2}:
            _refuse()
        if type(child["attempt_ordinal"]) is not int or child["attempt_ordinal"] < 1:
            _refuse()
        expected = child["expected_current_attempt_id"]
        if expected is not None and (type(expected) is not str
                                     or not 0 < len(expected) <= 128):
            _refuse()
        command = child["command_id"]
        if (type(command) is not str
                or command != selected_child_command_id(
                    child["root_job_id"], child["job_id"], child["attempt_ordinal"])):
            _refuse()
        if command in commands:
            _refuse()
        commands.add(command)
    material = selected_child_material(raw["work_ref"], children)
    digest = raw["material_digest"]
    if type(digest) is not str or _HEX64.fullmatch(digest) is None:
        _refuse()
    if selected_child_material_digest(material) != digest:
        _refuse()
    source = raw["source"]
    if type(source) is not dict or set(source) != SELECTED_CHILD_SOURCE_KEYS:
        _refuse()
    if source["schema"] != SELECTED_CHILD_SOURCE_SCHEMA:
        _refuse()
    for key in ("policy_sha", "reservation_digest"):
        if type(source[key]) is not str or _HEX64.fullmatch(source[key]) is None:
            _refuse()
    for key in ("plan_attempt_id", "plan_digest"):
        if type(source[key]) is not str or not 0 < len(source[key]) <= 128:
            _refuse()
    if source["observation_state"] not in {"SAME", "UNKNOWN"}:
        _refuse()
    identity = source["observation_source_identity"]
    if identity is not None and (type(identity) is not str
                                  or not 0 < len(identity) <= 128):
        _refuse()
    if any(child["plan_attempt_id"] != source["plan_attempt_id"]
           or child["plan_digest"] != source["plan_digest"] for child in children):
        _refuse()
    return json.loads(canonical(raw))


def build_selected_child_publication(*, work_ref, root_job_id, children, source):
    """Compose the closed publication projection from one frozen capture.

    Pure: it derives the material digest over exactly the frozen
    coordinates and never recomputes an ordinal, selects a replacement
    child or reads any source.
    """

    document = {
        "schema": SELECTED_CHILD_TARGET_SCHEMA,
        "work_ref": work_ref,
        "root_job_id": root_job_id,
        "children": [dict(child) for child in children],
        "material_digest": selected_child_material_digest(
            selected_child_material(work_ref, children)),
        "source": dict(source),
    }
    return validate_selected_child_target(document)


def _refuse():
    raise ValueError("installed COO authority unavailable")


def generation(row):
    immutable = {k: v for k, v in row.items() if k != "enabled"}
    return hashlib.sha256(canonical(immutable)).hexdigest()


def _mission_actions(row):
    keys = set(row)
    if keys == MISSION_KEYS_V1:
        return DEFAULT_PRINCIPAL_ACTIONS
    if keys != MISSION_KEYS_V2 or type(row.get("authority_version")) is not int:
        _refuse()
    if row["authority_version"] != MISSION_AUTHORITY_VERSION:
        _refuse()
    actions = row.get("principal_actions")
    if (type(actions) is not list or not actions
            or actions != sorted(set(actions))
            or any(type(action) is not str or action not in PRINCIPAL_ACTIONS
                   for action in actions)):
        _refuse()
    return tuple(actions)


def _authority(row):
    return AuthorityFact(work_ref=row["work_ref"],
        mission_authority_ref=row["mission_authority_ref"],
        authority_generation_digest=generation(row), outcome_ref=row["outcome_ref"],
        proof_contract_ref=row["proof_contract_ref"], release_class=ReleaseClass.RESERVED_RELEASE,
        capability_profile_digest=row["capability_profile_digest"],
        source_grant_digest=None, economic_envelope_digest=None,
        principal_actions=_mission_actions(row))


def validate_missions(value):
    if type(value) is not list or len(value) > 64:
        _refuse()
    seen = []
    for row in value:
        if type(row) is not dict or type(row.get("enabled")) is not bool:
            _refuse()
        _mission_actions(row)
        _authority(row)
        PrincipalAdmissionContext(row["work_ref"], row["principal_binding_digest"],
            row["mission_authority_ref"], generation(row))
        if type(row["capability_profile_id"]) is not str or not row["capability_profile_id"]:
            _refuse()
        profiles = row["execution_profiles"]
        if (type(profiles) is not list or not profiles or profiles != sorted(set(profiles))
                or not set(profiles) <= {"research_only", "bounded_code_change"}):
            _refuse()
        paths = ceo_intent._write_paths(row["allowed_write_paths"])
        if paths != row["allowed_write_paths"] or paths != sorted(set(paths)):
            _refuse()
        if any(any(c in path for c in "*?[]") for path in paths):
            _refuse()
        if ("bounded_code_change" in profiles) != bool(paths):
            _refuse()
        seen.append(row["work_ref"])
    if seen != sorted(set(seen)) or len(canonical(value)) > 65_536:
        _refuse()
    return json.loads(canonical(value))


class CooHostProvider:
    """Consume trusted neutral source callbacks, not wire-authored authority.

    The installed launcher separately requires the exact root-sealed adapter.
    Keeping this dependency structural preserves the core/integration boundary.
    """
    def __init__(self, source, workspace, *, agentos_context_reader=None):
        from control_plane.workspace_read_service import WorkspaceReadService
        if (not callable(getattr(source, "snapshot", None))
                or not callable(getattr(source, "for_principal", None))
                or type(workspace) is not WorkspaceReadService):
            _refuse()
        self.source, self.workspace = source, workspace
        from control_plane.agentos_context_bundle import AgentOsContextBundleReader
        if agentos_context_reader is not None and type(agentos_context_reader) is not AgentOsContextBundleReader:
            _refuse()
        self.agentos_context_reader = agentos_context_reader

    def read_agentos_context(self, frame):
        """One explicitly granted read; never invoke fresh-effect eligibility."""
        from common import coo_agentos_context_contract as wire
        from control_plane.agentos_context_bundle import AgentOsContextBundleReader
        wire.validate_frame(frame)
        context = wire.context(frame["principal_context"])
        source, workspace, reader = self.source, self.workspace, self.agentos_context_reader
        if type(reader) is not AgentOsContextBundleReader:
            _refuse()

        def capture():
            if (self.source is not source or self.workspace is not workspace
                    or self.agentos_context_reader is not reader):
                _refuse()
            source.require_context_source_current()
            row, fact, authority = source.for_principal(frame["principal"], context.work_ref)
            actual = PrincipalAdmissionContext(row["work_ref"], fact.principal_binding_digest,
                authority.mission_authority_ref, authority.authority_generation_digest)
            if (row["enabled"] is not True or actual != context
                    or authority.capability_profile_digest != frame["capability_profile_digest"]
                    or wire.ACTION not in authority.principal_actions
                    or source.catalogue_for_principal(frame["principal"]) != wire.CATALOGUE):
                _refuse()
            # generation(row) excludes enabled. Keep a detached full row as well
            # as immutable facts so late mission disablement cannot be missed.
            return json.loads(canonical(row)), dataclasses.replace(fact), dataclasses.replace(authority)

        before = capture()
        raw, receipt = reader.read(work_ref=context.work_ref)
        result = wire.result(raw, receipt, principal_context=frame["principal_context"],
            capability_profile_digest=frame["capability_profile_digest"])
        if capture() != before:
            _refuse()
        return result

    def read_current_agentos_context(self, frame):
        return self._read_current_agentos_context(frame, discovery=False)

    def read_discovery_agentos_context(self, frame):
        return self._read_current_agentos_context(frame, discovery=True)

    def read_knowledge_agentos_context(self, frame):
        return self._read_current_agentos_context(frame, discovery=False, knowledge=True)

    def _read_current_agentos_context(self, frame, *, discovery, knowledge=False):
        """Join two authenticated projections to the original installed DATA owner."""
        import base64
        from common import coo_agentos_context_contract as wire
        from common.executive_workspace_contract import permission_stamp
        from control_plane.installed_canonical_project_data_binding import read_installed_project_data
        (wire.validate_knowledge_frame if knowledge else wire.validate_discovery_frame if discovery else wire.validate_current_frame)(frame)
        context = wire.context(frame["principal_context"])
        source, workspace = self.source, self.workspace
        binding, authorize, runtime = workspace._canonical_project_data, workspace.authorize, workspace.runtime
        if binding is None or binding.store is not runtime.store:
            _refuse()

        def capture():
            if (self.source is not source or self.workspace is not workspace
                    or workspace._canonical_project_data is not binding or workspace.authorize is not authorize
                    or workspace.runtime is not runtime or binding.store is not runtime.store):
                _refuse()
            source.require_context_source_current()
            row, fact, authority = source.for_principal(frame["principal"], context.work_ref)
            joined = source.for_workspace_read_principal(frame["workspace_principal"], context.work_ref)
            actual = PrincipalAdmissionContext(row["work_ref"], fact.principal_binding_digest,
                authority.mission_authority_ref, authority.authority_generation_digest)
            if (row["enabled"] is not True or actual != context or joined != (row, fact, authority)
                    or authority.capability_profile_digest != frame["capability_profile_digest"]
                    or wire.CURRENT_ACTION not in authority.principal_actions
                    or source.catalogue_for_principal(frame["principal"]) !=
                        (wire.KNOWLEDGE_CATALOGUE if knowledge else wire.DISCOVERY_CATALOGUE if discovery else wire.CURRENT_CATALOGUE)
                    or authorize(frame["workspace_principal"]) is not True):
                _refuse()
            stamp = permission_stamp(authorize, frame["workspace_principal"])
            if stamp is None:
                _refuse()
            return (json.loads(canonical(row)), dataclasses.replace(fact), dataclasses.replace(authority), stamp)

        before = capture()
        data = read_installed_project_data(binding, frame["workspace_principal"],
            operation="agentos_current_context", selection={"work_ref": context.work_ref})
        if data is None:
            _refuse()
        body, view, _ = data
        if set(body) != {"bundle_encoding", "bundle_base64", "receipt"} or body["bundle_encoding"] != "base64":
            _refuse()
        raw = base64.b64decode(body["bundle_base64"], validate=True)
        result = wire.current_result(raw, body["receipt"], principal_context=frame["principal_context"],
            capability_profile_digest=frame["capability_profile_digest"], workspace_principal=frame["workspace_principal"],
            discovery=discovery, knowledge=knowledge)
        view.check()
        if capture() != before:
            _refuse()
        return result

    async def read_workspace_host_observation(self, frame):
        from control_plane.workspace_host_observation_read import handle_from_original_coo
        return await handle_from_original_coo(self.workspace, frame, self.source)

    async def read_workspace_resource_capacity(self, frame):
        from control_plane.workspace_resource_capacity_read import handle_from_original_coo
        return await handle_from_original_coo(self.workspace, frame, self.source)

    async def read_workspace_retained_activity(self, frame):
        """Delegate one *read-only* original Executive OHF observation.

        The installed COO provider already owns this source and its existing
        Workspace reader. No new grant registry, new host or action token.
        """
        from common.executive_workspace_activity_contract import validate_frame
        validate_frame(frame)
        return await self.workspace.handle_activity_from_original_coo(frame, self.source)

    async def read_workspace_fabric(self, frame, paid_source):
        """Join this actual installed COO source to the original paid owner."""
        from control_plane.workspace_fabric_read import handle_fabric_frame
        return await handle_fabric_frame(self.workspace, frame, self.source, paid_source)

    def capture_selected_child_target(self, *, principal, context, work_ref,
                                      root_job_id, child_job_ids):
        """Freeze one trusted host's selected-child set from the canonical owners.

        This is a private host preparation entry. It is never an mmx_delegate
        model argument and never an HTTP frame. It requires the actual
        installed mission/principal association and the owned Workspace and
        Runtime source: a supplied hash, a mapping's shape or a Hermes role
        name is never an authenticated origin.

        The admitted plan, the current work-or-repair lineage and the exact
        chosen children are acquired through ONE bounded incumbent
        observation. Nothing here dispatches a Job, mutates the Runtime,
        creates a request identity or previews a CooCycle.
        """

        if not _check_work_ref(work_ref) or not _check_job_id(root_job_id):
            raise ValueError("selected child capture identity is invalid")
        if (type(context) is not PrincipalAdmissionContext
                or context.work_ref != work_ref):
            raise ValueError("selected child capture authority is unavailable")
        if type(child_job_ids) not in (list, tuple):
            raise ValueError("selected child capture set is invalid")
        chosen = tuple(child_job_ids)
        if not 1 <= len(chosen) <= MAX_SELECTED_CHILDREN:
            raise ValueError("selected child capture set is invalid")
        if any(type(item) is not str or not _check_job_id(item) for item in chosen):
            raise ValueError("selected child capture set is invalid")
        if len(set(chosen)) != len(chosen):
            raise ValueError("selected child capture set is invalid")
        # The installed source proves the association; the supplied mapping
        # is only a selector that must match the installed facts exactly.
        before = self.source.for_principal(principal, work_ref)
        row, fact, authority = before
        current = PrincipalAdmissionContext(
            row["work_ref"], fact.principal_binding_digest,
            authority.mission_authority_ref, authority.authority_generation_digest,
        )
        if row["enabled"] is not True or context != current:
            raise ValueError("selected child capture authority is unavailable")
        if self.source.for_principal(principal, work_ref) != before:
            raise ValueError("selected child capture authority changed")
        # The owned Workspace mission names the exact root. An ambiguous root
        # is a refusal, never a choice.
        association = self._mission_association(work_ref, root_job_id)
        capture = self.workspace.capture_selected_child_target(
            work_ref=work_ref, root_job_id=root_job_id, child_job_ids=chosen)
        if self.source.for_principal(principal, work_ref) != before:
            raise ValueError("selected child capture authority changed")
        # The association is proven BEFORE and AFTER the Runtime observation:
        # a mission or root publication change inside the capture window can
        # never freeze an old root.
        if self._mission_association(work_ref, root_job_id) != association:
            raise ValueError("selected child capture mission changed")
        return capture

    def _mission_association(self, work_ref, root_job_id):
        """The genuine mission/root association of one owned Workspace read.

        The returned tuple is the association itself, never the whole
        document: the association is what must be the same before and after
        the capture, and a change of it is a refusal.
        """

        mission = self.workspace.read_mission_for_work_ref(work_ref)
        program = mission.get("program") if type(mission) is dict else None
        body = mission.get("mission") if type(mission) is dict else None
        if (type(mission) is not dict
                or mission.get("schema") != "mastermind.mission_workspace.v3"
                or type(program) is not dict
                or program.get("work_ref") != work_ref
                or type(body) is not dict
                or body.get("root_job_id") != root_job_id
                or body.get("root_job_ambiguous") is not False):
            raise ValueError("selected child capture mission is unavailable")
        return (mission.get("schema"), program.get("work_ref"),
                body.get("root_job_id"), body.get("root_job_ambiguous"))

    def facts(self, frame):
        validate_facts_frame(frame)
        before = self.source.for_principal(frame["principal"], frame["work_ref"])
        if frame["operation"] == "authority":
            result = dataclasses.asdict(before[2])
        elif "preparation" in frame:
            result = self._prepare_selected_child(frame, before)
        else:
            if before[0]["enabled"] is not True:
                _refuse()
            result = self.workspace.read_mission_for_work_ref(frame["work_ref"])
        if self.source.for_principal(frame["principal"], frame["work_ref"]) != before:
            _refuse()
        return result

    def _prepare_selected_child(self, frame, before):
        """One closed preparation of the frozen selected-child capture.

        The authority of this preparation is the installed host's OWN facts:
        the principal is re-proved against the installed source, the
        admission context is DERIVED from the installed row, fact and
        authority, and the capture itself re-proves the mission/root
        association before and after the Runtime observation.  The frame
        never supplies an authority and never selects a child.
        """

        row, fact, authority = before
        if row["enabled"] is not True:
            _refuse()
        context = PrincipalAdmissionContext(
            row["work_ref"], fact.principal_binding_digest,
            authority.mission_authority_ref, authority.authority_generation_digest,
        )
        preparation = frame["preparation"]
        return self.capture_selected_child_target(
            principal=frame["principal"], context=context,
            work_ref=frame["work_ref"], root_job_id=preparation["root_job_id"],
            child_job_ids=list(preparation["child_job_ids"]))

    def guard(self, envelope):
        if type(envelope) is not dict or envelope.get("schema") != ceo_intent.INTENT_SCHEMA_PRINCIPAL:
            _refuse()
        before = self.source.snapshot(envelope.get("workstream"))
        row, principal, authority = before
        context = PrincipalAdmissionContext(row["work_ref"], principal.principal_binding_digest,
            authority.mission_authority_ref, authority.authority_generation_digest)
        if row["enabled"] is not True or any(envelope.get(k) != v for k, v in
                dataclasses.asdict(context).items() if k != "work_ref"):
            _refuse()
        if "bounded_intent" not in authority.principal_actions:
            _refuse()
        contract = envelope.get("execution_contract", {})
        allowed = [ceo_request.derive_authorities(p) for p in row["execution_profiles"]]
        if contract.get("requested_authorities") not in allowed:
            _refuse()
        for path in contract.get("allowed_write_paths", []):
            if not any(PurePosixPath(path).is_relative_to(PurePosixPath(root))
                       for root in row["allowed_write_paths"]):
                _refuse()
        mission = self.workspace.read_mission_for_work_ref(row["work_ref"])
        mandate = project_coo_principal_mandate(principal=principal,
            authority=authority, mission_workspace=mission)
        if mandate["new_effect_gate"] != "OPEN" or self.source.snapshot(row["work_ref"]) != before:
            _refuse()
        return None

    def guard_orchestration(self, bundle):
        """Re-prove current COO authority before a governed root effect."""

        try:
            normalized = validate_principal_orchestration_bundle(bundle)
        except (TypeError, ValueError):
            _refuse()
        envelope = normalized["envelope"]
        before = self.source.snapshot(envelope["workstream"])
        row, principal, authority = before
        context = PrincipalAdmissionContext(
            row["work_ref"],
            principal.principal_binding_digest,
            authority.mission_authority_ref,
            authority.authority_generation_digest,
        )
        if (
            row["enabled"] is not True
            or envelope["workstream"] != context.work_ref
            or any(
                envelope.get(key) != value
                for key, value in dataclasses.asdict(context).items()
                if key != "work_ref"
            )
            or "governed_orchestration" not in authority.principal_actions
        ):
            _refuse()
        mission = self.workspace.read_mission_for_work_ref(row["work_ref"])
        mandate = project_coo_principal_mandate(
            principal=principal,
            authority=authority,
            mission_workspace=mission,
        )
        if (
            mandate["new_effect_gate"] != "OPEN"
            or self.source.snapshot(row["work_ref"]) != before
        ):
            _refuse()
        return None

    def guard_dialogue(self, *, context, root_job_id, capability_profile_digest):
        """Revalidate a trusted App caller at the existing Control effect seam.

        This method authenticates no transport and grants no action. Only an
        already-authorized host may supply these facts; an App peer still needs
        its separate kernel-peer gate. Child/Relay identity and single COMMIT
        remain with their existing owners. No source selection or fallback.
        """
        try:
            if type(context) is not PrincipalAdmissionContext:
                _refuse()
            before = self.source.snapshot(context.work_ref)
            row, principal, authority = before
            current = PrincipalAdmissionContext(
                row["work_ref"], principal.principal_binding_digest,
                authority.mission_authority_ref, authority.authority_generation_digest,
            )
            if (row["enabled"] is not True or context != current
                    or authority.capability_profile_digest != capability_profile_digest
                    or "governed_orchestration" not in authority.principal_actions):
                _refuse()
            def read_mandate():
                return project_coo_principal_mandate(principal=principal,
                    authority=authority,
                    mission_workspace=self.workspace.read_mission_for_work_ref(context.work_ref))
            mandate = read_mandate()
            mission = mandate["mission"]
            if (mandate["new_effect_gate"] != "OPEN"
                    or mandate["decision_posture"] != "DECIDE_CONTINUE"
                    or mission["work_ref"] != context.work_ref
                    or mission["root_job_id"] != root_job_id
                    or mission["accountable_seat"] != "coo"
                    or mission["owed_turn"]["seat"] != "coo"
                    or read_mandate() != mandate
                    or self.source.snapshot(context.work_ref) != before):
                _refuse()
        except Exception:
            raise ValueError("installed COO authority unavailable") from None
        return None


__all__ = [
    "FACT_SCHEMA",
    "FACT_FRAME_KEYS",
    "FACT_PREPARATION_FRAME_KEYS",
    "FACT_PREPARATION_KEYS",
    "FACT_PREPARATION_SCHEMA",
    "MAX_FACT_SELECTED_CHILDREN",
    "MISSION_AUTHORITY_VERSION",
    "MISSION_KEYS_V1",
    "MISSION_KEYS_V2",
    "CooHostProvider",
    "MAX_SELECTED_CHILDREN",
    "SELECTED_CHILD_SOURCE_SCHEMA",
    "SELECTED_CHILD_TARGET_SCHEMA",
    "build_selected_child_publication",
    "selected_child_command_id",
    "selected_child_material",
    "selected_child_material_digest",
    "validate_missions",
    "validate_facts_frame",
    "validate_selected_child_target",
]


FACT_PRINCIPAL_KEYS = frozenset({"policy_id", "issuer_digest", "subject_digest", "client_ref", "resource", "scopes"})


def _validate_fact_preparation(preparation):
    """The closed selector block of one preparation request."""

    if (type(preparation) is not dict or set(preparation) != FACT_PREPARATION_KEYS
            or preparation["schema"] != FACT_PREPARATION_SCHEMA):
        _refuse()
    if not _check_job_id(preparation["root_job_id"]):
        _refuse()
    children = preparation["child_job_ids"]
    if type(children) is not list or not 1 <= len(children) <= MAX_FACT_SELECTED_CHILDREN:
        _refuse()
    if any(type(item) is not str or not _check_job_id(item) for item in children):
        _refuse()
    if len(set(children)) != len(children):
        _refuse()
    return preparation


def validate_facts_frame(frame):
    """Closed read frame; authority still comes from the enrolled host source.

    The legacy four-key authority/mission frame is preserved exactly, with
    the same results.  The PREPARATION variant is that same closed frame
    with ONE explicit tag: it keeps ``operation == "mission"`` so the
    incumbent admission-arming gate still applies, and it adds exactly the
    closed selector block.  An extra key, an unsupported tag, a duplicate,
    empty or oversized selector is refused BEFORE any acquisition.
    """
    if type(frame) is not dict:
        _refuse()
    keys = set(frame)
    if "preparation" in keys:
        if keys != FACT_PREPARATION_FRAME_KEYS or frame["operation"] != "mission":
            _refuse()
        _validate_fact_preparation(frame["preparation"])
    elif keys != FACT_FRAME_KEYS:
        _refuse()
    if (frame["schema"] != FACT_SCHEMA or frame["operation"] not in {"authority", "mission"}
            or not _check_work_ref(frame["work_ref"])):
        _refuse()
    principal = frame["principal"]
    if (type(principal) is not dict or set(principal) != FACT_PRINCIPAL_KEYS
            or type(principal["scopes"]) is not list or not 1 <= len(principal["scopes"]) <= 16
            or any(type(scope) is not str or not 1 <= len(scope) <= 96 for scope in principal["scopes"])
            or principal["scopes"] != sorted(set(principal["scopes"]))
            or any(type(principal[key]) is not str or not 1 <= len(principal[key]) <= 256
                   for key in FACT_PRINCIPAL_KEYS - {"scopes"})
            or len(canonical(frame)) + 1 > 8192):
        _refuse()
    return frame
