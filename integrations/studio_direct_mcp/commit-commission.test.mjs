import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFile as execFileCallback } from 'node:child_process';
import { chmod, mkdtemp, mkdir, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';
import { createGitPublisher } from './git-publish.mjs';

const execFile = promisify(execFileCallback);
const GIT = '/usr/bin/git';
const COMMISSION = 'research/executive_commissions/COMMISSION.md';
const run = (file, args, options = {}) => execFile(file, args, {encoding:'utf8', maxBuffer:1024*1024, ...options});
const git = (cwd, ...args) => run(GIT, args, {cwd});

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'commission-commit-'));
  const sourceRepo = path.join(root, 'source');
  const workspace = path.join(root, 'workspace');
  const remote = path.join(root, 'remote.git');
  const operationId = 'commission-prepare-test';
  const branch = 'sol/web-' + operationId;
  const cli = path.join(root, 'mmx-workspace');
  await mkdir(sourceRepo); await mkdir(workspace);
  await git(root, 'init', '--bare', remote); await git(workspace, 'init');
  await git(workspace, 'config', 'user.name', 'Test'); await git(workspace, 'config', 'user.email', 'test@example.invalid');
  await git(workspace, 'checkout', '-b', branch);
  await writeFile(path.join(workspace, 'proof.txt'), 'base\n'); await git(workspace, 'add', 'proof.txt'); await git(workspace, 'commit', '-m', 'base');
  await git(workspace, 'remote', 'add', 'origin', remote);
  const head=(await git(workspace,'rev-parse','HEAD')).stdout.trim();
  const receipt={action:'status',effect:'NOT_APPLIED',schema_version:'mastermind.workspace_cli/v1',
    receipt:{source_repository:sourceRepo,workspace_path:workspace,branch,head_sha:head,dirty:false,state:'RELEASABLE'}};
  await writeFile(cli, '#!/bin/sh\nprintf "%s\\n" \'' + JSON.stringify(receipt) + '\'\n'); await chmod(cli,0o700);
  return {root,sourceRepo,workspace,remote,operationId,branch,head,config:{enabled:true,workspaceCli:cli,gitBinary:GIT,sourceRepository:sourceRepo,allowedRemoteUrls:[remote]},
    cleanup:()=>rm(root,{recursive:true,force:true})};
}
async function commission(f, bytes) {
  const target=path.join(f.workspace,COMMISSION); await mkdir(path.dirname(target),{recursive:true}); await writeFile(target,bytes); return target;
}
const sha=(bytes)=>createHash('sha256').update(bytes).digest('hex');

