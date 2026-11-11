# Exact Ubuntu host sparse-helper release preflight — 2026-10-15 UTC

**Verified by direct read-only original-host device probes.** No source checkout changed, no task started, no lease acquired, no privileged OS profile/BIOS control invoked.

| Host | Macro donor source Git blob | `fabric-mint` supported | Config sparse enabled | Original checkout directory | Free disk (GiB) |
|---|---|---|---|---|---:|
| ubuntu0 | `296e47bab2d28f9a019e81b5aef76eeea62a6cc3` | **No** | Yes | `~/lanes/wt` | 316.01 |
| ubuntu1 | `296e47bab2d28f9a019e81b5aef76eeea62a6cc3` | **No** | Yes | `~/lanes/wt` | 287.06 |
| ubuntu2 | `296e47bab2d28f9a019e81b5aef76eeea62a6cc3` | **No** | Yes | `~/lanes/wt` | 258.54 |
| ubuntu3 | `296e47bab2d28f9a019e81b5aef76eeea62a6cc3` | **No** | Yes | `~/lanes/wt` | 341.90 |

All four physical hosts have the shared Macro donor Git repo at `~/lanes/repos/macro` and valid `config/sparse_worktree.json` excluding `data`, `site`, `mockups`, and `verify_shots`. The installed helper is **still the base/main version** with blob `296e47...`; not one host has the exact reviewed PR #9194 helper blob `620927823770362b5c1d1e0dec6584612624d848` or a `fabric-mint` command.

**Hard release invariant:** The staged combined Fabric sparse/CPU-scope candidate [combined patch](FABRIC_COMBINED_SPARSE_AND_CPU_SCOPE_20261015.patch) pins the reviewed `620927...` helper. If installed while hosts retain `296e47...`, the prelaunch helper verification **must refuse** new sparse opt-in; it must never fall back to an unbounded full checkout or attempt global force-reset of original Macro repos. Installing the source candidate or opening a PR is not a producer/worker activation.

## Current CI-source issue

Macro draft [#9194](https://github.com/mastermindx-market-intelligence/macro/pull/9194) source head `7d36fc9d427545329b5daecd942e49778de95989`: the targeted guard workflow `38531188701` succeeded. The full legacy CI workflow `38531188805` ended failed: its only direct failing pack was `ci-pack-0` (`115744022447`), exact test `tests/test_ci_pack.py::test_exclusive_curation_narrows_ordinary_code_prs`, with **1 failed, 643 passed, 1 skipped** in that pack. The fail concerns existing template/build/Prophet CI job selection, not the sparse helper tests. Current main has since changed the curation baseline, while this draft's base is older `6b154e09357300964c0720448cee9654bf2585d0`. It requires *original source owner* current-base integration/review, not weakening the curation assertion or waiving CI. The current main's `scripts/worktree_sparse.py` blob remains unchanged (`296e47...`).

## What can be done without risky host effects

1. Reconcile/rebase the **one** original Macro sparse-helper source PR to an accepted current main source, with the overlapping external Mac SSD draft #6939 reviewed for ownership/collision. Rerun exact-head CI.
2. Only after source approval, distribute that exact reviewed helper through existing authorized Macro source/host release processes; read back the **exact matching Git blob** on the selected donor host. Do not reset active branches, adopt someone else's source lease or modify old full worktrees.
3. Reconcile the newer combined original Fabric source patch into one immutable support generation (not independently layering two patches). Preserve original broker/provider/root/parent, physical admission, and effect-unknown receipt behavior.
4. Dispatch **one newly admitted** bounded provider task using its original root/parent, strict new sparse workspace and optional CPU scope as approved. Verify real donor commit, Git HEAD/branch, sparse checkout, disk reserve, support digest, cgroup CPU quota if requested, no leftover descendant PIDs, RC/result and acceptance separately. A temporary repo test does not count.
5. Retain the conservative one-lane new-worker caps for overheating 9950X Ubuntu2/3 until attended MSI BIOS thermal-point / cooling maintenance and matched-load throughput proof. No earlier OS power-profile authorization denial is overridden by this source checklist.

**NO RELEASE/INSTALL IN THIS PREFLIGHT:** all four helper source products remain production **OLD**; current M2 launcher is unchanged. This is the exact active constraint preventing honest end-to-end sparse adoption despite complete source-only tests.
