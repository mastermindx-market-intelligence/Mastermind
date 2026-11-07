import "./CompanyPrioritiesRead.css";
import {useEffect,useRef,useState} from "react";
import type {MissionHost} from "../host";
import type {CompanyPriorities,CompanyPrioritiesOwner} from "./company-priorities";
/** Explicit authored company READ, independent of selected project or unsent draft. */
export function CompanyPrioritiesRead({host,locale="en"}:{host:MissionHost|undefined;locale?:"en"|"zh-CN"}){
 const t=(en:string,zh:string)=>locale==="zh-CN"?zh:en,owner=host?.companyPriorities;
 const latest=useRef({host,owner});latest.current={host,owner};
 const [read,setRead]=useState<{owner:CompanyPrioritiesOwner;generation:number;value:CompanyPriorities}|null>(null);
 const [phase,setPhase]=useState<"idle"|"pending"|"unavailable">("idle");
 const flight=useRef<AbortController|null>(null),button=useRef<HTMLButtonElement>(null);
 const current=(o=owner,g?:number)=>{try{const expected=g??o?.generation();return !!host&&latest.current.host===host&&window.MastermindMissionHost===host&&latest.current.owner===o&&host.companyPriorities===o&&!!o&&o.available()&&o.generation()===expected}catch{return false}};
 useEffect(()=>{setRead(null);setPhase("idle");const clear=()=>{flight.current?.abort();setRead(null);setPhase("unavailable")};const off=owner?.subscribe(clear);return()=>{flight.current?.abort();off?.()}},[host,owner]);
 useEffect(()=>{if(!read)return;const timer=setTimeout(()=>{setRead(null);setPhase("unavailable")},Math.max(0,Math.min(2147483647,read.value.owner_context.verified_expiry*1000-Date.now())));return()=>clearTimeout(timer)},[read]);
 const value=read&&current(read.owner,read.generation)&&read.value.owner_context.verified_expiry*1000>Date.now()?read.value:null;
 async function acquire(){if(!owner||!current())return;const captured=owner,generation=owner.generation(),controller=new AbortController();flight.current?.abort();flight.current=controller;setRead(null);setPhase("pending");try{const v=await captured.read(controller.signal);if(!controller.signal.aborted&&current(captured,generation)){setRead({owner:captured,generation,value:v});setPhase("idle")}}catch{if(!controller.signal.aborted&&latest.current.owner===captured){setRead(null);setPhase("unavailable")}}finally{if(flight.current===controller)flight.current=null}}
 const active=value?.priorities.filter(p=>p.status==="active")??[],other=value?.priorities.filter(p=>p.status!=="active")??[];
 const status=(s:string)=>({paused:t("Paused","已暂停"),achieved:t("Achieved","已达成"),retired:t("Retired","已归档")}[s]??s);
 return <section className="office-panel office-company-priorities" aria-labelledby="office-company-priorities-title" lang={locale}>
  <h2 id="office-company-priorities-title">{t("Company priorities","公司优先事项")}</h2>
  <p className="office-muted">{t("Authored strategy and declared review criteria. They do not establish adoption, readiness or permission to act.","已编写的战略与已声明的审查条件；不代表采纳、就绪或行动权限。")}</p>
  <button ref={button} type="button" disabled={!current()||phase==="pending"} onClick={()=>void acquire()}>{phase==="pending"?t("Reading company priorities…","正在读取公司优先事项…"):t("Read company priorities","读取公司优先事项")}</button>
  {(phase==="unavailable"||!current())&&<p role="status">{t("Company priorities are unavailable. No company conclusion can be drawn from this read.","公司优先事项暂不可用。不能据此次读取得出公司层面的结论。")}</p>}
  {value&&<>
   <p>{t("Authored as of","编写日期")} {value.as_of}</p>
   <details className="office-disclosure"><summary>{t("Company direction in the source","来源中编写的公司方向")}</summary><ul>{value.north_star.map((n,i)=><li key={i}>{n}</li>)}</ul></details>
   <h3>{t("Active priorities","当前优先事项")}</h3>
   <ul className="office-lanes">{active.map(p=><li key={p.id}><div><p>{p.objective}</p><details className="office-raw"><summary>{t("Source reference","来源引用")}</summary><p className="office-ref">{p.id} · {p.department}</p></details></div></li>)}</ul>
   {!active.length&&<p>{t("No active priority is declared in this source.","此来源未声明当前优先事项。")}</p>}
   <details className="office-disclosure"><summary>{t("Declared phase-review criteria","已声明的阶段审查条件")}</summary><p>{t("These are review criteria, not evaluated results or a ranked critical path.","这些是审查条件，不是已评估的结果或已排序的关键路径。")}</p>{Object.entries(value.phase_review_criteria).map(([key,g])=><section key={key}><h3 className="office-ref">{key}</h3><p>{g.purpose}</p><ul>{g.criteria.map((c,i)=><li key={i}>{c}</li>)}</ul><p>{t("Declared follow-up after a qualified pass","确认通过后声明的后续事项")}: {g.on_pass}</p></section>)}</details>
   <details className="office-raw"><summary>{t("Company source details","公司来源详情")}</summary><p className="office-ref">{value.source.path} · {value.source.revision}</p><p>{t("Observed","观测时间")}: {value.source.observed_at}</p><p className="office-ref">{value.authority} · {value.company_phase}</p>{other.map(p=><p key={p.id} className="office-ref">{p.id} · {status(p.status)} · {p.objective}</p>)}</details>
  </>}
 </section>;
}
