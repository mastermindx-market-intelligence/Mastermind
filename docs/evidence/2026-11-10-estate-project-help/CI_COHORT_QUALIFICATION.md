# Exact paired Macro CI pin reconciliation

## Outcome

The failing estate integration retains an obsolete paired Macro fixture pin. The repair already exists under the original owners: Macro #10740 published the qualified successor, and merged Mastermind #2401 adopted it. The candidate here changes exactly one immutable fixture reference in `.github/workflows/ci.yml` at estate head `95762fc3700598a7be1a12b8c6c1995753071eed`. It preserves every unrelated workflow byte and produces exactly the already-accepted workflow blob.

No Macro source, cohort predicate, production security predicate, workflow trigger, required check, fixture assertion or installed runtime is changed. No workflow was rerun.

## Bound failure

- Repository/PR: `mastermindx-market-intelligence/Mastermind` #2424.
- [Run 42796811883](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42796811883), attempt 1, pull_request event, source head `95762fc3700598a7be1a12b8c6c1995753071eed`.
- Job `129774519664`, shard 0, step **Verify exact scoped Fabric model and Metabolism composition**.
- Actual merge checkout: `a2bf5931c4ce69f9c2afc427c5e1bb399256c847`; Git tree `e2f3936b89a67ac88a02526f585c10182a285cf6`, matching the source candidate tree.
- Ubuntu 24.04.5 hosted runner. The earlier isolated transport step passed 170 cases. The paired exact-composition invocation ended at `2026-11-10T10:58:14Z` with **63 passed, 56 errors in 3.54 seconds**, exit 1.
- First repeated setup error: `AssertionError: complete paired native source cohort required` in `tests/test_fabric_exact_scoped_model_composition.py::native_source_pins` / `_require_native_source_cohort`.

The workflow checked out Macro `a82b310ebc1a3cd67547c5a2df6ef5c5fc54bb8c` into `.ci-production-macro`. That fixture recognizes the original 19-file runtime cohort and the complete GLMv4 cohort. All 19 current candidate identities were independently read from the exact source through GitHub's content owner. Seventeen match GLMv4; the only changes are the two accepted private-fixture repairs:

| Relative to `ops/native_fabric/quota_continuity/` | Old fixture blob | Exact candidate blob |
|---|---|---|
| `tests/test_application_registered_pool_selection.py` | `754d6d8c1a6391fcfefdbd26417f87944403ea2b` | `b0c1991f33bff830284225687700ee8d6b32e735` |
| `tests/test_application_registered_pool_composition.py` | `3c1bb6f596fa8821af19c71eb2ea2327147b19eb` | `59685ae3086241fec086c1e5eda4a37632ada044` |

This is deterministic source-cohort incompatibility. It is not evidence of a flaky transport, provider failure or need to relax a security check.

## Existing source owners

[Mastermind #2387](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2387) repaired private ledger fixtures for permissive runner umasks and merged as `ebc48690f20bb5c0554f91ec7cf2b4533f641f5a` at `2026-11-10T01:00:45Z`.

The [original Macro #10740 proof](https://github.com/mastermindx-market-intelligence/macro/pull/10740#issuecomment-6757956429) publishes `0c0521169260d87889da8a7711a90460982eefa2`, with `tests/test_fabric_exact_scoped_model_composition.py` blob `649a89dacaf2ad62e359da048862523cba221c83`. The existing guard adds `GLM_FIXTURE_NATIVE_PINS` as a third complete 19-file cohort. It retains whole-map equality, rejects mixed versions, and retains the old two complete cohorts. Its original source owner reports 121 Fabric/compiler and 291 Metabolism cases passing in an isolated network-disabled Linux proof. Those 412 results remain attributed to that owner; they are not relabeled as this local diagnosis or full hosted CI. Macro's release holds remain separate.

[Mastermind #2401](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2401) already adopted the successor through its existing paired-fixture consumer. It merged as `fd9f414bf63b3a2e059d192ce580c5754aababcd` at `2026-11-10T07:31:28Z`. The resulting workflow blob is `b201f8336b34bdd4a82469f234a4d2f622febd33`.

The inspected live [#2404](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2404) at `c10cd0b45fc3cd64c145bfbae01307926c8b446e` already carries that same workflow blob. Its five-path patch concerns separate acquisition/security-fixture diagnostics; it adds no new Macro cohort or workflow-pin change. No duplicate repair carrier is needed.

## Exact candidate and qualification

`accepted-macro-pin.patch` changes only:

```diff
-          ref: a82b310ebc1a3cd67547c5a2df6ef5c5fc54bb8c
+          ref: 0c0521169260d87889da8a7711a90460982eefa2
```

Original workflow blob: `d80e562479c5b30e7c7cdbdb85e4b23d495fd923`.
Final workflow blob: `b201f8336b34bdd4a82469f234a4d2f622febd33`.
Patch SHA256: `a54a96836e125baa20626dffedebcbea0b63b5f8c384608be707e424f18b5b2f`.

Executed `verify_cohort.py` using the established qualification pytest dependency directory. It verifies exact original/full source blobs, the 19-file observed map, original guard rejection and successor acceptance. It executes the three unchanged pure owner cohort tests: all 128 runtime/fixture combinations admit exactly the three known complete cohorts; mixed, missing, drifted and extra members are refused. A deliberately loose per-file whitelist fails the existing atomic-cohort test. The one-line patch passes whitespace check, applies over the exact957 preimage, and replays to the already-accepted postimage byte-for-byte.

This local proof deliberately isolates the original pure cohort AST; it does not import the Macro runtime or claim a fresh Fabric/Metabolism execution. The initial default interpreter lacked pytest; that environment-only failure is retained, and the qualified invocation reused the existing dependency directory without installing or altering anything. Required hosted checks remain owed on the parent's composed head.

The parent can compose this exact patch under existing #2424. Source/CI delivery remains separate from customer/runtime acceptance. `source_manifest.json` records artifact hashes and original/postimage identities; `observations.json`, `observed_cohort.json`, the bounded CI excerpt, original source snapshots and `qualification.log` retain the evidence.
