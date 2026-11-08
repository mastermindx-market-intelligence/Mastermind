// @vitest-environment jsdom
/** Exported from actual Fresh Runtime -> original private socket -> donor JSONL.
 * Frontend auth/transport are explicit seams; no installed/provider claim.
 */
import {afterEach,describe,expect,it} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {createElement} from 'react';
import fixture from '../fixtures/native-fresh-content-owner.json';
import {canonicalJson} from '../orchestration/operation-key';
import {decodeFreshConversationReadRequest,type FreshConversationReadRequest} from './fresh-conversation-reference';
import {decodeFreshNativeContent,decodeFreshNativeAnswer} from './fresh-native-content';
import {createProjectConversationCatalogueOwner} from './project-conversation-catalogue-owner';
import {NativeConversationRecord} from './NativeConversationRecord';
afterEach(cleanup);
const work=fixture.catalogue.work_ref;
function ownerCase(onRead?:(request:FreshConversationReadRequest)=>void,change?:(value:any)=>any){
  let auth=1,listener=()=>{};
  const reads:FreshConversationReadRequest[]=[];
  const transport={
    context:()=>({workRef:work,principalScope:'a'.repeat(64),generation:'original-read'}),
    authGeneration:()=>auth,available:()=>true,subscribe:(fn:()=>void)=>{listener=fn;return()=>{};},
    catalogue:async()=>{throw Error('unselected source');},read:async()=>{throw Error('unselected source');},
    freshReferences:async()=>fixture.catalogue,
    readFreshReference:async(request:FreshConversationReadRequest)=>{
      reads.push(request);onRead?.(request);
      if(!request.content)return fixture.window;
      const part=fixture.fragments.find(row=>row.request.content.offset_bytes===request.content!.offset_bytes);
      if(!part||canonicalJson(part.request)!==canonicalJson(request))throw Error('wrong original selector');
      return change?change(structuredClone(part.response)):part.response;
    },
  };
  const owner=createProjectConversationCatalogueOwner({transport,workRef:()=>work,selectionGeneration:()=> 'same-project'});
  return {owner,reads,revoke:()=>{auth++;listener();}};
}
async function selected(h:ReturnType<typeof ownerCase>){
  const signal=new AbortController().signal,page=await h.owner.freshCatalogue({workRef:work,signal});
  const window=await h.owner.readFresh(page.entries[0]!.reference,signal);
  if(window.schema!=='mastermind.fresh_conversation_window.v3'||!window.initial_result)throw Error();
  return {window,result:window.initial_result,signal};
}
describe('original native answer recovery',()=>{
  it('reassembles the exact original answer and keeps native context/source records',async()=>{
    const h=ownerCase(),{window,result,signal}=await selected(h);
    const answer=await h.owner.readFreshResult(window,result,signal);
    expect(answer.messages.join('')).toBe(fixture.answer);
    expect(answer.records).toHaveLength(7);
    expect(answer.state).toBe('CONTENT');
    expect(Object.isFrozen(answer.records)).toBe(true);
    expect(h.reads.filter(row=>row.content)).toHaveLength(24);
    expect(JSON.stringify(answer)).not.toContain('A different later answer');
  });
  it('withholds bytes after an authorization change without a retry',async()=>{
    let h:ReturnType<typeof ownerCase>;
    h=ownerCase(request=>{if(request.content)h.revoke();});
    const {window,result,signal}=await selected(h);
    await expect(h.owner.readFreshResult(window,result,signal)).rejects.toThrow();
    expect(h.reads.filter(row=>row.content)).toHaveLength(1);
    expect(h.owner.currentFresh(window)).toBe(false);
  });
  it('does not read copied or unissued result references',async()=>{
    const h=ownerCase(),{window,result,signal}=await selected(h);
    await expect(h.owner.readFreshResult(window,{...result},signal)).rejects.toThrow();
    expect(h.reads.filter(row=>row.content)).toHaveLength(0);
  });
  it.each(['claim','session','digest','offset','length','base64','terminal','reference'])('rejects substituted %s',async fault=>{
    const h=ownerCase(undefined,value=>{
      if(fault==='claim')value.native.claim.messageId='foreign';
      if(fault==='session')value.native_session_id='foreign';
      if(fault==='digest')value.native.content.sha256='f'.repeat(64);
      if(fault==='offset')value.native.content.next_offset_bytes=1;
      if(fault==='length')value.native.content.total_bytes=4194305;
      if(fault==='base64')value.native.content.data+='=';
      if(fault==='terminal')value.native.terminal.throughSeq=0;
      if(fault==='reference')value.content.native_ref.event_id++;
      return value;
    });
    const {window,result,signal}=await selected(h);
    await expect(h.owner.readFreshResult(window,result,signal)).rejects.toThrow();
  });
  it('requires complete hash-qualified native records before rendering',()=>{
    const first=fixture.fragments[0]!,decoded=decodeFreshNativeContent(first.response,first.request as FreshConversationReadRequest);
    const all=Uint8Array.from(fixture.fragments.flatMap(row=>Array.from(atob(row.response.native.content.data),c=>c.charCodeAt(0))));
    expect(decodeFreshNativeAnswer(all,decoded).messages[0]).toBe(fixture.answer);
    all[all.length-10]^=1;
    expect(()=>decodeFreshNativeAnswer(all,decoded)).toThrow();
    expect(()=>decodeFreshConversationReadRequest({...first.request,before_event_id:100},work)).toThrow();
    expect(()=>decodeFreshConversationReadRequest({...first.request,content:{...first.request.content,offset_bytes:1}},work)).toThrow();
  });
  it('renders the qualified reply on request and withdraws it with the same read ticket',async()=>{
    const h=ownerCase(),{window,result,signal}=await selected(h);
    const props={input:window.initial_input,result,current:()=>h.owner.currentFresh(window),
      readInput:async()=>window.initial_input.preview,
      readResult:()=>h.owner.readFreshResult(window,result,signal)};
    const view=render(createElement(NativeConversationRecord,props));
    expect(h.reads.filter(row=>row.content)).toHaveLength(0);
    fireEvent.click(screen.getByRole('button',{name:'Read reply'}));
    await waitFor(()=>expect(view.container.textContent).toContain('Original answer — 原样保留 🧭'));
    h.revoke();view.rerender(createElement(NativeConversationRecord,props));
    expect(view.container.textContent).not.toContain('Original answer — 原样保留 🧭');
  });
});
