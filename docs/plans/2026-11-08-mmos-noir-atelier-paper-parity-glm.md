# Mastermind OS — Noir Atelier Paper-to-Product Parity Programme

**Status:** EXECUTION BRIEF / NOT IMPLEMENTED BY THIS DOCUMENT.  
**Program:** [Mastermind issue #2361](https://github.com/mastermindx-market-intelligence/Mastermind/issues/2361).  
**Executive owner:** Chairman-directed Sol integration; preferred execution: GLM 5.3-qualified Subagent Fabric operator plus bounded leaves, not an assumed model binding.  
**Intake/source snapshot:** protected Mastermind `master@7f711df8c12b9198aec3559fc017d722f2f7b7a2`; Macro `main@448f681b2dcacd2639674b91afc6a812437e402f`; requalify affected heads/real installed runtime before writes or acceptance.  
**Chairman outcome:** the signed-in **web and macOS Tauri Mastermind OS** should feel and function like its approved canonical Paper 'Noir Atelier' design, not like the current partially skinned implementation.

## 1. Completion is a working application, not a visual packet

**DONE_WHEN** all the following are independently evidenced on a real release candidate:
1. Both web and installed/signed-in macOS use the same coherent Atelier design grammar and accurate responsive composition, with screens traceably compared to approved Paper artboards.
2. Every current, owner-backed main journey has an understandable glance state, truthful source/access/permission states, usable next actions, and retained drafts/selection/recovery. At least Today -> Project -> Work/Result -> review/continue, Conversation return, Meta-CEO/Sessions, and sign-in/recovery must be exercised.
3. Representative desktop, narrow viewport, light, dark, EN and ZH screenshots, including overlays and incomplete/error data, are compared against specific Paper boards and adjudicated. Mobile uses responsive content behavior, not CSS scaling of a 1600px screenshot.
4. Tests and actual authenticated browser + installed native evidence show unchanged auth, guarded commands, permission boundaries, provenance and native continuation. A screenshot fixture or green CI alone is insufficient.
5. Source is accepted through the actual protected GitHub/release owner, and a real web/native consumer has verified installed output. Never assume a permission/merge/release/production effect from this plan.

**Primary users** are the Chairman, executive operators and invited company-team members. **First five seconds:** Where am I? What is actually happening? What needs my decision or action? Where do I continue?

## 2. Authority, visual direction and evidence hierarchy

1. Approved actual *OS-specific* Paper file `01M3NRCX55B452A12819WNE1RH`, [start page](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-1-0) -> **current** pages 12/12A/12B/12C/12D. Page 12 artboards AT00 `KSB-0` (design authority), AT90 `KSQ-0` (shared shell), AT91 `NDE-0` (states), and page 13 UX contracts. Obtain live guarded Paper `get_basic_info`, `get_screenshot`, `get_jsx`, `get_tokens` on **exact fileId and nodeId**; never infer the target from currently foregrounded Paper file. Exported JSX is a visual reference, **not** safe production JSX.
2. `app/mastermind_os/README.md` documents the Chairman's October 2026 approved Noir direction, route/board history and real source capability limits. Current `src/styles.css` already defines Noir (canvas #080808, sidebar #0c0c0c, panel #121212, ivory text, champagne actions) and light-mode aliases. **Evolve these tokens/actual components**; no parallel root style family or competing app.
3. Macro `docs/DESIGN_DOCTRINE.md` and `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` at `main@448f681b2dcacd2639674b91afc6a812437e402f`. User-first clarity, accessible progressive disclosure, truthful provenance; **never put a colored stripe/edge rail on cards, rows, tabs, navigational selections or banners.** Labeled semantic status/icons, neutral even borders, quiet fills, typography and focus outlines are allowed. Dark and light are independently composed. EN/ZH need meaning-preserving copy.
4. Product 15 (Team & Delivery) and product 16 (Team Conversations), Paper `p-O-0` / `p-R-0`, are expansion sources **only for source-supported existing Team/Hermes/T3/Fleet integration**. Page 15B `p-Q-0`, artboards `12DE-0` / `12LO-0`, already specifies GLM-00..GLM-06 engineering sequence. Do not mistake its packet design for admitted workers or implemented features.
5. Historical REF and ARCHIVE pages are evidence, **not current screen authority**. Do not copy old market shell, duplicate screenshots or legacy decorative container-edge idioms.
6. Prior scoped Project Workspace source PR [#2252](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2252) **merged**; do not redo or regress its composer viewport and unboxed status treatment. Adjacent active implementation/release PRs and authentic writers/effects must be checked before modifying overlapping paths.

## 3. Architecture and source inventory — keep what works

**One shared interface**: `app/mastermind_os/src/App.tsx` routes/combines React components and `src/main.tsx` uses the web or Tauri host under `composeMissionHost`.  
**Desktop host**: `app/mastermind_os/src-tauri/tauri.conf.json` (Tauri v2; `com.mastermind.os`; initial window 1200x820/min 390x600) with existing private Rust auth/command path.  
**Web host**: `https://mcp.mastermind-x.com/os/`, existing sign-in/PKCE/auth/Executive capability and source guards.  
**Design entry**: `app/mastermind_os/src/styles.css`, route styles and components below.  
**Existing app-control proof**: `docs/MASTERMIND_OS_APP_CONTROL.md` outlines bounded observe/navigate/act/check tools via existing Workbench browser context where actually installed; do not presume they're exposed in every environment. Existing Playwright/Chromium proof remains valid through its own owner.

| Surface / user job | Canonical Paper page + artboard IDs | Current implementation pointers | Primary lane | Check/falsifier |
|---|---|---|---|---|
| Shared navigation/chrome and meaningful states | 12: AT90 `KSQ-0`, AT91 `NDE-0`; UX page13 | `src/styles.css`, `src/App.tsx`, `src/preferences/DisplayPreferences.tsx`, route shell tests | W1 | Navigation focus/selection; no color edge accents; responsive light and dark; no route-specific breakage |
| Today command home | 12: AT01 `LNV-0`, mobile `N27-0` | `src/today/Today.tsx`, `src/today/today.css`, App daily routes | W2 | Main state + next action visible immediately; owner-backed priority; honest no-data |
| Project catalogue | 12: AT02 `M4J-0`, `N28-0` | `src/projects/Projects.tsx`, `src/projects/projects.css` | W2 | Find correct project; filtered/empty/unavailable distinct; stable return |
| Project workspace, plan, work, evidence | 12A: AT03 `MHD-0`/`N29-0`; AT10 `LF7-0`/`MOG-0`; AT16 `NV9-0`/`O1V-0`; AT18 `OE8-0`/`OKF-0` | `src/projects/ProjectWorkspace.tsx`, `src/projects/project-workspace.css`, `src/workJourney.css`, planning and activity components | W2 | Existing #2252 composer position preserved; Work -> actual evidence -> result -> origin/continue; no fake completion |
| Project draft/details, Journal and result | 12A: AT14 `N8N-0`/`NBB-0`; AT34 `XYO-0`/`Y60-0`; AT35 `XLQ-0`/`XT2-0`; AT19 `OMG-0`/`ORL-0` | `src/projects/NewProjectDraft.tsx`, `src/projects/ProjectDetailsNavigator.tsx`, `src/project-journal.css`, activity/result family | W2 | Source-only and saved/draft states not conflated; reopen exact project |
| Conversations, selected session and composition | 12: CV01 `SD8-0`; 11: CH91 `KDN-0`; page13 UX06/UX07 | `src/conversations/ConversationWindow.tsx`, `ConversationsList.tsx`, `conversation.css`, `conversations-list.css`, `src/orchestration/ui/` | W3 | Composer/reader state survives navigation, streaming, long text/IME; Send only if allowed |
| Inbox and knowledge/search/sources | 12: AT04 `KY5-0`/`MNL-0`; AT05 `L0Z-0`/`MNM-0`; AT06 `L3N-0`/`MNN-0`; AT07 `L6N-0`/`MNO-0` | `src/inbox/InboxWorkspace.tsx`, `src/knowledge/Knowledge.tsx`, `src/knowledge/knowledge.css`, `src/discovery/`, source readers | W3 | Search -> exact destination -> back, partial source and freshness honesty |
| Decisions and Plan revisions | 12B: AT20 `OU0-0`/`P0I-0`; AT21 `P2V-0`/`P8L-0`; AT27 `QW9-0`/`R1H-0`; AT28 `R43-0`/`RAE-0`; AT29 `RD5-0`/`RJA-0`; AT33 `UB2-0`/`UB3-0` | `src/direction/`, `src/planning/`, route wiring | W4 | Actual authority and pending decision state, receipt vs preview, owner-correct return |
| Meta-CEO and supervision | 12C: AT08 `L9V-0`/`MNS-0`; AT25 `Q9N-0`/`QF9-0`; AT26 `QM6-0`/`QT7-0`; AT30 `RKW-0`/`RTC-0`; AT31 `RW9-0`/`S3L-0` | `src/meta-ceo/MetaCeoOffice.tsx`, `src/meta-ceo/office.css`, source owner projections | W4 | State/authority clear; gaps disclosed; no command granted by presentation |
| Sessions, access, activation, private entry | 12D: AT12 `KVF-0`/`M29-0`; AT15 `NKM-0`/`NPO-0`; AT22 `PK4-0`/`PXW-0`; AT23 `PR3-0`/`Q1O-0`; AT24 `Q50-0`/`QJN-0`; AU01 `TEP-0`/`TGL-0`; AU02 `THK-0`/`TIQ-0` | `src/session-estate/SessionEstate.tsx`, `session-estate.css`, `src/auth-entry/AuthEntry.tsx`, `auth-entry.css`, auth-recovery | W4 | Signed-out privacy, browser sign-in, permission refusals, pending callbacks, exact current account |
| Team / Hermes bot / code / fleet expansion | 15: TD01 `ZQN-0`, TD04 `10L5-0`, TD05 `10WB-0`; 16: HC01 `12UW-0`, HC02 `136T-0`, HC04 `13RP-0`, HC05 `142O-0`, HC07 `14MJ-0`; 15B TB02 `12LO-0` | `src/fabric/`, `src/resources/`, existing Team/T3/Hermes consumers as found; check active PR #2345 | W4 follow-on, only after source qualification | No invented bots/hosts/quotas; link existing source-capability states and real controls |

These paths are *starter navigation*, not a claim that every displayed Paper target is already built. Each worker must record exact found source paths and unresolved product/implementation differences.

## 4. Team allocation and custody (one modification owner per path)

**W0 — GLM 5.3-preferred operator, C2_COMPLEX_BOUNDED, census and integration contract.** Own plan, route/board deficit matrix, source/write collision check, verified baseline capture and gate decisions. Start by checking which model identifier the actual `glm` pool admits; exact GLM 5.3 is preference, not demonstrated grant. Operator may delegate only when true native child admission/depth and original-root parent permit it; otherwise return bounded packets. Initial W0 is read-only until source ownership is qualified.

**W1 — GLM implementation leaf, C2**: one exclusive writer for `src/styles.css`, global shell/theme/preferences and genuinely shared primitives. Freeze tokens, CSS class/override interface before W2/W3/W4 write their disjoint route styles. No broad churn of unrelated backend and no new design tokens without source justification.

**W2 — GLM implementation leaf, C2**: exclusive Today + Project + Work visual components and route-local CSS, preserving Project Workspace existing merged behavior and data owners. Functional tests and visual diffs must travel with code.

**W3 — GLM implementation leaf, C2**: exclusive Conversations + Inbox + Knowledge/Search and their route-local CSS. Do not create second conversation/session/agent lifecycle.

**W4 — GLM implementation leaf, C2**: exclusive Decisions + Meta-CEO + Sessions/Access. Team/T3/Fleet extensions are contingent on actual implemented APIs and separate original authors; if source contracts are not there, document it instead of a decorative fake page.

**W5 — integration / verification owner, C2**: reconcile source changes, test interactions, actual browser + installed macOS captures, hold all release/merge criteria from real repo; visual critique by distinct qualified actor if materially needed. Source authors do not self-report independent approved review.

**Coupling rule:** W2/W3/W4 must not modify `src/styles.css`, `src/App.tsx`, global navigation, auth, transport, shared DTOs or other lane files concurrently. Proposed shared navigation changes return to W1/W5 and are serialized. No second PR/worktree per logical effect. Existing overlapping PRs with live/uncertain effects are protected until their original owner reconciles.

**Routing receipt:** `ROUTE=GLM Fabric operator/worker if admitted; TASK_COMPLEXITY=C1/C2; BUSINESS_IMPACT=critical; EXECUTION_RISK=elevated; AMBIGUITY=medium (UI gaps only)`. **WHY NOT FABLE:** approved Paper and current React/Tauri architecture freeze taste and service boundaries; independently testable UI slices do not need scarce frontier principal labor. Escalate genuine design/contract contradictions for principal decision, not ad-hoc GLM taste invention. No model-provider/account/host/spend binding by this plan.

## 5. Execution ladder — always verify, save, continue

**P0 — qualify, measure, bind.** At fresh current Mastermind SHA, inspect protected instructions `docs/sol_skills/INDEX.md`, `AGENTS.md`, current PRs/writers/effects and same-SHA applicable skills. Confirm Paper `get_basic_info`, `get_tokens` and exact artboards; extract relevant JSX as reference; visually inspect live screenshots. Capture current web + native screenshots from actual authenticated app if access exists. Build a row for each currently built route: actual component, source state, Paper board, visual gap, interaction gap, platform/state gaps, owner, effort/priority and a fail criterion. A static fixture does not equal authenticated baseline. Reuse the GitHub issue/plan; do not spawn duplicate plan/authority systems. **NEXT:** first viable shared shell/one-page parity vertical.

**P1 — first representative vertical.** Align shell/Today/Projects in dark desktop and mobile without breaking current user flow. Save exact commit/CI/test proof, **continue** into next disjoint screen without waiting for every broad suite if independent work is ready.

**P2 — coupled product route families.** Implement the remaining current canonical 12A–12D families in disjoint batches with real state semantics, tests and visual evidence. Integrate shared settings and tokens once.

**P3 — adjacent Team/Coding/Fleet actual consumer.** Apply page15/16 interaction patterns where existing backend and auth supply truthful capabilities. Do not narrow the parent to shell-only or invent API data because Paper illustrates it.

**P4 — final integrated release and real consumer proof.** Run actual signed-in web (not screenshot fixture) and installed/signed-in macOS release candidate through the main journeys. Compare screen captures to exact Paper boards, test both themes/languages/breakpoints/permissions, get expected-head CI, use authorized release owner and verify public/installed output. Record remaining gaps with evidence rather than claiming all screens pass.

After each meaningful milestone, **SAVE/READBACK -> reassess DONE_WHEN -> next safe work** on the same healthy turn/worker. An issue comment, PR, CI green or build is never final acceptance.

## 6. Reproducible verification and visual quality bar

At `app/mastermind_os`: `npm ci --ignore-scripts`; `npm run typecheck`; affected `npm test` suites; `npm run build`; `npm run build -- --mode native`. Run broader tests/CI for integration and production candidate. Native Rust tests use exact Git revision and an owned external `CARGO_TARGET_DIR` under the existing release scripts. Do not mutate installed auth/bundle or publish app merely to get a screenshot.

Capture **comparison triplets**: Paper (board ID + current snapshot), pre-change application (web/native and build SHA), post-change application (same state/dimensions and build SHA). Use **1600x1040** Paper references as source, **1200x820** native default, and **390x844** narrow viewport; make real viewport width and DPR explicit. For native app prove actual packaged host rather than only browser emulation. Cover dark/light, EN/ZH where designed and realistic long-text overflow. Current design may show only certain variants; derive the rest through the canonical shared language/theme contract and mark inferred variants as needing design adjudication.

Required failures to challenge: narrow sidebar/navigation, horizontal scroll at 390, oversized nested card-stack, colored rail/stripe, tiny tap targets, contrast failure, focus trapped/lost, stale/withheld data mislabeled CURRENT, null/partial hidden, unauthorized Send/Launch actionable, pending/unknown outcome falsely completed, sign-out still showing prior private content, project selection/editor draft lost, long streaming text shifting composer, dark-only CSS in light mode, fonts/figures jitter, macOS titlebar/window safe area conflict, direct WebAuth conflated with Tauri native auth. Reduced motion must disable nonessential animation; no invalid decorative motion.

Actual proof rows include **source commit, route, Paper artboard ID, viewport + theme + locale, data/auth state, user action/result, screenshot/video evidence, test method, PASS/FAIL, ownership of next repair**. GitHub PR/issue owns evidence; don't invent a second evidence database.

## 7. Commission instructions for each qualified worker

`RECEIVER_MODE=DIRECT_TARGETED` only after actual accepted Fabric placement/delivery to exact worker. Otherwise `WAITING_CAPACITY / needs_placement`—a GitHub issue, draft packet or queued request alone is not START.

Each worker reads this plan, the linked issue, protected same-pin source law, relevant Paper artboards, affected frontend source and test files; checks occupied paths and original effects; then ACKs/STARTs only on its real admitted carrier. Work inside its disjoint source grant. Investigate -> implement -> run focused checks -> repair -> take actual screenshot/behavior evidence -> save/ref-readback -> send compact result to the operator.

**Worker return schema (human readable, not a new API):** operation/root and real worker/model/START receipt; role and assigned files; exact base/head + PR; changed component list; Paper page/node IDs; screenshots and UI/state/keyboard checks with PASS/FAIL; regression tests and native/web build result; factual capability/liveness tier; known collisions and original-carrier unknown effects; next source action. A cosmetic success without a real owner-backed interaction is NOT_ACCEPTED.

**Separate reviews:** proportionate self-check + affected tests are mandatory. A distinct reviewer may critique consequential visual differences, but no fictional blanket independent review/formal GitHub APPROVED gate is invented for ChatGPT Web. Real GitHub CODEOWNERS, security, release holds and exact-head checks remain binding.

## 8. Durable recovery and non-goals

Canonical ongoing discussion/task tree: [issue #2361](https://github.com/mastermindx-market-intelligence/Mastermind/issues/2361). This Markdown file is editorial source, **not** an Executive Job, Agent OS task store, admission, RuntimeBinding, workspace grant, release order or watcher.

Never replace Tauri or build a separate web client, lifecycle store, auth, Hermes session store, Executive Jobs, Fabric quota router, T3 engine, SDK credential path or CSS competing token system. Keep native privacy, model/provider consent, exact source/project/role and unknown-effect fences. Do not modify Paper designs without a separate scoped approved mutation and its guarded snapshot. Do not merge/undraft/deploy held work without actual current applicable authority. No Vercel.

If GLM 5.3 cannot be admitted, preserve this fully specified programme and the exact pre-task refusal; continue source-independent visual/source analysis. Do **not** claim a GLM team is working, impersonate a model, brute-force the provider alias or switch carriers to evade a denial. The next substantive lane is the first available source/visual vertical not conflicting with an active writer; return precise blocker and start/proof distinctions.