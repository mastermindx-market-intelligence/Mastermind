# DSH exact-dispatch binding: executable foundation support

Operation: `deepseek-os-foundation-support-20260929-sol-001`.
Parent: Mastermind #600 / #1037, `WS:EXECUTIVE-CAPACITY-FABRIC`.
Status: **TESTED PATCH CANDIDATE / NOT INSTALLED / MISSION_COMPLETE:false**.

This implements the previously unexecuted counterexample in
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

## License

The one-file donor patch and fetched test references derive from DeepSeek's MIT
source; `UPSTREAM_LICENSE` retains that notice. Donor sources and third-party
packages stay in ignored caches/node_modules. This work grants no rights to
optional proprietary products, and none were installed by this experiment.
