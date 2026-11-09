# Fabric Catalog — navigate original parent / child without another read

**BUILT_NOT_PROVEN / mission incomplete.** This is app-side source-capability work on the existing PR #1426 original carrier. Source base `53b940fbcada2ba32f64eaf85cb7494e76db8829`. It does not create or enroll a new machine-owner service, authorization registry, user scope, provider, worker, queue or backend. Original actor and protected PR remain unchanged until normal review/release.

## What now works locally

Within one already-acquired, server-authorized `mastermind.attended_fabric_catalog.v1` sample (up to32 rows), selecting a run now reveals *observed parent* and *observed child* links when the corresponding sibling record and matching original root already exist in that same sample. Clicking a relationship selects its exact existing record; search and filter controls are reset to make the selected run visible. **No Fabric status request, new catalog request, launch, result read or acceptance occurs.** Root-label-only entries are not turned into workers. Cross-root purported relationships are not navigable; incomplete source relationships remain explicitly labelled and do not imply the global roster.

If the authenticated host principal changes, the catalog now clears user-entered search/query/filter state, and the selected exact-run inspector clears manually entered run/root labels when its host changes. Existing source-generation guards, aborts and typed refusal remain. Localized English/zh-CN controls remain keyboard-selectable buttons; no programmatic autofocus was added (prior denied autofocus change remains held).

## Proof

Red-first tests demonstrated missing same-snapshot navigation and two identity-change leaks. The repaired candidate passes **40 focused tests across3 files** and **1,495 complete app tests with one existing skip across66 files**, zero failures. `tsc --noEmit` and production Vite build both passed. The original chunk and mixed Tauri import warnings remain. The exact source and local log hashes are in `CATALOG_NAVIGATION_IDENTITY_20261015.json`.

**Not yet proven:** independent source review, browser pixels/keyboard behavior in a live browser (earlier platform denial preserved), any authenticated Mastermind OS Fabric producer, production deployment, or customer account selection. M2 C3 Fabric MCP and original remote tunnel were previously verified READY, but a trusted machine-owner channel does not grant a web principal access to arbitrary original runs. Consumer UI is still opt-in and explicitly disconnected by default. Do not bypass the canonical OS acquisition / permission-stamp / original-run association owner.
