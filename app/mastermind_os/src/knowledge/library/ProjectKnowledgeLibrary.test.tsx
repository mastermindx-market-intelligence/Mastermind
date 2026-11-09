// @vitest-environment jsdom
/** Actual Python temp-Git/parser/recipe DTOs → fixed native host → Library/Search.
 * Fixture values are synthetic; this test creates no installed/authenticated effect.
 */
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {ProjectKnowledgeLibrary} from './ProjectKnowledgeLibrary';
import {validate_catalogue,validate_memory,validate_source,sha256Hex} from './knowledge-library-contract';
import fixture from '../../fixtures/project-knowledge-owner.json';
import {bindMissionHost,createNativeClient} from '../../host';
import {searchProjectFiles} from '../../discovery/project-file-search';
import {readProjectFileMatchSource} from '../../discovery/project-file-open';
afterEach(cleanup);
const signed={status:'signed_in' as const,reason:null,acquisition:true,content:false};
const uploaded=fixture.catalogue.project.files.find(row=>row.origin.kind==='PRINCIPAL_UPLOAD')!;
async function realHost(){
 const invoke=vi.fn(async(command:string,args?:Record<string,unknown>)=>{
  if(command==='auth_status')return signed;if(command==='executive_auth_status')return {generation:0,available:false};
  if(command==='read_project_knowledge_catalogue')return fixture.catalogue;
  if(command==='read_project_knowledge_memory')return fixture.memory;
  if(command==='read_project_knowledge_source'){
   const selection=args!.selection as {source_ref:string};return fixture.sources[selection.source_ref as keyof typeof fixture.sources];
  }
  throw new Error('Unexpected fixed native read');
 });
 const raw=await createNativeClient(invoke as never,async()=>()=>{});return {host:bindMissionHost(raw),invoke};
}
describe('actual canonical producer joins',()=>{
 it('decodes exact source/memory/file metadata with independent Git blob revisions',async()=>{
  expect(fixture.fixture_scope).toBe('SYNTHETIC_TEMP_GIT_WITH_ACTUAL_MACRO_PARSER_AND_RECIPES');
  const catalogue=validate_catalogue(fixture.catalogue,fixture.work_ref);expect(catalogue.availability).toBe('AVAILABLE');
  expect(validate_memory(fixture.memory,fixture.work_ref).memory!.value).toBe(fixture.memory.memory.value);
  for(const [ref,raw] of Object.entries(fixture.sources)){
   const source=validate_source(raw,fixture.work_ref,ref);expect(await sha256Hex(source.document!.contentUtf8)).toBe(source.source!.contentSha256);
   expect(source.source!.revision).not.toBe(source.source!.commit);
  }
 });
 it('opens the actual uploaded file through the fixed host and preserves exact text, one h1 and return focus',async()=>{
  const {host,invoke}=await realHost();const view=render(<ProjectKnowledgeLibrary host={host} workRef={fixture.work_ref} authGeneration={0} hostGeneration={0} renderSourceCompanion={source=><pre data-testid="exact-source">{source.contentUtf8}</pre>}/>);
  await screen.findByRole('heading',{level:1,name:fixture.catalogue.project.title});
  const row=screen.getByText('Uploaded file').closest('.knowledge-library-row')!;
  const open=within(row as HTMLElement).getByRole('button',{name:'Open'});fireEvent.click(open);
  const raw=fixture.sources[uploaded.source_ref as keyof typeof fixture.sources];
  await waitFor(()=>expect(view.container.querySelector('[data-testid=exact-source]')?.textContent).toBe(raw.document.content_utf8));
  expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
  expect(invoke.mock.calls.filter(([name])=>name==='read_project_knowledge_source')).toEqual([['read_project_knowledge_source',{selection:{work_ref:fixture.work_ref,source_ref:uploaded.source_ref,expected_revision:uploaded.revision}}]]);
  fireEvent.click(screen.getByRole('button',{name:'Back'}));expect(document.activeElement).toBe(open);
 });
 it('reads the literal project preference and actual file Search through the same fixed host',async()=>{
  const {host}=await realHost();render(<ProjectKnowledgeLibrary host={host} workRef={fixture.work_ref} authGeneration={0} hostGeneration={0} renderSourceCompanion={source=><pre data-testid="exact-source">{source.contentUtf8}</pre>}/>);
  await screen.findByRole('heading',{level:1,name:fixture.catalogue.project.title});fireEvent.click(screen.getByRole('tab',{name:'Memory'}));
  await screen.findByText(fixture.memory.memory.value);
  expect(screen.queryByRole('button',{name:'Edit'})).toBeNull(); // No distinct writer grant/port was supplied.
  const result=await searchProjectFiles({workRef:fixture.work_ref,query:'中文',signal:new AbortController().signal},host.projectFilesSearch!);
  expect(result.state).toBe('AVAILABLE');expect(result.items.some(row=>row.sourceRef===uploaded.source_ref)).toBe(true);
  expect(result.items.find(row=>row.sourceRef===uploaded.source_ref)!.sourceTextSha256).toBe(uploaded.content_sha256);
 });
 it('reopens an actual Search match through fresh catalogue membership and exact source SHA',async()=>{
  const {host,invoke}=await realHost();const signal=new AbortController().signal;
  const found=await searchProjectFiles({workRef:fixture.work_ref,query:'中文',signal},host.projectFilesSearch!);
  const match=found.items.find(row=>row.sourceRef===uploaded.source_ref)!;
  invoke.mockClear();
  const opened=await readProjectFileMatchSource({workRef:fixture.work_ref,match,signal},host.projectFilesSearch!);
  expect(opened.state).toBe('AVAILABLE');
  expect(opened.document!.document!.contentUtf8).toBe(fixture.sources[uploaded.source_ref as keyof typeof fixture.sources].document.content_utf8);
  expect(invoke.mock.calls.map(([command])=>command)).toEqual(['read_project_knowledge_catalogue','read_project_knowledge_source']);
  expect(invoke.mock.calls[1][1]).toEqual({selection:{work_ref:fixture.work_ref,source_ref:uploaded.source_ref,expected_revision:uploaded.revision}});
 });

 it('joins explicit Search Open to the Library reader and returns to the original Search route',async()=>{
  const {host,invoke}=await realHost();const signal=new AbortController().signal;
  const found=await searchProjectFiles({workRef:fixture.work_ref,query:'中文',signal},host.projectFilesSearch!);
  const match=found.items.find(row=>row.sourceRef===uploaded.source_ref)!;
  const requestedFile=Object.freeze({match,workRef:fixture.work_ref,authGeneration:0,hostGeneration:0});
  const back=vi.fn();
  const view=render(<ProjectKnowledgeLibrary host={host} workRef={fixture.work_ref} authGeneration={0} hostGeneration={0} requestedFile={requestedFile} onReturnToSearch={back} renderSourceCompanion={source=><pre data-testid="exact-source">{source.contentUtf8}</pre>}/>);
  const raw=fixture.sources[uploaded.source_ref as keyof typeof fixture.sources];
  await waitFor(()=>expect(screen.getByTestId('exact-source').textContent).toBe(raw.document.content_utf8));
  expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
  fireEvent.click(screen.getByRole('button',{name:'Back'}));expect(back).toHaveBeenCalledTimes(1);
  const readsBefore=invoke.mock.calls.filter(([command])=>command==='read_project_knowledge_source').length;
  // Keeping an old navigation snapshot cannot expose its body under a new epoch.
  view.rerender(<ProjectKnowledgeLibrary host={host} workRef={fixture.work_ref} authGeneration={1} hostGeneration={0} requestedFile={requestedFile} onReturnToSearch={back}/>);
  expect(screen.queryByTestId('exact-source')).toBeNull();
  await screen.findByText('SOURCE_CONTEXT_CHANGED');
  expect(invoke.mock.calls.filter(([command])=>command==='read_project_knowledge_source')).toHaveLength(readsBefore);
 });

});
