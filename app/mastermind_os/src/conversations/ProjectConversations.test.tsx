// @vitest-environment jsdom
/** Actual temporary Runtime/NativeReplyReader DTO; auth/transport are explicit
 * local fixtures. This is source-to-consumer proof, not installed auth proof. */
import {afterEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen} from '@testing-library/react';
import fixture from '../fixtures/project-conversation-catalogue-owner.json';
import {ProjectConversations} from './ProjectConversations';
import {createProjectConversationCatalogueOwner,type ProjectConversationCatalogueTransport} from './project-conversation-catalogue-owner';
afterEach(cleanup);

function make(){
  const state={work:fixture.catalogue.work_ref,selection:'selected-1',auth:0,epoch:'read-1',available:true};
  const listeners=new Set<()=>void>();
  const transport:ProjectConversationCatalogueTransport={
    context:()=>({workRef:state.work,principalScope:'1'.repeat(64),generation:state.epoch}),
    authGeneration:()=>state.auth,available:()=>state.available,
    subscribe(listener){listeners.add(listener);return()=>{listeners.delete(listener);};},
    refreshContext:vi.fn(async()=>{}),
    catalogue:vi.fn(async()=>fixture.catalogue),read:vi.fn(async()=>fixture.read),
  };
  const owner=createProjectConversationCatalogueOwner({transport,workRef:()=>state.work,selectionGeneration:()=>state.selection});
  return {state,transport,owner,notify:()=>{for(const listener of listeners)listener();}};
}

it('mounts without IO, reads only explicit selected project, then Open/Back/reopen preserves filter and exact source',async()=>{
  const s=make();render(<ProjectConversations workRef={s.state.work} owner={s.owner} projectTitle="Actual selected project"/>);
  expect(s.transport.catalogue).not.toHaveBeenCalled();expect(s.transport.read).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Read project conversations'}));
  const open=await screen.findByRole('button',{name:'Open'});
  expect(s.transport.catalogue).toHaveBeenCalledTimes(1);
  expect(vi.mocked(s.transport.catalogue).mock.calls[0]![0]).toEqual({work_ref:s.state.work});
  fireEvent.change(screen.getByRole('textbox',{name:'Find in these conversations'}),{target:{value:'selected'}});
  fireEvent.click(open);
  expect(await screen.findByText(fixture.read.turns[0]!.instruction!)).toBeTruthy();
  expect(screen.getByText(fixture.read.turns[0]!.reply!.text)).toBeTruthy();
  expect(screen.getByRole('heading',{level:2,name:'Conversation'})).toBe(document.activeElement);
  fireEvent.click(screen.getByRole('button',{name:'Back to conversations'}));
  expect((screen.getByRole('textbox',{name:'Find in these conversations'}) as HTMLInputElement).value).toBe('selected');
  const reopened=screen.getByRole('button',{name:'Open'});expect(reopened).toBe(document.activeElement);
  await act(async()=>{fireEvent.click(reopened);});await screen.findByText(fixture.read.turns[0]!.reply!.text);
  expect(s.transport.read).toHaveBeenCalledTimes(2);
  expect(s.transport.catalogue).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(window,{key:'Escape'});
  expect(screen.getByRole('button',{name:'Open'})).toBe(document.activeElement);
  expect(screen.queryByRole('button',{name:/send|resume/i})).toBeNull();
  expect(screen.queryByText('Draft saved')).toBeNull();
});

it('cannot Open an unacquired row or a changed selected request manifest',async()=>{
  const s=make();const signal=new AbortController().signal;
  await expect(s.owner.read(fixture.selection,signal)).rejects.toThrow();
  await s.owner.refresh();await s.owner.catalogue({workRef:s.state.work,signal});
  await expect(s.owner.read({...fixture.selection,revision:'f'.repeat(64)},signal)).rejects.toThrow();
  expect(s.transport.read).not.toHaveBeenCalled();
});

