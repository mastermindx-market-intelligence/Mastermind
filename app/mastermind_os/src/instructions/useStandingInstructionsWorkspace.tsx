import {useEffect,useLayoutEffect,useRef,useState} from "react";
import {StandingInstructionsPanel} from "./StandingInstructionsPanel";
import {decodeStandingInstructions,validStandingInstructionSelection,type StandingInstructionSelection} from "./standing-instructions";
import {decodeInstructionAdmissionControl,type InstructionAdmissionSelection} from "./instruction-admission";
import {createInstructionAdmissionCommandPort,type InstructionAdmissionSnapshot,type InstructionAdmissionTransport} from "./instruction-command-port";
import {instructionRecoveryContext,readInstructionRecoveryTarget,type InstructionRecoverySnapshot} from "./instruction-recovery";
import {OperationController,type PendingPointerStore} from "../orchestration/operation-controller";
import {serializeInstructionAdmissionTarget} from "../orchestration/instruction-admission-target";
import type {DraftSource} from "../conversations/drafts";
import type {InstructionContentRequest,InstructionControlRequest} from "./instruction-host";
export interface StandingInstructionsWorkspaceProps {
 selection:StandingInstructionSelection|null;authGeneration:number;sourceGeneration?:()=>number;canRead:()=>boolean;
 readContent?:(request:InstructionContentRequest)=>Promise<unknown>;
 readCurrent?:(request:InstructionControlRequest)=>Promise<unknown>;
 transport?:InstructionAdmissionTransport;
 /** Actual incumbent commandBinding.store. Its Executive context is not borrowed. */
 store?:PendingPointerStore;locale:"en"|"zh-CN";
 onChangeInConversation?:(source:DraftSource)=>void;
}
type Source={data:unknown;generation:string;readVersion:number};
type State={scope:string;content:Source|null;control:(Source&{selection:InstructionAdmissionSelection})|null;selected:string|null;reading:boolean;hydrate:number|null;recover:{ref:string;serial:number}|null};
/** App-lifetime read/controller join. Every I/O begins with an explicit user
 * read/review/recover gesture. Default recovery observes only the original ID. */
