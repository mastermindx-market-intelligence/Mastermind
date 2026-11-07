---
name: mastermind-ci-triage
description: Diagnose a failing or slow Mastermind CI validation, merge-group check, flaky test or order-dependent test using the exact repository, head, run and job. Use for CI failure triage, deterministic test isolation and measured shard bottlenecks. Do not use for a generic code review, unrelated product incident, or an unchanged queued run.
---

# Mastermind CI Triage

## Work inside the current assignment

Reuse the verified Mastermind source pin and applicable repository instructions; do
not restart full bootstrap for each observation. This method supplies no runtime,
tool grant, release approval or trade authority. Keep denied actions denied and
EFFECT_UNKNOWN on the original operation and carrier. Continue independent safe
work instead of widening access or retrying an uncertain effect. Use existing
Executive/Fabric, Agent OS, source, browser and deployment owners, not replacements.

## Bind the failure

Record repository, PR or merge group, immutable head, workflow/run/attempt/job,
failed step, first failure signature, runner environment and timestamp. Read the
actual logs through the available source owner. A pasted tail is a clue, not a
complete result. Redact credentials, private payloads and tokens from evidence.
Missing run identity permits source investigation but not claims about that run.

Separate queue wait, setup, dependency work, test execution and teardown. Measure
wall time and critical path separately from summed parallel job time. Compare like
workflow events and runner/cache conditions. Never infer six usable shards from
six files or from idle hosts alone.

## Diagnose before changing the candidate

1. Classify evidence as test assertion/regression, order or state leakage,
   nondeterminism, dependency/environment, resource failure, infrastructure, or
   unresolved. A timeout or a later green run is not proof of flakiness.
2. Reproduce the smallest discriminating case at the exact candidate. For suspected
   order dependence compare the failing test alone, with its predecessor, and in
   the observed order. Inspect shared globals, environment, cwd, import state,
   files, ports, database rows, clocks and random seeds.
3. State a falsifiable cause before editing. Change one causal boundary and add a
   regression test that fails on the old behavior. Keep public behavior covered;
   do not merely update expected output to the observed bug.
4. Repair the smallest owned scope. Use fixture teardown, explicit isolation,
   deterministic test data or appropriate dependency repair. Do not mask failures
   with sleeps, broad exception handling, weaker assertions, removed tests,
   unexpected skips or relaxed security/branch checks.
5. Run the targeted reproducer, its interacting group, and the required relevant
   suite. Record commands, exact revision and actual results, including skips or
   collection failures. Local green is not hosted or merge-group green.

Read [diagnostic cases](references/cases.md) when selecting a reproducer.

## Preserve delivery semantics

Keep one existing exact-candidate observer. An unchanged queued run needs no new
poll loop or push. Use a bounded same-owner status read at a real integration
boundary when no observer can supply the result. A changed head invalidates only
affected evidence; never relabel an old review or CI run as proof of the new head.

Rerun or cancel only through the authorized owner for that exact run. An explicit
permission denial is not a request to use a different tool. Respect the actual
cooldown and retry policy; do not install another watcher. Preserve every test,
required security check, branch protection and required merge-group validation.

## Return a repair, not just a diagnosis

Return exact failure identity; observed evidence versus hypothesis; minimal
reproducer; causal fix and regression; test commands/results; remaining hosted,
review and release gates; and the next concrete action. Include before/after
critical-path measurements only when comparable observations exist. A source fix,
green CI, merged code and user acceptance are different claims.
