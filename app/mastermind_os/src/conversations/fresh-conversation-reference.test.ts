/** Syntax/adversarial fixtures only. Actual S34 owner DTO join is separate. */
import {expect,it} from 'vitest';
import {decodeFreshConversationReference,decodeFreshConversationCatalogue} from './fresh-conversation-reference';
const work='WS:DEMO';
const reference=()=>({schema:'mastermind.fresh_conversation_reference.v1',work_ref:work,root_job_id:'JOB-001',
  root_event_id:1,root_event_sha256:'a'.repeat(64),principal_scope_sha256:'b'.repeat(64)});
const page=(message='原始消息\n  literal lines preserved')=>({schema:'mastermind.fresh_conversation_references.v1',work_ref:work,state:'AVAILABLE',
  coverage:{state:'COMPLETE',limit:8,returned:1},entries:[{kind:'fresh_native',reference:reference(),initial_message:message,root_state:'RUNNING'}]});

it('detaches and freezes the exact original reference without a synthetic operation key',()=>{
  const raw=reference(),value=decodeFreshConversationReference(raw,work);raw.root_event_sha256='f'.repeat(64);
  expect(value.root_event_sha256).toBe('a'.repeat(64));expect(Object.isFrozen(value)).toBe(true);
  expect(Object.keys(value)).not.toContain('operation_key');
});
it('preserves canonical literal Unicode and line breaks, including source-valid U+FEFF',()=>{
  const message='\ufeff\n中文\t  original';const value=decodeFreshConversationCatalogue(page(message),work);
  expect(value.entries[0]!.initial_message).toBe(message);expect(Object.isFrozen(value.entries[0]!.reference)).toBe(true);
  expect(decodeFreshConversationCatalogue(page('😀'.repeat(700)),work).entries).toHaveLength(1);
});
it.each(['work','root','sha','extra','native'])('rejects foreign or malformed reference coordinates %s',fault=>{
  const value:Record<string,unknown>=reference();
  if(fault==='work')value.work_ref='WS:FOREIGN';if(fault==='root')value.root_job_id='JOB-001\n';
  if(fault==='sha')value.root_event_sha256='a'.repeat(64)+'\n';if(fault==='extra')value.operation_key='not-a-grant';
  if(fault==='native')value.provider_session_id='caller-provider';
  expect(()=>decodeFreshConversationReference(value,work)).toThrow();
});
it('rejects reference accessors and descriptor traps without executing getters',()=>{
  const value=reference();let gets=0;
  Object.defineProperty(value,'root_event_id',{enumerable:true,get(){gets++;return 1;}});
  expect(()=>decodeFreshConversationReference(value,work)).toThrow();expect(gets).toBe(0);
});
it('rejects duplicate roots and mismatched coverage counts',()=>{
  const value=page();value.entries.push({...value.entries[0]!});value.coverage.returned=2;
  expect(()=>decodeFreshConversationCatalogue(value,work)).toThrow();
  const second=page();second.coverage.returned=0;expect(()=>decodeFreshConversationCatalogue(second,work)).toThrow();
});
it.each(['\u0000','\u007f','\u0085','\ud800',' '.repeat(8),'😀'.repeat(701)])('rejects source-invalid message syntax',message=>{
  expect(()=>decodeFreshConversationCatalogue(page(message),work)).toThrow();
});
