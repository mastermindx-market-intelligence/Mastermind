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

## Continuation: actual upstream/native observation composition

The current Chairman continuation explicitly requests research, planning and
implementation through completion. The original PR/branch remains the source
carrier; its prior manually provisioned clean worktree is preserved, not
relabelled as a managed workspace or silently re-homed. New workspace acquisition
continues to require the installed custody owner.

Important research correction: Harness2 starts each new task from H0. Its
per-domain library influences the improver; it does not blindly deploy the prior
task's adopted harness. Task-local experimentation, cross-task experience, and
fleet-wide policy promotion are separate operations. The library and stage
instructions are fixed during each task. The reference selector chooses among
composed finals and adoption is not verified optimality.

`scripts/agent_eval/harness2_native.py` now implements a real format adapter for
upstream `core/schedule.py::_run_one_mode` at the pinned upstream source. Inputs
are retained raw summary/native-observation/output bytes, the complete resolved
harness-file inventory, and an independently supplied expected binding digest.
The binding joins one selected upstream rollout to its existing native EVAL run,
scenario and configuration. Strong SHA256 hashes bind all retained bytes;
upstream's truncated SHA1 is used only for serialization compatibility.

The adapter checks duplicates, nonfinite numbers, nesting/byte/file limits,
source/task/mode/budget/run identity, complete finals, fallback and errors,
canonical native shapes and exact configuration/output joins. It never follows
`chosen_run_dir` or any upstream path. It appends provenance to the existing
native evidence list, then uses the incumbent EVAL finalizer. An existing
ArtifactStore handles create-only publication and conflict detection. There is
no new store, runner, scheduler, provider route or promotion decision.

Authentication remains external: matching a caller-supplied hash does not prove
who issued it or whether supplied observations were truthful. Effect, cleanup,
model and fresh-session observations come from the original native runner and
are never synthesized from upstream success flags. Unknown model fields that
violate native schema are refused, not filled with a guessed model. Invalid
native effect/cleanup observations survive as invalid native run receipts.
The importer covers selected completed artifacts; it does not replace native
failure recording or provide a complete experiment's enumeration by itself.

Current local check: native import tests + original bridge + existing inertness
suite: 194 passed. This is synthetic source/contract and real native ArtifactStore
round-trip proof, not real model execution, holdout efficacy, live admission,
independent review or production acceptance. No provider or application was
installed or altered.

Delegation evidence: existing paid Fabric reviewer
`harness2-1663-review-20261021-01` (same root/parent
`harness2-agentos-evidence-20261021`) returned terminal rc1, no review, with
`QWEN_FINAL_RESPONSE_UNCONFIRMED` and provider 429. A distinct bounded adapter
build request `harness2-1663-adapter-build-20261021-01` first refused an optional
unqualified continuation contract before dispatch; exact status remained NOT_FOUND.
One bounded retry without that unsupported option returned no eligible remote
mode: Ubuntu disk/thermal/recovery/qualification blockers. No worker source effect
or accepted review is claimed. Direct bounded source implementation uses
NO_ELIGIBLE_PRE_EFFECT_WORKER; required independent review remains outstanding.
Executive v3 reader separately returned backend_unavailable before dispatch.
Neither failure proves every provider or all runtime writes unavailable.

## Native method and machine-interface milestone

The existing `scripts/agent_evaluation.py harness2-import` command now reads
explicit bounded retained files, joins the existing native scenario/configuration/
experiment through ArtifactStore, checks the upstream/native byte binding, and
publishes a native EVAL run through the existing create-only store. The existing
`score-integrity` command consumes that run without an alternate scorer registry.
A real separate Python-process CLI test verifies publication and exact readback.
Tampered inputs do not publish; a native EFFECT_UNKNOWN observation is retained
as INVALID_EFFECT_UNKNOWN, not changed into success.

`scripts/ohf/harness2_recursion.py` implements the published parallel-branch and
sequential-refinement algorithms in native code. Each task starts at common H0;
k baseline, 2k proposal probes and k composed probes give 4k rollouts, with 3k
improvement calls plus reflection and, for k>1, anonymized final-output selection.
Parallel means independent branches; actual parallel placement/concurrency belongs
to the existing host port, not a new executor created by this function.

