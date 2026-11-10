import { useLayoutEffect, useRef, useState } from 'react';
import { decodeProjectExecutionResource, sameProjectRootProvenance, type ProjectRootHistory } from './project-discovery';
import type { ProjectExecutionResourceRead, ProjectExecutionResourceReader } from './mission';

/** The App supplies its existing Programs/auth/host epoch and currentness test. */
export interface ProjectExecutionInspectionPort {
  readonly read: ProjectExecutionResourceReader;
  readonly generation: string | number;
  readonly current: () => boolean;
}
export interface ProjectExecutionInspectionProps {
  history: ProjectRootHistory;
  rootJobId: string;
  locale: 'en' | 'zh-CN';
  port?: ProjectExecutionInspectionPort;
}
type State = { kind: 'idle' | 'loading' | 'unavailable' | 'changed' } |
  { kind: 'ready'; value: ProjectExecutionResourceRead };

const COPY = {
  en: {
    title: 'Execution details', inspect: 'Inspect execution', refresh: 'Refresh execution details',
    loading: 'Reading this execution…', unavailable: 'Execution details are unavailable from this connection.',
    changed: 'The project history or connection changed. Refresh Programs before inspecting this execution.',
    status: 'Observed status', mode: 'Working mode', durable: 'Durable', attended: 'Attended',
    previous: 'Previous execution', input: 'The original work input is unavailable in this read.',
    adoption: 'The currently adopted plan has not been read.',
    scope: 'This view reads the original execution record. It does not select a current Mission or authorize work.',
    observed: 'Status comes from this execution read; the project history observation is retained separately.',
  },
  'zh-CN': {
    title: '执行详情', inspect: '查看执行', refresh: '刷新执行详情', loading: '正在读取此执行…',
    unavailable: '当前连接无法提供执行详情。', changed: '项目历史或连接已更改。请刷新工作流后再查看此执行。',
    status: '观测状态', mode: '工作模式', durable: '持续执行', attended: '有人值守', previous: '上一次执行',
    input: '此次读取无法提供原始工作输入。', adoption: '尚未读取当前采用的计划。',
    scope: '此视图读取原始执行记录，不选择当前任务，也不授权开展工作。',
    observed: '状态来自此次执行读取；项目历史的观测保持独立。',
  },
};
const STATUS: Record<string, readonly [string,string]> = {
  QUEUED:['Queued','排队中'], RUNNING:['Running','运行中'], CHECKPOINTED:['Checkpointed','已保存进度'],
  RATE_LIMITED:['Rate limited','速率受限'], FAILED:['Failed','失败'], LOST:['Lost','已失联'],
  CANCEL_REQUESTED:['Cancellation requested','已请求取消'], COMPLETED:['Completed','已完成'], CANCELLED:['Cancelled','已取消'],
};
export function projectRootStatusLabel(status:string,locale:'en'|'zh-CN'):string {
  return STATUS[status]?.[locale==='en'?0:1] ?? status;
}
function current(port:ProjectExecutionInspectionPort|undefined):boolean {
  try{return !!port&&port.current();}catch{return false;}
}

/** One explicit, joined display read. No polling, action selection or persistence. */
export function ProjectExecutionInspection({history,rootJobId,locale,port}:ProjectExecutionInspectionProps) {
  const copy=COPY[locale];
  const [state,setState]=useState<State>({kind:'idle'});
  const active=useRef<AbortController|null>(null);
  const frame=useRef({history,rootJobId,generation:port?.generation,read:port?.read});
  const next={history,rootJobId,generation:port?.generation,read:port?.read};
  const sameFrame=frame.current.history===history&&frame.current.rootJobId===rootJobId
    &&frame.current.generation===port?.generation&&frame.current.read===port?.read;
  // Hide stale material during the render itself; cleanup aborts before paint.
  const shown=sameFrame&&current(port)?state:{kind:'idle'} as State;
  useLayoutEffect(()=>{
    frame.current=next;
    active.current?.abort();active.current=null;setState({kind:'idle'});
    return ()=>{active.current?.abort();active.current=null;};
  },[history,rootJobId,port?.generation,port?.read]);
  const read=async()=>{
    if(!port||active.current||!current(port))return;
    const held=frame.current,controller=new AbortController();active.current=controller;
    setState({kind:'loading'});
    const heldCurrent=()=>!controller.signal.aborted&&active.current===controller&&frame.current===held&&current(port);
    try{
      const value=await port.read({workRef:history.work_ref,rootJobId,signal:controller.signal});
      if(!heldCurrent()){
        if(!controller.signal.aborted&&active.current===controller&&frame.current===held)setState({kind:'changed'});
        return;
      }
      const resource=decodeProjectExecutionResource(value.resource,{work_ref:history.work_ref,root_job_id:rootJobId});
      if(!resource)throw Error('PROJECT_EXECUTION_RESOURCE_INVALID');
      if(!sameProjectRootProvenance(history,resource.history)){setState({kind:'changed'});return;}
      setState({kind:'ready',value:{...value,resource}});
    }catch{
      if(heldCurrent())setState({kind:'unavailable'});
    }finally{
      if(active.current===controller)active.current=null;
    }
  };
  const resource=shown.kind==='ready'?shown.value.resource:null;
  const selected=resource?.history.roots.find(row=>row.root_job_id===rootJobId);
  return <section aria-label={copy.title} className="retained-execution-inspection">
    <h3>{copy.title}</h3>
    <p className="muted">{copy.scope}</p>
    {!port?<p role="status">{copy.unavailable}</p>:<>
      <button type="button" className="button" disabled={!current(port)||shown.kind==='loading'} onClick={()=>{void read();}}>
        {shown.kind==='ready'?copy.refresh:copy.inspect}
      </button>
      {shown.kind==='loading'?<p role="status">{copy.loading}</p>:null}
      {shown.kind==='unavailable'?<p role="status">{copy.unavailable}</p>:null}
      {shown.kind==='changed'||!current(port)?<p role="status">{copy.changed}</p>:null}
      {resource&&selected?<>
        <dl>
          <dt>{copy.status}</dt><dd>{projectRootStatusLabel(selected.status,locale)}</dd>
          <dt>{copy.mode}</dt><dd>{resource.original_execution.continuation_mode==='DURABLE'?copy.durable:copy.attended}</dd>
          {resource.original_execution.previous_root_job_id?<><dt>{copy.previous}</dt><dd>{resource.original_execution.previous_root_job_id}</dd></>:null}
        </dl>
        <p>{copy.observed}</p><p>{copy.input}</p><p>{copy.adoption}</p>
      </>:null}
    </>}
  </section>;
}
