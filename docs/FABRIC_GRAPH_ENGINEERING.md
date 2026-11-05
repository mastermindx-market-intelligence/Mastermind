# Fabric graph engineering

Status: source implementation and operating guide; production qualification is separate.
Source baseline: `adf612f8041f12597ec732f8898c06c8adcddf59`.
Task tree: [FABRIC_GRAPH_ENGINEERING_PLAN.md](FABRIC_GRAPH_ENGINEERING_PLAN.md).

## Contents

1. [Decision rule](#decision-rule)
2. [Roles and core methods](#roles-and-core-methods)
3. [Admission and reservation arithmetic](#admission-and-reservation-arithmetic)
4. [Use the planning consumer](#use-the-planning-consumer)
5. [Context, delegation and completion](#context-delegation-and-completion)
6. [Model and harness selection](#model-and-harness-selection)
7. [Economics and comparative evaluation](#economics-and-comparative-evaluation)
8. [Rollout and evidence boundaries](#rollout-and-evidence-boundaries)
9. [Primary evidence](#primary-evidence)

## Decision rule

Choose the smallest graph that can preserve the original outcome, competent execution, required independent review and integrated product acceptance. Add a coordinator when it owns a separable domain, resolves dependencies, isolates substantial context, or protects a real permission boundary. Remove a proposed relay that adds none of those benefits.

The Chairman's principal -> native program coordinator -> Fabric operator -> workers is a useful **optional program shape**. It is not a mandatory four-hop path for every request. Conceptual roles do not automatically map one-for-one to admitted runtime depth; the actual root, parent chain and existing hierarchy grant govern each launch.

Choose structure before selecting qualified model/harness routes, then revisit both using measured whole-cycle outcomes. A model family does not confer an organizational role. A worker may need a stronger or longer-horizon model than its coordinator.

This implementation supplies composition methods and static advice. It does not claim an evidence-trained optimizer, automatically select the cheapest graph, issue grants, reserve money, dispatch work, or change runtime defaults.

## Roles and core methods

| Role | Owns | Useful when |
|---|---|---|
| Strategic principal, including assigned Astra/Fable | Original intent, priorities, architecture tradeoffs, exceptions and integrated acceptance | Every consequential program needs an accountable principal |
| Native program coordinator, including assigned Sol/Opus | Cross-domain plan, interfaces, critical dependencies, acceptance evidence and exception escalation | Multiple meaningful domains need continuing coordination |
| Qualified Fabric operator | Bounded delivery cycle: decomposition, lawful worker requests, return adjudication, review, bounded repair and integration | Delegated ownership reduces the principal's total work |
| Fabric worker or specialist | A concrete artifact or investigation under a narrow contract | Work is bounded and can be judged from a clear return |
| Independent reviewer | Adversarial evaluation against original criteria and exact artifacts | Existing risk and review obligations require independence |

A reviewer is an independent responsibility, not necessarily another permanent management layer. The existing assignment determines whether an operator may commission descendants. A label such as "operator" or a source skill cannot grant spawning rights. Workers and reviewers remain leaves under current policy.

| Method | Select it for | Composer behavior | Main failure to avoid |
|---|---|---|---|
| `direct` | One cohesive deliverable with shared evolving context | Requires exactly one non-delegating step | Splitting a tightly coupled task into costly handoffs |
| `pipeline` | Genuine sequential prerequisites | Adds the immediately previous step as a prerequisite and preserves existing edges | Inventing stages that only repeat or summarize context |
| `fanout_join` | Independent investigations or disjoint bounded work with one combined deliverable | Requires at least two leaves and a final supplied step; makes the final step depend on every leaf | Parallel branch success without a competent integration owner |
| `hierarchical` | Substantial separable workstreams with useful delegated ownership | Requires an existing v5 plan with an explicit coordinator; analyzes inherited allowances | Fresh budgets per child or a hierarchy that only relays messages |
| `custom` | A task-specific DAG not covered by a template | Preserves the caller's graph under the same plan validator | Using custom as a bypass for review, scope or admission |

Independent verification and bounded repair use the incumbent `review_required` cycle; they are orthogonal to these shapes. Do not add a superficial "review step" and assume it establishes reviewer independence.

For `fanout_join`, the orchestrator must supply a final step whose objective and validation references carry the original acceptance and integration obligations. Dependency edges alone cannot establish that meaning. Empty leaf prerequisites also do not prove semantic independence. The report explicitly leaves integration-contract semantics unverified.

For `custom`, multiple terminal steps are allowed by the underlying contract. The principal must identify who consumes them and proves the combined result in the existing commission/acceptance records. The advisor reports terminal step IDs and does not invent a generic acceptance node.

### Practical choices

- A localized bug fix normally has one capable owner, focused validation and the required review: `direct`.
- A migration where the compatibility layer must exist before consumers change uses `pipeline`.
- Independent source investigations followed by a synthesis uses `fanout_join`.
- A product with distinct data, application and infrastructure domains may justify `hierarchical`, but only within the actual inherited grant and with affordable review/integration capacity.
- A diamond graph, staged investigation, or task-specific branch/join pattern can use `custom`.

These are starting hypotheses. Strong coupling, uncertain interfaces or shared files can make a single owner more effective even on a large task.

## Admission and reservation arithmetic

The canonical owners remain:

- [ExecutionPlan validation](../control_plane/executive_orchestration_result.py).
- [COO cycle policy](../control_plane/executive_coo_policy.py).
- [Hierarchy validation](../control_plane/executive_coo_hierarchy.py).
- Existing admission, model routing, capacity, source custody and effect reconciliation.

The consumer reuses the existing v1-v5 plan validator and current policy. It does not add an execution-plan schema, queue, state store, scheduler or model registry. The report's schema identifies an ephemeral diagnostic, not a new admitted plan or persistent state owner.

At this source baseline, a reviewed work step reserves:

```text
(1 + 2 possible repair rounds) * (1 work + 2 possible reviews) = 9 descendants
```

The planner reserves one additional descendant. The total allowance is 16. These are **cumulative reservations**, not concurrent worker counts.

| Prospective shape | Reserved demand | Interpretation |
|---|---:|---|
| One reviewed work step | 1 + 9 = 10 | Fits this numeric allowance |
| Two reviewed work steps, including a pipeline | 1 + 9 + 9 = 19 | Exceeds it by 3; serialization does not refund cumulative slots |
| Three genuinely read-only evidence leaves plus one reviewed synthesis | 1 + 3 + 9 = 13 | Fits if the original review obligations genuinely permit those leaves |
| Root planner plus a coordinator with a subtree allowance of 10 | 1 + 1 + 10 = 12 | Counts the coordinator and its subtree; the child does not receive another root allowance |

Do not downgrade required review to make a plan fit. Do not create replacement roots, hide parents, increase caps, or treat a lower concurrency setting as a fix for cumulative reservation demand. Re-scope the actual work without losing obligations, or seek a separately reviewed policy change through its owner.

A coordinator's `descendant_limit` includes its own planner and potential review/repair descendants. It is partitioned from its parent's allowance. Its depth and descendant bounds must attenuate. The prospective policy is selected from the candidate schema; this does not authenticate the policy under which an existing root was admitted. Existing-root replay must still use the runtime's admitted policy and root history.

The report separates:

- `capacity_fits`: whether numeric demand is within the declared limit.
- `policy_compatible`: whether the incumbent static reservation policy accepts the hierarchy and bounds.
- `shortfall`: numeric missing slots only.

A zero shortfall cannot repair an invalid depth or inherited grant. Reservation size is a capacity bound, **not** a price, token forecast, live capacity measurement or economic ranking.

Unordered potential write-scope overlap produces a conservative warning. An ordered pair can still collide with other active source carriers; the runtime/source owner must reconcile that wider custody. The advisor's dependency width is the maximum antichain of the supplied steps, while depth is their number of dependency layers. Neither expands child plans or measures actual concurrency or elapsed critical path.

## Use the planning consumer

From an ordinary approved checkout of this source:

```bash
python -m scripts.fabric_graph_plan catalog

python -m scripts.fabric_graph_plan plan examples/fabric_graph/direct.json \
  --root-job-id example-root --plan-attempt-id example-plan-attempt --method direct

python -m scripts.fabric_graph_plan plan examples/fabric_graph/fanout_join.json \
  --root-job-id example-root --plan-attempt-id example-plan-attempt --method fanout_join

python -m scripts.fabric_graph_plan plan examples/fabric_graph/hierarchical.json \
  --root-job-id example-root --plan-attempt-id example-plan-attempt --method hierarchical

python -m scripts.fabric_graph_plan plan examples/fabric_graph/over_capacity.json \
  --root-job-id example-root --plan-attempt-id example-plan-attempt --method pipeline
```

The first three plan examples return exit 0 for static compatibility; the last deliberately returns exit 1 with demand 19. The examples are read-only planning illustrations. Their example identities and validation hashes are not issued runtime identities or actual evidence. Replace them from the real assignment before considering a plan for execution.

Exit 0 means static compatibility, exit 1 means findings require attention, and exit 2 means invalid input or unavailable policy/store. **No exit code means admitted, dispatched, independently reviewed, accepted or installed.** The input file remains unchanged.

The report contains the composed `candidate_plan`, its canonical digest, policy identity, reservation breakdown, dependency facts, findings and explicit unperformed checks. Return an appropriately reviewed candidate through the existing planner-result path. The existing harness must still bind and seal the actual result. Do not manufacture a completed envelope from this report.

For a nested v5 candidate, pass all three declared inherited bounds:

```bash
python -m scripts.fabric_graph_plan plan nested-candidate.json \
  --root-job-id ORIGINAL_ROOT --plan-attempt-id ACTUAL_PLAN_ATTEMPT \
  --method custom --coordinator-depth 1 --descendant-limit 10 --max-depth 3
```

Caller-supplied bounds remain unauthenticated. The advisor never changes root or coordinator identity, write paths, authorities, review requirements, validation references, attempt limits, placement or delegation grants. Templates only add dependency edges when applicable. Existing leaf dependencies cannot be erased to force a fanout.

The implementation imports the current canonical plan validator rather than changing that owner's API while adjacent planner work is active. Validator contract changes require rerunning these parity and negative tests; a future public helper belongs to that same owner.

## Context, delegation and completion

Use existing commission and return contracts. Put the following task-local information in the worker packet without introducing another mutable registry:

1. The outcome and original acceptance criteria, including falsifiers.
2. Exact source/effect carrier, original root and real parent.
3. Minimum relevant file paths, immutable references, interfaces and current findings.
4. Permitted scope and actions, review expectations, explicit exclusions that matter.
5. Required artifact and validation evidence, expected return shape and consumer.
6. Inherited resource/attempt bounds and the next decision when blocked.

Load the core policy and only the assigned role and relevant reference. Prefer exact artifacts and bounded source excerpts to cloned parent transcripts. Preserve decisions, invariants, uncertainty and evidence links when summarizing. A short summary that loses an acceptance obligation is not an efficiency gain.

Keep invariant context stable within the approved harness where supported, but record actual cache treatment before estimating its economic benefit. Avoid repeated broad repository censuses after a coherent source pin. Ask workers to return changed artifacts, validation results, unresolved findings and the next required decision; raw logs remain available through their authoritative references.

Batch tightly related small work under one capable owner when the setup and context dominate execution. Parallelize truly independent branches only after reserving review and integration. Stop widening builders when review or integration becomes the bottleneck. Reuse the existing bounded repair flow with a precise defect list; do not repeatedly restart an unchanged failing approach.

Escalate when the failure changes the problem class: missing authority, uncertain effects, source conflict, insufficient evidence, or frontier judgment. These require different decisions. A normal retry budget or a stronger model does not fix every category.

The principal consumes the integrated user/machine path and unresolved risk. Worker success, published source, green CI and technical EVAL validity are intermediate evidence. Preserve NOT_ACCEPTED when material integration or original-intent proof is missing.

## Model and harness selection

Separate four choices:

| Dimension | Meaning | Evidence needed |
|---|---|---|
| Role | Principal, coordinator, operator, worker or reviewer | Accepted assignment and actual authority |
| Model | Capability, reasoning behavior, context and task fit | Exact requested/served identity and representative task results |
| Harness | Tools, workspace, persistent context, checkpoints and execution semantics | Qualified harness/version and actual tool-loading proof |
| Provider/account pool | Admission, quota, cost and concurrency | Current eligible route and shared-pool capacity evidence |

A product name such as Cursor may identify a harness or pool rather than one model tier. The Chairman's Grok, Qwen, GLM, Kimi, DeepSeek and other candidates should enter through qualified exact routes. This guide makes no claim that a named version is available, admitted or cheapest.

Use the least costly **qualified complete cycle** consistent with the outcome. Cheap workers suit narrow transformations with inexpensive verification; ambiguous architecture, poorly specified debugging or difficult long-horizon execution may justify stronger models. A weaker builder plus extensive frontier repair can cost more than a strong direct executor.

Reserve frontier reasoning for high-consequence ambiguity, cross-domain decisions and exceptions when required by current classification. Do not use a large model solely because its supervisor is large. Likewise, do not force low-cost workers onto tasks whose verification is harder than the original work.

Consider provider marginal cost, quota opportunity cost, retry risk, expected review/integration effort and latency. Subscription access does not imply free or unlimited work. Apply any pool preference only after eligibility and task fitness; guidance cannot create a new route or authorize cross-provider continuation of uncertain effects.

## Economics and comparative evaluation

Optimize quality-constrained whole-cycle cost. For an evaluation batch with comparable tasks:

```text
observed cost per accepted outcome =
  sum(attributed framing + coordination + execution + tools
      + review + repair + integration cost across all attempts)
  / independently accepted outcomes
```

Failures stay in the numerator. If acceptance is unavailable, the denominator is unknown. If no outcome is accepted, report no finite cost-per-accepted result. Do not replace acceptance with "completed", source publication, a technically valid receipt, or a self-reported success.

Report money, scarce-pool consumption, recorded token units, completion latency and quality separately. Any combined objective requires explicit business weights. Token counts alone cannot compare different cache/reasoning/billing conventions across providers.

### Existing evaluation consumer

```bash
python -m scripts.fabric_graph_plan resources \
  --root /path/to/existing-evaluation-store \
  --experiment-id experiment:ACTUAL_UUID
```

This uses the incumbent EVAL ArtifactStore and verification/finalization owners. It observes one complete run enumeration, verifies selected run graphs and their canonical identity, and groups by arm, configuration, scenario and version. It creates no store when the supplied path is missing.

The report includes observed-population digest, run/status counts, observed sums, missing-observation counts, total input/output tokens only when complete, exact decimal cost sums separated by currency and usage-reference coverage. Failed, invalid, degraded and incomplete receipts remain included.

Limits remain visible: expected trial coverage is not established; resource observations may overlap; parent framing/review/integration can be unrecorded; usage references are not audited bills; external evidence content and independent product acceptance remain unverified. `cost_per_accepted_outcome` remains null. This command produces no winning model, routing recommendation or automatic policy promotion.

### Comparative qualification

Use the existing experiment/scenario/configuration and acceptance owners; do not add a parallel benchmark database.

1. Select representative real tasks: a cohesive change, independent research, integration-heavy product work and a difficult long-horizon problem. Preserve original requirements and evaluation difficulty.
2. First compare graph methods with equivalent qualified execution capabilities. Then compare model/harness assignments within promising graphs. Finally compare context packaging. Avoid confounding every dimension at once.
3. Pin scenario versions, source basis, tools, permissions and acceptance obligations. Record requested and served models, harness versions, provider pool and actual resources.
4. Use repeated paired tasks or matched trials with declared stopping/budget rules. Include failed attempts, abandoned work, reviews and repairs. Do not select a few successful runs after seeing results.
5. Obtain independent artifact/user-path acceptance. Compare per-task quality, integration defects, required human intervention, wall time and total attributed cost with uncertainty and coverage.
6. Retain a task-specific Pareto set of quality/cost/latency choices. Promote a default only through the current policy owner after measured evidence and a rollback criterion.

Start with a direct capable baseline and the best justified alternative, rather than a large combinatorial tournament. Add hierarchical candidates where the work has enough independent domain ownership to plausibly repay coordination. Never run an economically attractive candidate that cannot fit current review, authority or effect constraints.

## Rollout and evidence boundaries

1. Source review: exact candidate code, examples and negative tests.
2. Protected merge/release: incumbent independent review and required gates.
3. Installed consumer qualification: exact source/harness/skill loading, with a read-only positive and negative case.
4. Admitted pilot: a genuine assignment through the existing client with original-root custody and terminal reconciliation.
5. Comparative evidence: accepted outcomes, attribution coverage and task-specific default proposals.

These are separate proofs. Source test success does not establish future-session loading, provider admission, worker start, product quality or measured savings. The existing admitted-plan projection at the baseline supports earlier plan versions; this advisor's v5 support must not be represented as v5 support everywhere in the installed UI.

The current operation's initial paid census was refused before worker start by host thermal admission. The retained result and unchanged original root are recorded in the task tree. It is evidence of that attempt's refusal, not a claim that every provider or host is unavailable. Do not retry that refused operation or bypass the host condition.

## Primary evidence

- Anthropic, [Building agents: when to fold subagents into your main agent loop](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop), 2026-10-22. Supports removing unnecessary delegation while retaining real parallelism, independent verification and useful context/permission separation.
- [Towards a Science of Scaling Agent Systems](https://arxiv.org/abs/2512.08296), v3, 2026-04-08. Its controlled comparisons support task-dependent topology selection; sequential and parallel workloads do not benefit equally. Its results do not establish a universal optimal depth for Mastermind.
- Anthropic, [How we built our multi-agent research system](https://www.anthropic.com/research/multi-agent-research-system), 2025-06-13. Demonstrates a useful research pattern while documenting substantial token consumption; this is not a measured savings result for our engineering workflow.
- [RouteLLM](https://arxiv.org/abs/2406.18665), v4, 2025-02-23. Supports evaluating quality-cost routing tradeoffs. It does not rank current Mastermind model/pool/harness combinations.

The selection rules above are engineering judgments informed by these sources and the pinned local policy. Prospective evaluation must determine which combinations actually improve Mastermind completion economics.
