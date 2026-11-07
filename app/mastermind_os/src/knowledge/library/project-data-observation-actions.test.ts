import {describe,expect,it} from 'vitest';
import {knowledgeReadKeys,sameKnowledgeCodeContext,validateKnowledgeReadMetadata,
 validateProjectDataObservation,validateProjectKnowledgeCodeContext,
 type CanonicalProjectDataObservation} from './project-data-observation';

const REPEAT=(char:string,n:number)=>char.repeat(n);
const CODE=REPEAT('a',40),DATA=REPEAT('b',40),OTHER40=REPEAT('7',40),COMMIT=REPEAT('9',40);
const READER=REPEAT('c',64),PRINCIPAL=REPEAT('e',64);
const SHA2=REPEAT('2',64),SHA3=REPEAT('3',64),SHA4=REPEAT('4',64),SHA5=REPEAT('5',64);
const TAIL='a1b2c3d4e5a1b2c3d4e5a1b2c3d4e5a1b2c3d4e5',TAILUP=TAIL.toUpperCase();
const WORK='ALPHA',WSREF='WS:'+WORK;
const MS=1700000000000,WHEN='2026-01-15T10:20:30Z';
const INVALID='INVALID_CANONICAL_DATA_OBSERVATION';
const WS_PATH='agentos/workstreams/WS-'+WORK+'.md';
const DECISION='agentos/decisions/DEC-PLAN-ADOPTION-'+TAILUP+'.md';
const PLAN='research/project-plans/PLAN-'+WORK+'-'+TAIL+'.md';
const createRequest='mmos-project-create-'+TAIL;
const planRequest='mmos-project-plan-proposal-'+TAIL;
const adoptRequest='mmos-project-adopt-'+TAIL;
const addRequest='mmos-project-file-add-'+TAIL;
const prefRequest='mmos-project-preference-set-'+TAIL;
const fails=(value:unknown,expected:{workRef?:string;canonicalDataCommit?:string;executableMacroCommit?:string}={}):void=>{
 expect(()=>validateProjectDataObservation(value,expected)).toThrow(INVALID);
};
function source(path:string,commit:string=COMMIT,content=SHA2):Record<string,unknown>{
 return {repository:'macro',commit,path,content_sha256:content};
}
function operation(action:string,request:string,work:string,sources:unknown,selectionPatch:Record<string,unknown>={}):Record<string,unknown>{
 return {selection:{action,request_id:request,work_ref:work,...selectionPatch},principal_scope:PRINCIPAL,
  request_sha256:SHA3,recipe_fingerprint_sha256:SHA4,event_id:11,receipt_sha256:SHA5,recorded_at_ms:MS,sources};
}
function body(operation:unknown,patch:Record<string,unknown>={}):Record<string,unknown>{
 return {schema:'mastermind.canonical_project_data_observation.v1',repository:'mastermindx-market-intelligence/macro',
  default_ref:'main',executable_macro_commit:CODE,canonical_data_commit:CODE,canonical_commit_at:WHEN,
  canonical_observed_at_ms:MS,publication_recorded_at_ms:operation===null?null:MS,publication_time:null,
  source_operation:operation,reader_closure_sha256:READER,code_config_relation:'IDENTICAL_READER_CLOSURE',
  authority:'OBSERVATION_ONLY',...patch};
}
function continuity():Record<string,unknown>{
 return {schema:'mastermind.project_data_continuity.v1',kind:'UNCHANGED_SELECTED_PROJECT_DATA',work_ref:WSREF,
  principal_scope:PRINCIPAL,executable_macro_commit:CODE,canonical_data_commit:DATA,
  reader_closure_sha256:READER,selected_data_closure_sha256:SHA2,ancestry:'CODE_ANCESTOR_OF_DATA'};
}
function adoptContinuityBody():Record<string,unknown>{
 return body(null,{canonical_data_commit:DATA,publication_recorded_at_ms:null,data_continuity:continuity()});
}
function sparseAdopt():unknown[]{
 const items:unknown[]=new Array(3);items[0]=source(WS_PATH);items[2]=source(DECISION);return items;
}

