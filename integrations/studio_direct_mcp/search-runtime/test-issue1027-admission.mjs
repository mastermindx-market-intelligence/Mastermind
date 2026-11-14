import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { setTimeout as sleep } from 'node:timers/promises';
import { SearchManager, searchManager } from '../dist/search-manager.js';
import { configManager } from '../dist/config-manager.js';
import { handleStartSearch, handleGetMoreSearchResults } from '../dist/handlers/search-handlers.js';
import { createTempDir, isTestHome } from './helpers/test-env.js';
assert.ok(isTestHome(), 'Run through the upstream isolated test runner');
const root=createTempDir('issue1027-admission-');
const dist=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../dist');
const managers=[],copies=[],results=[],gates=[];
const original=await configManager.getConfig();
let serial=0;
const manager=()=>{const m=new SearchManager();managers.push(m);return m;};
const opts={rootPath:root,pattern:'needle',searchType:'content',literalSearch:true,timeout:1500,maxResults:10};
const check=(name)=>{results.push(name);console.log('PASS '+name);};
async function loadInjected(needle,insert) {
  const source=await fs.readFile(path.join(dist,'search-manager.js'),'utf8');
  assert.equal(source.split(needle).length,2,needle);
  const file=path.join(dist,`issue1027-injected-${process.pid}-${serial++}.js`);copies.push(file);
  await fs.writeFile(file,source.replace(needle,insert));
  const module=await import(pathToFileURL(file).href);
  module.SearchManager.testSingleton=module.searchManager;module.SearchManager.testFile=file;
  return module.SearchManager;
}
async function waitFor(predicate,ms=1500) {
  const end=Date.now()+ms;
  while(!predicate()&&Date.now()<end)await sleep(5);
  assert.ok(predicate(),'bounded wait did not settle');
}
try {
  await fs.writeFile(path.join(root,'one.txt'),'needle\nneedle\n');
  await configManager.setValue('allowedDirectories',[root]);
  const m=manager();
  const args=m.buildRipgrepArgs(opts);
  assert.deepEqual(args.slice(0,3),['--no-config','--threads','2']);check('fixed two-thread ripgrep budget');
  for(const broad of ['/',os.tmpdir(),os.homedir(),path.join(root,'agent-workspaces')]) {
    await assert.rejects(m.startSearch({...opts,rootPath:broad}),e=>e.code==='search_root');
  }
  assert.equal(m.sessions.size,0);check('broad roots refused before spawning');
  await fs.symlink(os.tmpdir(),path.join(root,'broad-alias'));
  await configManager.setValue('allowedDirectories',[root,os.tmpdir()]);
  await assert.rejects(m.startSearch({...opts,rootPath:path.join(root,'broad-alias')}),e=>e.code==='search_root');
  await configManager.setValue('allowedDirectories',[root]);
  check('canonical broad-root alias is refused before spawning');
  const normal=await m.startSearch(opts);await m.waitForCompletion(normal.sessionId);
  assert.equal(m.readSearchResults(normal.sessionId).totalMatches,2);check('narrow fixture remains searchable');

  // Before genuine path validation, resolver and stat stages respectively.
  for(const [label,needle] of [
    ['validation','const validation = startPathValidation(options.rootPath);'],
    ['resolver','rgPath = await getRipgrepPath();'],
    ['stat','const rootIsDirectory = (await fs.stat(validPath)).isDirectory();']
  ]) {
    const token=`delay-${serial}`;let release;
    globalThis[token]=new Promise(r=>{release=r;gates.push(r);});
    const Type=await loadInjected(needle,`await globalThis[${JSON.stringify(token)}];\n${needle}`);
    const delayed=new Type();managers.push(delayed);
    const began=Date.now();
    const started=delayed.startSearch({...opts,timeout:30});
    await assert.rejects(started,e=>e.code==='search_deadline');
    assert.ok(Date.now()-began<300);assert.equal(delayed.sessions.size,0);
    assert.equal(delayed.admissions.size,1,'deadline must not release unsettled preflight');
    release();await waitFor(()=>delayed.admissions.size===0);
    assert.equal(delayed.sessions.size,0,'late preflight spawned a search');delete globalThis[token];
    check(`${label} deadline is bounded; late resolution cannot spawn`);
  }

  const needle='const validation = startPathValidation(options.rootPath);';
  let unblock;globalThis.issue1027Pending=new Promise(r=>{unblock=r;gates.push(r);});
  const Type=await loadInjected(needle,'await globalThis.issue1027Pending;\n'+needle);
  const held=new Type();managers.push(held);
  const first=held.startSearch({...opts,timeout:40});
  first.catch(()=>{});
  const duplicate=held.startSearch({...opts,timeout:40});assert.equal(first,duplicate);
  const second=held.startSearch({...opts,pattern:'other',timeout:40});
  second.catch(()=>{});
  await assert.rejects(held.startSearch({...opts,pattern:'third'}),e=>e.code==='search_capacity');
  await Promise.all([assert.rejects(first,e=>e.code==='search_deadline'),assert.rejects(second,e=>e.code==='search_deadline')]);
  assert.equal(held.admissions.size,2);
  await assert.rejects(held.startSearch({...opts,pattern:'fourth'}),e=>e.code==='search_capacity');
  let disposed=false;const disposing=held.dispose().then(()=>{disposed=true;});
  await sleep(10);assert.equal(disposed,false);
  unblock();await disposing;assert.equal(held.admissions.size,0);assert.equal(held.sessions.size,0);
  check('duplicate preflight shares promise; two permits remain charged through deadline/disposal');

  // A real owned child stays running while spawn acknowledgement is delayed.
  const spawnNeedle='const rgProcess = spawn(rgPath, args, {';
  let ack;globalThis.issue1027Ack=new Promise(r=>{ack=r;gates.push(r);});
  const Stalled=await loadInjected(spawnNeedle,"const rgProcess = spawn(process.execPath, ['-e','setInterval(()=>{},1000)'], {");
  const running=new Stalled();managers.push(running);running.whenStarted=()=>globalThis.issue1027Ack;
  const begin=Date.now(),stopped=await running.startSearch({...opts,timeout:60});
  assert.ok(Date.now()-begin<400);const session=running.sessions.get(stopped.sessionId);
  await running.waitForCompletion(stopped.sessionId);
  assert.equal(session.timedOut,true);assert.ok(session.process.exitCode!==null||session.process.signalCode!==null);
  ack();check('deadline covers spawn acknowledgement and awaits owned child exit');

  const live=new Stalled();managers.push(live);live.whenStarted=async()=>{};
  const one=await live.startSearch({...opts,timeout:1000});
  const again=await live.startSearch({...opts,timeout:1000});assert.equal(one.sessionId,again.sessionId);
  await live.startSearch({...opts,pattern:'different',timeout:1000});
  await assert.rejects(live.startSearch({...opts,pattern:'third'}),e=>e.code==='search_capacity');
  live.terminateSearch(one.sessionId);await live.waitForCompletion(one.sessionId);
  const replacement=await live.startSearch({...opts,pattern:'replacement',timeout:1000});
  assert.notEqual(replacement.sessionId,one.sessionId);await live.dispose();check('live handles deduplicate and capacity releases only after settlement');

  const retained=manager();
  for(let i=0;i<32;i++){const s=await retained.startSearch(opts);await retained.waitForCompletion(s.sessionId);}
  await assert.rejects(retained.startSearch(opts),e=>e.code==='search_retention');
  assert.equal(retained.sessions.size,32);check('retained-session ceiling refuses extra work without evicting unread handles');

  // Force the genuine handler to observe cap/deadline settlement before returning.
  const originalStart=searchManager.startSearch.bind(searchManager);
  searchManager.startSearch=async options=>{const result=await originalStart(options);await searchManager.waitForCompletion(result.sessionId);return searchManager.startSnapshot(searchManager.sessions.get(result.sessionId));};
  const capped=await handleStartSearch({path:root,pattern:'needle',searchType:'content',maxResults:1,timeout_ms:1000});
  assert.equal(capped.structuredContent.maxResultsReached,true);assert.equal(capped.structuredContent.isComplete,true);
  assert.match(capped.content[0].text,/result limit reached.*incomplete/i);
  const page=await handleGetMoreSearchResults({sessionId:capped.structuredContent.sessionId});
  assert.match(page.content[0].text,/result limit reached.*incomplete/i);check('initial and later cap responses disclose truncation after before-return settlement');
  // A genuine search child plus delayed spawn acknowledgement deterministically
  // crosses its deadline before the initial handler returns.
  const timedManager=Stalled.testSingleton;managers.push(timedManager);
  const timedStart=timedManager.startSearch.bind(timedManager);
  timedManager.startSearch=async options=>{const result=await timedStart(options);await timedManager.waitForCompletion(result.sessionId);return timedManager.startSnapshot(timedManager.sessions.get(result.sessionId));};
  const handlerCopy=path.join(dist,'handlers',`issue1027-handlers-${process.pid}.js`);copies.push(handlerCopy);
  const handlerSource=await fs.readFile(path.join(dist,'handlers/search-handlers.js'),'utf8');
  await fs.writeFile(handlerCopy,handlerSource.replace("'../search-manager.js'",JSON.stringify('../'+path.basename(Stalled.testFile))));
  const timedHandler=await import(pathToFileURL(handlerCopy).href);
  const timed=await timedHandler.handleStartSearch({path:root,pattern:'needle',searchType:'content',maxResults:100,timeout_ms:25});
  assert.equal(timed.structuredContent.timedOut,true,JSON.stringify(timed));
  assert.equal(timed.structuredContent.isComplete,true);assert.match(timed.content[0].text,/deadline reached.*incomplete/i);
  searchManager.startSearch=originalStart;
  check('initial deadline response discloses truncation after before-return settlement');
  const refused=await handleStartSearch({path:'/',pattern:'x',searchType:'content'});
  assert.equal(refused.isError,true);assert.equal(refused.structuredContent.admissionRefusal,'search_root');check('native handler exposes typed admission refusal');
} finally {
  for(const release of gates)release();
  await searchManager.dispose();
  await Promise.all(managers.map(m=>m.dispose()));
  for(const file of copies)await fs.rm(file,{force:true});
  await configManager.updateConfig(original);
  await fs.rm(root,{recursive:true,force:true});
  delete globalThis.issue1027Pending;delete globalThis.issue1027Ack;
}
console.log(JSON.stringify({passed:results.length,checks:results,ownedManagersSettled:true}));
