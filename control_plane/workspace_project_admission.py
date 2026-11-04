"""Fixed project-admission reads/actions over existing owners, with no state store.

READ membership supplies identity only. The sealed v4 singleton-project grant,
actual root creation association, and existing source/currentness guards remain
mandatory. There is no cancellation, provider or host-collector path.
"""
from __future__ import annotations

import hashlib
import time

from common import executive_workspace_contract as workspace
from common import workspace_project_admission_contract as wire
from common.workspace_project_admission_contract import OPERATION as PROJECT_SUSPEND_ACTION
from common.workspace_project_resumption_contract import OPERATION as PROJECT_RESUME_ACTION
from control_plane.workspace_project_permission_binding import ProjectAdmissionPermissions


class _AdmissionRefused(Exception):
    def __init__(self, reason):
        self.reason = reason


def _project_context(service, checked, *, permissions, host_ready, now, action=PROJECT_SUSPEND_ACTION):
    from control_plane.executive_runtime import Runtime, JobRegistry
    from control_plane.workspace_read_service import WorkspaceReadService, _retained_root_join, _qualified_retained_root, _plan_validity_identity
    from control_plane.workspace_autonomy_policy_adapter import _same_source
    if type(service) is not WorkspaceReadService:
        raise ValueError("existing Workspace owner required")
    selected, principal = checked["selection"], checked["principal"]
    pair = {key: selected[key] for key in ("work_ref", "root_job_id") if key in selected}
    read_authorize, cache, runtime, identity = service.authorize, service.cache, service.runtime, service.runtime_identity
    if type(runtime) is not Runtime:
        raise _AdmissionRefused("OWNER_NOT_READY")
    jobs, store = runtime.jobs, runtime.store
    if (type(jobs) is not JobRegistry or jobs.store is not store
            or not all(callable(value) for value in (host_ready, now))
            or type(permissions) is not ProjectAdmissionPermissions):
        raise _AdmissionRefused("OWNER_NOT_READY")
    # A current READ shares source qualification across its two independent
    # grants. Each action keeps its own authorizer and permission stamp.
    if type(action) is str and action in (PROJECT_SUSPEND_ACTION, PROJECT_RESUME_ACTION):
        actions = (action,)
    elif action == (PROJECT_SUSPEND_ACTION, PROJECT_RESUME_ACTION):
        actions = action
    else:
        raise _AdmissionRefused("ACCESS_DENIED")
    try:
        action_authorizers = {name: permissions.authorizer(action=name, work_ref=selected["work_ref"]) for name in actions}
    except Exception:
        raise _AdmissionRefused("ACCESS_DENIED") from None

    def permission():
        try:
            permissions.check()
            if service.authorize is not read_authorize or read_authorize(principal) is not True:
                raise _AdmissionRefused("ACCESS_DENIED")
            first = workspace.permission_stamp(read_authorize, principal)
            stamps = []
            for name, authorize in action_authorizers.items():
                allowed = authorize(principal) is True
                stamp = workspace.permission_stamp(authorize, principal) if allowed else None
                if allowed and stamp is None:
                    raise _AdmissionRefused("ACCESS_DENIED")
                stamps.append((name, stamp))
            if first is None or not any(stamp is not None for _, stamp in stamps):
                raise _AdmissionRefused("ACCESS_DENIED")
            permissions.check()
            return first, tuple(stamps)
        except _AdmissionRefused:
            raise
        except Exception:
            raise _AdmissionRefused("ACCESS_DENIED") from None

    expected_permission, expected_identity = permission(), workspace.digest(identity)
    before = cache.snapshot()
    plan_reader = service._project_plan_reader
    expected_project = None
    if "root_job_id" not in selected:
        # Existing canonical Agent OS reader, not a bare work-ref or UI flag.
        from common.workspace_project_plan_contract import validate_body, validate_source
        try:
            project = validate_body(service._read_project_plan(pair))
            if project["availability"] != "AVAILABLE" or project["selection"] != {"work_ref": pair["work_ref"]}:
                raise _AdmissionRefused("SOURCE_UNAVAILABLE")
            expected_project = validate_source(project["source"], pair["work_ref"])
        except _AdmissionRefused:
            raise
        except Exception:
            raise _AdmissionRefused("SOURCE_UNAVAILABLE") from None

    def identity_guard():
        if (service.cache is not cache or service.runtime is not runtime or runtime.jobs is not jobs
                or runtime.store is not store or jobs.store is not store or service.runtime_identity is not identity
                or workspace.digest(identity) != expected_identity or service._project_admission_permissions is not permissions):
            raise _AdmissionRefused("SOURCE_CHANGED")

    def guard(*, recheck_project=True):
        identity_guard()
        if permission() != expected_permission:
            raise _AdmissionRefused("ACCESS_DENIED")
        try:
            current_time = now()
            if (type(current_time) not in (int, float) or not 0 <= current_time < checked["admission_expires_at"]
                    or host_ready() is not True):
                raise _AdmissionRefused("OWNER_NOT_READY")
            current = cache.snapshot()
            if not _same_source(before, current, _plan_validity_identity):
                raise _AdmissionRefused("SOURCE_CHANGED")
            if "root_job_id" in selected:
                _retained_root_join(current.document, pair)
                if not _qualified_retained_root(current, pair):
                    raise _AdmissionRefused("SOURCE_UNAVAILABLE")
                if jobs.admission_workstream_for_root(selected["root_job_id"]) != selected["work_ref"]:
                    raise _AdmissionRefused("ROOT_MISMATCH")
            else:
                if service._project_plan_reader is not plan_reader:
                    raise _AdmissionRefused("SOURCE_CHANGED")
                if recheck_project:
                    project = validate_body(service._read_project_plan(pair))
                    if (project["availability"] != "AVAILABLE" or project["selection"] != {"work_ref": pair["work_ref"]}
                            or validate_source(project["source"], pair["work_ref"]) != expected_project):
                        raise _AdmissionRefused("SOURCE_CHANGED")
                # Full captures bracket their own publication; interim READ
                # fences still verify the same request-local cache/owner proof.
                after_project = cache.snapshot()
                if not _same_source(before, after_project, _plan_validity_identity):
                    raise _AdmissionRefused("SOURCE_CHANGED")
            identity_guard()
            if permission() != expected_permission:
                raise _AdmissionRefused("ACCESS_DENIED")
            if not 0 <= now() < checked["admission_expires_at"] or host_ready() is not True:
                raise _AdmissionRefused("OWNER_NOT_READY")
        except _AdmissionRefused:
            raise
        except LookupError:
            raise _AdmissionRefused("ROOT_MISMATCH") from None
        except Exception:
            raise _AdmissionRefused("SOURCE_UNAVAILABLE") from None

    # Both IDs are opaque derivations of verified identity/selection. Neither is
    # an authority token; every request rechecks the actual sealed grant.
    actor = "workspace:" + hashlib.sha256(workspace.canonical(principal)).hexdigest()
    target = "project_admission:" + workspace.digest({"principal": principal, "selection": pair})
    # The initial sealed capture has just completed; this fence rechecks its
    # permission/cache/owner bracket without capturing the same source again.
    guard(recheck_project=False)
    granted_actions = frozenset(name for name, stamp in expected_permission[1] if stamp is not None)
    return jobs, actor, target, guard, granted_actions


