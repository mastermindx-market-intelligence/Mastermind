# States, responsiveness and accessibility

## Required state matrix

For material UI work, cover the cells that apply across:

- **Theme:** dark / light
- **Language:** EN / ZH
- **Device:** desktop / 390px mobile (plus tablet when the archetype depends on it)
- **Data state:** loading / empty / stale / partial / denied / error / corrected / success
- **Interaction:** default / hover / focus-visible / pressed / selected / expanded-open / disabled

Do not simulate every state on every component when irrelevant; do not omit a state that changes meaning or action.

## State semantics

- **Loading:** skeleton at true final geometry; no placeholder prose pretending to be data.
- **Empty:** full-weight user-facing sentence + mandatory reason/why.
- **Stale/behind:** status/freshness treatment + last settled observation, when safe.
- **Partial:** say what is excluded or unavailable; denominators/rates must not silently treat missing as zero.
- **Denied/locked:** access is a separate channel from data truth. The public answer remains semantically intact.
- **Error:** name what failed, what still works, and a lawful retry/recovery path.
- **Corrected:** show that a correction occurred and preserve evidence lineage.
- **Success:** do not over-celebrate; confirm the actual result/readback.
- **Unknown:** never render as zero, healthy or complete.

## Dark / light contract

Dark uses luminance hierarchy and restrained bloom. Light uses surface contrast, border discipline, whitespace and controlled shadow. Do not merely invert colors.

Examples:

- dark glow → light ring/tight shadow
- dark jewel aurora → lighter/airier alpha
- Quiet neutral fill, even neutral border and stronger text in both themes; labeled semantic status ink, no colored container-edge accent or relocated stripe
- dark glass → light brighter glass + crisp top edge
- dark chart series → light-twin series colors, same semantics/geometry
- locked preview ghost remains lock-only; never recolor it as data meaning

## ZH semantics

Market direction follows the Asia convention: red = up/bullish, green = down/bearish. Health/severity does **not** flip. Direction must never be conveyed by color alone—pair it with sign, arrow or language. ZH drops forced uppercase and English tracking; use native-shaped copy rather than English-shaped literal translations.

## Responsive law

- 390px is the design floor.
- No page-level horizontal scroll.
- Mobile is deliberate re-composition, not desktop squeezed vertically.
- Preserve answer + current evidence + next action.
- Demoted density gets a named landing/link/disclosure, not silent disappearance.
- Tables scroll inside their container; convert to row cards only when the archetype/reference calls for it.
- Touch cannot depend on hover.

## Accessibility floor

- Small text: ≥4.5:1 against the actual painted surface.
- Affordance boundaries/focus/segmented controls: ≥3:1 where the boundary carries meaning.
- Visible `:focus-visible` on every interactive element.
- Comfortable product targets: prefer 44px; production law currently sets an effective floor of at least 40×40.
- Keyboard, touch and zoom must preserve the task.
- Exactly one h1; sections use semantic h2.
- Non-color meaning for direction/severity/state.
- Respect `prefers-reduced-motion`; coarse-pointer interaction should not rely on animation.
- Hover-only evidence is noncompliant.

## Four proof types

Keep these separate:

1. **Technical:** data/layout/state implementation works.
2. **Design:** hierarchy, reading order, copy, responsive reduction and visual language are correct.
3. **Human/access:** keyboard/touch/zoom/non-hover paths are usable.
4. **Journey:** the user can complete the real task, inspect evidence and return with context preserved.