describe('new publication and adoption action variants',()=>{
 it('accepts CREATE with exactly one workstream source',()=>{
  const observation=validateProjectDataObservation(body(operation('publish_project_proposal',createRequest,WSREF,[source(WS_PATH)])));
  expect(observation.source_operation?.selection).toEqual({action:'publish_project_proposal',request_id:createRequest,work_ref:WSREF});
  expect(observation.source_operation?.sources).toHaveLength(1);
  expect(Object.isFrozen(observation)).toBe(true);
  expect(Object.isFrozen(observation.source_operation?.sources)).toBe(true);
 });
 it('accepts PLAN with the workstream plus the exact lowercase-tail plan path',()=>{
  const observation=validateProjectDataObservation(body(operation('publish_project_plan_proposal',planRequest,WSREF,[source(PLAN),source(WS_PATH)])));
  expect(observation.source_operation?.sources.map(item=>item.path).sort()).toEqual([PLAN,WS_PATH].sort());
 });
 it('accepts ADOPT with exactly two sources including the adoption decision',()=>{
  const observation=validateProjectDataObservation(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(DECISION),source(WS_PATH)])));
  expect(observation.source_operation?.selection.action).toBe('ADOPT_PLAN');
  expect(observation.source_operation?.sources.map(item=>item.path).sort()).toEqual([DECISION,WS_PATH].sort());
 });
 it('accepts ADOPT with exactly one canonical predecessor decision',()=>{
  const observation=validateProjectDataObservation(body(operation('ADOPT_PLAN',adoptRequest,WSREF,
   [source(WS_PATH),source(DECISION),source('agentos/decisions/DEC-PLAN-B-STATUS.md')])));
  expect(observation.source_operation?.sources).toHaveLength(3);
 });
 it('accepts predecessor keys at the 2 and 128 length boundaries',()=>{
  validateProjectDataObservation(body(operation('ADOPT_PLAN',adoptRequest,WSREF,
   [source(WS_PATH),source(DECISION),source('agentos/decisions/DEC-K2.md')])));
  validateProjectDataObservation(body(operation('ADOPT_PLAN',adoptRequest,WSREF,
   [source(WS_PATH),source(DECISION),source('agentos/decisions/DEC-'+REPEAT('A',128)+'.md')])));
 });
 it('never infers that source commits equal the DATA commit',()=>{
  const observation=body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH,OTHER40),source(DECISION,OTHER40)]),
   {canonical_data_commit:DATA});
  expect(validateProjectDataObservation(observation).canonical_data_commit).toBe(DATA);
 });
 it('preserves detached null-prototype bodies and recursive freezing',()=>{
  const detached=Object.assign(Object.create(null),body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION)])));
  const observation:CanonicalProjectDataObservation=validateProjectDataObservation(detached);
  expect(Object.isFrozen(observation)).toBe(true);
  expect(Object.isFrozen(observation.source_operation)).toBe(true);
  expect(Object.isFrozen(observation.source_operation?.sources[0])).toBe(true);
 });
});

