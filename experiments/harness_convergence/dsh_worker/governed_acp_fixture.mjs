/** Provider-free governed 4878 ACP journey. No installed route or provider. */
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync, fstatSync } from 'node:fs'
import { Socket } from 'node:net'
import { createInterface } from 'node:readline'
import { spawnSync } from 'node:child_process'
import { Context } from '@deepseek-ai/cordis'
import LlmRuntime, { LlmAdapter, ToolCallId } from '@deepseek-ai/dsh-llm'
import SessionStore, { SessionLogOffset } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import SessionPersistence, { SessionPersistenceRevision } from '@deepseek-ai/dsh-session-persistence'
import { createGovernedAcpPlugin } from '@deepseek-ai/dsh-acp'
import { ToolRuntime, createDshGrantedToolProfile } from '@mmx/dsh-grant-profile'
import { bindProfileToAgent } from './scoped_profile.mjs'

// The same ephemeral fixture persistence contract as N1; no donor disk/session store.
class EphemeralPersistence extends SessionPersistence {
  rows = /* @__PURE__ */ new Map();
  async create(header, options = {}) {
    options.signal?.throwIfAborted();
    if (this.rows.has(header.id)) throw new Error("N1_SESSION_ALREADY_EXISTS");
    const stored = {
      header: structuredClone(header),
      inheritedEventCount: options.inheritedEventCount ?? SessionLogOffset(0),
      events: [],
      revision: 0,
      writerOpen: true
    };
    this.rows.set(header.id, stored);
    return this.handle(stored, "write");
  }
  async open(id, access, options = {}) {
    options.signal?.throwIfAborted();
    const stored = this.rows.get(id);
    if (stored === void 0) throw new Error("N1_SESSION_NOT_FOUND");
    if (access === "write") throw new Error("N1_RESUME_DISABLED");
    return this.handle(stored, "read");
  }
  async flush() {
  }
  stat(id, options = {}) {
    options.signal?.throwIfAborted();
    const stored = this.rows.get(id);
    return Promise.resolve(stored === void 0 ? void 0 : this.snapshot(stored));
  }
  list(options = {}) {
    options.signal?.throwIfAborted();
    return Promise.resolve([...this.rows.values()].map((row) => this.snapshot(row)));
  }
  snapshot(stored) {
    return {
      header: structuredClone(stored.header),
      revision: SessionPersistenceRevision("n1:" + stored.header.id + ":" + stored.revision),
      eventCount: stored.events.length
    };
  }
  handle(stored, access) {
    let closed = false;
    let floor = 0;
    const ensure = () => {
      if (closed) throw new Error("N1_SESSION_HANDLE_CLOSED");
    };
    const handle = {
      id: stored.header.id,
      header: stored.header,
      inheritedEventCount: stored.inheritedEventCount,
      access,
      async read(offset = 0, length = Number.MAX_SAFE_INTEGER) {
        ensure();
        const start = Math.max(floor, offset);
        const events = stored.events.slice(start, start + length).map((event) => structuredClone(event));
        floor = Math.max(floor, start + events.length);
        return { eventState: "detached", events };
      },
      async append(events) {
        ensure();
        if (access !== "write" || !stored.writerOpen) throw new Error("N1_SESSION_READ_ONLY");
        for (const [index, event] of events.entries()) {
          if (event.seq !== stored.events.length + index) throw new Error("N1_SESSION_NONCONTIGUOUS");
        }
        stored.events.push(...events.map((event) => structuredClone(event)));
        stored.revision += 1;
      },
      async flush() {
        ensure();
        if (access !== "write") throw new Error("N1_SESSION_READ_ONLY");
      },
      async close() {
        if (closed) return;
        closed = true;
        if (access === "write") stored.writerOpen = false;
      },
      async [Symbol.asyncDispose]() {
        await handle.close();
      }
    };
    return handle;
  }
}
const sha = value => createHash('sha256').update(value).digest('hex')
const canonical = value => JSON.stringify(value, (_key, row) => row !== null && typeof row === 'object'
  && !Array.isArray(row) ? Object.fromEntries(Object.keys(row).sort().map(key => [key, row[key]])) : row)
