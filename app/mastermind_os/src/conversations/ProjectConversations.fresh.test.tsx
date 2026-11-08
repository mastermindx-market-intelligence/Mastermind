// @vitest-environment jsdom
/** Same immutable D4B signed-source run: real Create/Runtime/seal/reference
 * reader/consume/follow-up/archive DTO. Client transport/auth are synthetic;
 * these tests do not invoke creation, consumption, send or a live provider. */
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import fixture from '../fixtures/project-fresh-conversation-owner.json';
import {canonicalJson,sha256Hex} from '../orchestration/operation-key';
import {decodeFreshConversationCatalogue,decodeFreshConversationWindow} from './fresh-conversation-reference';
import {createProjectConversationCatalogueOwner,type ProjectConversationCatalogueTransport} from './project-conversation-catalogue-owner';
import {ProjectConversations,type ProjectConversationsProps} from './ProjectConversations';
afterEach(cleanup);
const work=fixture.catalogue.work_ref,reference=fixture.catalogue.entries[0]!.reference;

function make(){
  const state={auth:0,selection:'project-1',generation:'authenticated-read-1',window:structuredClone(fixture.initial_read) as unknown};
  const listeners=new Set<()=>void>();
  const transport:ProjectConversationCatalogueTransport={
    context:()=>({workRef:work,principalScope:'1'.repeat(64),generation:state.generation}),
    authGeneration:()=>state.auth,available:()=>true,subscribe(listener){listeners.add(listener);return()=>{listeners.delete(listener);};},
    refreshContext:vi.fn(async()=>{}),catalogue:vi.fn(async()=>{throw Error('old session source unavailable');}),read:vi.fn(async()=>{throw Error('not an old session');}),
    freshReferences:vi.fn(async()=>fixture.catalogue),readFreshReference:vi.fn(async()=>state.window),
  };
  const owner=createProjectConversationCatalogueOwner({transport,workRef:()=>work,selectionGeneration:()=>state.selection});
  return {state,transport,owner,notify(){for(const listener of listeners)listener();}};
}

it('validates actual new and archived windows without an invented generic target or operation key',()=>{
  const page=decodeFreshConversationCatalogue(fixture.catalogue,work);
  expect(page.entries[0]!.initial_message).toBe(fixture.request.message);
  const initial=decodeFreshConversationWindow(fixture.initial_read,page.entries[0]!.reference);
  const archived=decodeFreshConversationWindow(fixture.archived_read,page.entries[0]!.reference);
  expect(initial.state).toBe('RETAINED');expect(initial.epoch).not.toBeNull();
  expect(archived.state).toBe('SETTLED');expect(archived.epoch).toBeNull();
  expect(archived.turns[0]!.message).toBe(fixture.turn_request.message);
  expect(archived.turns[0]!.result).toEqual(fixture.archived_read.turns[0]!.result);
  expect(Object.keys(initial)).not.toContain('operation_key');expect(initial.can_send).toBe(false);
});

