import os from 'node:os';
import {lstat, readFile} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {
  canonicalDigest,
  discoverAccounts,
  probeInstalledAccount,
} from './fleet-contract-status.mjs';

export const SCHEMA = 'mastermind.studio_direct_release_fleet.v1';
const ACCOUNT_RE = /^[a-z0-9][a-z0-9_-]{0,47}$/;
const HEX64_RE = /^[0-9a-f]{64}$/;
const FILE_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const FAILURE_CODE_RE = /^[A-Z][A-Z0-9_]{0,63}$/;
const MAX_ACCOUNTS = 16;
const MAX_MANIFEST_BYTES = 128 * 1024;
const MAX_FILES = 64;
const PRIVATE_ROOT = path.join(os.homedir(), '.local', 'share', 'studio-direct-mcp', 'private');

function exactDigest(value, field) {
  if (typeof value !== 'string' || !HEX64_RE.test(value)) {
    throw new TypeError(`${field} requires a sha256 digest`);
  }
  return value;
}

function normalizedFiles(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError('manifest files must be an object');
  }
  const names = Object.keys(value).sort();
  if (names.length === 0 || names.length > MAX_FILES) {
    throw new RangeError('manifest files must be non-empty and bounded');
  }
  const files = {};
  for (const name of names) {
    if (!FILE_NAME_RE.test(name)) throw new TypeError('manifest file name is invalid');
    files[name] = exactDigest(value[name], `manifest file ${name}`);
  }
  return files;
}

/**
 * Return the account-insensitive staged runtime generation.
 *
 * Account/port/config/plist/source paths are deliberately excluded: they are
 * seat-specific deployment state, not the source/runtime build generation.
 */
export function releaseBuildIdentity(manifest) {
  if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) {
    throw new TypeError('manifest must be an object');
  }
  if (!Number.isInteger(manifest.version) || manifest.version < 1) {
    throw new TypeError('manifest version is invalid');
  }
  const payload = {
    version: manifest.version,
    nodeHash: exactDigest(manifest.nodeHash, 'nodeHash'),
    backendHash: exactDigest(manifest.backendHash, 'backendHash'),
    dependencyTreeHash: exactDigest(manifest.dependencyTreeHash, 'dependencyTreeHash'),
    files: normalizedFiles(manifest.files),
  };
  return canonicalDigest(payload);
}

async function readReleaseManifest(root, account) {
  if (!ACCOUNT_RE.test(account)) throw new TypeError('invalid account');
  const manifestPath = path.join(root, account, 'manifest.json');
  const stat = await lstat(manifestPath);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new TypeError('manifest must be a regular file');
  if (stat.size > MAX_MANIFEST_BYTES) throw new RangeError('manifest exceeds size limit');
  const value = JSON.parse(await readFile(manifestPath, 'utf8'));
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError('manifest must be an object');
  }
  if (value.account !== account) throw new TypeError('manifest account mismatch');
  return value;
}

export async function probeReleaseAccount(account, root = PRIVATE_ROOT) {
  const [contract, manifest] = await Promise.all([
    probeInstalledAccount(account, root),
    readReleaseManifest(root, account),
  ]);
  return {
    account,
    buildIdentity: releaseBuildIdentity(manifest),
    toolCount: contract.toolCount,
    invocationDigest: contract.invocationDigest,
    publishedDigest: contract.publishedDigest,
  };
}

function assertReleaseRow(row) {
  if (!row || typeof row !== 'object' || !ACCOUNT_RE.test(row.account ?? '')) {
    throw new TypeError('release row requires account');
  }
  exactDigest(row.buildIdentity, 'buildIdentity');
  exactDigest(row.invocationDigest, 'invocationDigest');
  exactDigest(row.publishedDigest, 'publishedDigest');
  if (!Number.isInteger(row.toolCount) || row.toolCount < 0 || row.toolCount > 256) {
    throw new TypeError('release row requires bounded toolCount');
  }
}

function groupBy(rows, key, extra) {
  const groups = new Map();
  for (const row of rows) {
    const identity = row[key];
    const current = groups.get(identity);
    if (current) {
      current.accounts.push(row.account);
      current.buildIdentities.add(row.buildIdentity);
      current.invocationDigests.add(row.invocationDigest);
      current.publishedDigests.add(row.publishedDigest);
      current.toolCounts.add(row.toolCount);
      continue;
    }
    groups.set(identity, {
      identity,
      accounts: [row.account],
      buildIdentities: new Set([row.buildIdentity]),
      invocationDigests: new Set([row.invocationDigest]),
      publishedDigests: new Set([row.publishedDigest]),
      toolCounts: new Set([row.toolCount]),
    });
  }
  return [...groups.values()]
    .map(group => ({
      [extra.identityField]: group.identity,
      accounts: group.accounts.sort(),
      buildIdentities: [...group.buildIdentities].sort(),
      invocationDigests: [...group.invocationDigests].sort(),
      publishedDigests: [...group.publishedDigests].sort(),
      toolCounts: [...group.toolCounts].sort((a, b) => a - b),
    }))
    .sort((a, b) => a.accounts[0].localeCompare(b.accounts[0]));
}

