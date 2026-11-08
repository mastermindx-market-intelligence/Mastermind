// @vitest-environment jsdom
// Actual App + NativeClient/Host; only native invoke/listen and readiness are inert.
import {cleanup,render,screen,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {App} from './App';
import {createNativeClient,type AuthState} from './host';
import {composeMissionHost} from './compose-mission-host';
vi.mock('@tauri-apps/api/core',()=>({invoke:vi.fn(async()=>{throw new Error('INERT_READINESS_UNAVAILABLE');})}));
let dispose=()=>{};
beforeEach(()=>{history.replaceState(null,'','/os/');localStorage.clear();delete window.MastermindMissionHost;Object.defineProperty(window,'__TAURI_INTERNALS__',{configurable:true,value:{}});});
afterEach(()=>{cleanup();dispose();dispose=()=>{};delete window.MastermindMissionHost;delete (window as unknown as Record<string,unknown>).__TAURI_INTERNALS__;vi.restoreAllMocks();});
async function mount(state:AuthState,locale:'en'|'zh-CN'='en'){
 const invoke=vi.fn(async(command:string):Promise<unknown>=>{
  if(command==='auth_status')return state;
  if(command==='executive_auth_status')return {generation:1,available:false};
  if(command==='read_programs'||command==='read_work')throw new Error('SOURCE_UNAVAILABLE');
  throw new Error('UNEXPECTED_NATIVE_COMMAND');
 });
 const client=await createNativeClient(invoke as never,async()=>()=>{});
 const composition=composeMissionHost(client,null,undefined,'native');dispose=composition.dispose;
 window.MastermindMissionHost=composition.host;
 const view=render(<App locale={locale}/>);
 return {invoke,client,footer:view.container.querySelector('.nav-account')!,container:view.container};
}
it.each(['en','zh-CN'] as const)('explains the observed Content timeout while preserving Workspace sign-in and the original control: %s',async locale=>{
 const e=await mount({status:'error',reason:'AUTH_TRANSACTION_EXPIRED',acquisition:true,content:false},locale);
 const footer=within(e.footer as HTMLElement);
 expect(e.footer.textContent).toContain(locale==='en'?'Workspace signed in':'工作区已登录');
 expect(e.footer.textContent).toContain(locale==='en'?'Content authorization timed out.':'内容访问授权已超时');
 expect(e.footer.textContent).not.toContain(locale==='en'?'Please try again.':'请重试');
 expect(e.footer.textContent).not.toContain(locale==='en'?'Sign-in unavailable':'暂时无法登录');
 expect(footer.getByRole('button',{name:locale==='en'?'Sign out':'退出登录'})).toBeTruthy();
 expect(e.client.getState()).toEqual({status:'error',reason:'AUTH_TRANSACTION_EXPIRED',acquisition:true,content:false});
 expect(e.container.querySelector('.shell')).toBeTruthy();expect(e.container.querySelector('.auth-entry')).toBeNull();
 expect((screen.getByRole('button',{name:locale==='en'?'New conversation':'新建对话'}) as HTMLButtonElement).disabled).toBe(true);
 expect(e.invoke.mock.calls.every(([name])=>['auth_status','executive_auth_status','read_programs','read_work'].includes(name)),e.invoke.mock.calls.map(([name])=>name).join(',')).toBe(true);
});
it('labels the same incomplete grant as pending only while the existing owner is signing in',async()=>{
 const e=await mount({status:'signing_in',reason:null,acquisition:true,content:false});
 expect(e.footer.textContent).toContain('Workspace signed in');expect(e.footer.textContent).toContain('Content authorization is still pending.');
 expect(within(e.footer as HTMLElement).getByRole('button',{name:'Cancel sign in'})).toBeTruthy();
 expect(e.invoke.mock.calls.some(([name])=>name==='sign_in'||name==='sign_out')).toBe(false);
});
it('preserves the existing non-native footer for the same flags without inferring native progress',async()=>{
 delete (window as unknown as Record<string,unknown>).__TAURI_INTERNALS__;
 const e=await mount({status:'error',reason:'AUTH_TRANSACTION_EXPIRED',acquisition:true,content:false});
 expect(e.footer.textContent).toContain('Sign-in unavailable');
 expect(e.footer.textContent).not.toContain('Workspace signed in');
 expect(within(e.footer as HTMLElement).getByRole('button',{name:'Sign out'})).toBeTruthy();
 expect(e.invoke.mock.calls.some(([name])=>name==='sign_in'||name==='sign_out')).toBe(false);
});
