---
title: "Mastermind Portfolio Product — frozen view spec (V1–V7)"
status: "FROZEN-DRAFT (awaiting independent review and seat design acceptance)"
date: 2026-10-22
owner: pbr-product
program: Mastermind#1693 — Portfolio Bot Rebuild, Wave 9
root: "Mastermind#1693 (Portfolio Bot Rebuild)"
orchestrator: pbr-product-ed665c78
lane: pbr-p2-spec
base_commit: "origin/master @ db5a001b (PR #1711). Every cited app/portfolio file is byte-identical at dce821e0; §2 and §6 were drafted at census base 230e9a301 and every citation was re-verified against db5a001b after independent review r1 (see §3 preamble)"
sources:   # _pbr_inputs/ is the lane input bundle. Repo copies: PRODUCT_CENSUS.md and PRODUCT_CONTRACT_REQUESTS.md -> research/commission_pbr_fable_masterplan/2026-10-22/lanes/PRODUCT/{PRODUCT_CENSUS.md,CONTRACT_REQUESTS.md} (ids minted here, R6 and S6-S9, are defined in section 7); ECON_CONTRACTS_PR1699.md -> lanes/ECON/CONTRACTS.md; DS_* and MASTER_PRODUCT_DESIGN_SYSTEM_V1.md -> the Mastermind Product Design System references
  - _pbr_inputs/PRODUCT_CENSUS.md          # factual baseline; its §"Orchestrator verification (pbr-product)" overrides the lane text on conflict
  - _pbr_inputs/MASTERPLAN_EXCERPTS.md      # §10.2 five questions / seven views / truth rules; §4 defect register
  - _pbr_inputs/DESIGN_DOCTRINE.md          # content law (highest authority for copy)
  - _pbr_inputs/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md   # visual + composition law
  - _pbr_inputs/DS_foundations.md
  - _pbr_inputs/DS_components.md
  - _pbr_inputs/DS_archetypes.md
  - _pbr_inputs/DS_states-accessibility.md
  - _pbr_inputs/DS_patterns.md
  - _pbr_inputs/ECON_CONTRACTS_PR1699.md    # A02 nav_status/carried/unattested/nav_withheld.jsonl; A12 benchmark helper
  - _pbr_inputs/PRODUCT_CONTRACT_REQUESTS.md # E1–E13, R1–R6, S1–S9, CR-R2/CR-R6 answers
  - app/static/theme.css                    # the app's actual token + primitive source (no Macro .mx-* classes ship here)
  - app/static/theme.js
  - app/static/index.html                   # the SPA that carries V1–V4, V6, parts of V7
  - app/static/portfolio.html               # /portfolio_desk (Portfolio Risk Desk)
  - app/static/account.js
---

## 0. Scope

This document freezes the **product view specification** for the seven Mastermind portfolio
views V1–V7 required by MASTERPLAN §10.2: what each view answers, which archetype it composes
as, the exact fields it may render and where each field comes from today, how it recomposes at
375 / 768 / 1280, every state it must render with exact EN + ZH copy, the accessibility and
density budgets it must hold, and the testable acceptance items that close it. It binds the
art direction supplied by the lane packet, places each view against the **real** current
route/panel/API surface recorded in `PRODUCT_CENSUS.md` (spot-checked by this lane against
`origin/master @ 230e9a301`), uses the **exact** ECON A02/A12 valuation vocabulary from
`ECON_CONTRACTS_PR1699.md` rather than inventing a parallel one, and binds every visual role to
a real `app/static/theme.css` variable rather than to the Macro `.mx-*` classes the Mastermind
app does not ship. Where a field does not exist yet it is written as
`CONTRACT REQUEST → <id>` with type, nullability, units and provenance, never as an assumed
field; where a needed component does not exist in the canonical inventory it is written as
`DESIGN-SYSTEM-GAP`. It specifies no implementation: no HTML, CSS, JS or Python beyond tiny
token names. It proposes no route, IA or seat change as settled — each is marked
`SEAT DECISION`.

---

## 1. Art direction

**1 · The account is the answer.** Every view opens with the settled factual state — what is
held, the cash, the value, and the as-of that value was computed at — before any narrative, and
narrative is rendered as subordinate annotation that can never contradict the ledger. Visual
consequence: V1's first content element is a VerdictHero-shaped answer block (DS anatomy, bound in §3 Tokens to the `.panel` surface + `.mm-perf-stat-value` figure; no `.mx-vh` class ships) (holdings count, cash,
NAV + status, one as-of stamp) occupying the canvas tier; the decision memo, posture and brain
log sit below it in panel tier and are visually quieter than the account, and where a memo
sentence and `account.json` disagree, the account's value is the one that is drawn.

**2 · Archetype G (Monitor) is the product shell; no tenth archetype is minted.** The product
answers "what changed since I last looked", so the shell is since-stamp → what changed →
managed list; position review composes as C (Instrument Analyzer) and opportunities as B
(Discovery Board) *inside* that shell. Visual consequence: the book's freshness stamp is the
first thing painted on every view; "what changed" is a bounded change list, not a narrative
wall; holdings, pending rows and finalists are managed lists with counted `See all N` depth.

**3 · Instrument calm; hue is a reserved word.** Dark is a graphite command centre, light is a
cool research workspace, both in Inter/SF with tabular numerals everywhere a figure appears.
Colour appears only for market direction (flipping under ZH red-up/green-down), health/severity,
provisional/epistemic status, and lock (violet, lock only); there are no coloured container-edge
accents, no gloss and no emoji icons. Visual consequence: hierarchy comes from spacing,
typography, surface depth and weight; a state is carried by a **labelled word plus a non-colour
cue**, never by a hue alone.

**4 · Epistemic honesty is visual grammar, not fine print.** `Provisional`, `Behind`, `Partial`,
`Unavailable`, `Queued` and `Unverified` are first-class states with their own label, their own
non-colour cue and their own plain sentence; unknown is never rendered as `0`; a missing-price
flat line is drawn as a **gap in the curve**, never as a horizontal segment; a small sample shows
its `n` and is never celebrated. Visual consequence: the canonical state vocabulary in §3 is a
printed token, not a styling hook, and each state sentence names what is still safe to use.

**5 · Density by tier.** Tier 1 is the answer plus at most two supporting modules above the
fold; an L1 table shows at most 8 rows and then a counted `See all N`; mechanics and receipts
live in disclosures that open by keyboard **and** touch; 375 px is a deliberate recomposition
that keeps answer + current evidence + next action and gives every demoted module a named
landing. Visual consequence: nothing is deleted for space — it is demoted with a landing, and
the page never scrolls horizontally at any width.

---

## 2. Information architecture

### Route and panel map

| View | Lives today | Route / panel ids | Proposed V1 home | Change class |
|---|---|---|---|---|
| **V1 Portfolio overview** | `/` SPA dashboard, existing panels | `index.html` `#performance` (NAV/cash/as-of), `#alloc`, `#positions`, `#safety`, `#live-marks-status` | Composed as one V1 route: an answer block + `#positions` + `#alloc`; `#safety` demoted to V1's own support-2 | **SEAT DECISION** — merges four shipped panels into one view |
| **V2 Manager decision** | `/` SPA, existing panels | `#decision-availability` (`index.html:2723`), `#auto-banner-sec` (`:2730`), `#decisions-sec` (`:2861`), posture chip | V2 route: `#decision-availability` promoted to the answer, `#auto-banner` as support-1, `#decisions-sec` as support-2 | **SEAT DECISION** — promotes an evidence panel to the page answer |
| **V3 Pending activity** | `/` SPA, existing panel | `#trades` pending block (`index.html:5031-5068`, `_pendingTruthNoticeHtml` `:5015`), `accepted_target.pending` inside `#decision-availability` | V3 route: the pending block promoted out of Trade History, which keeps only fills | **SEAT DECISION** — splits one shipped panel |
| **V4 Performance** | `/` SPA, existing panel | `#performance` (`index.html:2755`), `#equity-curve` (`:2794`), `#perf-evidence` (`:2757`) | V4 route: `#performance` becomes its own view; its as-of/strip moves with it | **SEAT DECISION** — separates a shipped panel into its own view |
| **V5 Opportunities** | `/` SPA, **hidden for product books** | `#rejected` is in `PF_GATED_ONLY` (`index.html:6468`) so it is hidden whenever a Brain book is active (`index.html:6542-6545`); `#nav-research` / `#view-research` render only when `_portfolio === 'flagship'` (`index.html:6550-6551`) | V5 route reachable for every active book | **SEAT DECISION** — exposes a view that is unreachable today |
| **V6 Position review** | `/` SPA, existing panel | expand-row under `#positions` (`toggleExpand`, `index.html:4988-5003`), `#trades` blotter, `#sizing-sec` | V6 route per holding: the existing expand-row becomes a first-class route (`/position?ticker=` or `#position/<ticker>`) so it is linkable, keyboard-navigable and shareable | **SEAT DECISION** — promotes an in-page disclosure to a route |
| **V7 Operations** | `/` SPA (`#runs`, `#view-desk`) + standalone `/market_view`, `/agenda` | `#runs` (`:2893`), `#forward-evaluation` (`:2746`), `/api/scheduler`, `/api/desk/*` (Flagship-only in UI) | V7 route: one operations surface per book; operator technical detail opens separately | **SEAT DECISION** — new operator-facing view |

All seven mappings are proposals. The IA owner decides; this lane only states what each view
needs and what would have to be redesigned if it moved.

### Navigation between views

- The book switcher is the **primary** navigation axis and stays in chrome (it is not a view).
  It currently lives in `#mm-nav` as `#pf-switch`, ordered by `_PF_ORDER`
  (`index.html:3847`): `autonomous, china, hk, self_directed, flagship, heavyweight, etf`.
  Each tab shows book label, archived chip, and a NAV + return sub-line
  (`renderPortfolioSwitch`, `index.html:6477`).
- The **view** axis is a second, secondary axis: Overview · Decision · Pending · Performance ·
  Opportunities · Position review · Operations. At ≥ 768 px it is a horizontal tabset; at 375 px
  it is a horizontally-scrolled strip that recentres the active item, reusing the existing
  `revealActivePortfolioTab` behaviour (`index.html:6504-6513`) rather than minting a new idiom.
- Selection writes the URL so every view is linkable and browser-back works. Today the SPA
  keeps `showView(name)` in memory and `applyPortfolioScope()` (`index.html:6529`) hides panels
  by id; the move to real routes is a `SEAT DECISION` under the IA owner.
- Cross-view entry points that must exist: a held ticker in V1 opens **V6**; a queued row in V3
  and a pending verdict chip in V1 both open **V6** on the same holding; a decision id in V2 opens
  the decision row that produced it; a rejected name in V5 opens its V6-style thesis card even
  though the name is not held.

### Per-book switching

| Book id | Display label EN / ZH | Currency | Benchmark | Lifecycle | Currency symbol source |
|---|---|---|---|---|---|
| `autonomous` | US Brain / 美股大脑 | USD | SPY | active | `_ccySymOf(undefined)` → `$` (`index.html:3827`) |
| `china` | CN Brain / A股大脑 | CNY | `000300.SS` "CSI 300" / 沪深300 | active | `¥` |
| `hk` | HK Brain / 港股大脑 | HKD | `^HSI` "Hang Seng" / 恒生指数 | active | `HK$` |
| `self_directed` | Self-Directed / 自选组合 | USD | SPY | active | `$` |
| `flagship` | Flagship / 旗舰 | USD | SPY | archived, superseded by `autonomous` | `$` |
| `heavyweight` | Heavyweight / 重仓组合 | USD | SPY | archived, superseded by `autonomous` | `$` |
| `etf` | ETF Brain / ETF大脑 | USD | SPY | archived, superseded by `autonomous` | `$` |

Source: `portfolio/registry.py` `PORTFOLIOS` (`registry.py:32-146`); tab order `index.html:3828-3848`.

- **Archived books** render a persistent `ARCHIVED` / `已归档` chip plus the
  `archived_reason` and `superseded_by` line (`index.html:6493`, `registry.py:44-45`). Archived
  books are read-only; no pending, no ordering, no "next action" module.
- **The switcher resets every view-scoped panel** on book change. Today `applyPortfolioScope()`
  hides/reveals by id and `_safeRender` re-renders from already-cached payloads; the spec
  requires that switching a book invalidates all cached per-book payloads (positions, marks,
  performance, trades) before the first paint of the new book, because the census verified the
  response cache key is path + canonicalised query only and carries **no user** and **no session**
  (`app/response_cache.py:72-83`).

### Pro gating today

**No view is Pro-gated in this process.** `app/auth.py:132-141` documents the entitlement layer
as external to the app and states the edge must not be treated as the gate; `app/auth.py:436-438`
lets every GET through; there is no browser login at all (`app/auth.py:13-16`). Only
`/api/pfolio/*` (bearer on the authoritative VPS) and 19 operator mutating/LLM paths are
restricted. Therefore:

- V1–V7 carry **no** `TierLock` treatment today, and the spec must not draw a lock affordance on
  any of them.
- `DS_components.md` `TierLock` is listed for completeness only; the canonical lock primitive
  `.mx-tier-gate` has no app equivalent (see DESIGN-SYSTEM-GAP G1: tier-lock primitive, §8).
- If an edge paywall is later proven for this app, the lock is a **separate channel from data
  truth** (`DS_states-accessibility.md` §State semantics): the public answer stays semantically
  intact and the lock appears as a labelled tier gate, never as a silent empty state.

---

## 3. Shared rules

These rules bind V1–V7. They are printed once here so each view subsection states only what is
specific to it. Line citations throughout this spec are against **`origin/master @ db5a001b`**
(PR #1711); every cited app/portfolio file is byte-identical at `dce821e0`. `§2` and `§6` were
drafted against census base `230e9a301`; Mastermind PR #1707 then inserted `index.html` lines
(+4 after old line 349, +9 after old 3444, +73 after old 4707, +88 after old 4762), so every
`index.html` citation in those sections was re-cited. After independent review r1 (VERDICT: FAIL,
retained at `lanes/PRODUCT/reviews/pbr-p2-spec-review-r1.md`) every flagged citation, and the V6
Fields rows the review did not reach, was re-verified by direct read against `db5a001b`. Panel
anchors: `#decision-availability` `index.html:2723`, `#performance` `:2755`, `#alloc` `:2819`,
`#positions` `:2837`, `#trades` `:2845`, `#safety` `:2853`.

### Tokens

The Mastermind app does not ship the Macro `.mx-*` primitives. Every visual role below is bound to
a variable that exists today in `app/static/theme.css` or to a class that exists today in
`app/static/index.html`. Where a needed role has no app equivalent it is written as a
`DESIGN-SYSTEM-GAP` by name; the orchestrator numbers them at assembly.

| Visual role | Binding | Cite |
|---|---|---|
| Page canvas | `--bg` | `theme.css:16` dark `#0a0c11`; light override `--bg: #f5f7fa` `theme.css:46` |
| One-answer panel surface (E1) | `--panel` | `theme.css:16`; light `#ffffff` `:46` |
| Set-member / raised surface (E2), hover, selected | `--panel2` | `theme.css:16`; light `#edf1f6` `:46` |
| Primary text | `--text` | `theme.css:16`; light `#17202d` `:46` |
| Secondary text, labels, sub-lines, `Behind` as-of | `--muted` | `theme.css:16`; light `#5f6c7e` `:47` |
| Hairline, table rule, chip border | `--line`, `--hairline` | `theme.css:17`, `:28` |
| Market direction ink | `--up` / `--down` | `theme.css:20`; **flips** under ZH at `:71-80` |
| Health / severity — never flips | `--ok` / `--warn` / `--act` | `theme.css:19`; the flip rule is stated at `theme.css:64-67` and deliberately excludes these |
| Wayfinding, focus, primary action | `--info`, `--link` | `theme.css:21`; light `:51` |
| Focus ring | `--focus-ring` | `theme.css:29` (`color-mix(in srgb, var(--info) 72%, transparent)`) |
| Regime quadrant (V2/V6 context only) | `--q1`–`--q4` | `theme.css:18`; ZH quadrant remap `:73-74`, `:78-79` |
| Chart canvas | `--chart-bg` | `theme.css:23`; light deliberately stays dark `#11151c` `:53` |
| Inset tile behind a metric | `--surface-inset` | `theme.css:27` |
| Card / popover elevation | `--card-shadow`, `--popover-shadow` | `theme.css:24-26`; light `:54-58` |
| Verdict chip base + per-verdict tints | `.mm-verdict-chip` and `.add` / `.hold` / `.trim` / `.reduce` / `.exit_pending` / `.avoid` | `index.html:338`, `:345-349`; queued timing line `.mm-q-when` `index.html:353` |
| Sleeve allocation segments | `.mm-sleeve-seg`, `.mm-seg-lead`, `.mm-seg-conv`, `.mm-seg-cash` | `index.html:280`, `:282-284`, `:294` (cash uses `--muted`, never a hue) |
| Performance figure + signed delta | `.mm-perf-stat-value` with `.pos` / `.neg` / `.neu` | `index.html:922-932` |
| Empty / loading block | `.mm-empty` (+ existing empty glyph spans) | rendered at `index.html:2839`, `:4787`, `:4036` |
| Archived book chip | `.mm-archive-chip` | rendered `index.html:6492` |
| Pending-fill chip on a not-yet-filled row | `.mm-pend-chip` | rendered `index.html:4843` |
| One-answer verdict block (DS VerdictHero anatomy) | `.panel` surface on `--panel` + `.mm-perf-stat-value` figure + `.mm-perf-stat-sub` evidence line | `.panel` `theme.css:129`, `index.html:72`; `#performance` `index.html:2755-2757`; figure `:922-932` |
| Bounded data table (L1 rows) | `.mm-table-wrap` > `table` | `index.html:565`; rendered `:4963`, `:5059` |
| Tier-2/3 disclosure | `<details class="mm-da-foot">` (or `mm-da-detail`) whose `<summary>` names what is inside | style `index.html:2492-2493`; rendered `:7006`, `:7087`, `:7258`, `:7412` |

- **Lock ink is violet only** and only on a tier gate. No view in this product draws one today
  (see §2 "Pro gating today"), so the binding is reserved, not rendered:
  `DESIGN-SYSTEM-GAP G1: tier-lock primitive — DS_components.md lists `.mx-tier-gate` with measured
  tier ink as the canonical locked-content component, but `app/static/theme.css` ships no tier
  colour variable and `app/static/index.html` ships no tier gate class; if an edge paywall is ever
  proven for this app, the violet lock needs a real token before it can be drawn.`
- **No new hex values.** A colour that is not in the table above is a defect. There are no
  coloured container-edge accents, no stripes and no gloss (`DS_components.md` Callout).
- **Tints, not new colours.** Chips stay the canonical class; a state never introduces a hue that
  the chip does not already own. `Queued` reuses `.mm-verdict-chip.exit_pending` exactly as
  PR #1707 shipped it (`index.html:348`, `:4834`).

### Typography scale

`DS_foundations.md` prints a canonical 10-step scale; the app implements the same scale with real
values but no size variables. Sizes below are the app's today (`index.html`, page-scoped
`body.page-mm`). **DESIGN-SYSTEM-GAP G2: type scale tokens — the canonical `--fs-*` / `--fs-num-*`
scale has no counterpart in `app/static/theme.css`, which defines only `--font-sans`,
`--font-display` and `--font-mono` (`:11-15`); every size is a hard-coded literal per rule, so a
global type change means editing ~80 declarations.** The spec binds roles to the *values the app
already paints*, not to the missing variables.

| Role | Size today | Weight | Cite |
|---|---:|---:|---|
| Page title (`h1`) | 24px | default | `theme.css:131` (`html body h1`) |
| Hero answer numeral (NAV) | 30px desktop / 18px ≤ breakpoint | 750 | `.mm-perf-nav-value` `index.html:2419`; `.mm-perf-stat-value` `index.html:2419` |
| Performance figure | 22px → 20px page-scoped → 18px narrow | 700 / 750 | `index.html:922-929`, `:1984-1987`, `:2419` |
| Panel title (`h2`) | inherit `display` family, `var(--font-display)` | 700 | `theme.css:98` |
| Section/eyebrow label | 9.5px, `letter-spacing:.10em`, uppercase EN | 700 | `.mm-perf-stat-label` `index.html:915-921` |
| Body / lead figure | 15px | 400–500 | `theme.css:96` (`html body`) |
| Table + secondary copy | 12.5px | 600 | `theme.css:421` (`.tbl-filter .cnt` family) |
| Metric tile label / value / tag | 12px / 20px / 9px | 700 / 600 | `.mtile-lbl` / `.mtile-val` / `.mtile-tag` `theme.css:223-225` |
| Dense tick + micro sub-line | 9.5px–10.5px | 400–600 | `.mtile-tag` `theme.css:224`; `.mm-perf-stat-sub` `index.html:933-937` |
| Queued timing line | 11px, muted, 500 | — | `.mm-q-when` `index.html:353` |

- Numerals are tabular wherever a figure aligns: `.mm-perf-stat-value` sets
  `font-variant-numeric: tabular-nums` (`index.html:927`), the positions row sets it inline on
  weight/entry/current (`index.html:4846-4848`), and a page-scoped rule extends it to every table
  cell (`index.html:2105-2108`). **Rule: any new numeric cell inherits
  `body.page-mm :is(td, …)`; a numeral rendered outside that selector set is a defect.**
- Tickers and axis ticks may use `--font-mono` (`theme.css:15`); UI prose may not.
- ZH drops forced uppercase and Latin tracking: `html[data-lang="zh"] h2 { letter-spacing: 0 }`
  (`theme.css:90`) and the ZH body family swaps to a native CJK sans (`theme.css:86-89`). ZH
  eyebrows therefore render at their natural case; the label text itself is ZH copy, never
  transliterated English.

### Spacing

The app ships a real spacing scale: `--space-1: 4px` … `--space-8: 32px` (`theme.css:31-32`),
covering `DS_foundations.md`'s `4 / 8 / 12 / 16 / 20 / 24 / 32 / 44px` except the 44px step.

- **Within a panel**: 4 / 8 / 12px. Label→value 3px, value→sub-line 1px
  (`.mtile-val` margin `3px 0 1px`, `theme.css:225`); row vertical padding 6px
  (`.mm-perf-stat` `gap: 4px` `index.html:912`)).
- **Between elements inside one answer**: 16 / 20px (`--space-4`, `--space-5`).
- **Between panels**: 24 / 32px (`--space-6`, `--space-8`).
- **Page gutter**: 16px at 375, 24px at 768+.
- **The 44px step** is a **target-size** rule, not a margin: every tappable row and control keeps
  ≥ 40px (`DS_states-accessibility.md` "Accessibility floor") of hit area even when its painted box
  is shorter. Panel radius is `--radius-lg: 15px` (`theme.css:30`); the chip radius stays the
  small scale (`--radius-sm: 8px`, `theme.css:30`) so a chip never reads as a panel.

### Number formatting

The app has real, consistent helpers today; the spec binds to them rather than to new ones.

- **Currency symbol is per book and comes from the book registry, not from a price** —
  `registry.currency(portfolio_id)` (`portfolio/registry.py:305-307`), declared per book in
  `PORTFOLIOS` (`registry.py:106` `CNY` for `china`, `registry.py:124` `HKD` for `hk`) and
  defaulting to `USD` (`registry.py:307`). It reaches the view as
  `/api/live_marks.currency` (`app/web.py:1197`) and `/api/portfolio.currency`
  (`app/web.py:249`). The renderer's `_ccySym()`/`_ccySymOf()` (`index.html:3827`) maps the code
  to `$` / `¥` / `HK$`. A currency symbol is **never** written into prose copy; it prefixes the
  numeral only. Note the one live gap: `/api/portfolio`'s `account_preview` sub-object
  (`app/web.py:1343-1354`) does **not** carry `currency`, so a V1 that reads only that object has
  no currency and must take it from `/api/live_marks`.
- **Whole-money figures** (NAV, cash, invested, position market value) render through `fmtNav()`
  (`index.html:3861-3864`): symbol + `Math.round(n).toLocaleString('en-US')`, thousands-separated,
  **no decimals**. Fractional cents are not displayed at Tier 1; a per-lot exact value moves to
  the receipt.
- **Per-share prices** render at 2dp with the symbol (`index.html:4819-4820`).
- **Signed money** always carries an explicit `+`/`−` **outside** the symbol, and the percent sits
  in a parenthesised, 1dp, 70%-opacity span (`pnlCell`, `index.html:3612-3617`). Absolutes only:
  `+`/`-` + `Math.abs()`, so the sign column never jitters.
- **Percentages**: 1dp for weights and cell percentages (`pct()`, `index.html:3682`);
  2dp with an explicit sign for changes (`fmtPctSign`, `index.html:3869-3873`; `fmtPct1`,
  `:3866-3868`). A percent is always suffixed `%`; a fraction is never shown raw.
- **Basis points**: drawn as `bps` only for spreads, correlations and attribution deltas
  (`123 bps`, no `+` for magnitude, `+12 bps` for a signed delta). Basis points are never used for
  a return; a return is a percent.
- **Sample sizes** are integers and always sit next to the rate they qualify (`n = 42`).
- **Counts** render as one canonical integer per population per page
  (`DS_foundations.md` "Information density") — one holdings count, one pending count. Never
  `0` for an unknown count; see the coercion rule below.
- **Null never becomes a number.** `pct(null)` and `fmtPctSign(null)` return an em-dash today
  (`index.html:3682`, `:3870`), and `pnlCell(null)` returns a dash with **no colour class**
  (`:3613`). That is correct for a per-cell mark. It is **not** correct for a *state*: an
  unavailable, withheld or benchmark-less slot renders the word `unavailable`, never `—`.
  `DESIGN-SYSTEM-GAP G3: unavailable value slot — DS_components.md "Metric" says null gets an
  explanation and never a bare em-dash, but `app/static/index.html` renders `—` for every null
  metric and has no muted text style for "the value cannot be computed"; V1–V7 need one, and
  #1719 supplies the ZH/EN word `Unavailable` / `不可用` for the self-directed header only.*
- **No coercion to zero.** A missing `account.cash` is coerced to `0.0` at `app/web.py:1341`
  (`float(account.get("cash") or 0.0)`), `n_names` renders `(m.n_names || 0)` and `cash_weight`
  renders `(d.cash_weight || 0) * 100` (`index.html:4606`, `:4610`), and sleeve weights render
  `(sl.leadership || 0) * 100` (`index.html:4516-4518`). Every one of these must become `unavailable`
  under `CONTRACT REQUEST → E7` (`account.cash` must stay distinguishable from 0) and its siblings
  in V1's field table. This is the one rule that applies to **every** numeric slot in V1–V7.

### Timestamps and freshness

- **Exactly one freshness stamp per panel and one page stamp per view** (`DS_foundations.md`).
  The page stamp is the book's own as-of and is the first thing painted (art direction §1). V1
  additionally carries a per-name mark age inside the row, which is evidence, not a stamp.
- **Relative age wins over absolute time** for anything under 7 days ("3 min ago", "2 days
  behind"); an absolute date wins beyond that. A timestamp with no value renders `unavailable`,
  never today's date.
- **Timezone**: a **date-only** value (`YYYY-MM-DD`, a fill date, a mark date) renders as that
  calendar date and is **never** converted through UTC — the app already parses it locally for
  exactly this reason (`_parseLocalDate`, `index.html:3686-3690`, with the in-code note that a
  bare date read as UTC midnight renders the previous day in a negative-offset zone). A
  **timestamp** renders in the **viewer's local zone** with its offset once, in the page stamp.
- **US session times are always ET**, regardless of the viewer's zone, because they name a market
  event: "fills at the 2026-10-22 09:30 ET open". The value today is the projected
  `pending_target.fill_after` / `market.next_open` (`app/web.py:2064-2066`); the spec prefers the
  book's own eligible session under `CONTRACT REQUEST → R2` (`next_eligible_session
  {session_open_at, market, reason}`, ISO-8601 **with offset**, nullable when not queued, from
  the market calendar + scheduler).
- **Date format**: ISO `YYYY-MM-DD` in all machine surfaces and receipts; `M/D/YY` only in a
  compact table cell (`fmtDateShort`, `index.html:3692-3698`). EN and ZH share one date format;
  ZH changes the words around it, never the digits' order.

### EN / ZH conventions

- **One language at a time**, toggled by `html[data-lang]`; copy is dual-emitted with `.l-en` /
  `.l-zh` spans and CSS visibility (`theme.css:82-83`), or read from the `T()` dictionary whose
  keys carry both strings (e.g. `pos.q_exit` `index.html:3450`). A view may not mix.
- **Direction flips, health does not.** `--up`/`--down` swap under `html[data-lang="zh"]`
  (`theme.css:71-80`), and `--q1`/`--q3` remap with them. `--ok`/`--warn`/`--act` never flip —
  the exclusion is written into the stylesheet's own comment (`theme.css:64-67`).
- **Direction is never colour alone**: every up/down figure carries its sign and, where space
  allows, an arrow. A red `+2.4%` and a green `−1.1%` remain readable in greyscale.
- **No forced uppercase in ZH.** `text-transform: uppercase` is applied to EN eyebrows only
  (`index.html:919`, inside `:915-921`); the ZH family drops the Latin tracking (`theme.css:90`).
- **Native-shaped copy, not literal translation.** A ZH sentence is written for a Chinese reader,
  so it drops an English subordinate clause rather than transliterating it; the constraint is the
  ≤14-word clause budget (`DS_components.md` VerdictHero), counted per language.
- **A missing `name_zh` falls back to `name`; a missing `name` draws no subtitle** — the app
  already refuses to render a duplicated ticker-as-name subtitle (`securityName`,
  `index.html:3596-3603`). V1's ticker cell inherits that.
- **A missing `summary_zh` falls back to the EN memo** (`app/web.py:1741` family); it never shows
  an empty memo block.

### Accessibility floor

Per `DS_states-accessibility.md` and `MASTER_PRODUCT_DESIGN_SYSTEM_V1.md`:

- Text ≥ 4.5:1 against the **painted** surface; affordance boundaries, focus rings and segmented
  controls ≥ 3:1 where the boundary carries meaning. Dark `--muted #8c96a6` on `--panel #14171e`
  and light `--muted #5f6c7e` on `--panel #ffffff` are the pairs that must be checked at 12px and
  below; a sub-line at 9.5px is measured against `--panel`, never against `--bg`.
- `:focus-visible` on every interactive element, drawn with `--focus-ring`
  (`theme.css:29`); focus must never be clipped by the table's internal scroll container.
- Targets ≥ 40×40 effective (`DS_states-accessibility.md`; 44px preferred).
- Exactly one `h1` per view; every panel keeps a real `h2` (they exist today —
  `index.html:2756`, `:2820`, `:2838` — and must survive the §2 route split).
- `aria-live="polite"` is already on the status strips (`#decision-availability` `:2723`,
  `#perf-evidence` `:2757`, `#live-marks-status` `:2758`); the V1 answer block takes the same
  politeness so a `Provisional` badge change is announced, and no `aria-live` region contains a
  value that changes on every poll tick.
- `prefers-reduced-motion` disables motion including pseudo-element sweeps
  (`DS_foundations.md` "Motion"). Settled data never pulses; only a live fact may.
- Every hover affordance (LENS, help popover, posture tooltip) also opens on focus and on tap.
  `helpIcon` is already `tabindex="0"` (`index.html:3606-3608`); the pattern is binding.
- No page-level horizontal scroll at 375px; tables scroll inside their own container.

### Density rules

- Above the fold: chrome + **the answer** + at most **two** supporting modules
  (`DS_foundations.md` "Information density"). Default L1 budget 5 modules, ceiling 7.
