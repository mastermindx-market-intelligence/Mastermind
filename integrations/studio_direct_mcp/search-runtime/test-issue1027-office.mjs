import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Worker } from 'node:worker_threads';
import { setTimeout as sleep } from 'node:timers/promises';
import ExcelJS from 'exceljs';
import PizZip from 'pizzip';
import { createOfficeWorker } from '../dist/office-worker-host.js';

import { configManager } from '../dist/config-manager.js';
import { isTestHome } from './helpers/test-env.js';
assert.ok(isTestHome(), 'Run through the upstream isolated test runner');
const originalConfig=await configManager.getConfig();
const root=await fs.mkdtemp(path.resolve('.office-1027-'));
await configManager.setValue('allowedDirectories',[root]);
const workers=[],managers=[],sessions=[],results=[];
const sentinel=new Worker('setInterval(()=>{},1000)',{eval:true});
const guard=setTimeout(()=>{for(const w of workers)void w.terminate();void sentinel.terminate();throw new Error('Office fixture exceeded 15 seconds');},15000);
let sentinelExited=false;sentinel.once('exit',()=>{sentinelExited=true;});
function observe(manager) {
  managers.push(manager);
  const run=manager.runOfficeWorker;
  manager.runOfficeWorker=function(session,source,...rest) {
    const promise=run.call(this,session,source,...rest);
    const w=session.officeWorkers?.get(source)?.worker;
    if(w){workers.push(w);w.ownerMessage=w.listeners('message')[0];w.ownerError=w.listeners('error')[0];w.on('message',m=>{if(m?.kind==='done'){w.doneSeen=true;w.completeAtDone=session.isComplete;}});w.once('exit',()=>{w.actualExitObserved=true;w.completeAtExit=session.isComplete;});}
    return promise;
  };
  return manager;
}
async function fixtureModule(name,{stall=false,entry=null}={}) {
  const dir=path.join(root,name);await fs.cp(path.resolve('../dist'),dir,{recursive:true});
  await fs.writeFile(path.join(dir,'package.json'),'{"type":"module"}\n');
  const marker=path.join(root,`${name}.entered`);
  if(stall) {
    const file=path.join(dir,'office-search.js');let src=await fs.readFile(file,'utf8');
    const target='getMatchContext(text, matchStart, matchLength) {';assert.equal(src.split(target).length,2);
    src="import { writeFileSync as mark, existsSync as marked } from 'node:fs';\n"+src.replace(target,target+`\nif (!marked(${JSON.stringify(marker)})) { mark(${JSON.stringify(marker)},'actual parser entered match-context'); const until=Date.now()+2000; while(Date.now()<until){} }\n`);
    await fs.writeFile(file,src);
  }
  if(entry!==null)await fs.writeFile(path.join(dir,'office-search-worker.js'),entry);
  const module=await import(pathToFileURL(path.join(dir,'search-manager.js')).href);
  return {Manager:module.SearchManager,marker};
}
async function search(manager,file,extra={}) {
  const s=await manager.startSearch({rootPath:file,pattern:'needle',searchType:'content',literalSearch:true,contextLines:0,maxResults:500,timeout:5000,...extra});
  const session=manager.sessions.get(s.sessionId);sessions.push(session);return session;
}
try {
  const workbook=new ExcelJS.Workbook();const sheet=workbook.addWorksheet('é中');
  for(let i=0;i<12;i++)sheet.addRow([`${'p'.repeat(80)} needle é中🙂 ${i} ${'x'.repeat(200)}`]);
  const xlsx=path.join(root,'tiny.xlsx');await workbook.xlsx.writeFile(xlsx);
  const zip=new PizZip();zip.file('word/document.xml','<w:document xmlns:w="urn:test"><w:body>'+Array.from({length:12},(_,i)=>`<w:p><w:r><w:t>${'p'.repeat(80)} needle é中🙂 ${i} ${'x'.repeat(200)}</w:t></w:r></w:p>`).join('')+'</w:body></w:document>');
  const docx=path.join(root,'tiny.docx');await fs.writeFile(docx,zip.generate({type:'nodebuffer',compression:'DEFLATE'}));
  const normal=await fixtureModule('normal');
  for(const [kind,file] of [['xlsx',xlsx],['docx',docx]]) {
    const manager=observe(new normal.Manager()),s=await search(manager,file);
    await manager.waitForCompletion(s.id);
    assert.equal(s.totalMatches,12);assert.equal(s.isComplete,true);assert.equal(s.officeWorkers.size,0);
    assert.ok(s.results.every(r=>r.match.length<=101&&r.match.includes('é中🙂')));
    assert.ok(s.retainedTextBytes<=1048576);
    const before=JSON.stringify(manager.readSearchResults(s.id));
    workers.at(-1).ownerMessage({kind:'match',result:{file:'late',line:1,match:'late',type:'content'}});
    workers.at(-1).ownerError(new Error('late worker error'));
    const after=JSON.stringify(manager.readSearchResults(s.id));
    // runtime is wall time; terminal data and stop reason must remain fixed.
    const beforeData=JSON.parse(before),afterData=JSON.parse(after);delete beforeData.runtime;delete afterData.runtime;
    assert.deepEqual(afterData,beforeData);
    results.push({check:`real ${kind} parse`,pass:true,matches:s.totalMatches,retainedTextBytes:s.retainedTextBytes});
    await manager.dispose();

    const capped=observe(new normal.Manager()),cap=await search(capped,file,{maxResults:1});
    await capped.waitForCompletion(cap.id);assert.equal(cap.totalMatches,1);assert.equal(cap.maxResultsReached,true);assert.equal(cap.officeWorkers.size,0);
    results.push({check:`real ${kind} global budget and terminal race`,pass:true,matches:cap.totalMatches});
    await capped.dispose();
  }
  // Both Office producers share the same real source manager and retention cap.
  const mixed=observe(new normal.Manager()),all=await search(mixed,root,{filePattern:'*.xlsx|*.docx',maxResults:3});
  await mixed.waitForCompletion(all.id);assert.equal(all.totalMatches,3);assert.equal(all.officeWorkers.size,0);await mixed.dispose();
  results.push({check:'real mixed Office shared cap',pass:true,matches:all.totalMatches});

  // The real producer cannot flood IPC while synchronous parsing is active.
  const control=new Int32Array(new SharedArrayBuffer(8));
  const bp=createOfficeWorker({source:'docx',rootPath:docx,pattern:'needle',ignoreCase:true,includeHidden:false,control:control.buffer});
  workers.push(bp);bp.once('exit',()=>{bp.actualExitObserved=true;});
  const messages=[];
  await new Promise((resolve,reject)=>{bp.on('error',reject);bp.on('message',m=>{messages.push(m);if(m.kind==='match')resolve();});});
  await sleep(50);assert.equal(messages.length,1,'worker exceeded one in-flight record');assert.notEqual(bp.threadId,-1);
  Atomics.store(control,0,1);await bp.terminate();assert.equal(bp.threadId,-1);
  results.push({check:'real synchronous parser has at most one unacknowledged IPC record',pass:true,inFlight:messages.length});

  for(const [kind,file] of [['xlsx',xlsx],['docx',docx]]) for(const reason of ['cancel','deadline']) {
    const module=await fixtureModule(`stall-${kind}-${reason}`,{stall:true});
    const manager=observe(new module.Manager());const began=Date.now();
    const s=await search(manager,file,{timeout:reason==='deadline'?900:5000});
    while(!existsSync(module.marker)&&Date.now()-began<850)await sleep(5);
    assert.equal(existsSync(module.marker),true,'deadline hit before genuine parser entry; NOT PROVEN');
    assert.equal(s.isComplete,false);
    if(reason==='cancel')manager.terminateSearch(s.id);
    await manager.waitForCompletion(s.id);const elapsed=Date.now()-began;
    assert.ok(elapsed<1800,`did not preempt the 2000ms synchronous parser stall: ${elapsed}`);
    assert.equal(reason==='deadline'?s.timedOut:s.cancelled,true);
    assert.equal(s.officeWorkers.size,0);assert.equal(s.totalMatches,0);
    const n=s.results.length;await sleep(10);assert.equal(s.results.length,n);
    assert.equal(sentinelExited,false);
    results.push({check:`real ${kind} parser-entry hard ${reason}`,pass:true,elapsedMs:elapsed,stallMs:2000,actualParserEntry:true,lateAppends:0});
    await manager.dispose();
  }
  const empty=observe(new normal.Manager()),noMatch=await search(empty,docx,{pattern:'absent-marker'});
  await empty.waitForCompletion(noMatch.id);assert.equal(noMatch.totalMatches,0);assert.equal(noMatch.resourceLimit,undefined);await empty.dispose();
  results.push({check:'real Office no-match completion',pass:true});

  for(const [name,entry] of [
    ['worker error',"throw new Error('fixture parser worker failure');"],
    ['oversized returned record',"import {parentPort} from 'node:worker_threads';parentPort.postMessage({kind:'match',result:{file:'x'.repeat(4097),line:1,match:'x',type:'content'}});setInterval(()=>{},1000);"],
    ['diagnostic output budget',"process.stdout.write('x'.repeat(65537));setInterval(()=>{},1000);"]
  ]) {
    const mod=await fixtureModule('fault-'+name.replaceAll(' ','-'),{entry});
    const m=observe(new mod.Manager()),s=await search(m,docx);await m.waitForCompletion(s.id);
    assert.equal(s.resourceLimit,'office_worker');assert.equal(s.totalMatches,0);assert.equal(s.officeWorkers.size,0);
    await m.dispose();results.push({check:name,pass:true,resourceLimit:s.resourceLimit});
  }
  const done=await fixtureModule('done-before-exit',{entry:"import {parentPort} from 'node:worker_threads';parentPort.postMessage({kind:'done'});setTimeout(()=>parentPort.close(),150);"});
  const dm=observe(new done.Manager()),ds=await search(dm,docx),dw=workers.at(-1);
  await dm.waitForCompletion(ds.id);assert.equal(dw.doneSeen,true);assert.equal(dw.completeAtDone,false);assert.equal(dw.actualExitObserved,true);await dm.dispose();
  results.push({check:'done message does not release worker lifetime',pass:true});

  const disposal=await fixtureModule('dispose-blocked',{stall:true}),om=observe(new disposal.Manager());
  const os=await search(om,docx),at=Date.now();while(!existsSync(disposal.marker)&&Date.now()-at<850)await sleep(5);
  assert.equal(existsSync(disposal.marker),true);await om.dispose();
  assert.equal(os.isComplete,true);assert.equal(os.officeWorkers.size,0);assert.equal(om.sessions.size,0);
  results.push({check:'awaited disposal interrupts actual parser-entry stall',pass:true});
  assert.ok(workers.every(w=>w.actualExitObserved&&w.threadId===-1&&!w.completeAtExit));
  assert.ok(sessions.every(s=>s.process.exitCode!==null||s.process.signalCode!==null));
  assert.equal(sentinelExited,false);
} finally {
  clearTimeout(guard);
  await Promise.all(workers.map(w=>w.terminate()));
  await Promise.all(managers.map(m=>m.dispose()));
  await sentinel.terminate();
  await fs.rm(root,{recursive:true,force:true});
  await configManager.updateConfig(originalConfig);
}
const report={results,passed:results.filter(r=>r.pass).length,ownedWorkerCount:workers.length,residualWorkers:workers.filter(w=>w.threadId!==-1).length,residualProcesses:sessions.filter(s=>s.process.exitCode===null&&s.process.signalCode===null).length,unrelatedSentinelUnaffected:true,fixtureRemoved:!existsSync(root),parserDependencies:{exceljs:'4.4.0',pizzip:'3.2.0'},faultInjection:'For hard preemption only, a bounded 2000ms synchronous stall is inserted at the genuine parser match-context entry after actual XLSX/DOCX parsing. Production worker code has no test hook.'};
await fs.writeFile('office-results.json',JSON.stringify(report,null,2)+'\n');
console.log(`Office integration ${report.passed}/${results.length} PASS; ${workers.length} actual worker exits; zero residual workers; unrelated sentinel survived.`);
