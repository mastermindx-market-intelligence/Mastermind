// A fixed authenticated operation in the incumbent Studio gateway lifecycle.
// It never admits its bearer to generic Studio MCP tools.
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { lstat, readFile } from 'node:fs/promises';
import path from 'node:path';
import { createRepositoryWorkspaceAccess } from './workspace-access.mjs';
import { canonicalJson, createCommissionPreparer } from './commission-prepare.mjs';

export const COMMISSION_ROUTE = '/os-internal/commission/prepare';
const ROOT = '/Library/Application Support/MastermindExecutive';
const CONFIG = ROOT + '/config/os-commission-publication.json';
// Reuse the Executive gateway's qualified network runtime (executive_installed_peer.py).
const PYTHON = ROOT + '/network-runtimes/9512f58e382dbb94c730f74a0d80935e460f6c2707da7689b4beaecead9cb94d/bin/python';
const SHA40 = /^[0-9a-f]{40}$/;
const SHA64 = /^[0-9a-f]{64}$/;
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');

async function sealed(filename) {
  let current = filename;
  let first = true;
  while (true) {
    const info = await lstat(current);
    if (info.uid !== 0 || (info.mode & 0o022) || info.isSymbolicLink() ||
        (first ? (!info.isFile() || info.nlink !== 1) : !info.isDirectory())) {
      throw new Error('COMMISSION_INSTALLATION_REFUSED');
    }
    if (current === path.dirname(current)) break;
    current = path.dirname(current);
    first = false;
  }
}

export async function readCommissionConfiguration(expectedDigest, accountLabel, port) {
  if (!SHA64.test(expectedDigest)) throw new Error('COMMISSION_CONFIGURATION_REFUSED');
  await sealed(CONFIG);
  const raw = await readFile(CONFIG);
  if (raw.length > 65536 || hash(raw) !== expectedDigest) throw new Error('COMMISSION_CONFIGURATION_CHANGED');
  const value = JSON.parse(raw);
  const keys = ['schema', 'release_sha', 'studio_uid', 'studio_account', 'studio_port',
    'policy', 'grants', 'base_sha', 'audit_directory', 'auth_helper_sha256', 'file_helper_sha256'];
  if (!value || typeof value !== 'object' || Object.keys(value).length !== keys.length ||
      keys.some((key) => !Object.hasOwn(value, key)) ||
      value.schema !== 'mastermind.os_commission_publication.v1' ||
      process.getuid() !== process.geteuid() || value.studio_uid !== process.getuid() || value.studio_account !== accountLabel || value.studio_port !== port ||
      !SHA40.test(value.release_sha) || !SHA40.test(value.base_sha) ||
      !SHA64.test(value.auth_helper_sha256) || !SHA64.test(value.file_helper_sha256) ||
      value.audit_directory !== ROOT + '/audit/os-commission-publication') throw new Error('COMMISSION_CONFIGURATION_REFUSED');
  return value;
}

function runHelper(filename, input, timeoutMs) {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON, ['-I', '-B', filename], {
      env: { PATH: '/usr/bin:/bin', LANG: 'en_US.UTF-8' },
      stdio: ['pipe', 'pipe', 'ignore'], windowsHide: true,
    });
    let output = Buffer.alloc(0);
    let failed = false;
    const fail = () => { failed = true; child.kill('SIGKILL'); };
    const timer = setTimeout(fail, timeoutMs);
    child.stdout.on('data', (chunk) => {
      if (output.length + chunk.length > 4096) return fail();
      output = Buffer.concat([output, chunk]);
    });
    child.on('error', () => { failed = true; });
    child.stdin.on('error', () => { failed = true; });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (failed || code !== 0) return reject(new Error('COMMISSION_HELPER_REFUSED'));
      try { resolve(JSON.parse(output.toString('utf8'))); }
      catch { reject(new Error('COMMISSION_HELPER_REFUSED')); }
    });
    // Bearer/brief bytes never enter argv, environment, errors or logs.
    child.stdin.end(JSON.stringify(input));
  });
}

