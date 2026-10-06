import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { Context } from '@deepseek-ai/cordis'
import { createScope } from '@deepseek-ai/dsh-scope'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import { ToolRuntime, createDshGrantedToolProfile } from '@mmx/dsh-grant-profile'
import { bindProfileToAgent } from './scoped_profile.mjs'

test('exact profile scoped preflight: unadapted RED, scoped GREEN, isolated and disposed', async () => {
  const root = process.env.MMX_GOVERNED_INPUT
  const projection = JSON.parse(readFileSync(root + '/projection.json'))
  const config = JSON.parse(readFileSync(root + '/fixture-config.json'))
  const eventsPath=root+'/fixture-input/events.jsonl'
  const eventFloor=readFileSync(eventsPath,'utf8').trim().split('\n').length
  const ctx = new Context(), controller = new AbortController()
  const agent = {}, otherAgent = {}
  let scope, other, mounted, refused
  const calls = [], phases = []
  let allowed = true
  try {
    await ctx.plugin(SystemPrompt)
    await ctx.plugin(ToolRuntime, {strictDispatchBinding:true})
    scope = createScope(ctx, agent); other = createScope(ctx, otherAgent)
    const factory = () => createDshGrantedToolProfile({projection,signal:controller.signal,
      isCurrentBinding(_binding,request) {phases.push(request.phase); return allowed}})
    refused = scope.ctx.plugin(factory(), config)
    await assert.rejects(Promise.resolve(refused), /Loaded DSH dispatch policy failed: positive/)
    await refused.dispose()
    scope.ctx.on('tools/execute', (exec,next) => {calls.push(exec);return next()})
    mounted = scope.ctx.plugin(bindProfileToAgent(factory(),scope.ctx), config)
    await mounted
    assert.ok(phases.includes('discovery'))
    const probes = calls.filter(call=>call.name.startsWith('mmx_dispatch_probe_'))
    assert.equal(probes.length,4) // All incumbent positive/revocation/replacement/result-owner checks ran.
    assert.ok(probes.every(call=>call.agent===agent))
    assert.ok(probes.every(call=>ctx.tools.get(call.name,agent)===undefined))
    const name='mcp__granted__read_file'
    assert.ok(ctx.tools.get(name,agent))
    assert.equal(ctx.tools.get(name,otherAgent),undefined)
    assert.equal(ctx.tools.get(name),undefined)
    assert.equal(ctx.tools.get('mcp__granted__write_file',agent),undefined)
    const result=await ctx.tools.execute({agent,signal:controller.signal,name,callId:'actual-read',
      arguments:{file:'memo.txt'}})
    assert.notEqual(result.isError,true)
    allowed=false
    const denied=await ctx.tools.execute({agent,signal:controller.signal,name,callId:'revoked-read',
      arguments:{file:'memo.txt'}})
    assert.equal(denied.isError,true)
    await mounted.dispose()
    assert.equal(ctx.tools.get(name,agent),undefined)
  } finally {
    controller.abort()
    await mounted?.dispose();await refused?.dispose()
    await other?.dispose();await scope?.dispose();await ctx.fiber.dispose()
  }
  const events=readFileSync(eventsPath,'utf8').trim().split('\n').slice(eventFloor).map(JSON.parse)
  assert.equal(events.filter(row=>row.event==='read').length,1)
  assert.ok(!events.some(row=>['search','ungranted-write','resource-read'].includes(row.event)))
  for (const pid of new Set(events.filter(row=>row.event==='start').map(row=>row.pid))) {
    assert.throws(()=>process.kill(pid,0),error=>error.code==='ESRCH')
  }
})

test('adapter refuses missing/different agent, cross-agent dispatch, and reuse', async () => {
  const ctx=new Context(),agent={},otherAgent={}
  let scope,other
  try {
    await ctx.plugin(SystemPrompt);await ctx.plugin(ToolRuntime,{strictDispatchBinding:true})
    scope=createScope(ctx,agent);other=createScope(ctx,otherAgent)
    const profile={name:'facade-contract',inject:['tools'],async apply(inner) {
      assert.throws(()=>inner.tools.execute(null),/INPUT_REQUIRED/)
      assert.throws(()=>inner.tools.execute({agent:otherAgent}),/CROSS_AGENT/)
    }}
    assert.throws(()=>bindProfileToAgent(profile,ctx),/SCOPE_REQUIRED/)
    const mismatch=other.ctx.plugin(bindProfileToAgent(profile,scope.ctx))
    await assert.rejects(Promise.resolve(mismatch),/SCOPE_CHANGED_OR_REUSED/)
    await mismatch.dispose()
    const bound=bindProfileToAgent(profile,scope.ctx)
    const first=scope.ctx.plugin(bound)
    await first;await first.dispose()
    const second=scope.ctx.plugin(bound)
    await assert.rejects(Promise.resolve(second),/SCOPE_CHANGED_OR_REUSED/)
    await second.dispose()
  } finally {await other?.dispose();await scope?.dispose();await ctx.fiber.dispose()}
})
