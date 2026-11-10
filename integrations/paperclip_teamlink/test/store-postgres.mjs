// Optional installed-host qualification. Uses the installed Paperclip SQL guards
// and PostgreSQL binaries, but always creates a disposable, socket-only database.
// It cannot select Paperclip's database or issue any agent/native T3 operation.
// Usage: node test/store-postgres.mjs <paperclip-node-modules> <postgres-bin>
import assert from 'node:assert/strict';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, mkdir, readFile, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { setTimeout as delay } from 'node:timers/promises';
import { Store } from '../store.mjs';
import manifest from '../manifest.mjs';

const [modules, binaries] = process.argv.slice(2).map(x => resolve(x));
if (!modules || !binaries || process.argv.length !== 4) throw new Error('TWO_LOCAL_DEPENDENCY_PATHS_REQUIRED');
const execute = promisify(execFile);
const guard = await import(pathToFileURL(join(modules, '@paperclipai/server/dist/services/plugin-database.js')));
const { default: postgres } = await import(pathToFileURL(join(modules, 'postgres/src/index.js')));
const requireInstalled = createRequire(join(modules, 'paperclipai/package.json'));
const { drizzle } = await import(pathToFileURL(requireInstalled.resolve('drizzle-orm/postgres-js')));
const tables = await import(pathToFileURL(join(modules, '@paperclipai/db/dist/index.js')));
const namespace = guard.derivePluginDatabaseNamespace(manifest.id, manifest.database.namespaceSlug);
assert.equal(namespace, 'plugin_mastermind_teamlink_ddd6e53475');
const directory = await mkdtemp('/tmp/tl-pg-');
const data = join(directory, 'data'), socket = join(directory, 'socket');
const port = 65431; // Private Unix socket directory; no TCP listener is opened.
let server, ended, sql, orm, serverClosed = false, stderr = '', statements = 0;
const checks = [];
const connect = () => postgres({ host: socket, port, database: 'postgres', username: 'teamlink_test',
  max: 4, connect_timeout: 2, idle_timeout: 2, onnotice() {} });
// Only the plugin registry rows are fixtures. Runtime SQL uses the installed
// service's actual validation, placeholder binding, ORM and PostgreSQL driver.
const nativeService = guard.pluginDatabaseService({
  select() { return { from(table) { return { where() { return { async limit() {
    if (table === tables.plugins) return [{ id: 'fixture-plugin', manifestJson: manifest }];
    if (table === tables.pluginDatabaseNamespaces) return [{ namespaceName: namespace, status: 'active' }];
    throw new Error('UNEXPECTED_CORE_METADATA_READ');
  } }; } }; } }; },
  execute(statement) { return orm.execute(statement); },
});
const database = () => ({ namespace,
  async query(statement, params = []) {
    statements++; return nativeService.query('fixture-plugin', statement, params);
  },
  async execute(statement, params = []) {
    statements++; return nativeService.execute('fixture-plugin', statement, params);
  },
});
const operation = (name, issue = 'issue', company = 'company') => ({ companyId: company,
  operationId: name, issueId: issue, fingerprint: `fingerprint-${name}`, phase: 'created',
  bindingId: 'binding', direction: 'paperclip_to_t3', nativeRun: null });

