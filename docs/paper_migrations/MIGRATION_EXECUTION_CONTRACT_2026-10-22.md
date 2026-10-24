# MASTERMIND PAGES - Migration Execution and Adapter Acceptance Contract (2026-10-22)

**State: PREPARED; ZERO PAPER TRANSFERS.** Companion to the existing 63-page inventory in Mastermind PR #1721 (https://github.com/mastermindx-market-intelligence/Mastermind/pull/1721). A document, generated plan, passing synthetic test, destination ID, or green adapter CI is never Paper migration.

- Original Paper file: 01M2WGNCX9475G79JRKJTCM08P (MASTERMIND PAGES): 63 observed pages / 139,812 nodes / 903 artboards. Counts are not storage bytes.
- Paper warning: "Your file is too large. Further changes will result in data loss. Please start a new file."
- Drift hold: page p-19-0 was visible on first read but absent on a later page list and explicit page read. Final state and initiating editor remain UNPROVEN. Reconcile native Paper history before any source deletion.
- Initial protected Sol pin: Mastermind d31aade92b969e8897513d8634ecd59dba00e1e3 / Skillpack 1.0.1. At inspection, subsequent protected master 21f9bf03e94883e5fc1e607fa9dbf99b15a2f909 changed no Paper source law in the compared revision.
- Adjacent adapter-owner draft PR #1722: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1722; observed head 9e9c848321b61e16d058dc07e2df6b33f0efe156. This contract neither modifies nor deploys that adapter.

## 1. Ownership and no-duplication boundary

| Concern | Canonical owner | This lane's participation |
|---|---|---|
| Editable design contents, page/artboard IDs, assets | Paper through an approved exact modifying carrier | Inventory, independent verification and future approved canaries |
| Guarded tools, tests, runtime, client publication | PR #1722 and existing Paper/Studio Direct owners | Acceptance constraints only; no adapter edits |
| Destination partition proposals and safety checks | PR #1721 | Own inventory, offline planner and migration contract |
| Production tokens and product design system | Mastermind design-system source plus Macro product authorities | Re-extract after confirmed relocation; no blind token replacement |
| Product implementation evidence and live links | Macro, Terminal and existing PR/workspace owners | Find impacted current links; send precise rewrites to their owners |
| Lifecycle, effect reconciliation and organizational continuity | Existing Executive OS / Agent OS | No new queue, registry, lease, retry, publication or authority plane |

Source-law guard: Inspect the actual action, capability, source, target, writer and effect before every future write. Technical access is not permission. Ambiguous effects stay on the SAME original carrier; no blind retry and no bypass through generic host/browser, alternate app/account or raw vendor endpoint.

## 2. Distinguish adapter preparation from lossless transfer

Draft PR #1722 describes the following SOURCE-ONLY, NOT-DEPLOYED additions:

| Proposed capability | What it may enable after publication and canary | What it cannot prove |
|---|---|---|
| list_resources | Admitted resource identification | Arbitrary host/raw resource access |
| Guarded blank-file create | Independently identified new destination | Any transferred design content |
| Guarded whole-file clone | Whole-file duplicate | Smaller original or one individually migrated page |
| Guarded exact-file rename_resource | Exact resource renaming | Transfer or retry after unknown effects |
| arrange_pages / update_pages | Same-file page ordering and metadata | Cross-file page move or original deletion |
| Existing move_nodes | Node move in actually supported target scope | Cross-file native page migration |
| Lossless cross-file page/artboard copy | **NOT QUALIFIED in PR #1722** | Must not infer this from an action containing "move" |
| Source page/file deletion | **NOT QUALIFIED in PR #1722** | Must not assume it exists |

A whole-file clone is as heavy as its source at creation. Do not create dozens of full-sized clones under a supposed "split". A legal native copy (including components, tokens, images and comments) and a separately legal source cleanup are still open dependencies.

Every new adapter action needs schema/catalog receipt, exact fileId, fresh snapshot guard, stable operation ID, serialized desktop effect, no-replay on ambiguous result, explicit target independent readback, and published client snapshot proof. Merely merged, staged or connected is insufficient.

## 3. Offline planner - committed and tested, not an effect plane

