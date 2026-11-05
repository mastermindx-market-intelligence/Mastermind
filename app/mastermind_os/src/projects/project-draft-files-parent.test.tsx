// @vitest-environment jsdom
import {act,cleanup,renderHook} from '@testing-library/react';
import {afterEach,expect,it} from 'vitest';
import {projectGoalDraftScope} from '../auth-recovery/project-goal-scope';
import {createNativeDraftRecoveryOwner} from '../auth-recovery/native-draft-owner';
import {useProjectJourneyState} from './useProjectJourneyState';
import {commitProjectJourneySelection,projectJourneyUrl,readProjectJourneyLocation} from './project-journey-location';
import {serializeProjectDraftFileLookup,type ProjectDraftFileLookup} from './project-draft-file-lookup';
import type {ProjectDraftFile} from './useProjectDraftFiles';
const cid='mmos-project-create-'+'a'.repeat(40),work='WS:FILE-ONE';
const selection={createRequestId:cid,workRef:work,planningOperationKey:null,jobId:null};
const lookup:ProjectDraftFileLookup={action:'add_project_file',request_id:'mmos-project-file-add-'+'b'.repeat(40),work_ref:work,source_commit:'c'.repeat(40),base_revision:'d'.repeat(64),request_sha256:'e'.repeat(64),expected_preference_revision:null};
afterEach(()=>{cleanup();delete window.MastermindMissionHost;});
async function setup(){
 let generation=1,epoch=1,signed=true,principal='f'.repeat(64);
 const owner=createNativeDraftRecoveryOwner({inspect:async()=>({schema:'mastermind.native_draft_continuity.v1',owner_instance:'1'.repeat(32),privacy_epoch:1,phase:'QUALIFIED',cause:'OWNER_QUALIFIED',principal_scope:principal,valid_until_ms:5000}),sourceGeneration:()=>generation,signedIn:()=>signed,now:()=>1000});
 const host={auth:{getState:()=>({status:signed?'signed_in':'signed_out',acquisition:signed})},invalidationGeneration:()=>generation,nativeDraftRecovery:owner} as Parameters<typeof useProjectJourneyState>[0]['host'];
 window.MastermindMissionHost=host as typeof window.MastermindMissionHost;
 history.replaceState(null,'','/os/?new_project=1');
 const h=renderHook(()=>useProjectJourneyState({host,authRevision:epoch,currentAuthRevision:()=>epoch}));
 const origin=await owner.capture('project-file-draft.v1:'+lookup.request_id);expect(origin).toBeTruthy();await owner.check(origin!);
 const file=new File(['literal private DATA'],'Context.md',{type:'text/markdown'});
 const row:ProjectDraftFile={privacyOwner:owner,origin:origin!,file,data:{display_name:'Context.md',media_type:'text/markdown',content_utf8:'literal private DATA'},requestId:lookup.request_id,request:null,savedRequestSha256:null};
 return {...h,host,row,setPrincipal:(p:string)=>{principal=p;},bump:()=>{generation++;epoch++;},expire:()=>{signed=false;},signIn:()=>{signed=true;}};
}
it('preserves exact File refs across own blank CREATE, Back and Options render; URL never contains private bytes',async()=>{
 const h=await setup();act(()=>h.result.current.onDraftFilesChange([h.row]));
 act(()=>h.result.current.onSelection(selection));expect(h.result.current.draftFiles[0].file).toBe(h.row.file);
 act(()=>h.result.current.hide());act(()=>h.result.current.open());h.rerender();
 expect(h.result.current.draftFiles[0]).toBe(h.row);expect(h.result.current.hasUnsentDraft()).toBe(true);
 expect(location.href).not.toContain('literal');expect(location.href).not.toContain('Context');
});
it('commits closed File original before callback, preserves same CREATE planning updates, and rejects foreign work',async()=>{
 const h=await setup();act(()=>h.result.current.onSelection(selection));
 act(()=>h.result.current.onOriginalFileLookupChange(lookup));expect(readProjectJourneyLocation(location.href).fileLookup).toEqual(lookup);
 act(()=>h.result.current.onSelection({...selection,planningOperationKey:'mmos-project-planning-'+'a'.repeat(40)}));
 expect(readProjectJourneyLocation(location.href).fileLookup).toEqual(lookup);
 expect(()=>h.result.current.onOriginalFileLookupChange({...lookup,work_ref:'WS:FOREIGN'})).toThrow();
 const order:string[]=[];commitProjectJourneySelection(location.href,selection,{replaceState:()=>order.push('replace')},()=>order.push('callback'),lookup);expect(order).toEqual(['replace','callback']);
});
it('external CREATE restore masks original File refs; no-render Host/gen withdrawal refuses handoff',async()=>{
 const h=await setup();act(()=>h.result.current.onDraftFilesChange([h.row]));act(()=>h.result.current.onSelection(selection));
 history.replaceState(null,'',projectJourneyUrl(location.href,{...selection,createRequestId:'mmos-project-create-'+'d'.repeat(40)}));act(()=>h.result.current.restoreLocation());
 expect(h.result.current.draftFiles).toEqual([]);expect(h.result.current.filesHeld).toBe(true);
 const before=h.result.current;window.MastermindMissionHost={} as typeof window.MastermindMissionHost;act(()=>before.onDraftFilesChange([]));expect(h.result.current.filesHeld).toBe(true);
 window.MastermindMissionHost=h.host as typeof window.MastermindMissionHost;h.bump();expect(()=>before.onOriginalFileLookupChange(lookup)).toThrow();
});
it('passive auth masks before reacquisition and genuine foreign-principal proof clears rather than adopts old File',async()=>{
 const h=await setup();act(()=>h.result.current.onDraftFilesChange([h.row]));act(()=>h.result.current.onSelection(selection));
 h.expire();act(()=>h.result.current.invalidateFilesAuth(true));expect(h.result.current.draftFiles).toEqual([]);expect(h.result.current.filesHeld).toBe(true);
 h.signIn();h.bump();h.setPrincipal('a'.repeat(64));h.rerender();
 let restored=true;await act(async()=>{restored=await h.result.current.checkRetainedFileDraft();});
 expect(restored).toBe(false);expect(h.result.current.draftFiles).toEqual([]);expect(h.result.current.filesHeld).toBe(false);
});
it.each(['duplicate','orphan','work','extra','body','alternate'] as const)('closes malformed File lookup route: %s',kind=>{
 const url=new URL(projectJourneyUrl('http://localhost/os/',selection,lookup));
 if(kind==='duplicate')url.searchParams.append('project_file_original',url.searchParams.get('project_file_original')!);
 if(kind==='orphan')url.searchParams.delete('project_create_work_ref');
 if(kind==='work')url.searchParams.set('project_file_original',JSON.stringify({...lookup,work_ref:'WS:FOREIGN'}));
 if(kind==='extra'||kind==='body')url.searchParams.set('project_file_original',JSON.stringify({...lookup,[kind==='extra'?'unknown':'file']:'literal private DATA'}));
 if(kind==='alternate')url.searchParams.set('project_file_original',JSON.stringify(lookup,null,2));
 expect(readProjectJourneyLocation(url)).toEqual({valid:false,open:false,selection:null});
});
it('keeps absent File URL exact and rejects File without selection without any replace',()=>{
 const url=projectJourneyUrl('http://localhost/os/?secret=never',selection);expect(url).not.toContain('file');
 const read=readProjectJourneyLocation(url);expect(Object.keys(read)).toEqual(['valid','open','selection']);
 let called=false;expect(()=>commitProjectJourneySelection(url,null,{replaceState:()=>{called=true;}},()=>{},lookup)).toThrow();expect(called).toBe(false);
 expect(serializeProjectDraftFileLookup(lookup,work)).not.toContain('content_utf8');
});

