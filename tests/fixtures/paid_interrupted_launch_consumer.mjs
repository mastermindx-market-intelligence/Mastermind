// paid_interrupted_launch_consumer.mjs — test-only IPC driver.
//
// Drives the REAL ExecutiveLaunchCommandPort and OperationController classes
// supplied by the parent against a line-delimited JSON IPC channel. The parent
// owns the authenticated HTTP fixture; this process performs no network I/O,
// sends no credentials, and never mints operation or root Job identity.
//
// Phase `begin`  : submit once, lose the reply, keep the durable pointer with
//                  an `unknown` outcome and no retry.
// Phase `reopen` : fresh process; begin() must block on the retained pointer
//                  without any client call, recover() must poll exactly once
//                  with ceo_intent_status, reach an accepted state carrying the
//                  ORIGINAL workRef and a server-issued rootJobId, and only
//                  then clear the hint.
//
// usage:
//   node paid_interrupted_launch_consumer.mjs <begin|reopen> <port.mjs> \
//     <controller.mjs> <input.json> <hint.json>

import assert from 'node:assert/strict';
import fs from 'node:fs';
import readline from 'node:readline';
import { pathToFileURL } from 'node:url';

const USAGE =
  'usage: node paid_interrupted_launch_consumer.mjs <begin|reopen> <port.mjs> <controller.mjs> <input.json> <hint.json>';

const argv = process.argv.slice(2);
if (argv.length !== 5) fail(USAGE, 2);
const [phase, portPath, controllerPath, inputPath, hintPath] = argv;
if (phase !== 'begin' && phase !== 'reopen') fail(USAGE, 2);

function fail(message, code) {
  process.stderr.write(`${message}\n`);
  process.exit(code);
}

function note(message) {
  process.stderr.write(`[${phase}] ${message}\n`);
}

const fixture = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
assert.ok(fixture && typeof fixture === 'object', 'input.json must hold the fixture object');
assert.ok(fixture.config && typeof fixture.config === 'object', 'fixture.config is required');
assert.ok(fixture.form && typeof fixture.form === 'object', 'fixture.form is required');
assert.equal(typeof fixture.principalScope, 'string', 'fixture.principalScope must be a string');
assert.equal(typeof fixture.generation, 'string', 'fixture.generation must be a string');

// --- pointer helpers ---------------------------------------------------------
// A pointer is the EXACT {operationKey, kind, targetKey} tuple. Payload,
// objective, receipt or Job state must never travel inside it.

const POINTER_KEYS = ['kind', 'operationKey', 'targetKey'];

function asPointer(candidate) {
  assert.ok(
    candidate !== null && typeof candidate === 'object' && !Array.isArray(candidate),
    'pointer must be an object',
  );
  const pointer = {
    operationKey: candidate.operationKey,
    kind: candidate.kind,
    targetKey: candidate.targetKey,
  };
  for (const key of POINTER_KEYS) {
    assert.equal(typeof pointer[key], 'string', `pointer.${key} must be a string`);
  }
  return pointer;
}

function samePointer(left, right) {
  return POINTER_KEYS.every((key) => left[key] === right[key]);
}

function isTupleShaped(node) {
  return (
    node !== null &&
    typeof node === 'object' &&
    !Array.isArray(node) &&
    typeof node.operationKey === 'string' &&
    typeof node.kind === 'string' &&
    typeof node.targetKey === 'string'
  );
}

// --- durable hint file (test-only store) -------------------------------------
// The file holds exactly {scope, pointer}; the pointer is the bare tuple.

function hintDirOf(filePath) {
  const cut = filePath.lastIndexOf('/');
  return cut === -1 ? '.' : filePath.slice(0, cut);
}

function readHintDoc() {
  let raw;
  try {
    raw = fs.readFileSync(hintPath, 'utf8');
  } catch (error) {
    if (error && error.code === 'ENOENT') return null;
    throw error;
  }
  return JSON.parse(raw);
}

