import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

const root = fileURLToPath(new URL('.', import.meta.url))
export default defineConfig({
  root,
  resolve: { alias: { '@hermes/plugin-sdk': fileURLToPath(new URL('./tests/sdk-fixture.js', import.meta.url)) } },
  test: { environment: 'jsdom', include: ['tests/*.test.jsx'], testTimeout: 15000, hookTimeout: 30000, env: { NODE_ENV: 'development' } }
})
