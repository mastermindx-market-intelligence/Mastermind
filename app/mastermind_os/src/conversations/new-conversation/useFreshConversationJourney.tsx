import {useEffect,useLayoutEffect,useMemo,useRef,useState,type ReactNode} from "react";
import type {OperationPointer,OperationState,OwnerContext} from "../../orchestration/operation-controller";
import {NewConversationDraft} from "./NewConversationDraft";
import {NewConversationOutcome} from "./NewConversationOutcome";
import {decodeFreshConversationResult,decodeFreshConversationInitialResult,validateFreshConversationRequest,type FreshConversationData,type FreshConversationPayload,type FreshConversationLocator} from "./fresh-conversation";
import {sameConversationOwner,type ConversationPreviewRequest,type ConversationRequestSelection,type ConversationProjectChoice,type FreshConversationBinding} from "./fresh-conversation-binding";
import {parseFreshConversationTarget} from "../../orchestration/fresh-conversation-target";
import "./new-conversation-journey.css";

export interface FreshConversationInitialRead {
  readonly selection:ConversationRequestSelection;
  readonly result:FreshConversationPayload;
  readonly locator:FreshConversationLocator;
  /** Exact current readonly body/owner witness, never continuation authority. */
  current():boolean;
}
export interface FreshConversationJourneyProps {
  locale:"en"|"zh-CN";
  /** This hook stays mounted at App lifetime; route Back only hides its panel. */
  active:boolean;
  binding:FreshConversationBinding|null;
  authGeneration:number;
  host:object|undefined;
  projects:readonly ConversationProjectChoice[];
  projectsState:"reading"|"available"|"unavailable";
  isProjectCurrent:(workRef:string)=>boolean;
  /** Opaque identity of the same acquired list body. Never a grant. */
  projectReadIdentity?:unknown;
  /** Controlled ephemeral first-message text; never the current Window notes. */
  workRef:string|null;
  message:string;
  draftOwner:OwnerContext|null;
  onWorkRefChange:(value:string|null)=>void;
  onMessageChange:(value:string)=>void;
  /** Pure App lookup selection, synchronously before preview/read await. */
  onOriginalKeySelected:(selection:ConversationRequestSelection)=>void;
  /** Lookup DATA discovered on App initialization, never authority. The
   * parent issues this snapshot under its verified current Executive owner.
   * Read once per actual owner/host scope, after the pending store wins. */
  originalLookup?:{selection:ConversationRequestSelection;owner:OwnerContext}|null;
  onBack:()=>void;
  /** Pure optional mount of separately qualified attended owner controls. */
  renderContinuation?:(read:FreshConversationInitialRead)=>ReactNode;
}
type Original=ConversationRequestSelection&{message?:string};
type Preview={request:ConversationPreviewRequest;data:FreshConversationData;projectTitle:string|null;projectReadIdentity?:unknown};
type View={scope:number;phase:"draft"|"preview"|"outcome";preview:Preview|null;original:Original|null;
  projectTitle:string|null;data:FreshConversationData|null;operation:OperationState|null;
  retained:OperationPointer|null;lookup:boolean;other:boolean;discovering:boolean;busy:"preview"|"operation"|"read"|null;
  opened:boolean;error:"unavailable"|"invalid"|"changed"|null};
const blank=(scope:number):View=>({scope,phase:"draft",preview:null,original:null,projectTitle:null,data:null,
 operation:null,retained:null,lookup:false,other:false,discovering:true,busy:null,opened:false,error:null});
const ownerOf=(binding:FreshConversationBinding|null):OwnerContext|null=>{
 try{const value=binding?.context();return value?{...value}:null;}catch{return null;}
};
function selectionOf(pointer:OperationPointer|null):ConversationRequestSelection|null{
 if(!pointer?.targetKey)return null;
 if(pointer.kind==="conversation_consume"||pointer.kind==="conversation_turn"){
  const key=pointer.kind==="conversation_consume"?/^mmos-conversation-consume-[0-9a-f]{40}$/:/^mmos-conversation-turn-[0-9a-f]{40}$/;
  if(typeof pointer.operationKey!=="string"||!key.test(pointer.operationKey))return null;
  const original=parseFreshConversationTarget(pointer.targetKey);
  return original&&"operation_key"in original?{work_ref:original.work_ref,operation_key:original.operation_key}:null;
 }
 if(pointer.kind!=="conversation_create")return null;
 return validateFreshConversationRequest({work_ref:pointer.targetKey,operation_key:pointer.operationKey},"status")
  ?{work_ref:pointer.targetKey,operation_key:pointer.operationKey}:null;
}
const sameSelection=(a:ConversationRequestSelection,b:ConversationRequestSelection)=>a.work_ref===b.work_ref&&a.operation_key===b.operation_key;
const canOpen=(data:FreshConversationData|null)=>!!data?.locator&&(
 data.state==="CREATED"&&data.session!==null||data.state==="SETTLED");

