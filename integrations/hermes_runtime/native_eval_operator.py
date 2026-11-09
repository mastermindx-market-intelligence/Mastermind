"""Attended consumer of the existing held native evaluation owners.

Each invocation performs one finite submit, historical read, or publication.
There is no poller, enrollment, inference runner, retry, receipt store, or
caller-supplied observation here. Recovery identity is returned to the caller.
"""
from __future__ import annotations

import asyncio
import copy
import re

from scripts.agent_eval import contracts
from scripts.agent_eval.store import run_path

from .errors import RuntimeRefusal
from . import native_eval_inputs as inputs
from . import native_session_control as control
from .native_eval_publication import SCHEMA as PUBLICATION_SCHEMA, _TERMINAL

SUBMIT_SCHEMA = "mastermind.hermes_native_eval_submit/v1"
RECOVERY_SCHEMA = "mastermind.hermes_native_eval_recovery/v1"
RESULT_SCHEMA = "mastermind.hermes_native_eval_operator/v1"
TRIAL_RESULT_SCHEMA = "mastermind.hermes_native_eval_trial_operator/v1"
MAX_REQUEST_BYTES = 60 * 1024
_RECOVERY = {"schema", "profile_id", "session_id", "run_id", "submission_id",
             "input_sha256", "admission_id", "evaluation_binding"}
_ADMISSION = {"admission_id", "ref", "sequence", "status", "outcome",
              "authority_epoch", "execution_generation"}
_OBSERVATION = {"schema", "status", "admission", "evaluation_binding", "answer", "successful",
                "terminal_metadata", "request_observation", "request_observation_error",
                "evaluation_inputs", "evaluation_inputs_error"}


def _refuse():
    raise RuntimeRefusal("NATIVE_EVAL_OPERATOR_CONTRACT_INVALID")


def _digest(value, *, prefixed=False):
    if type(value) is not str or re.fullmatch(
            r"sha256:[0-9a-f]{64}" if prefixed else r"[0-9a-f]{64}", value) is None:
        _refuse()
    return value


def _binding(value, run_id):
    if (type(value) is not dict or set(value) != {"run_id", "binding_sha256"}
            or value["run_id"] != run_id):
        _refuse()
    return {"run_id": run_id, "binding_sha256": _digest(value["binding_sha256"])}


def parse_request(operation, raw):
    from ops.executive_os.release_manifest import _closed_json
    if operation not in {"submit", "read", "publish", "trial"} or type(raw) is not bytes or not 0 < len(raw) <= MAX_REQUEST_BYTES:
        _refuse()
    value = _closed_json(raw)
    if type(value) is not dict:
        _refuse()
    if operation == "submit":
        if set(value) != {"schema", "session_id", "text", "evaluation"} or value["schema"] != SUBMIT_SCHEMA:
            _refuse()
        control._id(value["session_id"])
        control.input_digest(value["text"])
        spec = inputs._detach(value["evaluation"], maximum=MAX_REQUEST_BYTES)
        if type(spec) is not dict or set(spec) != inputs._REQUEST_FIELDS:
            _refuse()
        inputs.submission_id_for_run(spec["run_id"])
        inputs.render_inputs(spec["candidate_files"], spec["context_text"])
        return {**value, "evaluation": spec}
    if set(value) != _RECOVERY or value["schema"] != RECOVERY_SCHEMA:
        _refuse()
    for key in ("profile_id", "session_id"):
        control._id(value[key])
    if value["submission_id"] != inputs.submission_id_for_run(value["run_id"]):
        _refuse()
    _digest(value["input_sha256"])
    if value["admission_id"] is not None:
        control._id(value["admission_id"])
    if value["evaluation_binding"] is not None:
        value["evaluation_binding"] = _binding(value["evaluation_binding"], value["run_id"])
    return value


def recovery_for(operation, request, home):
    if operation == "submit":
        run_id = request["evaluation"]["run_id"]
        return {"schema": RECOVERY_SCHEMA, "profile_id": str(home),
                "session_id": request["session_id"], "run_id": run_id,
                "submission_id": inputs.submission_id_for_run(run_id),
                "input_sha256": control.input_digest(request["text"]),
                "admission_id": None, "evaluation_binding": None}
    if request["profile_id"] != str(home):
        _refuse()
    return copy.deepcopy(request)


def result(operation, status, *, recovery, reason=None, admission=None, publication=None, trial=None):
    value = {"schema": TRIAL_RESULT_SCHEMA if operation == "trial" else RESULT_SCHEMA,
             "operation": operation, "status": status, "reason": reason,
             "recovery": recovery, "admission": admission,
             "publication": publication, "complete_evaluation": False}
    if operation == "trial":
        value["trial"] = trial
    return value


