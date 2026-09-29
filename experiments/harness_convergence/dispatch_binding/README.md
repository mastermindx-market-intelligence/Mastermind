# DSH exact-dispatch binding: executable foundation support

Operation: `deepseek-os-foundation-support-20260929-sol-001`.
Parent: Mastermind #600 / #1037, `WS:EXECUTIVE-CAPACITY-FABRIC`.
Status: **TESTED PATCH CANDIDATE / NOT INSTALLED / MISSION_COMPLETE:false**.

This implements the dispatch counterexample and MCP admission seam from
[`2026-09-27-builder-support-r2.md`](../../../research/harness_reuse/2026-09-27-builder-support-r2.md).
It does not replace the existing ACP worker, take #825's source custody, or add
DSH to the native Mastermind OS release's critical path.

## What actually changed

Before: an approved tool could be replaced or revoked while a supported async
wrapper/scheduler awaited; the later body still ran. A completed body's value
could also be converted using a replacement definition's output contract.

After: the optional `strictDispatchBinding` policy in the **existing donor
ToolRuntime** binds the definition before policy, rechecks live guards just
before dispatch, and refuses a changed definition before invoking a body.
Once a body has started, result conversion stays with that original definition;
registry movement does not erase an effect or authorize replay. Existing caller
cancellation and draining remain intact. Default behavior is unchanged.

The patch changes one upstream source file; it adds no second tool registry,
MCP proxy, scheduler, process owner, provider route, memory store or retry engine.
The per-call WeakMap is subordinate execution state in the existing owner.

## Exact scope and proof

Donor source: `deepseek-ai/deepseek-harness@4878cdabd87d4041bdaff61d04c966883b9fd07a`.
Core blob: `ca89f370febac1fa24f84cc25351a186866fe7e7`, unchanged from R2's
`21638c56315ae6a2b552d6091945d3144c9af32e` core source.
The published `@deepseek-ai/dsh-tools@0.2.0-rc.1` is independently tested;
its package name/version is not asserted to prove whole-artifact equivalence.
All source and npm dependency identities are pinned in `donor-manifest.json`
and `package-lock.json`. The original #825 donor pin remains different.

| Verification | Observed outcome |
| --- | --- |
| Published package, 19 targeted cases | 10 pass; exact 9 expected failures |
| Unmodified pinned TypeScript, same cases | Same 10 pass / 9 failures |
| Patched TypeScript, strict and legacy cases | **19 / 19 pass** |
| Four unmodified upstream test files | **178 / 178 pass**, before and after |
| Strict TypeScript check of patched core | Pass |
| Three independent forbidden mutations | All killed by their exact expected cases |

The first ten-case reproduction had four failures; the expanded nineteen-case
suite covers additional queue, own-scope, name-only-guard and result-removal
variants. Nine failing cases are not a claim of nine independent vulnerabilities.

## Reproduce without a provider or installed DSH application

Tested on macOS arm64, Node 26.8.2. Python 3, npm and `patch` are setup tools.
This package uses real Cordis and ToolRuntime; only the leaf tools are inert.
It downloads no native Codex/Claude product, starts no DSH service, and makes
no model/provider requests. Setup needs public source/npm access; verification
itself is offline and runs children with an allowlisted, credential-free environment.

```sh
cd experiments/harness_convergence/dispatch_binding
python3 prepare.py --download
# This is a test-local install, with no lifecycle scripts or ambient npm settings.
env -i PATH="$PATH" HOME="$PWD/.cache/home" \
  NPM_CONFIG_USERCONFIG="$PWD/.cache/empty-user.npmrc" \
  NPM_CONFIG_GLOBALCONFIG="$PWD/.cache/empty-global.npmrc" \
  NPM_CONFIG_CACHE="$PWD/.cache/npm-cache" \
  NPM_CONFIG_REGISTRY=https://registry.npmjs.org/ \
  npm ci --ignore-scripts --legacy-peer-deps --no-audit --no-fund
python3 verify.py
```

