# C0 Semantic Falsifier — Phase A Repair Status

`publication_operation: mastermind-codeintel-c0-real-result-publication-20260903-sol-001`
`experiment_operation: mastermind-codeintel-c0-semantic-falsifier-20260830-sol-001`
`canonical_carrier: C0BSBM78V1N/1788475769.871519`
`PR: #375 (DRAFT / HOLD-FOR-SOL)`
`artifact_contract: mastermind.codeintel_c0_result.v2`
`wave_status: DISPOSABLE FALSIFIER / PRODUCTION_INERT`
`return: PROGRESS / PHASE_A_REPAIR_PUBLISHED / PHASE_B_B0_HELD`

> **No C0 decision is currently valid.** The previously published v1
> `DECIDED / NO_SAFE_BACKEND` result is superseded by the controlling repair
> ruling. It must not be used as backend-selection evidence.

## Current state

**`decision_state: NON_DECISION` — `decision: absent`.**

Phase A repairs the falsifier and its artifact contract only. It does not rerun
the real paired experiment, publish a replacement empirical artifact, accept a
backend, create a capability, or authorize Phase B. A replacement decision is
reachable only after every candidate has complete real cold/warm coverage of
the full sample plus protected Terminal matrix and every scored trial scope has
complete executable and dependency identity.

The v1 result was not decision-grade because its artifact could not prove all
of the following:

- whether an execution was real or a stand-in from machine-derived provenance;
- the difference between a launcher/interpreter and the actual server target,
  module, or Serena bundle;
- the exact canonical argv and every argv-file digest for each execution;
- the exact Python package closure and npm package-level `resolved` plus
  `integrity` closure, bound to immutable resolution/provenance manifests;
- a one-to-one execution receipt for every candidate/corpus/language trial
  scope; and
- cold and warm coverage of the protected Terminal `migrateLegacy` case.

Those omissions now produce a typed `NON_DECISION` hold. They can never fall
through to `DECIDED / NO_SAFE_BACKEND`.

## Phase A repair contract

Each v2 execution row and its matching binding receipt now carries:

| Identity plane | Required evidence |
|---|---|
| Launcher | path-free launcher name and SHA-256 |
| Invocation | canonical argv with every argv file replaced by an index/name/SHA-256 token |
| Target | explicitly declared and measured server target/module/bundle SHA-256 rows, bound to ecosystem/package/version and to the launcher, an exact argv-file position, or the independently verified Serena bundle |
| Provenance | machine-derived `real` or `stand_in`, included in the backend identity digest |
| Backend | source version/commit, configuration digest, targets, invocation, and provenance under one recomputable digest |
| Trial scope | exact candidate, corpus id, and language, cross-checked receipt-to-execution-to-trials |
| Python supply chain | expected-digest closure manifest plus remeasured installed-file SHA-256 rows and a canonical per-package tree digest |
| npm supply chain | package name/version plus package-level `resolved` and `integrity`, parsed from an expected-digest lockfile |
| Resolution provenance | measured Python and npm manifest SHA-256 plus canonical closure SHA-256, bound into every execution identity |

There is no launcher-as-target fallback. A real direct-LSP execution without an
explicit measured target cannot clear identity. Each declared target must
resolve to the launcher or to the exact indexed argv file it claims; the Serena
bundle is separately remeasured before startup but cannot substitute for a
launch-selected target. Python target bytes must match a remeasured file or
canonical tree digest in the claimed package coordinate, and npm targets must
name a coordinate present in the expected-digest lock closure.
Launcher, argv-file, target, target binding, dependency-manifest, provenance, or
source substitution changes the backend identity digest. Tampering with the
duplicated execution projection is also refused. Stand-in provenance must agree
with every trial's `synthetic` marker and with the residual-risk disclosure, so
changing a prose note cannot promote synthetic evidence.

The existing JSON-RPC transport remains unchanged. Its tests prove that the
spawned executable and argv equal the bound `ExecutableSpec` invocation and
that launcher plus argv-file digests are verified before launch.

## Protected Terminal source

The Terminal case is derived mechanically from the immutable external Git
object; there is no copied Terminal fixture or committed answer key.

| Field | Protected identity |
|---|---|
| Repository | `mastermindx-market-intelligence/mastermind-terminal` |
| Commit | `fadd8b82f03ecaabe8a86d693da89f27be096d9f` |
| Tree | `2ef6840d07c24456fc39e67029c45131fed53b1f` |
| Path | `terminal/lib/workspaceMigrate.ts` |
| Blob | `3b6feb5295d77cefa4f609b4cbafe5e6a68b5565` |

Materialization first verifies that the normalized `origin` is the named
Terminal repository, then refuses a missing commit, wrong tree, missing/wrong
path, or wrong blob before deriving the `migrateLegacy` case. The source parser masks
comments and quoted text, then derives identifier locations from the verified
blob bytes. The exact protected object is locally resolvable and yields the
live declaration at line 112; this source verification is not an empirical C0
backend run.

The v2 decision matrix adds the protected
`terminal_migrate_legacy/typescript/terminal_migrate_legacy/{cold,warm}` rows
for both candidates. Missing either row is `NON_DECISION`.

## Verification evidence

The authorized C0 test surface is green: 256 tests covering backend contracts,
direct LSP, Serena, the semantic facade, runner/schema/cross-checks, ground
truth, decision law, and the unchanged JSON-RPC transport. Discriminating
controls prove refusal of target substitution, target/invocation mismatch,
Python target/package digest mismatch, package-closure deletion, Terminal pin
substitution, receipt/trial mismatch, and synthetic provenance promotion.

## Hold and effects

| Plane | State |
|---|---|
| Source | bounded Phase A repair on existing PR #375 |
| Result | prior v1 decision superseded; no v2 empirical result published |
| Review | independent exact-head review required after repair publication |
| Phase B / B0 | **held** pending review `ACCEPT/APPROVE` and a new controlling Sol command |
| Remote | Draft / HOLD-FOR-SOL; no Ready; auto-merge absent |
| Merge/deploy | none |
| Installation/profile/service | none |
| Market/trading/production | none |

The quarantined predecessor worktree was not opened, read, cleaned, reset,
reused, cherry-picked, salvaged, or used to infer commit content.
