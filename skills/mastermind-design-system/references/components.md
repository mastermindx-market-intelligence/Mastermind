# Canonical component inventory

New shared primitives use the `.mx-*` namespace. Builders do not invent a parallel card system or local component vocabulary.

| Component | Canonical form / anatomy | Key constraint |
|---|---|---|
| PageShell / PageHeader | `_site_nav.html.j2` product family or `_public_nav.html.j2` anonymous/H/I family + footer + h1 | Only two shell families |
| VerdictHero | `.mx-vh`: eyebrow → verdict word → ≤14-word plain clause → stance verb → one freshness stamp → LENS receipt | Page-header/canvas tier; answer first |
| Section header | `.mx-sec`: eyebrow + real h2 + optional LENS + optional as-of | Never lose semantic outline |
| Surface / Panel | `.panel` E1 / `.panel2` E2; `.card` clickable variant | One answer per E1 panel |
| Metric | `.mtile`: label + tabular value + signed delta + micro tag | Null gets explanation, never bare em-dash |
| SignalCard | `.pvcard` for Prophet; generic signal = card + stance | Preserve scoped semantics |
| Quality block | `.qual2` | Two columns; no fused total row |
| Plan claim | `.plan-claim` | One savings/entitlement claim per plan card |
| DecisionRow | `.mx-chg-row`: name + ≤14-word change + stance + chevron | Two-line stack on narrow widths |
| Table | `.mx-tbl` | L1 ≤8 rows; tabular figures; internal scroll |
| Tabs | `.mx-tabset` | Parallel tasks; selected tab writes URL hash |
| Filter/ladder control | `.mx-ladder` only where sanctioned | Not a generic sitewide control |
| Status/Freshness | `.dtp`, `.dtp-chip`, `.dtp-asof` | Only freshness/session language |
| Tooltip/Evidence | LENS `data-tip-en/zh`, receipt fields | Must work on hover + focus/touch |
| ChartFrame | illus / `lib/illus.py` + `illus.css/js` | Every chart answers a stated question |
| Empty/Loading/Error/Stale | `.mx-empty` + `.mx-empty-why`, true-geometry skeleton, dtp behind states | Unknown never becomes zero |
| TierLock | `.mx-tier-gate` + measured tier ink | Violet = lock only |
| Callout | `.mx-callout`: quiet fill + even neutral border + strong text with labeled semantic status ink/icon | No colored container edge, stripe or relocated accent; preserve complete focus outlines |
| Detail disclosure | `.mx-disc` styled `<details>` | Summary says what is inside + why open |
| Icon | `_icons.html.j2` monoline set | 24×24, currentColor; no emoji UI icons |
| Buttons | `.gbtn` family | Reuse existing variants |
| Lifecycle rail | `.mx-rail` | Chronology by weight/surface, not colorful goodness |
| Count ladder | `.mx-ladder` headline device for Discovery Board | Exhaustive/disjoint stage cells; active by weight, never violet |

## Paper-observed component anatomy

The governed Paper dark/light component atlases visually confirmed these patterns:

### Verdict Hero

- small blue/wayfinding eyebrow
- large verdict word with semantic ink
- one plain explanatory clause
- one stance/action line
- settled/as-of receipt

### Count Ladder

Four-stage example: `EARLY → BUILDING → READY → ACTIVE`. Active state uses weight and surface emphasis rather than decorative hue.

### Interaction row

Explicit `Default / Hover / Focus / Disabled` controls plus a focusable decision row. Supported interaction state design belongs in the editable reference, not as late QA improvisation.

### Degraded/corrected states

- **STALE** — “Data is behind” + “Showing the last settled observation.”
- **ERROR** — “Feed unavailable” + what remains usable.
- **CORRECTED** — state that the observation changed and preserve original-evidence lineage.

### Lifecycle rail

Example stages: `Discovered / Researching / Ready / Tracking`. Chronology is not goodness. Historical stages remain non-actionable.

### Evidence Lens

Evidence card is visibly a deeper layer. It opens by hover, keyboard or tap; hover-only depth is noncompliant.

## New-component discipline

If a needed component is not here, return `DESIGN-SYSTEM-GAP`. A new primitive becomes canonical only through the design-system authority path, with dark + light + ZH + mobile and state coverage. Do not solve the gap with a page-local `:root`, a local card family or copied inline hex values.
