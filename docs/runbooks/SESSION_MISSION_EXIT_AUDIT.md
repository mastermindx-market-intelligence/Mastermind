# Mission-exit proof-gap audit (read-only source candidate)

## Purpose

Prevent one recurring false-completion pattern: a terminal zero-exit analysis worker is
mistaken for accepted code delivery, or a successful CI/review from an unchanged head
is mistaken for the remaining commercial/production evidence. This is a bounded,
secret-free, standard-library diagnostic over an **operator-collected snapshot**.
It adds no owner, queue, retry, session, clock, autonomous watcher, permission,
credential handler, or publication right.

Current organizational owners remain Executive OS (Job/Attempt/consumption), Fabric
(result/acceptance), GitHub (source/CI/reviews), Agent OS (project continuity),
ProviderRealm (issuer attestation), and the original effect carrier (denial/unknown).

## Run and interpret

From the Mastermind repository root:

```sh
python3 -m scripts.ohf.mission_exit_audit research/fixtures/mission_exit_byteplus_20261101.json
```

The sample is a *historical illustration* of the November 1 BytePlus incident, not
live owner data, not a synthetic acceptance receipt and not an automatic status
refresh. It deliberately shows an unaccepted terminal analysis result, unchanged
source, CI/current-head MiniMax review already passed, and the exact denied source
write kept on hold. The script exits 1 for incomplete proof, 0 for a packet ready
for external canonical adjudication, and 2 for invalid/unreadable input.

No return value authorizes a source write, retry, account fallback, merge, spend,
START, approval or production activation. The caller must read current canonical
owners and apply the platform's existing authorization and effect fences. The
`held_actions` section never supplies a replacement execution carrier. A new task
may proceed only if genuinely independent in target, authority and effect, as
already determined by current protected law.

## Lane and exit-claim discrimination (2026-11-02)

An optional `lanes` snapshot section classifies the **claimed session exit**
against observed lane state. It exists to separate three outcomes that static
summaries conflate:

1. lawful **continuation** while a lane-local `WAITING_EXTERNAL` (pending review,
   CI, capacity, owner reply) blocks only its own lane and a safe independent
   lane remains (`CONTINUE` claim);
2. a **premature exit** that ends on a status/checkpoint/CI summary, or ends to
   wait without a real accepted/started durable executor with a lawful return
   path (`CHECKPOINT_SUMMARY_STOP` / `WAIT_EXTERNAL_EXECUTOR` claims); and
3. the lawful **all-lanes stop or safety/effect-unknown fence**
   (`ALL_LANES_BLOCKED_STOP` claim with every scoped lane evidenced as blocked,
   including source-attributed `WAITING_EXTERNAL` review/CI dependencies or
   `BLOCKED_PROVEN`, and `FENCED` holds bound to the exact original effect).

Two support/status-only cycles without a capability delta report
`no_delta_loop_forces_tactic_change`. The flags are read-only classifications of
supplied observations; they authorize nothing and are not served-model proof.
Snapshots without `lanes` keep the exact incumbent output.

### Owner-only handoff is not continuation

Use `OWNER_HANDOFF_STOP` when a session proposes to finish because the next
step "requires the original owner", "release owner", "reviewer", or another
role without proving an actual reachable receiver and completed handoff or
lawful original-carrier operation. The existing lane inventory still identifies
what is safe to execute. The audit reports
`owner_only_handoff_is_not_continuation: true` and
`premature_exit_detected: true` even if every listed lane is observed as
`WAITING_EXTERNAL`. A premature claim also forces `disposition: INCOMPLETE`
and CLI exit 1 even when every separately enumerated proof gate is present;
`READY_FOR_CANONICAL_ADJUDICATION` requires both proof completeness and a
non-premature exit. An owner name is not a START, runtime binding, GitHub
approval, transfer receipt or a session that will wake. The assigned session
must reconcile any live writer/lease and effect, act on permitted source,
review diagnostics or qualified release steps, and preserve genuine permission,
security, credential and protected-queue gates. This is diagnostic only: it
cannot appoint a successor, authorize self-approval, or perform a release.

### Evidence for lawful exit claims

An enumerated `lanes.items` list alone is not proof of completeness. A
mission-wide blocked stop or executor-only wait requires `scope_evidence`:
`source_ref`, `owner_readback_ref`, immutable `source_revision`,
`source_observed=true`, `all_dependencies_checked=true`, and
`canonical_lane_ids` equal to the enumerated lane IDs. Operators must verify
the existing Agent OS/GitHub/Executive owners independently; these fields
cannot create authority.

A `WAITING_EXTERNAL` lane needs `blocker_ref`, `blocker_owner_ref` and
`blocker_observed=true`. `BLOCKED_PROVEN` additionally requires a verified
negative capability, while a `FENCED` lane must match its exact held action
and original carrier. Independent ready work defeats all-lanes-blocked.

