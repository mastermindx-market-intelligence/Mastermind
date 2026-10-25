# Paper: guarded native clone-then-prune evidence

**Status:** Scratch workflow proven on Paper Desktop 0.5.15 (2026-10-22);
read-only evidence helper is a source candidate, **not** a deployed MCP action,
live release, or authority to delete anyone's pages.

## Why this exists

Paper's reviewed 0.5.14 and 0.5.15 37-tool MCP catalog supports creating
whole-file copies but has no first-party `delete_page` MCP action. Its **desktop
UI** exposes both Dashboard > file card > Duplicate and page sidebar >
right-click > Delete page. Do not substitute `delete_nodes` or JSX re-import:
neither is proven lossless page migration.

Native *clone entire file, then prune unwanted pages from the copy* preserves
the source file and retained page IDs in our bounded scratch test. It remains
unproven for complex image libraries, fonts, tokens, comments, collaborative
references and large-file failure cases. Actual production acceptance needs
these tested on representative real design content.

## First-hand scratch receipt (M1, Paper 0.5.15)

- Scratch source: `01M5HPWFPQ2Z5X79A9H8MJFKK0`, `Young harmony`.
- First-party UI New File and page Add: two pages with IDs `p-1-0`
  and `p-3-0` at the time of copying. An earlier scratch page `p-2-0`
  was intentionally deleted first to test UI deletion alone.
- Dashboard Duplicate created clone `01M5HQ8VMMY87NVDENZAGJNYKM`,
  `Young harmony (copy)`. Separate exact-file `get_basic_info` reads
  confirmed both pages and IDs on **both** files at clone creation.
- On the clone only, first-party right-click Delete page removed `p-3-0`.
  Exact-file readback: source remains `p-1-0,p-3-0`; clone contains
  `p-1-0` only. No default active-file ID was used to infer the original.
- A later exact-file read of production `MASTERMIND PAGES`,
  `01M2WGNCX9475G79JRKJTCM08P`, returned 57 pages. It was not
  cloned, renamed, reordered, modified or pruned in this test.
- Both scratch pages had no meaningful design artwork (`nodeCount=1`).
  **This is metadata-path proof, not full-fidelity design migration proof.**

## Evidence helper

Invoke the helper with `python3 -m integrations.paper_desktop.clone_prune_guard` from the Mastermind repository root. This reuses the canonical `integrations.paper_desktop.bridge` module identity; direct script-path invocation is not the supported operator entrypoint.


`integrations/paper_desktop/clone_prune_guard.py` is read-only. It uses
the same reviewed Paper `bridge.execute(read/get_basic_info)` and existing
desktop serialization; no new Paper HTTP endpoint, listener, token, retry
engine, queue, write permission or deployment mechanism.

Before any UI deletion, make a complete **clone** and confirm its page
array matches the exact source. With the separate source and clone IDs:

```sh
python3 -m integrations.paper_desktop.clone_prune_guard plan \
  --source-file-id 01M5HPWFPQ2Z5X79A9H8MJFKK0 \
  --clone-file-id 01M5HQ8VMMY87NVDENZAGJNYKM \
  --keep-page-id p-1-0 \
  --operation-id scratch-copy-prune-20261022 > scratch-plan.json
```

This example is the *pre-deletion* form. The actual test clone above has
already been pruned, so don't rerun `plan` against those same two files to
reproduce the original condition. `CLONE_PAGE_LIST_MISMATCH` is expected.

An independently authorized **single** host UI carrier may then remove the
specified pages from the **clone only**, one by one, after inspecting the
foreground Paper file identity and exact page target. For a subsequent
fresh scratch clone, re-read both exact files before each irreversible UI
click. Do not use fixed click coordinates for a different file, window
size, page position, or screen. Paper's AX tree is sparse and OCR did not
reliably find even short page names in a trial; a visual mismatch is a
**refusal**, not reason to approximate a target.

After each intended removal, use the original carrier's readback, then:

```sh
python3 -m integrations.paper_desktop.clone_prune_guard verify \
  --plan scratch-plan.json
```

`CLONE_PRUNE_METADATA_VERIFIED` means exact source page-list identities were preserved, the clone retained precisely the designated pages, available token hashes remained stable, and the retained-page native node/artboard/font metadata has been rechecked on both source and clone.
It explicitly returns `production_migration_accepted: false` and
`original_deletion_authorized: false`. With no `--verify-node-id` it cannot
attest to retained native node styling. With specific node IDs, matching
native JSX provides bounded structure/style evidence but **not** image
pixels, imported fonts, linked components, references or comments.

### Contentful scratch upgrade (same M1/M2 team, 2026-10-22)

Following the first blank-page proof, the exact source scratch
`01M5HPWFPQ2Z5X79A9H8MJFKK0` gained Paper-native artboard `1-1`,
"Migration fidelity specimen" (1440x900), with an editable child frame,
two text nodes, inline typography and a dark background. On the accepted
M2 Paper carrier, `create_artboard` and incremental `write_html` each
returned `APPLIED_RESPONSE_OBSERVED`, and an exact source read showed
five total nodes on Page 1.

The first-party M1 Dashboard duplicated that file into a **new**
contentful clone, `01M5HRAG5659SFE58D3PTA7D0V`, preserving page
IDs `p-1-0,p-3-0`, artboard ID `1-1` and child hierarchy. The two
file headers naturally differed, but Paper `get_jsx` for artboard `1-1`
with explicit `inline-styles` returned identical 1,017-character JSX
bodies. The read-only `clone_prune_guard.py plan` then produced a
bound plan to retain `p-1-0` and remove `p-3-0`.

