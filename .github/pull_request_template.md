Workstream: REQUIRED
Linear: REQUIRED
Portfolio-Mode: REQUIRED
Wave: REQUIRED
Authority: REQUIRED
Completion: REQUIRED

<!--
MAS-28 V1 canonical authoring grammar. The six contiguous lines above are the strict
header zone: replace every REQUIRED token with one concrete allowed value before a
report can be interpreted. This template is an authoring aid, not execution authority.

Allowed values:
- Workstream: WS:<KEY> | NONE
- Linear: MAS-### | NONE
- Portfolio-Mode: tracked | maintenance_exception | creates_workstream | architecture_candidate
- Wave: a non-empty bounded identifier
- Authority: implementation | records | research | maintenance | proof | deploy | architecture_candidate
- Completion: merge-is-done | built-not-proven | proof-required | acceptance-required | records-only

Use an exact canonical WS key—never fuzzy-match by title. Workstream: NONE is valid
only for an explicitly typed maintenance or architecture-candidate change. A PR may
not self-authorize a successor phase, production arming, Wake, or worker execution.

MAS28-V1-CONTRACT-SHA256: 9c57ad499fa34ee32f0ffeb9f2f5928f0515dba1609f984e5a20ce6576e7f75e
MAS28-V1-RULESET-SHA256: 2e97ad7acd0aec77ef18dbd76a1b3f2bbf8b7d4585e938498615de1917aa71aa

Native relationship law: `Fixes`/`Closes MAS-###` is permitted only when
`Completion: merge-is-done`. For every other completion class, use `Refs MAS-###`
or the issue URL; merge must not erase proof, natural-time, independent-review, or
acceptance obligations.
-->

<!--
Keep this description proportional to the change. Fill applicable sections only.
A small source or documentation repair does not need a new project plan, authority
ceremony, full local test suite, independent reviewer or deployment solely because
this template mentions them. Actual source law, required CI, repository rules,
CODEOWNERS and explicit holds still apply.
-->

## Change and outcome

<!-- Explain the concrete problem, what changes, and the resulting behavior.
Link the existing issue/plan when useful; do not duplicate its entire contract. -->

## Verification

<!-- List relevant checks actually run and their results, reused evidence, and
material limits. Run the smallest useful local checks while iterating and preserve
mandatory hosted CI. Add security, failure/recovery, accessibility or real-path
proof only where the change or assigned outcome needs it. Do not report unrun
tests, requested reviews, pending CI or fixtures as completed acceptance. -->

## Release and remaining work

<!-- State any actual hold and next action. Source-only changes do not require a
VPS restart. When runtime rollout is assigned and authorized, release through the
existing protected path using this operation's exact merged commit and verify the
affected consumer. Merge is not installation or production proof.
A review-only assignment does not authorize release. A broader delivery assignment
continues through its next safe authorized step; creating this PR is not a stop. -->

## Author check

- [ ] The six header fields identify the real scope; existing writers and unknown effects are preserved.
- [ ] The scoped diff and relevant verification were inspected; secrets, runtime state and backups are excluded.
- [ ] Required CI, actual approvals and release holds remain enforced; no self-approval, self-merge or bypass.
- [ ] Remaining work and its next executable action are accurate; deployment is included only when owed.
