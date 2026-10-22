# Exact-target Paper native UI page pruning — candidate, not installed

**Scope:** One page deletion from an already cloned, exact-ID Paper file using the current first-party Paper desktop app; original file is immutable. This is **not** authorization for deletion, an active MCP tool, or a substitute for GitHub review and selected-seat installation.

## Evidence

In Paper Desktop 0.5.15 on the M1, right-clicking a page exposes **Copy link** and **Delete page**. Copy link on scratch clone `01M5HRAG5659SFE58D3PTA7D0V` for `p-1-0` returned the exact `https://app.paper.design/file/<fileId>/<pageId>` form, independently matching the Paper catalog's exact-file read. Native whole-file duplicate of the 57-page MASTERMIND PAGES original `01M2WGNCX9475G79JRKJTCM08P` created `01M5HVW84WZFE62DREB6QB9ZDJ` without modifying the source. Per-page reads: 57 equal page identities, 137,113 nodes, 887 boards, matching font lists and design tokens; 11 representative native JSX artboards equal, two image-bearing board screenshots byte-identical. **No pages were deleted on the production clone or original.**

## Candidate code

`integrations/paper_desktop/native_page_ui.py` is a private *opt-in candidate*, NOT exposed from the current MCP catalog. It reuses the exact source/clone plan from `clone_prune_guard.py`, bridge schema admission and lock. Before a deletion it requires original source identity/pages unchanged, clone metadata and page order matching, one kept page or more, a uniquely named page selected for removal, verified foreground clone, exact target page link from the first-party Copy link action, a freshly reopened observed Delete page menu, and pre-delete rechecks. Then it attempts **one** deletion and reads the original source and clone to establish observed outcome. It must not repeat after a lost subprocess response. A reported confirmation is metadata-specific, not full fidelity acceptance.

### Real first-party UI canary — October 22, 2026

M2's **live Business Paper plugin** created a disposable source file `01M5JRN1HWF62YK527NKCY7WD5`, created and renamed/reordered its two pages, then made a whole-file clone `01M5JS8TNZKQ01SJS4D0S9VQFC`. Separate exact-file reads confirmed source and clone each held `p-2-0,p-1-0` in that order. The M1's v14 Paper bridge and stacked native UI candidate `b6120e31...` with reviewed 0.5.15 schema built an immutable source/clone plan to retain `p-1-0` and delete `p-2-0` **from the disposable clone only**.

The first UI attempt returned `UI_MENU_ITEM_UNVERIFIED` because live Peekaboo OCR saw Delete page and Add divider but **missed Copy link** despite its clearly visible first-party menu presence. Readback confirmed NO page was removed; operation `paper-e2e-native-ui-prune-20261022-a` was not retried. A narrowly reviewed fallback locates the **non-destructive** Copy link coordinate only when precisely one Add divider and one Delete page OCR element share a first-party menu column and their row geometry matches bounded criteria; the clicked link must still return the exact file and page IDs, or deletion is prohibited. This fallback has positive and negative synthetic tests.

A new, separate same-carrier operation `paper-e2e-native-ui-prune-20261022-b` returned `CLONE_PAGE_UI_DELETE_VERIFIED`, `removed_page_id=p-2-0`, `retry_allowed:false`, `source_unchanged:true`. Two independent exact-file Paper reads subsequently confirmed the original scratch source still contained `p-2-0,p-1-0`, while the clone retained only `p-1-0`. Separate `clone_prune_guard verify` returned `CLONE_PRUNE_METADATA_VERIFIED` with `production_migration_accepted:false`. **This establishes a real one-page deletion from a disposable clone via the native UI candidate, with independent post-effect proof.**

Run any future deletion only after separate operator approval, source review, and selected-session installation. Never start a second browser/tunnel/agent or use raw Paper endpoints to perform deletion. It does not grant deletion of MASTERMIND PAGES or its preservation copy, which has a known eight-node Commodities discrepancy. Any error/uncertain actuation retains its original carrier. The source is still an opt-in candidate; synthetic and real *scratch* success is not evidence that all Business plugin consumers have a published deletion action. Global active-file races still require one UI writer, and the released plugin must retain these exact guards.

## Gate for users waiting on plugin

PR #1722 (guarded create/clone/rename/page organization), #1724 (0.5.15 catalog), #1728 (Studio response mapping), and #1742 (clone/prune read-only verification) require protected review/merge/selected-seat rollout. The Paper native UI adapter is an additional candidate, not a replacement for those prerequisites. **Green CI does not imply deployed capability.**
