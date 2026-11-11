import {beforeAll,describe,expect,it,vi} from "vitest";
import {bindMissionHost,createNativeClient,type RawClient} from "./host";
import {searchProjectFiles} from "./discovery/project-file-search";
import {sha256Hex} from "./knowledge/library/knowledge-library-contract";
import {knowledgeReadSelection} from "./knowledge/library/knowledge-read-port";
const WORK="WS:ONE",REF="project-file.v1."+"a".repeat(64),REV="b".repeat(40),COMMIT="c".repeat(40);
const TEXT="\ufeff# Owner file\r\nExact needle 内容 🧭\r\n",PATH="docs/owner.md";
const signed={status:"signed_in" as const,reason:null,acquisition:true,content:false};
const out={...signed,status:"signed_out" as const,acquisition:false};
let SHA="";
beforeAll(async()=>{SHA=await sha256Hex(TEXT);});
const selected={work_ref:WORK};
const sourceSelected={...selected,source_ref:REF,expected_revision:REV};
const signal=()=>new AbortController().signal;
function catalogue(){return {schema:"mastermind.workspace_project_knowledge.v1",selection:selected,availability:"AVAILABLE",reason_codes:[],
 source:{repository:"mastermindx-market-intelligence/macro",commit:COMMIT,workstream_sha256:"d".repeat(64)},
 project:{title:"Owner project",files:[{source_ref:REF,repository:"macro",path:PATH,revision:REV,display_name:"owner.md",media_type:"text/markdown",content_sha256:SHA,state:"READABLE",origin:{kind:"DECLARED_ARTIFACT",actor_ref:null,request_sha256:null},viewer_relation:"UNKNOWN"}],records:[],memory:{state:"EMPTY",source_ref:null,revision:null},coverage:{files:{state:"COMPLETE",declared:1,listed:1,omitted:0},records:{state:"BOUNDED_SAMPLE",scanned:1,matched:0,omitted:0,invalid:0}}}};}
