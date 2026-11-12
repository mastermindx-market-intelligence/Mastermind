import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { setTimeout as sleep } from 'node:timers/promises';
import { configManager } from '../dist/config-manager.js';
import { createTempDir, isTestHome } from './helpers/test-env.js';
assert.ok(isTestHome());
const root=createTempDir('issue1027-owner-settlement-');
const dist=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../dist');
const original=await configManager.getConfig(), files=[], managers=[], releases=[];
const failures=[], passed=[];
let sequence=0;
const options={rootPath:root,pattern:'needle',searchType:'content',timeout:1000,maxResults:10};
async function fixture(timeout=30, descendants=false) {
  const token=`issue1027Owner${process.pid}_${sequence++}`;
  let release;const gate=new Promise(r=>{release=r;releases.push(r);});
  globalThis[token]={gate,entered:0,exited:0};
  const owner=path.join(dist,'tools',`${token}.js`),manager=path.join(dist,`${token}.js`);files.push(owner,manager);
  let source=await fs.readFile(path.join(dist,'tools/filesystem.js'),'utf8');
  const needle=descendants ? 'async function getAllowedDirRealPath(allowedDir) {' : 'const validationOperation = async () => {';
  assert.equal(source.split(needle).length,2);
  const stall=`globalThis[${JSON.stringify(token)}].entered++; await globalThis[${JSON.stringify(token)}].gate; globalThis[${JSON.stringify(token)}].exited++;`;
  source=source.replace(needle,`${needle}\n ${descendants ? `if (allowedDir === ${JSON.stringify(path.join(root,'slow-alias'))}) { ${stall} }` : stall}`);
  source=source.replace('FILE_OPERATION_TIMEOUTS.PATH_VALIDATION,',`${timeout},`);
  await fs.writeFile(owner,source);
  const search=await fs.readFile(path.join(dist,'search-manager.js'),'utf8');
  await fs.writeFile(manager,search.replace("'./tools/filesystem.js'",JSON.stringify('./tools/'+path.basename(owner))));
  const module=await import(pathToFileURL(manager).href);managers.push(module.searchManager);
  const m=new module.SearchManager();managers.push(m);
  return {m,release,state:globalThis[token]};
}
async function check(name,body){try{await body();passed.push(name);console.log('PASS '+name);}catch(e){failures.push({name,error:String(e)});console.error('FAIL '+name+': '+e);}}
function terminalSnapshot(session) {
  return structuredClone({
    isComplete:session.isComplete,isError:session.isError,error:session.error,
    timedOut:session.timedOut===true,cancelled:session.cancelled===true,
    maxResultsReached:session.maxResultsReached===true,wasIncomplete:session.wasIncomplete===true,
    totalMatches:session.totalMatches,totalContextLines:session.totalContextLines,
    results:session.results,pendingSources:[...session.pendingSources],
  });
}
async function completedResultStaysStable(trigger) {
  for(const alias of ['fast-alias','slow-alias']) {
    try {await fs.symlink(root,path.join(root,alias));}
    catch(error) {if(error.code!=='EEXIST')throw error;}
  }
  await configManager.setValue('allowedDirectories',[path.join(root,'fast-alias'),path.join(root,'slow-alias')]);
  const {m,release,state}=await fixture(5000,true);
  let disposing;
  try {
    const start=await m.startSearch({...options,timeout:1000});
    await m.waitForCompletion(start.sessionId);
    const session=m.sessions.get(start.sessionId),admission=[...m.admissions.values()][0];
    const before=terminalSnapshot(session);
    assert.equal(before.isComplete,true);assert.equal(before.isError,false);
    assert.equal(before.timedOut,false);assert.equal(before.cancelled,false);
    assert.equal(before.totalMatches,1);assert.equal(before.results.length,1);
    assert.deepEqual(before.pendingSources,[]);
    assert.equal(state.entered,1);assert.equal(state.exited,0);
    assert.equal(m.admissions.size,1,'completed search released outstanding validation');
    let disposed=false;
    if(trigger==='deadline') {
      await sleep(Math.max(0,admission.deadline-performance.now())+30);
      assert.ok(performance.now()>=admission.deadline);
    } else {
      assert.ok(performance.now()<admission.deadline,'dispose fixture missed its pre-deadline boundary');
      disposing=m.dispose().then(()=>{disposed=true;});
      await sleep(30);
      assert.equal(disposed,false,'dispose returned before parallel validation settled');
    }
    assert.deepEqual(terminalSnapshot(session),before,`completed search terminal state changed after ${trigger}`);
    assert.equal(state.exited,0);assert.equal(m.admissions.size,1);
    if(!disposing) {
      disposing=m.dispose().then(()=>{disposed=true;});
      await sleep(30);assert.equal(disposed,false);
      assert.deepEqual(terminalSnapshot(session),before,'dispose relabelled a completed search');
    }
    release();await disposing;
    assert.equal(state.exited,1);assert.equal(m.admissions.size,0);assert.equal(m.sessions.size,0);
    assert.deepEqual(terminalSnapshot(session),before,'settlement changed completed search evidence');
  } finally {release();await m.dispose();await configManager.setValue('allowedDirectories',[root]);}
}
try {
  await configManager.setValue('allowedDirectories',[root]);
  await fs.writeFile(path.join(root,'one.txt'),'needle\n');
  await check('internal validation timeout retains both permits until actual operation settles',async()=>{
    const {m,release,state}=await fixture();
    const a=m.startSearch(options),b=m.startSearch({...options,pattern:'other'});
    const ended=await Promise.allSettled([a,b]);
    assert.ok(ended.every(x=>x.status==='rejected'&&/Path validation operation timed out/.test(String(x.reason))));
    assert.equal(state.entered,2);assert.equal(state.exited,0);
    assert.equal(m.admissions.size,2,'non-cancelling internal timeout released live work');
    await assert.rejects(m.startSearch({...options,pattern:'third'}),e=>e.code==='search_capacity');
    let disposed=false;const disposing=m.dispose().then(()=>{disposed=true;});
    await sleep(30);assert.equal(disposed,false,'dispose returned before validation settled');
    release();await disposing;
    assert.equal(state.exited,2);assert.equal(m.admissions.size,0);assert.equal(m.sessions.size,0,'late validation spawned a child');
  });
  await check('successful validation retains parallel lookup work through search completion and disposal',async()=>{
    await fs.symlink(root,path.join(root,'fast-alias'));
    await fs.symlink(root,path.join(root,'slow-alias'));
    await configManager.setValue('allowedDirectories',[path.join(root,'fast-alias'),path.join(root,'slow-alias')]);
    const {m,release,state}=await fixture(1000,true);
    try {
      const start=await m.startSearch(options);await m.waitForCompletion(start.sessionId);
      assert.equal(state.entered,1);assert.equal(state.exited,0);
      assert.equal(m.admissions.size,1,'first path answer released parallel lookup work');
      let disposed=false;const disposing=m.dispose().then(()=>{disposed=true;});
      await sleep(30);assert.equal(disposed,false);
      release();await disposing;assert.equal(state.exited,1);assert.equal(m.admissions.size,0);
    } finally {release();await configManager.setValue('allowedDirectories',[root]);}
  });
  await check('completed result survives admission deadline while parallel validation remains live',()=>completedResultStaysStable('deadline'));
  await check('completed result survives disposal while parallel validation remains live',()=>completedResultStaysStable('disposed'));
  // Separate check continues even if the owner-lifetime assertion fails.
  await check('omitted/true share admission; false stays distinct and exhausts exact filenames',async()=>{
    const {m,release}=await fixture(1000);
    const o={...options,searchType:'files',pattern:'same.txt'};
    for(const d of ['a','b','c']){await fs.mkdir(path.join(root,d));await fs.writeFile(path.join(root,d,'same.txt'),'x');}
    const omitted=m.startSearch(o);omitted.catch(()=>{});
    const explicit=m.startSearch({...o,earlyTermination:true});explicit.catch(()=>{});
    assert.equal(omitted,explicit,'same effective true produced different admission');
    const exhaustive=m.startSearch({...o,earlyTermination:false});exhaustive.catch(()=>{});
    assert.notEqual(omitted,exhaustive);assert.equal(m.admissions.size,2);
    release();
    const [first,second]=await Promise.all([omitted,exhaustive]);
    assert.notEqual(first.sessionId,second.sessionId);
    await Promise.all([m.waitForCompletion(first.sessionId),m.waitForCompletion(second.sessionId)]);
    assert.equal(m.sessions.get(first.sessionId).options.earlyTermination,true);
    assert.equal(m.sessions.get(second.sessionId).options.earlyTermination,false);
    assert.equal(m.readSearchResults(second.sessionId).totalMatches,3);
  });
} finally {
  for(const release of releases)release();
  await Promise.all(managers.map(m=>m.dispose()));
  for(const file of files)await fs.rm(file,{force:true});
  await configManager.updateConfig(original);await fs.rm(root,{recursive:true,force:true});
}
console.log(JSON.stringify({passed,failures,ownedManagersSettled:true}));
assert.equal(failures.length,0,'review regressions');
