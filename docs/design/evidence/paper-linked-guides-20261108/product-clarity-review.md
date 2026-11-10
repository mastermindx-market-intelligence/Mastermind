# Product clarity review — bounded read-only return

## Outcome and limits

The seven-file cohort has **72 pages inventoried with zero read errors**. This review inspected the native structure of all 72 pages, read **13 focused boards as JSX**, and visually inspected **8 representative screenshots**. It did not deeply inspect every board or verify browser behavior. No Paper, repository, runtime, browser, messaging, or other external writes were performed. Scratch reports are the only artifacts created.

The clearest new repair opportunities are in AERLOR: restore the identity of the mobile project-list control, align the planner preview with its fields, and explain which design versions have an implementation source. Other reviewed product surfaces already preserve useful separation of product, evidence, explanation, and build notes; this return does not invent a redesign task for each file.

Mastermind pin: `1d0579c0540f5281e52faf069dd7dba2f480c7c6`
Macro pin: `b5674d8ef898e503d6164922654f5ff89be9981c`
AERLOR main, discovered and read in this review: `c6f7deee41b9d941182130d9bfb95c1e84f8a319`

## 1. Repairs ready for parent integration

### A. Identify the mobile project-list control

**Target:** AERLOR file `01M6JNN71ZN4867VJZ83PPXQZ0`, page `p-9-1`.

| Board | Exact text node | Parent | Current defect |
|---|---|---|---|
| R9 Solutions mobile `5HU-1` | `5UX-1` | `5UW-1` | Bare `0` appears beside the menu with no icon or label. |
| R9 Salons mobile `5HV-1` | `5WW-1` | `5WV-1` | Same bare count confirmed in JSX. |

The Solutions screenshot shows the defect. Salons shares the same native structure, confirmed by JSX; its full screenshot was not separately inspected. Desktop planner calls this control **Project list 0**, node `5RJ-1`.

**Minimal repair:** keep the existing project-list destination and count, and restore its identity with a short visible label or the existing outline bag icon plus count. The source-backed icon pattern is already in [scripts/r4/ui.mjs](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/scripts/r4/ui.mjs): `header()` emits the bag outline, `data-cart-count`, and the accessible label “Your project bag, 0 items.” The Paper label should stay consistent with the selected R9 vocabulary. Avoid turning the count into an unconnected decorative number.

The parent flex row uses a 24px gap and a 22px menu icon; both count nodes have max-content width and no fixed box. Recheck the 390px composition after the repair and specify a 44px action target in implementation guidance. Do not imply the Paper control is interactive.

### B. Match the project preview to the form

**Target:** same AERLOR file/page, R9 Business planner desktop `5HT-1`.

| Role | Node | Existing content |
|---|---|---|
| Form field label | `5SR-1` | Project stage |
| Form field value | `5ST-1` | Choose a project stage |
| Preview label | `5U3-1` | First priority |
| Preview value | `5U4-1` | Not selected |

The visible form contains environment, market, estimated units/stations, locations, project stage, collections, and free-text requirements. It has no “first priority” selector. The preview has no project-stage row.

**Minimal repair:** change preview label `5U3-1` to **Project stage**, preserving its initial **Not selected** value. Keep priorities in the free-text requirements rather than silently inventing a new ranking field. Record this field mapping in build notes.

The older planner `R3-0` on `p-2-0` has **What matters most?** at `TE-0`, followed by free text. The actual [src/pilot.ts](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/src/pilot.ts) exports this as **Priorities / notes** from `input.message`, not as an enumerated first-priority selection. The current R5 inquiry form is separately owned by [scripts/r4/ui.mjs](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/scripts/r4/ui.mjs) and its behavior by [src/storefront.ts](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/src/storefront.ts). Thus the proposed R9 mapping is a design repair, not a claim that the R9 form is implemented.

**Useful companion builder note:** bind each preview row to exactly one visible draft field. Never infer a top priority from free text. Preserve the draft if copying or downloading fails. “Prepared for download” does not mean saved to the user’s device, sent, or accepted. This extends existing local-brief behavior; it must not create a second inquiry, project-bag, or persistence owner.

### C. Add a source and version map for AERLOR

**Targets:** current R9 `p-9-1`; original Foundations `p-3-0`, board `18U-0`; older Product interaction states `p-2-0`; original Website `p-1-0`.

