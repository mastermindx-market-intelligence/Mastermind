/** Actual Python private-input/Events/temp-Git DTOs through the existing native
 * transport and durable controller. Native authentication is an explicit seam. */
import {expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {bindMissionHost,createNativeClient} from '../../host';
import {OperationController} from '../../orchestration/operation-controller';
import {createIndexedDbPendingPointerStore} from '../../orchestration/indexeddb-pending-pointer-store';
import {parseProjectSourceWriteTarget,serializeProjectSourceWriteTarget} from '../../orchestration/project-source-write-target';
import {decodeCurrentProjectAccess} from '../../access/project-access-current';
import v5 from '../../access/fixtures/v5-current-grants.json';
import fixture from '../../fixtures/discovery-correction-owner.json';
import {validateDiscoveryCorrectionRequest,validateDiscoveryCorrectionLookup,discoveryReplacementRef,
  qualifyDiscoveryCorrectionSources} from './project-discovery-correction';
import {publicRequestSha256} from './project-knowledge-requests';
import {decodeProjectKnowledgePreview} from './project-knowledge-preview';
import {bindProjectKnowledgeCommandOwner,prepareProjectKnowledgeWrite,createProjectKnowledgeCommandPort,
  type PreparedProjectKnowledgeWrite} from './project-knowledge-port';

const signal=()=>new AbortController().signal;
const request=()=>validateDiscoveryCorrectionRequest(structuredClone(fixture.request));
const lookup=()=>validateDiscoveryCorrectionLookup(structuredClone(fixture.lookup));
const principal=fixture.context.owner_context.principal_scope;
it('keeps exact actual request bytes, SHA, derived replacement and v2 original target',async()=>{
 const r=request(),l=lookup();expect(await publicRequestSha256(r)).toBe(fixture.preview.request_sha256);
 expect(Object.isFrozen(r.replacement.evidence)).toBe(true);
 const {request_id,...target}=l,key=serializeProjectSourceWriteTarget(target);
 expect(key).toMatch(/^project-source-write\.v2:/);expect(parseProjectSourceWriteTarget(key!)).toEqual(target);
 expect(parseProjectSourceWriteTarget(key!.replace('.v2:','.v1:'))).toBeNull();
 expect(fixture.preview.preview.change.replacement_ref).toBe(discoveryReplacementRef({request_id,work_ref:r.work_ref},principal));
 expect(decodeProjectKnowledgePreview(fixture.preview,r,await publicRequestSha256(r))).toEqual(fixture.preview);
});
it.each(['authority','preference','prefix','date','expiry','duplicate','sparse','surrogate','bytes','empty','extraReplacement'])(
 'refuses malformed correction %s before I/O',change=>{
 const r:any=structuredClone(fixture.request);
 if(change==='authority')r.principal_scope=principal;
 if(change==='preference')r.expected_preference_revision=null;
 if(change==='prefix')r.request_id=r.request_id.replace('discovery-correct','file-add');
 if(change==='date')r.replacement.verified_at='2026-02-29';
 if(change==='expiry')r.replacement.expires='2026-11-04';
 if(change==='duplicate')r.replacement.evidence.push(r.replacement.evidence[0]);
 if(change==='sparse')r.replacement.evidence=new Array(2);
 if(change==='surrogate')r.replacement.claim='\ud800';
 if(change==='bytes')r.replacement.claim='中'.repeat(683);
 if(change==='empty')r.replacement.confidence='';
 if(change==='extraReplacement')r.replacement.auto_verify=true;
 expect(()=>validateDiscoveryCorrectionRequest(r)).toThrow();
});
it('does not invoke request or evidence accessors and preserves exact eight-field lookup',()=>{
 let read=0;const r=structuredClone(fixture.request);
 Object.defineProperty(r.replacement.evidence,'0',{enumerable:true,get(){read++;return 'caller';}});
 expect(()=>validateDiscoveryCorrectionRequest(r)).toThrow();expect(read).toBe(0);
 const l=lookup();expect(Object.keys(l)).toHaveLength(8);
 expect(()=>validateDiscoveryCorrectionLookup({...l,expected_preference_revision:null})).toThrow();
});
it.each(['missing','duplicate','old','commit','content'])(
 'qualifies the original three-source set and rejects %s',change=>{
 const sources=structuredClone(fixture.source_status.receipt.sources);
 qualifyDiscoveryCorrectionSources(lookup(),principal,sources,fixture.preview.preview.postimages);
 if(change==='missing')sources.pop();
 if(change==='duplicate')sources[2]=sources[0]!;
 if(change==='old')sources.find(item=>item.path==='agentos/discoveries/DSC-ORIGINAL-FINDING.md')!.path='agentos/discoveries/DSC-FOREIGN-FINDING.md';
 if(change==='commit')sources[2]!.commit='e'.repeat(40);
 if(change==='content')sources[2]!.content_sha256='f'.repeat(64);
 expect(()=>qualifyDiscoveryCorrectionSources(lookup(),principal,sources,fixture.preview.preview.postimages)).toThrow();
});
it('rejects a preview with altered evidence or a fourth postimage',async()=>{
 const r=request(),sha=await publicRequestSha256(r),first=structuredClone(fixture.preview);
 first.preview.change.replacement.confidence='verified';expect(decodeProjectKnowledgePreview(first,r,sha)).toBeNull();
 const next=structuredClone(fixture.preview);next.preview.postimages.push(next.preview.postimages[0]!);
 expect(decodeProjectKnowledgePreview(next,r,sha)).toBeNull();
});
async function setup(){
 let source=true,current=true,published=false,prepared:PreparedProjectKnowledgeWrite|null=null;
 const invoke=vi.fn(async(name:string)=>{
  if(name==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:false};
  if(name==='executive_auth_status')return {generation:0,available:false};
  if(name==='source_operation_prepare')return fixture.preview;
  if(name==='source_operation_submit')return fixture.proposal_status;
  if(name==='source_operation_read'||name==='source_operation_reconcile')return published?fixture.source_status:fixture.proposal_status;
  throw Error('Unexpected native call');
 });
 const host=bindMissionHost(await createNativeClient(invoke as never,async()=>()=>{}));
 const owner=bindProjectKnowledgeCommandOwner({workRef:fixture.request.work_ref,generation:'fixture-host:0',
  contexts:{correct_project_discovery:fixture.context},isCurrent:()=>current,sourceIsCurrent:()=>source,discoveryIsCurrent:()=>source});
 const transport=host.sourceOperations!,factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
 const port=()=>createProjectKnowledgeCommandPort({workRef:fixture.request.work_ref,transport,owner,prepared:()=>prepared,
  isPreparedCurrent:value=>source&&prepared===value});
 return {invoke,owner,transport,store,factory,port,loseSource:()=>{source=false;prepared=null;},publish:()=>{published=true;},
  revoke:()=>{current=false;},prepare:async()=>prepared=await prepareProjectKnowledgeWrite({request:request(),transport,owner,isCurrent:()=>current},signal())};
}
it('reserves one safe pointer, submits once, and reopens/reconciles without original body or compiler',async()=>{
 const f=await setup(),p=await f.prepare();expect(await f.store.read(principal)).toBeNull();
 const first=new OperationController(f.port(),f.store),intent={kind:'project_source_write' as const,targetKey:p.targetKey,payload:{action:p.target.action,request:p.request}};
 expect((await first.begin(intent)).status).toBe('unknown');await first.begin(intent);
 const saved=await f.store.read(principal);expect(saved?.operationKey).toBe(p.request.request_id);
 expect(JSON.stringify(saved)).not.toContain('correction_reason');expect(JSON.stringify(saved)).not.toContain('preview_witness');
 first.invalidate();f.loseSource();f.publish();
 const reopened=new OperationController(f.port(),createIndexedDbPendingPointerStore(f.factory));
 expect((await reopened.recover({reconcileSource:true})).status).toBe('accepted');
 expect(await f.store.read(principal)).toBeNull();
 expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_prepare')).toHaveLength(1);
 expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_submit')).toHaveLength(1);
 expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_reconcile')).toHaveLength(1);
});
it('requires the issued discovery separately from the correction grant',async()=>{
 const f=await setup();f.loseSource();
 await expect(f.prepare()).rejects.toThrow();expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_prepare')).toHaveLength(0);
});
it('requires the exact v6 eleven-action read projection and never infers correction from v5',()=>{
 const body:any=structuredClone(v5);body.schema='mastermind.workspace_project_access.v3';
 body.grant_schema='mastermind.workspace_acquisition_bindings.v6';
 body.grants.push({...body.grants[8],action:'correct_project_discovery'});
 const decoded=decodeCurrentProjectAccess(body,body.selection);expect(decoded).toEqual(body);
 body.grants.pop();expect(decodeCurrentProjectAccess(body,body.selection)).toBeNull();
 expect(decodeCurrentProjectAccess(v5,v5.selection)?.grants?.some(row=>String(row.action)==='correct_project_discovery')).toBe(false);
});
