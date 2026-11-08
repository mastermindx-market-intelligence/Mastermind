import {useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import type {OperationController} from '../../orchestration/operation-controller';
import {freshConversationTarget,type FreshConversationOriginalSelector} from '../../orchestration/fresh-conversation-target';
import type {FreshNativeConversationWindow} from '../fresh-conversation-reference';
import type {ProjectConversationCatalogueOwner} from '../project-conversation-catalogue-owner';
import {NativeConversationRecord} from '../NativeConversationRecord';
import {FreshConversationContinuation,type FreshConversationContinuationProps} from './FreshConversationContinuation';
import type {FreshConversationOriginalRead} from './fresh-conversation-attended-binding';
import {NativeConversationActions} from './NativeConversationActions';
import type {NativeConversationObservation} from './native-conversation-controls';
import type {NativeFreshConversationObservation} from './useFreshConversationJourney';
type Common=Omit<FreshConversationContinuationProps,'entry'>;
interface BodyProps extends Common {
 selection:FreshConversationOriginalSelector;read:FreshConversationOriginalRead|null;
 observation:NativeConversationObservation|null;refresh:()=>Promise<void>;
 createController?:OperationController;onControlSettled?:()=>Promise<void>|void;
 record?:(held:boolean)=>ReactNode;
 initialConsumption?:FreshNativeConversationWindow['initial_consumption'];
}
/** Native presentation joins the existing attended owner and its actual reader. */
function NativeContinuationBody(props:BodyProps){
 const scope=useMemo(()=>({}),[props.binding,props.host,props.authGeneration,freshConversationTarget(props.selection),props.read]);
 const currentScope=useRef(scope);currentScope.current=scope;
 const empty=()=>({scope,control:false,turn:!!props.read});
 const [storedHold,setHeld]=useState(empty);
 const held=storedHold.scope===scope?storedHold:empty();
 const [pendingRevision,setPendingRevision]=useState(0);
 const latest=useRef(props);latest.current=props;
 const reports=useMemo(()=>{
  const report=(field:'control'|'turn',value:boolean)=>{
   if(currentScope.current!==scope)return;
   setHeld(old=>{
    const current=old.scope===scope?old:{scope,control:false,turn:!!props.read};
    return current[field]===value&&current===old?old:{...current,[field]:value};
   });
  };
  return {control:(value:boolean)=>report('control',value),turn:(value:boolean)=>report('turn',value)};
 },[scope]);
 useEffect(()=>{props.onUnresolvedChange(held.control||held.turn);},[props.onUnresolvedChange,held.control,held.turn]);
 useEffect(()=>()=>props.onUnresolvedChange(false),[props.onUnresolvedChange]);
 const ready=!!props.observation?.current()&&props.observation.data.can_send;
 return <>
  <NativeConversationActions locale={props.locale} active={props.active} host={props.host} authGeneration={props.authGeneration}
   binding={props.binding} selection={props.selection} observation={props.observation} refresh={props.refresh}
   createController={props.createController} onControlSettled={async()=>{setPendingRevision(n=>n+1);await latest.current.onControlSettled?.();}} onUnresolvedChange={reports.control}/>
  {props.record?.(held.control||held.turn)}
  {props.read?<FreshConversationContinuation {...props} pendingRevision={pendingRevision} entry={{kind:'initial',read:props.read,initialConsumption:props.initialConsumption}}
    messageReadOnly={props.messageReadOnly||!ready} onUnresolvedChange={reports.turn}
    onOriginalSettled={()=>{latest.current.onOriginalSettled?.();void latest.current.refresh().catch(()=>{});}}/>:null}
 </>;
}
export interface NativeJourneyContinuationProps extends Common {
 observation:NativeFreshConversationObservation;
 historyOwner:ProjectConversationCatalogueOwner|undefined;
 onControlSettled?:()=>Promise<void>|void;
}
export function NativeJourneyContinuation(props:NativeJourneyContinuationProps){
 const latest=useRef(props);latest.current=props;
 const mounted=useRef(false);useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 const source=props.observation,data=source.data,owner=props.binding?.context(),target=freshConversationTarget(source.selection);
 const original=useMemo<FreshConversationOriginalRead|null>(()=>{
  if(!data?.result||!data.locator?.job_id||!data.locator.attempt_id||!owner)return null;
  const selection=source.selection,result=data.result,locator={...data.locator,job_id:data.locator.job_id,attempt_id:data.locator.attempt_id};
  const principal=owner.principalScope,generation=owner.generation,host=props.host,auth=props.authGeneration,binding=props.binding;
  return {contract:'native-v2',selection,result,locator,current:()=>{
   const p=latest.current,next=p.observation,currentOwner=p.binding?.context();
   return mounted.current&&p.active&&p.host===host&&p.authGeneration===auth&&p.binding===binding&&
    currentOwner?.principalScope===principal&&currentOwner.generation===generation&&next.initialCurrent()&&
    freshConversationTarget(next.selection)===target&&next.data?.result?.digest===result.digest&&
    next.data.locator?.root_job_id===locator.root_job_id&&next.data.locator.job_id===locator.job_id&&next.data.locator.attempt_id===locator.attempt_id;
  }};
 },[target,data?.result?.digest,data?.locator?.root_job_id,data?.locator?.job_id,data?.locator?.attempt_id,
  owner?.principalScope,owner?.generation,props.host,props.authGeneration,props.binding]);
 const observation=useMemo<NativeConversationObservation|null>(()=>data?{selection:source.selection,data,current:source.current}:null,[source,data]);
 return <NativeContinuationBody {...props} selection={source.selection} read={original} observation={observation}
  refresh={source.refresh} createController={source.binding.controller}
  record={held=><NativeRecordedConversation owner={props.historyOwner} read={original} active={props.active} held={held||source.creating||source.observing||!!source.pendingParent} locale={props.locale}/>}/>;
}
/** The canonical history body is acquired only on the user's read gesture. */
function NativeRecordedConversation(props:{owner:ProjectConversationCatalogueOwner|undefined;read:FreshConversationOriginalRead|null;active:boolean;held:boolean;locale:'en'|'zh-CN'}){
 const latest=useRef(props);latest.current=props;
 const [view,setView]=useState<{owner:ProjectConversationCatalogueOwner;read:FreshConversationOriginalRead;window:FreshNativeConversationWindow}|null>(null);
 const [state,setState]=useState<'idle'|'reading'|'unavailable'>('idle'),abort=useRef<AbortController|null>(null);
 const [,rerender]=useState(0),sequence=useRef(0);
 useEffect(()=>{sequence.current++;abort.current?.abort();setView(null);setState('idle');
  return()=>{sequence.current++;abort.current?.abort();};
 },[props.owner,props.read]);
 useEffect(()=>props.owner?.subscribe(()=>rerender(n=>n+1)),[props.owner]);
 const t=(en:string,zh:string)=>props.locale==='zh-CN'?zh:en;
 async function open(){
  const {owner,read}=latest.current;
  if(!owner||!read||!read.current()||latest.current.held||!latest.current.active||state==='reading')return;
  const id=++sequence.current,controller=new AbortController();abort.current?.abort();abort.current=controller;setState('reading');
  const current=()=>sequence.current===id&&!controller.signal.aborted&&latest.current.owner===owner&&latest.current.read===read&&
   latest.current.active&&!latest.current.held&&read.current();
  try{
   await owner.refresh();
   if(!current())return;
   const page=await owner.freshCatalogue({workRef:read.selection.work_ref,signal:controller.signal});if(!current())return;
   const entry=page.entries.find(item=>item.reference.root_job_id===read.locator.root_job_id&&'result_contract'in item&&
    item.result_contract==='mastermind.dsh_native_conversation/v1');if(!entry)throw Error('original missing from bounded catalogue');
   const window=await owner.readFresh(entry.reference,controller.signal);if(!current())return;
   if(window.schema!=='mastermind.fresh_conversation_window.v3'||!window.initial_result||
    window.initial_result.digest!==read.result.digest||window.locator.work_ref!==read.locator.work_ref||
    window.locator.root_job_id!==read.locator.root_job_id||window.locator.job_id!==read.locator.job_id||
    window.locator.attempt_id!==read.locator.attempt_id||!owner.currentFresh(window))throw Error('original mismatch');
   setView({owner,read,window});setState('idle');
  }catch{if(current())setState('unavailable');}
  finally{if(sequence.current===id&&abort.current===controller)setState(value=>value==='reading'?'idle':value);}
 }
 const visible=view&&props.owner===view.owner&&props.read===view.read&&props.active&&view.read.current()&&view.owner.currentFresh(view.window)?view:null;
 return <section aria-label={t('Recorded conversation','已记录对话')}>
  <button type="button" disabled={!props.owner||!props.read?.current()||!props.active||props.held||state==='reading'} onClick={()=>void open()}>
   {state==='reading'?t('Reading conversation…','正在读取对话…'):visible?t('Refresh recorded conversation','刷新已记录对话'):t('Read recorded conversation','读取已记录对话')}
  </button>
  {state==='unavailable'?<p role="status">{t('The original response could not be recovered from the current project history.','暂时无法从当前项目历史恢复原始回复。')}</p>:null}
  {visible?<>
   <NativeConversationRecord input={visible.window.initial_input} result={visible.window.initial_result} locale={props.locale}
    current={()=>latest.current.owner===visible.owner&&latest.current.read===visible.read&&latest.current.active&&visible.read.current()&&visible.owner.currentFresh(visible.window)}
    readInput={signal=>visible.owner.readFreshInput(visible.window,visible.window.initial_input,undefined,signal)}
    readResult={signal=>visible.owner.readFreshResult(visible.window,visible.window.initial_result!,signal)}/>
   {visible.window.turns.map(turn=><section key={turn.turn_key}><NativeConversationRecord input={turn.input} result={turn.result} locale={props.locale}
    current={()=>latest.current.owner===visible.owner&&latest.current.read===visible.read&&latest.current.active&&visible.read.current()&&visible.owner.currentFresh(visible.window)}
    readInput={signal=>visible.owner.readFreshInput(visible.window,turn.input,turn.turn_key,signal)}
    readResult={signal=>visible.owner.readFreshResult(visible.window,turn.result!,signal)}/></section>)}
  </>:null}
 </section>;
}
export interface NativeReferenceContinuationProps extends Common {
 window:FreshNativeConversationWindow;current:()=>boolean;
}
export function NativeReferenceContinuation(props:NativeReferenceContinuationProps){
 const latest=useRef(props);latest.current=props;
 const selection=useMemo(()=>({work_ref:props.window.reference.work_ref,reference:props.window.reference}),[props.window.reference]);
 const [observed,setObserved]=useState<{data:NativeConversationObservation['data'];owner:ReturnType<NonNullable<Common['binding']>['context']>;
  binding:Common['binding'];host:Common['host'];authGeneration:Common['authGeneration'];window:FreshNativeConversationWindow}|null>(null);
 const issued=useRef<typeof observed>(null);
 const abort=useRef<AbortController|null>(null),ticket=useRef(0),busy=useRef(false);
 useEffect(()=>{ticket.current++;abort.current?.abort();busy.current=false;issued.current=null;setObserved(null);
  return()=>{ticket.current++;abort.current?.abort();issued.current=null;};},
  [props.window,props.binding,props.host,props.authGeneration,props.active]);
 const read=useMemo<FreshConversationOriginalRead|null>(()=>{
  const window=props.window,locator=window.locator;
  if(!window.initial_result||!locator.job_id||!locator.attempt_id)return null;
  return {contract:'native-v2',selection,result:window.initial_result,
   locator:{...locator,job_id:locator.job_id,attempt_id:locator.attempt_id},current:()=>latest.current.window===window&&latest.current.active&&latest.current.current()};
 },[props.window,selection]);
 async function refresh(){
  const p=latest.current,b=p.binding,owner=b?.context();if(!p.active||!b?.native||!owner||!p.current()||busy.current)return;
  busy.current=true;const id=++ticket.current,controller=new AbortController();abort.current?.abort();abort.current=controller;
  try{
   const data=await b.native.readCurrent(selection,controller.signal),now=b.context();
   if(id===ticket.current&&!controller.signal.aborted&&latest.current.binding===b&&latest.current.window===p.window&&
    latest.current.host===p.host&&latest.current.authGeneration===p.authGeneration&&latest.current.current()&&
    now?.principalScope===owner.principalScope&&now.generation===owner.generation&&data){
    const next={data,owner,binding:b,host:p.host,authGeneration:p.authGeneration,window:p.window};
    issued.current=next;setObserved(next);
   }
  }finally{if(ticket.current===id)busy.current=false;}
 }
 const observation=useMemo<NativeConversationObservation|null>(()=>observed?{selection,data:observed.data,current:()=>{
  const p=latest.current,owner=p.binding?.context();
  return issued.current===observed&&p.active&&p.current()&&p.window===observed.window&&p.binding===observed.binding&&
   p.host===observed.host&&p.authGeneration===observed.authGeneration&&owner?.principalScope===observed.owner?.principalScope&&owner?.generation===observed.owner?.generation;
 }}:null,[observed,selection]);
 return <NativeContinuationBody {...props} selection={selection} read={read} observation={observation} refresh={refresh}
  initialConsumption={props.window.initial_consumption}/>;
}