function source(){return {schema:"mastermind.workspace_project_source.v1",selection:{work_ref:WORK,source_ref:REF},availability:"AVAILABLE",reason_codes:[],source:{repository:"mastermindx-market-intelligence/macro",commit:COMMIT,path:PATH,revision:REV,content_sha256:SHA,committed_at:"2026-11-04T00:00:00+00:00"},document:{title:"owner.md",media_type:"text/markdown",content_utf8:TEXT,content_sha256:SHA}};}
function memory(){return {schema:"mastermind.workspace_project_preference.v1",selection:selected,availability:"EMPTY",reason_codes:[],source:null,memory:null};}
async function env(read:(command:string)=>Promise<unknown>=(command:string)=>Promise.resolve(command.endsWith("catalogue")?catalogue():command.endsWith("memory")?memory():source())){
 let notify=(_:unknown)=>{};
 const invoke=vi.fn(async(command:string,_args?:Record<string,unknown>)=>{
  if(command==="auth_status")return signed;if(command==="executive_auth_status")return {generation:0,available:false};
  if(command.startsWith("read_project_knowledge_"))return read(command);throw Error("unexpected");
 });
 const raw=await createNativeClient(invoke as never,async(_event,listener)=>{notify=p=>listener({payload:p});return ()=>{};});
 return {raw,host:bindMissionHost(raw),invoke,notify};
}
function deferred(){let resolve!:(v:unknown)=>void;return {promise:new Promise<unknown>(yes=>resolve=yes),resolve:(v:unknown)=>resolve(v)};}
describe("real fixed Knowledge host composition",()=>{
 it("routes catalogue/memory/source through only their three fixed rootless native methods",async()=>{
  const e=await env();expect(await e.host.readProjectKnowledgeCatalogue!({...selected,signal:signal()})).toEqual(catalogue());
  expect(await e.host.readProjectKnowledgeMemory!({...selected,signal:signal()})).toEqual(memory());
  expect(await e.host.readProjectKnowledgeSource!({...sourceSelected,signal:signal()})).toEqual(source());
  expect(e.invoke.mock.calls.filter(([name])=>name.startsWith("read_project_knowledge_"))).toEqual([
   ["read_project_knowledge_catalogue",{selection:selected}],["read_project_knowledge_memory",{selection:selected}],["read_project_knowledge_source",{selection:sourceSelected}]]);
 });
 it("runs the actual file composer from signed Workspace READ without any Runtime session/principal label",async()=>{
  const e=await env();expect(e.host.projectFilesSearch!.context()).toEqual({generation:expect.any(String)});
  const result=await searchProjectFiles({workRef:WORK,query:"needle",signal:signal()},e.host.projectFilesSearch!);
  expect(result.state).toBe("AVAILABLE");expect(result.items).toHaveLength(1);expect(TEXT.includes(result.items[0].excerpt)).toBe(true);
  expect(e.invoke.mock.calls.filter(([name])=>name.startsWith("read_project_knowledge_"))).toHaveLength(2);
 });
 it("old clients expose neither invented reads nor a search owner",async()=>{
  const e=await env();const old:RawClient={...e.raw,readProjectKnowledgeCatalogue:undefined,readProjectKnowledgeMemory:undefined,readProjectKnowledgeSource:undefined};
  const host=bindMissionHost(old);expect(host.readProjectKnowledgeCatalogue).toBeUndefined();expect(host.projectFilesSearch).toBeUndefined();
 });
 it.each(["catalogue","memory","source"])("auth revocation discards pending %s and never retries",async kind=>{
  const late=deferred(),e=await env(()=>late.promise);const method=kind==="catalogue"?e.host.readProjectKnowledgeCatalogue!:kind==="memory"?e.host.readProjectKnowledgeMemory!:e.host.readProjectKnowledgeSource!;
  const pending=method({... (kind==="source"?sourceSelected:selected),signal:signal()} as never);
  const rejected=expect(pending).rejects.toThrow("READ_CANCELLED");e.notify(out);late.resolve(kind==="source"?source():kind==="memory"?memory():catalogue());await rejected;
  expect(e.invoke.mock.calls.filter(([name])=>name.startsWith("read_project_knowledge_"))).toHaveLength(1);
 });
 it("rejects wrong source revision and tampered exact body",async()=>{
  for(const change of ["revision","content"]){const body=source();if(change==="revision")body.source.revision="f".repeat(40);else body.document.content_utf8+="tampered";
   const e=await env(()=>Promise.resolve(body));await expect(e.host.readProjectKnowledgeSource!({...sourceSelected,signal:signal()})).rejects.toThrow();}
 });
 it("wrong-work body is never released",async()=>{const body=catalogue();body.selection={work_ref:"WS:OTHER"};const e=await env(()=>Promise.resolve(body));await expect(e.host.readProjectKnowledgeCatalogue!({...selected,signal:signal()})).rejects.toThrow();});
 it("abort and missing grant cause zero content reads",async()=>{
  const e=await env(),controller=new AbortController();controller.abort();await expect(e.host.readProjectKnowledgeCatalogue!({...selected,signal:controller.signal})).rejects.toThrow();
  e.notify(out);await expect(e.host.readProjectKnowledgeMemory!({...selected,signal:signal()})).rejects.toThrow();expect(e.host.projectFilesSearch!.context()).toBeNull();
  expect(e.invoke.mock.calls.filter(([name])=>name.startsWith("read_project_knowledge_"))).toHaveLength(0);
 });
 it("replacing the actual source method discards its already-running result",async()=>{
  const late=deferred(),e=await env(()=>late.promise),pending=e.host.readProjectKnowledgeCatalogue!({...selected,signal:signal()});
  e.raw.readProjectKnowledgeCatalogue=async()=>catalogue();late.resolve(catalogue());await expect(pending).rejects.toThrow("READ_CANCELLED");
 });
 it("rejects accessor selectors without invoking them",()=>{let called=0;const value={get work_ref(){called++;return WORK;}};expect(knowledgeReadSelection(value,"catalogue")).toBeNull();expect(called).toBe(0);});
 it.each([{...selected,path:PATH},{...selected,root_job_id:"JOB-1"},{...sourceSelected,expected_revision:REV+"\n"},{...sourceSelected,source_ref:"https://example.com/private"}])("closed selectors reject caller path/root/invalid tuple",value=>{expect(knowledgeReadSelection(value,"source")).toBeNull();});
 it('returns the detached original source when caller data mutates during its digest await',async()=>{
  const body=source(),e=await env(()=>Promise.resolve(body));const original=crypto.subtle.digest.bind(crypto.subtle);
  const spy=vi.spyOn(crypto.subtle,'digest').mockImplementation(async(...args)=>{body.document.content_utf8='different private content';return original(...args);});
  try{const value=await e.host.readProjectKnowledgeSource!({...sourceSelected,signal:signal()}) as ReturnType<typeof source>;expect(value.document.content_utf8).toBe(TEXT);}
  finally{spy.mockRestore();}
 });
 it('checks the actual auth boundary again after source hashing',async()=>{
  const e=await env();const original=crypto.subtle.digest.bind(crypto.subtle);
  const spy=vi.spyOn(crypto.subtle,'digest').mockImplementation(async(...args)=>{e.notify(out);return original(...args);});
  try{await expect(e.host.readProjectKnowledgeSource!({...sourceSelected,signal:signal()})).rejects.toThrow('READ_CANCELLED');}
  finally{spy.mockRestore();}
 });

});
