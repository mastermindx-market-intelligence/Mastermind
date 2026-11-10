import {useRef,useState} from "react";
import type {OperationController,OperationState} from "../orchestration/operation-controller";
import type {DraftSource} from "../conversations/drafts";
import {serializeInstructionAdmissionTarget} from "../orchestration/instruction-admission-target";
import {decodeStandingInstructions,type StandingInstructionSelection} from "./standing-instructions";
import {decodeInstructionAdmissionControl,type InstructionAdmissionSelection} from "./instruction-admission";
import {instructionDraftSource} from "./instruction-draft-source";
import "./standing-instructions.css";
export interface StandingInstructionsPanelProps {
 selection:StandingInstructionSelection|null;selectedInstructionRef:string|null;canRead:boolean;sourceGeneration:string;
 content:{data:unknown;generation:string;readVersion:number}|null;
 control:{data:unknown;selection:InstructionAdmissionSelection;generation:string;readVersion:number}|null;
 reading?:boolean;controller?:OperationController;locale?:"en"|"zh-CN";
 /** Existing App controller owner fences this slot on identity/generation/selection. */
 operation?:{state:OperationState;selection:InstructionAdmissionSelection;generation:string;principalScope:string};
 onReadInstructions?:()=>void;onSelectInstruction?:(instruction_ref:string)=>void;onReadCurrent?:()=>void;onFindOriginal?:()=>void;
 /** Existing App source owner withholds this exact read across route remounts. */
 onControlConsumed:(selection:InstructionAdmissionSelection,generation:string,readVersion:number)=>void;
 /** Existing unsent-draft insertion owner preserves prior text/revision/Undo. */
 onChangeInConversation?:(source:DraftSource)=>void;
}
const COPY={
 en:{title:"Standing instructions",intro:"Review the instructions supplied for this project.",read:"Read instructions",reading:"Reading…",idle:"Instructions have not been read here.",unavailable:"Standing instructions are unavailable.",absent:"No standing instructions were declared for this project.",empty:"This project currently supplies an empty instruction list.",review:"Review instruction",detail:"Instruction",choose:"Select an instruction to review its text and current controls.",removed:"The selected instruction is not supplied in the current project content.",change:"Change in conversation",draft:"Adds this instruction to the existing unsent draft. Nothing is sent or published.",noDraft:"An existing conversation draft is not connected here.",pause:"Pause this instruction",note:"Stops new work from this instruction. Other project work and work already running may continue.",paused:"New work from this instruction is paused.",open:"This instruction is not paused here. Other limits and permissions still apply.",check:"Check instruction status",recover:"Check original instruction request",unknown:"The original request outcome is unresolved. Do not resend it, choose another destination, or create a replacement request.",pending:"Request in progress…",committed:"Pause request committed. Check current status to confirm the current setting.",refused:"Request declined.",refresh:"Check instruction status to see the current setting.",controls:"Instruction controls are unavailable.",noController:"Instruction controls are not connected here.",changed:"The instruction or its source changed. Read the current content and status before pausing it.",source:"Source details",project:"Project",reference:"Instruction reference",revision:"Content revision",commit:"Source commit",digest:"Source content hash",currentInstruction:"Current instruction",recorded:"Recorded pause request",request:"Command ID",event:"Event ID",recordedAt:"Pause recorded at",changedAfterPause:"The instruction text changed after this pause was recorded. It is still paused."},
 "zh-CN":{title:"常设指令",intro:"查看此项目提供的指令。",read:"读取指令",reading:"读取中…",idle:"此处尚未读取指令。",unavailable:"暂时无法获取常设指令。",absent:"此项目未声明常设指令。",empty:"此项目当前提供的指令列表为空。",review:"查看指令",detail:"指令",choose:"选择一条指令，查看其内容和当前控制。",removed:"当前项目内容未提供所选指令。",change:"在对话中修改",draft:"将此指令加入现有未发送草稿，不会发送或发布。",noDraft:"此处尚未接入现有对话草稿。",pause:"暂停此指令",note:"停止由此指令产生的新工作；其他项目工作及已在运行的工作可能继续。",paused:"此指令产生的新工作已暂停。",open:"此处未暂停该指令，仍须满足其他限制和权限。",check:"检查指令状态",recover:"检查原始指令请求",unknown:"原请求结果尚不明确。请勿重发、改用其他目标或创建替代请求。",pending:"正在处理请求…",committed:"暂停请求已提交生效。请检查当前状态以确认当前设置。",refused:"请求未获准。",refresh:"请检查指令状态以查看当前设置。",controls:"暂时无法使用指令控制。",noController:"此处尚未接入指令控制。",changed:"指令或其来源已更改。请读取当前内容和状态后再暂停。",source:"来源详情",project:"项目",reference:"指令引用",revision:"内容版本",commit:"来源提交",digest:"来源内容哈希",currentInstruction:"当前指令",recorded:"已记录的暂停请求",request:"命令标识",event:"事件标识",recordedAt:"暂停记录时间",changedAfterPause:"此暂停记录之后指令文字已更改，指令仍处于暂停状态。"},
} as const;
export function StandingInstructionsPanel(props:StandingInstructionsPanelProps){
 const {selection,selectedInstructionRef,content,control,canRead,sourceGeneration,controller,reading,locale="en"}=props,t=COPY[locale];
 const scope=JSON.stringify([selection,selectedInstructionRef,canRead,sourceGeneration]),live=useRef(scope);live.current=scope;
 const [busy,setBusy]=useState(false),[request,setRequest]=useState<{scope:string;state:OperationState}|null>(null),[withheld,setWithheld]=useState<string|null>(null);
 const document=selection&&canRead&&content?.generation===sourceGeneration?decodeStandingInstructions(content.data,selection):null;
 const available=document?.availability==="AVAILABLE"?document:null;
 const row=available?.instructions.find(item=>item.instruction_ref===selectedInstructionRef);
 const selected=selection&&selectedInstructionRef?{...selection,instruction_ref:selectedInstructionRef}:null;
 const readKey=control?JSON.stringify([scope,control.readVersion]):null;
 const sameSelection=selected&&control&&selected.work_ref===control.selection.work_ref&&selected.instruction_ref===control.selection.instruction_ref;
 const gate=selected&&sameSelection&&canRead&&control?.generation===sourceGeneration&&withheld!==readKey?decodeInstructionAdmissionControl(control.data,selected):null;
 const qualified=gate?.availability==="AVAILABLE"?gate:null;
 const identity=gate?.owner_context?.principal_scope??(available?.schema==="mastermind.workspace_project_instructions.v2"?available.recovery_identity?.principal_scope:undefined);
 const operation=props.operation;
 const external=canRead&&selected&&operation?.generation===sourceGeneration&&operation.selection.work_ref===selected.work_ref
  &&operation.selection.instruction_ref===selected.instruction_ref&&(!identity||identity===operation.principalScope)?operation.state:null;
 const state=request?.scope===scope?request.state:external;
 const unresolved=state?.status==="unknown"||state?.status==="checking"||state?.status==="submitting";
 const matched=!!(row&&available&&qualified&&row.revision===qualified.instruction_revision
  &&available.source.repository===qualified.source.repository&&available.source.commit===qualified.source.commit
  &&available.source.path===qualified.source.path&&available.source.content_sha256===qualified.source.content_sha256);
 const recorded=qualified?.current_receipt;
 const recordedClock=recorded?(Number.isFinite(new Date(recorded.committed_at_ms).getTime())?new Date(recorded.committed_at_ms).toISOString():`${recorded.committed_at_ms} ms (Unix)`):null;
 const canPause=matched&&qualified?.state==="NOT_SUSPENDED"&&qualified.permission.pause&&controller&&!busy&&!reading&&!unresolved;
 async function pause(){
  if(!canPause||!controller||!qualified||!selected||!control)return;
  const started=scope,version=control.readVersion,target=serializeInstructionAdmissionTarget(selected);if(!target)return;
  setBusy(true);
  const pending=controller.begin({kind:"instruction_pause",targetKey:target,payload:{selection:{...selected},expected_revision:qualified.instruction_revision,expected_source:{...qualified.source}}});
  setRequest({scope:started,state:controller.getState()});
  try{const result=await pending;props.onControlConsumed(selected,sourceGeneration,version);if(live.current===started){setRequest({scope:started,state:result});setWithheld(readKey);}}
  finally{setBusy(false);}
 }
 function change(){
  if(!row||!available||!selection||!props.onChangeInConversation)return;
  const source=instructionDraftSource(available,selection,row.instruction_ref);if(source)props.onChangeInConversation(source);
 }
 async function recover(){
  if(!canRead||busy||reading)return;
  if(!controller||!unresolved||!selected){props.onFindOriginal?.();return;}
  const started=scope;setBusy(true);
  const pending=controller.recover();setRequest({scope:started,state:controller.getState()});
  try{const result=await pending;if(live.current===started){setRequest({scope:started,state:result});if(result.status==="accepted"){setWithheld(readKey);if(control)props.onControlConsumed(selected,sourceGeneration,control.readVersion);}}}
  finally{setBusy(false);}
 }
 return <section className="standing-instructions" aria-label={t.title} lang={locale}>
  <header><div><h3>{t.title}</h3><p>{t.intro}</p></div><button disabled={!canRead||!selection||reading||busy||!props.onReadInstructions} onClick={props.onReadInstructions}>{reading?t.reading:t.read}</button></header>
  {!document&&<p role="status">{content?t.unavailable:t.idle}</p>}
  {document?.availability==="UNAVAILABLE"&&<p role="status">{t.unavailable}</p>}
  {available?.instructions.length===0&&<p role="status">{available.declaration==="NOT_DECLARED"?t.absent:t.empty}</p>}
  {available&&available.instructions.length>0&&<ul className="standing-instructions__list">{available.instructions.map(item=><li key={item.instruction_ref} className="standing-instructions__card" data-selected={item.instruction_ref===selectedInstructionRef}><p>{Array.from(item.text).slice(0,160).join("")}{Array.from(item.text).length>160?"…":""}</p><button aria-label={`${t.review}: ${Array.from(item.text).slice(0,80).join("")}`} onClick={()=>props.onSelectInstruction?.(item.instruction_ref)} disabled={!props.onSelectInstruction||busy}>{t.review}</button></li>)}</ul>}
  <article className="standing-instructions__card"><h4>{t.detail}</h4>
   {!selected?<p>{t.choose}</p>:!row?<p>{available?t.removed:t.unavailable}</p>:<><p className="standing-instructions__text">{row.text}</p><button onClick={change} disabled={!props.onChangeInConversation||busy}>{t.change}</button><p className="standing-instructions__muted">{props.onChangeInConversation?t.draft:t.noDraft}</p></>}
   {selected&&<><p>{t.note}</p><p role="status">{qualified?qualified.state==="PAUSED"?t.paused:matched?t.open:t.changed:withheld===readKey&&control?t.refresh:t.controls}</p>
    {matched&&qualified?.state==="PAUSED"&&recorded&&row?.revision!==recorded.revision&&<p>{t.changedAfterPause}</p>}
    {qualified&&!controller&&<p>{t.noController}</p>}
    {state?.status==="accepted"&&<p>{t.committed}</p>}{state?.status==="refused"&&<p>{t.refused}</p>}
    {unresolved&&<p className="standing-instructions__notice" role="alert">{busy?t.pending:t.unknown}</p>}
    <div className="standing-instructions__actions"><button disabled={!canRead||busy||reading||!props.onReadCurrent} onClick={props.onReadCurrent}>{t.check}</button><button disabled={!canPause} onClick={()=>void pause()}>{t.pause}</button></div>
   </>}
   <button disabled={!canRead||(!available&&!unresolved)||busy||reading||(!props.onFindOriginal&&!(controller&&unresolved))} onClick={()=>void recover()}>{t.recover}</button>
   {canRead&&(available||gate?.owner_context)&&<details><summary>{t.source}</summary>{row&&<h5>{t.currentInstruction}</h5>}<dl><dt>{t.project}</dt><dd>{selection?.work_ref}</dd><dt>{t.reference}</dt><dd>{selectedInstructionRef}</dd><dt>{t.revision}</dt><dd>{row?.revision}</dd><dt>{t.commit}</dt><dd>{available?.source.commit}</dd><dt>{t.digest}</dt><dd>{available?.source.content_sha256}</dd></dl>{recorded&&<><h5>{t.recorded}</h5><dl><dt>{t.revision}</dt><dd>{recorded.revision}</dd><dt>{t.commit}</dt><dd>{recorded.source.commit}</dd><dt>{t.digest}</dt><dd>{recorded.source.content_sha256}</dd><dt>{t.request}</dt><dd>{recorded.command_id}</dd><dt>{t.event}</dt><dd>{recorded.event_id}</dd><dt>{t.recordedAt}</dt><dd>{recordedClock}</dd></dl></>}</details>}
  </article>
 </section>;
}
