import { spawn } from 'node:child_process';

const schema = 'mastermind.teamlink.native-watch.v1';
const allowed = new Set(['schema', 'type', 'environmentId', 'threadId', 'sequence', 'code']);
export function parseNotice(line, environmentId, threads) {
  if (Buffer.byteLength(line) > 4096) throw new Error('WATCH_NOTICE_LIMIT');
  const value = JSON.parse(line);
  if (!value || Array.isArray(value) || Object.keys(value).some(k => !allowed.has(k)) ||
      value.schema !== schema || value.environmentId !== environmentId ||
      !['ready', 'changed', 'heartbeat', 'error'].includes(value.type) ||
      value.threadId !== undefined && !threads.has(value.threadId) ||
      value.sequence !== undefined && (!Number.isSafeInteger(value.sequence) || value.sequence < 0) ||
      value.code !== undefined && !/^[A-Z0-9_]{1,80}$/.test(value.code) ||
      value.type === 'changed' && !value.threadId) throw new Error('WATCH_NOTICE_INVALID');
  return value;
}

// A read-only native CLI child belongs to this Paperclip worker. It holds no
// agent credentials, never sends a message and cannot outlive its stdin owner.
export class NativeSubscription {
  constructor(config, threadIds, notify, { spawnProcess = spawn, staleMs = 45000 } = {}) {
    this.stopping = false; this.lastNoticeAt = null; this.ready = new Set();
    this.threadIds = new Set(threadIds); this.error = null;
    let out = '', settled = false, timer, startupTimer, terminateTimer, killTimer;
    let finish;
    this.done = new Promise(resolve => { finish = resolve; });
    const stopChild = () => {
      this.child.stdin.end();
      if (!terminateTimer) terminateTimer = setTimeout(() => this.child.kill('SIGTERM'), 1500);
      if (!killTimer) killTimer = setTimeout(() => this.child.kill('SIGKILL'), 7000);
      terminateTimer.unref?.(); killTimer.unref?.();
    };
    const fail = code => {
      if (settled || this.stopping || this.error) return;
      this.error = code; notify({ type: 'unavailable', code }); stopChild();
    };
    const arm = () => {
      clearTimeout(timer);
      timer = setTimeout(() => fail('WATCH_HEARTBEAT_TIMEOUT'), staleMs);
      timer.unref?.();
    };
    this.child = spawnProcess(config.nodePath, [config.nativeCliPath, 'thread', 'native-watch', '--json', '--log-level', 'error'], {
      shell: false, stdio: ['pipe', 'pipe', 'pipe'],
      env: { HOME: process.env.HOME, PATH: '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin',
        TMPDIR: process.env.TMPDIR || '/tmp', T3CODE_HOME: config.t3Home },
    });
    this.child.stderr.resume();
    this.child.stdout.on('data', part => {
      if (this.stopping || this.error) return;
      out += part.toString('utf8');
      // Process complete frames before checking the unfinished suffix. A native
      // burst can contain many valid small notices in a single pipe chunk.
      let end;
      while ((end = out.indexOf('\n')) >= 0) {
        const line = out.slice(0, end); out = out.slice(end + 1);
        try {
          const notice = parseNotice(line, config.environmentId, this.threadIds);
          this.lastNoticeAt = new Date().toISOString(); arm();
          if (notice.type === 'error') { fail(notice.code || 'WATCH_NATIVE_UNAVAILABLE'); return; }
          if (notice.type === 'ready') {
            if (notice.threadId) this.ready.add(notice.threadId);
            else this.ready = new Set(this.threadIds);
            if (this.ready.size === this.threadIds.size) clearTimeout(startupTimer);
          }
          notify(notice);
        } catch { fail('WATCH_NOTICE_INVALID'); return; }
      }
      if (Buffer.byteLength(out) > 4096) fail('WATCH_NOTICE_LIMIT');
    });
    this.child.stdin.on('error', () => fail('WATCH_INPUT_CLOSED'));
    this.child.on('error', () => fail('WATCH_START_UNAVAILABLE'));
    this.child.on('close', () => {
      settled = true;
      clearTimeout(timer); clearTimeout(startupTimer); clearTimeout(terminateTimer); clearTimeout(killTimer);
      if (!this.stopping) {
        this.error ||= 'WATCH_CONNECTION_CLOSED'; this.ready.clear();
        notify({ type: 'closed', code: this.error });
      }
      finish();
    });
    this.stop = async () => {
      if (!settled && !this.stopping) { this.stopping = true; clearTimeout(timer); clearTimeout(startupTimer); stopChild(); }
      await this.done;
    };
    arm();
    startupTimer = setTimeout(() => fail('WATCH_READY_TIMEOUT'), Math.min(25000, staleMs));
    startupTimer.unref?.();
    this.child.stdin.write(JSON.stringify({ environmentId: config.environmentId, projectIds: config.projectIds, threadIds }) + '\n');
  }
  health() {
    return { readyThreads: this.ready.size, requestedThreads: this.threadIds.size,
      lastNoticeAt: this.lastNoticeAt, error: this.error };
  }
}
