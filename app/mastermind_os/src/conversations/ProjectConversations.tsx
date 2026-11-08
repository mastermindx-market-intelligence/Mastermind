import {useEffect,useId,useLayoutEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import type {ProjectConversationCatalogue,ProjectConversationRead} from './project-conversation-catalogue-contract';
import type {ProjectConversationCatalogueOwner} from './project-conversation-catalogue-owner';
import {SourceMarkdown} from './SourceMarkdown';
import {FreshConversationInitialResponse} from './new-conversation/NewConversationOutcome';
import {freshConversationNextPage,freshConversationInput,type FreshConversationHistoryCatalogue as FreshConversationCatalogue,
  type FreshConversationHistoryWindow as FreshConversationWindow,type FreshConversationReference} from './fresh-conversation-reference';
import {NativeConversationRecord} from './NativeConversationRecord';
import './conversations-list.css';

export interface ProjectConversationsProps {
  workRef:string;
  /** Actual selected-project name, never inferred from reply content. */
  projectTitle?:string;
  owner?:ProjectConversationCatalogueOwner;
  locale?:'en'|'zh-CN';theme?:'dark'|'light';
  /** Optional actual attended owner composition. READ data/currentness never
   * grants Keep/Send/Check; the parent supplies their independent live ports. */
  renderFreshContinuation?:(source:{window:FreshConversationWindow;reference:FreshConversationReference;
    current:()=>boolean;invalidate:()=>void;refresh:()=>void})=>ReactNode;
}
type Snapshot={owner:ProjectConversationCatalogueOwner;context:NonNullable<ReturnType<ProjectConversationCatalogueOwner['context']>>;
  workRef:string;page:ProjectConversationCatalogue|null;fresh:FreshConversationCatalogue|null};
type FreshHistory={window:FreshConversationWindow;turns:FreshConversationWindow['turns'];next:number|null;busy:boolean;unavailable:boolean;older:boolean};

/** A genuine retained-session list and bounded owned-turn reader. Catalogue
 * and body reads require explicit gestures. Back preserves the current page
 * and filter; reopen always re-reads the selected original session window. */
export function ProjectConversations(props:ProjectConversationsProps){
  const live=useRef(props);live.current=props;
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null),[conversation,setConversation]=useState<ProjectConversationRead|null>(null);
  const [freshWindow,setFreshWindow]=useState<FreshConversationWindow|null>(null);
  const [freshHistory,setFreshHistory]=useState<FreshHistory|null>(null);
  const historyLive=useRef(freshHistory);historyLive.current=freshHistory;
  const liveFresh=useRef(freshWindow);liveFresh.current=freshWindow;
  const bodyLive=useRef(false);
  const [phase,setPhase]=useState<'idle'|'reading'|'ready'|'unavailable'>('idle'),[query,setQuery]=useState('');
  const [,changed]=useState(0);const pending=useRef<AbortController|null>(null),heading=useRef<HTMLHeadingElement>(null);
  const openButton=useRef<HTMLButtonElement|null>(null),focusAfter=useRef<'reader'|'list'|null>(null);
  const openReference=useRef<string|null>(null),rowButtons=useRef(new Map<string,HTMLButtonElement>());
  const filterId=useId();
  const zh=props.locale==='zh-CN',t=(en:string,cn:string)=>zh?cn:en;
  function current(value:Snapshot|null){try{return bodyLive.current&&!!value&&live.current.owner===value.owner&&live.current.workRef===value.workRef&&value.owner.current(value.context);}catch{return false;}}
  const visible=current(snapshot)?snapshot:null;
  const readerOpen=!!conversation||!!freshWindow;
  useLayoutEffect(()=>{bodyLive.current=true;return()=>{bodyLive.current=false;};},[]);
  useLayoutEffect(()=>{pending.current?.abort();setSnapshot(null);setConversation(null);setFreshWindow(null);setFreshHistory(null);setPhase('idle');},[props.owner,props.workRef]);
  useEffect(()=>props.owner?.subscribe(()=>{setConversation(null);setFreshWindow(null);setFreshHistory(null);changed(value=>value+1);}),[props.owner]);
  useEffect(()=>()=>pending.current?.abort(),[]);
  function back(){pending.current?.abort();setConversation(null);setFreshWindow(null);setFreshHistory(null);setPhase('ready');focusAfter.current='list';}
  // Listen before focusing the reader; a focus handler may immediately send Escape.
  useLayoutEffect(()=>{if(!readerOpen)return;const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();back();}};
    window.addEventListener('keydown',escape);return()=>window.removeEventListener('keydown',escape);},[readerOpen]);
  useLayoutEffect(()=>{
    // Consume the intent before focus handlers can request a return to the list.
    if(focusAfter.current==='reader'&&readerOpen&&visible){focusAfter.current=null;heading.current?.focus();}
    else if(focusAfter.current==='list'&&!readerOpen){
      focusAfter.current=null;const restored=openReference.current?rowButtons.current.get(openReference.current):null;
      if(restored?.isConnected)restored.focus();else if(openButton.current?.isConnected)openButton.current.focus();else heading.current?.focus();
    }
  },[readerOpen,visible]);
  async function read(cursor?:string){
    const owner=live.current.owner,work=live.current.workRef;
    if(!owner||(cursor&&(!current(snapshot)||snapshot?.page?.next_cursor!==cursor)))return;
    pending.current?.abort();const controller=new AbortController();pending.current=controller;
    setPhase('reading');setConversation(null);setFreshWindow(null);setFreshHistory(null);
    try{
      if(cursor===undefined)await owner.refresh();
      const context=owner.context();if(!context||controller.signal.aborted||live.current.owner!==owner||live.current.workRef!==work)throw Error();
      const [legacy,fresh]=await Promise.allSettled([
        owner.catalogue({workRef:work,...(cursor?{cursor}:{}),signal:controller.signal}),
        cursor?Promise.resolve(snapshot?.fresh??null):owner.freshCatalogue({workRef:work,signal:controller.signal}),
      ]);
      const page=legacy.status==='fulfilled'?legacy.value:null,freshPage=fresh.status==='fulfilled'?fresh.value:null;
      if(!page&&!freshPage)throw Error();
      const next={owner,context,workRef:work,page,fresh:freshPage};if(controller.signal.aborted||!current(next))throw Error();
      setSnapshot(next);setPhase('ready');
    }catch{if(!controller.signal.aborted){setSnapshot(null);setConversation(null);setFreshWindow(null);setFreshHistory(null);setPhase('unavailable');}}
  }
  async function open(row:ProjectConversationCatalogue['conversations'][number],button:HTMLButtonElement){
    const captured=snapshot;if(!button.isConnected||!current(captured)||!captured!.page?.conversations.includes(row))return;
    pending.current?.abort();const controller=new AbortController();pending.current=controller;openButton.current=button;openReference.current=row.conversation_ref;setConversation(null);setFreshWindow(null);setFreshHistory(null);setPhase('reading');
    try{
      const value=await captured!.owner.read({work_ref:captured!.workRef,conversation_ref:row.conversation_ref,revision:row.revision,requests:row.requests},controller.signal);
      if(controller.signal.aborted||!current(captured))throw Error();
      focusAfter.current='reader';setConversation(value);setPhase('ready');
    }catch{if(!controller.signal.aborted){setConversation(null);setPhase('unavailable');}}
  }
  async function readFreshWindow(captured:Snapshot,reference:FreshConversationReference,signal:AbortSignal){
    const value=await captured.owner.readFresh(reference,signal);
    let history:FreshHistory={window:value,turns:value.turns,next:freshConversationNextPage(value),busy:false,unavailable:false,older:false};
    // A full initial envelope can occupy the first page. The user's Open/Send
    // gesture also reads one recent history page so the latest reply is visible.
    if(!value.turns.length&&history.next!==null){
      try{
        const page=await captured.owner.readFreshOlder(value,history.next,signal);
        history={...history,turns:page.turns,next:freshConversationNextPage(page)};
      }catch{
        if(signal.aborted)throw Error();
        history={...history,unavailable:true};
      }
    }
    return {value,history};
  }
  async function refreshFresh(captured:Snapshot,value:FreshConversationWindow){
    if(!current(captured)||liveFresh.current!==value)return;
    pending.current?.abort();const controller=new AbortController();pending.current=controller;setPhase('reading');
    try{
      const next=await readFreshWindow(captured,value.reference,controller.signal);
      if(controller.signal.aborted||!current(captured)||liveFresh.current!==value)throw Error();
      setFreshWindow(next.value);setFreshHistory(next.history);setPhase('ready');
    }catch{if(!controller.signal.aborted)setPhase('unavailable');}
  }
  async function readOlder(){
    const captured=snapshot,value=liveFresh.current,history=historyLive.current;
    if(!captured||!value||!history||history.window!==value||history.next===null||history.busy||
      !current(captured)||!captured.owner.currentFresh(value))return;
    pending.current?.abort();const controller=new AbortController();pending.current=controller;
    setFreshHistory({...history,busy:true,unavailable:false});
    try{
      const page=await captured.owner.readFreshOlder(value,history.next,controller.signal);
      if(controller.signal.aborted||!current(captured)||liveFresh.current!==value||!captured.owner.currentFresh(value))throw Error();
      // Replace one complete source page; keep the initial action witness.
      // Earlier cursors and Return to latest stay with the canonical reader.
      setFreshHistory({window:value,turns:page.turns,next:freshConversationNextPage(page),busy:false,unavailable:false,older:true});
    }catch{if(!controller.signal.aborted&&current(captured)&&liveFresh.current===value)setFreshHistory({...history,busy:false,unavailable:true});}
  }
  async function openFresh(row:FreshConversationCatalogue['entries'][number],button:HTMLButtonElement){
    const captured=snapshot;if(!button.isConnected||!current(captured)||!captured!.fresh?.entries.includes(row))return;
    pending.current?.abort();const controller=new AbortController();pending.current=controller;
    openButton.current=button;openReference.current='fresh:'+row.reference.root_job_id;setConversation(null);setFreshWindow(null);setFreshHistory(null);setPhase('reading');
    try{
      const {value,history}=await readFreshWindow(captured!,row.reference,controller.signal);
      if(controller.signal.aborted||!current(captured))throw Error();
      focusAfter.current='reader';setFreshWindow(value);setFreshHistory(history);setPhase('ready');
    }catch{if(!controller.signal.aborted){setFreshWindow(null);setFreshHistory(null);setPhase('unavailable');}}
  }
  const freshSource=useMemo(()=>{
    const captured=snapshot,value=freshWindow;
    if(!captured||!value)return null;
    return Object.freeze({window:value,reference:value.reference,
      current:()=>current(captured)&&liveFresh.current===value&&captured.owner.currentFresh(value),
      invalidate:()=>{if(current(captured)&&liveFresh.current===value){captured.owner.invalidateFreshRead();setFreshWindow(null);setFreshHistory(null);}},
      refresh:()=>{if(current(captured)&&liveFresh.current===value)void refreshFresh(captured,value);},
    });
  },[snapshot,freshWindow]);
  const shownHistory=freshHistory?.window===freshWindow?freshHistory:null;
  const shownTurns=shownHistory?.turns??freshWindow?.turns??[];
  return <section className="conversations-list project-conversations" data-theme={props.theme??'dark'} lang={props.locale??'en'} aria-label={t('Project conversations','项目对话')}>
    <h2 ref={heading} tabIndex={-1}>{readerOpen&&visible?t('Conversation','对话'):t('Project conversations','项目对话')}</h2>
    <p>{props.projectTitle??t('Selected project','所选项目')}</p>
    {!readerOpen?<><p className="conversations-list__scope">{t('Known conversations from this project. Some conversations and turns may not appear here.','此项目中有记录的对话。部分对话和轮次可能未列出。')}</p>
      <button type="button" disabled={!props.owner||phase==='reading'} onClick={()=>{void read();}}>{t('Read project conversations','读取项目对话')}</button></>:null}
    {phase==='reading'?<p role="status">{t('Reading…','正在读取…')}</p>:null}
    {phase==='unavailable'||(snapshot&&!visible)?<p role="status">{t('Conversations are unavailable here. Read again to check the source.','此处无法查看对话。请重新读取以检查来源。')}</p>:null}
    {visible&&conversation?<>
      <button type="button" onClick={back}>{t('Back to conversations','返回对话列表')}</button>
      <p>{t('Recorded turns only. Opening this conversation does not send or resume anything.','仅显示有记录的轮次。打开对话不会发送消息或恢复会话。')}</p>
      {conversation.turns.map(turn=><article key={turn.read_ref} className="conversations-list__section">
        <p>{t('Request time','请求时间')}: <time dateTime={turn.requested_at}>{turn.requested_at}</time></p>
        {turn.state==='AVAILABLE'&&turn.reply?<>
          <h3>{t('Original request','原始请求')}</h3><SourceMarkdown source={turn.instruction!} locale={props.locale}/>
          <h3>{t('Reply','回复')}</h3><SourceMarkdown source={turn.reply.text} locale={props.locale}/>
          <details className="conversations-list__sources"><summary>{t('Turn details','轮次详情')}</summary>
            <p>{turn.stop_condition}</p><p>{turn.reply.next_step}</p><code>{turn.read_ref}</code><code>{turn.request_revision}</code>
          </details>
        </>:<p>{t('This recorded turn is unavailable. No message content was supplied.','此轮记录暂不可用，未提供消息内容。')}</p>}
      </article>)}
    </>:visible&&freshWindow?<>
      <button type="button" onClick={back}>{t('Back to conversations','返回对话列表')}</button>
      {freshWindow.schema==='mastermind.fresh_conversation_window.v3'?<NativeConversationRecord
        input={freshWindow.initial_input} result={freshWindow.initial_result} locale={props.locale}
        current={()=>!!freshSource?.current()} readInput={signal=>visible.owner.readFreshInput(freshWindow,freshWindow.initial_input,undefined,signal)}
        readResult={signal=>visible.owner.readFreshResult(freshWindow,freshWindow.initial_result!,signal)}/>:
        <FreshConversationInitialResponse locale={props.locale??'en'} result={freshWindow.initial_result} originalMessage={freshWindow.initial_message}
          caption={t('Opening this recorded conversation does not send or acknowledge a message.','打开此对话记录不会发送消息或确认接收。')}/>}
      <div className="conversations-list__history-actions">
        <button type="button" disabled={phase==='reading'||shownHistory?.busy} onClick={()=>{if(snapshot)void refreshFresh(snapshot,freshWindow);}}>
          {shownHistory?.older?t('Return to latest messages','返回最新消息'):t('Refresh conversation','刷新对话')}
        </button>
        {shownHistory?.next!==null&&shownHistory?.next!==undefined?<button type="button" disabled={phase==='reading'||shownHistory.busy} onClick={()=>void readOlder()}>
          {shownHistory.busy?t('Loading earlier messages…','正在加载更早的消息…'):t('Load earlier messages','加载更早的消息')}
        </button>:null}
      </div>
      {shownHistory?.older?<p>{t('Showing one page of earlier messages.','当前显示一页更早的消息。')}</p>:null}
      {shownHistory?.unavailable?<p role="status">{t('Earlier messages could not be loaded. Try again.','暂时无法加载更早的消息，请重试。')}</p>:null}
      {shownTurns.map(turn=><article className="conversations-list__section" key={turn.turn_key}>
        {'input' in turn?<NativeConversationRecord input={turn.input} result={turn.result} locale={props.locale}
          current={()=>!!freshSource?.current()} readInput={signal=>visible.owner.readFreshInput(freshWindow,turn.input,turn.turn_key,signal)}
          readResult={signal=>visible.owner.readFreshResult(freshWindow,turn.result!,signal)}/>:
          <FreshConversationInitialResponse locale={props.locale??'en'} result={turn.result} originalMessage={turn.message}
            responseKind="followup" headingLevel={3}/>}
      </article>)}
      {freshSource?props.renderFreshContinuation?.(freshSource):null}
    </>:visible?<>
      <div className="conversations-list__filter"><label htmlFor={filterId}>{t('Find in these conversations','查找这些对话')}</label>
        <input id={filterId} value={query} onChange={event=>setQuery(event.target.value)}/></div>
      {!visible.page?.conversations.length&&!visible.fresh?.entries.length?<p>{t('No conversations were returned for this page.','本页未返回对话。')}</p>:null}
      {visible.fresh?.entries.filter(row=>`${props.projectTitle??''} ${typeof freshConversationInput(row)==='string'?freshConversationInput(row):'initial_input' in row?row.initial_input.preview:''}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())).map(row=>{
        const key='fresh:'+row.reference.root_job_id;
        return <article className="conversations-list__row" key={key}>
          <div className="conversations-list__row-copy"><h3>{t('Conversation','对话')}</h3><p>{'initial_input' in row?row.initial_input.preview:row.initial_message}</p></div>
          <button type="button" ref={node=>{if(node)rowButtons.current.set(key,node);else rowButtons.current.delete(key);}} disabled={phase==='reading'} onClick={event=>{void openFresh(row,event.currentTarget);}}>{t('Open','打开')}</button>
        </article>;
      })}
      {visible.page?.conversations.filter(row=>`${props.projectTitle??''} ${row.title??t('Conversation','对话')}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())).map(row=>
        <article className="conversations-list__row" key={row.conversation_ref}>
          <div className="conversations-list__row-copy"><h3>{row.title??t('Conversation','对话')}</h3>
            <p>{t('Latest recorded request','最近记录的请求')}: <time dateTime={row.last_request_at}>{row.last_request_at}</time></p>
            <p>{t(`${row.requests.length} recorded turns in this window`, `此窗口中有 ${row.requests.length} 轮记录`)}</p></div>
          <button type="button" ref={node=>{if(node)rowButtons.current.set(row.conversation_ref,node);else rowButtons.current.delete(row.conversation_ref);}} disabled={phase==='reading'} onClick={event=>{void open(row,event.currentTarget);}}>{t('Open','打开')}</button>
        </article>)}
      {visible.page?.next_cursor?<button type="button" disabled={phase==='reading'} onClick={()=>{void read(visible.page!.next_cursor!);}}>{t('Read next page','读取下一页')}</button>:null}
    </>:null}
    {visible?<details className="conversations-list__sources"><summary>{t('Conversation source details','对话来源详情')}</summary>
      <p>{visible.workRef}</p><p>{t('Coverage: recorded session windows','覆盖范围：已记录的会话窗口')}</p>
      <p>{t('Original-session source','原有会话来源')}: {visible.page?'AVAILABLE':'UNAVAILABLE'}</p>
      <p>{t('New-conversation source','新建对话来源')}: {visible.fresh?'AVAILABLE':'UNAVAILABLE'}</p>
      {(conversation?[conversation]:visible.page?.conversations??[]).map(row=><div key={row.conversation_ref}><code>{row.conversation_ref}</code><code>{row.revision}</code><code>{row.root_job_id}</code></div>)}
      {freshWindow?<code>{JSON.stringify({reference:freshWindow.reference,state:freshWindow.state,epoch:freshWindow.epoch,
        initial_consumption:freshWindow.initial_consumption})}</code>:visible.fresh?.entries.map(row=><code key={row.reference.root_job_id}>{JSON.stringify(row.reference)}</code>)}
    </details>:null}
  </section>;
}
