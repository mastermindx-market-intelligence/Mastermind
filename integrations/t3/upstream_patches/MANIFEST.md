# Pinned upstream patch: Mastermind admission adapter

- **Repo (donor):** https://github.com/pingdotgg/t3code
- **Pinned SHA:** `0770446869d247a8b28c27d7ed93f47f8ff0c1e4` (verified: shared clone HEAD, clean tree)
- **Patch file:** `mastermind_admission_0770446.patch`
- **Patch sha256:** `999a1b1e9472e47955714235f9478ac7145569d1870436f3df06b5796e771a1f`
- **Diff stat:** 3 files changed, 1528 insertions(+), 6 deletions(-)
  - `apps/server/src/mastermind/MastermindAdmissionAdapter.ts` — new, 810 lines
  - `apps/server/src/mastermind/MastermindAdmissionAdapter.test.ts` — new, 689 lines (colocated vitest suite)
  - `apps/server/src/orchestration-v2/runtimeLayer.ts` — modified, +29/−6
- **Attribution (also carried in the module docstring):** Mastermind pinned admission patch - donor: github.com/pingdotgg/t3code @0770446869d247a8b28c27d7ed93f47f8ff0c1e4 — adapt existing seams, never rebuild.

## Pinned upstream patch: Claude driver live answer-text streaming (lane T1s, 2026-11-10)

Same donor and pin. Makes the Claude driver's `claudeAgent` adapter stream answer text
live (`text_delta`), exactly the way the same source's Codex adapter already does, instead
of emitting each completed content block in one piece.

- **Patch file:** `claude_text_delta_0770446.patch`
- **Patch sha256:** `661566e19617b282ea61c0004f55e51438f034696b50ccda7c82a439f4625400`
  (supersedes `8ca39b00…4d56`, which settled only the FIRST per-block snapshot; see the
  adversarial-review note under Verification)
- **Diff stat:** 2 files changed, 880 insertions(+)
  - `apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts` — modified, +234 (new
    `assistantTextDeltas` coalescer mirroring Codex `agentMessageDeltas`; text arms in the
    `stream_event` branch; snapshot completion correlated by API `message.id`; flush at turn
    finalize; `streamedAnyText` guards on both result-text fallback sites)
  - `apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.test.ts` — modified, +646
    (new `assistant text streaming` suite: 7 tests, upstream testkit/`makeWakeHarness`)
- **Applies cleanly (both tested with `git apply --check`, exit 0):**
  1. on the bare pin `0770446869d247a8b28c27d7ed93f47f8ff0c1e4` (throwaway worktree of a
     private clone; tree clean before/after), and
  2. on the pin with `mastermind_admission_0770446.patch` applied first (the two patches
     touch disjoint files).
- **Mechanism:** one streamed item per API message id (`assistant-text:<message.id>`; every
  text block of the message concatenates into it, matching `textFromClaudeContent`). The SDK
  snapshots each completed block, so ONE message id settles repeatedly with cumulative
  content: every such snapshot completes the SAME item, re-settling only when the
  authoritative text grew (a `streamedItemSettledText` map dedupes unchanged snapshots), and
  a later text block re-opens the item seeded with the settled prefix so live text never
  regresses. No second uuid-keyed item is ever opened for a streamed message (snapshot
  uuids join `emittedNativeItemIds`). Streamed text reserves its ordinal at the first
  delta, so text keeps its place before tool items of the same snapshot (upstream emitted
  tool items first). At turn finalize, never-snapshotted streamed text settles as one
  completed item (interrupt case). Parented (sub-agent) frames never reach the new arms;
  synthetic notices never stream. Downstream is unchanged: running updates flow through the
  existing `makeAssistantStreamingFilter` exactly like Codex's (no new streaming mode).

### Verification actually run (2026-11-10, private clone `~/.mastermind/mmos-dev/t3/src-textdelta` at the pin, patch applied; re-run after the adversarial-review fix)

