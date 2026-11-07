// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {createSavedConversationNavigation,SavedConversationReader} from './SavedConversationReader';
import {searchSavedConversations,type SavedConversationSearchOwner} from './saved-conversations';
import {emptyDrafts,readDraft,readDraftRevision,readDraftInsertion,appendDraftSource,undoDraftSource,type DraftSource} from '../conversations/drafts';
import type {ProjectSourceDraftPort} from '../knowledge/library/project-source-draft';
afterEach(cleanup);
const work='WS:SAVED',hex=(c:string)=>c.repeat(64);
const text='# Actual reply\r\n\r\n中文 source 🌟\r\nexact second line';
function fixture(){
 let generation='owner-1';
 const ref={read_ref:'session-reply-'+hex('a'),operation_key:'session-continue-'+hex('b'),request_ref:'original-request',request_event_id:41,request_revision:hex('c'),requested_at:'2026-11-03T10:20:30.000Z',work_ref:work,root_job_id:'JOB-123',target_ref:'fabric_attempt:'+hex('d'),reference_only:true as const};
 const envelope={schema:'mastermind.os.executive.session_result.v1',operation:'references',ok:true,effect:'NONE',operation_key:null,error:null,data:{schema:'mastermind.session_reply_references.v1',status:'COMPLETE',references:[ref],next_cursor:null,high_water:100}};
 const answer={receipt:{operationKey:ref.operation_key,targetKey:ref.target_ref,kind:'message',disposition:'accepted'},answer:{readRef:ref.read_ref,text,nextStep:'PRIVATE nextStep',parentConsumed:false}};
 const owner={context:()=>({principalScope:'principal-fixture',generation}),authGeneration:()=>7,readReferences:vi.fn(async()=>envelope),readAnswer:vi.fn(async()=>answer)} as unknown as SavedConversationSearchOwner;
 return {owner,ref,envelope,answer,changeContext:()=>{generation='owner-2';}};
}
async function navigation(f:ReturnType<typeof fixture>){
 const found=await searchSavedConversations({workRef:work,query:'中文',signal:new AbortController().signal},f.owner);
 expect(found.state).toBe('AVAILABLE');
 const selection=createSavedConversationNavigation({workRef:work,authGeneration:3,hostGeneration:1,match:found.items[0],pageCursor:'cGFnZS0y',expectedHighWater:100},f.owner)!;
 vi.mocked(f.owner.readReferences).mockClear();vi.mocked(f.owner.readAnswer).mockClear();
 return selection;
}
describe('saved Search source reader integration',()=>{
 it('re-reads exact producing page and answer, shows full exact source and one heading, and returns once',async()=>{
  const f=fixture(),selection=await navigation(f),onBack=vi.fn();
  const view=render(<SavedConversationReader selection={selection} workRef={work} authGeneration={3} hostGeneration={1} owner={f.owner} onBack={onBack} renderSourceCompanion={source=><pre data-testid="exact">{source.text}</pre>}/>);
  await screen.findByTestId('exact');expect(screen.getByTestId('exact').textContent).toBe(text);
  expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
  expect(screen.getByRole('heading',{level:3,name:'Actual reply'})).toBeTruthy();
  expect(screen.queryByText('PRIVATE nextStep')).toBeNull();
  expect(f.owner.readReferences).toHaveBeenCalledTimes(1);
  expect(vi.mocked(f.owner.readReferences).mock.calls[0][0]).toMatchObject({workRef:work,pageSize:4,cursor:'cGFnZS0y'});
  expect(f.owner.readAnswer).toHaveBeenCalledWith({operationKey:f.ref.operation_key,targetKey:f.ref.target_ref,kind:'message'},expect.any(AbortSignal));
  const details=view.container.querySelector('details')!;expect(details.hasAttribute('open')).toBe(false);
  const button=screen.getByRole('button',{name:'Back to search'});button.focus();fireEvent.click(button);fireEvent.keyDown(window,{key:'Escape'});
  expect(onBack).toHaveBeenCalledTimes(1);expect(screen.queryByTestId('exact')).toBeNull();
 });
 it.each([{authGeneration:4,hostGeneration:1,workRef:work},{authGeneration:3,hostGeneration:'1',workRef:work},{authGeneration:3,hostGeneration:1,workRef:'WS:OTHER'}])('rejects old original navigation before any owner body read %j',async changed=>{
  const f=fixture(),selection=await navigation(f);
  render(<SavedConversationReader selection={selection} {...changed} owner={f.owner}/>);
  await screen.findByText('SOURCE_CONTEXT_CHANGED');expect(f.owner.readReferences).not.toHaveBeenCalled();expect(f.owner.readAnswer).not.toHaveBeenCalled();
 });
 it('retains locale/theme without reading again, clears private source before paint when owner context changes',async()=>{
  const f=fixture(),selection=await navigation(f);
  const props={selection,workRef:work,authGeneration:3,hostGeneration:1,owner:f.owner,renderSourceCompanion:(source:{text:string|null})=><pre data-testid="exact">{source.text}</pre>};
  const view=render(<SavedConversationReader {...props}/>);await screen.findByTestId('exact');
  view.rerender(<SavedConversationReader {...props} locale="zh-CN" theme="light"/>);
  expect(screen.getByRole('heading',{level:1,name:'已保存的回复'})).toBeTruthy();expect(f.owner.readAnswer).toHaveBeenCalledTimes(1);
  f.changeContext();view.rerender(<SavedConversationReader {...props}/>);
  expect(screen.queryByTestId('exact')).toBeNull();await screen.findByText('SOURCE_CONTEXT_CHANGED');expect(f.owner.readAnswer).toHaveBeenCalledTimes(1);
 });
 it('aborts late source read on Back without displaying it or repeating navigation',async()=>{
  const f=fixture(),selection=await navigation(f);let resolve!:(value:unknown)=>void;
  const pending=new Promise(resolvePromise=>{resolve=resolvePromise;});
  vi.mocked(f.owner.readAnswer).mockImplementation(async()=>pending as never);
  // New method identity requires a fresh explicit owner witness.
  const original=createSavedConversationNavigation({...selection},f.owner)!;
  const back=vi.fn();render(<SavedConversationReader selection={original} workRef={work} authGeneration={3} hostGeneration={1} owner={f.owner} onBack={back} renderSourceCompanion={s=><pre data-testid="exact">{s.text}</pre>}/>);
  await waitFor(()=>expect(f.owner.readAnswer).toHaveBeenCalledTimes(1));
  const signal=vi.mocked(f.owner.readAnswer).mock.calls[0][1];fireEvent.keyDown(window,{key:'Escape'});expect(signal.aborted).toBe(true);
  resolve(f.answer);await Promise.resolve();expect(screen.queryByTestId('exact')).toBeNull();expect(back).toHaveBeenCalledTimes(1);
 });
 it('rejects reference watermark movement without a detail read and has truthful missing Back',async()=>{
  const f=fixture(),selection=await navigation(f);f.envelope.data.high_water=101;
  render(<SavedConversationReader selection={selection} workRef={work} authGeneration={3} hostGeneration={1} owner={f.owner}/>);
  await screen.findByText('SOURCE_CHANGED');expect(f.owner.readAnswer).not.toHaveBeenCalled();
  expect((screen.getByRole('button',{name:'Back to search'}) as HTMLButtonElement).disabled).toBe(true);
 });
 it('rejects a different answer readRef without displaying even its text',async()=>{
  const f=fixture(),selection=await navigation(f);f.answer.answer.readRef='session-reply-'+hex('f');
  render(<SavedConversationReader selection={selection} workRef={work} authGeneration={3} hostGeneration={1} owner={f.owner} renderSourceCompanion={s=><pre data-testid="exact">{s.text}</pre>}/>);
  await screen.findByText('INVALID_SOURCE');expect(screen.queryByTestId('exact')).toBeNull();
 });
});


