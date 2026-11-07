import {describe,expect,it,vi} from 'vitest';
import fixture from '../../fixtures/native-fresh-transport-owner.json';
import {NATIVE_FRESH_OPERATIONS,nativeMessage,validateNativeFreshRequest,type NativeFreshOperation} from './native-fresh-request';
import {freshConversationArguments,freshConversationPath,freshConversationNeedsWorkspace} from '../../orchestration/fresh-conversation-transport';
const hex='b'.repeat(64);
const selector={work_ref:fixture.request.work_ref,operation_key:fixture.request.operation_key};
function request(operation:NativeFreshOperation){
  if(operation==='preview')return fixture.request;
  if(operation==='create')return {...fixture.request,preview_digest:hex};
  if(operation==='consume'||operation==='consume_status')return {...selector,initial_digest:fixture.send.initial_digest};
  if(operation==='turn_preview'){const {preview_digest,...preview}=fixture.send;return preview;}
  if(operation==='turn')return fixture.send;
  if(operation==='turn_status'||operation==='turn_read'||operation==='turn_recover')return {...selector,turn_key:fixture.send.turn_key};
  if(operation==='stop')return {...selector,stop_key:'original-stop',turn_id:'original-native-turn',binding_digest:hex};
  if(operation==='stop_status')return {...selector,stop_key:'original-stop'};
  if(operation==='resume_status')return {...selector,resume_key:'original-resume'};
  if(operation==='resume_preview')return {...selector,resume_key:'original-resume',expected_result_digest:hex};
  if(operation==='resume')return {...selector,resume_key:'original-resume',expected_result_digest:hex,preview_digest:hex};
  return selector;
}
describe('native-v2 closed syntax on the incumbent carrier',()=>{
 it.each(NATIVE_FRESH_OPERATIONS)('preserves exact %s fields and chooses only its explicit v2 route',(operation)=>{
  const raw=request(operation),copy=freshConversationArguments(operation,raw,'native-v2');
  expect(copy).toEqual(raw);expect(copy).not.toBe(raw);expect(Object.isFrozen(copy)).toBe(true);
  expect(freshConversationPath(operation,'native-v2')).toBe('conversation/v2/'+operation.replaceAll('_','/'));
  expect(freshConversationNeedsWorkspace(operation,'native-v2')).toBe(
   ['preview','create','consume','turn_preview','turn','resume_preview','resume','stop','recover','turn_recover'].includes(operation));
  for(const extra of ['principal','auth','can_send','source_generation'])
   expect(()=>validateNativeFreshRequest({...raw,[extra]:'foreign'},operation)).toThrow();
 });
 it('uses the actual owner 128KiB message unchanged without relaxing legacy syntax',()=>{
  expect(new TextEncoder().encode(fixture.request.message)).toHaveLength(131072);
  expect(validateNativeFreshRequest(fixture.request,'preview').message).toBe(fixture.request.message);
  expect(()=>freshConversationArguments('preview',fixture.request)).toThrow();
  expect(()=>nativeMessage(fixture.request.message+'a')).toThrow();
  expect(nativeMessage('😀'.repeat(32768))).toHaveLength(65536);
  expect(()=>nativeMessage('😀'.repeat(32768)+'a')).toThrow();
  expect(nativeMessage('\uFEFF')).toBe('\uFEFF');
 });
 it.each(['',' \t\r\n','x\u0000','x\u0085','\ud800','\udfff'])('refuses invalid native text %j',message=>{
  expect(()=>nativeMessage(message)).toThrow();
 });
 it('refuses accessors without invoking them and requires the real turn preview digest',()=>{
  const getter=vi.fn(()=>fixture.request.message),raw=Object.defineProperty({...fixture.request},'message',{enumerable:true,get:getter});
  expect(()=>validateNativeFreshRequest(raw,'preview')).toThrow();expect(getter).not.toHaveBeenCalled();
  const {preview_digest,...before}=fixture.send;
  expect(()=>validateNativeFreshRequest(before,'turn')).toThrow();
  expect(validateNativeFreshRequest(before,'turn_preview')).toEqual(before);
  expect(()=>freshConversationArguments('stop',request('stop'))).toThrow();
  expect(()=>freshConversationPath('read','other' as never)).toThrow();
 });
 it('keeps root read provenance separate from native result references',()=>{
  const reference={schema:'mastermind.fresh_conversation_reference.v1',work_ref:selector.work_ref,
   root_job_id:'JOB-42',root_event_id:42,root_event_sha256:hex,principal_scope_sha256:hex};
  expect(validateNativeFreshRequest({work_ref:selector.work_ref,reference},'status').reference).toEqual(reference);
  expect(()=>validateNativeFreshRequest({work_ref:selector.work_ref,reference:fixture.initial.data.result!.reference},'status')).toThrow();
  expect(()=>validateNativeFreshRequest({...selector,reference},'status')).toThrow();
  expect(()=>validateNativeFreshRequest({work_ref:selector.work_ref,reference:{...reference,work_ref:'WS:Foreign'}},'read')).toThrow();
  expect(()=>validateNativeFreshRequest({work_ref:selector.work_ref,reference,message:'original'},'preview')).toThrow();
 });
});

it.each(['recover','turn_recover'] as const)('recovery %s accepts only its original selector',operation=>{
 const original=request(operation);
 for(const field of ['message','preview_digest','initial_digest','binding_digest','turn_id','replacement_key'])
  expect(()=>validateNativeFreshRequest({...original,[field]:'not-original'},operation)).toThrow();
 expect(()=>freshConversationPath(operation,'legacy-v1')).toThrow();
});
