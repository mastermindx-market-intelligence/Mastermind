import { defineConfig } from 'vitest/config'
import { createRequire } from 'node:module'
import { resolve, isAbsolute } from 'node:path'
import { pathToFileURL } from 'node:url'
import { execFileSync } from 'node:child_process'

const donor = process.env.DSH_SOURCE
const pin = '687f282e8625c6b8d11ff58211a90524be2e4317'
if (!donor || !isAbsolute(donor)
  || execFileSync('git', ['-C', donor, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim() !== pin
  || execFileSync('git', ['-C', donor, 'status', '--porcelain'], { encoding: 'utf8' }).trim())
  throw new Error('Exact clean adopted DeepSeek source required: ' + pin)
const requireDonor = createRequire(resolve(donor, 'package.json'))
const ts = requireDonor('typescript')
const parsed = ts.readConfigFile(resolve(donor, 'tsconfig.base.json'), ts.sys.readFile)
if (parsed.error) throw new Error('Native TypeScript source map unavailable')
const aliases = Object.entries(parsed.config.compilerOptions.paths)
  .filter(([name]) => !name.includes('*')).map(([name, values]) => ({
    find: new RegExp('^' + RegExp.escape(name) + '$'),
    replacement: resolve(donor, (values as string[])[0]),
  }))
const shared = await import(pathToFileURL(resolve(donor, 'vitest.shared.ts')).href)
export default defineConfig({
  resolve: { alias: [
    { find: 'mmx-native-mock-adapter', replacement: resolve(donor, 'packages/core/agent-loop/tests/mock-adapter.ts') },
    ...aliases,
  ] },
  plugins: [shared.standardDecoratorPlugin()],
  test: {
    environment: 'node', include: ['*.test.ts'], maxWorkers: 1, fileParallelism: false,
    testTimeout: 15000, hookTimeout: 15000, execArgv: shared.vitestExecArgv,
  },
})
