// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';
import {createSourcesAppFixture,sourcesTitle,sourcesWorkRef} from './discovery/sources-app-fixture';
let dispose=()=>{};
beforeEach(async()=>{history.replaceState(null,'','/os/');delete window.MastermindMissionHost;
 const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');vi.stubGlobal('crypto',webcrypto);});
afterEach(()=>{cleanup();dispose();delete window.MastermindMissionHost;vi.unstubAllGlobals();});
async function setup(){const e=await createSourcesAppFixture(new IDBFactory());window.MastermindMissionHost=e.host;
 const ui=render(<App/>);dispose=()=>{ui.unmount();e.dispose();};
 fireEvent.click(screen.getByRole('button',{name:'Projects',exact:true}));
 fireEvent.click(await screen.findByRole('button',{name:`Open project ${sourcesTitle}`}));
 fireEvent.click(screen.getByRole('button',{name:'Search',exact:true}));
 const input=await screen.findByLabelText('Search this project');
 await waitFor(()=>expect(input).toHaveProperty('disabled',false));
 fireEvent.change(input,{target:{value:'literal'}});fireEvent.submit(input.closest('form')!);
 await within(document.querySelector('.project-search') as HTMLElement).findByRole('button',{name:'Open',exact:true});
 fireEvent.click(screen.getByText('Advanced',{selector:'summary'}));fireEvent.click(screen.getByRole('button',{name:'Sources',exact:true}));
 await screen.findByRole('heading',{name:'Sources',level:1});return e;}
it('inspects actual source provenance and returns to the same acquired project Search query without new reads',async()=>{
 const e=await setup(),list=within(screen.getByRole('region',{name:'Supplied sources'}));
 expect(screen.getByText('Sources and scope',{selector:'summary'}).parentElement).toHaveProperty('open',false);
 const button=list.getAllByRole('button')[0];fireEvent.click(button);
 const detail=within(screen.getByRole('complementary',{name:'Source details'}));
 expect(document.activeElement).toBe(detail.getByRole('heading',{level:2}));
 const expected=button.textContent;fireEvent.click(detail.getByRole('button',{name:'Close source details'}));
 expect(document.activeElement).toBe(button);expect(button.textContent).toBe(expected);
 fireEvent.click(button);fireEvent.keyDown(detail.getByRole('heading',{level:2}),{key:'Escape'});expect(document.activeElement).toBe(button);
 const reads=e.calls.length;fireEvent.click(screen.getByRole('button',{name:'Back to search',exact:true}));
 expect(screen.getByLabelText('Search this project')).toHaveProperty('value','literal');
 expect(document.activeElement).toBe(screen.getByLabelText('Search this project'));
 expect(e.calls.length).toBe(reads);
 const scoped=e.calls.filter(c=>c.command.startsWith('read_project_knowledge_'));
 expect(scoped.length).toBeGreaterThan(0);
 expect(scoped.every(c=>(c.args as {selection:{work_ref:string}}).selection.work_ref===sourcesWorkRef)).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Sources',exact:true}));
 await screen.findByRole('heading',{name:'Sources',level:1});
 expect(screen.queryByRole('button',{name:'Close source details'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Back to search',exact:true}));
 expect(screen.getByLabelText('Search this project')).toHaveProperty('value','literal');
 expect(document.activeElement).toBe(screen.getByLabelText('Search this project'));
 expect(e.calls.filter(c=>/prepare|submit|consume|create|send|pause|resume|reconcile/.test(c.command))).toHaveLength(0);
});
it('does not revive a detached return or private query after actual auth withdrawal',async()=>{
 const e=await setup(),back=screen.getByRole('button',{name:'Back to search',exact:true});
 act(()=>e.notify('mastermind-auth-state',{status:'signed_out',reason:null,acquisition:false,content:false}));
 fireEvent.click(back);expect(document.body.textContent).not.toContain(sourcesWorkRef);
 expect(document.querySelector<HTMLInputElement>('.project-search__input')?.value).not.toBe('literal');
 expect(e.calls.filter(c=>/prepare|submit|consume|create|send/.test(c.command))).toHaveLength(0);
});
it('refuses the detached parent return after actual Host replacement',async()=>{
 const e=await setup(),back=screen.getByRole('button',{name:'Back to search',exact:true});
 const count=e.calls.length;window.MastermindMissionHost={...e.host};fireEvent.click(back);
 expect(screen.getByRole('heading',{name:'Sources',level:1})).toBeTruthy();expect(e.calls.length).toBe(count);
});
