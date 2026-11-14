"""Run the native read controller with deferred GETs, never ledger mutations."""
import shutil
import subprocess
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
NODE = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[1],'utf8'), name=process.argv[2];
const begin=html.includes('var _readGeneration =')?html.indexOf('var _readGeneration ='):html.indexOf('function load()');
const source=html.slice(begin,html.indexOf('\nfunction render(',begin));
const pending=[],paint=[],errors=[];
let message='';
const ctx={
 fetch:(url,opt)=>{assert.equal(url,'/api/pfolio/positions');assert.equal(opt.credentials,'same-origin');
  assert.equal(opt.method,undefined);return new Promise((resolve,reject)=>pending.push({resolve,reject}));},
 render:data=>paint.push(data.marker),
 hide:()=>{},showBlock:id=>errors.push(id),
 document:{getElementById:id=>{assert.equal(id,'pf-error');return {set textContent(x){message=x;}}}}
};
vm.createContext(ctx);vm.runInContext(source,ctx);
const tick=()=>new Promise(setImmediate);
const ok=(i,marker)=>pending[i].resolve({ok:true,json:async()=>({marker})});
const bad=i=>pending[i].reject(Error('fixture failure'));
(async()=>{
 ctx.load();
 if(name==='sequential'){ok(0,'first');await tick();ctx.load();ok(1,'second');await tick();assert.deepEqual(paint,['first','second']);return;}
 ctx.load();
 if(name==='reverse-success'){ok(1,'new');await tick();ok(0,'old');await tick();assert.deepEqual(paint,['new']);}
 if(name==='old-failure'){ok(1,'new');await tick();bad(0);await tick();assert.deepEqual(paint,['new']);assert.deepEqual(errors,[]);}
 if(name==='new-failure'){bad(1);await tick();ok(0,'old');await tick();assert.deepEqual(paint,[]);assert.deepEqual(errors,['pf-error']);assert(message.includes('fixture failure'));}
 if(name==='old-during-new-pending'){ok(0,'old');await tick();assert.deepEqual(paint,[]);ok(1,'new');await tick();assert.deepEqual(paint,['new']);}
 if(name==='json-late'){
 let release;pending[0].resolve({ok:true,json:()=>new Promise(r=>release=r)});await tick();
 ok(1,'new');await tick();release({marker:'old'});await tick();assert.deepEqual(paint,['new']);
 }
 if(name==='latest-http-error'){pending[1].resolve({ok:false,status:503});await tick();bad(0);await tick();assert.deepEqual(errors,['pf-error']);assert(message.includes('503'));}
 if(name==='recovery'){bad(1);await tick();ctx.load();ok(2,'recovered');await tick();ok(0,'old');await tick();assert.deepEqual(paint,['recovered']);}
 assert.equal(pending.length,name==='recovery'?3:2,'No extra retry or request');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
@pytest.mark.parametrize("case",["sequential","reverse-success","old-failure","new-failure","old-during-new-pending","json-late","latest-http-error","recovery"])
def test_native_pfolio_get_ownership(case):
    node=shutil.which("node")
    assert node, "Node is required to qualify the native read controller"
    subprocess.run([node,"-e",NODE,str(ROOT/"app/static/portfolio.html"),case],
                   capture_output=True,text=True,check=True,timeout=10)
