#!/usr/bin/env node
/** Exercise the real pinned T3 contract consumers without starting an agent. */
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';

const PIN = '0770446869d247a8b28c27d7ed93f47f8ff0c1e4';
const EXPECTED = {
  'packages/shared/src/t3ProjectFile.ts': '6a4cf049f3e6d58a81ce0b93cbe9b9d3a1970694ef16679b13ab756e6de58f69',
  'packages/contracts/src/t3ProjectFile.ts': 'efabd7fb41fb38d401169eb661cea698acb679f899ead6b490f02cb57f083fea',
  'packages/contracts/src/orchestratorMcp.ts': 'a1a1f5ffc84c5cc151947db666069a440f1f4f15c96cdd6dabfbc0b9bae826d1',
  'packages/contracts/src/orchestrationV2.ts': '55479fd5af733e0af6afad7f60d3d8de9f4e6916822e404e28f11deccd3d5ee0',
};

async function main() {
  const argv = process.argv.slice(2);
  if (argv.length !== 4 || argv[0] !== '--native-root' || argv[2] !== '--input') {
    throw new Error('QUALIFICATION_ARGUMENTS_REQUIRED');
  }
  const root = realpathSync(argv[1]);
  const head = execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8', timeout: 10000 }).trim();
  if (head !== PIN) throw new Error('NATIVE_SOURCE_PIN_DIFFERS');
  // Imported native contract/helper source must be unchanged, even if unrelated
  // runtime work exists in this read-only checkout. Never install dependencies here.
  execFileSync('git', ['-C', root, 'diff', '--exit-code', 'HEAD', '--',
    'packages/contracts/src', 'packages/shared/src'], { timeout: 10000, stdio: 'pipe' });
  for (const [file, expected] of Object.entries(EXPECTED)) {
    const hash = createHash('sha256').update(readFileSync(join(root, file))).digest('hex');
    if (hash !== expected) throw new Error('NATIVE_CONSUMER_BYTES_DIFFER');
  }
  const raw = readFileSync(argv[3]);
  if (raw.length > 1048576) throw new Error('QUALIFICATION_INPUT_TOO_LARGE');
  const input = JSON.parse(raw.toString('utf8'));
  const requireNative = createRequire(join(root, 'packages/contracts/package.json'));
  const Schema = await import(pathToFileURL(requireNative.resolve('effect/Schema')).href);
  const project = await import(pathToFileURL(join(root, 'packages/shared/src/t3ProjectFile.ts')).href);
  const mcp = await import(pathToFileURL(join(root, 'packages/contracts/src/orchestratorMcp.ts')).href);
  const orchestration = await import(pathToFileURL(join(root, 'packages/contracts/src/orchestrationV2.ts')).href);
  const accepts = (schema, value) => Schema.decodeExit(schema)(value)._tag === 'Success';
  const invalidActions = structuredClone(input.actions);
  invalidActions.scripts[0].icon = 'not-a-native-icon';
  const checks = [
    ['native_project_actions_parse', project.parseT3ProjectFile(JSON.stringify(input.actions)) !== null],
    ['native_project_actions_reject_bad_icon', project.parseT3ProjectFile(JSON.stringify(invalidActions)) === null],
    ['native_delegate_shared_schema', accepts(mcp.OrchestratorMcpDelegateTaskInput, { ...input.delegation, isolation: 'shared' })],
    ['native_delegate_worktree_schema', accepts(mcp.OrchestratorMcpDelegateTaskInput, { ...input.delegation, isolation: 'worktree' })],
    ['native_delegate_rejects_unknown_isolation', !accepts(mcp.OrchestratorMcpDelegateTaskInput, { ...input.delegation, isolation: 'custom-worktree-controller' })],
    ['native_delegate_rejects_unknown_role', !accepts(mcp.OrchestratorMcpDelegateTaskInput, { ...input.delegation, role: 'privileged-ceo' })],
    ['native_launch_workspace_schema', accepts(orchestration.OrchestrationV2ThreadLaunchWorkspaceStrategy, input.launch.arguments.workspaceStrategy)],
    ['native_launch_rejects_shadow_workspace', !accepts(orchestration.OrchestrationV2ThreadLaunchWorkspaceStrategy, { type: 'shadow-workspace' })],
    ['native_child_inventory_request_schema', accepts(mcp.OrchestratorMcpThreadListInput, input.inventory)],
    ['native_child_inventory_rejects_bad_cursor', !accepts(mcp.OrchestratorMcpThreadListInput, { ...input.inventory, cursor: -1 })],
    ['native_child_inventory_rejects_oversize_page', !accepts(mcp.OrchestratorMcpThreadListInput, { ...input.inventory, limit: 101 })],
    ['native_settled_wait_schema', accepts(mcp.OrchestratorMcpThreadWaitInput, input.settledWait)],
    ['native_settled_wait_rejects_non_boolean_join', !accepts(mcp.OrchestratorMcpThreadWaitInput, { ...input.settledWait, untilDelegatedWorkSettled: 'true' })],
    ['native_launch_request_id_schema', accepts(mcp.OrchestratorMcpClientRequestId, input.launch.arguments.clientRequestId)],
    ['native_message_fits_prompt_contract', accepts(mcp.OrchestratorMcpDelegateTaskInput.fields.task, input.launch.arguments.message)],
  ];
  const failed = checks.filter(([, passed]) => !passed).map(([name]) => name);
  const report = {
    schema: 'mastermind.t3_project_team_native_qualification.v1',
    native_source_pin: head,
    native_consumer_sha256: EXPECTED,
    node_version: process.version,
    checks: checks.map(([name, passed]) => ({ name, passed })),
    passed: failed.length === 0,
    effects: { native_threads: 0, model_calls: 0, credentials: 0, profile_edits: 0 },
    proves: 'Actual pinned native project-file parser and delegation/workspace/prompt contracts consume the compiler output.',
    does_not_prove: 'Live native agent execution, active-project import, installed app source identity, routing admission, model quality or project acceptance.',
  };
  console.log(JSON.stringify(report, null, 2));
  if (failed.length) process.exitCode = 1;
}

main().catch(() => {
  console.log(JSON.stringify({ error: 'NATIVE_QUALIFICATION_NOT_PROVEN', effects: 'No agent dispatch is implemented by this script' }));
  process.exitCode = 2;
});
