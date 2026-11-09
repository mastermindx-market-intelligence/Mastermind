# Portfolio navigation review — 8 November 2026

## Scope and evidence

Read-only architecture/navigation review of 41 files / 130 pages in the assigned migration cohort. Mastermind pin: 1d0579c0540f5281e52faf069dd7dba2f480c7c6. Macro pin: b5674d8ef898e503d6164922654f5ff89be9981c.

Every assigned page has inventory/classification coverage in portfolio-navigation-coverage.json. Detailed evidence comprises 12 JSX board reads, two representative visual inspections (Bonds start and Market Breadth desktop), four exact original-page destination text reads, and direct GitHub source reads. Other page dispositions are metadata classification, not full content or visual review. No browser, interaction, production or native hyperlink acceptance is claimed. No external mutations were made.

## Minimal mutation shortlist

### 1. Fix the selected global workspace on Market Breadth

Target: file 01M6Y3CRMC345RTB3ZDP3XSYRP / p-1-0 / desktop board 1-0.

Observed breadcrumb is MARKETS / UNITED STATES / BREADTH. Global Overview is selected while Markets is inactive; local Overview is also selected. The two levels therefore contradict the location.

- Global Overview container 9-0, icon A-0, label B-0.
- Global Markets container C-0, icon D-0, label E-0.
- Set global Markets selected and global Overview inactive; preserve local Overview.
- Exact before JSX is in breadth-navigation-before.jsx.
- Use neutral selected background/border under current doctrine. Existing selected Overview has background #151B29, border #29354B, radius9px, 1px border; do not propagate an obsolete blue container edge.
- This is a navigational state correction, not a route, owner or financial-signal change.

### 2. Append one central Builder sources section to Migration Directory

Target: file 01M6XQ0KYY6ZDDV6F3G85SX6WW / p-1-0 / root board 1-0.

The root is an auto-height flex column: width1440px, padding64px, gap32px, height fit-content. Append a new sibling after existing 1T-0. That existing directory panel is column/gap14px/padding28px/bg#F7F8FA. Its final child 1X-0 is historical migration evidence. Preserve that text and the source/recovery block C-0.

A compact section can expose the candidate source guide plus the migrated Paper build page, without spreading implementation footnotes into product frames or editing archives. Distinguish source implementation candidate from native build reference.

Suggested entries:
- Bonds R33: source/inspector implementation candidate; native study and S05 build map.
- Shared shell F01: operative candidate.4; PARTIAL / RIG draft; implementation handoff and joint contract. Candidate.5 is proposed, not adopted.
- BioCatalyst and Government Revenue: existing native builder contracts and product-page destinations.
- Forex guided studies: existing native source reference, not latest production authority.

The existing directory1-0, index24-0 and inspected signposts export blue URL spans rather than href attributes. Do not call a visual link clickable without a verified retained link and actual open behavior.

### 3. Give migrated route registers a page crosswalk, preserving original IDs

BioCatalyst builder board1-0 contains a rich route/state register but still references original p-K-0 / p-S-1 and old artboard IDs. It explicitly says DESIGN ROUTING CONTRACT — NOT CLICKABLE LINKS. Do not blindly replace historical IDs with guessed ones.

Expose the verified page mappings centrally (below) and retain old IDs as provenance. Artboard-level crosswalk must come from the actual migration receipt/current-node inspection before further changes. This preserves the only detailed source/state/recovery contracts.

## Verified source-guide URLs

### Bonds R33

PR9578 is open and unmerged at observed head 34a32ff08b9e8296863668440adb208feac126f2.

Verified guide:
https://github.com/mastermindx-market-intelligence/macro/blob/34a32ff08b9e8296863668440adb208feac126f2/research/bonds_transmission_r30_2026-10-18/r33/SESSION_HANDOFF_2026-10-18.md

Path:
research/bonds_transmission_r30_2026-10-18/r33/SESSION_HANDOFF_2026-10-18.md

The same path returns404 at pinned Macro main b5674d8ef898e503d6164922654f5ff89be9981c. This is a candidate source destination, not a main-branch implementation.

The guide preserves BUILT_NOT_PROVEN, production_acceptance=false / mission_complete=false context. Existing offline/native acceptance remains bounded. The Paper start badge “Interactive reference verified” is supported as an offline/reference claim and should not be declared false. Better surface the candidate source link than broadly rewrite its status.

Current Paper study:
https://app.paper.design/file/01M6Y3T1K3573JYPMBATASW1W5/p-1-0
Start1-0; S05 implementation map11G-0.

S05 already contains routes01–08, toolsI01–I15, identity/time/return/save contracts, source clocks and missing evidence, production connections pending, Investigationv2/Alerts reuse and local-reference scope. Preserve that depth.

### Shared shell F01

PR10645 is open at observed source head dce261d07ebc993e8a9579cca2200e445b6636d4.

