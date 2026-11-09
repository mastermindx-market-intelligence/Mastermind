---
name: mastermind-design-system
description: Use when designing, implementing, reviewing, or refactoring customer-facing Mastermind UI in an authorized Web, native Codex/Claude or Fabric assignment. Applies the Mastermind Product Design System: tokens, dark/light art directions, EN/ZH semantics, canonical components, A–I page archetypes, responsive reduction, degraded states, accessibility, density, and evidence-first interaction rules. Do not use for backend-only work with no user-facing UI.
---

# Mastermind Design System

Use this skill for every customer-facing Mastermind surface. The goal is **composition from the existing vocabulary**, not local redesign.

## Authority order

When sources disagree, use this order:

1. `docs/DESIGN_DOCTRINE.md` — user-facing content law.
2. `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` — visual/composition law.
3. `templates/theme.css` — production token and shared-component implementation authority.
4. Reference-integrity-approved archetype/component reference.
5. Live pages — evidence of current behavior, never precedent by themselves.
6. Paper — governed agentic composition/reference projection; useful for visual intent, component anatomy and code round-trip, but not a parallel token authority.

The extraction in this skill is pinned in `references/sources.md`. Re-read current repository law before making a durable production change if those sources have moved materially.

## Mandatory workflow

1. **Name the job before the page.** Identify the user's primary question, next decision/action, success condition and route family.
2. **Choose exactly one canonical archetype** from `references/archetypes.md`. If the job does not fit A–I (or the separately governed Terminal workspace), classify a product/IA gap. Do not create a page-local tenth archetype.
3. **Read `references/foundations.md` and `references/components.md`.** Compose only canonical primitives. A missing primitive is `DESIGN-SYSTEM-GAP`; do not invent a local token root, visual language, card family or ad-hoc component.
4. **Use production tokens, never literal styling.** Treat `tokens/mastermind.css` and `tokens/mastermind.tokens.json` as a portable reference projection. In the actual product, bind to the existing `templates/theme.css` variables/classes instead of copying this file over them.
5. **Design the answer first.** At Tier 1, show the state, what it means, and the useful stance/action in seconds. Put mechanics, methodology and receipts in LENS/details/Tier 3.
6. **Preserve the semantic channels.** Direction, health, action, provisional epistemic status and locked access are separate. Violet is lock-only. Health never flips. Market direction flips under ZH conventions.
7. **Prove the state matrix.** Apply `references/states-accessibility.md`: dark + light × EN + ZH × desktop + 390px mobile, plus relevant loading/empty/stale/partial/denied/error/corrected/success and interaction states.
8. **Treat mobile as re-composition, not squeezed desktop.** Keep answer + current evidence + next action; demote extra density to a named landing rather than silently deleting it.
9. **Do not use generated JSX as architecture.** It is implementation input. Integrate into existing components, data paths, auth, routing and state semantics.
10. **Before declaring UI work complete, verify the real journey.** Visual fidelity, keyboard/touch behavior, responsive layout, unhappy/degraded states and truthful data semantics are separate proof obligations.

## Fast design rules

- Apply the October 18, 2026 rule: **no colored container-edge accents**. Do not use colored left borders, inset stripes, pseudo-element rails or move the stripe to another edge. Use quiet fills, even neutral borders and explicit status/selection labels. Actual chart marks, neutral dividers and complete keyboard focus outlines retain their separate jobs.
- Treat skill loading as method availability, not a browser/Paper grant. Use the existing approved carrier and preserve its exact-target and uncertain-effect controls.
- Dark = **command center**: graphite, luminance depth, disciplined hairlines, instrument calm.
- Light = **research workspace**: cool canvas, white material, firmer hairlines, controlled shadow; never a mechanical inversion of dark.
- Hue is reserved for meaning. Otherwise use achromatic surfaces/text.
- Above 1440×900 fold: chrome + answer + at most two supporting modules.
- Default first-level section budget = 5; hard ceiling = 7.
- One canonical count per population per page; duplicates become slices/quotes/links.
- L1 tables show at most 8 rows, then a counted `See all N` landing.
- Exactly one h1; panel sections use h2.
- Hover-only information is noncompliant; evidence depth must open by keyboard/touch too.
- Loading is true-geometry skeleton. Empty is a sentence + why. Error says what failed + what still works + retry. Unknown is never rendered as zero.
- No emoji UI icons on migrated surfaces; use the monoline icon system.

## Read only what the task needs

- Foundations / color / type / density: `references/foundations.md`
- Component inventory and anatomy: `references/components.md`
- Route/page composition: `references/archetypes.md`
- States, responsive, accessibility: `references/states-accessibility.md`
- Exact Paper boards and extraction provenance: `references/paper-sources.md`
- Source precedence and pins: `references/sources.md`
- Practical patterns: `examples/patterns.md`
- Portable token payload: `tokens/mastermind.tokens.json`
- CSS projection: `tokens/mastermind.css`

## Review output

When reviewing or generating a Mastermind UI change, report:

- archetype + primary question;
- canonical components reused;
- any `DESIGN-SYSTEM-GAP` (do not silently fill it);
- Tier-1 answer/stance and where deeper evidence lands;
- theme/language/device/state cells checked;
- accessibility/interaction risks;
- whether the result is only a design/reference, implemented code, or actually browser/prod-proven.
