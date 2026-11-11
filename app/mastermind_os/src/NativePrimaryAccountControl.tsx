import {useLayoutEffect, useRef, useState, type ReactNode, type RefObject} from "react";
import type {AuthState, MissionHost} from "./host";
import {primaryAccountEntry} from "./native-primary-account";
const copy = {
  en: {action: "Sign in to account", detail: "Account access only. Work needs separate authorization.",
    reset: "Clear saved sign-in", resetUnknown: "The sign-out result is unconfirmed. Check the current account state before another request.",
    unavailable: "Account sign-in is unavailable here.", unknown: "The sign-in handoff is unconfirmed. Check the current account state before another request."},
  "zh-CN": {action: "登录账户", detail: "仅登录账户；工作操作仍需单独授权。",
    reset: "清除已保存的登录", resetUnknown: "退出登录的结果尚未确认。请先确认当前账户状态，再发起其他请求。",
    unavailable: "此处暂时无法登录账户。", unknown: "登录请求的交接结果尚未确认。请先确认当前账户状态，再发起其他请求。"},
};
/** A fresh gesture uses only the optional primary action; mounting never invokes auth. */
export function NativePrimaryAccountControl({host, state, locale, beforeSignIn, pendingControl, pendingControlRef}: {
  host: MissionHost | undefined; state: AuthState; locale: "en" | "zh-CN"; beforeSignIn?: () => void; pendingControl?: ReactNode; pendingControlRef?: RefObject<HTMLButtonElement | null>;
}) {
  const text=copy[locale], owner=host?.primaryAccount, busy=useRef(false), alive=useRef(true), uncertain=useRef(false);
  const primaryButton=useRef<HTMLButtonElement>(null), focusPending=useRef(false);
  // Only the initiating keyboard gesture transfers focus to the incumbent Cancel control.
  useLayoutEffect(()=>{
    if (state.status === "signing_in" && focusPending.current) {focusPending.current=false;pendingControlRef?.current?.focus();}
  },[state.status,pendingControlRef]);
  const [pending,setPending]=useState(false),[unconfirmed,setUnconfirmed]=useState(false);
  const [resetUnconfirmed,setResetUnconfirmed]=useState(false);
  useLayoutEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  useLayoutEffect(()=>{uncertain.current=false;setUnconfirmed(false);setResetUnconfirmed(false);},[host,owner]);
  const auth=host?.auth, command=owner?.signIn, resetCommand=auth?.signOut, stateReader=auth?.getState, generation=host?.invalidationGeneration;
  const epoch=generation?.call(host), snapshot=JSON.stringify(state);
  const current=()=>{try{return alive.current && !uncertain.current && window.MastermindMissionHost===host &&
    !!host && host.primaryAccount===owner && owner?.signIn===command && host.auth===auth && auth?.getState===stateReader &&
    host.invalidationGeneration===generation && Number.isSafeInteger(epoch) && generation?.call(host)===epoch &&
    !!stateReader && JSON.stringify(stateReader.call(auth))===snapshot && primaryAccountEntry(stateReader.call(auth));}catch{return false;}};
  const send=async()=>{
    if(busy.current||!command||!current())return;
    focusPending.current=document.activeElement===primaryButton.current;
    busy.current=true;setPending(true);
    try {beforeSignIn?.();if(!current())return;await command.call(owner);}
    catch {uncertain.current=true;if(alive.current)setUnconfirmed(true);}
    finally {busy.current=false;if(alive.current)setPending(false);}
  };
  const reset=async()=>{
    if(busy.current||!resetCommand||!current()||auth?.signOut!==resetCommand)return;
    busy.current=true;setPending(true);
    try {await resetCommand.call(auth);}
    catch {uncertain.current=true;if(alive.current){setUnconfirmed(true);setResetUnconfirmed(true);}}
    finally {busy.current=false;if(alive.current)setPending(false);}
  };
  const supported=!!owner&&!!auth&&!!command&&primaryAccountEntry(state);
  return <>
    {state.status === "signing_in" && pendingControl ? pendingControl : <button ref={primaryButton} type="button" disabled={!supported||pending||unconfirmed} onClick={()=>{void send();}}>{text.action}</button>}
    {primaryAccountEntry(state) && !!auth && !!resetCommand && <button type="button" disabled={pending||unconfirmed} onClick={()=>{void reset();}}>{text.reset}</button>}
    {state.status !== "signing_in" && <small role="status">{unconfirmed?(resetUnconfirmed?text.resetUnknown:text.unknown):supported?text.detail:text.unavailable}</small>}
  </>;
}
