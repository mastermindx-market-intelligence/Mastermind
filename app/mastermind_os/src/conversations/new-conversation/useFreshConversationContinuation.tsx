import {useEffect, useLayoutEffect, useMemo, useRef, useState} from "react";
import type {OperationPointer, OperationState, OwnerContext} from "../../orchestration/operation-controller";
import {freshConversationTarget, type FreshConversationOriginalSelector} from "../../orchestration/fresh-conversation-target";
import {FreshConversationTurnPanel} from "./FreshConversationTurnPanel";
import type {FreshConversationAttendedBinding, FreshConversationOriginalRead, PreparedFreshConversationTurn} from "./fresh-conversation-attended-binding";
import {decodeFreshConversationTurnResult, validateFreshConversationTurnRequest, type FreshConversationTurnData, type FreshConversationTurnRequest, type FreshConversationTurnConsumption} from "./fresh-conversation-turn";
import {validateAttendedRequest,decodeAttendedResult,attendedReadSettled,attendedContractForKey,type FreshAttendedData} from "./fresh-conversation-attended-contract";
import "./new-conversation-journey.css";
import type {FreshConversationTurnDraftCapture,FreshConversationTurnDraftState} from "./useFreshConversationTurnDraftState";

export interface FreshConversationContinuationProps {
  locale:"en"|"zh-CN";
  /** A qualified sibling control settled; re-read only the incumbent local hint. */
  pendingRevision?:number;
  active:boolean;
  /** A readonly source window still permits qualified original recovery. */
  readOnly?:boolean;
  messageReadOnly?:boolean;
  onMessageFocus?:()=>void;
  binding:FreshConversationAttendedBinding|null;
  host:object|undefined;
  authGeneration:number;
  selection:FreshConversationOriginalSelector;
  read:FreshConversationOriginalRead|null;
  /** Supplied only from the same actual current reader, never a permission. */
  initialConsumption?:FreshConversationTurnConsumption|null;
  /** Separate controlled follow-up text, never the initial first message. */
  message:string;
  draftOwner:OwnerContext|null;
  onMessageChange:(message:string)=>void;
  /** Qualified original receipt/read settled; request local hint refresh only. */
  onOriginalSettled?:()=>void;
  draftSubmission?:Pick<FreshConversationTurnDraftState,"captureSubmission"|"submissionFor"|"settleSubmission"|"submittedTurnKey">;
}
type Busy="keeping"|"sending"|"checking"|"reviewing"|null;
type View={scope:object;data:FreshAttendedData|null;operation:OperationState|null;
  pending:OperationPointer|null;discovering:boolean;pendingKnown:boolean;busy:Busy;attempted:boolean;
  request:FreshConversationTurnRequest|null;prepared:PreparedFreshConversationTurn|null;
  originalTurnMessage:string|null;lastTurnKey:string|null;lastKind:"consume"|"turn"|null;
  draftCapture:FreshConversationTurnDraftCapture|null;turnSettled:boolean;recoveryHeld:boolean;historyLimited:boolean;
  recordedTurns:readonly {data:FreshAttendedData;message:string|null}[];
  error:"unavailable"|"pending"|"other"|"changed"|"readFirst"|null};
const blank=(scope:object):View=>({scope,data:null,operation:null,pending:null,discovering:true,pendingKnown:false,busy:null,
  attempted:false,request:null,prepared:null,originalTurnMessage:null,lastTurnKey:null,lastKind:null,draftCapture:null,turnSettled:false,recoveryHeld:false,historyLimited:false,recordedTurns:[],error:null});
const sameOwner=(a:OwnerContext|null,b:OwnerContext|null)=>!!a&&!!b&&a.principalScope===b.principalScope&&a.generation===b.generation;
function ownerOf(binding:FreshConversationAttendedBinding|null):OwnerContext|null {
  try {const owner=binding?.context();return owner?{...owner}:null;}catch{return null;}
}
const methods=(b:FreshConversationAttendedBinding|null)=>[b?.context,b?.makeConsumeIntent,b?.makeTurnRequest,b?.previewTurn,b?.makeTurnIntent,b?.readOriginalConsume,b?.readOriginalTurn,b?.store,b?.controller];

/** Presentation integration only. The incumbent controller owns effects and the
 * incumbent store owns unresolved lookup hints. React effects read only that
 * local hint; every source read, preview, Keep and Send needs a user gesture. */
