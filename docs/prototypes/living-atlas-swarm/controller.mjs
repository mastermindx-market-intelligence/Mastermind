import {PROJECTS,ACTORS,DURATION,clamp,snapshotAt} from './fixture.mjs';
import {AtlasRenderer} from './renderer.mjs';
export function mountAtlas(root,{canvasFactory,autoPlay=true}={}){
 if(!root)throw new Error('Atlas root is missing.');
 const canvas=root.querySelector('canvas'),q=name=>root.querySelector('[data-control="'+name+'"]'),f=name=>root.querySelector('[data-field="'+name+'"]');
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 const state={time:0,playing:autoPlay,speed:1.5,selected:'lead',project:'',follow:false,motion:reduced.matches?'off':'full',lostAt:null,
  camera:{x:620,y:490,zoom:.6},target:{x:620,y:490,zoom:.6},width:0,height:0,drag:null,disposed:false};
 const renderer=new AtlasRenderer(canvas,PROJECTS,{canvasFactory});
 let frame=0,timer=0,last=performance.now(),lastUI=-1,lastEvent='',wasPlaying=false,resizeObserver;
 const listeners=[];const listen=(target,event,callback,options)=>{target.addEventListener(event,callback,options);listeners.push(()=>target.removeEventListener(event,callback,options));};
 function fit(project=state.project,instant=false){const p=PROJECTS.find(x=>x.id===project);state.target=p?{x:p.x,y:p.y,zoom:Math.min(state.width/(p.r*2.8),state.height/(p.r*2.6),1.8)}:{x:620,y:490,zoom:Math.min((state.width-42)/1210,(state.height-65)/945)};
  if(instant||state.motion==='off')state.camera={...state.target};}
 function current(){return snapshotAt(state.time,{motion:state.motion,lostAt:state.lostAt});}
 function updateUI(model,force=false){
  if(!force&&Math.abs(state.time-lastUI)<.12)return;lastUI=state.time;
  const original=ACTORS.find(a=>a.id===state.selected),actor=model.actors.find(a=>a.id===state.selected),project=PROJECTS.find(p=>p.id===(actor?.project||original.project));
  f('name').textContent=original.name;f('role').textContent=original.role+' · '+original.owner;
  f('status').textContent=(actor?.status||'queued').toUpperCase();f('status').dataset.state=actor?.status||'queued';
  f('current').textContent=actor?.label||'This session has not started in the scenario.';
  f('project').textContent=project.label;f('repo').textContent=original.repo||'Coordination';
  f('parent').textContent=ACTORS.find(a=>a.id===original.parent)?.name||'No parent in this sample';
  f('evidence').textContent=actor?.stale?'Observation unavailable':'Synthetic fixture';
  f('process').textContent=model.process?'Targeted checks · '+model.process.state+' · attempt '+model.process.attempt+(model.process.stale?' · last observed':''):'Checks have not started';
  f('source').textContent=actor?.stale?'Last T3 observation: '+state.lostAt.toFixed(1)+' s · current work unknown':'Fixture data · not current fleet state';
  f('clock').textContent=state.time.toFixed(1).padStart(4,'0');q('time').value=String(state.time);
  const latest=model.events.at(-1);f('milestone').textContent=model.partial?'Partial observation':model.finished?'Scenario complete':latest?.kind||'Brief';
  const eventKey=model.events.slice(-3).map(e=>e.at).join(',')+'|'+state.lostAt;
  if(eventKey!==lastEvent){lastEvent=eventKey;f('events').replaceChildren(...model.events.slice(-3).reverse().map(e=>{const li=document.createElement('li'),time=document.createElement('time'),span=document.createElement('span');time.textContent=String(Math.floor(e.at)).padStart(2,'0')+'s';span.textContent=e.label;li.append(time,span);return li;}));f('announcement').textContent=model.partial?'T3 observations are unavailable. Other teams continue.':latest?.label||'';}
  const active=model.actors.filter(a=>a.status==='working'||a.status==='attention').length,unknown=model.actors.filter(a=>a.stale).length;
  f('coverage').textContent=PROJECTS.length+' project fields · '+model.actors.length+' observed sample sessions · '+active+' working'+(unknown?' · '+unknown+' unobserved':'');
  q('pause').textContent=state.playing?'Pause display':model.finished?'Play again':'Play display';
  q('follow').setAttribute('aria-pressed',String(state.follow));q('follow').textContent=state.follow?'Following session':'Follow session';
  q('motion').textContent='Motion: '+state.motion[0].toUpperCase()+state.motion.slice(1);
  q('feed').setAttribute('aria-pressed',String(state.lostAt!==null));q('feed').textContent=state.lostAt===null?'Lose T3 feed':'Restore T3 feed';
  q('project').value=state.project;q('actor').value=state.selected;
  root.dataset.scenarioTime=state.time.toFixed(2);root.dataset.sourceState=model.partial?'partial':'fixture';
 }
 function draw(dt=.016,force=false){
  const model=current(),actor=model.actors.find(a=>a.id===state.selected);
  if(state.follow&&actor){const dx=actor.x-state.target.x,dy=actor.y-state.target.y,margin=38/state.camera.zoom;
   if(Math.abs(dx)>margin||Math.abs(dy)>margin)state.target={x:actor.x,y:actor.y,zoom:Math.min(1.18,state.width/460)};}
  const ease=state.motion==='off'?1:1-Math.exp(-Math.max(dt,.016)*7);
  for(const k of ['x','y','zoom'])state.camera[k]+=(state.target[k]-state.camera[k])*ease;
  renderer.render(model,{camera:state.camera,selected:state.selected,project:state.project,motion:state.motion,connections:true});updateUI(model,force);
 }
 function cancel(){if(frame)cancelAnimationFrame(frame);if(timer)clearTimeout(timer);frame=0;timer=0;}
 function schedule(){if(state.disposed||document.hidden||!state.playing)return;cancel();if(state.motion==='off')timer=setTimeout(()=>tick(performance.now()),200);else frame=requestAnimationFrame(tick);}
 function tick(now){frame=0;timer=0;if(state.disposed||!root.isConnected){dispose();return;}const dt=Math.min(.25,Math.max(0,(now-last)/1000));last=now;if(state.playing)state.time=Math.min(DURATION,state.time+dt*state.speed);if(state.time>=DURATION)state.playing=false;draw(dt,state.time>=DURATION);schedule();}
 function redraw(){if(!state.playing)state.camera={...state.target};draw(.1,true);if(state.playing){last=performance.now();schedule();}}
 function select(id){if(!ACTORS.some(a=>a.id===id))return;state.selected=id;const a=ACTORS.find(x=>x.id===id),pose=current().actors.find(x=>x.id===id),project=pose?.project||a.project;if(state.project&&state.project!==project){state.project=project;fit();}if(state.follow){state.target={x:pose?.x??a.steps[0].x,y:pose?.y??a.steps[0].y,zoom:Math.min(1.18,state.width/460)};}redraw();}
 function resize(){const rect=canvas.getBoundingClientRect();state.width=Math.max(280,rect.width);state.height=Math.max(320,rect.height);renderer.resize(state.width,state.height,window.devicePixelRatio||1);if(!state.widthInitialized){state.widthInitialized=true;if(state.width<500)state.project='os';}fit(state.project,true);redraw();}
 function replay(){state.time=0;state.lostAt=null;state.playing=true;lastEvent='';last=performance.now();fit(state.project,true);redraw();}
 listen(q('pause'),'click',()=>{if(state.time>=DURATION){replay();return;}state.playing=!state.playing;cancel();last=performance.now();redraw();});
 listen(q('follow'),'click',()=>{state.follow=!state.follow;if(state.follow){const actor=current().actors.find(a=>a.id===state.selected);if(actor)state.target={x:actor.x,y:actor.y,zoom:Math.min(1.18,state.width/460)};}else fit();redraw();});
 listen(q('motion'),'click',()=>{state.motion=state.motion==='full'?'calm':state.motion==='calm'?'off':'full';cancel();last=performance.now();redraw();});
 listen(q('feed'),'click',()=>{state.lostAt=state.lostAt===null?state.time:null;redraw();});
 listen(q('time'),'input',()=>{state.time=clamp(Number(q('time').value),0,DURATION);if(state.lostAt!==null&&state.time<state.lostAt)state.lostAt=state.time;lastEvent='';redraw();});
 listen(q('speed'),'change',()=>{state.speed=Number(q('speed').value);});
 listen(q('actor'),'change',()=>select(q('actor').value));
 listen(q('project'),'change',()=>{state.project=q('project').value;state.follow=false;if(state.project){const a=current().actors.find(a=>a.project===state.project)||ACTORS.find(a=>a.project===state.project);if(a)state.selected=a.id;}fit();redraw();});
 listen(q('reset'),'click',()=>{state.project='';state.follow=false;fit('',!state.playing);redraw();});
 for(const name of ['zoom-in','zoom-out'])listen(q(name),'click',()=>{state.follow=false;state.target.zoom=clamp(state.target.zoom*(name==='zoom-in'?1.24:1/1.24),.22,2.2);if(!state.playing)state.camera={...state.target};redraw();});
 listen(q('replay'),'click',replay);
 for(const b of root.querySelectorAll('[data-select]'))listen(b,'click',()=>select(b.dataset.select));
 listen(canvas,'pointerdown',e=>{if(e.pointerType==='touch')return;state.drag={x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY,moved:false};canvas.setPointerCapture?.(e.pointerId);});
 listen(canvas,'pointermove',e=>{if(!state.drag)return;const dx=e.clientX-state.drag.x,dy=e.clientY-state.drag.y;state.drag.moved=state.drag.moved||Math.hypot(e.clientX-state.drag.startX,e.clientY-state.drag.startY)>5;if(state.drag.moved){state.follow=false;state.camera.x-=dx/state.camera.zoom;state.camera.y-=dy/state.camera.zoom;state.target={...state.camera};draw(.016);}state.drag.x=e.clientX;state.drag.y=e.clientY;});
 listen(canvas,'pointerup',e=>{const dragged=state.drag?.moved;state.drag=null;canvas.releasePointerCapture?.(e.pointerId);if(dragged)return;const rect=canvas.getBoundingClientRect(),hit=renderer.hitTest(e.clientX-rect.left,e.clientY-rect.top);if(hit?.kind==='actor')select(hit.id);else if(hit?.kind==='project'){state.project=hit.id;state.follow=false;fit();redraw();}});
 listen(canvas,'pointercancel',()=>{state.drag=null;});
 listen(document,'visibilitychange',()=>{if(document.hidden){wasPlaying=state.playing;state.playing=false;cancel();}else if(wasPlaying){wasPlaying=false;state.playing=state.time<DURATION;last=performance.now();redraw();}});
 listen(reduced,'change',e=>{if(e.matches){state.motion='off';cancel();redraw();}});
 listen(window,'pagehide',()=>dispose());
 function dispose(){if(state.disposed)return;state.disposed=true;cancel();resizeObserver?.disconnect();for(const remove of listeners)remove();renderer.destroy();delete root.atlasStudy;}
 root.atlasStudy={state,renderer,snapshot:current,seek(t){state.time=clamp(t,0,DURATION);redraw();},dispose};
 resizeObserver=new ResizeObserver(resize);resizeObserver.observe(canvas);resize();
 return dispose;
}
