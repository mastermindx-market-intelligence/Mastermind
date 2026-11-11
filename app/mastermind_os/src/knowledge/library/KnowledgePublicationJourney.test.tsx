// @vitest-environment jsdom
/** Exact actual canonical compiler/private/Events/temp-Git publication DTOs.
 * The native invoke and normal upstream landing are explicit synthetic fixtures;
 * these are joined source tests, never installed grant/authenticated proof. */
import {useState} from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within,waitFor} from '@testing-library/react';
import {bindMissionHost,createNativeClient,type MissionHost} from '../../host';
import {ProjectKnowledgeLibrary} from './ProjectKnowledgeLibrary';
import {ProjectSearchWorkspace} from '../../discovery/ProjectSearchWorkspace';
import {searchProjectFiles,type ProjectFileMatch} from '../../discovery/project-file-search';
import {readProjectFileMatchSource} from '../../discovery/project-file-open';
import {decodeProjectSourceOperationStatus} from './project-source-operation';
import fixture from '../../fixtures/knowledge-write-owner.json';
afterEach(cleanup);
const file=fixture.journeys[0]!,preference=fixture.journeys[1]!,work=fixture.work_ref;
async function realHost(){
 const selected={journey:file,after:false};
 const invoke=vi.fn(async(command:string,args?:Record<string,unknown>)=>{
  if(command==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:false};
  if(command==='executive_auth_status')return {generation:0,available:false};
  if(command==='read_project_knowledge_catalogue')return selected.after?selected.journey.after_catalogue:selected.journey.before_catalogue;
  if(command==='read_project_knowledge_memory')return selected.journey.after_memory;
  if(command==='read_project_knowledge_source'){
   const ref=(args!.selection as {source_ref:string}).source_ref;
   return selected.journey.sources[ref as keyof typeof selected.journey.sources];
  }
  throw new Error('Unexpected fixed native read');
 });
 const raw=await createNativeClient(invoke as never,async()=>()=>{});
 return {host:bindMissionHost(raw),invoke,selected};
}
function qualifyPublished(journey:typeof file){
 const request=journey.request;
 const status=decodeProjectSourceOperationStatus(journey.source_status,{action:journey.preview.selection.action as 'add_project_file'|'set_project_communication_preference',
  workRef:work,requestId:request.request_id,requestSha256:journey.preview.request_sha256,
  principalScope:journey.preview.owner_context.principal_scope});
 expect(status.disposition).toBe('accepted');expect(status.receipt?.kind).toBe('SOURCE_OBSERVED');
 return status;
}
it('shows the actual canonical publication in the same fixed Library, then opens, returns and reopens exact bytes',async()=>{
 const f=await realHost();
 const props={host:f.host,workRef:work,authGeneration:0,hostGeneration:0,
  renderSourceCompanion:(source:{contentUtf8:string})=><pre data-testid="exact">{source.contentUtf8}</pre>};
 const view=render(<ProjectKnowledgeLibrary {...props} refreshKey={0}/>);
 await screen.findByRole('heading',{level:1,name:file.before_catalogue.project.title});
 expect(screen.queryByText('Notes.md')).toBeNull();
 qualifyPublished(file);f.selected.after=true;view.rerender(<ProjectKnowledgeLibrary {...props} refreshKey={1}/>);
 const row=(await screen.findByText('Notes.md')).closest('.knowledge-library-row')!;
 const open=within(row as HTMLElement).getByRole('button',{name:'Open'});
 for(let count=1;count<=2;count++){
  fireEvent.click(open);await waitFor(()=>expect(screen.getByTestId('exact').textContent).toBe(file.request.file!.content_utf8));
  expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
  fireEvent.click(screen.getByRole('button',{name:'Back'}));
  expect(document.activeElement).toBe(open);
  expect(f.invoke.mock.calls.filter(([name])=>name==='read_project_knowledge_source')).toHaveLength(count);
 }
});
it('reads the literal canonical preference after its same-original source receipt without promoting the proposal',async()=>{
 const f=await realHost();f.selected.journey=preference;f.selected.after=true;
 qualifyPublished(preference);
 render(<ProjectKnowledgeLibrary host={f.host} workRef={work} authGeneration={0} hostGeneration={0}/>);
 await screen.findByRole('heading',{level:1,name:preference.after_catalogue.project.title});
 fireEvent.click(screen.getByRole('tab',{name:'Memory'}));
 expect(await screen.findByText(preference.request.value!,{normalizer:value=>value})).toBeTruthy();
 expect(preference.proposal_status.disposition).toBe('unknown');
 expect(preference.after_memory.memory!.origin.kind).toBe('USER_EDIT');
});
function SearchReader({host}:{host:MissionHost}){
 const [match,setMatch]=useState<ProjectFileMatch|null>(null);
 return <><div hidden={match!==null} aria-hidden={match!==null}>
  <ProjectSearchWorkspace workRef={work} authGeneration={0} hostGeneration={0} projectFiles={host.projectFilesSearch} onOpenFile={setMatch}/>
 </div>{match?<ProjectKnowledgeLibrary host={host} workRef={work} authGeneration={0} hostGeneration={0}
  requestedFile={{match,workRef:work,authGeneration:0,hostGeneration:0}} onReturnToSearch={()=>setMatch(null)}
  renderSourceCompanion={source=><pre data-testid="exact">{source.contentUtf8}</pre>}/>:null}</>;
}
it('Search Open re-reads the published owner source, Back preserves the query, and reopen re-reads',async()=>{
 const f=await realHost();f.selected.after=true;qualifyPublished(file);
 render(<SearchReader host={f.host}/>);
 fireEvent.change(screen.getByRole('textbox',{name:'Search this project'}),{target:{value:'literal'}});
 fireEvent.click(screen.getByRole('button',{name:'Search'}));
 for(let count=0;count<2;count++){
  const open=await screen.findByRole('button',{name:'Open'});fireEvent.click(open);
  await waitFor(()=>expect(screen.getByTestId('exact').textContent).toBe(file.request.file!.content_utf8));
  fireEvent.click(screen.getByRole('button',{name:'Back'}));
  expect((screen.getByRole('textbox',{name:'Search this project'}) as HTMLInputElement).value).toBe('literal');
 }
 expect(f.invoke.mock.calls.filter(([name])=>name==='read_project_knowledge_source').length).toBe(3);
});
it('a later data generation refuses the old source match before body read and a fresh explicit query finds the new opaque identity',async()=>{
 const f=await realHost();f.selected.after=true;
 const signal=new AbortController().signal;
 const old=await searchProjectFiles({workRef:work,query:'literal',signal},f.host.projectFilesSearch!);
 expect(old.items).toHaveLength(1);
 f.selected.journey=preference;qualifyPublished(preference);f.invoke.mockClear();
 const stale=await readProjectFileMatchSource({workRef:work,match:old.items[0]!,signal},f.host.projectFilesSearch!);
 expect(stale.state).toBe('UNAVAILABLE');expect(f.invoke.mock.calls.filter(([name])=>name==='read_project_knowledge_source')).toHaveLength(0);
 const fresh=await searchProjectFiles({workRef:work,query:'literal',signal},f.host.projectFilesSearch!);
 expect(fresh.items[0]!.sourceRef).not.toBe(old.items[0]!.sourceRef);
 const opened=await readProjectFileMatchSource({workRef:work,match:fresh.items[0]!,signal},f.host.projectFilesSearch!);
 expect(opened.state).toBe('AVAILABLE');expect(opened.document!.document!.contentUtf8).toBe(file.request.file!.content_utf8);
});
