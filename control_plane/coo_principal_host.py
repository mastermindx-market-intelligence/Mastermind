"""Installed COO facts and final guard; no new store, token or runtime owner.

Delegations are explicit root-published data in the existing Executive MCP
installation. Workspace retains mission/currentness ownership. This capability
admits bounded Jobs only; it grants no direct source release or deployment.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import PurePosixPath

from common.executive_workspace_contract import canonical, _check_work_ref
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
MISSION_AUTHORITY_VERSION = 2
MISSION_KEYS_V1 = frozenset({"enabled", "work_ref", "principal_binding_digest",
    "mission_authority_ref", "outcome_ref", "proof_contract_ref",
    "capability_profile_id", "capability_profile_digest",
    "execution_profiles", "allowed_write_paths"})
MISSION_KEYS_V2 = MISSION_KEYS_V1 | frozenset({"authority_version", "principal_actions"})
MISSION_KEYS = MISSION_KEYS_V1


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
    def __init__(self, source, workspace):
        from control_plane.workspace_read_service import WorkspaceReadService
        if (not callable(getattr(source, "snapshot", None))
                or not callable(getattr(source, "for_principal", None))
                or type(workspace) is not WorkspaceReadService):
            _refuse()
        self.source, self.workspace = source, workspace

    async def read_workspace_retained_activity(self, frame):
        """Delegate one *read-only* original Executive OHF observation.

        The installed COO provider already owns this source and its existing
        Workspace reader. No new grant registry, new host or action token.
        """
        from common.executive_workspace_activity_contract import validate_frame
        validate_frame(frame)
        return await self.workspace.handle_activity_from_original_coo(frame, self.source)

    def facts(self, frame):
        validate_facts_frame(frame)
        before = self.source.for_principal(frame["principal"], frame["work_ref"])
        if frame["operation"] == "authority":
            result = dataclasses.asdict(before[2])
        else:
            if before[0]["enabled"] is not True:
                _refuse()
            result = self.workspace.read_mission_for_work_ref(frame["work_ref"])
        if self.source.for_principal(frame["principal"], frame["work_ref"]) != before:
            _refuse()
        return result

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
    "MISSION_AUTHORITY_VERSION",
    "MISSION_KEYS_V1",
    "MISSION_KEYS_V2",
    "CooHostProvider",
    "validate_missions",
    "validate_facts_frame",
]


FACT_PRINCIPAL_KEYS = frozenset({"policy_id", "issuer_digest", "subject_digest", "client_ref", "resource", "scopes"})


def validate_facts_frame(frame):
    """Closed read frame; authority still comes from the enrolled host source."""
    if (type(frame) is not dict or set(frame) != {"schema", "operation", "work_ref", "principal"}
            or frame["schema"] != FACT_SCHEMA or frame["operation"] not in {"authority", "mission"}
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