it('same-original native goal return retains only safe File lookup; File body still requires its own original proof',async()=>{
 const h=await setup();act(()=>h.result.current.onDraftFilesChange([h.row]));act(()=>h.result.current.onSelection(selection));act(()=>h.result.current.onGoalChange('private goal'));act(()=>h.result.current.onOriginalFileLookupChange(lookup));
 const owner=h.host!.nativeDraftRecovery!,goalOrigin=await owner.capture(projectGoalDraftScope(selection)!);await owner.check(goalOrigin!);
 h.expire();act(()=>h.result.current.invalidateAuth(true));h.signIn();h.bump();h.rerender();await owner.check(goalOrigin!);
 let returned=false;act(()=>{returned=h.result.current.returnToNativeRetainedGoal(goalOrigin!,owner);});expect(returned).toBe(true);
 expect(readProjectJourneyLocation(location.href).fileLookup).toEqual(lookup);expect(h.result.current.draftFiles).toEqual([]);expect(h.result.current.filesHeld).toBe(true);
 let files=false;await act(async()=>{files=await h.result.current.checkRetainedFileDraft();});expect(files).toBe(true);expect(h.result.current.draftFiles[0].file).toBe(h.row.file);
 const foreign={...selection,createRequestId:'mmos-project-create-'+'c'.repeat(40)};history.replaceState(null,'',projectJourneyUrl(location.href,foreign));act(()=>h.result.current.restoreLocation());expect(h.result.current.originalFileLookup).toBeNull();expect(h.result.current.draftFiles).toEqual([]);
});
