import crypto from 'node:crypto';
import os from 'node:os';
import {lstat, readFile, readdir} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

export const SCHEMA = 'mastermind.studio_direct_contract_fleet.v1';
const ACCOUNT_RE = /^[a-z0-9][a-z0-9_-]{0,47}$/;
const HEX64_RE = /^[0-9a-f]{64}$/;
const MAX_ACCOUNTS = 16;
const MAX_TOOLS = 256;
const MAX_PAGES = 16;
const PRIVATE_ROOT = path.join(os.homedir(), '.local', 'share', 'studio-direct-mcp', 'private');

function canonicalize(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new TypeError('unsupported JSON value');
    return value;
  }
  if (Array.isArray(value)) return value.map(canonicalize);
  if (typeof value === 'object') {
    const out = {};
    for (const key of Object.keys(value).sort()) {
      if (value[key] === undefined) throw new TypeError('unsupported JSON value');
      out[key] = canonicalize(value[key]);
    }
    return out;
  }
  throw new TypeError('unsupported JSON value');
}

export function canonicalDigest(value) {
  const bytes = JSON.stringify(canonicalize(value));
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function normalizedTool(tool) {
  if (!tool || typeof tool !== 'object' || typeof tool.name !== 'string' || !tool.name) {
    throw new TypeError('tool requires name');
  }
  if (!tool.inputSchema || typeof tool.inputSchema !== 'object') {
    throw new TypeError(`tool ${tool.name} requires inputSchema`);
  }
  return {
    name: tool.name,
    title: typeof tool.title === 'string' ? tool.title : null,
    description: typeof tool.description === 'string' ? tool.description : null,
    inputSchema: tool.inputSchema,
    outputSchema: tool.outputSchema && typeof tool.outputSchema === 'object' ? tool.outputSchema : null,
    annotations: tool.annotations && typeof tool.annotations === 'object' ? tool.annotations : null,
    _meta: tool._meta && typeof tool._meta === 'object' ? tool._meta : null,
  };
}

export function contractDigests(tools) {
  if (!Array.isArray(tools)) throw new TypeError('tools must be an array');
  if (tools.length > MAX_TOOLS) throw new RangeError(`tool count exceeds ${MAX_TOOLS}`);
  const normalized = tools.map(normalizedTool).sort((a, b) => a.name.localeCompare(b.name));
  const names = normalized.map(tool => tool.name);
  if (new Set(names).size !== names.length) throw new TypeError('duplicate tool name');
  const invocation = normalized.map(tool => ({name: tool.name, inputSchema: tool.inputSchema}));
  return {
    toolCount: normalized.length,
    toolNames: names,
    invocationDigest: canonicalDigest(invocation),
    publishedDigest: canonicalDigest(normalized),
  };
}

export function validateManifest(manifest, expectedAccount) {
  if (!ACCOUNT_RE.test(expectedAccount)) throw new TypeError('invalid expected account');
  if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) {
    throw new TypeError('manifest must be an object');
  }
  if (manifest.account !== expectedAccount) throw new TypeError('manifest account mismatch');
  if (!Number.isInteger(manifest.port) || manifest.port < 1024 || manifest.port > 65535) {
    throw new TypeError('manifest port must be an integer in range');
  }
  return {account: expectedAccount, port: manifest.port};
}

async function readManifest(root, account) {
  const manifestPath = path.join(root, account, 'manifest.json');
  const stat = await lstat(manifestPath);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new TypeError('manifest must be a regular file');
  const parsed = JSON.parse(await readFile(manifestPath, 'utf8'));
  return validateManifest(parsed, account);
}

export async function discoverAccounts(root = PRIVATE_ROOT) {
  const entries = await readdir(root, {withFileTypes: true});
  const accounts = [];
  for (const entry of entries) {
    if (!entry.isDirectory() || !ACCOUNT_RE.test(entry.name)) continue;
    try {
      await readManifest(root, entry.name);
      accounts.push(entry.name);
    } catch {
      continue;
    }
  }
  accounts.sort();
  if (accounts.length > MAX_ACCOUNTS) throw new RangeError(`account count exceeds ${MAX_ACCOUNTS}`);
  return accounts;
}

async function loadSdk(root, account) {
  const sdkRoot = path.join(root, account, 'node_modules', '@modelcontextprotocol', 'sdk', 'dist', 'esm', 'client');
  const [{Client}, {StreamableHTTPClientTransport}] = await Promise.all([
    import(pathToFileURL(path.join(sdkRoot, 'index.js')).href),
    import(pathToFileURL(path.join(sdkRoot, 'streamableHttp.js')).href),
  ]);
  return {Client, StreamableHTTPClientTransport};
}

