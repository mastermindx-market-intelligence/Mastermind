import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'
const directory = process.env.MMX_DSH_SOURCE === 'pristine' ? 'pristine' : 'donor'
export default defineConfig({
  resolve: {
    alias: [{
      find: /^@deepseek-ai\/dsh-tools$/,
      replacement: fileURLToPath(new URL(`./.cache/${directory}/index.ts`, import.meta.url)),
    }],
  },
  test: {
    include: ['.cache/tests/*.spec.ts'],
    exclude: [],
    maxWorkers: 1,
    fileParallelism: false,
    testTimeout: 10000,
    server: { deps: { inline: [/^@deepseek-ai\//] } },
  },
})