function writeHintDoc(doc) {
  fs.mkdirSync(hintDirOf(hintPath), { recursive: true }); // only what is missing
  const tempPath = `${hintPath}.tmp-${process.pid}-${Date.now()}`;
  const fd = fs.openSync(tempPath, 'wx', 0o600); // private temp, exclusive create
  try {
    fs.writeFileSync(fd, JSON.stringify(doc));
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  fs.renameSync(tempPath, hintPath); // atomic publish
}

function makeHintStore() {
  return {
    read(scope) {
      assert.equal(typeof scope, 'string', 'scope must be a string');
      const doc = readHintDoc();
      if (!doc || doc.scope !== scope) return null;
      const pointer = asPointer(doc.pointer);
      assert.deepEqual(doc.pointer, pointer, 'hint pointer must be the bare tuple');
      return pointer;
    },
    reserve(scope, pointer) {
      assert.equal(typeof scope, 'string', 'scope must be a string');
      const wanted = asPointer(pointer);
      const doc = readHintDoc();
      if (doc) {
        // An existing pointer is never overwritten, not even by an equal one.
        assert.equal(typeof doc.scope, 'string', 'hint scope must be a string');
        return { reserved: false, pointer: asPointer(doc.pointer) };
      }
      writeHintDoc({ scope, pointer: wanted });
      return { reserved: true };
    },
    clearIfEqual(scope, pointer) {
      assert.equal(typeof scope, 'string', 'scope must be a string');
      const wanted = asPointer(pointer);
      const doc = readHintDoc();
      if (!doc || doc.scope !== scope || !samePointer(asPointer(doc.pointer), wanted)) {
        return false;
      }
      try {
        fs.unlinkSync(hintPath); // remove this exact file only
      } catch (error) {
        if (error && error.code === 'ENOENT') return false;
        throw error;
      }
      return true;
    },
  };
}

// --- IPC client --------------------------------------------------------------
// One JSON line per call on stdout, then exactly one JSON reply line is awaited
// on stdin. Replies are either {envelope} or {throw}; a throw reply rejects the
// promise so the real controller decides the outcome. No retries, no guessing.

let activeRunner = null;

class IpcRunner {
  constructor() {
    this.callNames = [];
    this.interface = readline.createInterface({ input: process.stdin, terminal: false });
    this.replies = this.interface[Symbol.asyncIterator](); // single iterator for all replies
    activeRunner = this;
  }

  async callTool(name, args) {
    assert.equal(typeof name, 'string', 'callTool name must be a string');
    this.callNames.push(name);
    if (name === 'submit_ceo_intent') {
      // The pending pointer must already be durable before the first submit.
      assert.ok(fs.existsSync(hintPath), 'hint file must be committed before the first submit');
    }
    process.stdout.write(`${JSON.stringify({ type: 'call', name, arguments: args })}\n`);
    const reply = await this.nextReply();
    if (Object.prototype.hasOwnProperty.call(reply, 'throw')) {
      // The parent intentionally lost the fixture response; surface a real
      // rejection and never fabricate an accepted or repaired envelope.
      throw new Error(String(reply.throw));
    }
    assert.ok(
      Object.prototype.hasOwnProperty.call(reply, 'envelope'),
      'parent reply must carry either envelope or throw',
    );
    return reply.envelope;
  }

  async nextReply() {
    for (;;) {
      const next = await this.replies.next();
      assert.ok(!next.done, 'parent closed stdin before replying');
      const line = String(next.value).trim();
      if (line === '') continue;
      return JSON.parse(line);
    }
  }

  releaseStdin() {
    this.interface.close();
    process.stdin.destroy();
  }
}

// --- deep state inspection ---------------------------------------------------

function deepVisit(root, visit) {
  const seen = new Set();
  const walk = (node, path) => {
    if (node === null || typeof node !== 'object' || seen.has(node)) return;
    seen.add(node);
    visit(node, path);
    for (const [key, value] of Object.entries(node)) walk(value, path.concat(key));
  };
  walk(root, []);
}

function findTuple(root) {
  let found = null;
  deepVisit(root, (node) => {
    if (!found && isTupleShaped(node)) found = asPointer(node);
  });
  return found;
}

function findWorkRef(root, workRef) {
  let found = null;
  deepVisit(root, (node, path) => {
    if (found || node === null || typeof node !== 'object') return;
    if (typeof node.workRef === 'string' && node.workRef === workRef) {
      found = { path: path.concat('workRef').join('.'), value: workRef };
    }
  });
  return found;
}

function findJobIdentity(root) {
  let found = null;
  deepVisit(root, (node, path) => {
    if (found || node === null || typeof node !== 'object') return;
    for (const [key, value] of Object.entries(node)) {
      if (/job/i.test(key) && typeof value === 'string' && /^JOB-/.test(value)) {
        found = { path: path.concat(key).join('.'), value };
        return;
      }
    }
  });
  return found;
}

// --- real supplied classes ---------------------------------------------------
// The parent supplies transpiled real modules; they are imported by their exact
// paths and never reimplemented here.

async function loadClasses() {
  const portModule = await import(pathToFileURL(portPath).href);
  const controllerModule = await import(pathToFileURL(controllerPath).href);
  assert.equal(
    typeof portModule.ExecutiveLaunchCommandPort,
    'function',
    'port.mjs must export ExecutiveLaunchCommandPort',
  );
  assert.equal(
    typeof controllerModule.OperationController,
    'function',
    'controller.mjs must export OperationController',
  );
  return [portModule.ExecutiveLaunchCommandPort, controllerModule.OperationController];
}

function buildSession(PortClass, ControllerClass, client, fxt, store) {
  const port = new PortClass(fxt.config, client, () => ({
    principalScope: fxt.principalScope,
    generation: fxt.generation,
  }));
  const intent = port.makeLaunchIntent(fxt.form);
  assert.ok(intent, 'makeLaunchIntent must produce a launch intent');
  return { intent, controller: new ControllerClass(port, store) };
}

// --- phase: begin ------------------------------------------------------------

async function runBegin(fxt) {
  const client = new IpcRunner();
  const store = makeHintStore();
  const [PortClass, ControllerClass] = await loadClasses();
  const { intent, controller } = buildSession(PortClass, ControllerClass, client, fxt, store);

  const state = await controller.begin(intent);

  // The parent committed the HTTP submission and then intentionally lost the
  // response: exactly one submit, no retry, and an `unknown` outcome.
  assert.deepEqual(
    client.callNames,
    ['submit_ceo_intent'],
    'begin must issue exactly one submit_ceo_intent and nothing else',
  );
  assert.ok(state !== null && typeof state === 'object', 'begin must return a state object');
  assert.equal(
    state.status,
    'unknown',
    `begin must report status "unknown", got ${JSON.stringify(state.status)}`,
  );

  // The durable hint must hold exactly the original pending pointer.
  const doc = readHintDoc();
  assert.ok(doc, 'hint file must survive the lost reply');
  assert.deepEqual(Object.keys(doc).sort(), ['pointer', 'scope'], 'hint file must hold only scope and pointer');
  assert.equal(doc.scope, fxt.principalScope, 'hint scope must be the principal scope');
  const retainedPointer = asPointer(doc.pointer);
  assert.deepEqual(doc.pointer, retainedPointer, 'hint pointer must be the bare tuple');

  // If the returned state exposes a pointer it must be the same exact one.
  const statePointer = findTuple(state);
  if (statePointer) {
    assert.deepEqual(statePointer, retainedPointer, 'state pointer must match the retained hint pointer');
  }

  client.releaseStdin();
  await emit({
    type: 'result',
    phase: 'begin',
    state,
    callNames: client.callNames,
    retainedPointer,
  });
}

// --- phase: reopen -----------------------------------------------------------

async function runReopen(fxt) {
  const client = new IpcRunner();
  const store = makeHintStore();
  const [PortClass, ControllerClass] = await loadClasses();

  // A fresh process must find the durable hint left by the interrupted run.
  const retainedPointer = store.read(fxt.principalScope);
  assert.ok(retainedPointer, 'reopen requires an existing durable hint for the principal scope');

  const { intent, controller } = buildSession(PortClass, ControllerClass, client, fxt, store);

  const blockedState = await controller.begin(intent);

  // The retained pointer must block the launch before any client traffic.
  assert.deepEqual(
    client.callNames,
    [],
    'begin must make no client calls while a pending pointer is retained',
  );
  assert.ok(blockedState !== null && typeof blockedState === 'object', 'begin must return a blocked state object');
  assert.ok(
    JSON.stringify(blockedState).includes(retainedPointer.operationKey) ||
      JSON.stringify(blockedState).includes(retainedPointer.targetKey),
    'blocked state must reference the retained pending pointer',
  );
  const blockedPointer = findTuple(blockedState);
  if (blockedPointer) {
    assert.deepEqual(blockedPointer, retainedPointer, 'blocked state must reference the exact retained pointer');
  }
  if (typeof blockedState.status === 'string') {
    assert.ok(
      !/accept|complete|unknown/i.test(blockedState.status),
      `blocked state must be an interim checking/pending state, got "${blockedState.status}"`,
    );
    note(`blocked on retained pointer with status ${JSON.stringify(blockedState.status)}`);
  } else {
    note('blocked on retained pointer (state exposes no status field)');
  }

  const state = await controller.recover();

  // Recovery polls the already-committed submission exactly once; never a submit.
  assert.deepEqual(
    client.callNames,
    ['ceo_intent_status'],
    'recover must issue exactly one ceo_intent_status and no submit',
  );
  assert.ok(state !== null && typeof state === 'object', 'recover must return a state object');
  if (typeof state.status === 'string') {
    assert.match(state.status, /accept/i, `recover must report an accepted state, got "${state.status}"`);
  }

  // The accepted state carries the ORIGINAL work target (not the stale draft)
  // and the root Job identity issued by the server — never by this driver.
  const selection = findWorkRef(state, retainedPointer.targetKey);
  assert.ok(selection, `accepted state must include the original workRef "${retainedPointer.targetKey}"`);
  note(`workRef ${selection.value} found at state.${selection.path}`);
  const job = findJobIdentity(state);
  assert.ok(job, 'accepted state must include a root Job identity matching /^JOB-/');
  note(`root Job identity ${job.value} found at state.${job.path}`);

  // Only an accepted outcome may clear the durable hint.
  assert.equal(fs.existsSync(hintPath), false, 'hint file must be removed after the accepted outcome');
  assert.equal(store.read(fxt.principalScope), null, 'store must read empty after the accepted outcome');

  client.releaseStdin();
  await emit({
    type: 'result',
    phase: 'reopen',
    state,
    callNames: client.callNames,
    retainedPointer,
    blockedState,
    pointerBeforeClear: retainedPointer,
  });
}

// --- entry -------------------------------------------------------------------

async function emit(result) {
  await new Promise((resolve) => process.stdout.write(`${JSON.stringify(result)}\n`, resolve));
}

async function main() {
  if (phase === 'begin') await runBegin(fixture);
  else await runReopen(fixture);
}

main().catch((error) => {
  const detail = error && error.stack ? error.stack : String(error);
  note(`driver failure: ${detail}`);
  if (activeRunner) {
    try {
      activeRunner.releaseStdin();
    } catch {
      // stdin already gone
    }
  }
  process.exit(1);
});
