// @vitest-environment jsdom
// Native source event -> existing NativeClient/Host -> actual App presentation.
import {act,cleanup,render,screen} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {App} from './App';
import {createNativeClient,type AuthState} from './host';
import {composeMissionHost} from './compose-mission-host';
vi.mock('@tauri-apps/api/core',()=>({invoke:vi.fn(async()=>{throw new Error('INERT_READINESS_UNAVAILABLE');})}));
let dispose=()=>{};
beforeEach(()=>{history.replaceState(null,'','/os/');localStorage.clear();Object.defineProperty(window,'__TAURI_INTERNALS__',{configurable:true,value:{}});});
afterEach(()=>{cleanup();dispose();dispose=()=>{};delete window.MastermindMissionHost;delete (window as unknown as Record<string,unknown>).__TAURI_INTERNALS__;vi.restoreAllMocks();});
async function mount(locale:'en'|'zh-CN'){
 const handlers=new Map<string,(e:{payload:unknown})=>void>();
 const invoke=vi.fn(async(command:string):Promise<unknown>=>{
  if(command==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:true};
  if(command==='executive_auth_status')return {generation:9,available:false};
  if(command==='read_programs'||command==='read_work')throw new Error('SOURCE_UNAVAILABLE');
  throw new Error('UNEXPECTED_NATIVE_COMMAND');
 });
 const client=await createNativeClient(invoke as never,async(event,handler)=>{handlers.set(event,handler);return ()=>{};});
 const composition=composeMissionHost(client,null,undefined,'native');dispose=composition.dispose;window.MastermindMissionHost=composition.host;
 const view=render(<App locale={locale}/>);
 const publish=async(state:AuthState)=>act(async()=>handlers.get('mastermind-auth-state')!({payload:state}));
 return {invoke,client,view,publish};
}
it.each(['en','zh-CN'] as const)('distinguishes actual closed native expiry, unfinished timeout and resource-neutral refusal without another auth request: %s',async locale=>{
 const f=await mount(locale);
 for(const [reason,status,en,zh] of [
  ['NATIVE_TOKEN_EXPIRED','signed_out','Your app access has expired.','应用访问权限已过期。'],
  ['AUTH_TRANSACTION_EXPIRED','error','The authorization attempt timed out before it completed.','本次授权尚未完成便已超时。'],
  ['AUTHORIZATION_REFUSED','error','Authorization was not granted.','授权未获批准。'],
 ] as const){
  await f.publish({status,reason,acquisition:false,content:false});
  expect(screen.getByRole('alert').textContent).toBe(locale==='en'?en:zh);
  expect(screen.getByRole('button',{name:locale==='en'?'Sign in':'登录'})).toBeTruthy();
  expect(f.view.container.textContent).not.toContain(locale==='en'?'Continue in your browser, then return here.':'在浏览器中继续，完成后返回此处。');
  expect(f.view.container.textContent).not.toContain('Work authorization was not granted');
  expect(f.client.getState()).toEqual({status,reason,acquisition:false,content:false});
 }
 expect(f.invoke.mock.calls.some(([c])=>['sign_in','sign_out','continue_authorization'].includes(c))).toBe(false);
});
it('does not turn an unknown timeout-like native reason into a proven timeout or echo it',async()=>{
 const f=await mount('en');await f.publish({status:'error',reason:'UNRECOGNIZED_TIMEOUT_PRIVATE',acquisition:false,content:false});
 expect(screen.getByRole('alert').textContent).toBe('Sign-in could not complete. Please try again.');
 expect(f.view.container.textContent).not.toContain('UNRECOGNIZED_TIMEOUT_PRIVATE');expect(screen.getByRole('alert').textContent).not.toContain('timed out');
});
it('keeps the original active-flow control and does not expose browser-continuation guidance in a settled entry',async()=>{
 const f=await mount('en');await f.publish({status:'signing_in',reason:null,acquisition:false,content:false});
 expect(screen.getByRole('button',{name:'Cancel sign in'})).toBeTruthy();expect(screen.queryByRole('alert')).toBeNull();
 await f.publish({status:'signed_out',reason:null,acquisition:false,content:false});
 expect(screen.getByRole('button',{name:'Sign in'})).toBeTruthy();expect(f.view.container.textContent).not.toContain('Continue in your browser, then return here.');
 expect(f.invoke.mock.calls.some(([c])=>['sign_in','sign_out','continue_authorization'].includes(c))).toBe(false);
});