it('refuses no-notify auth or A→B→A selection change before any Open call',async()=>{
  for(const fault of ['auth','selection','method']){
    const s=make(),signal=new AbortController().signal;
    await s.owner.refresh();await s.owner.catalogue({workRef:s.state.work,signal});
    if(fault==='auth')s.state.auth++;
    if(fault==='selection')s.state.selection='selected-3';
    if(fault==='method')s.transport.read=vi.fn(async()=>fixture.read);
    await expect(s.owner.read(fixture.selection,signal)).rejects.toThrow();
    expect(s.transport.read).not.toHaveBeenCalled();s.owner.dispose();
  }
});

it('withholds a late answer after source/auth retirement',async()=>{
  const s=make();let finish!:(value:unknown)=>void;
  s.transport.read=vi.fn(()=>new Promise(resolve=>{finish=resolve;}));
  // The factory captures the actual fixed method identities at composition.
  s.owner.dispose();const owner=createProjectConversationCatalogueOwner({transport:s.transport,workRef:()=>s.state.work,selectionGeneration:()=>s.state.selection});
  render(<ProjectConversations workRef={s.state.work} owner={owner}/>);
  fireEvent.click(screen.getByRole('button',{name:'Read project conversations'}));
  fireEvent.click(await screen.findByRole('button',{name:'Open'}));
  s.state.auth++;s.notify();
  await act(async()=>{finish(fixture.read);});
  expect(screen.queryByText(fixture.read.turns[0]!.reply!.text)).toBeNull();
  expect(screen.getByRole('status').textContent).toContain('Conversations are unavailable');
});

it('a fresh catalogue acquisition retires the previous page membership',async()=>{
  const s=make(),signal=new AbortController().signal;
  await s.owner.refresh();await s.owner.catalogue({workRef:s.state.work,signal});
  await s.owner.refresh();
  await expect(s.owner.read(fixture.selection,signal)).rejects.toThrow();
  expect(s.transport.read).not.toHaveBeenCalled();
});

it('renders unavailable turns as gaps and preserves no fabricated prompt or reply',async()=>{
  const s=make(),raw=structuredClone(fixture.read);
  raw.turns[0]={...raw.turns[0]!,state:'UNAVAILABLE',instruction:null,stop_condition:null,reply:null} as never;
  s.transport.read=vi.fn(async()=>raw);s.owner.dispose();
  const owner=createProjectConversationCatalogueOwner({transport:s.transport,workRef:()=>s.state.work,selectionGeneration:()=>s.state.selection});
  render(<ProjectConversations workRef={s.state.work} owner={owner} locale="zh-CN" theme="light"/>);
  fireEvent.click(screen.getByRole('button',{name:'读取项目对话'}));fireEvent.click(await screen.findByRole('button',{name:'打开'}));
  await screen.findByText('此轮记录暂不可用，未提供消息内容。');
  expect(screen.queryByText(fixture.read.turns[0]!.instruction!)).toBeNull();
  expect(screen.getByRole('button',{name:'返回对话列表'})).toBeTruthy();
});

it('does not steal focus when an explicit catalogue read completes',async()=>{
  const s=make();render(<ProjectConversations workRef={s.state.work} owner={s.owner}/>);
  const button=screen.getByRole('button',{name:'Read project conversations'});button.focus();fireEvent.click(button);
  await screen.findByRole('button',{name:'Open'});expect(document.activeElement).toBe(button);
});

it('withdraws cached bodies when selected-project owner changes',async()=>{
  const s=make();const view=render(<ProjectConversations workRef={s.state.work} owner={s.owner}/>);
  fireEvent.click(screen.getByRole('button',{name:'Read project conversations'}));fireEvent.click(await screen.findByRole('button',{name:'Open'}));
  await screen.findByText(fixture.read.turns[0]!.reply!.text);
  view.rerender(<ProjectConversations workRef="WS:OTHER" owner={s.owner}/>);
  expect(screen.queryByText(fixture.read.turns[0]!.reply!.text)).toBeNull();
});