const mode = process.env.MMX_GOVERNED_BEHAVIOR ?? 'ok'
assert.ok(['ok', 'failed-tool', 'revoked', 'schema-mismatch', 'source-mismatch', 'invalid-result', 'hang'].includes(mode))
const input = process.env.MMX_GOVERNED_INPUT
assert.ok(input?.startsWith('/'))
const projectionBytes = readFileSync(input + '/projection.json')
const projection = JSON.parse(projectionBytes)
const config = JSON.parse(readFileSync(input + '/fixture-config.json'))
assert.equal(projection.production_armed, false)
const expectedSource = structuredClone(projection.source)
const admittedTools = projection.tools.map(tool => ({name: 'mcp__granted__' + tool.name,
  contract_sha256: sha(canonical(tool))}))
let state = { allowed: true, ready: false, mountCalls: 0, discovery: false }

// A native owner supplies only this descriptor. Remove its discovery hint before
// creating any subordinate transport; libuv owns its close-on-exec socket handle.
const descriptor = Number(process.env.MMX_ACP_ATTEST_FD)
delete process.env.MMX_ACP_ATTEST_FD
assert.ok(Number.isSafeInteger(descriptor) && descriptor > 2)
const channel = new Socket({ fd: descriptor, readable: true, writable: true })
const privateIdentity = fstatSync(descriptor)
const probe = spawnSync(process.execPath, ['-e', `
 const fs=require('node:fs');try {const s=fs.fstatSync(Number(process.env.FD));
 process.exit(s.dev===Number(process.env.DEV)&&s.ino===Number(process.env.INO)?91:0)}
 catch(e){if(e.code!=='EBADF')throw e}`], {env:{FD:String(descriptor),
 DEV:String(privateIdentity.dev),INO:String(privateIdentity.ino)},stdio:['ignore','pipe','pipe']})
assert.equal(probe.status, 0, 'attestation socket inherited by a descendant')
const lines = createInterface({input: channel})[Symbol.asyncIterator]()
const seed = JSON.parse((await lines.next()).value)
assert.equal(seed.pid, process.pid)
assert.equal(seed.projection_sha256, sha(projectionBytes))
assert.deepEqual(seed.admitted_tools, admittedTools)

function modelResult(options, id) {
  const message = options.messages.findLast(row => row.role === 'tool' && row.toolCallId === id)
  assert.ok(message, 'committed actual tool result missing')
  if (message.isError) return {error: true}
  let result = JSON.parse(message.content.filter(row => row.type === 'text').map(row => row.text).join(''))
  if (result.content) result = JSON.parse(result.content[0].text)
  return result
}