def _envelope(value, allowed):
    if (type(value) is not dict or not {"schema", "status"} <= set(value)
            or not set(value) <= allowed
            or value["schema"] != control.conversation_contract("mmmeta").native_schema
            or type(value["status"]) is not str):
        _refuse()


def _receipt(value, recovery, home):
    if type(value) is not dict or set(value) != _ADMISSION or type(value["ref"]) is not dict:
        _refuse()
    receipt = control._admission(value, home, recovery["session_id"])
    if (recovery["admission_id"] is not None and receipt["admission_id"] != recovery["admission_id"]
            or receipt["outcome"] not in {None, "completed", "interrupted", "rejected", "failed",
                                           "cancelled", "steering", "steered"}
            or any(type(receipt[key]) is int and receipt[key] > 2**53 - 1
                   for key in ("sequence", "authority_epoch", "execution_generation"))):
        _refuse()
    return receipt


def _original(value, recovery, home, *, submitted=False):
    _envelope(value, {"schema", "status", "admission", "evaluation_binding"} if submitted else _OBSERVATION)
    if value["status"] != ("ADMITTED" if submitted else "OBSERVED"):
        _refuse()
    if not {"admission", "evaluation_binding"} <= set(value):
        _refuse()
    receipt = _receipt(value["admission"], recovery, home)
    binding = _binding(value["evaluation_binding"], recovery["run_id"])
    if recovery["evaluation_binding"] is not None and recovery["evaluation_binding"] != binding:
        _refuse()
    # Only exact public identity crosses the CLI. Answer/metadata siblings stay
    # in native storage and the original publisher reads them independently.
    return receipt, {**recovery, "admission_id": receipt["admission_id"], "evaluation_binding": binding}