async function listAllTools(client) {
  const tools = [];
  let cursor;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const result = await client.listTools(cursor ? {cursor} : {});
    if (!result || !Array.isArray(result.tools)) throw new TypeError('listTools returned invalid payload');
    tools.push(...result.tools);
    if (tools.length > MAX_TOOLS) throw new RangeError(`tool count exceeds ${MAX_TOOLS}`);
    cursor = result.nextCursor;
    if (!cursor) return tools;
  }
  throw new RangeError(`tool catalog exceeded ${MAX_PAGES} pages`);
}

export async function probeInstalledAccount(account, root = PRIVATE_ROOT) {
  const {port} = await readManifest(root, account);
  const {Client, StreamableHTTPClientTransport} = await loadSdk(root, account);
  const client = new Client({name: 'studio-direct-contract-status', version: '1'});
  const transport = new StreamableHTTPClientTransport(new URL(`http://127.0.0.1:${port}/mcp`));
  try {
    await client.connect(transport);
    const digests = contractDigests(await listAllTools(client));
    return {account, ...digests};
  } finally {
    try { await transport.terminateSession(); } catch {}
    try { await client.close(); } catch {}
  }
}

function assertRow(row) {
  if (!row || typeof row !== 'object' || !ACCOUNT_RE.test(row.account ?? '')) {
    throw new TypeError('contract row requires account');
  }
  if (!Number.isInteger(row.toolCount) || row.toolCount < 0 || row.toolCount > MAX_TOOLS) {
    throw new TypeError('contract row requires bounded toolCount');
  }
  if (!Array.isArray(row.toolNames) || row.toolNames.length !== row.toolCount || row.toolNames.some(name => typeof name !== 'string')) {
    throw new TypeError('contract row requires toolNames');
  }
  if (!HEX64_RE.test(row.invocationDigest ?? '') || !HEX64_RE.test(row.publishedDigest ?? '')) {
    throw new TypeError('contract row requires SHA-256 digests');
  }
}

export function groupContracts(rows) {
  if (!Array.isArray(rows)) throw new TypeError('rows must be an array');
  const normalized = [...rows].sort((a, b) => a.account.localeCompare(b.account));
  const seen = new Set();
  const groups = new Map();
  for (const row of normalized) {
    assertRow(row);
    if (seen.has(row.account)) throw new TypeError('duplicate account');
    seen.add(row.account);
    const existing = groups.get(row.publishedDigest);
    if (existing) {
      if (
        existing.invocationDigest !== row.invocationDigest ||
        existing.toolCount !== row.toolCount ||
        canonicalDigest(existing.toolNames) !== canonicalDigest(row.toolNames)
      ) {
        throw new TypeError('published digest collision with inconsistent contract');
      }
      existing.accounts.push(row.account);
      continue;
    }
    groups.set(row.publishedDigest, {
      publishedDigest: row.publishedDigest,
      invocationDigest: row.invocationDigest,
      toolCount: row.toolCount,
      toolNames: [...row.toolNames],
      accounts: [row.account],
    });
  }
  return [...groups.values()].sort((a, b) => a.accounts[0].localeCompare(b.accounts[0]));
}

export function publicFleetProjection(rows) {
  const sorted = [...rows].sort((a, b) => a.account.localeCompare(b.account));
  for (const row of sorted) assertRow(row);
  return {
    schema: SCHEMA,
    accountCount: sorted.length,
    contractGroupCount: groupContracts(sorted).length,
    accounts: sorted.map(row => ({
      account: row.account,
      toolCount: row.toolCount,
      invocationDigest: row.invocationDigest,
      publishedDigest: row.publishedDigest,
    })),
    groups: groupContracts(sorted),
  };
}

export async function buildFleetContractStatus(root = PRIVATE_ROOT) {
  const accounts = await discoverAccounts(root);
  const rows = [];
  for (const account of accounts) rows.push(await probeInstalledAccount(account, root));
  return publicFleetProjection(rows);
}

async function main() {
  if (process.argv.length !== 2) throw new Error('fleet contract status accepts no arguments');
  const output = await buildFleetContractStatus();
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => {
    process.stderr.write(`fleet contract status failed: ${error.message}\n`);
    process.exitCode = 1;
  });
}