The port must be provided by the incumbent admitted native execution owner.
Every returned native EVAL receipt is revalidated under a comparison configuration
sealed before the first callback. Only the exact admitted overlay paths may change.
All root/Attempt admission, real resource accounting, sandboxing, native retention,
provider sessions and pending-effect reconciliation remain at that owner. The
method has no provider subprocess, account choice, queue, database, retry loop,
persistent library or automatic deployment. A callback exception ends this finite
invocation; an invalid/effect-unknown returned run is preserved in its error frontier.

The model-facing improvement and reflection views exclude scenario/grader contracts.
Prior Agent OS lesson references and adopted-harness artifact references are frozen
through the task. The result contains a candidate claim, falsifier, so_what and
supporting native run IDs, never an automatic record write or verified discovery.
The full selected harness remains referenced through the native artifact owner.

The original score-only `assess` interface is now an explicitly UNVERIFIED diagnostic.
It no longer declares a proposal eligible from supplied scalar JSON. Its old numeric
screen is a compatibility diagnostic, not a statistical rule, efficacy claim,
independent review, content verification or release authority. Baseline contamination,
per-case score regressions and huge-integer input failures are covered.

Latest complete local command (current candidate bytes, before publication):

    PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -o addopts='' -q --tb=short tests/test_agent_eval_*.py

Result: **813 passed**. This includes the existing EVAL suites, imported artifact
composition, CLI/store/scorer tests, and 23 native recursion mechanism checks.
One fixed, scripted laboratory test actually executes the arithmetic helper four
times: the positive-only baseline produces 105; the corrected signed sum produces85.
This demonstrates execution and integration of the algorithm mechanics, not model
learning, honest holdout provenance, external-service authenticity or production
harness efficacy. No upstream provider launcher was executed. No independent
source review, hosted CI, merge, deployed native port or later live worker adoption
is claimed by these local checks.

Next source consumer: resolve the already-compiled Agent OS context bundle and
adopted-harness references through their existing owners, preserve excluded/stale/
superseded/omitted/degraded evidence, and feed only appropriate domain experience
to the native method. Next runtime dependency: qualify the existing native port's
actual model/effect/session observations and run a new bounded admitted canary;
do not reuse or alter the old sealed E1 or Outcome Learning #398 held operation.

## Source-bound Agent OS consumer and cross-repository proof

Macro PR #9965 (https://github.com/mastermindx-market-intelligence/macro/pull/9965),
head `6b24d5f6de4332c0bd004a07aca7576523d26dcf`, now supplies the optional native
`compile-context --harness-experience` projection. Four source files changed;
12 new feature cases and 224 total compiler/schema cases passed locally. It is
DRAFT/HOLD, not installed or merged. Its original source workspace was obtained
through the existing `mmx-workspace` manager, operation
`harness2-agentos-consumer-20261021`, lane web, base
`cd90f651ea2db5a24ca46c5ded45f7e64cdbc733`. No existing Agent OS decision was
superseded, no generated state was edited and no synthetic lesson was published
as validated institutional knowledge.

`scripts/agent_eval/harness2_context.py` consumes the actual context_bundle.v1
bytes, expected digest, exact source generation and explicit workstream. It keeps
the WHOLE context (higher law, workstream, all exclusions, omissions and degradation)
while extracting typed same-domain experiences with their original confidence,
source-run and adopted-artifact provenance. It refuses changed/malformed/conflicting
input; future-dated lessons do not become prior experience. Old clipped prose is
not parsed into invented complete lesson fields. No external artifact is fetched.

The native refinement function now consumes that reader directly when
`agentos_context_inputs` is supplied. It refuses a second unbound library and
requires the complete context packet digest to match the existing native evaluation
configuration before any port call. Higher law and missingness are not replaced
by a persuasive lesson list. Only the existing port owns actual execution, model,
capability grants and observation authenticity.

