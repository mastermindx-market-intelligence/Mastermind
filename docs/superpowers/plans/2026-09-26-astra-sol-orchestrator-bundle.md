# Astra/Sol Orchestrator Bundle Implementation Plan

> For agentic workers: use superpowers:executing-plans. Follow the tests-first steps below.

**Goal:** Make both principal coordinator roles deliverable as a complete optional Codex
bundle without changing global defaults or granting recursive execution.
**Architecture:** Extend #981 through new paths only. A pure source snapshot feeds one
read-only inspector and an explicit, no-overwrite installer. Codex consumes the profile
and standalone roles; existing Executive owners retain every execution gate.
**Tech Stack:** Python standard library, TOML, pytest, installed Codex 0.154.0 parse probe.
**Spec:** `docs/superpowers/specs/2026-09-26-astra-sol-orchestrator-bundle-design.md`.

## Global constraints

- Same operation, source workspace and Studio Direct carrier throughout this slice.
- #981 exact parent remains untouched; #633 DCR effect remains frozen.
- One native coordinator; no recursive native children; no provider or auth invocation.
- Default command is read-only inspection; no overwrites, auth files or global config edits.
- Build source; do not activate a candidate awaiting review.

## Review focus

- Destination conflict late in the bundle: refuse before creating any earlier file.
- Source mutation between inspection and application: digest mismatch refuses before writes.
- Symlinked source/destination component: refuse, never follow into another tree.
- Partial publication/interruption: preserve completed files and explicit uncertainty.
- Inherited parent permissions: read-only file content never substitutes for runtime proof.

## Task 1: Complete role bundle and installer

Files: add `ops/codex_fabric/mastermind-orchestrators.config.toml`,
`ops/codex_fabric/agents/l2-astra-ceo.toml`, `ops/codex_fabric/orchestrator_bundle.py`,
`tests/test_codex_orchestrator_bundle.py`. Consume existing `agents/l2-sol-ceo.toml` unchanged.

Interfaces: `inspect_bundle(codex_home, *, source_root=SOURCE_ROOT) -> dict`;
`install_bundle(codex_home, *, expected_bundle_digest, source_root=SOURCE_ROOT) -> dict`;
`configuration_overrides(codex_home, *, expected_bundle_digest, source_root=SOURCE_ROOT) -> tuple[str, ...]`.
`BundleError` carries a fixed error code and exact completed relative paths, never content.
Receipts contain bundle/file digests and `execution_authorized=false`.

- [x] Write behavioral tests for complete role projection, default inspect, install, repeat,
  conflict/no partial overwrite, source drift, symlinks, malformed roles, interrupted
  publication, and CLI error/exit behavior. Verify they fail because the implementation is absent.
- [x] Add the two source TOML files and implement the snapshot/inspection/install contract.
- [x] Run the new tests and all #981 source policy tests; repair only evidenced defects.
- [x] Probe native Codex against a temporary credentialless home containing the new bundle;
  prove parsing and principal instructions, not model execution or recursive authority.
- [x] Inspect the real attended home without writing. Publish exact source/test receipts
  as a stacked Draft child of #981, and persist the remaining R2/R3 frontier.

## Execution record

Direct implementation rationale: PRINCIPAL_JUDGMENT for the capability/authority boundary;
NO_ELIGIBLE_PRE_EFFECT_WORKER for this unqualified native-hierarchy change. The current
session performs the bounded source slice; no Fable or hidden worker is dispatched.
The generic planning playbook does not add a second approval ceremony to the current
Chairman-authorized plan/build cycle (protected ACTIVE_EXECUTION). Release gates remain.

### Evidence and implementation rulings

The first 24 behavioral cases failed before implementation. Three added regression
cases exposed optimized-Python validation bypass and root/role-directory rebinding;
all were repaired under tests. Three effective-override cases failed before their
compiler existed. A boolean-vs-integer contract case and CLI-output case failed
before their corresponding repairs. Native qualification exposed trusted-project
precedence; explicit command-line settings preserve the intended one-child limit.

Final focused command runs all five inherited client modules plus both new modules,
with the native probe explicitly enabled. Result: 125 passed. The repository-pinned
PyJWT dependency is installed only in an isolated test environment. No full-repository
CI, independent review, live role selection, child permissions or provider execution
is claimed. The new utility adds no runtime owner. The sole #981 reviewer remains
undisturbed; this stacked source child requires its own exact-delta review.

