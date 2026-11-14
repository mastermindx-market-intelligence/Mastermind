/* Optional development check: controller stubs + real native canvas, not browser QA. */
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {mountAtlas} from './controller.mjs';
const require=createRequire(import.meta.url);
const {createCanvas}=require(process.env.ATLAS_CANVAS_PACKAGE||'@napi-rs/canvas');
const surface=readFileSync(new URL('./surface.html',import.meta.url),'utf8');
class Element{
 constructor(){this.dataset={};this.style={};this.textContent='';this.value='';this.attributes={};this.events=new Map();this.children=[];}
 addEventListener(name,fn){if(!this.events.has(name))this.events.set(name,new Set());this.events.get(name).add(fn);}
 removeEventListener(name,fn){this.events.get(name)?.delete(fn);}
 emit(name,value={}){for(const fn of this.events.get(name)||[])fn(value);}
 setAttribute(name,value){this.attributes[name]=value;}
 replaceChildren(...children){this.children=children;}
 append(...children){this.children.push(...children);}
}
function run(width,height){
 const nodes=new Map(),root=new Element(),canvas=createCanvas(width,height);root.isConnected=true;
 for(const [_,kind,key]of surface.matchAll(/data-(control|field)="([^"]+)"/g))nodes.set('[data-'+kind+'="'+key+'"]',new Element());
 const buttons=[...surface.matchAll(/data-select="([^"]+)"/g)].map(m=>{const n=new Element();n.dataset.select=m[1];return n;});
 canvas.events=new Map();canvas.addEventListener=Element.prototype.addEventListener;canvas.removeEventListener=Element.prototype.removeEventListener;
 canvas.getBoundingClientRect=()=>({width,height,left:0,top:0});
 root.querySelector=selector=>{if(selector==='canvas')return canvas;assert.ok(nodes.has(selector),'Missing actual markup selector: '+selector);return nodes.get(selector);};
 root.querySelectorAll=selector=>{assert.equal(selector,'[data-select]');return buttons;};
 const doc=new Element();doc.hidden=false;doc.createElement=()=>new Element();
 const win=new Element();win.devicePixelRatio=1;const media=new Element();media.matches=false;
 let now=0,next=0;const frames=new Map(),timers=new Map(),observers=[];
 const originals={};for(const k of ['document','window','matchMedia','requestAnimationFrame','cancelAnimationFrame','setTimeout','clearTimeout','ResizeObserver','performance'])originals[k]=globalThis[k];
 Object.assign(globalThis,{document:doc,window:win,matchMedia:()=>media,performance:{now:()=>now},
  requestAnimationFrame:fn=>{frames.set(++next,fn);return next;},cancelAnimationFrame:id=>frames.delete(id),
  setTimeout:fn=>{timers.set(++next,fn);return next;},clearTimeout:id=>timers.delete(id),
  ResizeObserver:class{constructor(fn){this.fn=fn;this.active=true;observers.push(this);}observe(){this.fn();}disconnect(){this.active=false;}}});
 const c=n=>nodes.get('[data-control="'+n+'"]'),f=n=>nodes.get('[data-field="'+n+'"]');
 let count=0,dispose;
 try{
  dispose=mountAtlas(root,{canvasFactory:createCanvas});
  assert.equal(root.dataset.sourceState,'fixture');assert.equal(f('status').textContent,'QUEUED');count++;
  root.atlasStudy.seek(13);assert.match(f('current').textContent,/browser/i);assert.match(f('process').textContent,/running/);count++;
  c('feed').emit('click');assert.equal(f('status').textContent,'UNOBSERVED');root.atlasStudy.seek(29);assert.equal(f('status').textContent,'UNOBSERVED');count++;
  c('feed').emit('click');assert.match(f('current').textContent,/Collecting/);assert.match(f('process').textContent,/passed/);count++;
  c('project').value='research';c('project').emit('change');assert.equal(root.atlasStudy.state.selected,'researcher');count++;
  buttons.find(b=>b.dataset.select==='lead').emit('click');assert.equal(root.atlasStudy.state.project,'os');assert.equal(f('name').textContent,'T3 coding lead');count++;
  c('follow').emit('click');assert.equal(c('follow').attributes['aria-pressed'],'true');count++;
  c('motion').emit('click');c('motion').emit('click');assert.equal(root.atlasStudy.state.motion,'off');assert.equal(frames.size,0);assert.equal(timers.size,1);count++;
  c('pause').emit('click');assert.equal(root.atlasStudy.state.playing,false);assert.equal(timers.size,0);count++;
  c('time').value='44';c('time').emit('input');assert.match(f('current').textContent,/verified/i);assert.equal(f('milestone').textContent,'Verified');count++;
  c('reset').emit('click');const oldZoom=root.atlasStudy.state.camera.zoom;c('zoom-in').emit('click');assert.ok(root.atlasStudy.state.camera.zoom>oldZoom);assert.deepEqual(root.atlasStudy.state.camera,root.atlasStudy.state.target);count++;
  c('replay').emit('click');assert.equal(root.atlasStudy.state.time,0);assert.equal(root.atlasStudy.state.lostAt,null);count++;
  doc.hidden=true;doc.emit('visibilitychange');assert.equal(frames.size+timers.size,0);doc.hidden=false;doc.emit('visibilitychange');assert.equal(timers.size,1);count++;
  media.emit('change',{matches:true});assert.equal(root.atlasStudy.state.motion,'off');count++;
  dispose();assert.equal(root.atlasStudy,undefined);assert.equal(frames.size+timers.size,0);assert.ok(observers.every(o=>!o.active));count++;
  return{canvas:[width,height],checks:count,result:'passed',browserLayout:'not tested'};
 }finally{dispose?.();for(const [k,v]of Object.entries(originals)){if(v===undefined)delete globalThis[k];else globalThis[k]=v;}}
}
console.log(JSON.stringify([run(760,610),run(372,470)]));
