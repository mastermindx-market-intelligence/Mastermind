import assert from 'node:assert/strict';
import cp from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtempSync, realpathSync, writeFileSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const temporary = realpathSync(mkdtempSync(join(tmpdir(), 'mmx-launch-observer-')));
const observer = new URL('./launch_observer.mjs', import.meta.url);
observer.searchParams.set('output', temporary);
const properties = Object.fromEntries(['exec', 'execFile'].map(api => [api, Object.getOwnPropertyDescriptors(cp[api])]));
const { snapshot, flush } = await import(observer.href);
const program = 'process.stdout.write("fixture-ok")';
const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";
const command = `${quote(process.execPath)} -e ${quote(program)}`;
const wait = child => new Promise((resolve, reject) => {
  child.stdout?.resume(); child.stderr?.resume();
  child.once('error', reject);
  child.once('close', status => status === 0 ? resolve() : reject(new Error(`Control child exited ${status}`)));
});
try {
  for (const api of ['exec', 'execFile']) assert.deepEqual(Object.getOwnPropertyDescriptors(cp[api]), properties[api]);
  await wait(cp.spawn(process.execPath, ['-e', program]));
  assert.equal(cp.spawnSync(process.execPath, ['-e', program], { encoding: 'utf8' }).stdout, 'fixture-ok');
  await new Promise((resolve, reject) => cp.exec(command, (error, stdout) => {
    if (error) return reject(error); assert.equal(stdout, 'fixture-ok'); resolve();
  }));
  assert.equal(cp.execSync(command, { encoding: 'utf8' }), 'fixture-ok');
  await new Promise((resolve, reject) => cp.execFile(process.execPath, ['-e', program], (error, stdout) => {
    if (error) return reject(error); assert.equal(stdout, 'fixture-ok'); resolve();
  }));
  assert.equal(cp.execFileSync(process.execPath, ['-e', program], { encoding: 'utf8' }), 'fixture-ok');
  const childModule = join(temporary, 'control.mjs');
  writeFileSync(childModule, program);
  await wait(cp.fork(childModule, [], { silent: true }));
  for (const [api, args] of [['exec', [command]], ['execFile', [process.execPath, ['-e', program]]]]) {
    const promise = promisify(cp[api])(...args);
    assert.ok(promise.child instanceof cp.ChildProcess);
    assert.deepEqual(await promise, { stdout: 'fixture-ok', stderr: '' });
  }
  assert.throws(() => cp.execFileSync(process.execPath, ['-e', 'process.exit(17)']), error => error.status === 17);
  const unhandled = cp.spawnSync(process.execPath,
    ['--import', observer.href, '-e', "require('node:child_process').spawn('/mmx-nonexistent-control-command')"],
    { encoding: 'utf8' });
  assert.notEqual(unhandled.status, 0, 'Observer must not swallow an unhandled asynchronous error');
  assert.match(unhandled.stderr, /ENOENT/);
  assert.match(unhandled.stderr, /Unhandled 'error' event/);
  const parentModule = join(temporary, 'parent.mjs');
  writeFileSync(parentModule, "import {fork} from 'node:child_process'; const child=fork(process.argv[2],[],{silent:true}); child.stdout.resume(); child.stderr.resume(); child.once('close',code=>{process.exitCode=code;});\n");
  const beforeFork = new Set(readdirSync(temporary));
  cp.execFileSync(process.execPath, ['--import', observer.href, parentModule, childModule]);
  const inherited = readdirSync(temporary).filter(name => name.startsWith('observer-') && !beforeFork.has(name));
  assert.equal(inherited.length, 2, 'Inherited preload must retain separate parent/child observations');
  const apis = [...new Set(snapshot().records.map(item => item.api))].sort();
  assert.deepEqual(apis, ['ChildProcess.spawn', 'exec', 'execFile', 'execFileSync', 'execSync', 'fork', 'spawn', 'spawnSync'].sort());
  assert.equal(snapshot().dropped, 0);
  flush();
  const result = JSON.parse(readFileSync(join(temporary, `observer-${process.pid}.json`), 'utf8'));
  assert.ok(result.records.length > 0);
  assert.ok(!JSON.stringify(result).includes('fixture-ok'), 'No raw child output belongs in observation');
  console.log(JSON.stringify({ schema: 'mastermind.launch_observer_selfcheck.v1', passed: true,
    node: process.versions.node, apis, custom_promisification_preserved: true, unhandled_error_preserved: true,
    inherited_preload_processes: inherited.length }));
} finally { rmSync(temporary, { recursive: true, force: true }); }