Actual cross-repository proof executed the new Macro CLI at the published source
against its temporary synthetic Agent OS test store, then read the unmodified
result with the Mastermind context consumer and executed the four-rollout scripted
native laboratory. The complete lesson was 1,400 characters (not the clipped
excerpt), all context was preserved, the fixed arithmetic program changed from
105 to 85, and four native fixture EVAL records resolved through the existing store.
Context digest:
`sha256:c578865773bdc3459a0870588a45443f803b44c7f7cb00e5bc1fc7bda2d460dd`.
Record-set digest:
`sha256:867b4c04494000ca40b28d88a2604f8aa797a70f06e0eb80d517f2cb3fb1fdf7`.
This was an actual compiler/consumer/program path with SCRIPTED fixture inference,
not a real provider run, native runtime admission, prospective efficacy test or
authenticated live observation. The temporary test store is not production memory.

Latest complete EVAL test command remains the same `tests/test_agent_eval_*.py`
selection: **844 passed** (17.81s). This includes 24 new source-context cases and
four additional native-method integration cases; do not add earlier overlapping
suite counts. Macro's separate compiler/schema result is 224 passed.

A second independent paid review of exact core head `1b86c212...`, child
`harness2-1663-review-1b86c212-20261021`, failed before worker launch on the M1
transport: `TRANSPORT_READBACK_REFUSED` / not-a-directory `lanes` / packet readback
hash mismatch. Status stayed NOT_FOUND; no review or source edit occurred. A
bounded read-only check found the named physical directories present but did not
establish the cause. Preserve the readback guard; no unchanged retry or alternate
carrier was used. This review route and the native production-port qualification
remain actual dependencies, not accepted work.


## Feedback producer and actual two-task mechanism proof

The native kernel now names its actual baseline run IDs and baseline harness
hash. Model reflection must cite both a baseline and the selected result. The
shared configuration factor lock remains one implementation in the pure native
adapter, consumed by the kernel and the Agent OS draft producer.

`harness2_context.build_discovery_payload()` resolves the complete declared
4k native run set through the incumbent ArtifactResolver, recomputes the existing
EVAL graph/validity, checks the factor lock, baseline identities, selected
harness/output bytes and selected artifact association. It prepares only the
existing `agentos.py draft-discovery` input. It writes no memory, issues no
approval and authenticates no source issuer. Its confidence is always `suspected`;
the claim explicitly remains an unvalidated hypothesis. No reflection or an
unchanged selected harness produces no positive-learning draft. The external
content, factual lesson and any claimed performance gain still need independent
review. Graph consistency is not that review.

The actual Macro text renderer previously dropped full nested harness metadata
under `--harness-experience --text`, although the JSON view retained it. A failing
real-CLI regression exposed the omission. The existing renderer now emits the
same complete selected data; default text without the opt-in is unchanged.

Proof through the real native commands, all in a disposable fixture store:

1. A scripted improver and four real Python helper processes produced the first
   signed-accounting contrast: 105 baseline versus 85 candidate. Existing native
   EVAL records retained the observations.
2. The new native draft producer read those records. The real Macro
   `draft-discovery --from` command returned the identical payload and valid
   existing DSC frontmatter, with confidence `suspected`.
3. The unchanged Macro `compile-context` machinery read that temporary record,
   emitted full provenance and missingness, and its raw JSON was byte-bound by
   the native reader.
4. A second task with DIFFERENT amounts (35, -10, -5) started from its own common
   H0, received the prior suspected lesson and retained the complete context. Its
   four scripted-improver/real-helper executions yielded 35 baseline versus 20
   candidate. Both the JSON and text consumers retained the complete lesson.

This proves data transport, deterministic mechanics and H0 reset, NOT that an
LLM learned, that a lesson caused a gain, that holdout efficacy is demonstrated,
or that any production memory or harness changed. The fixture improver is
scripted and already knows its edit. All eight executions are synthetic EVAL
fixtures even though their arithmetic helper subprocesses actually ran.

Original retained fixture: `/private/tmp/harness2-feedback-20261021-i_s0h2i3/`.
Its report and existing EVAL stores preserve exact run identities, content
hashes and limitations. The first diagnostic stopped before second-task
execution because the test driver omitted the required `prior_experience=()`;
the original first-task artifacts were preserved and only the missing second
leg was run. No live operation was retried or moved.

