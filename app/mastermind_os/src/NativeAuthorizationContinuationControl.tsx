import {useEffect, useLayoutEffect, useRef, useState} from "react";
import type {AuthState, MissionHost} from "./host";
import {incompleteAuthorization} from "./native-authorization-continuation-host";
const copy = {
  en: {action: "Continue authorization", sending: "Opening authorization…", opened: "Authorization request opened. Complete the requested step in your browser.",
    unavailable: "Additional authorization is unavailable here. Your account remains connected.",
    unconfirmed: "Authorization outcome is unconfirmed. Do not send another request; check the current authorization status.",
    changed: "Authorization status changed. This request was not sent."},
  "zh-CN": {action: "继续授权", sending: "正在打开授权…", opened: "授权请求已打开。请在浏览器中完成所需步骤。",
    unavailable: "此处暂时无法继续授权；您的账户仍保持连接。",
    unconfirmed: "授权结果尚未确认。请勿再次发送请求；请确认当前授权状态。",
    changed: "授权状态已改变，未发送此请求。"},
};
/** Capability reads are local metadata only. Every handoff requires a fresh explicit gesture. */
export function NativeAuthorizationContinuationControl({host, state, revision, locale}: {
  host: MissionHost | undefined; state: AuthState; revision: number; locale: "en" | "zh-CN";
}) {
  const text = copy[locale], owner = host?.authorizationContinuation;
  const [eligible, setEligible] = useState(false), [pending, setPending] = useState(false);
  const [message, setMessage] = useState<keyof Pick<typeof text, "opened" | "unavailable" | "unconfirmed" | "changed"> | null>(null);
  const frame = useRef<(() => boolean) | null>(null), busy = useRef(false), alive = useRef(true);
  const action = useRef<HTMLButtonElement>(null);
  const notice = useRef<HTMLParagraphElement>(null), focusAfterGesture = useRef(false), uncertain = useRef(false);
  const refresh = useRef<() => void>(() => {});
  useEffect(() => {alive.current = true; return () => {alive.current = false; frame.current = null;};}, []);
  useLayoutEffect(() => {frame.current = null; setEligible(false); setPending(false); setMessage(null); focusAfterGesture.current = false;}, [host, owner]);
  useEffect(() => {if (!state.acquisition) {setMessage(null); setPending(false);}}, [state.acquisition]);
  useLayoutEffect(() => {if (focusAfterGesture.current && message && notice.current) {
    focusAfterGesture.current = false; notice.current.focus();
  }}, [message, pending]);
  useEffect(() => {
    const abort = new AbortController();
    frame.current = null; setEligible(false);
    if (!host || !owner || !host.auth || !incompleteAuthorization(state)) {refresh.current = () => {}; return;}
    const auth = host.auth, stateReader = auth.getState, read = owner.read, command = owner.continue;
    const epoch = host.invalidationGeneration?.(), generationReader = host.invalidationGeneration;
    const snapshot = JSON.stringify(auth.getState());
    const current = () => {try {return !abort.signal.aborted && window.MastermindMissionHost === host &&
      host.authorizationContinuation === owner && host.auth === auth && auth.getState === stateReader && owner.read === read && owner.continue === command &&
      host.invalidationGeneration === generationReader && Number.isSafeInteger(epoch) &&
      host.invalidationGeneration?.() === epoch && JSON.stringify(auth.getState()) === snapshot;} catch {return false;}};
    let sequence = 0;
    const acquire = () => {
      frame.current = null; setEligible(false);
      const ticket = ++sequence;
      if (!current()) return;
      Promise.resolve().then(() => read.call(owner, {signal: abort.signal})).then(value => {
        if (ticket !== sequence || !current() || busy.current) return;
        const allowed = value.state === "ELIGIBLE" && !uncertain.current;
        frame.current = allowed ? current : null; setEligible(allowed);
      }, () => {if (ticket === sequence && current() && !busy.current) setMessage(previous => previous ?? "unavailable");});
    };
    refresh.current = acquire; acquire();
    return () => {abort.abort(); sequence++; frame.current = null;};
  }, [host, owner, revision, state.status, state.reason, state.acquisition, state.content]);
  const send = async () => {
    const current = frame.current; frame.current = null;
    if (busy.current) return;
    if (!current || !current() || !owner) {setEligible(false); focusAfterGesture.current = true; setMessage("changed"); return;}
    busy.current = true; setPending(true); setEligible(false); setMessage(null);
    let outcome: "opened" | "unavailable" | "unconfirmed" = "opened";
    try {await owner.continue();} catch (error) {
      const code = error instanceof Error ? error.message : error;
      outcome = typeof code === "string" && ["AUTH_CONTINUATION_INELIGIBLE", "AUTHORIZATION_IDENTITY_UNAVAILABLE",
        "AUTHORIZATION_IDENTITY_CHANGED", "AUTHENTICATION_CHANGED"].includes(code) ? "unavailable" : "unconfirmed";
      if (outcome === "unconfirmed") uncertain.current = true;
    }
    finally {
      busy.current = false;
      if (alive.current && window.MastermindMissionHost === host) {
        setPending(false); focusAfterGesture.current = document.activeElement === action.current || document.activeElement === document.body; setMessage(outcome); refresh.current();
      }
    }
  };
  if (window.MastermindMissionHost !== host || !state.acquisition || (!eligible && !pending && !message)) return null;
  return <>
    {(eligible || pending) && <button ref={action} disabled={pending} onClick={() => {void send();}}>{pending ? text.sending : text.action}</button>}
    {message && <p className="muted" role="status" tabIndex={-1} ref={notice}>{text[message]}</p>}
  </>;
}