These pages lack an evident start/build map comparable to the other cohort files. The current named Foundations page presents warm paper/ink tokens and says that `src/paper-tokens.css` is the implementation export (`1BB-0` / `1BC-0`). This describes the older lineage, while current repository documentation names precision tokens and the R5 release.

**Source evidence:** [README.md](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/README.md) and [design/precision-r5/README.md](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/design/precision-r5/README.md) identify R5 `p-6-0` as the current source-backed release and `src/precision-tokens.css` as the current shared token export. R7–R9 appear in Paper but were not found as corresponding directories in the pinned main tree. This is not proof that no branch or unmerged implementation exists.

**Minimal repair:** add a compact AERLOR build/source directory, visibly distinguish:
- Current source-backed R5 release: `p-6-0`.
- Later Paper direction: R7/R8 consumer/product studies and R9 Solutions/planner; implementation adoption remains to be verified.
- Original foundation and planner states: retained reference, with useful local-brief/error behavior preserved.
- Current source owners and full copyable URLs below.

Do not collapse all AERLOR pages into the highest revision number: R9 Solutions, R8 flagship product, and R7 home serve different jobs. Do not label older states deletable until their recovery/privacy behavior has a mapped replacement. No market/monitoring vocabulary belongs in this project.

## 2. Concrete AERLOR implementation URLs to put in Paper

