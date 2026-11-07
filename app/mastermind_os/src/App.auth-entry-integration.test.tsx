// @vitest-environment jsdom
/** Actual App presentation branch; auth and preferences are explicit inert
 * owner ports. No browser ceremony, credential or backend proof is claimed. */
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {App} from './App';
import type {AuthState} from './host';
beforeEach(()=>{history.replaceState(null,'','/os/');delete window.MastermindMissionHost;delete (window as any).__TAURI_INTERNALS__;});
afterEach(()=>{cleanup();delete window.MastermindMissionHost;vi.restoreAllMocks();});
it.each(['signed_out','signing_in','error','unconfigured'] as const)('uses only the incumbent explicit auth control in actual private entry: %s',status=>{
 const signIn=vi.fn(async()=>{}),signOut=vi.fn(async()=>{});
 const state:AuthState={status,reason:status==='error'?'POPUP_CLOSED':null,acquisition:false,content:false};
 window.MastermindMissionHost={auth:{getState:()=>state,subscribe:()=>()=>{},signIn,signOut}};
 const view=render(<App preferencesControl={<button type="button">Display preferences</button>}/>);
 expect(view.container.querySelector('.auth-entry')).toBeTruthy();
 expect(view.container.querySelector('.shell')).toBeNull();
 expect(screen.queryByRole('navigation',{name:'Company navigation'})).toBeNull();
 expect(screen.getAllByRole('button',{name:'Display preferences'})).toHaveLength(1);
 expect(signIn).not.toHaveBeenCalled();expect(signOut).not.toHaveBeenCalled();
 const control=screen.getByRole('button',{name:status==='signing_in'?'Cancel sign in':'Sign in'}) as HTMLButtonElement;
 expect(screen.getAllByRole('button',{name:status==='signing_in'?'Cancel sign in':'Sign in'})).toHaveLength(1);
 expect(control.disabled).toBe(status==='unconfigured');
 fireEvent.click(control);
 expect(signIn).toHaveBeenCalledTimes(status==='signed_out'||status==='error'?1:0);
 expect(signOut).toHaveBeenCalledTimes(status==='signing_in'?1:0);
 if(status==='error'){expect(screen.getByRole('alert').textContent).not.toContain('POPUP_CLOSED');expect(screen.getByRole('alert').textContent!.length).toBeGreaterThan(0);}
});
it('does not infer signed-out private entry from an absent auth owner',()=>{
 const view=render(<App/>);expect(view.container.querySelector('.auth-entry')).toBeNull();
 expect(view.container.querySelector('.shell')).toBeTruthy();
});
it('keeps signed-in source-unavailable product state distinct from private entry',()=>{
 const signIn=vi.fn(async()=>{}),signOut=vi.fn(async()=>{});
 window.MastermindMissionHost={auth:{getState:()=>({status:'signed_in',reason:null,acquisition:true,content:false}),subscribe:()=>()=>{},signIn,signOut}};
 const view=render(<App/>);expect(view.container.querySelector('.auth-entry')).toBeNull();
 expect(view.container.querySelector('.shell')).toBeTruthy();expect(screen.getByRole('button',{name:'Sign out'})).toBeTruthy();
 expect(signIn).not.toHaveBeenCalled();expect(signOut).not.toHaveBeenCalled();
});
