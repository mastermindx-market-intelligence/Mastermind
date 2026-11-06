/** Existing safe Knowledge lookup only; URL DATA, never a body or authority. */
import {sourceOperationRequest,type KnowledgeSourceLookup} from '../source-operations/transport';
export type ProjectDraftFileLookup=KnowledgeSourceLookup & {readonly action:'add_project_file';readonly expected_preference_revision:null};
function invalid():never{throw Error('PROJECT_DRAFT_FILE_LOOKUP_INVALID');}
export function decodeProjectDraftFileLookup(raw:unknown,workRef:string):Readonly<ProjectDraftFileLookup>{
 try{
  const value=sourceOperationRequest('read',raw);
  if(value.action!=='add_project_file'||value.work_ref!==workRef||value.expected_preference_revision!==null)invalid();
  return Object.freeze({action:'add_project_file',request_id:value.request_id,work_ref:value.work_ref,
   source_commit:value.source_commit,base_revision:value.base_revision,request_sha256:value.request_sha256,expected_preference_revision:null}) as Readonly<ProjectDraftFileLookup>;
 }catch{return invalid();}
}
export function serializeProjectDraftFileLookup(raw:unknown,workRef:string):string{
 return JSON.stringify(decodeProjectDraftFileLookup(raw,workRef));
}
export function parseProjectDraftFileLookup(raw:string,workRef:string):Readonly<ProjectDraftFileLookup>{
 try{
  // Fixed seven ASCII fields fit below this bound even at maximal work-ref
  // length. Exact round trip rejects duplicate keys and alternate spellings.
  if(typeof raw!=='string'||raw.length>1024)invalid();
  const value=decodeProjectDraftFileLookup(JSON.parse(raw),workRef);
  if(serializeProjectDraftFileLookup(value,workRef)!==raw)invalid();return value;
 }catch{return invalid();}
}