export function classifyFleetRelease(rows) {
  if (!Array.isArray(rows)) throw new TypeError('rows must be an array');
  const normalized = [...rows].sort((a, b) => a.account.localeCompare(b.account));
  const seen = new Set();
  for (const row of normalized) {
    assertReleaseRow(row);
    if (seen.has(row.account)) throw new TypeError('duplicate release account');
    seen.add(row.account);
  }
  const buildGroupCount = new Set(normalized.map(row => row.buildIdentity)).size;
  const invocationGroupCount = new Set(normalized.map(row => row.invocationDigest)).size;
  const contractGroupCount = new Set(normalized.map(row => row.publishedDigest)).size;
  let classification;
  if (normalized.length === 0) classification = 'UNKNOWN_EMPTY_FLEET';
  else if (invocationGroupCount > 1) classification = 'INVOCATION_CONTRACT_DRIFT';
  else if (contractGroupCount > 1) classification = 'PUBLISHED_METADATA_CONTRACT_DRIFT';
  else if (buildGroupCount > 1) classification = 'CONTRACT_PRESERVING_BUILD_DRIFT';
  else classification = 'UNIFORM_RELEASE_CONTRACT';
  return {
    classification,
    buildGroupCount,
    invocationGroupCount,
    contractGroupCount,
    buildGroups: groupBy(normalized, 'buildIdentity', {identityField: 'buildIdentity'}),
    contractGroups: groupBy(normalized, 'publishedDigest', {identityField: 'publishedDigest'}),
  };
}

function normalizeFailures(failures) {
  if (!Array.isArray(failures)) throw new TypeError('failures must be an array');
  const rows = failures.map(row => {
    if (!row || typeof row !== 'object' || !ACCOUNT_RE.test(row.account ?? '')) {
      throw new TypeError('failure row requires account');
    }
    if (!FAILURE_CODE_RE.test(row.code ?? '')) throw new TypeError('failure row requires closed code');
    return {account: row.account, code: row.code};
  }).sort((a, b) => a.account.localeCompare(b.account));
  if (new Set(rows.map(row => row.account)).size !== rows.length) {
    throw new TypeError('duplicate failure account');
  }
  return rows;
}

export function publicReleaseProjection(rows, failures = []) {
  if (!Array.isArray(rows)) throw new TypeError('rows must be an array');
  const normalized = [...rows].sort((a, b) => a.account.localeCompare(b.account));
  for (const row of normalized) assertReleaseRow(row);
  const normalizedFailures = normalizeFailures(failures);
  const identities = [...normalized.map(row => row.account), ...normalizedFailures.map(row => row.account)];
  if (identities.length > MAX_ACCOUNTS) throw new RangeError('account count exceeds limit');
  if (new Set(identities).size !== identities.length) throw new TypeError('duplicate account');
  const classified = classifyFleetRelease(normalized);
  const complete = identities.length > 0 && normalizedFailures.length === 0;
  return {
    schema: SCHEMA,
    accountCount: identities.length,
    observedReleaseCount: normalized.length,
    allReleasesObserved: complete,
    classification: complete ? classified.classification : 'UNKNOWN_INCOMPLETE_FLEET',
    buildGroupCount: classified.buildGroupCount,
    invocationGroupCount: classified.invocationGroupCount,
    contractGroupCount: classified.contractGroupCount,
    accounts: normalized.map(row => ({
      account: row.account,
      buildIdentity: row.buildIdentity,
      toolCount: row.toolCount,
      invocationDigest: row.invocationDigest,
      publishedDigest: row.publishedDigest,
    })),
    buildGroups: classified.buildGroups,
    contractGroups: classified.contractGroups,
    failures: normalizedFailures,
  };
}

export async function buildFleetReleaseStatus(
  root = PRIVATE_ROOT,
  {discover = discoverAccounts, probe = probeReleaseAccount} = {},
) {
  const accounts = await discover(root);
  if (!Array.isArray(accounts) || accounts.length > MAX_ACCOUNTS) {
    throw new RangeError('account discovery is invalid or exceeds limit');
  }
  const rows = [];
  const failures = [];
  for (const account of accounts) {
    try {
      rows.push(await probe(account, root));
    } catch {
      failures.push({account, code: 'RELEASE_PROBE_FAILED'});
    }
  }
  return publicReleaseProjection(rows, failures);
}

async function main() {
  if (process.argv.length !== 2) throw new Error('fleet release status accepts no arguments');
  const output = await buildFleetReleaseStatus();
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => {
    process.stderr.write(`fleet release status failed: ${error.message}\n`);
    process.exitCode = 1;
  });
}
