import {expect,it} from 'vitest';
import fixture from '../fixtures/project-conversation-catalogue-owner.json';
import {decodeProjectConversationCatalogue,decodeProjectConversationRead} from './project-conversation-catalogue-contract';

it('preserves the actual Runtime UTC offset and allows canonical 64-character work keys',()=>{
  expect(decodeProjectConversationCatalogue(fixture.catalogue,fixture.catalogue.work_ref).conversations[0]!.last_request_at)
    .toBe(fixture.catalogue.conversations[0]!.last_request_at);
  const work='WS:'+'A'.repeat(64);
  expect(decodeProjectConversationCatalogue({...fixture.catalogue,work_ref:work},work).work_ref).toBe(work);
  expect(()=>decodeProjectConversationCatalogue({...fixture.catalogue,work_ref:'WS:A'},'WS:A')).toThrow();
});

it.each(['work_ref','conversation_ref','revision','read_ref','root_job_id','last_request_at'])('rejects trailing newline on exact protocol coordinate %s',field=>{
  const value=structuredClone(fixture.catalogue);
  if(field==='work_ref')value.work_ref+='\n';
  else if(field==='read_ref')value.conversations[0]!.requests[0]!.read_ref+='\n';
  else (value.conversations[0] as unknown as Record<string,string>)[field]+='\n';
  expect(()=>decodeProjectConversationCatalogue(value,fixture.catalogue.work_ref)).toThrow();
});

it('reads descriptor values only, including object and array Proxy inputs',()=>{
  const value=structuredClone(fixture.catalogue);let gets=0;
  const proxy=<T extends object>(target:T):T=>new Proxy(target,{get(){gets++;throw Error('unsafe get');}});
  value.conversations[0]!.requests=proxy(value.conversations[0]!.requests);
  value.conversations[0]=proxy(value.conversations[0]!);
  const decoded=decodeProjectConversationCatalogue(proxy(value),value.work_ref);
  expect(decoded.conversations).toHaveLength(1);expect(gets).toBe(0);
});

it('rejects an accessor in the expected read witness without executing it',()=>{
  const row=fixture.catalogue.conversations[0]!;let gets=0;
  const expected={get workRef(){gets++;return fixture.catalogue.work_ref;},conversationRef:row.conversation_ref,revision:row.revision,requests:row.requests};
  expect(()=>decodeProjectConversationRead(fixture.read,expected)).toThrow();expect(gets).toBe(0);
});
