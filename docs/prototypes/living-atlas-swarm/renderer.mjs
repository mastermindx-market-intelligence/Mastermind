/* Original display-only renderer. Geometry has no execution or telemetry authority. */
import {clamp,smooth} from './fixture.mjs';
const TAU=Math.PI*2;
const rgba=(hex,a)=>{const n=parseInt(hex.slice(1),16);return 'rgba('+[(n>>16)&255,(n>>8)&255,n&255,a].join(',')+')';};
const lerp=(a,b,t)=>a+(b-a)*t;
function random(seed){let x=seed>>>0;return()=>{x^=x<<13;x^=x>>>17;x^=x<<5;return(x>>>0)/4294967296;};}
function roundRect(c,x,y,w,h,r){r=Math.min(r,w/2,h/2);c.beginPath();c.moveTo(x+r,y);c.lineTo(x+w-r,y);c.quadraticCurveTo(x+w,y,x+w,y+r);c.lineTo(x+w,y+h-r);c.quadraticCurveTo(x+w,y+h,x+w-r,y+h);c.lineTo(x+r,y+h);c.quadraticCurveTo(x,y+h,x,y+h-r);c.lineTo(x,y+r);c.quadraticCurveTo(x,y,x+r,y);c.closePath();}
export function cubicPoint(a,b,c,d,u){const v=1-u;return{x:v*v*v*a.x+3*v*v*u*b.x+3*v*u*u*c.x+u*u*u*d.x,y:v*v*v*a.y+3*v*v*u*b.y+3*v*u*u*c.y+u*u*u*d.y};}
export function probeGeometry(origin,target,age,index=0,mode='full'){
 const dx=target.x-origin.x,dy=target.y-origin.y,d=Math.max(1,Math.hypot(dx,dy)),nx=-dy/d,ny=dx/d;
 const cycle=((age+index*.173)%1.26+1.26)%1.26;
 const extension=mode!=='full'?1:cycle<.18?smooth(cycle/.18):cycle<.62?1:cycle<.86?1-smooth((cycle-.62)/.24):0;
 const bend=(index%2?1:-1)*(22+Math.min(d*.1,21));
 const tip={x:lerp(origin.x+dx/d*30,target.x,extension),y:lerp(origin.y+dy/d*30,target.y,extension)};
 return {a:origin,b:{x:lerp(origin.x,tip.x,.32)+nx*bend,y:lerp(origin.y,tip.y,.32)+ny*bend},
  c:{x:lerp(origin.x,tip.x,.72)-nx*bend*.4,y:lerp(origin.y,tip.y,.72)-ny*bend*.4},d:tip,
  contact:extension>.98,extension};
}
export function makeField(project,index,canvasFactory){
 const rnd=random(9281+index*731),r=project.r,w=Math.ceil(r*2.36),h=Math.ceil(r*1.92),res=1.4;
 const canvas=canvasFactory(Math.ceil(w*res),Math.ceil(h*res)),ctx=canvas.getContext('2d');
 ctx.scale(res,res);ctx.translate(w/2,h/2);
 const points=[],buckets=new Map(),cell=25;
 for(let i=0;i<1850;i++){
  const a=i*2.3999632297+rnd()*.3,rad=Math.sqrt(rnd()),z=(rnd()-.5)*2;
  const shape=.88+.1*Math.sin(a*3+index)+.06*Math.cos(a*5-index);
  const x=Math.cos(a)*r*rad*shape+(rnd()-.5)*12;
  const y=Math.sin(a)*r*rad*.72*shape+z*20;
  const point={x,y,z,brightness:.14+rnd()*.68};points.push(point);
  const key=Math.floor(x/cell)+','+Math.floor(y/cell);if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(i);
 }
 for(let bin=0;bin<4;bin++){
  ctx.fillStyle=bin%2?rgba(project.color,.20+bin*.03):'rgba(202,222,242,'+(.13+bin*.05)+')';ctx.beginPath();
  for(let i=0;i<1050;i++){const a=rnd()*TAU,rad=Math.sqrt(rnd()),shape=.88+.1*Math.sin(a*3+index)+.06*Math.cos(a*5-index),x=Math.cos(a)*r*rad*shape,y=Math.sin(a)*r*rad*.72*shape+(rnd()-.5)*35,s=.4+rnd()*.6;ctx.rect(x,y,s,s);}ctx.fill();
 }
 let edges=0;
 ctx.lineWidth=.4;
 for(let i=0;i<points.length;i++){
  const p=points[i],bx=Math.floor(p.x/cell),by=Math.floor(p.y/cell),near=[];
  for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++)for(const j of buckets.get((bx+dx)+','+(by+dy))||[]){if(j>=i)continue;const q=points[j],dist=Math.hypot(p.x-q.x,p.y-q.y);if(dist<42)near.push({j,dist});}
  near.sort((a,b)=>a.dist-b.dist);
  for(const {j,dist} of near.slice(0,2)){
   const q=points[j],depth=.2+.8*Math.pow(1-clamp(Math.hypot(p.x/r,p.y/(r*.82))),.6);ctx.strokeStyle=i%4===0?rgba(project.color,.12*depth*(1-dist/65)):'rgba(192,210,232,'+(.14*depth*(1-dist/65))+')';
   ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();edges++;
  }
 }
 for(let i=0;i<points.length;i++){const p=points[i];ctx.fillStyle=i%5===0?rgba(project.color,p.brightness*.72):'rgba(225,235,250,'+(p.brightness*.62)+')';const s=i%19===0?1.5:.7;ctx.fillRect(p.x-s/2,p.y-s/2,s,s);}
 const mist=ctx.createRadialGradient(0,0,8,0,0,r);mist.addColorStop(0,rgba(project.color,.035));mist.addColorStop(1,rgba(project.color,0));ctx.fillStyle=mist;ctx.fillRect(-w/2,-h/2,w,h);
 return{canvas,w,h,points,edges};
}
export class AtlasRenderer{
 constructor(canvas,projects,{canvasFactory}={}){
  this.canvas=canvas;this.ctx=canvas.getContext('2d');if(!this.ctx)throw new Error('Canvas rendering is unavailable.');
  this.factory=canvasFactory||((w,h)=>{const c=document.createElement('canvas');c.width=w;c.height=h;return c;});
  this.fields=projects.map((p,i)=>makeField(p,i,this.factory));this.projects=projects;this.hits=[];this.labels=[];
  this.resources=new Map();this.stats={texturePoints:this.fields.reduce((s,f)=>s+f.points.length,0),textureEdges:this.fields.reduce((s,f)=>s+f.edges,0)};
 }
 resize(width,height,dpr=1){this.width=width;this.height=height;this.dpr=Math.min(1.5,dpr);this.canvas.width=Math.round(width*this.dpr);this.canvas.height=Math.round(height*this.dpr);}
 point(x,y){return{x:this.width/2+(x-this.camera.x)*this.camera.zoom,y:this.height/2+(y-this.camera.y)*this.camera.zoom};}
 world(x,y){return{x:(x-this.width/2)/this.camera.zoom+this.camera.x,y:(y-this.height/2)/this.camera.zoom+this.camera.y};}
 hitTest(x,y){return this.hits.slice().reverse().find(h=>Math.hypot(h.x-x,h.y-y)<=h.r)||null;}
 render(model,view){
  const c=this.ctx,w=this.width,h=this.height;this.camera=view.camera;this.view=view;this.model=model;this.hits=[];this.labels=[];
  this.resources=new Map(model.resources.map(r=>[r.id,r]));c.setTransform(this.dpr,0,0,this.dpr,0,0);c.clearRect(0,0,w,h);
  const bg=c.createRadialGradient(w*.53,h*.47,0,w*.53,h*.47,Math.max(w,h)*.75);bg.addColorStop(0,'#0a101a');bg.addColorStop(1,'#03060b');c.fillStyle=bg;c.fillRect(0,0,w,h);
  c.save();c.translate(w/2,h/2);c.scale(this.camera.zoom,this.camera.zoom);c.translate(-this.camera.x,-this.camera.y);
  this.drawStructure(c);
  for(let i=0;i<model.projects.length;i++)this.drawField(c,model.projects[i],this.fields[i],i);
  if(view.connections)this.drawRelations(c);
  for(const r of model.resources)this.drawResource(c,r);
  if(model.process)this.drawProcess(c,model.process);
  for(const signal of model.signals)this.drawSignal(c,signal);
  const ordered=[...model.actors].sort((a,b)=>(a.id===view.selected?1:0)-(b.id===view.selected?1:0)||a.y-b.y);
  for(const a of ordered)this.drawProbes(c,a);
  for(const a of ordered)this.drawActor(c,a);
  c.restore();this.drawLabels(c);
  if(model.partial){c.fillStyle='rgba(5,9,15,.88)';roundRect(c,14,14,Math.min(267,w-28),28,6);c.fill();c.font='12px ui-monospace, monospace';c.fillStyle='#e8c487';c.fillText('T3 unobserved · other teams continue',25,32);}
 }
 drawStructure(c){
  const pairs=[[0,1],[0,4],[0,5],[4,3],[3,2]],ps=this.model.projects;
  for(const [ia,ib] of pairs){const a=ps[ia],b=ps[ib];c.strokeStyle='rgba(130,160,195,.10)';c.lineWidth=.7;c.beginPath();c.moveTo(a.x,a.y);c.bezierCurveTo(a.x+(b.x-a.x)*.4,a.y-70,b.x-(b.x-a.x)*.25,b.y+60,b.x,b.y);c.stroke();}
 }
 drawField(c,p,f,i){
  const screen=this.point(p.x,p.y);if(screen.x<-220||screen.x>this.width+220||screen.y<-180||screen.y>this.height+180)return;
  const focus=!this.view.project||this.view.project===p.id,alpha=focus?1:.3;c.globalAlpha=alpha;
  c.drawImage(f.canvas,p.x-f.w/2,p.y-f.h/2,f.w,f.h);
  if(this.view.motion!=='off'){
   for(let k=0;k<12;k++){const point=f.points[(k*31+i*17)%f.points.length],a=.1+.24*(.5+.5*Math.sin(this.model.time*(.7+k*.015)+k*1.8));c.fillStyle=rgba(p.color,a);c.fillRect(p.x+point.x,p.y+point.y,1.9,1.9);}
  }
  c.globalAlpha=1;
  const label=this.point(p.x,p.y-p.r*.84-15);
  const members=this.model.actors.filter(a=>a.project===p.id),working=members.filter(a=>['working','attention'].includes(a.status)).length;
  const unknown=members.some(a=>a.stale);
  if(focus&&label.y>=12&&label.y<this.height-30&&label.x>-20&&label.x<this.width+20)this.labels.push({kind:'project',id:p.id,text:p.label,sub:unknown?'T3 observation missing':working+' working · '+p.detail,x:label.x,y:label.y,color:p.color,alpha:1,priority:1});
  this.hits.push({kind:'project',id:p.id,x:screen.x,y:screen.y,r:p.r*this.camera.zoom*.78});
 }
 drawRelations(c){
  for(const actor of this.model.actors){if(!actor.parent)continue;const parent=this.model.actors.find(a=>a.id===actor.parent);if(!parent)continue;
   if(this.view.selected!==actor.id&&this.view.selected!==parent.id)continue;
   c.setLineDash([4,6]);c.lineWidth=1;c.strokeStyle=rgba(actor.color,actor.stale?.17:.38);c.beginPath();c.moveTo(parent.x,parent.y);c.quadraticCurveTo((parent.x+actor.x)/2,(parent.y+actor.y)/2-35,actor.x,actor.y);c.stroke();c.setLineDash([]);
  }
 }
 drawResource(c,r){
  const selected=this.model.actors.find(a=>a.id===this.view.selected),active=selected?.targets.includes(r.id),inProject=!this.view.project||this.view.project===r.project;
  const color=this.projects.find(p=>p.id===r.project).color;
  c.globalAlpha=inProject?1:.25;c.strokeStyle=rgba(color,active?.75:.23);c.fillStyle=active?rgba(color,.10):'#091019';c.lineWidth=1;
  const size=r.kind==='process'?11:7;
  if(r.kind==='browser'){roundRect(c,r.x-10,r.y-7,20,14,2);c.fill();c.stroke();c.beginPath();c.moveTo(r.x-10,r.y-3);c.lineTo(r.x+10,r.y-3);c.stroke();}
  else if(r.kind==='file'){c.strokeRect(r.x-6,r.y-8,12,16);c.beginPath();c.moveTo(r.x-3,r.y-3);c.lineTo(r.x+3,r.y-3);c.moveTo(r.x-3,r.y+1);c.lineTo(r.x+3,r.y+1);c.stroke();}
  else if(r.kind==='message'){c.beginPath();c.moveTo(r.x,r.y-7);c.lineTo(r.x+9,r.y);c.lineTo(r.x,r.y+7);c.lineTo(r.x-9,r.y);c.closePath();c.fill();c.stroke();}
  else {roundRect(c,r.x-size,r.y-size*.7,size*2,size*1.4,2);c.fill();c.stroke();}
  c.globalAlpha=1;
  if(active){const p=this.point(r.x,r.y);this.labels.push({text:r.label,sub:null,x:p.x,y:p.y-20,color:'#dce7f2',priority:3,kind:'resource'});}
 }
 drawProcess(c,p){
  const color=p.state==='failed'?'#f8ba72':p.state==='unobserved'?'#7e8b9a':p.state==='passed'?'#69e0b5':'#9aa4ff';
  c.save();c.translate(p.x,p.y);c.fillStyle='#0a101a';c.strokeStyle=rgba(color,.8);c.lineWidth=1;roundRect(c,-17,-12,34,24,3);c.fill();c.stroke();
  c.fillStyle=color;c.font='13px ui-monospace,monospace';c.textAlign='center';c.fillText(p.state==='failed'?'!':p.state==='passed'?'✓':p.state==='unobserved'?'?':'>_',0,5);
  if(p.state==='running'){c.strokeStyle=rgba(color,.7);c.lineWidth=1.3;c.beginPath();const a=this.view.motion==='off'?0:this.model.time*1.6;c.arc(0,0,24,a,a+Math.PI*.7);c.stroke();}
  c.restore();const pt=this.point(p.x,p.y);this.labels.push({kind:'process',text:'Checks · '+p.state,x:pt.x,y:pt.y+30,color,priority:2});
 }
 drawSignal(c,s){
  const u=clamp((this.model.time-s.at)/s.duration),a={x:s.from[0],y:s.from[1]},d={x:s.to[0],y:s.to[1]},b={x:lerp(a.x,d.x,.3),y:a.y-85},cc={x:lerp(a.x,d.x,.7),y:d.y-85};
  c.lineWidth=1;c.strokeStyle=rgba(s.color,.18);c.beginPath();c.moveTo(a.x,a.y);c.bezierCurveTo(b.x,b.y,cc.x,cc.y,d.x,d.y);c.stroke();
  if(this.view.motion==='off')return;
  for(let k=0;k<10;k++){const t=u-k*.018;if(t<0)continue;const p=cubicPoint(a,b,cc,d,t);c.fillStyle=rgba(s.color,(1-k/10)*.9);const size=k===0?6:2.2;c.fillRect(p.x-size/2,p.y-size/2,size,size);}
 }
 drawProbes(c,a){
  if(a.stale||!['working','attention'].includes(a.status)||a.moving||!a.targets.length)return;
  const selected=a.id===this.view.selected,dim=this.view.project&&this.view.project!==a.project;
  c.globalAlpha=dim?.18:1;
  a.targets.forEach((id,i)=>{const target=this.resources.get(id);if(!target)return;
   const g=probeGeometry(a,target,this.model.time-a.born,i,this.view.motion);
   if(g.extension<.05)return;
   const color=a.status==='attention'?'#f6bd7b':a.color;c.lineWidth=selected?1.5:1;c.strokeStyle=rgba(color,selected?.76:.4);
   c.beginPath();c.moveTo(g.a.x,g.a.y);c.bezierCurveTo(g.b.x,g.b.y,g.c.x,g.c.y,g.d.x,g.d.y);c.stroke();
   if(selected&&this.view.motion==='full')for(let j=1;j<13;j++){const p=cubicPoint(g.a,g.b,g.c,g.d,j/13);c.fillStyle=rgba(color,.58);c.fillRect(p.x-1,p.y-1,2,2);}
   c.fillStyle=g.contact?'#efffff':color;c.beginPath();c.arc(g.d.x,g.d.y,selected?2.3:1.7,0,TAU);c.fill();
   if(g.contact&&selected){const f=this.view.motion==='full'?((this.model.time+i*.3)%1):.4;c.strokeStyle=rgba(color,.42*(1-f));c.lineWidth=.8;c.beginPath();c.arc(target.x,target.y,5+f*12,0,TAU);c.stroke();}
  });c.globalAlpha=1;
 }
 drawActor(c,a){
  const selected=a.id===this.view.selected,dim=this.view.project&&this.view.project!==a.project;
  const screen=this.point(a.x,a.y);if(screen.x<-100||screen.x>this.width+100||screen.y<-100||screen.y>this.height+100)return;
  c.globalAlpha=dim?.25:a.stale?.42:1;
  if(!a.stale&&this.view.motion==='full'&&a.age<a.travelDuration+.45&&Math.hypot(a.x-a.fromX,a.y-a.fromY)>20){
   c.strokeStyle=rgba(a.color,.24*(1-clamp((a.age-a.travelDuration)/.45)));c.lineWidth=1.2;c.beginPath();c.moveTo(a.fromX,a.fromY);c.quadraticCurveTo((a.fromX+a.x)/2,(a.fromY+a.y)/2-22,a.x,a.y);c.stroke();}
  c.save();c.translate(a.x,a.y);
  const r=selected?23:15,phase=this.view.motion==='off'?0:this.model.time;
  const locomotion=a.moving&&this.view.motion==='full',living=['working','attention'].includes(a.status)&&!a.stale;
  const angle=a.heading*.34+(living&&this.view.motion==='full'?Math.sin(phase*1.2+a.born)*.035:0);c.rotate(angle);
  const color=a.status==='attention'?'#f6bd7b':a.stale?'#8995a6':a.color;
  const legs=selected?14:8;
  for(let i=0;i<legs;i++){
   const theta=TAU*(i+.35)/legs,rhythm=phase*(locomotion?16:living?5:0)+i*1.15+a.born;
   const stride=locomotion?Math.sin(rhythm)*7:living&&this.view.motion==='full'?Math.sin(rhythm)*1.5:0;
   const bend=.16*Math.sin(theta*2)+(locomotion?.08*Math.sin(rhythm):.04),span=r*(2.15+.23*Math.sin(i*2.3))+stride;
   const rootx=Math.cos(theta)*r*.95,rooty=Math.sin(theta)*r*.72;
   const elbowx=Math.cos(theta+bend)*r*1.5,elbowy=Math.sin(theta+bend)*r*1.2;
   const footx=Math.cos(theta)*span,footy=Math.sin(theta)*span*.82;
   c.lineWidth=selected?1.1:.85;c.strokeStyle=rgba(color,selected?.75:.58);c.beginPath();c.moveTo(rootx,rooty);
   c.lineTo(elbowx,elbowy);c.lineTo(footx-Math.cos(theta+.3)*5,footy-Math.sin(theta+.3)*5);c.lineTo(footx,footy);c.stroke();
   c.fillStyle=rgba('#e6ffff',selected?.83:.5);c.fillRect(footx-1,footy-1,2,2);
  }
  c.fillStyle='#07131b';c.strokeStyle=rgba(color,.8);c.lineWidth=1.1;c.beginPath();c.ellipse(0,0,r*1.1,r*.78,0,0,TAU);c.fill();c.stroke();
  c.save();c.beginPath();c.ellipse(0,0,r*1.08,r*.76,0,0,TAU);c.clip();c.strokeStyle=rgba(color,selected?.25:.16);c.lineWidth=.6;
  for(let i=-3;i<=3;i++){const x=i*r*.25;c.beginPath();c.moveTo(x,-r);c.quadraticCurveTo(x*.6,0,x,r);c.stroke();const y=i*r*.19;c.beginPath();c.moveTo(-r*1.2,y);c.quadraticCurveTo(0,y*.45,r*1.2,y);c.stroke();}
  c.restore();
  if(selected){c.strokeStyle=rgba(color,.23);c.lineWidth=.7;c.beginPath();c.ellipse(0,0,r*1.25,r*.91,0,0,TAU);c.stroke();}
  const pulse=living&&this.view.motion==='full'?1+Math.sin(phase*4+a.born)*.08:1;
  c.fillStyle=a.status==='complete'?'#9af1ce':a.status==='waiting'?'#b7c4d6':a.stale?'#738396':'#ff8bb9';
  c.beginPath();c.moveTo(0,-5*pulse);c.lineTo(5*pulse,0);c.lineTo(0,5*pulse);c.lineTo(-5*pulse,0);c.closePath();c.fill();
  if(a.status==='waiting'){c.strokeStyle='#a4b6c9';c.lineWidth=1.4;c.beginPath();c.moveTo(-2,-3);c.lineTo(-2,3);c.moveTo(2,-3);c.lineTo(2,3);c.stroke();}
  c.restore();c.globalAlpha=1;
  this.hits.push({kind:'actor',id:a.id,x:screen.x,y:screen.y,r:Math.max(20,r*this.camera.zoom*1.8)});
  if(selected)this.labels.push({kind:'actor',text:a.id==='lead'?'T3 lead':a.name,sub:a.stale?'UNOBSERVED':null,x:screen.x,y:screen.y+Math.max(48,r*this.camera.zoom*2.6),color:a.stale?'#98a5b8':a.color,priority:0});
 }
 drawLabels(c){
  const occupied=this.hits.filter(h=>h.kind==='actor').map(h=>({x:h.x-h.r*.8,y:h.y-h.r*.8,w:h.r*1.6,h:h.r*1.6}));c.textAlign='center';
  for(const l of this.labels.sort((a,b)=>a.priority-b.priority)){
   c.font=(l.kind==='project'?'600 14px':'12px')+' ui-monospace, SFMono-Regular, monospace';
   let width=c.measureText(l.text).width+18;if(l.sub){c.font='11px ui-monospace, monospace';width=Math.max(width,c.measureText(l.sub).width+18);}
   const height=l.sub?39:24,baseX=clamp(l.x-width/2,8,Math.max(8,this.width-width-8)),baseY=clamp(l.y-12,8,this.height-height-8);let x=baseX,y=baseY,placed=false;
   for(const shift of [[0,0],[0,-26],[0,26],[-84,0],[84,0],[0,-54],[0,54],[-84,36],[84,36]]){const xx=clamp(baseX+shift[0],8,Math.max(8,this.width-width-8)),yy=clamp(baseY+shift[1],8,this.height-height-8);if(!occupied.some(b=>xx<b.x+b.w+4&&xx+width+4>b.x&&yy<b.y+b.h+3&&yy+height+3>b.y)){x=xx;y=yy;placed=true;break;}}
   if(!placed&&l.priority>1)continue;occupied.push({x,y,w:width,h:height});
   c.globalAlpha=l.alpha??1;if(l.kind==='resource'&&(Math.abs(x-baseX)>30||Math.abs(y-baseY)>30)){c.strokeStyle='rgba(190,212,232,.3)';c.lineWidth=.7;c.beginPath();c.moveTo(l.x,l.y+12);c.lineTo(x+width/2,y+height/2);c.stroke();}c.fillStyle=l.kind==='actor'?'rgba(6,16,25,.94)':'rgba(5,9,15,.84)';roundRect(c,x,y,width,height,4);c.fill();
   if(l.kind==='actor'){c.strokeStyle=rgba(l.color,.37);c.lineWidth=1;c.stroke();}
   c.font=(l.kind==='project'?'600 14px':'12px')+' ui-monospace, SFMono-Regular, monospace';c.fillStyle=l.kind==='project'?'#e0e8f4':l.color;c.fillText(l.text,x+width/2,y+16);
   if(l.sub){c.font='11px ui-monospace, monospace';c.fillStyle=l.kind==='actor'?l.color:'#8c9eb5';c.fillText(l.sub,x+width/2,y+31);}
   c.globalAlpha=1;
  }
 }
 destroy(){this.fields.length=0;this.hits.length=0;this.labels.length=0;this.canvas.width=1;this.canvas.height=1;}
}
