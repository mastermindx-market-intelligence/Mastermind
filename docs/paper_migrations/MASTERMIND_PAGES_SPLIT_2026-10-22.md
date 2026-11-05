# MASTERMIND PAGES - safe split / relocation inventory (2026-10-22)

**State: INVENTORIED, NOT MOVED. Do not claim the original file is smaller.**

- Original: https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P
- Verified on 2026-10-22 via Paper Desktop fileId + pageId reads: **63 pages / 139,812 nodes / 903 artboards**.
- Node and artboard counts indicate relative density, **not** file bytes or guaranteed quota reduction.
- Paper explicitly warns: "Your file is too large. Further changes will result in data loss. Please start a new file."
- The connected Mastermind Paper adapter can inspect/get JSX/create pages in a bound existing file, but does not permit file creation, cross-file page copy/move, or page/node deletion. No original pages were modified by this audit.
- During the audit, archived commodities duplicate `p-19-0` was present in the first file inventory; a subsequent list excluded it, and an explicit page read returned `Page not found`. This is external change or drift and is not part of our 63 verified pages. Do not infer who removed it or whether its contents survived.

## Highest-priority heavy pages

| Page | Nodes | Artboards | Proposed home |
|---|---:|---:|---|
| [Forex Guided Intelligence R1](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-N-1) | 14,225 | 101 | 09 Forex R1 - subdivide artboards |
| [ARCHIVE Sector Intelligence Legacy Studies](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-Z-0) | 11,638 | 71 | 19 Sector archive - subdivide artboards |
| [Live Site Baselines Wave 1](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-8-1) | 11,305 | 10 | 18 Live site baselines - subdivide artboards |
| [ARCHIVE Intelligence Hub R4 Original Source](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1A-0) | 7,087 | 66 | 13 Intelligence Hub archive - dedicated |
| [Sector Intelligence R3 Completion 2026-10-21](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-24-0) | 7,065 | 23 | 04 Sector R3 - dedicated |
| [Commodities R1 Study](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-L-0) | 5,664 | 39 | 12 Macro commodities |
| [ARCHIVE Bonds and Transmission pre-R30](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1Y-1) | 5,121 | 28 | 08 Bonds archive - dedicated |
| [Gov Revenue Signal Desk R5](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-S-1) | 4,362 | 25 | 15 Gov and Bio builders |
| [Bonds Decision Workspace R1](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-O-1) | 4,299 | 29 | 07 Bonds current studies |
| [Shared Market All Tools and Research Launcher Reference](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1R-0) | 3,925 | 16 | 03 Shared market references |
| [Sector Intelligence R2 Current Build](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-Y-0) | 3,840 | 26 | 05 Sector R2 and references |
| [News Intelligence](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-3-1) | 3,509 | 20 | 16 News breadth and confluence |
| [Forex Advanced Movement and Decision Studies R17-R24](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1F-0) | 3,411 | 23 | 10 Forex archive |
| [Shared Market Prepared Research and Reading Reference](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1U-0) | 2,877 | 20 | 03 Shared market references |
| [ARCHIVE Crypto Intelligence R1-R2](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-11-0) | 2,807 | 23 | 11 Crypto |

## Destination files / estimated load

Each destination below is a proposed new Paper file, NOT a created file. For a destination over ~8,000 nodes, further split into multiple files by artboard group; 8,000 is a planning target only, not a published Paper limit.

