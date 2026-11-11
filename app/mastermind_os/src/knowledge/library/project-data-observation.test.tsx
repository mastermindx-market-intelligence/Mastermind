// @vitest-environment jsdom
/** Actual Resources canonical DATA/read DTOs; explicit synthetic CODE frame
 * and native auth carrier. S7 owns nominal sealed context/HTTP issuance. */
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within,waitFor} from '@testing-library/react';
import {bindMissionHost,createNativeClient} from '../../host';
import {ProjectKnowledgeLibrary} from './ProjectKnowledgeLibrary';
import {validate_catalogue,validate_memory,validate_source,type KnowledgeLibrarySourceOwner} from './knowledge-library-contract';
import {validateKnowledgeReadMetadata,validateProjectDataObservation} from './project-data-observation';
import {searchProjectFiles} from '../../discovery/project-file-search';
import {readProjectFileMatchSource} from '../../discovery/project-file-open';
import {emptyDrafts,readDraft,readDraftRevision,readDraftInsertion,appendDraftSource,undoDraftSource,type DraftSource} from '../../conversations/drafts';
import fixture from '../../fixtures/knowledge-data-observation-owner.json';
afterEach(cleanup);
const reader='07e317ef5b6e0107fcfca9228f179c7d269bb234',work='WS:DEMO';
type Case=typeof fixture|typeof fixture.memory_edit;
function frame(value:unknown,case_:Case,observation=true){
 const code={schema:'mastermind.project_knowledge_code_context.v1',work_ref:work,
  executable_macro_commit:case_.prepared_request.source_commit,reader_source_commit:reader};
 return {...value as object,code_context:code,...(observation?{data_observation:case_.data_observation}:{})};
}
function clone<T>(value:T):T{return JSON.parse(JSON.stringify(value));}
async function realHost(case_:Case=fixture){
 const selected={catalogue:frame(case_.catalogue,case_),source:frame(case_.source,case_),memory:frame(case_.memory,case_)};
 const invoke=vi.fn(async(command:string)=>{
  if(command==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:false};
  if(command==='executive_auth_status')return {generation:0,available:false};
  if(command==='read_project_knowledge_catalogue')return selected.catalogue;
  if(command==='read_project_knowledge_source')return selected.source;
  if(command==='read_project_knowledge_memory')return selected.memory;
  throw new Error('Unexpected fixed native read');
 });
 const client=await createNativeClient(invoke as never,async()=>()=>{});
 return {host:bindMissionHost(client),invoke,selected};
}
it.each([false,true])('preserves actual separate C/N clocks and exact Event facts in strict DTOs %s',memory=>{
 const f=memory?fixture.memory_edit:fixture;
 const catalogue=validate_catalogue(frame(f.catalogue,f),work);
 const source=validate_source(frame(f.source,f),work,f.source.selection.source_ref);
 const pref=validate_memory(frame(f.memory,f),work);
 for(const result of [catalogue,source,pref]){
  expect(result.codeContext!.executable_macro_commit).toBe(f.prepared_request.source_commit);
  expect(result.dataObservation!.canonical_data_commit).toBe(f.catalogue.source.commit);
  expect(result.dataObservation!.executable_macro_commit).not.toBe(result.dataObservation!.canonical_data_commit);
  expect(result.dataObservation!.publication_time).toBeNull();
  expect(result.dataObservation!.source_operation).toEqual(f.data_observation.source_operation);
 }
 expect(Object.isFrozen(catalogue.dataObservation!.source_operation!.sources[0])).toBe(true);
});
it.each(['missing-code','wrong-code','wrong-data','foreign-work','fake-time','extra','getter','symbol','hidden','clock','invalid-day'])('fails closed on unqualified or malformed optional provenance %s',kind=>{
 const value=clone(frame(fixture.catalogue,fixture)) as Record<string,any>;
 let hooks=0;
 if(kind==='missing-code')delete value.code_context;
 if(kind==='wrong-code')value.code_context.executable_macro_commit='f'.repeat(40);
 if(kind==='wrong-data')value.data_observation.canonical_data_commit='f'.repeat(40);
 if(kind==='foreign-work')value.data_observation.source_operation.selection.work_ref='WS:OTHER';
 if(kind==='fake-time')value.data_observation.publication_time='2026-11-04T00:00:00Z';
 if(kind==='extra')value.code_context.can_write=true;
 if(kind==='getter')Object.defineProperty(value,'data_observation',{enumerable:true,get(){hooks++;return fixture.data_observation;}});
 if(kind==='symbol')value.data_observation[Symbol('receipt')]=true;
 if(kind==='hidden')Object.defineProperty(value.code_context,'can_write',{value:true,enumerable:false});
 if(kind==='clock')value.data_observation.canonical_observed_at_ms=0;
 if(kind==='invalid-day')value.data_observation.canonical_commit_at='2026-02-30T00:00:00+00:00';
 expect(()=>validate_catalogue(value,work)).toThrow();expect(hooks).toBe(0);
});
it('keeps legacy parsing independent of newly issued CODE/DATA capability',()=>{
 const legacy=validate_catalogue(fixture.initial_catalogue,work);
 expect(legacy.codeContext).toBeUndefined();expect(legacy.dataObservation).toBeUndefined();
 const raw:Record<string,unknown>=clone(fixture.data_observation);raw.source_operation=null;raw.publication_recorded_at_ms=null;
 expect(()=>validateProjectDataObservation(raw)).toThrow();
});
it('first actual N catalogue establishes independent C on the live Library owner, then Open/Back/reopen keeps exact DATA bytes',async()=>{
 const f=await realHost();let current:KnowledgeLibrarySourceOwner|null=null;
 const view=render(<ProjectKnowledgeLibrary host={f.host} workRef={work} authGeneration={0} hostGeneration={0}
  onCurrentSourceOwner={owner=>{current=owner;}} renderSourceCompanion={source=><pre data-testid="exact">{source.contentUtf8}</pre>}/>);
 await screen.findByRole('heading',{level:1,name:fixture.catalogue.project.title});
 expect(current!.codeContext!()!.executable_macro_commit).toBe(fixture.initial_catalogue.source.commit);
 const captured=current!;
 const snapshot={workRef:work,sourceCommit:fixture.catalogue.source.commit,baseRevision:fixture.catalogue.source.workstream_sha256};
 expect(captured.current(snapshot)).toEqual(snapshot);
 const rows=screen.getAllByText('notes.md').map(node=>node.closest('.knowledge-library-row') as HTMLElement);
 const open=rows.flatMap(row=>within(row).queryAllByRole('button',{name:'Open'}))[0]!;
 expect(open).toBeTruthy();
 for(let i=0;i<2;i++){
  fireEvent.click(open);await waitFor(()=>expect(screen.getByTestId('exact').textContent).toBe(fixture.source.document.content_utf8));
  const raw=view.container.querySelector('details');expect(raw?.hasAttribute('open')).toBe(false);
  expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
  fireEvent.click(screen.getByRole('button',{name:'Back'}));
 }
 view.unmount();expect(captured.codeContext!()).toBeNull();
});
it('reads actual Memory DATA N using its own independent C and literal authored preference',async()=>{
 const f=await realHost(fixture.memory_edit);
 render(<ProjectKnowledgeLibrary host={f.host} workRef={work} authGeneration={0} hostGeneration={0}/>);
 await screen.findByRole('heading',{level:1,name:fixture.memory_edit.catalogue.project.title});
 fireEvent.click(screen.getByRole('tab',{name:'Memory'}));
 expect(await screen.findByText(fixture.memory_edit.memory.memory!.value,{normalizer:value=>value})).toBeTruthy();
});
it('bounded Search/Open binds same CODE frame and DATA N, rejecting a reader-S change without exposing its source',async()=>{
 const f=await realHost(),signal=new AbortController().signal;
 const searched=await searchProjectFiles({workRef:work,query:'authored',signal},f.host.projectFilesSearch!);
 expect(searched.state).toBe('AVAILABLE');expect(searched.items).toHaveLength(1);
 const opened=await readProjectFileMatchSource({workRef:work,match:searched.items[0]!,signal},f.host.projectFilesSearch!);
 expect(opened.state).toBe('AVAILABLE');expect(opened.document!.document!.contentUtf8).toBe(fixture.source.document.content_utf8);
 f.selected.source=frame(fixture.source,fixture);(f.selected.source.code_context as {reader_source_commit:string}).reader_source_commit='f'.repeat(40);
 const changed=await readProjectFileMatchSource({workRef:work,match:searched.items[0]!,signal},f.host.projectFilesSearch!);
 expect(changed.state).toBe('UNAVAILABLE');expect(changed.reason).toBe('SOURCE_CHANGED');expect(changed.document).toBeNull();
});


