# Signed-in Fabric catalog: reject machine-owner source scope

**Source-built / not production-proven.** Existing Fabric Discovery PR #1426, parent commit `0961a9e7e30afb7b6b96e8e78c8b8c2f72acc1b3`. No new authentication, registry, backend, worker or machine service.

## Security finding and fix

The existing `mastermind.attended_fabric_catalog.v1` diagnostic schema permits both `MACHINE_OWNER` and `EXACT_RUN_SET`. A signed-in Workspace principal does not thereby own every M2 worker. Before this change, an accidentally connected machine-owned source could be rendered as a permitted OS run list.

`decodeFabricCatalog` still validates sanitized diagnostics including machine-owned observations. The new `decodeBrowserScopedFabricCatalog` wrapper refuses any catalog not labeled `EXACT_RUN_SET` with a closed `FABRIC_CATALOG_SCOPE_REFUSED` error. It is enforced both in the MissionHost port after source/identity checks and in the FabricRunCatalog presentation. Machine-owned rows never appear and their direct-inspect action cannot be offered through that catalog. The existing Fleet integration fixture now accurately uses an explicit exact-run-set scope.

**This is defense in depth, not authorization.** `EXACT_RUN_SET` is a producer-supplied label, not a signed owner entitlement. The existing Workspace/Executive/Agent OS source must still establish the signed-in principal's specific original run membership before M2 acquisition and recheck that same grant afterward. Forging an exact-run-set source cannot be trusted as membership.

## Verification

Two red-first regressions demonstrated the previous risk. The completed scope guard passes 36 focused tests across three catalog/Fleet files, 1,515 tests across 67 complete app files (one existing skip, zero failures), TypeScript and Vite build. Existing Tauri mixed import and large-bundle warnings remain. Exact source and test-log SHA256 values are in the sibling JSON.

One obsolete intermediate test process overlapped a helper rename and produced failures on intermediate source. It is not the final frozen-source result and is excluded from the acceptance counts. The final process returned success with 1,515 passing tests after all references were updated.

## Source-admission observation and remaining gates

A separate read-only M2 retained ledger observation returned 10,199 entries, with zero run IDs matching the canonical `ATT-[0-9a-f]{32}` Runtime Attempt form or explicit Runtime association fields. This **does not prove absence** of every Executive-bound run, but that retained machine-owner ledger cannot supply the positive principal-to-run proof by itself.

PR #1426 remains Draft/Hold. No authorized user-to-native-run server producer, independent review, current required hosted CI, signed-in browser/native installation proof, or production deployment was completed. Original FleetHealth #1425 and Mission lineage #1435 retain source ownership.
