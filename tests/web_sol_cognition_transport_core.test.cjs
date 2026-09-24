'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto, createHash} = require('node:crypto');

const CORE = process.env.COGNITION_CORE || require('node:path').join(__dirname, 'cognition_transport_core.js');
const source = fs.readFileSync(CORE, 'utf8');

function canonical(value) {
  if (value === null) return 'null';
  if (typeof value === 'boolean' || typeof value === 'number' || typeof value === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
}
function digestText(value) { return createHash('sha256').update(value).digest('hex'); }
function digest(value) { return digestText(canonical(value)); }
function clone(value) { return JSON.parse(JSON.stringify(value)); }

const IDS = Object.freeze({
  turn_id: 'ohf-turn-cognition-0001',
  runtime_binding_id: 'bind-wsx-' + 'a'.repeat(48),
  runtime_binding_generation: 7,
  runtime_binding_fingerprint: 'b'.repeat(64),
  job_id: 'JOB-CG-1',
  attempt_id: 'ATT-CG-1',
  worker_id: 'WORKER-CG-1',
  root_job_id: 'ROOT-CG-1',
  role: 'work',
});
const SCHEMA_DIGEST = 'c'.repeat(64);
const EPOCH = 'd'.repeat(32);

function assignment(overrides={}) {
  const value = {
    schema_version: 'mastermind.web_sol_cognition_assignment/v1',
    continuation: {
      schema: 'mastermind.web_sol_continuation/v1',
      workstream: 'WS:AUTOMATE-RESEARCH-HANDOFFS',
      agentos_source_sha: '1'.repeat(40),
      state: 'bounded',
    },
    continuation_digest: '2'.repeat(64),
    effect_contract: {
      allowed_write_paths: [],
      external_effects_allowed: false,
      requested_authorities: ['READ', 'RESEARCH'],
    },
    job: {
      attempt_id: IDS.attempt_id,
      job_id: IDS.job_id,
      objective: 'Read current evidence and return one bounded research result.',
      plan_attempt_id: 'PLAN-1',
      plan_digest: '3'.repeat(64),
      plan_step_id: 'STEP-1',
      quota_class: 'web-pro',
      repair_round: 0,
      review_required: false,
      reviews_job_id: null,
      role: IDS.role,
      root_job_id: IDS.root_job_id,
      worker_id: IDS.worker_id,
    },
    result_contract: {
      schema: {
        properties: {
          job_id: {const: IDS.job_id},
          run_id: {const: IDS.attempt_id},
          worker_id: {const: IDS.worker_id},
          role: {const: IDS.role},
          role_result: {properties: {root_job_id: {const: IDS.root_job_id}}},
        },
      },
      schema_digest: SCHEMA_DIGEST,
    },
    source: {
      work_ref: 'WS:AUTOMATE-RESEARCH-HANDOFFS',
      commission_ref: 'commission-1',
      dialogue_source_digest: '4'.repeat(64),
    },
  };
  Object.assign(value, overrides);
  return value;
}

function submitPayload(changes={}) {
  const a = assignment();
  return {
    schema: 'mastermind.web_sol_cognition_submit_payload/v1',
    assignment: a,
    turn_id: IDS.turn_id,
    assignment_digest: digest(a),
    result_schema_digest: SCHEMA_DIGEST,
    runtime_binding_id: IDS.runtime_binding_id,
    runtime_binding_generation: IDS.runtime_binding_generation,
    runtime_binding_fingerprint: IDS.runtime_binding_fingerprint,
    job_id: IDS.job_id,
    attempt_id: IDS.attempt_id,
    worker_id: IDS.worker_id,
    root_job_id: IDS.root_job_id,
    role: IDS.role,
    ...changes,
  };
}

function observePayload(submit=submitPayload(), changes={}) {
  const value = {...submit};
  delete value.assignment;
  value.schema = 'mastermind.web_sol_cognition_result_observe_payload/v1';
  return {...value, ...changes};
}

function resultObject() {
  return {
    current_state: 'Research completed from bounded read-only evidence.',
    errors: [],
    job_id: IDS.job_id,
    next_actions: ['Parent may consume this result through the existing Executive result owner.'],
    role: IDS.role,
    role_result: {root_job_id: IDS.root_job_id},
    run_id: IDS.attempt_id,
    schema_version: 'mastermind.executive_orchestration_result/v1',
    status: 'COMPLETED',
    summary: 'Bounded research result.',
    validations: [],
    worker_id: IDS.worker_id,
  };
}

function context(reducerMode='ready') {
  const ctx = vm.createContext({
    globalThis: null,
    crypto: webcrypto,
    TextEncoder,
    Uint8Array,
    Object,
    Array,
    Set,
    RegExp,
    JSON,
    String,
    Number,
    Boolean,
    Promise,
  });
  ctx.globalThis = ctx;
  ctx.MMXWebSolCognitionResult = {
    reduceCanonicalResultText(text, expected) {
      if (reducerMode === 'throw') throw Error('reducer failure');
      if (reducerMode !== 'ready') {
        return {status: 'RESULT_REFUSED', canonical_result_json: null, canonical_result_byte_length: 0};
      }
      const parsed = JSON.parse(text);
      assert.equal(parsed.job_id, expected.job_id);
      assert.equal(parsed.run_id, expected.run_id);
      assert.equal(parsed.worker_id, expected.worker_id);
      assert.equal(parsed.role, expected.role);
      assert.equal(parsed.role_result.root_job_id, expected.root_job_id);
      assert.equal(text, canonical(parsed));
      return {status: 'RESULT_READY', canonical_result_json: text, canonical_result_byte_length: Buffer.byteLength(text)};
    },
  };
  vm.runInContext(source, ctx, {filename: 'cognition_transport_core.js'});
  return ctx;
}

function message(role, id, text='', status='finished_successfully', endTurn=true) {
  return {id, author:{role}, status, end_turn:endTurn, content:{content_type:'text', parts:[text]}};
}
function node(id, parent, msg, children=[]) { return {id, parent, children, message:msg}; }
function snapshot(prompt, assistantText=canonical(resultObject()), {assistantStatus='finished_successfully', endTurn=true}={}) {
  const user='user-cognition-assignment-001';
  const assistant='assistant-cognition-result-001';
  return {
    current_node: assistant,
    mapping: {
      [user]: node(user, null, message('user', user, prompt, 'finished_successfully', false), [assistant]),
      [assistant]: node(assistant, user, message('assistant', assistant, assistantText, assistantStatus, endTurn), []),
    },
  };
}

async function rendered(ctx=context(), payload=submitPayload()) {
  return await ctx.MMXWebSolCognitionTransport.renderAssignmentPrompt(payload);
}

function plain(value) { return JSON.parse(JSON.stringify(value)); }

test('renders one fixed canonical assignment prompt without transport-private identity', async () => {
  const ctx=context(); const payload=submitPayload(); const prompt=await rendered(ctx,payload);
  assert.ok(prompt);
  assert.ok(prompt.startsWith(ctx.MMXWebSolCognitionTransport.DIRECTIVE_TEXT + '\n'));
  const suffix=prompt.slice(ctx.MMXWebSolCognitionTransport.DIRECTIVE_TEXT.length+1);
  assert.equal(suffix, canonical(payload.assignment));
  assert.equal(digestText(suffix), payload.assignment_digest);
  assert.ok(Buffer.byteLength(suffix) <= ctx.MMXWebSolCognitionTransport.MAX_ASSIGNMENT_BYTES);
  assert.ok(Buffer.byteLength(prompt) <= ctx.MMXWebSolCognitionTransport.MAX_RENDERED_ASSIGNMENT_BYTES);
  for (const forbidden of [IDS.turn_id, IDS.runtime_binding_id, IDS.runtime_binding_fingerprint]) {
    assert.equal(prompt.includes(forbidden), false);
  }
});

test('renderer fails closed on digest drift, write authority, private fields and identity mismatch', async () => {
  const cases=[];
  const digestDrift=submitPayload({assignment_digest:'f'.repeat(64)}); cases.push(digestDrift);
  const write=submitPayload(); write.assignment.effect_contract.external_effects_allowed=true;
  write.assignment_digest=digest(write.assignment); cases.push(write);
  const privateField=submitPayload(); privateField.assignment.source.profile_id='private-profile';
  privateField.assignment_digest=digest(privateField.assignment); cases.push(privateField);
  const wrongJob=submitPayload(); wrongJob.assignment.job.job_id='JOB-OTHER';
  wrongJob.assignment_digest=digest(wrongJob.assignment); cases.push(wrongJob);
  for (const value of cases) assert.equal(await rendered(context(),value), null);
});

test('unique exact assignment plus one terminal assistant emits only closed ready observation', async () => {
  const ctx=context(); const submit=submitPayload(); const prompt=await rendered(ctx,submit);
  const request=observePayload(submit); const snap=snapshot(prompt);
  const result=plain(await ctx.MMXWebSolCognitionTransport.reduceConversation(snap,request,EPOCH));
  assert.equal(result.status,'COGNITION_RESULT_READY');
  assert.equal(result.provider_native_turn_id,'assistant-cognition-result-001');
  assert.equal(result.result_digest,digestText(canonical(resultObject())));
  assert.equal(result.result_byte_length,Buffer.byteLength(canonical(resultObject())));
  assert.deepEqual(result.result,resultObject());
  assert.match(result.provider_turn_artifact_digest,/^[0-9a-f]{64}$/);
  const serialized=JSON.stringify(result);
  assert.equal(serialized.includes('mapping'),false);
  assert.equal(serialized.includes('transcript'),false);
  assert.equal(serialized.includes(ctx.MMXWebSolCognitionTransport.DIRECTIVE_TEXT),false);
});

test('assignment not yet visible and active assistant are pending without provider/result content', async () => {
  const ctx=context(); const submit=submitPayload(); const prompt=await rendered(ctx,submit); const req=observePayload(submit);
  const other=await rendered(ctx, submitPayload({assignment_digest:'e'.repeat(64)}));
  assert.equal(other,null);
  const absent=snapshot('not the assignment');
  const pending1=plain(await ctx.MMXWebSolCognitionTransport.reduceConversation(absent,req,EPOCH));
  assert.equal(pending1.status,'COGNITION_RESULT_PENDING');
  const active=snapshot(prompt,'',{assistantStatus:'in_progress',endTurn:false});
  const pending2=plain(await ctx.MMXWebSolCognitionTransport.reduceConversation(active,req,EPOCH));
  assert.equal(pending2.status,'COGNITION_RESULT_PENDING');
  for (const item of [pending1,pending2]) {
    assert.equal(item.provider_native_turn_id,null);assert.equal(item.provider_turn_artifact_digest,null);
    assert.equal(item.result,null);assert.equal(item.result_digest,null);assert.equal(item.result_byte_length,0);
  }
});

test('duplicate exact assignment on active path refuses instead of choosing one', async () => {
  const ctx=context(); const submit=submitPayload(); const prompt=await rendered(ctx,submit); const req=observePayload(submit);
  const u1='user-cognition-assignment-001', a1='assistant-intermediary-001', u2='user-cognition-assignment-002', a2='assistant-cognition-result-001';
  const snap={current_node:a2,mapping:{
    [u1]:node(u1,null,message('user',u1,prompt,'finished_successfully',false),[a1]),
    [a1]:node(a1,u1,message('assistant',a1,'interim','finished_successfully',false),[u2]),
    [u2]:node(u2,a1,message('user',u2,prompt,'finished_successfully',false),[a2]),
    [a2]:node(a2,u2,message('assistant',a2,canonical(resultObject())),[]),
  }};
  assert.equal((await ctx.MMXWebSolCognitionTransport.reduceConversation(snap,req,EPOCH)).status,'COGNITION_RESULT_REFUSED');
});

test('later user, failed assistant and malformed graph all refuse', async () => {
  const ctx=context(); const submit=submitPayload(); const prompt=await rendered(ctx,submit); const req=observePayload(submit);
  const later=snapshot(prompt); const final=later.current_node; const laterUser='user-later-001';
  later.mapping[final].children=[laterUser]; later.mapping[laterUser]=node(laterUser,final,message('user',laterUser,'new request','finished_successfully',false),[]); later.current_node=laterUser;
  assert.equal((await ctx.MMXWebSolCognitionTransport.reduceConversation(later,req,EPOCH)).status,'COGNITION_RESULT_REFUSED');
  const failed=snapshot(prompt,'failure',{assistantStatus:'failed',endTurn:true});
  assert.equal((await ctx.MMXWebSolCognitionTransport.reduceConversation(failed,req,EPOCH)).status,'COGNITION_RESULT_REFUSED');
  const cyclic=snapshot(prompt); cyclic.mapping['user-cognition-assignment-001'].parent=cyclic.current_node;
  assert.equal((await ctx.MMXWebSolCognitionTransport.reduceConversation(cyclic,req,EPOCH)).status,'COGNITION_RESULT_REFUSED');
});

test('wrong assignment identity or noncanonical assignment prompt cannot bind the result', async () => {
  const ctx=context(); const submit=submitPayload(); const prompt=await rendered(ctx,submit); const req=observePayload(submit);
  const wrong=clone(submit.assignment); wrong.job.job_id='JOB-OTHER'; const wrongPrompt=ctx.MMXWebSolCognitionTransport.DIRECTIVE_TEXT+'\n'+canonical(wrong);
  assert.equal((await ctx.MMXWebSolCognitionTransport.reduceConversation(snapshot(wrongPrompt),req,EPOCH)).status,'COGNITION_RESULT_PENDING');
  const suffix=prompt.slice(ctx.MMXWebSolCognitionTransport.DIRECTIVE_TEXT.length+1);
  const noncanonical=ctx.MMXWebSolCognitionTransport.DIRECTIVE_TEXT+'\n '+suffix;
  assert.equal((await ctx.MMXWebSolCognitionTransport.reduceConversation(snapshot(noncanonical),req,EPOCH)).status,'COGNITION_RESULT_PENDING');
});

test('tool intermediary is tolerated but the final assistant must be unique and current', async () => {
  const ctx=context(); const submit=submitPayload(); const prompt=await rendered(ctx,submit); const req=observePayload(submit);
  const user='user-cognition-assignment-001', assistantTool='assistant-tool-call-001', tool='tool-result-001', final='assistant-cognition-result-001';
  const toolMessage=message('assistant',assistantTool,'','finished_successfully',false); toolMessage.content.parts=[{opaque:'tool-call'}];
  const snap={current_node:final,mapping:{
    [user]:node(user,null,message('user',user,prompt,'finished_successfully',false),[assistantTool]),
    [assistantTool]:node(assistantTool,user,toolMessage,[tool]),
    [tool]:node(tool,assistantTool,message('tool',tool,'','finished_successfully',false),[final]),
    [final]:node(final,tool,message('assistant',final,canonical(resultObject())),[]),
  }};
  const result=await ctx.MMXWebSolCognitionTransport.reduceConversation(snap,req,EPOCH);
  assert.equal(result.status,'COGNITION_RESULT_READY');assert.equal(result.provider_native_turn_id,final);
  const extra='assistant-extra-001'; snap.mapping[final].children=[extra]; snap.mapping[extra]=node(extra,final,message('assistant',extra,canonical(resultObject())),[]); snap.current_node=extra;
  assert.equal((await ctx.MMXWebSolCognitionTransport.reduceConversation(snap,req,EPOCH)).status,'COGNITION_RESULT_REFUSED');
});

test('canonical result reducer refusal or failure stays closed', async () => {
  for (const mode of ['refused','throw']) {
    const ctx=context(mode); const submit=submitPayload(); const prompt=await rendered(ctx,submit); const req=observePayload(submit);
    const result=plain(await ctx.MMXWebSolCognitionTransport.reduceConversation(snapshot(prompt),req,EPOCH));
    assert.equal(result.status,'COGNITION_RESULT_REFUSED');assert.equal(result.result,null);assert.equal(result.provider_native_turn_id,null);
  }
});


test('invalid observe identity or document epoch produces no fabricated observation', async () => {
  const ctx=context(); const submit=submitPayload(); const prompt=await rendered(ctx,submit); const snap=snapshot(prompt);
  const invalidRequest=observePayload(submit,{runtime_binding_generation:0});
  assert.equal(await ctx.MMXWebSolCognitionTransport.reduceConversation(snap,invalidRequest,EPOCH),null);
  const request=observePayload(submit);
  assert.equal(await ctx.MMXWebSolCognitionTransport.reduceConversation(snap,request,'not-an-epoch'),null);
});