The new scripts/paper_migration_planner.py reads only docs/paper_migrations/MASTERMIND_PAGES_INVENTORY_2026-10-22.json. It contains no Paper credentials, network calls, host controls, move tool, delete code or runtime status writer. The output is a proposal, not a work order or migration permission.

Generate:

    python3 scripts/paper_migration_planner.py --inventory docs/paper_migrations/MASTERMIND_PAGES_INVENTORY_2026-10-22.json --out /tmp/mastermind-paper-offline-plan.json

Verify reproducibility and false-green rejection:

    python3 scripts/paper_migration_planner.py --inventory docs/paper_migrations/MASTERMIND_PAGES_INVENTORY_2026-10-22.json --check-plan /tmp/mastermind-paper-offline-plan.json
    python3 -m unittest tests.test_paper_migration_planner -v

The planner refuses duplicated source IDs, wrong file IDs/links, inconsistent totals, impossible counts, invented migration status and the unreconciled p-19-0 being treated as an observed source page.

Planning targets: 6,000 nodes OR 32 artboards per new volume, deliberately conservative heuristics; **not** Paper limits or demonstrated safe file sizes. Initial deterministic result:

- 21 product families.
- 57 pages eligible for whole-page *planning* units.
- 27 candidate volumes for those 57 pages.
- 6 pages held for measured per-artboard splitting: p-N-1 (Forex R1; 14,225 nodes/101 boards), p-Z-0 (Sector legacy; 11,638/71), p-8-1 (Site baselines; 11,305/10), p-1A-0 (Intelligence Hub R4 archive; 7,087/66), p-24-0 (Sector R3; 7,065/23), p-L-0 (Commodities R1; 5,664/39).

Do not partition a large page by equally splitting its boards: the node distribution is unknown and a single board might dominate. Obtain actual per-artboard measurements and shared dependency boundaries first. Input snapshot and its fingerprint must be renewed for real transfers.

Keep themed destinations navigable; preserve related dark/light, EN/ZH, mobile/desktop, error/degraded states and shared component instances together where necessary. Avoid enormous catch-all archives and an enlarged START HERE file.

## 4. Required ordered phases; no implied permission

### Phase A - reconcile source and protect

1. Read exact source file/page/artboard IDs, fresh snapshot, active writer/custody and visible warning; diff the current set against the initial 63-page inventory. Record observed changes rather than overwriting historical evidence.
2. Resolve p-19-0 through native version history and involved editing operation. Coordinate actual overlapping source targets; do not freeze disjoint work indefinitely because of a ghost owner.
3. Create/identify a Paper-supported native backup/version history point and **prove a safe reopen and restoration in a disposable location**. An image export or JSX is not a restorable editable source backup. Do not tunnel blocked export/delete methods through read-only tools.
4. If backup or the warning cannot be safely handled, restrict this lane to read-only and disposable scratch work.

### Phase B - scratch qualification for PR #1722

Through the actual released/published and admitted carrier: create a disposable blank file, observe exact returned ID, independently reopen it and read back. Qualify whole-file clone and distinguish source/clone identity. Test resource rename, page metadata/order, stale snapshot, wrong target ID, permission refusal, concurrency and lost-response reconciliation. Never rely only on one tool's success.

Representative scratch fixtures must include nested groups, instances, tokens, typography, images, hidden states, mobile/desktop, light/dark, EN/ZH and comments/interactions. Individual feature success does not qualify a different modifying action or an unseen seat.

### Phase C - bounded destination provision

Create only a few independently verified small destination files under exact published authorization. Store exact target file IDs in the existing program/PR record, not a new tracker. The creation response alone is RESPONSE_OBSERVED_REQUIRES_TARGET_VERIFICATION. Avoid bulk oversized whole-file clones.

### Phase D - copy-only transfer

Copy with a genuinely supported editable native operation (or reviewed lossless vendor equivalent). Capture exact original file/page/artboard IDs -> new file/page/artboard IDs. No screenshot, JSX, static HTML, flattened image or reimplemented approximate mockup qualifies. Require pre-read + one modifying carrier/operation + independent target and source readback. Lost effects remain EFFECT_UNKNOWN at original action; inspect before further writes.

