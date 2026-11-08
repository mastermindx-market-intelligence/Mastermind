import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {ProjectConversationCatalogueOwner} from './project-conversation-catalogue-owner';
import type {ProjectExecutionHistoryCatalogue,ProjectExecutionHistoryWindow} from './project-execution-history-contract';
import type {ProjectExecutionPreviousRun} from '../planning/project-execution-transport';
import {FreshConversationInitialResponse} from './new-conversation/NewConversationOutcome';
import './conversations-list.css';

export interface ProjectExecutionHistoryProps {
  workRef:string;owner?:ProjectConversationCatalogueOwner;locale?:'en'|'zh-CN';theme?:'dark'|'light';
  onContinue?:(witness:ProjectExecutionPreviousRun,current:()=>boolean)=>Promise<string|void>|string|void;
}
type Snapshot={owner:ProjectConversationCatalogueOwner;context:NonNullable<ReturnType<ProjectConversationCatalogueOwner['context']>>;
  workRef:string;page:ProjectExecutionHistoryCatalogue};
export function ProjectExecutionHistory(props:ProjectExecutionHistoryProps){
  const live=useRef(props);live.current=props;
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null),[selected,setSelected]=useState<ProjectExecutionHistoryWindow|null>(null);
  const selectedRef=useRef(selected);selectedRef.current=selected;
  const [phase,setPhase]=useState<'idle'|'reading'|'ready'|'unavailable'|'preparing'>('idle');
  const [notice,setNotice]=useState<string|null>(null);
  const pending=useRef<AbortController|null>(null),refreshing=useRef<AbortController|null>(null),mounted=useRef(false),busy=useRef(false);
  const heading=useRef<HTMLHeadingElement>(null),opener=useRef<HTMLButtonElement|null>(null),openerRoot=useRef<string|null>(null);
  const focus=useRef<'reader'|'list'|null>(null);
  const t=(en:string,zh:string)=>props.locale==='zh-CN'?zh:en;
  function current(value:Snapshot|null):value is Snapshot {
    try{return mounted.current&&!!value&&live.current.owner===value.owner&&live.current.workRef===value.workRef&&value.owner.current(value.context);}
    catch{return false;}
  }
  const visible=current(snapshot)?snapshot:null;
  const windowCurrent=()=>!!visible&&!!selected&&visible.owner.currentExecution(selected);
  function cancel(){pending.current?.abort();pending.current=null;refreshing.current=null;busy.current=false;}
  function clear(){setSnapshot(null);selectedRef.current=null;setSelected(null);setNotice(null);}
  useLayoutEffect(()=>{mounted.current=true;return()=>{mounted.current=false;cancel();};},[]);
  useLayoutEffect(()=>{cancel();clear();setPhase('idle');},[props.owner,props.workRef]);
  useEffect(()=>props.owner?.subscribe(()=>{
    // Refresh clears the owner's old identity and membership before acquiring new
    // context. Its own notifications must not cancel that explicit acquisition.
    // The owner still checks auth and selection again before refresh can return.
    const ownRefresh=pending.current!==null&&refreshing.current===pending.current;
    if(!ownRefresh)cancel();clear();if(!ownRefresh)setPhase('idle');
  }),[props.owner]);
  function back(){cancel();selectedRef.current=null;setSelected(null);setNotice(null);setPhase('ready');focus.current='list';}
  // Listen before focusing the reader; a focus handler may immediately send Escape.
  useLayoutEffect(()=>{if(!selected)return;const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();back();}};
    document.addEventListener('keydown',escape);return()=>document.removeEventListener('keydown',escape);},[selected]);
  useLayoutEffect(()=>{
    // Consume the intent before focus handlers can request a return to the list.
    if(focus.current==='reader'&&selected&&visible){focus.current=null;heading.current?.focus();}
    if(focus.current==='list'&&!selected){focus.current=null;if(opener.current?.isConnected)opener.current.focus();else heading.current?.focus();}
  },[selected,visible]);
  async function read(){
    if(busy.current)return;
    const owner=live.current.owner,workRef=live.current.workRef;if(!owner)return;
    busy.current=true;pending.current?.abort();const controller=new AbortController();pending.current=controller;refreshing.current=controller;
    clear();setPhase('reading');
    try{
      await owner.refresh();if(refreshing.current===controller)refreshing.current=null;
      const context=owner.context();
      if(controller.signal.aborted||pending.current!==controller||!context)throw Error();
      const page=await owner.executionCatalogue({workRef,signal:controller.signal});
      const next={owner,context,workRef,page};if(controller.signal.aborted||!current(next))throw Error();
      setSnapshot(next);setPhase('ready');
    }catch{if(mounted.current&&!controller.signal.aborted){setSnapshot(null);setPhase('unavailable');}}
    finally{if(refreshing.current===controller)refreshing.current=null;if(pending.current===controller){pending.current=null;busy.current=false;}}
  }
  async function open(row:ProjectExecutionHistoryCatalogue['entries'][number],button:HTMLButtonElement){
    const captured=snapshot;if(busy.current||!current(captured)||!captured.page.entries.includes(row))return;
    busy.current=true;pending.current?.abort();const controller=new AbortController();pending.current=controller;opener.current=button;openerRoot.current=row.reference.root_job_id;
    setPhase('reading');setNotice(null);
    try{
      const value=await captured.owner.readExecution(row.reference,controller.signal);
      if(controller.signal.aborted||!current(captured))throw Error();
      selectedRef.current=value;setSelected(value);setPhase('ready');focus.current='reader';
    }catch{if(mounted.current&&!controller.signal.aborted){selectedRef.current=null;setSelected(null);setPhase('unavailable');}}
    finally{if(pending.current===controller){pending.current=null;busy.current=false;}}
  }
  async function reply(){
    const captured=snapshot,value=selected,callback=live.current.onContinue,controller=new AbortController();
    const sourceCurrent=()=>!controller.signal.aborted&&current(captured)&&selectedRef.current===value&&!!value&&captured.owner.currentExecution(value);
    if(busy.current||!sourceCurrent()||!value?.parent_witness||!callback)return;
    busy.current=true;pending.current?.abort();pending.current=controller;setPhase('preparing');setNotice(null);
    try{const message=await callback(value.parent_witness,sourceCurrent);
      if(sourceCurrent()){setNotice(typeof message==='string'?message:t('Write your next message in the project form.','请在项目表单中填写下一条消息。'));setPhase('ready');}}
    catch{if(sourceCurrent()){setNotice(t('The next message could not be prepared. Refresh this project and try again.','无法准备下一条消息。请刷新此项目后重试。'));setPhase('ready');}}
    finally{if(pending.current===controller){pending.current=null;busy.current=false;}}
  }
  const status=(state:string)=>state==='COMPLETED'?t('Completed','已完成'):state==='RUNNING'?t('Working','执行中'):
    state==='QUEUED'?t('Queued','已排队'):state==='CANCELLED'?t('Cancelled','已取消'):
    state==='CHECKPOINTED'?t('Checkpoint saved','已保存检查点'):state==='RATE_LIMITED'?t('Waiting for capacity','等待可用容量'):t('Needs attention','需要处理');
  return <section className="conversations-list project-execution-history" data-theme={props.theme??'dark'} lang={props.locale??'en'}
    aria-label={t('Project team conversation','项目团队对话')}>
    <h2 tabIndex={-1} ref={heading}>{t('Project team conversation','项目团队对话')}</h2>
    {!selected?<><p>{t('Open a run to read the team’s work or continue from its completed result.','打开一次执行以查看团队工作，或从已完成的结果继续。')}</p>
      <button type="button" disabled={!props.owner||phase==='reading'||phase==='preparing'} onClick={()=>void read()}>{t('Read project runs','读取项目执行')}</button></>:null}
    {(phase==='reading'||phase==='preparing')?<p role="status">{phase==='preparing'?t('Preparing your next message…','正在准备下一条消息…'):t('Reading project work…','正在读取项目工作…')}</p>:null}
    {notice?<p role="status">{notice}</p>:null}
    {phase==='unavailable'||snapshot&&!visible?<p role="status">{t('Project work is unavailable. Read again to check its current source.','项目工作暂不可用。请重新读取当前来源。')}</p>:null}
    {visible&&selected&&windowCurrent()?<>
      <button type="button" onClick={back}>{t('Back to project runs','返回项目执行')}</button>
      <p>{status(selected.state)}</p>
      <FreshConversationInitialResponse locale={props.locale??'en'} originalMessage={selected.goal} result={selected.result}
        caption={selected.previous_run?t('This run continues the preceding project result.','此执行延续先前的项目结果。'):t('Original project request and team result.','原始项目请求及团队结果。')}/>
      {selected.parent_witness?<button type="button" disabled={!props.onContinue||phase==='preparing'} onClick={()=>void reply()}>{t('Reply to project team','回复项目团队')}</button>:
        <p>{t('Follow-up work becomes available after the team returns a verified result.','团队返回经过验证的结果后，可以继续后续工作。')}</p>}
      <details className="conversations-list__sources"><summary>{t('Run details','执行详情')}</summary>
        <p>{props.workRef}</p><code>{selected.reference.root_job_id}</code>
        <p>{selected.continuation_mode==='DURABLE'?t('The service continues this run after the app closes.','应用关闭后，服务会继续此执行。'):t('This run requires the attended execution session.','此执行需要有人值守的执行会话。')}</p>
        {selected.previous_run?<p>{t('Previous run','前一次执行')}: {selected.previous_run.root_job_id}</p>:null}
      </details>
    </>:visible&&!selected?<>
      {!visible.page.entries.length?<p>{t('No project runs yet. Start work to begin your team conversation.','尚无项目执行。开始工作即可创建团队对话。')}</p>:null}
      {visible.page.entries.map(row=><article className="conversations-list__row" key={row.reference.root_job_id}>
        <div className="conversations-list__row-copy"><h3>{status(row.root_state)}</h3><p>{row.goal}</p></div>
        <button type="button" ref={node=>{if(openerRoot.current===row.reference.root_job_id)opener.current=node;}}
          disabled={phase==='reading'} onClick={event=>void open(row,event.currentTarget)}>{t('Open run','打开执行')}</button>
      </article>)}
      {visible.page.coverage.state==='PARTIAL'?<p>{t('Showing the most recent runs that fit this view.','显示此视图可容纳的最近执行。')}</p>:null}
    </>:null}
  </section>;
}