- An L1 table shows **≤ 8 rows**, then a counted `See all N` / `查看全部 N 项` that names the
  landing. The Positions table does not cap at 8 today; the spec caps it and names V6 as the
  landing (`SEAT DECISION` — capping `#positions` at 8 rows is a behaviour change to a shipped
  panel).
- Demotion is a first-class act and every demoted module gets a **named landing**, never silent
  disappearance (`DS_patterns.md` responsive law).
- Mechanics and receipts live in `<details>` disclosures that open by keyboard **and** touch
  (`DS_components.md` Detail disclosure; the app already uses this shape for "Method & caveats",
  `index.html:4708-4710`).
- 375px is a recomposition that preserves **answer + current evidence + next action**; it is not
  the desktop view squeezed.
- A number that is derivable from another visible number does not earn Tier 1.
  `DESIGN-SYSTEM-GAP G4: counted overflow affordance — DS_components.md and the density law require
  a counted "See all N" depth affordance, but `app/static/index.html` has no such component and
  `PF_GATED_ONLY` panel gating (`index.html:6468`) hides whole panels instead of counting rows;
  V1 and V2 both need the counted version.*

### Canonical state vocabulary

This table is **binding for V1–V7 and every other part of this spec**. A view uses these exact EN
and ZH labels; a view may not mint a synonym. Every state is carried by a **labelled word plus a
non-colour cue**, so the state survives greyscale, colour-blindness and a screen reader.

| state | EN label | ZH label | non-colour cue |
|---|---|---|---|
| loading | Loading | 加载中 | skeleton at final geometry, no placeholder prose |
| empty | Empty | 暂无 | full-weight sentence with the reason |
| stale | Behind | 滞后 | label + last settled as-of stamp |
| partial | Partial | 部分 | label + names what is excluded |
| error | Couldn't load | 加载失败 | label + what failed + what still works + retry |
| closed-market | Market closed | 休市 | label + next open time |
| benchmark-unavailable | Benchmark unavailable | 基准不可用 | the word, never 0 or a dash alone |
| provisional valuation | Provisional | 暂定 | label + carried names and their age (ECON A02 PROVISIONAL, `carried[]`) |
| withheld valuation | Withheld | 暂不估值 | a gap in the curve with its reason (A02 WITHHELD, `nav_withheld.jsonl`) |
| unverified (pre-A02 row) | Unverified | 未核实 | label only; never upgraded to qualified |
| queued (pending while held) | Queued | 已排队 | the held row keeps its shares and shows the #1707 chip + timing line |
| unavailable | Unavailable | 不可用 | the word in the value slot, muted, never a number |

**Shipped strings that predate this table.** Four shipped empty strings open with a bespoke phrase
instead of the `Empty` / `暂无` label: `pos.empty` (`index.html:3250`), `pend.none` (`:3297`),
`ec.no_data` (`:3235`) and `rej.empty` (`:3395`). Each view cites the shipped string only as the
current state and specifies its replacement as a **copy request** (i18n strings are PRODUCT's write
scope); the replacement lands in that view's build PR with an EN/ZH agreement test. No view treats
a shipped bespoke string as accepted copy.

What each state still does — the honest reading of the table:

- **loading** — nothing is drawn, so nothing is wrong yet; the previous settled render stays
  readable underneath until the skeleton lands, at **final geometry** so nothing reflows.
- **empty** — the read succeeded and the population is genuinely zero; holdings, cash, NAV, the
  as-of and the session clock all still work, and the sentence says why (new vs cleared vs filtered).
- **stale** — the value is real but old; every number still works and only its currency is behind,
  with the **last settled as-of** inline so the reader can judge the age.
- **partial** — the answer and every included row still work; the label names exactly what is
  excluded and a denominator never silently treats the exclusion as zero.
- **error** — one source failed; everything not sourced by that read still works, the label says
  what failed, and a retry is present. Error is **not** `unavailable`: error says the read failed,
  `unavailable` says this slot has no contract yet.
- **closed-market** — nothing failed, the market is shut; every last-settled value still works and
  the label carries the **next open time**, so the reader never guesses whether the age is the
  market's doing or the feed's.
- **benchmark-unavailable** — the portfolio side is fine; the portfolio figure stands alone at full
  weight and only the comparison slot carries the word.
- **provisional valuation** — the NAV is computed but ≥1 price is carried or unattested (A02
  `PROVISIONAL`); the numeral renders at reduced weight beside the badge and the label lists the
  carried names with `age_days`, and it is never upgraded because the number happens to be close.
- **withheld valuation** — ≥1 held line is UNPRICED, so under A02 **no NAV row is written**; in a
  series this is a **gap with its reason**, never a zero or a flat segment, and at Tier 1 the
  affected dates are named from `nav_withheld.jsonl`.
- **unverified** — a pre-A02 row no published contract qualifies; label only, never re-labelled
  `Provisional` (which asserts a cause) and never upgraded to `Qualified`.
- **queued** — an accepted, validated target exists and has not filled; the account is still the
  account, so the held row keeps its shares, marks, weight and P&L and only the verdict cell
  changes to the PR #1707 chip + timing line. After the fill the chip disappears because the row
  is re-read from the settled account — it never lingers as a historical badge.
- **unavailable** — this slot has no shipped contract; the **word** sits in the value slot, muted,
  with no number, zero, em-dash or inferred value anywhere near it.

Three axes stay separate on purpose, because the census found all three failures: **valuation
status** (QUALIFIED / PROVISIONAL / WITHHELD / unverified) is *not* a **data-availability** status
and neither is a **market** status. A provisional valuation of a fully available account is not
partial; a closed market with a qualified NAV is not stale; an unavailable field on a perfectly
qualified row is not provisional.

---

## 4. Views

### V1 Portfolio overview

#### Question

**"What does this book actually hold, and what is it actually worth right now — including the
things it cannot tell me?"** It answers **Q1** of the five (MASTERPLAN §10.2). It does not answer
"what should I do" (V2), "what is about to happen" (V3) or "how has it done" (V4); those are the
other views and V1 links to them rather than absorbing them.

#### Archetype

**G — Monitor**, as the product shell. It is a since-stamp → what-changed → managed-list
composition: the book as-of stamp, the bounded change list (a queued MU exit is a change), then
the holdings list. V1 is the only view that composes a **C (Instrument Analyzer)** interior — each
row's disclosure is a compact instrument summary — but the shell stays G, because the reader's
first question is always "what is true right now", not "explain this name".

#### Information hierarchy

- **Tier 1 — the answer.** One answer block, above the fold: holdings count · cash · NAV with its
  qualification badge · one page freshness stamp. Plus at most two supports: (1) the session +
  pricing strip, (2) the positions table capped at 8 rows with a counted `See all N`.
- **Tier 2 — the account, in full.** `#alloc` sleeve bar with its legend and Gross; the remaining
  holdings rows behind `See all N`; per-name mark provenance (source, as-of, staleness days) on
  each row's sub-line; the limitations list (ECON A02 `carried[]` / `unattested[]`, partial
  pricing, session state); `#safety` as the risk module.
- **Tier 3 — mechanics and receipts.** Method & caveats disclosure (the shape already in use at
  `index.html:4708-4710`); per-position thesis/expansion (the landing is **V6**, not a Tier-3
  drawer on this page — see §2); the risk subscores, breaches and caveats bars; the source-coverage block.

V1's own landing rules: the `#positions` expand-row becomes **V6**; Trade History becomes **V3** and
**V4**; the decision memo becomes **V2**. Nothing from V2–V7 is duplicated into V1's tree.

#### Fields

Required content for this view: actual holdings, cash, current/estimated valuation, valuation
timestamp, and meaningful limitations. Every row below is either cited against this checkout or
marked `CONTRACT REQUEST` with type, nullability and units.

| Field | Meaning | Owner | Source today (API + JSON path) | Type / units | Nullable? | Display when null / unknown |
|---|---|---|---|---|---|---|
| `portfolio` | active book id | RUNTIME | `/api/live_marks.portfolio` — `app/web.py:1195`; `/api/portfolio?portfolio=` | string enum | no | — |
| `currency` | book base + display currency | ECON | `/api/live_marks.currency` — `app/web.py:1197` → `registry.currency()` `portfolio/registry.py:305-307` | `USD\|CNY\|HKD` | no (defaults `USD` `registry.py:307`) | never null in practice; if a response omits it, symbol falls back to `USD` and the stamp says so |
| `account_preview.cash` | settled cash | ECON | `/api/portfolio.account_preview.cash` — `app/web.py:1347`, coerced at `:1341` | number, book ccy | **must remain distinguishable from 0** | `Unavailable` — **never `$0`**. Fix = `CONTRACT REQUEST → E7` (remove the `or 0.0` coercion at `app/web.py:1341`) |
| `account_preview.current_nav` | marked value of the book | ECON | `app/web.py:1346`; `paper_account.nav()` | number, book ccy | yes | `Unavailable` |
| `account_preview.invested` | NAV − cash | ECON | `app/web.py:1348` (`max(0.0, nav − cash)`) | number, book ccy | yes | `Unavailable`; note it is derived, never independent |
| `account_preview.inception_date` / `starting_nav` | book age and capital base | ECON | `app/web.py:1344-1345` (`or 1_000_000.0` default at `:1342`) | date / number | yes | `Unavailable`; the `$1,000,000` default must go (`SEAT DECISION` — see below) |
| `performance.current_nav` | NAV used for weights | ECON | `/api/live_marks.performance.current_nav` — `app/web.py:1177`, `:1185-1192` | number, book ccy | yes | `Unavailable`; weights render `Unavailable` too because the denominator is gone |
| `performance.availability.valuation_basis` | `last_recorded_nav` / `provided_prices` / `cash_only` / `unavailable` | ECON | `app/web.py:1179`; consumed `index.html:3934-3936`, `_performanceEvidenceText` `:3875-3900` | enum | yes | `Unavailable` |
| `nav_status` (QUALIFIED / PROVISIONAL) | ECON A02 qualification of the current NAV row | ECON | **not yet exposed by any API** — `paper_account.valuation()` per `_pbr_inputs/ECON_CONTRACTS_PR1699.md:68-88` | enum `QUALIFIED\|PROVISIONAL`; absent on pre-A02 rows | yes | pre-A02 → `Unverified`; contract `CONTRACT REQUEST → E1` |
| `nav_qualified` | qualified NAV, null under PROVISIONAL | ECON | `paper_account.valuation()` | number, book ccy | yes (null when PROVISIONAL) | PROVISIONAL renders `nav` at reduced weight beside the badge; pre-A02 renders `Unverified`. `CONTRACT REQUEST → E2` |
| `carried[]` | names priced from an older close | ECON | `paper_account.valuation()` — A02 shape `ECON_CONTRACTS_PR1699.md:84-87` | `{ticker, price, price_asof, age_days, source, value, weight_of_invested}[]`; price book ccy; `age_days` calendar days | no — empty array, never absent | empty array → no limitation line at all. `CONTRACT REQUEST → E3` |
| `unattested[]` | names with no attested price source | ECON | `paper_account.valuation()` — A02 `ECON_CONTRACTS_PR1699.md:88` | `string[]` of tickers | no — empty array | empty → nothing drawn. `CONTRACT REQUEST → E4` |
| **current-valuation projection** | one API object carrying status + as-of + nav + nav_qualified + carried + unattested + unpriced for the *current* book | ECON (read helper) / PRODUCT (`app/web.py` wiring) | not yet exposed — the legacy `paper_account.nav()` call at `app/web.py:1339` migrates to `valuation()` in the same change | object; `status:"unavailable"` when no valuation exists | object is non-null; its members are null | whole header renders `Unavailable`. `CONTRACT REQUEST → E6` |
| `positions[].ticker` | held lot | ECON | `/api/portfolio.positions[].ticker` — `app/web.py:1355-1400`; render `index.html:4843` | string | no | row absent → no row; the account may still hold lots the strategy snapshot omits (`app/web.py:1388-1420`) |
| `positions[].name` / `name_zh` | security name sub-line | PRODUCT | `app/web.py:1420` `_attach_security_names`; `securityName()` `index.html:3596-3603` | string | yes | subtitle not drawn (correct); a ticker-as-name duplicate is suppressed in code |
| `positions[].shares` | lot size | ECON | `/api/live_marks.positions[].shares`; `app/web.py:1389` | number | yes | `Unavailable` |
| `positions[].sleeve` | `brain` / `conviction` / `leadership` / `account` | RESEARCH | `app/web.py:1385`, `:1390` (`"account"` for account-only rows) | enum | yes | defaults to leadership styling today (`index.html:4799`) — must render `Unavailable`, not a guessed sleeve |
| `positions[].stage` | DOCTRINE stage 0–4 | RESEARCH | book file `latest.json` | int 0–4 | yes | `—` (existing cell behaviour, correct: a stage is a per-cell value) |
| `positions[].verdict` | book verdict | RESEARCH | `vKey` map `index.html:4823`, incl. `pos.v_exit_pending` | enum | yes | `(p.verdict \|\| 'hold')` at `:4804` renders HOLD — **must become `Unavailable`**, never a default verdict |
| `positions[].cost_basis` / `avg_cost` | entry price | ECON | `app/web.py:1364`, `:1155`; render `index.html:4818-4819` | number, book ccy | yes | `—`; a `pending` (unfilled) row shows `est_price` instead |
| `positions[].current_price` | mark | ECON | `app/web.py:1361`; render `index.html:4849` | number, book ccy | yes | `—` (correct per-cell behaviour) |
| `positions[].market_value` | shares × mark; the weight denominator | ECON | `app/web.py:1363`; weight computed `:1156`, `:1380` | number, book ccy | yes | `—` |
| `positions[].weight` | weight of NAV | ECON | `app/web.py:1380`, gated on valuation basis `app/web.py:1186-1193`; render `pct()` `index.html:4846` | fraction 0–1 | yes | `—` today via `pct(null)` (`index.html:3682`); correct per-cell, but the **sleeve bar** must not inherit it (see below) |
| `positions[].unrealized_pnl` / `unrealized_pct` | open P&L | ECON | `app/web.py:1365-1366`; `pnlCell()` `index.html:3612-3617` | number ccy / fraction | yes | `—` with **no colour class** (correct) |
| `positions[].quote_source` / `quote_as_of` / `quote_is_live` / `quote_stale_days` | per-name mark provenance | RUNTIME | `app/web.py:1149-1157`, `:1367-1371`; strip render `index.html:8697-8768` | string / date / bool / days | yes | strip falls back to `generated_at`; the "live feed asleep" branch is `stale` |
| `pending_target.rows[]` action on a **held** row | queued change against a lot still held | ECON | `/api/trades.pending_target.rows[].action` — projected `app/web.py:2001-2222`; helper `_heldPendingChange` `index.html:4717-4780` | enum `exit\|trim\|add\|comparison_unavailable\|unpriceable` → `unclassified` | yes | `pt.status !== 'queued'` → no chip (`:4733`); `hold/blocked/buy/filtered/unknown` → no chip (`:4755`); never infer a direction |
| `pending_target.rows[].fill_after` / `.queued_at` | when it fills / when it was queued | RUNTIME | `app/web.py:2064-2066`, `:2216-2219`; chip timing `index.html:4836` | ISO-8601 with offset | yes | `fill_after` null → `awaiting settlement` (`pend.awaiting_lbl` `index.html:3294`) |
| `sleeves.leadership` / `.conviction` / `.cash` | sleeve weights | ECON | `renderAllocation()` `index.html:4513`; `(sl.leadership \|\| 0) * 100` `:4516-4518`, legend `:4528-4530` | fraction | yes | **today renders `0%`** in both the bar width and the legend — must render `Unavailable` (census truth violation 3) |
| `gross` | gross exposure | ECON | `renderAllocation()` `index.html:4532` (`b.gross != null` guard) | fraction | yes | label hidden when null (correct) |
| `pricing.priced_positions` / `total_positions` / `complete` | how much of the book is priced | ECON | `app/web.py:1204-1208` | ints / bool | no | `Number(pricing.total_positions \|\| 0)` at `index.html:8806` — **must stop coercing to 0**; see the partial state |
| `session.state` / `market` / `timezone` / `next_open` / `is_open` | exchange clock | RUNTIME | `portfolio/market_sessions.py`; labels `index.html:8727-8736` | enum / string | yes | unknown venue state currently falls back to `'closed'` (`:8731`) — **must become `Unavailable`**, never a fabricated `closed` |
| `poll_after_seconds` | refresh cadence | RUNTIME | `app/web.py:1198-1200`; `index.html:8752` | seconds | yes | `Number(seconds) \|\| 120` — the `\|\| 120` default is a guess and must go |
| `archived` / `frozen_as_of` | archived book | ECON | `app/web.py:247-253`; strip `index.html:8710-8714` | bool / ISO-8601 | no | chip `.mm-archive-chip` + `Archived` / `已归档` (`index.html:6492`) |
| **benchmark comparison** | same-window return difference | ECON | `/api/performance` via `brain/benchmark_comparison.compare_curves` (#1434 helper, per A12 `ECON_CONTRACTS_PR1699.md:307-355`); today read as `/api/live_marks.performance.vs_benchmark_pct` / `.vs_spy_pct` (`app/web.py:1177-1178`, `:210-211`) | `{status: supported\|unsupported, reason, start, end, book_return, bench_return, delta}`; fractions | object non-null; `unsupported` ⇒ every number null | `status:"unsupported"` ⇒ the tile renders **`Benchmark unavailable` / `基准不可用`** and the portfolio figure keeps its weight. `CONTRACT REQUEST → E8` |
| **page as-of** | one freshness stamp for the whole view | RUNTIME | `/api/live_marks.generated_at` (`app/web.py:1194`) + `session.timezone` | ISO-8601 with offset | yes | `Unavailable` |
| **per-name mark age** | how old each mark is | RUNTIME | `positions[].quote_age_seconds` / `.quote_stale_days` (`app/web.py:1150`, `:1152`) | seconds / days | yes | no sub-line drawn |
| `disclaimer` / `disclaimer_zh` | footer qualifier | RESEARCH | `app/web.py:1428-1433`; render `index.html:8483-8487` | string | yes | falls back to the dictionary footer string |
| risk module (`safety_score`, `grade`, `metrics.*`, `coverage.*`) | the `#safety` support | ECON | `/api/risk` — `app/web.py:1228-1267`; `renderSafety()` `index.html:4539-4610` | number / enum / mixed | yes | `Not enough data to assess portfolio safety yet.` (`:4547`); **`(m.n_names \|\| 0)` at `:4606` and `(d.cash_weight \|\| 0) * 100` at `:4610` must render `Unavailable`, not `0 actual` / `0.0%`** (census truth violation 4) |

#### Layout

Ordered module lists per breakpoint. Every demoted module gets a **named landing**; nothing is
deleted for space.

**1280 — desktop.**

1. Chrome: book switcher (primary axis) + view tabset (secondary axis), per §2.
2. **Answer block** — holdings count · cash · NAV + qualification badge · page freshness stamp.
   Canvas tier, above the fold, the only 30px numeral on the page.
3. Session + pricing strip (`#live-marks-status`, `index.html:2758`) — market, state, next open,
   pricing completeness. Support-1.
4. **Positions** (`#positions`, `index.html:2837`) — 8 rows max + `See all N`. Support-2.
5. Allocation (`#alloc`, `index.html:2819`) — sleeve bar + legend + Gross.
6. Limitations — carried names, unattested names, partial pricing, valuation basis sentence.
7. Portfolio Safety (`#safety`, `index.html:2853`) — collapsed by default.
8. Method & caveats disclosure.
9. Footer disclaimer (`disclaimer` / `disclaimer_zh`).

Above the fold: 1–4 only. `#safety` never appears above the fold.

**768 — tablet.** Same order, two-column where a module has independent content: the answer block
keeps full width; Positions takes 8 of 12 columns with Allocation stacked beside it; Safety goes
full width below. The `mm-hide-sm` columns (sleeve, stage, entry, current price —
`index.html:4844-4845`, `:4847-4848`) stay hidden; weight, unrealized and verdict remain.

**375 — mobile recomposition.** Answer + current evidence + next action survive; mechanics do not.

1. Chrome: book switcher (scrollable), view strip (horizontally scrolled, recentred on the
   active item, reusing `revealActivePortfolioTab`, `index.html:6504`).
2. Answer block — stacked: count, then NAV (18px numeral, `index.html:2419`), then cash, then the
   page stamp. The qualification badge sits **next to the numeral**, never below it.
3. Session strip — one line, truncated with the full string in the disclosure.
4. Positions — the verdict cell and the weight are the only columns that survive
   (`index.html:4846`, `:4832`); everything else is `mm-hide-sm` today and stays hidden.
5. `See all N` for the remaining holdings → **V6 list landing**.
6. Allocation — the bar with its legend, at full width.
7. Limitations — a disclosure whose summary names the count ("3 carried prices"), per
   `DS_components.md` Detail disclosure ("summary says what is inside + why open").
8. Demoted: Safety → V7-adjacent `#safety` landing inside the Operations view; method & caveats →
   its own disclosure; per-row mark provenance → the row's second tap.

No horizontal page scroll at 375. The Positions table scrolls **inside its container**; it does
not become a card list unless the table itself is replaced.

#### States

Each state below gives the trigger at field level, the exact EN + ZH copy, the visual treatment,
and what still works. The two worked examples are **observations on the captured `autonomous`
book at 2026-10-22** (Facts observed), used as the acceptance fixtures.

**loading.** Trigger: `/api/portfolio` or `/api/live_marks` has not resolved for the active book;
the panel body is still the shipped placeholder (`index.html:2839` "Loading positions…").
EN `Loading` · ZH `加载中`. Treatment: skeleton at **final geometry** — the answer block reserves the
30px numeral's box, the positions table reserves 8 rows of exact height, the sleeve bar reserves
its full-width strip — so nothing reflows on arrival. **No placeholder prose**: the shipped
"Loading market clock…" (`index.html:2759`) is replaced by the skeleton, because a sentence that
looks like data is not a skeleton. Still works: chrome, book switcher, view tabset, the previous
book's render if one is already painted.

**empty.** Trigger: `positions[]` is `[]` **and** `pricing.total_positions === 0` — a genuinely
new or fully cleared book, not a failed read. EN `Empty — this book holds no positions yet; the
next daily run will rebuild it.` · ZH `暂无 — 本组合尚无持仓，下次每日运行后重建。` This is a **copy
request** replacing the shipped `pos.empty` string (`index.html:3250`), which predates the §3 vocabulary. Treatment: full-weight sentence,
`--text` at body weight, no glyph, no dashed placeholder box. Still works: cash, NAV, the page
stamp, the session strip, allocation (which correctly shows 100% cash).

**stale.** Trigger: any of `positions[].quote_stale_days > 0`, `generated_at` older than
`poll_after_seconds × 2`, or `frozen_as_of` set. EN `Behind` + the last settled stamp —
`Behind — showing the last settled observation of 2026-10-21 16:00 ET` ·
ZH `滞后 — 显示最近一次结算观察：2026-10-21 16:00 ET`. Treatment: `--muted` label, `--muted` chip
fill, the as-of in the same line so the age is never separated from the word. Still works:
everything — every number is real, only its currency is behind. **The stale label is never
suppressed when the market is closed**; a closed market gets `Market closed` instead (below), and
the two are different sentences about different things.

**partial.** Trigger: `pricing.complete === false`, or `carried[]` non-empty, or
`unattested[]` non-empty, or `account.status === "partial"`. EN `Partial — MU and AAPL are priced
from an earlier close; the other 2 names are live.` ZH `部分 — MU 与 AAPL 使用较早收盘价定价，其余
2 个标的为实时。` Treatment: `--muted` chip + a **count** of what is excluded, never a ratio that
treats the exclusion as zero. **Observed today and currently wrong**: `pricing` counts are rendered
through `Number(pricing.total_positions || 0)` (`index.html:8806`), so a missing count draws `0`;
and the sleeve bar's `(sl.leadership || 0) * 100` (`index.html:4516-4518`) draws a plausible `0%` split for a
sleeve that was never priced. Both become `Unavailable`. Still works: the account, cash, NAV at its
real (qualified-or-provisional) status, and every included row.

**error.** Trigger: a source read fails — `/api/portfolio` non-2xx, an unreadable `account.json`,
or (for `self_directed`) the exception branch at `app/web.py:2422-2432`. EN `Couldn't load the
account file. Holdings, cash and NAV are unavailable; the session clock and the last settled
positions still work.` + `Retry` · ZH `加载账户文件失败。持仓、现金与净值不可用；交易时段信息与
上次结算持仓仍可用。` + `重试`. Treatment: `--warn` semantic ink on the label word only, a quiet
`--panel2` fill and an **even neutral `--line` border** — no coloured container edge, no stripe
(`DS_components.md` Callout). **This state must never render a fabricated book.** The captured
`/api/self_directed` exception path returns `nav = cash = 1,000,000`, `positions: []`,
`total_return_pct: 0.0` (`app/web.py:2423-2432`) — Mastermind PR #1719 replaces it with
`status:"unavailable"` and every money field `null`; V1 must render that as `Unavailable`, and the
silent `_fresh_account()` fallback beneath it is `CONTRACT REQUEST → E13`. Still works: every panel
not sourced from the failed read.

**closed-market.** Trigger: `session.is_open === false`. EN `Market closed — next open
2026-10-22 09:30 ET` · ZH `休市 — 下次开盘 2026-10-22 09:30 ET`. The label and the next-open time
are **one unit**: a closed market with no next-open time renders `Market closed — next open
Unavailable`. Treatment: `--muted`, never `--warn`; the session dot is static. Still works:
every last-settled number, at full weight. This is the state that most often gets confused with
`stale`, and the distinction is the whole point: the market being shut is a fact about the market,
not a defect in the feed.

**benchmark-unavailable.** Trigger: A12 `compare_curves` returns
`status:"unsupported"` with a `reason` (fewer than two finite-positive dated points on both curves,
disjoint windows, or a WITHHELD endpoint — `ECON_CONTRACTS_PR1699.md:336-350`), or
`vs_benchmark_pct` is `null` (`app/web.py:194-197` only computes it when a final `spy_nav` exists
and `starting_nav > 0`). EN `Benchmark unavailable` + the reason · ZH `基准不可用` + 原因.
Treatment: the **word** in the value slot at `--muted`; **never `0.00%`, never `—`, never an
omitted tile**. A tile that simply disappears reads as "no outperformance"; the word reads as
"not computed". The portfolio-side figure is unaffected and keeps full weight. Still works:
portfolio return, NAV, drawdown, cash. (The "vs SPY" tile rendering a bare dash with the
explanation in a separate sentence is the captured defect this state replaces —
`CONTRACT REQUEST → E8`.)

**provisional valuation.** Trigger: A02 `nav_status === "PROVISIONAL"` — no UNPRICED line, but at
least one CARRIED or UNATTESTED line (`ECON_CONTRACTS_PR1699.md:68-88`). EN `Provisional` /
ZH `暂定`, plus the carried names and their ages: `Provisional — MU priced from the 2026-10-21
close, 1 day old` · `暂定 — MU 使用 2026-10-21 收盘价定价，已滞后 1 天`. Treatment: the numeral stays at
full size but takes `--muted` ink beside the badge — reduced **weight**, not reduced size, so the
answer is never visually demoted by its own honesty. `nav_qualified` is `null`, so the qualified
figure is not drawn. Still works: holdings, cash, weights, P&L, allocation, the sleeve bar — all of
which are computed from the same carried price and inherit the same qualification. A `Provisional`
badge is never upgraded because the carried price turned out close.

**queued vs held — the accepted MU exit.** Trigger: `/api/trades.pending_target.status ===
"queued"` and `pending_target.rows[]` contains `MU` with `action === "exit"` while
`positions[]` still contains `MU` with shares > 0. **Observed**: `autonomous` holds XOM, MSFT, MU,
AAPL; a target queued at `2026-10-22T06:23:03Z` omits MU, and the projection carries
`rows[MU].action = "exit"` with `fill_after = 2026-10-22T09:30:00-04:00`. Before PR #1707 the
Positions verdict cell rendered the stale book verdict `HOLDING` and the exit appeared only in the
separate Pending Orders panel, so the primary holdings view contradicted the accepted decision the
queue already carried. **Required behaviour, as shipped by Mastermind PR #1707** (`helper between
`index.html:4717-4780`, `_heldPendingChange`; chip classes and keys `:338-353`, `:3448-3453`;
render `:4830-4840`):

| queued action | chip class | EN label (`pos.q_*`) | ZH label |
|---|---|---|---|
| `exit` | `.mm-verdict-chip.exit_pending` | `EXIT QUEUED` | `已排队卖出` |
| `trim` | `.mm-verdict-chip.trim` | `TRIM QUEUED` | `已排队减仓` |
| `add` | `.mm-verdict-chip.add` | `ADD QUEUED` | `已排队加仓` |
| `unpriceable` / `comparison_unavailable` | `.mm-verdict-chip.hold` | `CHANGE QUEUED` | `已排队调整` |

- The **queued state label is `Queued` / `已排队`** in the canonical vocabulary; the chip above is
  the view's *specific* wording and must carry the same meaning — the chip's tinted fill and its
  border are the non-colour cue's partner, and the row also carries
  `data-queued-change="exit|trim|add|unclassified"` (`:4839`) so the state is assertable in a DOM
  test rather than only visible.
- The timing line sits **under** the chip in `.mm-q-when` (11px, `--muted`, wrapping):
  `fills at open 2026-10-22` (`pend.fills_at_lbl` + `fmtDate`, `index.html:4836`, `:3293`), or
  `awaiting settlement` (`pend.awaiting_lbl`, `:3294`) when no fill time is known. The fill time is
  ET under the shared timestamp rule.
- **Only the verdict cell changes.** Shares, entry, current price, unrealized P&L, weight, sleeve,
  held-since and the thesis row stay exactly as they are, because nothing has filled
  (`index.html:4827-4829`). The `p.pending` branch is separate and still renders the `PENDING` chip
  on a not-yet-filled *new* lot (`:4843`).
- **A direction is never inferred.** `hold`, `blocked`, `buy`, `filtered` and `unknown` actions
  return `null` from `_heldPendingChange` (`:4755`) — they are carries or filters, not changes to a
  held lot. An unpriceable or comparison-unavailable row renders `CHANGE QUEUED` and never a
  guessed exit or trim.
- **After the fill.** At the next settled read the row's shares go to 0 and the lot leaves
  `positions[]` entirely (an `exit` is a full exit, not a trim), so the chip disappears **because
  the row is gone** — it is never retained as a historical "exited" badge, because a row that still
  shows shares and a queued-exit chip is the exact contradiction this rule exists to prevent. A
  `trim` behaves differently by design: the row survives with smaller shares and the chip clears on
  the next settled read. If the queued target is superseded or expires without filling, the chip
  clears on that read for the same reason — the settled account is the truth and the chip is a
  pending annotation on top of it, never a durable state.
- Still works: every other column of the row, the totals, the allocation, and V1's answer block.
  A queued exit does **not** change holdings, cash or NAV until it fills.

**withheld valuation** (carried on the curve, named at Tier 1). Trigger: A02 `nav_status ===
"WITHHELD"` — at least one UNPRICED held line, so **no NAV row is written for that date** and an
existing same-date row is left byte-identical (`ECON_CONTRACTS_PR1699.md:74`, `:91-93`, `:167`).
EN `Withheld` / ZH `暂不估值`, naming the unpriced names from `nav_withheld.jsonl`; the affected
dates are named rather than drawn. In V1's answer block a withheld current valuation renders the
**word plus the affected names**, never an interpolated number. Still works: cash, every position
row with its last observed mark, and the decision record. `CONTRACT REQUEST → E5`.

