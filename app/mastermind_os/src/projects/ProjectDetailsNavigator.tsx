import {useLayoutEffect,useRef,useState,type KeyboardEvent,type ReactNode} from 'react';
import './project-details-navigator.css';
export type ProjectDetailsSectionId='direction'|'plan'|'work'|'instructions'|'permissions'|'history';
export interface ProjectDetailsNavigatorProps {
  scopeKey:string;locale:'en'|'zh-CN';title:string;goal:string|null;
  sections:readonly {id:ProjectDetailsSectionId;content:ReactNode}[];
}
const LABELS:Record<ProjectDetailsSectionId,readonly[string,string,string,string]>={
 direction:['Direction','方向','Accepted direction and earlier revisions.','已接受的方向与早期修订。'],
 plan:['Plan','计划','Recorded objective and delivery plan.','已记录的目标与推进计划。'],
 work:['Work controls','工作控制','Project pause and related work details.','项目暂停与相关工作详情。'],
 instructions:['Standing instructions','常设指令','Instructions supplied for this project.','此项目提供的指令。'],
 permissions:['Project permissions','项目权限','Existing permission records for this project.','此项目的现有权限记录。'],
 history:['History and sources','历史与来源','Recorded conversations, journal and source evidence.','已记录的对话、日志和来源证据。'],
};
/** Presentation navigation only. Every owner remains mounted; choosing a section
 * does not read a source, publish data, or establish currentness/permission. */
export function ProjectDetailsNavigator({scopeKey,locale,title,goal,sections}:ProjectDetailsNavigatorProps) {
 const zh=locale==='zh-CN';
 const [selection,setSelection]=useState<{scope:string;id:ProjectDetailsSectionId|null}>({scope:scopeKey,id:null});
 const active=selection.scope===scopeKey&&sections.some(s=>s.id===selection.id)?selection.id:null;
 const buttons=useRef(new Map<ProjectDetailsSectionId,HTMLButtonElement>());
 const owners=useRef(new Map<ProjectDetailsSectionId,HTMLElement>());
 const overviewHeading=useRef<HTMLHeadingElement>(null);
 const gesture=useRef<{scope:string;kind:'open'|'back';id:ProjectDetailsSectionId}|null>(null);
 useLayoutEffect(()=>{
  if(selection.scope!==scopeKey){gesture.current=null;setSelection({scope:scopeKey,id:null});}
 },[scopeKey,selection.scope]);
 useLayoutEffect(()=>{
  const intent=gesture.current;gesture.current=null;
  if(!intent||intent.scope!==scopeKey)return;
  const target=intent.kind==='open'&&active===intent.id?owners.current.get(intent.id)
    :intent.kind==='back'&&active===null?buttons.current.get(intent.id)??overviewHeading.current:null;
  if(!target?.isConnected)return;
  target.focus();
  if(intent.kind==='open'&&typeof target.scrollIntoView==='function')target.scrollIntoView({block:'start'});
 },[active,scopeKey]);
 const choose=(id:ProjectDetailsSectionId)=>{
  gesture.current={scope:scopeKey,kind:'open',id};setSelection({scope:scopeKey,id});
 };
 const back=()=>{
  if(active===null)return;
  gesture.current={scope:scopeKey,kind:'back',id:active};setSelection({scope:scopeKey,id:null});
 };
 const onKeyDown=(event:KeyboardEvent<HTMLElement>)=>{
  if(event.key!=='Escape'||event.defaultPrevented||active===null)return;
  const target=event.target as HTMLElement;
  if(target.closest('input,textarea,[contenteditable="true"]'))return;
  event.preventDefault();event.stopPropagation();back();
 };
 return <section className="mm-project-details-nav" lang={locale} aria-label={zh?'项目详情导航':'Project details navigation'} onKeyDown={onKeyDown}>
  <div className="mm-project-details-nav__overview" hidden={active!==null}>
   <header><h2 ref={overviewHeading} tabIndex={-1}>{zh?'项目概览':'Project overview'}</h2><p className="mm-project-details-nav__title">{title}</p></header>
   <div className="mm-project-details-nav__goal"><h3>{zh?'目标':'Goal'}</h3><p>{goal??(zh?'此视图暂时无法显示项目目标。':'The project goal is unavailable in this view.')}</p></div>
   <h3>{zh?'查看':'Inspect'}</h3>
   <div className="mm-project-details-nav__links">{sections.map(({id})=><button type="button" aria-label={LABELS[id][zh?1:0]} aria-description={LABELS[id][zh?3:2]} key={id} ref={node=>{if(node)buttons.current.set(id,node);else buttons.current.delete(id);}} onClick={()=>choose(id)}>
    <span><strong>{LABELS[id][zh?1:0]}</strong><small>{LABELS[id][zh?3:2]}</small></span><span aria-hidden="true">›</span>
   </button>)}</div>
  </div>
  {sections.map(({id,content})=><section key={id} ref={node=>{if(node)owners.current.set(id,node);else owners.current.delete(id);}}
    className="mm-project-details-nav__owner" hidden={active!==id} tabIndex={-1} aria-label={zh?`查看：${LABELS[id][1]}`:`Inspect ${LABELS[id][0]}`}>
    <button type="button" className="mm-project-details-nav__back" onClick={back}>← {zh?'返回项目详情':'Back to project details'}</button>
    {content}
   </section>)}
 </section>;
}
