// @vitest-environment jsdom
/** Real original Runtime/READ DTO; frontend transport/auth are explicit seams. */
import {describe,expect,it,vi} from 'vitest';
import fixture from '../fixtures/native-fresh-conversation-owner.json';
import {sha256Hex} from '../orchestration/operation-key';
import {decodeFreshConversationHistoryCatalogue,decodeFreshConversationHistoryWindow,
  decodeFreshConversationInputFragment,decodeFreshConversationReadRequest,
  type FreshConversationReadRequest} from './fresh-conversation-reference';
import {createProjectConversationCatalogueOwner} from './project-conversation-catalogue-owner';

const work=fixture.catalogue.work_ref;
function nativeWindow(){
  const page=decodeFreshConversationHistoryCatalogue(fixture.catalogue,work);
  const value=decodeFreshConversationHistoryWindow(fixture.window,page.entries[0]!.reference);
  if(value.schema!=='mastermind.fresh_conversation_window.v3')throw Error('expected actual native fixture');
  return {page,value};
}
function fragment(request:FreshConversationReadRequest){
  const selected=request.fragment!;
  const original=selected.kind==='initial_input'?fixture.initial_message:fixture.followup_message;
  const bytes=new TextEncoder().encode(original),start=selected.offset_utf8;
  let end=Math.min(start+4096,bytes.length),part='';
  for(;end>start;end--){try{part=new TextDecoder('utf-8',{fatal:true}).decode(bytes.slice(start,end));break;}catch{}}
  return {schema:'mastermind.fresh_conversation_input_fragment.v1',reference:fixture.window.reference,
    fragment:selected,text:part,utf8_bytes:bytes.length,next_offset_utf8:end===bytes.length?null:end};
}
function ownerCase(onRead?:(request:FreshConversationReadRequest)=>void){
  let auth=1,listener=()=>{};
  const reads:FreshConversationReadRequest[]=[];
  const transport={
    context:()=>({workRef:work,principalScope:'a'.repeat(64),generation:'original-read'}),
    authGeneration:()=>auth,available:()=>true,
    subscribe:(value:()=>void)=>{listener=value;return()=>{};},
    catalogue:async()=>{throw Error('legacy source is not this fixture');},
    read:async()=>{throw Error('legacy source is not this fixture');},
    freshReferences:async()=>fixture.catalogue,
    readFreshReference:async(request:FreshConversationReadRequest)=>{
      reads.push(request);onRead?.(request);return request.fragment?fragment(request):fixture.window;
    },
  };
  const owner=createProjectConversationCatalogueOwner({transport,workRef:()=>work,selectionGeneration:()=> 'same-project'});
  return {owner,reads,revoke:()=>{auth++;listener();}};
}

