// @vitest-environment jsdom
// Actual NativeClient/Host/App; fixed inert local IPC. No auth/browser/HTTP.
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {App} from './App';
import {createNativeClient,type AuthState} from './host';
import {composeMissionHost} from './compose-mission-host';
vi.mock('@tauri-apps/api/core',()=>({invoke:vi.fn(async()=>{throw Error('INERT_UNAVAILABLE');})}));
const account:AuthState={status:'signed_in',reason:null,acquisition:true,content:true};
const ready={schema:'mastermind.native_work_authorization.v1',state:'ELIGIBLE',reason:'WORK_NOT_ESTABLISHED',generation:3};
let dispose=()=>{};
beforeEach(()=>{history.replaceState(null,'','/os/');localStorage.clear();Object.defineProperty(window,'__TAURI_INTERNALS__',{configurable:true,value:{}});});
afterEach(()=>{cleanup();dispose();dispose=()=>{};delete window.MastermindMissionHost;delete(window as unknown as Record<string,unknown>).__TAURI_INTERNALS__;});
async function mount(value:unknown=ready,action:()=>Promise<unknown>=async()=>({status:'signing_in',reason:null,acquisition:false,content:false}),missing=false,locale:'en'|'zh-CN'='en'){
 const handlers=new Map<string,(x:{payload:unknown})=>void>();const invoke=vi.fn(async(c:string,args?:unknown):Promise<unknown>=>{
  if(c==='auth_status')return account;
  if(c==='executive_auth_status')return args?{schema:'mastermind.native_executive_status.v1',generation:3,available:false,configured:true,reason:'NOT_ESTABLISHED',programs_read:{phase:'NOT_OBSERVED',http_status:null}}:{generation:3,available:false};
  if(c==='read_work_authorization')return value;if(c==='sign_in_for_work')return action();
  if(c==='read_programs'||c==='read_work')throw Error('SOURCE_UNAVAILABLE');throw Error('UNEXPECTED_NATIVE_COMMAND');
 });
 const client=await createNativeClient(invoke as never,async(e,h)=>{handlers.set(e,h);return()=>{};});if(missing)delete client.signInForWork;
 const composition=composeMissionHost(client,null,undefined,'native');dispose=composition.dispose;window.MastermindMissionHost=composition.host;
 const view=render(<App locale={locale}/>);await screen.findByRole('button',{name:locale==='en'?'Sign out':'退出登录'});
 return {client,host:composition.host,invoke,view,handlers};
}
const effects=(x:Awaited<ReturnType<typeof mount>>)=>x.invoke.mock.calls.filter(([c])=>['sign_in','sign_in_primary','sign_in_for_work','continue_authorization','executive_intent_submit'].includes(c as string));
it.each(['en','zh-CN'] as const)('reaches first work sign-in only after inspection and gesture: %s',async locale=>{
 const x=await mount(ready,undefined,false,locale),zh=locale==='zh-CN';expect(effects(x)).toHaveLength(0);expect(x.invoke.mock.calls.some(([c])=>c==='read_work_authorization')).toBe(false);
 const entry=screen.getByRole('button',{name:zh?'工作访问':'Work access'});entry.focus();fireEvent.click(entry);
 const action=await screen.findByRole('button',{name:zh?'登录以访问工作':'Sign in for work'});expect(screen.getByText(zh?'将重新登录账户，再请求工作授权；期间账户访问暂时关闭。':'This starts a fresh account sign-in before requesting work authorization. Account access is temporarily withdrawn.')).toBeTruthy();expect(effects(x)).toHaveLength(0);
 fireEvent.click(action);await waitFor(()=>expect(effects(x)).toEqual([['sign_in_for_work']]));expect(x.client.getState().acquisition).toBe(false);
 expect(screen.queryByRole('button',{name:zh?'登录以访问工作':'Sign in for work'})).toBeNull();
});
it('keeps held Executive refusal administrator-only with zero auth and returns focus',async()=>{
 const x=await mount({...ready,state:'ADMIN_ACTION_REQUIRED',reason:'AUTHORIZATION_REFUSED'});const entry=screen.getByRole('button',{name:'Work access'});entry.focus();fireEvent.click(entry);
 expect(await screen.findByText(/Contact your administrator/)).toBeTruthy();expect(screen.queryByRole('button',{name:'Sign in for work'})).toBeNull();expect(effects(x)).toHaveLength(0);
 fireEvent.click(screen.getByRole('button',{name:'Back'}));expect(document.activeElement).toBe(screen.getByRole('button',{name:'Work access'}));expect(effects(x)).toHaveLength(0);
});
it('does not fall back when optional work facet is absent',async()=>{
 const x=await mount(ready,undefined,true);fireEvent.click(screen.getByRole('button',{name:'Work access'}));expect(await screen.findByText('Work sign-in is unavailable here.')).toBeTruthy();expect(effects(x)).toHaveLength(0);
});
it.each(['host','method','generation'] as const)('refuses no-render %s withdrawal at App gesture',async kind=>{
 const x=await mount();fireEvent.click(screen.getByRole('button',{name:'Work access'}));const button=await screen.findByRole('button',{name:'Sign in for work'});
 if(kind==='host')window.MastermindMissionHost={...x.host};else if(kind==='method')x.host.workAuthorization!.signIn=vi.fn();else x.host.invalidationGeneration=()=>999;
 fireEvent.click(button);expect(effects(x)).toHaveLength(0);
});
it('retains lost original handoff without duplicate or legacy fallback',async()=>{
 let reject!:(v:unknown)=>void;const held=new Promise((_,r)=>{reject=r;});const x=await mount(ready,()=>held);fireEvent.click(screen.getByRole('button',{name:'Work access'}));const b=await screen.findByRole('button',{name:'Sign in for work'});fireEvent.click(b);fireEvent.click(b);await waitFor(()=>expect(effects(x)).toEqual([['sign_in_for_work']]));
 await act(async()=>reject(Error('INERT_LOST_HANDOFF')));expect(await screen.findByText(/handoff is unconfirmed/)).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Back'}));fireEvent.click(screen.getByRole('button',{name:'Work access'}));expect(effects(x)).toEqual([['sign_in_for_work']]);
});
