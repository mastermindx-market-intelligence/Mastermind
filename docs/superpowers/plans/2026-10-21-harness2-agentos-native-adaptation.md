# Harness^2 into Mastermind OS / Agent OS — native adaptation integration

Date: 2026-10-21. State: SOURCE-ONLY FIRST VERTICAL; NOT production installed,
not auto-promoting, not a full end-to-end harness improvement cycle.

## Exact research and source identity

- Google Research upstream: https://github.com/google-research/harness2
  pinned `1cfe254e8d25b15f37048c3730134686abe60335` (Apache-2.0).
- Current Mastermind protected skillpack and source:
  `mastermindx-market-intelligence/Mastermind@d010b161386853586198a43f9ea9f535bbebb377`.
- Macro Agent OS inspected:
  `mastermindx-market-intelligence/macro@c4555b488c56302f36f7128ea7cacf190115d0b6`.
- This work is additive to existing `scripts/agent_eval/`. It neither imports
  Harness^2 nor copies its implementation, and does not modify existing evaluator contracts.
- Mastermind #398 is a distinct unmerged Outcome Learning source with explicit HOLD;
  Mastermind #600 is an unmerged orchestration plan; neither is assumed installed.

## What the upstream actually supplies

1. Task-level recursion: shared baseline rollouts; invariant/general and
   domain-specific proposals; independent candidate probes; parallel compositions
   or sequential composition. With budget k: 4k rollouts and 3k improvement stages,
   plus selector/reflection cost.
2. Harnessing-level recursion: an adopted harness tree and evidence-based
   cue/lesson are available to later tasks in the same domain.
3. Upstream only selects among composed finals, not an objectively independently
   validated no-change baseline; its selector is not a safe Mastermind promotion gate.
4. The reference Codex substrate passes unsafe sandbox/approval-bypass flags.
   Never copy those launcher flags or use upstream runner against production
   credentials, governance state, host filesystem, or live Worker Attemps.
5. Same-task adaptations and domain experience are research behavior;
   continuous unsupervised production rewriting is NOT demonstrated or authorized.

## Canonical composition (no new owners)

| Function | Incumbent owner | Required integration |
| --- | --- | --- |
| Job/Attempt identity, leases, effects, child budgets | Executive OS | Bind experiment to existing admitted Attempt; never let Harness^2 dispatch independently |
| Provider session/workspace, tool and skill install | Operator Harness / capability registry | Produce candidate overlays only in isolated fresh disposable evaluations |
| Measured paired baseline/candidate evidence | Existing Agent Evaluation EVAL-R0 + OHF | Existing sealed scenario/configuration/run/scorer/evidence contracts |
| Causal attribution and memory efficacy | Existing Outcome Learning | Prospective, held-out evaluation; no self-issued gain claim |
| Lessons and cross-session continuity | Macro Agent OS | Reviewed DSC with falsifier, so_what, source-qualified evidence |
| Ranking proposed work | Mastermind improvement agenda | Ingest reviewed suggestion, not a new optimization queue |
| Policy/surface deployment, rollback, independent review | Existing source/release owner | Rev-bound staged shadow/canary, exact reviewer, revert path |

## Eventual product loop

1. Every admitted native Attempt may emit bounded, redacted and source-qualified
   outcome/rework/role/context evidence through incumbent observation paths.
   Missing observations are UNKNOWN, not an all-good baseline.
2. Eligibility should trigger *experimentation* at approved cadence or sufficient
   evidence sample, not launch 4k extra rollouts each time a user asks a task.
3. Select one bounded change class: a skill trigger, a context-compiler selection
   rule, a tool schema/projection, a worker brief, a review checklist, or a
   provider-specific harness instruction. Never let task text widen write paths,
   grant capabilities, edit source law or touch credentials.
4. Freeze a base and candidate tree and exact task-family/holdout revision.
   Run bounded parallel/sequence recursion in isolated OHF/EVAL workspaces
   with each candidate and baseline using the same model, profile, grants,
   environment, judge and predefined held-out tasks.
5. Record independent objective test evidence and external adjudication.
   Negative/unknown/tainted evidence cannot be interpreted as zero loss.
6. Feed validated paired holdout observations into
   `scripts.agent_eval.harness2_bridge.assess()`. This pure function checks
   shape, digests, matched cases, grader agreement, resource/authority regression
   and a minimum sample and improvement threshold; it yields only proposal status.
   Its caller-provided evidence must be authenticated/verified by incumbent EVAL,
   NOT accepted as trustworthy merely because it passes this shape/metric check.
7. For an accepted, independently reviewed experiment, Outcome Learning may
   propose a real evidence-backed DSC/DEC under existing Macro Agent OS schema.
   Promotion stays with current native capability/release owners, not Agent OS.
8. Graduated release: SHADOW -> supervised reversible CANARY -> independently
   evaluated limited production -> policy-reviewed broad roll-out. Automatic
   promotion/reversion only inside explicitly approved existing release and
   safety controls, NEVER newly granted by recursive model suggestions.
9. Learn also from failed proposals by retaining scoped negative evidence,
   without stuffing all transcripts into every future worker.

## Delivered first source slice (this branch)

- `scripts/agent_eval/harness2_bridge.py`: strict provider-free
  candidate comparison; promotion NONE; no Agent OS write.
- `tests/test_agent_eval_harness2_bridge.py`: eligible-proposal,
  undersampled, regressions, effect-unknown, invalid/bogus/tainted inputs,
  and deterministic idempotent output checks.
- Test evidence and exact candidate head belong to branch/PR receipt.

## Next independently useful engineering slices, in order

A. Add an `agent_eval` *verified artifact reader* that maps actual upstream
   Harness^2 JSON trajectory/adoption metadata into incumbent immutable
   EVAL configurations and scorer passes with exact SHA, provenance and
   environment attestation; do not trust user-supplied metric JSON.
B. Integrate that reader into an existing OHF sandboxed lab runner with
   strict resource budget, network holdout-egress fences, prompt injection
   isolation, fixed runner identity and explicit absence of production effects.
C. Prove two real matched baseline/candidate tasks end-to-end and one
   counterexample that rejects a tempting candidate; then expand to a
   preregistered unseen 10+ pair holdout with independent reviewer.
D. Resume existing Outcome Learning #398 through its actual HOLD/review owner
   before trying durable Agent OS lesson admission.
E. Implement artifact-backed, read-only library/context projection through
   existing compile-context/skillpack materializer (generation-bound);
   only then a supervised reversible canary through existing release owners.
F. Add Mastermind OS user experience for task performance, rejected proposals,
   provenance, currently selected generation, rollback and longitudinal
   net accepted-outcome/cost measurement.
G. Fleet rollout only after real native Codex/Claude/Fabric parent->worker->
   independent review->parent consumption checks, including interrupted,
   stale, duplicate and effect-unknown situations.

## Full DONE_WHEN (NOT YET MET)

A real authorized user task traverses Executive admission -> qualified
worker -> observed artifact/outcome -> reproducible isolated adaptation ->
real independent holdout evaluation -> verified outcome learning -> reviewed
Agent OS lesson -> generation-bound reversible deployment -> later distinct
task reads the new harness -> measured improvement on previously unseen work.
Production automation may only propose within approved budgets and promotion
rights. Proven no-regression, reproducibility, attribution, rollback and
correct parent consumption are essential.

**Do not misreport green source tests or an isolated candidate comparison as
Harness^2 fully installed or Agent OS autonomously self-improving.**