describe('action grammar negatives',()=>{
 it('rejects unknown actions including candidate and READY selections',()=>{
  fails(body(operation('READY',adoptRequest,WSREF,[source(WS_PATH),source(DECISION)])));
  fails(body(operation('candidate',createRequest,WSREF,[source(WS_PATH)])));
  fails(body(operation('publish_project_plan',planRequest,WSREF,[source(WS_PATH),source(PLAN)])));
 });
 it('rejects foreign request id prefixes and malformed tails',()=>{
  fails(body(operation('publish_project_proposal',adoptRequest,WSREF,[source(WS_PATH)])));
  fails(body(operation('ADOPT_PLAN',createRequest,WSREF,[source(WS_PATH),source(DECISION)])));
  fails(body(operation('publish_project_proposal',createRequest+'0',WSREF,[source(WS_PATH)])));
  fails(body(operation('ADOPT_PLAN','mmos-project-adopt-'+TAILUP,WSREF,[source(WS_PATH),source(DECISION)])));
  fails(body(operation('ADOPT_PLAN','mmos-project-adopt-'+REPEAT('8',39),WSREF,[source(WS_PATH),source(DECISION)])));
 });
 it('rejects wrong CREATE and PLAN source paths',()=>{
  fails(body(operation('publish_project_proposal',createRequest,WSREF,[source('agentos/workstreams/WS-BETA.md')])));
  fails(body(operation('publish_project_proposal',createRequest,WSREF,[source('agentos/workstreams/WS-'+WORK.toLowerCase()+'.md')])));
  fails(body(operation('publish_project_plan_proposal',planRequest,WSREF,[source(WS_PATH),source('research/project-plans/PLAN-'+WORK+'-'+TAILUP+'.md')])));
  fails(body(operation('publish_project_plan_proposal',planRequest,WSREF,[source(WS_PATH),source('research/project-plans/PLAN-'+WORK+'.md')])));
  fails(body(operation('publish_project_plan_proposal',planRequest,WSREF,[source(WS_PATH),source('research/plans/PLAN-'+WORK+'-'+TAIL+'.md')])));
 });
 it('rejects wrong ADOPT paths: candidate, READY, receipt and lowercase decisions',()=>{
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source('agentos/decisions/DEC-READY.md')])));
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(DECISION),source('agentos/decisions/DEC-CLIENT-RECEIPT.md')])));
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source('agentos/decisions/dec-plan-adoption-'+TAILUP+'.md')])));
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source('agentos/decisions/DEC-PLAN-ADOPTION-'+TAIL+'.md')])));
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION),source('agentos/client/receipt-1.md')])));
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION),source('agentos/decisions/DEC-plan-b.md')])));
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION),source('agentos/decisions/DEC-PLAN-B/../DEC-C.md')])));
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION),source('agentos/decisions/DEC-A.md')])));
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION),source('agentos/decisions/DEC-'+REPEAT('A',129)+'.md')])));
 });
 it('rejects wrong source counts per action',()=>{
  fails(body(operation('publish_project_proposal',createRequest,WSREF,[source(WS_PATH),source(PLAN)])));
  fails(body(operation('publish_project_plan_proposal',planRequest,WSREF,[source(WS_PATH)])));
  fails(body(operation('publish_project_plan_proposal',planRequest,WSREF,[source(WS_PATH),source(PLAN),source(DECISION)])));
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH)])));
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION),source('agentos/decisions/DEC-K2.md'),source('agentos/decisions/DEC-K3.md')])));
 });
 it('rejects work refs outside the 2..64 canonical key',()=>{
  fails(body(operation('publish_project_proposal',createRequest,'WS:A',[source(WS_PATH)])));
  fails(body(operation('publish_project_proposal',createRequest,'WS:'+REPEAT('A',65),[source(WS_PATH)])));
  fails(body(operation('publish_project_proposal',createRequest,'WS:'+WORK.toLowerCase(),[source(WS_PATH)])));
  fails(body(operation('ADOPT_PLAN',adoptRequest,'ALPHA',[source(WS_PATH),source(DECISION)])));
  fails(body(operation('publish_project_proposal',createRequest,WSREF,[source(WS_PATH)]),{workRef:'WS:BETA'}));
 });
 it('rejects wrong commits and hashes in sources',()=>{
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION,OTHER40)])));
  fails(body(operation('publish_project_proposal',createRequest,WSREF,[source(WS_PATH,REPEAT('9',39))])));
  fails(body(operation('publish_project_proposal',createRequest,WSREF,[source(WS_PATH,REPEAT('A',40))])));
  fails(body(operation('publish_project_proposal',createRequest,WSREF,[{...source(WS_PATH),content_sha256:REPEAT('2',63)}])));
 });
 it('rejects extra fields anywhere in the strict shapes',()=>{
  fails({...body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION)])),extra:1});
  fails(body({...operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION)]),extra:1}));
  fails(body(operation('publish_project_proposal',createRequest,WSREF,[source(WS_PATH)],{extra:1})));
  fails(body(operation('publish_project_proposal',createRequest,WSREF,[{...source(WS_PATH),extra:1}])));
 });
 it('rejects getter-backed fields in selections and sources',()=>{
  const getterItem=source(WS_PATH);
  Object.defineProperty(getterItem,'path',{enumerable:true,get:()=>WS_PATH});
  fails(body(operation('publish_project_proposal',createRequest,WSREF,[getterItem])));
  const getterSelection=operation('publish_project_proposal',createRequest,WSREF,[source(WS_PATH)]);
  Object.defineProperty(getterSelection.selection,'request_id',{enumerable:true,get:()=>createRequest});
  fails(body(getterSelection));
 });
 it('rejects sparse or non-array source lists',()=>{
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,sparseAdopt())));
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,{0:source(WS_PATH),1:source(DECISION),length:2})));
  const planSparse:unknown[]=[];planSparse[0]=source(WS_PATH);planSparse[2]=source(PLAN);
  fails(body(operation('publish_project_plan_proposal',planRequest,WSREF,planSparse)));
  fails(body(operation('publish_project_proposal',createRequest,WSREF,null as unknown as unknown[])));
 });
});