def _failure(operation, value, recovery, admission=None):
    _envelope(value, {"schema", "status", "reason", "admission_id",
                      "evaluation_binding", "frozen_record_retained"})
    if value["status"] not in {"REFUSED", "NOT_SUBMITTED", "UNAVAILABLE", "EFFECT_UNKNOWN"}:
        _refuse()
    if value["status"] == "NOT_SUBMITTED" and operation != "submit":
        _refuse()
    reason = value.get("reason")
    if reason is not None and (type(reason) is not str or re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", reason) is None):
        _refuse()
    extra = set(value) - {"schema", "status", "reason"}
    if extra:
        if (extra != {"admission_id", "evaluation_binding", "frozen_record_retained"}
                or value["status"] != "REFUSED" or reason != "EVALUATION_ARTIFACT_CONFLICT"
                or value["frozen_record_retained"] is not True
                or value["admission_id"] != recovery["admission_id"]
                or value["evaluation_binding"] != recovery["evaluation_binding"]):
            _refuse()
    return result(operation, value["status"], recovery=recovery, admission=admission, reason=reason)


async def _capabilities(client, profile, home, implementation, native_launch):
    from .profile import dump_profile, profile_sha256
    recipe = native_launch.recipe
    if (type(recipe.get("evaluation_inputs")) is not dict
            or recipe["evaluation_inputs"].get("schema") != inputs.RECIPE_SCHEMA):
        _refuse()
    derivation = recipe.get("vendor_derivation")
    if type(derivation) is not dict or derivation.get("kind") != "native_eval_inputs":
        _refuse()
    expected = {
        "producer": inputs.producer_descriptor(implementation, derivation["base_sha"], derivation["patch_sha256"]),
        "profile_id": str(home), "profile_digest": "sha256:" + profile_sha256(dump_profile(profile)),
        "run_schema": contracts.RUN_SCHEMA_V3, "complete_evaluation": False,
    }
    value = await asyncio.to_thread(client.evaluation_capabilities)
    _envelope(value, {"schema", "status", "evaluation"})
    if (set(value) != {"schema", "status", "evaluation"} or value["status"] != "OBSERVED"
            or type(value["evaluation"]) is not dict or value["evaluation"] != expected
            or value["evaluation"].get("complete_evaluation") is not False):
        _refuse()


def _publication(value, recovery):
    _envelope(value, {"schema", "status", "admission_id", "evaluation_binding", "publication"})
    if (set(value) != {"schema", "status", "admission_id", "evaluation_binding", "publication"}
            or value["status"] != "PUBLISHED" or value["admission_id"] != recovery["admission_id"]
            or value["evaluation_binding"] != recovery["evaluation_binding"]):
        _refuse()
    item = value["publication"]
    if (type(item) is not dict or set(item) != {
            "schema", "disposition", "relative_path", "run_digest", "validity", "reason_codes",
            "complete_evaluation", "provider_delivery_proven", "model_identity_verified"}
            or item["schema"] != PUBLICATION_SCHEMA
            or item["disposition"] not in {"CREATED", "IDEMPOTENT"}
            or item["relative_path"] != str(run_path(recovery["run_id"]))
            or item["validity"] not in contracts._VALIDITY_STATUSES - {"VALID"}
            or any(item[key] is not False for key in (
                "complete_evaluation", "provider_delivery_proven", "model_identity_verified"))
            or type(item["reason_codes"]) is not list or not 1 <= len(item["reason_codes"]) <= 128
            or any(type(code) is not str or re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", code) is None
                   for code in item["reason_codes"])
            or len(set(item["reason_codes"])) != len(item["reason_codes"])):
        _refuse()
    _digest(item["run_digest"], prefixed=True)
    return copy.deepcopy(item)


def _trial_response(value, recovery, home, *, expected_admission):
    from .native_eval_publication import decode_trial, _trial_summary
    allowed = {"schema", "status", "admission", "evaluation_binding", "trial_summary"}
    status = value.get("status") if type(value) is dict else None
    allowed |= {"trial"} if status == "TRIAL_OBSERVED" else {"reason"}
    _envelope(value, allowed)
    if set(value) != allowed or status not in {"TRIAL_OBSERVED", "REFUSED"}:
        _refuse()
    admission = _receipt(value["admission"], recovery, home)
    binding = _binding(value["evaluation_binding"], recovery["run_id"])
    if (admission != expected_admission or binding != recovery["evaluation_binding"] or admission["status"] != "terminal"
            or admission["outcome"] not in _TERMINAL):
        _refuse()
    summary = value["trial_summary"]
    if (type(summary) is not dict or set(summary) != {
            "run_id", "run_digest", "validity", "reason_codes", "eligible_for_consumption", "eligibility_reason"}
            or summary["run_id"] != recovery["run_id"]
            or summary["validity"] not in contracts._VALIDITY_STATUSES
            or type(summary["eligible_for_consumption"]) is not bool
            or type(summary["reason_codes"]) is not list or len(summary["reason_codes"]) > 128
            or any(type(code) is not str or re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", code) is None
                   for code in summary["reason_codes"])
            or summary["reason_codes"] != sorted(set(summary["reason_codes"]))):
        _refuse()
    _digest(summary["run_digest"], prefixed=True)
    if status == "TRIAL_OBSERVED":
        trial = decode_trial(value["trial"], admission_id=admission["admission_id"], evaluation_binding=binding)
        if (trial.run["capabilities"]["profile_id"] != str(home)
                or summary != _trial_summary(trial.run, eligible=True)):
            _refuse()
    else:
        reasons = {"NATIVE_TRIAL_INVALID", "NATIVE_EFFECT_REQUIRES_RECONCILIATION",
            "NATIVE_EVAL_TRIAL_OUTPUT_NOT_RETAINED", "NATIVE_EVAL_TRIAL_OUTPUT_LIMIT",
            "NATIVE_EVAL_TRIAL_OUTPUT_INVALID", "NATIVE_EVAL_TRIAL_OUTPUT_CONFLICT",
            "NATIVE_EVAL_TRIAL_DOCUMENT_LIMIT", "NATIVE_EVAL_TRIAL_EVIDENCE_INVALID"}
        if (summary["eligible_for_consumption"] is not False
                or value["reason"] not in reasons or summary["eligibility_reason"] != value["reason"]
                or value["reason"] == "NATIVE_TRIAL_INVALID" and summary["validity"] == "VALID"):
            _refuse()
    return admission, copy.deepcopy(summary)


async def execute(operation, request, *, recovery, profile, home, implementation, native_launch, connected):
    entered, admission = False, None
    recovery = copy.deepcopy(recovery)
    try:
        async with connected() as (client, before, owner):
            async def current():
                if await owner() != before:
                    raise RuntimeRefusal("NATIVE_EVAL_OPERATOR_OWNER_CHANGED")

            if operation == "submit":
                capability = control.validate_enrollment_capability(
                    native_launch.recipe.get("session_enrollment"), role="mmmeta")
                enrollment = await asyncio.to_thread(
                    client.inspect_enrollment, implementation, capability["request_id"])
                enrollment = control.validate_enrollment_result(enrollment, implementation_sha=implementation,
                    request_id=capability["request_id"], profile_id=str(home),
                    principal_id=f"uid:{native_launch.row['uid']}", role="mmmeta")
                if (enrollment["status"] != "ENROLLED"
                        or enrollment["target"]["session_id"] != recovery["session_id"]
                        or any(enrollment["target"][key] != before["endpoint"][key]
                               for key in ("profile_id", "instance_id", "authority_epoch"))):
                    return result(operation, "REFUSED", recovery=recovery, reason="ORIGINAL_ENROLLMENT_REQUIRED")
                await current()
                await _capabilities(client, profile, home, implementation, native_launch)
                observed = await asyncio.to_thread(client.observe, recovery["session_id"])
                _envelope(observed, {"schema", "status", "target"})
                if set(observed) != {"schema", "status", "target"} or observed["status"] != "TARGET":
                    _refuse()
                target = control.validate_target(observed["target"])
                if (target["session_id"] != recovery["session_id"]
                        or target["principal_id"] != f"uid:{native_launch.row['uid']}"
                        or any(target[key] != before["endpoint"][key]
                               for key in ("profile_id", "instance_id", "authority_epoch"))):
                    _refuse()
                await current()
                entered = True
                value = await asyncio.to_thread(client.submit, target, recovery["submission_id"], request["text"],
                                                evaluation=request["evaluation"])
                if type(value) is dict and value.get("status") == "ADMITTED":
                    admission, recovery = _original(value, recovery, home, submitted=True)
                    outcome = result(operation, "ADMITTED", recovery=recovery, admission=admission)
                else:
                    outcome = _failure(operation, value, recovery)
                await current()
                return outcome

            value = await asyncio.to_thread(client.read_original, session_id=recovery["session_id"],
                submission_id=recovery["submission_id"], input_sha256=recovery["input_sha256"],
                admission_id=recovery["admission_id"], evaluation_binding=recovery["evaluation_binding"])
            if type(value) is dict and value.get("status") == "OBSERVED":
                admission, recovery = _original(value, recovery, home)
            else:
                await current()
                return _failure(operation, value, recovery)
            await current()
            if operation == "read":
                return result(operation, "OBSERVED", recovery=recovery, admission=admission)
            if operation == "trial":
                if admission["status"] != "terminal" or admission["outcome"] not in _TERMINAL:
                    return result(operation, "OBSERVED", recovery=recovery, admission=admission,
                                  reason="ORIGINAL_NOT_TERMINAL")
                value = await asyncio.to_thread(client.read_evaluation_trial,
                    session_id=recovery["session_id"], submission_id=recovery["submission_id"],
                    input_sha256=recovery["input_sha256"], admission_id=recovery["admission_id"],
                    evaluation_binding=recovery["evaluation_binding"])
                await current()
                if type(value) is dict and "trial_summary" in value:
                    admission, summary = _trial_response(value, recovery, home, expected_admission=admission)
                    await current()
                    return result(operation, value["status"], recovery=recovery, admission=admission,
                        reason=value.get("reason"), trial=summary)
                return _failure(operation, value, recovery, admission)
            if admission["status"] != "terminal" or admission["outcome"] not in _TERMINAL:
                return result(operation, "OBSERVED", recovery=recovery, admission=admission,
                              reason="ORIGINAL_NOT_PUBLISHABLE")
            # Historical publication deliberately does not inspect or change
            # today's enrollment. The original session/binding remains fixed.
            await _capabilities(client, profile, home, implementation, native_launch)
            await current()
            entered = True
            value = await asyncio.to_thread(client.publish_evaluation, session_id=recovery["session_id"],
                submission_id=recovery["submission_id"], input_sha256=recovery["input_sha256"],
                admission_id=recovery["admission_id"], evaluation_binding=recovery["evaluation_binding"])
            if type(value) is dict and value.get("status") == "PUBLISHED":
                published = _publication(value, recovery)
                outcome = result(operation, "PUBLISHED", recovery=recovery, admission=admission, publication=published)
            else:
                outcome = _failure(operation, value, recovery, admission)
            await current()
            return outcome
    except Exception:
        return result(operation, "EFFECT_UNKNOWN" if entered else "UNAVAILABLE",
            recovery=recovery, admission=admission,
            reason="ORIGINAL_ADMISSION_RECONCILIATION_REQUIRED" if entered and operation == "submit"
            else "ORIGINAL_PUBLICATION_RECONCILIATION_REQUIRED" if entered
            else "EVALUATION_OPERATOR_UNAVAILABLE")
