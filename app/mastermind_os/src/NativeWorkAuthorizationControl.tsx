import {useLayoutEffect,useRef,useState} from 'react';
import type {AuthState,MissionHost} from './host';
import type {WorkAuthorization} from './native-work-authorization';
export function NativeWorkAuthorizationControl({host,state,revision,locale,beforeSignIn}:{host:MissionHost|undefined;state:AuthState;revision:number;locale:'en'|'zh-CN';beforeSignIn?:()=>void}) {
 const zh=locale==='zh-CN',t=(en:string,cn:string)=>zh?cn:en,owner=host?.workAuthorization;
 const [open,setOpen]=useState(false),[data,setData]=useState<WorkAuthorization|null>(null),[phase,setPhase]=useState<'idle'|'reading'|'pending'|'unavailable'|'unknown'>('idle');
 const frame=useRef<(()=>boolean)|null>(null),sequence=useRef(0),busy=useRef(false),uncertain=useRef(false),alive=useRef(true),entry=useRef<HTMLButtonElement>(null),backFocus=useRef(false),action=useRef<HTMLButtonElement>(null),notice=useRef<HTMLParagraphElement>(null),focus=useRef(false);
 useLayoutEffect(()=>{alive.current=true;return()=>{alive.current=false;sequence.current++;frame.current=null;};},[]);
 useLayoutEffect(()=>{sequence.current++;frame.current=null;setData(null);setPhase(uncertain.current?'unknown':'idle');},[host,owner,revision,state.status,state.reason,state.acquisition,state.content]);
 useLayoutEffect(()=>{if(backFocus.current&&!open){backFocus.current=false;entry.current?.focus();}else if(focus.current&&phase!=='reading'){focus.current=false;(action.current??notice.current)?.focus();}},[open,phase,data]);
 const capture=()=>{const auth=host?.auth,read=owner?.read,command=owner?.signIn,get=auth?.getState,gen=host?.invalidationGeneration,g=gen?.call(host),s=JSON.stringify(state);
 return()=>{try{return alive.current&&window.MastermindMissionHost===host&&!!host&&host.workAuthorization===owner&&host.auth===auth&&auth?.getState===get&&owner?.read===read&&owner?.signIn===command&&host.invalidationGeneration===gen&&Number.isSafeInteger(g)&&gen?.call(host)===g&&JSON.stringify(get?.call(auth))===s&&state.status==='signed_in'&&state.acquisition&&state.content;}catch{return false;}};};
 const inspect=async()=>{const current=capture(),n=++sequence.current;frame.current=null;setData(null);setOpen(true);setPhase('reading');focus.current=document.activeElement===entry.current;
  if(!owner||!current()){setPhase('unavailable');return;}
  try{const value=await owner.read({signal:new AbortController().signal});if(n===sequence.current&&current()&&!busy.current){frame.current=current;setData(value);setPhase(uncertain.current?'unknown':'idle');}}
  catch{if(n===sequence.current&&current())setPhase(uncertain.current?'unknown':'unavailable');}
 };
 const send=async()=>{const current=frame.current;frame.current=null;if(busy.current||uncertain.current)return;if(data?.state!=='ELIGIBLE'||!current?.()||!owner){setData(null);setPhase('unavailable');return;}
  const n=sequence.current;busy.current=true;setPhase('pending');try{beforeSignIn?.();if(!current())return;await owner.signIn();}
  catch{uncertain.current=true;if(alive.current&&sequence.current===n&&window.MastermindMissionHost===host&&host?.workAuthorization===owner)setPhase('unknown');}finally{busy.current=false;}
 };
 if(!state.acquisition||!state.content||state.status!=='signed_in'||window.MastermindMissionHost!==host)return null;
 if(!open)return <button type="button" ref={entry} onClick={()=>{void inspect();}}>{t('Work access','工作访问')}</button>;
 const current=frame.current?.()===true;
 return <>
  <p className="muted" role="status" tabIndex={-1} ref={notice}>{phase==='reading'?t('Checking local work access…','正在检查本地工作访问…'):phase==='pending'?t('Opening work sign-in…','正在打开工作登录…'):phase==='unknown'?t('The sign-in handoff is unconfirmed. Another request is unavailable.','登录请求的交接结果尚未确认，暂不能发起其他请求。'):!current?t('Work sign-in is unavailable here.','此处暂时无法进行工作登录。'):data?.state==='ADMIN_ACTION_REQUIRED'?t('Work authorization was not granted. Contact your administrator. Retrying this authorization is unavailable here.','工作授权未获批准。请联系管理员；此处不能重试该授权。'):data?.state==='ELIGIBLE'?t('This starts a fresh account sign-in before requesting work authorization. Account access is temporarily withdrawn.','将重新登录账户，再请求工作授权；期间账户访问暂时关闭。'):t('Work sign-in is unavailable for the current authorization state.','当前授权状态不允许进行工作登录。')}</p>
  {current&&data?.state==='ELIGIBLE'&&<button type="button" ref={action} disabled={phase==='pending'||phase==='unknown'} onClick={()=>{void send();}}>{t('Sign in for work','登录以访问工作')}</button>}
  <button type="button" onClick={()=>{sequence.current++;frame.current=null;backFocus.current=true;setOpen(false);setData(null);}}>{t('Back','返回')}</button>
 </>;
}
