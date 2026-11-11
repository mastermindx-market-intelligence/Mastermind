import { spawn } from 'node:child_process';

const schema = 'mastermind.teamlink.native-watch.v1';
const allowed = new Set(['schema', 'type', 'environmentId', 'threadId', 'sequence', 'code']);
// Native CLI codes are a closed lowercase vocabulary. Keep reconnect decisions
// in the existing parent lifecycle, with scope/auth refusals distinct from a
// dropped transport or the helper's deliberate finite-session renewal.
const nativeCodes = Object.freeze({
  invalid_request: 'WATCH_REQUEST_INVALID', request_too_large: 'WATCH_REQUEST_TOO_LARGE',
  environment_mismatch: 'WATCH_ENVIRONMENT_MISMATCH', project_not_found: 'WATCH_PROJECT_NOT_FOUND',
  thread_not_found: 'WATCH_THREAD_NOT_FOUND', thread_not_root: 'WATCH_THREAD_NOT_ROOT',
  qualification_failed: 'WATCH_QUALIFICATION_FAILED', qualification_incomplete: 'WATCH_QUALIFICATION_INCOMPLETE',
  authorization_failed: 'WATCH_AUTHORIZATION_FAILED', server_unreachable: 'WATCH_SERVER_UNREACHABLE',
  connection_lost: 'WATCH_CONNECTION_UNAVAILABLE',
  session_failed: 'WATCH_SESSION_FAILED', subscription_failed: 'WATCH_SUBSCRIPTION_FAILED',
  subscription_closed: 'WATCH_CONNECTION_CLOSED', stdin_closed: 'WATCH_INPUT_CLOSED',
  lifetime_expired: 'WATCH_SESSION_ROTATE', terminated: 'WATCH_TERMINATED',
});
export function parseNotice(line, environmentId, threads) {
  if (Buffer.byteLength(line) > 4096) throw new Error('WATCH_NOTICE_LIMIT');
  const value = JSON.parse(line);
  if (!value || Array.isArray(value) || Object.keys(value).some(k => !allowed.has(k)) ||
      value.schema !== schema || value.environmentId !== environmentId ||
      !['ready', 'changed', 'heartbeat', 'error'].includes(value.type) ||
      value.threadId !== undefined && !threads.has(value.threadId) ||
      value.sequence !== undefined && (!Number.isSafeInteger(value.sequence) || value.sequence < 0) ||
      value.code !== undefined && (typeof value.code !== 'string' ||
        !Object.hasOwn(nativeCodes, value.code) && !/^[A-Z0-9_]{1,80}$/.test(value.code)) ||
      value.type === 'changed' && !value.threadId) throw new Error('WATCH_NOTICE_INVALID');
  return value.code === undefined ? value : { ...value, code: nativeCodes[value.code] ?? value.code };
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
