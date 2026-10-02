/**
 * Real pinned DSH core conformance fixture, not a Worker or provider route.
 * Build only against the qualified external source/lock closure from the runbook.
 * The surrounding process owner must enforce the OS boundary BEFORE loading it.
 */
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {connect} from 'node:net';
import {pathToFileURL} from 'node:url';
import {Context} from '@deepseek-ai/cordis';
import Loader from '@deepseek-ai/cordis-plugin-loader';
import LlmRuntime, {LlmAdapter} from '@deepseek-ai/dsh-llm';
import type {GenerateOptions, StreamChunk} from '@deepseek-ai/dsh-llm';
import SessionStore, {SessionId} from '@deepseek-ai/dsh-session';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import AgentRegistry, {installModelSelection} from '@deepseek-ai/dsh-agent';
import AgentLoop from '@deepseek-ai/dsh-agent-loop';
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection';
import {nativeFixtureFactory, withOwnedFixture} from './fixture_host.ts';
import type {NativeFactoryContext} from './fixture_host.ts';
import {canonical, ObservationError} from './observe.ts';
import type {Agent, Binding, ModuleIdentity} from './observe.ts';

type Recipe = Readonly<{
  recipe_digest: string;
  modules: readonly ModuleIdentity[];
  implementation_digest: string;
}>;
const CASES = ['positive', 'ambient-tool', 'implementation-drift', 'cancel',
  'late-cancel', 'setup-failure', 'cleanup-failure', 'setup-subprocess',
  'setup-network', 'setup-write'] as const;
type CaseName = typeof CASES[number];

/** Only a deliberately inert provider is mounted. Any generation is a failure. */
class NoGenerationAdapter extends LlmAdapter {
  calls = 0;
  onResolve: (() => void) | undefined;
  override async resolveModel(provider: string, model: string) {
    assert.equal(provider, 'fixture');
    assert.equal(model, 'fixture-model');
    this.onResolve?.();
    return {provider, id: model, name: model, defaultMaxTokens: 64};
  }
  override async * stream(_options: GenerateOptions): AsyncIterable<StreamChunk> {
    this.calls++;
    throw new Error('FIXTURE_GENERATION_FORBIDDEN');
  }
}

/** All services below are the actual upstream classes, never contract doubles. */
const PLUGINS = [
  ['llm', LlmRuntime],
  ['sessions', SessionStore],
  ['projections', SessionProjectionRegistry],
  ['prompt', SystemPrompt],
  ['tools', ToolRuntime],
  ['agents', AgentRegistry],
  ['loop', AgentLoop],
] as const;