Complete core `tests/test_agent_eval_*.py`: 862 passed. New draft-producer
negative cases first failed on the missing producer. Exact targeted producer,
kernel and inertness suite: 192 passed. Macro text feature subset: 13 passed;
its new discriminator failed before the renderer fix. The full Macro compiler
and schema campaign is separately recorded on its original PR.

## Current execution and independent-review boundaries

Executive V3 exact bounded summon `harness2-native-crossrepo-audit-e39917f5-20261021`
returned `backend_unavailable`, with no Job/START. The existing native manual
Fabric route is distinct and remains the lawful alternate for new admitted
bounded work, never a replay of an uncertain action.

MiniMax cross-repository review `harness2-crossrepo-minimax-e39917f5-20261021`
terminated before model execution with `REMOTE_SUB_CWD_MISSING`. The corrected
new child `harness2-crossrepo-minimax-e39917f5-r2-20261021` used the documented
host-relative directory and terminated rc78: `canonical_source_unreadable`.
Both retain their original root/parent and terminal receipts; neither produced
review or source effects. Cursor labor was policy-refused; it was not relabelled
to evade that policy. Flash refused bounded C2 complexity. A subsequent eligible
GLM-5.3 review preview selected Ubuntu0 under the existing explicit C2 escalation
rule; a preview is not execution and must be followed by actual retained evidence.
The earlier M1 Qwen review was independently reconciled terminal before launch:
its direct cause was a `lanes` symlink rejected by the current no-follow
transport reader, not a model opinion or successful review. Preserve its original
terminal ID and no-follow guard; do not repeat that same failed invocation.

The real native-port gap is concrete. The existing
`OperatorHarnessOrchestrator.start_attempt/run_turn` requires an actual admitted
Attempt, immutable provider profile and owner-provided prompt binding. A
`CandidateResult.summary` is not a full retained deliverable; an observed
attestation can legitimately have `served_model=None`. Neither may be filled
with an invented output/model to satisfy EVAL. The actual production composition
must supply each stage's source/profile, complete raw result, observed process/
session/model/capabilities/network/effects/cleanup and resource evidence through
the incumbent owners. It must retain root-wide limits and the actual release
holds. Creating an injected callback or a self-signed observation is not the
missing implementation. Preserve the existing Runtime/COO/observation source
custody; this PR does not start or replace that control plane.


## Complete prior-harness materialization

The original integration delivered prior lesson metadata plus a harness artifact
reference, leaving actual full-tree retrieval optional in the port. That was an
incomplete implementation of the published full-adopted-harness library. A
regression proved that a nonempty history could previously start without the
prior files. The kernel now requires `resolved_experience_harnesses` from the
existing artifact owner before any port call when prior experience is present.

The input is exactly the referenced artifact set, not a filesystem search or a
new library. Every complete file map passes the existing alias/path/UTF-8 bounds
and must hash to its associated native artifact. Missing, partial, modified,
conflicting-ref, unrelated and oversized inputs stop before any rollout. All
unique prior trees share the existing four-MiB bound. Frozen detached complete
files are supplied to each improver/reflection context so the admitted port can
stage them for on-demand inspection. They never replace this task's common H0
and do not grant execution authority to their contents. The result explicitly
names the realized artifact refs. No-history callers retain their prior behavior.

The focused context/kernel/inertness suite passed 202 tests after the change;
the missing-files discriminator first failed on the predecessor. The existing
later-task and real Agent OS context tests now require actual matching full files,
not merely a matching prose lesson.

## Existing Fabric release finding and preserved effects

The independent GLM run `harness2-core-glm-fa39136c-r2-20261021` ended without
review at `transport_verification_log_not_prelaunch`. Its router selected
Ubuntu2, and the launcher correctly recorded its physical `glm-frontier` lease;
the installed verifier instead demanded the logical `glm` string. The same
contradiction was confirmed on the active combined source #1674 at
`b30168a811d938716da2188ba27dd8d08286cfae`: `candidate/remote_sub.sh:733`
versus `candidate/remote_sub_helpers.py:410,597,679`. The original native status
is terminal failure with no result and null root/parent projection. A before-launch
log does not substitute for any remaining original lease/effect reconciliation.