it('qualified first-N source metadata still reaches the genuine same-work unsent draft proof',async()=>{
 const f=await realHost();
 const context={authGeneration:0,selection:{workRef:work,rootJobId:'JOB-999'},sessionRef:'original-destination',bindingGeneration:'current',revisions:{mission:null,programs:null,result:null,conversation:null}};
 let drafts=emptyDrafts(0);
 const append=(source:DraftSource,revision:number)=>{drafts=appendDraftSource(drafts,context,revision,source);return readDraftRevision(drafts,context)===revision+1;};
 const undo=(identity:string,revision:number)=>{drafts=undoDraftSource(drafts,context,revision,identity);return readDraftRevision(drafts,context)===revision+1;};
 const port={text:'',revision:0,insertion:readDraftInsertion(drafts,context),append,undo,
  readWitness:()=>({workRef:work,binding:'genuine-original-destination',revision:readDraftRevision(drafts,context)})};
 render(<ProjectKnowledgeLibrary host={f.host} workRef={work} authGeneration={0} hostGeneration={0} draftPort={port}/>);
 await screen.findByRole('heading',{level:1,name:fixture.catalogue.project.title});
 const rows=screen.getAllByText('notes.md').map(node=>node.closest('.knowledge-library-row') as HTMLElement);
 fireEvent.click(rows.flatMap(row=>within(row).queryAllByRole('button',{name:'Open'}))[0]!);
 fireEvent.click(await screen.findByRole('button',{name:'Add excerpt to draft'}));
 expect(readDraft(drafts,context)).toContain(fixture.source.document.content_utf8);
 expect(readDraftInsertion(drafts,context)!.source.label).toContain(fixture.catalogue.source.commit);
 expect(readDraftInsertion(drafts,context)!.source.label).not.toContain('JOB-999');
});
const fixtureObservation=fixture.data_observation;
function continuityInner(overrides:Record<string,unknown>={}):Record<string,unknown>{
 return {schema:'mastermind.project_data_continuity.v1',kind:'UNCHANGED_SELECTED_PROJECT_DATA',work_ref:work,
  principal_scope:fixtureObservation.source_operation.principal_scope,executable_macro_commit:fixtureObservation.executable_macro_commit,
  canonical_data_commit:fixtureObservation.canonical_data_commit,reader_closure_sha256:fixtureObservation.reader_closure_sha256,
  selected_data_closure_sha256:'e'.repeat(64),ancestry:'CODE_ANCESTOR_OF_DATA',...overrides};
}
function continuityObservation(baseOverrides:Record<string,unknown>={},innerOverrides:Record<string,unknown>={}):Record<string,unknown>{
 const raw=clone(fixtureObservation) as Record<string,unknown>;
 raw.source_operation=null;raw.publication_recorded_at_ms=null;raw.publication_time=null;
 raw.data_continuity=continuityInner(innerOverrides);
 return {...raw,...baseOverrides};
}
it('accepts a closed data_continuity frame joined to the same work, principal, reader closure and both commits',()=>{
 const observation=validateProjectDataObservation(continuityObservation(),{workRef:work});
 expect(observation.source_operation).toBeNull();expect(observation.publication_recorded_at_ms).toBeNull();
 const continuity=observation.data_continuity!;
 expect(continuity.work_ref).toBe(work);
 expect(continuity.principal_scope).toBe(fixtureObservation.source_operation.principal_scope);
 expect(continuity.executable_macro_commit).toBe(observation.executable_macro_commit);
 expect(continuity.canonical_data_commit).toBe(observation.canonical_data_commit);
 expect(continuity.executable_macro_commit).not.toBe(continuity.canonical_data_commit);
 expect(continuity.reader_closure_sha256).toBe(observation.reader_closure_sha256);
 expect(Object.keys(continuity)).toEqual(['schema','kind','work_ref','principal_scope','executable_macro_commit','canonical_data_commit','reader_closure_sha256','selected_data_closure_sha256','ancestry']);
 expect(Object.isFrozen(continuity)).toBe(true);expect(Object.isFrozen(observation)).toBe(true);
});
it('keeps the legacy identical-C/N shape closed with data_continuity absent',()=>{
 const raw=clone(fixtureObservation) as Record<string,unknown>;
 raw.source_operation=null;raw.publication_recorded_at_ms=null;raw.publication_time=null;
 raw.executable_macro_commit=raw.canonical_data_commit;
 const observation=validateProjectDataObservation(raw,{workRef:work});
 expect('data_continuity' in observation).toBe(false);expect(observation.data_continuity).toBeUndefined();
});
const continuityNegatives:[string,Record<string,unknown>,Record<string,unknown>][]=[
 ['wrong-schema',{schema:'mastermind.project_data_continuity.v2'},{}],
 ['wrong-kind',{kind:'REBUILT_SELECTED_PROJECT_DATA'},{}],
 ['wrong-ancestry',{ancestry:'DATA_ANCESTOR_OF_CODE'},{}],
 ['bad-work-format',{work_ref:'WS:demo'},{}],
 ['short-work',{work_ref:'WS:A'},{}],
 ['long-work',{work_ref:'WS:'+'A'.repeat(65)},{}],
 ['foreign-work',{work_ref:'WS:OTHER'},{}],
 ['inner-code',{executable_macro_commit:fixtureObservation.canonical_data_commit},{}],
 ['inner-data',{canonical_data_commit:fixtureObservation.executable_macro_commit},{}],
 ['reader-closure',{reader_closure_sha256:'f'.repeat(64)},{}],
 ['principal-scope',{principal_scope:'0'.repeat(63)},{}],
 ['selected-closure',{selected_data_closure_sha256:'E'.repeat(64)},{}],
 ['inner-extra',{unspecified:'extra'},{}],
 ['operation-mixed',{},{source_operation:clone(fixtureObservation.source_operation)}],
 ['clock-mixed',{},{publication_recorded_at_ms:fixtureObservation.publication_recorded_at_ms}],
 ['code-equals-data',{executable_macro_commit:fixtureObservation.canonical_data_commit,canonical_data_commit:fixtureObservation.canonical_data_commit},{executable_macro_commit:fixtureObservation.canonical_data_commit}],
];
it.each(continuityNegatives)('rejects unjoined or malformed data_continuity %s',(_kind,inner,base)=>{
 expect(()=>validateProjectDataObservation(continuityObservation(base,inner),{workRef:work})).toThrow();
});
it('rejects accessor, symbol-keyed, hidden and unrelated extra outer keys around data_continuity',()=>{
 const accessor=continuityObservation();let hooks=0;
 Object.defineProperty(accessor,'data_continuity',{enumerable:true,get(){hooks++;return continuityInner();}});
 expect(()=>validateProjectDataObservation(accessor,{workRef:work})).toThrow();
 const symbolKeyed=continuityObservation();
 Object.defineProperty(symbolKeyed.data_continuity as object,Symbol('receipt'),{value:true,enumerable:true,configurable:true,writable:true});
 expect(()=>validateProjectDataObservation(symbolKeyed,{workRef:work})).toThrow();
 const hidden=continuityObservation();
 Object.defineProperty(hidden,'data_continuity',{value:continuityInner(),enumerable:false});
 expect(()=>validateProjectDataObservation(hidden,{workRef:work})).toThrow();
 const extra=continuityObservation();extra.extra='unrelated';
 expect(()=>validateProjectDataObservation(extra,{workRef:work})).toThrow();
 expect(hooks).toBe(0);
});
it('validateKnowledgeReadMetadata joins the continuity work_ref and both commits to the actual read body',()=>{
 const code=fixtureObservation.executable_macro_commit,data=fixtureObservation.canonical_data_commit;
 const body:Record<string,unknown>={data_observation:continuityObservation(),
  code_context:{schema:'mastermind.project_knowledge_code_context.v1',work_ref:work,executable_macro_commit:code,reader_source_commit:reader},source:{commit:data}};
 const metadata=validateKnowledgeReadMetadata(body,work);
 expect(metadata.dataObservation!.data_continuity!.work_ref).toBe(work);
 expect(metadata.dataObservation!.data_continuity!.executable_macro_commit).toBe(code);
 expect(metadata.dataObservation!.data_continuity!.canonical_data_commit).toBe(data);
 expect(Object.isFrozen(metadata.dataObservation!.data_continuity)).toBe(true);
 expect(()=>validateKnowledgeReadMetadata({...body,data_observation:continuityObservation({},{work_ref:'WS:OTHER'})},work)).toThrow();
 expect(()=>validateKnowledgeReadMetadata({...body,code_context:{schema:'mastermind.project_knowledge_code_context.v1',work_ref:work,executable_macro_commit:data,reader_source_commit:reader}},work)).toThrow();
 expect(()=>validateKnowledgeReadMetadata({...body,source:{commit:code}},work)).toThrow();
});