try {
  await mkdir(socket, { mode: 0o700 });
  await execute(join(binaries, 'initdb'), ['-D', data, '-A', 'trust', '-U', 'teamlink_test', '--no-locale', '-E', 'UTF8'],
    { timeout: 20000, maxBuffer: 32768 });
  server = spawn(join(binaries, 'postgres'), ['-D', data, '-h', '', '-k', socket, '-p', String(port),
    '-c', 'fsync=off', '-c', 'unix_socket_permissions=0700'], { stdio: ['ignore', 'ignore', 'pipe'] });
  server.stderr.on('data', part => { stderr = (stderr + part.toString()).slice(-12000); });
  ended = new Promise(done => {
    server.once('error', error => { serverClosed = true; done({ error: error.code }); });
    server.once('close', (code, signal) => { serverClosed = true; done({ code, signal }); });
  });
  sql = connect(); orm = drizzle(sql);
  const deadline = Date.now() + 15000;
  while (true) {
    try { await sql`SELECT 1`; break; }
    catch (error) {
      if (serverClosed || Date.now() >= deadline) throw error;
      await delay(50);
    }
  }
  assert.equal((await sql`SHOW listen_addresses`)[0].listen_addresses, '');
  await sql.unsafe(`CREATE SCHEMA ${namespace}`);
  for (const name of ['001_transport.sql', '002_reconcile_indexes.sql']) {
    const source = await readFile(new URL(`../migrations/${name}`, import.meta.url), 'utf8');
    for (const statement of source.split(';').map(x => x.trim()).filter(Boolean)) {
      guard.validatePluginMigrationStatement(statement, namespace, []);
      await sql.unsafe(statement);
    }
  }
  checks.push('native_namespace_and_migration_guards');
  const first = new Store(database()), second = new Store(database());
  const inserted = await Promise.all([first.insert(operation('same')), second.insert({ ...operation('same'), fingerprint: 'contender' })]);
  assert.equal(inserted.filter(x => x.inserted).length, 1);
  assert.equal(inserted[0].row.fingerprint, inserted[1].row.fingerprint);
  assert.equal(await first.get('other-company', 'same'), null);
  checks.push('unique_operation_and_company_isolation');

  const preimage = await first.get('company', 'same');
  const claims = await Promise.allSettled([
    first.change(preimage, { phase: 'send_inflight', claimant: 'first' }),
    second.change(preimage, { phase: 'send_inflight', claimant: 'second' }),
  ]);
  assert.equal(claims.filter(x => x.status === 'fulfilled').length, 1,
    JSON.stringify(claims.map(x => ({ status: x.status, error: x.reason?.message, code: x.reason?.code }))));
  assert.match(claims.find(x => x.status === 'rejected').reason.message, /OPERATION_REVISION_CONFLICT/);
  const claimed = await first.get('company', 'same');
  assert.equal(claimed.revision, 2); assert.equal(claimed.phase, 'send_inflight');
  checks.push('one_concurrent_dispatch_claim');

  const bindings = await Promise.allSettled([
    first.saveBinding('company', 'issue', 0, { issueId: 'issue', companyId: 'company', bindingId: 'one' }),
    second.saveBinding('company', 'issue', 0, { issueId: 'issue', companyId: 'company', bindingId: 'two' }),
  ]);
  assert.equal(bindings.filter(x => x.status === 'fulfilled').length, 1);
  assert.match(bindings.find(x => x.status === 'rejected').reason.message, /BINDING_REVISION_CONFLICT/);
  const binding = await first.binding('company', 'issue');
  const revised = await first.saveBinding('company', 'issue', binding.revision, { ...binding, watchCursor: 42 });
  await assert.rejects(second.saveBinding('company', 'issue', binding.revision, binding), /BINDING_REVISION_CONFLICT/);
  assert.equal(revised.watchCursor, 42);
  checks.push('binding_revision_and_cursor_fence');

  for (let n = 0; n < 257; n++) {
    const issueId = `page-${String(n).padStart(4, '0')}`;
    await first.saveBinding('pages', issueId, 0, { companyId: 'pages', issueId, bindingId: `b-${n}` });
  }
  let cursor = null; const seen = [], sizes = [];
  do {
    const page = await first.bindingPage('pages', cursor, 128);
    seen.push(...page.bindings.map(x => x.issueId)); sizes.push(page.bindings.length); cursor = page.nextCursor;
  } while (cursor !== null);
  assert.deepEqual(sizes, [128, 128, 1]); assert.equal(new Set(seen).size, 257);
  const scanned = await first.bindings('pages');
  for (const item of scanned) await first.scanAttempted('pages', item.issueId);
  const nextScans = await first.bindings('pages');
  assert.ok(nextScans.every(x => !scanned.some(y => y.issueId === x.issueId)));
  checks.push('real_sql_pagination_and_scan_fairness');

  for (let n = 0; n < 35; n++) await first.insert(operation(`pending-${n}`, 'pending-issue', 'pending-company'));
  const pending = await first.pendingForIssue('pending-company', 'pending-issue');
  assert.equal(pending.length, 32);
  for (const row of pending) await first.attempted(row.companyId, row.operationId);
  const next = await first.pendingForIssue('pending-company', 'pending-issue');
  assert.equal(next.length, 32);
  assert.ok(next.slice(0, 3).every(x => !pending.some(y => y.operationId === x.operationId)));
  assert.equal((await first.pendingForIssue('pending-company', 'other-issue')).length, 0);
  checks.push('pending_recovery_fairness');

  const withRun = await first.change(claimed, { nativeRun: { runId: 'native-original' }, phase: 'in_native' });
  assert.equal(await first.outgoingRun('company', 'binding', 'native-original'), true);
  assert.equal(await first.outgoingRun('other-company', 'binding', 'native-original'), false);
  assert.equal(await first.outgoingRun('company', 'other-binding', 'native-original'), false);
  checks.push('original_run_echo_correlation');
  await sql.end({ timeout: 3 }); sql = connect(); orm = drizzle(sql);
  const restored = new Store(database());
  assert.deepEqual(await restored.get('company', 'same'), withRun);
  assert.equal((await restored.binding('company', 'issue')).watchCursor, 42);
  checks.push('fresh_connection_retains_receipts_and_cursor');
} finally {
  try { await sql?.end({ timeout: 3 }); }
  finally {
    if (server && !serverClosed) {
      server.kill('SIGTERM');
      await Promise.race([ended, delay(5000)]);
      if (!serverClosed) { server.kill('SIGINT'); await Promise.race([ended, delay(5000)]); }
      if (!serverClosed) { server.kill('SIGKILL'); await ended; }
    }
    // Never remove a data directory while its owned database is still running.
    if (!server || serverClosed) await rm(directory, { recursive: true, force: true });
  }
}
assert.ok(serverClosed);
console.log(JSON.stringify({ ok: true, checks, guardedStatements: statements,
  database: 'disposable_socket_only_postgresql', serverStopped: serverClosed,
  productionDatabaseAccess: false, nativeOrAgentCalls: 0 }));
