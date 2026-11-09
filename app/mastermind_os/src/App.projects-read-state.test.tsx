// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {App} from './App';import {createNativeClient} from './host';import {composeMissionHost} from './compose-mission-host';
import actual from './fixtures/project-discovery-app-source.json';
vi.mock('@tauri-apps/api/core',()=>({invoke:vi.fn(async()=>{throw new Error('INERT_READINESS_UNAVAILABLE');})}));
let dispose=()=>{};
beforeEach(()=>{history.replaceState(null,'','/os/');localStorage.clear();Object.defineProperty(window,'__TAURI_INTERNALS__',{configurable:true,value:{}});});
afterEach(()=>{cleanup();dispose();dispose=()=>{};delete window.MastermindMissionHost;delete (window as unknown as Record<string,unknown>).__TAURI_INTERNALS__;vi.restoreAllMocks();});
function deferred(){let resolve!:(v:unknown)=>void,reject!:(v:unknown)=>void;const promise=new Promise((y,n)=>{resolve=y;reject=n;});return {promise,resolve,reject};}
async function setup(locale:'en'|'zh-CN'='en'){
 let current=deferred();const handlers=new Map<string,(x:{payload:unknown})=>void>();
 const invoke=vi.fn(async(command:string):Promise<unknown>=>{
  if(command==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:true};
  if(command==='executive_auth_status')return {generation:3,available:false};
  if(command==='read_programs')return current.promise;
  throw new Error('SOURCE_UNAVAILABLE');
 });
 const raw=await createNativeClient(invoke as never,async(event,handler)=>{handlers.set(event,handler);return ()=>{};});
 const joined=composeMissionHost(raw,null,undefined,'native');dispose=joined.dispose;window.MastermindMissionHost=joined.host;
 const view=render(<App locale={locale}/>);await waitFor(()=>expect(invoke.mock.calls.filter(([c])=>c==='read_programs')).toHaveLength(1));
 fireEvent.click(screen.getByRole('button',{name:locale==='en'?'Projects':'项目'}));
 return {invoke,host:joined.host,view,handlers,held:()=>current,next:()=>{current=deferred();return current;},reads:()=>invoke.mock.calls.filter(([c])=>c==='read_programs')};
}
it.each(['en','zh-CN'] as const)('shows real pending and failed read states, then supplied current rows after one explicit refresh without archive permission: %s',async locale=>{
 const x=await setup(locale),zh=locale==='zh-CN';
 expect(screen.getByText(zh?'正在读取项目…':'Reading projects…')).toBeTruthy();
 expect(x.view.container.textContent).not.toContain('No projects were supplied by the current read.');
 await act(async()=>x.held().reject(new Error('SOURCE_UNAVAILABLE')));
 expect(screen.getByText(zh?'项目暂不可用；当前项目列表尚未确认。':'Projects are unavailable right now. The current project list could not be confirmed.')).toBeTruthy();
 expect(x.view.container.textContent).not.toContain('0 projects');expect(x.view.container.textContent).not.toContain('No projects were supplied by the current read.');
 const next=x.next(),button=screen.getByRole('button',{name:'Refresh Projects'});button.focus();fireEvent.click(button);fireEvent.click(button);
 await waitFor(()=>expect(x.reads()).toHaveLength(2));expect(screen.getByText(zh?'正在读取项目…':'Reading projects…')).toBeTruthy();
 await act(async()=>next.resolve(structuredClone(actual.programs_before)));
 expect(await screen.findByText(actual.programs_before.control_room.work[0].work_ref)).toBeTruthy();
 expect(document.activeElement).toBe(button);expect(x.reads()).toHaveLength(2);
 expect(screen.queryByText(zh?'项目暂不可用；当前项目列表尚未确认。':'Projects are unavailable right now. The current project list could not be confirmed.')).toBeNull();
 expect(x.invoke.mock.calls.some(([c])=>['read_project_archive','sign_in','sign_in_primary','continue_authorization','executive_intent_submit'].includes(c))).toBe(false);
 expect(screen.getByRole('button',{name:zh?'新建项目':'New project'})).toBeTruthy();
});
it('withholds a late catalogue after no-render Host replacement and never calls it qualified empty',async()=>{
 const x=await setup();window.MastermindMissionHost={...x.host};await act(async()=>x.held().resolve(structuredClone(actual.programs_before)));
 expect(screen.getByText('Projects are unavailable right now. The current project list could not be confirmed.')).toBeTruthy();
 expect(screen.queryByText(actual.programs_before.control_room.work[0].work_ref)).toBeNull();expect(x.reads()).toHaveLength(1);
});
it('does not resurface catalogue rows after native acquisition withdrawal',async()=>{
 const x=await setup();await act(async()=>x.handlers.get('mastermind-auth-state')!({payload:{status:'signed_out',reason:'NATIVE_TOKEN_EXPIRED',acquisition:false,content:false}}));
 await act(async()=>x.held().resolve(structuredClone(actual.programs_before)));
 expect(screen.queryByText(actual.programs_before.control_room.work[0].work_ref)).toBeNull();expect(x.view.container.querySelector('.auth-entry')).toBeTruthy();expect(x.reads()).toHaveLength(1);
});
