# Subagent Fabric routing: deep audit and bounded repair candidate

Date: 2026-10-13 (US evening). Operation: `fabric-routing-deep-audit-20261013-c2-001`.
Protected procedure/source: `76576d8680bb70cdb9e1cfe7016aefec0fb3286f`.

**Disposition: AUDITED / SOURCE CANDIDATE / NOT INSTALLED / NOT RELEASE-QUALIFIED.**
The Chairman requested an audit and improvements to model choice, priority and load balancing. This operation inspected the installed M2 native Fabric, compared it with protected Executive routing and current integration PRs, reproduced classification defects, and built two narrowly scoped patches in isolation. It did not modify the running Fabric, launch workers, access provider credentials, change quotas, settle leases, restart services, merge source, or adopt another source writer's changes.

## What was established

Four concrete defects have candidate repairs: logical work priority is lost at the remote broker boundary; C0/C1 review labels can override explicit routine complexity on premium routes; C3 witness requirements are inconsistent across providers and cheap-model short circuits; and MiniMax silently ignores invalid explicit complexity. The actual router is predominantly an ordered first-eligible selector, not a general weighted load balancer. Several advertised YAML scoring controls do not govern its selection code.

The evidence does **not** establish measured fleet-wide utilization, billed savings, production latency after repair, or production acceptance. A planned live-ledger schema read was blocked before dispatch and was not retried. Conclusions below distinguish direct source/reproduction evidence, existing owners' source candidates, and unmeasured design risks.

### Verification status, without inflating the result

- Original captured source: **30 new regression checks failed; 20 passed**.
- Isolated candidate: **49 passed; one failed**. The remaining test is `test_glm_pairing_refusal_is_not_bypassed_by_logical_class`: its synthetic account fixture defines MiniMax, not an enabled GLM provider, so the unchanged provider-enabled guard correctly returns `provider_disabled` before the pairing filter. This is a fixture defect, not proof of a pairing regression; nevertheless, the intended pairing test has **not** passed.
- `bash -n` of the candidate remote launcher succeeded.
- Broader legacy regression collection stopped because the isolated snapshot omitted `pool_status`; no broader pass is claimed.
- Two later host actions were blocked before dispatch: fixture correction plus test/ledger inspection, and separate legacy-test preparation/execution. Neither denied action was retried, repackaged, or moved to another carrier. Effects remain absent for those actions. The earlier acknowledged candidate files and 49/50 result remain valid evidence.
- Independent review, complete regression, integrated patch qualification, protected acceptance, installation and real-parent acceptance remain open. These patches must not be treated as deployable because the first 49 tests pass.

## The actual selection and admission path

1. **Executive logical routing.** Protected `control_plane/model_router.py` selects a logical execution shape, capability requirements and ordered suitability tiers. It does not grant a worker or account lease. This protected revision primarily uses task kind, execution risk and ambiguity; the richer TaskFit candidate belongs to PR #1248.
2. **Native request preparation.** Installed `fabric_task.py:414-458` derives complexity and escalation evidence, asks `pick.format_pick` for a route, checks its emitted model with `launch_policy`, and forwards `POOL_TASK_CLASS` and the same economic metadata to the launcher. A visible model choice is not an admitted worker.
3. **Pool/model/host eligibility and ranking.** `pick.format_pick` first obtains eligible per-pool host routes, including model-aware GLM account observations, then runs the appropriate class-specific selection. Role restrictions, capabilities, review separation, quality where implemented, caps and economic checks filter candidates.
4. **Atomic claim.** `remote_sub.sh` invokes the existing broker. `lease_broker.py` enforces pool/account/model capacity, root fair share, queue ordering, account stickiness and relevant host/account admission under its existing lock. This is the capacity grant, not the earlier advisory pick.
5. **Execution and consumption.** A lease, process START, retained result, independent review and original-parent consumption remain separate. None of the proposed ranking changes authorizes retry after refusal or failover after an uncertain effect.

## Findings, severity and changes

### F01 — P1: remote transport labels erase work priority — candidate repair

**Direct source:** `remote_sub.sh:649,655,661` passes `--task-class "remote-$MODE"` at all three broker acquisition call sites. Broker `CLASS_PRIORITY` recognizes heal=0, build/fix=1, review=2, census/audit/mechanical=3; unrecognized classes receive 4. Thus remote heal, build and review requests are indistinguishable to this priority calculation even though the logical class remains available in `POOL_TASK_CLASS`.

