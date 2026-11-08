"""Finalize one original native admission through the existing EVAL store.

The original admission/tombstone freezes the publication bytes. It does not
claim filesystem publication success. Reconciliation always sends those same
bytes through ArtifactStore's create-only durability and readback barrier.
No inference, enrollment, retry queue, result envelope or second store exists
here. Historical producer identity is distinct from today's finalizer.
"""
from __future__ import annotations

import copy
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import re

from scripts.agent_eval import contracts
from scripts.agent_eval.canonical import canonical_json_bytes, digest_value
from scripts.agent_eval.errors import ArtifactConflictError, ContractError
from scripts.agent_eval.privacy import assert_public_safe_evidence
from scripts.agent_eval.validity import evaluate_validity, finalize_run_receipt
from scripts.agent_eval.verification import closed_input_resolver, verify_run_graph

from .errors import RuntimeRefusal

SCHEMA = "mastermind.hermes_native_eval_publication/v1"
MAX_PUBLICATION_BYTES = 64 * 1024
TRIAL_SCHEMA = "mastermind.hermes_native_eval_trial/v1"
MAX_TRIAL_BYTES = 256 * 1024
MAX_RETAINED_RESULT_BYTES = 2 * 1024 * 1024
VALIDATOR_ID = "mastermind.hermes_native_eval_finalizer"
VALIDATOR_VERSION = "1"
_TERMINAL = {
    "completed": ("COMPLETED", "NATIVE_COMPLETED"),
    "failed": ("FAILED", "NATIVE_FAILED"),
    "cancelled": ("CANCELLED", "NATIVE_CANCELLED"),
    # Failure of the selected execution, not a claim that the user cancelled it.
    "interrupted": ("FAILED", "NATIVE_INTERRUPTED"),
    "rejected": ("FAILED", "NATIVE_REJECTED"),
}
_FIELDS = frozenset({"schema", "admission_id", "native_outcome", "binding_sha256", "run_id", "run_digest",
                     "producer", "publication", "run"})


class PublicationEffectUnknown(RuntimeRefusal):
    """Only the original freeze/artifact may need reconciliation; no new run."""

    def __init__(self):
        super().__init__("NATIVE_EVAL_PUBLICATION_RECONCILIATION_REQUIRED")


def _refuse(code):
    raise RuntimeRefusal("NATIVE_EVAL_" + code)


def _detached(value):
    raw = canonical_json_bytes(value)
    if len(raw) > MAX_PUBLICATION_BYTES:
        _refuse("PUBLICATION_LIMIT")
    assert_public_safe_evidence(value)
    return json.loads(raw)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scenario_ref(marker):
    scenario = marker["scenario"]
    return {**{key: scenario[key] for key in (
        "scenario_id", "scenario_version", "scenario_digest", "corpus_revision")},
        "temporal_cutoff": scenario["temporal"]["cutoff_at"]}


def _configuration_ref(marker):
    return {key: marker["configuration"][key] for key in ("configuration_id", "configuration_digest")}


def _context(marker):
    return {"source_policy_digest": digest_value(marker["scenario"]["source_policy"]),
            **copy.deepcopy(marker["configuration"]["context"])}


def _original_ref(marker, receipt):
    # A locator for the existing private result, not a new retained answer.
    return "native-admission:" + digest_value({"admission_id": receipt["admission_id"],
        "binding_sha256": marker["binding_sha256"]})


def _utc_ms(value):
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value // 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OverflowError, OSError):
        return None