describe('native immutable history',()=>{
  it('decodes actual native result references without a role envelope or a Send grant',()=>{
    const {page,value}=nativeWindow();
    expect(page.schema).toBe('mastermind.fresh_conversation_references.v2');
    expect(value.initial_input.utf8_bytes).toBe(131072);
    expect(value.turns[0]!.input.utf8_bytes).toBe(131072);
    expect(value.initial_result?.contract).toBe('mastermind.dsh_native_conversation/v1');
    expect(value.head_result).toEqual(value.turns[0]!.result);
    expect(value.initial_result).not.toHaveProperty('envelope');
    expect(value.can_send).toBe(false);
    expect(Object.isFrozen(value.turns[0]!.input)).toBe(true);
  });
  it('reconstructs exact 128KiB Unicode and whitespace through the existing READ owner',async()=>{
    const {owner,reads}=ownerCase(),signal=new AbortController().signal;
    const page=await owner.freshCatalogue({workRef:work,signal});
    const window=await owner.readFresh(page.entries[0]!.reference,signal);
    if(window.schema!=='mastermind.fresh_conversation_window.v3')throw Error();
    expect(await owner.readFreshInput(window,window.initial_input,undefined,signal)).toBe(fixture.initial_message);
    expect(await owner.readFreshInput(window,window.turns[0]!.input,window.turns[0]!.turn_key,signal)).toBe(fixture.followup_message);
    expect(reads.filter(r=>r.fragment).length).toBeGreaterThanOrEqual(64);
    expect(sha256Hex(fixture.followup_message)).toBe(window.turns[0]!.input.sha256);
  });
  it('withdraws an incomplete range read at the original auth boundary',async()=>{
    let current:ReturnType<typeof ownerCase>;
    current=ownerCase(request=>{if(request.fragment)current.revoke();});
    const signal=new AbortController().signal,page=await current.owner.freshCatalogue({workRef:work,signal});
    const window=await current.owner.readFresh(page.entries[0]!.reference,signal);
    if(window.schema!=='mastermind.fresh_conversation_window.v3')throw Error();
    await expect(current.owner.readFreshInput(window,window.initial_input,undefined,signal)).rejects.toThrow();
    expect(current.reads.filter(r=>r.fragment)).toHaveLength(1);
    expect(current.owner.currentFresh(window)).toBe(false);
  });
  it('does not issue reads for copied input descriptors or another turn',async()=>{
    const {owner,reads}=ownerCase(),signal=new AbortController().signal;
    const page=await owner.freshCatalogue({workRef:work,signal}),window=await owner.readFresh(page.entries[0]!.reference,signal);
    if(window.schema!=='mastermind.fresh_conversation_window.v3')throw Error();
    await expect(owner.readFreshInput(window,{...window.initial_input},undefined,signal)).rejects.toThrow();
    await expect(owner.readFreshInput(window,window.turns[0]!.input,'foreign-key',signal)).rejects.toThrow();
    expect(reads.filter(r=>r.fragment)).toHaveLength(0);
  });
  it('rejects wrong source, seal, completeness, page and selector joins',()=>{
    for(const alter of [
      (v:any)=>{v.initial_input.source_event_sha256='0'.repeat(64);},
      (v:any)=>{v.initial_input.complete=true;},
      (v:any)=>{v.initial_input.utf8_bytes=131073;},
      (v:any)=>{v.initial_result.digest='0'.repeat(64);},
      (v:any)=>{v.initial_result.reference.command_id='foreign-result';},
      (v:any)=>{v.turns[0].input.source_event_id=v.reference.root_event_id;},
      (v:any)=>{v.can_send=true;},
    ]){
      const value=structuredClone(fixture.window);alter(value);
      expect(()=>decodeFreshConversationHistoryWindow(value,fixture.window.reference)).toThrow();
    }
    const {value}=nativeWindow(),input=value.initial_input;
    const selected={...value.reference,fragment:{kind:'initial_input' as const,source_event_id:input.source_event_id,
      source_event_sha256:input.source_event_sha256,sha256:input.sha256,offset_utf8:0}};
    const response=fragment(selected);
    expect(decodeFreshConversationInputFragment(response,selected).text).toBe(response.text);
    for(const bad of [{...response,next_offset_utf8:1},{...response,utf8_bytes:1},
      {...response,fragment:{...selected.fragment,sha256:'0'.repeat(64)}}]){
      expect(()=>decodeFreshConversationInputFragment(bad,selected)).toThrow();
    }
    expect(()=>decodeFreshConversationReadRequest({...selected,before_event_id:99},work)).toThrow();
    expect(()=>decodeFreshConversationReadRequest({...selected,fragment:{...selected.fragment,offset_utf8:131072}},work)).toThrow();
    let gets=0;const getter=structuredClone(fixture.window);
    Object.defineProperty(getter.initial_input,'preview',{enumerable:true,get(){gets++;return 'forged';}});
    expect(()=>decodeFreshConversationHistoryWindow(getter,fixture.window.reference)).toThrow();expect(gets).toBe(0);
  });
});
