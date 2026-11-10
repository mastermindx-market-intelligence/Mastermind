"""One current project-help read through the existing COO/Workspace owners.

There is no root selection heuristic, new registry, target store or execution
grant here. The installed scope must still agree with the original mission
and its exact adopted source plan before and after the bounded target read.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import time

from common import coo_project_help_contract as wire
from common.executive_workspace_contract import canonical, permission_stamp
from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.workspace_owned_task import remaining_read_seconds


# The installed CooFactsClient retains its existing 30-second acceptance
# ceiling. This whole private read has one smaller budget; no source's own
# 15-second maximum, grant lifetime or observation lifetime is extended.
PROJECT_HELP_READ_BUDGET_SECONDS = wire.PRIVATE_READ_MAX_SECONDS


def _digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _mission_owner_identity(receipt):
    """Compare qualified owner/source identity across fresh acquisitions.

    Runtime source_identity names a request-local read connection. DATA
    observed-at/source-generation and validity digests describe that acquisition,
    so equality would reject a fresh read of unchanged source. Each full receipt
    is independently validated by Mission v3 and retained as evidence below.
    This closed projection compares the original owners, stable source bytes,
    original selection and Runtime generation/snapshot; it grants no currency.
    """
    runtime, control = receipt["runtime"], receipt["control_room"]
    stable = {
        "schema": receipt["schema"], "state": receipt["state"], "selection": receipt["selection"],
        "runtime": {key: runtime[key] for key in ("schema", "state", "before", "after", "snapshot_digest")},
        "control_room": {key: control[key] for key in ("instance_before", "instance_after",
            "publication_before", "publication_after", "document_digest", "cache_currentness_digest")},
    }
    if receipt["schema"] in {"mastermind.workspace_source_observation.v2", "mastermind.workspace_source_observation.v3"}:
        from common.project_discovery_observation_contract import validate_coherence
        from common.canonical_project_data_observation_contract import validate
        selected = receipt["selection"]
        validate_coherence(receipt, work_ref=selected["work_ref"], root_job_id=selected["root_job_id"])
        data = receipt["project_data"]
        observation = validate(data["data_observation"])
        stable["project_data"] = {
            "source": data["source"], "code_source": data["code_source"],
            "creation_publication": data["creation_publication"],
            "data_observation": {key: value for key, value in observation.items()
                if key != "canonical_observed_at_ms"},
        }
        if receipt["schema"] == "mastermind.workspace_source_observation.v3":
            resource = receipt["resource"]
            stable["resource"] = {key: value for key, value in resource.items() if key != "history"}
            stable["resource"]["history"] = {key: value for key, value in resource["history"].items()
                if key != "observation"}
    elif receipt["schema"] != "mastermind.workspace_source_observation.v1":
        wire._refuse()
    return _digest(stable)


@dataclasses.dataclass(frozen=True)
class ProjectHelpAuthority:
    scope: dict
    source_row: dict
    principal_context: dict
    capability_profile_digest: str
    permission_stamp: object
    mission_identity: str
    plan_identity: str
    mission_read: dict
    mission_observation_sha256: str = dataclasses.field(compare=False)
    source_owner: object = dataclasses.field(repr=False)
    workspace_owner: object = dataclasses.field(repr=False)
    runtime_owner: object = dataclasses.field(repr=False)
    cache_owner: object = dataclasses.field(repr=False)
    data_owner: object = dataclasses.field(repr=False)
    discovery_owner: object = dataclasses.field(repr=False)
    authorize_owner: object = dataclasses.field(repr=False)
    original_execution: dict | None = None
    input_reader_owner: object = dataclasses.field(default=None, repr=False)


def capture_project_help_authority(provider, frame, *, deadline=None):
    """Re-prove one explicitly enrolled original root; never select a new one."""
    from control_plane.coo_principal_host import CooHostProvider
    from control_plane.coo_principal_mandate import _mission_state
    from common.workspace_project_plan_contract import validate_body, BODY_SCHEMA_V2
    frame = wire.validate_frame(frame)
    remaining_read_seconds(deadline, maximum=PROJECT_HELP_READ_BUDGET_SECONDS)
    if type(provider) is not CooHostProvider:
        wire._refuse()
    source, workspace = provider.source, provider.workspace
    runtime, cache, data, authorize = (workspace.runtime, workspace.cache,
        workspace._canonical_project_data, workspace.authorize)
    discovery = workspace._project_discovery
    input_reader = provider.project_execution_input_reader
    context = frame["principal_context"]
    work_ref = context["work_ref"]

    def capture_grant():
        remaining_read_seconds(deadline, maximum=PROJECT_HELP_READ_BUDGET_SECONDS)
        if (provider.source is not source or provider.workspace is not workspace
                or workspace.runtime is not runtime or workspace.cache is not cache
                or workspace._canonical_project_data is not data or workspace.authorize is not authorize
                or workspace._project_discovery is not discovery
                or provider.project_execution_input_reader is not input_reader
                or data is not None and data.store is not runtime.store):
            wire._refuse()
        source.require_context_source_current()
        row, fact, authority = source.for_principal(frame["principal"], work_ref)
        joined = source.for_workspace_read_principal(frame["workspace_principal"], work_ref)
        actual = PrincipalAdmissionContext(row["work_ref"], fact.principal_binding_digest,
            authority.mission_authority_ref, authority.authority_generation_digest)
        if (row["enabled"] is not True or actual != PrincipalAdmissionContext(**context)
                or joined != (row, fact, authority)
                or authority.capability_profile_digest != frame["capability_profile_digest"]
                or wire.ACTION not in authority.principal_actions
                or source.catalogue_for_principal(frame["principal"], work_ref=work_ref) not in {
                    wire.CATALOGUE, wire.API_REQUESTER_CATALOGUE}
                or authorize(frame["workspace_principal"]) is not True):
            wire._refuse()
        stamp = permission_stamp(authorize, frame["workspace_principal"])
        if stamp is None:
            wire._refuse()
        return json.loads(canonical(row)), dataclasses.replace(fact), dataclasses.replace(authority), stamp

    grant = capture_grant()
    row = grant[0]
    if row.get("authority_version") != 4:
        wire._refuse()
    selected = wire.scope(row.get("project_help"))
    if selected["source_plan"]["work_ref"] != work_ref:
        wire._refuse()
    # The current owner must uniquely resolve THIS enrolled original root.
    # This never assumes every project has one root, picks a latest root, or
    # treats an effect hold as a denial of a qualified observational read.
    # The sealed original root is only a selector. This existing acquisition
    # also supports genuinely published current-DATA projects absent from the
    # older Control Room catalogue, through its installed discovery owner.
    acquired = workspace._read_mission_v3({"principal": frame["workspace_principal"],
        "selection": {"work_ref": work_ref, "root_job_id": selected["root_job_id"]}}, _project_help=True,
        **({"_deadline": deadline} if deadline is not None else {}))
    remaining_read_seconds(deadline, maximum=PROJECT_HELP_READ_BUDGET_SECONDS)
    if type(acquired) is not dict or acquired.get("ok") is not True:
        wire._refuse()
    mission = acquired["result"]
    owner_observation = mission["source"]["owner_observation"]
    execution_resource = owner_observation.get("schema") == "mastermind.workspace_source_observation.v3"
    read_qualification = acquired.get("help_read_qualification")
    qualification = "CURRENT_MISSION"
    root_origin_sha256 = None
    if execution_resource:
        from common.project_execution_resource_contract import validate_resource
        from control_plane.project_execution_admission import ProjectExecutionInputReadOwner
        resource = validate_resource(owner_observation.get("resource"), work_ref=work_ref,
            root_job_id=selected["root_job_id"])
        body = mission["mission"]
        if (type(input_reader) is not ProjectExecutionInputReadOwner
                or input_reader._runtime is not runtime
                or mission["schema"] != "mastermind.mission_workspace.v3"
                or mission["program"]["work_ref"] != work_ref
                or body["root_job_id"] != selected["root_job_id"]
                or body["root_job_candidates"] != [selected["root_job_id"]]
                or body["root_job_ambiguous"] is not False or body["runtime_root_state"] != "RESOLVED"):
            wire._refuse()
        qualified = False
    else:
        state = _mission_state(mission, expected_work_ref=work_ref)
        if state.root_job_id != selected["root_job_id"]:
            wire._refuse()
        qualified = state.qualified
    if not qualified:
        if type(read_qualification) is not dict:
            wire._refuse()
        root_origin_sha256 = wire._digest(read_qualification.get("root_origin_sha256"))
        expected = {"schema": "mastermind.project_help_execution_resource_read.v1" if execution_resource
                else "mastermind.project_help_mission_read.v1",
            "kind": wire.EXECUTION_READ_QUALIFICATION if execution_resource
                else "CURRENT_DATA_CARD_WITH_UNOBSERVED_DISPATCH",
            "selection": {"work_ref": work_ref, "root_job_id": selected["root_job_id"]},
            "owner_observation_sha256": _digest(mission["source"]["owner_observation"]),
            "root_origin_sha256": root_origin_sha256,
            "mission_read_state": "PARTIAL", "transport": mission["transport"], "execution_authorized": False}
        if (read_qualification != expected
                or not execution_resource and state.reason_codes != ("mission_read_state_not_current",)):
            wire._refuse()
        qualification = expected["kind"]
    elif read_qualification is not None:
        wire._refuse()
    mission_read = {"qualification": qualification, "root_origin_sha256": root_origin_sha256,
        "mission_read_state": mission["read_state"]["state"], "diagnostics": list(mission["degraded"]),
        "transport": {key: mission["transport"][key] for key in ("dispatch_state", "reason", "actionable", "historical")},
        "execution_authorized": False}
    # Current DATA supplies both documents inside its original issued view.
    # Legacy C acquisition keeps its existing installed Plan reader; only a
    # host-owned outer deadline may reduce that reader's existing budget.
    plan = validate_body(acquired["help_plan"] if "help_plan" in acquired else
        workspace._read_project_plan({"work_ref": work_ref}, frame["workspace_principal"],
            **({"_deadline": deadline} if deadline is not None else {})))
    if plan["schema"] != BODY_SCHEMA_V2 or plan["availability"] != "AVAILABLE":
        wire._refuse()
    adoption = plan["continuity"]["adoption"]
    if (adoption["state"] != "AVAILABLE"
            or adoption["adoption"]["adopted_source"] != selected["source_plan"]["source"]
            or hashlib.sha256(adoption["content"].encode("utf-8")).hexdigest()
                != selected["source_plan"]["source"]["content_sha256"]):
        wire._refuse()
    from common.project_task_contract import parse_plan, contract_digest
    adopted_plan = parse_plan(adoption["content"].encode("utf-8"))
    if (adopted_plan["workstream"] != work_ref
            or contract_digest(adopted_plan) != selected["source_plan"]["contract_sha256"]):
        wire._refuse()
    original_execution = None
    if execution_resource:
        remaining_read_seconds(deadline, maximum=PROJECT_HELP_READ_BUDGET_SECONDS)
        original_execution = input_reader.read(selected_scope=selected,
            expected_source_sha256=resource["original_execution"]["source_sha256"],
            adopted_content=adoption["content"], project_plan_sha256=_digest(plan), deadline=deadline)
        remaining_read_seconds(deadline, maximum=PROJECT_HELP_READ_BUDGET_SECONDS)
        if (original_execution["input_reference_sha256"] != resource["original_execution"]["input_reference_sha256"]
                or original_execution["input_context_sha256"] != resource["original_execution"]["context_sha256"]):
            wire._refuse()
    if capture_grant() != grant:
        wire._refuse()
    return ProjectHelpAuthority(selected, row, dict(context), frame["capability_profile_digest"],
        grant[3], _mission_owner_identity(mission["source"]["owner_observation"]), _digest(plan),
        mission_read, _digest(mission["source"]["owner_observation"]), source, workspace, runtime, cache, data, discovery, authorize,
        original_execution, input_reader)


async def read_project_help(provider, frame, *, session_bridge_owner=None, host_current=None):
    from common.session_bridge_private_contract import PRIVATE_SCHEMA, PRIVATE_RESULT_SCHEMA, SessionBridgeIngressOwner
    frame = wire.validate_frame(frame)
    if host_current is not None and not callable(host_current):
        wire._refuse()
    deadline = time.monotonic() + PROJECT_HELP_READ_BUDGET_SECONDS

    def current():
        remaining_read_seconds(deadline, maximum=PROJECT_HELP_READ_BUDGET_SECONDS)
        if host_current is not None and host_current() is False:
            wire._refuse()

    from control_plane.workspace_owned_task import await_owned

    async def capture():
        # Existing owner joins its original bounded work even on cancellation;
        # Workspace filesystem/Git/Runtime reads must not block the service loop.
        current()
        value = await await_owned(asyncio.create_task(asyncio.to_thread(
            capture_project_help_authority, provider, frame, deadline=deadline)))
        current()
        return value

    current()
    before = await capture()
    current()
    owner = session_bridge_owner
    if owner is not None and type(owner) is not SessionBridgeIngressOwner:
        wire._refuse()

    async def current_targets():
        if owner is None:
            return wire.unavailable_targets("SESSION_BRIDGE_NOT_COMPOSED")
        items = []
        # These two original Runtime target kinds carry the qualified
        # work/root/continuation coordinates. Other native inventories are not
        # promoted into this root scope merely because a protocol is supported.
        for kind in ("fabric_attempt", "codex"):
            current()
            request = {"schema": PRIVATE_SCHEMA, "tool": "session_targets",
                "principal": frame["session_principal"], "arguments": {"kind": kind}}
            if owner.validate_frame(request) != "session_targets":
                wire._refuse()
            response = await owner.handle_frame(request)
            current()
            if (type(response) is not dict or set(response) != {"schema", "tool", "ok", "data", "error"}
                    or response["schema"] != PRIVATE_RESULT_SCHEMA or response["tool"] != "session_targets"
                    or response["ok"] is not True or response["error"] is not None
                    or type(response["data"]) is not list or len(response["data"]) > 256):
                return wire.unavailable_targets("CURRENT_TARGETS_UNAVAILABLE")
            for target in response["data"]:
                if type(target) is not dict:
                    wire._refuse()
                if (target.get("root_job_id") == before.scope["root_job_id"]
                        and target.get("work_ref") == before.principal_context["work_ref"]):
                    if set(target) != wire._TARGET_KEYS or target.get("kind") != kind:
                        wire._refuse()
                    items.append(dict(target))
        if len(items) > wire.MAX_TARGETS:
            return wire.unavailable_targets("TARGET_BUDGET_EXCEEDED")
        return {"state": "AVAILABLE", "reason_codes": [],
            "items": sorted(items, key=lambda item: (item["kind"], item["target_ref"])),
            "scope": "ORIGINAL_EXECUTIVE_ROOT", "coverage": "CURRENT_INSTALLED_SESSION_BRIDGE"}

    targets = await current_targets()
    # Preserve actual target epoch/currentness across the composed read. A
    # changed inventory is not a successful empty list or a replacement target.
    if await current_targets() != targets:
        wire._refuse()
    current()
    after = await capture()
    if after != before or any(getattr(after, key) is not getattr(before, key) for key in (
            "source_owner", "workspace_owner", "runtime_owner", "cache_owner",
            "data_owner", "discovery_owner", "authorize_owner", "input_reader_owner")):
        wire._refuse()
    current()
    return wire.result(principal_context=before.principal_context,
        capability_profile_digest=before.capability_profile_digest,
        workspace_principal=frame["workspace_principal"], selected_scope=before.scope,
        mission_identity=after.mission_observation_sha256, plan_identity=after.plan_identity,
        mission_read=after.mission_read, targets=targets, original_execution=after.original_execution)