def _request(params, home, *, operation="publish_evaluation"):
    from .native_session_control import _id
    if (type(params) is not dict or set(params) != {
            "operation", "profile_id", "session_id", "submission_id", "input_sha256",
            "admission_id", "evaluation_binding"}
            or operation not in {"publish_evaluation", "read_evaluation_trial"}
            or params["operation"] != operation or params["profile_id"] != str(home)):
        _refuse("PUBLICATION_REQUEST_INVALID")
    for key in ("session_id", "submission_id", "admission_id"):
        _id(params[key])
    expected = params["evaluation_binding"]
    if (type(expected) is not dict or set(expected) != {"run_id", "binding_sha256"}
            or any(type(value) is not str for value in expected.values())
            or re.fullmatch(r"[0-9a-f]{64}", expected["binding_sha256"]) is None
            or type(params["input_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", params["input_sha256"]) is None):
        _refuse("PUBLICATION_REQUEST_INVALID")
    try:
        contracts.parse_run_id(expected["run_id"])
    except ContractError:
        _refuse("PUBLICATION_REQUEST_INVALID")
    return json.loads(canonical_json_bytes(params))


def _selected_owner(runner, home, owner):
    from .native_eval_inputs import NativeEvalInputOwner
    if type(owner) is not NativeEvalInputOwner or owner.profile_id != str(home):
        _refuse("PUBLICATION_OWNER_UNAVAILABLE")
    owner.check()
    authority = owner.binding.authority
    if authority is None or authority is not runner.session_authority or authority.profile_id != str(home):
        _refuse("PUBLICATION_OWNER_CHANGED")
    if type(authority.epoch) is not int or authority.epoch < 1:
        _refuse("PUBLICATION_OWNER_CHANGED")
    return authority


def _original(conn, params, principal, home, owner):
    from hermes_state_runtime import _admission, _row
    from .native_eval_inputs import MARKER_SCHEMA
    from .native_session_control import _original_binding
    raw = dict(_admission(conn, params["admission_id"]))
    receipt, marker = _original_binding(home, params, principal, _row(raw))
    # A raw terminal/steering row can still be requeued by the original owner.
    # Steered is another claim's execution. Neither can become a frozen run.
    if receipt["status"] != "terminal" or receipt["outcome"] not in _TERMINAL:
        _refuse("PUBLICATION_TERMINAL_REQUIRED")
    if marker is None or marker["schema"] != MARKER_SCHEMA:
        _refuse("PUBLICATION_PROVENANCE_NOT_RETAINED")
    if marker["publication"] != owner.publication:
        _refuse("PUBLICATION_ORIGINAL_STORE_REQUIRED")
    return raw, receipt, marker


def _wire_observations(draft, unavailable, observation, marker, selected_inputs):
    transport = observation.get("transport")
    if not isinstance(transport, dict):
        return
    execution = transport["execution"]
    process = execution["process_start"]
    if (transport["installation"]["status"] == "qualified" and execution["same_process"] is True
            and process["status"] == "observed" and process["facts"]["release_sha"] == marker["source"]["release"]):
        draft["execution"]["process_fingerprint"] = "sha256:" + process["fingerprint"]
    elif (execution["same_process"] is False or process["status"] == "observed"
          and process["facts"]["release_sha"] != marker["source"]["release"]):
        unavailable["execution.process_fingerprint"] = "OBSERVATION_CONFLICT"
    for source, target in (("started_at_ms", "started_at"), ("finished_at_ms", "completed_at")):
        draft["timing"][target] = _utc_ms(execution[source])
    draft["timing"]["monotonic_duration_ms"] = execution["duration_ms"]
    draft["resources"]["elapsed_ms"] = execution["duration_ms"]
    from .native_transport_observation import APPLICATION_SCHEMA
    application_observed = transport["schema"] == APPLICATION_SCHEMA
    application_attempts = transport["application_attempts"] if application_observed else []
    if transport["attempts"] or application_attempts:
        draft["observation_availability"]["coverage"]["provider_requests"] = {
            "status": "PARTIAL", "reason": "OBSERVATION_LIMIT"}
    # Scalar observations must cover every retained logical call and dispatch,
    # with no lost instrumentation record, unsupported route or in-flight span.
    calls, dispatches = transport["calls"], transport["dispatches"]
    http_attempts = transport["attempts"]
    attempts = [*http_attempts, *application_attempts]
    if (transport["installation"]["status"] != "qualified" or transport["overflow"]
            or transport["errors"] or observation["overflow"] or observation["errors"]
            or observation.get("metadata_overflow") or not calls or not dispatches or not attempts
            or any(row["state"] == "entered" or row["invalid_fields"] for row in (*calls, *dispatches))
            or any(row["state"] == "entered" or row["request"]["body_state"] != "observed_json_object"
                   for row in http_attempts)
            or any(row["state"] != "returned" or row["response"] is None for row in application_attempts)
            or application_observed and any(row["state"] != "headers_returned" for row in http_attempts)
            or {row["call_sequence"] for row in dispatches} != {row["sequence"] for row in calls}
            or {row["dispatch_sequence"] for row in attempts} != {row["sequence"] for row in dispatches}
            or any(row["client_binding"] not in ({"qualified_sync_httpx", "qualified_application"}
                   if application_observed else {"qualified_sync_httpx"}) for row in dispatches)
            or selected_inputs is None or selected_inputs["errors"]):
        return
    # Native API retries can reuse api_request_id while rebuilding content.
    # Join the full original identity and counters, then both content hashes;
    # a subset join or request ID alone would mix distinct attempts.
    key_fields = ("agent_session_id", "turn_id", "api_request_id", "api_call_count", "retry_count")
    indexed = {}
    for event in observation["observations"]:
        if event.get("invalid_fields") or any(key not in event for key in key_fields):
            return
        key = tuple(event[name] for name in key_fields)
        if key in indexed:
            return
        indexed[key] = event
    matched = {}
    for call in calls:
        key = tuple(call["identity"].get(name) if name in {
            "agent_session_id", "turn_id", "api_request_id"} else call[name] for name in key_fields)
        if None in key or key not in indexed or key in matched:
            return
        matched[key] = indexed[key]
    if set(matched) != set(indexed):
        return
    from .native_eval_inputs import RESULT_SCHEMA as CURRENT_INPUT_OBSERVATION, STRONG_RESULT_SCHEMAS
    content_fields = (("agent_session_id", "turn_id", "api_request_id", "api_call_count", "retry_count", "content_sha256")
                      if selected_inputs["schema"] in STRONG_RESULT_SCHEMAS
                      else ("turn_id", "api_request_id", "content_sha256"))
    if Counter(tuple(row[key] for key in content_fields) for row in selected_inputs["assemblies"]) != Counter(
            tuple(row[key] for key in content_fields) for row in indexed.values()):
        return
    for attempt in attempts:
        dispatch = dispatches[attempt["dispatch_sequence"] - 1]
        call = calls[dispatch["call_sequence"] - 1]
        key = tuple(call["identity"].get(name) if name in {
            "agent_session_id", "turn_id", "api_request_id"} else call[name] for name in key_fields)
        event = indexed[key]
        if (attempt["request"]["content_sha256"] != event["content_sha256"]
                or attempt["request"]["content_fields"] != event["fields"]):
            return
    from .native_transport_observation import SCHEMA as CURRENT_TRANSPORT_OBSERVATION, PROVIDER_SCHEMAS
    if transport["schema"] in PROVIDER_SCHEMAS or application_observed:
        # Identify the frozen public runtime selector only when its label
        # matched samples at dispatch, original factory return and every
        # retained HTTP-send boundary. This does not attest factory inputs,
        # client endpoint configuration, remote identity or delivery.
        selected_provider = marker["configuration"]["execution"]["provider"]
        provider_bytes = selected_provider.encode("utf-8")
        expected_provider = {"status": "observed_digest",
            "sha256": hashlib.sha256(provider_bytes).hexdigest(), "bytes": len(provider_bytes)}
        witnesses = [row["runtime_provider"] for row in (*dispatches, *attempts)]
        if (any(row["provider_client_check"] == "conflicting" for row in dispatches)
                or any(item["status"] == "observed_digest" and item != expected_provider for item in witnesses)):
            unavailable["execution.provider"] = "OBSERVATION_CONFLICT"
        elif (all(row["provider_client_check"] == "matched" for row in dispatches)
                and all(item == expected_provider for item in witnesses)):
            draft["execution"]["provider"] = selected_provider
    if transport["schema"] == CURRENT_TRANSPORT_OBSERVATION:
        # A closed nonsecret mechanism from the original credential/client/send
        # chain. No account, exact realm, remote acceptance or delivery claim.
        checks = [row["auth_client_check"] for row in dispatches]
        mechanisms = [row["auth_mechanism"] for row in attempts]
        selected_auth = marker["configuration"]["execution"]["auth_realm_class"]
        if ("conflicting" in checks or "conflicting" in mechanisms
                or (all(value == "API_KEY" for value in mechanisms) and selected_auth != "API_KEY")):
            unavailable["execution.auth_realm_class"] = "OBSERVATION_CONFLICT"
        elif (selected_auth == "API_KEY" and all(value == "matched" for value in checks)
                and all(value == "API_KEY" for value in mechanisms)):
            draft["execution"]["auth_realm_class"] = "API_KEY"
    physical_ids = {row["identity"].get("agent_session_id") for row in calls}
    if len(physical_ids) == 1:
        draft["execution"]["native_session_fingerprint"] = digest_value([
            marker["source"]["profile_id"], next(iter(physical_ids))])
    else:
        unavailable["execution.native_session_fingerprint"] = "OBSERVATION_CONFLICT"
    if selected_inputs["schema"] == CURRENT_INPUT_OBSERVATION and len(physical_ids) == 1:
        # Every retained request must join the same original history-adoption
        # witness through its delivery. Empty history is not freshness evidence.
        histories = {row["sequence"]: row for row in selected_inputs["histories"]}
        deliveries = {row["sequence"]: row for row in selected_inputs["deliveries"]}
        joined = [histories.get(deliveries[row["delivery_sequence"]]["history_sequence"])
                  for row in selected_inputs["assemblies"]]
        if joined and all(row is not None and row["conversation_rows"] > 0
                          and row["agent_session_id"] in physical_ids for row in joined):
            draft["execution"]["resume_used"] = True
            draft["execution"]["fresh_session_observed"] = False
    requests = [row["request"] for row in attempts]

    def uniform(path, values):
        group, key = path.split(".")
        if None in values:
            return
        unique = {canonical_json_bytes(item) for item in values}
        if len(unique) != 1:
            unavailable[path] = "OBSERVATION_CONFLICT"
        else:
            draft[group][key] = values[0]

    for field, path in (("seed", "randomness.seed"), ("reasoning_effort", "execution.reasoning_effort")):
        uniform(path, [row[field].get("value") if row.get(field, {}).get("status") == "present"
            and (field != "reasoning_effort" or row[field]["value"] in {"low", "medium", "high"})
            else None for row in requests])
    # Explicit wire sampling excludes implicit SDK/provider defaults. Retain
    # its measured digest in trace; do not relabel it as effective sampling.
    # A configured public label can identify an observed request only when its
    # actual wire bytes match. Differing or absent labels remain unavailable.
    selected = draft.pop("_selected_model")
    raw = selected.encode("utf-8")
    expected = {"status": "observed_digest", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    if all(row["model"] == expected for row in requests):
        draft["execution"]["model_requested"] = selected
    elif any(row["model"]["status"] == "observed_digest" and row["model"] != expected for row in requests):
        unavailable["execution.model_requested"] = "OBSERVATION_CONFLICT"
    # APPLICATION request content is an entry snapshot, not an independently
    # verified owner-wire request. Its source-qualified owner receipt remains
    # separately retained in trace, including original/routed commitments.
    # A response-reported label is not verified serving-model identity.


def _build_run(marker, receipt, projected, *, finalizer_ref, now, missing_reason):
    from .native_eval_inputs import STRONG_RESULT_SCHEMAS, observed_record_sources
    scenario, config = marker["scenario"], marker["configuration"]
    completion, reason = _TERMINAL[receipt["outcome"]]
    if (receipt["outcome"] == "completed"
            and projected.get("terminal_metadata", {}).get("reported", {}).get("partial") is True):
        completion, reason = "PARTIAL", "NATIVE_PARTIAL"
    unavailable = {path: missing_reason for path in contracts.RUN_OBSERVATION_PATHS}
    coverage = {key: {"status": "UNOBSERVED", "reason": missing_reason}
                for key in contracts.RUN_OBSERVATION_COVERAGE_KEYS}
    draft = {
        "schema": contracts.RUN_DRAFT_SCHEMA_V3, "run_id": marker["run_id"],
        "scenario": _scenario_ref(marker), "configuration": _configuration_ref(marker),
        "comparison": copy.deepcopy(marker["comparison"]),
        "execution": {**copy.deepcopy(marker["producer"]),
            **{key: None for key in contracts.RUN_OBSERVATION_NULLABLE_FIELDS["execution"]},
            "completion_status": completion, "termination_reason": reason},
        "procedure": copy.deepcopy(config["procedure"]), "context": _context(marker),
        "observations": {key: [] for key in (
            "observed_sources", "observed_capability_ids", "observed_tool_schema_digests",
            "observed_network_destinations", "dependency_degradations")},
        "capabilities": {"profile_id": marker["source"]["profile_id"],
            "profile_digest": marker["source"]["profile_digest"],
            **{key: None for key in contracts.RUN_OBSERVATION_NULLABLE_FIELDS["capabilities"]}},
        "randomness": {"seed": None, "sampling_parameters_digest": None},
        "effect": {"state": "EFFECT_UNKNOWN", "operation_ref": _original_ref(marker, receipt),
                   "reconciliation_ref": None},
        "cleanup": {"status": "UNPROVEN", "proof": None},
        "evidence": {"output": None, "tool_events": None, "trace": None, "artifacts": []},
        "resources": {key: None for key in ("input_tokens", "output_tokens", "tool_calls", "elapsed_ms",
            "provider_usage_ref", "estimated_marginal_cost", "cost_currency")},
        "timing": {"started_at": None, "completed_at": None, "monotonic_duration_ms": None},
        "observation_availability": {"unavailable": [], "coverage": coverage},
    }
    ref = _original_ref(marker, receipt)
    output = projected.get("terminal_metadata", {}).get("output")
    if output is not None:
        draft["evidence"]["output"] = {"artifact_ref": ref + "#final_response", "digest": "sha256:" + output["sha256"]}
    observation = projected.get("request_observation")
    if observation is not None:
        draft["evidence"]["trace"] = {"artifact_ref": ref + "#request_observation", "digest": digest_value(observation)}
        if "executions" in observation:
            tool_projection = {key: observation[key] for key in (
                "tools_stage", "tool_coverage", "executions", "commits", "tool_overflow", "metadata_overflow")}
            draft["evidence"]["tool_events"] = {"artifact_ref": ref + "#tool_observations",
                                                 "digest": digest_value(tool_projection)}
            coverage["tool_events"] = {"status": "PARTIAL", "reason": "OBSERVATION_LIMIT"}
        draft["_selected_model"] = config["execution"]["model_requested"]
        _wire_observations(draft, unavailable, observation, marker, projected.get("evaluation_inputs"))
        draft.pop("_selected_model", None)
    elif "request_observation_error" in projected:
        for path in unavailable:
            if path != "evidence.output":
                unavailable[path] = "OBSERVATION_CONFLICT"
    selected = projected.get("evaluation_inputs")
    if selected is not None:
        if selected["deliveries"]:
            for key in ("procedure_delivery", "context_delivery"):
                coverage[key] = {"status": "PARTIAL", "reason": "OBSERVATION_LIMIT"}
        digests = sorted({value for row in selected["assemblies"] for value in row["tool_schema_digests"]})
        draft["observations"]["observed_tool_schema_digests"] = digests
        if selected["assemblies"]:
            coverage["observed_tool_schema_digests"] = {"status": "PARTIAL", "reason": "OBSERVATION_LIMIT"}
            if selected["schema"] in STRONG_RESULT_SCHEMAS:
                draft["observations"]["observed_sources"] = observed_record_sources(selected)
                coverage["observed_sources"] = {"status": "PARTIAL", "reason": "OBSERVATION_LIMIT"}
    timing = draft["timing"]
    wall_conflict = any(timing[key] is not None and timing[key] > now for key in ("started_at", "completed_at"))
    wall_conflict = wall_conflict or (timing["started_at"] is not None and timing["completed_at"] is not None
                                    and timing["started_at"] > timing["completed_at"])
    if observation is not None:
        transport = observation.get("transport", {})
        wall_conflict = wall_conflict or "clock_regression" in transport.get("errors", [])
        for source, target in (("started_at_ms", "started_at"), ("finished_at_ms", "completed_at")):
            if transport.get("execution", {}).get(source) is not None and timing[target] is None:
                unavailable["timing." + target] = "OBSERVATION_CONFLICT"
    if wall_conflict:
        for key in ("started_at", "completed_at"):
            timing[key] = None
            unavailable["timing." + key] = "OBSERVATION_CONFLICT"
    # Keep valid monotonic duration independently. Never advance the actual
    # finalization clock to make contradictory execution wall times fit.
    # Loss or incomplete coverage never becomes evidence of zero capabilities,
    # no network, a fresh session, no effects or completed cleanup.
    draft["observation_availability"]["unavailable"] = [
        {"path": path, "reason": unavailable[path]} for path in sorted(unavailable)
        if draft[path.split(".")[0]][path.split(".")[1]] is None]
    return finalize_run_receipt(scenario, config, marker["experiment"], draft,
        validator_id=VALIDATOR_ID, validator_version=VALIDATOR_VERSION,
        validator_code_ref=finalizer_ref, validated_at=now, created_at=now)


def _validate_record(value, marker, receipt):
    value = _detached(value)
    expected = {"schema": SCHEMA, "admission_id": receipt["admission_id"], "native_outcome": receipt["outcome"],
        "binding_sha256": marker["binding_sha256"], "run_id": marker["run_id"],
        "producer": marker["producer"], "publication": marker["publication"]}
    if (type(value) is not dict or set(value) != _FIELDS
            or any(value[key] != item for key, item in expected.items())):
        _refuse("PUBLICATION_RECORD_MISMATCH")
    run, config = value["run"], marker["configuration"]
    contracts.validate_run_shape(run)
    if (run["schema"] not in {contracts.RUN_SCHEMA_V2, contracts.RUN_SCHEMA_V3} or run["run_id"] != marker["run_id"]
            or run["run_digest"] != value["run_digest"] or run["scenario"] != _scenario_ref(marker)
            or run["configuration"] != _configuration_ref(marker) or run["comparison"] != marker["comparison"]
            or run["procedure"] != config["procedure"] or run["context"] != _context(marker)
            or any(run["execution"][key] != item for key, item in marker["producer"].items())
            or any(run["capabilities"][key] != marker["source"][key] for key in ("profile_id", "profile_digest"))
            or run["validity"]["validator_id"] != VALIDATOR_ID
            or run["validity"]["validator_version"] != VALIDATOR_VERSION
            or not run["validity"]["validator_code_ref"].startswith("git:mastermindx-market-intelligence/Mastermind@")):
        _refuse("PUBLICATION_RECORD_MISMATCH")
    completion = (run["execution"]["completion_status"], run["execution"]["termination_reason"])
    allowed = {_TERMINAL[receipt["outcome"]]}
    if receipt["outcome"] == "completed":
        allowed.add(("PARTIAL", "NATIVE_PARTIAL"))
    if completion not in allowed:
        _refuse("PUBLICATION_RECORD_MISMATCH")
    resolver = closed_input_resolver(scenarios=(marker["scenario"],), configurations=(config,),
        experiments=(marker["experiment"],) if marker["experiment"] is not None else ())
    verify_run_graph(run, resolver)
    evaluated = evaluate_validity(marker["scenario"], config, marker["experiment"], run)
    if (run["validity"]["status"] != evaluated["status"]
            or run["validity"]["reason_codes"] != list(evaluated["reason_codes"])):
        _refuse("PUBLICATION_VALIDITY_MISMATCH")
    return value


def publish_original(runner, home, params, principal, *, owner, role):
    """One same-UID operation; freeze first, then publish the confirmed bytes."""
    from hermes_state_terminal import ADMISSION_PREFIX, RESULT_PREFIX, load_result
    from hermes_state_runtime import _epoch, RuntimeStoreError
    from .native_session_control import _project_original_result, _result
    params = _request(params, home)
    authority = _selected_owner(runner, home, owner)
    db, epoch = authority.db, authority.epoch

    def freeze(conn):
        # Today's writer must still own the original DB. The execution row's
        # historical owner epoch and generation are not rewritten or compared
        # to today's epoch.
        _epoch(conn, epoch)
        raw, receipt, marker = _original(conn, params, principal, home, owner)
        retained = raw.get("eval_publication_json")
        if retained is not None:
            if type(retained) is not str or len(retained.encode("utf-8")) > MAX_PUBLICATION_BYTES:
                _refuse("PUBLICATION_RECORD_INVALID")
            return _validate_record(json.loads(retained), marker, receipt)
        saved_row = conn.execute("SELECT CASE WHEN length(CAST(value AS BLOB))<=? THEN value ELSE NULL END "
            "FROM state_meta WHERE key=?", (MAX_RETAINED_RESULT_BYTES, RESULT_PREFIX + receipt["admission_id"])).fetchone()
        saved, missing = None, "NOT_RETAINED"
        if saved_row is not None and saved_row[0] is None:
            missing = "OBSERVATION_LIMIT"
        elif saved_row is not None:
            try:
                saved = load_result(saved_row[0])
                if type(saved) is not dict:
                    saved = None
                    missing = "OBSERVATION_CONFLICT"
                else:
                    missing = "NOT_OBSERVED"
            except (ValueError, TypeError, RecursionError):
                missing = "OBSERVATION_CONFLICT"
        projected = _project_original_result(receipt, marker, saved, role=role)
        run = _build_run(marker, receipt, projected, finalizer_ref=owner.producer["runner_code_ref"],
                         now=_now(), missing_reason=missing)
        record = _validate_record({"schema": SCHEMA, "admission_id": receipt["admission_id"], "native_outcome": receipt["outcome"],
            "binding_sha256": marker["binding_sha256"], "run_id": marker["run_id"],
            "run_digest": run["run_digest"], "producer": marker["producer"],
            "publication": marker["publication"], "run": run}, marker, receipt)
        encoded = canonical_json_bytes(record).decode("utf-8")
        live = conn.execute("SELECT 1 FROM session_admissions WHERE admission_id=?",
                            (receipt["admission_id"],)).fetchone()
        if live is not None:
            changed = conn.execute("UPDATE session_admissions SET eval_publication_json=? "
                "WHERE admission_id=? AND eval_publication_json IS NULL", (encoded, receipt["admission_id"]))
        else:
            raw["eval_publication_json"] = encoded
            changed = conn.execute("UPDATE state_meta SET value=? WHERE key=?",
                (json.dumps(raw, ensure_ascii=False, allow_nan=False), ADMISSION_PREFIX + receipt["admission_id"]))
        if changed.rowcount != 1:
            _refuse("PUBLICATION_FREEZE_CONFLICT")
        return record

    # SessionDB owns serialization, SQLite retry and retirement ordering. A
    # lost commit response propagates: do not publish an unconfirmed candidate.
    try:
        frozen = db._execute_write(freeze)
    except RuntimeRefusal:
        # The callback's typed refusal rolls back its original transaction.
        raise
    except RuntimeStoreError as exc:
        if exc.reason in {"stale_epoch", "not_found"}:
            _refuse("PUBLICATION_ORIGINAL_OR_WRITER_UNAVAILABLE")
        raise PublicationEffectUnknown() from None
    except ContractError:
        # Graph/privacy/shape validation happens before the nullable-field write.
        _refuse("PUBLICATION_RECORD_UNQUALIFIED")
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        _refuse("PUBLICATION_RECORD_UNQUALIFIED")
    except Exception:
        raise PublicationEffectUnknown() from None
    try:
        with db._read_ctx() as conn:
            _epoch(conn, epoch)
            raw, receipt, marker = _original(conn, params, principal, home, owner)
            retained = raw.get("eval_publication_json")
            if type(retained) is not str or len(retained.encode("utf-8")) > MAX_PUBLICATION_BYTES:
                _refuse("PUBLICATION_FREEZE_READBACK_FAILED")
            confirmed = _validate_record(json.loads(retained), marker, receipt)
            if canonical_json_bytes(confirmed) != canonical_json_bytes(frozen):
                _refuse("PUBLICATION_FREEZE_READBACK_FAILED")
        if _selected_owner(runner, home, owner) is not authority or authority.epoch != epoch:
            _refuse("PUBLICATION_OWNER_CHANGED")
        written = owner.store.create(confirmed["run"])
        owner.check()
        return _result("PUBLISHED", role=role, admission_id=receipt["admission_id"],
            evaluation_binding={"run_id": marker["run_id"], "binding_sha256": marker["binding_sha256"]},
            publication={"schema": SCHEMA, "disposition": written.disposition.value,
                "relative_path": written.path, "run_digest": written.artifact_digest,
                "validity": confirmed["run"]["validity"]["status"],
                "reason_codes": confirmed["run"]["validity"]["reason_codes"],
                "complete_evaluation": False, "provider_delivery_proven": False, "model_identity_verified": False})
    except ArtifactConflictError:
        return _result("REFUSED", role=role, reason="EVALUATION_ARTIFACT_CONFLICT",
                       admission_id=params["admission_id"], evaluation_binding=params["evaluation_binding"],
                       frozen_record_retained=True)
    except Exception:
        raise PublicationEffectUnknown() from None


def _trial_summary(run, *, eligible, reason=None):
    return {"run_id": run["run_id"], "run_digest": run["run_digest"],
            "validity": run["validity"]["status"],
            "reason_codes": copy.deepcopy(run["validity"]["reason_codes"]),
            "eligible_for_consumption": eligible, "eligibility_reason": reason}


def decode_trial(document, *, admission_id, evaluation_binding):
    """Decode evidence from the authenticated original reader, never a grant.

    The caller owns carrier/principal authentication and expected original
    identity. Graph/content validation alone cannot supply either authority.
    """
    from scripts.ohf.harness2_recursion import Trial, _validate_trial
    from scripts.agent_eval.harness2_native import validate_native_harness_text
    raw = canonical_json_bytes(document)
    if len(raw) > MAX_TRIAL_BYTES:
        _refuse("TRIAL_DOCUMENT_LIMIT")
    value = json.loads(raw)
    if (type(value) is not dict or set(value) != {
            "schema", "scenario", "configuration", "experiment", "run", "candidate_files", "output"}
            or value["schema"] != TRIAL_SCHEMA
            or type(evaluation_binding) is not dict
            or set(evaluation_binding) != {"run_id", "binding_sha256"}
            or type(value["run"]) is not dict
            or value["run"].get("run_id") != evaluation_binding["run_id"]
            or type(evaluation_binding["binding_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", evaluation_binding["binding_sha256"]) is None):
        _refuse("TRIAL_DOCUMENT_INVALID")
    from .native_session_control import _id, MAX_ANSWER_BYTES
    _id(admission_id)
    contracts.v_run_id(evaluation_binding["run_id"], "$.run_id")
    output = value["output"]
    if (type(output) is not dict or set(output) != {"stage", "text", "digest", "bytes"}
            or output["stage"] != "retained_redacted_final_response"
            or type(output["text"]) is not str or type(output["bytes"]) is not int):
        _refuse("TRIAL_OUTPUT_INVALID")
    encoded = output["text"].encode("utf-8")
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    expected_ref = _original_ref(
        {"binding_sha256": evaluation_binding["binding_sha256"]}, {"admission_id": admission_id}) + "#final_response"
    if (not 0 < len(encoded) <= MAX_ANSWER_BYTES
            or any(ord(c) < 32 and c not in "\n\r\t" for c in output["text"])
            or output["bytes"] != len(encoded) or output["digest"] != digest
            or value["run"].get("evidence", {}).get("output") != {
                "artifact_ref": expected_ref, "digest": digest}):
        _refuse("TRIAL_OUTPUT_CONFLICT")
    source = value["candidate_files"]
    if type(source) is not dict or any(type(p) is not str or type(v) is not str for p, v in source.items()):
        _refuse("TRIAL_HARNESS_INVALID")
    candidate = {p: text.encode("utf-8") for p, text in source.items()}
    validate_native_harness_text(candidate)
    assert_public_safe_evidence(value)
    trial = Trial(value["scenario"], value["configuration"], value["experiment"], value["run"], encoded)
    _validate_trial(trial, candidate)
    return trial


def read_original_trial(runner, home, params, principal, *, owner, role):
    """Read one already published original trial. No create, submit or repair."""
    from hermes_state_runtime import _epoch
    from hermes_state_terminal import RESULT_PREFIX, load_result
    from scripts.agent_eval.verification import verify_scenario_graph, verify_configuration_graph, verify_experiment_graph
    from scripts.ohf.harness2_recursion import Harness2CycleError
    from .native_session_control import _project_original_result, _result
    if role != "mmmeta":
        _refuse("TRIAL_ROLE_UNQUALIFIED")
    params = _request(params, home, operation="read_evaluation_trial")
    authority = _selected_owner(runner, home, owner)
    db, epoch, store = authority.db, authority.epoch, owner.store

    def read():
        with db._read_ctx() as conn:
            _epoch(conn, epoch)
            raw, receipt, marker = _original(conn, params, principal, home, owner)
            frozen = raw.get("eval_publication_json")
            if frozen is None:
                _refuse("TRIAL_PUBLICATION_NOT_FROZEN")
            if type(frozen) is not str or len(frozen.encode("utf-8")) > MAX_PUBLICATION_BYTES:
                _refuse("TRIAL_PUBLICATION_INVALID")
            record = _validate_record(json.loads(frozen), marker, receipt)
            saved_row = conn.execute(
                "SELECT CASE WHEN length(CAST(value AS BLOB))<=? THEN value ELSE NULL END "
                "FROM state_meta WHERE key=?", (MAX_RETAINED_RESULT_BYTES, RESULT_PREFIX + receipt["admission_id"])).fetchone()
            saved, unavailable = None, "NATIVE_EVAL_TRIAL_OUTPUT_NOT_RETAINED"
            if saved_row is not None:
                if saved_row[0] is None:
                    unavailable = "NATIVE_EVAL_TRIAL_OUTPUT_LIMIT"
                else:
                    try:
                        saved = load_result(saved_row[0])
                        if type(saved) is not dict:
                            saved = None
                        unavailable = "NATIVE_EVAL_TRIAL_OUTPUT_INVALID"
                    except (ValueError, TypeError, RecursionError):
                        unavailable = "NATIVE_EVAL_TRIAL_OUTPUT_INVALID"
            projected = _project_original_result(receipt, marker, saved, role=role)
            # Only this closed output projection survives the read context.
            return record, receipt, marker, projected.get("answer"), projected.get("terminal_metadata", {}).get("output"), unavailable

    record, receipt, marker, answer, output, unavailable = read()
    published = store.resolve_run(marker["run_id"])
    if published is None:
        _refuse("TRIAL_ARTIFACT_NOT_RETAINED")
    if canonical_json_bytes(published) != canonical_json_bytes(record["run"]):
        _refuse("TRIAL_ARTIFACT_CONFLICT")
    scenario = store.resolve_scenario(marker["scenario"]["scenario_id"], marker["scenario"]["scenario_version"])
    configuration = store.resolve_configuration(marker["configuration"]["configuration_id"])
    experiment = (store.resolve_experiment(marker["experiment"]["experiment_id"])
                  if marker["experiment"] is not None else None)
    if any(canonical_json_bytes(actual) != canonical_json_bytes(marker[key])
           for actual, key in ((scenario, "scenario"), (configuration, "configuration"), (experiment, "experiment"))):
        _refuse("TRIAL_GRAPH_CONFLICT")
    verify_scenario_graph(scenario, store)
    verify_configuration_graph(configuration, store)
    if experiment is not None:
        verify_experiment_graph(experiment, store)
    verify_run_graph(published, store)
    binding = {"run_id": marker["run_id"], "binding_sha256": marker["binding_sha256"]}
    status, reason, document = "REFUSED", unavailable, None
    # The original graph already established these facts. Preserve the
    # incumbent consumer's effect/validity precedence without constructing or
    # disclosing an ineligible candidate, including an empty failed answer.
    if published["effect"]["state"] != "NO_EFFECT":
        reason = "NATIVE_EFFECT_REQUIRES_RECONCILIATION"
    elif published["validity"]["status"] != "VALID":
        reason = "NATIVE_TRIAL_INVALID"
    elif output is not None and type(answer) is str:
        expected = {"artifact_ref": _original_ref(marker, receipt) + "#final_response",
                    "digest": "sha256:" + output["sha256"]}
        if (output["stage"] != "retained_redacted_final_response"
                or published["evidence"]["output"] != expected):
            reason = "NATIVE_EVAL_TRIAL_OUTPUT_CONFLICT"
        else:
            candidate = {"schema": TRIAL_SCHEMA, "scenario": scenario, "configuration": configuration,
                "experiment": experiment, "run": published, "candidate_files": marker["candidate_files"],
                "output": {"stage": output["stage"], "text": answer,
                           "digest": expected["digest"], "bytes": output["utf8_bytes"]}}
            try:
                decode_trial(candidate, admission_id=receipt["admission_id"], evaluation_binding=binding)
            except Harness2CycleError as exc:
                reason = (exc.code if exc.code in {
                    "NATIVE_TRIAL_INVALID", "NATIVE_EFFECT_REQUIRES_RECONCILIATION"}
                    else "NATIVE_EVAL_TRIAL_EVIDENCE_INVALID")
            except RuntimeRefusal as exc:
                reason = (exc.code if exc.code in {
                    "NATIVE_EVAL_TRIAL_DOCUMENT_LIMIT", "NATIVE_EVAL_TRIAL_OUTPUT_INVALID",
                    "NATIVE_EVAL_TRIAL_OUTPUT_CONFLICT"} else "NATIVE_EVAL_TRIAL_EVIDENCE_INVALID")
            except ContractError:
                reason = "NATIVE_EVAL_TRIAL_EVIDENCE_INVALID"
            else:
                status, reason, document = "TRIAL_OBSERVED", None, candidate
    # A source/store/owner replacement, changed frozen record or result expiry
    # during the read cannot splice a surviving publication to different bytes.
    if (_selected_owner(runner, home, owner) is not authority or authority.epoch != epoch
            or owner.store is not store):
        _refuse("TRIAL_OWNER_CHANGED")
    again = read()
    first = (record, receipt, marker, answer, output, unavailable)
    if canonical_json_bytes(list(again)) != canonical_json_bytes(list(first)):
        _refuse("TRIAL_ORIGINAL_CHANGED")
    if (_selected_owner(runner, home, owner) is not authority or authority.epoch != epoch
            or owner.store is not store):
        _refuse("TRIAL_OWNER_CHANGED")
    result = _result(status, role=role, admission=receipt, evaluation_binding=binding,
        trial_summary=_trial_summary(published, eligible=document is not None, reason=reason))
    if document is not None:
        result["trial"] = document
    else:
        result["reason"] = reason
    return result