**Repair:** an optional `job_class` argument and `--job-class` flag feed the existing waiter priority calculation. The launcher forwards both dimensions. The transport class remains `remote-glm` or its other original value in leases and admission. This distinction is essential: the GLM model/account/host guard explicitly tests `task_class == "remote-glm"`; replacing that field with `heal` would remove that guard's trigger.

**Observed candidate proof:** synthetic SQLite tests demonstrate an urgent heal getting the next grant ahead of an older mechanical waiter, normalized logical class priorities, unknown classes retaining default priority, and preserved transport-class lease records. The GLM pairing-specific test remains unqualified for the fixture reason above. No queue schema, second broker, authority grant, root or provider cap was added.

### F02 — P1: explicit routine complexity loses to a reviewer label — candidate repair

**Reproduced:** `launch_policy` admits C0/C1 `review` on Grok, Cursor and native premium routes without an escalation witness, because their class label maps to `frontier-labor`. The same explicit routine complexity with full GLM is refused without a witness. A routine review and routine audit therefore have different economics merely because of their labels/provider.

**Repair:** C0/C1 cannot obtain a non-cheap route merely by carrying a review/operator-style class. After existing registered-cheap, capability and dated-authorization checks, the expensive path requires the incumbent escalation evidence. Unclassified legacy behavior remains unchanged; ordinary economical workers remain eligible. This is restrictive classification consistency, not a new model entitlement or claim that all reviews are equally difficult.

### F03 — P1: C3 evidence requirement is not provider-invariant — candidate repair

**Reproduced:** C3 without a witness is accepted by cheap GLM, registered Bailian worker, free-model and several premium review paths; non-cheap GLM requires a witness. Early cheap-provider returns and class-based premium returns precede a common complexity check.

**Repair:** require the existing C3 witness across the covered providers before those shortcuts. Preserve Go's stricter short-capability refusal. A witness still does not prove model competence, resolve ambiguity, authorize credentials, or expand the root grant. The existing witness validator is textual evidence presence, not semantic verification; stronger evidence binding remains a follow-on requirement.

### F04 — P2: one provider silently ignores a malformed complexity — candidate repair

**Reproduced:** MiniMax accepts `C9_TYPO` because it returns as outside economic-guard scope before checking the complexity vocabulary. Other covered modes reject it.

**Repair:** include MiniMax in common explicit-classification validation while preserving its ordinary economic scope and no-I/O fast path. Unknown classifications fail clearly instead of silently appearing valid.

### F05 — P2: advertised scoring controls do not control normal routing — confirmed source finding

The installed YAML contains `routing.score_weights`, `base_scores`, `task_class_mapping` and `priority_order`. The inspected picker does not read those controls; `_score_pool` uses Python constants. More importantly, both normal execution and judgment use ordered first-eligible walks, while `_score_pool` is reached through the residual scored path.

Changing the YAML least-busy weight therefore does not rebalance normal builds or judgments. A UI or operator should not imply otherwise. Either remove/label obsolete controls or wire accepted controls into the existing ranking owner with conformance tests. Do not create another optimizer alongside it.

### F06 — P2: first-fit concentration and misleading preference semantics — confirmed behavior, not automatically a policy violation

Execution order is MiniMax, GLM Flash, Bailian, Go, Grok, Cursor, subject to hard exclusions; judgment order begins full GLM, Grok and Cursor. These lists are not eligibility grants. Cursor remains forbidden for labor. A dated Grok quota exception is currently disabled.

Normal work tends to fill the first eligible pool before considering the next. There is a useful existing exception: deterministic 35% Bailian exploration for narrowly qualified routine classes with a stable task identity. Preserve it; do not claim it is a general load balancer. In the ordered paths, `prefer` can be reported in the selected reason without changing the order. Preference receipts should distinguish requested, applied and overridden preferences.

A better policy preserves the first lawful suitability tier and hard economics, then compares admitted headroom, expected completion cost and fresh urgency within that tier. Equal pool shares are not inherently optimal: avoiding paid waste is reasonable, but idle capable capacity should not coexist with avoidable queuing merely because of an undocumented fixed ordering.

### F07 — P2: account ranking is not normalized utilization — confirmed comparator; operational effect unmeasured

Non-Bailian accounts are sorted by `(held, -capacity, name)`. That is raw occupancy, not `held / capacity` or remaining model-specific room. For example, the comparator prefers one held slot on a two-slot account over two held slots on a twelve-slot account. Sequential equal-capacity work can repeatedly favor the same name. Bailian already adds last-grant history to break ties; preserve that completed improvement.

