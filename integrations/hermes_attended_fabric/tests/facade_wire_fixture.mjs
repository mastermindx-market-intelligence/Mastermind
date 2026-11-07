// Exercise the real Fabric facade. The engine only consumes fixture outputs;
// it never executes a command, opens a connection or starts a paid worker.
import { createHash } from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import { createFabricFacade } from '../../studio_direct_mcp/fabric-backend.mjs';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const spec = JSON.parse(input);
const outputs = [...spec.adapter_outputs];
const calls = [];
const captured = value => {
  const bytes = Buffer.from(value, 'utf8');
  const envelope = JSON.stringify({
    exit_code: 0, stdout_base64: bytes.toString('base64'),
    stdout_bytes: bytes.length,
    stdout_sha256: createHash('sha256').update(bytes).digest('hex'),
  });
  return { content: [{ type: 'text', text:
    `Process started with PID 123 (shell: /bin/zsh)\nInitial output:\n${envelope}\nMMX_FABRIC_EXIT=0\n` }] };
};
const engine = { async callTool(request) {
  calls.push(request);
  if(spec.revoke_native_after_call===calls.length && spec.hermes_native) {
    const path=join(spec.hermes_native.home,'config.yaml');
    const cfg=JSON.parse(readFileSync(path,'utf8'));
    cfg.plugins.entries['mastermind-fabric-worker'].native_origin.enabled=false;
    writeFileSync(path,JSON.stringify(cfg));
  }
  const next = outputs.shift();
  if (!next) throw new Error('fixture output exhausted');
  if (next.kind === 'lost') throw new Error('fixture transport lost');
  if (next.kind === 'pending') return { content: [{ type: 'text', text:
    'Process started with PID 456 (shell: /bin/zsh)\nInitial output:\n' }] };
  if (next.kind === 'json') return captured(JSON.stringify(next.value));
  if (next.kind === 'text') return captured(next.value);
  throw new Error('unknown fixture output');
} };
const facade = createFabricFacade(engine, {
  adapterPath: '/fixture/fabric_task.py', quotaFallback: spec.follow === true,
  hermesNative: spec.hermes_native ?? null,
});
const reply = await facade.call(spec.action, spec.arguments);
process.stdout.write(JSON.stringify({ reply, calls, unused: outputs.length }));
