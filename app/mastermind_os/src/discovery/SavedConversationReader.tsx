/** Explicit saved Search Open over the existing qualified Session Bridge owner.
 * Ephemeral navigation witnesses are not permissions or persisted sessions. */
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {SourceMarkdown} from '../conversations/SourceMarkdown';
import '../knowledge/library/knowledge-library.css';
import {captureProjectSourceDraftRead,completeProjectSourceDraftRead,type ProjectSourceDraftPort,type ProjectSourceDraftProof} from '../knowledge/library/project-source-draft';
import {ProjectSourceDraftCompanion} from '../knowledge/library/ProjectSourceDraftCompanion';
import {readSavedConversationSource,type SavedConversationMatch,type SavedConversationSearchOwner,type SavedConversationSourceRead} from './saved-conversations';

type Context=NonNullable<ReturnType<SavedConversationSearchOwner['context']>>;
type Methods=Readonly<{context:SavedConversationSearchOwner['context'];auth:SavedConversationSearchOwner['authGeneration'];references:SavedConversationSearchOwner['readReferences'];answer:SavedConversationSearchOwner['readAnswer']}>;
export interface SavedConversationNavigation {
 readonly workRef:string; readonly authGeneration:number; readonly hostGeneration:string|number;
 readonly match:SavedConversationMatch; readonly pageCursor?:string; readonly expectedHighWater:number;
 readonly owner:SavedConversationSearchOwner; readonly context:Context; readonly ownerAuthGeneration:number;
 readonly methods:Methods;
}
function capture(owner:SavedConversationSearchOwner|undefined){
 try {
  if(!owner)return null;
  const methods={context:owner.context,auth:owner.authGeneration,references:owner.readReferences,answer:owner.readAnswer};
  if(Object.values(methods).some(method=>typeof method!=='function'))return null;
  const context=methods.context.call(owner),auth=methods.auth.call(owner);
  if(!context || typeof context.principalScope!=='string' || !context.principalScope || typeof context.generation!=='string' || !context.generation || !Number.isSafeInteger(auth)||auth<0)return null;
  return {context:Object.freeze({principalScope:context.principalScope,generation:context.generation}),auth,methods:Object.freeze(methods)};
 }catch{return null;}
}
/** Call only at the explicit onOpenSaved event, using the same actual owner as
 * Search. Captures current owner/epoch; it never reads a reference or body. */
