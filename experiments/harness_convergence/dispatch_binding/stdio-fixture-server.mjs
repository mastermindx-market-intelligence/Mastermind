// Test-only server: two fixed synthetic files; never a production file service.
import { readFileSync, appendFileSync, lstatSync, realpathSync } from 'node:fs'
import { resolve, isAbsolute } from 'node:path'
import { createHash } from 'node:crypto'
import { z } from 'zod'
import { McpServer } from '@modelcontextprotocol/server'
import { serveStdio } from '@modelcontextprotocol/server/stdio'

const [rootArgument, mode = 'normal'] = process.argv.slice(2)
if (!rootArgument || !isAbsolute(rootArgument)) throw new Error('Fixture root required')
const root = realpathSync(rootArgument)
if (lstatSync(rootArgument).isSymbolicLink()) throw new Error('Fixture root link refused')
if (!['normal', 'lost-reply', 'wait-cancel', 'reject-list'].includes(mode)) throw new Error('Unknown mode')
const marker = JSON.parse(readFileSync(resolve(root, 'fixture.json'), 'utf8'))
if (marker.kind !== 'mmx-synthetic-stdio-test' || typeof marker.nonce !== 'string') throw new Error('Wrong fixture')
const files = ['memo.txt', 'signals.txt']
const log = event => appendFileSync(resolve(root, 'events.jsonl'), JSON.stringify({ ...event,
  pid: process.pid, nonce: marker.nonce }) + '\n')
function read(file) {
  if (!files.includes(file)) throw new Error('Fixture file refused')
  const path = resolve(root, file), stat = lstatSync(path)
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 16384) throw new Error('Fixture file shape refused')
  return readFileSync(path, 'utf8')
}
const reply = value => ({ content: [{ type: 'text', text: JSON.stringify(value) }] })
log({ event: 'start', cwd: process.cwd(), home: process.env.HOME,
  ambient: process.env.MMX_UNAPPROVED_CONFIG ?? null,
  explicit: process.env.MMX_EXPLICIT_CONFIG ?? null,
  nodeOptions: process.env.NODE_OPTIONS ?? null })
const server = new McpServer({ name: 'mmx-stdio-fixture', version: '1' },
  { instructions: 'Synthetic server instructions must not enter a tool-only profile.' })
server.registerTool('read_file', { inputSchema: z.object({ file: z.enum(files) }) }, async ({ file }, context) => {
  const text = read(file); log({ event: 'read', file })
  if (mode === 'lost-reply') { process.exit(23) }
  if (mode === 'wait-cancel') {
    const signal = context.mcpReq.signal
    await new Promise(resolve => {
      if (signal.aborted) resolve()
      else signal.addEventListener('abort', resolve, { once: true })
    })
    log({ event: 'cancelled' })
  }
  return reply({ file, text, sha256: createHash('sha256').update(text).digest('hex'),
    pid: process.pid, nonce: marker.nonce })
})
server.registerTool('search_files', { inputSchema: z.object({ query: z.string().min(1).max(64) }) }, async ({ query }) => {
  log({ event: 'search', query })
  return reply({ matches: files.flatMap(file => read(file).split('\n').flatMap((line, index) =>
    line.includes(query) ? [{ file, line: index + 1, text: line }] : [])), pid: process.pid, nonce: marker.nonce })
})
server.registerTool('write_file', { inputSchema: z.object({}), annotations: { readOnlyHint: true } }, async () => {
  log({ event: 'ungranted-write' }); return reply({ refusedFixture: false })
})
server.registerResource('synthetic', 'fixture://secret', {}, async () => {
  log({ event: 'resource-read' }); return { contents: [{ uri: 'fixture://secret', text: 'synthetic' }] }
})
if (mode === 'reject-list') server.server.setRequestHandler('tools/list', async () => { throw new Error('Fixture discovery refused') })
const handle = serveStdio(() => server)
process.stdin.once('end', () => { void handle.close() })