export function useStandingInstructionsWorkspace(props:StandingInstructionsWorkspaceProps){
 const owner=useRef({content:props.readContent,current:props.readCurrent,transport:props.transport,store:props.store,pause:props.transport?.pause,status:props.transport?.status,epoch:0});
 const prior=owner.current;
 if(prior.content!==props.readContent||prior.current!==props.readCurrent||prior.transport!==props.transport||prior.store!==props.store||prior.pause!==props.transport?.pause||prior.status!==props.transport?.status)
  owner.current={content:props.readContent,current:props.readCurrent,transport:props.transport,store:props.store,pause:props.transport?.pause,status:props.transport?.status,epoch:prior.epoch+1};
 let hostGeneration:number|null=null,authorized=false;
 try{const value=props.sourceGeneration?.();if(typeof value==="number"&&Number.isSafeInteger(value)&&value>=0)hostGeneration=value;authorized=props.canRead()===true;}catch{/* qualified owner absent */}
 const selection=props.selection&&validStandingInstructionSelection(props.selection)?props.selection:null;
 const generation=hostGeneration===null?null:JSON.stringify([props.authGeneration,hostGeneration,owner.current.epoch]);
 const canRead=authorized&&selection!==null&&generation!==null&&typeof props.readContent==="function";
 const scope=JSON.stringify([selection,generation,canRead]);
 const live=useRef(props);live.current=props;
 const proof=useRef({authGeneration:props.authGeneration,hostGeneration});proof.current={authGeneration:props.authGeneration,hostGeneration};
 function qualifiedLive():boolean {
  try{const value=live.current,expected=owner.current;return value.canRead()===true&&proof.current.hostGeneration!==null
   &&value.authGeneration===proof.current.authGeneration&&value.sourceGeneration?.()===proof.current.hostGeneration
   &&value.readContent===expected.content&&value.readCurrent===expected.current&&value.transport===expected.transport
   &&value.transport?.pause===expected.pause&&value.transport?.status===expected.status&&value.store===expected.store;}catch{return false;}
 }
 const liveScope=useRef(scope);liveScope.current=scope;
 const [state,setState]=useState<State|null>(null),[,repaint]=useState(0);
 const current=state?.scope===scope?state:null;
 const selected=current?.selected&&selection?{...selection,instruction_ref:current.selected}:null;
 const content=canRead?current?.content??null:null;
 const control=canRead&&selected&&current?.control?.selection.instruction_ref===selected.instruction_ref?current.control:null;
 const contentSnapshot=useRef<InstructionRecoverySnapshot>({selection:null,data:null,dataGeneration:null,generation:null,canRead:false});
 contentSnapshot.current={selection,data:content?.data??null,dataGeneration:content?.generation??null,generation,canRead};
 const snapshot=useRef<InstructionAdmissionSnapshot>({selection:null,data:null,dataGeneration:null,generation:null,canRead:false});
 snapshot.current={selection:selected,data:control?.data??null,dataGeneration:control?.generation??null,generation,canRead:canRead&&typeof props.readCurrent==="function"};
 const port=useRef<ReturnType<typeof createInstructionAdmissionCommandPort>|null>(null);
 if(!port.current)port.current=createInstructionAdmissionCommandPort(()=>qualifiedLive()?snapshot.current:{...snapshot.current,canRead:false,generation:null,data:null,dataGeneration:null},{
  pause:request=>live.current.transport?live.current.transport.pause(request):Promise.reject(Error("INSTRUCTION_UNAVAILABLE")),
  status:request=>live.current.transport?live.current.transport.status(request):Promise.reject(Error("INSTRUCTION_UNAVAILABLE")),
 });
 const slot=useRef<{store:PendingPointerStore;controller:OperationController}|null>(null);
 if(props.store&&props.transport&&slot.current?.store!==props.store)slot.current={store:props.store,controller:new OperationController(port.current,props.store)};
 const controller=props.store&&props.transport&&slot.current?.store===props.store?slot.current.controller:undefined;
 const controllerScope=JSON.stringify([scope,selected]),committed=useRef({scope:controllerScope,controller}),committedProject=useRef(scope);
 const scopedController=committed.current.scope===controllerScope&&committed.current.controller===controller?controller:undefined;
 const ticket=useRef(0),version=useRef(0),abort=useRef<AbortController|null>(null),serial=useRef(0);
 useLayoutEffect(()=>{
  if(committedProject.current!==scope){committedProject.current=scope;setState(null);}
  if(committed.current.scope!==controllerScope||committed.current.controller!==controller){
   committed.current.controller?.invalidate();if(committed.current.controller!==controller)controller?.invalidate();
   abort.current?.abort();ticket.current++;committed.current={scope:controllerScope,controller};repaint(value=>value+1);
  }
 },[controllerScope,controller,scope]);
 useEffect(()=>()=>{abort.current?.abort();committed.current.controller?.invalidate();},[]);
 function empty():State{return {scope,content:null,control:null,selected:null,reading:false,hydrate:null,recover:null};}
 function release(started:string,request:number,pending:AbortController):boolean {
  try{return !pending.signal.aborted&&ticket.current===request&&liveScope.current===started&&live.current.canRead()===true
   &&live.current.authGeneration===props.authGeneration&&live.current.sourceGeneration?.()===hostGeneration;}catch{return false;}
 }
 async function readContent(){
  if(!canRead||!selection||!generation||!live.current.readContent)return;
  const started=scope,request=++ticket.current,pending=new AbortController();abort.current?.abort();abort.current=pending;
  setState(value=>({...((value?.scope===started?value:null)??empty()),content:null,control:null,reading:true,hydrate:null,recover:null}));
  try{
   const raw=await live.current.readContent({selection:{...selection},signal:pending.signal}),body=decodeStandingInstructions(raw,selection);
   if(!body)throw Error("INSTRUCTION_CONTENT_INVALID");if(!release(started,request,pending))return;
   setState(value=>value?.scope===started?{...value,content:{data:body,generation,readVersion:++version.current},reading:false}:value);
  }catch{if(release(started,request,pending))setState(value=>value?.scope===started?{...value,reading:false}:value);}
 }
 async function readCurrent(ref=current?.selected??null){
  if(!canRead||!selection||!generation||!ref||!live.current.readCurrent)return;
  const target={...selection,instruction_ref:ref};if(serializeInstructionAdmissionTarget(target)===null)return;
  const started=scope,request=++ticket.current,pending=new AbortController();abort.current?.abort();abort.current=pending;
  setState(value=>({...((value?.scope===started?value:null)??empty()),selected:ref,control:null,reading:true,hydrate:null,recover:null}));
  try{
   const raw=await live.current.readCurrent({selection:target,signal:pending.signal}),body=decodeInstructionAdmissionControl(raw,target);
   if(!body)throw Error("INSTRUCTION_CONTROL_INVALID");if(!release(started,request,pending))return;
   const identity=instructionRecoveryContext(contentSnapshot.current);
   if(body.owner_context&&identity&&body.owner_context.principal_scope!==identity.principalScope){setState(value=>value?.scope===started?{...value,reading:false}:value);return;}
   const readVersion=++version.current;
   setState(value=>value?.scope===started&&value.selected===ref?{...value,control:{selection:target,data:body,generation,readVersion},reading:false,hydrate:readVersion}:value);
  }catch{if(release(started,request,pending))setState(value=>value?.scope===started?{...value,reading:false}:value);}
 }
 const handled=useRef(0);
 useLayoutEffect(()=>{
  if(!current?.recover||current.recover.serial===handled.current)return;
  handled.current=current.recover.serial;void readCurrent(current.recover.ref);
 },[current?.recover,scope]);
 const hydrated=useRef(0);
 useLayoutEffect(()=>{
  if(!control||current?.hydrate!==control.readVersion||hydrated.current===control.readVersion||!controller||!canRead)return;
  hydrated.current=control.readVersion;
  if(!port.current!.context()){setState(value=>value?.scope===scope?{...value,hydrate:null}:value);return;}
  const started=scope,readVersion=control.readVersion;
  setState(value=>value?.scope===started?{...value,reading:true,hydrate:null}:value);
  void controller.recover().then(result=>{
   if(liveScope.current!==started)return;
   setState(value=>value?.scope===started&&value.control?.readVersion===readVersion?{...value,reading:false,control:result.status==="accepted"||result.status==="refused"?null:value.control}:value);repaint(value=>value+1);
  },()=>{if(liveScope.current===started){setState(value=>value?.scope===started?{...value,reading:false}:value);repaint(value=>value+1);}});
 },[control,current?.hydrate,controller,canRead,scope]);
 async function findOriginal(){
  if(!canRead||!props.store||!generation)return;
  const started=scope,request=++ticket.current,pending=new AbortController();abort.current?.abort();abort.current=pending;
  try{
   const found=await readInstructionRecoveryTarget(()=>qualifiedLive()?contentSnapshot.current:{...contentSnapshot.current,canRead:false,generation:null,data:null,dataGeneration:null},props.store,pending.signal);
   if(!found||!release(started,request,pending))return;
   setState(value=>value?.scope===started?{...value,selected:found.selection.instruction_ref,control:null,hydrate:null,recover:{ref:found.selection.instruction_ref,serial:++serial.current}}:value);
  }catch{/* Unavailable/corrupt store stays held. Never clear or replace it. */}
 }
 const context=scopedController?port.current.context():null;
 return <StandingInstructionsPanel selection={selection} selectedInstructionRef={current?.selected??null} canRead={canRead}
  sourceGeneration={generation??"SOURCE_UNAVAILABLE"} content={content} control={control} reading={current?.reading}
  controller={scopedController} locale={props.locale} onChangeInConversation={props.onChangeInConversation?source=>{
   if(qualifiedLive()&&liveScope.current===scope)live.current.onChangeInConversation?.(source);
  }:undefined}
  operation={context&&selected&&scopedController?{state:scopedController.getState(),selection:selected,generation:generation!,principalScope:context.principalScope}:undefined}
  onReadInstructions={props.readContent?()=>void readContent():undefined}
  onSelectInstruction={ref=>setState(value=>({...((value?.scope===scope?value:null)??empty()),selected:ref,control:null,hydrate:null,recover:null}))}
  onReadCurrent={props.readCurrent?()=>void readCurrent():undefined}
  onFindOriginal={props.store&&props.transport?()=>void findOriginal():undefined}
  onControlConsumed={(target,sourceGeneration,readVersion)=>{
   if(liveScope.current===scope&&sourceGeneration===generation)setState(value=>value?.scope===scope&&value.control?.readVersion===readVersion
    &&value.control.selection.work_ref===target.work_ref&&value.control.selection.instruction_ref===target.instruction_ref?{...value,control:null}:value);
  }}/>;
}