it('joins actual saved reply re-read to the genuine same-work destination while preserving a different source root',async()=>{
 const f=fixture(),selection=await navigation(f);
 const context={authGeneration:3,selection:{workRef:work,rootJobId:'JOB-DESTINATION'},sessionRef:'genuine-destination',
  bindingGeneration:'session-current',revisions:{mission:null,programs:null,result:null,conversation:null}};
 let drafts=emptyDrafts(3);
 const append=(source:DraftSource,revision:number)=>{drafts=appendDraftSource(drafts,context,revision,source);return readDraftRevision(drafts,context)===revision+1;};
 const undo=(identity:string,revision:number)=>{drafts=undoDraftSource(drafts,context,revision,identity);return readDraftRevision(drafts,context)===revision+1;};
 const readWitness=()=>({workRef:work,binding:'genuine-current-destination',revision:readDraftRevision(drafts,context)});
 const port=():ProjectSourceDraftPort=>({text:readDraft(drafts,context),revision:readDraftRevision(drafts,context),insertion:readDraftInsertion(drafts,context),append,undo,readWitness});
 const props={selection,workRef:work,authGeneration:3,hostGeneration:1,owner:f.owner};
 const view=render(<SavedConversationReader {...props} draftPort={port()}/>);
 fireEvent.click(await screen.findByRole('button',{name:'Add excerpt to draft'}));
 expect(readDraft(drafts,context)).toContain(text);
 expect(readDraftInsertion(drafts,context)!.source.label).toContain('JOB-123');
 expect(readDraftInsertion(drafts,context)!.source.label).not.toContain('JOB-DESTINATION');
 view.rerender(<SavedConversationReader {...props} draftPort={port()}/>);
 fireEvent.click(await screen.findByRole('button',{name:'Remove added excerpt'}));
 expect(readDraft(drafts,context)).toBe('');expect(f.owner.readAnswer).toHaveBeenCalledTimes(1);
});