class FixtureAdapter extends LlmAdapter {
  calls = 0
  providerInfo(provider) { assert.equal(provider, 'fixture'); return {id:provider,name:'Fixture'} }
  async listModels(provider) { return provider === 'fixture' ? [{provider,id:'fixture-model',name:'Fixture',inputModalities:['text']}] : [] }
  async resolveModel(provider, model) {
    assert.equal(provider, 'fixture'); assert.equal(model, 'fixture-model')
    return {provider,id:model,name:model,inputModalities:['text'],context:{contextWindow:8192}}
  }
  async *stream(options) {
    assert.ok(state.ready, 'model began before owner readiness ACK')
    assert.equal(options.provider, 'fixture'); assert.equal(options.model, 'fixture-model')
    this.calls++
    process.stderr.write('GOVERNED_MODEL_CALL ' + this.calls + '\n')
    if (this.calls === 2 && mode === 'hang') {
      await new Promise((_resolve,reject) => {
        if(options.signal?.aborted) return reject(new Error('cancelled'))
        options.signal?.addEventListener('abort',()=>reject(new Error('cancelled')),{once:true})
      })
    }
    let name, args
    if (this.calls === 1) {
      name='mcp__granted__read_file';args={file:mode==='failed-tool'?'forbidden.txt':'memo.txt'}
    } else if (this.calls === 2 && mode !== 'failed-tool') {
      const read=modelResult(options,'governed-read')
      assert.equal(typeof read.nonce,'string')
      if(mode==='revoked') state.allowed=false
      name='mcp__granted__search_files';args={query:read.nonce}
    }
    if (name) {
      const id=ToolCallId(this.calls===1?'governed-read':'governed-search')
      const argumentsText=JSON.stringify(args)
      yield {type:'block-start',index:0,blockType:'tool-call'}
      yield {type:'tool-call-delta',index:0,id,name,argumentsDelta:argumentsText}
      yield {type:'block-end',index:0,block:{type:'tool-call',id,name,arguments:argumentsText}}
      yield {type:'usage',usage:{inputTokens:1,outputTokens:1}}
      yield {type:'finish',reason:{kind:'tool-calls'}}
      return
    }
    const read=modelResult(options,'governed-read')
    const search=mode==='failed-tool'?{error:true}:modelResult(options,'governed-search')
    const text=JSON.stringify({answer:mode==='invalid-result'?7:'governed-research',
      read,search,model_calls:this.calls})
    yield {type:'block-start',index:0,blockType:'text'}
    yield {type:'text-delta',index:0,text}
    yield {type:'block-end',index:0,block:{type:'text',text}}
    yield {type:'usage',usage:{inputTokens:1,outputTokens:text.length}}
    yield {type:'finish',reason:{kind:'stop'}}
  }
}

async function main() {
  const ctx = new Context()
  try {
    await ctx.plugin(LlmRuntime)
    await ctx.plugin(SessionStore)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(SystemPrompt)
    await ctx.plugin(ToolRuntime, {strictDispatchBinding:true})
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(EphemeralPersistence)
    await ctx.plugin(AgentLoop, {agents:[]})
    ctx.llm.registerAdapter(['fixture'], new FixtureAdapter())
    const hostMount = async (agentCtx, signal) => {
      assert.equal(++state.mountCalls, 1)
      const fixedProjection=structuredClone(projection)
      if(mode==='source-mismatch') fixedProjection.source.profile_digest='d'.repeat(64)
      if(mode==='schema-mismatch') fixedProjection.tools[0].inputSchema.properties.file.type='number'
      const grantedProfile = createDshGrantedToolProfile({projection:fixedProjection,signal,
        isCurrentBinding(binding, request) {
          const valid=state.allowed && canonical(binding.source)===canonical(expectedSource)
          if(request.phase==='discovery' && valid) state.discovery=true
          return valid
        }})
      await agentCtx.plugin(bindProfileToAgent(grantedProfile, agentCtx), config)
      assert.ok(state.discovery, 'no successful grant discovery witness')
      // Discovery compared every immutable projected schema to the actual MCP
      // catalog. These are admitted contracts, not the complete discovered catalog.
      assert.deepEqual(fixedProjection.tools.map(tool=>({name:'mcp__granted__'+tool.name,
        contract_sha256:sha(canonical(tool))})),seed.admitted_tools)
      channel.write(JSON.stringify({...seed,ready:true})+'\n')
      assert.deepEqual(JSON.parse((await lines.next()).value),{accepted:true})
      state.ready=true
      channel.destroy()
    }
    const plugin=createGovernedAcpPlugin(hostMount)
    await ctx.plugin({name:'governed-fixture',inject:[...plugin.inject],
      apply(inner) {plugin.apply(inner,{provider:'fixture',model:'fixture-model'})}})
    await new Promise((resolve,reject)=>{
      process.stdin.once('end',resolve);process.stdin.once('error',reject);process.stdin.resume()
    })
  } finally {state.allowed=false;channel.destroy();await ctx.fiber.dispose()}
}
main().catch(error=>{process.stderr.write('GOVERNED_FIXTURE_FAILED '+String(error)+'\n');process.exitCode=70})