Verified handoff:
https://github.com/mastermindx-market-intelligence/macro/blob/dce261d07ebc993e8a9579cca2200e445b6636d4/research/design_candidates/production_design_20261102/f01/IMPLEMENTATION_HANDOFF.md

Verified operative contract:
https://github.com/mastermindx-market-intelligence/macro/blob/dce261d07ebc993e8a9579cca2200e445b6636d4/research/design_candidates/production_design_20261102/f01/JOINT_SHELL_SYSTEM_CONTRACT.md

Native F01:
https://app.paper.design/file/01M6Y2GT8S3YP4TK052PPESZEC/p-1-0

Native integration:
https://app.paper.design/file/01M6Y2GT8S3YP4TK052PPESZEC/p-2-0
Builder30C-0; entry2WG-0; state contract2YL-0.

The migrated readme UZ-0 still labels candidate.1 and p-23-0 references. Source PR says candidate.4 operative, candidate.5 PROPOSED_NOT_ADOPTED; acceptance PARTIAL / REQUEST_CHANGES / RIG draft. This does not authorize altering held original effects.

Fences: original atlas F01-20261103-c4-state-8-v1 at710Z-0/711X-0 is EFFECT_UNKNOWN; original readme F01-20261103-c4-readme-concurrence-v2 at6ZZX-0 is DOCUMENT_CHANGED,retry_allowed:false. No migrated-clone correction should replay/rehome those effects. Central independent source navigation is safe in principle, subject to root's fresh snapshot.

## Verified old/new page mappings

Old file for all first four rows:
https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P

| Original page | Readback node | Exact migrated destination | Role |
|---|---|---|---|
| p-27-0 |74XL-0|https://app.paper.design/file/01M6Y2GT8S3YP4TK052PPESZEC/p-1-0|F01 candidate|
| p-23-0 |74Z6-0|https://app.paper.design/file/01M6Y2GT8S3YP4TK052PPESZEC/p-2-0|Shared shell integration|
| p-K-0 |74VH-0|https://app.paper.design/file/01M6Y34XE4JKS3A40GMMZ954JE/p-2-0|BioCatalyst product reference|
| p-S-1 |74P5-0|https://app.paper.design/file/01M6Y3397SE03G626MJ72N90PF/p-2-0|Government Revenue R5 product reference|
| p-T-0 Hub signpost |61O3-0|https://app.paper.design/file/01M2VWK62FA5S4VVF6G7SBPE5J/p-1-0|Existing current Hub working file|

Hub signpost explicitly retains its historical source separately:
https://app.paper.design/file/01M6Y486E4X85MVP1AWS8H6E53/p-1-0

Native builder destinations:
- BioCatalyst: https://app.paper.design/file/01M6Y34XE4JKS3A40GMMZ954JE/p-1-0 ; blueprint1-0.
- Government Revenue: https://app.paper.design/file/01M6Y3397SE03G626MJ72N90PF/p-1-0 ; blueprint1-0; R11 state/recovery component2G-0.
- Forex guided source revisions: https://app.paper.design/file/01M6Y4CC5V5NZ92G3A0X3XZN3B/p-1-0 ; decisions1-0, source mappingU-0, return contract2H-0.

No GitHub guide was independently established for those three native-builder rows in this bounded review. Use native notes rather than inventing a source path.

## Preserve and classify

- Migration directory/start already separates working originals, recovery and newer product authorities. Keep migration fidelity counts as historical claims; they are not production acceptance.
- Gov Revenue blueprint1-0 explicitly rejects the old funding-first front door: stock setup/action uses existing signal owner; catalyst evidence is contextual. Preserve current R5 front-door guidance when following older Bio/Gov cross-domain notes.
- BioCatalyst detailed blueprint is valuable: exact source/version identity, observation clocks, unknown versus zero, pending/failed/uncertain save, reconciliation before retry, focus/context return, responsive/keyboard coverage and no Paper-runtime equivalence.
- Forex R1 builder guide identifies specific semantic risks (comparison baseline, currency versus pair direction, normalized liquidity explanation, sided rate gap) and preserves gated watch activation. Keep this as source reference; no newly inferred shipping status.
- Shared shell30C-0 separates reachable, journey accepted and natively converted. It has dated20Oct runtime observations; do not promote or erase them without refreshing those actual owners.
- Sector R2 board1-0 calls itself current build direction within its dated27Sep revision and retains old reference-library coordinates. New Sector R4 file01M6FAXA774QT1VRDMAG7DFQ2W is provisional in current inventory. Do not automatically call R2 rejected or R4 accepted solely because R4 is newer. Directory entry can label “R2 design revision” and expose newer candidate separately.
- Archive/recovery/canary/source-only material receives classification and navigation context, not sweeping interior restyling. Preserve unique contracts and accepted historical evidence.

## No additional mutations recommended from this evidence

Intraday Flow, T47 search, crypto/commodity/history, MedTech, memory and other cohort pages were inventoried but not deeply inspected. Do not claim their content or interactions passed review. A future focused audit can use the coverage file to pick current work without re-reading all archives.

