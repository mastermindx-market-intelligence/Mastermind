# Routing source CI evidence repair

Operation `fabric-routing-deep-audit-20261013-c2-001`; existing PR #1443 and branch. Compatible protected procedure pin `76576d8680bb70cdb9e1cfe7016aefec0fb3286f`. Source repair only; no native installation or provider execution.

## Observed failure and cause

CI run `38676847597` for source `d47c54a46e7e20baa42d18c0a12f8eef09c2a0db` completed with failure. Test job `116232367236` passed compilation and shell validation, then failed the repository test gate. The reported failing test was `tests/test_ceo_submit_armed_composition.py::test_d8_template_topology_and_protected_defaults`: its unchanged identity scanner returned `['400']` instead of `[]`. The job checked merged source `5767e8672af7c4521e08e56720c582625687ff3e` against base `b89bcff184c78461bb6af83267e927bc5574d83b`.

The literal is the count of synthetic capacity combinations in the new account-balance manifest, not an OS identity or runtime default. The source scanner treats that manifest's identity-bearing path conservatively. Its existing `research/evidence/*.json` route deliberately performs structural identity checks while allowing ordinary measured quantities.

## Change

Move measurement-only verification values into `research/evidence/fabric_routing_validation_20261015.json`, with units, original source/report/blob provenance and the same numeric values. The source manifest retains a SHA256-bound evidence reference and all release gates, source/patch hashes, selection rules and effect limits. The 400-case measurement remains a numeric 400; it is not removed, disguised as an expression, or presented as additional tests. Existing source code and the security scanner are unchanged.

Add 15 focused regressions using the existing guard functions. On the original manifest, two checks fail and 13 pass. With the evidence split, all 15 pass in an isolated diagnostic using the unchanged source/evidence classifier functions retrieved from the source revision. Controls continue to reject real identity value 400 under UID/account/owner fields, malformed/duplicate evidence, and wrong-path evidence. Repository CI imports the real complete guard module and must separately qualify the full changed-file scan; this local check is not a full CI result.

No original denied host inspection or native fixture/preparation action was retried. The original native suite remains 49 passed/one disclosed GLM fixture failure; the earlier 89 source checks remain accepted evidence, not newly rerun or production proof. No routing implementation bytes changed in this phase.

## Next action

Consume the new exact-head hosted result while advancing independent current-source integration assessment. Existing independent review remains unreturned. Preserve native source writer, neighboring #1365/#1441 changes, old stale M2 workspace, and original action holds. Full native integration/regression, protected acceptance, compatible installation and original-parent execution/return remain unfinished.