def project_admission_request(service, frame, *, permissions,
                              host_ready, now=time.time, status=False, resume=False):
    """Action or exact original-command status; no automatic retry or replacement."""
    from common import workspace_project_resumption_contract as resume_wire
    action_wire = resume_wire if resume else wire
    try:
        checked = action_wire.validate_frame(frame, status=status)
    except (TypeError, ValueError):
        return workspace.error("invalid_input", 400)
    selected, attempted = checked["selection"], False

    def result(reason=None, receipt=None, *, observed=False):
        if status:
            body = {"schema": action_wire.STATUS_RESULT_SCHEMA, "selection": dict(selected),
                "state": "UNAVAILABLE" if reason else "OBSERVED" if observed else "NOT_OBSERVED",
                "receipt": receipt, "reason_codes": [] if reason is None else [reason]}
            return {"ok": True, "result": action_wire.validate_status_result(body, selected)}
        disposition = "COMMITTED" if receipt is not None else "EFFECT_UNKNOWN" if attempted else "NOT_DISPATCHED"
        if disposition == "EFFECT_UNKNOWN":
            reason = "OWNER_OUTCOME_UNCONFIRMED"
        body = {"schema": action_wire.ACTION_RESULT_SCHEMA, "selection": dict(selected),
            "disposition": disposition, "receipt": receipt, "reason_codes": [] if reason is None else [reason]}
        return {"ok": True, "result": action_wire.validate_action_result(body, selected)}

    try:
        jobs, actor, _target, guard, _grants = _project_context(service, checked, permissions=permissions,
            host_ready=host_ready, now=now,
            action=PROJECT_RESUME_ACTION if resume else PROJECT_SUSPEND_ACTION)
        if status:
            reader = jobs.read_workstream_admission_resume_command if resume else jobs.read_workstream_admission_pause_command
            receipt = reader(selected["work_ref"],
                command_id=selected["command_id"], actor=actor)
            guard()
            return result(receipt=receipt, observed=receipt is not None)
        attempted = True
        if resume:
            token = checked["pause_token"]
            receipt = jobs.resume_workstream_admission(selected["work_ref"],
                command_id=selected["command_id"], actor=actor, expected_pause_event_id=token["event_id"],
                expected_pause_receipt_digest=token["receipt_digest"], _commit_guard=guard)
        else:
            receipt = jobs.pause_workstream_admission(selected["work_ref"],
                command_id=selected["command_id"], actor=actor, _commit_guard=guard)
        # A denial or transport failure after the owner invocation can follow
        # COMMIT; withhold the receipt and retain its original command identity.
        guard()
        return result(receipt=receipt)
    except _AdmissionRefused as exc:
        return result(exc.reason)
    except Exception:
        return result("SOURCE_UNAVAILABLE")


