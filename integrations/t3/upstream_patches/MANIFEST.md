# Pinned upstream patch: Mastermind admission adapter

- **Repo (donor):** https://github.com/pingdotgg/t3code
- **Pinned SHA:** `0770446869d247a8b28c27d7ed93f47f8ff0c1e4` (verified: shared clone HEAD, clean tree)
- **Patch file:** `mastermind_admission_0770446.patch`
- **Patch sha256:** `34510fe7bbaecc6ef53d54678b33668b735f7460a50c5949e7e98c6ec3943f6f`
- **Diff stat:** 2 files changed, 727 insertions(+), 6 deletions(-)
  - `apps/server/src/mastermind/MastermindAdmissionAdapter.ts` — new, 698 lines
  - `apps/server/src/orchestration-v2/runtimeLayer.ts` — modified, +29/−6
- **Attribution (also carried in the module docstring):** Mastermind pinned admission patch - donor: github.com/pingdotgg/t3code @0770446869d247a8b28c27d7ed93f47f8ff0c1e4 — adapt existing seams, never rebuild.

## Inert upstream default

With `MASTERMIND_ADMISSION_ENDPOINT` unset (and, separately, the operator-granted root ref comes only from `MASTERMIND_ADMISSION_ROOT_REF`), the adapter's `mode` is `disabled` and every decorator returns the incumbent service unchanged: the patch is a **pure passthrough** and upstream behavior is bit-for-bit identical without Mastermind. Admission decisions (`admitted | blocked_with_reason | passthrough`) are made by a `MastermindAdmissionService` Context.Service reading that env-driven config. Authority is never minted from prompt text, request fields, or any other environment variable: a manual UI launch is admitted as an ordinary interactive root within the existing grant — there is no per-prompt ceremony.

## Files touched by the patch

- `apps/server/src/mastermind/MastermindAdmissionAdapter.ts` (new)
- `apps/server/src/orchestration-v2/runtimeLayer.ts` (modified: 1 import, 6 decorator wraps; zero edits to the six service modules themselves)

## Modified seams

All line numbers refer to the pin `0770446`. **Why each seam needs a pinned patch:** T3 Code's `apps/server/src` exposes no plugin/middleware/extension registry anywhere — the ONLY supported extension mechanism is the Effect-TS `Context.Service`/`Layer` system itself, and these decorators use exactly that system, wrapping each service's incumbent exported `Layer` while leaving the incumbent export and all upstream logic intact.

| # | Upstream seam (file:line at pin) | Decorator | Behavior | Why no supported hook exists |
|---|---|---|---|---|
| a | `orchestration-v2/ThreadLaunchService.ts:169` (service class), `:835` (`launch` Effect.fn), `:843-883` (prep effects: clone-tracker rejection, project resolution, receipt recovery, scratch/worktree allocation), `:1170` (`layer`) | `decorateThreadLaunch` | Validates/admits BEFORE the first preparation effect of the single funnel for ALL thread creation (MCP, UI, CLI), then binds the admitted root/binding onto the launched thread | No admission hook exists; launch is a plain `Effect.fn` consumed end-to-end with no interception point other than decorating the service layer |
| a' | `orchestration-v2/ThreadLaunchService.ts` `retryPreparation` | (same decorator) | Prepared-run release/retry: propagate the existing binding only — never re-decide | Same |
| b | `orchestration-v2/ThreadManagementService.ts:502` (class), `:755-758` (`dispatch` = validate → orchestrator.dispatch), `:1648` (`layer`), `:1660` (`layerWithLegacyImporter`) | `decorateThreadManagementDispatch` | Carries root/binding through messages, delegation, and prepared-run release/retry. Propagation only — dispatch is never re-decided or blocked | No command-interceptor registry; the wrapper is the only vantage point that sees every dispatched command without touching the 13k-line Orchestrator (deliberately NOT patched) |
| c | `orchestration-v2/EffectWorker.ts:66` (`OrchestrationEffectExecutorV2`), `:141-143` (`provider-turn.start`), `:234-242` (`provider-turn.steer`), `:342-381` (`provider-turn.restart`), `:71` (`layerExecutor`) | `decorateOrchestrationEffectExecutor` | Revalidates the current attempt/placement/fence immediately before start/steer/restart effects, with the effect's own error type preserved via `OrchestrationEffectExecutionError.cause`. Stale lease blocks **new execution only** (start, restart-into-replacement) — interrupts/cancels are never decorated, so a stale lease can never interrupt or cancel work. Steer revalidation records but never blocks (steer delivers into an existing turn). Upstream restart lifecycle preserved: restart still interrupts the original turn before starting the replacement | All native effects flow through this executor's `execute` switch; there is no effect middleware seam, so the wrapper layer is the only supported interception point |
| d | `orchestration-v2/ProviderTurnStartService.ts:119` (interface), `:126` (class), `:131` (`layer`), `:338` (`start`) | `decorateProviderTurnStartService` | Revalidates placement+fence immediately before the native turn binding (typed errors preserved via `ProviderTurnStartError.cause`) | No hook between command dispatch and native binding; decorator covers every caller, including the restart path |
| d' | `orchestration-v2/ProviderSessionManager.ts:160-181` (`open` in Shape), `:221` (class), `:329` (`layerWithOptions`), `:2381` (`open` impl; ACP agent process spawn happens at `open`) | `decorateProviderSessionManager` | Revalidates placement+fence immediately before the native process/session binding (typed errors preserved via `ProviderSessionOpenError.cause`) | Process spawn happens directly inside `open` with no seam before it |
| e | `orchestration-v2/ThreadTitleRegenerationService.ts:30` (class), `:110` (`execute`), `:212` (`layer`) | `decorateThreadTitleRegenerationService` | Bounded accounted helper-route record (counts the helper-model call against the admission ledger). Accounting only — no upstream behavior change | Helper-model calls are app-owned, deliberately separate from ACP instances (see `docs/user/providers-acp.md:134-136`); no accounting hook exists |
| — | `orchestration-v2/ThreadPullRequestService.ts:31` (class tag **not** exported), starts from `server.ts:594-595` | none | Verified: at this pin ThreadPullRequestService performs **no helper-model calls** (no TextGeneration import). `generateCommitMessage` is reached only via `provider/Drivers/CodexManagedProvider.ts:277` (provider-native path, already under turn control); `generateBranchName` runs inside the launch funnel (`ThreadLaunchService.ts:338/353/491`), i.e. after seam (a); `generateThreadTitle` is seam (e). Nothing to account, and decoration via Layers is impossible for a non-exported tag — documented rather than papered over | Same mechanism caveat plus non-exported tag |
| f | `orchestration-v2/Orchestrator.ts` (13k+ lines) — **NOT patched** | — | Native child spawns are covered composition-wise by (b) + (c): every delegate/child command is seen at `dispatch` and its provider-turn effects at the executor | Census recommendation: patch the smaller wrappers that already see every dispatched command and native effect, at far smaller blast radius |