export function createSavedConversationNavigation(
 selection:Omit<SavedConversationNavigation,'owner'|'context'|'ownerAuthGeneration'|'methods'>,
 owner:SavedConversationSearchOwner|undefined,
):SavedConversationNavigation|null {
 const captured=capture(owner);if(!captured||!owner || !Number.isSafeInteger(selection.authGeneration)||selection.authGeneration<0 ||
  !((typeof selection.hostGeneration==='string'&&selection.hostGeneration.length>0)||(typeof selection.hostGeneration==='number'&&Number.isFinite(selection.hostGeneration))))return null;
 return Object.freeze({...selection,owner,context:captured.context,ownerAuthGeneration:captured.auth,methods:captured.methods});
}
export interface SavedConversationReaderProps {
 readonly draftPort?:ProjectSourceDraftPort;
 readonly selection:SavedConversationNavigation;
 readonly workRef:string|null; readonly authGeneration:number; readonly hostGeneration:string|number|null;
 readonly owner?:SavedConversationSearchOwner;readonly locale?:'en'|'zh-CN';readonly theme?:'dark'|'light';
 readonly onBack?:()=>void; readonly renderSourceCompanion?:(source:SavedConversationSourceRead)=>ReactNode;
}
const ids=new WeakMap<object,number>();let seq=0;
function id(value:object|undefined){if(!value)return 0;let result=ids.get(value);if(!result){result=++seq;ids.set(value,result);}return result;}
function sameOwner(selection:SavedConversationNavigation,owner:SavedConversationSearchOwner|undefined){
 const now=capture(owner);return !!now && owner===selection.owner && now.auth===selection.ownerAuthGeneration &&
 now.context.principalScope===selection.context.principalScope && now.context.generation===selection.context.generation &&
 now.methods.context===selection.methods.context && now.methods.auth===selection.methods.auth &&
 now.methods.references===selection.methods.references && now.methods.answer===selection.methods.answer;
}
function current(props:SavedConversationReaderProps){
 const s=props.selection;return s.workRef===props.workRef && s.authGeneration===props.authGeneration &&
 typeof s.hostGeneration===typeof props.hostGeneration && s.hostGeneration===props.hostGeneration && sameOwner(s,props.owner);
}
export function SavedConversationReader(props:SavedConversationReaderProps){
 const now=capture(props.owner);
 const identity=JSON.stringify([props.workRef,props.authGeneration,typeof props.hostGeneration,props.hostGeneration,
 id(props.selection),id(props.owner),now?.auth,now?.context.principalScope,now?.context.generation,
 id(now?.methods.context),id(now?.methods.auth),id(now?.methods.references),id(now?.methods.answer)]);
 return <ReaderBody key={identity} {...props}/>;
}
function ReaderBody(props:SavedConversationReaderProps){
 const zh=props.locale==='zh-CN';const t=(en:string,cn:string)=>zh?cn:en;
 const [draftProof,setDraftProof]=useState<ProjectSourceDraftProof|null>(null);
 const [source,setSource]=useState<SavedConversationSourceRead|null>(null);
 const [phase,setPhase]=useState<'loading'|'ready'|'unavailable'|'closed'>('loading');
 const [reason,setReason]=useState<string|null>(null);
 const active=useRef<AbortController|null>(null),closed=useRef(false);
 const live=useRef(props);live.current=props;
 useEffect(()=>{
  if(!current(props)){setPhase('unavailable');setReason('SOURCE_CONTEXT_CHANGED');return;}
  const controller=new AbortController();active.current=controller;
  const {selection:s,owner}=props;
  const sourceIsCurrent=()=>!controller.signal.aborted&&!closed.current&&current(live.current);
  const ticket=props.draftPort?captureProjectSourceDraftRead(props.draftPort,s.workRef,sourceIsCurrent):null;
  void readSavedConversationSource({workRef:s.workRef,match:s.match,expectedHighWater:s.expectedHighWater,
   ...(s.pageCursor!==undefined?{pageCursor:s.pageCursor}:{}),signal:controller.signal},owner!).then(async result=>{
    if(controller.signal.aborted||closed.current||!current(live.current))return;
    if(result.state==='AVAILABLE'&&result.reference&&result.text!==null&&result.sourceTextSha256){
      const proof=ticket&&live.current.draftPort?await completeProjectSourceDraftRead(ticket,{kind:'SAVED_REPLY',result},live.current.draftPort):null;
      if(!sourceIsCurrent())return;
      setDraftProof(proof);setSource(result);setPhase('ready');}
    else{setSource(null);setReason(result.reason);setPhase('unavailable');}
   }).catch(()=>{if(!controller.signal.aborted&&!closed.current){setSource(null);setPhase('unavailable');setReason('SOURCE_UNAVAILABLE');}});
  return()=>controller.abort();
 },[]);
 const back=()=>{if(closed.current||!props.onBack)return;closed.current=true;active.current?.abort();setSource(null);setPhase('closed');props.onBack();};
 const backRef=useRef(back);backRef.current=back;
 useEffect(()=>{const escape=(event:KeyboardEvent)=>{if(event.key==='Escape')backRef.current();};window.addEventListener('keydown',escape);return()=>window.removeEventListener('keydown',escape);},[]);
 const available=current(props)&&phase==='ready'&&source?.state==='AVAILABLE';
 const ref=available?source.reference:null;
 return <section className="knowledge-library" data-knowledge-theme={props.theme==='light'?'light':'dark'} lang={zh?'zh-CN':'en'}>
  <div className="knowledge-library-reader">
   <article className="knowledge-library-document">
    <button className="knowledge-library-button" type="button" disabled={!props.onBack||phase==='closed'} onClick={back}>{t('Back to search','返回搜索')}</button>
    <h1>{t('Saved reply','已保存的回复')}</h1>
    {available&&source.text!==null?<SourceMarkdown source={source.text} locale={props.locale}/>:<p role="status">{phase==='loading'&&current(props)?t('Loading source…','正在加载来源…'):t('This saved reply is unavailable here. Return to search to try again.','此处无法查看此已保存的回复。请返回搜索后重试。')}</p>}
    {!available&&reason?<details className="knowledge-library-details"><summary>{t('Source details','来源详情')}</summary><p>{reason}</p></details>:null}
   </article>
   {available&&ref?<aside className="knowledge-library-aside">
    {props.draftPort?<ProjectSourceDraftCompanion proof={draftProof} port={props.draftPort} locale={props.locale}/>:null}
    {props.renderSourceCompanion?.(source)}
    <div className="knowledge-library-aside-panel"><h2>{t('Source','来源')}</h2>
     <p>{t('Request time','请求时间')}: {ref.requested_at}</p>
     <details className="knowledge-library-details"><summary>{t('Source details','来源详情')}</summary><dl>
      {Object.entries(ref).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}
      <div><dt>sourceTextSha256</dt><dd>{source.sourceTextSha256}</dd></div>
     </dl></details>
    </div>
   </aside>:null}
  </div>
 </section>;
}
