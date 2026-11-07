/** Test-only cold-process recovery through the unchanged native JSONL owner. */
import assert from 'node:assert/strict'
import { realpath } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createInterface } from 'node:readline'
import { Context } from '@deepseek-ai/cordis'
import { SessionId } from '@deepseek-ai/dsh-session'
import { expandAssistantStream } from '@deepseek-ai/dsh-llm'
import { SessionAlreadyOwnedError } from '@deepseek-ai/dsh-session-persistence'
import * as JsonlPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'

const [root, rawId, mode] = process.argv.slice(2)
assert.equal(process.argv.length, 5)
assert.equal(await realpath(root), resolve(root))
assert.ok(rawId && ['read', 'hold', 'probe', 'acquire'].includes(mode))
const id = SessionId(rawId)
const ctx = new Context()
let handle
try {
  await ctx.plugin(JsonlPersistence, { root })
  try {
    handle = await ctx.sessionPersistence.open(id, mode === 'read' ? 'read' : 'write')
  } catch (error) {
    if (mode !== 'probe' || !(error instanceof SessionAlreadyOwnedError)) throw error
    console.log(JSON.stringify({ state: 'ACTIVE_WRITER_REFUSED', session_id: id }))
  }
  if (handle) {
    if (mode === 'hold') {
      console.log(JSON.stringify({ state: 'WRITE_HELD', session_id: id }))
      const input = createInterface({ input: process.stdin })
      let released = false
      try {
        for await (const line of input) {
          assert.equal(line, 'release')
          released = true
          break
        }
        assert.equal(released, true, 'fixture holder lost its original release request')
      } finally {
        input.close()
      }
      await handle.close()
      handle = undefined
      console.log(JSON.stringify({ state: 'WRITE_RELEASED', session_id: id }))
    } else {
      const { events } = await handle.read()
      console.log(JSON.stringify({
        state: mode === 'read' ? 'READ_RECOVERED' : 'WRITE_ACQUIRED',
        session_id: id, header: handle.header, events,
        streams: events.filter(event => event.type === 'assistant/message')
          .map(event => ({seq: event.seq, chunks: expandAssistantStream(event.data.stream)})),
      }))
    }
  }
} finally {
  await handle?.close()
  await ctx.fiber.dispose()
}
