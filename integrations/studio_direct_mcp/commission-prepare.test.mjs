import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFile as execFileCallback, spawn } from 'node:child_process';
import { chmod, mkdtemp, mkdir, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';
import { createCommissionPreparer, commissionBytes, canonicalJson, operationKeyForCommission } from './commission-prepare.mjs';
import { createGitPublisher } from './git-publish.mjs';

const execFile=promisify(execFileCallback), GIT='/usr/bin/git', PY='/usr/bin/python3';
const run=(f,a,o={})=>execFile(f,a,{encoding:'utf8',...o});
const git=(cwd,...args)=>run(GIT,args,{cwd});
const sha=(v)=>createHash('sha256').update(v).digest('hex');
const scope='1'.repeat(64), policy='2'.repeat(64);

async function fixture() {
 const root=await mkdtemp(path.join(await realpath(os.tmpdir()),'commission-publish-')), source=path.join(root,'source'), workspace=path.join(root,'workspace'), remote=path.join(root,'remote.git'), cli=path.join(root,'mmx-workspace'), operationId='mmos-launch-92496ea172b022aae3ce74c7cae0d68fb06453f5', branch='sol/web-'+operationId;
 await mkdir(source);await mkdir(workspace);await git(root,'init','--bare',remote);await git(workspace,'init');await git(workspace,'config','user.name','Test');await git(workspace,'config','user.email','test@example.invalid');await git(workspace,'checkout','-b',branch);await writeFile(path.join(workspace,'proof.txt'),'base\n');await git(workspace,'add','proof.txt');await git(workspace,'commit','-m','base');await git(workspace,'remote','add','origin',remote);
 const head=(await git(workspace,'rev-parse','HEAD')).stdout.trim();
 const receipt={action:'status',effect:'NOT_APPLIED',schema_version:'mastermind.workspace_cli/v1',receipt:{source_repository:source,workspace_path:workspace,branch,head_sha:head,dirty:false,state:'RELEASABLE'}};
 await writeFile(cli,'#!/usr/bin/env python3\nimport json,subprocess\nr=json.loads('+JSON.stringify(JSON.stringify(receipt))+')\nr["receipt"]["head_sha"]=subprocess.check_output(["/usr/bin/git","-C",r["receipt"]["workspace_path"],"rev-parse","HEAD"],text=True).strip()\nr["receipt"]["dirty"]=bool(subprocess.check_output(["/usr/bin/git","-C",r["receipt"]["workspace_path"],"status","--porcelain"],text=True))\nprint(json.dumps(r))\n');await chmod(cli,0o700);
 return {root,source,workspace,remote,cli,head,operationId,branch,config:{enabled:true,workspaceCli:cli,gitBinary:GIT,sourceRepository:source,allowedRemoteUrls:[remote]},cleanup:()=>rm(root,{recursive:true,force:true})};
}
function argumentsFor(operationId){const rest={objective:'integration proof',workstream:'WS:EXECUTIVE-CAPACITY-FABRIC',department:'engineering',priority:5,execution_profile:'research_only'}; const derived=operationKeyForCommission(rest,scope); assert.equal(derived,operationId); return {...rest,operation_key:derived};}
async function fixedWrite(receipt,bytes){const input=JSON.stringify({workspace_path:receipt.workspace_path,content_base64:Buffer.from(bytes).toString('base64')});return await new Promise((resolve,reject)=>{const child=spawn(PY,[fileURLToPath(new URL('./commission_file.py', import.meta.url))],{stdio:['pipe','pipe','pipe']});let out='',err='';child.stdout.on('data',d=>out+=d);child.stderr.on('data',d=>err+=d);child.on('error',reject);child.on('close',code=>{if(code!==0)return reject(Error(err||'writer failure'));try{resolve(JSON.parse(out))}catch(e){reject(e)}});child.stdin.end(input);});}

test('fresh composer uses real publisher and fixed writer to return exact prepared receipt',async()=>{const f=await fixture();try{
 const args=argumentsFor(f.operationId), publisher=createGitPublisher(f.config);let present=false,pushes=0;
 const receipt={operation_id:f.operationId,branch:f.branch,base_sha:f.head,head_sha:f.head,reused:false,workspace_path:f.workspace};
 const workspace={
  inspect:async()=>present?{status:'PRESENT'}:{status:'ABSENT'},
  acquire:async()=>{present=true;return {status:'OK',effect_state:'APPLIED',receipt}},
  commitCommission:async ({repository,...x})=>{const r=await publisher.commitCommission(x);return r},
  push:async ({repository,...x})=>{pushes++;const r=await publisher.push(x);return r},
  commissionStatus:async ({repository,...x})=>{const r=await publisher.commissionStatus(x);return r},
 };
 const authenticate=async(_b,a)=>({ok:true,identity:{principal_scope:scope,policy_digest:policy,expires_at:9999999999},arguments_digest:sha(canonicalJson(a))});
 const prepare=createCommissionPreparer({workspace,files:{write:async(...x)=>{const r=await fixedWrite(...x);return r}},authenticate,baseSha:f.head,policyDigest:policy,grants:[{principal_scope:scope,template:{workstream:'WS:EXECUTIVE-CAPACITY-FABRIC',department:'engineering',priority:5,execution_profile:'research_only'}}]}).prepare;
 const out=await prepare(args,'bearer');
 assert.equal(out.status,'prepared');assert.equal(out.operation_key,f.operationId);assert.equal(out.head_sha,(await git(f.workspace,'rev-parse','HEAD')).stdout.trim());assert.equal(pushes,1);
 const bytes=await readFile(path.join(f.workspace,'research/executive_commissions/COMMISSION.md'));assert.match(bytes.toString('utf8'),/WS:EXECUTIVE-CAPACITY-FABRIC/);assert.equal(out.content_sha256,sha(bytes));
 const beforeDuplicate=pushes; const duplicate=await prepare(args,'bearer'); assert.equal(duplicate.status,'prepared'); assert.equal(pushes,beforeDuplicate,'same key must reconcile without a second push');
}finally{await f.cleanup()}});

function grant(){return [{principal_scope:scope,template:{workstream:'WS:EXECUTIVE-CAPACITY-FABRIC',department:'engineering',priority:5,execution_profile:'research_only'}}]}
async function system(f,{present=false,losePush=false,authenticate}={}) {
 const counter={push:0,commit:0,write:0}; let loss=losePush;
 const publisher=createGitPublisher(f.config,{execFile:async(file,args,opts)=>{if(file===GIT&&args.includes('push')){counter.push++;if(loss){loss=false;await execFile(file,args,opts);throw Error('lost response')}}return execFile(file,args,opts)}});
 const receipt={operation_id:f.operationId,branch:f.branch,base_sha:f.head,head_sha:f.head,reused:false,workspace_path:f.workspace};
 const workspace={inspect:async()=>present?{status:'PRESENT'}:{status:'ABSENT'},acquire:async()=>{present=true;return {status:'OK',effect_state:'APPLIED',receipt}},commitCommission:async({repository,...x})=>{counter.commit++;return publisher.commitCommission(x)},push:async({repository,...x})=>publisher.push(x),commissionStatus:async({repository,...x})=>publisher.commissionStatus(x)};
 const good=async(_b,a)=>({ok:true,identity:{principal_scope:scope,policy_digest:policy,expires_at:9999999999},arguments_digest:sha(canonicalJson(a))});
 return {counter,prepare:createCommissionPreparer({workspace,files:{write:async(...x)=>{counter.write++;return fixedWrite(...x)}},authenticate:authenticate??good,baseSha:f.head,policyDigest:policy,grants:grant()}).prepare};
}
test('lost push response then reopened preparer reconciles exact head with one total push',async()=>{const f=await fixture();try{const a=argumentsFor(f.operationId),first=await system(f,{losePush:true}),one=await first.prepare(a,'b');assert.equal(one.status,'prepared');assert.equal(first.counter.push,1);const reopened=await system(f,{present:true}),two=await reopened.prepare(a,'b');assert.equal(two.status,'prepared');assert.equal(reopened.counter.push,0);assert.equal(two.head_sha,one.head_sha);assert.equal((await git(f.workspace,'ls-remote','--heads','origin','refs/heads/'+f.branch)).stdout.trim().split(/\s+/)[0],one.head_sha)}finally{await f.cleanup()}});
test('preexisting dirty foreign commission returns unknown with zero write commit push',async()=>{const f=await fixture();try{const a=argumentsFor(f.operationId);await mkdir(path.join(f.workspace,'research','executive_commissions'),{recursive:true});await writeFile(path.join(f.workspace,'research','executive_commissions','COMMISSION.md'),'foreign\n');const s=await system(f,{present:true}),out=await s.prepare(a,'b');assert.equal(out.status,'effect_unknown');assert.deepEqual(s.counter,{push:0,commit:0,write:0})}finally{await f.cleanup()}});
test('authorization policy drift after write preserves partial source and prevents commit push',async()=>{const f=await fixture();try{let calls=0;const drift=async(_b,a)=>{calls++;return {ok:true,identity:{principal_scope:scope,policy_digest:calls>=4?'3'.repeat(64):policy,expires_at:9999999999},arguments_digest:sha(canonicalJson(a))}};const s=await system(f,{authenticate:drift}),out=await s.prepare(argumentsFor(f.operationId),'b');assert.equal(out.status,'effect_unknown');assert.equal(s.counter.write,1);assert.equal(s.counter.commit,0);assert.equal(s.counter.push,0);await readFile(path.join(f.workspace,'research','executive_commissions','COMMISSION.md'))}finally{await f.cleanup()}});