The first-party UI deletion affected **only the new clone**. M1
exact-file postreads independently confirmed the source still held
both pages and five nodes, while the clone retained `p-1-0`, artboard
`1-1` and five nodes. M2 `clone_prune_guard.py verify` returned
`CLONE_PRUNE_METADATA_VERIFIED`. The retained native artboard JSX
body remained byte-for-byte identical after pruning.

For a known native artboard, optionally add `--verify-node-id 1-1`
to the `verify` command to compare source and clone native JSX bodies
again at verification time. The option does **not** auto-select nodes,
and never makes image pixels, imported fonts, linked components or
comments proven. Failures `CLONE_JSX_MISMATCH`,
`JSX_SCHEMA_UNVERIFIED`, and `INVALID_JSX_EVIDENCE_TARGETS` all
refuse completion without any write.

**Production original remains untouched:** MASTERMIND PAGES
`01M2WGNCX9475G79JRKJTCM08P` still reported 57 pages on a separate
exact-file read after this contentful scratch test.

## Retained-page native metadata guard (added October 22)

The previous helper checked page lists and token hashes only. An independent real-path source-versus-copy read found a consequential counterexample: **Commodities page `p-L-0` contains 6,078 native nodes in the active source and 6,070 in the old copy**, despite equal page lists, 41 artboards, top-level child counts and token catalogs. The source and clone are therefore no longer content-equivalent.

The helper's new `plan` step now reads **each page that is intended to survive pruning**, using exact source and clone `fileId` + `pageId`. It compares node totals, complete returned artboard IDs/names/direct child counts and available font families, stores a structural metadata digest in the plan, and refuses incomplete/truncated artboard enumeration. A retained page that differs across source and clone is refused as `RETAINED_PAGE_NATIVE_STRUCTURE_MISMATCH`.

The separate `verify` step re-reads that retained page from **both files** and compares each with the pre-prune digest. Source drift is `SOURCE_NATIVE_PAGE_DRIFT`; clone drift is `CLONE_NATIVE_PAGE_DRIFT`. Neither can be marked complete on the strength of stable page names or a stable global token hash. The reported `source_page_list_unchanged_ids` refers only to list identities—not unchanged native content. This is deliberately target-scoped: removed pages need not be frozen against legitimate ongoing edits in the original.

**This does not prove full fidelity.** Nested node edits that keep counts and direct-child summaries unchanged can escape this metadata census; JSX style equivalence, images, live components, fonts not enumerated by the API, comments, color-space precision and representative visual output still require independent checks. A page with 101 artboards but a capped 100-record read fails closed until the adapter offers a verified complete enumeration. The helper continues to return `production_migration_accepted:false` and `original_deletion_authorized:false`.

The live production clone must **not** be pruned based on a historical creation receipt: its active retained pages have to pass this fresh check. The existing clone of MASTERMIND PAGES is preserved intact.

## Selected native JSX check before clone-only pruning

The guarded `plan` command now accepts optional `--verify-node-id ARTBOARD_ID` (repeatable, up to 24), and **refuses any selected ID that is not a top-level artboard on a retained page**. For each selected artboard it reads full native JSX from original and clone **before** any first-party UI page deletion; a mismatch refuses `CLONE_JSX_MISMATCH`, including OKLab-to-hex conversion, even when node counts agree. It records the original JSX content digest and selected artboard IDs in the plan. Later `verify` re-reads the same selected IDs automatically, detects content drift relative to the pre-prune baseline, and refuses an attempted switch of targets. Without selected IDs it still only proves structural metadata; it does not imply full visual or asset fidelity.

Example **on a future fresh, authorized disposable unpruned clone** (do not rerun the historical already-pruned scratch):

```sh
python3 -m integrations.paper_desktop.clone_prune_guard plan \
  --source-file-id SOURCE_FILE_ID --clone-file-id VERIFIED_NEW_CLONE_FILE_ID \
  --keep-page-id p-1-0 --operation-id approved-scratch-unique-id \
  --verify-node-id 1-1 > /private/scratch-plan.json
```

No GUI mutation or Paper source deletion is performed by this helper. For the existing production-sized historical clone, any retained artboard whose source/clone JSX differs must be held for exact style-semantic reconciliation **before** attempting clone-only page pruning.

## Release and permission fence

The current task authorizes bounded local scratch testing, not unrestricted
deletion of a 57-page production document. The original file reports
**Your file is too large. Further changes will result in data loss** in
Paper Desktop. Preserve it untouched while establishing safe full-fidelity
clone verification. Never delete source pages merely because a clone was
created, Paper indicated a click succeeded, or this helper emitted a
metadata-only receipt.

Native UI interaction is a distinct carrier choice made **before** each
logical mutation through existing authority. The existing Paper MCP
adapter cannot gain permission through a missing native deletion tool.
Do not use generic shell or browser automation to bypass an existing
explicit denial. A lost deletion reply must be reconciled against the
original clone file; do not replay it or switch carriers. The same
host-global Paper mutex and original operation tracking remain owners;
this helper does not create its own effect control plane.

For Web/agent universal use, future integration must add an explicitly
reviewed guarded UI deletion adapter with exact-file, page-ID, foreground
target and UI evidence binding. Until that production-reviewed capability
exists, use this as operator-side verification evidence only.

## Acceptance gap

- Production-routed guarded file creation/cloning requires completion of
  PRs #1722 and #1724 and the normal selected-seat install/scratch canary.
- A native UI page deletion was observed on isolated scratch only.
- Before claiming feature-complete migration: one representative contentful
  scratch file must prove artwork, styles/fonts, image assets, tokens,
  comments and references survive clone-then-prune; one exact UI-targeting
  control must be reviewed and reject ambiguous/hidden duplicate pages;
  end-to-end worker tool dispatch on its accepted route must be observed.
