// Disposable fixture observation only. No production hook, retries or raw output.
import cp from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';
import { openSync, closeSync, writeSync, realpathSync, statSync } from 'node:fs';
import { isAbsolute, join } from 'node:path';

const output = new URL(import.meta.url).searchParams.get('output');
if (!output || !isAbsolute(output) || realpathSync(output) !== output || !statSync(output).isDirectory()) {
  throw new Error('Fixture observer requires its own existing canonical output directory');
}
const key = Symbol.for('mastermind.hermes.disposable-launch-observer.v1');
const existing = globalThis[key];
if (existing && existing.output !== output) throw new Error('Conflicting fixture observation destination');
const state = existing ?? { output, records: [], dropped: 0, emitted: false };
globalThis[key] = state;

function data(object, name) {
  const descriptor = object && Object.getOwnPropertyDescriptor(object, name);
  return descriptor && Object.hasOwn(descriptor, 'value') ? descriptor.value : undefined;
}
function observe(action) {
  try { return action(); } catch { return null; }
}
function executable(value, shell = false) {
  if (shell) return 'shell-command';
  if (typeof value !== 'string') return 'unobserved';
  const name = value.split(/[\\/]/).at(-1);
  if (/^python(?:\d+(?:\.\d+)*)?$/.test(name)) return 'python';
  return ['node', 'sh', 'bash', 'zsh'].includes(name) ? name : 'other';
}
function record(api, value, environment = null) {
  if (state.records.length >= 64) { state.dropped += 1; return null; }
  const item = { api, executable: executable(value, api === 'exec' || api === 'execSync'),
    environment, status: null, signal: null, thrownCode: null, outputClass: null };
  state.records.push(item);
  return item;
}
function code(value) {
  return typeof value === 'string' && /^[A-Z][A-Z0-9_]{0,63}$/.test(value) ? value : null;
}
function outputClass(value) {
  if (!Buffer.isBuffer(value) && typeof value !== 'string') return null;
  const sample = Buffer.isBuffer(value) ? value.subarray(0, 8192).toString('utf8') : value.slice(0, 8192);
  if (/error while loading shared libraries|cannot open shared object file/.test(sample)) return 'shared-library-loader-error';
  if (/ModuleNotFoundError|No module named/.test(sample)) return 'python-module-unavailable';
  if (/SyntaxError/.test(sample)) return 'syntax-error';
  return sample.length ? 'other-output' : 'empty';
}
function returned(item, result) {
  if (!item || !result || typeof result !== 'object') return;
  // No stream draining or asynchronous error listener: preserve the caller's behavior.
  if (result instanceof cp.ChildProcess) {
    result.once('close', (status, signal) => {
      item.status = Number.isInteger(status) ? status : null;
      item.signal = code(signal);
    });
  } else {
    const status = data(result, 'status');
    item.status = Number.isInteger(status) ? status : null;
    item.signal = code(data(result, 'signal'));
    item.outputClass = outputClass(data(result, 'stderr'));
  }
}
function thrown(item, error) {
  if (!item || !error || typeof error !== 'object') return;
  item.thrownCode = code(data(error, 'code'));
  const status = data(error, 'status');
  item.status = Number.isInteger(status) ? status : null;
  item.signal = code(data(error, 'signal'));
  item.outputClass = outputClass(data(error, 'stderr'));
}
if (!existing) {
  for (const api of ['spawn', 'spawnSync', 'exec', 'execSync', 'execFile', 'execFileSync', 'fork']) {
    cp[api] = new Proxy(cp[api], {
      apply(target, receiver, args) {
        const item = observe(() => record(api, args[0]));
        let result;
        try {
          result = Reflect.apply(target, receiver, args);
        } catch (error) { observe(() => thrown(item, error)); throw error; }
        observe(() => returned(item, result));
        return result;
      },
    });
  }
  cp.ChildProcess.prototype.spawn = new Proxy(cp.ChildProcess.prototype.spawn, {
    apply(target, receiver, args) {
      const item = observe(() => {
        const options = args[0];
        const pairs = data(options, 'envPairs');
        const environment = Array.isArray(pairs) ? {
          homePresent: pairs.some(value => typeof value === 'string' && value.startsWith('HOME=')),
          ldLibraryPathPresent: pairs.some(value => typeof value === 'string' && value.startsWith('LD_LIBRARY_PATH=')),
          pythonPathPresent: pairs.some(value => typeof value === 'string' && value.startsWith('PYTHONPATH=')),
        } : null;
        return record('ChildProcess.spawn', data(options, 'file'), environment);
      });
      let result;
      try {
        result = Reflect.apply(target, receiver, args);
      } catch (error) { observe(() => thrown(item, error)); throw error; }
      observe(() => returned(item, receiver));
      return result;
    },
  });
  syncBuiltinESMExports();
  process.once('exit', () => { try { flush(); } catch { /* Observation must not replace the original outcome. */ } });
}
export function snapshot() {
  return { schema: 'mastermind.disposable_launch_observation.v1', pid: process.pid,
    parentPid: process.ppid, scope: 'standard-exports-and-childprocess-prototype',
    records: structuredClone(state.records), dropped: state.dropped };
}
export function flush() {
  if (state.emitted) return;
  const descriptor = openSync(join(state.output, `observer-${process.pid}.json`), 'wx', 0o600);
  try { writeSync(descriptor, JSON.stringify(snapshot()) + '\n'); state.emitted = true; }
  finally { closeSync(descriptor); }
}
