import {expect,it} from 'vitest';
import {decodeProjectDraftFileLookup,serializeProjectDraftFileLookup,parseProjectDraftFileLookup} from './project-draft-file-lookup';
const work='WS:FILES';const lookup={action:'add_project_file',request_id:'mmos-project-file-add-'+'a'.repeat(40),work_ref:work,source_commit:'b'.repeat(40),base_revision:'c'.repeat(64),request_sha256:'d'.repeat(64),expected_preference_revision:null};
it('retains exactly the incumbent original lookup, no File, name, body, permission or new identity',()=>{
 const text=serializeProjectDraftFileLookup(lookup,work),value=parseProjectDraftFileLookup(text,work);
 expect(value).toEqual(lookup);expect(Object.isFrozen(value)).toBe(true);expect(Object.keys(value)).toHaveLength(7);
});
it.each([
 {payload:'private'}, {action:'set_project_communication_preference'}, {request_id:'mmos-project-create-'+'a'.repeat(40)},
 {work_ref:'WS:OTHER'}, {source_commit:'b'.repeat(39)}, {base_revision:'c'.repeat(40)}, {request_sha256:'d'.repeat(40)}, {expected_preference_revision:'e'.repeat(64)},
])('refuses an extra or substituted original operand %j',change=>{expect(()=>decodeProjectDraftFileLookup({...lookup,...change},work)).toThrow('PROJECT_DRAFT_FILE_LOOKUP_INVALID');});
it('refuses getters, symbols, duplicate JSON and noncanonical serialized fields',()=>{
 let called=false;const forged={...lookup};Object.defineProperty(forged,'request_sha256',{get(){called=true;return lookup.request_sha256;},enumerable:true});
 expect(()=>decodeProjectDraftFileLookup(forged,work)).toThrow();expect(called).toBe(false);
 expect(()=>decodeProjectDraftFileLookup({...lookup,[Symbol('extra')]:true},work)).toThrow();
 const raw=serializeProjectDraftFileLookup(lookup,work);
 expect(raw.startsWith('{')).toBe(true);
 const duplicateAction='{"action":"add_project_file",'+raw.slice(1);
 expect(()=>parseProjectDraftFileLookup(duplicateAction,work)).toThrow();
 expect(()=>parseProjectDraftFileLookup(' '+raw,work)).toThrow();expect(()=>parseProjectDraftFileLookup(raw,'WS:OTHER')).toThrow();
});