```
$ git rev-parse HEAD
0770446869d247a8b28c27d7ed93f47f8ff0c1e4
$ cd apps/server && npx -y pnpm@12.14.0 exec effect-tsgo tsrs --noEmit; echo exit=$?
exit=0        # 0 error-level diagnostics (suggestions unchanged from the pin's baseline)
$ node "$(ls -d ../../node_modules/.pnpm/vitest@5.0.5*/node_modules/vitest | head -1)/vitest.mjs" \
    run src/orchestration-v2/Adapters/ClaudeAdapterV2.test.ts -t "assistant text streaming"
# BEFORE patch (red):  Tests  5 failed | 2 passed | 346 skipped   (the 2 are guards that
#                      pass by design pre-patch: parented exclusion, replay/duplicate)
# AFTER patch (green): Tests  7 passed | 346 skipped
$ node ".../vitest.mjs" run src/orchestration-v2/Adapters/ClaudeAdapterV2.test.ts --maxWorkers=4
Test Files  1 passed (1)   Tests  353 passed (353)
$ node ".../vitest.mjs" run <assistantStreaming + ClaudeAutomaticDelivery.integration +
    ThreadFork.execution + ThreadStop + ThreadLaunchService> --maxWorkers=4
Test Files  5 passed (5)   Tests  107 passed (107)
$ node ".../vitest.mjs" run <testkit: ThreadMergeBack, OrchestratorReplayRestartBackgroundNote,
    OrchestratorReplayRecovery, ClaudeReplayFixtures + ThreadFork.execution + ProviderSwitchService>
    --maxWorkers=4
Test Files  6 passed (6)   Tests  65 passed (65)
```

Red/green runs and the full-suite runs are saved in `~/.mastermind/mmos_evidence/t1s-20261110/`
(`tests_red_before_patch.log`, `tests_red_before_patch_v2.log`, `tests_green_after_patch.log`,
`tests_full_suite_patched.log`, `tests_affected_set1_patched.log`, `tests_affected_set2_patched.log`).
What the lane's seven new tests pin: (a) live streaming event of one item during the block; (b)
the snapshot does not emit text a second time and the final text equals the snapshot exactly; (c)
ordinals text → tool use → text; (d) parented sub-agent frames still excluded; (e) an interrupted
turn keeps its partial text with no stuck `streaming` item; (f) replayed history never streams and
duplicate snapshots add no item or announcement; (g) the two adversarial "attack" tests below.

**Adversarial review (kimi-k3.1-pro, read-only, via Fabric):** the reviewer's session ended
mid-run without a final verdict, but its attack hypothesis was confirmed empirically here.
Because the SDK snapshots each completed block, one message id whose content is
`[text, tool_use]` (or `[text, tool_use, text]`) arrives as multiple cumulative snapshots with
distinct uuids. The incumbent uuid-keyed path re-emits the text once per snapshot — on the
unpatched pin the attack sequences produce 2 and 3 text items respectively (pre-existing
upstream duplication). The first patch bytes completed the streamed item on the first
snapshot and then let later snapshots fall through to that same uuid path (2 items, and the
streamed item settled early with only the first block). The current bytes keep one item for
the whole message and re-settle it as the authoritative text grows; the two attack tests
(kept in the suite) pin 1 item with no loss and no stuck streaming. The reviewer's draft
attack file is archived in the evidence directory.


## Rework A3 (2026-11-09) — audit finding #2: no nested `Layer.build`

