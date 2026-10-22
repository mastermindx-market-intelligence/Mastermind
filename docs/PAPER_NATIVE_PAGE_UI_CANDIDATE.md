# Exact-target Paper native UI page pruning — candidate, not installed

**Scope:** One page deletion from an already cloned, exact-ID Paper file using the current first-party Paper desktop app; original file is immutable. This is **not** authorization for deletion, an active MCP tool, or a substitute for GitHub review and selected-seat installation.

## Evidence

In Paper Desktop 0.5.15 on the M1, right-clicking a page exposes **Copy link** and **Delete page**. Copy link on scratch clone `01M5HRAG5659SFE58D3PTA7D0V` for `p-1-0` returned the exact `https://app.paper.design/file/<fileId>/<pageId>` form, independently matching the Paper catalog's exact-file read. Native whole-file duplicate of the 57-page MASTERMIND PAGES original `01M2WGNCX9475G79JRKJTCM08P` created `01M5HVW84WZFE62DREB6QB9ZDJ` without modifying the source. Per-page reads: 57 equal page identities, 137,113 nodes, 887 boards, matching font lists and design tokens; 11 representative native JSX artboards equal, two image-bearing board screenshots byte-identical. **No pages were deleted on the production clone or original.**

## Candidate code

`integrations/paper_desktop/native_page_ui.py` is a private *opt-in candidate*, NOT exposed from the current MCP catalog. It reuses the exact source/clone plan from `clone_prune_guard.py`, bridge schema admission and lock. Before a deletion it requires original source identity/pages unchanged, clone metadata and page order matching, one kept page or more, a uniquely named page selected for removal, verified foreground clone, exact target page link from the first-party Copy link action, a freshly reopened observed Delete page menu, and pre-delete rechecks. Then it attempts **one** deletion and reads the original source and clone to establish observed outcome. It must not repeat after a lost subprocess response. A reported confirmation is metadata-specific, not full fidelity acceptance.

Run only after separate operator approval, source review, and scratch validation in the selected Paper Desktop session. Never start a second browser/tunnel/agent or use raw Paper endpoints to perform deletion. It does not grant original-file deletion. Any error/uncertain actuation retains its original carrier. The current code is an engineering prototype with synthetic tests; *desktop screenshot OCR and global active-file races still need adversarial inspection and real scratch acceptance*.

## Gate for users waiting on plugin

PR #1722 (guarded create/clone/rename/page organization), #1724 (0.5.15 catalog), #1728 (Studio response mapping), and #1742 (clone/prune read-only verification) require protected review/merge/selected-seat rollout. The Paper native UI adapter is an additional candidate, not a replacement for those prerequisites. **Green CI does not imply deployed capability.**
