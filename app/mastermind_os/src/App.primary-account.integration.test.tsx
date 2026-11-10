// @vitest-environment jsdom
// Actual NativeClient -> composed Host -> App. Native IPC is an inert fixed owner fixture.
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {App} from './App';
import {createNativeClient,type AuthState} from './host';
import {composeMissionHost} from './compose-mission-host';
vi.mock('@tauri-apps/api/core',()=>({invoke:vi.fn(async()=>{throw new Error('INERT_READINESS_UNAVAILABLE');})}));
const out:AuthState={status:'signed_out',reason:'NATIVE_TOKEN_EXPIRED',acquisition:false,content:false};
const pending:AuthState={status:'signing_in',reason:null,acquisition:false,content:false};
const connected:AuthState={status:'signed_in',reason:null,acquisition:true,content:true};
let dispose=()=>{};
beforeEach(()=>{history.replaceState(null,'','/os/');localStorage.clear();Object.defineProperty(window,'__TAURI_INTERNALS__',{configurable:true,value:{}});});
afterEach(()=>{cleanup();dispose();dispose=()=>{};delete window.MastermindMissionHost;delete (window as unknown as Record<string,unknown>).__TAURI_INTERNALS__;vi.restoreAllMocks();});
async function mount(locale:'en'|'zh-CN'='en',action:()=>Promise<unknown>=async()=>pending,missing=false){
 const handlers=new Map<string,(e:{payload:unknown})=>void>();
 const invoke=vi.fn(async(command:string,args?:unknown):Promise<unknown>=>{
  if(command==='auth_status')return out;
  if(command==='executive_auth_status')return args?{schema:'mastermind.native_executive_status.v1',generation:9,available:false,configured:true,reason:'AUTHORIZATION_REFUSED',programs_read:{phase:'NOT_OBSERVED',http_status:null}}:{generation:9,available:false};
  if(command==='sign_in_primary')return action();
  if(command==='sign_out')return {...out,reason:'USER_SIGNED_OUT'};
  if(command==='read_programs'||command==='read_work')throw new Error('SOURCE_UNAVAILABLE');
  throw new Error('UNEXPECTED_NATIVE_COMMAND');
 });
 const client=await createNativeClient(invoke as never,async(event,handler)=>{handlers.set(event,handler);return ()=>{};});
 if(missing)delete client.signInPrimary;
 const composition=composeMissionHost(client,null,undefined,'native');dispose=composition.dispose;window.MastermindMissionHost=composition.host;
 const view=render(<App locale={locale}/>);
 const publish=async(state:AuthState)=>act(async()=>{
  handlers.get('mastermind-auth-state')!({payload:state});
  // The incumbent native emit publishes the closed account + Executive pair.
  handlers.get('mastermind-executive-auth-state')!({payload:{generation:10,available:false}});
 });
 return {invoke,client,host:composition.host,view,publish};
}
const requests=(x:{invoke:ReturnType<typeof vi.fn>})=>x.invoke.mock.calls.filter(([c])=>c==='sign_in'||c==='sign_in_primary'||c==='continue_authorization'||c==='executive_intent_submit'||c==='executive_session_send');
it.each(['en','zh-CN'] as const)('opens only account authorization on a real App gesture, settles by source event, preserves work refusal: %s',async locale=>{
 const x=await mount(locale),zh=locale==='zh-CN';
 expect(screen.getByRole('alert').textContent).toBe(zh?'应用访问权限已过期。':'Your app access has expired.');expect(requests(x)).toHaveLength(0);
 const button=screen.getByRole('button',{name:zh?'登录账户':'Sign in to account'});
 expect(button.parentElement?.classList.contains('auth-entry__control')).toBe(true);button.focus();fireEvent.click(button);
 await waitFor(()=>expect(requests(x)).toEqual([['sign_in_primary']]));
 await waitFor(()=>expect(document.activeElement).toBe(screen.getByRole('button',{name:zh?'取消登录':'Cancel sign in'})));
 await x.publish(connected);expect(x.view.container.querySelector('.shell')).toBeTruthy();
 expect(screen.getByText(zh?'工作连接不可用':'Work connection unavailable')).toBeTruthy();
 expect((screen.getByRole('button',{name:zh?'新建对话':'New conversation'}) as HTMLButtonElement).disabled).toBe(true);
 fireEvent.click(screen.getByText(zh?'连接详情':'Connection details',{selector:'summary'}));
 await act(async()=>fireEvent.click(screen.getByRole('button',{name:zh?'刷新本地原生诊断':'Refresh local native diagnostics'})));
 expect(screen.getByText(zh?'工作授权未获批准':'Work authorization was not granted')).toBeTruthy();
 expect(x.client.executive!.available()).toBe(false);expect(requests(x)).toEqual([['sign_in_primary']]);
 expect(within(x.view.container.querySelector('.nav-account') as HTMLElement).getByRole('button',{name:zh?'退出登录':'Sign out'})).toBeTruthy();
});
it('keeps unsupported native primary entry disabled and never mounts generic full Sign in',async()=>{
 const x=await mount('en',async()=>pending,true);const b=screen.getByRole('button',{name:'Sign in to account'}) as HTMLButtonElement;
 expect(b.disabled).toBe(true);expect(screen.queryByRole('button',{name:'Sign in'})).toBeNull();
 fireEvent.click(b);expect(requests(x)).toHaveLength(0);expect(screen.getByText('Account sign-in is unavailable here.')).toBeTruthy();
});
it.each(['host','method','epoch'] as const)('refuses actual App no-render %s withdrawal before native dispatch',async kind=>{
 const x=await mount();const b=screen.getByRole('button',{name:'Sign in to account'});
 if(kind==='host')window.MastermindMissionHost={...x.host};
 else if(kind==='method')x.host.primaryAccount!.signIn=vi.fn();
 else x.host.invalidationGeneration=()=>999;
 fireEvent.click(b);expect(requests(x)).toHaveLength(0);
});
it('holds duplicate/lost original handoff without generic retry or a replacement',async()=>{
 let reject!:(x:unknown)=>void;const held=new Promise((_,r)=>{reject=r;});const x=await mount('en',()=>held),b=screen.getByRole('button',{name:'Sign in to account'});
 fireEvent.click(b);fireEvent.click(b);await waitFor(()=>expect(requests(x)).toEqual([['sign_in_primary']]));
 await act(async()=>reject(new Error('INERT_LOST_HANDOFF')));expect(screen.getByText(/handoff is unconfirmed/)).toBeTruthy();
 expect((b as HTMLButtonElement).disabled).toBe(true);fireEvent.click(b);expect(requests(x)).toEqual([['sign_in_primary']]);
});
it('refuses a delayed reply after actual native withdrawal without resurrecting an account grant',async()=>{
 let finish!:(x:unknown)=>void;const held=new Promise(r=>{finish=r;});const x=await mount('en',()=>held);fireEvent.click(screen.getByRole('button',{name:'Sign in to account'}));
 await waitFor(()=>expect(requests(x)).toHaveLength(1));await x.publish({...out,reason:'USER_SIGNED_OUT'});
 await act(async()=>finish(pending));expect(x.client.getState()).toEqual({...out,reason:'USER_SIGNED_OUT'});
 expect(x.view.container.querySelector('.shell')).toBeNull();expect(screen.queryByRole('button',{name:'Cancel sign in'})).toBeNull();expect(requests(x)).toEqual([['sign_in_primary']]);
});

it('retains the incumbent cancel control for an active native flow even without the optional primary facet',async()=>{
 const x=await mount('en',async()=>pending,true);await x.publish(pending);
 const cancel=screen.getByRole('button',{name:'Cancel sign in'});cancel.focus();fireEvent.click(cancel);
 await waitFor(()=>expect(x.invoke.mock.calls.filter(([c])=>c==='sign_out')).toEqual([['sign_out']]));
 expect(requests(x)).toHaveLength(0);expect(screen.queryByRole('button',{name:'Cancel sign in'})).toBeNull();
 expect((screen.getByRole('button',{name:'Sign in to account'}) as HTMLButtonElement).disabled).toBe(true);
});
