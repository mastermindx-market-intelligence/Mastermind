# DeepSeek native company-job ingress

This package registers `mmx_fabric_worker` in **one actual DeepSeek Agent's
native tool scope**. It submits and observes jobs through the existing
authenticated Subagent Fabric MCP owner. Native conversations remain in the
adopted DeepSeek Session/AgentLoop; Executive, Capacity Fabric and Model Router
keep job, host, account, model, budget and recovery authority.

Programme: [existing ecosystem plan, section 8](../../research/EXECUTIVE_ECOSYSTEM_COMPLETION_PROGRAMME_PLAN_2026-10-17.md),
node **F3.U2**, under [#983](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983).
The current DeepSeek application/ACP/launcher carrier remains
[#2177](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2177).
This package does not edit that active carrier or its release selector.

## Source qualification versus live operation

The adopted upstream source is exactly
`687f282e8625c6b8d11ff58211a90524be2e4317`.
The native tests load its actual Cordis, Tools, AgentRegistry, AgentLoop and
Session implementations. A scripted provider asks the native parent to submit,
retrieve and consume a digest-verified result; the original parent's native
history retains the run and result, and another native Agent cannot access it.
Provider tokens and Fabric replies in that test are deterministic fixtures.

**No installed host enrollment, actual remote worker, provider usage,
production conversation resumption, service deployment, OS display or scale
acceptance is claimed.** A callable source extension is not a production bridge.

## Native installation contract

The incumbent authenticated native application owner calls
`installFabricTool(agent, host)` from the real Agent's setup scope, after Tools
is available. The helper refuses a global/forged scope. Native Cordis effects
own registration and disposal. There is no global fallback or model-supplied
grant in configuration.

```ts
const parent = await ctx.agents.create({
  sessionId: existingNativeSessionId,
  agentOptions: existingNativeOptions,
  setup(_agentCtx, agent) {
    installFabricTool(agent, existingAuthenticatedFabricHost)
  },
})
```

This illustrates the native setup seam, **not permission to create a replacement
Agent/session**. The application must use its original create/resume owner and
enrollment. Do not construct a new lifecycle just to mount the tool.

The trusted host supplies four callbacks:

| Callback | Required incumbent proof |
| --- | --- |
| `authorizeSession(agent)` | Existing authenticated application enrollment binds this exact live native Agent/session to a profile, original company root/parent and current generation. No grant is derived from model arguments. |
| `isCurrent(grant, agent)` | Rechecks the captured scalar grant against current native identity, enrollment and permissions. A rotated generation or revoked capability invalidates it. The adapter copies/freezes the grant and rechecks after asynchronous boundaries. |
| `authorizeNewRun(grant, runId)` | Existing original admission owner durably fences this exact run against previous/uncertain submissions and concurrent claimants before returning exactly true. A merely observed NOT_FOUND, session authentication or in-memory set is insufficient. |
| `callTool(name, args)` | Existing enrolled, authenticated single-owner MCP transport returns the normalized `mastermind.fabric_mcp.v1` payload for the exact requested action. The adapter creates no client, endpoint, credential reader or account fallback. |

The callback interface is an integration boundary, not a new implementation of
those owners. Missing callbacks fail closed. **Do not install with allow-all
test callbacks.** The present installed native application has not supplied the
above complete production composition; it remains an explicit integration gate.
The original admission owner must also reconcile a durable claim acquired just
before native currentness is lost and no request is sent. The enrolled transport
must have its own bounded settlement/deadline behavior; this adapter will not
abandon a pending request with an independent timeout/retry mechanism.

## Tool surface and effects

The closed model schema allows only:

- `submit`: task_key, task_class, task_complexity, work_packet, optional
  escalation_reason (required for C3).
- `status` and `result`: action and the original task_key only.

The model cannot choose root, parent, session, host, credentials, pool, provider
or account. The current route is AUTO under existing admission. A tool request
is not permission for recursive child budgets or another host reservation.

The logical run ID hashes profile + native session + task_key. Native process
generation is deliberately excluded: reconnecting observes the same original
run. Keep the same task_key for the same logical work; never mint another key
to evade an uncertain effect.

Before submission the adapter observes the original run. Existing, unverified,
refused and terminal observations do not resubmit. Even NOT_FOUND requires the
separate original-owner admission fence. Any exception or malformed response
after calling `fabric_request` becomes **EFFECT_UNKNOWN** and exposes the
original identity, with retry_authorized=false. A valid controller receipt
proves only controller creation; it never proves worker START.

Status requires canonical root/parent lineage before authorizing result
transfer. A retained prelaunch refusal can be reported as request correlation
only; it creates no root, dispatch, consumption or replay authority.

Result transfer is bounded to 8192 UTF-8 bytes. It requires matching original
root/run, effective and acceptance run IDs, exact byte count and SHA-256,
terminal lineage before and after transfer, and current native permission
after the final read. The output flag `result_transfer_verified` covers only
that identity/byte-count/digest/lineage/currentness transfer check. It does not
validate worker claims or referenced artifacts, create an atomic result seal,
call fabric_accept or change acceptance.

The tool is exclusive within the native tool scheduler. Cross-process and
cross-session duplicate prevention remains the incumbent original admission
owner's responsibility; there is no adapter-local task ledger.

## Cancellation and lifecycle limit

This is an **externally owned company-job tool**, not a DeepSeek
`SubagentProvider`. The adopted provider contract requires disposal to cancel
remaining child work, await quiescence and release resources. The currently
exposed Fabric MCP contract has request/status/result/accept but no qualified
cancel-and-settled-cleanup operation. The existing ACP worker cancellation
contract operates in the reverse Executive-to-worker direction.

An already interrupted local call performs no owner operation. Once an owner
call has started, this adapter awaits its settlement and observes native
cancellation/currentness before any next call or result release. It does not
abandon a request promise, promise remote cancellation, free a reservation, or
start a background watcher. Native Tools may represent the caller's interrupted
invocation as ABORTED even if Fabric retained the request; recovery uses the
same task_key and original owner. Plugin disposal removes access and withholds
in-flight result content; the independently owned company job remains with
Executive.

A future managed SubagentProvider is held until the existing cancellation owner
exposes and qualifies the exact original run, settled process cleanup,
completed-versus-cancel races and sibling isolation.

## Reproduce the source tests

Use Node 24+ and an authorized **clean** checkout of the exact adopted donor
with its normal installed dependencies. The test config verifies the Git HEAD
and clean status before importing native source. It does not fetch/install an
unqualified donor or change its files.

```sh
export DSH_SOURCE=/absolute/path/to/qualified/deepseek-donor
# Make the donor's existing dependencies available to this package's loader.
ln -s "$DSH_SOURCE/node_modules" node_modules
npm test
```

The symlink is local test setup only and is ignored by Git. Do not overwrite an
existing dependency directory. Tests use one worker and no actual model calls,
network dispatch, remote host workload or production credentials.

The source suite covers exact native scope and parent identity, actual agent
loop/result retention, interruption/recovery, stale grants, original-owner
atomic admission, response loss, malformed receipts, prelaunch refusal,
unverified lineage, result corruption/size/identity, final-attempt changes and
permission revocation. See [EVIDENCE.md](EVIDENCE.md) for executed receipts and
remaining qualification.

## Release and rollback

Source publication follows the existing protected Mastermind delivery path.
No installer or service selector is changed by this package. Future native
composition must occur on the original application's admitted release carrier.

To withdraw the tool, dispose its original native registration/effect through
the owning application. This does not cancel or erase company jobs; reconcile
any original requests and results through Executive before changing enrollment.
A rollback must preserve native session history and unresolved job identities.