| Proposed destination | Pages | Nodes | Artboards |
|---|---:|---:|---:|
| 01 Design system | 3 | 1,290 | 22 |
| 02 Shared shell | 3 | 4,362 | 31 |
| 03 Market memory | 1 | 574 | 8 |
| 03 Shared market references | 4 | 10,181 | 76 |
| 04 Sector R3 - dedicated | 1 | 7,065 | 23 |
| 05 Sector R2 and references | 4 | 3,885 | 29 |
| 06 Terminal | 9 | 5,050 | 36 |
| 07 Bonds current studies | 3 | 9,112 | 52 |
| 08 Bonds archive - dedicated | 1 | 5,121 | 28 |
| 09 Forex R1 - subdivide artboards | 1 | 14,225 | 101 |
| 10 Forex archive | 4 | 6,696 | 45 |
| 11 Crypto | 2 | 3,798 | 31 |
| 12 Macro commodities | 3 | 6,180 | 46 |
| 13 Intelligence Hub archive - dedicated | 5 | 10,610 | 98 |
| 14 Catalyst and policy | 4 | 3,450 | 38 |
| 15 Gov and Bio builders | 6 | 11,061 | 78 |
| 16 News breadth and confluence | 4 | 7,745 | 48 |
| 17 Bot designs | 1 | 2,000 | 13 |
| 18 Live site baselines - subdivide artboards | 1 | 11,305 | 10 |
| 19 Sector archive - subdivide artboards | 1 | 11,638 | 71 |
| 20 Misc legacy archives | 2 | 4,464 | 19 |

## Controlled migration sequence