### Composition (deviation note)

The delegated plan pointed at `serverRuntimeStartup.ts` as "the layer-assembly point." Verified against the pin: `serverRuntimeStartup.ts` (720 lines) only **consumes** `ThreadManagement`/`ThreadLaunch` services (e.g. `:153`, `:269`) and exports `layerWithOptions = (options) => Layer.effect(ServerRuntimeStartup, make(options))` (`:719-720`) — it composes none of the six service layers. The actual assembly point is `orchestration-v2/runtimeLayer.ts` (imported at `server.ts:201`; `server.ts:567` composes `RuntimeLayer.layerProduction`), where all six `layer*Provided` definitions live. The ONE surgical composition edit therefore landed there: one import line + six two-line wraps (`const layerXxxIncumbent = <incumbent expression unchanged>; const layerXxxProvided = MastermindAdmission.decorateX(layerXxxIncumbent).pipe(Layer.provide(MastermindAdmission.layer));`). Every downstream reference keeps consuming the same `layerXxxProvided` names, so `server.ts` and the rest of the tree are untouched. `orchestration-v2/testkit/ProviderReplayHarness.ts` builds its own layer graph for tests only and is intentionally left undecorated.

## Verification actually run

Shared clone (read-only) at `/Users/chriswong/.hermes/profiles/engineering/mmos/t3code-src`, HEAD verified as the pin:

```
$ git rev-parse HEAD
0770446869d247a8b28c27d7ed93f47f8ff0c1e4
$ git apply --check /tmp/mastermind_admission.patch  # (the committed patch bytes, identical)
(exit code 0 — no output)
```

Round-trip in a private scratch copy of the clone: reverted the edits, `git apply` of the committed patch succeeded (exit 0), reproducing the identical working tree. `tests/test_t3_upstream_patch.py` re-runs `git apply --check` against the pinned clone (skipped if the clone is absent).

## Honest limitations

- **No typecheck/build was run.** The pinned clone is read-only and the vp/pnpm toolchain is unavailable in this environment (no node_modules installed), so `tsc -p apps/server` was not executed. The patch follows the exact Effect-TS 4.1.2 idioms verified against the pinned dependency source (`Context.Service`/`Context.Key`, `Context.get` returning the service shape, `Layer.effect` auto-providing the build scope to `Layer.build`, `Effect.fn`-free plain closures, upstream error classes reused for typed errors: `ThreadLaunchError`, `OrchestrationEffectExecutionError`, `ProviderTurnStartError`, `ProviderSessionOpenError`). Residual risk: TypeScript-level diagnostics under T3's own tsconfig strictness were not machine-verified.
- Admission-block failures surface through each service's existing typed error channel, wrapping `MastermindAdmissionBlockedError` as the cause (the six error channels are closed unions upstream; adding members would have required touching the service modules, which the patch forbids). The `ThreadLaunchError.operation` label for launch admission blocks is approximated as `"resolve-project"` (the first launch operation) since the literals list is closed; the structured cause carries the real admission reason and phase.
- The endpoint wire protocol (`POST {endpoint}/v1/admit`) is the minimal contract implied by the env config; it is implemented with plain `fetch` and an explicit payload parser rather than schema validation to avoid adding new platform dependencies to upstream's layer graph.
