# A2 host-factor boundary repair

Date: 2026-09-17. Operation: `harness-convergence-a2-boundary-repair-20260917-sol-001`.
Carrier: existing Mastermind PR #692 / `sol/agent-eval-host-factor-lock-20260916`.
Parent: harness-convergence research #687; no replacement program or carrier.
Disposition: source-only repair candidate; not shared-owner adoption or production acceptance.

## Mission and assignment

The current Chairman appointed Sol to recover and lead the orphaned harness
convergence project and then directed continuation of #692's bounded repair.
Recover a useful evidence comparison without weakening the evaluation core or
building a second host validator. The wider Fable Agent Evaluation program and
its organizational records remain with their incumbent owner. This record does
not assert Fable approval, independent review, runtime admission or worker START.
The source authorization and exact-path decision are recorded on #692 at
issue comment 5710543606. Implementation publication is not protected law.

Governing protected source: `42d210bc07a75234092ff5be71f6038ccacaa884`, compatible
Skillpack 1.0.1 / bootstrap 1. Recovered candidate:
`f4bcccfa5166640e5f6874b3dde8d67f772ff391`. The evaluator core, its inertness
fence, the Executive host-contract dependencies and the environment-free amendment
are unchanged between the candidate base and that protected source.

## Root causes

The old candidate's nine focused tests passed, but full repository CI failed:
its evaluation-core module imported `control_plane.executive_host_capacity`,
and neither newly added file was within the explicit per-wave source fence.
The former violates the environment-free core boundary; the latter is a real
missing wave admission, not an unrelated-PR false positive. Repeated unchanged
CI, import exemptions, scope skipping and copied validators are rejected.

## Bounded design

Move the one host-specific composition to
`scripts/agent_eval_host_factor_lock.py`, an explicit outer integration module.
Its functions and narrow result remain unchanged. It uses the canonical
Executive host validator/canonicalizer and the existing run-receipt validator.
No new parser, host identity, snapshot schema, artifact store or lifecycle exists.
No module or CLI inside `scripts/agent_eval/` may import this bridge, and the
old unmerged core path is removed without a compatibility shim.

The core's unconditional import ban and complete production-file discovery stay
unchanged. A separate bridge test covers its exact pure Executive dependency
closure, including the package initializer, and tests import/call behavior under
an environment-read refusal and network/process audit hook. Relocation alone
without that coverage is insufficient.

The only exact-path scope additions are the outer bridge, the retained
`tests/test_agent_eval_host_factor_lock.py`, and this source plan. The existing
`tests/test_agent_eval_inertness.py` already belongs to the admitted surface.
The test remains classified as Agent Eval work; foreign siblings and all
control-plane/config/workflow changes remain rejected. No prefix is widened.
Sol authorizes that bounded source candidate as recovery principal for this
harness lane, not a transfer of the whole Agent Evaluation program. Shared-owner
adoption and the outstanding independent review remain separate release gates.

## User and machine journey

An evidence consumer explicitly invokes the outer bridge with two distinct finalized
run receipts and their exact snapshot mappings. The bridge checks each run's existing
immutable digest, uses the Executive contract to validate/canonicalize snapshots,
checks that each run binds exactly one copy of its snapshot digest, and compares
opaque host and boot references. It returns the existing bounded evidence-only
verdict or existing structured refusal; it writes nothing and starts nothing.

Missing, malformed, duplicated, tampered or mismatched evidence, including a
repeated finalized run identity on both sides, never defaults to equality.
Untrusted snapshot values are not echoed in the bridge's public error message. Later correction creates new canonical evidence; it does not
rewrite a finalized run or re-age an observation. Snapshot validity is structural
and content-addressed: it is not proof of origin or process execution location.

## Ordered implementation and acceptance

1. Add failing boundary/closure/scope regressions before moving production code.
2. Relocate the bridge and its test import; preserve all existing verdict semantics.
3. Add the exact per-wave paths; preserve unconditional core and forbidden-path guards.
4. Run all existing and added factor-lock tests, including a repeated-run-identity
   refusal, evaluator-core tests and owner host-contract tests. Check the real
   committed delta, not a mocked empty diff.
5. Demonstrate that removing wave admission, restoring a forbidden core import,
   or adding ambient observation is caught by the intended tests.
6. Check current-base material compatibility and integrated source. Publish only
   to the existing PR branch with a normal fast-forward, then consume exact-head
   repository/security review before any release decision.

A passing unit suite proves only this bounded integration. A finalizer accepting
a digest is not attestation that the run process executed on that host. Preserve
`HOST_FACTOR_EVIDENCE_LOCK_VERIFIED`; never emit process-host, model-effect,
harness-effect, global-winner, routing or promotion authority from this bridge.

## Scope, failures and continuation

No provider/model run, DSH install, secret/realm access, holdout generation or
exposure, host registry, Executive Job, production route, canonical Agent OS
mutation or deployment is included. The eight research artifacts on #687 and
prior test evidence are do-not-redo unless material source changes.

An unexpected source writer/head change or unknown modifying result stops the
same carrier for reconciliation. A shared-owner objection or required wider
source law returns to Sol; never fix it by excluding a module or guard.
The phase ends at an exact source-and-test checkpoint, not harness completion.
Next: consume this repair's current-head checks and owner/reviewer returns on
#692, then continue the existing #687 environment/backend qualification DAG.


## Executed repair evidence

The source repair commit `891a50f6cca878f778276a40949eee9306d75c25` was exercised
on the managed MacBook with CPython 3.12.14, pytest 9.1.1 and PyYAML 6.0.3.
Four new boundary/scope tests were first RED against the original candidate.
The repaired focused suite is 15 tests; the combined evaluator and two pure
Executive host-contract suites are 787 tests, zero failures/errors/skips.
Command family: `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
<isolated-python> -m pytest --noconftest -p no:cacheprovider -q
 tests/test_agent_eval*.py tests/test_executive_host_capacity.py
 tests/test_executive_host_pressure.py` (continued as one argv list).
The explicit `--noconftest` excludes unrelated global repository fixtures;
this is full execution of those selected modules, NOT full repository CI.

Three temporary mutations each failed the named boundary test: removing exact
wave admission, removing the core control-plane import ban, and adding a bridge
ambient environment read. Original bytes were restored in all cases and the
15-test focused suite passed again; the worktree was clean. AST comparison
against the recovered candidate proves the relocated algorithm/imports are
unchanged except for the module documentation. Full hosted CI, current-base
release proof, independent review and shared-owner adoption remain separate.

## Repeated-run identity repair — 2026-09-19

Exact prior head `a5ad195e224cacb364862e4987f669b2bb3f261e` accepted the
same immutable finalized run as both comparison sides and returned
`HOST_FACTOR_EVIDENCE_LOCK_VERIFIED`. The added regression was RED there with
`DID NOT RAISE ContractError`. The bounded repair rejects equal `run_id` values
with `HOST_FACTOR_RUN_DUPLICATE` after each side's existing run/snapshot binding
has validated and before host/boot equality can return success.

The repaired branch worktree passes the 16 focused host-factor tests and all 788
selected Agent Evaluation plus pure Executive host-contract tests. Python compile
and `git diff --check` pass. This is source evidence only; current-base integrated
execution, fresh hosted checks, independent review and shared-owner adoption
remain separate gates.
