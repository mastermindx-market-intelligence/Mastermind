// Test double for the incumbent Mastermind Craft commission compiler
// (research/worker_craft/mastermind-craft/scripts/brief.py, PR #587).
//
// It reproduces only that compiler's frozen process contract:
//   <interpreter> <compiler> compile-commission <request.json> --format json
//   -> stdout: mastermind.craft_commission_compilation.v1
//   -> exit 2 with "BRIEF_REFUSED <field>.<reason>" on stderr when refusing.
//
// It deliberately does NOT reimplement compact-request validation or the real
// rendering. Its job is to let the Studio Direct adapter be proved against the
// contract, including adversarial compiler behavior, while the real compiler is
// still unprotected. STUB_COMMISSION_MODE selects the behavior under test.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

function refuse(token) {
  process.stderr.write(`BRIEF_REFUSED ${token}\n`);
  process.exit(2);
}

const mode = process.env.STUB_COMMISSION_MODE ?? 'ok';
if (mode === 'refuse') refuse('commission.fields');
if (mode === 'refuse_unbounded') refuse(`commission.${'x'.repeat(400)}`);

const [command, requestPath, formatFlag, format, ...rest] = process.argv.slice(2);
if (command !== 'compile-commission' || formatFlag !== '--format' || format !== 'json' || rest.length) {
  refuse('cli.contract');
}

let request;
try {
  request = JSON.parse(readFileSync(requestPath, 'utf8'));
} catch {
  refuse('input.unavailable');
}

// A deliberately verbose deterministic rendering: the whole point of the
// adapter is that the caller sends the small request and the host produces
// the large artifact.
const filler = [
  'Recover the current outcome, the machine job, and the observable end state before writing code.',
  'Use the existing owners: Executive OS for lifecycle, GitHub for implementation, Linear as a projection.',
  'Keep source facts, observations, assumptions, and proposed changes distinct in every return.',
  'Treat each external side effect separately and reconcile an ambiguous mutation on its original carrier.',
];
const sections = [
  ['Mission / outcome', request.outcome?.objective],
  ['Why it matters', request.outcome?.why],
  ['Authority and exact source identities', request.authority_ref],
  ['Scope / write boundary', JSON.stringify(request.scope)],
  ['Acceptance / proof', JSON.stringify(request.acceptance)],
];
const rendered = ['# Worker commission', '', 'Deterministic authoring output from the test compiler contract.'];
for (const [heading, body] of sections) {
  rendered.push('', `## ${heading}`, '', String(body));
  for (let index = 0; index < 12; index += 1) rendered.push(filler[index % filler.length]);
}
rendered.push('');
const markdown = rendered.join('\n');

const result = {
  schema_version: 'mastermind.craft_commission_compilation.v1',
  role: request.role,
  compact_input_sha256: createHash('sha256').update(JSON.stringify(request)).digest('hex'),
  normalized_brief_sha256: createHash('sha256').update('normalized').digest('hex'),
  method_files: ['references/common.md'],
  method_sha256: createHash('sha256').update('method').digest('hex'),
  commission_sha256: createHash('sha256').update(Buffer.from(markdown, 'utf8')).digest('hex'),
  binding_observation: { host_ref: null, workspace_ref: null },
  execution_authority: false,
  runtime_admission: 'NOT_REQUESTED',
  source_verification: 'NOT_PERFORMED',
  provider_selection: 'NOT_PERFORMED',
  model_selection: 'NOT_PERFORMED',
  account_selection: 'NOT_PERFORMED',
  instructions_markdown: markdown,
};

if (mode === 'digest_mismatch') {
  result.commission_sha256 = createHash('sha256').update('a different artifact').digest('hex');
}
if (mode === 'selected_provider') result.provider_selection = 'PERFORMED';
if (mode === 'granted_authority') result.execution_authority = true;
if (mode === 'wrong_schema') result.schema_version = 'mastermind.craft_brief_compilation.v1';
if (mode === 'no_markdown') delete result.instructions_markdown;
if (mode === 'invalid_json') {
  process.stdout.write('{not json');
  process.exit(0);
}

process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
