import { describe, expect, it } from 'vitest';
import actual from './fixtures/project-execution-resource-owner.json';
import legacy from './fixtures/project-discovery-current-data.json';
import { decodeProgramsObservation } from './programs-observation';
import { decodeOwnerObservation } from './workspace-contract';
import { decodeMissionv3, decodeProjectExecutionResourceRead, programsFromControlRoom } from './mission';
import { canChooseRetainedHistory, decodeProjectRootHistory, isProjectExecutionHistoryRoot, sameProjectRootProvenance } from './project-discovery';
import { canonicalJson, sha256Hex } from './orchestration/operation-key';

const selection={workRef:actual.selection.work_ref,rootJobId:actual.selection.root_job_id};
const clone=()=>structuredClone(actual) as any;
const history=()=>decodeProjectRootHistory(actual.programs.canonical_projects[0].root_history,selection.workRef)!;
const rehash=(value:any)=>{value.observation.snapshot_digest=sha256Hex(canonicalJson({work_ref:value.work_ref,roots:value.roots}));};

describe('actual original execution owner through the closed history/resource projections',()=>{
  it('keeps all roots and global conflict while exposing original roles only on v3',()=>{
    const observation=decodeProgramsObservation(actual.programs);
    const cards=programsFromControlRoom(observation.programsInput);
    expect(cards.state).toBe('AVAILABLE');
    const card=cards.programs.find(item=>item.workRef===selection.workRef)!;
    expect(card).toMatchObject({rootJobId:null,rootState:'CONFLICT',rootCandidates:['JOB-001','JOB-002']});
    expect(card.rootHistory).toEqual(actual.programs.canonical_projects[0].root_history);
    expect(card.rootHistory?.roots.map(row=>row.purpose)).toEqual(['PLANNING','PROJECT_EXECUTION']);
    expect(canChooseRetainedHistory(card,selection.rootJobId)).toBe(true);
    expect(isProjectExecutionHistoryRoot(card.rootHistory,'JOB-001')).toBe(false);
    const old=decodeProgramsObservation(legacy.programs);
    expect(programsFromControlRoom(old.programsInput).programs.every(row=>!Object.hasOwn(row,'rootHistory'))).toBe(true);
  });
  it('admits the actual PARTIAL resource only through the dedicated reader',()=>{
    const result=decodeProjectExecutionResourceRead(actual.mission,selection)!;
    expect(result).not.toBeNull();expect(result.missionReadState).toBe('PARTIAL');
    expect(result.resource.execution_authorized).toBe(false);
    expect(result.resource.current_adoption.state).toBe('NOT_OBSERVED');
    expect(result.resource.original_input.state).toBe('UNAVAILABLE');
    expect(decodeMissionv3(actual.mission,selection)).toBeNull();
    expect(decodeOwnerObservation(actual.mission.source.owner_observation,actual.selection)).toBeNull();
    expect(Object.isFrozen(result.resource.history.roots)).toBe(true);
  });
  it.each(['missing','legacy-scope','foreign-root','scope','authority','numeric-false','history-digest','foreign-work',
    'input','adoption','unsafe-after','boolean-after','changed-after','extra'])('refuses %s resource evidence',fault=>{
    const value=clone().mission,o=value.source.owner_observation,r=o.resource;
    if(fault==='missing')delete o.resource;
    if(fault==='legacy-scope'){o.schema='mastermind.workspace_source_observation.v2';delete o.resource;}
    if(fault==='foreign-root')r.selection.root_job_id='JOB-999';
    if(fault==='scope')r.scope='CURRENT_MISSION';
    if(fault==='authority')r.execution_authorized=true;
    if(fault==='numeric-false')r.execution_authorized=0;
    if(fault==='history-digest')r.history.observation.snapshot_digest='f'.repeat(64);
    if(fault==='foreign-work')r.history.work_ref='WS:OTHER';
    if(fault==='input')r.original_input={state:'AVAILABLE',reason:null};
    if(fault==='adoption')r.current_adoption={state:'CURRENT',reason:null};
    if(fault==='unsafe-after')r.history.observation.after=2**53;
    if(fault==='boolean-after')r.history.observation.after=true;
    if(fault==='changed-after')r.history.observation.after++;
    if(fault==='extra')r.send=true;
    expect(decodeProjectExecutionResourceRead(value,selection)).toBeNull();
  });
  it.each(['missing-history','extra-root','wrong-work','wrong-digest','empty-v3'])('refuses %s Programs history instead of dropping it',fault=>{
    const value=clone().programs,p=value.canonical_projects[0];
    if(fault==='missing-history')delete p.root_history;
    if(fault==='extra-root'){const row=structuredClone(p.root_history.roots[0]);row.root_job_id='JOB-003';p.root_history.roots.push(row);rehash(p.root_history);}
    if(fault==='wrong-work')p.root_history.work_ref='WS:OTHER';
    if(fault==='wrong-digest')p.root_history.observation.snapshot_digest='f'.repeat(64);
    if(fault==='empty-v3'){const row=p.root_history.roots[1];row.execution=null;row.purpose='ORCHESTRATION';rehash(p.root_history);}
    expect(()=>decodeProgramsObservation(value)).toThrow();
  });
  it('permits a fresh status/observation but refuses changed original provenance',()=>{
    const before=history(),raw=structuredClone(before) as any;
    raw.roots[1].status='RUNNING';raw.observation.before=raw.observation.after=99;
    raw.observation.source_identity='new-bounded-observation';rehash(raw);
    const after=decodeProjectRootHistory(raw,selection.workRef)!;
    expect(after).not.toBeNull();expect(sameProjectRootProvenance(before,after)).toBe(true);
    raw.roots[1].creation_event_sha256='e'.repeat(64);rehash(raw);
    expect(sameProjectRootProvenance(before,decodeProjectRootHistory(raw,selection.workRef)!)).toBe(false);
  });
  it('recognizes sole execution history without making a planning root a resource',()=>{
    const raw=structuredClone(history()) as any;raw.roots=raw.roots.filter((row:any)=>row.execution!==null);rehash(raw);
    const one=decodeProjectRootHistory(raw,selection.workRef)!;
    const card={workRef:selection.workRef,rootState:'RESOLVED',rootJobId:selection.rootJobId,rootCandidates:[selection.rootJobId],rootHistory:one};
    expect(canChooseRetainedHistory(card,selection.rootJobId)).toBe(true);
    expect(canChooseRetainedHistory({...card,rootHistory:undefined},selection.rootJobId)).toBe(false);
    expect(canChooseRetainedHistory({...card,rootJobId:'JOB-001',rootCandidates:['JOB-001'],rootHistory:history()},'JOB-001')).toBe(false);
  });
});
