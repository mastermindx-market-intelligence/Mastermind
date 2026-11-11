// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import{cleanup,fireEvent,render,screen,within}from'@testing-library/react';
import{ResourcesSystemsPanel}from'./ResourcesSystemsPanel';
import type{ControlRoomState}from'../control-room';
import{decodeWorkDocument}from'../work';
import source from'../fixtures/project-activity-whole-source.json';
afterEach(cleanup);
// Explicit controlled inventory inputs. No host/capacity producer claim.
const control=():ControlRoomState=>({state:'AVAILABLE',ownerRevision:1,programs:[],observedAt:'2026-11-04T05:00:00Z',liveBuildsActive:false,refreshInFlight:false,freshness:'UNKNOWN',publicationSeq:null,crossPlane:{state:'UNAVAILABLE',reason:'NOT_INSTALLED'},navigation:{state:'AVAILABLE',bindings:[],unboundBindingIds:[],conflicts:[],bindingsPathPresent:true,capabilities:{codex:{installed:true,version:'1.2.3',state:'PARTIAL',detail:null},cursor_agent:{installed:false,version:null,state:'NOT_INSTALLED',detail:null}}}});
const absent={kind:'UNAVAILABLE' as const,reason:'RAW_NOT_PUBLIC'};
it('explicit inspection and Back move focus; passive source updates do not',()=>{
 const c=control();const{rerender}=render(<><input aria-label="Other draft"/><ResourcesSystemsPanel controlRoom={c} work={absent}/></>);
 const row=screen.getByRole('button',{name:/Codex/});fireEvent.click(row);
 const inspector=screen.getByRole('region',{name:'Selected resource'});
 expect(document.activeElement).toBe(within(inspector).getByRole('heading',{name:'Codex'}));
 fireEvent.click(within(inspector).getByRole('button',{name:'Back to systems'}));expect(document.activeElement).toBe(row);
 fireEvent.click(row);expect(document.activeElement).toBe(within(inspector).getByRole('heading',{name:'Codex'}));
 const draft=screen.getByRole('textbox');draft.focus();
 rerender(<><input aria-label="Other draft"/><ResourcesSystemsPanel controlRoom={{...c,ownerRevision:2}} work={absent}/></>);
 expect(document.activeElement).toBe(draft);
});
it('unavailable inventory omits an empty inspector and source evidence stays closed',()=>{
 render(<ResourcesSystemsPanel controlRoom={{state:'UNAVAILABLE',ownerRevision:1,reason:'SOURCE_UNAVAILABLE'}} work={absent}/>);
 expect(screen.queryByRole('region',{name:'Selected resource'})).toBeNull();
 expect(screen.getByText(/System inventory is unavailable/)).toBeTruthy();
 const more=screen.getByText('Additional resource evidence',{selector:'summary'}).parentElement as HTMLDetailsElement;
 expect(more.open).toBe(false);expect(screen.getByText(/CPU, memory and disk readings remain unknown/)).toBeTruthy();
 expect(screen.queryByText('RAW_NOT_PUBLIC')).toBeNull();
});
it('a source withdrawal removes a selected inventory inspector without moving focus',()=>{
 const{rerender}=render(<ResourcesSystemsPanel controlRoom={control()} work={absent}/>);
 fireEvent.click(screen.getByRole('button',{name:/Codex/}));
 rerender(<ResourcesSystemsPanel controlRoom={{state:'UNAVAILABLE',ownerRevision:2,reason:'SIGNED_OUT'}} work={absent}/>);
 expect(screen.queryByRole('region',{name:'Selected resource'})).toBeNull();expect(screen.queryByText('1.2.3')).toBeNull();
});
it.each(['en','zh-CN'] as const)('uses one explicit %s title and retains real bounded Work scope',locale=>{
 const doc=decodeWorkDocument(source.final.work.body)!;const open=vi.fn();
 render(<ResourcesSystemsPanel controlRoom={{state:'UNAVAILABLE',ownerRevision:1,reason:'NO_PORT'}} work={{kind:'DOCUMENT',document:doc}} locale={locale} headingLevel={1} onOpenWork={open} canOpenWork={()=>false}/>);
 expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);expect(screen.getByRole('heading',{level:1}).closest('section')!.lang).toBe(locale);
 expect(screen.queryByRole('button',{name:locale==='en'?'Assigned work':'查看工作'})).toBeNull();
 expect(screen.getByText(locale==='en'?'Partial returned view':'返回视图不完整',{exact:false})).toBeTruthy();
 expect(open).not.toHaveBeenCalled();
});
it('a qualified Work callback keeps the exact root, with no placement action',()=>{
 const doc=decodeWorkDocument(source.final.work.body)!;const open=vi.fn();
 render(<ResourcesSystemsPanel controlRoom={{state:'UNAVAILABLE',ownerRevision:1,reason:'NO_PORT'}} work={{kind:'DOCUMENT',document:doc}} onOpenWork={open} canOpenWork={root=>root===source.selection.root_job_id}/>);
 fireEvent.click(screen.getByRole('button',{name:'Assigned work'}));expect(open).toHaveBeenCalledExactlyOnceWith(source.selection.root_job_id);
 expect(screen.queryByRole('button',{name:/place|start|send/i})).toBeNull();
});