No native cross-file transfer support means Phase D stays BLOCKED. Do not disguise it as same-file move, export or file creation.

### Phase E - quality and native data-fidelity proof

For EACH transfer unit, compare native node hierarchy, editability, frame sizes/constraints, hidden states, components/instances, fonts, tokens, image and external assets, interactions/prototype states and comments. Explicitly mark metadata that the vendor cannot preserve; withhold lossless acceptance if consequential. Compare real screenshots under representative responsive/theme/locale states, review actual readable visual hierarchy, and close/reopen the destination via its new ID. Confirm source remains unchanged until cutover and backup is still restorable.

Node count, matching artboard names, synthetic CI, and adapter create response alone are insufficient.

### Phase F - reference rewrites with source provenance

After new links exist, scan owning repositories again for the original Paper file ID and every migrated page/artboard ID. Update *current build/design* links through their normal owners and protected PRs. Preserve immutable historical evidence citations or annotate archival relocation; never blind global-replace IDs.

Known downstream anchors discovered on current default branches:

- Mastermind skills/mastermind-design-system/manifest.json, skills/mastermind-design-system/references/paper-sources.md, skills/mastermind-design-system/tokens/mastermind.tokens.json. Governed design reference p-5-0 requires a fresh re-extraction and review, not a JSON string substitution.
- Macro research/forex_r26_2026-10-20/OWNER_INTEGRATION.md binds p-N-1 and many other design/research reports reference MASTERMIND PAGES. Also Shared Shell/design source.
- Terminal terminal/docs/pr-crops/chart-context-redesign/DESIGN.md binds p-21-0, terminal/settings R3 references p-1G-0 and portfolio/options build evidence binds other pages.

GitHub search was bounded and is **not** an exhaustive link census. At cutover, scan all relevant tracked files and verify each current new link resolves.

### Phase G - separately admitted cleanup and acceptance

Remove an original ONLY through separately reviewed vendor capability and operator authority, after backup, exhaustive mapping, native fidelity, ownership, URL integrity and effect reconciliation are proven. Unsupported or denied deletion holds that lane; no bypass. The unresolved p-19-0 history holds original-file destructive cleanup.

After each small admitted cleanup unit, re-read both documents. Real completion requires: original file measurably smaller or below the vendor danger condition, no oversize data-loss warning, valid new native editable content, original/current links resolved and representative visual checks after reopening. Source code merge, CI success, adapter publication, target creation and actual content migration are DISTINCT receipts.

Do not attempt to write START HERE into the unsafe original merely to add redirects. Place navigation in a healthy new lightweight file until the original is safe.

## 5. Exact evidence fields under existing canonical owner

| Field | Required observation |
|---|---|
| Identity | Original and destination file/page/artboard IDs and exact URLs |
| Source | Fresh source snapshot and observed item census; writer/lease/effect safety |
| Recovery | Native version-history or verified restorable copy plus restoration proof |
| Adapter | Exact installed immutable runtime SHA; published action schema/catalog; admitted seat/carrier |
| Effect | Stable operation ID; pre-dispatch/response class and independent source/target post-read |
| Fidelity | Native hierarchy, tokens/components/assets/comments/prototypes, screenshot comparison, reviewer |
| References | Changed current links and preserved historical source links, resolved target URL proof |
| Cleanup | Separate reviewed delete support, bounded admitted batch and before/after source readback |
| Final health | Post-change original warning absent and new editable file opens to useful product design |

This is an evidence checklist, **not a second lifecycle, state machine or deletion authorization**. Do not label a completed transfer from RESPONSE_OBSERVED_REQUIRES_TARGET_VERIFICATION.

## 6. Failure injection cases to demand before source cleanup

