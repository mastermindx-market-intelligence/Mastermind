// @vitest-environment jsdom
// Actual NativeClient/Host/App; fixed inert local IPC. No auth/browser/HTTP.
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {App} from './App';
import nativeFixture from './fixtures/native-work-authorization-source.json';
import {createNativeClient,type AuthState} from './host';
import {composeMissionHost} from './compose-mission-host';
vi.mock('@tauri-apps/api/core',()=>({invoke:vi.fn(async()=>{throw Error('INERT_UNAVAILABLE');})}));
const account:AuthState={status:'signed_in',reason:null,acquisition:true,content:true};
const ready = nativeFixture.active;
let dispose=()=>{};
beforeEach(()=>{history.replaceState(null,'','/os/');localStorage.clear();Object.defineProperty(window,'__TAURI_INTERNALS__',{configurable:true,value:{}});});
afterEach(()=>{cleanup();dispose();dispose=()=>{};delete window.MastermindMissionHost;delete(window as unknown as Record<string,unknown>).__TAURI_INTERNALS__;});
async function mount(read: () => Promise<unknown> = async () => ready, missing = false, locale: 'en' | 'zh-CN' = 'en'){
 const handlers=new Map<string,(x:{payload:unknown})=>void>();const invoke=vi.fn(async(c:string,args?:unknown):Promise<unknown>=>{
  if(c==='auth_status')return account;
  if(c==='executive_auth_status')return args?{schema:'mastermind.native_executive_status.v1',generation:3,available:false,configured:true,reason:'NOT_ESTABLISHED',programs_read:{phase:'NOT_OBSERVED',http_status:null}}:{generation:3,available:false};
  if(c==='read_work_authorization')return read();
  if(c==='read_programs'||c==='read_work')throw Error('SOURCE_UNAVAILABLE');throw Error('UNEXPECTED_NATIVE_COMMAND');
 });
 const client=await createNativeClient(invoke as never,async(e,h)=>{handlers.set(e,h);return()=>{};});if(missing)delete client.readWorkAuthorization;
 const composition=composeMissionHost(client,null,undefined,'native');dispose=composition.dispose;window.MastermindMissionHost=composition.host;
 const view=render(<App locale={locale}/>);await screen.findByRole('button',{name:locale==='en'?'Sign out':'退出登录'});
 return {client,host:composition.host,invoke,view,handlers};
}
const effects=(x:Awaited<ReturnType<typeof mount>>)=>x.invoke.mock.calls.filter(([c])=>['sign_in','sign_in_primary','sign_in_for_work','continue_authorization','executive_intent_submit'].includes(c as string));

it.each(['en', 'zh-CN'] as const)('inspects unavailable work access without changing A/C: %s', async locale => {
 const x = await mount(undefined, false, locale);
 const zh = locale === 'zh-CN';
 expect(x.invoke.mock.calls.some(([command]) => command === 'read_work_authorization')).toBe(false);
 const entry = screen.getByRole('button', {name: zh ? '工作访问' : 'Work access'});
 entry.focus();
 fireEvent.click(entry);
 expect(await screen.findByText(zh ? '此处暂时无法进行工作登录。' : 'Work sign-in is unavailable here.')).toBeTruthy();
 expect(x.invoke.mock.calls.filter(([command]) => command === 'read_work_authorization')).toEqual([['read_work_authorization']]);
 expect(screen.queryByRole('button', {name: zh ? '登录以访问工作' : 'Sign in for work'})).toBeNull();
 expect(x.client.getState()).toEqual(account);
 expect(effects(x)).toHaveLength(0);
 fireEvent.click(screen.getByRole('button', {name: zh ? '返回' : 'Back'}));
 expect(document.activeElement).toBe(screen.getByRole('button', {name: zh ? '工作访问' : 'Work access'}));
});

it('keeps held Executive refusal administrator-only', async () => {
 const x = await mount(async () => nativeFixture.refused);
 fireEvent.click(screen.getByRole('button', {name: 'Work access'}));
 expect(await screen.findByText(/Contact your administrator/)).toBeTruthy();
 expect(screen.queryByRole('button', {name: 'Sign in for work'})).toBeNull();
 expect(effects(x)).toHaveLength(0);
 expect(x.client.getState()).toEqual(account);
});

it('withholds the executable work action when older native metadata claims ELIGIBLE', async () => {
 const x = await mount(async () => nativeFixture.initial);
 fireEvent.click(screen.getByRole('button', {name: 'Work access'}));
 await waitFor(() => expect(x.invoke.mock.calls.filter(([c]) => c === 'read_work_authorization')).toEqual([['read_work_authorization']]));
 expect(await screen.findByText('Work sign-in is unavailable here.')).toBeTruthy();
 expect(screen.queryByRole('button', {name: 'Sign in for work'})).toBeNull();
 expect(effects(x)).toHaveLength(0);
});

it('does not fall back when the optional local observation is absent', async () => {
 const x = await mount(undefined, true);
 fireEvent.click(screen.getByRole('button', {name: 'Work access'}));
 expect(await screen.findByText('Work sign-in is unavailable here.')).toBeTruthy();
 expect(x.invoke.mock.calls.some(([command]) => command === 'read_work_authorization')).toBe(false);
 expect(effects(x)).toHaveLength(0);
});

it.each(['method', 'generation', 'back', 'auth', 'host'] as const)('discards a late local refusal after %s withdrawal', async kind => {
 let finish!: (value: unknown) => void;
 const pending = new Promise(resolve => { finish = resolve; });
 const x = await mount(() => pending);
 fireEvent.click(screen.getByRole('button', {name: 'Work access'}));
 await screen.findByText('Checking local work access…');
 if (kind === 'method') x.host.workAuthorization!.read = vi.fn();
 if (kind === 'generation') x.host.invalidationGeneration = () => 999;
 if (kind === 'back') fireEvent.click(screen.getByRole('button', {name: 'Back'}));
 if (kind === 'host') window.MastermindMissionHost = {...x.host};
 if (kind === 'auth') await act(async () => {
   x.handlers.get('mastermind-auth-state')!({payload:{status:'signed_out',reason:'USER_SIGNED_OUT',acquisition:false,content:false}});
 });
 await act(async () => finish(nativeFixture.refused));
 expect(screen.queryByText(/Contact your administrator/)).toBeNull();
 expect(screen.queryByRole('button', {name: 'Sign in for work'})).toBeNull();
 expect(effects(x)).toHaveLength(0);
});
