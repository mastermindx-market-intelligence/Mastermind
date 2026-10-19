# Mastermind browser findings and minimal containment repair

## Source binding

The original actual HTTP/browser run is
`/tmp/sovereign-auction-mastermind-ui-proof-01/browser_receipt.json`, SHA256
`c61137cd723f7cfe6f1fed323fab9f4e35018fa98494936e5f4523d3e7727f3f`.
It completed on 2026-10-08 at 23:29:02.161Z with Chromium 149.0.7827.55:
12 passed cases, four desktop expansion cases requiring review, and 32 narrow
screen failures. Those results remain failures/review requirements in that
historical receipt. No assertion was removed or relaxed.

The affected HTML preimage is
`ea065f214c49c053fa584eb1143631f9b09bee5f7a3563b9c5e7237178d70daa`.
The two-line candidate replacement is
`b8d84a7313bdd7c9f4bbcc3ddfeadaaeddd85b9976ca143a64acaf5146c8a043`.
Only `mastermind_patch/app/static/market_view.html` was edited for this repair.
Root authorized the minimal existing-page containment correction after the
inherited problem was distinguished from the new auction expansion defect.

## Findings

**New auction defect — expanded cards collapsed into the label column.**
The new auction group reuses the existing `.brief-row` grid, whose desktop
columns are `170px minmax(0, 1fr)`. The group's third direct child, `<details>`,
therefore entered the 170px first column. Its two-column card grid produced
80.5px event cards, compared with 518.5px initially visible cards. The actual
desktop screenshot shows extreme word wrapping and largely empty panel space.
The repair spans that auction-only direct expander across both grid columns.
Initial card layout and unrelated brief rows remain the same.

**Inherited narrow-screen defect — the planes panel forced grid minimum width.**
The actual initial run measured a 924px document at both 820px and 390px viewport
widths. The same overflow occurred in the unavailable auction case, with no
auction rows. An independent browser diagnosis then rendered the exact pre-auction
HTML from Mastermind `c7e47c859eb2925c5626931fd511800773ba09ac` with the same native
background fixture and real theme. It reproduced 924px at both narrow widths
with no auction section at all. The containing planes panel had `min-width:auto`
and expanded to 912px to accommodate the table's existing 880px minimum plus
its wrappers. The table already had an `overflow:auto` container, but its grid
item's automatic minimum width prevented that intended internal scrolling.

The repair sets `min-width:0` on this page's existing `.panel` grid items. The
table remains 880px wide and scrolls inside its existing container. No table
columns, content, typography, viewport breakpoints or overflow assertion change.

## Exact source patch

```diff
 .auction-context h3 { font-size: 13px; margin: 16px 0 8px; }
+body.page-mv .auction-context .brief-row > details { grid-column: 1 / -1; }

 body.page-mv .panel {
+  min-width: 0;
   margin: 0;
```

## Verification completed

The actual original screenshots inspected were:

- `1440x900-en-light-observed-expanded-1.png`
- `390x844-en-light-unavailable-auction.png`
- `820x1180-en-light-observed-auction.png`

The separate read-only diagnosis ran 21 Chromium cases using intercepted
loopback requests: three exact incumbent baselines without auctions, three
current unavailable baselines, three repaired unavailable baselines, and 12
repaired observed views covering all requested sizes, languages and themes.
It served the **exact candidate HTML bytes** from memory, the real current theme,
and the actual final producer/reader's 74-row context. It did not modify any
remote source or evidence file. The diagnosis created no application server and
does not replace the final actual FastAPI browser acceptance run.

| Viewport | Incumbent document width | Current unavailable width | Repaired document width | Repaired planes scroll container | Minimum visible card width after expansion |
|---|---:|---:|---:|---:|---:|
| 1440×900 | 1440 | 1440 | 1440 | 1232; table fits | 518.5 |
| 820×1180 | 924 | 924 | 820 | 764; table scroll width 880 | 378.5 |
| 390×844 | 924 | 924 | 390 | 334; table scroll width 880 | 336 |

The repaired observed results were consistent across EN/ZH and light/dark.
There were no page errors or off-origin requests. Exact source hashes and all
measurements are retained in `MASTERMIND_LAYOUT_DIAGNOSIS_RECEIPT.json`; the
reproducible source is `mastermind_layout_diagnosis.cjs`. The diagnosis explicitly
requires the old HTML preimage because it compares that original revision with
the patch; after root installs the repair, use the main browser harness rather
than silently rebinding this historical diagnosis.

The existing actual-renderer unit command also passed after the two CSS lines:
`node tests/test_sovereign_auction_renderer.cjs`.

## Remaining acceptance

Root should replace the exact HTML preimage in the canonical owned workspace and
run the unchanged 48-case actual FastAPI/Chromium harness into a new proof
directory. That run must retain its overflow, clipping and expansion assertions
and produce new screenshots for inspection. This receipt supports the diagnosis
and minimal fix; it does not claim that the new full HTTP/browser run has already
passed. The old failed receipt remains material evidence.