/** Presentation reconciliation over the incumbent controller/store. No new
 * operation lifecycle, persistent payload, session registry, polling or mount dispatch. */
export function useFreshConversationJourney(props:FreshConversationJourneyProps){
 const actualOwner=ownerOf(props.binding);
 const boundary=useRef({binding:props.binding,owner:actualOwner,auth:props.authGeneration,host:props.host,scope:0});
 if(boundary.current.binding!==props.binding||boundary.current.auth!==props.authGeneration||boundary.current.host!==props.host||
  (boundary.current.owner!==null||actualOwner!==null)&&!sameConversationOwner(boundary.current.owner,actualOwner))
  boundary.current={binding:props.binding,owner:actualOwner,auth:props.authGeneration,host:props.host,scope:boundary.current.scope+1};
 const scope=boundary.current.scope;
 const [stored,setStored]=useState<View>(()=>blank(scope));
 const view=stored.scope===scope?stored:blank(scope);
 const latest=useRef(props);latest.current=props;
 const current=useRef(view);current.current=view;
 const root=useRef<HTMLDivElement>(null),ticket=useRef(0),readAbort=useRef<AbortController|null>(null);
 const committed=useRef({scope,binding:props.binding});
 const focus=useRef<{selector:string;from:Element|null}|null>(null);
 function patch(change:Partial<View>){const old=current.current;if(old.scope!==scope)return;
  const next={...old,...change};current.current=next;setStored(next);}
 function capture(){const binding=latest.current.binding,owner=ownerOf(binding);
  return binding&&owner?{binding,owner,scope:boundary.current.scope,auth:latest.current.authGeneration,host:latest.current.host}:null;}
 type Capture=NonNullable<ReturnType<typeof capture>>;
 function live(c:Capture){return boundary.current.scope===c.scope&&latest.current.binding===c.binding&&
  latest.current.authGeneration===c.auth&&latest.current.host===c.host&&sameConversationOwner(c.owner,ownerOf(c.binding));}
 function projectCurrent(workRef:string){try{return latest.current.projectsState==="available"&&latest.current.isProjectCurrent(workRef)===true;}catch{return false;}}
 function gestureFocus(selector:string,from:Element|null=document.activeElement){focus.current={selector,from};}
 useLayoutEffect(()=>{
  if(committed.current.scope!==scope){committed.current.binding?.controller.invalidate();
   readAbort.current?.abort();ticket.current++;focus.current=null;committed.current={scope,binding:props.binding};}
 },[scope,props.binding]);
 useLayoutEffect(()=>{
  const requested=focus.current;if(!requested||!props.active)return;
  const target=root.current?.querySelector<HTMLElement>(requested.selector);if(!target)return;
  focus.current=null;
  if(document.activeElement!==requested.from&&!(document.activeElement===document.body&&!requested.from?.isConnected))return;
  if(!target.matches("button,input,select,textarea"))target.tabIndex=-1;
  target.focus();target.scrollIntoView?.({block:"nearest"});
 });
 useEffect(()=>{
  const c=capture();if(!c){patch({discovering:false});return;}
  let valid=true;
  Promise.resolve().then(()=>c.binding.store.read(c.owner.principalScope)).then(pointer=>{
   if(!valid||!live(c))return;
   const pending=selectionOf(pointer),supplied=latest.current.originalLookup;
   const lookup=!pointer&&supplied&&sameConversationOwner(supplied.owner,c.owner)
    ?validateFreshConversationRequest(supplied.selection,"status"):null;
   const original=pending??(lookup?{work_ref:lookup.work_ref,operation_key:lookup.operation_key}:null);
   patch({discovering:false,retained:pointer,lookup:!!lookup,other:!!pointer&&!pending,
    original,phase:pointer||lookup?"outcome":"draft",operation:null});
  },()=>{if(valid&&live(c))patch({discovering:false,error:"unavailable",other:true});});
  return()=>{valid=false;};
 },[scope]);
 useEffect(()=>()=>{readAbort.current?.abort();committed.current.binding?.controller.invalidate();},[]);

 async function readOriginal(c:Capture,original:Original){
  const raw=await c.binding.readOriginal({work_ref:original.work_ref,operation_key:original.operation_key},readAbort.current!.signal);
  if(!live(c)||readAbort.current?.signal.aborted)return null;
  const decoded=decodeFreshConversationResult(raw,"read",original);
  if(!decoded?.ok||!decoded.data)return null;
  const data=decoded.data;
  if(data.result!==null){
   if(!data.locator)return null;
   const result=decodeFreshConversationInitialResult(data.result,data.locator);
   if(!result)return null;
   return {...data,result};
  }
  return data;
 }
 async function preview(){
  if(current.current.busy||current.current.discovering||current.current.retained||current.current.other)return;
  const origin=document.activeElement,c=capture(),p=latest.current;
  if(!c||!p.workRef||!projectCurrent(p.workRef)||!sameConversationOwner(p.draftOwner,c.owner)){patch({error:"unavailable"});return;}
  const syntax=validateFreshConversationRequest({work_ref:p.workRef,operation_key:"syntax-check",message:p.message},"preview");
  if(!syntax){patch({error:"invalid"});return;}
  const previous=current.current.original;
  patch({busy:"preview",error:null,preview:null});
  const id=++ticket.current;readAbort.current?.abort();readAbort.current=new AbortController();
  try{
   const raw=previous?{work_ref:p.workRef,operation_key:previous.operation_key,message:p.message}:c.binding.makePreviewRequest(p.workRef,p.message);
   const checked=validateFreshConversationRequest(raw,"preview");
   if(!checked||!("message"in checked)){patch({busy:null,error:"unavailable"});return;}
   const request:ConversationPreviewRequest={work_ref:checked.work_ref,operation_key:checked.operation_key,message:checked.message};
   // Select the ordinary original key before any preview await; no effect or reservation.
   latest.current.onOriginalKeySelected({work_ref:request.work_ref,operation_key:request.operation_key});
   patch({original:request});
   if(!live(c)||!projectCurrent(request.work_ref))return;
   const rawResult=await c.binding.preview(request,readAbort.current.signal);
   if(!live(c)||ticket.current!==id||readAbort.current.signal.aborted)return;
   if(latest.current.workRef!==request.work_ref||latest.current.message!==request.message||latest.current.projectReadIdentity!==p.projectReadIdentity||!projectCurrent(request.work_ref)){
    patch({busy:null,error:"changed"});return;}
   const decoded=decodeFreshConversationResult(rawResult,"preview",request);
   if(!decoded?.ok||!decoded.data?.preview){patch({busy:null,error:"unavailable"});return;}
   gestureFocus(".new-conversation-preview h1",origin);
   patch({busy:null,phase:"preview",preview:{request,data:decoded.data,
    projectTitle:p.projects.find(item=>item.workRef===request.work_ref)?.title??null,projectReadIdentity:p.projectReadIdentity}});
  }catch{if(live(c)&&ticket.current===id)patch({busy:null,error:"unavailable"});}
 }
 async function confirm(){
  const origin=document.activeElement,c=capture(),shown=current.current.preview,p=latest.current;
  if(!c||!shown||current.current.busy||current.current.retained||current.current.other||current.current.discovering)return;
  if(p.workRef!==shown.request.work_ref||p.message!==shown.request.message||p.projectReadIdentity!==shown.projectReadIdentity||!projectCurrent(shown.request.work_ref)||!sameConversationOwner(p.draftOwner,c.owner)){
   patch({phase:"draft",preview:null,error:"changed"});return;}
  try{
   const intent=c.binding.makeCreateIntent(shown.request,shown.data);
   if(!live(c)||!intent||intent.kind!=="conversation_create"||intent.targetKey!==shown.request.work_ref){patch({error:"unavailable"});return;}
   gestureFocus(".mm-new-conversation-outcome h1",origin);
   patch({busy:"operation",phase:"outcome",opened:false,error:null,projectTitle:shown.projectTitle,original:shown.request});
   const pending=c.binding.controller.begin(intent);
   patch({operation:c.binding.controller.getState()});
   const state=await pending;if(!live(c))return;
   const retained="pointer"in state?state.pointer:null;
   patch({operation:state,retained,busy:null});
   if(state.status==="accepted"){
    readAbort.current=new AbortController();patch({busy:"read"});
    const data=await readOriginal(c,shown.request);if(live(c))patch({data,busy:null,error:data?null:"unavailable"});
   }
  }catch{if(live(c))patch({busy:null,operation:c.binding.controller.getState(),error:"unavailable"});}
 }
 async function check(open=false){
  const origin=document.activeElement,c=capture(),v=current.current;if(!c||v.busy||v.discovering||v.other)return;
  const original=v.original??selectionOf(v.retained);if(!original){patch({error:"unavailable"});return;}
  patch({busy:"read",error:null});readAbort.current?.abort();readAbort.current=new AbortController();
  try{
   latest.current.onOriginalKeySelected({work_ref:original.work_ref,operation_key:original.operation_key});
   if(v.retained?.kind==="conversation_create"){
    const state=await c.binding.controller.recover();if(!live(c))return;
    const retained=state.pointer;
    if(retained&&(retained.kind!=="conversation_create"||!sameSelection(original,{work_ref:retained.targetKey??"",operation_key:retained.operationKey}))){
     patch({busy:null,other:true,data:null,operation:null});return;}
    patch({operation:state,retained});
   }
   const data=await readOriginal(c,original);if(!live(c))return;
   if(open&&data&&canOpen(data))gestureFocus(".mm-new-conversation-outcome h1",origin);
   patch({data,busy:null,phase:"outcome",opened:(open||v.opened)&&canOpen(data),error:data?null:"unavailable"});
  }catch{if(live(c))patch({busy:null,data:null,error:"unavailable"});}
 }
 function back(){
  focus.current=null;
  // Cancelling a read-only preview stops only that observation. A submitted
  // original remains owned by its controller and durable pointer after Back.
  if(current.current.busy==="preview"){
   readAbort.current?.abort();ticket.current++;
   patch({busy:null,phase:"draft",preview:null,error:null});
  }
  // Retire only a stale presentation hint after the incumbent owner cleared
  // its durable slot. This is not an effect verdict or a source request.
  const retained=current.current.retained,c=capture();
  if(c&&retained&&(retained.kind==="conversation_consume"||retained.kind==="conversation_turn")){
   Promise.resolve().then(()=>c.binding.store.read(c.owner.principalScope)).then(pointer=>{
    if(live(c)&&!pointer&&current.current.retained===retained)patch({retained:null});
   },()=>{});
  }
  latest.current.onBack();
 }
 /** Called only after the attended owner settles its genuine original.
  * Refresh local lookup DATA without changing the issued body or source state. */
 async function refreshPendingOriginal(){
  const c=capture(),v=current.current,pointer=v.retained;
  if(!c||!latest.current.active||v.busy||v.discovering||!pointer||
    (pointer.kind!=="conversation_consume"&&pointer.kind!=="conversation_turn"))return false;
  const expected=selectionOf(pointer);
  if(!expected||!v.original||!sameSelection(v.original,expected))return false;
  const store=c.binding.store,read=store.read,context=c.binding.context,id=++ticket.current;
  try{
   const next=await read.call(store,c.owner.principalScope);
   if(!live(c)||!latest.current.active||ticket.current!==id||c.binding.store!==store||store.read!==read||
     c.binding.context!==context||current.current.retained!==pointer||current.current.busy||
     !current.current.original||!sameSelection(current.current.original,expected))return false;
   if(next!==null){
    const pending=selectionOf(next);
    if(pending&&!sameSelection(pending,expected))patch({retained:next,other:false,original:pending,
      lookup:false,phase:"outcome",opened:false,data:null,operation:null,preview:null});
    else patch({retained:next,other:!pending});
    return false;
   }
   patch({retained:null,other:false});return true;
  }catch{return false;}
 }
 async function start(){
  const origin=document.activeElement;let v=current.current;
  if(v.busy||v.discovering)return;
  // Another owner may have completed its original while this App-lifetime
  // view stayed mounted. An explicit entry gesture rechecks ONLY local lookup
  // storage. It never mints a key, reads a source, or submits a command.
  {
   const c=capture();if(!c)return;
   const id=++ticket.current;patch({discovering:true,error:null});
   try{
    const pointer=await c.binding.store.read(c.owner.principalScope);
    if(!live(c)||ticket.current!==id)return;
    const pending=selectionOf(pointer);
    if(pointer){
     gestureFocus(".mm-new-conversation-outcome h1",origin);
     patch({discovering:false,retained:pointer,other:!pending,phase:"outcome",opened:false,
      ...(pending?{original:{...pending,...(v.original&&sameSelection(v.original,pending)&&v.original.message!==undefined?{message:v.original.message}:{})},lookup:false,data:null,preview:null,
       operation:v.operation?.status==="unknown"&&v.operation.pointer.kind===pointer.kind&&v.operation.pointer.operationKey===pointer.operationKey?v.operation:null}:{})});
     return;
    }
    const supplied=latest.current.originalLookup;
    const lookup=!current.current.original&&supplied&&sameConversationOwner(supplied.owner,c.owner)
     ?validateFreshConversationRequest(supplied.selection,"status"):null;
    patch({discovering:false,retained:v.operation?.status==="unknown"?v.retained:null,other:false,error:null,
     ...(lookup?{original:{work_ref:lookup.work_ref,operation_key:lookup.operation_key},lookup:true}: {})});
   }catch{if(live(c)&&ticket.current===id)patch({discovering:false,other:true,error:"unavailable"});return;}
   v=current.current;
  }
  // A pending original always wins over a new-entry gesture. Back/reopen
  // never prepares, reserves, submits, or replays that operation.
  if(v.retained||v.busy||v.other||v.operation?.status==="unknown"||v.lookup&&!canOpen(v.data)){gestureFocus(".mm-new-conversation-outcome h1",origin);patch({phase:"outcome",opened:false});return;}
  const settled=v.operation?.status==="accepted"||v.operation?.status==="refused"||v.lookup&&canOpen(v.data);
  gestureFocus("select",origin);
  if(settled){
   if(v.operation?.status==="accepted")latest.current.onMessageChange("");
   patch({phase:"draft",preview:null,original:null,data:null,operation:null,lookup:false,opened:false,error:null});
  }else patch({phase:"draft",opened:false});}
 const zh=props.locale==="zh-CN",t=(en:string,cn:string)=>zh?cn:en;
 const ownsDraft=sameConversationOwner(props.draftOwner,actualOwner);
 const error=view.error? <p role="status">{view.error==="invalid"?t("Choose a project and enter a valid first message.","请选择项目并填写有效的第一条消息。"):
  view.error==="changed"?t("The draft or project changed. Review it again before creating a conversation.","草稿或项目已更改。请重新预览后再创建对话。"):
  view.phase==="outcome"?t("The original request cannot be checked here right now.","此处暂时无法查看原请求。"):
  t("Conversation preview is unavailable here. Your message remains a draft.","此处暂时无法预览对话。消息仍是草稿。")}</p>:null;
 const feedback=<>{view.discovering?<p role="status">{t("Checking for an original request…","正在查找原请求…")}</p>:null}
  {view.retained&&!view.other&&!view.operation?<p role="status">{view.retained.kind==="conversation_create"
   ?t("An original conversation request needs a status check. Don’t create it again.","原对话请求需要查询状态。请勿再次创建。")
   :t("An original follow-up request needs a status check. Open its first response to use the existing status controls. Don’t send it again.","原后续请求需要查询状态。请打开首条回复，通过原有状态控件查询。请勿再次发送。")}</p>:null}
  {view.lookup&&!view.operation?<p role="status">{t("An original conversation request is selected. Check its status to reopen it.","已选择原对话请求。请查询状态后重新打开。")}</p>:null}
  {view.phase==="outcome"&&!view.operation?<p>{t("Going back does not cancel the original request.","返回不会取消原请求。")}</p>:null}
  {view.other?<p role="status">{t("Another request needs its existing status controls before a new conversation can be created.","请先通过原有状态控件处理另一条请求，再创建新对话。")}</p>:null}{error}</>;
 const validDraft=!!props.workRef&&projectCurrent(props.workRef)&&!!validateFreshConversationRequest({work_ref:props.workRef,operation_key:"syntax-check",message:props.message},"preview");
 const draft=<NewConversationDraft locale={props.locale} projects={props.projects.filter(item=>projectCurrent(item.workRef))} projectsState={props.projectsState}
  workRef={props.workRef} onWorkRefChange={value=>{patch({preview:null,error:null});props.onWorkRefChange(value);}}
  message={ownsDraft?props.message:""} onMessageChange={value=>{patch({preview:null,error:null});props.onMessageChange(value);}}
  readOnly={!actualOwner||!!view.busy||view.other} onBack={back} feedback={feedback}
  previewControl={<button type="button" className="primary" disabled={!actualOwner||!ownsDraft||!validDraft||!!view.busy||view.discovering||!!view.retained||view.other}
   onClick={()=>void preview()}>{view.busy==="preview"?t("Reviewing…","正在预览…"):t("Review conversation","预览对话")}</button>}/>;
 const prepared=view.preview;
 const initialRead=useMemo<FreshConversationInitialRead|null>(()=>{
  const data=view.data,original=view.original,c=capture();
  if(!data?.result||!data.locator||!original||!c)return null;
  const selection={work_ref:original.work_ref,operation_key:original.operation_key};
  return {selection,result:data.result,locator:data.locator,current:()=>{
   const visible=current.current;
   return root.current?.isConnected===true&&live(c)&&latest.current.active&&visible.scope===c.scope&&visible.phase==="outcome"&&visible.opened&&
    !visible.busy&&visible.data===data&&!!visible.original&&sameSelection(visible.original,selection);
  }};
 },[scope,view.data,view.original?.work_ref,view.original?.operation_key,actualOwner?.principalScope,actualOwner?.generation]);
 const continuation=initialRead&&view.opened&&props.active?props.renderContinuation?.(initialRead):undefined;
 const panel=<div ref={root} className="new-conversation-journey" lang={props.locale}>
  {view.phase==="draft"?draft:view.phase==="preview"&&prepared?
   <section className="new-conversation-preview"><header><h1>{t("Review new conversation","预览新对话")}</h1>
    <p>{t("Confirm the project and first message before creating a separate conversation.","确认项目和第一条消息后，再创建单独的对话。")}</p></header>
    <div className="new-conversation-preview-message"><h2>{t("Project","项目")}</h2><p>{prepared.projectTitle??prepared.request.work_ref}</p>
     <h2>{t("First message","第一条消息")}</h2><p>{prepared.request.message}</p></div>
    {error}<div className="new-conversation-preview-actions"><button type="button" disabled={!!view.busy} onClick={()=>{
     gestureFocus("textarea");patch({phase:"draft",preview:null,error:null});}}>{t("Back to message","返回消息草稿")}</button>
     <button type="button" className="primary" disabled={!!view.busy||!actualOwner||!projectCurrent(prepared.request.work_ref)||props.projectReadIdentity!==prepared.projectReadIdentity} onClick={()=>void confirm()}>{t("Create conversation","创建对话")}</button>
     <button type="button" onClick={back}>{t("Cancel","取消")}</button></div>
    <p>{t("Creation still depends on the current conversation checks.","创建仍需通过当前的对话检查。")}</p>
    <details><summary>{t("Sources and access","来源与访问")}</summary><dl>{Object.entries(prepared.data.preview??{}).map(([key,value])=>
     <div key={key}><dt>{key}</dt><dd><code>{typeof value==="object"?JSON.stringify(value):String(value)}</code></dd></div>)}</dl></details>
   </section>:<>{feedback}<NewConversationOutcome locale={props.locale} data={view.data} operationState={view.operation}
    awaitingCheck={(view.lookup||!!view.retained&&view.retained.kind!=="conversation_create")&&!view.data&&!view.operation&&!view.busy&&!view.error}
    originalMessage={view.original&&"message"in view.original?view.original.message??null:null} projectTitle={view.projectTitle}
    opened={view.opened} busy={!!view.busy||view.discovering||view.other} activity={view.busy==="operation"?"creating":view.busy==="read"?"checking":null} canOpen={canOpen(view.data)&&!view.other&&!!actualOwner}
    onCheck={()=>void check()} onOpen={()=>void check(true)} onBack={back} continuation={continuation}/></>}
 </div>;
 return {panel,start,refreshPendingOriginal,hasUnresolvedOriginal:!!view.retained||view.other||view.busy==="operation"||view.discovering||view.operation?.status==="unknown"||view.lookup&&!canOpen(view.data)};
}