test('internal commission commit admits only the fixed path and exact blob bytes', async () => {
  const f=await fixture(); try {
    const bytes=Buffer.from('schema: mastermind.commission.v1\noperation: commission-prepare-test\n','utf8');
    await commission(f,bytes);
    const out=await createGitPublisher(f.config).commitCommission({operation_id:f.operationId,expected_head_sha:f.head,expected_content_sha256:sha(bytes)});
    assert.equal(out.schema,'mastermind.studio_git_commit_result.v1'); assert.equal(out.status,'OK'); assert.equal(out.effect_state,'APPLIED'); assert.equal(out.code,'APPLIED');
    const changed=(await git(f.workspace,'diff-tree','--no-commit-id','--name-only','-r',out.commit_head_sha)).stdout.trim();
    assert.equal(changed,COMMISSION);
    const committed=await readFile(path.join(f.workspace,COMMISSION)); assert.equal(sha(committed),sha(bytes));
    assert.equal((await git(f.workspace,'ls-remote','--heads','origin','refs/heads/'+f.branch)).stdout.trim(),'');
  } finally { await f.cleanup(); }
});
test('foreign worktree content and mismatched expected bytes refuse without moving HEAD', async () => {
  const f=await fixture(); try {
    const bytes=Buffer.from('commission\n'); await commission(f,bytes); await writeFile(path.join(f.workspace,'foreign.txt'),'x\n');
    let out=await createGitPublisher(f.config).commitCommission({operation_id:f.operationId,expected_head_sha:f.head,expected_content_sha256:sha(bytes)});
    assert.equal(out.code,'FOREIGN_WORKTREE_CHANGES'); assert.equal((await git(f.workspace,'rev-parse','HEAD')).stdout.trim(),f.head);
    await rm(path.join(f.workspace,'foreign.txt'));
    out=await createGitPublisher(f.config).commitCommission({operation_id:f.operationId,expected_head_sha:f.head,expected_content_sha256:'0'.repeat(64)});
    assert.equal(out.code,'COMMISSION_CONTENT_SHA256_MISMATCH'); assert.equal((await git(f.workspace,'rev-parse','HEAD')).stdout.trim(),f.head);
  } finally { await f.cleanup(); }
});
test('ordinary typed commit remains all-current-changes behavior', async () => {
  const f=await fixture(); try {
    await writeFile(path.join(f.workspace,'a.txt'),'a\n'); await writeFile(path.join(f.workspace,'b.txt'),'b\n');
    const out=await createGitPublisher(f.config).commit({operation_id:f.operationId,expected_head_sha:f.head,message:'test: ordinary unchanged'});
    assert.equal(out.effect_state,'APPLIED');
    assert.deepEqual((await git(f.workspace,'diff-tree','--no-commit-id','--name-only','-r',out.commit_head_sha)).stdout.trim().split('\n'),['a.txt','b.txt']);
  } finally { await f.cleanup(); }
});

test('commission commit refuses a symlink entry before accepting its digest', async () => {
  const f=await fixture(); try {
    const target=path.join(f.workspace,COMMISSION); await mkdir(path.dirname(target),{recursive:true});
    await symlink('../../proof.txt',target);
    const out=await createGitPublisher(f.config).commitCommission({
      operation_id:f.operationId, expected_head_sha:f.head, expected_content_sha256:sha(Buffer.from('base\n')),
    });
    assert.equal(out.status,'REFUSED'); assert.equal(out.effect_state,'NOT_APPLIED');
    assert.equal(out.code,'COMMISSION_ENTRY_NOT_REGULAR_BLOB');
    assert.equal((await git(f.workspace,'rev-parse','HEAD')).stdout.trim(),f.head);
  } finally { await f.cleanup(); }
});
test('commission status proves a published same-head digest after a lost push return without writes', async () => {
  const f=await fixture(); try {
    const bytes=Buffer.from('commission published\n'); await commission(f,bytes);
    const committed=await createGitPublisher(f.config).commitCommission({
      operation_id:f.operationId,expected_head_sha:f.head,expected_content_sha256:sha(bytes),
    });
    let lost=false;
    const pusher=createGitPublisher(f.config,{execFile:async(file,args,options)=>{
      if(file===GIT && args.includes('push') && !lost) {
        lost=true; await execFile(file,args,options); throw new Error('lost push response');
      }
      return execFile(file,args,options);
    }});
    const pushed=await pusher.push({operation_id:f.operationId,expected_head_sha:committed.commit_head_sha});
    assert.equal(pushed.effect_state,'APPLIED'); assert.equal(pushed.remote_head_sha,committed.commit_head_sha);
    let writes=0;
    const reader=createGitPublisher(f.config,{execFile:async(file,args,options)=>{
      if(file===GIT && ['update-ref','commit-tree','read-tree','add','push'].some((command)=>args.includes(command))) writes++;
      return execFile(file,args,options);
    }});
    const status=await reader.commissionStatus({operation_id:f.operationId});
    assert.deepEqual(status,{
      schema:'mastermind.studio_git_commission_status.v1',operation_id:f.operationId,branch:f.branch,
      local_head_sha:committed.commit_head_sha,remote_head_sha:committed.commit_head_sha,clean:true,
      commission_content_sha256:sha(bytes),
    });
    assert.equal(writes,0);
  } finally { await f.cleanup(); }
});
