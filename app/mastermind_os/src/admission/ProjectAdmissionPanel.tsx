import { useRef, useState } from "react";
import type { OperationController, OperationState } from "../orchestration/operation-controller";
import { decodeProjectAdmissionControl, validProjectAdmissionSelection, type ProjectAdmissionSelection } from "./project-admission";
import "./project-admission.css";

export interface ProjectAdmissionPanelProps {
  selection: ProjectAdmissionSelection | null;
  canRead: boolean;
  sourceGeneration: string;
  /** Body retained by the actual host read under this generation. */
  source: { data: unknown; generation: string; readVersion: number } | null;
  reading?: boolean;
  onReadCurrent?: () => void;
  /** Existing controller, with its actual durable pending-pointer store. */
  controller?: OperationController;
  /** Withdraw this read in its App-lifetime owner after an operation settles. */
  onOperationSettled?: (state:OperationState)=>void;
  locale?: "en" | "zh-CN";
}
const COPY = {
  en: {
    title:"New work", note:"Stops new work for this project. Work already running may continue.",
    read:"Check pause status", reading:"Reading…", unavailable:"Project admission controls are unavailable.",
    idle:"Project admission status has not been read here.", paused:"New work paused", open:"New work is not paused here. Other limits and permissions still apply.",
    pause:"Pause new work", resume:"Resume new work", pending:"Request in progress…", accepted:"Request committed",
    historical:"This request receipt is historical. Read project status to confirm the current gate.",
    refused:"Request declined", unknown:"The original request outcome is unresolved. Do not resend it, choose another destination, or create a replacement request.",
    localHold:"The pending request state could not be read. New requests are held until that state can be checked.",
    check:"Check original project request", details:"Source details", scope:"Project", current:"Current transition", noPermission:"This read does not supply current permission for this action.", refresh:"Check pause status to see the current setting.", noController:"Project controls are not connected here.",
  },
  "zh-CN": {
    title:"新工作", note:"停止此项目的新工作；已在运行的工作可能继续。",
    read:"读取项目状态", reading:"读取中…", unavailable:"暂时无法使用项目准入控制。",
    idle:"此处尚未读取项目准入状态。", paused:"新工作已暂停", open:"此处未暂停新工作，仍须满足其他限制和权限。",
    pause:"暂停新工作", resume:"恢复新工作", pending:"正在处理请求…", accepted:"请求已提交生效",
    historical:"此请求回执属于历史记录。请读取项目状态以确认当前准入状态。",
    refused:"请求未获准", unknown:"原请求结果尚不明确。请勿重发、改用其他目标或创建替代请求。",
    localHold:"无法读取待处理请求状态。确认该状态之前，暂不接受新请求。",
    check:"检查原始项目请求", details:"来源详情", scope:"项目", current:"当前变更", noPermission:"此读取未提供执行此操作的当前许可。", refresh:"请检查暂停状态以查看当前设置。", noController:"此处尚未接入项目控制。",
  },
} as const;
export function ProjectAdmissionPanel(props: ProjectAdmissionPanelProps) {
  const {selection,source,sourceGeneration,canRead,controller,reading,onReadCurrent,locale="en"}=props;
  const t=COPY[locale];
  const scope=JSON.stringify([selection,sourceGeneration,canRead]);
  const currentScope=useRef(scope);currentScope.current=scope;
  const [busy,setBusy]=useState(false);
  const [withheldRead,setWithheldRead]=useState<string|null>(null);
  const readKey=source ? JSON.stringify([scope,source.readVersion]) : null;
  const [request,setRequest]=useState<{scope:string;state:OperationState}|null>(null);
  const valid=selection !== null && validProjectAdmissionSelection(selection);
  const data=canRead && valid && readKey!==withheldRead && source?.generation===sourceGeneration ? decodeProjectAdmissionControl(source.data,selection) : null;
  const qualified=data?.availability === "AVAILABLE" ? data : null;
  const controllerState=controller?.getState();
  const localStoreHold=(state:OperationState|null|undefined)=>state?.status==="idle" && (state.reason==="LOCAL_UNAVAILABLE" || state.reason==="MALFORMED_POINTER");
  const state=request?.scope===scope ? request.state : controllerState && (controllerState.status!=="idle" || localStoreHold(controllerState)) ? controllerState : null;
  // Any unresolved original pointer, including a different operation kind,
  // holds new submissions in the same incumbent controller/store scope.
  const unresolved=state?.status==="unknown" || state?.status==="checking" || state?.status==="submitting" || localStoreHold(state);
  const canAct=qualified !== null && controller !== undefined && !busy && !reading && !unresolved;
  async function perform(resume:boolean) {
    if (!canAct || !selection || !qualified || !controller) return;
    if (resume ? !qualified.permissions.resume || qualified.state!=="PAUSED" || !qualified.pause_token : !qualified.permissions.pause || qualified.state==="PAUSED") return;
    const selected={...selection}, started=scope;
    const payload=resume ? {selection:selected,pause_token:{...qualified.pause_token!}} : {selection:selected};
    setBusy(true);
    const promise=controller.begin({kind:resume ? "project_resume" : "project_pause",targetKey:selected.work_ref,payload});
    setRequest({scope:started,state:controller.getState()});
    try {
      const result=await promise;
      if(currentScope.current===started){setRequest({scope:started,state:result});setWithheldRead(readKey);props.onOperationSettled?.(result);}
    } finally {setBusy(false);}
  }
  async function recover() {
    if(!controller || !canRead || !valid || busy || reading)return;
    const started=scope;setBusy(true);
    const promise=controller.recover();setRequest({scope:started,state:controller.getState()});
    try {const result=await promise;if(currentScope.current===started){setRequest({scope:started,state:result});if(result.status==="accepted"){setWithheldRead(readKey);props.onOperationSettled?.(result);}}}
    finally {setBusy(false);}
  }
  return <section className="project-admission" aria-label={t.title} lang={locale}>
    <div className="project-admission__intro"><h3>{t.title}</h3><p>{t.note}</p></div>
    <p role="status">{qualified ? qualified.state==="PAUSED" ? t.paused : t.open : withheldRead===readKey && source ? t.refresh : source ? t.unavailable : t.idle}</p>
    {qualified && !controller && <p>{t.noController}</p>}
    {qualified && controller && !(qualified.state==="PAUSED" ? qualified.permissions.resume : qualified.permissions.pause) && <p>{t.noPermission}</p>}
    {state?.status==="accepted" && !busy && <p>{t.accepted}. {t.historical}</p>}
    {state?.status==="refused" && !busy && <p>{t.refused}</p>}
    {busy && !unresolved && <p role="status">{t.pending}</p>}
    {unresolved && <p className="project-admission__unknown" role="alert">{(state?.status==="unknown" || localStoreHold(state)) && !busy ? state?.pointer ? t.unknown : t.localHold : t.pending}</p>}
    <div className="project-admission__actions">
      {onReadCurrent && <button type="button" disabled={!canRead || !valid || reading || busy} onClick={onReadCurrent}>{reading ? t.reading : t.read}</button>}
      {qualified && qualified.state!=="PAUSED" && qualified.permissions.pause && <button type="button" disabled={!canAct} onClick={()=>void perform(false)}>{t.pause}</button>}
      {qualified?.state==="PAUSED" && qualified.permissions.resume && <button type="button" disabled={!canAct} onClick={()=>void perform(true)}>{t.resume}</button>}
      {unresolved && <button type="button" disabled={!canRead || !valid || !controller || busy || reading} onClick={()=>void recover()}>{t.check}</button>}
    </div>
    {qualified && <details className="project-admission__details"><summary>{t.details}</summary>
      <dl><dt>{t.scope}</dt><dd>{qualified.selection.work_ref}</dd>
        {qualified.current_receipt && <><dt>{t.current}</dt><dd>{qualified.current_receipt.command_id}</dd></>}
      </dl>
    </details>}
  </section>;
}