The patch is a zero-context unified diff; manual Git application requires
`--unidiff-zero` and the same exact preimage check. The supplied setup handles it.
`prepare.py` verifies every source's SHA-256 and Git blob identity, applies
only the exact pinned patch, and refuses unexpected cache bytes rather than
overwriting them. Without `--download` it never fetches missing inputs.
`verify.py` requires the **exact** baseline failure set, complete passing repair,
unchanged upstream regression counts, type-check and three discriminating
mutation kills. A missing import, skipped test, or unrelated crash is not RED proof.
Raw local logs stay ignored; `verification-receipt.json` retains the measured
summary, input identities and selected tool traces. This is not the full DSH
suite, OS sandbox qualification, a remote-exploit finding or a provider canary.

## Integration instructions for the existing builders

1. Keep native Codex/Claude, #1046 app, Runtime/hierarchy and #1056 Pro-led
   delivery moving independently. This support package changes none of them.
2. Preserve #825's exact-writer hold and provider-free proof. Recover/integrate
   that predecessor through its current owner, not by copying it into this PR.
3. When selecting the useful DSH profile, review and apply this patch to the
   chosen immutable artifact, with `strictDispatchBinding: true` required.
   **A config row alone is not proof:** stock DSH ignores this unknown option
   and still exhibits the failures. Attest the actual patched artifact/profile.
4. The Mastermind guard must bind real server/tool/schema/connection generation,
   use repeatable synchronous checks, and cover own-scope tools. Definition
   objects must be immutable in the reviewed closure; this patch is not a
   sandbox against arbitrary plugin code or in-place object mutation.
5. Then qualify the remaining existing R3 seams: pre-prompt process/profile
   attestation, real granted read/search tools, MCP generation admission and
   instruction/resource controls, host confinement, eligible provider accounting,
   and an actual result consumed by the original Executive parent.

This narrows the unexecuted R2 M05/M07 assumption to measured source behavior
and supplies its repair. It does **not** mark the original 53-case R3 matrix
passed, prove full MCP/server authorization, alter the current launch capability
registry, or transfer #825's old proof to a new donor release. Adoption,
installation and useful end-to-end acceptance remain with the incumbent owners.

## Executable loaded-runtime preflight (continuation)

`qualify-loaded-runtime.mjs` closes the config-only false-green gap without
changing the donor patch or inventing another ACP adapter. The incumbent fixed
profile bootstrap can call it on its **actual, already-created ToolRuntime**:

```js
import { qualifyLoadedDispatchRuntime } from './qualify-loaded-runtime.mjs'
const dispatchEvidence = await qualifyLoadedDispatchRuntime(ctx, {
  signal: ownerAbortSignal,
})
```

This must occur in the host-owned exclusive, provider-free pre-prompt phase,
before any model session/workload is exposed. It is not safe to inject probes
into a running admitted worker. The supplied context's middleware must itself
be reviewed/provider-free for this phase; the helper makes no direct provider
call but is not a sandbox around arbitrary plugin callbacks. Existing guards
are never disabled: if they prevent the positive probe, preflight refuses.

The helper executes four temporary **in-memory** probes: permitted call,
revocation while awaiting a wrapper, same-name definition replacement, and
original-result ownership after a body starts. It disposes its exact tools,
guards and wrappers on success or failure. All errors, cancellation, or cleanup
uncertainty block further startup; they are not replay/alternate-provider
permission. A caller deadline does not prove cleanup: the existing process
owner must reconcile a pipeline that has not settled.

The frozen return is behavioral evidence only. Bind it to the existing exact
artifact/profile/process generation and final tool census before the existing
owner admits work. It is not source authentication, a cached admission grant,
a replacement tool registry, or proof of MCP server/schema/generation rights.
Do not claim it is installed or called by #825 merely because the helper exists.