PR #1365 already owns a source candidate for GLM claim-time expiry affinity. Do not duplicate it. Integrate any remaining utilization/rotation change into the same atomic account selector, after model/host eligibility and before a lease, preserving account stickiness and shared non-additive caps. This audit did not measure actual account imbalance or claim the expiry candidate is live.

### F08 — P1 investigation: head-of-line blocking and demand conflation

`_front_of_queue` checks pool-wide priority/FIFO before `_pick_account` establishes whether the next request can use an account/model. An older waiter pinned to a full account can therefore obstruct a newer request for another available account. The waiter row also lacks model identity and is looked up by `(orchestrator_id, pool)`, so concurrent requests from one root can overwrite each other's account, class and host demand. This is a source-level mechanism finding; a dedicated live or synthetic end-to-end reproduction was not completed in this operation.

The repair belongs in the existing broker: preserve each actual request's relevant eligibility, distinguish request identity from root accounting, and let an ineligible head block only the capacity it can consume. Keep fairness charged to the original root; never mint another root to gain slots. This requires deliberate compatibility and concurrent-waiter tests, not an ad hoc queue replacement.

### F09 — P2: quality evidence has cold-start and missing-data gaps

The inspected quality gate correctly uses the concrete selected model and adjudicated outcomes, rather than treating transport failure as model-quality failure. Preserve that improvement. However:

- `below_acceptance_floor` returns false until it has the full configured 20 outcomes. Even 19 negative adjudications cannot activate that statistical floor. This is an explicit cold-start policy, not proof of good quality.
- Samples are separated by model and task class, not explicit complexity or harness/version. Difficult and routine instances can contaminate one another's selection evidence.
- `floor_demotes` catches every exception and returns false. A broken evidence reader is consequently indistinguishable from no demotion unless separately observed.
- The normal judgment walk does not apply the same quality-floor check as execution; this difference should be intentional, documented and tested rather than invisible.

Use the existing outcome/observation owners for confidence and sample sufficiency. Record `QUALITY_UNKNOWN` distinctly; preserve hard exclusions for known unsupported capabilities separately from statistical quality. Do not fabricate acceptance rates for unreviewed work or globally suppress a model because a host or protocol failed.

### F10 — P1 integration debt: source fixes and live policy are divergent

At inspection, multiple relevant improvements were still separate source candidates:

| Owner | Exact observed head | Relevant work | Boundary |
|---|---|---|---|
| Mastermind #1441 | `faa2d094db7abaa0d1433c2a091da3bc51e8f7f5` | Cache-only advisory quota selection; freshness/side-effect repairs | Draft, not installed; preserve separate physical-install refusal |
| Mastermind #1365 | `4c27a8d3a4dab635b5301e3f8fda84576b711b9f` | Exact model/host selector, paired GLM windows, atomic account-expiry affinity | Draft/source bundle; not proof of real selected-account consumption |
| Mastermind #1248 | `c2168fb0656688c11c386e83b26d0dc778bb4be4` | Explicit TaskFit and model-aware capacity planning | Existing review/account-linking gate; do not retry its closed review operation |
| Mastermind #1254 | `90fb8651260720a48fd7677467d6b63277dde896` | Role reserves and excluded models through incumbent installer #1228 | Source-only; prior denied native instruction actions remain held |
| Mastermind #1391 | `bc50ff19eec5f8d73fd5395d410c64388bdccefd` | Original native process/credential/cleanup integration | Preserve source custody and original worker effects |

Do not reimplement the quota cache or GLM expiry algorithm from this audit. The latest #1365 body contains later source results than its older comments; its historical account-affinity gap is not evidence that its present candidate lacks a repair. Source publication, review, merge, installation, selection and acceptance must be tracked separately.

## Recommended target behavior within the existing owners

**Separate which job runs next from which model runs that job.** Work priority and root fairness belong to broker demand scheduling. Model suitability and economics belong to routing. A high business priority may justify stronger review or faster scheduling without automatically buying a frontier model.

For a specific bounded job, the order should be:

