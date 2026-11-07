# Selective Harness Reuse Implementation Plan

**Revision R3 — 2026-09-28.** Reuse the existing ACP worker and #825 predecessor; do not create another DSH Worker adapter. This corrects the R1 omission of existing implementation. The original 53 acceptance IDs remain requirements, not proof that tests ran. Source acceptance, installation, provider eligibility and useful parent-consumed results remain separate.

**Current procedure/source:** Mastermind `dcc4829a811d3f6e4fe8c16a103f813c3501f48e`, Skillpack 1.0.1/bootstrap1. **Operation:** `deepseek-harness-mastermind-integration-20260927-sol-001`. **Existing source parent:** #687; company integration #600. **Spec:** `docs/superpowers/specs/2026-09-27-selective-harness-reuse.md`.

## Reuse inventory and source custody

- #825 at `838d70b3625ae61476336615ef4c9b841a208297` already adds provider-scoped ACP model selection, cancellation-time frame admission, the real DSH fixture, native tests and its runbook. Use `integrations/acp_worker/adapter.py`, `turn.py`, the existing `AcpNativeProcessOwner`, `experiments/harness_convergence/dsh_worker/acp_fixture.ts` and `tests/harness_convergence/test_dsh_acp_worker.py`.
- The #825 author reports 109 focused cases and 13 Python ACP SDK conformance cases; a later source approval/hold is recorded. These are attributable historical receipts, not this session's rerun or production proof. Current #825 is unmerged and its source-custody recovery must remain on its own carrier. A missing/refused local binding does not authorize a replacement workspace or copied implementation.
- Default-branch ACP already owns native resources, prompt/session framing, common WorkerResult/CollectionReceipt, bounded cancellation and cleanup. Its result check rejects complete changed paths independently of tracked status. Reuse this implementation, not only its abstract interface.
- Donor pins differ: #825 native proof used `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`; R1/R2 source research inspected `21638c56315ae6a2b552d6091945d3144c9af32e`. Keep evidence bound to its actual pin. Choose one qualified closure before changing runtime bytes; do not treat the later commit as an automatic upgrade.
- Not commissioned: `control_plane/dsh_worker.py`, `DshWorkerAdapter`, a second process/cancellation/result implementation, global Node migration, native adapter/auth rewrite, provider/account store, new MCP proxy, queue, lifecycle, memory plane or reviewer.

## Task 1 — Recover the predecessor and lock the chosen profile [H01–H08]

**Existing owners/files:** #825's six-file scope and supply runbook; existing immutable package/capability owners. Do not copy #825 source into #1037 or recreate its completed process proof.

1. Reconcile the exact #825 remote head, approved semantic evidence, current source-writer binding and material protected-source changes through the existing custody owner. Its later documented hold is writer continuity, not an unanswered review request. Current Chairman review direction does not waive source custody or required checks.
2. Keep the old valid proof where inputs are unchanged. Inspect the retained supply manifest/artifact identities through authorized access; cache-path existence is not artifact verification. Changed inputs invalidate only affected evidence.
3. Bind exact Node, DSH package/lock, ACP dependencies, profile and ordered patches. Use explicit private runtime home/startup directory and a positively allowlisted environment, separate from the agent workspace. Prove project/home configuration cannot alter routing or expose unexpected tools.
4. H01–H08 still cover artifact/config/include drift, optional-bundle omissions and incorrect compatibility claims. There is no model request, credential ceremony or shared-host package installation merely to enumerate readiness.

## Task 2 — Extend the real ACP path to a useful credential-free task [P01–P06]

**Existing fixture/turn owners:** #825 DSH fixture and ACP turn. Initial tool capability is a proposed separate profile, not a change that silently makes #825's intentionally rejected tool case pass.

1. Reuse request-correlated ACP prompt completion and cancellation; do not substitute high-level SDK enqueue/whole-agent-idle behavior or build another SDK runner.
2. Before enabling tools, bind actual process/Agent/session/model/profile identity at the existing pre-prompt seam. Then admit only lifecycle-correlated evidence for two bounded repository read/search operations under the exact approved workspace.
3. The deterministic provider-free journey must perform a real approved tool call, obtain a fresh source nonce from that call, and return a schema-valid useful result through the existing ACP collection path. Correct prose without observed tool use fails.
4. P01–P06 require missing capability, extra input producer, wrong session/model, malformed/oversized frames and fake readiness to fail. Keep source provenance and settled owned-process evidence. No real provider or production readiness is inferred.

## Task 3 — Integrate MCP generation and actual dispatch admission [M01–M12]

**Scope:** only when MCP enters the chosen useful profile, use the existing donor client `ToolBridgeOptions`/`syncTools`, `registerServerContext`, and core dispatch pipeline. No parallel discovery service or registry.

1. Reconcile these seams against the selected donor pin before applying the R1/R2 patch proposal. Bind configured server, raw tool identity, full schema and connection generation; filter discovery and revalidate at actual execution.
2. Preserve the R2 counterexample: an asynchronous executor can separate approval from final callable lookup. A name-only guard must not bless a replacement body or revoked binding. Use the already supplied four-case fixture as proposed coverage, not as executed proof.
3. Gate instructions/resources independently of tool discovery. Refusal must make an unprovable old generation non-executable. Retain cancellation/dispatch/result provenance; reconnect must not replay a potentially completed call.
4. M01–M12 retain added/changed/duplicate tools, schema drift, stale generations, direct/own-scope bypass, replacement, resource/instruction changes and false read-only annotations. Include permitted-tool positives; denying everything is not success.