Seventeen new real-runtime tests cover stock/ignored config, default/explicit
legacy mode, each independently broken guard/definition/result patch, deny-all
false positives, cancellation, middleware failure, repeated probes, and
preservation of unrelated tools, pipeline draining and cleanup failure.
`verify.py` runs these alongside the unchanged
19 race cases, 178 upstream regressions and original three mutation falsifiers.
The new helper's initial absent implementation produced 12 failing tests;
behavioral enforcement proof comes from the actual stock/disabled/defect cases,
not from that missing-module failure.

## MCP tool-generation admission (Task 3 source continuation)

`mcp-generation-admission.patch` extends the existing donor MCP client, not a new
proxy or capability registry. It adds a trusted synchronous admission callback to
`syncTools` and threads it through the existing `startConnection` synchronization
and reconnect owner. No host callback is accepted from a model argument or YAML.
The unconfigured plugin retains its original behavior; installing bytes alone is
not proof that the host selected or invoked the admitted path.

The incumbent immutable profile can use the exported factory:

```js
const connection = startConnection(ctx, fixedConfig, reconnectPolicy, admitGeneration)
const readiness = await connection.ready
// The existing factory owns startup failure and awaits connection.dispose() on close.
```

The callback receives a detached, deeply frozen snapshot containing the actual
server's reported name/version, the local server namespace, and every discovered
raw tool with its full input/output schemas and annotations. It returns an array
of `{ rawName, allow(execution) }` entries. The raw names must be unique members of
the discovered generation; displayed names are never parsed into wire identities.
Each `allow` is synchronous, repeatable, and must return literal `true`. Promise
or truthy-object returns never authorize dispatch.

The host must compare that snapshot with its already-admitted exact endpoint,
transport, authentication realm, capability/profile and full-schema bindings.
A server's self-reported identity and `readOnlyHint` are not permission. The
callback is an integration seam for the existing owner, not a new policy store.
Empty selection is permitted but does not prove any required capability exists.

An admitted old generation is retired before refreshed discovery can await or
fail. Permission/current-connection checks run again immediately before the
actual SDK `callTool`; old retained definitions cannot reuse a retired binding.
A call already sent is drained and its original result retained; revocation
never becomes evidence that the remote effect did not happen or can be replayed.
Existing connection serialization and disposal retain ownership throughout.

Verification uses the real MCP 2.0 Client/Server and linked in-memory transport,
with the actual donor bridge and patched ToolRuntime. The permitted server call
returns a new nonce; the ungranted tool advertises a misleading read-only hint
but is neither exposed nor invoked. Actual SDK notifications exercise the
connection's re-admission path. This is protocol/source proof, not a production
repository service, model inference, ACP-worker or original-Executive-parent proof.

Observed: **32/32 MCP cases pass**, versus **3 pass / 29 expected failures** on
unchanged MCP source. All **93 unchanged selected upstream MCP cases pass** on
both versions. Four independently broken filtering/dispatch/connection/context variants
are detected by their exact expected cases. Six source-preparation checks pass:
exact/repeated patching, source/patch/output drift refusal, no implicit download,
and source-symlink refusal. Strict MCP TypeScript uses ES2024 for the donor's
existing `Promise.withResolvers`; no donor workaround or skipped check is used.

To prepare the additional exact public inputs, run `python3 prepare_mcp.py --download`
after the core preparation. Then install only this directory's locked test
packages with the private npm settings above. `npm test` now runs both verifiers;
`python3 verify_mcp.py` runs just the MCP suite offline after preparation.
`mcp-manifest.json` pins every input and all four patched-file digests. The
MCP patch is zero-context (manual Git application needs --unidiff-zero); the
preparer verifies exact preimages/postimages and refuses changed inputs/outputs
instead of overwriting them. `mcp-verification-receipt.json` contains the measured
suite results and actual nonce/notification observations.