def read_project_admission_state(service, frame, *, permissions, host_ready, now=time.time):
    """Qualified current gate/capability read; it never reconciles an action."""
    from common import workspace_project_admission_state_contract as state_wire
    try:
        checked = state_wire.validate_frame(frame)
    except (TypeError, ValueError):
        return workspace.error("invalid_input", 400)
    selected = checked["selection"]

    def result(reason=None, receipt=None, target=None):
        body = {"schema": state_wire.BODY_SCHEMA, "selection": dict(selected),
            "availability": "AVAILABLE" if reason is None else "UNAVAILABLE",
            "state": ("PAUSED" if receipt is not None else "NOT_SUSPENDED") if reason is None else None,
            "capability": ({"operation": PROJECT_SUSPEND_ACTION, "target_ref": target, "can_pause": receipt is None}
                           if reason is None else None),
            "current_receipt": receipt, "reason_codes": [] if reason is None else [reason]}
        # This owner contract validates by producing the bounded canonical
        # envelope bytes. The existing socket handler owns serialization;
        # return our freshly built body after that complete validation.
        state_wire.validate_body(body, selected)
        return {"ok": True, "result": body}

    try:
        jobs, _actor, target, guard, _grants = _project_context(service, checked, permissions=permissions,
            host_ready=host_ready, now=now)
        first = jobs.read_workstream_admission_suspension(selected["work_ref"])
        guard()
        second = jobs.read_workstream_admission_suspension(selected["work_ref"])
        guard()
        if first != second:
            raise _AdmissionRefused("SOURCE_CHANGED")
        return result(receipt=second, target=target)
    except _AdmissionRefused as exc:
        return result(exc.reason)
    except Exception:
        return result("SOURCE_UNAVAILABLE")


def read_project_admission_control(service, frame, *, permissions, host_ready, now=time.time):
    """Independently qualified Pause/Resume grants and actual current gate.

    One grant cannot promote its sibling. Rootless requests require the actual
    canonical project reader; an explicit root adds retained provenance proof.
    """
    from common import workspace_project_admission_control_contract as control
    from control_plane.workstream_resumption_contract import pause_receipt_digest
    try:
        checked = control.validate_frame(frame)
    except (TypeError, ValueError):
        return workspace.error("invalid_input", 400)
    selected = checked["selection"]

    def result(reason=None, *, receipt=None, permissions=None, scope=None):
        body = {"schema": control.BODY_SCHEMA, "selection": dict(selected),
            "availability": "AVAILABLE" if reason is None else "UNAVAILABLE",
            "state": (receipt["state"] if receipt else "NOT_SUSPENDED") if reason is None else None,
            "permissions": permissions, "owner_context": {"principal_scope": scope} if scope is not None else None,
            "current_receipt": receipt,
            "pause_token": ({"event_id": receipt["event_id"], "receipt_digest": pause_receipt_digest(receipt)}
                            if receipt is not None and receipt["state"] == "PAUSED" else None),
            "reason_codes": [] if reason is None else [reason]}
        return {"ok": True, "result": control.validate_body(body, selected)}
    try:
        jobs, actor, _target, guard, grants = _project_context(service, checked, permissions=permissions,
            host_ready=host_ready, now=now,
            action=(PROJECT_SUSPEND_ACTION, PROJECT_RESUME_ACTION))
        guard(recheck_project=False)
        first = jobs.read_workstream_admission_transition(selected["work_ref"])
        guard(recheck_project=False)
        second = jobs.read_workstream_admission_transition(selected["work_ref"])
        # One final fresh sealed source capture brackets the observations. The
        # proof is request-local; action/commit guards retain their fresh reads.
        guard()
        if first != second:
            raise _AdmissionRefused("SOURCE_CHANGED")
        return result(receipt=second, permissions={"pause": PROJECT_SUSPEND_ACTION in grants,
            "resume": PROJECT_RESUME_ACTION in grants}, scope=actor.removeprefix("workspace:"))
    except _AdmissionRefused as exc:
        return result(exc.reason)
    except Exception:
        return result("SOURCE_UNAVAILABLE")