it('actual Create→new-owner catalogue→Open→Back→archived reopen preserves literal first message and query',async()=>{
  const s=make();render(<ProjectConversations workRef={work} owner={s.owner}/>);
  expect(s.transport.freshReferences).not.toHaveBeenCalled();expect(s.transport.readFreshReference).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Read project conversations'}));
  const open=await screen.findByRole('button',{name:'Open'});
  expect(s.transport.freshReferences).toHaveBeenCalledTimes(1);
  expect(vi.mocked(s.transport.freshReferences!).mock.calls[0]![0]).toEqual({work_ref:work});
  fireEvent.change(screen.getByRole('textbox',{name:'Find in these conversations'}),{target:{value:'新对话'}});
  fireEvent.click(open);
  await screen.findByText(fixture.initial_read.initial_result.envelope.summary);
  expect(screen.getByText(fixture.initial_read.initial_message,{normalizer:value=>value}).textContent).toBe(fixture.request.message);
  expect(vi.mocked(s.transport.readFreshReference!).mock.calls[0]![0]).toEqual(reference);
  expect(screen.queryByRole('button',{name:/send|resume|consume/i})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Back to conversations'}));
  expect((screen.getByRole('textbox',{name:'Find in these conversations'}) as HTMLInputElement).value).toBe('新对话');
  expect(screen.getByRole('button',{name:'Open'})).toBe(document.activeElement);
  s.state.window=fixture.archived_read;fireEvent.click(screen.getByRole('button',{name:'Open'}));
  await screen.findByText(fixture.archived_read.turns[0]!.result.envelope.summary);
  expect(screen.getByText(fixture.turn_request.message)).toBeTruthy();
  expect(s.transport.freshReferences).toHaveBeenCalledTimes(1);expect(s.transport.readFreshReference).toHaveBeenCalledTimes(2);
  fireEvent.keyDown(window,{key:'Escape'});expect(screen.getByRole('button',{name:'Open'})).toBe(document.activeElement);
});

it.each(['reference','locator','digest','capability','consumption','turn'])('withholds inconsistent actual-window tuple %s',fault=>{
  const value=structuredClone(fixture.archived_read);
  if(fault==='reference')value.reference.root_event_sha256='f'.repeat(64);
  if(fault==='locator')value.locator.root_job_id='JOB-999';
  if(fault==='digest')value.initial_result.digest='f'.repeat(64);
  if(fault==='capability')(value as unknown as {can_send:boolean}).can_send=true;
  if(fault==='consumption')value.initial_consumption.initial_digest='f'.repeat(64);
  if(fault==='turn')value.turns[0]!.result.envelope.job_id='JOB-999';
  expect(()=>decodeFreshConversationWindow(value,reference)).toThrow();
});

it('wrong child remains refused even when its forged result has a matching digest',()=>{
  const value=structuredClone(fixture.initial_read);value.initial_result.envelope.job_id='JOB-999';
  value.initial_result.digest=sha256Hex(canonicalJson(value.initial_result.envelope));
  expect(()=>decodeFreshConversationWindow(value,reference)).toThrow();
});

it('a result accessor is refused without executing it before shared digest decoding',()=>{
  const value=structuredClone(fixture.initial_read);let gets=0;
  Object.defineProperty(value.initial_result.envelope,'summary',{enumerable:true,get(){gets++;return 'must not run';}});
  expect(()=>decodeFreshConversationWindow(value,reference)).toThrow();expect(gets).toBe(0);
});

it('fresh membership is tied to its acquired READ epoch before any subsequent Open',async()=>{
  for(const change of ['auth','selection','method']){
    const s=make(),signal=new AbortController().signal;
    await s.owner.refresh();await s.owner.freshCatalogue({workRef:work,signal});
    if(change==='auth')s.state.auth++;
    if(change==='selection')s.state.selection='project-ABA-3';
    if(change==='method')s.transport.readFreshReference=vi.fn(async()=>fixture.initial_read);
    await expect(s.owner.readFresh(reference,signal)).rejects.toThrow();
    expect(s.transport.readFreshReference).not.toHaveBeenCalled();s.owner.dispose();
  }
});

it('late fresh Open is withheld after current principal/source withdrawal',async()=>{
  const s=make();let finish!:(value:unknown)=>void;
  s.transport.readFreshReference=vi.fn(()=>new Promise(resolve=>{finish=resolve;}));s.owner.dispose();
  const owner=createProjectConversationCatalogueOwner({transport:s.transport,workRef:()=>work,selectionGeneration:()=>s.state.selection});
  render(<ProjectConversations workRef={work} owner={owner}/>);
  fireEvent.click(screen.getByRole('button',{name:'Read project conversations'}));fireEvent.click(await screen.findByRole('button',{name:'Open'}));
  s.state.auth++;s.notify();await act(async()=>{finish(fixture.initial_read);});
  expect(screen.queryByText(fixture.initial_read.initial_result.envelope.summary)).toBeNull();
});

it('a changed first message under the same reference is withheld against catalogue membership',async()=>{
  const s=make(),signal=new AbortController().signal;await s.owner.refresh();await s.owner.freshCatalogue({workRef:work,signal});
  s.state.window={...fixture.initial_read,initial_message:'A different original question'};
  await expect(s.owner.readFresh(reference,signal)).rejects.toThrow();
});

it('only the issued current body is a live read witness, and explicit invalidation retires it',async()=>{
  const s=make(),signal=new AbortController().signal;await s.owner.refresh();await s.owner.freshCatalogue({workRef:work,signal});
  const value=await s.owner.readFresh(reference,signal);
  expect(s.owner.currentFresh(value)).toBe(true);expect(s.owner.currentFresh(structuredClone(value))).toBe(false);
  s.owner.invalidateFreshRead();expect(s.owner.currentFresh(value)).toBe(false);
  const next=await s.owner.readFresh(reference,signal);expect(s.owner.currentFresh(next)).toBe(true);
});

it('a late older read cannot replace a newer issued archived window',async()=>{
  const s=make(),signal=new AbortController().signal;let first!:(value:unknown)=>void,second!:(value:unknown)=>void,calls=0;
  s.transport.readFreshReference=vi.fn(()=>new Promise(resolve=>{if(calls++===0)first=resolve;else second=resolve;}));s.owner.dispose();
  const owner=createProjectConversationCatalogueOwner({transport:s.transport,workRef:()=>work,selectionGeneration:()=>s.state.selection});
  await owner.refresh();await owner.freshCatalogue({workRef:work,signal});
  const old=owner.readFresh(reference,signal);const oldOutcome=old.catch(error=>error);
  const latest=owner.readFresh(reference,signal);second(fixture.archived_read);const current=await latest;
  first(fixture.initial_read);expect(await oldOutcome).toBeInstanceOf(Error);expect(owner.currentFresh(current)).toBe(true);
});

it('the optional attended slot receives a stable issued read witness and only explicit local invalidation/refresh',async()=>{
  const s=make();let supplied:Parameters<NonNullable<ProjectConversationsProps['renderFreshContinuation']>>[0]|null=null;
  const slot:NonNullable<ProjectConversationsProps['renderFreshContinuation']>=source=>{supplied=source;return <p>Read-only supplied slot</p>;};
  const view=render(<ProjectConversations workRef={work} owner={s.owner} renderFreshContinuation={slot}/>);
  fireEvent.click(screen.getByRole('button',{name:'Read project conversations'}));fireEvent.click(await screen.findByRole('button',{name:'Open'}));
  await screen.findByText('Read-only supplied slot');const captured=supplied!;
  expect(captured.current()).toBe(true);expect(captured.reference).toEqual(reference);
  view.rerender(<ProjectConversations workRef={work} owner={s.owner} locale="zh-CN" renderFreshContinuation={slot}/>);
  expect(supplied).toBe(captured);expect(captured.current()).toBe(true);
  act(()=>captured.refresh());
  await waitFor(()=>expect(s.transport.readFreshReference).toHaveBeenCalledTimes(2));
  await waitFor(()=>expect(supplied!.current()).toBe(true));
  expect(captured.current()).toBe(false);
  expect(screen.getByRole('button',{name:'返回对话列表'})).toBeTruthy();
  expect(s.transport.freshReferences).toHaveBeenCalledTimes(1);
  const refreshed=supplied!;
  act(()=>refreshed.invalidate());expect(refreshed.current()).toBe(false);
  expect(screen.queryByText(fixture.initial_read.initial_result.envelope.summary)).toBeNull();
  act(()=>captured.refresh());expect(s.transport.readFreshReference).toHaveBeenCalledTimes(2);
  view.unmount();expect(refreshed.current()).toBe(false);
});

it('keeps real archived turns visible beside an optional attended component that returns no controls',async()=>{
  const s=make();s.state.window=fixture.archived_read;
  function ReadOnlyContinuation(){return null;}
  render(<ProjectConversations workRef={work} owner={s.owner}
    renderFreshContinuation={()=> <ReadOnlyContinuation/>}/>);
  fireEvent.click(screen.getByRole('button',{name:'Read project conversations'}));
  fireEvent.click(await screen.findByRole('button',{name:'Open'}));
  await screen.findByText(fixture.archived_read.turns[0]!.result.envelope.summary);
  expect(screen.getByText(fixture.turn_request.message)).toBeTruthy();
  expect(s.transport.readFreshReference).toHaveBeenCalledTimes(1);
});

it('handles Escape at the fresh and archived reader focus handoff without reacquiring the list',async()=>{
  const s=make(),view=render(<ProjectConversations workRef={work} owner={s.owner}/>);
  const gestures:{unrelatedPrevented:boolean;readerRetained:boolean;escapePrevented:boolean}[]=[];
  let escapeOnFocus=true;
  const onFocus=(event:FocusEvent)=>{
    if(!escapeOnFocus||event.target!==screen.queryByRole('heading',{name:'Conversation'})||
       !screen.queryByRole('button',{name:'Back to conversations'}))return;
    const unrelated=new KeyboardEvent('keydown',{key:'x',bubbles:true,cancelable:true});
    window.dispatchEvent(unrelated);
    const readerRetained=!!screen.queryByRole('button',{name:'Back to conversations'});
    const escape=new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true});
    window.dispatchEvent(escape);
    gestures.push({unrelatedPrevented:unrelated.defaultPrevented,readerRetained,escapePrevented:escape.defaultPrevented});
  };
  document.addEventListener('focusin',onFocus);
  try{
    fireEvent.click(screen.getByRole('button',{name:'Read project conversations'}));
    await screen.findByRole('button',{name:'Open'});
    fireEvent.change(screen.getByRole('textbox',{name:'Find in these conversations'}),{target:{value:'新对话'}});
    for(const [index,value] of [fixture.initial_read,fixture.archived_read].entries()){
      s.state.window=value;
      await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Open'}));});
      expect(gestures).toHaveLength(index+1);
      expect(gestures[index]).toEqual({unrelatedPrevented:false,readerRetained:true,escapePrevented:true});
      expect(screen.queryByRole('button',{name:'Back to conversations'})).toBeNull();
      expect(document.activeElement).toBe(screen.getByRole('button',{name:'Open'}));
      expect((screen.getByRole('textbox',{name:'Find in these conversations'}) as HTMLInputElement).value).toBe('新对话');
      expect(s.transport.freshReferences).toHaveBeenCalledTimes(1);expect(s.transport.readFreshReference).toHaveBeenCalledTimes(index+1);
      const afterReturn=new KeyboardEvent('keydown',{key:'Escape',cancelable:true});
      window.dispatchEvent(afterReturn);expect(afterReturn.defaultPrevented).toBe(false);
    }
    escapeOnFocus=false;
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Open'}));});
    expect(screen.getByRole('button',{name:'Back to conversations'})).toBeTruthy();
    view.unmount();
    const afterUnmount=new KeyboardEvent('keydown',{key:'Escape',cancelable:true});
    window.dispatchEvent(afterUnmount);expect(afterUnmount.defaultPrevented).toBe(false);
    expect(s.transport.freshReferences).toHaveBeenCalledTimes(1);expect(s.transport.readFreshReference).toHaveBeenCalledTimes(3);
    expect(s.transport.read).not.toHaveBeenCalled();
  }finally{
    document.removeEventListener('focusin',onFocus);
  }
});
