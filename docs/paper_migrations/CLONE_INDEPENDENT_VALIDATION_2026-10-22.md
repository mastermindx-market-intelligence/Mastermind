# Live native full-size clone — independent read-only fidelity check (October 22, 2026)

**Classification: VERIFIED_PARTIAL_COPY_FIDELITY; NOT AN ACCEPTED MIGRATION OR SAFE SOURCE CLEANUP.**

## Exact resources and authority

| | Original source | First-party native clone |
|---|---|---|
| Paper file ID | `01M2WGNCX9475G79JRKJTCM08P` | `01M5HVW84WZFE62DREB6QB9ZDJ` |
| File name | MASTERMIND PAGES | MASTERMIND PAGES (copy) |
| Source record | Native original, 57 pages on later live reads | Created **once** by the existing M1 UI owner; see [PR #1722 original-carrier receipt](https://github.com/mastermindx-market-intelligence/Mastermind/issues/1722#issuecomment-6341740169) |
| Ownership | Still authoritative for active editing | Preserved as read-only migration/recovery candidate; **do not reclone, prune, or rename from this lane** |

The adapter-owner verified an exact source-to-clone census immediately after the one authorized native duplication: **57 matched page IDs/names/icons; 137,113 nodes on each file, 887 artboards on each; no node/artboard count, ID/name/child-count, token hash or font-family mismatch across those 57 page reads.** That is **their historical post-clone result**, not proof content remained unchanged indefinitely. The source-page original warning still appears. The earlier 63-page inventory in PR #1721 remains historical, and the six Terminal IDs plus `p-19-0` require reconciliation.

This independent follow-up was executed via the existing M2 guarded `mcp__Mastermind_Paper__paper_read` client against explicit IDs, Paper Desktop **0.5.14**, with no raw-host effects or Paper mutations.

## Independent observed checks

- Exact-page readback: `p-16-0` in both files resolved as `ARCHIVE · Forex Duplicate Study · Not for Build`, **138 nodes, 1 artboard, ID `1N0G-0`**. This is independent proof the existing clone is readable on another authorized Paper client.
- `get_tokens(fileId, format=json)`: **110 full token objects** in each file, exactly equal as returned (not merely matching the `cfd3d65c` token contentHash).
- `list_comment_threads(fileId, status=all, limit=200)`: zero visible comment threads from either file in this client context. **This does not prove a transfer preserves comments when present.**
- Rendered `get_screenshot(fileId,nodeId,scale=1)` returned **byte-identical JPEG payloads** for the following exact source/copy artboards: Forex ZH mobile `p-16-0/1N0G-0`, Earnings desktop `p-1B-0/1CR6-0`, Sector Cycles desktop dark `p-24-0/6PCB-0`, Commodities R4 overview `p-L-0/6XO2-1`.
- `get_tree_summary` for Forex mobile `1N0G-0`, depth 6, had **137 lines** with identical node/name/text topology after removing measured width/height fields. The source returned many unmeasured `?×?` sizes whereas the clone had numeric dimensions; no structural difference was observed.
- `get_tree_summary` for Earnings `1CR6-0` depth 5 matched exactly.

## Two important limitations discovered independently

**A. Current source is no longer identical to historical clone.** Commodities `p-L-0` currently has **6,078 nodes in original vs 6,070 in clone**, both with **41 artboards**, identical page name, artboard IDs/names and direct child counts; token listings still match. The original now contains **8 more observed nested nodes** on this page than its clone. This is a live content divergence; no assignment of timing or author is proven. A clone-prune plan relying only on page name/list/icon/token cannot detect it. Do not claim current full-file copy parity or use this clone as an accepted copy of every active page. Preserve legitimate active source edits. Relevant guard-owner report: [PR #1742](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1742), comment `6347809590`.

**B. Website Front Cover render and JSX are not byte-for-byte identical.** The source and clone have the same 1,000-line (depth 4) native tree for `p-8-1/EBS-1` and repeatable identical images *within each file*, but screenshots differ in JPEG bytes *between* files. The two renders appeared visually very similar to manual inspection. Full `get_jsx` (inline styles, node IDs) returned **5,001 lines each**: 42 lines differ; **40** differences replace OKLab gradient stop values with hexadecimal representations, **2** contain rewritten file-scoped image asset URL values. The exact image-fill bytes for the two changed asset references are **identical** on source/clone: node `FSA-0` (89,120-character encoded image payload) and node `NMQ-0` (64,260-character encoded image payload). A visually similar rendering is not proof of preserved color-space/editable style semantics; the transformed gradient definitions need qualified review. The JSX body is *not* a migration substitute.

## Safety implications and exact next action

1. Existing native copy **is real**. It must not be duplicated or recreated without effect reconciliation. The current first-party clone remains an oversized file and itself emits the data-loss warning.
2. Advance **clone-prune on a contentful disposable scratch**, using the existing PR #1742 read-only guard and **one separately accepted exact-file/page-ID UI operation**, not via unsupported MCP `delete_page`, JSX reconstruction or fixed blind coordinates.
3. Harden the clone-prune guard to distinguish **page metadata parity** from **content parity**. An unchanged page list/token hash is not evidence that all current native pages match the clone; `p-L-0` proves the gap concretely. Confirm source snapshot or per-page native node/asset structure before future cutover and after cleanup.
4. Reconcile page-link consumers before design authority is reassigned. Active product links continue targeting the original, and already-accepted source/review work must not be silently replaced with a historical frozen clone.
5. Keep all original source and existing clone pages unchanged until a supported native recovery pathway, exact page targeting, visual/asset/component fidelity and separate cleanup authorization are proved.

**Actual Paper effects performed by this independent validation: 0. Actual source pages removed: 0. Actual clone pages pruned here: 0.**
