import {useLayoutEffect, useRef, useState} from 'react';
import type {AuthState, MissionHost} from './host';
import type {WorkAuthorization} from './native-work-authorization';

interface Props {
  host: MissionHost | undefined;
  state: AuthState;
  revision: number;
  locale: 'en' | 'zh-CN';
}

export function NativeWorkAuthorizationControl({host, state, revision, locale}: Props) {
  const translate = (en: string, zh: string) => locale === 'zh-CN' ? zh : en;
  const owner = host?.workAuthorization;
  const [open, setOpen] = useState(false);
  const [reading, setReading] = useState(false);
  const [observation, setObservation] = useState<{value: WorkAuthorization; current(): boolean} | null>(null);
  const request = useRef<AbortController | null>(null);
  const entry = useRef<HTMLButtonElement>(null);
  const notice = useRef<HTMLParagraphElement>(null);
  const returnFocus = useRef(false);
  const inspectFocus = useRef(false);

  useLayoutEffect(() => {
    request.current?.abort();
    setObservation(null);
    setReading(false);
    return () => request.current?.abort();
  }, [host, owner, revision, state.status, state.reason, state.acquisition, state.content]);

  useLayoutEffect(() => {
    if (returnFocus.current && !open) {
      returnFocus.current = false;
      entry.current?.focus();
    } else if (inspectFocus.current && !reading && notice.current) {
      inspectFocus.current = false;
      if (document.activeElement === document.body) notice.current.focus();
    }
  }, [open, reading, observation]);

  async function inspect() {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    inspectFocus.current = document.activeElement === entry.current;
    setOpen(true);
    setObservation(null);
    if (!host || !owner || !host.auth || !host.invalidationGeneration) return;

    const {auth, invalidationGeneration: generation} = host;
    const {getState} = auth;
    const {read} = owner;
    const epoch = generation.call(host);
    const current = () => {
      try {
        if (controller.signal.aborted || window.MastermindMissionHost !== host ||
            host.auth !== auth || auth.getState !== getState ||
            host.workAuthorization !== owner || owner.read !== read ||
            host.invalidationGeneration !== generation ||
            !Number.isSafeInteger(epoch) || generation.call(host) !== epoch) return false;
        const now = getState.call(auth);
        return now.status === state.status && now.reason === state.reason &&
          now.acquisition === state.acquisition && now.content === state.content;
      } catch {
        return false;
      }
    };

    if (!current()) return;
    setReading(true);
    try {
      const value = await read.call(owner, {signal: controller.signal});
      if (current()) setObservation({value, current});
    } catch {
      // A missing or unrecognized observation leaves the inspector unavailable.
    } finally {
      if (!controller.signal.aborted) setReading(false);
    }
  }

  if (state.status !== 'signed_in' || !state.acquisition || !state.content ||
      window.MastermindMissionHost !== host) return null;
  if (!open) return <button type="button" ref={entry} onClick={() => { void inspect(); }}>{translate('Work access', '工作访问')}</button>;

  const refused = observation?.current() && observation.value.state === 'ADMIN_ACTION_REQUIRED';
  return <>
    <p className="muted" role="status" tabIndex={-1} ref={notice}>
      {reading ? translate('Checking local work access…', '正在检查本地工作访问…')
        : refused ? translate('Work authorization was not granted. Contact your administrator. Retrying this authorization is unavailable here.',
            '工作授权未获批准。请联系管理员；此处不能重试该授权。')
          : translate('Work sign-in is unavailable here.', '此处暂时无法进行工作登录。')}
    </p>
    <button type="button" onClick={() => {
      request.current?.abort();
      returnFocus.current = true;
      inspectFocus.current = false;
      setOpen(false);
      setObservation(null);
      setReading(false);
    }}>{translate('Back', '返回')}</button>
  </>;
}
