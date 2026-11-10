// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';
import {createToolsAppFixture,toolsTitle,toolsWorkRef} from './discovery/tools-app-fixture';
let dispose=()=>{};
beforeEach(async()=>{history.replaceState(null,'','/os/');delete window.MastermindMissionHost;
 const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');vi.stubGlobal('crypto',webcrypto);});
afterEach(()=>{cleanup();dispose();delete window.MastermindMissionHost;vi.unstubAllGlobals();});
async function setup(){const e=await createToolsAppFixture(new IDBFactory());window.MastermindMissionHost=e.host;
 const ui=render(<App/>);dispose=()=>{ui.unmount();e.dispose();};
 fireEvent.click(screen.getByRole('button',{name:'Projects',exact:true}));
 fireEvent.click(await screen.findByRole('button',{name:`Open project ${toolsTitle}`}));
 await waitFor(()=>expect(e.calls.some(c=>c.command==='read_mission_v3')).toBe(true));
 fireEvent.click(screen.getByText('Advanced',{selector:'summary'}));fireEvent.click(screen.getByRole('button',{name:'Tools',exact:true}));
 return e;}
it('uses genuine selected context and existing capability navigation while unavailable tools stay inert',async()=>{
 const e=await setup();await screen.findByRole('heading',{name:'Tools',level:1});
 const list=within(screen.getByRole('region',{name:'Other tools'}));
 fireEvent.click(list.getByRole('button',{name:'Placement',exact:true}));
 const inspector=within(screen.getByRole('region',{name:'Selected tool'}));
 expect(document.activeElement).toBe(inspector.getByRole('heading',{name:'Selected tool'}));
 fireEvent.click(inspector.getByRole('button',{name:'Back to tools'}));expect(document.activeElement).toBe(list.getByRole('button',{name:'Placement',exact:true}));
 expect(inspector.getByRole('button',{name:'Open placement'})).toHaveProperty('disabled',true);
 expect(inspector.getByText('Placement is not connected to this view.')).toBeTruthy();
 expect(inspector.getByText('Why unavailable',{selector:'summary'}).parentElement).toHaveProperty('open',false);
 fireEvent.click(list.getByRole('button',{name:'Source context',exact:true}));
 const open=inspector.getByRole('button',{name:'Open source context'});expect(open).toHaveProperty('disabled',false);
 expect(inspector.getAllByText('Read only',{exact:true})).toHaveLength(1);
 const context=inspector.getByText('Project context',{selector:'summary'});
 expect(context.parentElement?.tagName).toBe('DETAILS');expect(context.parentElement).toHaveProperty('open',false);
 fireEvent.click(open);await screen.findByRole('heading',{name:'Sources',level:1});
 fireEvent.click(screen.getByRole('button',{name:'Back to tools',exact:true}));
 const returned=within(screen.getByRole('region',{name:'Selected tool'}));
 expect(returned.getByRole('heading',{name:'Source context',level:3})).toBeTruthy();
 expect(document.activeElement).toBe(within(screen.getByRole('region',{name:'Other tools'})).getByRole('button',{name:'Source context',exact:true}));
 expect(e.calls.filter(c=>/submit|prepare|create|send|consume|pause|resume|source_operation/.test(c.command))).toHaveLength(0);
 expect(new URLSearchParams(location.search).get('work_ref')).toBe(toolsWorkRef);
});

it('preserves selector order and changes focus only for explicit selection, Back and Escape',async()=>{
 await setup();const list=within(screen.getByRole('region',{name:'Other tools'}));
 const selectors=list.getAllByRole('button'),order=selectors.map(n=>n.textContent);
 const release=list.getByRole('button',{name:'Release',exact:true});release.focus();
 expect(within(screen.getByRole('region',{name:'Selected tool'})).queryByRole('heading',{name:'Release'})).toBeNull();
 fireEvent.click(release);const heading=within(screen.getByRole('region',{name:'Selected tool'})).getByRole('heading',{name:'Selected tool'});
 expect(document.activeElement).toBe(heading);fireEvent.keyDown(heading,{key:'Escape'});
 expect(document.activeElement).toBe(release);expect(list.getAllByRole('button').map(n=>n.textContent)).toEqual(order);
});
it('clears the owned return and project metadata on actual auth withdrawal without offering a command',async()=>{
 const e=await setup(),list=within(screen.getByRole('region',{name:'Other tools'}));
 fireEvent.click(list.getByRole('button',{name:'Source context',exact:true}));
 fireEvent.click(screen.getByRole('button',{name:'Open source context'}));await screen.findByRole('heading',{name:'Sources',level:1});
 const back=screen.getByRole('button',{name:'Back to tools',exact:true});
 act(()=>e.notify('mastermind-auth-state',{status:'signed_out',reason:null,acquisition:false,content:false}));
 expect(screen.queryByRole('button',{name:'Back to tools',exact:true})).toBeNull();
 fireEvent.click(back);expect(e.calls.filter(c=>/submit|prepare|create|send|consume|pause|resume|source_operation/.test(c.command))).toHaveLength(0);
 expect(document.body.textContent).not.toContain(toolsWorkRef);
});