## Task 2: existing attended-launch integration (R2A)

Scope: modify the existing ops/codex_fabric/attended_parent.py consumed from
#1000, add tests/test_codex_fabric_orchestrator_launch.py, extend native parser
coverage and this same source/evidence/continuation record. Keep dependency source
branches and #633 auth frozen. Direct rationale: PRINCIPAL_JUDGMENT for the joined
capability boundary and LOWER_TOTAL_OVERHEAD for its small implementation seam.
Current Chairman continuation supplies implementation intent; no second procedural
approval is added. Existing independent-review and deployment gates remain.

Interface: prepare_launch(..., expected_bundle_digest: str | None = None).
LaunchPlan carries optional exact bundle digest and effective Codex home. The
existing main adds --orchestrator-bundle-digest and revalidates before os.execv.
Default native-disabled behavior must survive #981's profile addition. No new
launch command, identity owner, auth flow or permission service is introduced.

- [x] Prove old and joined profile normalization; reject unknown roles and bool/int drift.
- [x] Add failing integration tests for exact digest/home, complete installation,
  five-tool composition, held auth, no preflight effect and pre-exec input drift.
- [x] Implement only the existing launcher seam using configuration_overrides.
- [x] Exercise the complete prepared argv with native credentialless Codex; verify
  two slots and principal instructions under trusted-project configuration.
- [x] Run the joined regression set, capture exact source proof, publish the same
  PR and update the existing canonical Agent OS handoff.

Review focus: effective-home mismatch; partial/tampered roles; source drift during
census and between preparation/exec; inherited sandbox/config precedence; held auth
must never be promoted by optional coordinator selection.

R2A verification: 170 tests and 25 subtests passed across the joined nine-module
client suite, including the installed Codex probe. Initial integration exposed 12
legacy-launcher failures and 19 missing-feature cases; subsequent regressions caught
same-path home replacement and unhandled native unknown auth. Both were repaired.
A native test fixture initially replaced only Python's environment mapping; it now
sets the actual process environment so native children use the isolated home. The
MCP-initializing diagnostic is explicitly distinguished from parent-only rendering.
No live bundle installation, credential helper, model turn, RuntimeBinding change or
worker dispatch is claimed. Old hosted CI was green for both source inputs; new-head
full CI and independent review remain release gates, never inferred from local tests.

## R2B: native coordinator machinery qualification

The next bounded proof drives the installed Codex binary through the existing OHF
AppServerClient with scripted loopback Responses events in a temporary, credentialless
home. It observes real native child creation/model routing/role and tool ceilings,
without a real model service, Executive Job, installed-user-profile change or DCR
operation. The fixture is test-only; it is not a provider, supervisor or admission route.
Use source-owned roles unchanged first. Repair only a reproduced integration defect.
The source canary must never be reported as real Astra/Sol reasoning, authenticated
Executive submission or end-to-end acceptance. Preserve all existing reviews/holds.

- [x] Prove deterministic loopback protocol and actual native tool schema.
- [x] Exercise named Sol/Astra child creation and read exact native metadata.
- [x] Exercise descendant/permission negatives, preserving any unsupported capability.
- [ ] Publish exact source/proof and update the same canonical continuation.

R2B result: both native role/model routes and exact-parent return work with scripted
Responses; the child sandbox denies the test-project write. Role-local native-disable
and max_depth do not constrain recursive spawning on the observed binary. The
single-child cap is the actual tested guard. Do not repair the negative test into
a false positive or broaden live capacity. The fixture also now closes its listener
when source setup fails; the cleanup regression failed before that repair.

CI R2A run 36288753172 failed in test_cli_receipt_is_deterministic_and_secret_free:
the two reads returned 0 then 1. The validator deliberately rejects changes to its
supplied root inventory; deterministic interleaving in a disposable copied package
reproduced this same failure class. The exact concurrent hosted writer was not logged.
Repair only that test's input ownership: copy current package inputs to its existing
pytest tmp_path, retaining the real CLI and all assertions. No validator or pipeline
policy changes. Open #916 touches only an adjacent numeric-alias count in that file;
its changes and #535 remain untouched. Full new-head CI is still required.

R2B verification: 178 focused client tests and 25 subtests passed, with all native
fixtures enabled; 106 plugin-package tests passed separately. Exact commands and
source/native-entry digests are in continuation_r2b of the existing evidence file.
Source syntax compilation and input-digest recheck passed. No new-head full CI or
independent review is claimed.