| Case | Expected guard |
|---|---|
| File-creation reply lost but file was created | EFFECT_UNKNOWN; same-carrier original-effect reconciliation; no duplicate |
| Guessed or mismatched fileId | Typed pre-dispatch refusal without mutation |
| Source or destination changed after snapshot | Stale-snapshot refusal; re-read only once preceding effect is known |
| Two agents change overlapping page metadata | Coordinate exact scope and reject collisions, preserve disjoint work |
| Different files have identical names | Never identify by display name |
| Whole-file clone counted as page transfer | Reject acceptance; original is still full |
| Node/artboard count matches but token/image/instance differs | Withhold editable-content proof and source cleanup |
| Hidden state, interaction or comments missing | Hold lossless transfer acceptance |
| Large page has uneven artboard weights | Measure actual per-artboard structure, refuse naive equal partition |
| Delete tool unavailable/denied | Halt cleanup without carrier/tool bypass |
| Concurrent editor changes source during copy | Reconcile affected exact page and operation, do not blanket overwrite |
| p-19-0 absent at later read | Reconcile native history; do not report deleted/restored without evidence |

## 7. Exact independent work boundaries and next actions

- **Adapter PR #1722 owner:** independently finish review/CI/runtime release, actual published action inspection, scratch canary and write-catalog readback; report exactly which operations are available. Cross-file lossless page copy and page deletion remain unmet in its current advertised scope.
- **Migration PR #1721 owner:** finish deterministic preflight/test and reference impact inventory; protect original and stage small, non-destructive destination names/records only once capability is qualified.
- **Joint interface:** when a genuine native cross-file copy becomes available, use the **exact live source** archived Forex duplicate `p-16-0`, artboard `1N0G-0` ("ARCHIVE COPY · Forex ZH Dark Mobile Overview"; 390px mobile; page 138 observed nodes) for the first non-destructive ZH/nested-frame test. The second observed multi-artboard specimen is archived Earnings/Dossiers `p-1B-0`, 698 page nodes / 5 boards, including `1CR6-0` ("10 · DESKTOP · Earnings Command Center"; 1440×1000). These are bounded source identities, **not** transfer receipts or proof that images/components are present; select an image-bearing specimen only after actual asset census. Never delete originals as part of a canary.
- **Critical path after canary:** large archival pages first, then active/product-linked pages with usual builder/link custody; do not prioritize by node count alone if semantic or effect risk is greater.

**Current finalization: MORE_WORK_EXISTS, migration not accepted.** Do not mark the original file cleaned up merely because this companion is committed.


## 8. Official Paper vendor capability and version compatibility research

Official Paper documentation consulted on October 22, 2026:

- https://paper.design/downloads now advertises **Paper Desktop and MCP v0.5.16, dated October 15, 2026**. The live inspected Mastermind adapter session reported paper-desktop **v0.5.14**. Do not infer current local update from the download page, and do not auto-upgrade a shared live desktop under an active bridge's 37-tool catalog pin. Capture actual installed vendor version **and complete catalog SHA** before accepting any new adapter write; if drift, fail closed and have the existing adapter-owner qualify it.
- https://paper.design/docs/support documents native **selection copy/paste** keyboard shortcuts and multiple-file workflows in the desktop UI, but does not, by itself, prove lossless editable **cross-file page** transfer, component references or comment preservation. A source-artboard -> new-file paste is a **scratch canary hypothesis**, not an authorized backend/API path and not verified user-content relocation.
- https://paper.design/docs/tokens explicitly documents copying tokens from one file's Theme tab to another. It also says copied tokens **do not update when changed in a different file**. Therefore each destination must have an explicit repository-derived token projection, post-copy token inventory and future drift checks. A copied palette is *not* a new shared live design-system authority.
- https://paper.design/build-log advertises multiple-file desktop tabs and file duplication, plus later performance work for larger files. Those improvements do not prove that this original file's data-loss warning has disappeared or that the vendor imposes the provisional 6,000-node planning target.

**Engineering inference, not vendor promise:** A compatible, authorized native clipboard copy can be tested on an entirely disposable pair of Paper files while waiting for a reviewed cross-file MCP tool. First copy tokens into the target scratch file, then copy ONE simple native artboard, then a component/image-rich board, and compare deeply. If fidelity fails, abandon this path; never recreate from HTML/JSX and call it lossless. The source 63-page file remains read-only during this feasibility check.

**Specific adapter PR #1722 compatibility requirement:** treat release publication/installed source SHA/catalog SHA as distinct. The historical 0.5.14 full-catalog digest is not guaranteed to match 0.5.16. A version bump alone is not a proof of drift or compatibility; compare the actual reviewed catalog and accepted schema under the existing bridge and no-replay laws.


