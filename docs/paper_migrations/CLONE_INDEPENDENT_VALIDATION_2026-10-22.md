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

## Contentful scratch clone-prune: separate independent readback

The adapter owner previously performed a separately authorized first-party native **clone then prune on a disposable source** and documented its operation at [Paper PR #1742](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1742). This workstream independently verified the **post-prune result** from M2 with read-only exact-file tool calls, without reproducing deletion:

| Identity | Exact native read |
|---|---|
| Scratch original `01M5HPWFPQ2Z5X79A9H8MJFKK0` | `Young harmony`: pages `p-1-0`, `p-3-0`; retained specimen on `p-1-0`: **5 nodes**, artboard `1-1` |
| Pruned scratch clone `01M5HRAG5659SFE58D3PTA7D0V` | `Young harmony (copy)`: only `p-1-0`; retained specimen: **5 nodes**, artboard `1-1` |
| `get_jsx(fileId,nodeId=1-1,format=inline-styles,includeNodeIds=true)` | Both returned **1,017-character JSX bodies with exact byte equality** after pruning. |

This is a real, editable **five-node** contentful scratch clone-prune readback with preserved source; it does **not** prove full-file mixed assets/comments/fonts/components, permission to prune a 57-page clone, exact unattended UI page-ID targeting, or removal of the source's oversize warning. The candidate PR #1742 remains subject to its own review, CI, publication and higher-stakes live canary gates. Never rerun its existing deletion operation.

### Quantified OKLab-to-hex gradient conversion

A subsequent read-only calculation compared the **162 OKLab color stops** in the 40 converted Website Front Cover JSX gradient lines with the clone's corresponding six-/eight-digit hexadecimal colors. Using standard OKLab-to-linear-sRGB conversion followed by sRGB transfer/8-bit scaling, all 162 stops paired in their original order. The maximum per-stop **RGB channel difference** was **2.499 out of 255**, with mean per-stop largest-channel difference **0.383/255**; maximum alpha error was **0.500/255**. No stop exceeded 2.5 channel units. The remaining two modified JSX lines were file-ID-scoped image asset URL rebinding, for which exact image-fill bytes were independently verified equal.

**Interpretation:** This supports *near-equivalent rendered color values*, not an exact preservation of the original editable OKLab stop syntax, dynamic effects, source CSS precision, or full file-wide appearance. The first-party clone appears to normalize color stops to 8-bit sRGB. No style rewrite was applied to either Paper document by this inspection.

## Five low-complexity candidate pages — independent current-source comparison

Later October 22, 2026, the same guarded direct Paper read carrier independently compared **five exact source pages against the existing full-size clone**, not a new duplicate. Every selected page returned equal page names, native node counts, artboard totals, entire returned artboard ID/name/direct-child lists, and available font-family lists. No listed page had a truncated artboard response. These are sequential, non-atomic observations; they require fresh pre-prune checks if used later.

| Exact source page | Current source nodes | Clone nodes | Boards | Selected artboard | Selected native JSX readback |
|---|---:|---:|---:|---|---|
| Market Memory `p-22-0` | 574 | 574 | 8 | `6LEM-0` | 22,757 characters each; **exact equality** |
| Commodities legacy archive `p-1I-0` | 405 | 405 | 5 | `1A6C-0` | 48,267 vs 48,245 characters; **one style-serialization difference** |
| Macro Dark Flow `p-1W-1` | 111 | 111 | 2 | `63EB-1` | 14,219 characters each; **exact equality** |
| Catalyst Decision Desk `p-20-0` | 776 | 776 | 10 | `6HNW-0` | 31,918 characters each; **exact equality** |
| Forex duplicate archive `p-16-0` | 138 | 138 | 1 | `1N0G-0` | 30,107 characters each; **exact equality** |

The single selected Commodities legacy JSX mismatch is at node `1AIX-0` in `linear-gradient(in oklab 120deg,...)`: original `oklab(68.5% -0.034 -0.138 / 8%)`, clone `#5B9BF014`. It is a color-space/precision transformation, **not an image URL rebinding or missing layer**. The selected screenshot rendered from each exact file was visually alike on inspection but **not byte-identical** (JPEG base64 lengths 258,340 versus 258,520). Hence this page **does not have strict style-preservation proof**, despite matching native counts; hold it from any full-fidelity assertion until the vendor semantics are qualified. This aligns with the earlier front-cover OKLab normalization finding.

**Migration-use distinction:** `p-22-0`, `p-1W-1`, `p-20-0` and `p-16-0` now have one independently checked native artboard with exact JSX equality and page-level structural parity; this does **not** certify all their artboards, image assets, components, comments, interaction states, or currentness after the observation. The proposed 32-family allocation remains purely read-only. Do not prune either existing file without authorized first-party page targeting, an individually admitted effect, complete relevant content checks, an independently restored native backup and post-prune verification. Source and clone were **not modified** by any check in this section.