## Task 4 — Complete the existing native-owner qualification [W01–W07]

**Reuse:** `AcpNativeProcessOwner`, `AcpWorkerAdapter`, current `WorkerExecutionAdapter`/`WorkerProcessRef` contracts, inspector and host isolation. Do not introduce `DshWorkerAdapter` or a second recoverable process API.

1. Add only missing exact artifact/profile attestation and host confinement to the qualified native factory. Preserve spec/workspace/base/UID checks, one active run, run-id reuse refusal, finite deadlines and cleanup reserve.
2. W01–W07 qualify wrong binary/profile/workspace/principal, PID reuse, initialization failure, surviving descendants and interruption/recovery against that actual owner. A frame-level cancellation acknowledgment does not prove settled processes or no remote tool effect.
3. Reuse #825's cancellation-frame correction rather than reimplementing it. Recovery never resends a prompt; unsupported resume/validation capabilities remain explicitly unavailable. READ/RESEARCH does not permit write or test execution.

## Task 5 — Use the current result/parent contract [R01–R09]

**Reuse:** `AcpReadOnlyTurn`, `AcpWorkerAdapter._collection`, `WorkerResult`, `CollectionReceipt` and existing Executive parent-result projection. No DSH-specific result translator, transcript DB or result API.

1. Existing collection checks already bind job/run/worker/model/session, prompt stop reason, output schema, clean workspace and native settlement. Add required tool-result attribution and appropriate bounded artifacts only through their existing owners.
2. R01–R09 preserve malformed/foreign/duplicate/oversized output, cancellation races and uncertain external effects. Ordinary errors or process exit never authorize retry. Preserve actual usage and exact result/artifact hashes.
3. Parent acceptance must resolve the full canonical result/artifact, not an `executive_job` MCP bounded preview. Qualify an oversized result with a required tail sentinel: projection may be bounded while original-parent consumption preserves and validates the full result.
4. The current ACP collector already checks complete changed paths. Preserve that invariant when #1042's tracked-only status optimization is composed; a declared artifact name cannot replace WRITE_BRANCH authority.

## Task 6 — Bind eligible provider, budget and accounting [E01–E07]

**Reuse:** existing provider profile/binding, Model Router, Capacity, credential owner and WorkerResult.usage. First use a counting loopback provider in the useful fixture; real provider access requires its own current positive admission.

1. E01–E07 require explicit endpoint/credential mechanism, no ambient login discovery, no hidden retry/redirect/fallback, honest requested-versus-served identity and exactly attributed whole-Attempt usage. Do not confuse output-token cap with total budget.
2. Keep #825's private ACP `[provider, model]` selector separate from plain WorkerLaunchSpec.model. It grants no provider entitlement. Do not activate the historical SPEC_ONLY OpenCode Go realm or another subscription based on API compatibility.
3. Preserve economical existing router defaults; parent/subagent topology alone cannot escalate model tier. Sharing an entitlement across harnesses creates no additional pool.

## Task 7 — Deliver useful native and ACP outcomes to the existing OS [U01–U04]

**Reuse:** existing capability/status projection, app producer/consumer contracts, Executive parent-result path and Macro Agent OS. Native #987/#1043/#1007/hierarchy delivery remains independent of DSH.

1. Use the current app owner's bounded real task/output schema and approved source/devserver. Show one useful native baseline and one admitted ACP/DSH tool-using result consumed by its actual parent; qualify a second eligible provider only after the first works.
2. U01–U04 cover truthful unavailable/auth-required/denied/healthy status, original-parent consumption, unsupported capability refusal and disabling new DSH placements without disturbing native work or uncertain running Attempts.
3. Preserve source/CI/merge/install/START/accepted distinctions. Use current Chairman review direction rather than add an independent-review wait already waived; required checks, source custody, provider permissions and actual product acceptance still apply.
4. Record accepted decisions/discoveries/continuation in the existing Macro Agent OS owner with readback. A GitHub delivery or plan is not recipient pickup, a Worker START or proof of knowledge-plane adoption.

## Exact continuation and proof accounting

The next DSH dependency is existing-carrier #825 source recovery/current-base integration followed by the useful pre-prompt/read-tool extension, not building a new adapter. This session's typed publication-status read for #825 returned TYPED_GIT_PRECHECK_REFUSED/NOT_APPLIED; it was not bypassed with a different tool, clone or branch. This is an exact surface limitation, not proof that the old owner is dead or all source access is unavailable. Existing custody recovery remains with its owner.

The original acceptance matrix remains an unexecuted requirement inventory; do not relabel its 53 cases PASS using earlier #825 tests. Qualify only changed/new behavior, retain exact pin and case provenance, and do not replay any denied invocation. R1 SDK observations remain reference/fallback evidence, not current default implementation instructions. No package install, provider call, worker start or source transfer is performed by this plan revision.
