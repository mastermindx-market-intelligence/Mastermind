// @vitest-environment jsdom
// Actual NativeClient -> composed Host -> App. Only native IPC is inert.
import {act,cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {App} from './App';
import {createNativeClient,type AuthState} from './host';
import {composeMissionHost} from './compose-mission-host';
vi.mock('@tauri-apps/api/core',()=>({invoke:vi.fn(async()=>{throw new Error('INERT_READINESS_UNAVAILABLE');})}));
let dispose=()=>{};
beforeEach(()=>{history.replaceState(null,'','/os/');localStorage.clear();Object.defineProperty(window,'__TAURI_INTERNALS__',{configurable:true,value:{}});});
afterEach(()=>{cleanup();dispose();dispose=()=>{};delete window.MastermindMissionHost;delete (window as unknown as Record<string,unknown>).__TAURI_INTERNALS__;vi.restoreAllMocks();});
const refusal=()=>({schema:'mastermind.native_executive_status.v1',generation:9,available:false,configured:true,reason:'AUTHORIZATION_REFUSED',programs_read:{phase:'TIMEOUT',http_status:null}});
async function mount(locale:'en'|'zh-CN'='en',flags={acquisition:true,content:true},executive=false){
 const handlers=new Map<string,(e:{payload:unknown})=>void>();
 const invoke=vi.fn(async(command:string,args?:unknown):Promise<unknown>=>{
  if(command==='auth_status')return {status:'signed_in',reason:null,...flags};
  if(command==='executive_auth_status')return args?refusal():{generation:9,available:executive};
  if(command==='read_programs'||command==='read_work')throw new Error('SOURCE_UNAVAILABLE');
  throw new Error('UNEXPECTED_NATIVE_COMMAND');
 });
 const client=await createNativeClient(invoke as never,async(event,handler)=>{handlers.set(event,handler);return ()=>{};});
 const composition=composeMissionHost(client,null,undefined,'native');dispose=composition.dispose;
 window.MastermindMissionHost=composition.host;
 const view=render(<App locale={locale}/>);
 return {invoke,client,host:composition.host,handlers,view};
}
const details=(locale='en')=>screen.getByText(locale==='en'?'Connection details':'连接详情',{selector:'summary'});
const readButton=(locale='en')=>screen.getByRole('button',{name:locale==='en'?'Refresh local native diagnostics':'刷新本地原生诊断',hidden:true});
it.each(['en','zh-CN'] as const)('separates reported account/content access from unavailable work and an explicitly read refusal: %s',async locale=>{
 const f=await mount(locale);
 expect(screen.getByText(locale==='en'?'Work connection unavailable':'工作连接不可用')).toBeTruthy();
 expect(screen.getByText(locale==='en'?'Your latest sign-in status reports account and content access.':'最近的登录状态显示账户和内容访问已连接。')).toBeTruthy();
 expect(f.view.container.textContent).not.toContain(locale==='en'?'Work authorization was not granted':'工作授权未获批准');
 const before=f.invoke.mock.calls.length;
 const summary=details(locale);fireEvent.click(summary);
 expect((summary.parentElement as HTMLDetailsElement).open).toBe(true);
 expect(f.invoke.mock.calls).toHaveLength(before);
 await act(async()=>fireEvent.click(readButton(locale)));
 expect(f.invoke.mock.calls.slice(before)).toEqual([['executive_auth_status',{diagnostics:true}]]);
 expect(screen.getByText(locale==='en'?'Work authorization was not granted':'工作授权未获批准')).toBeTruthy();
 expect(f.view.container.textContent).toContain(locale==='en'?'The latest local observation reports that work authorization was not granted.':'最近的本地观察显示工作授权未获批准。');
 expect(f.view.container.textContent).toContain('TIMEOUT');expect(f.view.container.textContent).not.toContain('503');
 expect(within(f.view.container.querySelector('.nav-account') as HTMLElement).getByRole('button',{name:locale==='en'?'Sign out':'退出登录'})).toBeTruthy();
 expect(f.invoke.mock.calls.some(([c])=>['sign_in','continue_authorization','sign_out','executive_context'].includes(c))).toBe(false);
});
it('keeps a single pending local read and focuses the existing control after the result',async()=>{
 const f=await mount();fireEvent.click(details());let resolve!:(v:unknown)=>void;
 f.invoke.mockImplementationOnce(()=>new Promise(done=>{resolve=done;}));const button=readButton();button.focus();
 await act(async()=>{fireEvent.click(button);fireEvent.click(button);});
 expect(f.invoke.mock.calls.filter(([c,a])=>c==='executive_auth_status'&&a)).toHaveLength(1);
 expect((button as HTMLButtonElement).disabled).toBe(true);
 await act(async()=>resolve(refusal()));expect(document.activeElement).toBe(button);
 expect((button as HTMLButtonElement).disabled).toBe(false);
});
it('withdraws a pending reason on native auth loss rather than resurfacing it later',async()=>{
 const f=await mount();fireEvent.click(details());let resolve!:(v:unknown)=>void;
 f.invoke.mockImplementationOnce(()=>new Promise(done=>{resolve=done;}));await act(async()=>fireEvent.click(readButton()));
 await act(async()=>f.handlers.get('mastermind-auth-state')!({payload:{status:'signed_out',reason:null,acquisition:false,content:false} satisfies AuthState}));
 await act(async()=>resolve(refusal()));
 expect(screen.queryByText('Work authorization was not granted')).toBeNull();expect(screen.queryByText('Work connection unavailable')).toBeNull();
 expect(f.view.container.textContent).toContain('Sign in to your workspace.');
 expect(f.invoke.mock.calls.some(([c])=>['sign_in','continue_authorization','sign_out'].includes(c))).toBe(false);
});
it('refuses a no-render Host replacement before any local dispatch',async()=>{
 const f=await mount();fireEvent.click(details());const button=readButton(),before=f.invoke.mock.calls.length;
 window.MastermindMissionHost={...f.host};await act(async()=>fireEvent.click(button));
 expect(f.invoke.mock.calls).toHaveLength(before);expect(screen.queryByText('Work authorization was not granted')).toBeNull();
 expect(f.view.container.textContent).not.toContain('LAST_EXPLICIT_LOCAL_READ');
});
it.each([{acquisition:true,content:false},{acquisition:false,content:true}])('does not claim account/content connection when either reported grant is absent: %j',async flags=>{
 await mount('en',flags);expect(screen.queryByText('Your latest sign-in status reports account and content access.')).toBeNull();
 expect(screen.queryByText('Connection details',{selector:'summary'})).toBeNull();
});
it('does not add an authorization warning when the existing work transport reports available',async()=>{
 await mount('en',{acquisition:true,content:true},true);
 expect(screen.queryByText('Work connection unavailable')).toBeNull();expect(screen.queryByText('Work authorization was not granted')).toBeNull();
});

it('replaces an old refusal only with the next qualified local observation, without granting work access',async()=>{
 const f=await mount();fireEvent.click(details());await act(async()=>fireEvent.click(readButton()));
 expect(screen.getByText('Work authorization was not granted')).toBeTruthy();
 f.invoke.mockImplementationOnce(async()=>({...refusal(),available:true,reason:'AVAILABLE'}));
 await act(async()=>fireEvent.click(readButton()));
 expect(screen.queryByText('Work authorization was not granted')).toBeNull();expect(screen.getByText('Work connection not confirmed')).toBeTruthy();
 expect(f.client.executive!.available()).toBe(false);expect((screen.getByRole('button',{name:'New conversation'}) as HTMLButtonElement).disabled).toBe(true);
});
it('does not echo a failed local read or turn it into an authorization refusal',async()=>{
 const f=await mount();fireEvent.click(details());f.invoke.mockImplementationOnce(async()=>{throw new Error('PRIVATE_PROVIDER_DETAIL');});
 await act(async()=>fireEvent.click(readButton()));
 expect(f.view.container.textContent).toContain('Local diagnostics unavailable.');
 expect(f.view.container.textContent).not.toContain('PRIVATE_PROVIDER_DETAIL');expect(screen.queryByText('Work authorization was not granted')).toBeNull();
});