export function useFreshConversationContinuation(props:FreshConversationContinuationProps){
  const liveOwner=ownerOf(props.binding),target=freshConversationTarget(props.selection);
  let readWitnessCurrent=false;
  try{readWitnessCurrent=!!props.read&&props.read.current()===true&&freshConversationTarget(props.read.selection)===target;}catch{ /* withdrawn witness */ }
  const renderMethods=methods(props.binding);
  const scope=useMemo(()=>({}),[props.host,props.binding,props.authGeneration,target,props.read,readWitnessCurrent,
    liveOwner?.principalScope,liveOwner?.generation,...renderMethods]);
  const latest=useRef(props);latest.current=props;
  const mounted=useRef(false),committedScope=useRef(scope),latch=useRef<object|null>(null);
  const abort=useRef<AbortController|null>(null),root=useRef<HTMLDivElement>(null);
  const requestedFocus=useRef<{scope:object;selector:string}|null>(null);
  const [stored,setStored]=useState<View>(()=>blank(scope));
  const current=useRef(stored);current.current=stored.scope===scope?stored:blank(scope);
  const view=current.current;
  const t=(en:string,zh:string)=>props.locale==="zh-CN"?zh:en;
  const patch=(change:Partial<View>)=>setStored(v=>({...(v.scope===scope?v:blank(scope)),...change,scope}));
  function capture(requireRead=false){
    const p=latest.current,b=p.binding,owner=ownerOf(b),key=freshConversationTarget(p.selection);
    if(!mounted.current||!p.active||!b||!owner||!key||committedScope.current!==scope||!sameOwner(owner,liveOwner)||
      methods(b).some((method,i)=>method!==renderMethods[i]))return null;
    const read=p.read;
    if(requireRead&&(p.readOnly||!read||read.current()!==true||freshConversationTarget(read.selection)!==key))return null;
    return {scope,b,owner,key,host:p.host,auth:p.authGeneration,read,methods:methods(b),message:p.message};
  }
  type Capture=NonNullable<ReturnType<typeof capture>>;
  function valid(c:Capture,requireRead=false){
    const p=latest.current,b=p.binding;
    if(!mounted.current||!p.active||committedScope.current!==c.scope||b!==c.b||p.host!==c.host||p.authGeneration!==c.auth||
       freshConversationTarget(p.selection)!==c.key||!sameOwner(ownerOf(b),c.owner))return false;
    const now=methods(b);if(now.some((method,i)=>method!==c.methods[i]))return false;
    return !requireRead||!p.readOnly&&!!c.read&&p.read===c.read&&c.read.current()===true&&freshConversationTarget(c.read.selection)===c.key;
  }
  function belongs(pointer:OperationPointer,c:Capture){
    return (pointer.kind==="conversation_consume"||pointer.kind==="conversation_turn")&&pointer.targetKey===c.key;
  }
  useLayoutEffect(()=>{
    mounted.current=true;committedScope.current=scope;
    return()=>{mounted.current=false;abort.current?.abort();props.binding?.controller.invalidate();requestedFocus.current=null;};
  },[scope]);
  useEffect(()=>{
    const c=capture();if(!c){patch({discovering:false});return;}
    let cancelled=false;
    Promise.resolve().then(()=>c.b.store.read(c.owner.principalScope)).then(pointer=>{
      if(cancelled||!valid(c))return;
      patch({pending:pointer,discovering:false,pendingKnown:true,error:pointer?(belongs(pointer,c)?"pending":"other"):null});
    },()=>{if(!cancelled&&valid(c))patch({discovering:false,pendingKnown:false,error:"unavailable"});});
    return()=>{cancelled=true;};
  },[scope,props.pendingRevision]);
  useLayoutEffect(()=>{
    const request=requestedFocus.current;if(!request||request.scope!==scope)return;
    requestedFocus.current=null;
    if(capture(true))root.current?.querySelector<HTMLElement>(request.selector)?.focus();
  },[scope,view.prepared]);

  async function pending(c:Capture){
    try{
      const pointer=await c.b.store.read(c.owner.principalScope);
      if(!valid(c))return {held:true,pointer:null};
      patch({pending:pointer,pendingKnown:true,error:pointer?(belongs(pointer,c)?"pending":"other"):null});
      return {held:pointer!==null,pointer};
    }catch(error){if(valid(c))patch({pendingKnown:false});throw error;}
  }
  function unsettledTurn(){
    return current.current.lastKind==="turn"&&!current.current.turnSettled||
      !!latest.current.draftSubmission?.submittedTurnKey;
  }
  function noSubmittedOriginal(){
    return !current.current.attempted&&!current.current.lastKind&&!current.current.data?.initial_consumption&&
      !latest.current.draftSubmission?.submittedTurnKey&&!currentConsumption();
  }
  async function readBack(c:Capture,kind:"consume"|"turn",turnKey:string|null,sentMessage?:string,allowUnsubmittedAbsence=false){
    if(!valid(c)||!c.read||c.read.current()!==true){if(valid(c))patch({error:"readFirst"});return;}
    const selection=c.read.selection;
    const contract=c.read.contract??"legacy-v1";
    const request=validateAttendedRequest(kind==="consume"
      ?{...selection,initial_digest:c.read.result.digest}:{...selection,turn_key:turnKey},kind==="consume"?"consume_status":"turn_read",contract);
    if(!request)return;
    patch({recoveryHeld:true});
    const raw=kind==="consume"?(contract==="native-v2"?await c.b.readOriginalConsume(selection,abort.current!.signal,contract):await c.b.readOriginalConsume(selection,abort.current!.signal))
      :await c.b.readOriginalTurn(selection,turnKey!,abort.current!.signal);
    if(!valid(c)||latest.current.read!==c.read||c.read.current()!==true)return;
    const decoded=decodeAttendedResult(raw,kind==="consume"?"consume_status":"turn_read",request,contract);
    if(!decoded?.ok){patch({error:"unavailable"});return;}
    patch({data:decoded.data,error:null});
    const settled=kind==="consume"?decoded.data.state==="CONSUMED"&&decoded.data.initial_consumption!==null
      :decoded.data.state==="RECORDED"&&decoded.data.result!==null;
    const absent=allowUnsubmittedAbsence&&kind==="consume"&&decoded.data.state==="ABSENT"&&decoded.data.effect==="NONE";
    if(!absent&&(!settled||!attendedReadSettled(decoded.data)))return;
    // A remounted controller can be idle after its genuine accepted receipt
    // cleared the hint. The exact source read settles the original; it never
    // manufactures controller acceptance or clears a newer unresolved pointer.
    const pointer=await c.b.store.read(c.owner.principalScope);
    if(!valid(c)||latest.current.read!==c.read||c.read.current()!==true)return;
    const operation=c.b.controller.getState();
    patch({operation,pending:pointer??null,pendingKnown:true,error:pointer?(belongs(pointer,c)?"pending":"other"):pointer===null?null:"unavailable"});
    if(absent){
      // A status-only check before Keep has no original effect to recover.
      // Release only this read hold after fresh empty/idle owner observations.
      if(pointer===null&&operation.status==="idle"&&noSubmittedOriginal())patch({recoveryHeld:false});
      return;
    }
    if(pointer!==null||operation.status!=="accepted"&&operation.status!=="idle")return;
    if(kind==="turn"&&turnKey){
      const draft=latest.current.draftSubmission;
      const token=current.current.draftCapture??draft?.submissionFor(turnKey);
      const matched=!!token&&draft?.submissionFor(turnKey)===token;
      const retainedText=current.current.lastTurnKey===turnKey?current.current.originalTurnMessage:null;
      const sent=sentMessage??retainedText??(matched?c.message:null);
      if(draft&&matched)draft.settleSubmission(token!,raw);
      const previous=current.current.recordedTurns.filter(turn=>turn.data.turn_key!==decoded.data.turn_key);
      const candidates=[...previous,{data:decoded.data,message:sent}];
      let recordedTurns=candidates.slice(-8);
      // Keep complete, decoder-bounded results. Canonical older pages remain
      // with the original project history owner, never this presentation slot.
      while(recordedTurns.length&&new TextEncoder().encode(JSON.stringify(recordedTurns)).length>65536)
        recordedTurns=recordedTurns.slice(1);
      patch({turnSettled:true,lastKind:"turn",lastTurnKey:turnKey,request:null,prepared:null,draftCapture:null,
        originalTurnMessage:sent,recordedTurns,historyLimited:current.current.historyLimited||recordedTurns.length<candidates.length});
      if(!draft&&sent!==null&&latest.current.message===sent)latest.current.onMessageChange("");
    }
    patch({recoveryHeld:false});
    try{latest.current.onOriginalSettled?.();}catch{ /* A local hint observer cannot undo the actual receipt. */ }
  }
  function enter(requireRead:boolean){
    if(latch.current===scope)return null;
    const c=capture(requireRead);if(!c)return null;
    latch.current=scope;abort.current?.abort();abort.current=new AbortController();return c;
  }
  function leave(c:Capture){if(latch.current===c.scope)latch.current=null;if(valid(c))patch({busy:null});}
  async function keep(){
    const c=enter(true);if(!c)return;
    try{
      if((await pending(c)).held||!valid(c,true))return;
      if(current.current.attempted||current.current.data?.initial_consumption||currentConsumption())return;
      const intent=c.b.makeConsumeIntent(c.read!);if(!intent){patch({error:"unavailable"});return;}
      patch({busy:"keeping",attempted:true,lastKind:"consume",error:null});
      const state=await c.b.controller.begin(intent);
      if(!valid(c))return;
      patch({operation:state,pending:state.pointer});
      if(state.status==="accepted")await readBack(c,"consume",null);
    }catch{if(valid(c))patch({error:"unavailable"});}finally{leave(c);}
  }
  async function review(){
    const c=enter(true);if(!c)return;
    try{
      if((await pending(c)).held||!valid(c,true)||latest.current.messageReadOnly||!sameOwner(latest.current.draftOwner,c.owner))return;
      if(!(current.current.data?.initial_consumption??currentConsumption())||unsettledTurn())return;
      const prior=current.current.request;
      const request=prior&&"message"in prior&&prior.message===c.message?prior:c.b.makeTurnRequest(c.read!,c.message);
      if(!request){patch({error:"unavailable"});return;}
      patch({busy:"reviewing",request,prepared:null,error:null});
      const prepared=await c.b.previewTurn(c.read!,request,abort.current!.signal);
      if(!valid(c,true))return;
      if(latest.current.message!==c.message){patch({error:"changed"});return;}
      if(!prepared){patch({error:"unavailable"});return;}
      requestedFocus.current={scope,selector:"[data-turn-review]"};patch({prepared});
    }catch{if(valid(c))patch({error:"unavailable"});}finally{leave(c);}
  }
  async function send(){
    const c=enter(true);if(!c)return;
    try{
      const prepared=current.current.prepared;
      if(latest.current.messageReadOnly||unsettledTurn()||!prepared||!("message"in prepared.request)||prepared.request.message!==c.message||
        !sameOwner(latest.current.draftOwner,c.owner)||(await pending(c)).held||!valid(c,true))return;
      if(unsettledTurn())return;
      const intent=c.b.makeTurnIntent(prepared);if(!intent){patch({prepared:null,error:"changed"});return;}
      if(!("turn_key"in prepared.request))return;
      const key=prepared.request.turn_key;
      const draft=latest.current.draftSubmission,token=draft?.captureSubmission(key,c.message)??null;
      if(draft&&!token){patch({prepared:null,error:"changed"});return;}
      patch({busy:"sending",lastTurnKey:key,lastKind:"turn",turnSettled:false,originalTurnMessage:c.message,draftCapture:token,prepared:null,error:null});
      const state=await c.b.controller.begin(intent);
      if(!valid(c))return;
      patch({operation:state,pending:state.pointer});
      if(state.status==="accepted")await readBack(c,"turn",key,c.message);
    }catch{if(valid(c))patch({error:"unavailable"});}finally{leave(c);}
  }
  async function check(){
    const c=enter(false);if(!c)return;
    const wasOther=current.current.error==="other";
    try{
      patch({busy:"checking",error:null});
      const held=await pending(c);if(!valid(c))return;
      if(held.pointer&&!belongs(held.pointer,c))return;
      // A cleared foreign hint is not an original receipt. This gesture only
      // refreshes the local hint; a fresh Keep still needs a separate click.
      if(wasOther&&!held.pointer&&!current.current.attempted&&!current.current.lastKind)return;
      const submitted=latest.current.draftSubmission?.submittedTurnKey;
      const kind=held.pointer?.kind==="conversation_turn"?"turn":held.pointer?.kind==="conversation_consume"?"consume":submitted?"turn":current.current.lastKind??"consume";
      const key=kind==="turn"?(held.pointer?.operationKey??submitted??current.current.lastTurnKey??null):null;
      if(held.pointer){
        const native=held.pointer.kind==="conversation_turn"&&attendedContractForKey(held.pointer.operationKey)==="native-v2";
        const state=await c.b.controller.recover(native?{reconcileNative:true,expectedPointer:held.pointer}:undefined);if(!valid(c))return;
        const sameTurn=current.current.lastKind==="turn"&&current.current.lastTurnKey===key;
        patch({operation:state,pending:state.pointer,lastKind:kind,lastTurnKey:key,
          ...(kind==="turn"&&!sameTurn?{originalTurnMessage:null,draftCapture:null,turnSettled:false}:{})});
        if(state.status!=="accepted")return;
      }
      const allowUnsubmittedAbsence=kind==="consume"&&!held.pointer&&noSubmittedOriginal()&&c.b.controller.getState().status==="idle";
      await readBack(c,kind,key,undefined,allowUnsubmittedAbsence);
    }catch{if(valid(c))patch({error:"unavailable"});}finally{leave(c);}
  }
  const ownsDraft=sameOwner(props.draftOwner,liveOwner);
  const readCurrent=readWitnessCurrent;
  function currentConsumption(){
    const p=latest.current,value=p.initialConsumption;
    return p.read?.current()&&value?.state==="CONSUMED"&&value.initial_digest===p.read.result.digest&&
      Number.isSafeInteger(value.event_id)&&value.event_id>0&&/^[0-9a-f]{64}$/.test(value.event_sha256)?value:null;
  }
  const suppliedConsumption=currentConsumption();
  const consumption=view.data?.initial_consumption??suppliedConsumption;
  const held=!!view.pending||view.operation?.status==="unknown"||view.discovering||!!liveOwner&&!view.pendingKnown||view.recoveryHeld;
  const prepared=view.prepared&&"message"in view.prepared.request&&view.prepared.request.message===props.message?view.prepared:null;
  const editable=props.active&&!props.readOnly&&!!liveOwner&&readCurrent&&ownsDraft&&!view.busy&&!held;
  const errorText=view.error==="pending"?t("Check the original request before continuing. Don’t send it again.","请先查看原请求状态，再继续。请勿再次发送。")
    :view.error==="other"?t("Another request needs its existing status controls before continuing.","请先通过另一请求原有的状态控件查询，再继续。")
    :view.error==="changed"?t("The message or its context changed. Review it again before sending.","消息或其上下文已改变。发送前请重新预览。")
    :view.error==="readFirst"?t("The original request was checked. Reopen its first response to continue.","已查询原请求。请重新打开首条回复后继续。")
    :view.error==="unavailable"?t("This action could not be completed here. Check the original request for its outcome.","此处暂时无法完成此操作。请查看原请求以确认结果。") :null;
  const submittedTurnKey=props.draftSubmission?.submittedTurnKey;
  const turnAttempted=view.lastKind==="turn"&&!view.turnSettled||!!submittedTurnKey;
  const canReview=editable&&!props.messageReadOnly&&!turnAttempted&&!!consumption&&props.message.length>0;
  const panel=<div ref={root} className="new-conversation-journey" lang={props.locale}>
    <FreshConversationTurnPanel locale={props.locale} data={turnAttempted&&view.data?.turn_key!==(view.lastTurnKey??submittedTurnKey)?null:view.data} initialConsumption={consumption}
      responsePending={turnAttempted} allowNextMessage={view.turnSettled}
      allowInitialKeep={view.data?.state==="ABSENT"&&!held&&view.operation?.status==="idle"&&noSubmittedOriginal()}
      recordedTurns={view.recordedTurns} historyLimited={view.historyLimited} operationState={view.operation}
      activity={view.busy==="reviewing"?null:view.busy} message={ownsDraft?props.message:""} originalTurnMessage={view.originalTurnMessage}
      onMessageChange={value=>{if(latest.current.messageReadOnly||unsettledTurn()||!capture(true)||!ownsDraft)return;patch({prepared:null,error:null});props.onMessageChange(value);}}
      messagePreview={prepared?<section className="new-conversation-preview"><h3 data-turn-review tabIndex={-1}>{t("Review message","预览消息")}</h3>
      <p className="new-conversation-preview-message">{props.message}</p>
      <button type="button" disabled={!!view.busy} onClick={()=>{requestedFocus.current={scope,selector:"textarea"};patch({prepared:null});}}>{t("Edit message","编辑消息")}</button>
    </section>:undefined}
      messageReadOnly={props.messageReadOnly} onMessageFocus={props.onMessageFocus}
      readOnly={!editable} feedback={errorText?<p role="status">{errorText}</p>:view.busy==="reviewing"?<p role="status">{t("Reviewing message…","正在预览消息…")}</p>:null}
      keepControl={!props.readOnly&&!view.attempted&&!consumption&&readCurrent&&!held?<button type="button" className="primary" disabled={!editable} onClick={()=>void keep()}>{t("Keep first response","保留第一条回复")}</button>:undefined}
      sendControl={!props.readOnly&&!turnAttempted&&consumption&&!held?<button type="button" className="primary" disabled={!canReview} onClick={()=>void(prepared?send():review())}>{prepared?t("Send message","发送消息"):t("Review message","预览消息")}</button>:undefined}
      checkControl={<button type="button" disabled={!props.active||!liveOwner||!!view.busy||view.discovering} onClick={()=>void check()}>{view.error==="other"?t("Check for pending requests","检查待处理请求"):t("Check original request","查看原请求状态")}</button>}/>
  </div>;
  return {panel,hasUnresolvedOriginal:held||turnAttempted||view.busy==="keeping"||view.busy==="sending"};
}