1. **Freeze writes to the oversized source** while obtaining a native Paper backup/version-history recovery point, and coordinate with live canvas editors. Do not assume no concurrent work because the file changes during reads.
2. **Create new, empty Paper files through the official Paper UI** for the target product groups. The current Mastermind connector intentionally does not support this operation. Do not bypass that restriction through a hidden host export or deletion API.
3. **Copy, never cut first.** For each source page or artboard group, use Paper-native editable content copy/paste or an officially supported duplication path. Do not substitute PNG/JSX screenshots for editable source as proof of equivalence.
4. **Verify destination** against each source page: artboard count/names, layouts (desktop/tablet/mobile), layers/editability, typography, shared tokens, image assets, interactions, comments, and evidence/implementation annotations. Copy the original theme/tokens when required (Paper docs: https://paper.design/docs/tokens).
5. **Record old-to-new mapping:** original file/page/artboard -> new file/page/artboard links, and update original builder references after new IDs exist. Retain original until readback and screenshots are accepted.
6. **Only then remove originals via the reviewed native Paper UI workflow**, in small batches, with a fresh backup and observation after every batch. If Paper still warns about possible data loss, stop. Never issue a destructive cleanup through Mastermind Paper read/edit bypasses.
7. **End-state proof:** active product pages load quickly, source file no longer emits oversize warning, all moved destination artboards remain editable and visually equivalent, and internal implementation/PR links resolve.

## Full page inventory

| Source page and link | Nodes | Artboards | Proposed destination |
|---|---:|---:|---|
| [p-5-0: Archetype Starters - Governed](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-5-0) | 362 | 9 | 01 Design system |
| [p-24-0: Sector Intelligence R3 Completion 2026-10-21](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-24-0) | 7,065 | 23 | 04 Sector R3 - dedicated |
| [p-23-0: Shared Shell Completion and Integration R1](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-23-0) | 1,938 | 17 | 02 Shared shell |
| [p-22-0: Market Memory Evidence workspace R1](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-22-0) | 574 | 8 | 03 Market memory |
| [p-21-0: Terminal Chart Context R1](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-21-0) | 1,003 | 2 | 06 Terminal |
| [p-20-0: Catalyst Intelligence Decision Desk R1](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-20-0) | 776 | 10 | 14 Catalyst and policy |
| [p-1Z-1: Catalyst-to-Opportunity Source-bound integration](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1Z-1) | 315 | 5 | 14 Catalyst and policy |
| [p-1Y-1: ARCHIVE Bonds and Transmission pre-R30](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1Y-1) | 5,121 | 28 | 08 Bonds archive - dedicated |
| [p-1X-1: Forex Archive Prior studies and build history](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1X-1) | 2,277 | 15 | 10 Forex archive |
| [p-1W-1: Macro Dark Flow Implementation](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1W-1) | 111 | 2 | 12 Macro commodities |
| [p-1V-0: Terminal Portfolio Builder and Acceptance References](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1V-0) | 209 | 2 | 06 Terminal |
| [p-1U-0: Shared Market Prepared Research and Reading Reference](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1U-0) | 2,877 | 20 | 03 Shared market references |
| [p-1T-0: Shared Market Watchlists and Save States Reference](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1T-0) | 1,956 | 22 | 03 Shared market references |
| [p-1S-0: Shared Market Search and Comparison Reference](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1S-0) | 1,423 | 18 | 03 Shared market references |
| [p-1R-0: Shared Market All Tools and Research Launcher Reference](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1R-0) | 3,925 | 16 | 03 Shared market references |
| [p-1Q-0: Design Foundations Components and Archetype Rules](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1Q-0) | 870 | 10 | 01 Design system |
| [p-1P-0: START HERE Product and File Navigation](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1P-0) | 58 | 3 | 01 Design system |
| [p-1O-0: Terminal Portfolio Personal Desk](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1O-0) | 1,218 | 6 | 06 Terminal |
| [p-1N-0: Gov Revenue Builder Contracts and State Specimens](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1N-0) | 550 | 2 | 15 Gov and Bio builders |
| [p-1M-0: BioCatalyst Builder and Acceptance Contracts](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1M-0) | 566 | 3 | 15 Gov and Bio builders |
| [p-1L-0: ARCHIVE Synthetic Catalyst Investment Cases](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1L-0) | 1,293 | 11 | 15 Gov and Bio builders |
| [p-1K-0: MedTech Regulatory Catalyst R13 References](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1K-0) | 1,918 | 14 | 15 Gov and Bio builders |
| [p-1J-0: REFERENCE Policy Watch R2-R3 and HELD](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1J-0) | 1,205 | 14 | 14 Catalyst and policy |
| [p-1I-0: ARCHIVE Commodities Legacy 90-94](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1I-0) | 405 | 5 | 12 Macro commodities |
| [p-1H-0: Bonds Advanced Mechanism and Decision Studies R18-R25](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1H-0) | 2,340 | 12 | 07 Bonds current studies |
| [p-1G-0: Terminal R3 Refraction Top-edge only](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1G-0) | 43 | 3 | 06 Terminal |
| [p-1F-0: Forex Advanced Movement and Decision Studies R17-R24](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1F-0) | 3,411 | 23 | 10 Forex archive |
| [p-1E-0: Cross-Asset Bonds x Forex Transmission and Confluence](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1E-0) | 2,473 | 11 | 07 Bonds current studies |
| [p-1D-0: Terminal Settings Original Pane Aurora Only R2](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1D-0) | 344 | 3 | 06 Terminal |
| [p-1C-0: Terminal Account and Settings](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1C-0) | 288 | 2 | 06 Terminal |
| [p-1B-0: ARCHIVE Earnings and Dossiers Original Source](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1B-0) | 698 | 5 | 06 Terminal |
| [p-1A-0: ARCHIVE Intelligence Hub R4 Original Source](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-1A-0) | 7,087 | 66 | 13 Intelligence Hub archive - dedicated |
| [p-18-0: Investor Shell Market Overview Design Candidates](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-18-0) | 262 | 3 | 02 Shared shell |
| [p-17-0: REFERENCE Forex Alternate R19-R21 Studies](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-17-0) | 870 | 6 | 10 Forex archive |
| [p-16-0: ARCHIVE Forex Duplicate Study](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-16-0) | 138 | 1 | 10 Forex archive |
| [p-15-0: Returns Calendar Terminal and Dossier](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-15-0) | 1,237 | 12 | 06 Terminal |
| [p-14-0: Bot Paper Portfolio V3 Upgrade](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-14-0) | 2,000 | 13 | 17 Bot designs |
| [p-Q-0: Earnings and Dossiers North Star Study - placeholder](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-Q-0) | 10 | 1 | 06 Terminal |
| [p-3-1: News Intelligence](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-3-1) | 3,509 | 20 | 16 News breadth and confluence |
| [p-D-0: Mastermind Shared Shell Review 01](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-D-0) | 2,162 | 11 | 02 Shared shell |
| [p-13-1: Market Breadth Command Center R1](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-13-1) | 1,563 | 3 | 16 News breadth and confluence |
| [p-A-0: Confluence Screener Governed Reference](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-A-0) | 1,102 | 12 | 16 News breadth and confluence |
| [p-H-1: Confluence Screener R2](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-H-1) | 1,571 | 13 | 16 News breadth and confluence |
| [p-O-1: Bonds Decision Workspace R1](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-O-1) | 4,299 | 29 | 07 Bonds current studies |
| [p-N-1: Forex Guided Intelligence R1](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-N-1) | 14,225 | 101 | 09 Forex R1 - subdivide artboards |
| [p-J-1: Policy Watch Decision Desk R1 Study](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-J-1) | 1,154 | 9 | 14 Catalyst and policy |
| [p-8-1: Live Site Baselines Wave 1](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-8-1) | 11,305 | 10 | 18 Live site baselines - subdivide artboards |
| [p-T-0: Intelligence Hub Unified US and China R4 - placeholder](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-T-0) | 10 | 1 | 13 Intelligence Hub archive - dedicated |
| [p-10-0: Crypto Intelligence R3 Current Build](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-10-0) | 991 | 8 | 11 Crypto |
| [p-L-0: Commodities R1 Study](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-L-0) | 5,664 | 39 | 12 Macro commodities |
| [p-Y-0: Sector Intelligence R2 Current Build](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-Y-0) | 3,840 | 26 | 05 Sector R2 and references |
| [p-S-1: Gov Revenue Signal Desk R5](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-S-1) | 4,362 | 25 | 15 Gov and Bio builders |
| [p-K-0: BioCatalyst North Star and Build Blueprint](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-K-0) | 2,372 | 23 | 15 Gov and Bio builders |
| [p-Z-0: ARCHIVE Sector Intelligence Legacy Studies](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-Z-0) | 11,638 | 71 | 19 Sector archive - subdivide artboards |
| [p-V-0: ARCHIVE Company Intelligence](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-V-0) | 1,931 | 5 | 20 Misc legacy archives |
| [p-11-0: ARCHIVE Crypto Intelligence R1-R2](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-11-0) | 2,807 | 23 | 11 Crypto |
| [p-X-0: ARCHIVE Intelligence Hub R1-R3](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-X-0) | 2,420 | 25 | 13 Intelligence Hub archive - dedicated |
| [p-W-0: ARCHIVE International Markets R9](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-W-0) | 2,533 | 14 | 20 Misc legacy archives |
| [p-E-1: Sector Intelligence vNext Study - placeholder](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-E-1) | 25 | 1 | 05 Sector R2 and references |
| [p-6-1: Sector Intelligence Unified Detail - placeholder](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-6-1) | 10 | 1 | 05 Sector R2 and references |
| [p-I-1: Intelligence Hub R1 Study - placeholder](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-I-1) | 25 | 1 | 13 Intelligence Hub archive - dedicated |
| [p-9-0: Sector Central Redesign - placeholder](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-9-0) | 10 | 1 | 05 Sector R2 and references |
| [p-7-1: China Intelligence vNext](https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-7-1) | 1,068 | 5 | 13 Intelligence Hub archive - dedicated |

## Effect ledger / release status

- All inspection reads: READ_ONLY / EFFECT_NONE.
- Paper original page content: NO_WRITE_BY_THIS_AUDIT. No new Paper files created; zero pages transferred; no original pages deleted by this session.
- Unknown external change: `p-19-0` no longer found when explicitly requested; requires native history/owner reconciliation before relying on that page.
- Source procedure: `mastermindx-market-intelligence/Mastermind` protected `master` at `d31aade92b969e8897513d8634ecd59dba00e1e3`, Sol Skillpack `1.0.1`.
- Exact next blocker: safe cross-file file/page creation/migration plus source deletion has no permitted modifying tool on the connected Paper MCP interface. Use a Paper-approved interactive UI carrier only with independently authorized host/effect, or add an explicitly reviewed capability to the existing guarded adapter; do not synthesize migration by bypassing blocked tools.
