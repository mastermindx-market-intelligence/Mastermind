import test from 'node:test';
import assert from 'node:assert/strict';
import {ACTORS,DURATION,snapshotAt,actorAt} from './fixture.mjs';
import {probeGeometry,cubicPoint} from './renderer.mjs';

test('a helper is absent until its explicit start, and keeps its own identity',()=>{
 assert.equal(snapshotAt(5.3).actors.some(a=>a.id==='ui'),false);
 const helper=snapshotAt(5.4).actors.find(a=>a.id==='ui');
 assert.equal(helper.parent,'lead');assert.notEqual(helper.id,helper.parent);
});
test('a terminal process survives its initiating actor moving to the browser',()=>{
 const s=snapshotAt(13),lead=s.actors.find(a=>a.id==='lead');
 assert.equal(s.process.state,'running');assert.ok(lead.targets.includes('browser'));
 assert.ok(Math.hypot(lead.x-s.process.x,lead.y-s.process.y)>80);
});
test('failure replaces running immediately and a restart has a distinct attempt',()=>{
 assert.equal(snapshotAt(18).process.state,'failed');
 assert.equal(snapshotAt(18).actors.find(a=>a.id==='lead').status,'attention');
 assert.equal(snapshotAt(23).process.attempt,2);assert.equal(snapshotAt(26).process.state,'passed');
});
test('lost T3 observation freezes known identities and hides later starts',()=>{
 const s=snapshotAt(29,{lostAt:4}),lead=s.actors.find(a=>a.id==='lead');
 assert.equal(lead.status,'unobserved');assert.equal(lead.targets.length,0);
 assert.equal(s.actors.some(a=>a.id==='ui'),false);assert.equal(s.process,null);
 assert.equal(s.actors.find(a=>a.id==='researcher').status,'complete');
});
test('loss interrupts T3 signal animation while independent source return survives',()=>{
 assert.equal(snapshotAt(28.1,{lostAt:17}).signals.some(s=>s.scope==='t3'),false);
 assert.ok(snapshotAt(22.4,{lostAt:17}).signals.some(s=>s.scope==='research'));
 assert.equal(snapshotAt(33.6,{lostAt:17}).events.some(e=>e.kind==='PR ready'),false);
});
test('restoration reconciles current state without replaying an old failure',()=>{
 const s=snapshotAt(29),lead=s.actors.find(a=>a.id==='lead');
 assert.equal(lead.stale,false);assert.equal(s.process.state,'passed');
 assert.equal(s.signals.some(e=>e.kind==='delegation'),false);
});
test('losing the feed does not erase previously confirmed terminal evidence',()=>{
 const s=snapshotAt(45,{lostAt:30});
 assert.equal(s.process.state,'passed');assert.equal(s.process.stale,true);
 assert.equal(s.actors.find(a=>a.id==='ui').status,'complete');
 assert.equal(s.actors.find(a=>a.id==='lead').status,'unobserved');
 assert.ok(s.events.some(e=>e.kind==='Checks'));assert.equal(s.events.some(e=>e.kind==='Verified'),false);
});
test('prepared, merged, and verified results remain distinct timeline facts',()=>{
 for(const t of [26,33.6,40,44]){
  const kinds=snapshotAt(t).events.map(e=>e.kind);
  assert.equal(kinds.includes('PR ready'),t>=33.5);
  assert.equal(kinds.includes('Merged'),t>=40);
  assert.equal(kinds.includes('Verified'),t>=44);
 }
});
test('seeking backwards is deterministic and removes future completion',()=>{
 const before=snapshotAt(13);snapshotAt(DURATION);const after=snapshotAt(13);
 assert.deepEqual(after,before);assert.equal(after.events.some(e=>e.kind==='Verified'),false);
});
test('motion-off preserves identities, current facts, and exact destinations',()=>{
 const full=snapshotAt(21.25),off=snapshotAt(21.25,{motion:'off'});
 assert.deepEqual(full.actors.map(a=>[a.id,a.status,a.label]),off.actors.map(a=>[a.id,a.status,a.label]));
 const helper=off.actors.find(a=>a.id==='ui');assert.equal(helper.x,1065);assert.equal(helper.y,238);
});
test('every interpolated pose remains finite through starts, stops and jumps',()=>{
 for(let t=0;t<=DURATION;t+=.07)for(const actor of ACTORS){const p=actorAt(actor,t);if(p)assert.ok([p.x,p.y,p.heading].every(Number.isFinite));}
});
test('probe contact reaches its exact target and calm mode retains the relationship',()=>{
 const origin={x:10,y:20},target={x:140,y:95},p=probeGeometry(origin,target,.3,0,'full');
 assert.equal(p.contact,true);assert.deepEqual(p.d,target);
 assert.deepEqual(probeGeometry(origin,target,4,0,'off').d,target);
 assert.deepEqual(cubicPoint(p.a,p.b,p.c,p.d,1),target);
});