export async function runMountedFixture(recipe: Recipe, caseName: CaseName) {
  assert.ok(CASES.includes(caseName));
  assert.deepEqual(recipe.modules.map(row => [row.entry_id, row.module]),
    PLUGINS.map(([name]) => ['n0-' + name, 'cordis:n0-' + name]));
  const ctx = new Context();
  const adapter = new NoGenerationAdapter();
  const controller = new AbortController();
  const binding: Binding = Object.freeze({
    attempt_id: 'n0-native-fixture-attempt',
    worker_id: 'n0-native-fixture-worker',
    process_generation_id: 'n0-native-fixture-generation',
    native_session_id: 'n0-native-fixture-session',
  });
  let outcome: Awaited<ReturnType<typeof withOwnedFixture>> | undefined;
  let failure: unknown;
  let nativeAgentAbsent = false;
  let nativeSessionAbsent = false;
  let nativeServicesAbsent = false;
  let setupDenial: string | null = null;
  const requireDenied = (code: unknown) => {
    assert.ok(code === 'EPERM' || code === 'EACCES', 'OS boundary did not deny the setup effect');
    setupDenial = String(code);
    throw new Error('CONTROLLED_SETUP_EFFECT_DENIED');
  };
  try {
    await ctx.plugin(Loader);
    for (const [name, plugin] of PLUGINS) ctx.loader.builtins['n0-' + name] = plugin;
    await ctx.loader.root.update(PLUGINS.map(([name]) => ({
      id: 'n0-' + name, name: 'cordis:n0-' + name,
    })));
    await ctx.loader.await();
    assert.deepEqual([...ctx.loader.entries()].map(row => row.fiber?.state),
      PLUGINS.map(() => 2), 'all real native services must be active');
    ctx.llm.registerAdapter(['fixture'], adapter);
    if (caseName === 'ambient-tool') {
      ctx.tools.register({name: 'unexpected_global', description: 'negative control',
        parameters: {type: 'object'}, execute: async () => 'inert',
        output: {schema: {type: 'string'}, render: () => []}});
    }
    const install = caseName === 'setup-failure'
      ? (...args: Parameters<typeof installModelSelection>) => {
          installModelSelection(...args);
          throw new Error('CONTROLLED_SETUP_FAILURE');
        }
      : installModelSelection;
    // Narrow structural ports adapt only IDs; every read still uses the exact
    // native registry/Agent, with no fabricated inventory or lifecycle.
    const exactAgent = (scope: Agent) => {
      const native = ctx.agents.get(SessionId(scope.session.id));
      if (!native || native !== scope) throw new ObservationError('NATIVE_IDENTITY_STALE');
      return native;
    };
    const ports: NativeFactoryContext = {
      agents: {
        get: id => ctx.agents.get(SessionId(id)),
        create: options => ctx.agents.create({...options,
          sessionId: SessionId(options.sessionId),
          setup: async agentCtx => {
            if (caseName === 'setup-subprocess') {
              const result = spawnSync('/usr/bin/true', [], {encoding: 'utf8'});
              requireDenied((result.error as NodeJS.ErrnoException | undefined)?.code);
            }
            if (caseName === 'setup-write') {
              let code: unknown;
              try {writeFileSync(new URL('../denied-native-setup-canary', import.meta.url), 'public-test');}
              catch (error) {code = (error as NodeJS.ErrnoException).code;}
              requireDenied(code);
            }
            if (caseName === 'setup-network') {
              const code = await new Promise<string>(resolve => {
                const socket = connect({host: '127.0.0.1', port: 9});
                const settle = (value: string) => {socket.destroy(); resolve(value);};
                socket.once('error', error => settle((error as NodeJS.ErrnoException).code ?? 'UNKNOWN'));
                socket.once('connect', () => settle('UNEXPECTED_CONNECTION'));
                socket.setTimeout(1000, () => settle('TIMEOUT_NOT_DENIAL'));
              });
              requireDenied(code);
            }
            await options.setup(agentCtx);
          },
        }),
      },
      tools: {
        schemas: scope => ctx.tools.schemas(exactAgent(scope)),
        get: (name, scope) => ctx.tools.get(name, exactAgent(scope)),
      },
      loader: ctx.loader,
      llm: ctx.llm,
    };
    const factory = nativeFixtureFactory(ports, binding, recipe, install);
    try {
      outcome = await withOwnedFixture(async signal => {
        const fixture = await factory(signal);
        if (caseName === 'implementation-drift') {
          adapter.onResolve = () => {
            fixture.owner.definitions[0]!.definition.execute = async () => 'replaced';
          };
        }
        if (caseName === 'cancel') adapter.onResolve = () => controller.abort();
        if (caseName === 'cleanup-failure') {
          const original = fixture.handle;
          fixture.handle = {agent: original.agent, dispose: async () => {
            await original.dispose();
            throw new Error('CONTROLLED_CLEANUP_FAILURE');
          }};
        }
        if (caseName === 'late-cancel') {
          const original = fixture.handle;
          fixture.handle = {agent: original.agent, dispose: async () => {
            await original.dispose();
            controller.abort();
          }};
        }
        return fixture;
      }, controller.signal);
    } catch (error) { failure = error; }
    nativeAgentAbsent = ctx.agents.get(SessionId(binding.native_session_id)) === undefined;
    nativeSessionAbsent = ctx.sessions.get(SessionId(binding.native_session_id)) === undefined;
  } finally {
    await ctx.fiber.dispose();
    nativeServicesAbsent = ['agents','sessions','llm','tools','systemPrompt','sessionProjections','loader']
      .every(name => ctx.get(name) === undefined);
  }
  const expected = {positive: null, 'ambient-tool': 'TOOL_CENSUS_MISMATCH',
    'implementation-drift': 'TOOL_IMPLEMENTATION_DRIFT', cancel: 'CANCELLED',
    'late-cancel': 'CANCELLED', 'setup-failure': 'SETUP_FAILED_EFFECT_UNRESOLVED',
    'cleanup-failure': 'CLEANUP_UNSETTLED',
    'setup-subprocess': 'SETUP_FAILED_EFFECT_UNRESOLVED',
    'setup-network': 'SETUP_FAILED_EFFECT_UNRESOLVED',
    'setup-write': 'SETUP_FAILED_EFFECT_UNRESOLVED'}[caseName];
  const actual = failure instanceof ObservationError ? failure.code : failure ? 'UNEXPECTED_FAILURE' : null;
  assert.equal(actual, expected, 'actual native outcome differs from the required result');
  assert.equal(adapter.calls, 0, 'native fixture must not generate');
  assert.ok(nativeAgentAbsent, 'owned Agent must be removed from the native registry');
  assert.ok(nativeSessionAbsent, 'owned Session must be removed from the native registry');
  assert.ok(nativeServicesAbsent, 'all mounted services must be drained');
  if (['setup-subprocess','setup-network','setup-write'].includes(caseName)) assert.ok(setupDenial);
  return {scope: 'REAL_PINNED_DSH_CORE_FIXTURE_NOT_PRODUCTION', case: caseName,
    decision: actual ?? 'OBSERVATION_PRODUCED', native_generation_calls: adapter.calls,
    native_agent_absent: nativeAgentAbsent, native_session_absent: nativeSessionAbsent,
    native_services_absent: nativeServicesAbsent, setup_effect_denial: setupDenial,
    observation: outcome?.observation ?? null,
    identity_scope: 'SYNTHETIC_N0_BINDING_NOT_EXECUTIVE_ADMISSION'};
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const caseName = process.argv[2];
  assert.ok(CASES.includes(caseName as CaseName), 'closed fixture case required');
  const recipe = JSON.parse(readFileSync(process.argv[3]!, 'utf8')) as Recipe;
  console.log(canonical(await runMountedFixture(recipe, caseName as CaseName)));
}