#### EN / ZH

Key labels, both languages. Existing keys cite the shipped dictionary entry so the spec cannot
drift from the strings already in the file.

| Concept | EN | ZH | Key / cite |
|---|---|---|---|
| View title | Portfolio overview | 组合总览 | new — V1 has no title today; `#performance` is titled `Performance — Simulated Account` (`perf.title` `index.html:3219`) |
| NAV | NAV | 净值 | `perf.current_nav` `:3220` |
| Provisional NAV | Provisional NAV | 暂定净值 | `index.html:3936` (literal, both branches) |
| Last recorded NAV | Last recorded NAV | 最近记录净值 | `index.html:3935` (literal) |
| Cash | cash: | 现金: | `perf.cash_lbl` `:3229` |
| Change from Start | Change from Start | 相对初始净值变化 | static `index.html:2770` |
| Last observed change | Last observed change | 最近记录变动 | `perf.today` `:3226` / static `:2782` |
| Recorded Drawdown | Recorded Drawdown | 已记录最大回撤 | `perf.max_drawdown` `:3228` / static `:2788` |
| vs benchmark | vs SPY (per book) | 相对标普500 (per book) | `perf.vs_spy` `:3224`; label composed per book at `index.html:3961-3963` from `benchmark_name` / `benchmark_name_zh` |
| Benchmark unavailable | Benchmark unavailable | 基准不可用 | new state word |
| Positions | Positions | 持仓 | static `index.html:2838` |
| Empty (no positions) | Empty — this book holds no positions yet; the next daily run will rebuild it. | 暂无 — 本组合尚无持仓，下次每日运行后重建。 | copy request: replaces shipped `pos.empty` `:3250` ("No positions yet — …" / "暂无持仓 — …") |
| Allocation | Allocation | 仓位分配 | static `index.html:2820` |
| Portfolio Safety | Portfolio Safety | 组合安全度 | static `index.html:2854` |
| Holding (verdict) | HOLDING | 持有中 | `pos.v_hold` `:3447` |
| Queued exit | EXIT QUEUED | 已排队卖出 | `pos.q_exit` `:3450` |
| Queued trim | TRIM QUEUED | 已排队减仓 | `pos.q_trim` `:3451` |
| Queued add | ADD QUEUED | 已排队加仓 | `pos.q_add` `:3452` |
| Queued, direction unknown | CHANGE QUEUED | 已排队调整 | `pos.q_unclassified` `:3453` |
| Fills at | at open | 开盘 | `pend.fills_at_lbl` `:3293` |
| Awaiting settlement | awaiting settlement | 等待结算 | `pend.awaiting_lbl` `:3294` |
| Archived | ARCHIVED | 已归档 | literal `index.html:6492` |
| See all N | See all 12 holdings | 查看全部 12 个持仓 | new — counted overflow affordance |
| Method & caveats | Method & caveats | 方法与说明 | `index.html:4709` |

Market-direction copy is book-agnostic; the session-strip state words already exist in both
languages (`index.html:8727-8736`: `open`/开市, `pre-market`/盘前, `closed`/收市,
`lunch break`/午间休市, `early close`/提前收市, `holiday`/假日休市, `weekend`/周末休市).

#### Accessibility

- **Contrast pairs used on this view**: `--text` on `--panel` (body, ≥4.5:1 in both themes);
  `--muted` on `--panel` for every sub-line and for the `.mm-q-when` timing line (measured at
  11px, so the pair must clear 4.5:1, not 3:1); `--up`/`--down` chip inks against their own
  `color-mix(... 15%, var(--panel2))` fills (`index.html:345-349`) at ≥4.5:1 for the label text —
  a chip is a **text** surface, so it inherits the text threshold, not the boundary one.
- **Focus order**: book switcher → view tabset → answer block (not focusable; it is prose) →
  session strip (not focusable) → positions table rows → each row's queued chip is **part of the
  row's focus target**, not a second stop → `See all N` → allocation → limitations disclosure →
  Safety disclosure → method & caveats. The DOM order above is the required tab order; no
  `tabindex` above 0 is introduced.
- **Keyboard / touch path to every Tier 2 and Tier 3 disclosure**: `Method & caveats`, the
  limitations list, the Safety panel and each position's expansion are all native `<details>`
  elements (`index.html:4708`), so Enter/Space toggle them and a touch tap does too. The
  `#positions` row is currently a `click`-only `onclick="toggleExpand(i)"`
  (`index.html:4842`) with no `tabindex`/`role` — **it is not keyboard-reachable today**; the
  expansion must become a real button or a focusable row with an Enter/Space handler, and the
  expansion's content must be reachable when the control is focusable (`aria-expanded`).
- **No hover-only content.** The posture/playbook hover pattern is V2's; V1 keeps zero hover-only
  affordances. A queued chip's timing line is always visible, never a tooltip.
- **Reduced motion**: the `Live` dot may pulse only while `session.is_open` is true and a poll is
  actually in flight; under `prefers-reduced-motion` it renders static (settled data never pulses
  anyway). Skeletons cross-fade rather than shimmer. No sweep pseudo-element is introduced.
- **Announcements**: the answer block carries `aria-live="polite"` and announces the qualification
  badge change (`Provisional` → qualified), not the NAV numeral, which changes on every poll and
  would make the region unusable with a screen reader.
- **Zoom**: at 200% zoom the positions table scrolls inside its container and the answer block
  stacks; the page never scrolls horizontally.

#### Density

- **Above-fold budget**: chrome + answer + session strip + positions (8 rows). Nothing else.
- **Row cap**: 8 rows, then `See all N holdings` naming the true total. The captured
  `autonomous` book holds fewer than 8 names, so the cap is not binding there — it binds a 12-name book. Capping a
  shipped panel at 8 is a behaviour change: **SEAT DECISION** — cap and name the landing (the V6
  list), or keep the full table with an in-panel scroll. Recommendation: cap, because the uncapped
  table pushes the sleeve bar and the limitations below the fold on a 4-name book today.
- **Never at Tier 1**: the sleeve legend's `Gross` when null; the `#safety` score; any per-name
  mark provenance; the risk subscores; the method & caveats; the footer disclaimer; the queue's
  `schema_version` / `engine_version`.
- **One canonical integer per population per page**: the holdings count in the answer block. The
  sleeve bar carries percentages, not counts; the risk module's `n_names` is demoted so it does not
  compete.
- **Redundancy rule**: the answer block's NAV and the positions table's weight column share a
  denominator. Weight stays (it is per-name and not derivable from the count), but the answer
  block never repeats the total return that V4's curve owns.

#### Truth rules

Quoted verbatim from MASTERPLAN §10.2 and binding as acceptance sentences on V1:

1. **"A natural-language explanation cannot overrule the actual account."** V1 renders the account
   first and the narrative as subordinate annotation. The `#performance` qualification sentence
   (`_performanceEvidenceText`, `index.html:3875-3900`) is evidence *about* the account, never a
   replacement for it, and no memo, posture or disclaimer sentence may contradict a rendered
   figure.
2. **"A queued MU exit must show as a pending change while MU is still held."** Implemented by PR
   #1707 exactly as specified in the States section above; on this checkout the row carries
   `data-queued-change` (`index.html:4839`) so the requirement is DOM-assertable.
3. **"An unavailable benchmark displays unavailable rather than zero."** The `vs <benchmark>` tile
   renders `Benchmark unavailable` / `基准不可用` when A12 returns `status:"unsupported"` or
   `vs_benchmark_pct` is `null`. It never renders `0.00%`, never `—`, and never disappears.
4. **"Do not visually reward a missing-price flat line as low volatility or a tiny closed-position
   sample as a winning strategy."** V1's half of this is the **day-change tile**.
   **Observed**: `nav_history.jsonl` rows for 2026-10-21 and 2026-10-22 are identical in `nav`,
   `cash`, `invested` and `spy_nav` — the 10-22 row was written before the session opened, from
   10-21 closes — and the overview rendered `Last observed change +0.00%` with the range
   `2026-10-21 → 2026-10-22`. Today `day_change_pct` is computed as
   `(navs[-1] / navs[-2] - 1.0) * 100.0` (`app/web.py:189-191`) with a `0.0` initial value at
   `:189`, so a book with **fewer than two distinct marks** produces a literal `+0.00%`.
   **Required**: a flat `+0.00%` day change that was **written before the open**, or computed from
   **fewer than two distinct marks**, renders `Unavailable` / `不可用` — never `+0.00%`. When both
   marks are real and equal, `0.00%` is a true zero and is shown, in `--muted`, with no direction
   ink. Under ECON A02 this exact row is `PROVISIONAL` with `carried[].age_days >= 1`
   (`ECON_CONTRACTS_PR1699.md:151-155`), so V1 shows `Provisional` on the same tile. A muted
   `0.00%` with a `Provisional` badge beside it is the correct render; a bare green `+0.00%` is
   the defect.

Seat-accepted truth requirements that apply here, stated as requirements:

- **Missing never coerces to zero.** `app/web.py:1341` (`float(account.get("cash") or 0.0)`) must
  render `Unavailable`, as must `(sl.leadership || 0) * 100` (`index.html:4516-4518`),
  `(m.n_names || 0)` (`:4606`), `(d.cash_weight || 0) * 100` (`:4610`),
  `Number(pricing.total_positions || 0)` (`:8806`) and `Number(seconds) || 120` (`:8835`).
  `CONTRACT REQUEST → E7`.
- **The self-directed error path never shows a funded $1,000,000 book** (`app/web.py:2423-2432`;
  Mastermind PR #1719 renders `status:"unavailable"` with every money field `null` and the header
  `Unavailable` / `不可用` with a muted value and a static muted heartbeat dot). The silent
  `_fresh_account()` fallback beneath it is `CONTRACT REQUEST → E13`.
- **A win rate always shows its `n` and is withheld below a minimum closed-sample size.** On this
  checkout the Trade History scorecard renders a bare rounded percentage (from
  `Math.round(d.win_rate * 100)`, `index.html:6242`) with no sample-size
  label. **SEAT DECISION — minimum n: 30 closed trades.** Below it the tile renders
  `Sample too small (n = 12 closed)` / `样本不足（已平仓 n = 12）` and names the shortfall; it
  never renders a percentage and never renders `0%`. Above it the tile is `57% · n = 42 closed` /
  `57% · 已平仓 n = 42`. The realized-P&L basis the rate depends on is `CONTRACT REQUEST → E10`
  (`portfolio/self_directed.py:802` is the only producer today). The captured book is above the
  floor, so its tile would render — with its `n`.

#### Acceptance checklist

Each item names its verification: **unit**, **API/DOM agreement**, or **browser screenshot**.

1. **API/DOM agreement** — for the active book, every number rendered in the answer block equals
   the same JSON path from `/api/portfolio.account_preview` and `/api/live_marks.performance`,
   character for character including the currency symbol. *Test: a DOM-extraction test that reads
   the rendered strings and diffs them against the fixture responses.*
2. **No-coercion** — with fixtures for a missing `cash`, a missing `sleeves.cash`, a missing
   `pricing.total_positions`, a missing `metrics.n_names` and a missing `quote_as_of`, every
   affected slot renders `Unavailable` / `不可用` and **no** `0`, `$0`, `0%`, `0 actual` or
   fabricated default appears in the DOM. *Test: unit over the render helpers plus a DOM assertion
   that the substring `0%` does not occur in the answer block.*
3. **Queued-vs-held** — with the captured `autonomous` fixture (`pending_target.status:"queued"`,
   `rows[MU].action:"exit"`, MU present in `positions[]`), the MU row renders
   `.mm-verdict-chip.exit_pending` with text `EXIT QUEUED` / `已排队卖出`, the row carries
   `data-queued-change="exit"`, the timing line reads `at open 2026-10-22`, and MU's shares, entry,
   current price, unrealized and weight are **unchanged** from the un-queued render. *Test: DOM
   comparison of the two renders.*
4. **No inferred direction** — with `rows[MU].action:"unpriceable"`, the row renders
   `.mm-verdict-chip.hold` + `CHANGE QUEUED` / `已排队调整`; with `action:"hold"`, `"blocked"`,
   `"filtered"` or an unknown string, **no** queued chip renders. *Test: unit over
   `_heldPendingChange` for all nine action values.*
5. **After the fill** — with the next settled fixture (MU absent from `positions[]`) no MU row
   exists and no chip is retained anywhere; with a `trim` fill the row survives with the reduced
   share count and the chip is gone. *Test: DOM assertion.*
6. **Flat-line** — with the captured 2026-10-21/2026-10-22 identical rows the day-change tile
   renders `Unavailable`, **not** `+0.00%`; with a synthetic fixture of two genuinely distinct
   marks that happen to be equal it renders `0.00%` in `--muted` with no `--up`/`--down` class.
   *Test: unit on the day-change rule + DOM class assertion.*
7. **Provisional** — with an A02 `nav_status:"PROVISIONAL"` fixture carrying
   `carried:[{ticker:"MU", age_days:1}]`, the answer block shows the `Provisional` badge **and** the
   sentence naming MU and its age; with `nav_status:"QUALIFIED"` neither appears; with a pre-A02
   row the badge reads `Unverified` / `未核实` and is never upgraded. *Test: three DOM fixtures.*
8. **Withheld** — with a `nav_withheld.jsonl` fixture for today's date, the answer block renders
   `Withheld` + the unpriced names and **no numeral**; the previous settled row is untouched. *Test:
   DOM fixture + a unit assertion that no NAV value was rendered.*
9. **Benchmark-unavailable** — with A12 `status:"unsupported"` the benchmark tile renders
   `Benchmark unavailable` / `基准不可用`; with `supported` it renders the signed delta. The DOM never
   contains `0.00%` in the benchmark slot for the unsupported fixture. *Test: DOM assertion.*
10. **States** — loading draws a skeleton at final geometry and **zero** placeholder prose; empty,
    stale, partial, error and closed-market each draw their exact sentence above; the error state
    renders `Retry` and no fabricated `$1,000,000`. *Test: browser screenshot at 375 and 1280 for
    each of the five states, EN and ZH.*
11. **Breakpoints** — at 375 / 768 / 1280 the module order is the one in Layout, no page-level
    horizontal scroll at any width, and the `mm-hide-sm` columns are hidden at 375. *Test: browser
    screenshots at all three widths, dark and light.*
12. **EN/ZH** — switching `html[data-lang]` flips direction ink (`--up`/`--down`,
    `theme.css:71-80`) while `--ok`/`--warn`/`--act` are unchanged, drops eyebrow uppercase and
    tracking, and renders every label in ZH with no English leak. *Test: screenshot pair + a DOM
    scan for `.l-en` visibility.*
13. **A11y** — exactly one `h1`; every panel has a real `h2`; all interactive elements show
    `:focus-visible` with the `--focus-ring`; the positions row is keyboard-reachable and its
    expansion toggles on Enter and Space; every `<details>` opens by keyboard and by tap; text
    contrast ≥4.5:1 including the 11px `.mm-q-when` line. *Test: automated axe pass + a keyboard
    walkthrough script.*
14. **Cache isolation** — with the response cache active, two different books requested in the
    same session never render each other's numbers (the cache key carries no user and no session —
    `app/response_cache.py:72-83`). *Test: two-session integration test asserting per-book payloads
    and DOM.*
15. **Archived books** — switching to `flagship` / `heavyweight` / `etf` shows the `.mm-archive-chip`
    `ARCHIVED` / `已归档` with the superseded line, offers no pending/ordering affordance, and shows
    the frozen as-of. *Test: DOM fixture per archived book.*

### V2 Manager decision

#### Question