export async function createCommissionService(options, dependencies = {}) {
  const { configurationDigest, accountLabel, port, gitConfig, workspaceConfig } = options;
  const readConfig = dependencies.readConfiguration ?? readCommissionConfiguration;
  const initial = await readConfig(configurationDigest, accountLabel, port);
  const source = ROOT + '/releases/' + initial.release_sha;
  const authHelper = source + '/ops/executive_os/os_commission_auth_entry.py';
  const fileHelper = source + '/integrations/studio_direct_mcp/commission_file.py';
  const verifyFiles = dependencies.verifyFiles ?? (async () => {
    await Promise.all([sealed(PYTHON), sealed(authHelper), sealed(fileHelper)]);
    const [authBytes, fileBytes] = await Promise.all([readFile(authHelper), readFile(fileHelper)]);
    if (hash(authBytes) !== initial.auth_helper_sha256 || hash(fileBytes) !== initial.file_helper_sha256) {
      throw new Error('COMMISSION_HELPER_CHANGED');
    }
  });
  await verifyFiles();
  const invoke = dependencies.runHelper ?? runHelper;
  const workspace = dependencies.workspace ?? createRepositoryWorkspaceAccess(workspaceConfig, gitConfig);
  const policyDigest = hash(canonicalJson(initial.policy));
  let closed = false;
  let active = null;

  async function current() {
    if (closed) throw new Error('COMMISSION_SERVICE_CLOSED');
    await readConfig(configurationDigest, accountLabel, port);
    await verifyFiles();
  }
  async function authenticateRaw(bearer, body) {
    await current();
    const value = await invoke(authHelper, { bearer, ...(body === undefined ? {} : { request_body: body }) }, 10000);
    if (value?.ok !== true || value.identity?.policy_digest !== policyDigest) throw new Error('COMMISSION_AUTHENTICATION_REFUSED');
    return value;
  }
  const preparer = createCommissionPreparer({
    workspace, baseSha: initial.base_sha, policyDigest, grants: initial.grants,
    authenticate: (bearer, args) => authenticateRaw(bearer, JSON.stringify({ arguments: args })),
    files: { write: async (receipt, bytes) => {
      await current();
      return invoke(fileHelper, { workspace_path: receipt.workspace_path, content_base64: bytes.toString('base64') }, 10000);
    } },
  });

  function response(res, status, value) {
    res.statusCode = status;
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.end(JSON.stringify(value));
  }
  async function readBody(req) {
    let body = Buffer.alloc(0);
    const timer = setTimeout(() => req.destroy(), 5000);
    try {
      for await (const chunk of req) {
        if (body.length + chunk.length > 65536) throw new Error('COMMISSION_BODY_REFUSED');
        body = Buffer.concat([body, chunk]);
      }
      // fatal decoding prevents Unicode replacement from changing identity.
      return new TextDecoder('utf-8', { fatal: true }).decode(body);
    } finally { clearTimeout(timer); }
  }
  async function handle(req, res) {
    const tokens = [];
    for (let index = 0; index < req.rawHeaders.length; index += 2) {
      if (req.rawHeaders[index].toLowerCase() === 'authorization') tokens.push(req.rawHeaders[index + 1]);
    }
    if (tokens.length !== 1 || !/^Bearer [A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(tokens[0]) ||
        tokens[0].length > 16391) return response(res, 401, { ok: false, code: 'authentication_required' });
    const bearer = tokens[0].slice(7);
    // Authenticate before consuming request bytes. Loopback never proves identity.
    await authenticateRaw(bearer);
    const body = await readBody(req);
    await authenticateRaw(bearer, body); // canonical parser rejects duplicate members
    const args = JSON.parse(body).arguments;
    const result = await preparer.prepare(args, bearer);
    response(res, 200, result);
  }
  function middleware(req, res, next) {
    if (!req.url.startsWith('/os-internal/commission')) return next();
    if (req.method !== 'POST' || req.url !== COMMISSION_ROUTE) {
      return response(res, 404, { ok: false, code: 'route_refused' });
    }
    if (closed || active) return response(res, 503, { ok: false, code: 'publication_unavailable' });
    // One bounded operation, no queue. Clear only this exact completion.
    const task = handle(req, res).catch(() => {
      if (!res.writableEnded && !res.destroyed) response(res, 503, { ok: false, code: 'publication_unavailable' });
    });
    active = task;
    task.finally(() => { if (active === task) active = null; });
  }
  return Object.freeze({ middleware, close: async () => { closed = true; if (active) await active; } });
}
