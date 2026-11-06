/**
 * Evidence-only failure interpretation for attended callers. This projection is
 * NOT an admission, retry, fallback, lifecycle or permission owner. In particular,
 * EXECUTION_NOT_ELIGIBLE is an acceptance projection, not a refusal cause.
 * Never inspect work_packet, free-form output or provider prose for authority.
 */
export function projectFabricFailureDiagnosis(value) {
  const observation=value && typeof value==='object' && !Array.isArray(value) ? value : {};
  const candidate=observation.status;
  const s=candidate && typeof candidate==='object' && !Array.isArray(candidate)
    && candidate.schema==='mastermind.fabric_task_status.v1' ? candidate : {};
  const code=typeof observation.error==='string' ? observation.error : '';
  const state=typeof s.state==='string' ? s.state : '';
  const signal=typeof s.signal==='string' ? s.signal : '';
  // Only typed owner fields participate. acceptance_reason is deliberately absent.
  const typed=[code,s.error,s.reason,signal,observation.native_reason];
  const explicitDenials=new Set([
    'SAFETY_DENIED','SAFETY_REFUSAL','PERMISSION_DENIED','AUTHORIZATION_DENIED',
    'safety_denied','safety_refusal','permission_denied','authorization_denied',
  ]);
  const policyDenied=typed.some(x=>typeof x==='string' && explicitDenials.has(x));
  const uncertain=code==='EFFECT_UNKNOWN' || state==='EFFECT_UNKNOWN'
    || signal==='effect_unknown' || s.continuation?.controller_return==='UNCONFIRMED'
    || ['STATUS_UNREADABLE','RESULT_UNAVAILABLE','REQUEST_RETAINED_NO_START_EVIDENCE'].includes(state)
    || code==='CONTROLLER_RETURN_UNCONFIRMED';
  let classification='UNCLASSIFIED';
  let nextStep='INSPECT_ORIGINAL_TYPED_RECEIPT';
  if(uncertain) {
    classification='EFFECT_UNCERTAIN';nextStep='RECONCILE_ORIGINAL_EFFECT_NO_REPLAY';
  } else if(policyDenied) {
    classification='EXPLICIT_SAFETY_OR_ACCESS_DENIAL';nextStep='STOP_DENIED_ACTION_CONTINUE_INDEPENDENT_WORK';
  } else if(['ROOT_MISMATCH','ROOT_UNVERIFIED','CONTROLLER_NOT_BOUND'].includes(code)) {
    classification='IDENTITY_OR_BINDING_GATE';nextStep='VERIFY_ORIGINAL_IDENTITY_NO_SUBSTITUTION';
  } else if(code==='INVALID_ARGUMENT') {
    const consentFields=['retention_opt_in','sensitive_data_opt_in','code_exposure_opt_in'];
    classification=consentFields.includes(observation.field) ? 'REQUIRED_CONSENT_MISSING' : 'REQUEST_SCHEMA_ERROR';
    nextStep=consentFields.includes(observation.field)
      ? 'OBTAIN_ACTUAL_REQUIRED_CONSENT_NOT_AUTOFILL_TRUE'
      : 'CORRECT_INPUT_WITHIN_SCOPE_THEN_EXISTING_OWNER_RECHECK';
  } else if(code==='MANUAL_ROUTE_PREFLIGHT_REFUSED') {
    classification='NATIVE_ELIGIBILITY_REFUSAL';
    nextStep=observation.native_reason==='bounded_complexity_requires_escalation'
      ? 'VERIFY_FACTUAL_ESCALATION_REQUIREMENT_WITH_EXISTING_OWNER'
      : 'INSPECT_NATIVE_ELIGIBILITY_PRESERVE_MANUAL_PIN';
  } else if(['REQUEST_ALREADY_ATTEMPTED','RUN_EXISTS'].includes(code)) {
    classification='ORIGINAL_OPERATION_ALREADY_EXISTS';nextStep='OBSERVE_ORIGINAL_RUN_NO_DUPLICATE';
  } else if(['MANUAL_ROUTE_UNAVAILABLE','ADAPTER_CONTINUITY_UNAVAILABLE','ADAPTER_TURN_LIMIT_UNAVAILABLE',
    'ADAPTER_OBSERVATION_UNAVAILABLE','PROCESS_TRANSPORT_ERROR','CAPTURE_INVALID','UNKNOWN_TOOL'].includes(code)) {
    classification='TECHNICAL_INTERFACE_OR_TRANSPORT';nextStep='DIAGNOSE_ORIGINAL_INTERFACE_AND_EFFECTS_WITHIN_GRANT';
  } else if(['RESULT_TOO_LARGE','RESULT_NOT_FULLY_DELIVERED','RESULT_OFFSET_OUT_OF_RANGE'].includes(code)) {
    classification='RESULT_RETRIEVAL_REQUIREMENT';nextStep='READ_ORIGINAL_RESULT_WITH_EXISTING_PAGING';
  } else if(signal==='quota' || s.reason==='prelease_broker_busy') {
    classification='CAPACITY_OR_QUOTA';nextStep='INSPECT_INCUMBENT_CONTROLLER_CAPACITY_DISPOSITION';
  } else if(state==='REQUEST_REFUSED_BEFORE_LAUNCH') {
    classification='PRELAUNCH_REFUSAL_CAUSE_UNRESOLVED';nextStep='INSPECT_ORIGINAL_PRELAUNCH_REASON_AND_EFFECT_EVIDENCE';
  } else if(['ACTIVE_OR_WAITING','SETTLING'].includes(state)) {
    classification='EXECUTION_PENDING';nextStep='OBSERVE_ORIGINAL_CONTROLLER_NO_DUPLICATE';
  } else if(state==='NOT_FOUND') {
    classification='ORIGINAL_RUN_NOT_FOUND';nextStep='VERIFY_ORIGINAL_REQUEST_LINEAGE_NOT_ABSENCE_BY_INFERENCE';
  } else if(state==='TERMINAL' && s.rc===0 && signal==='ok' && s.result_available===true) {
    classification=s.accepted===true && s.acceptance_state==='ACCEPTED'
      && ['reviewer','deterministic'].includes(s.accepted_by) ? 'ACCEPTED_RESULT_OBSERVED' : 'RESULT_VERIFICATION_REQUIRED';
    nextStep=classification==='ACCEPTED_RESULT_OBSERVED'
      ? 'CONSUME_VERIFIED_ORIGINAL_RESULT' : 'VERIFY_ORIGINAL_RESULT_BEFORE_ACCEPTANCE';
  } else if(['TERMINAL','TERMINAL_FAILURE','RECONCILED_PRESTART_FAILURE','RECONCILED_PREEXEC_FAILURE'].includes(state)) {
    classification='EXECUTION_FAILURE';nextStep='DIAGNOSE_ORIGINAL_FAILURE_WITHIN_EXISTING_GRANT';
  }
  return {
    schema:'mastermind.fabric_failure_diagnosis.v1',classification,
    policy_denial_evidence:policyDenied ? 'EXPLICIT_TYPED_DENIAL' : 'NOT_ESTABLISHED',
    effect_evidence:uncertain ? 'UNCERTAIN' : s.execution_absence_proven===true
      ? 'OWNER_REPORTS_EXECUTION_ABSENCE' : 'NO_ABSENCE_PROOF',
    acceptance_reason_scope:'RESULT_ACCEPTANCE_ONLY_NOT_FAILURE_CAUSE',
    retry_allowed_scope:'CALLER_REPLAY_OR_REROUTE_OF_ORIGINAL_EFFECT',
    next_step:nextStep,
    // Interpretation does not turn owner evidence into new authority.
    caller_replay_authorized:false,diagnosis_grants_permission:false,
  };
}