The endpoint/authentication/profile admission callback still belongs to the
incumbent integration owner. The admitted connection is explicitly **tool-only**:
`instructions()` returns no server text, and resources/list, templates/list and
resources/read refuse before sending an SDK request. This remains true even if
a caller registers the returned connection with the existing context consumer.
Default legacy connections retain their original instructions/resources behavior.
A future resource/instruction capability needs its own reviewed admission; the
tool callback does not authorize it. Seven real-protocol context tests distinguish
these boundaries. The first tool-only candidate produced five expected failures
in those seven cases before the two channel checks were added. No tool permission
was widened and no new policy store was introduced. This patch does not call
`registerServerContext` or grant additional channels. Actual immutable
artifact packaging, host confinement, eligible-provider accounting, #825 source
recovery, startup in the owned ACP process, and useful parent-consumed work are
not proven by these test results. No default route or production profile changed.

Independent review remains outstanding. The attempted review-task preparation
was platform-blocked and was not retried or routed elsewhere. This source is an
unreviewed integration candidate, not a release or installed acceptance.

## Actual stdio child and startup environment

`mcp-stdio.test.mjs` now composes the patched ToolRuntime and loaded-runtime
preflight with the real `startConnection` and `createTransport`. No transport
mock or `InMemoryTransport` is used in this group. The SDK launches the fixed
`stdio-fixture-server.mjs` in a unique synthetic test directory. Its only file
inputs are two small named fixture files; it is not a production filesystem
service. A real read and literal search return the fresh disk nonce, content
hash and line matches. The ungranted write tool never executes; the two input
files remain unchanged. Cancellation, discovery failure and a lost reply are
also exercised through actual process/stdio boundaries.

These tests exposed a startup gap: the admitted path still inherited the
full scrubbed parent environment, including harmless test values for an
unapproved configuration variable and `NODE_OPTIONS`. The smallest repair
threads the existing tool-only host decision into `createTransport`:
admitted stdio uses explicit `config.env`, not `scrubbedParentEnv()`.
Legacy/default behavior is unchanged, and HTTP transport is not changed.
The SDK still adds its own platform bootstrap allowlist; this is NOT an empty
environment or an OS sandbox. The immutable host profile must explicitly pin
HOME, PATH, cwd, executable and any required approved proxy/startup settings.
A tool/model cannot supply this trusted factory argument.

**Process-accounting finding:** MCP Client 2.0 auto negotiation starts a
short-lived disposable sibling before starting the actual session process.
The official SDK owns and reaps the probe. Do not mistake it for replay, but
do not omit it from process evidence either. The pinned test observes two
distinct PIDs, proves the probe absent before useful readiness, attributes the
read to the session PID, and proves both absent after disposal. A lost reply
performs exactly one read and creates no process beyond the startup census.
Startup must therefore be side-effect-free for both the probe and session;
this is not proof of every possible descendant or installed worker confinement.

Observed before environment repair: **10 PASS / 2 expected failures** in the
12-case real-stdio group. After repair: **12/12 PASS**, including useful read/
search, denied tools/context, private configured home/cwd, revoked grants,
in-flight cancellation, startup failure, lost reply, probe and session cleanup,
and unchanged legacy behavior. A separate environment-wiring mutation must
reproduce exactly the two failures. The original initial test incorrectly
expected one process; SDK source inspection corrected that assertion before
RED was frozen. No duplicate tool request was observed in that initial run.

The full `npm test` includes this group and its mutation. Raw fixture logs and
source/result evidence remain in the ignored cache; the verification receipt
retains the exact measured scope and hashes. No new model/provider, ACP adapter,
credential, production service, dependency installation, source-custody transfer
or Executive Job is part of this continuation. These real MCP subprocess tests
still do not prove an installed DSH ACP worker or original-parent consumption.

## License

The donor patches and fetched test references derive from DeepSeek's MIT
source; `UPSTREAM_LICENSE` retains that notice. Donor sources and third-party
packages stay in ignored caches/node_modules. This work grants no rights to
optional proprietary products, and none were installed by this experiment.