1. Normalize closed task/complexity fields, required tools, context breadth, continuity and expected runtime. Keep execution risk, business impact and role separate. Unknown inputs must produce an explicit outcome, not silently become permission.
2. Apply hard eligibility: approved model identity, funding/reserves/exclusions, confidentiality, capability, live host/account compatibility, capacity and the original root grant. A quota promotion cannot relax these gates.
3. Fix the first lawful suitability tier. Within it, rank eligible offers using fresh paired reset/remaining observations, model-specific headroom, whole-outcome cost, latency and scarce-capacity preservation. Advisory observations do not reserve a slot; claim-time rechecks remain mandatory.
4. Use stable request identity for tie-breaking and bounded exploration, not a per-process counter. Rotate otherwise equivalent sequential accounts through existing grant history, and compare normalized/model-aware headroom when capacities differ.
5. Emit an explanation that distinguishes requested and selected model, applied versus rejected preferences, each eliminated candidate's reason, policy generation and observation age. Unknown served-model identity stays unknown; a requested model is not proof of what executed.
6. After an original run ends, use its retained result and review to decide repair or escalation. Never select another provider merely because the original run is slow, disconnected, refused or effect-unknown.

Do not use one arbitrary weighted score to mix hard safety/capability gates with price. Do not optimize nominal tokens alone: the relevant cost includes expected review and repair consumption and the value of delay. Historical placeholder $/token values in the YAML are not invoices or a validated savings model.

## Patch package and exact boundaries

`ops/native_fabric/routing_audit_20261013/` contains:

- `logical_job_priority.patch`: existing broker optional logical class plus forwarding at all three remote acquisition call sites.
- `complexity_invariants.patch`: restrictive consistency changes inside the existing economic guard only.
- `routing_audit.tests.py.txt`: the exact 50-check reproducer, intentionally inert and **still containing the disclosed fixture failure**. Do not present it as a green CI suite.
- `manifest.json`: exact captured preimages, candidate digests, patch digests and verification limits.

No active #1365/#1441 workspace or installed source was edited. Captured source is retained in the operation's isolated evidence directory on the managed volume. The package does not contain live accounts, credentials, lease databases or production logs. It is not an installer. A patch with an exact preimage is not permission to overwrite a newer live generation.

## Acceptance sequence and next useful action

First resolve the denied test-preparation boundary through the actual permitted recovery, without replaying or changing carriers to get the same effect through. Then correct the disclosed GLM fixture, finish the new regression matrix, and qualify unchanged incumbent suites with their complete isolated source dependencies. The test correction must not relax the actual provider/host/account guard.

Next the existing native source owners must integrate these narrow changes with the accepted #1365/#1441 generation. Reconcile exact hashes and real pending effects; do not take over their workspaces or install an arbitrary union of drafts. Review the broker and launcher as a compatible pair: an old broker must not be exposed to a newly forwarded CLI flag without deliberate version qualification. The external broker-command override needs a real compatibility check, not an assumption based on the default subprocess wrapper.

Independent review must cover priority conservation, same-root concurrent demand, GLM pairing, original-root fairness, legacy calls, capacity refusal and effect-unknown behavior. Hosted checks and protected acceptance precede installation. The launcher's economic check and atomic broker check must still agree on the exact requested model/host account after integration.

Finally, use an already-admitted useful work item through the original parent to prove selected model/pool/account, real grant/refusal, START, retained result and exact-parent consumption. Verify the actual installed generation and rollback identity separately. No new worker was created by this audit, and no unattended continuation, automatic merge or production acceptance is claimed.

## Recoverable frontier

- Current source branch: `sol/web-fabric-routing-deep-audit-20261013-c2-001`.
- Managed workspace: `/Volumes/Mastermind 2/agent-workspaces/web/fabric-routing-deep-audit-20261013-c2-001`.
- Evidence directory: `/Volumes/Mastermind 2/evidence/fabric-routing-deep-audit-20261013-c2-001`.
- Last confirmed effects: isolated snapshots, candidate source edits, 49/50 regression run, and this source-only artifact package. No production modifications or unresolved writes.
- DO_NOT_REDO: broad source census, original 30-failure reproduction, already-owned quota/expiry/TaskFit implementations, or any denied call. Do not rerun already accepted tests without a changed relevant candidate/dependency; do not erase the one failing test from the evidence.
- Remaining work: permitted fixture/regression completion, independent review, owner integration and actual protected installation/parent proof. Mission production-complete: **false**.

### Artifact verification before publication

The six captured source hashes, three changed candidate hashes, both patch hashes and exact reproducer bytes were checked successfully against the manifest. Changed Python/shell source lines have no trailing whitespace. Both patch files parse as unified diffs: 24 additions/13 removals in the broker, 3/3 in the launcher and 19/1 in the picker. A literal text-whitespace scan of the patch artifact flagged its required blank-context marker; those markers were preserved rather than corrupting the diff. None of these structural checks substitutes for the incomplete regression or release acceptance.