| Purpose | Exact source |
|---|---|
| Release and source map | [README.md](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/README.md) |
| Source-backed Paper release and artboard IDs | [design/precision-r5/README.md](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/design/precision-r5/README.md) |
| Page generator; avoids editing generated route HTML | [scripts/build-storefront.mjs](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/scripts/build-storefront.mjs) |
| Shared header, controls, inquiry form | [scripts/r4/ui.mjs](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/scripts/r4/ui.mjs) |
| Project bag, forms, downloads, inquiry/checkout handoff | [src/storefront.ts](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/src/storefront.ts) |
| Original local pilot brief semantics | [src/pilot.ts](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/src/pilot.ts) |
| Commercial and transmission boundaries | [LAUNCH.md](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/LAUNCH.md) |
| Older Paper lineage and recoverable state references | [design/paper/README.md](https://github.com/mastermindx-market-intelligence/aerlor/blob/c6f7deee41b9d941182130d9bfb95c1e84f8a319/design/paper/README.md) |

These contents were read at the exact AERLOR pin. AERLOR is a separate repository and brand. Its source says that products and imagery remain concepts, direct inquiry and checkout remain gated, and prepared/downloaded briefs do not prove delivery. Paper’s later design direction must retain those relevant limits.

Parent reports both supported Paper HTML paths flatten `href` into styled spans. Full selectable/copyable URLs with embedded notes are therefore the usable confirmed fallback. Do not describe the styled labels as working hyperlinks or invent an unsupported link API.

## 3. What to preserve in the rest of the cohort

| File | Focused review | Assessment and next source link |
|---|---|---|
| Mastermind AI | Mobile answer `1VE-0`; builder map `1MO-0`; source gaps `5VN-0` | Current answer is concise with optional Sources and deeper work. Existing build notes already cover answer-bound evidence, uncertain stream outcome, mention-context separation, non-monitoring save hold, and owner custody. Preserve them. [templates/chat.html](https://github.com/mastermindx-market-intelligence/macro/blob/b5674d8ef898e503d6164922654f5ff89be9981c/templates/chat.html) was read at the current pin; add its full URL beside the existing source observations, preserving the observation’s own historic pin. |
| MarketOntology | Public first visit `OX-0`; preserved build contracts `ADK-0` | Public explanation and sign-in-only current trace are clearly separated. Contracts retain source spans, receipt versions, missing-vs-zero, thesis save, and exact return. Keep the held duplicate shared shell separate. Candidate source paths were verified as present in the template listing: `templates/ontology.html.j2`, `templates/ontology.js`, `templates/ontology-company-contract.js`, `templates/ontology-company-controller.js`; their behavior was not reread in this bounded review. |
| Market Guide | Current mobile entry `1WO-1`; directory `37N-0` | Strong question-led entry. Longer teaching content is intentional user help, not removable builder verbosity. Recent proposed guide-return work is already mapped to `p-8-0 / 44J-0`. Preserve eight-variant baseline and all full Risk Guide variants. |
| International Markets | Frozen mobile scanner `IRV-0`; directory `41M-0`; engine ledger `P9-0` | Preserve R14 freeze and proposed scanner-to-dossier states. Builder ledger explicitly distinguishes existing owner/source from unverified R10 binding. Long mobile height carries clocks, coverage, units and evidence, so shortening requires a task-specific design decision. Template listing confirms `templates/intl_workspace.js`, `templates/intl_workspace_state.js`, `templates/intl_workspace_entry.js`, and `templates/intl.html.j2`; no new source behavior claim made. |
| Market Dashboard Popups | Partial-data mobile `8R6-0`; contracts `AHN-0` | Missing data, unverified freshness/calibration, retained values and separate score scales remain explicit. Do not remove these qualifiers merely to make the popup shorter. Follow/save states already distinguish confirmed failure from unknown outcome. Template listing confirms existing Risk Radar workspace and dialog sources; no new payload/forecast recommendation made here. |
| Canonical design system | Build overview `47Q-0` | Already contains source URLs, domain-owner boundaries and precise candidate/HOLD status. Preserve final-freeze/joint acceptance hold, unrecovered write responses, and 32 captured board pairs. Do not rewrite it as accepted runtime behavior. Existing mutable draft links are clearly labeled as navigation, not approval identity. |

The Macro template listing is path-existence evidence only; do not promote it into source behavior or deployed-consumer proof. The full exact URLs can use the verified prefix `https://github.com/mastermindx-market-intelligence/macro/blob/b5674d8ef898e503d6164922654f5ff89be9981c/`.

## 4. Coverage and exclusions

| File | Pages structurally inventoried |
|---|---:|
| Mastermind AI | 10 |
| International Markets | 21 |
| MarketOntology | 7 |
| Market Guide | 7 |
| Market Dashboard Popups | 8 |
| Canonical design system | 10 |
| AERLOR | 9 |
| **Total** | **72** |

Screenshot evidence: `01M6JNN71ZN4867VJZ83PPXQZ0/p-9-1/5HU-1`, `01M6JNN71ZN4867VJZ83PPXQZ0/p-9-1/5HT-1`, `01M3P1QEHS5XXQY85BJT6QR2E1/p-1-0/1VE-0`, `01M32XYWDYSFTNDZVJKQ5QHT33/p-1-0/1WO-1`, `01M3P1X4FR6BRTB13KA736Y1HT/p-2-0/OX-0`, `01M3P1TW5Y3XWQC37ADDS8K5AG/p-I-0/IRV-0`, `01M38EVF74SJWG1GANN5VP380Z/p-1-0/8R6-0`, `01M312VSDSZFVT45674GDVJVZN/p-9-0/47Q-0`.

The evidence JSON lists every focused JSX board, exact screenshot target, observed page names, preserved references and source URLs. All page-level metadata is in `product-clarity-page-inventory.json`.

### Explicit preserved holds and historical surfaces

- AI: `p-6-0` QA HOLD duplicate shared-shell transfer. `p-5-0` source-only live baseline; `p-2-0`, `p-3-0`, `p-4-0` references remain separate from current R10.
- Ontology: `p-5-0` QA HOLD duplicate shared-shell transfer.
- International: `p-A-0` archived relocated families, including `QYU-0` working HOLD comparison references; `p-9-0` archived Return v2 duplicates. `p-I-0` frozen R14; `p-G-0` R12 and `p-H-0` R13 references.
- Guide: `p-5-0` baseline theme/locale references retained.
- Popups: `p-2-0` historical program handoff retained.
- Canonical design system: `p-8-1` source imports/assets pending review; utility `9ZY-0` on `p-B-0` is an existing empty 1×1 native utility, not an unreviewed deletion target.
- AERLOR: older pages are **not automatically archived**. Add version/source clarity while preserving state coverage and brand lineage.

## 5. Suggested parent integration order

1. Apply the two bounded AERLOR label/control repairs.
2. Add its source/version/build mapping, using the exact verified URLs.
3. Keep the cohort’s current proposed/recovery work and explicit holds intact.
4. Re-read and screenshot the changed AERLOR controls and planner. Check no clipping and no drift into claims of implemented interactions.
5. Attach this bounded evidence to the parent’s portfolio coverage record. Do not claim all 72 pages received deep visual review.

This child assignment is complete. No background work, external effects, or continuing writer is left running.

