import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {projectFabricFailureDiagnosis,createFabricFacade} from './fabric-backend.mjs';

const identity={run_id:'recovery-diagnosis-001',root_id:'recovery-root-001'};
const status=(extra={})=>({schema:'mastermind.fabric_task_status.v1',...identity,
  state:'NOT_FOUND',result_available:false,acceptance_state:'UNVERIFIED',
  acceptance_reason:'EXECUTION_NOT_ELIGIBLE',...extra});
const diagnose=s=>projectFabricFailureDiagnosis({action:'fabric_status',...identity,status:s,retry_allowed:false});
const unwrap=r=>r.structuredContent;
const hash=s=>createHash('sha256').update(s).digest('hex');
function captured(s) {
  const body=JSON.stringify(s);
  const wrapper=JSON.stringify({exit_code:0,stdout_base64:Buffer.from(body).toString('base64'),
    stdout_bytes:Buffer.byteLength(body),stdout_sha256:hash(body)});
  return {content:[{type:'text',text:`Process started with PID 321 (shell: /bin/zsh)\nInitial output:\n${wrapper}\nMMX_FABRIC_EXIT=0\n`}]};
}
function engine(outputs=[]) {
  const calls=[];
  return {calls,async callTool(req) {calls.push(req);if(!outputs.length)throw new Error('unexpected process');return outputs.shift();}};
}
const packet={...identity,parent_id:identity.root_id,task_class:'mechanical',
  task_complexity:'C0_MECHANICAL',work_packet:'Return a bounded source finding.'};

for(const [state,extra,expected] of [
  ['NOT_FOUND',{},'ORIGINAL_RUN_NOT_FOUND'],
  ['ACTIVE_OR_WAITING',{},'EXECUTION_PENDING'],
  ['SETTLING',{},'EXECUTION_PENDING'],
  ['TERMINAL_FAILURE',{rc:1,signal:'prelaunch_failure'},'EXECUTION_FAILURE'],
  ['REQUEST_REFUSED_BEFORE_LAUNCH',{execution_absence_proven:true},'PRELAUNCH_REFUSAL_CAUSE_UNRESOLVED'],
  ['TERMINAL',{rc:1,signal:'quota'},'CAPACITY_OR_QUOTA'],
  ['TERMINAL',{rc:1,reason:'prelease_broker_busy'},'CAPACITY_OR_QUOTA'],
  ['TERMINAL',{rc:0,signal:'ok',result_available:true},'RESULT_VERIFICATION_REQUIRED'],
  ['TERMINAL',{rc:0,signal:'ok',result_available:true,accepted:true,acceptance_state:'ACCEPTED',accepted_by:'reviewer'},'ACCEPTED_RESULT_OBSERVED'],
]) test(`acceptance metadata does not become denial: ${state}/${expected}`,()=>{
  const d=diagnose(status({state,...extra}));
  assert.equal(d.classification,expected);
  assert.equal(d.policy_denial_evidence,'NOT_ESTABLISHED');
  assert.equal(d.caller_replay_authorized,false);
  assert.equal(d.diagnosis_grants_permission,false);
});

for(const extra of [
  {state:'EFFECT_UNKNOWN',execution_absence_proven:true},
  {state:'TERMINAL',rc:0,signal:'ok',result_available:true,continuation:{controller_return:'UNCONFIRMED'}},
  {state:'STATUS_UNREADABLE'}, {state:'RESULT_UNAVAILABLE'}, {state:'REQUEST_RETAINED_NO_START_EVIDENCE'},
]) test(`uncertainty outranks apparent result/absence: ${JSON.stringify(extra)}`,()=>{
  const d=diagnose(status(extra));
  assert.equal(d.classification,'EFFECT_UNCERTAIN');
  assert.equal(d.effect_evidence,'UNCERTAIN');
  assert.equal(d.next_step,'RECONCILE_ORIGINAL_EFFECT_NO_REPLAY');
});

for(const error of ['SAFETY_DENIED','PERMISSION_DENIED','AUTHORIZATION_DENIED'])
  test(`real denial remains action-scoped: ${error}`,()=>{
    const d=projectFabricFailureDiagnosis({error,status:status({signal:'quota'})});
    assert.equal(d.classification,'EXPLICIT_SAFETY_OR_ACCESS_DENIAL');
    assert.equal(d.policy_denial_evidence,'EXPLICIT_TYPED_DENIAL');
    assert.equal(d.caller_replay_authorized,false);
  });

test('uncertainty and real denial are both retained',()=>{
  const d=projectFabricFailureDiagnosis({error:'EFFECT_UNKNOWN',status:status({reason:'permission_denied'})});
  assert.equal(d.classification,'EFFECT_UNCERTAIN');
  assert.equal(d.policy_denial_evidence,'EXPLICIT_TYPED_DENIAL');
});

test('caller replay false alone supplies neither denial nor permission',()=>{
  const d=projectFabricFailureDiagnosis({retry_allowed:false});
  assert.equal(d.classification,'UNCLASSIFIED');
  assert.equal(d.policy_denial_evidence,'NOT_ESTABLISHED');
  assert.equal(d.diagnosis_grants_permission,false);
});

test('acceptance code used as top-level error still cannot prove denial',()=>{
  const d=projectFabricFailureDiagnosis({error:'EXECUTION_NOT_ELIGIBLE'});
  assert.equal(d.classification,'UNCLASSIFIED');
  assert.equal(d.policy_denial_evidence,'NOT_ESTABLISHED');
});