The exact finding and discriminating controller-test recipe were delivered to
that existing source owner in Mastermind #1674 comment `6315860850`. Its active
source/release and both frozen News requests were left untouched. #1665/#1674
must compose their original release unit; #1681 separately identifies existing
Studio consumer-pin coordination requirements. No installed generation, selector,
manifest or runtime helper was patched to bypass these obligations.

A separate observed Ubuntu0 directory-custody defect was corrected by its owning
UID with a single no-follow descriptor operation: only the group-write bit on
`/home/ubuntu0/lanes/support-releases` was removed, mode 0775 to 0755. Owner/group,
release files, credentials, admission guards and selector remained unchanged;
readback verified the narrower mode. This does not claim the other hosts fixed.

Executive's current read surface is live at v1.5.0 with installed source
`80f384b8f58b7ca46422d9783aa5c0613c7bf4b2`, but reports `readonly`. Its
2026-10-21T12:08:25Z snapshot had zero running Jobs/Attempts. The earlier bounded
summon returned backend_unavailable and no Job. Neither read-side health nor
three existing queued Jobs establishes a writable Harness2 execution path.

The native router separately exposes the established exact-model Grok quota
exception through `cursor-grok-4.6-high`; source `policy_allows` explicitly keeps
ordinary Cursor labor forbidden and admits only exhausted-weekly-Grok tasks with
that exact eligible model. A future actual review must preserve those native
checks, original root, its own identity and real retained return; the route
preview is not a review. No categorical Cursor-labor policy is relaxed here.


## Independent paid source review and first repair

The original request `harness2-crossrepo-grok-0c820ffa-20261021` completed through
the existing qualified Grok quota fallback at 2026-10-21T12:46Z, remote rc0,
native terminal receipt and retained full 9,593-byte result. Native status now
binds the original root and parent `harness2-agentos-evidence-20261021`. The
parent read the complete review and independently reproduced its four material
counterexamples. The report was accepted through the existing native outcome
ledger (`accepted_by=reviewer`, VALIDATED_OUTCOME). That accepts the useful
review deliverable, NOT the source PRs, production readiness, or a merge.
Original controller PID49013 terminated rc0; no worker or polling daemon is
claimed running. Its usage receipt was missing; no zero-cost or measured usage
claim is made. Requested Grok model identity is not independent served-model
attestation.

The independent reviewer inspected core 0c820ffa, Macro c7c12096, named native
EVAL/OHF interfaces and pinned upstream source. It found no incumbent-validity,
cleanup or default-AgentOS corruption, but four material repairs:

1. The importer rejected upstream `fell_back` even though the published method
   can inherit a current harness after an invalid proposal and still produce a
   complete valid selected result. The importer now validates exact unique stage
   labels, returns `inherited_stages`, and retains the original summary as native
   evidence. It does not retry execution, relabel fallback as improvement, accept
   incomplete selection or suppress native effect/cleanup failure. A real CLI
   fixture imports a complete inherited run; unknown/duplicate/malformed stage
   lists refuse and inherited EFFECT_UNKNOWN still finalizes invalid.
2. File identity improperly conflated raw-byte fingerprinting with native text
   eligibility. `harness_manifest` and upstream compatibility fingerprint now
   hash complete raw bytes, including binary assets. The native refinement
   kernel separately applies `validate_native_harness_text` to its current
   admitted text-only experiment surface, before executing a changed proposal.
   This preserves existing native execution restrictions while allowing faithful
   archival import. Binary native-edit experiments are not newly admitted.
3. Legacy seven-field experience entries could omit confidence. Their detached
   model-facing copy now explicitly defaults to `suspected`; provided complete
   provenance retains its original confidence. Caller input is unchanged. A
   confidence-free legacy record never becomes implicitly verified knowledge.
4. The kernel itself now clears `experience_candidate` whenever the selected
   harness equals the common baseline. The draft producer retains its independent
   no-op check. Model reflection may still consume its accounted call, but it
   cannot issue a positive learning candidate from an unchanged harness.

