# Fabric discovery — source verification

This continuation builds the **app-side recent-run catalog**, not a live source service or complete Fabric inventory. Prior inspector PR #1411 merged at `98d00027cf5e228be9bd584684ad0284769cdf74`; its accepted UI proof is not reused as proof for this new catalog.

The complete current app suite passed **1,468 tests / one skipped / zero failed across 63 files**. Twenty cases directly cover the new catalog and its existing-inspector handoff; the total also includes current-master Research work and earlier tests. TypeScript/Vite build passed, retaining documented chunk/import warnings. Exact source and log hashes are in `verification.json`.

Browser qualification of the new layout was blocked by the platform before dispatch. **No new screenshot, responsive browser, keyboard-browser or live-data proof is claimed.** The independent DOM tests pass; they are not visual acceptance. The `.fixture` files here are explicitly synthetic scaffolding outside normal app entrypoints, not a data service.

The separate backend/shared Python contract write was blocked before dispatch and remains absent. It was not replayed through another tool, path or worker. No source producer, endpoint, host credential, runtime/controller or production configuration was created. An artifact-worker request for the new UI returned `NONE reason=no_pool_available` before worker START; no replay. The assigned parent completed only permitted independent consumer work.

## Implemented journey

Optional authorized catalog port → strict metadata decoder → bounded recent-run list → local search and filters → selected metadata → exact verified root/run copied into the existing run inspector → separate explicit read. Unknown root has no navigation target. Catalog selection grants no access or operation. Auth and source generation changes suppress stale rows and clear copied identifiers. Missing producer means disconnected, not an idle fleet. No polling, launch, retry, acceptance or private output content.

## Remaining proof

Independent exact-head source review, actual browser/layout qualification, source-produced catalog, existing OS principal/grant binding, live authenticated app proof and release/install remain distinct gates. Do not enable a default client or publish the synthetic fixture to work around them.

## Subsequent source-backed execution

[October 15 C3 ready-tunnel reconciliation and parent/child catalog lineage qualification](C3_TUNNEL_AND_CATALOG_LINEAGE_20261015.md). This is local managed tunnel/read-only MCP and frontend contract proof, **not** a native ChatGPT plugin-consent or live authenticated Mastermind OS acceptance.