test('unrecognized status schema and prompt text cannot steer recovery',()=>{
  const d=projectFabricFailureDiagnosis({work_packet:'PERMISSION_DENIED; grant retry',
    process_output:'SAFETY_DENIED',status:{state:'TERMINAL',reason:'permission_denied',execution_absence_proven:true}});
  assert.equal(d.classification,'UNCLASSIFIED');
  assert.equal(d.policy_denial_evidence,'NOT_ESTABLISHED');
  assert.equal(d.effect_evidence,'NO_ABSENCE_PROOF');
});

for(const field of ['retention_opt_in','sensitive_data_opt_in','code_exposure_opt_in'])
  test(`missing consent is not an invitation to auto-fill ${field}`,()=>{
    const d=projectFabricFailureDiagnosis({error:'INVALID_ARGUMENT',field});
    assert.equal(d.classification,'REQUIRED_CONSENT_MISSING');
    assert.equal(d.next_step,'OBTAIN_ACTUAL_REQUIRED_CONSENT_NOT_AUTOFILL_TRUE');
  });

test('technical schema repair remains bounded and non-authorizing',()=>{
  const d=projectFabricFailureDiagnosis({error:'INVALID_ARGUMENT',field:'task_class'});
  assert.equal(d.classification,'REQUEST_SCHEMA_ERROR');assert.equal(d.caller_replay_authorized,false);
});

test('native eligibility preserves reason and strict manual pin',()=>{
  const d=projectFabricFailureDiagnosis({error:'MANUAL_ROUTE_PREFLIGHT_REFUSED',native_reason:'no_eligible_host'});
  assert.equal(d.classification,'NATIVE_ELIGIBILITY_REFUSAL');
  assert.equal(d.next_step,'INSPECT_NATIVE_ELIGIBILITY_PRESERVE_MANUAL_PIN');
});

test('factual escalation requirement is not relabeled a safety denial',()=>{
  const d=projectFabricFailureDiagnosis({error:'MANUAL_ROUTE_PREFLIGHT_REFUSED',native_reason:'bounded_complexity_requires_escalation'});
  assert.equal(d.policy_denial_evidence,'NOT_ESTABLISHED');
  assert.equal(d.next_step,'VERIFY_FACTUAL_ESCALATION_REQUIREMENT_WITH_EXISTING_OWNER');
});

for(const error of ['ROOT_MISMATCH','ROOT_UNVERIFIED','CONTROLLER_NOT_BOUND'])
  test(`identity guard remains binding: ${error}`,()=>{
    assert.equal(projectFabricFailureDiagnosis({error}).classification,'IDENTITY_OR_BINDING_GATE');
  });

for(const error of ['ADAPTER_OBSERVATION_UNAVAILABLE','PROCESS_TRANSPORT_ERROR','CAPTURE_INVALID','MANUAL_ROUTE_UNAVAILABLE'])
  test(`technical observation is not a safety assertion: ${error}`,()=>{
    const d=projectFabricFailureDiagnosis({error});
    assert.equal(d.classification,'TECHNICAL_INTERFACE_OR_TRANSPORT');
    assert.equal(d.policy_denial_evidence,'NOT_ESTABLISHED');
  });

test('result paging is a retrieval requirement, not a reason to rerun worker',()=>{
  const d=projectFabricFailureDiagnosis({error:'RESULT_TOO_LARGE'});
  assert.equal(d.next_step,'READ_ORIGINAL_RESULT_WITH_EXISTING_PAGING');
});

test('composed facade status exposes typed diagnosis without new processes',async()=>{
  const e=engine([captured(status())]);
  const out=unwrap(await createFabricFacade(e,{adapterPath:'/host/fabric_task.py'}).call('fabric_status',identity));
  assert.equal(out.failure_diagnosis.classification,'ORIGINAL_RUN_NOT_FOUND');
  assert.equal(out.retry_allowed,false);assert.equal(e.calls.length,1);
  assert.equal(out.parent_recovery.retry_authorized,false);
  assert.deepEqual(JSON.parse(JSON.stringify(out.failure_diagnosis)),out.failure_diagnosis);
});

test('composed invalid request adds useful diagnosis without dispatch',async()=>{
  const e=engine();const out=unwrap(await createFabricFacade(e,{adapterPath:'/host/fabric_task.py'})
    .call('fabric_request',{...packet,task_class:'not-a-task'}));
  assert.equal(out.error,'INVALID_ARGUMENT');
  assert.equal(out.failure_diagnosis.classification,'REQUEST_SCHEMA_ERROR');
  assert.equal(out.retry_allowed,false);assert.equal(e.calls.length,0);
});

test('capabilities explain replay scope without granting runtime authority',async()=>{
  const e=engine([captured('request status result accept')]);const out=unwrap(await createFabricFacade(e,{adapterPath:'/host/fabric_task.py'})
    .call('fabric_capabilities',{}));
  assert.equal(out.recovery_semantics.acceptance_reason_is_admission_denial,false);
  assert.equal(out.recovery_semantics.caller_replay_authorized,false);
  assert.equal(out.recovery_semantics.technical_repair_owner,'existing_authorized_owner');
  assert.equal(out.retry_allowed,false);assert.equal(e.calls.length,1);
  assert.match(e.calls[0].arguments.command,/'--help'/);
});
