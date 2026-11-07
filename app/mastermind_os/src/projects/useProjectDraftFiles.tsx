import {useEffect,useId,useRef,useState,type ReactNode} from 'react';
import type {MissionHost} from '../host';
import type {PendingPointerStore} from '../orchestration/operation-controller';
import type {ProjectDraftFileLookup} from './project-draft-file-lookup';
export type {ProjectDraftFileLookup} from './project-draft-file-lookup';
import {useProjectKnowledgeWorkspace} from '../knowledge/useProjectKnowledgeWorkspace';
import {validate_catalogue,type KnowledgeCatalogueResult,type KnowledgeLibrarySourceOwner} from '../knowledge/library/knowledge-library-contract';
import {buildProjectFileRequest,readStagedProjectFile,publicRequestSha256,type ProjectFileAddRequest,type ProjectFileAddRequestFile,type ProjectKnowledgeSourceContext} from '../knowledge/library/project-knowledge-requests';
import {nativeDraftReturnQualified,type NativeDraftOrigin,type NativeDraftRecoveryOwner} from '../auth-recovery/native-draft-owner';
import type {ProjectSourceStatus} from '../knowledge/library/project-source-operation';

/** Ephemeral actual browser File and literal DATA. Never a grant or upload.
 * The App retains this only for the same draft/actor and clears it on auth loss. */
export interface ProjectDraftFile {
 readonly privacyOwner:NativeDraftRecoveryOwner;
 readonly origin:NativeDraftOrigin;
 readonly file:File;
 readonly data:Readonly<ProjectFileAddRequestFile>;
 readonly requestId:string;
 readonly request:ProjectFileAddRequest|null;
 readonly savedRequestSha256:string|null;
}
export interface ProjectDraftFilesProps {
 locale:'en'|'zh-CN';host:MissionHost|null;store:PendingPointerStore;
 isCurrent:()=>boolean;interactionBlocked?:()=>boolean;workRef:string|null;created:boolean;planningStarted:boolean;
 files:readonly ProjectDraftFile[];onFilesChange:(value:readonly ProjectDraftFile[])=>void;
 original:ProjectDraftFileLookup|null;
 /** App commits safe original lookup synchronously BEFORE server prepare. */
 onOriginalChange:(value:ProjectDraftFileLookup|null)=>void;
}
function observedFileMembers(value:KnowledgeCatalogueResult|null,original:ProjectDraftFileLookup|null){
 const event=value?.dataObservation?.source_operation;
 if(!value?.catalogue||!original||event?.selection.action!=='add_project_file'||
  event.selection.request_id!==original.request_id||event.selection.work_ref!==original.work_ref||
  event.request_sha256!==original.request_sha256)return [];
 // The incumbent compiler records its RECIPE fingerprint in file origin.
 // The public operation's request digest remains a separate exact join.
 return value.catalogue.files.filter(file=>file.state==='READABLE'&&
  file.origin.requestSha256===event.recipe_fingerprint_sha256&&
  event.sources.some(source=>source.path===file.path&&source.content_sha256===file.contentSha256));
}
const key=/^mmos-project-file-add-[0-9a-f]{40}$/;
function originalId(){const raw=new Uint8Array(20);crypto.getRandomValues(raw);return 'mmos-project-file-add-'+Array.from(raw,v=>v.toString(16).padStart(2,'0')).join('');}
function sourceOf(catalogue:KnowledgeCatalogueResult):ProjectKnowledgeSourceContext|null {
 const c=catalogue.catalogue;return c?{workRef:c.workRef,sourceCommit:c.sourceCommit,baseRevision:c.workstreamSha256}:null;
}
/** One original File publisher, composed from the incumbent Knowledge owner.
 * Selecting never sends. Prepare/Review/Publish/Check are distinct gestures.
 * No File/body enters the safe URL or durable pending-pointer store. */
