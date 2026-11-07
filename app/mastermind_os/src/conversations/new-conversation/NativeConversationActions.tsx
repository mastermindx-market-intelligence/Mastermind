import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import type {OperationController,OperationPointer,OperationState} from '../../orchestration/operation-controller';
import {freshConversationTarget,type FreshConversationOriginalSelector} from '../../orchestration/fresh-conversation-target';
import type {FreshConversationAttendedBinding} from './fresh-conversation-attended-binding';
import type {NativeConversationObservation,PreparedNativeResume} from './native-conversation-controls';
export interface NativeConversationActionsProps {
 locale:'en'|'zh-CN';active:boolean;host:object|undefined;authGeneration:number;
 selection:FreshConversationOriginalSelector;binding:FreshConversationAttendedBinding|null;
 observation:NativeConversationObservation|null;refresh:()=>Promise<void>;
 /** The actual creation owner, only supplied by its existing journey. */
 createController?:OperationController;
 onUnresolvedChange:(held:boolean)=>void;
 onControlSettled?:()=>Promise<void>|void;
}
/** Presentation gestures over the incumbent controller and row; no effect owner. */
export function NativeConversationActions(props:NativeConversationActionsProps){
 const target=freshConversationTarget(props.selection),owner=props.binding?.context();
 const scope=useMemo(()=>({}),[target,props.binding,props.host,props.authGeneration,owner?.principalScope,owner?.generation,props.createController]);
 const latest=useRef(props);latest.current=props;
 const mounted=useRef(false),latch=useRef<object|null>(null),abort=useRef<AbortController|null>(null);
 const [view,setView]=useState<{scope:object;inspection:'checking'|'ready'|'unavailable';inspectedData:NativeConversationObservation['data']|undefined;busy:boolean;pointer:OperationPointer|null;child:OperationPointer|null;state:OperationState|null;preview:PreparedNativeResume|null;error:boolean}>(
  {scope,inspection:'checking' as const,inspectedData:undefined,busy:false,pointer:null,child:null,state:null,preview:null,error:false});
 const current=view.scope===scope?view:{scope,inspection:'checking' as const,inspectedData:undefined,busy:false,pointer:null,child:null,state:null,preview:null,error:false};
 const inspectionTicket=useRef(0);
 const committed=useRef(scope),retiredObservation=useRef<NativeConversationObservation|null>(null);
 const blank=()=>({scope,inspection:'checking' as const,inspectedData:undefined,busy:false,pointer:null,child:null,state:null,preview:null,error:false});
 const patch=(change:Partial<typeof view>)=>setView(old=>({...(old.scope===scope?old:blank()),...change,scope}));
 const t=(en:string,zh:string)=>props.locale==='zh-CN'?zh:en;
 function capture(){
  const p=latest.current,b=p.binding,o=b?.context();
  if(!mounted.current||committed.current!==scope||!p.active||!b?.native||!o||
    o.principalScope!==owner?.principalScope||o.generation!==owner?.generation||freshConversationTarget(p.selection)!==target)return null;
  return {b,n:b.native,o,host:p.host,auth:p.authGeneration,scope,store:b.store,read:b.store.read,context:b.context};
 }
 type Capture=NonNullable<ReturnType<typeof capture>>;
 function valid(c:Capture){
  const p=latest.current,o=p.binding?.context();
  return mounted.current&&committed.current===c.scope&&p.active&&p.binding===c.b&&c.b.native===c.n&&c.b.store===c.store&&
   c.store.read===c.read&&c.b.context===c.context&&p.host===c.host&&p.authGeneration===c.auth&&
   freshConversationTarget(p.selection)===target&&o?.principalScope===c.o.principalScope&&o.generation===c.o.generation;
 }
 function parentOwner(pointer:OperationPointer,c:Capture|null):OperationController|null{
  if(!c)return null;
  const p=latest.current;
  if(pointer.kind==='conversation_turn'&&/^mmos-native-turn-[0-9a-f]{40}$/.test(pointer.operationKey)&&pointer.targetKey===target)return c.b.controller;
  if(pointer.kind==='conversation_create'&&'operation_key'in p.selection&&pointer.operationKey===p.selection.operation_key&&
    pointer.targetKey===p.selection.work_ref&&/^mmos-native-create-[0-9a-f]{40}$/.test(pointer.operationKey))return p.createController??null;
  return null;
 }
 async function inspect(c:Capture){
  const ticket=++inspectionTicket.current,inspectedData=latest.current.observation?.data;patch({inspection:'checking'});
  const current=()=>valid(c)&&inspectionTicket.current===ticket;
  try{
   const pointer=await c.read.call(c.store,c.o.principalScope);if(!current())return null;
   let child:OperationPointer|null=null;
   if(pointer&&parentOwner(pointer,c)){
    if(!c.store.readControl)throw Error('unavailable');
    const attached=await c.store.readControl(c.o.principalScope,pointer);if(!current())return null;
    if(!attached.matched)throw Error('parent changed during inspection');
    child=attached.control;
   }
   patch({pointer,child,inspection:'ready',inspectedData});return {pointer,child};
  }catch(error){if(!current())return null;patch({inspection:'unavailable',error:true});throw error;}
 }
 useEffect(()=>{mounted.current=true;committed.current=scope;
  return()=>{mounted.current=false;inspectionTicket.current++;abort.current?.abort();};
 },[scope]);
 useEffect(()=>{const c=capture();if(!c)return;let live=true;
  void inspect(c).catch(()=>{if(live&&valid(c))patch({error:true});});
  return()=>{live=false;};
 },[scope,props.observation?.data,props.active]);
 const knownHeld=!!current.child||!!current.pointer&&['conversation_stop','conversation_resume'].includes(current.pointer.kind)||
  current.state?.status==='unknown'||current.busy;
 // A new status publication is uninspected during its first render too;
 // its passive local read cannot briefly inherit the preceding ready state.
 const inspectionReady=current.inspection==='ready'&&current.inspectedData===props.observation?.data;
 const held=!inspectionReady||knownHeld;
 useLayoutEffect(()=>{props.onUnresolvedChange(held);},[props.onUnresolvedChange,held]);
 useLayoutEffect(()=>()=>props.onUnresolvedChange(false),[props.onUnresolvedChange]);
 function enter(){if(latch.current===scope)return null;const c=capture();if(!c)return null;
  latch.current=scope;abort.current?.abort();abort.current=new AbortController();patch({busy:true,error:false});return c;}
 function leave(c:Capture){if(latch.current===c.scope)latch.current=null;if(valid(c))patch({busy:false});}
 async function refresh(c:Capture,settled=false){
  if(settled)await latest.current.onControlSettled?.();
  if(!valid(c))return;await latest.current.refresh();if(valid(c))await inspect(c);
 }
 async function stop(){
  const c=enter();if(!c)return;
  try{
   const row=await inspect(c),witness=latest.current.observation;
   if(!row||!valid(c)||!witness||witness===retiredObservation.current||!witness.current()||freshConversationTarget(witness.selection)!==target||row.child)return;
   const parent=row.pointer,controller=parent?parentOwner(parent,c):c.b.controller;
   if(!controller){patch({error:true});return;}
   // A non-parent durable control belongs to its existing recovery action.
   if(parent&&!['conversation_create','conversation_turn'].includes(parent.kind))return;
   const intent=c.n.makeStopIntent(witness);if(!intent){patch({error:true});return;}
   retiredObservation.current=witness;
   const state=parent?await controller.beginControl(parent,intent):await controller.begin(intent);
   if(!valid(c))return;patch({state,preview:null});
   await inspect(c);if(state.status==='accepted'&&valid(c))await refresh(c,true);
  }catch{if(valid(c))patch({error:true});}finally{leave(c);}
 }
 async function check(){
  const c=enter();if(!c)return;
  try{
   const row=await inspect(c);if(!row||!valid(c))return;
   let state:OperationState|null=null;
   if(row.pointer&&row.child){
    const controller=parentOwner(row.pointer,c);if(!controller)return;
    state=await controller.recoverControl(row.pointer);
   }else if(row.pointer&&row.pointer.targetKey===target&&
     ['conversation_stop','conversation_resume'].includes(row.pointer.kind))state=await c.b.controller.recover();
   if(!valid(c))return;
   patch({state,preview:null});await refresh(c,state?.status==='accepted');
  }catch{if(valid(c))patch({error:true});}finally{leave(c);}
 }
 async function resume(){
  const c=enter();if(!c)return;
  try{
   const row=await inspect(c);if(!row||row.pointer||!valid(c))return;
   const preview=current.preview;
   if(preview){
    const intent=c.n.makeResumeIntent(preview);if(!intent){patch({preview:null,error:true});return;}
    if(preview.witness===retiredObservation.current)return;
    retiredObservation.current=preview.witness;
    const state=await c.b.controller.begin(intent);if(!valid(c))return;patch({state,preview:null});
    await inspect(c);
    // APPLIED is the original control receipt. Only a new read can show G2.
    if(state.status==='accepted'&&valid(c))await refresh(c,true);return;
   }
   const witness=latest.current.observation;if(!witness||witness===retiredObservation.current||!witness.current())return;
   const request=c.n.makeResumeRequest(witness);if(!request){patch({error:true});return;}
   const prepared=await c.n.previewResume(witness,request,abort.current!.signal);
   if(valid(c))patch({preview:prepared,error:!prepared});
  }catch{if(valid(c))patch({error:true});}finally{leave(c);}
 }
 const observation=props.observation!==retiredObservation.current&&props.observation?.current()?props.observation:null;
 const stalePreview=current.preview&&current.preview.witness.current()!==true;
 const blocked=!props.active||!owner||!props.binding?.native||current.busy;
 return <section aria-label={t('Conversation controls','对话控件')}>
  {current.error?<p role="status">{t('The current conversation could not be checked. Keep the original request and check again.','暂时无法查看当前对话。请保留原请求并再次查询。')}</p>:null}
  {knownHeld&&!current.busy?<p role="status">{t('An original conversation control still needs confirmation. Do not repeat it.','原对话控制请求仍需确认。请勿重复提交。')}</p>:null}
  {current.preview&&!stalePreview?<p>{t('Resume this conversation from its latest recorded response.','从最近记录的回复继续此对话。')}</p>:null}
  {observation?.data.can_stop?<button type="button" disabled={blocked||!inspectionReady||!!current.child||!!current.pointer&&!parentOwner(current.pointer,capture())}
    onClick={()=>void stop()}>{t('Stop response','停止回复')}</button>:null}
  {observation?.data.can_resume?<button type="button" disabled={blocked||!inspectionReady||!!current.pointer||!!current.child}
    onClick={()=>void resume()}>{current.preview&&!stalePreview?t('Resume conversation','继续对话'):t('Review resume','预览继续')}</button>:null}
  <button type="button" disabled={blocked||current.inspection==='checking'} onClick={()=>void check()}>
   {current.busy?t('Checking conversation…','正在查看对话…'):knownHeld?t('Check original control','查看原控制请求'):t('Check conversation status','查看对话状态')}
  </button>
 </section>;
}
