import { describe, expect, it } from 'vitest';
import actual from './fixtures/project-discovery-current-data.json';
import legacy from './fixtures/programs-available-workspace-service.json';
import { decodeMissionv3, programsFromControlRoom } from './mission';
import { decodeProgramsEnvelope } from './workspace-contract';
import { decodeProgramsObservation } from './programs-observation';
import { decodeProjectDataOwnerObservation, decodeCanonicalProgramsProjects } from './project-discovery';
import { canonicalJson, sha256Hex } from './orchestration/operation-key';

const clone = () => structuredClone(actual) as any;
const selected = { workRef: actual.programs.canonical_projects[0].work_ref, rootJobId: actual.mission.mission.root_job_id! };

describe('actual canonical CREATE/default C→N producer through Programs and Mission consumers', () => {
  it('keeps genuine configured C receipt and clock, normalizes the separate new N row with its actual Runtime root', () => {
    const observation = decodeProgramsObservation(actual.programs);
    expect(observation.controlRoom).toEqual(actual.programs.control_room);
    expect(observation.observation).toEqual(actual.programs.source_observation);
    expect(observation.programsInput).toEqual(decodeProgramsEnvelope(actual.programs));
    const cards = programsFromControlRoom(observation.programsInput);
    expect(cards.state).toBe('AVAILABLE');
    expect(cards.programs).toHaveLength(2);
    expect(cards.programs.find(row => row.workRef === selected.workRef)).toMatchObject({ title:'Mastermind OS delivery',rootJobId:selected.rootJobId,rootState:'RESOLVED' });
    expect(cards.programs[0].workRef).toBe(actual.programs.control_room.work[0].work_ref);
    expect(actual.programs.control_room.generated_at).not.toBe(actual.programs.canonical_projects[0].control_room.generated_at);
    expect(observation.observation?.control_room?.document_digest).toBe(sha256Hex(canonicalJson(actual.programs.control_room)));
  });
  it('decodes explicit actual-root Mission without inventing completeness or dispatch', () => {
    const mission=decodeMissionv3(actual.mission,selected);
    expect(mission?.program.work_ref).toBe(selected.workRef);
    expect(mission?.mission.root_job_id).toBe(selected.rootJobId);
    expect(mission?.read_state.state).toBe('PARTIAL');
    expect(mission?.source.owner_observation?.schema).toBe('mastermind.workspace_source_observation.v2');
    expect(decodeMissionv3(actual.mission,{...selected,rootJobId:'JOB-9999'})).toBeNull();
  });
  it.each(['N-digest','C-anchor','foreign-work','code-pin','clock','generation','duplicate','extra','coverage'])('withholds malformed or mismatched %s rather than returning a partial invented list',fault=>{
    const copy=clone(), body=copy.programs, project=body.canonical_projects[0], basis=project.source_observation.project_data;
    if(fault==='N-digest')basis.document_digest='f'.repeat(64);
    if(fault==='C-anchor')project.source_observation.control_room.publication_after+=1;
    if(fault==='foreign-work')project.work_ref='WS:FOREIGN';
    if(fault==='code-pin')basis.code_source.commit='f'.repeat(40);
    if(fault==='clock')basis.data_observation.canonical_observed_at_ms+=3600000;
    if(fault==='generation')project.cache_currentness.source_generation='f'.repeat(64);
    if(fault==='duplicate'){body.canonical_projects.push(structuredClone(project));body.coverage.returned+=1;}
    if(fault==='extra')project.send_permission=true;
    if(fault==='coverage')body.coverage.returned+=1;
    expect(()=>decodeProgramsObservation(body)).toThrow();
  });
  it('retains legacy v1 normalization and observation shape unchanged',()=>{
    const observation=decodeProgramsObservation(legacy);
    expect(observation).not.toHaveProperty('programsInput');
    expect(observation.controlRoom).toEqual(decodeProgramsEnvelope(legacy));
    expect(programsFromControlRoom(observation.controlRoom)).toEqual(programsFromControlRoom(legacy.control_room));
  });
});


describe('canonical DATA codec currentness and inert JSON boundary',()=>{
  const owner=()=>clone().programs.canonical_projects[0].source_observation;
  it('detaches and freezes an issued syntax result without claiming command authority',()=>{
    const raw=owner(),decoded=decodeProjectDataOwnerObservation(raw,null)!;
    expect(decoded.state).toBe('SAME');expect(Object.isFrozen(decoded.project_data)).toBe(true);
    raw.project_data.source.commit='f'.repeat(40);
    expect(decoded.project_data.source.commit).not.toBe(raw.project_data.source.commit);
    expect(decoded).not.toHaveProperty('can_send');
  });
  it.each(['accessor','toJSON','symbol','cycle','nonfinite','oversize','array-extra','prototype'])('refuses hostile %s JSON without invoking content',fault=>{
    let calls=0;const raw:any=owner();
    if(fault==='accessor')Object.defineProperty(raw,'project_data',{get(){calls++;return {};},enumerable:true});
    if(fault==='toJSON')raw.toJSON=()=>{calls++;return {};};
    if(fault==='symbol')raw[Symbol('hidden')]=true;
    if(fault==='cycle')raw.cycle=raw;
    if(fault==='nonfinite')raw.runtime.before=Infinity;
    if(fault==='oversize')raw.padding='x'.repeat(2_000_001);
    if(fault==='array-extra')raw.project_data.creation_publication.sources.extra=true;
    if(fault==='prototype')Object.setPrototypeOf(raw,{can_send:true});
    expect(decodeProjectDataOwnerObservation(raw,null)).toBeNull();expect(calls).toBe(0);
  });
  it.each(['expired','schema','policy','root','proof','unqualified','missing'])('rejects forged card %s even with freshly recomputed transport hashes',fault=>{
    const copy=clone(),p=copy.programs.canonical_projects[0],row=p.control_room.autonomy.responsibilities[0],r=p.source_validity.cards[0].components.card;
    if(fault==='expired'){r.remaining_ms=0;r.state='stale';}
    if(fault==='schema')row.validity.card.schema='other';
    if(fault==='policy')row.validity.card.policy='other';
    if(fault==='root')p.source_validity.cards[0].root_job_id='JOB-9999';
    if(fault==='proof')r.proof_ref='f'.repeat(64);
    if(fault==='unqualified'){r.remaining_ms=null;r.state='unqualified';}
    if(fault==='missing')delete p.source_validity.cards[0].components.card;
    p.source_observation.project_data.document_digest=sha256Hex(canonicalJson(p.control_room));
    p.source_observation.project_data.source_validity_digest=sha256Hex(canonicalJson(p.source_validity));
    expect(()=>decodeCanonicalProgramsProjects([p],copy.programs.source_observation,copy.programs.control_room)).toThrow('PROJECT_DATA_INVALID');
  });
});