describe('original two-source actions, continuity, clock and knowledge law preserved',()=>{
 it('still accepts add_project_file and set_project_communication_preference',()=>{
  const added=validateProjectDataObservation(body(operation('add_project_file',addRequest,WSREF,[source(WS_PATH),source('agentos/decisions/DEC-ALPHA.md')])));
  expect(added.source_operation?.selection.action).toBe('add_project_file');
  const preferred=validateProjectDataObservation(body(operation('set_project_communication_preference',prefRequest,WSREF,[source(WS_PATH),source(DECISION)])));
  expect(preferred.source_operation?.selection.action).toBe('set_project_communication_preference');
  fails(body(operation('add_project_file',addRequest,WSREF,[source(WS_PATH)])));
  fails(body(operation('add_project_file',addRequest,WSREF,[source(WS_PATH),source(WS_PATH)])));
 });
 it('keeps the no-operation, continuity and mutual-exclusion law',()=>{
  const quiet=validateProjectDataObservation(body(null));
  expect(quiet.publication_recorded_at_ms).toBe(null);
  expect(quiet.source_operation).toBe(null);
  fails(body(null,{publication_recorded_at_ms:MS}));
  fails(body(null,{canonical_data_commit:DATA}));
  const moved=validateProjectDataObservation(adoptContinuityBody());
  expect(moved.data_continuity?.canonical_data_commit).toBe(DATA);
  expect(Object.isFrozen(moved.data_continuity)).toBe(true);
  fails(body(null,{canonical_data_commit:DATA,data_continuity:{...continuity(),canonical_data_commit:CODE}}));
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION)]),{data_continuity:continuity()}));
  fails(adoptContinuityBody(),{workRef:'WS:BETA'});
  fails(body(null,{canonical_data_commit:DATA,publication_recorded_at_ms:null,data_continuity:{...continuity(),reader_closure_sha256:SHA3}}));
 });
 it('keeps the exact clock, date and null law',()=>{
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION)]),{publication_recorded_at_ms:MS+1}));
  fails(body(null,{canonical_observed_at_ms:0}));
  fails(body(null,{canonical_commit_at:'2026-02-30T00:00:00Z'}));
  fails(body(null,{canonical_commit_at:'2026-01-15T10:20:60Z'}));
  fails(body(null,{canonical_commit_at:'2026-01-15T10:20:30+24:00'}));
  fails(body(null,{publication_time:WHEN}));
  fails(body(null,{authority:'PUBLICATION'}));
  fails(body(null,{schema:'mastermind.canonical_project_data_observation.v2'}));
  fails(body(null,{repository:'other/repo'}));
 });
 it('keeps expected CODE/DATA/work binding checks',()=>{
  fails(body(operation('ADOPT_PLAN',adoptRequest,WSREF,[source(WS_PATH),source(DECISION)]),{executable_macro_commit:OTHER40}),{executableMacroCommit:CODE});
  fails(body(null),{canonicalDataCommit:OTHER40});
  fails(body(null),{executableMacroCommit:OTHER40});
  validateProjectDataObservation(body(null),{executableMacroCommit:CODE,canonicalDataCommit:CODE});
 });
 it('keeps Knowledge two-source behavior unchanged',()=>{
  expect(knowledgeReadKeys({a:1,code_context:{},data_observation:{}},['a'])).toEqual(['a','code_context','data_observation']);
  expect(knowledgeReadKeys({a:1},['a'])).toEqual(['a']);
  const codeContext={schema:'mastermind.project_knowledge_code_context.v1' as const,work_ref:WSREF,executable_macro_commit:CODE,reader_source_commit:CODE};
  expect(validateProjectKnowledgeCodeContext(codeContext,WSREF).executable_macro_commit).toBe(CODE);
  expect(()=>validateProjectKnowledgeCodeContext(codeContext,'WS:BETA')).toThrow(INVALID);
  const withData=validateKnowledgeReadMetadata({code_context:codeContext,source:{commit:DATA},
   data_observation:adoptContinuityBody()},WSREF);
  expect(withData.dataObservation?.canonical_data_commit).toBe(DATA);
  expect(withData.codeContext?.work_ref).toBe(WSREF);
  expect(validateKnowledgeReadMetadata({code_context:codeContext,source:{commit:CODE}},WSREF).dataObservation).toBeUndefined();
  expect(()=>validateKnowledgeReadMetadata({code_context:codeContext,source:{commit:DATA}},WSREF)).toThrow(INVALID);
  expect(Object.keys(validateKnowledgeReadMetadata({source:{commit:CODE}},WSREF))).toEqual([]);
  expect(sameKnowledgeCodeContext(codeContext,{...codeContext})).toBe(true);
  expect(sameKnowledgeCodeContext(codeContext,undefined)).toBe(false);
  expect(sameKnowledgeCodeContext(undefined,undefined)).toBe(true);
  expect(sameKnowledgeCodeContext(codeContext,{...codeContext,reader_source_commit:OTHER40})).toBe(false);
 });
});

// Parent review: fixed-count variants must reject a trailing empty array slot,
// retaining the original exact-two Knowledge grammar as well as new C/P laws.
it('refuses trailing sparse slots in every fixed-count source variant',()=>{
 const cases:[string,string,unknown[]][]=[
  ['publish_project_proposal',createRequest,[source(WS_PATH)]],
  ['publish_project_plan_proposal',planRequest,[source(WS_PATH),source(PLAN)]],
  ['add_project_file',addRequest,[source(WS_PATH),source('agentos/project-files/WS-ALPHA/one.md')]],
  ['set_project_communication_preference',prefRequest,[source(WS_PATH),source('agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-ALPHA.md')]],
 ];
 for(const [action,id,sources] of cases){sources.length++;fails(body(operation(action,id,WSREF,sources)));}
});
