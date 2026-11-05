# Foundations

## Product personality

Mastermind is the desk that already did the reading. It should feel intelligent because it compresses complexity rather than displaying every engine output.

**Dark — command center.** Graphite surfaces, luminance depth, restrained bloom, disciplined hairlines, instrument calm. Nothing blinks unless a live/ongoing fact warrants it.

**Light — research workspace.** Cool `#F7F8FA` canvas, white material, firmer hairlines, controlled shadow. Light is its own art direction, not an inverted dark palette.

## Reserved-hue law

Hue is a reserved word. It appears only for:

1. **Market direction** — up/down and direction ink; flips under ZH `红涨绿跌` convention.
2. **Health / severity** — ok/warn/act; never flips.
3. **Wayfinding / action** — link/info.
4. **Provisional / epistemic status** — prov/prov-ink.
5. **Locked content** — tier accent/ink; violet is lock-only, never data or chart meaning.

Everything else is achromatic. A decorative accent with no semantic job is a defect.

## Surface/elevation ladder

- **E0 Canvas:** page chrome + page header/verdict tier.
- **E1 Panel/Card:** one answer per panel.
- **E2 Raised/Panel2:** set members, hover/selected/raised state.
- **E3 Glass:** floating menus, LENS, sheets/popovers only.

Nesting depth ≤2. Nothing nests inside a Panel2 merely to create visual depth.

## Typography

UI words use the canonical UI family; numbers/tickers/code/axis ticks use the mono family only where appropriate. Numeral columns are tabular.

| Token | Size | Job |
|---|---:|---|
| `--fs-display` | 46px | hero verdict word |
| `--fs-num-xl` | 38px | large score |
| `--fs-h1` | 28px | page title |
| `--fs-num-lg` | 22px | secondary numeral |
| `--fs-h2` | 17px | panel title |
| `--fs-md` | 15px | lead/strong figure |
| `--fs-body` | 14px | base dashboard copy |
| `--fs-h3` | 14px | subsection title |
| `--fs-sm` | 12.5px | secondary/table copy |
| `--fs-label` | 11px | eyebrow/caps |
| `--fs-micro` | 10px | dense ticks/table heads |

Weight grammar: display/h1 ≈ 800; h2/h3 ≈ 700; body 400–500; eyebrow ≈ 600. Verdict display tracking is tight in EN; ZH removes tracking/forced uppercase.

## Spacing and geometry

Spacing scale: `4 / 8 / 12 / 16 / 20 / 24 / 32 / 44px`.

Named legacy skeleton constants include 18px grid gap and 16×18px panel padding where the production system uses them.

Radius court: controls 8px, buttons 10px, cards 12px, panels 14px, pills 999px. Do not mint ad-hoc radius scales.

## Motion

Motion is a status channel, not garnish.

- fast `.16s`: color/border state
- medium `.2s`: lift/reveal
- slow `.55s`: sweep where actually warranted
- standard easing `ease`
- lift easing `cubic-bezier(.2,.7,.3,1)`

Clickable containers may lift 1–2px. Tabs/toggles never move. Live data may pulse; settled data does not. Prefer one breathing element per page maximum, normally the primary CTA. `prefers-reduced-motion` must disable motion, including pseudo-element sweeps.

## Information density

- One primary question per page.
- First content element answers it.
- 1440×900 above-fold budget: chrome + answer + at most two supports.
- 390px mobile: answer within one swipe.
- Default L1 section budget 5; hard ceiling 7.
- Tier-1 number must change a decision, arrive with meaning, and not be derivable from another visible number.
- One canonical integer per population per page.
- One freshness stamp per panel + one page/session stamp.
- Mechanics/receipts go to LENS/details/Tier 3, except a caveat that materially changes how the headline should be read stays beside the headline.
- Deletion/demotion are first-class design acts. Demoted content gets a named landing rather than disappearing.

## Content doctrine

Tier 1 must give **signal + meaning + stance** in seconds. Preferred stance vocabulary:

`Act` · `Get ready` · `Watch — don't chase` · `Protect gains` · `Stand aside` · `Ignore`

Tier 1 avoids internal state slugs, unexplained acronyms and raw research statistics. Preserve truth; move receipts/technical detail to deeper tiers rather than hiding them.