**"What did the manager most recently decide to do, what did it actually do, and what would prove
it wrong?"** It answers **Q2** of the five (MASTERPLAN §10.2) and contributes to **Q5**. V2 never
answers "what is true right now" (that is V1's account) and never answers "what is about to
happen" (V3) — V2 is the *record of intent and its evidence*, and it must be legible even when
the account says something different.

#### Archetype

**G — Monitor**, composing a **C (Instrument Analyzer)** interior per decision. It is a Monitor
because it opens with *what changed in the decision record* — accepted, failed, carried, or
nothing new — before any rationale. The per-name lines inside the accepted target compose as C
because each is a small instrument read, but the shell's job is change-over-time, not explanation.

#### Information hierarchy

- **Tier 1 — the answer.** One answer block: the **latest accepted decision** (its stamp, its
  outcome word, and its one-clause rationale) plus the **account's current state beside it**, and
  the page stamp. If the latest attempt failed, the answer *is* the failure — the failure is the
  headline, not a footnote under a stale success.
- **Tier 2 — the record.** Explicit actions (executed fills and the accepted target's weights);
  compact rationale (the original accepted memo, never a refreshed snapshot); horizon and
  invalidation; the unchanged-book explanation; the per-name thesis status slots (TR-P1).
- **Tier 3 — mechanics.** Settlement-price evidence table; provider-diagnostics panel; source
  coverage and identities; the qualifications (`issues[]`) list; the decision-snapshot inspector
  (**operator-gated only**, see CR-R6 below); the full Daily Decision Log.

#### Fields

Required content: latest accepted decision, explicit actions, compact rationale, horizon,
invalidation, and unchanged-book explanation.

| Field | Meaning | Owner | Source today (API + JSON path) | Type / units | Nullable? | Display when null / unknown |
|---|---|---|---|---|---|---|
| `portfolio_id` | identity re-check that gates the whole panel | RUNTIME | `/api/portfolio?view=decision_availability` → `app/decision_availability.py:530`; gate `index.html:7267-7268` | string | no | a mismatch renders `Decision status unavailable` / `决策状态不可用` with **no numbers at all** |
| `observed_at` | the read's own stamp | RUNTIME | `app/decision_availability.py:530` | ISO-8601 UTC | yes | `Unavailable` / `不可用` (`_daTime`, `index.html:6623-6625`) |
| `status` | `available` / `partial` | RUNTIME | `app/decision_availability.py:531` | enum | no | `partial` → the panel is Partial and `issues[]` names what is excluded |
| `last_valid_decision.ts` / `.asof` | when the last valid decision was taken | RESEARCH | `app/decision_availability.py:535`; `_decision()` `:138-157` | ISO-8601 | yes | `Unavailable` / `不可用` (`index.html:7295`) — **never today's date** |
| `last_valid_decision.summary` / `.summary_zh` | the original accepted memo (rationale) | RESEARCH | `app/decision_availability.py:145-157`; banner `#auto-sum` `index.html:2741` | string (≤14-word clause at Tier 1) | yes | `Valid decision memo unavailable. See decision and account status above.` — never an empty memo block |
| `last_valid_decision.submitted_holding_count` | holdings in the submitted target | ECON | `app/decision_availability.py:145-157`; render `index.html:7296` | int | yes | `Unavailable` (today a bare `—`) |
| `last_valid_decision.summary_truncated` | the memo preview was cut | RESEARCH | render `index.html:7298-7300` | bool | no | note omitted when false |
| **`horizon`** | when this decision stops being the live thesis | RESEARCH | **absent from every payload today** — only `time_stop_by` exists per position in `/api/trades open[]` (`portfolio/position_log.py:331`) | per-holding `{horizon_end, next_review_at, review_condition, decision_id}`; date / ISO-8601 UTC | yes — absent ⇒ `Unavailable`, **never derived from holding age** | `CONTRACT REQUEST → S5` |
| **`local_thesis_status`** | does a local thesis exist for this holding | RESEARCH | **absent today** | enum `present\|absent\|unavailable` | yes | `Unavailable` — **never inferred from `provider_plan_status`** (TR-P1) |
| **`provider_plan_status`** | does the Prophet plan exist for this holding | RESEARCH | **absent today** | enum `present\|absent\|held_without_active_plan\|unavailable` | yes | `Unavailable` — **never inferred from `local_thesis_status`** (TR-P1) |
| `latest_attempt.ts` / `.run_id` / `.target_status` | the most recent attempt, accepted or not | RUNTIME | `app/decision_availability.py:536`; render `index.html:7301-7306` | ISO-8601 / string / string | yes | `Unavailable` |
| `latest_attempt_kind` | `accepted` / `accepted_with_error` / `failed` / `protective_carry` | RUNTIME | `app/decision_availability.py:537`; label map `index.html:7296-7301` | enum | yes | unknown → `Outcome unverified` / `结果未验证` (`index.html:7301`) — the map already has this fallback |
| `accepted_target.execution_evidence` | whether the target actually executed | ECON | `app/decision_availability.py:289-318` | enum `receipt_identity_verified\|not_settled\|unverified` | yes | `Execution evidence unavailable` — **never `executed`** |
| `accepted_target.fill_count` / `.settled_asof` / `.settlement_transaction_id` | the fills that happened | ECON | `app/decision_availability.py:313-317`; render `index.html:7309-7311` | int / date / string | yes | branch shows queued/unverified wording, not `0 fills` |
| `accepted_target.gross_exposure` | target gross | ECON | `app/decision_availability.py:296`; render `index.html:7307` | fraction | yes | `Unavailable` |
| `accepted_target.weights` | target weight per name (explicit actions) | ECON | `app/decision_availability.py:295`, `_weights()` `:271-288` | `{ticker: weight}`; fractions | yes | row omitted; `weights_status` is `unavailable` |
| `accepted_target.pending.status` | the queue's own state | ECON | `app/decision_availability.py:302-303`, `:335-357` | enum `none\|queued\|invalid\|unavailable` | no | `No pending target file observed` / `Pending target <status>` |
| `accepted_target.pending.queued_at` / `.asof` / `.lineage_status` / `.clock_status` | queue provenance and trust | ECON | `app/decision_availability.py:335-357`; render `index.html:7252-7261`, `:7269-7271` | ISO-8601 / status | yes | `Pending target timing is unverified.` for `clock_status:"invalid"` (`index.html:7330-7332`) |
| `account.status` | the account read's own status | ECON | `_account()` `app/decision_availability.py:160-232`; render `index.html:7272-7280` | enum `available\|partial\|invalid\|unavailable` | no | 7 explicit labels; unknown → `Account status unverified` |
| `account.cash` / `.position_count` | the account beside the decision | ECON | `app/decision_availability.py:170-175`, `:213`; render `index.html:7281-7282` | number / int | yes | `Unavailable` — this read does **not** coerce (`money()` returns a dash), which is correct |
| `account.valuation.{status,nav,invested,gross_exposure,cash_weight,price_date_from,price_date_through}` | the account's marked value | ECON | `app/decision_availability.py:164-166`, `:220-228`; render `index.html:7283-7290` | number / fraction / date | yes | the shipped sentence is explicit: `Valuation unavailable: quantities or qualified prices are incomplete.` — keep it |
| `account.valuation.missing_tickers[]` | which names block a qualified valuation | ECON | `app/decision_availability.py:208` | `string[]` | no — empty array | names each rendered, not a count-only |
| `account.last_recorded_nav.{nav,date}` | the last NAV ledger entry | ECON | `_recorded_nav()` `app/decision_availability.py:233-270`; render `index.html:7291-7293` | number / date | yes | row omitted when no entry exists |
| `consistency.status` / `.transaction` / `.changed_sources` | whether the account and decision were read coherently together | RUNTIME | `app/decision_availability.py:540-542`; render `index.html:7322-7330` | enum `observed_stable\|transaction_pending\|changed_during_read` / string[] | yes | `observed_stable` → no alert (correct) |
| `history_status` / `attempt_coverage` / `origin_lineage_status` | how complete the decision history is | RUNTIME | `app/decision_availability.py:532-534`; render `index.html:7243-7247`, `:7297` | enum | yes | `Decision history is incomplete or unavailable; the latest attempt may be missing.` |
| `expected_opportunity.status` | was today's run even scheduled | RUNTIME | `app/decision_availability.py:538` — **permanently `{"status":"unknown","reason":"scheduler_evidence_not_bound"}`** | enum | yes | the view must render `Unknown — the scheduler is not bound to this book`, never "no run was due". Part of `CONTRACT REQUEST → R1` |
| `issues[]` | machine-readable qualifications | RUNTIME | `app/decision_availability.py:543`; render `index.html:7251-7254`, `:7340` | `string[]` | no — empty array | empty → the qualifications list is omitted |
| `sources{file,status,sha256}` | source coverage and identities | RUNTIME | `app/decision_availability.py:541`; render `index.html:7316-7322` | object map | yes | status text is always printed (correct) |
| `settlement_price_inspection.*` | settlement-price evidence | ECON | `app/decision_availability.py:398-425`; render `_settlementPriceEvidenceHtml` `index.html:6629` | object; server default `{"status":"unavailable","reason":"receipt_inspection_unavailable"}` (`:403`) | no | that exact unavailable object renders as-is |
| `provider_diagnostic_inspection.*` | provider-diagnostics evidence | RUNTIME | `app/decision_availability.py:427-463`; render `index.html:7022-7100` | object; default `status:"unavailable"`, `provider_start:"not_proven"`, `effect_reconciliation:"not_performed"` (`:429`) | no | renders as-is |
| `summary` / `summary_zh` / `sold_note` | memo for **non-availability books** | RESEARCH | `app/web.py:1481-1499` (walks back to the last decision carrying a summary); banner `#auto-sum` | string | yes | `No decision yet — appears after the Brain's first run.` |
| `/api/decisions` `decisions[].asof` / `.today` | the Daily Decision Log | RUNTIME | `app/web.py:1708`; render `index.html:5088-5100` | date | yes | badge omitted |
| `decisions[].executed[].ticker/side/value/pct_of_position/realized_pnl/realized_pct` | explicit actions with realized P&L | ECON | `app/web.py:1723-1733` (FIFO backfill from `trade_history.sell_realized`) | string / string / number / fraction | yes | the whole line is not drawn — **not** a zero-valued line |
| `decisions[].execution_evidence_status` | `receipt_verified` / `legacy_unverified` / `none` | ECON | `app/web.py:1712-1721` — derived on every read, never trusted from the file | enum | yes | renders the qualifier beside the row |
| `decisions[].holdings[].rationale` / `_zh` | compact per-name rationale | RESEARCH | `app/web.py:1742-1747` | string | yes | line omitted (correct) |
| `/api/posture` `posture_label(_zh)` / `posture_tone` / `favored[]` / `avoided[]` / `driver` / `as_of` / `available` | the unchanged-book explanation's narrative half | RESEARCH | `app/web.py:1755-1775`; render `index.html:7664-7694` | string / enum / string[] / date / bool | yes | `available:false` → `No posture yet` / `Appears after the Brain's first run.` |
| **unchanged-book reason (structured)** | *why* the book did not change | RESEARCH | **not modelled anywhere** — today it is inferred from the memo plus `latest_attempt_kind` | enum `new_book\|no_fresh_evidence\|risk_hold\|protective_carry\|target_unchanged\|no_cash\|unavailable` + free text | yes | `Unavailable` — the view must not invent one from the memo. `CONTRACT REQUEST → S6` (new id) — `unchanged_reason {code, text(_zh), decision_id, asof}`; nullable; provenance the decision ledger's protective-carry/hold branch; needed by V2 and V7; displays `Unavailable` until shipped |
| `decision-snapshot inspector` | raw decision snapshot | RUNTIME | **#1357's operator-gated surface only**, per CR-R6 | object | yes | **never drawn for an anonymous viewer**; the affordance is absent, not disabled |

#### Layout

**1280.** 1. Chrome. 2. **Answer block** — outcome word · last valid decision stamp · the accepted
memo's ≤14-word clause · the account's NAV beside it · page stamp. 3. Attempt alert row (failed /
accepted-with-error / protective-carry / inconsistent read) — support-1. 4. Explicit actions:
accepted-target weights + executed fills — support-2. 5. Horizon + invalidation. 6.
Unchanged-book explanation. 7. Per-name thesis/plan status slots (TR-P1). 8. Qualifications
(`issues[]`) disclosure. 9. Settlement-price evidence table → provider diagnostics → source
coverage. 10. Daily Decision Log. 11. Posture chip + playbook.

**768.** Answer block full width; actions and horizon side by side in two columns of six; the
evidence tables stay full width with internal scroll.

**375.** Answer (outcome word → stamp → clause → account NAV → page stamp, stacked), attempt
alert, actions list capped at 4 with `See all N`, horizon/invalidation inside one disclosure whose
summary names the check-by date, the unchanged-book explanation, then the decision log capped at
3. Both evidence tables move behind the operator landing; **the provider-diagnostics and
settlement-price tables are Tier 3 and never appear above the fold at any width.**

Demoted landings: settlement-price evidence and provider diagnostics → the **V7 Operations**
operator surface; the Daily Decision Log's older rows → its own `See all N`; the playbook → its
disclosure. Nothing is deleted for space.

#### States

**loading.** Trigger: `_decisionAvailabilityPending` is true with no payload
(`index.html:7421-7426`). EN `Loading` · ZH `加载中`. Treatment: skeleton at final geometry across
the answer block and the two evidence tables; the shipped `Reading this book's recorded decisions
and account…` sentence (`index.html:7424`) is a placeholder sentence and is replaced by the
skeleton. Still works: chrome, book switcher, and V1's already-painted account.

**empty.** Trigger: `last_valid_decision === null` **and** `history_status === "available"` — the
Brain genuinely has no accepted decision yet. EN `Empty — no decision has been accepted for this
book yet. The next daily run produces the first one.` ZH `暂无 — 本账本尚未接受任何决策。下次每日
运行将产生第一条。` Treatment: full-weight sentence; the **account block beside it still renders
in full**, because an empty decision log is not an empty book. The shipped wording for
non-availability books is the model (`app/web.py:1481-1499`). Still works: cash, positions, NAV,
allocation, the session clock.

**stale.** Trigger: `last_valid_decision.ts` older than the book's expected cadence, or
`consistency.status === "changed_during_read"` (sources moved mid-read —
`app/decision_availability.py:514-524`). EN `Behind` + the last settled stamp · ZH `滞后` +
最近结算时间戳. Treatment: `--muted` label with the stamp inline, plus the shipped coherence note
`Sources changed during the read; account reconciliation is provisional.` (`index.html:7324-7325`).
Still works: the decision and the account as read — both are real observations; only their joint
currency is behind. **Stale is never used for a failed attempt**; that is the `failed` outcome
word, which is a different fact.

**partial.** Trigger: top-level `status === "partial"`, or `history_status !== "available"`, or
`attempt_coverage !== "complete"`, or `account.status === "partial"`. EN `Partial — the latest
attempt is missing, so the decision shown may not be today's.` ZH `部分 — 缺少最近一次尝试，所
展示的决策可能不是今天的。` Treatment: `--muted` chip naming **what is excluded** — never a partial
figure rendered as a complete one. The shipped sentences are the model (`index.html:7328-7329`,
`:7243-7247`). Still works: the accepted decision and its account, each labelled for what is
missing.

**error.** Trigger: `portfolio_id` mismatch, or the read itself fails. EN `Couldn't load the
decision record. The account, holdings and performance in Portfolio overview still work.` +
`Retry` · ZH `加载决策记录失败。组合总览中的账户、持仓与业绩仍可用。` + `重试`. Treatment: `--warn`
label ink on the word only, quiet `--panel2` fill, even neutral `--line` border; the identity
mismatch case renders **no numbers at all** (the shipped behaviour at `index.html:7267-7268`).
Still works: V1 in full, because V1 does not source from this read. **No fabricated decision,
target or account is ever drawn in this state** — the `Outcome unverified` fallback of the kind
map (`index.html:7301`) is a *label for an unknown outcome*, not a substitute for a read.

**closed-market.** Trigger: `session.is_open === false`. EN `Market closed — next open
2026-10-22 09:30 ET` · ZH `休市 — 下次开盘 2026-10-22 09:30 ET`. Treatment: `--muted`, static. This
state matters more on V2 than on V1 because an accepted target fills **at the open**: with the
market closed, a queued target is queued-and-waiting, and the view says so in the actions block
rather than in a warning. Still works: every decision field, unchanged.

**benchmark-unavailable.** **n/a for the primary answer** — V2 renders no benchmark comparison;
a return difference belongs to V4 and V1. The one place V2 can meet it is the Daily Decision Log's
per-day context, and the rule applies there: when A12 returns `status:"unsupported"` that slot
renders `Benchmark unavailable` / `基准不可用` rather than `0.00%` or a dash. No other V2 slot is
benchmark-bearing.

**provisional valuation.** Trigger: `account.valuation.status === "provisional"` — at least one
held line lacks a qualified price (`app/decision_availability.py:220-228`). EN `Provisional` /
ZH `暂定`, with `account.valuation.missing_tickers[]` named in the same sentence: `Provisional —
AAPL and MU are priced from an earlier close.` Treatment: the account NAV beside the decision
takes `--muted` ink beside a `Provisional` chip; the decision itself is unaffected, because a
qualified decision and a provisional account valuation are independent facts. Still works: the
accepted target, the weights, the executed fills, the qualification sentence.

**queued vs held.** Trigger: `accepted_target.pending.status === "queued"` — an accepted,
validated, unfilled target exists. EN `Queued` / `已排队` chip on the actions block, with the
queue's own `queued_at` and its clock words; for a **held** name carrying a queued exit the chip
is V1's `EXIT QUEUED` / `已排队卖出` row chip (`pos.q_exit`, `index.html:3450`) and V2 links to that
row rather than redrawing it. Two rules bind here: (a) `clock_status === "invalid"` renders
`Pending target timing is unverified.` (`index.html:7330-7332`) — a queued target with an
unverified clock never states a fill time; (b) `issues[]` containing
`queued_decision_without_pending_target` renders `The decision journal says queued, but no pending
target was observed.` (`index.html:7336-7337`), which is a **disagreement between two records**,
not a queue. Still works: the account, which is settled and separate — the shipped copy says
exactly this (`index.html:7306-7307`).

**TR-P1 — plan and thesis are separate slots** (RESEARCH CR-R2; binding on V2 and V6). Neither
field exists today, so both slots currently render `Unavailable` / `不可用`. The rules:

- `provider_plan_status` and `local_thesis_status` are **two independent slots**. Neither is
  inferred from the other, and neither is inferred from `positions[].verdict`, from a decision's
  existence, or from the absence of a queued action.
- `held_without_active_plan` renders **`no active provider plan`** / `无有效的提供方计划` — **never**
  `no thesis`.
- The words `no thesis` / `无投资论点` are **reserved** for `local_thesis_status === "absent"`.
  Nothing else in the product may render them.
- Each slot renders `Unavailable` independently until its field ships, so a partial delivery (one
  field, not the other) yields one honest word and one unavailable word — never a guess.
- A held name with a present thesis and an absent plan renders **both words side by side**:
  `Thesis: <summary>` + `no active provider plan`. That combination is normal and must not be
  compressed into a single status.

#### EN / ZH

| Concept | EN | ZH | Cite |
|---|---|---|---|
| View title | Manager decision | 经理决策 | new |
| Section title (today) | Decision and account status | 决策与账户状态 | static `index.html:2724` |
| Outcome — accepted | Accepted | 已接受 | `index.html:7297` |
| Outcome — accepted with error | Accepted with an attempt error | 已接受，但尝试存在错误 | `index.html:7298` |
| Outcome — failed | Failed · no accepted decision | 失败 · 未接受决策 | `index.html:7299` |
| Outcome — protective carry | Protective carry recorded | 已记录保护性延续 | `index.html:7300` |
| Outcome — unknown | Outcome unverified | 结果未验证 | `index.html:7301` |
| Outcome — unavailable | Unavailable | 不可用 | `say()` `index.html:7295` |
| Attempt failed alert | Latest recorded decision attempt failed | 最近记录的决策尝试失败 | `index.html:7303` |
| Protective freeze | Protective freeze recorded | 已记录保护性冻结 | `index.html:7311` |
| No valid origin | No valid originating decision could be established | 尚无法确认有效的原始决策 | `index.html:7317` |
| Valuation unavailable | Valuation unavailable: quantities or qualified prices are incomplete. | 估值不可用：数量或合格价格不完整。 | `index.html:7283-7290` |
| Queue timing unverified | Pending target timing is unverified. | 待执行目标的时间未经验证。 | `index.html:7331` |
| Journal/queue disagreement | The decision journal says queued, but no pending target was observed. | 决策日志标记为排队，但未发现待执行目标。 | `index.html:7337` |
| Horizon | Horizon | 期限 | new (S5) |
| Review by | Review by | 复核日期 | new (S5) |
| Would prove wrong | Would prove wrong | 证伪条件 | new (S5); free-text source is `thesis_full.what_would_prove_wrong` |
| No active provider plan | no active provider plan | 无有效的提供方计划 | new (TR-P1) |
| No thesis | no thesis | 无投资论点 | **reserved for `local_thesis_status = absent` only** |
| No decision yet | No decision yet — appears after the Brain's first run. | 尚无决策 — 大脑首次运行后出现。 | `app/web.py:1481-1499` |
| Strategy posture | Strategy posture | 策略姿态 | render `index.html:7664-7694` |

The Daily Decision Log, settlement-price evidence and provider-diagnostics copy already exists in
both languages inside `_decisionAvailabilityHtml` via its local `say(en, zh)`
(`index.html:7268`) and the two evidence helpers (`:6629`, `:7022`); those are reused verbatim, not
retranslated.

#### Accessibility

- **Contrast pairs**: `--text` on `--panel` for the outcome word and the memo clause; `--muted` on
  `--panel` for every detail line (`index.html:6634-6635` region) and for source-coverage text at
  small sizes; `--warn`/`--act` on `--panel2` for the failed / accepted-with-error alerts — these
  are **text** surfaces, so ≥4.5:1; `--ok` for `observed_stable` where a healthy state is named in
  words.
- **Focus order**: chrome → answer block (prose; not focusable) → attempt alert (focusable if it
  contains the `Retry` control) → actions list rows → horizon disclosure → unchanged-book
  explanation → TR-P1 status slots → qualifications disclosure → evidence tables (internal scroll,
  focus must not be clipped) → decision-log rows → posture chip → playbook disclosure.
- **Keyboard / touch**: every Tier 2/Tier 3 element is a native `<details>` or a `<button>`. The
  posture playbook is currently hover-driven (`index.html:7664-7694`) — **that is hover-only and
  noncompliant**; it must open on focus and on tap. The decision-snapshot inspector affordance is
  a link and is only rendered for an operator (CR-R6).
- **Reduced motion**: no motion on this view beyond the shared live dot rule; the outcome word
  does not animate when it changes. The playbook popover must not animate in under
  `prefers-reduced-motion`.
- **Announcements**: `#decision-availability` already carries `aria-live="polite"`
  (`index.html:2723`) — it keeps it. The announcement must be the **outcome word and its stamp**,
  not the whole re-rendered panel, because the panel re-renders on every poll.
- **Zoom**: at 200% the actions list becomes a stacked two-line row (`DS_components.md`
  DecisionRow) and the evidence tables scroll internally.

#### Density

- **Above-fold budget**: chrome + answer + attempt alert + actions. Horizon, invalidation and the
  unchanged-book explanation are Tier 2 and sit below.
- **Row caps**: actions list ≤ 8 names then `See all N`; Daily Decision Log ≤ 8 rows then
  `See all N decisions`; executed fills ≤ 8 per decision.
- **Never at Tier 1**: the settlement-price evidence table; the provider-diagnostics panel; source
  file names and `sha256` values; `issues[]` raw codes; `weights_status`; the run id.
- **One canonical integer per population**: the holdings count in the submitted target
  (`submitted_holding_count`). The actions list shows weights, not a second count.
- **Redundancy rule**: the account NAV shown beside the decision is the same figure V1's answer
  block shows. V2 shows it because the comparison *is* the point (intent vs reality), but it never
  also shows the sleeve bar or the risk score.

#### Truth rules

1. **"A natural-language explanation cannot overrule the actual account."** This is V2's
   primary obligation, because V2 is the view that carries narrative. The memo, the posture, the
   per-name rationale and the playbook are rendered **beneath** the account and the accepted
   target, and where a memo sentence and `account.json` disagree the account is drawn. A
   `protective_carry` explicitly states that the account and the pending target remain separate
   observations (`index.html:7315-7316`) — that sentence is binding, not flavour.
2. **"A queued MU exit must show as a pending change while MU is still held."** V2's half: a
   queued exit appears in the actions block with the `Queued` state and links to V1's held row;
   V2 never renders it as *executed* until `execution_evidence` is `receipt_identity_verified`
   and `fill_count` is non-null.
3. **"An unavailable benchmark displays unavailable rather than zero."** Applies only to the Daily
   Decision Log's per-day comparison slot, as written in States.
4. **"Do not visually reward a missing-price flat line as low volatility or a tiny closed-position
   sample as a winning strategy."** V2's half: an outcome word is never decorated. A `failed`
   attempt gets the same weight as an `accepted` one; no confetti, no colour burst, no green panel
   for an accepted-but-empty target. Where a decision produced **no change**, the view says the
   book was unchanged and why — it never renders a successful-looking empty state.

Seat-accepted requirements on V2:

- **TR-P1** as specified in States: separate `provider_plan_status` and `local_thesis_status`
  slots; `held_without_active_plan` renders `no active provider plan`, never `no thesis`;
  `no thesis` is reserved for `local_thesis_status = absent`; each slot renders `Unavailable`
  independently until its field ships; neither is inferred from the other.
- **An unavailable field renders the word, never a substitute.** `execution_evidence`,
  `fill_count`, `settled_asof` and `settlement_transaction_id` each render `Unavailable` — not
  `0 fills`, not an empty object, not `executed`.
- **Missing never coerces to zero** wherever this view renders counts.
- **The decision-snapshot inspector is #1357's surface only** (CR-R6): operator-gated on
  `app.auth.is_operator_authorized`, denied by `app/response_cache.py`, CSP-hardened static
  shell. **Never drawn for an anonymous viewer** — the affordance is absent, not disabled — and
  #673's inline `app/web.py` handler must not ship whichever lands first. Required tests stay
  `test_operator_auth_required_on_every_read`,
  `test_endpoint_excluded_from_shared_response_cache`, `test_no_second_route_registered`.
- **A win rate is never shown on V2** without its `n` and the ≥30 minimum-n gate (V1's rule),
  because the Daily Decision Log is where a reader would otherwise meet one.

#### Acceptance checklist

1. **API/DOM agreement** — every outcome word, stamp, weight and executed line in the rendered
   decision panel equals `/api/portfolio?view=decision_availability` character for character, and
   the Daily Decision Log lines equal `/api/decisions`. *Test: DOM-extraction diff against
   fixtures.*
2. **Identity gate** — with a fixture whose `portfolio_id` differs from the active book, the panel
   renders `Decision status unavailable` / `决策状态不可用` and contains **no digits from the payload**.
   *Test: DOM assertion that no numeric payload value appears.*
3. **Book gate** — with `self_directed` active, `#decision-availability` is not rendered
   (`_isAvailabilityBook`, `index.html:6620-6622`; `ACTIVE_BOOKS`,
   `app/decision_availability.py:20`); with `autonomous` active it is. *Test: DOM fixture per
   book.*
4. **TR-P1** — with a fixture carrying `provider_plan_status:"held_without_active_plan"` and
   `local_thesis_status:"absent"`, the two slots render `no active provider plan` / `无有效的提供方
   计划` and `no thesis` / `无投资论点` respectively, in **separate** elements. With
   `provider_plan_status` present but `local_thesis_status` absent from the payload, the thesis slot
   renders `Unavailable` and the plan slot still renders its own value. **The string `no thesis`
   never appears when `local_thesis_status !== "absent"`** — asserted directly. *Test: unit plus DOM.*
5. **Failed attempt is the answer** — with `latest_attempt_kind:"failed"`, the outcome word is
   `Failed · no accepted decision` / `失败 · 未接受决策`, the shipped alert renders
   (`index.html:7304-7308`), and the last valid decision is still shown beneath it, clearly labelled
   as the last valid intent rather than as current. *Test: DOM fixture.*
6. **Unknown outcome** — with `latest_attempt_kind` absent or unrecognised, the word is `Outcome
   unverified` / `结果未验证` and **never** `Accepted`. *Test: unit over the label map.*
7. **Horizon/invalidation** — with no S5 payload the two rows render `Unavailable`; with an S5
   fixture they render `horizon_end` as a date-only value and the review condition verbatim, and
   the horizon is **never** derived from `held_days`. *Test: DOM fixtures + a unit assertion that
   holding-age derivation does not occur.*
8. **Queued vs settled** — with `accepted_target.pending.status:"queued"`, the actions block shows
   the `Queued` chip and **not** an executed line; with
   `execution_evidence:"receipt_identity_verified"` and a non-null `fill_count`, the executed line
   appears. *Test: two DOM fixtures.*
9. **Unverified clock** — with `pending.clock_status:"invalid"`, no fill time is rendered anywhere
   in the panel. *Test: DOM assertion on the absence of a timestamp in the actions block.*
10. **Record disagreement** — with `issues[]` containing
    `queued_decision_without_pending_target`, the disagreement sentence renders and **no**
    `Queued` chip renders. *Test: DOM fixture.*
11. **Unavailable slots** — with `execution_evidence`, `fill_count`, `settled_asof` and
    `settlement_transaction_id` all null, each renders `Unavailable` and the DOM contains no `0
    fills`, no empty object and no `executed`. *Test: DOM assertion.*
12. **Operator gate** — the decision-snapshot inspector affordance is absent for an anonymous
    session and present for an operator session; the anonymous DOM contains no link to it and the
    endpoint is cache-denied. *Test: the two required CR-R6 unit tests plus a two-session DOM
    check.*
13. **States** — loading, empty, partial, error and closed-market each draw their exact sentence;
    the error state renders `Retry` and no fabricated decision or account. *Test: browser
    screenshots at 375 and 1280, EN and ZH, five states.*
14. **Breakpoints** — module order matches Layout at 375/768/1280; the evidence tables never appear
    above the fold at any width; no page-level horizontal scroll. *Test: browser screenshots.*
15. **EN/ZH** — every row of the EN/ZH table above renders in its language with no leak; the
    outcome words stay words, not status slugs (`DS_foundations.md` Tier 1 avoids internal state
    slugs). *Test: screenshot pair + DOM scan.*
16. **A11y** — exactly one `h1`; the posture playbook opens on focus and tap (the hover-only path
    is closed); every disclosure is keyboard-operable; the polite live region announces the outcome
    word and not the whole panel. *Test: axe pass + keyboard walkthrough.*
17. **No celebration** — with an accepted-but-unchanged target, the outcome word carries no colour
    burst, no motion and no "great"/"success" copy; with a tiny closed sample no win rate is drawn.
    *Test: DOM snapshot comparison against the accepted-changed render.*

### V3 Pending activity

#### Question

What is queued, when does it become eligible to settle, and what has already happened
to it? (MASTERPLAN §10.2 Q3, `Pending activity`.) V3 never answers "what should we hold" — that is
V2; it answers "what has the manager already accepted that has not yet touched the account".

#### Archetype

**G (Monitor)** as the product shell (§2 Art direction, item 2), composed with the
canonical **Lifecycle rail** (DS `.mx-rail`; no app class ships — `DESIGN-SYSTEM-GAP G6: lifecycle rail`, §8) as the identity device for the one queued target's
chronology — drawn "by weight/surface, not colorful goodness", with historical stages
non-actionable. Not A: there is no multi-event change ledger to triage, a queue is one target's
life. Not C: there is no thesis/evidence/task tabset to browse.

#### Information hierarchy

| Tier | Content |
|---|---|
| **Tier 1** | The queue answer: verdict word (`Queued` / `Empty`), the count of actionable queued rows, the next eligible session, one freshness stamp. Nothing else above the fold. |
| **Tier 2** | (1) the actionable queued-order rows (`pending[]` after `pending_target.rows[]` promotion); (2) target identity strip — `queued_at`, target `asof`, `schema_version`, `engine_version`; (3) the truth notice when `comparison_status` or `status` is degraded. |
| **Tier 3** | The full audit table (`pending_target.rows[]` including `hold` / `filtered` / `unpriceable` / `blocked` / `comparison_unavailable` and `suppressed_by`); market-calendar detail; the target's lifecycle rail; per-row exit rationale (S3); expiry / supersession / final disposition (E9). |

#### Fields

| Field | Meaning | Owner | Source today | Type / units | Nullable | Display when null / unknown |
|---|---|---|---|---|---|---|
| `pending_target.status` | whether a complete desired book is queued | ECON | `/api/trades` `pending_target.status` (`app/web.py:2044-2053`) | enum `queued\|none\|invalid\|unavailable` | no | `none` → **Empty**; `invalid` / `unavailable` → their own truth notice (`index.html:3299-3300`) |
| `pending_target.rows[]` | full audit rows, incl. carries and filters | ECON | `app/web.py:2143-2220`; rendered `index.html:5031-5068` | array | never absent once `status:"queued"` | `[]` with `status:"queued"` → **Partial**, naming the target id |
| `rows[].action` | projected direction for that name | ECON | `app/web.py:2148-2199` | enum `exit\|trim\|add\|buy\|hold\|filtered\|unpriceable\|blocked\|comparison_unavailable` | no | `hold` / `filtered` are audit-only; never promoted to an order row |
| `rows[].side` | executable side | ECON | `app/web.py:2201-2222` (`side in {buy,sell}` → `pending[]`) | `buy\|sell\|hold\|null` | nullable | `null` → the row is audit-only; `_pendingOrderSide` (`index.html:5006-5013`) must **not** be allowed to fall back to BUY for a target row — its legacy BUY fallback is a V7 truth fix, not a V3 rule |
| `rows[].suppressed_by` | why an action did not become an order | ECON | `app/web.py:2171`, `:2183`, `:2190` | `no_trade_band\|buy_dust\|missing_price\|missing_exit_price` | nullable | absent → no suppression sentence |
| `rows[].current_weight` / `.target_weight` | weight comparison behind the action | ECON | `app/web.py:2207-2210` | fraction 0–1 | `current_weight` nullable when prices unavailable | `null` → the audit row drops the weight columns; the action still renders |
| `pending_target.comparison_status` | whether the target can be compared to the account | ECON | `app/web.py:2075-2086`; `index.html:5022-5028` | enum `current_weights_available\|prices_unavailable\|account_unavailable\|constraint_snapshot_mismatch\|transaction_pending` | nullable when not computed | absent → no notice drawn |
| `pending_target.fill_after` | the session the queue is projected to fill at | ECON (value) / RUNTIME (source) | `app/web.py:2064-2066` — set from `market_status.next_open` | ISO-8601 with offset | nullable | `null` → `awaiting settlement` (`index.html:3294`) |
| `next_eligible_session{session_open_at, market, reason}` | the **book's** eligible session, which is not the market's next open | RUNTIME | **CONTRACT REQUEST → R2** | object; ISO-8601 with offset | whole object null when not queued | **Unavailable** — never substituted by `market.next_open` in the label |
| `pending_target.queued_at` / `.asof` / `.schema_version` / `.engine_version` | target provenance | ECON | `app/web.py:2060-2063`, `:2216-2218` | ISO-8601 / string | each null until known | absent → the identity strip shows only what arrived; never a fabricated version |
| `pending_target.expires_at` | when this queued target stops being actionable | ECON | **CONTRACT REQUEST → E9** | ISO-8601 UTC | null until known; never absent | **Unavailable**; never inferred from the target's age |
| `pending_target.superseded_by` | the target identity that replaced this one | ECON | **CONTRACT REQUEST → E9** | string (target/decision id) | null when not superseded | **Unavailable** — never renamed from `constraint_snapshot_mismatch` |
| `final_disposition` / `disposition_at` / `receipt_id` | how the target ended: `filled\|partially_filled\|expired\|superseded\|rejected` | ECON | **CONTRACT REQUEST → E9** | enum / ISO-8601 / string | each null until known; never absent | **Unavailable** |
| exit rationale `{ticker, decision_id, exit_reason_code, narrative, asof}` | why a queued exit exists | RESEARCH | **CONTRACT REQUEST → S3** | object | null → the row shows the exit is queued **without** a rationale | row shows `no rationale recorded`; never invents one, and never lets it overrule the account |
| `snapshot_status` | whether the read is coherent | RUNTIME | `app/web.py:2291-2292`, `:2383` | enum `coherent\|account_unavailable\|transaction_pending` | no | `transaction_pending` → empty arrays plus the transaction notice (`index.html:3302`); never a partial mix |
| `market{is_open, session, next_open}` | exchange clock for the venue | RUNTIME | `app/web.py:2354-2361` (`market_calendar` / `china_calendar`) | object | `{}` on the failure path | the closed-market strip is omitted, never guessed |
| `pending[]` (Self-Directed) | the user's own paper orders | ECON | `/api/self_directed` `pending[]` (`portfolio/self_directed.py:616-700`; render `index.html:6214-6233`) | array of `{ticker,side,shares,notional,est_value,est_shares,order_id}` | empty array → the block is not rendered | — |
| held-row queued chip | the #1707 cross-view rule: a lot we **still hold** that a queued target names | PRODUCT (render), ECON (source) | `_heldPendingChange` (`index.html:4717-4780`), keys `pos.q_exit` / `pos.q_trim` / `pos.q_add` / `pos.q_unclassified` (`index.html:3450-3453`), class `.mm-q-when` (`index.html:353`) | enum `exit\|trim\|add\|unclassified` + `data-queued-change` on the row (`index.html:4839`) | null when the queue does not name the lot | the lot's normal verdict chip is restored, unchanged |

#### Layout

| Breakpoint | Modules, in order |
|---|---|
| **1280** | 1. Verdict block (VerdictHero anatomy, bound per §3 Tokens to the `.panel` surface + `.mm-perf-stat-value` figure): `Queued` / `Empty`, the actionable-row count, next eligible session, one freshness stamp. 2. Support-1: queued order rows, `.mm-table-wrap` table, L1 ≤ 8 rows then counted `See all N`. 3. Support-2: the lifecycle rail (G6) for the target's life. 4. Tier-3 band: target identity strip; audit table `pending_target.rows[]` in a `<details class="mm-da-foot">` whose summary names what is inside and why one would open it. |
| **768** | Same four modules; the rail moves above the audit disclosure; the order table keeps 4 columns (name · action · est. price · settlement) with `mm-hide-sm` columns demoted to the row's audit landing. No column is deleted — §3 Shared rules, Density. |
| **375** | 1. Verdict block. 2. One queued row as a card (name · action chip · settlement line), each opening V6 for that holding. 3. The rail. 4. **Named landing**: `See all N queued changes` → the audit table as its own route. The identity strip, `suppressed_by` detail and the `no trade band / dust` mechanics are inside that landing, never removed. The page must not scroll horizontally; the table scrolls inside its own container. |

#### States

Each row gives the field-level trigger, the copy (the EN of the pair printed in **EN/ZH**
below), the treatment and what still works.

| State | Trigger (field-level) | Copy + treatment | What still works |
|---|---|---|---|
| **Loading** | `/api/trades` in flight | Skeleton at final geometry — verdict block, one row, rail stub. No prose. `t('rej.loading')`-style "Loading…" prose is **not** allowed in V3's own blocks. | Navigation, book switch, the last settled panel behind the skeleton. |
| **Empty** | `pending_target.status:"none"` and `pending[]` empty | `Empty` / `暂无` + the mandatory reason: `Empty — nothing is accepted and waiting to settle.` / `暂无 — 没有已接受、待结算的订单。` Copy request: replaces the shipped `pend.none` string `No orders queued.` / `暂无挂单。` (`index.html:3297`). Rendered at full weight. Queued-orders block is replaced, not zero-height. | V1, V2, V4, V6, V7. |
| **Stale** | the panel's as-of is behind the session clock | `Behind` + the last settled as-of stamp (§3 vocabulary). The stamp is the panel's own; it never borrows V1's. | Everything, with the staleness labelled. |
| **Partial** | `status:"queued"` with `rows:[]`; `comparison_status:"prices_unavailable"` or `"account_unavailable"`; `snapshot_status:"transaction_pending"` | The exact per-state sentences already shipped at `index.html:3301-3302` — "Target is queued, but the account snapshot is unavailable, so no buy or sell direction is inferred." / "Account settlement is in progress. Trade history is withheld until one coherent snapshot is available." Treatment: quiet `.mm-pend-alert` fill + even neutral border, labelled status ink; never a coloured container edge (`DS_states-accessibility.md`). | The queue identity, `queued_at`, and the held-row chips for names whose direction is already classified. |
| **Error** | `pending_target.status:"unavailable"` or the endpoint's `error` | `Couldn't load` + what failed + what still works + a lawful retry. Copy: "Queued-target status is temporarily unavailable. No execution is being claimed." (`index.html:3300`). **No queue is claimed, and no row is drawn.** | V1/V4/V6 for the same book; the retry re-reads `/api/trades` only. |
| **Closed-market** | `market.is_open === false` | `Market closed` + the next open time (non-colour cue: the word plus a timestamp). The settlement column reads `at open <date>` from `fill_after`, or `awaiting settlement` (`index.html:3293-3294`). | Everything; the queue is still queued. |
| **Queued (pending while held)** | `pending_target.status:"queued"` **and** `rows[]` names a ticker the account still holds | See the dedicated rule below. | — |
| **Unavailable** | any E9 / R2 slot without a value | The word `Unavailable` / `不可用`, muted, in the value slot — never a dash alone, never a zero, never an inferred date. | Every other slot. |
| **Benchmark-unavailable** | n/a — V3 renders no benchmark. | — | — |
| **Provisional valuation** | n/a — V3 renders no valuation. | — | — |

**The queued-vs-held rule (binding, consistent with merged #1707).**

`_heldPendingChange` (`index.html:4717-4780`) is the whole rule, and V3 states it rather than
re-derives it: when a queued target names a lot the account **still holds**, that lot's verdict cell
reads `EXIT QUEUED` / `TRIM QUEUED` / `ADD QUEUED` / `CHANGE QUEUED` (keys `pos.q_exit`,
`pos.q_trim`, `pos.q_add`, `pos.q_unclassified`, `index.html:3450-3453`) on chip classes `exit_pending`
/ `trim` / `add` / `hold`, with a wrapping muted timing line in `.mm-q-when` reading `at open <date>`
or `awaiting settlement`, and the row carries `data-queued-change="exit|trim|add|unclassified"`.

1. **Only `status:"queued"` is intent.** `invalid` / `unavailable` / `none` are fail-closed reads
   with no executable rows and must never appear as a queued change (`index.html:4731-4733`).
2. **Only the verdict cell changes.** Shares, marks, P&L, weight, sleeve, held date and the thesis
   row stay exactly as they are, because nothing is filled until the next open
   (`index.html:4827-4830`). V3's order row and the held row are therefore the *same* economic fact
   in two places; neither may show a direction the other lacks.
3. **No inferred direction.** `unpriceable` and `comparison_unavailable` map to `unclassified` →
   `CHANGE QUEUED` / `已排队调整`; `hold`, `blocked`, `buy` and `filtered` return null (a carry or a
   filter, not a change to a held lot) — `index.html:4744-4756`.
4. **`data-queued-change` is the testable hook.** A DOM-agreement test asserts: for every
   `pending_target.rows[]` entry whose ticker is in `positions[]`, the rendered row carries
   `data-queued-change` matching the action class; and for every row **not** named by the queue, no
   `data-queued-change` attribute is present.

##### What the row shows at each lifecycle event

Three of the four depend on E9; until E9 ships the
spec requires the honest degraded rendering, never the inferred one.

| Event | Requirement | Until E9 ships |
|---|---|---|
| **After the fill** | The queue is discharged. The queued chip disappears from the held row in the same read that the account no longer holds the lot (exit) or its share count reflects the fill (trim/add). The fill appears in Trade History with its recorded price; estimates never survive the fill — `pend.est_note` (`index.html:3298`) already scopes `est_price`/`est_value` to the pre-fill window. V3 keeps a **disposition row** in Tier 3 recording `final_disposition: filled` with `disposition_at` and `receipt_id`. | The chip clears correctly because it is derived from the queue read; the disposition row renders `Unavailable`. V3 must not narrate a fill it cannot cite. |
| **After an expiry** | The queue entry is removed by the expiry, not by settlement. V3 keeps the target identity and renders `Expired` with `expires_at`, `disposition_at` and — when it exists — the receipt. An expired target is **not** a rejection and carries no loss/gain figure. | `expires_at` is `Unavailable`. If the entry vanished with no disposition record, V3 renders **Partial** naming the target identity and the date it stopped being queued, and must not write "expired", "cancelled" or "rejected". |
| **After a supersession** | A newer accepted target replaces this one. V3 renders the superseded target as a completed rail stage (non-actionable, weight/surface only) with `superseded_by` naming the successor target identity and both `queued_at` values. | `superseded_by` is `Unavailable`. The only observable signal today is `comparison_status:"constraint_snapshot_mismatch"` — whose shipped copy is "Target is queued, but its protected account snapshot no longer matches. No action is projected." (`index.html:3304`). That is a **mismatch, not a supersession**; V3 must not rename it. |
| **After a rejection** | The target failed validation or the cycle that produced it was rejected. V3 renders `Rejected` with `final_disposition: rejected` and `disposition_at`, keeps the target visible for operator review, and never renders an order row for it. | `final_disposition` is `Unavailable`. A target that fails validation renders `status:"invalid"` with the existing copy "Queued target is invalid and cannot execute. It remains visible for operator review." (`index.html:3299`, error tone at `index.html:5023`). V3 must not assert *why* it was rejected beyond that sentence. RUNTIME's per-cycle `rejected` disposition (RUNTIME #1711) is a **different** fact about a different cycle and belongs to V7. |

#### EN / ZH

V3 reuses the shipped strings where they exist and marks the ones it must add. ZH drops
forced uppercase and English tracking (`DS_states-accessibility.md` §ZH semantics); a ZH label is
not a transliteration of the EN string.

| Element | EN (existing today) | ZH (existing today) |
|---|---|---|
| Panel title | `Pending activity` | `待处理活动` |
| Verdict word (queued) | `Queued` (§3 vocabulary; chip `pend.status` = `PENDING` / `待成交`, `index.html:3296`) | `已排队` |
| Order block title | `Pending Orders` (`index.html:3288`) | `待成交订单` |
| Block subtitle | `Queued for deterministic settlement — not yet in Positions or Trade History` (`index.html:3289`) | `等待确定性结算 — 尚未计入持仓或交易历史` |
| Side chips | `Buy` / `Sell` / `Hold` (`trades.buy/sell/hold`) | `买入` / `卖出` / `持有` |
| Settlement | `at open <date>` · `awaiting settlement` · `no trade required` (`index.html:3293-3295`) | `开盘 <日期>` · `等待结算` · `无需交易` |
| Estimate columns | `Est. Price` / `Est. Value` (`pend.est_px` / `pend.est_val`) | `预估价格` / `预估金额` |
| Estimates footnote | `Any estimates use the previous close. Actual prices appear only after a recorded fill.` (`index.html:3298`) | `预估值采用上一收盘价；只有记录成交后才会显示实际价格。` |
| Queued-on-held chips | `EXIT QUEUED` / `TRIM QUEUED` / `ADD QUEUED` / `CHANGE QUEUED` (`index.html:3450-3453`) | `已排队卖出` / `已排队减仓` / `已排队加仓` / `已排队调整` |
| Empty | `Empty — nothing is accepted and waiting to settle.` (copy request; replaces shipped `pend.none` `No orders queued.`, `index.html:3297`) | `暂无 — 没有已接受、待结算的订单。` |
| Degraded | the six `pend.*` sentences at `index.html:3299-3304` | shipped pairs at the same lines |
| NEW — expiry / supersession | `Expires` · `Superseded by <target id>` | `有效期至` · `被 <目标编号> 取代` |
| NEW — disposition / none yet | `Filled` / `Partly filled` / `Expired` / `Superseded` / `Rejected` · `No disposition recorded` | `已成交` / `部分成交` / `已过期` / `已被取代` / `已拒绝` · `暂无处置记录` |

`EXIT QUEUED` and `TRIM QUEUED` keep EN caps because they are chip labels matching the existing
`pos.v_*` chip family; their ZH labels are caps-free and native-shaped.

#### Accessibility

- Contrast: chip text is `--text` on a `color-mix` of `--panel2` with `--down`
  (`.mm-verdict-chip.exit_pending`, `index.html:348`), clear of 4.5:1 at the 11–12 px label;
  `.mm-q-when` is `--muted` on `--panel` (`theme.css:17`, `:47`), clear of 4.5:1 in both themes and
  languages — `--muted` is the only permitted muted role here.
- Focus order: verdict block → queued rows (each a link to V6) → non-actionable rail stages → the
  audit `<details class="mm-da-foot">` summary → `See all N`. Every Tier-2/3 disclosure opens by
  **keyboard and touch**, never hover only (`DS_states-accessibility.md`).
- `:focus-visible` is `--focus-ring` (`theme.css:29`) at 2 px and `.mm-pend-alert` must not clip it
  (`DS_components.md` §Callout). Targets are at least 44 px; the chip and its `.mm-q-when` line are
  one target and one accessible name ("EXIT QUEUED, at open 2026-10-22").
- Direction is never colour alone: the chip carries the word `EXIT` plus a monoline-set glyph; under
  ZH `--up`/`--down` flip (`theme.css:72-79`) and health ink does not. `prefers-reduced-motion`
  disables the alert fade; a queued chip never pulses — queued data is settled data.

#### Density

- Above the fold at 1280: verdict block + queued rows only; L1 cap: 8 actionable rows, then a
  counted `See all N` (`DS_components.md` Table). Never at Tier 1: `schema_version` /
  `engine_version`, `suppressed_by` codes, the no-trade band, `target_weight`/`current_weight`,
  `next_eligible_session.reason` or the Self-Directed order id.
- A book with 0 holdings and a `queued` target is not a contradiction: an add-only target shows
  `ADD QUEUED` order rows with no held-row counterpart, and V3 states that in its empty-rail copy.

#### Truth rules

1. *A natural-language explanation cannot overrule the actual account.* (MASTERPLAN §10.2, verbatim.)
   V3 binding: an S3 exit narrative renders in Tier 3 beside the action and never in a position
   where it could be read as the account state. Test: with an S3 narrative that contradicts
   `positions[]`, the rendered held-row shares and the order row's side are unchanged.
2. *A queued MU exit must show as a pending change while MU is still held.* (verbatim.) V3 binding:
   the rule above (items 1–4) is the shared acceptance with V1.
3. Missing `expires_at` / `superseded_by` / `final_disposition` / `next_eligible_session` renders
   `Unavailable` (`不可用`), never a dash, a zero or an age-derived date (E9, R2); and
   `_pendingOrderSide` (`index.html:5006-5013`) must not convert a target row with no `side` into a
   BUY order row — its legacy fallback applies only to rows from the legacy `pending` list, and V7
   records that as the candidate truth fix.

#### Acceptance checklist

1. **API↔DOM, queued-vs-held.** Unit/DOM test: for a fixture where `pending_target.status:"queued"`
   and `rows[]` contains `MU: {action:"exit"}` while `positions[]` still holds MU, the rendered MU
   row carries `data-queued-change="exit"` and the text `EXIT QUEUED` / `已排队卖出`. Inverse fixture:
   remove MU from `rows[]`; the attribute disappears and the row's chip returns to its snapshot
   verdict. (`_heldPendingChange` unit test at `index.html:4717`.)
2. **API↔DOM, no inferred direction.** Fixture with `action:"unpriceable"` and
   `action:"comparison_unavailable"` on a held lot → `data-queued-change="unclassified"`, chip
   `CHANGE QUEUED`. Fixture with `action:"hold"` on a held lot → **no** `data-queued-change`.
3. **No cross-cell leakage.** With a queued MU exit, the MU row's shares, entry, current price,
   unrealized P&L, weight, sleeve, held date and thesis row are byte-identical to the same fixture
   with no queue. (DOM snapshot diff.)
4. **Fail-closed and lifecycle.** `status:"invalid"`, `"unavailable"` and `"none"` produce **no**
   `data-queued-change` anywhere and no order row; four fixtures — fill, expiry, supersession,
   rejection — assert the rendered disposition label and, before E9 ships, the `Unavailable` word in
   each E9 slot; a queue entry that vanishes with no disposition record renders **Partial**.
5. **Mismatch ≠ supersession.** `comparison_status:"constraint_snapshot_mismatch"` renders the
   shipped `pend.constraint_mismatch` sentence and never the word `Superseded`.
6. **States, breakpoints, EN/ZH and density.** The loading skeleton has final geometry and zero
   placeholder prose; Empty carries its mandatory reason; Stale carries label + last settled as-of;
   Partial names what is excluded; Error names what failed, what still works and offers retry;
   Closed-market carries label + next open; 375 / 768 / 1280 show no page-level horizontal scroll,
   the order table scrolling inside its own container and every demoted module's named landing
   reachable from 375.
7. **EN/ZH.** Every label in the EN/ZH table renders in both languages with no EN
   fallback for a string that has a ZH pair and no forced uppercase in ZH chips; with 12 queued rows
   L1 shows 8 and `See all 12` names the real count.
8. **A11y.** Keyboard-only traversal reaches every queued row, the disclosure and `See all N`;
    `:focus-visible` is unclipped; chip + timing line expose one accessible name; measured contrast
    ≥ 4.5:1 for `--muted` timing text in both themes.

### V4 Performance

#### Question

How has this account performed, on a basis that survives being questioned?
(MASTERPLAN §10.2 Q4: "How has the account performed on a defensible basis?".) The view's own
qualification sentence is part of the answer, not a footnote to it.

#### Archetype

**A (Command Center)** as the view body, carried inside the **G (Monitor)** product
shell (§2 Art direction, item 2) — the composition rule V6 (C in G) and V5 (B in G) follow. A's
identity device is the two-column command layout + change rows; V4's VerdictHero is the NAV block
plus its qualification label and the "change rows" are the metric tiles. Not G alone: "what changed
since I last looked" is not a cumulative measurement question. Not B: a ladder before the headline
would invert the answer.

#### Information hierarchy

| Tier | Content |
|---|---|
| **Tier 1** | NAV + its qualification status (`Qualified` / `Provisional` / `Withheld` / `Unverified` / `Unavailable`), total return with its window, and the same-window benchmark delta. The qualification sentence sits directly under the headline — `DS_foundations.md`: a caveat that materially changes how the headline reads stays beside the headline. |
| **Tier 2** | (1) the equity curve with its legend and range label; (2) max drawdown with its own observed window; (3) cash; (4) the evidence sentence (`_performanceEvidenceText`). |
| **Tier 3** | Attribution (E11); the window ledger (start/end endpoints, cohort, `observed_at`, `sources`); external-flow disclosure; the withheld-dates ledger (`nav_withheld.jsonl`, E5); the win-rate scorecard with its n-gate; benchmark method disclosure. |

#### Fields

| Field | Meaning | Owner | Source today | Type / units | Nullable | Display when null / unknown |
|---|---|---|---|---|---|---|
| `current_nav` | the headline NAV | ECON | `/api/performance` (`portfolio/performance_projection.py:275-302`; render `index.html:3939-3940`) | number, book currency | yes | `Unavailable`; never `—` alone (`DS_components.md` §Metric) |
| `availability.status` / `.valuation_basis` / `.as_of` / `.history_status` / `.account_history_binding` / `.issues[]` | the panel's own qualification | ECON | `performance_projection.py:294-301`; render `_performanceEvidenceText` (`index.html:3875-3901`) | enum / ISO / array | object absent on archived books (`app/web.py:205-225`) | an absent `availability` object must render the **Unverified** word, not an empty sentence and not a plain "NAV" label (census violation 7) |
| `nav_history[].nav_status` | A02 `QUALIFIED\|PROVISIONAL` | ECON | **CONTRACT REQUEST → E1** (consumption against published A02) | enum | absent on pre-A02 rows | `Unverified` / `未核实` (§3 vocabulary); **never upgraded to qualified** |
| `nav_history[].nav_qualified` | the qualified NAV | ECON | **CONTRACT REQUEST → E2** | number, book currency | null when PROVISIONAL | a PROVISIONAL row shows `nav` under the `Provisional` label; a QUALIFIED row shows `nav_qualified` |
| `nav_history[].carried[]` `{ticker, price, price_asof, age_days, source, value, weight_of_invested}` | which names are valued from an older close and how old | ECON | **CONTRACT REQUEST → E3** | array; price in book ccy; `age_days` calendar days | empty array once A02 lands, never absent | an empty array renders no limitation line; a non-empty one renders `Provisional` + the carried names with their ages |
| `nav_history[].unattested[]` | names used without price evidence | ECON | **CONTRACT REQUEST → E4** | string[] | empty array | same as `carried[]`, rendered as a distinct sentence |
| `nav_withheld.jsonl` rows `{date, mark_source, unpriced[], carried[], reason}` | dates on which no NAV was written | ECON | **CONTRACT REQUEST → E5** | file per book | file absent → no withheld dates | a withheld date is a **gap with a reason** on the curve, never a flat line |
| `total_return_pct` | change from `starting_nav` | ECON | `performance_projection.py:283`; render `index.html:3945-3950` | percent, 2 dp, signed | yes (the empty result returns `None`) | `Unavailable`; never `+0.00%` from a missing baseline (`app/web.py:190-196`) |
| `inception_date` / `starting_nav` | the measurement anchor | ECON | `performance_projection.py:278-279`; validated finite > 0 at `index.html:4042` | date / number | yes | `since inception` (`index.html:3222`); a null `starting_nav` renders pre-inception points as **gaps**, never zeros |
| `series[].date` / `.nav` / `.spy_nav` / `.kind` | the two curves | ECON | `performance_projection.py:233-275`; render `index.html:4011-4045` | date / number / number / enum `realized\|pre_inception` | `spy_nav` null per point | the pen lifts on a null point (`_equityAreaPath`, `index.html:3903-3921`); today the line does lift, the **area** is what must not be re-closed across the gap |
| `benchmark` / `benchmark_name` / `benchmark_name_zh` / `benchmark_as_of` | the book's own benchmark | ECON | `portfolio/registry.py` `benchmark*`; render `index.html:3925-3927`, `:4028-4029` | string / string / string / ISO | `benchmark` falls back to the literal `Benchmark` (`index.html:3925`) | the literal fallback may name the axis, never claim a series exists |
| `vs_benchmark_pct` | the same-window delta | ECON | `performance_projection.py:284`; render `index.html:3967` | percent, signed | yes | **Benchmark unavailable** (§3) |
| `vs_spy_pct` | the alias of the same value | ECON | `app/web.py:211` publishes `"vs_spy_pct": vs_benchmark_pct` | percent | yes | **must not be read as a fallback** (`index.html:3967`) — CN/HK would read "vs 沪深300" over an SPY-named field. V4 requires the alias dropped from the consumer and the field renamed at source (candidate bounded PR). |
| benchmark comparison `{status: supported\|unsupported, reason, start, end, book_return, bench_return, delta}` | the A12 same-window comparison | ECON | **CONTRACT REQUEST → E8** (against the #1434 helper `brain/benchmark_comparison.compare_curves`) | object; returns as fractions | `status:"unsupported"` → **every** number null | every number null **and** the word `Benchmark unavailable` / `基准不可用` in the value slot, with `reason` in the evidence sentence. Never 0, never a dash alone, never a bar at zero height. |
| `day_change_pct` + `day_change_window.{from,to}` | change between the last two recorded observations | ECON | `performance_projection.py:288`, `:290`; render `index.html:3973-3985` | percent / date pair | yes | `Unavailable` when computed from **fewer than two distinct marks**, or when the change is written before the session open (SEAT truth requirement). The window range still renders: "between recorded observations" (`index.html:3227`). |
| `max_drawdown_pct` + `drawdown_window.{from,to}` | peak-to-trough over recorded observations only | ECON | `performance_projection.py:289`, `:291`; render `index.html:3987-3999` | percent ≤ 0 / date pair | yes | `Unavailable`; the range line keeps `over recorded observations` (`index.html:3229`) |
| `cash` | cash held | ECON | render `index.html:4002-4004` | number, book currency | yes | `Unavailable`, never `0`. `app/web.py:1341` (`float(account.get("cash") or 0.0)`) coerces a missing cash to zero — **CONTRACT REQUEST → E7**; PRODUCT removes the coercion in the same change. |
| `realized_since` | the first recorded observation | ECON | `performance_projection.py:292`; render `index.html:4025-4027` | date | yes | legend shows `—`; the START marker is omitted when absent |
| `external_flow_adjustment` | whether the NAV change is net of outside money | ECON | carried in the payload (`app/web.py:1181`), rendered in the evidence sentence (`index.html:3897-3899`) | enum `not_applied\|…` | yes | absent → sentence omitted; `not_applied` → "NAV change is not adjusted for external cash flows." |
| `return_measure` / `benchmark_return_basis` / `benchmark_total_return_status` / `benchmark_comparison_scope` / `observed_at` / `sources` | method + provenance of the comparison | ECON | carried in the payload (`app/web.py:1180-1182`), rendered only through the qualification text today | string / enum / ISO / array | yes | Tier-3 window ledger; each absent value renders `Unavailable` in that row only |
| attribution `{ticker, window_start, window_end, contribution, contribution_basis, priced_through}[]` | which holdings drove the window's return | ECON | **CONTRACT REQUEST → E11** (census gap: attribution exists only on the Flagship Desk, `/api/desk/scorecard`, `app/web.py:3326-3413`) | array; `contribution` a fraction of NAV at `window_start` | a holding with an unqualified mark in the window → `contribution: null` **with its reason** | the module renders `Unavailable` and names that attribution is not yet delivered; **no** Brisson buckets, seat scores or sleeve credits are borrowed from the Desk |
| win rate over closed sells `{fills[].realized_pnl, fills[].cost_basis_method}` | the closed-position sample | ECON | **CONTRACT REQUEST → E10**; today derived client-side at `index.html:5087-5093` | number / enum; `realized_pnl` null for buys | yes | see the minimum-n rule below |

#### Layout

| Breakpoint | Modules, in order |
|---|---|
| **1280** | 1. VerdictHero: NAV value + `perf-nav-label` qualification word + the evidence sentence + one freshness stamp, in the existing `#performance` panel (`index.html:2757-2794`). 2. Support-1: metric row — total return, benchmark delta, day change, drawdown, cash (`#perf-ret`, `#perf-spy`, `#perf-day`, `#perf-dd`, `#perf-cash-lbl`). 3. Support-2: `#equity-curve` ChartFrame with legend + range label (`index.html:2794-2813`). 4. Tier-3 band in `<details class="mm-da-foot">`: attribution (E11), window ledger, withheld-dates ledger, win-rate scorecard. |
| **768** | Same order; metric row becomes a 2×3 grid; the chart keeps its legend and range label beneath it (chart context below the graph, per the shipped comment at `index.html:2800`). Attribution moves into the Tier-3 disclosure. |
| **375** | 1. NAV + qualification + evidence sentence. 2. The chart (min 180 px tall, legend below). 3. Total return and benchmark delta only. 4. **Named landing**: `See return, drawdown, cash and attribution` → the remaining metrics + the Tier-3 ledger as their own route. Nothing is deleted; the landing is named. |

#### States

| State | Trigger | Copy + treatment | What still works |
|---|---|---|---|
| **Loading** | `/api/performance` in flight | Skeleton at the real geometry: one hero numeral, five metric stubs, a chart frame with axes. No prose. | Book switch; V1's own as-of. |
| **Empty** | `series:[]` and `availability.history_status:"unavailable"` | `Empty` / `暂无` + the reason: `Empty — this account has no recorded NAV history yet.` / `暂无 — 本账户尚无净值记录。` Copy request: replaces the shipped `ec.no_data` string `No recorded performance observations available` / `暂无可用的业绩记录` (`index.html:3235`). Full weight. The chart frame stays, empty, at its real geometry. | NAV, cash, benchmark name (as a name only), the book switch. |
| **Stale** | the panel as-of is behind the session clock, or the last observation predates the open | `Behind` + last settled as-of stamp. A pre-open row is stale **and** the day change is unavailable — see the day-change rule below. | Every settled figure, labelled. |
| **Partial** | `availability.status:"provisional"` with `carried[]`/`unattested[]`; `history_status != "available"`; `benchmark_comparison_scope` narrower than the curve window | `Partial` + the word that names what is excluded. The shipped sentence already composes these clauses (`index.html:3891-3899`); V4 requires all of them to be present, not just the first. | Qualified figures render at full weight; the excluded part is named. |
| **Error** | `availability.status:"unavailable"` / the `unavailable_performance()` shape | The shipped sentence — `Performance evidence unavailable; no balance or zero return has been substituted.` (`index.html:3880`) — under the `Couldn't load` label, naming what still works (the book's holdings, from V1) plus retry. | V1, V3, V6 for the same book. |
| **Closed-market** | `market.is_open === false` | `Market closed` + next open. The curve's last point is stamped as pre-open, not as a closed session. | Everything; the last settled NAV is still the NAV. |
| **Benchmark-unavailable** | E8 `status:"unsupported"`, or `series[].spy_nav` null at every point | See the benchmark rule below. | Portfolio-only figures render normally. |
| **Provisional valuation** | A02 `nav_status:"PROVISIONAL"`, or `availability.valuation_basis:"provided_prices"` | `Provisional` / `暂定` label beside the NAV, plus the carried names and their ages: "MU priced from the 2026-10-21 close, 1 day old". Treatment: `--q2` epistemic ink **plus** the word, never ink alone; the affected curve points are drawn at reduced weight with a hollow marker. | The number renders — it is a real back-compat figure — under its label. |
| **Withheld valuation** | A02 `WITHHELD` date (`nav_withheld.jsonl`, E5) | `Withheld` / `暂不估值` and a **gap in the curve with its reason** — the reason names the unpriced tickers, never their cost (`ECON_CONTRACTS_PR1699.md` §a: exposure is stated in shares and last observed price, never at cost). The NAV axis interpolates nothing across it. | Every other date on the curve. |
| **Unverified (pre-A02 row)** | `nav_status` absent | `Unverified` / `未核实` — label only, never upgraded to qualified. | The figure renders under its unverified label. |
| **Queued** | n/a — V4 renders no position. | — | — |

**The same-window benchmark rule (A12, E8).** The delta, the overlay and the legend are one claim and
are rendered as one claim or not at all.

1. The comparison is produced by `brain/benchmark_comparison.compare_curves` (A12, #1434). Its
   boundary is binding on this view: named curves; an explicit cohort and as-of cutoff; **actual
   common endpoints** with ≥ 2 finite positive dated points; **no forward-fill** and **no
   missing-as-zero**; `C(end)/C(start) − 1` rebasing without re-weighting; a pairwise delta on the
   named pair only; and one shared window for ranking.
2. **Same window, both curves.** The portfolio segment and the benchmark segment drawn between the
   two delta endpoints are the same segment the number describes. A different start or end on either
   curve is a defect, not a rounding difference. (A12 defect register entry: consumers can compare
   different windows or select a sidecar instead of a dated ledger.)
3. **A02 composition.** A window whose endpoint rows are `PROVISIONAL` carries that label through to
   the delta's own status; a `WITHHELD` date is not an endpoint (`ECON_CONTRACTS_PR1699.md` §d.4).
4. **Unsupported ⇒ every number null and the word.** When E8 `status:"unsupported"`, V4 renders
   `book_return`, `bench_return` and `delta` as null, the value slot reads
   **`Benchmark unavailable` / `基准不可用`** in `--muted` (§3 vocabulary, non-colour cue: the word),
   and `reason` moves into the evidence sentence. Never `0`, never `0.00%`, never a dash alone,
   never a zero-height reference line.
5. **The legend must not claim a series that is not drawn.** The legend currently always appends
   `(reference series)` (`index.html:4029`) even when every `spy_nav` is null. V4 requires the
   benchmark legend entry to be replaced by `Benchmark unavailable` under the same conditions, so a
   chart with no benchmark line cannot claim one.

**Point styling by A02 status** (the visual half of the same contract):

| Status | Marker | Weight | Fill | Non-colour cue |
|---|---|---|---|---|
| `QUALIFIED` | solid circle | 1.8 px (`--up` for the portfolio series; direction tokens only) | `--panel` | none needed |
| `PROVISIONAL` | hollow circle | 1.8 px | `--panel` | hollow + the tooltip says `(provisional)` |
| `WITHHELD` | no marker | — | — | the gap carries the reason; nothing is drawn |
| benchmark point missing | no marker | — | — | the line breaks; the tooltip says `—` |

`DESIGN-SYSTEM-GAP G9: epistemic-qualification-badge — the A02 words QUALIFIED / PROVISIONAL / WITHHELD /
UNVERIFIED must be a labelled word beside a value, not a freshness chip; `DS_components.md` scopes
`.dtp*` to "only freshness/session language" and the app has no other canonical badge, so V1/V2/V4/V6
would each invent one.

Pre-inception reference points keep the existing treatment but must **not** be folded into the
portfolio series' identity: today they are drawn as a solid line in the same `--up` family at full
weight (`index.html:4044-4046`, census violation 9) and are included in the y-extent. V4 requires
them drawn as the dashed inception baseline with a `START` marker only, excluded from the y-extent
of the realised segment — so a long flat capital tail cannot make real performance look calm.

**The missing-price flat-line gap rule.** A date with no independent mark is **never** drawn as a
horizontal segment. `pathStr` already lifts the pen on a null (`index.html:4082-4092`) and
`_equityAreaPath` closes one area per contiguous observed segment (`index.html:3903-3921`); V4 binds
both: a null point produces a break in the **line**, a break in the **area**, and a break in the
**tooltip row**, and the range label still shows the full date span. Two consecutive identical `nav`
values are a missing-price artefact until A02 says otherwise — the observed 2026-10-21 → 10-22 case.

**The minimum-n win-rate rule (SEAT DECISION).** Proposed: **withhold** the win rate below
**n ≥ 30 closed sells** (counting only `action:"sell"` rows with a non-null `realized_pnl`,
`index.html:5087`). Below the floor the tile renders the word **`Sample too small`** /
`样本不足` with the actual n beside it (`n = 12 closed`), never a percentage, never a bar, never a
sparkline. At or above the floor the tile renders `NN%` **and** `n = NN closed`, so the n is always
on screen. Alternative considered: show the percentage at any n with the n attached — rejected,
because MASTERPLAN §10.2 forbids visually rewarding a tiny closed-position sample as a winning
strategy, and 1-of-1 at 100% is the canonical failure (census violation 5: a single closed position
today renders "Win Rate 100%"). This floor is a **SEAT DECISION**; V4 proposes n ≥ 30 and names
the alternative.

#### EN / ZH

| Element | EN | ZH |
|---|---|---|
| Panel title | `Performance — Simulated Account` (`index.html:3219`) | `业绩 — 模拟账户` |
| NAV label | `NAV` / `Last recorded NAV` / `Provisional NAV` (`index.html:3934-3936`) | `净值` / `最近记录净值` / `暂定净值` |
| Status words | `Qualified` / `Provisional` / `Withheld` / `Unverified` / `Unavailable` | `已核实` / `暂定` / `暂不估值` / `未核实` / `不可用` |
| Return | `Change from Start` · `since <date>` · `since inception` (`index.html:3221-3223`) | `相对初始净值变化` · `自 <日期>` · `自成立以来` |
| Benchmark | `vs <benchmark name>` / `相对<基准名>` (`index.html:3962-3963`); `Benchmark unavailable` | `基准不可用` |
| Day change | `Last observed change` · `between recorded observations` (`index.html:3226-3227`) | `最近记录变动` · `记录之间的变化` |
| Drawdown | `Recorded Drawdown` · `over recorded observations` (`index.html:3228`; range phrase `:3999`) | `记录最大回撤` · `已记录观察区间` |
| Cash | `cash:` (`perf.cash_lbl`, `index.html:3229`) | `现金:` |
| Legend | `Portfolio (recorded since <date>)` · `<benchmark> (reference series)` (`index.html:3232-3233`) | `组合（记录始于 <日期>）` · `<基准>（参考序列）` |
| New — carried / withheld reason | `priced from the <date> close, <n> day(s) old` · `Not valued on <date>: <tickers> could not be priced` | `采用 <日期> 收盘价，已过时 <n> 天` · `<日期> 未估值：<标的> 无法取得价格` |
| New — win-rate gate | `Sample too small (n = <n> closed)` | `样本不足（已平仓 n = <n>）` |

#### Accessibility

`ChartFrame` with the question captioned before the geometry; every number in the
tile row is also present as text (the SVG is `aria-hidden`) and the tooltip opens by focus and tap,
not hover only. Focus order: NAV → evidence sentence → tile row left→right → chart → each disclosure
summary. `--focus-ring` unclipped on every chip and marker; ≥ 4.5:1 for `--muted` sub-lines and 3:1
for the curve stroke against `--panel`; hollow `PROVISIONAL` markers clear 3:1 on both themes;
direction ink is always paired with a sign, and under ZH `--up`/`--down` swap (`theme.css:72-79`)
while `--q2`/`--q3` do not. `prefers-reduced-motion` disables the draw-on animation; a settled curve
does not animate at all.

#### Density

Above the fold at 1280: NAV + qualification + total return + benchmark delta + the
chart. Never at Tier 1: attribution rows, window-ledger fields, the withheld-dates ledger, win rate,
`schema_version`-class provenance, per-point tooltips. L1 cap: 8 attribution rows then counted
`See all N`. One canonical integer per population — the win rate shows one n, not two.

#### Truth rules

1. *An unavailable benchmark displays unavailable rather than zero.* (verbatim.) V4 binding: E8
   `unsupported` ⇒ all three numbers null + the word `Benchmark unavailable`; legend entry
   replaced; never `0`, never a dash alone.
2. *Do not visually reward a missing-price flat line as low volatility or a tiny closed-position
   sample as a winning strategy.* (verbatim.) V4 binding: the gap rule above, the pre-inception
   baseline excluded from the y-extent, and the n ≥ 30 win-rate gate.
3. *A natural-language explanation cannot overrule the actual account.* (verbatim.) V4 binding: the
   evidence sentence qualifies the NAV; it never restates or replaces it, and a `cash_only` or
   `last_recorded_nav` basis sentence (`index.html:3882-3883`) is mandatory, not optional.
4. Missing `cash` renders `Unavailable`, never `$0` (`app/web.py:1341`; E7); and a day change
   written **before** the open, or computed from **fewer than two distinct marks**, renders
   `Unavailable` — never `+0.00%` (SEAT truth requirement; covers the 2026-10-22 observation and
   `app/web.py:190-196`).

#### Acceptance checklist

1. **API↔DOM, benchmark.** Fixture with E8 `status:"unsupported"`: `perf-spy` text is exactly
   `Benchmark unavailable` / `基准不可用`, `series[].spy_nav` renders no line, the legend entry is
   replaced rather than appended, and no `0`, `0.00%` or `—`-alone appears anywhere in the delta path.
2. **Same window.** Fixture with two curves whose common dates differ: the delta's `start`/`end`
   equal the first and last x-coordinates of the drawn portfolio segment, asserted from the payload.
3. **A02 point styling.** Fixture with one `QUALIFIED`, one `PROVISIONAL` and one withheld date: the
   rendered markers are solid / hollow / absent respectively, and the withheld date appears in the
   ledger with its reason and no cost figure.
4. **Gap rule.** Fixture with a null `nav` between two dated points: `pathStr` produces two subpaths,
   `_equityAreaPath` produces two closed segments, and the y-extent excludes the gap's neighbours'
   interpolation. No horizontal segment spans the gap.
5. **Flat line.** Fixture with two identical consecutive `nav` values and no `nav_status`: the day
   change renders `Unavailable`, not `+0.00%` (unit test on the day-change guard).
6. **Cash.** Fixture with `account.cash` absent: the cash slot reads `Unavailable`, not `$0`
   (regression test for `app/web.py:1341`).
7. **Archived books and drawdown.** A fixture from `_archived_performance` (`app/web.py:205-225`)
   with no `availability` key renders the status word `Unverified` / `未核实`, not a blank sentence
   and not a plain `NAV` label; and a gap inside the drawdown window marks the drawdown **Partial**,
   names the gap, and still renders the `over recorded observations` range.
8. **Win-rate gate and attribution.** Fixtures at n = 0, 1, 29, 30, 42 render `Sample too small`
   with the real n and no percentage below 30, and `NN%` **and** `n = NN closed` at or above it;
   with E11 undelivered the attribution module renders `Unavailable` and borrows nothing from
   `/api/desk/scorecard`, and a fixture with one `contribution: null` shows that row's reason.
9. **States, breakpoints and a11y.** Screenshot matrix at 375 / 768 / 1280 × EN / ZH × dark /
    light covering loading, empty, stale, partial, error, closed-market, benchmark-unavailable,
    provisional, withheld, unverified, with no page-level horizontal scroll at 375; keyboard-only
    path reaches every tile, the chart, each point's tooltip value and each disclosure; measured
    contrast ≥ 4.5:1 for sub-lines and ≥ 3:1 for strokes/markers in all four theme-language
    combinations.

### V5 Opportunities

#### Question

What evidence supports the manager's decision and its limitations — what was
researched, what was rejected and why, what could be entered now, and how much rests on each source?
(MASTERPLAN §10.2 Q5, `Opportunities`.) The census records this view as answering **none** of Q1–Q5
for the product book; this spec is the proposal that makes it answer Q5.

#### Archetype

**B (Discovery Board)** composed inside the **G (Monitor)** shell (§2 Art direction,
item 2), exactly as V6 composes C. B's identity device is the **count ladder** (DS `.mx-ladder`; no app class ships — `DESIGN-SYSTEM-GAP G10: count ladder`, §8):
exhaustive, disjoint stage cells, the active stage marked by weight and surface and **never
violet**. The two populations are **finalists** (researched, not held) and **rejected** (evaluated,
not held) — disjoint by construction, so the ladder must never merge them into one total.

#### Information hierarchy

| Tier | Content |
|---|---|
| **Tier 1** | The count ladder over the two populations, plus the ladder's own as-of and its source-coverage summary word. Nothing else above the fold. |
| **Tier 2** | (1) Finalist rows — name, combined score, viability, entry readiness, as-of. (2) Rejected cards — name, reason, veto chips, top-3 bear bullets, confluence. |
| **Tier 3** | Per-name evidence: the research paper (`report_md`, key risks, price assessment), the calibration record (`/api/outcome_ledger` reliability + lens edge), the source-coverage ledger (S8), and the entry-readiness blockers (S9). |

#### Fields

Only fields that exist today or that carry a request id. Nothing is borrowed from the
Flagship Desk to fill a product-book gap.

| Field | Meaning | Owner | Source today | Type / units | Nullable | Display when null / unknown |
|---|---|---|---|---|---|---|
| `rejected[].ticker` | an evaluated name that is not held | RESEARCH | `/api/portfolio` `rejected[]` (`app/web.py:1463-1471`; render `index.html:4484`) | string | yes | `—` today; V5 requires the card to be omitted rather than titled `—` |
| `rejected[].reason` / `_zh.reason` | why it was not taken | RESEARCH | `app/web.py:1465-1469`; render `index.html:4479` | string | yes | card body reads `No reason recorded` / `未记录原因`; never invented |
| `rejected[].vetoes[]` | hard rules that fired | RESEARCH | render `index.html:4488-4494` | string[] | empty → the chip row is omitted | — |
| `rejected[].bear[]` / `_zh.bear[]` | the top risks | RESEARCH | `app/web.py:1470-1471`; render `index.html:4481`, `:4497-4502` | string[] | empty → the list is omitted, not rendered as "no bear points" | — |
| `rejected[].confluence` | the conviction score, worst first | RESEARCH | render `index.html:4473-4475`, `:4504` | number, 2 dp signed | yes | `Unavailable`; today it renders `—` with a `neu` class, which V4/V5 must upgrade to the word |
| finalist list | researched, not held, for **this** book | RESEARCH | **absent for product books** — the closest shape is `/api/research_papers` `papers[]` (`app/web.py:1905-1959`) | array | the endpoint exists; the book binding is wrong (below) | V5 renders its empty state naming that no finalist list is bound to this book until the join ships |
| `papers[].ticker` / `.asof` / `.reviewed_at` | name and review dates | RESEARCH | `app/web.py:1931-1933` | string / ISO / ISO | yes | the row renders with `Unavailable` in the date columns and stays out of the ladder |
| `papers[].engine_score` / `.research_score` / `.combined` / `.viability` | the scores | RESEARCH | `app/web.py:1943-1948`; render `index.html:5300-5302` | numbers | yes | each score cell renders `—` today; V5 requires the word per the shared rule |
| `papers[].mode` | which research mode produced it | RESEARCH | `app/web.py:1937` | string | yes | this is the **only** source field that exists today; it is the sole basis of the coverage word until S8 ships |
| `papers[].recommend` / `.confidence` / `.fair_value` / `.price_at_review` / `.price_assessment` | the paper's own conclusion | RESEARCH | `app/web.py:1949-1954` | string / number / number | yes | Tier-3 evidence rows; each missing value renders `Unavailable` |
| `papers[].summary(_zh)` / `.report_md(_zh)` / `.key_risks[]` | the argument | RESEARCH | `app/web.py:1955-1959` | string / markdown / string[] | yes | an empty body renders `Unavailable`, never an empty pane |
| `papers[].action` / `.trade_time` / `.weight` | the gate's verdict for that name | ECON | `app/web.py:1912-1925` — **the join reads `data/portfolio/latest.json`, the archived flagship tree, regardless of the requested book** (census violation 10) | enum / ISO / fraction | `action` defaults to `evaluated` | **V5 must not render `action`, `trade_time` or `weight` for a product book at all.** Until the join is book-bound, V5 omits the column entirely rather than showing a flagship-derived action under a product book's name. Recorded as a candidate truth fix, and as a SEAT DECISION below. |
| outcome ledger `summary.{n,status,brier,hit_rate,calibration_error}` | forward grading | RESEARCH | `/api/outcome_ledger` (`app/web.py:1964-2000`) | numbers / enum | yes | Tier-3 calibration block; `status:"building"` renders `Building` with its n, never a score |
| `reliability_curve[].bucket` / `.mean_predicted` / `.hit_rate` / `.n` | calibration buckets | RESEARCH | render `index.html:5429-5430` | fractions / int | `hit_rate` missing is coerced to `0` | V5 requires a bucket with `n === 0` to render as an **absent** bucket with its n, not a 0-width bar at "0%" (census violation 8) |
| `lens_edge[]` / `.lens_weights{}` / `records[]` | per-lens edge | RESEARCH | `app/web.py:1971-1999` | array / object | yes | Tier-3 only; not a Tier-1 or Tier-2 number |
| finalist source coverage `{sources[]: {source, status, asof}, coverage_complete}` | how much of each finalist rests on each source | RESEARCH | **CONTRACT REQUEST → S8** | array of objects / boolean | per-source nullable | the ladder's coverage word renders `Unavailable`; a finalist row shows `Coverage unavailable` / `来源覆盖不可用` |
| entry readiness `{status: enterable\|blocked\|unknown, blockers[], price_asof, next_session_at}` | can this finalist be entered now | RESEARCH + market calendar | **CONTRACT REQUEST → S9** — entry readiness is modelled nowhere today | enum / array / ISO | yes — the whole object until S9 ships | null → the readiness slot renders `Unavailable`; it is **never** inferred from score, confluence or a veto list |

#### Layout

| Breakpoint | Modules, in order |
|---|---|
| **1280** | 1. The count ladder (G10): `RESEARCHED n` \| `FINALIST n` \| `REJECTED n`, one exhaustive disjoint accounting, active cell by weight/surface. 2. Support-1: finalist rows (`.mm-table-wrap` table, L1 ≤ 8 then `See all N`). 3. Support-2: rejected cards in the existing `.mm-rej-grid` rhythm (`index.html:4470`). 4. Tier-3 band in `<details class="mm-da-foot">`: per-name paper + key risks, calibration block, source-coverage ledger, entry-readiness blockers. |
| **768** | Same four modules; the ladder spans full width; finalist table keeps name, combined, viability, readiness, as-of and demotes `engine_score`/`research_score` to the row's evidence landing. |
| **375** | 1. The ladder. 2. Top 3 finalists as row cards (name · combined · readiness word), each opening its V6-style thesis card (§2 Navigation, cross-view entry points). 3. Top 3 rejected cards. 4. **Named landing**: `See all N researched names` → the full ladder breakdown. Scores, papers and calibration move into that landing. Nothing is deleted. |

#### States

| State | Trigger | Copy + treatment | What still works |
|---|---|---|---|
| **Loading** | `/api/portfolio` or `/api/research_papers` in flight | Skeleton at final geometry: the ladder as three labelled cells with no counts, then card shells. No prose. | Navigation, book switch. |
| **Empty** | `rejected[]` empty and no finalist rows | `Empty` / `暂无` + the reason: `Empty — no rejected names: this book has not run yet, or every evaluated name passed.` / `暂无 — 无剔除标的：本组合尚未运行，或所有标的均通过评估。` Copy request: replaces the shipped `rej.empty` string (`index.html:3395`). Full weight. The block is not rendered as a zero-height shell. | V1, V2, V3, V4, V6, V7. |
| **Stale** | the ladder's as-of is behind the session clock | `Behind` + the ladder's last settled as-of stamp, separate from V1's page stamp (§3: one freshness stamp per panel + one page stamp). | Everything, labelled. |
| **Partial** | `rejected[]` present but the finalist join unbound (today's state for every product book) | `Partial` + the word that names what is excluded: "No finalist list is bound to this book. Rejected names below are complete." The ladder shows the `REJECTED` cell filled and `FINALIST` as `Unavailable` — **never 0**, because 0 finalists and unknown finalists are different facts. | Rejection reasons, vetoes and bear bullets in full. |
| **Error** | `/api/research_papers` returns its `{papers: [], error}` shape (`app/web.py:1905-1907`) or the request fails | `Couldn't load` + what failed + what still works (the rejected list, from a different endpoint) + retry. | Rejected cards render; the finalist ladder cell renders `Unavailable`. |
| **Closed-market** | `market.is_open === false` | `Market closed` + next open. Entry readiness for every finalist is rendered `Unavailable` while the market is shut — a closed market is an unknown readiness, not a blocked one. | Rejection reasons, scores, papers. |
| **Queued** | a finalist that also appears in the current `pending_target.rows[]` | `Queued` / `已排队` in that finalist's status slot with a link to V3. The held-row `#1707` chips do **not** apply here — `_heldPendingChange` requires a lot we still hold (`index.html:4737-4742`), and a finalist is by definition not held. | Everything else. |
| **Unavailable** | any S8 / S9 slot without a value | The word `Unavailable` / `不可用`, muted, in the value slot. | Every other slot. |
| **Benchmark-unavailable** | n/a — V5 renders no benchmark. | — | — |
| **Provisional / withheld valuation** | n/a — V5 renders no valuation. | — | — |

**Reachability for product books — SEAT DECISION.** V5 is unreachable for `autonomous`, `china` and
`hk` today: `#rejected` is in `PF_GATED_ONLY` (`index.html:6468`) and `applyPortfolioScope` hides every
gated panel when the active book is a Brain book and not self-directed (`index.html:6542-6544`,
`_isBrainBook` at `index.html:6524-6527`); the Research and Desk tabs render only when
`_portfolio === 'flagship'` (`index.html:6551-6552`), and both routes force that book
(`index.html:9122-9123`). `flagship` is **archived** (`portfolio/registry.py:33-45`), so the only book
that can reach V5 content is a retired one — and the endpoints behind it are book-agnostic, which is
how the flagship join leaks into product-book responses (census violation 10).

**SEAT DECISION V5-A.** *Does V5 become a route reachable for every active book?* **Recommendation:
yes**, in two separable steps so the risky half is not blocked by the safe half. (a) **the data
binding** — `rejected[]` and the finalist join become book-scoped and `/api/research_papers` stops
reading `data/portfolio/latest.json` for a requested product book: a bounded `app/web.py` read fix
with an API/DOM agreement test, which PRODUCT may propose as its own carrier. (b) **the navigation
change** — remove `rejected` from `PF_GATED_ONLY` and add V5 to the secondary view axis (§2), which
redesigns a shipped panel and is therefore the seat's. *Alternative considered and rejected:* keep
the gate and surface rejection reasons on V6/V1 as a disclosure — rejected because it leaves "what
was researched and not taken" (Q5) unanswerable for the book the product actually ships and keeps a
retired book as the only place the question can be asked. *Fallback if the seat declines (b):* V5
renders the `Partial` state with the exact exclusion sentence above.

#### EN / ZH

| Element | EN | ZH |
|---|---|---|
| Panel title | `Evaluated — Not Held, and Why` (`rej.title`, `index.html:3392`) | `已评估 — 未持仓及原因` |
| Subtitle | `the discipline made visible` (`rej.subtitle`) | `让纪律透明化` |
| Ladder cells | `RESEARCHED` \| `FINALIST` \| `REJECTED` | `已研究` \| `候选` \| `已剔除` |
| Ladder subtitle | `one accounting · both sets are disjoint` | `同一口径 · 两类互不重叠` |
| Veto chips | the veto string itself (`parabolic extension`, `distress`, `cycle-blocked`) | the veto's ZH string; a veto with no ZH pair renders the EN string, never a transliteration |
| Confluence | `Confluence:` (`rej.confluence`, `index.html:3397`) | `汇聚分:` |
| Empty | `Empty — no rejected names: this book has not run yet, or every evaluated name passed.` (copy request; replaces shipped `rej.empty`, `index.html:3395`) | `暂无 — 无剔除标的：本组合尚未运行，或所有标的均通过评估。` |
| No reason | `No reason recorded` | `未记录原因` |
| Coverage / readiness | `Source coverage unavailable` · `Entry readiness unavailable` | `来源覆盖不可用` · `入场就绪度不可用` |

#### Accessibility

The ladder is a `<table>`-semantics row whose cells expose counts ("REJECTED, 14
names"); the active cell is marked by `aria-current`, not by weight alone. Focus order: ladder →
finalist rows → rejected cards → each evidence disclosure; veto chips are non-focusable text inside a
focusable card, so the card has one accessible name. Cards carry no hue of their own (achromatic
fill, even neutral border, stronger text — `DS_states-accessibility.md`); `confluence < -0.05` uses
`neg` ink **only** because it is paired with its sign and the word `Confluence`. Targets are at least
44 px; disclosures open by keyboard and touch; `prefers-reduced-motion` disables any ladder
transition — a ladder is settled data and never pulses.

#### Density

Above the fold at 1280: the ladder + finalist rows. Never at Tier 1: raw scores
(`engine_score`, `research_score`, `viability`), Brier, hit rate, lens edge, paper text or price
assessment — Tier 1 avoids raw research statistics outright (`DESIGN_DOCTRINE.md`: a number must
arrive with its interpretation). L1 caps: 8 finalist rows, 6 rejected cards, then counted
`See all N` on each; one canonical count per population, so no card repeats a total.

#### Truth rules

1. *A natural-language explanation cannot overrule the actual account.* (verbatim.) V5 binding: a
   finalist or a rejected name is by definition **not** in `positions[]`. A paper that recommends
   `buy` never renders as a position, and V5 never draws a share count, weight or P&L for a name the
   account does not hold.
2. *An unavailable benchmark displays unavailable rather than zero.* (verbatim.) V5 binding: **n/a —
   V5 renders no benchmark**; that no-applicability is a determination, not an omission.
3. No missing value coerces to a number: a `reliability_curve` bucket with `n === 0` renders absent
   (`index.html:5429-5430`), a missing `confluence` or finalist count renders `Unavailable` rather
   than `0`, and no flagship-derived fact renders under a product book's name — until `action` /
   `trade_time` / `weight` are book-bound those columns are omitted rather than shown.

#### Acceptance checklist

1. **Reachability (SEAT DECISION V5-A).** With the book switch on `autonomous`, V5's nav item is
   present, its route resolves, the ladder's `FINALIST` cell renders `Unavailable` and `REJECTED`
   is populated; if the seat declines the navigation change, the same fixture renders the exact
   `Partial` exclusion sentence and no finalist cell claims `0`.
2. **Book binding.** API/DOM agreement test: request `/api/research_papers?book=china` and assert
   no `action` value equals `buy_confirmed` sourced from `data/portfolio/latest.json`. Until the join
   is book-scoped, assert instead that the rendered table has **no** `Action` column at all.
3. **Ladder arithmetic, states and no unknown→0.** Ladder cells sum to the union of the two
   disjoint populations for a fixture and each count appears exactly once on the page; Empty renders
   the §3 `Empty` sentence that replaces `rej.empty` at full weight; Partial names the excluded half and renders `Unavailable` (never
   `0`); Error names what failed, keeps the rejected list and offers retry; a `confluence: null` and
   a `hit_rate`-absent bucket render `Unavailable` and an absent bucket with its `n` — regression
   tests for `index.html:4473-4475` and `index.html:5429-5430`.
4. **Readiness and coverage are never inferred.** With S9 undelivered every finalist renders
   `Entry readiness unavailable` even when its scores are high and it has no vetoes, and with S8
   undelivered the word is `Source coverage unavailable`; a `blocked` fixture renders its named
   blockers with no `enterable` claim and a partial `{sources[]}` renders `Partial` naming the
   uncovered source.
5. **Queued cross-link, breakpoints and a11y.** A finalist present in `pending_target.rows[]` renders
   `Queued` and links to V3, one absent from it renders no such label; 375 / 768 / 1280 × EN / ZH ×
   dark / light show no page-level horizontal scroll and every demoted module's named landing
   reachable from 375; keyboard-only path reaches every card and disclosure, the ladder exposes
   per-cell counts, contrast is ≥ 4.5:1 for card text in all four theme-language combinations, and no
   meaning is carried by colour alone.

### V6 Position review

#### Question

For one holding: *what did I believe when I bought this, what actually filled, what
has changed factually since, what has it contributed, and what is the next condition that makes me
review it?* (MASTERPLAN §10.2, row "Position review".) It carries Q1, Q2 and Q5 for a single entity,
and it is the landing page for every cross-view entry point listed in §2 ("a held ticker in V1
opens V6; a queued row in V3 and a pending verdict chip in V1 both open V6 on the same holding").

#### Archetype

C — Instrument Analyzer, composed *inside* the G (Monitor) shell, per art direction
§2. The shell's since-stamp answers "what changed"; V6 answers "what is true of this lot". C's
identity device is a decision header plus a dated lifecycle/task tabset, which is exactly the shape
the existing `toggleExpand` panel already has (`index.html:4988-5002`, the `.mm-thesis-panel`
`div` opened at `:4855`). Promoting that in-page disclosure to a linkable route is the IA
proposal in §2 and is a `SEAT DECISION`; this view's content spec holds either way, because the
panel and the route must render the same tree.

#### Information hierarchy

| Tier | Contents |
|---|---|
| **1 · answer** | Ticker + security name · **two separate status slots** (local thesis, provider plan — TR-P1) · shares held · weight · entry basis vs current mark with `quote_source`/`quote_as_of` · unrealized P&L and % · the #1707 queued-change chip + `.mm-q-when` timing line when a change is classified · the freshness stamp + valuation-basis provenance (E12) |
| **2 · support** | Original thesis (summary + why-now) · Stage 0–4 + time stop + thesis amendments since entry (S7 — the subsequent factual changes) · the actual-fills blotter for this ticker · entry-risk levels (`published_stop`, `buy_zone`) · contribution over a stated window (E11) · realized P&L from closed sells |
| **3 · depth** | Case for / case against · vetoes · divergences · falsifier box · sizing rationale · `confluence` / `prob_correct` · Research Desk gate block and paper link · `open[]`/`closed[]` position-log rows · the decision-snapshot inspector (CR-R6 → #1357, operator-gated only) · the 6-dim confirmation scorecard (S2) · evidence items (S4) · accountability/Sizing Scorecard cards |

#### Fields

Owner is the domain that must publish the value, not the file that happens to emit it
today. "Display when null" is the §3 rule: the word, muted, never a number — except where a row
below names a narrower correct behaviour.

| Field | Meaning | Owner | Source today (API + JSON path) | Type / units | Nullable? | Display when null / unknown |
|---|---|---|---|---|---|---|
| `ticker` | holding symbol | PRODUCT | `/api/portfolio` `positions[].ticker`; `/api/live_marks` `positions[].ticker` (`app/web.py:1152-1153`) | string | no | n/a — a position row without a ticker is a contract error, not a row |
| `security_name` | display name | PRODUCT | `_attach_security_names`, `app/web.py:2370`; rendered `index.html:4843` | string | yes | omit the sub-line; the ticker is the answer |
| `shares` | shares held now | ECON | `/api/live_marks` `positions[].shares` — `paper_account.positions_pnl`, `portfolio/paper_account.py:1711-1736` | number, shares | no (`0` is real) | `0` renders as `0` — a closed lot is a lot with zero shares, not "unavailable" |
| `avg_cost` / `cost_basis` | true entry basis | ECON | `positions_pnl.avg_cost` (`paper_account.py:1725`); `app/web.py:1157-1158` republishes it as `cost_basis`; rendered `index.html:4818` | number, book ccy | yes | entry cell `Unavailable`; never `$0.00` |
| `current_price` | latest mark | ECON | `positions_pnl.current_price` (`paper_account.py:1726`) | number, book ccy | yes | mark cell `Unavailable`; weight, unrealized and P&L all become `Unavailable` in the same row — one missing mark quarantines the derived cells, never zeroes them |
| `market_value` | shares × mark | ECON | `positions_pnl.market_value` (`paper_account.py:1727,1732`) | number, book ccy | yes | `Unavailable` |
| `unrealized_pnl` / `unrealized_pct` | open contribution | ECON | `positions_pnl.unrealized_pnl/.unrealized_pct` (`paper_account.py:1728-1729,1733-1734`); rendered `index.html:4849` via `pnlCell` | number, book ccy / % | yes | `Unavailable`, no colour, no sign |
| `quote_source` / `quote_as_of` / `quote_time_kind` / `quote_stale_days` | mark provenance | ECON | `app/web.py:1161-1166` | string / ISO date / enum / integer days | yes | `quote_source` absent renders the `Behind` state with the last settled stamp (§3) |
| `weight` | share of book | PRODUCT | `positions[].weight`; rendered `index.html:4846` | fraction 0–1 | yes | `Unavailable`; the allocation bar does **not** redistribute the remainder |
| `sleeve` | Leadership / Conviction / Cash | PRODUCT | `positions[].sleeve`; `.mm-sleeve-chip` `index.html:4844` | enum | yes | chip omitted |
| `stage` | DOCTRINE Stage 0–4 | RESEARCH | `positions[].stage`; rendered `index.html:4845` (`DOCTRINE.md:62-72`) | integer 0–4 | yes | `Unavailable` — never coerced to 0, which would read "latent" |
| `opened_at` / `held_days` | holding age | ECON | `/api/trades` `open[].opened_at`, `open[].held_days` — `portfolio/position_log.py:326-327`; rendered `index.html:4809-4811` | ISO date / integer days | `opened_at` yes, `held_days` yes | age sub-line omitted; `time_stop_by` still renders if present |
| `entry_weight` / `current_weight` | weight at entry vs now | ECON | `position_log.py:328-329`; not rendered today — `_heldPendingChange` reads the pending-target row's own `current_weight` (`index.html:4775`) and does not draw it | fraction | yes | `Unavailable` |
| `time_stop_by` | **the existing next-review date** | RESEARCH | `/api/trades` `open[].time_stop_by` — `portfolio/position_log.py:331` (ledger stamped at `:179`) | ISO date | yes | this is the one review trigger PRODUCT can render **today**; when null the review-condition slot falls back to `Unavailable` and is never derived from `held_days` |
| `published_stop` / `buy_zone` | published entry-risk levels | ECON | `position_log.py:334-335` (echoed from `_levels` at `:157-161`) | number / [number, number] | yes (absent on legacy rows) | `Unavailable`; the stop line names which of the three stops is bound (DOCTRINE.md:115-124) |
| `thesis_id` | thesis episode id | RESEARCH | `position_log.py:332` | string | yes | see `local_thesis_status` below |
| `verdict` | manager stance on the lot | PRODUCT | `positions[].verdict`; `index.html:4804` reads it with a `'hold'` default | enum `hold\|add\|trim\|reduce\|avoid\|watch\|exit_pending` | yes | **must** render `Unavailable`, not `HOLDING` (census TV-18) |
| queued change `kind` | accepted, classified change to a held lot | RESEARCH → target, PRODUCT render | `_heldPendingChange()` between `PBR-HELD-PENDING-CHANGE:BEGIN/END` (`index.html:4717-4780`); consumed at `:4828-4841`; `data-queued-change` on the row | enum `exit\|trim\|add\|unclassified` | yes | no chip; the row is the book verdict alone |
| queued `fill_after` / `queued_at` | when the queued change can fill | RESEARCH → target, calendar-derived | `index.html:4766-4767` reads `row.fill_after` then `pending_target.fill_after`; rendered as `.mm-q-when` `index.html:4836-4838` | ISO-8601 with offset / UTC | yes | `.mm-q-when` renders the existing `pend.awaiting_lbl` = "awaiting settlement" / "等待结算" (`index.html:3294`) — never an invented date |
| `thesis_full.summary` / `.why_now` / `.sizing_rationale` (+ `_zh`) | the original thesis text | RESEARCH | `/api/portfolio` `positions[].thesis_full.*`; zh cache assembled `app/web.py:1441-1446`; rendered `index.html:4884-4893` | string | yes | the thesis block is omitted and the status slot carries the reason; no empty panel shell |
| `thesis_full.bull[]` / `.bear[]` (+ `_zh`) | the two-sided case | RESEARCH | `app/web.py:1448-1455`; rendered `index.html:4895-4910` | string[] | yes (empty array is a real answer) | today's explicit "no bull points" `li` (`index.html:4903`) stays; it is an answer, not a gap |
| `thesis_full.vetoes[]` / `.divergences[]` | standing objections | RESEARCH | rendered `index.html:4913-4923` | string[] | yes | section omitted; the omission is not an error |
| `thesis_full.what_would_prove_wrong` (+ `_zh`) | free-text falsifier | RESEARCH | `app/web.py:1445`; rendered `index.html:4927-4930` | string | yes | box omitted |
| `thesis_full.confluence` / `.prob_correct` | sizing numbers | RESEARCH | rendered `index.html:4934-4948` under a `!= null` guard | number | yes | block skipped entirely |
| `research.{engine_score,research_score,combined,viability,summary,summary_zh,mode,paper_id}` | the gate block that sized this buy | RESEARCH | `app/web.py:1433-1438`; rendered `index.html:4860-4878` | number / enum / string | yes | block omitted; `paper_id` never renders a dead "view full paper" link |
| `history[]` (this ticker) | **actual fills** | ECON | `/api/trades` `history[].{date,ticker,action,shares,price,exit_price,realized_pnl,realized_pct}` — `portfolio/trade_history.py:31-180`; rendered `index.html:5115-5134` | number / ISO date | per-cell | per-cell `Unavailable` |
| `realized_pnl`, `realized_pct` (per sell) | realized contribution | ECON | `history[].realized_pnl` — FIFO reader; requested with basis at `CONTRACT REQUEST → E10` | number, book ccy / % | buys | buy rows show `—` (a buy has no realized P&L; that is an answer, not a gap) |
| contribution over a window | **loss/gain contribution** | ECON | `CONTRACT REQUEST → E11` `{ticker, window_start, window_end, contribution, contribution_basis: realized\|unrealized\|both, priced_through}` | array; fraction of book NAV at window start | holding with an unqualified mark → `contribution: null` + reason | `Unavailable` with the named reason; the window selector defaults to inception-to-date and is **stated**, never implied |
| `local_thesis_status` | whether a local thesis exists | RESEARCH | `CONTRACT REQUEST → S1` (slot 2 of 2) | enum `present\|absent\|amended` | yes | slot renders `Unavailable` independently |
| `provider_plan_status` | whether an optional provider (Prophet) plan exists | RESEARCH | `CONTRACT REQUEST → S1` (slot 1 of 2) | enum `held_with_active_plan\|held_without_active_plan\|absent` | yes | slot renders `Unavailable` independently |
| `horizon_end` / `review_condition` / `next_review_at` | **next review condition** | RESEARCH | `CONTRACT REQUEST → S5`, extending the renderable `time_stop_by` above | ISO date / string | yes | `Unavailable`; never derived from holding age |
| `amendments[]` | **subsequent factual changes** — every amendment to this position's thesis after entry | RESEARCH | `CONTRACT REQUEST → S7` `{amendment_id, ticker, decision_id, effective_at, old_conditions, new_conditions, reason, evidence_refs[]}` | array; `effective_at` ISO-8601 UTC | no — empty array is a real answer (never amended) | delivered + empty → `Empty — no amendments since entry.` / `暂无 — 建仓后未修订。`; not yet delivered → `Unavailable`; never inferred by diffing `thesis_full` |
| `scorecard[]` | the 6-dim confirmation scorecard (DOCTRINE; catalyst gates full size) | RESEARCH | `CONTRACT REQUEST → S2` `{dim, score, evidence_ref}`×6 | array of 6; RESEARCH-named scale | per dim | Tier 3; a missing dim is listed by name as `Unavailable`, never zero-filled; the catalyst dim is never implied from position size |
| `evidence[]` | the evidence items behind the thesis | RESEARCH | `CONTRACT REQUEST → S4` `[{claim, source, asof, observed\|inferred}]` | array | empty | Tier 3; `Unavailable` until delivered; `inferred` items keep the `(unverified)` / `（未核实）` tag in both languages |
| `valued_at_cost[]` / `nav_basis` | valuation-basis provenance for the header | ECON | `CONTRACT REQUEST → E12` (`portfolio/self_directed.py` `book()` / `mark()`) | array / enum `marked\|includes_cost_fallback` | empty array, never absent | ticker in `valued_at_cost[]` → the header provenance line reads `Valued at cost — no market mark` / `按成本计价 — 无市价` and unrealized P&L renders `Unavailable` (a cost fallback is not a mark); not yet delivered → provenance line `Unavailable` and the header makes no qualified claim |
| `open[]` / `closed[]` (position log) | thesis history per position | RESEARCH / ECON | `/api/trades` `open[]`, `closed[]` (`app/web.py:2352-2353, 2375-2376`) — **payload only, rendered nowhere today** | array of objects | array | Tier 3 lifecycle rail stays `Unavailable` until consumed; the payload already exists, so this is a render task, not a contract |
| decision snapshot | the decision that set this lot | RESEARCH | `CONTRACT REQUEST → S1.decision_id`; inspector is #1357's surface per CR-R6 (`PRODUCT_CONTRACT_REQUESTS.md` §Requests answered) | object | yes | **never rendered for an anonymous viewer** — the row itself does not draw, and no lock affordance appears (see §2 Pro gating: no `TierLock` today) |

#### Layout

The three breakpoints from §3, recomposed rather than squeezed.

| Breakpoint | Module order | Demoted → named landing |
|---|---|---|
| **1280** | 1 V6 decision header (two status slots · shares · weight · entry → mark · unrealized · queued chip · freshness stamp · valuation basis (E12)) → 2 Original thesis (summary, why-now, sizing rationale) → 3 **Actual fills** blotter, L1 capped at 8 rows → 4 Contribution over the stated window → 5 lifecycle rail (`open[]`/`closed[]`, Stage 0–4, time stop, and S7 amendments as dated rail events — the subsequent factual changes) | case for/against, vetoes, divergences, falsifier, confluence, 6-dim scorecard (S2), evidence items (S4), Research Desk block, accountability cards → the same disclosure stack below, opened by keyboard and touch |
| **768** | 1 header (unchanged) → 2 Original thesis (summary + why-now; sizing rationale collapses into it) → 3 Actual fills blotter, L1 capped at 6 rows → 4 Contribution → 5 Review condition | the lifecycle rail becomes a single line: `Stage 3 · time stop 2026-11-05` linking to the full rail; everything in the 1280 demotion list moves under **Details** |
| **375** | 1 header, reflowed to: ticker + name → status slots → mark + P&L → shares/weight → queued chip + timing line → freshness stamp + valuation basis (E12) → 2 Original thesis, `summary` only, `why_now` in the disclosure → 3 next review condition (`time_stop_by` or `Unavailable`) → 4 fills, L1 capped at 4 rows → **See all N fills** | contribution, lifecycle rail (with S7 amendments), case for/against, scorecard (S2), evidence (S4), Research Desk, accountability → each gets a named row under **Details**; the blotter scrolls inside its container, the page never scrolls horizontally |

Row-cell composition at 375 is a recomposition, not a squeeze: `mm-hide-sm` cells (sleeve, stage, entry, mark, rs, confluence, held-since — `index.html:4844-4853`) demote into the header's stacked key/value lines with their labels, so a demoted number is never silently dropped.

#### States

Every state below names a **field-level trigger**, the exact EN + ZH copy from the §3 canonical vocabulary, and what still works. Copy is not invented per view: the labels are §3's; only the sentence after the label is view-specific.

| State | Trigger (field-level) | EN / ZH copy + visual treatment | What still works |
|---|---|---|---|
| **loading** | any of `/api/portfolio`, `/api/live_marks`, `/api/trades` unresolved for this ticker | `Loading` / `加载中`; skeleton at the final geometry of the header and the blotter; **no placeholder prose** — no `—`, no `$0.00`, no sample thesis | the G-shell since-stamp and the book switcher |
| **empty** | `_trades.history[]` has no row for this ticker and the lot has no fill evidence (a lot seeded by account-only injection, `app/web.py:1388-1420`) | `Empty` / `暂无` + "This holding has no recorded fills on this book." / "该持仓在本组合没有成交记录。" Full-weight sentence, never an empty table frame | position identity, weight, mark, P&L, thesis, queued chip — everything except the fill column |
| **stale** | `quote_stale_days ≥ 1`, or `positions[]` is older than the page stamp | `Behind` / `滞后` + the last settled as-of (`quote_as_of`) + the age in days; no colour change on the number itself | the last settled observation, with its date, per §3 |
| **partial** | some Tier-2/3 sources resolved and others did not (e.g. `/api/trades` ok, `/api/live_marks` failed) | `Partial` / `部分` + **what is excluded**, named: "Contribution and fills are unavailable; the holding and its thesis are current." | everything not named in the sentence; the view never implies the missing part is zero |
| **error** | the read for this ticker failed (`data.error` on `/api/trades`, `app/web.py:2386`) | `Couldn't load` / `加载失败` + what failed + what still works + a **retry** control that refetches this ticker only | the rest of the book in V1; the retry never reloads the page |
| **closed-market** | `market_status.session ≠ open` (venue books report their own exchange — `app/web.py:2355-2362`) | `Market closed` / `休市` + next open time; the mark cell carries the carried label | entry basis, fills, thesis, contribution over closed history, time stop |
| **benchmark-unavailable** | n/a — V6 renders no benchmark comparison. A per-name relative-to-benchmark figure is **out of scope by design**; if one is ever added it obeys the rule: the word, never a dash alone | — | — |
| **provisional valuation** | the mark used for this position is carried: A02 `carried[]` carries `{ticker, price, price_asof, age_days, ...}` (ECON A02, `_pbr_inputs/ECON_CONTRACTS_PR1699.md` §a) | `Provisional` / `暂定` + the carried name and its age: "MU priced from the 2026-10-21 close, 1 day old" — the exact sentence E3 was written for | the unrealized figure, **labelled** provisional; it is never presented as a qualified mark, and it is never zeroed |
| **withheld valuation** | A02 `WITHHELD`: ≥1 UNPRICED held line (ECON A02 §a table) | `Withheld` / `暂不估值` + the reason from `nav_withheld.jsonl` `{date, mark_source, unpriced[], carried[], reason}` (E5). For V6 specifically: **mark, market value, unrealized P&L and unrealized % are all withheld together** | shares, weight, entry basis, fills, thesis, time stop, contribution basis as realized-only |
| **unverified (pre-A02 row)** | a `nav_history` row written before A02 landed has no `nav_status` | `Unverified` / `未核实` — label only, never upgraded to qualified | the row renders with the label and no inference |
| **queued (pending while held)** | `pending_target.status == 'queued'` and a row names this ticker with a classified action (PR #1707, merged) | chip: `EXIT QUEUED` / `已排队卖出` (`pos.q_exit`, `index.html:3450`), class `exit_pending` (`index.html:348`); trim/add/unclassified use `pos.q_trim` `TRIM QUEUED` / `已排队减仓`, `pos.q_add` `ADD QUEUED` / `已排队加仓`, `pos.q_unclassified` `CHANGE QUEUED` / `已排队调整` (`index.html:3451-3453`). Timing line `.mm-q-when` (`index.html:353`) = "at open <date>" (`pend.fills_at_lbl` "at open" / "开盘", `:3293`) or "awaiting settlement" / "等待结算" (`:3294`). Row carries `data-queued-change` (`index.html:4839`) | **shares, mark, P&L, weight, sleeve, held-since and the thesis row are unchanged** — nothing is filled until the next open (`index.html:4826-4827`). After the fill the row loses the chip and V3 gains the `filled` disposition; see V3 Truth rules |
| **unavailable** | any CONTRACT REQUEST field not yet delivered | the word, muted, in the value slot (§3): `Unavailable` / `不可用`. Applied to: the local-thesis slot, the provider-plan slot, contribution, review condition, `published_stop`, amendments (S7), scorecard (S2), evidence (S4), valuation basis (E12) — **each independently**, never inferred from a sibling | everything already delivered; two `Unavailable` slots side by side never collapse into one "no thesis" |

#### EN / ZH

Bilingual pairs that already exist in the app are marked *shipped*; the rest are the
spec's own copy, with the ZH shaped natively rather than as a literal of the English.

| Element | EN | ZH | Note |
|---|---|---|---|
| Status slot 1 label | Local thesis | 本地论点 | TR-P1; label names the slot so the two can never be read as one |
| Status slot 1 · present | Thesis on file | 已有论点 | slot value |
| Status slot 1 · absent | **No thesis** | **无论点** | the only copy that may say this; reserved for `local_thesis_status = absent` |
| Status slot 2 label | Provider plan | 供方方案 | TR-P1 |
| Status slot 2 · `held_without_active_plan` | **No active provider plan** | **无有效供方方案** | the MU regression case; must never read "no thesis" |
| Next review | Next review | 下次复核 | label for the review-condition block |
| Time stop | Time stop by <date> | 时间止损 <date> | from `time_stop_by`; ZH keeps the doctrine's term |
| Stage | Stage <0–4> | 阶段 <0–4> | digits stay Latin in ZH |
| Actual fills | Actual fills | 实际成交 | blotter heading |
| Entry basis | Entry basis | 成本价 | `cost_basis` / `avg_cost` |
| Current mark | Mark | 现价 | |
| Contribution | Contribution | 贡献 | E11 |
| Window label | <start> → <end> | <start> → <end> | dates stay numeric in both |
| Falsifier box | What would prove this wrong | 证伪条件 | `what_would_prove_wrong` |
| Amendments | Amendments since entry | 建仓后修订 | S7; dated events on the lifecycle rail |
| No amendments | Empty — no amendments since entry. | 暂无 — 建仓后未修订。 | S7 delivered and empty |
| Scorecard | Confirmation scorecard | 确认评分卡 | S2; six dims, a missing dim is named |
| Evidence | Evidence | 证据 | S4; inferred items tagged `(unverified)` / `（未核实）` |
| Valued at cost | Valued at cost — no market mark | 按成本计价 — 无市价 | E12 header provenance line |
| Case for / against | Case for · Case against | 看多理由 · 看空理由 | existing two-column block, `index.html:4895-4910` |
| Queued chip labels | *shipped* `EXIT QUEUED` / `TRIM QUEUED` / `ADD QUEUED` / `CHANGE QUEUED` | *shipped* `已排队卖出` / `已排队减仓` / `已排队加仓` / `已排队调整` | `index.html:3450-3453` |
| Timing line | *shipped* `at open <date>` / `awaiting settlement` | *shipped* `开盘 <date>` / `等待结算` | `index.html:3293-3294` |

ZH conventions that bind this view: market direction flips (red = up) but **health and epistemic
status never flip** — a `Provisional` label is `--warn` in both languages and a queued exit is
epistemic/queued chrome, not a market-direction number. No forced uppercase in ZH beyond the
shipped chip strings. Tickers stay Latin in both. The count ladder/lifecycle rail uses native ZH
stage names rather than English stage labels.

#### Accessibility

- **Contrast pairs.** Body text `--text` on `--panel`/`--panel2`; secondary `--muted` on `--panel` (both themes ship ≥4.5:1 at the sizes used — §3 owns the measurement; this view uses no other pairing). State words use `--muted` for `Unavailable` **plus** the word itself, never colour alone. The queued chip reuses `exit_pending`'s `color-mix` on `--down`/`--panel2` (`index.html:348`) with a 1px `--line`-weight border as its ≥3:1 boundary; the `.mm-q-when` line (`index.html:353`) is `--muted` at 11px and must clear 4.5:1 against the surface it actually paints on — the raised expanded row (`--link` 10% mix on `--panel`, `index.html:5002`) is a different surface and is measured separately.
- **Focus order.** Ticker (opens V6 from V1) → status slots (text, not focusable) → mark/P&L → queued chip (focusable only if it links to V3) → time stop / review condition (links to the lifecycle rail) → blotter header → blotter rows → each `<details>` summary. The #1707 timing line is cell text inside the verdict cell, not a focus stop.
- **Keyboard / touch path.** The panel opens with <kbd>Enter</kbd>/<kbd>Space</kbd> on the position row (today `onclick="toggleExpand(i)"`, `index.html:4842` — the spec requires that handler on real button semantics, `aria-expanded` + `aria-controls` pointing at the `expand-<i>` row it already owns, `index.html:4856`). Every Tier-2/3 disclosure is a styled `<details>`: <kbd>Tab</kbd>-reachable, <kbd>Enter</kbd>/<kbd>Space</kbd>-operable, and tappable at ≥40×40px (preferred 44px). Touch never depends on hover — falsifier and evidence affordances have a focus/tap equivalent (`DS_states-accessibility.md`: hover-only evidence is noncompliant).
- **Motion.** Any mark-age pulse respects `prefers-reduced-motion`; V6 adds no motion of its own. `:focus-visible` uses `--focus-ring` (`theme.css:29`) on every interactive element including blotter rows and disclosure summaries. Exactly one `h1` per view; V6's entity name is the `h2` under the V6 route heading.

#### Density

Tier 1 budget: the decision header plus at most two supporting modules above the fold — Original thesis and Actual fills. Nothing else. L1 table caps **8 rows at 1280, 6 at 768, 4 at 375**, each followed by a counted `See all N fills` / `查看全部 N 笔成交` (§3 §5). Never at Tier 1: case for/against, vetoes, divergences, the falsifier, `confluence`/`prob_correct`, the Research Desk block, accountability cards, raw provenance, or the decision-snapshot inspector. Mechanics live behind disclosures. The view is one entity so the header has no row cap, but it never grows past nine labelled values at 375.

#### Truth rules

Applicable acceptance sentences, quoted verbatim from MASTERPLAN §10.2, plus the
CR-R2 and seat-accepted rules that bind this view.

1. "A natural-language explanation cannot overrule the actual account." — The thesis block, the
   provider-plan slot and the decision snapshot are rendered *below* the account values and may not
   change any figure above them. A memo saying "MU is held" cannot restore a row the account no
   longer holds, and a memo saying "no plan" cannot blank the local thesis slot.
2. "A queued MU exit must show as a pending change while MU is still held." — Bound to the
   `data-queued-change` chip on the held row (PR #1707) and to the V3 pending row; the V6 copy is
   the "what still works" column of the queued state: shares and marks are unchanged until the fill.
3. "Do not visually reward a missing-price flat line as low volatility or a tiny closed-position
   sample as a winning strategy." — Applied twice here: a carried mark renders `Provisional` with
   the carried name and age, never as a flat day; and any win-rate figure that appears in this view's
   blotter or its accountability cards always shows its `n` and is withheld below the minimum
   closed-sample size (SEAT DECISION below).
4. **TR-P1 (CR-R2).** `provider_plan_status` and `local_thesis_status` are separate slots.
   `held_without_active_plan` renders "no active provider plan", never "no thesis"; "no thesis" is
   reserved for `local_thesis_status = absent`; each slot renders `Unavailable` independently until
   its field ships and neither is inferred from the other.
5. **Seat-accepted — flat day.** A day change computed from fewer than two distinct marks, or
   written before the open, renders `Unavailable`, never `+0.00%`. V6 inherits this wherever it
   shows a per-position day change; the fill blotter never shows a day-change column derived from a
   single mark.
6. **Seat-accepted — missing is not zero.** Missing values never coerce to 0 (`app/web.py:1341`
   cash coercion; `CONTRACT REQUEST → E7`); `avg_cost` absent renders `Unavailable`, not `$0.00`,
   and `stage` absent renders `Unavailable`, not `0`.

#### Acceptance checklist

1. **API/DOM agreement** — every V6 header value (shares, weight, entry, mark, unrealized P&L and %) equals `/api/live_marks` `positions[]` and `/api/portfolio` `positions[]` to the rendered precision — API-vs-DOM agreement test over a seeded account.
2. **TR-P1** — a holding with `local_thesis_status: present` and `provider_plan_status: held_without_active_plan` renders "Thesis on file" **and** "No active provider plan", and the DOM contains no "no thesis" / `无论点` — DOM-text assertion test.
3. **TR-P1 independence** — with `local_thesis_status` undelivered and `provider_plan_status` `absent`, the slots render `Unavailable` and "No active provider plan" and neither reads from the other — unit test on the render function.
4. **Queued-while-held** — a `queued` `pending_target` naming the held ticker `exit` renders `EXIT QUEUED` / `已排队卖出`, a `.mm-q-when` "at open \<date\>" line, `data-queued-change="exit"`, and shares/mark/unrealized/weight byte-identical to the pre-queue render — agreement test + 1280 screenshot.
5. **Queued direction never guessed** — a queued `unpriceable` / `comparison_unavailable` row renders `CHANGE QUEUED` / `已排队调整` and no direction word — DOM assertion test.
6. **Unknown ≠ 0** — `avg_cost: null` renders `Unavailable` in the entry cell and no `$0.00`; `stage: null` renders `Unavailable` and no `0` — unit test.
7. **Withheld quarantine** — an A02 `WITHHELD` date renders `Withheld` / `暂不估值` with its reason and mark, market value, unrealized P&L and % are withheld together — no number in any of the four — unit test.
8. **Provisional carries a name and an age** — a carried mark renders `Provisional` / `暂定` plus the carried ticker and `age_days`; the sentence is not optional — DOM assertion test.
9. **Review condition** — `time_stop_by` present renders the date under "Time stop by \<date\>"; absent renders `Unavailable` and **never** derives a date from `held_days` — unit test.
10. **Breakpoints** — 1280 / 768 / 375 screenshots of the same seeded holding; at 375 the header recomposes to ticker → status slots → mark/P&L → shares/weight → queued chip → stamp, the blotter caps at 4 rows, there is no horizontal scrollbar, and every demoted module has a named landing.
11. **EN/ZH** — the full state matrix renders in both languages, including `EXIT QUEUED`/`已排队卖出`, `Provisional`/`暂定`, `Withheld`/`暂不估值`, `Unavailable`/`不可用`; direction colour flips for market P&L only and queued/provisional labels do **not** change hue with language.
12. **Accessibility** — keyboard-only traversal from the V1 ticker into every V6 disclosure, visible `:focus-visible` on each, correct `aria-expanded`, 200% zoom at 375 preserving the task, every state word readable with colour removed.
13. **A11y measurement** — ≥4.5:1 text and ≥3:1 boundaries in **both** dark and light, measured on the painted surface (`--panel`, `--panel2` and the raised expanded row) and recorded as contrast-tool screenshots, not asserted from hex.
14. **Empty and error** — a holding with no fills renders the §3 `Empty` sentence with its reason; a failed read renders `Couldn't load` naming what failed, what still works, and a retry scoped to this ticker.
15. **Closed market** — a closed session renders `Market closed` / `休市` plus the next open, and entry basis, fills, thesis and time stop all stay readable.

### V7 Operations

#### Question

*Is the book being maintained on schedule, and when it is not, what exactly is late,
failed or partial — with the full technical trace one layer below, for an operator, not for the
reader?* (MASTERPLAN §10.2, row "Operations".) It is the Q5 limb: the evidence and limitations behind
the manager's behaviour, including the machinery's own honest failures.

#### Archetype

A — Command Center, inside the G shell: verdict → change rows → action → deep links.
Today those four items exist but are scattered — `#runs` is a collapsed panel at the foot of the SPA
(`index.html:2895-2903`), the scheduler and Desk lanes are **Flagship-only in the UI**
(`index.html:6550-6551`) and flagship is archived (`portfolio/registry.py:33-45`), so an operator on
the product book cannot reach job-level delay at all (census gap map, V7). The view's identity device
is therefore *the disposition line*: one word per cycle, in #1711's vocabulary, with the change that
caused it beneath.

#### Information hierarchy

| Tier | Contents |
|---|---|
| **1 · answer** | The book stamp (last decision, last attempt, next scheduled) · one **per-cycle disposition** word from #1711's vocabulary · feed health in one line · the `unavailable` fallback when no lifecycle projection is wired |
| **2 · support** | The bounded "what changed" list: cycles whose disposition is `failed`, `rejected` or `incomplete_uncertain`, newest first, ≤8 rows + counted `See all N` · settlement receipts that block marks · scheduled-opportunity status |
| **3 · depth (operator-only)** | Per-run step traces (`/api/runlog`) · the scheduler job table · the Decision-Snapshot inspector (#1357 surface, CR-R6) · raw evaluation-record JSON · `/market_view` and `/agenda` as named external landings |

The operator/detail split is a **channel boundary, not a tier**: Tier 3 never renders in an
anonymous session, and its absence is not a lock affordance (§2 Pro gating: this process has no
entitlement gate at all). An anonymous reader sees Tier 1 + Tier 2 with the detail links absent.

#### Fields

| Field | Meaning | Owner | Source today (API + JSON path) | Type / units | Nullable? | Display when null / unknown |
|---|---|---|---|---|---|---|
| lifecycle projection | the disposition, per cycle | RUNTIME | `CONTRACT REQUEST → R1` `{run_status, last_decision_at, last_attempt_at, next_scheduled_at, failure_reason_code, halted_by}` | object; ISO-8601 UTC | `run_status: "unavailable"` when no projection exists | the whole Tier-1 disposition strip renders `Unavailable` / `不可用` + "Lifecycle projection is not wired for this book." Until R1 ships, **V7 shows `unavailable` — never `ok`** |
| per-cycle `disposition` | RUNTIME #1711's per-cycle disposition word | RUNTIME | `CONTRACT REQUEST → R6` `cycles[].{cycle_at, disposition}`, enumerated below | enum of 8 (§EN/ZH table) | never | `unavailable` when no projection is wired; there is no `unknown` member of this enum |
| `failure_reason_code` | why a cycle failed | RUNTIME | `CONTRACT REQUEST → R1` | enum/string | yes | `Unavailable`; the change row still renders with its disposition word |
| feed health | provider/feed liveness | RUNTIME | `CONTRACT REQUEST → R3` `[{feed, status: live\|stale\|down, asof, stale_after_s}]` | array; seconds | empty array → `unavailable` | `Unavailable` — an empty array is not "all feeds healthy" |
| settlement receipt | a retained receipt that blocks marks | RUNTIME | `CONTRACT REQUEST → R4` `{receipt_id, status: retained\|finalised, retained_reason}` per book | object | null when none | line omitted; its absence is never read as "no blocker" without the receipts row also being present |
| `jobs[].{id,last_status,last_severity,last_started,last_finished,last_skipped,last_reason,last_target_status,next_run_time}` | per-job scheduler health | RUNTIME | `/api/scheduler` `jobs[]` — `app/web.py:3539-3552`, `app/scheduler.py` `scheduler_health()`; rendered `index.html:5565-5600` | enum / ISO-8601 | yes (both clocks render `—` today) | `Unavailable`; today the empty list already renders "Scheduler not available…" — that is the correct §3 `unavailable` copy |
| `[].{run_id,ts,kind,title,title_zh,n_steps,cost_usd,summary,summary_zh}` | run list | RUNTIME | `/api/runs` — `app/web.py:3071-3093`; rendered `index.html:4304-4345` | string / number (USD) | `title` falls back to `run_id`, then `—`; `cost_usd` omitted when absent | title fallback chain is an existing, honest answer and stays |
| `steps[].{ts,type,title,detail}` | full step trace per run | RUNTIME | `/api/runlog?run_id=` — `app/web.py:3096-3103`; lazy fetch `index.html:4380` | array | 500 → `{run_id, steps: [], error}` | `Couldn't load` + "the step trace failed" + retry that refetches the same `run_id` only; other runs stay readable |
| `expected_opportunity.status` | was today's run scheduled at all | RUNTIME | `/api/portfolio?view=decision_availability` `expected_opportunity.status` — `app/decision_availability.py:538`; text `index.html:7410` | enum; permanently `unknown` with `reason: "scheduler_evidence_not_bound"` | not nullable | renders the existing footer sentence, which already says **unverified**. The spec keeps that sentence and adds no optimism |
| evaluation record status | is the forward-evaluation record qualified | ECON | `/api/forward-evaluation` `status`, `latest_asof`, `snapshot.{asof,book,schema,cohort.evaluation_start,nav_date_basis}`, `observation_qualification.*` — `app/web.py:1652-1679`, `portfolio/forward_evaluation.py:1840-2020`; rendered `index.html:7501-7611` | enum | yes | every unverified dimension renders `Unverified` / `未核实` — label only, never upgraded |
| raw evidence record | the JSON behind that record | ECON | the "Inspect evidence record" link, `index.html:7604` | object | yes | operator-only channel (Tier 3) |
| decision snapshot | the decision internals | RESEARCH | #1357's router per CR-R6 (`app/decision_snapshot.py` mounted in `app/main.py`, gated on `app.auth.is_operator_authorized`, denied by `app/response_cache.py`) | object | yes | **never drawn for an anonymous viewer**; #673's inline handler must not ship whichever PR lands first |
| market-view planes | macro plane coherence | RESEARCH | `/api/market_view` `planes{}`, `serving_freshness.current_confirmation_available`, `label_vs_planes.*`, `assembly.*`, `brief`, `coverage`, `built_at` — `app/web.py:1777-1804` | object | 404 `{available:false,note}` | `Unavailable` + the note; assembly counts must not render `0 fresh, 0 stale, 0 missing` (census TV-15) |
| agenda items | the ranked improvement queue | RESEARCH | `/api/agenda` `items[].{rank,title,evidence,suggested_fix,fix_type,expected_impact,owner,age_weeks,readiness}`, `n_items`, `owners`, `class_counts`, `as_of`, `schema_version` — `app/web.py:1807-1831`; rendered `agenda.html:300-400` | array + counters | 404 → `{available:false,note}` | `Unavailable` subtitle + note; `n_items: 0` from a failed read is never shown as "0 items" |
| `health` / `ready` | deploy + runtime probe | RUNTIME | `app/main.py:196-218` `_runtime_health()` `app/main.py:140-195` — `status`, `paper_only`, `scheduled_runtime_ok`, `reasoning_policy_ok`, `commit`, `serve_only`; **no page renders these today** | object | yes | Tier 3 only; an honest `"degraded"` is displayed as `degraded`, never smoothed to `ok` |

#### Layout

| Breakpoint | Module order | Demoted → named landing |
|---|---|---|
| **1280** | 1 disposition strip (three facts + the disposition word) → 2 feed-health line → 3 bounded change list, L1 ≤8 rows → 4 settlement receipts → 5 scheduled-opportunity sentence → **Operator detail** drawer | per-run traces, scheduler job table, snapshot inspector, evaluation raw JSON → **Operator detail**, one disclosure, operator-gated |
| **768** | 1 disposition strip → 2 feed-health line → 3 change list, ≤6 rows → 4 scheduled-opportunity sentence | receipts fold into the change list as a row kind; **Operator detail** becomes a button that opens the same drawer |
| **375** | 1 disposition strip, stacked: disposition word first, then last decision / last attempt / next scheduled → 2 feed health → 3 next-action line (the change list's newest row) → 4 **See all N changes** | everything else under **Details**, opened by tap; operator detail is a single row that is **absent**, not disabled, in an anonymous session |

Every Tier-3 module has a named landing: **Operator detail → Run traces · Scheduler jobs · Decision snapshot · Evaluation record**, and **Operator detail → /market_view**, **→ /agenda** as external links. Nothing disappears silently; absence of operator authority renders no row, and no row ever renders a lock.

#### States

| State | Trigger (field-level) | EN / ZH copy + visual treatment | What still works |
|---|---|---|---|
| **loading** | `/api/runs` or `/api/scheduler` in flight | `Loading` / `加载中`; skeleton at the disposition strip's final geometry | the G-shell book stamp and navigation |
| **empty** | `runs == []` and `jobs == []` | `Empty` / `暂无` + the reason: "No runs recorded for this book yet." / "本组合暂无运行记录。" — the existing `.mm-empty` + `runs.empty` treatment (`index.html:4308-4310`, key at `:3383`), which already names the reason | the disposition strip still renders its `unavailable` word for the lifecycle projection |
| **stale** | `latest_attempt_at` older than the expected cadence, or the evaluation record's `status: stale_after_error` | `Behind` / `滞后` + the last settled as-of; **no green** — staleness here is a schedule fact, not a health verdict | the last settled observation, dated; the change list keeps its prior rows |
| **partial** | some Tier-2/3 sources resolved and others did not (e.g. runs ok, scheduler failed) | `Partial` / `部分` + what is excluded: "Scheduler detail is unavailable; run history is current." | everything not named |
| **error** | `/api/runs` returns 500 (`app/web.py:3093`), or a 404 `{available:false,note}` from `/api/market_view` or `/api/agenda` | `Couldn't load` / `加载失败` + what failed + what still works + retry | the book stamp; the disposition strip, which is fed by R1, not by `/api/runs` |
| **closed-market** | `market_status.session ≠ open` | `Market closed` / `休市` + next open time | every operational fact — a closed market is not a failed schedule, and the two never share a colour or a word |
| **benchmark-unavailable** | n/a — V7 renders no benchmark comparison | — | — |
| **provisional valuation** | n/a — V7 renders no valuation | — | — |
| **withheld valuation** | n/a — V7 renders no valuation. A withheld mark surfaces here only as a **feed-health** fact under R3, carrying its reason rather than a number | — | — |
| **unverified (pre-A02 row)** | an evaluation-record dimension outside the shipped schema | `Unverified` / `未核实`, label only — this is the state the existing footer sentence already reports for `expected_opportunity` (`app/decision_availability.py:538`, shipped text `index.html:7410`) | the rest of the record |
| **queued (pending while held)** | n/a in V7 — the queued chip belongs to the held row (V1/V3/V6, PR #1707). V7 **links** to it and never re-renders it, so the chip can never disagree between views | — | — |
| **unavailable** | no lifecycle projection is wired (R1), or `R3` is an empty array, or R4 is null | the word, muted (§3): `Unavailable` / `不可用` + "Lifecycle projection is not wired for this book." / "本组合尚未接入运行周期投影。" L-P4 renders exactly this against a documented stub. **It never renders `ok`** | the page stamp, the run list and every already-delivered field |

**#1711 disposition vocabulary.** Exactly these eight members plus the §3 `unavailable`. No member
is invented and no identifier is renamed: the `disposition` value is the contract and the test key
and is never printed raw. The EN and ZH labels are PRODUCT display copy mapped 1:1 from it. Four EN
labels differ in wording from their identifier (`started` → `Running`, `accepted_no_change` →
`Accepted · no change`, `accepted_change` → `Accepted · change applied`, `incomplete_uncertain` →
`Incomplete · uncertain`); that mapping is §9 seat decision 11. The non-colour cue is what carries
the meaning if colour is unavailable.

| `disposition` | EN label | ZH label | non-colour cue | one-line meaning in this view |
|---|---|---|---|---|
| `not_due` | Not due | 未到时间 | plain text, no chip | the cycle has not come round yet — nothing is late |
| `disabled` | Disabled | 已停用 | struck step icon, `--muted` | the cycle is switched off for this book; a disabled cycle is **not** a failure |
| `started` | Running | 运行中 | in-progress marker, no animation under reduced motion | in flight; no outcome is implied |
| `accepted_no_change` | Accepted · no change | 已接受 · 无变更 | plain text, no chip | the cycle ran and correctly left the book alone |
| `accepted_change` | Accepted · change applied | 已接受 · 已执行变更 | checkmark glyph + change row | the cycle ran and its target reached the account |
| `rejected` | Rejected | 已否决 | cross glyph, `--warn` | the cycle ran and its decision was **not** accepted; this is a normal outcome, not an error |
| `failed` | Failed | 失败 | cross glyph + `--act` | the cycle ran and broke; `failure_reason_code` names why |
| `incomplete_uncertain` | Incomplete · uncertain | 未完成 · 存疑 | dashed outline + the word `uncertain` | the cycle's outcome is not knowable; **never** counted as accepted and never rendered as a neutral success |
| *(no projection wired)* | `Unavailable` | `不可用` | §3 muted word | R1 has not shipped; nothing is asserted about any cycle |

#### EN / ZH

The disposition table above carries both languages for the eight #1711 members. The
remaining view-specific pairs:

| Element | EN | ZH | Note |
|---|---|---|---|
| View title | Operations | 运行状态 | the §2 IA proposal; today `#runs` reads "Brain Activity — Full Trace" / "脑波活动 — 完整追踪" (`index.html:4300`) |
| Disposition strip label | Cycle disposition | 周期处置 | the answer's label |
| Last decision / last attempt / next scheduled | Last decision · Last attempt · Next scheduled | 上次决策 · 上次尝试 · 下次计划 | three facts, one line at 1280 |
| Feed health | Data feeds | 数据源 | R3 line |
| Change list | What changed | 变更明细 | the bounded list |
| More link | See all N changes | 查看全部 N 条变更 | counted, never unlabelled |
| Operator detail | Operator detail | 运维详情 | the Tier-3 drawer; absent, not disabled, for an anonymous reader |
| Run traces / Scheduler jobs | Run traces · Scheduler jobs | 运行追踪 · 调度任务 | drawer rows |
| Decision snapshot | Decision snapshot | 决策快照 | #1357 surface only |
| Evaluation record | Evaluation record | 评估记录 | existing `index.html:7501-7611` |
| Unverified footer | Scheduled opportunity status is unverified | 计划机会状态未核实 | the sentence already shipped at `index.html:7410`; kept verbatim |

ZH conventions: a disposition is a **status**, not a market direction, so it never takes the
ZH direction flip; `accepted_change` keeps its checkmark glyph and the same ink in both languages;
machine ids (`run_id`, `feed`, `failure_reason_code`) stay Latin; no forced uppercase on ZH labels.

#### Accessibility

Contrast: disposition words use `--text` on `--panel` with the glyph as the
non-colour cue, so the whole row is legible without hue; `failed` uses `--act` ink plus a cross;
`incomplete_uncertain` uses a dashed outline **plus** the word, never a muted colour alone;
`unavailable` uses `--muted` plus the word. Feed status chips meet ≥3:1 on their boundary and ≥4.5:1
on their text. Focus order: disposition strip → feed-health line → change-list rows (each linking to
the run that caused it) → counted `See all N` → the scheduled-opportunity sentence (static) →
**Operator detail** summary → each drawer row. Every Tier-3 disclosure is a styled `<details>`
reachable by <kbd>Tab</kbd> and operable by <kbd>Enter</kbd>/<kbd>Space</kbd>; run traces load
lazily on expand (today `index.html:4380`) and their load state is announced through the existing
`aria-live` region. Touch targets ≥40×40 (preferred 44). `prefers-reduced-motion` removes the
`started` progress animation and leaves the word `Running`. No hover-only affordance anywhere —
every step-trace detail is a tap target.

#### Density

Above the fold: the disposition strip plus at most one supporting module (the feed-health
line or the newest change). Change list L1 cap **8 rows at 1280, 6 at 768, 3 at 375**, each followed
by a counted `See all N changes`. Run list L1 cap **8 runs** with the existing `showMoreRuns()`
ladder (`index.html:4344-4347`). Never at Tier 1: the scheduler job table, per-run step traces, the
snapshot inspector, raw evaluation JSON, market-view planes, the agenda, or the health probe.

#### Truth rules

Applicable acceptance sentences, verbatim from MASTERPLAN §10.2, plus the rules that
bind this view.

1. "A natural-language explanation cannot overrule the actual account." — A run summary, a Desk
   verdict or an agenda item is **Tier 2/T3 narrative**. It may explain a disposition; it may not
   change the book, and it may not be promoted into Tier 1 above the disposition word. The existing
   `/api/activity` and research-paper join read the archived flagship tree under a product book's
   holdings (census TV-10, `app/web.py:2947`, `:2980`, `:1912`); until that is fixed, V7 must not
   present that narrative under this book's stamp at all.
2. "Do not visually reward a missing-price flat line as low volatility or a tiny closed-position
   sample as a winning strategy." — `accepted_no_change` is rendered in **plain text with no chip**,
   so "nothing changed" never reads as success; and `incomplete_uncertain` is never grouped with the
   accepted dispositions in any count.
3. **Seat-accepted — missing is not zero.** An empty `jobs[]` from a failed read is `Unavailable`,
   never "every job healthy"; missing assembly counts render `Unavailable`, never
   `0 fresh, 0 stale, 0 missing` (census TV-15, `market_view.html:414,427`); a missing
   `session.state` never renders `closed` (census TV-19, `index.html:8730-8736`) — it renders the
   §3 `unavailable` word.
4. **Seat-accepted — closed is not failed.** `Market closed` / `休市` and a failed disposition use
   different words, different cues and different copy; neither implies the other.
5. **CR-R6.** Any decision-snapshot inspector this view references is #1357's surface —
   operator-gated on `app.auth.is_operator_authorized`, denied by `app/response_cache.py`, never
   anonymous. No inspector is drawn for an anonymous viewer, and no lock affordance is drawn in its
   place (§2 Pro gating).

#### Acceptance checklist

1. **API/DOM agreement** — the disposition word, the three stamp facts and the feed statuses equal the R1/R3 payloads to the rendered text — API-vs-DOM agreement test.
2. **Vocabulary closure** — the disposition cell renders only the eight #1711 members or `Unavailable`; a DOM assertion fails on any other string — unit test.
3. **Unavailability before R1** — with R1 unwired the strip renders `Unavailable` / `不可用` and **never** `ok`, `Running` or any cycle claim — unit test.
4. **Uncertainty is not acceptance** — an `incomplete_uncertain` cycle is excluded from every count of accepted cycles and never styled as accepted — unit test.
5. **Closed ≠ failed** — a closed session with a healthy schedule renders `Market closed` / `休市` and no failure word appears anywhere in the DOM.
6. **Unknown ≠ 0** — a failed `/api/scheduler` renders `Unavailable` and not an empty healthy table; a failed `/api/agenda` renders `Unavailable` and not `0 items`; a missing `session.state` renders `Unavailable` and not `closed`.
7. **Operator channel** — in an anonymous session the Operator detail row is **absent** (not disabled, not locked) and no `/api/decision-snapshot` request is issued — DOM assertion + network assertion.
8. **Operator detail for an authorized operator** — the drawer opens, `/api/runlog?run_id=` is fetched lazily on expand, and a 500 renders `Couldn't load` with a retry scoped to that `run_id` only.
9. **Error path** — `/api/runs` 500 renders `Couldn't load` / `加载失败` naming what failed, what still works (the book stamp and the disposition strip) and a retry control.
10. **Breakpoints** — 1280 / 768 / 375 screenshots of the same seeded degraded book; at 375 the disposition word is the first painted element, the change list caps at 3 rows with a counted `See all N`, and there is no page-level horizontal scroll.
11. **EN/ZH** — all eight dispositions plus `Unavailable` render in both languages; `failed` and `incomplete_uncertain` do **not** change ink with language; ids stay Latin in ZH.
12. **Accessibility** — keyboard-only path from the book switcher into every Tier-2/3 disclosure, visible `--focus-ring` on each, every disposition legible with colour removed, 200% zoom at 375 preserving the task, ≥4.5:1 text and ≥3:1 boundaries in dark and light.
13. **Narrative containment** — with `/api/activity` returning flagship-tree content while the product book is active, that narrative does not appear under this book's stamp — seeded-payload DOM test.

---

## 5. Truth rules (acceptance sentences, verbatim)

MASTERPLAN §10.2, quoted exactly. Each binds specific views; each has one concrete test. A rule is
not satisfied by the API alone — the API being truthful while the rendered view contradicts it is the
defect the census found on TR2.

| # | Acceptance sentence (verbatim) | Binds | Concrete test |
|---|---|---|---|
| **TR-A** | "A natural-language explanation cannot overrule the actual account." | V1, V2, V5, V6, V7 | Seed a payload whose memo asserts a holding the account does not carry. API/DOM agreement test: the holding list, cash and NAV render from `account` only; no narrative string appears in a Tier-1 slot. V7 variant: the `/api/activity` flagship-tree narrative does not appear under a product book's stamp (census TV-10). |
| **TR-B** | "A queued MU exit must show as a pending change while MU is still held." | V1, V3, V6 | Seed `pending_target.status = "queued"` with a row naming the held ticker `exit`. Assert `data-queued-change="exit"`, the chip `EXIT QUEUED` / `已排队卖出`, and a `.mm-q-when` line; assert shares, mark, unrealized and weight are unchanged from the pre-queue render. After the fill is posted, assert the chip is gone and the row shows the settled verdict. **Status: fixed on master by PR #1707 (merged).** |
| **TR-C** | "An unavailable benchmark displays unavailable rather than zero." | V1, V4 | With `series[].spy_nav` null at every point, assert the benchmark tile renders the word `Benchmark unavailable` / `基准不可用` (never `0`, `—` alone or a downward arrow) and the curve legend does not name a reference series that is not drawn (census TV-20). |
| **TR-D** | "Do not visually reward a missing-price flat line as low volatility or a tiny closed-position sample as a winning strategy." | V1, V4, V6, V7 | (a) Seed two `nav_history` rows with identical `nav`/`cash`/`invested` on consecutive dates; assert the day change renders `Unavailable`, never `+0.00%`. (b) Seed `n < 30` closed trades; assert the win rate renders with its `n` **and** the withheld label, never a bare percentage. (c) Assert `accepted_no_change` renders with no success chip. |

---

## 6. Truth violations to fix first

From `PRODUCT_CENSUS.md` §Truth violations, restricted to those fixable **without a new field** —
i.e. a display or coercion fix in code that already receives the honest value. Status of the two the
packet names:

- **TR2 (queued exit on a still-held row) — FIXED.** Mastermind PR #1707 is merged on master
  (`dce821e0`): `_heldPendingChange` (`index.html:4717-4780`) drives the verdict cell
  (`:4828-4841`) with `pos.q_exit` / `pos.q_trim` / `pos.q_add` / `pos.q_unclassified`
  (`:3450-3453`) and `.mm-q-when` (`:353`). No further action; the spec above binds to it.
- **Self-directed fabrication — IN FLIGHT.** Mastermind PR #1719 (open; not on this checkout)
  makes `/api/self_directed` and `/api/self_directed/history` return `status: "unavailable"` with
  every money field `null` when the book cannot be read, and the Self-Directed header renders
  "Unavailable" / "不可用" with a muted value and a **static muted heartbeat dot** (replacing the
  animated `mmhb` pulse at `index.html:1564`). The server half `app/web.py:2424` is the fabrication;
  `CONTRACT REQUEST → E13` remains open for the silent `_load_account()` fallback that keeps it
  unreachable.

The rest, with the exact display rule that fixes each. Every row ships with a DOM assertion.

| # | Violation (census row) | Exact display rule that fixes it |
|---|---|---|
| 1 | Client-side repeat of the $1,000,000 invention — `index.html:6068` falls back to `1000000` when `nav` is absent | With #1719 landed, `#sd-nav` renders the §3 `Unavailable` word in `--muted` and the heartbeat dot takes the static muted class. Until then: delete the fallback so the seed `$1,000,000` static value (`index.html:3113`) is replaced by the word, never by a fabricated number. (Companion to E13.) |
| 2 | Missing sleeve weights render a definite 0% split — `index.html:4516-4518` (`(sl.leadership \|\| 0)`) | Render a segment only for a non-null weight; an absent weight contributes **no segment** and its legend entry reads `Unavailable`. The bar never sums to 100% on a partial payload and no zero-width segment is drawn. (Sibling `gross` already hides its label when null, `index.html:4532`.) |
| 3 | Safety tiles coerce missing metrics to 0 — `index.html:4606`, `:4610` | `Effective names` and `Cash buffer` use the existing `num()`/`pc()` null path, which already returns `'—'`; remove the `|| 0` so they join it. Display rule: `Unavailable` + "risk snapshot unavailable", never `0 actual` / `0.0%`. |
| 4 | **Win rate with no sample gate — `index.html:5087-5093` and `:6242`** (V6/V3) | Always render `n` beside the rate: `57% · n = 42 closed` / `57% · 已平仓 n = 42`. Below the minimum closed-sample size (SEAT DECISION: **n ≥ 30**) render the label instead of the rate: `Sample too small (n = <n> closed)` / `样本不足（已平仓 n = <n>）`. Never a bare percentage. |
| 5 | Mislabelled comparison — `index.html:3967`, `:7674` read a SPY-named field under a CSI-300/Hang-Seng label | Drop the alias fallback; when the two keys differ, render the value under the benchmark the server actually used, or `Benchmark unavailable`. The number is currently un-wrong because the server publishes both keys from one value (`performance_projection.py:599-600`), so this is a defect in the alias, fixed by removing it. |
| 6 | Missing `availability` leaves no qualification line — `index.html:3877`; `_archived_performance` returns no `availability` key at all (`app/web.py:205-225`) | When `availability` is absent, the NAV label renders with the §3 `Unverified` label rather than plain "NAV", so a frozen archived mark is never presented as a current qualified NAV. |
| 7 | `_archived_performance` fabricates `+0.00%` — `app/web.py:190-196` (`day_change_pct = 0.0`, `total_return_pct` default) | Return `None` for both, as the active-book path already does (`performance_projection.py:283` and `:288`). Display rule: the day change and total return render `Unavailable`. **This is the seat-accepted flat-day rule** and is the code half of TR-D(a). |
| 8 | Pre-inception synthetic points drawn as a solid `--up` line — `index.html:4040-4046`, `:4173-4175` | Draw synthetic points as a dashed, `--muted` segment excluded from `allVals` (`index.html:4077`), so a long flat `$1M` tail cannot compress the realised range. The existing inception baseline, `START` marker and "recorded since …" legend stay. |
| 9 | `/api/pfolio/positions` publishes `day_pnl: 0.0` when holdings exist but quotes do not — `app/pfolio.py:357-359`, `:382-383`; rendered `portfolio.html:676-686` | Publish `null` instead; the Desk renders `Unavailable` for day and total P&L. Sibling fix for the same rule: `portfolio.html:681,686` styles `parseFloat(null)` → `NaN` as negative (red); the null path must take the neutral `.neu` class, never `.neg` (census TV-13). |
| 10 | Calibration reliability buckets with no observations draw a 0-width bar — `index.html:5429-5430` | An empty bucket renders an absent/`—` bucket, not a bar pinned at 0%. |
| 11 | Market-view assembly counts print `0 fresh, 0 stale, 0 missing` — `market_view.html:414`, `:427` | Render `Unavailable` for a missing count; `0 fresh, 0 stale, 0 missing` must not be reachable from an absent `assembly` object. |
| 12 | A missing `pricing` block asserts holdings completeness — `index.html:8806` (`0 === 0`) | `holdingsComplete` requires the `pricing` block to be **present**; absent → the SPA keeps its cached positions and renders `Partial` naming the exclusion. |
| 13 | **Verdict default fabricates a manager stance — `index.html:4804` (`(p.verdict \|\| 'hold')`)** (V6) | An absent `verdict` renders the §3 `Unavailable` word in the verdict cell, never `HOLDING`. The account-only rows that carry an explicit `"verdict": "hold"` (`app/web.py:1388`) are unaffected — that is why the defect is currently invisible. |
| 14 | Unknown session state renders `closed` — `index.html:8730-8736` (V7-adjacent; the market clock feeds every view) | An unmapped `session.state` renders `Unavailable`, never `closed` / `休市`; a clock failure must not hide behind an ordinary closed market. |
| 15 | Curve legend always names the benchmark as a reference series — `index.html:4029` (TR-C) | The legend names a reference series only when at least one `series[].spy_nav` point is finite; otherwise the legend says `Benchmark unavailable` / `基准不可用`. |

---

## 7. Contract requests

The full ledger is `_pbr_inputs/PRODUCT_CONTRACT_REQUESTS.md`; this is the subset V6 and V7 consume plus every id
this spec mints (R6, S6–S9), with the display rule each one binds. E4 and E6–E9 are consumed by
V1–V4 and cited at the field where each binds. **Display until delivered is always the §3 `Unavailable` state
— the muted word in the value slot, never a number, a zero, a placeholder dash or an inferred
value.** No row below is a request for new design; rows marked *(A02)* / *(A12)* are consumption
requests against the shape ECON already published in #1699.

### To ECON

| Field | Type | Nullable | Units | Provenance / known-at | Needed by | Display until delivered |
|---|---|---|---|---|---|---|
| E1 `nav_status` *(A02)* | enum `QUALIFIED\|PROVISIONAL` | absent on pre-A02 rows | — | `paper_account.valuation()`; post-open | V6 Provisional/Withheld state | `Unverified` / `未核实` on a pre-A02 row |
| E2 `nav_qualified` *(A02)* | number | null when PROVISIONAL | book ccy | same | V6 provisional block | the label only, no number |
| E3 `carried[]` *(A02)* | array of `{ticker, price, price_asof, age_days, source, value, weight_of_invested}` | empty array, never absent once A02 lands | book ccy; days | same | V6 `Provisional` sentence; V4 limitations | `Unavailable` + "mark provenance unavailable" |
| E5 `nav_withheld.jsonl` *(A02)* | per-book file, `{date, mark_source, unpriced[], carried[], reason}` | file absent → no withheld dates | shares, last observed price | `paper_account.mark()` | V6 `Withheld` state; V4 curve gap | `Unavailable`, and the mark stays withheld |
| E10 `fills[].realized_pnl`, `cost_basis_method` | number / enum | null for buys | book ccy | settlement | V6 fill blotter + the win-rate gate | per-row `—` (a buy genuinely has none) |
| E11 per-holding attribution over a stated window | array `{ticker, window_start, window_end, contribution, contribution_basis, priced_through}` | a holding with an unqualified mark → `contribution: null` + reason | fraction of book NAV at window start | settlement + A02 marks | **V6 loss/gain contribution** | `Unavailable` with the named reason |
| E12 `valued_at_cost[]`, `nav_basis` | array / enum `marked\|includes_cost_fallback` | empty array, never absent | book ccy | `portfolio/self_directed.py` `book()` / `mark()` | V1/V6 header provenance | `Unavailable`; the NAV carries no qualified claim |
| E13 typed error for an unreadable self-directed account | contract behaviour | n/a | — | `portfolio/self_directed.py` `_load_account()` | V1 Self-Directed header; **#1719 ships the API half** | PR #1719's `status: "unavailable"` header — never `$1,000,000` / 100% cash |

### To RUNTIME

| Field | Type | Nullable | Units | Provenance / known-at | Needed by | Display until delivered |
|---|---|---|---|---|---|---|
| R1 lifecycle projection per book | object `{run_status, last_decision_at, last_attempt_at, next_scheduled_at, failure_reason_code, halted_by}` | `run_status: "unavailable"` when no projection | ISO-8601 UTC | RUNTIME lifecycle store | **V7 Tier-1 answer** | `Unavailable` / `不可用` — never `ok` |
| R2 `next_eligible_session` | object `{session_open_at, market, reason}` | null when not queued | ISO-8601 with offset | market calendar + scheduler | V3 queued row; V6 `.mm-q-when` | the shipped `awaiting settlement` / `等待结算` |
| R3 feed health | array `[{feed, status, asof, stale_after_s}]` | empty array → `unavailable` | seconds | feed-health gate | **V7 feed line** | `Unavailable` — an empty array is not "all healthy" |
| R4 settlement receipt | object `{receipt_id, status, retained_reason}` per book | null when none | — | `bot/settle.py` | **V7 receipts row** | row omitted; never read as "no blocker" without the receipts row |
| R5 `price_evidence` wiring | dependency record, not a field | — | — | `app/scheduler.py:1300-1390` | prerequisite for E1 = QUALIFIED | PRODUCT records the dependency only |
| **R6 (new)** per-cycle disposition record | array `cycles[]` of `{cycle_at, disposition}` | array empty → `unavailable` | ISO-8601 UTC; disposition from RUNTIME #1711's eight-member enum | RUNTIME lifecycle store, same origin as R1 | **V7 disposition word** | `Unavailable` — no cycle is asserted at all |

### To RESEARCH

| Field | Type | Nullable | Units | Provenance / known-at | Needed by | Display until delivered |
|---|---|---|---|---|---|---|
| S1 per-holding thesis | object `{ticker, thesis_summary, probability, check_by, falsifier, stage 0–4, decision_id, asof, **local_thesis_status**, **provider_plan_status**}` | holding without a thesis → `unavailable` | probability 0–1; date | decision ledger | **V6 original thesis + both TR-P1 slots** | each slot `Unavailable` **independently**; neither inferred from the other |
| S2 6-dim confirmation scorecard | array `{dim, score, evidence_ref}`×6 | missing dims listed, never zero-filled | RESEARCH-named scale | scorecard engine | V6 Tier 3 | the named dims are listed as missing; absent dims are never 0 |
| S3 per-name exit rationale for a queued exit | object `{ticker, decision_id, exit_reason_code, narrative, asof}` | null → the queued row shows the exit without a rationale | — | decision ledger | V3; V6 queued chip's tooltip | chip renders with no rationale line — the queue is never withheld because a reason is missing |
| S4 evidence items | array `[{claim, source, asof, observed\|inferred}]` | empty | — | research layer | V6 Tier 3 | `Unavailable`; inferred items stay tagged |
| S5 horizon + review condition | object `{ticker, horizon_end, next_review_at, review_condition, decision_id}`, extending the already-renderable `time_stop_by` (`portfolio/position_log.py:331`) | absent → `unavailable`, **never derived from holding age** | date; ISO-8601 UTC | decision ledger / thesis store | **V6 next review condition**; V2 horizon | `Unavailable` in the review slot |
| **S6 (new)** unchanged-book reason | object `{code, text, text_zh, decision_id, asof}`; code enum `new_book\|no_fresh_evidence\|risk_hold\|protective_carry\|target_unchanged\|no_cash\|unavailable` | null when no decision explains the book | ISO-8601 UTC; text | decision ledger, protective-carry / hold branch | **V2 "why unchanged"**; V7 | `Unavailable` — never inferred from the memo or from `latest_attempt_kind` |
| **S7 (new)** thesis amendment record per position episode | array `{amendment_id, ticker, decision_id, effective_at, old_conditions, new_conditions, reason, evidence_refs[]}` | empty array — a never-amended thesis is a real answer, not a gap | ISO-8601 UTC; text | decision ledger, written when a thesis changes | **V6 "subsequent factual changes"** (census gap map V6: today only divergence chips and a stale memo exist) | `Unavailable` for the change list; the original thesis stays exactly as filed, and a revised thesis never retroactively redefines an earlier prediction |
| **S8 (new)** finalist source coverage | object `{sources[]: {source, status, asof}, coverage_complete}` | per-source nullable | ISO-8601 UTC; boolean | research layer, per finalist | **V5 coverage word** | `Unavailable`; a finalist row shows `Coverage unavailable` / `来源覆盖不可用` |
| **S9 (new)** entry readiness | object `{status: enterable\|blocked\|unknown, blockers[], price_asof, next_session_at}` | null → `Unavailable` | enum; ISO-8601 UTC | RESEARCH + market calendar | **V5 readiness slot** | `Unavailable` — **never** inferred from score, confluence or a veto list |

---

## 8. DESIGN-SYSTEM-GAPs

Numbered G1–G10 (G10 added in the r1 repair); the index below the table maps every name used in §1–§4. Each is a real need this spec raises that the
canonical inventory (`DS_components.md`) does not cover **and** that the Mastermind app does not ship
— the app carries no `.mx-*` namespace, so a gap is also a place where the binding must land in
`app/static/theme.css` / `app/static/index.html` instead.

| Gap | Why it is needed |
|---|---|
| `DESIGN-SYSTEM-GAP G1: tier gate lock primitive` (`.mx-tier-gate`) | Referenced in §2: the canonical lock primitive has **no app equivalent**, and `TierLock` is listed in `DS_components.md` for completeness only. No view draws it today because this process has no entitlement gate (`app/auth.py:132-141`, `:436-438`); the gap exists so that if an edge paywall is ever proven, lock is a labelled channel separate from data truth rather than a page-local colour. |
| `DESIGN-SYSTEM-GAP G2: type scale tokens` | Raised in §1 / §4 V1: the canonical `--fs-*` / `--fs-num-*` scale has no counterpart in `app/static/theme.css`, which defines only the three font families; every size is a literal per rule. |
| `DESIGN-SYSTEM-GAP G3: metric tile with a null explanation` | `DS_components.md` `.mtile` requires "null gets explanation, never bare em-dash". The app's `.mm-perf-stat` (`index.html:3120`) renders a bare `—`, and truth-violation rows 3 and 9 above are exactly this gap. Needed in V6 (entry, mark, P&L), V7 (feeds, receipts) and V1. |
| `DESIGN-SYSTEM-GAP G4: counted overflow affordance` | Raised in §4 V1/V2: the density law requires a counted `See all N`; the app has no such component and `PF_GATED_ONLY` hides whole panels instead of counting rows. |
| `DESIGN-SYSTEM-GAP G5: skeleton loader at true final geometry` | The app ships `.mm-empty` and prose loaders (`index.html:2899`, `:4310`) but no skeleton primitive. §3 and `DS_states-accessibility.md` both require `loading` to be a skeleton at final geometry with **no placeholder prose**; without it, `Loading run history…` and a seed `$1,000,000` are the same class of fabrication. |
| `DESIGN-SYSTEM-GAP G6: lifecycle rail` | `DS_components.md` `.mx-rail` is a chronology by weight/surface. V6 needs one for Stage 0–4 + entry + time stop + amendments (the doctrine's stage lifecycle, `DOCTRINE.md:62-72`), V3 needs one for the single queued target's chronology (accepted → queued → fill window → settled, historical stages non-actionable), and V7 needs one for cycle dispositions. The app has `#runs` (a collapsible list) and nothing that reads as a chronology; the S7 amendment list has no primitive at all. |
| `DESIGN-SYSTEM-GAP G7: operational disposition chip family` | `.mm-verdict-chip` (`index.html:338-348`) is bound to *position verdicts* and `.mm-side-chip` to *order sides*. V7's eight #1711 dispositions are a third, different enum with a different semantic axis (did the machine work, not what should we hold). Reusing the verdict chip would make `accepted_change` look like an investment opinion. Needs its own primitive bound to `--warn`/`--act`/`--muted` with glyph cues. |
| `DESIGN-SYSTEM-GAP G8: evidence lens (hover + focus + tap)` | `DS_components.md` LENS `data-tip-en/zh` has no app equivalent; the app's evidence affordance is a raw-JSON link (`index.html:7604`) and inline title text. V6 needs a falsifier/evidence layer that opens by hover, keyboard **and** touch — `DS_states-accessibility.md` calls hover-only evidence noncompliant, and V7's failure rows need the same. |
| `DESIGN-SYSTEM-GAP G9: epistemic-qualification badge` | Raised in §4 V4: the A02 words QUALIFIED / PROVISIONAL / WITHHELD / UNVERIFIED must be a labelled word beside a value, not a freshness chip (`.dtp*` is scoped to freshness/session language); V1/V2/V4/V6 would otherwise each invent one. |
| `DESIGN-SYSTEM-GAP G10: count ladder` | `DS_components.md` `.mx-ladder` is V5's identity device: one exhaustive, disjoint accounting of `RESEARCHED n` · `FINALIST n` · `REJECTED n`, the active stage marked by weight and surface. The app ships `.mm-rej-grid` cards (`index.html:1239`) and no counted stage strip; without the primitive V5 would show three unrelated counters that need not sum. |

---

**Gap index (assembled).** G1 tier-lock primitive; G2 type scale tokens; G3 unavailable value slot (metric tile with a null explanation); G4 counted overflow affordance; G5 skeleton loader at true final geometry; G6 lifecycle rail; G7 operational disposition chip family; G8 evidence lens (hover + focus + tap); G9 epistemic-qualification badge; G10 count ladder. G1 and G3 merge the names parts of this spec used for the same need.

## 9. Seat decisions required

One line each: the question, this lane's recommendation, and the alternative.

1. **V1 route (SEAT DECISION, §2)** — merge `#performance`/`#alloc`/`#positions`/`#safety` into one view? **Recommend yes**, with `#safety` demoted to support-2, because "the account is the answer" (art direction §1) fails while four panels compete for the top of the page. *Alternative:* keep four panels and let V1 be a tab over them, which preserves the shipped IA but leaves no single answer above the fold.
2. **V2 route (SEAT DECISION, §2)** — promote `#decision-availability` from evidence panel to the page answer? **Recommend yes**; it is already the panel that carries the accepted decision and its consistency alerts. *Alternative:* keep the decision memo as the hero and the availability block as support-1, which reads more narratively and weakens the truth-first order.
3. **V3 route (SEAT DECISION, §2)** — split the pending block out of Trade History? **Recommend yes**; pending intent and settled fills are different questions and mixing them is what let TR2 hide. *Alternative:* keep one blotter with a filter, which costs no IA but keeps the queued/settled ambiguity on one screen.
4. **V4 route (SEAT DECISION, §2)** — give Performance its own route and take its as-of/strip with it? **Recommend yes**; a curve needs a wider canvas than a dashboard column and its qualification sentence needs to sit next to the curve, not above the fold of another view. *Alternative:* keep `#performance` in the V1 dashboard and let V4 be a deep link into it.
5. **V5 route (SEAT DECISION, §2; the same question as §4 V5 SEAT DECISION V5-A)** — expose the currently unreachable Opportunities view to the product book? **Recommend yes**, gated on fixing the `/api/research_papers` flagship-tree join (`app/web.py:1912`) first, so the product book never reads the archived gate. *Alternative:* leave V5 flagship-only and answer Q5 for the product book from V2 + V6 evidence panels only.
6. **V6 route (SEAT DECISION, §2)** — promote the `toggleExpand` disclosure to a linkable route? **Recommend yes**; a held ticker must be linkable from V1, V3 and a queued chip, and shareable, which an in-page disclosure cannot be. *Alternative:* keep it in-page and accept deep links as `#positions?expand=<idx>`, which is shareable but not keyboard-navigable as an entity.
7. **V7 route (SEAT DECISION, §2)** — a new operator-facing view per book, with the Desk/scheduler lanes un-gated from flagship? **Recommend yes**, with the operator detail behind an operator-gated channel and **absent** — never disabled, never locked — for an anonymous reader. *Alternative:* keep the Desk flagship-only and give the product book only the R1 disposition strip, which answers "was today late?" but not "why".
8. **Minimum closed-sample size for a win rate** — what n makes a win rate worth printing? **Recommend n ≥ 30 closed trades**, always printed as `57% · n = 42 closed` / `57% · 已平仓 n = 42`, and below it the label `Sample too small (n = <n> closed)` / `样本不足（已平仓 n = <n>）` with **no percentage at all**. *Alternative:* n ≥ 50 (slower to earn, harder to mislead), or print the rate with a "small sample" caveat (cheapest, but still puts a number where the eye rewards it — the thing TR-D forbids).

9. **`#positions` row cap (SEAT DECISION, §4 V1 Density)** — cap the shipped positions panel at 8 rows with a counted `See all N` landing on V6? **Recommend cap**; it is a behaviour change to a shipped panel, so it needs the seat. *Alternative:* keep the full table with in-panel scroll.
10. **`account_preview.starting_nav` default (SEAT DECISION, §4 V1 Fields)** — the `or 1_000_000.0` default at `app/web.py:1342` must stop being silent. **Recommend** render `Unavailable` / `不可用` when the book has no recorded starting NAV, the same rule PR #1719 applies to the self-directed book. *Alternative:* keep the default but label it `Assumed starting capital` / `假定初始资金` everywhere it feeds a return.
11. **V7 disposition display labels (SEAT DECISION, §4 V7)** — print #1711's dispositions through PRODUCT display labels (`started` → `Running`, `accepted_no_change` → `Accepted · no change`, `accepted_change` → `Accepted · change applied`, `incomplete_uncertain` → `Incomplete · uncertain`) or verbatim? **Recommend display labels**: the identifier stays the contract and the test key, and `Running` reads as a state where `Started` reads as an event. *Alternative:* title-case the identifiers (`Started`, `Accepted no change`, …), zero mapping but machine-sounding.

---

## 10. Browser acceptance plan

Two environments, both required. A journey that passes locally and is never re-run against the
real host is not accepted — the audit that commissioned this spec observed the Pro gate and did not
obtain that proof (MASTERPLAN §10.2, closing line).

### Local — serve-only, deterministic fixtures

| Matrix cell | What is captured |
|---|---|
| **375 and 1280** | Screenshot per view per state. 375 must show no page-level horizontal scroll, a recomposed (not squeezed) module order, and a named landing for every demoted module; 1280 must show the Tier-1 budget holding. 768 is captured where a row cap changes (V6 blotter 8→6, V7 change list 8→6). |
| **EN and ZH** | The same fixture rendered in both. Assert: every §3 state label has both languages; `EXIT QUEUED`/`已排队卖出` and `Unverified`/`未核实` appear as specified; market-direction colour flips under ZH while the queued, provisional and health inks do **not**; no forced-uppercase label is asserted in ZH. |
| **dark and light** | Both themes for every cell above, on `--bg`/`--panel`/`--panel2`. Recorded as pairs so a state label that only clears contrast in one theme is visible in the diff. |
| **state fixtures** | `loading` (slowed fixture), `empty`, `stale`, `partial`, `error`, `closed-market`, `benchmark-unavailable`, `provisional`, `withheld`, `unverified`, `queued-while-held`, `unavailable`. Each is a fixture, not a race — one capture per state per view. |
| **API/rendered agreement** | For every view, a scripted pass compares each rendered figure with the same figure in the JSON payload at the rendered precision. A mismatch anywhere is a failure, not a rounding note. |
| **truth acceptance** | The four §Truth rules acceptance sentences run as browser assertions: TR-B against a seeded queued target (including a `unpriceable` row rendering `CHANGE QUEUED`), TR-C with a null `spy_nav` series, TR-D(a) with identical consecutive `nav_history` rows and TR-D(b) with `n = 3` and `n = 42`. |
| **accessibility** | Keyboard-only traversal of every Tier-2/3 disclosure from the book switcher; `:focus-visible` visible at each stop; 200% zoom at 375 preserving the task; every state readable with colour removed; contrast measured on the painted surface in both themes. |

### Production — authenticated host, desktop and mobile

| Journey | Proof |
|---|---|
| **Authenticated desktop** | Full V1 → V6 → V3 → V2 → V7 traversal on the product book with a real session. Every number on screen is re-read from the live payload and compared; the operator-detail drawer opens for an authorized operator and the snapshot inspector is **absent** for an anonymous one. |
| **Authenticated mobile** | The same traversal at a real mobile viewport on real hardware: touch-only reachability of every disclosure and action, no hover dependency, no horizontal scroll, and the V6 header + V7 disposition word still first in the reading order. |
| **Auth isolation** | Two sessions on two books must never see each other's data through the SPA's cached payloads. Switching a book invalidates every cached per-book payload **before** the first paint of the new book, because the response cache key is path + canonicalised query only and carries no user and no session (`app/response_cache.py:72-83`, census §Auth + cache isolation). |
| **Cache isolation** | Same URL, different user and different book, within the cache TTL: the second response is never served from the first's entry. A cache-isolation failure is a severity-1 release blocker, not a UI defect. |
| **Operator gate** | The decision-snapshot inspector is reachable only through #1357's operator-gated router and is denied by the response cache; an anonymous request to it is refused. #673's inline handler is absent (CR-R6). |
| **Real data states** | On the live host, at least one run of each of `stale`, `partial`, `error` and `closed-market` is captured; where the day is genuinely quiet the capture must show the §3 state word, not a zero. |
