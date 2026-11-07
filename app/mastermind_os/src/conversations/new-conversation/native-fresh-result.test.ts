import {describe,expect,it,vi} from 'vitest';
import fixture from '../../fixtures/native-fresh-action-owner.json';
import recoveryFixture from '../../fixtures/native-fresh-recovery-owner.json';
import {decodeNativeFreshResult} from './native-fresh-result';
import {NATIVE_FRESH_OPERATIONS,type NativeFreshOperation} from './native-fresh-request';
const choose=(operation:string)=>fixture.samples.find(s=>s.operation===operation)!;
const copy=(sample:typeof fixture.samples[number])=>JSON.parse(JSON.stringify(sample.response));
describe('native-v2 original-owner action receipts',()=>{
 it('preserves all fifteen original operation samples and joins both signed recovery routes',()=>{
  expect(new Set(fixture.samples.map(s=>s.operation))).toEqual(new Set(NATIVE_FRESH_OPERATIONS.filter(op=>op!=='recover'&&op!=='turn_recover')));
  expect(new Set(recoveryFixture.samples.map(s=>s.operation))).toEqual(new Set(['recover','turn_recover']));
  expect(new Set([...fixture.samples,...recoveryFixture.samples].map(s=>s.operation))).toEqual(new Set(NATIVE_FRESH_OPERATIONS));
 });
 it.each(fixture.samples)('$test / $operation preserves actual DATA without legacy envelope conversion',sample=>{
  const result=decodeNativeFreshResult(sample.response,sample.operation as NativeFreshOperation,sample.arguments);
  expect(result).not.toBeNull();expect(result?.ok).toBe(sample.response.ok);
  if(result?.ok)expect(result.data).toEqual(sample.response.data);
  else expect(result?.error).toEqual(sample.response.error);
  expect(Object.isFrozen(result)).toBe(true);
 });
 it('joins exact selector, response family, original seal and state to the requested operation',()=>{
  for(const operation of ['create','turn_read','stop_status','resume_status']){
   const sample=choose(operation);
   for(const mutate of [
    (v:any)=>{v.data.operation_key='foreign-original';},
    (v:any)=>{v.data.work_ref='WS:Foreign';},
    (v:any)=>{v.operation='preview';},
    (v:any)=>{v.data.schema='mastermind.executive.fresh_conversation_data.v1';},
    (v:any)=>{v.data.parent_consumed=true;},
    (v:any)=>{v.data.extra='unrecognized';},
   ]){
    const value=copy(sample);mutate(value);
    expect(decodeNativeFreshResult(value,operation as NativeFreshOperation,sample.arguments)).toBeNull();
   }
  }
  const sample=choose('turn_read'),value=copy(sample);value.data.result.reference.seal_digest='e'.repeat(64);
  expect(decodeNativeFreshResult(value,'turn_read',sample.arguments)).toBeNull();
  value.data.result=null;expect(decodeNativeFreshResult(value,'turn_read',sample.arguments)).toBeNull();
 });
 it('preserves passive original recovery without inventing current-call effects or Send authority',()=>{
  for(const operation of ['turn_status','turn_read','consume_status']){
   const sample=choose(operation),result=decodeNativeFreshResult(sample.response,operation as NativeFreshOperation,sample.arguments);
   expect(result?.ok&&result.data.effect).toBe('NONE');
   const value=copy(sample);value.data.can_send=true;
   expect(decodeNativeFreshResult(value,operation as NativeFreshOperation,sample.arguments)).toBeNull();
   value.data.can_send=false;value.data.effect='COMMITTED';
   expect(decodeNativeFreshResult(value,operation as NativeFreshOperation,sample.arguments)).toBeNull();
  }
 });
 it('binds Stop/resume receipts to their original operation, including historical unknown state',()=>{
  const sample=choose('stop_status'),value=copy(sample);
  value.data.receipt.command_id='ohf-op:foreign:applied';
  expect(decodeNativeFreshResult(value,'stop_status',sample.arguments)).toBeNull();
  const unknown=copy(sample);unknown.data.state='EFFECT_UNKNOWN';unknown.data.effect='NONE';
  unknown.data.receipt.kind='OPERATOR_OPERATION_EFFECT_UNKNOWN';
  unknown.data.receipt.command_id=unknown.data.operation_id+':effect-unknown';
  expect(decodeNativeFreshResult(unknown,'stop_status',sample.arguments)?.ok).toBe(true);
  unknown.data.effect='UNKNOWN';expect(decodeNativeFreshResult(unknown,'stop_status',sample.arguments)).toBeNull();
  const tooLong=copy(sample);tooLong.data.operation_id='ohf-op:'+'x'.repeat(107);
  tooLong.data.receipt.command_id=tooLong.data.operation_id+':applied';
  expect(decodeNativeFreshResult(tooLong,'stop_status',sample.arguments)).toBeNull();
  const resumed=choose('resume_status'),later=copy(resumed);
  // Protocol permutation: a later current generation does not rewrite the historical target.
  later.data.session.binding_digest='c'.repeat(64);later.data.session.process_generation_id='generation-advanced';
  const result=decodeNativeFreshResult(later,'resume_status',resumed.arguments);
  expect(result?.ok).toBe(true);
  if(result?.ok&&result.data.schema==='mastermind.executive.fresh_conversation_control_data.v2'){
   expect(result.data.target).toEqual(resumed.response.data!.target);
   expect(result.data.target?.binding_digest).not.toBe(result.data.session?.binding_digest);
  }
 });
 it('refuses contradictory preview/absent controls and missing required original turn anchors',()=>{
  const preview=choose('resume_preview'),value=copy(preview);
  value.data.operation_id='ohf-op:not-yet-issued';
  expect(decodeNativeFreshResult(value,'resume_preview',preview.arguments)).toBeNull();
  value.data.operation_id=null;value.data.target.binding_digest='e'.repeat(64);
  expect(decodeNativeFreshResult(value,'resume_preview',preview.arguments)).toBeNull();
  const stop=choose('stop_status'),absent=copy(stop);absent.data.state='ABSENT';
  expect(decodeNativeFreshResult(absent,'stop_status',stop.arguments)).toBeNull();
  const turn=choose('turn_read'),missing=copy(turn);missing.data.initial_consumption=null;
  expect(decodeNativeFreshResult(missing,'turn_read',turn.arguments)).toBeNull();
 });
 it('rejects accessors, invalid UTF-8 keys and the full private-wrapper budget overflow',()=>{
  const sample=choose('preview'),value=copy(sample);
  value.data.preview.grounding={'':0};
  expect(decodeNativeFreshResult(value,'preview',sample.arguments)?.ok).toBe(true);
  value.data.preview.grounding={['\ud800']:0};
  expect(decodeNativeFreshResult(value,'preview',sample.arguments)).toBeNull();
  const getter=vi.fn(()=>({}));Object.defineProperty(value.data.preview,'grounding',{enumerable:true,get:getter});
  expect(decodeNativeFreshResult(value,'preview',sample.arguments)).toBeNull();expect(getter).not.toHaveBeenCalled();
  const bound=copy(sample);bound.data.preview.grounding={padding:''};
  const current=new TextEncoder().encode(JSON.stringify(bound)).length;
  bound.data.preview.grounding.padding='x'.repeat(32760-current);
  expect(new TextEncoder().encode(JSON.stringify(bound)).length).toBeLessThan(32768);
  expect(decodeNativeFreshResult(bound,'preview',sample.arguments)).toBeNull();
 });

 it.each(recoveryFixture.samples)('$test preserves the recovered original answer and current-call effect semantics',sample=>{
  const operation=sample.operation as NativeFreshOperation;
  const result=decodeNativeFreshResult(sample.response,operation,sample.arguments);
  expect(result?.ok).toBe(true);if(result?.ok)expect(result.data).toEqual(sample.response.data);
  expect(sample.response.data.effect).toBe('NONE');expect(sample.response.data.can_send).toBe(false);
  for(const mutate of [
   ...(operation==='turn_recover'?[(v:any)=>{v.data.can_send=true;}]:[]),
   (v:any)=>{v.data.effect='COMMITTED';},
   (v:any)=>{v.data.extra='unrecognized';},
   (v:any)=>{v.data.operation_key='mmos-native-create-'+'f'.repeat(40);},
   (v:any)=>{v.data.result=null;},
   (v:any)=>{v.data.schema='mastermind.executive.fresh_conversation_control_data.v2';},
  ]){
   const value:any=structuredClone(sample.response);mutate(value);
   expect(decodeNativeFreshResult(value,operation,sample.arguments)).toBeNull();
  }
 });
});