Four semantic regressions failed on the prior source. An added fifth native
text-guard regression initially had an overly specific error/count assertion;
its corrected assertion checks the retained cause and absence of any candidate
execution, rather than confusing a model proposal call with a rollout. Full
core campaign after repair: **881 passed, 27.34s**. This is author verification,
not a second independent approval; repaired source requires exact-head re-review.

The minor review observations were adjudicated separately: the 32-entry
experience ceiling is an explicit native pre-effect input bound, not silent
truncation; the complete input and reason remain available to the caller. Native
selector randomization deliberately uses the caller's declared seed and is not
claimed byte-identical to upstream's task-hash shuffle. CLI graph verification
already prints distinct `validity_status`, `reason_codes`, no-authority/promotion
and returns incomplete for invalid runs; graph association does not mean valid
effects or efficacy. These limits remain explicit rather than expanded here.

## Verified runtime-composition conclusion

The source trace and independent review agree on the real missing interface.
CodexOperatorAdapter already has an owner-controlled `turn_input_loader` and
`observe_raw_role_result`. The latter binds complete canonical JSON to its exact
Attempt/session/generation/native turn, including byte length and hashes; it is
preferable to CandidateResult.summary. It still needs actual prompt, profile,
capability and result-owner admission, not a user-supplied callback.

Protected ExecutiveOperatorSupervisor only admits plan/READ and four reviewed
read-only profiles. The original #1315 current source c4f2dbda provides opt-in
V3/V4 plan production but does not implement the missing nonplanner admission.
#698 e97ef3d2 is a pure claimed read-only provider/profile resolver, also not that
admission. Existing #1421/#1446/#1482/#1484 rich capability compositions explicitly
retain the same gap and original owner boundaries. A similarly named open PR
is not evidence that the required runtime path exists.

The exact consumer needed is an existing-owner, parent/Attempt-bound composition
that seals improve/select/reflect task context into admitted native Jobs, obtains
complete RawRoleResultObservation, and separately observes/retains actual EVAL
execution of each candidate bundle under the fixed scenario/configuration. It
must conserve root/depth/cost limits and genuine workspace authority, retain
missing served-model/capability/source/effect/cleanup evidence, and never use a
planner's grant for a work role. All current production and provider holds stay
in place. Source construction of a wrapper around run_turn cannot close this gap.
No dummy production write or self-signed Trial was attempted.


### Re-review: baseline text-gate regression

The original changed-head review `harness2-rereview-grok-3a2de988-20261021`
completed rc0 at 12:59Z with a retained 5,370-byte report and correct original
root/parent. It independently closed the fallback, confidence and no-op findings,
but caught a real regression in the binary-identity repair: a source edit intended
to check `common_base` had not matched the actual `base` variable. Consequently,
binary H0 could reach the first port execution before a later proposal refused.
The claimed baseline guard was not present; this is corrected evidence, not an
accepted behavior. No real provider or production binary was executed.

A new binary-H0 regression failed on 3a2, then passed after adding the actual
`validate_native_harness_text(base)` call before any effect and a defense-in-depth
check immediately before every `port.execute`. The test binds a real binary tree
and matching native configuration, then asserts an explicit UTF-8 refusal with
zero port calls and no retained trials. Raw upstream binary archival import
remains supported; native execution eligibility remains text-only. Full EVAL
campaign after this repair: **882 passed, 20.75s**. Re-review of this narrow
source repair is still separately required.

The 3a2 candidate was also tested at GitHub's actual current-base virtual merge
`ae4f70644139c4d1b36151fa6ff0f0f0b74b7359` (parents protected7ab47f0b and
3a2de988): 881 tests passed22.84s in a separately manager-acquired review
workspace. This is integration evidence for 3a2, not for the later baseline fix.
The 87-file protected-base delta did not change native EVAL/OHF dependencies;
ACTIVE_EXECUTION's sole relevant change clarifies refusal provenance, which was
read and preserves actual tool/lease/effect fences. Original procedure pin remains
usable. The temporary review workspace was safely released via mmx-workspace
only after removing its exactly enumerated 23 disposable Python3.14 bytecode
files; tracked source remained unchanged, manager receipt REMOVED /
UNCHANGED_FROM_ACQUIRED_BASE. Original source worktrees remain intact.