## 9. Tracked-source link-impact scanner and safe report output

The separate scripts/paper_link_reference_audit.py provides a reproducible local tracked-file census for **specific existing Git worktrees**, using the known original file ID and the 63-page inventory. Example, after replacing the sample paths with actual authorized Git roots:

    python3 scripts/paper_link_reference_audit.py \
      --inventory docs/paper_migrations/MASTERMIND_PAGES_INVENTORY_2026-10-22.json \
      --root mastermind=/ABSOLUTE/PATH/TO/Mastermind \
      --root macro=/ABSOLUTE/PATH/TO/macro \
      --root terminal=/ABSOLUTE/PATH/TO/mastermind-terminal \
      --out /tmp/mastermind-paper-link-impact.json

It uses local git ls-files (tracked files only) and bounded UTF-8 text reads, refuses a non-repository root and symlinks, reports skipped oversized/binary files instead of silently claiming completeness, identifies known vs historical/unknown page IDs, and never edits source links. Treat source-file-ID-only references as requiring manual scope review. Preserve original evidence links when they are historical and rewrite current build links only through the owning source branch.

Both offline CLIs now create report files **exclusively** (refuse existing outputs rather than overwriting). The partition planner explicitly refuses to overwrite its input inventory; the link scanner refuses any report output path **inside one of the scanned Git roots**. These guards and synthetic temporary-Git fixtures have **16 locally passing tests** (the added 2 tests verify no source-inventory or tracked worktree corruption). This is *not* a hosted CI or production acceptance claim.

Known source archive refs are not automatically authorized destination mappings. After adapter/native copy qualification, re-run the live exact-file source read, generate a fresh mapping, then run this scanner against actual current worktrees. Resolve skipped files and references in historical branches as needed before marking link cutover complete.


## 10. Live source-drift and capped-artboard API finding (later October 22 read)