export function useProjectDraftFiles(props:ProjectDraftFilesProps):{
 control:ReactNode;panel:ReactNode;blocksPlanning:()=>boolean;currentPlanningCommit:()=>string|null;isBusy:()=>boolean;
} {
 const live=useRef(props);live.current=props;
 const inputId=useId(), input=useRef<HTMLInputElement>(null);
 const mounted=useRef(true), ticket=useRef<object|null>(null);
 const origin=useRef<{bound:object;owner:NativeDraftRecoveryOwner;value:NativeDraftOrigin;requestId:string}|null>(null),privateBlocked=useRef(false);
 const busyRef=useRef(false);
 const [busy,setBusy]=useState(false),[notice,setNotice]=useState<string|null>(null);
 const [catalogue,setCatalogue]=useState<KnowledgeCatalogueResult|null>(null);
 const fileAccess=useRef<{ticket:object;available:boolean}|null>(null);
 const [originalStatus,setOriginalStatus]=useState<ProjectSourceStatus|null>(null);
 const rawRead=props.host?.readProjectKnowledgeCatalogue;
 const generation=props.host?.invalidationGeneration?.()??null;
 const scope=JSON.stringify([props.workRef,generation,props.host?.auth?.getState().status]);
 const bound=useRef({host:props.host,generation,scope});
 if(bound.current.host!==props.host||bound.current.generation!==generation||bound.current.scope!==scope){
   bound.current={host:props.host,generation,scope};ticket.current=null;
 }
 const renderBinding=bound.current;
 function current(){try{return bound.current===renderBinding&&mounted.current&&live.current.isCurrent()===true&&live.current.host===bound.current.host&&
   bound.current.generation!==null&&live.current.host?.invalidationGeneration?.()===bound.current.generation&&
   live.current.host?.auth?.getState().status==='signed_in'&&live.current.host.auth.getState().acquisition===true;}catch{return false;}}
 const publisher=useProjectKnowledgeWorkspace({workRef:props.workRef,hostGeneration:generation,
   authGeneration:generation??-1,canRead:current,readContext:props.host?.readSourceOperationContext,
   transport:props.host?.sourceOperations,store:props.store});
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;ticket.current=null;};},[]);
 const text=(en:string,zh:string)=>props.locale==='zh-CN'?zh:en;
 const recovery=()=>{try{return (live.current.host as (MissionHost&{nativeDraftRecovery?:NativeDraftRecoveryOwner})|null)?.nativeDraftRecovery??null;}catch{return null;}};
 const scopeFor=(requestId:string)=>{if(!key.test(requestId))throw Error('SOURCE_CHANGED');return 'project-file-draft.v1:'+requestId;};
 type FileOrigin=Pick<ProjectDraftFile,'privacyOwner'|'origin'|'requestId'>;
 const returnable=(row:FileOrigin)=>current()&&recovery()===row.privacyOwner&&nativeDraftReturnQualified(row.privacyOwner,row.origin,scopeFor(row.requestId));
 async function checkPrivate(row:FileOrigin){
   if(!current()||recovery()!==row.privacyOwner)throw Error('SOURCE_CHANGED');
   const result=await row.privacyOwner.check(row.origin);
   if(!current()||recovery()!==row.privacyOwner)throw Error('SOURCE_CHANGED');
   if(result==='CLEARED')live.current.onFilesChange(Object.freeze(live.current.files.filter(value=>value.origin!==row.origin)));
   if(result!=='RETURNABLE'||!returnable(row)){privateBlocked.current=true;throw Error('SOURCE_CHANGED');}
 }
 async function checkDraftPrivacy(){await guardCall(async()=>{for(const row of live.current.files)await checkPrivate(row);privateBlocked.current=false;});}

 const replace=(value:ProjectDraftFile)=>{
   if(!current())throw Error('SOURCE_CHANGED');
   live.current.onFilesChange(Object.freeze(live.current.files.map(row=>row.requestId===value.requestId?Object.freeze(value):row)));
 };
 const actualSnapshot=catalogue&&ticket.current?sourceOf(catalogue):null;
 const phase=publisher.phase;
 const status=publisher.status??originalStatus;
 const matchedStatus=status&&props.original&&status.selection.request_id===props.original.request_id&&status.selection.work_ref===props.original.work_ref?status:null;
 const confirmed=Boolean(current()&&ticket.current&&observedFileMembers(catalogue,props.original).length);
 const next=props.original&&!confirmed?props.files.find(row=>row.requestId===props.original!.request_id):props.files.find(row=>row.savedRequestSha256===null);
 async function guardCall(call:()=>Promise<void>){
   if(busyRef.current||live.current.interactionBlocked?.()===true||!current())return;busyRef.current=true;setBusy(true);setNotice(null);
   try{await call();}catch{if(current())setNotice(text('The original file request is unavailable. Keep it for checking.','原始文件请求暂不可用，请保留并查询。'));}
   finally{busyRef.current=false;if(mounted.current)setBusy(false);}
 }
 async function openChooser(){
   if(busyRef.current||live.current.interactionBlocked?.()===true||!current())return;
   const ready=origin.current;
   if(ready?.bound===renderBinding&&current()&&!privateBlocked.current&&recovery()===ready.owner&&nativeDraftReturnQualified(ready.owner,ready.value,scopeFor(ready.requestId))){input.current?.click();return;}
   await guardCall(async()=>{
     // Actual native/signed-Workspace issuer BEFORE choosing/reading private
     // bytes. No public auth DTO or later principal may adopt old File DATA.
     const owner=recovery();if(!owner)throw Error('SOURCE_CHANGED');
     const requestId=live.current.original&&!confirmed?live.current.original.request_id:originalId();
     const value=await owner.capture(scopeFor(requestId));
     if(!current()||recovery()!==owner||!value)throw Error('SOURCE_CHANGED');
     if(await owner.check(value)!=='RETURNABLE'||!current()||recovery()!==owner||!nativeDraftReturnQualified(owner,value,scopeFor(requestId)))throw Error('SOURCE_CHANGED');
     if(live.current.files.some(row=>row.privacyOwner!==owner||row.origin.principalScope!==value.principalScope||row.origin.ownerInstance!==value.ownerInstance||row.origin.privacyEpoch!==value.privacyEpoch)){
       owner.discard(value);privateBlocked.current=true;throw Error('SOURCE_CHANGED');
     }
     origin.current={bound:renderBinding,owner,value,requestId};
     setNotice(text('File selection is ready. Choose Add files to select a file.','文件选择已就绪，请点击“添加文件”选择文件。'));
     if(navigator.userActivation?.isActive===true)input.current?.click();
   });
 }
 async function refresh(){await guardCall(async()=>{
   const p=live.current,read=p.host?.readProjectKnowledgeCatalogue,work=p.workRef;
   if(!p.created||!read||!work)throw Error('SOURCE_CHANGED');
   const started=bound.current, token={};ticket.current=null;
   const raw=await read({work_ref:work,signal:new AbortController().signal});
   if(!current()||bound.current!==started||live.current.host?.readProjectKnowledgeCatalogue!==read)throw Error('SOURCE_CHANGED');
   const value=validate_catalogue(raw,work);
   const snapshot=sourceOf(value);if(!snapshot||!value.codeContext)throw Error('SOURCE_CHANGED');
   ticket.current=token;
   const sourceOwner:KnowledgeLibrarySourceOwner=Object.freeze({
     codeContext:()=>current()&&ticket.current===token?value.codeContext??null:null,
     current:(selected:ProjectKnowledgeSourceContext)=>{
       if(!current()||ticket.current!==token||selected.workRef!==snapshot.workRef||selected.sourceCommit!==snapshot.sourceCommit||selected.baseRevision!==snapshot.baseRevision)throw Error('SOURCE_CHANGED');
       return {...snapshot};
     }});
   publisher.registerSourceOwner(sourceOwner);setCatalogue(value);
   const actions=await publisher.readActions({...snapshot,signal:new AbortController().signal});
   fileAccess.current={ticket:token,available:actions.actions.add_files==='AVAILABLE'};
   if(!current()||ticket.current!==token)throw Error('SOURCE_CHANGED');
   const original=live.current.original;
   if(original){
     if(observedFileMembers(value,original).length){
       // Current READ/latest-DATA and the actual publication Event qualify
       // membership. A later File-WRITE revocation is not a read revocation.
       for(const file of live.current.files.filter(file=>file.requestId===original.request_id))file.privacyOwner.discard(file.origin);
       live.current.onFilesChange(Object.freeze(live.current.files.filter(file=>file.requestId!==original.request_id)));
       // Keep this safe latest lookup through reload; private bytes can vanish.
     }
   }
 });}
 async function choose(files:FileList|null){await guardCall(async()=>{
   const issued=origin.current;
   if(live.current.planningStarted||files?.length!==1||privateBlocked.current||issued?.bound!==renderBinding)throw Error('SOURCE_CHANGED');
   const started=bound.current, selected=Array.from(files), additions:ProjectDraftFile[]=[];
   for(const file of selected){
     const nativeRow:FileOrigin={privacyOwner:issued.owner,origin:issued.value,requestId:issued.requestId};
     await checkPrivate(nativeRow);
     const data=await readStagedProjectFile(file);
     if(!current()||bound.current!==started||origin.current!==issued||!nativeDraftReturnQualified(issued.owner,issued.value,scopeFor(issued.requestId)))throw Error('SOURCE_CHANGED');
     const original=live.current.original;
     if(original&&!confirmed){
       // Reload can lose private bytes. Only exact re-selection may restore
       // them; an unknown original never becomes a fresh request or new key.
       if(selected.length!==1)throw Error('SOURCE_CHANGED');
       const request:ProjectFileAddRequest={schema:'mastermind.project_file_add_request.v1',request_id:original.request_id,work_ref:original.work_ref,source_commit:original.source_commit,base_revision:original.base_revision,file:data};
       if(await publicRequestSha256(request)!==original.request_sha256||!current())throw Error('SOURCE_CHANGED');
       additions.push(Object.freeze({privacyOwner:issued.owner,origin:issued.value,file,data,requestId:original.request_id,request,savedRequestSha256:null}));
     }else additions.push(Object.freeze({privacyOwner:issued.owner,origin:issued.value,file,data,requestId:issued.requestId,request:null,savedRequestSha256:null}));
   }
   live.current.onFilesChange(Object.freeze([...live.current.files.filter(row=>!additions.some(add=>add.requestId===row.requestId)),...additions]));
   origin.current=null;
 });if(input.current)input.current.value='';}
 async function prepare(restore=false){await guardCall(async()=>{
   const p=live.current,row=p.original&&!confirmed?p.files.find(file=>file.requestId===p.original!.request_id):p.files.find(file=>file.savedRequestSha256===null);
   const snapshot=catalogue&&ticket.current?sourceOf(catalogue):null;
   if(!p.created||p.planningStarted||!row||!snapshot||!key.test(row.requestId)||fileAccess.current?.ticket!==ticket.current||fileAccess.current.available!==true)throw Error('SOURCE_CHANGED');
   if(p.original&&!confirmed&&(!restore||matchedStatus?.receipt?.kind!=='INTENT'||matchedStatus.disposition!=='unknown'))throw Error('SOURCE_CHANGED');
   await checkPrivate(row);
   const request=row.request??await buildProjectFileRequest(snapshot,row.requestId,row.file,null,publisher.currentSource);
   // Preserve the staged body exactly; browser selection is never called saved.
   if(JSON.stringify(request.file)!==JSON.stringify(row.data)||!current())throw Error('SOURCE_CHANGED');
   const digest=await publicRequestSha256(request);
   if(!current()||!returnable(row))throw Error('SOURCE_CHANGED');
   const lookup:ProjectDraftFileLookup=Object.freeze({action:'add_project_file',request_id:request.request_id,work_ref:request.work_ref,
     source_commit:request.source_commit,base_revision:request.base_revision,request_sha256:digest,expected_preference_revision:null});
   if(p.original&&!confirmed&&Object.keys(lookup).some(field=>p.original![field as keyof ProjectDraftFileLookup]!==lookup[field as keyof ProjectDraftFileLookup]))throw Error('SOURCE_CHANGED');
   replace({...row,request});
   p.onOriginalChange(lookup); // synchronous safe URL commit, may refuse/throw
   if(!current()||!returnable(row))throw Error('SOURCE_CHANGED');
   await publisher.prepare(request);
 });}
 async function publishFile(){await guardCall(async()=>{
   const prepared=publisher.prepared,row=live.current.files.find(value=>value.requestId===prepared?.request.request_id);
   if(!row||!prepared)throw Error('SOURCE_CHANGED');await checkPrivate(row);
   if(!returnable(row)||publisher.prepared!==prepared)throw Error('SOURCE_CHANGED');
   await publisher.publish();
 });}
 async function inspect(){await guardCall(async()=>{
   const original=live.current.original;if(!original)throw Error('SOURCE_CHANGED');
   // Controller recovery can settle only an existing durable publication
   // pointer. No pointer means this remains the exact pre-publication read.
   await publisher.checkOriginal();
   if(!current())throw Error('SOURCE_CHANGED');
   setOriginalStatus(await publisher.inspectOriginal(original));
 });}
 const blocksPlanning=()=>{if(live.current.files.length===0&&live.current.original===null)return false;return !current()||!confirmed||live.current.files.some(row=>!returnable(row)||row.savedRequestSha256===null||!catalogue?.catalogue?.files.some(file=>file.state==='READABLE'&&file.origin.requestSha256===row.savedRequestSha256));};
 const currentPlanningCommit=()=>!blocksPlanning()&&confirmed?catalogue?.catalogue?.sourceCommit??null:null;
 const canChoose=current()&&recovery()!==null&&!props.planningStarted&&!busy&&!privateBlocked.current;
 const control=<><button type="button" disabled={!canChoose} onClick={()=>void openChooser()}>{text('Add files','添加文件')}</button>
   <input ref={input} id={inputId} aria-label={text('Choose project files','选择项目文件')} type="file" accept=".txt,.md"
     hidden disabled={!canChoose||origin.current?.bound!==renderBinding} onChange={event=>void choose(event.target.files)}/></>;
 const panel=!current()?null:recovery()===null&&props.original===null?<p>{text('File selection is unavailable in this client.','此客户端暂时无法选择文件。')}</p>:(privateBlocked.current||props.files.some(row=>!returnable(row)))?<div><p role="status">{text('The file draft is held for its original signed-in identity.','文件草稿已为原始登录身份保留。')}</p><button type="button" disabled={busy} onClick={()=>void checkDraftPrivacy()}>{text('Check file draft access','查询文件草稿访问状态')}</button></div>:(props.files.length===0&&!props.original)?(notice?<p role="status">{notice}</p>:null):<section className="mm-project-draft-files" aria-label={text('Project files','项目文件')}>
   {props.files.map(row=><div key={row.requestId}><strong>{row.data.display_name}</strong>{' · '}
     <span>{row.savedRequestSha256?text('Added to the project','已添加到项目'):text('Selected file · Not added to the project yet','已选择文件 · 尚未添加到项目')}</span>
     {!row.request&&current()&&!props.planningStarted&&<button type="button" disabled={busy} onClick={()=>{if(!busyRef.current&&live.current.interactionBlocked?.()!==true&&returnable(row))live.current.onFilesChange(Object.freeze(live.current.files.filter(file=>file!==row)));}}>{text('Remove','移除')}</button>}</div>)}
   {confirmed&&observedFileMembers(catalogue,props.original).map(file=><p key={file.sourceRef}><strong>{file.displayName}</strong>{' · '}{text('Added to the project','已添加到项目')}</p>)}
   {props.original&&!next&&!confirmed&&<p>{text('The original file request is retained. Reselect the same file only if its preview must be restored.','原始文件请求已保留。仅当需要恢复预览时，请重新选择同一文件。')}</p>}
   {(props.files.length>0||props.original)&&<>
     {!props.created?<p>{text('Create the project first. Adding selected files is a separate action.','请先创建项目；添加所选文件是独立操作。')}</p>:<>
       <button type="button" disabled={busy||!current()} onClick={()=>void refresh()}>{text('Check current file access','查询当前文件权限')}</button>
       {actualSnapshot&&fileAccess.current?.ticket===ticket.current&&fileAccess.current.available===false&&<p>{text('File publishing is unavailable for this project. Selected files have not been added.','此项目暂时无法发布文件；所选文件尚未添加。')}</p>}
       {next&&(!props.original||confirmed)&&<button type="button" disabled={busy||!actualSnapshot||fileAccess.current?.ticket!==ticket.current||fileAccess.current?.available!==true||!current()} onClick={()=>void prepare()}>{text('Prepare file preview','准备文件预览')}</button>}
       {props.original&&<button type="button" disabled={busy||!current()} onClick={()=>void inspect()}>{text('Check original file request','查询原始文件请求')}</button>}
       {props.original&&next&&matchedStatus?.receipt?.kind==='INTENT'&&matchedStatus.disposition==='unknown'&&phase!=='prepared'&&<button type="button" disabled={busy||!actualSnapshot||fileAccess.current?.ticket!==ticket.current||fileAccess.current?.available!==true||!current()} onClick={()=>void prepare(true)}>{text('Restore original file preview','恢复原始文件预览')}</button>}
       {publisher.prepared&&!confirmed&&<div><p>{text('File preview ready. Adding this file is separate from project creation and planning.','文件预览已准备好；添加文件与创建项目、规划相互独立。')}</p>
         <strong>{publisher.prepared.request.schema==='mastermind.project_file_add_request.v1'?publisher.prepared.request.file.display_name:''}</strong>
         <button type="button" className="primary" disabled={busy||!publisher.canPublish||!current()} onClick={()=>void publishFile()}>{text('Add file to project','将文件添加到项目')}</button></div>}
       {props.original&&!confirmed&&<p>{text('File publication is not confirmed here. Check the original request, then current files. Planning waits for all selected files.','此处尚未确认文件发布。请查询原始请求及当前文件；所有所选文件就绪后才能规划。')}</p>}
     </>}
   </>}
   {notice&&<p role="status">{notice}</p>}
 </section>;
 return {control,panel,blocksPlanning,currentPlanningCommit,isBusy:()=>busyRef.current};
}
