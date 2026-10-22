import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'
const mode = process.env.MMX_MCP_SOURCE ?? 'donor'
if (!['donor', 'pristine', 'mutant'].includes(mode)) throw new Error('Unknown MCP source')
const root = name => fileURLToPath(new URL(name, import.meta.url))
const source = root(`./.cache/mcp-${mode}/`)
const run = process.env.MMX_MCP_TEST_RUN ?? 'manual'
if (!/^[A-Za-z0-9._-]{1,96}$/.test(run)) throw new Error('Invalid MCP test run identity')
export default defineConfig({
  cacheDir: root(`./.cache/vite-${run}/`),
  resolve: { alias: [
    { find: 'mmx-worker-profile', replacement: process.env.MMX_PROFILE_SOURCE === 'mutant'
      ? root('./.cache/profile-mutant/dsh_tool_profile.mjs')
      : root('../../../integrations/acp_worker/dsh_tool_profile.mjs') },
    { find: 'mmx-mcp-tools', replacement: `${source}tools.ts` },
    { find: 'mmx-mcp-connection', replacement: `${source}connection.ts` },
    { find: 'mmx-mcp-transport', replacement: `${source}transport.ts` },
    { find: /^@deepseek-ai\/dsh-mcp-client\/src\/(.*)$/, replacement: `${source}$1` },
    { find: '@deepseek-ai/dsh-mcp-client', replacement: `${source}index.ts` },
    { find: '../src/connection.ts', replacement: `${source}connection.ts` },
    { find: '../src/transport.ts', replacement: `${source}transport.ts` },
    { find: '../src/index.ts', replacement: `${source}index.ts` },
    { find: '../src/server-context.ts', replacement: `${source}server-context.ts` },
    { find: '@deepseek-ai/dsh-tools', replacement: root('./.cache/donor/index.ts') },
  ] },
  test: {
    include: process.env.MMX_MCP_PROFILE === '1' ? ['profile-startup.test.mjs']
      : process.env.MMX_MCP_STDIO === '1' ? ['mcp-stdio.test.mjs']
      : process.env.MMX_MCP_UPSTREAM === '1'
      ? ['.cache/mcp-tests/{mcp-client,tool-definition,protocol,reconnect,apply,server-context}.spec.ts']
      : ['mcp-admission.test.mjs', 'mcp-context-boundary.test.mjs'],
    fileParallelism: false, maxWorkers: 1, testTimeout: 5000,
  },
})
