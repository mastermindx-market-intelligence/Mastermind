import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';

export class NativePort {
  constructor(config) { this.config = config; }
  async call(action, payload = {}) {
    const c = this.config;
    const connectionId = createHash('sha256').update(JSON.stringify([c.environmentId, c.t3Home ?? null, c.t3Port ?? null])).digest('hex');
    if (payload.environmentId && payload.environmentId !== c.environmentId || payload.connectionId && payload.connectionId !== connectionId) throw new Error('NATIVE_CONNECTION_CHANGED');
    const request = JSON.stringify({ action, config: { nativeCliPath: c.nativeCliPath, nodePath: c.nodePath, t3Home: c.t3Home, environmentId: c.environmentId, projectIds: c.projectIds, t3Port: c.t3Port }, ...payload });
    if (Buffer.byteLength(request) > 100000) throw new Error('REQUEST_TOO_LARGE');
    return new Promise((resolve, reject) => {
      const child = spawn(c.pythonPath, ['-I', c.portPath], { shell: false, stdio: ['pipe', 'pipe', 'pipe'], env: { HOME: process.env.HOME, PATH: '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin', TMPDIR: process.env.TMPDIR || '/tmp' } });
      let out = '', oversized = false;
      const deadline = setTimeout(() => child.kill('SIGTERM'), 25000);
      deadline.unref();
      child.stdout.on('data', part => { if (Buffer.byteLength(out) + part.length > 2097152) oversized = true; else out += part; });
      // Native diagnostics can contain private paths or provider errors. Never relay raw stderr.
      child.stderr.resume();
      child.on('error', () => { clearTimeout(deadline); reject(new Error(action === 'send' ? 'NATIVE_PRECONDITION_UNAVAILABLE' : 'NATIVE_UNAVAILABLE')); });
      child.on('close', code => {
        clearTimeout(deadline);
        if (oversized) return reject(new Error(action === 'send' ? 'NATIVE_EFFECT_UNKNOWN' : 'NATIVE_OUTPUT_LIMIT'));
        try {
          const value = JSON.parse(out);
          if (code !== 0 || value.ok !== true) {
            const failure = new Error(/^[A-Z_]+$/.test(value.error) ? value.error : (action === 'send' ? 'NATIVE_EFFECT_UNKNOWN' : 'NATIVE_UNAVAILABLE'));
            if (typeof value.code === 'string' && /^[a-z_]+$/.test(value.code)) failure.nativeCode = value.code;
            reject(failure); return;
          }
          resolve(value.data);
        } catch (e) { reject(new Error(/^[A-Z][A-Z_]+$/.test(e.message) ? e.message : (action === 'send' ? 'NATIVE_EFFECT_UNKNOWN' : 'NATIVE_UNAVAILABLE'))); }
      });
      child.stdin.on('error', () => {}); // Close/error above supplies the outcome; never retry stdin.
      child.stdin.end(request);
    });
  }
}
