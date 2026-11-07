// @vitest-environment jsdom
import {useEffect,useState} from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {ProjectDetailsNavigator,type ProjectDetailsNavigatorProps} from './ProjectDetailsNavigator';
afterEach(()=>{cleanup();vi.restoreAllMocks();});
const props=():ProjectDetailsNavigatorProps=>({scopeKey:'actual-project-A',locale:'en',title:'Actual title',goal:'Exact goal\nsecond line',sections:[{id:'direction',content:<h2>Owned Direction</h2>},{id:'instructions',content:<textarea aria-label="Existing draft"/>}]});
it.each(['en','zh-CN'] as const)('shows exact context and compact inspection, with owners inaccessible until selected in %s',locale=>{
 const {container}=render(<ProjectDetailsNavigator {...props()} locale={locale}/>);
 expect(screen.getByText('Exact goal second line').textContent).toBe('Exact goal\nsecond line');
 expect(screen.getByText('Actual title')).toBeTruthy();expect(screen.queryByRole('heading',{name:'Owned Direction'})).toBeNull();
 expect(container.querySelectorAll('.mm-project-details-nav__owner')).toHaveLength(2);
});
it('reveals an owner only on explicit choice, keeps state mounted, and returns focus to its exact button',()=>{
 const mounted=vi.fn();function Owner(){const[count,setCount]=useState(0);useEffect(()=>{mounted();},[]);return <button onClick={()=>setCount(x=>x+1)}>Owner {count}</button>;}
 const p=props();p.sections=[{id:'direction',content:<Owner/>}];render(<ProjectDetailsNavigator {...p}/>);
 expect(mounted).toHaveBeenCalledTimes(1);const choose=screen.getByRole('button',{name:"Direction",exact:true});fireEvent.click(choose);
 const section=screen.getByRole('region',{name:'Inspect Direction',exact:true});expect(document.activeElement).toBe(section);
 fireEvent.click(screen.getByRole('button',{name:'Owner 0'}));fireEvent.click(screen.getByRole('button',{name:/Back to project details/}));expect(document.activeElement).toBe(choose);
 fireEvent.click(choose);expect(screen.getByRole('button',{name:'Owner 1'})).toBeTruthy();expect(mounted).toHaveBeenCalledTimes(1);
});
it('returns from ordinary Escape while draft Escape and nested handled Escape retain their owner',()=>{
 render(<ProjectDetailsNavigator {...props()}/>);fireEvent.click(screen.getByRole('button',{name:/Standing instructions/}));
 const text=screen.getByRole('textbox',{name:'Existing draft'});fireEvent.keyDown(text,{key:'Escape'});expect(screen.getByRole('textbox')).toBe(text);
 const section=screen.getByRole('region',{name:'Inspect Standing instructions',exact:true});fireEvent.keyDown(section,{key:'Escape'});
 expect(screen.queryByRole('textbox')).toBeNull();expect(document.activeElement).toBe(screen.getByRole('button',{name:/Standing instructions/}));
});
it('passive locale and source-node updates keep selection without focus, while scope change retires it',()=>{
 const p=props(),v=render(<ProjectDetailsNavigator {...p}/>);fireEvent.click(screen.getByRole('button',{name:"Direction",exact:true}));
 const input=document.createElement('input');document.body.append(input);input.focus();
 v.rerender(<ProjectDetailsNavigator {...p} locale="zh-CN"/>);expect(document.activeElement).toBe(input);expect(screen.getByRole('heading',{name:'Owned Direction'})).toBeTruthy();
 v.rerender(<ProjectDetailsNavigator {...p} scopeKey="actual-project-B"/>);expect(document.activeElement).toBe(input);expect(screen.queryByRole('heading',{name:'Owned Direction'})).toBeNull();
 v.rerender(<ProjectDetailsNavigator {...p}/>);expect(screen.queryByRole('heading',{name:'Owned Direction'})).toBeNull();input.remove();
});

it('lets an existing child consume Escape without changing the inspected section',()=>{
 const p=props();p.sections=[{id:'direction',content:<button onKeyDown={event=>{if(event.key==='Escape')event.preventDefault();}}>Child disclosure control</button>}];
 render(<ProjectDetailsNavigator {...p}/>);fireEvent.click(screen.getByRole('button',{name:'Direction',exact:true}));
 fireEvent.keyDown(screen.getByRole('button',{name:'Child disclosure control'}),{key:'Escape'});
 expect(screen.getByRole('region',{name:'Inspect Direction',exact:true})).toBeTruthy();
});

it('keeps exact unsent text in its existing owner through inspection and Back',()=>{
 const p=props();render(<ProjectDetailsNavigator {...p}/>);
 fireEvent.click(screen.getByRole('button',{name:/Standing instructions/}));
 const draft=screen.getByRole('textbox',{name:'Existing draft'});fireEvent.change(draft,{target:{value:'Original unsent text\nsecond line'}});
 fireEvent.click(screen.getByRole('button',{name:/Back to project details/}));fireEvent.click(screen.getByRole('button',{name:/Standing instructions/}));
 expect(screen.getByRole('textbox',{name:'Existing draft'})).toBe(draft);expect((draft as HTMLTextAreaElement).value).toBe('Original unsent text\nsecond line');
});