The distinct Opus audit (`integrations/t3/docs/AUDIT_T3_DURABLE_ADAPTER_OPUS_20261109.md`,
finding #2, BLOCKER) showed the previous bytes (sha256 `f78413fb…caa87`) were NOT a pure
passthrough at composition level: `decorateServiceLayer` ran `Layer.build(incumbent)` inside
the decorator's own `Layer.effect`. In effect 4.1.2 `Layer.build` forks the current memo map
(`CurrentMemoMap.forkOrCreate`), so any dependency first allocated inside that fork is never
written back to the outer graph, and the outer graph built shared singletons a SECOND time —
before the `mode === "disabled"` check could pass anything through.

Fix (this sha): the decorator never builds anything itself. It is
`Layer.effect(tag, gen { admission; inner = yield* tag; disabled ? inner : wrap(inner) })
.pipe(Layer.provide(incumbent))` — the incumbent service is a dependency wired by
`Layer.provide`, which builds it through the SAME memo map as the rest of the graph.
`runtimeLayer.ts` is unchanged (same six `decorateX(incumbent).pipe(Layer.provide(layer))`
wraps). Regression: the colocated suite's `MastermindAdmissionAdapter composition` block
builds `mergeAll(decorated, undecorated)` (both orders, disabled and enforce) over one shared
counting dependency and asserts it is built exactly once and that the disabled decorator
returns the incumbent instance itself. Against the previous bytes the decorated-first cases
FAIL (`expected 2 to be 1`, shared dependency built twice); against these bytes all 4 pass.

Verification of THIS sha (private APFS clone `/tmp/a3-t3-patch` of the scratch tree at the pin;
the shared pinned clone was only read with `git apply --check` and left clean):

```
$ git -C ~/.hermes/profiles/engineering/mmos/t3code-src apply --check mastermind_admission_0770446.patch
(exit 0; clone `git status --porcelain` empty before and after)
$ cd apps/server && npx -y pnpm@12.14.0 exec effect-tsgo tsrs --noEmit; echo exit=$?
exit=0        # 0 errors; 491 suggestions (unchanged; 2 are the patch's TaggedError brands)
$ node <vitest@5.0.5>/vitest.mjs run src/orchestration-v2/ThreadLaunchService.test.ts \
    src/mastermind/MastermindAdmissionAdapter.test.ts
Test Files  2 passed (2)
     Tests  59 passed (59)   # 13 admission (9 prior + 4 composition) + 46 upstream
```

## A6 bounded consult (2026-11-09) — closes A5 live finding #1

A5's live boot (`integrations/t3/live_proof/t3_admission_patch_boot_receipt.json`, scenario B4)
proved the previous bytes (`5785ac95…`) hung `t3_thread_launch` indefinitely when the admission
endpoint accepts but never answers: the consult was a plain `fetch` with no `AbortSignal`.

Fix (this sha `999a1b1e…`, same 3 files, donor pin unchanged):

- **The bound.** Every consult (`launch`, `revalidate`, `steer`) carries
  `signal: AbortSignal.timeout(config.consultTimeoutMs)` — default **10 s**
  (`DEFAULT_ADMISSION_TIMEOUT_MS`), overridable via `MASTERMIND_ADMISSION_TIMEOUT_MS`,
  clamped to `[1 ms, 60 s]` (`MAX_ADMISSION_TIMEOUT_MS` hard ceiling, so no configuration can
  reintroduce the unbounded hang); unparseable values fall back to the default. The knob never
  flips enforcement on by itself.
- **Fail-closed mapping.** A consult that exceeds its bound rejects with the typed
  `MastermindAdmissionTimeoutError` and follows the SAME fail-closed path as an unreachable
  endpoint: launch refused (`ThreadLaunchError.cause`), provider-turn start/restart and
  session-open refused, no thread minted, incumbent never runs. Interrupts are never
  decorated and remain ungated. Steer consults carry the same bound; a timed-out steer consult
  is swallowed (`Effect.ignore`) — steer still never blocks.
- **Typed cause codes.** `mastermindAdmissionCauseCode` maps the three failure shapes to the
  stable labels an MCP surface should emit (A5 finding #2):
  `admission_refused` (`MastermindAdmissionBlockedError`), `admission_timeout`
  (`MastermindAdmissionTimeoutError`), `admission_unreachable`
  (`MastermindAdmissionEndpointError` — its defect distinguishes unreachable vs malformed).
- **Colocated suite grows 13 → 20** (new "bounded consult" block: default/override/ceiling
  config; typed-cause mapping; launch timeout → refused, incumbent never called;
  provider-turn.start timeout → effect fails closed; interrupt during a hung consult → not
  gated, 0 extra consults; steer timeout → proceeds; malformed reply → fail-closed
  `admission_unreachable`, defect distinguishes).

Verification of THIS sha (scratch clone `/tmp/a6-t3` at the pin, patch applied):

```
$ npx -y pnpm@12.14.0 exec effect-tsgo tsrs --noEmit ; echo exit=$?
exit=0        # 0 errors; 492 suggestions (pristine pin: 489 — the patch adds exactly 3,
              # one per Schema.TaggedError class: Blocked, Endpoint, Timeout)
$ node <vitest@5.0.5>/vitest.mjs run src/mastermind/MastermindAdmissionAdapter.test.ts \
    src/orchestration-v2/ThreadLaunchService.test.ts
Test Files  2 passed (2)
     Tests  66 passed (66)   # 20 admission (13 prior + 7 bounded-consult) + 46 upstream
$ git apply --check mastermind_admission_0770446.patch   # clean shared pin clone: OK
```

Live re-proof: `integrations/t3/live_proof/t3_admission_patch_boot_receipt_r2.json` (A0/A1/B2/B3/B4
against a real isolated server; B4 now ends `REFUSED_WITHIN_WINDOW` — see
`LANE_T3_DIRECTOR_A.md` § "A6 bounded consult").

## Inert upstream default

With `MASTERMIND_ADMISSION_ENDPOINT` unset (and, separately, the operator-granted root ref comes only from `MASTERMIND_ADMISSION_ROOT_REF`), the adapter's `mode` is `disabled` and every decorator returns the incumbent service unchanged: the patch is a **pure passthrough** and upstream behavior is bit-for-bit identical without Mastermind. Admission decisions (`admitted | blocked_with_reason | passthrough`) are made by a `MastermindAdmissionService` Context.Service reading that env-driven config. Authority is never minted from prompt text, request fields, or any other environment variable: a manual UI launch is admitted as an ordinary interactive root within the existing grant — there is no per-prompt ceremony.

## Files touched by the patch

- `apps/server/src/mastermind/MastermindAdmissionAdapter.ts` (new)
- `apps/server/src/mastermind/MastermindAdmissionAdapter.test.ts` (new; unit suite proving disabled passthrough, typed blocked-cause surfacing, and the stale-lease fence)
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

Shared clone (read-only) at `/Users/chriswong/.hermes/profiles/engineering/mmos/t3code-src`, HEAD verified as the pin. All commands below ran on 2026-11-09 in a private scratch copy (`/tmp/t3-patch-proof`, `cp -R` of the pinned clone at the same HEAD) with dependencies installed per `package.json`:

```
$ git rev-parse HEAD            # /tmp/t3-patch-proof
0770446869d247a8b28c27d7ed93f47f8ff0c1e4
$ npx -y pnpm@12.14.0 install   # repo pins packageManager pnpm@12.14.0; local pnpm is 9.x
(exit 0)
```

**Typecheck (server)** — upstream's own script, `apps/server` `package.json` `"typecheck": "effect-tsgo tsrs --noEmit"`:

```
$ cd apps/server && npx -y pnpm@12.14.0 exec effect-tsgo tsrs --noEmit; echo exit=$?
exit=0        # 0 errors; 491 effect suggestions
```

Baseline comparison: the UNPATCHED pin typechecks exit 0 with 489 suggestions; the patch adds exactly 2 suggestions (`schemaClassMissingBrand` on the two new `Schema.TaggedError` classes — the same idiom upstream's own error classes use at this pin, e.g. ThreadLaunchService.ts:129). No new errors.

The original patch carried 5 real type errors (`deterministicKeys` Context key; `globalJsonInEffect` on `JSON.stringify` inside an Effect lambda; `optionMatchToFromOption`; `flatMapConditionalToFilterOrFail`; `catchToIgnore`). All five are fixed in the regenerated bytes: deterministic key `t3/mastermind/MastermindAdmissionAdapter/MastermindAdmissionService`; request-body serialization hoisted to plain code before the Effect; `Effect.fromOption` with a typed error mapper; `Effect.filterOrFail` in the launch decorator; `Effect.ignore` for steer recording.

**Unit tests (new colocated suite)** — the repo's `vp` runner is unavailable to external scratch trees, so vitest was invoked from the pnpm store directly:

```
$ cd apps/server
$ node "$(ls -d ../../node_modules/.pnpm/vitest@5.0.5*/node_modules/vitest | head -1)/vitest.mjs" \
    run src/mastermind/MastermindAdmissionAdapter.test.ts
Test Files  1 passed (1)
     Tests  9 passed (9)   # historical (pre-A3 bytes); A3 bytes: 13 passed, see above
```

The suite pins: disabled mode is pure passthrough (decorators return the incumbent service INSTANCE, no fetch consulted); a blocked launch fails `launch` with `ThreadLaunchError` whose cause is `MastermindAdmissionBlockedError` before any preparation effect; an admitted launch proceeds and binds the thread in the ledger; stale lease blocks `provider-turn.start` and `provider-turn.restart` (whole compound effect — the original turn is never interrupted by a stale holder) with the typed cause; `provider-turn.interrupt` is never decorated (admission never even consulted — `fetch` count 0); `provider-turn.steer` records but proceeds. The suite also exposed and drove out a real defect in the earlier patch bytes: the executor/turn-start/session-open decorators double-wrapped the blocked error (`OrchestrationEffectExecutionError{cause: OrchestrationEffectExecutionError{cause: BlockedError}}`); the fixed bytes fail with the raw blocked error and let each `mapError` wrap exactly once.

**Upstream regression check on the patched tree** — the decorated seam's own upstream suite, to prove the default (disabled) path is behaviorally unchanged:

```
$ node ".../vitest.mjs" run src/orchestration-v2/ThreadLaunchService.test.ts
Test Files  1 passed (1)
     Tests  46 passed (46)
```

**Standalone artifact round-trip** — the exact committed bytes were re-applied from a clean pin checkout (working tree reset, untracked files removed), then typecheck and both suites re-ran green: `effect-tsgo tsrs --noEmit` exit 0 with 0 errors; 55/55 tests (9 admission + 46 upstream). `tests/test_t3_upstream_patch.py` re-runs `git apply --check` against the pinned clone (skipped if the clone is absent).

No server was started, no port 3773 bound, and the patched tree was never run as a live desktop app.

## Honest limitations

- Admission-block failures surface through each service's existing typed error channel, wrapping `MastermindAdmissionBlockedError` as the cause exactly once (the six error channels are closed unions upstream; adding members would have required touching the service modules, which the patch forbids). The `ThreadLaunchError.operation` label for launch admission blocks is approximated as `"resolve-project"` (the first launch operation) since the literals list is closed; the structured cause carries the real admission reason and phase.
- The endpoint wire protocol (`POST {endpoint}/v1/admit`) is the minimal contract implied by the env config; it is implemented with plain `fetch` and an explicit payload parser rather than schema validation to avoid adding new platform dependencies to upstream's layer graph. An unreachable endpoint or malformed payload fails closed (blocks new execution only), and since A6 every consult is bounded (`AbortSignal.timeout`, see above) — a hung endpoint can no longer stall the launch funnel. The timeout and unreachable paths are proven both by the fetch doubles and live (r2 receipt scenarios B4/B3); the malformed-payload path is exercised through the fetch double only, not a live endpoint.
- Verification covered `apps/server` typecheck + the colocated admission suite + the upstream ThreadLaunchService suite. The desktop/e2e suites and the full repo-wide vitest run were NOT executed (out of assigned scope; heavy).

## Pinned upstream patch: cross-project delegated child (lane XP, 2026-11-10)

Same donor and pin. Lets a thread in registered project A start a delegated child in
registered project B on the same server with one `delegate_task` call carrying
`target.projectId`, with the child bound to B (own worktree cut from B's remote default
head after a fetch, B's project/instruction context) while the task stays on the parent
(`task_status`/`task_cancel`, completion wake-up, parent-child lineage).

- **Patch file:** `cross_project_child_0770446.patch`
- **Patch sha256:** `a5cfa90eba615daffdad358b4fa5177ca3077a84740084bbd1906be02544101d`
  (panel-repair regeneration 2026-11-11, lane XPb, branch `t3/mmos-v4-xpb`; supersedes
  the feature-round bytes `9038b359c1a3b7f13d23d4cdb13c789e6072ae36754eb835465cc39f36aabbba`)
- **Diff stat:** 10 files changed, 1849 insertions(+), 16 deletions(-) — same 10 files as
  the feature round plus, inside four of them, the four panel repairs and one
  stale-tracking-ref proof test:
  - XPb-5 `Orchestrator.ts:8084-8120,8164-8172` — guard in `dispatchDelegatedTaskRequest`
    (the command body): a `projectId` differing from the parent's requires a worktree
    strategy with `startFromOrigin` and `requireRemoteBase`, re-reads the target project
    (refuses unregistered/archived), and clears `branch`/`worktreePath` on the child
    record; receipt replay never runs the body, so an MCP retry keeps working.
  - XPb-2 `OrchestratorMcpService.ts:2588-2606` — a replayed request id whose child
    belongs to a different project than the request now names is refused
    `invalid_request` ("already used for a task in project X, not Y"), no admission
    against the new project.
  - XPb-3 `OrchestratorMcpService.ts:1338-1339,1372,2466` — driver-kind candidate
    filtering uses the TARGET project for cross-project requests.
  - XPb-4 `OrchestratorMcpService.ts` — unreachable `deletedAt !== null` refusal
    removed; a deleted project reads "was not found" (the lookup hides deleted rows).
  - Steer-2 `ThreadLaunchService.test.ts:1157` — "launches from origin/main with the
    remote's current head past a stale tracking ref": remote advanced from a second
    clone, stale tracking ref asserted first, worktree HEAD must equal the remote's
    current head. Passes unmodified; see the note's "Steer 2" section.
  - `packages/contracts/src/orchestrationV2.ts` — worktree strategy gains optional
    `requireRemoteBase` (refuse rather than fall back to the local branch);
    `delegated_task.request` gains optional `projectId`.
  - `packages/contracts/src/orchestratorMcp.ts` — `OrchestratorMcpTarget.projectId`
    description documents the cross-project case.
  - `apps/server/src/mcp/OrchestratorMcpService.ts` — the whole cross-project admission
    block in `delegate_task`: cross-project requires `isolation: "worktree"`; target must
    be a registered, non-archived, non-deleted project (`requireProject`); the chosen
    provider instance must be enabled in the TARGET project; the remote default branch is
    resolved strictly (new `resolveRemoteDefaultBaseRef`, never guesses, never falls back
    to a local branch) and the worktree strategy is forced to that remote base with
    `requireRemoteBase: true`; dispatch passes the target `projectId` through; retry of an
    accepted delegation with the same `clientRequestId` reuses the recorded task (no
    second child/worktree) and skips the parent-project enablement filter.
  - `apps/server/src/orchestration-v2/ThreadManagementService.ts` — the single dispatch
    chokepoint widens to `command.projectId ?? parent.thread.projectId`.
  - `apps/server/src/orchestration-v2/Orchestrator.ts` — the spawned child thread record
    carries the command's `projectId` when set.
  - `apps/server/src/orchestration-v2/ThreadLaunchService.ts` — `requireRemoteBase` fail
    path: if the fetch could not produce the remote base, the launch fails BEFORE any
    worktree is created (never silently cuts from the local branch).
  - `apps/server/src/mcp/toolkits/orchestrator/tools.ts` — `delegate_task` tool
    description documents `target.projectId`.
  - Tests colocated in the T3 tree's own suites: `CrossProjectDelegation.test.ts` (new,
    +251), `OrchestratorMcpService.test.ts` (+695 incl. 7 new cross-project tests),
    `ThreadLaunchService.test.ts` (+88, 3 new strict-remote-base tests).
- **Applies cleanly (`git apply --check` exit 0, then applied for real exit 0):** on the
  pin `0770446869d247a8b28c27d7ed93f47f8ff0c1e4` with BOTH prior patches
  (`mastermind_admission_0770446.patch`, `claude_text_delta_0770446.patch`) applied first —
  14 modified files afterwards, i.e. these 10 plus the 4 files the earlier patches touch.
  Feature-round receipt: `~/.mastermind/mmos_evidence/xp-20261111/patch_applies_on_pin_plus_two.log`;
  panel-repair regeneration receipt (same method, plus a 10/10 byte-compare of the patched
  files against the live clone):
  `~/.mastermind/mmos_evidence/xpb-20261111/patch_applies_on_pin_plus_two.log`.
- **Runtime-mode clamp:** unchanged from upstream — delegated children already inherit the
  clamped mode; the cross-project path re-checks provider enablement in the target project
  and refuses `ThreadManagementProviderInstanceDisabledError` when the parent's instance
  is disabled there.

### Verification actually run (2026-11-10, SSD clone `/Volumes/Mastermind/build-cache/xp-t3code` at the pin with both prior patches and this patch applied)

Red first (new tests against the unpatched pin; `red_*.log` in the evidence dir):

```
$ node ".../vitest.mjs" run src/orchestration-v2/CrossProjectDelegation.test.ts
      Tests  3 failed | 1 passed (4)      # red_cross_project_delegation.log
$ node ".../vitest.mjs" run src/mcp/OrchestratorMcpService.test.ts
      Tests  10 failed | 59 skipped (69)  # red_mcp_cross_project.log
$ node ".../vitest.mjs" run src/orchestration-v2/ThreadLaunchService.test.ts
      Tests  2 failed | 47 skipped (49)   # red_thread_launch_strict.log
```

Green after the patch (all from `apps/server`, vitest from the pnpm store as above):

```
$ node "$(ls -d ../../node_modules/.pnpm/vitest@5.0.5*/node_modules/vitest | head -1)/vitest.mjs" \
    run src/orchestration-v2/CrossProjectDelegation.test.ts
      Tests  4 passed (4)                 # green_cross_project_delegation.log
$ node ".../vitest.mjs" run src/orchestration-v2/ThreadLaunchService.test.ts
      Tests  49 passed (49)               # green_thread_launch.log
$ node ".../vitest.mjs" run src/orchestration-v2/CrossProjectDelegation.test.ts \
    src/orchestration-v2/ThreadLaunchService.test.ts src/mcp/OrchestratorMcpService.test.ts \
    src/orchestration-v2/DelegatedCompletionDelivery.test.ts \
    src/orchestration-v2/RemoteDelegatedTask.test.ts
      Tests  167 passed (167)             # green_affected_suites.log
$ cd apps/server && npx -y pnpm@12.14.0 exec effect-tsgo tsrs --noEmit; echo exit=$?
$ cd packages/contracts && npx -y pnpm@12.14.0 exec effect-tsgo tsrs --noEmit; echo exit=$?
      # both exit 0 — typecheck_apps_server.log / typecheck_packages_contracts.log
```

The pinned behaviors: cross-project dispatch binds the child to the target project (not
the parent's); non-worktree isolation is refused with one plain sentence; archived,
deleted and unregistered project ids are refused with one plain sentence each; a provider
instance disabled in the target project is refused; runtime mode escalations are clamped
to the parent's; the worktree base is the resolved remote default (strict, no local
fallback) and a failed fetch fails the launch before any worktree exists; retry with the
same `clientRequestId` returns the SAME task/thread without creating a second worktree;
cancel of the parent task interrupts the cross-project child; a child question reaches the
parent thread. A live proof on a throwaway dev server (own home, own port, free probe
agent, two throwaway projects with bare origins where B's local checkout is deliberately
one commit behind its origin) is recorded in
`integrations/mmos/XP_CROSS_PROJECT_CHILD.md` with its receipt JSON.

### Panel-repair verification actually run (2026-11-11, same clone, four repairs applied)

Red first per repair (`red_*.log`, `green_*.log` in `~/.mastermind/mmos_evidence/xpb-20261111/`;
XPb-4 has no red log — the removed branch was unreachable, which is the finding):

```
$ node ".../vitest.mjs" run src/orchestration-v2/CrossProjectDelegation.test.ts
      Tests  2 failed | 4 passed (6)      # red_xpb5_raw_command.log -> green: 6 passed
$ node ".../vitest.mjs" run src/mcp/OrchestratorMcpService.test.ts -t "refuses a retry"
      Tests  2 failed | 69 skipped        # red_xpb2_retry_mismatch.log -> green: 2 passed
$ node ".../vitest.mjs" run src/mcp/OrchestratorMcpService.test.ts -t "driver-kind"
      Tests  1 failed                    # red_xpb3_driver_kind.log -> green: 1 passed
$ node ".../vitest.mjs" run src/mcp/OrchestratorMcpService.test.ts \
    -t "refuses a cross-project task for"   # unknown/archived/deleted table
      Tests  3 passed | 69 skipped (72)  # green_xpb4_deleted_refusal.log (deleted row now
                                        #   asserts "was not found"; re-run with the old
                                        #   branch re-added also 3 passed — it was dead code)
$ node ".../vitest.mjs" run src/orchestration-v2/ThreadLaunchService.test.ts \
    -t "stale tracking ref"              # steer-2 proof, written test-first
      Tests  1 passed                    # green_steer2_stale_tracking_ref.log
$ node ".../vitest.mjs" run <all five suites as above>
      Tests  173 passed (173)            # final_five_suites.log (+ final_mcp_suite.log 72
                                        #   re-run after a mock-typing cast fix)
$ cd apps/server && npx -y pnpm@12.14.0 exec effect-tsgo tsrs --noEmit; echo exit=$?
      # exit 0, zero "error TS"          # typecheck_server.log
$ cd packages/contracts && npx -y pnpm@12.14.0 exec effect-tsgo tsrs --noEmit; echo exit=$?
      # exit 0, zero "error TS"          # typecheck_contracts.log
```