`WAIT_EXTERNAL_EXECUTOR` requires a genuinely started executor with
`ref`, `return_path_ref`, `owner_observed=true`, and `lane_id` naming an
existing `WAITING_EXTERNAL` lane. A historical START alone is insufficient:
`state` must currently be `STARTED` or `RUNNING`, with source-attributed
`state_ref` and `state_observed=true` from the incumbent owner. Terminal,
failed, canceled, unknown, queued, or absent current state leaves the worker
wait unverified; the read-only classifier never assumes a watcher or queue
is a live executor. The executor `ref` must equal the lane's
observed `blocker_ref` when that identifies the awaited run. If the blocker
is a separate receipt, the lane may supply an explicit `executor_ref`,
`executor_binding_ref` and `executor_binding_observed=true`; the executor
`ref` must equal that source-attributed bound ID. An unrelated worker
cannot justify this exit, regardless of START or a valid return path.
This diagnostic does not itself verify runtime START or owner identity.

`CHECKPOINTED_CONTINUATION` instead needs a canonically persisted,
read-back cumulative `checkpoint`, with revision, receipt, observed genuine
continuity risk, next action, resume surface, effect accounting, preserved
custody and incomplete mission. It does not require a running worker.
`CHECKPOINT_SUMMARY_STOP` is never continuation just because another
executor has started. The result is diagnostic, not release authority.

Sanitized realistic sample (November 2026 Prophet A2 settlement-preflight shape:
142 local test passes, the requested 145-test guard suite not staged, independent
review unreturned, hosted exact-head CI pending — the observed session exit was a
checkpoint/status-summary stop):

```sh
python3 -m scripts.ohf.mission_exit_audit research/fixtures/mission_exit_prophet10289_20261102.json
```

It must report `premature_exit_detected: true` with `all_lanes_proven_blocked:
false` — local test passes and a summary do not close the staged guard tests,
review, or hosted-CI gates. Served-model behavioral evidence for the matching
evaluator packets (SXA01–SXA07 in `research/fixtures/mission_exit_behavior_cases_20261101.json`)
remains with the existing fresh-Sol evaluation owner and is a separate, unmet
adoption gate.

## Consume pending work instead of duplicating it

The existing `gaps[].next_proof` now uses the supplied observation state:

| Observed gap | Guidance |
| --- | --- |
| Exact-head CI is QUEUED, PENDING, IN_PROGRESS, WAITING or REQUESTED, with its original run reference | Consume that run through its original observation path; no rerun or empty push. |
| Exact-head CI is FAILURE, CANCELLED, TIMED_OUT or ACTION_REQUIRED | Inspect the original result before a permitted repair; no blind retry. |
| CI identity/state is absent or unrecognized, or its conclusion is STALE, SKIPPED or NEUTRAL | Reconcile identity and required status with GitHub; these observations do not establish a failed build. |
| Eligible independent review is REQUESTED or PENDING on the exact head | Reconcile its actual original carrier and verify no START/unknown effect, then any eligible independent non-author may complete it; never bind acceptance to a historical reviewer session or duplicate started work. |
| An independent review is genuinely IN_PROGRESS on the exact head | Consume that active review on its original carrier; do not reroute or duplicate it. Execution is not approval. |
| Current independent review requests changes | Repair the findings in one stable source revision before renewed review. |
| Worker is QUEUED, STARTED or UNKNOWN | Reconcile the original worker; do not submit a replacement. |
| Worker is TERMINAL | Inspect/validate its original result and effects; exit zero is not acceptance and does not justify a relaunch. |

These values use the existing `source.ci_conclusion`, `source.review_verdict`
and `worker.state` fields; no new schema, observer, clock or scheduler is added.
The auditor cannot authenticate a caller-supplied snapshot or prove it is still
current. Stale/missing references and unknown or self-review identity never
become an eligible pending review. All proof predicates, held-action fences,
false authorization flags and CLI exit meanings are unchanged. Output guidance
uses fixed text and never echoes source references or private input.

## Integration sequence and boundaries

1. Source tests + exact-head CI and independent review of this diagnostic.
2. Use the existing fresh-Sol/served-model evaluation owner to test realistic
   BytePlus-like scenarios: terminal analysis vs implementation, safety denial
   vs other independent work, current-head review invalidation, blocked provider
   versus session completion. Record actual served-model outcomes, not static
   source-test passes.
3. Integrate this helper's **read-only proof-gap shape**, if accepted, into the
   incumbent Executive/OS owner that already renders mission progress; do not
   create an alert daemon, second acceptance registry or independent task queue.
4. Release through the existing source/installation owners and prove three live
   interrupted/normal missions with zero lost/duplicated effects, verified
   original-parent consumption, and lower false-stop rate versus baseline.

This slice implements **Step 1 source candidate only**. It does not repair the six
BytePlus P2 findings, assign a commercial credential owner, run a billable canary,
restart a source writer, or resolve the earlier platform safety refusal.