A later independent **read-only** exact source inspection returned **57 visible pages**, whereas an earlier inspection returned 63. This is a **source-list provenance disagreement**, not proof that six pages were moved or deleted between observations. The parallel adapter owner also reported 57 actual pages on M1 and M2, with resource updated_at 2026-10-17T06:41:53.472Z in the guarded v13 read-only resource listing (PR #1722 comment 6338671860). That timestamp is reported resource metadata, not a documented event history or a migration receipt. The exact six baseline pages absent from the current source list are **all Terminal**: p-21-0 (Chart Context), p-1V-0 (Portfolio Builder References), p-1O-0 (Portfolio Desk), p-1G-0 (R3 Refraction), p-1D-0 (Settings Original), and p-1C-0 (Account/Settings). See [source visibility delta](MASTERMIND_PAGES_DRIFT_2026-10-22.json). These six page IDs accounted for 3,105 nodes / 18 artboards **in the historical 63-page inventory**; this is not a direct before/after source byte measurement.

**Do not re-copy or recreate the six as though still present.** The 63-vs-57 disagreement might arise from prior organization, non-atomic state, tool representation, or other history not yet verified. Neither the timing, target Paper file ID nor native source-to-destination fidelity/cleanup receipt has been established by this workstream. A separate recent observation saw a Paper file named Terminal, but its exact ID and the destination of these particular six pages are unbound here. Unresolved p-19-0 remains distinct. Keep original-file destructive cleanup frozen while reconciling the existing operation/owner and actual target. The Paper oversize warning remains visible even with the 57-page list.


**Specific next provenance read, without modifying Paper:** The staged v13 adapter has already qualified read-only `list_resources` with 19 top-level resources. Ask the incumbent adapter owner to identify whether a separate resource named Terminal is among these resources, return its **exact file ID**, and (if available) compare the six historical page names/IDs in that exact destination with independent get_basic_info reads. Never infer a transfer from a name collision, recent editor focus, or the presence of a new blank destination. Preserve the original source file and the p-19-0 anomaly. 

The five other original-heavy page snapshots remained consistent. A sixth, **Forex R1 p-N-1**, reports 101 artboards, but Paper get_basic_info and get_children each **truncate their result to 100 artboards** (with a truncation flag). A separate read-only get_tree_summary at root depth 1 exposed all 101 top-level Frame IDs; get_node_info independently resolved the missing final board:

- Missing board: 6NKK-0 — R26 Watch lifecycle / Six state contracts / Future owner reference.
- [Heavy-page artboard identity index](HEAVY_PAGES_ARTBOARD_INDEX_2026-10-22.json) now records all **310 exact artboard identities across six heavy pages**, with method provenance and source warning.
- This is a recovered **ID/name census only**, NOT per-artboard subtree-node size, asset/token/component fidelity, layout acceptance or a viable partition. Tree readback is not a modification or a safe delete procedure.

The direct Paper tool catalog still showed **Paper v0.5.14 / 28 exposed tools** at this later read, with **no list_resources/create_file tool**. Thus draft PR #1722 is not production-proven or callable on this exact client action snapshot. Do not bypass its missing capabilities. The initial 63-page partition proposal is now **historical preflight**; future actual transfers require a refreshed exact-source plan that explicitly excludes/reconciles the six externally absent Terminal pages.


## 11. Visibility-aware offline plan and structural transfer-evidence preflight

The initial 63-page inventory is preserved as historical observation, and the [six-page visibility delta](MASTERMIND_PAGES_DRIFT_2026-10-22.json) is a read-only qualifier. Its now-preserved **complete returned 57-page identity list** must exactly partition the historic 63 page IDs with the six held entries; the strict offline validator rejects truncated, malformed, contradictory or ID-spoofed lists. A 57-item API result without a truncation indicator is not an atomic revision, proof of page deletion, or certified vendor pagination completeness. scripts/paper_migration_planner.py now accepts the --visibility-delta option and refuses to plan newly copying any of the six externally absent Terminal pages while their destination/effect remains unreconciled.

Current *provisional* aggregate (63-page baseline + later source-visibility delta): **57 currently visible pages; 51 whole-page planning candidates across 26 proposed volumes; six heavyweight pages held for per-artboard splitting; six Terminal pages held as externally absent and not proven migrated.** The previous 57 candidates / 27 proposed volumes describe historical unqualified baseline. Neither number is a Paper vendor limit or copy permission.

Visibility-aware read-only CLI example:

    python3 scripts/paper_migration_planner.py --inventory docs/paper_migrations/MASTERMIND_PAGES_INVENTORY_2026-10-22.json --visibility-delta docs/paper_migrations/MASTERMIND_PAGES_DRIFT_2026-10-22.json --out /tmp/mastermind-paper-visibility-aware-plan.json

A separate structural preflight for future claimed native-copy receipts exists at scripts/paper_transfer_evidence_preflight.py. It consumes a *real* source/target claim, not a fabricated one. Example invocation:

    python3 scripts/paper_transfer_evidence_preflight.py --inventory docs/paper_migrations/MASTERMIND_PAGES_INVENTORY_2026-10-22.json --visibility-delta docs/paper_migrations/MASTERMIND_PAGES_DRIFT_2026-10-22.json --heavy-artboards docs/paper_migrations/HEAVY_PAGES_ARTBOARD_INDEX_2026-10-22.json --claim /PATH/TO/ACTUAL-SOURCE-TARGET-CLAIM.json

The validator insists on distinct source/destination file IDs, page/artboard IDs, source baseline and visibility fingerprints, unique operation IDs, source-page presence, observed heavy-page artboard identity, native editable-copy mechanism and non-unknown effect state. It demands source and target evidence references and identifies missing independent visual/native editability, token, image/asset, component, comment and interaction evidence. **It cannot authenticate cited evidence, does not perform Paper edits, never proves a live migration and ALWAYS withholds source deletion authorization.**

The entire offline suite has **28 locally passing tests** as of this revision, including source drift, duplicates, false migration/transfer states, unknown effects, truncated heavy-board identity, output overwrite refusal and history holds. These local receipts do NOT prove hosted GitHub CI or live Paper functionality.

Before a small-page canary, capture its actual artboard identity: the test fixture's synthetic IDs are not a real destination. p-16-0 is absent from the index of the six heaviest pages and requires its own exact source artboard read/census. No artifact in this PR is an Execute/Migrate command, runtime registry, second retry plane or source-deletion gate.

## 12. Release and collision gate

1. Adapter PR #1722 owner separately qualifies real installed immutable runtime, catalog and published client action before use. Code or CI success alone does not prove a callable Paper tool.
2. Reconcile the six externally absent Terminal pages plus p-19-0 through actual incumbent owner/native history, without blind replay, reconstruction or original cleanup.
3. Refresh current exact-source inventory if the source changes again. Preserve historical base data and append read-only observations.
4. Prove native recovery/backup on disposable files, native copy fidelity and source-target readback before a single real transfer.
5. Verify editable content, visual equivalence, assets/tokens/comments/components/interaction state and downstream active links. Synthetic receipts never close these gates.
6. Admit a separately reviewed page cleanup action only after all evidence resolves; verify original source warning removal, content recovery and actual new-file usability.

State remains **PREPARED, NOT MIGRATED BY THIS LANE**. Original Paper still reports its oversized warning. PR #1721 owns planning/verification; PR #1722 owns adapter evolution, source releases and its own canary.


## 13. Heavy-page semantic partition candidates

The [read-only name-and-journey partition candidates](HEAVY_PAGE_SEMANTIC_PARTITION_CANDIDATES_2026-10-22.json) map all 310 artboards of the six largest pages into **29 provisional semantic groups**, with unique exact source artboard IDs and no duplicate assignments. Group counts per source page:

| Heavy source page | Artboards | Proposed journey clusters |
|---|---:|---:|
| Forex R1 p-N-1 | 101 | 7: early spec/routes; R2–R11 evidence; R26 navigation; case/event; watch lifecycle; decision panels; evidence/contracts |
| Sector archive p-Z-0 | 71 | 4: vNext intelligence; themes/rotation; Sector Central; detail and authority |
| Live site baselines p-8-1 | 10 | 2: historical live-source specimens 1–5 and 6–10; these are evidence, not new product UI authority |
| Intelligence Hub R4 archive p-1A-0 | 66 | 5: commands/evidence; build contracts; risk cases; research filters; recovery and locale states |
| Sector Intelligence R3 p-24-0 | 23 | 7: cycles, watches, brief, explore, dossier, research, shared/state/authority |
| Commodities p-L-0 | 39 | 4: R2 desktop primary, R2 states/device variants, North Star studies, R3 decision |

Max group size is 22 **artboards**, but that is NOT a safe vendor storage measurement. One complex artboard can still exceed the provisional per-file target. The artifact explicitly leaves per-board subtree-node counts, actual asset bytes, shared component dependencies, new destination file IDs and native copy verification unknown.

Before moving: obtain real per-artboard subtree weights, inspect references/components that cross proposed groups, move paired dark/light/EN/ZH/device states together when feasible, and revise any grouping that would break reuse, history lineage or useful end-user experience. The first source copy should remain small and non-destructive, with readback and native editability. Neither this partition proposal nor the preceding offline 51-page plan authorizes file creation or source cleanup.


## 14. Vendor storage, restoration and call-budget constraints (official-source research)

Official Paper public references reviewed October 22, 2026:

- https://paper.design/build-log — the **August 2026** changelog says the file-size limit was raised for Pro-plan files and dashboard duplication was added. The **September 2026** changelog reports large-file memory and navigation improvements. This does not disclose exact per-file document byte/node limits, prove the source warning is false or qualify a specific duplication/restoration method.
- https://paper.design/pricing — as inspected, Free lists 100/week MCP tool calls and Pro lists 1M/week MCP tool calls. These are public plan descriptions, not proof of the active seat's plan or available quota. The stated 25 MB Free / 100 MB Pro figure is a **max image size**, not a Paper document size. Never substitute it for a file/node capacity limit.
- https://paper.design/docs/support — copy/export shortcuts are documented, but an image/React/Tailwind export is not a restorable, natively editable Paper source.
- https://paper.design/docs/tokens — copying a theme between files is supported, but those token copies are **not synchronized** with future source token changes.
- https://paper.design/docs/paste/figma — importing from Figma may detach instances/variables and may omit unavailable images; this **does not prove** that Paper-to-Paper native copy does the same, but shows why imported/cross-file component and asset fidelity must be tested independently.

**Unverified recovery capability:** The consulted public docs did not establish a version-history restore API or a restorable native single-file archive. Do **not** assume that a dashboard duplicate, image export, JSX or a Paper comment is a disaster-recovery backup. Before deleting original pages, the actual operator must prove a **vendor-supported recovery path** for the exact file on a disposable target, or hold destructive cleanup. Whole-file duplication of an already oversized file may itself be risky and is not an automatic prerequisite.

**Call economics:** A naive one-artboard-at-a-time full pre-read/copy/post-read across 310 oversized artboards already implies hundreds of MCP calls, potentially exceeding the public Free allocation. Confirm the actual seat's capabilities and quota rather than assuming it is Free or Pro. Prefer the fewest bounded, exact-ID **read-only** inspections needed to produce sufficient proof; batch disjoint work only when the released adapter explicitly supports that action, with known per-operation effects. Never bypass denial, buy/upgrade a plan, invent quota, or turn batching into a no-replay loophole.

These are release planning constraints and official-source observations, not any new tool grant, catalog permission or evidence of restored Paper content.

## 15. Hierarchical native-clone partitioning optimization

The earlier 32 proposed destination buckets are a **logical plan, not a sequence of new full-size clones**. A straightforward strategy of cloning the complete 57-page source separately for each of 32 leaf buckets would require deleting 57 - pages_to_keep from every copy, approximately **1,767** individually targeted page deletions. Repeatedly doing this increases data-loss/ambiguous-effect exposure as well as Paper UI labor.

A **read-only, deterministic Huffman-weighted binary partition proposal** has now been preserved at [CLONE_PRUNE_HIERARCHICAL_ALLOCATION_2026-10-22.json](CLONE_PRUNE_HIERARCHICAL_ALLOCATION_2026-10-22.json). Its 31 internal binary splits allocate the same **57 exact historic-visible page identities** across 26 ordinary whole-page destination volumes plus 6 heavy-page one-page holds. Under the mathematical model, an authorized copy of each validated parent work file can be split by *pruning complementary page groups on two work copies*, recursively: **275 proposed page deletion operations** (84.4% fewer than 1,767) and **32 new working copies** if the original and the already verified first-party native clone remain untouched. The largest modeled branch depth is six.

**Important safety and engineering caveats:**

- The model is a **cost comparison**, not a command queue or permission to perform **275 irreversible GUI operations**. Paper does not yet expose an accepted `delete_page` MCP action or unattended exact-page UI targeting. A per-click manual/guarded target proof, source-vs-work-copy identity, snapshot/effect reconciliation, and post-delete readback are still obligatory. Any uncertain result stops the affected clone branch and must not be retried on another carrier.
- **Do not reuse, rename, prune, or recreate** the existing full-size verified clone `01M5HVW84WZFE62DREB6QB9ZDJ`. That clone is preserved as historical evidence; it still emits a data-loss warning. Starting a working root requires a distinct approved, safeguarded copy only after qualified recovery and acceptance of large-file copy safety. No working root/child IDs exist in this proposal.
- **The original is newer on at least one page.** Commodities `p-L-0` has 6,078 live original nodes and only 6,070 in the earlier native clone, both with 41 artboards. A plan made against the earlier clone cannot be declared a current lossless copy. Reconcile legitimate page changes before any cutover; metadata/token equality alone is insufficient.
- The six extra-large pages remain *holds*, not finished leaf destinations. Each may itself exceed safe file size and must be partitioned at the measured artboard/dependency level. The candidate 6,000-node/32-board targets are **heuristics**, not vendor safe limits. Some families need related theme, locale and device variants kept together to preserve components and workflow continuity.
- Hierarchical clones can propagate missing images, altered gradients, comments, linked components or outdated state at every level. Verify retained editable native content and downstream direct links at each accepted boundary; additional clones are not a substitute for qualified native recovery/version history. A clone merely passing `get_basic_info` is not content acceptance.

**Outcome status:** computational partitioning prepared, no Paper file created, pruned or deleted by this workstream. It does not supersede the adapter owner's existing first-party UI clone effect, PR #1742's required CI/identity fixes, PRs #1722/#1724/#1728's protected merge/release, or an explicit target-bound production canary.
