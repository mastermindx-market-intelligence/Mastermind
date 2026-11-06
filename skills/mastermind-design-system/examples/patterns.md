# Practical composition patterns

These are patterns, not replacement production components. Use the existing implementation classes when available.

## 1. Decision-first page skeleton

```text
PageShell
└─ PageHeader / h1
   └─ VerdictHero
      ├─ eyebrow
      ├─ verdict word
      ├─ ≤14-word plain clause
      ├─ stance
      └─ freshness + Evidence Lens
└─ Support 1: What changed
   └─ DecisionRows
└─ Support 2: Why / drivers / evidence
   └─ ≤4 focused members
└─ Named deep landing(s)
```

Do not start with a wall of equal-weight modules.

## 2. Verdict Hero

```text
MARKET REGIME
STRETCHED
Broad participation, but extension argues for patience.
Watch — don't chase
SETTLED · 2026-08-28
```

The verdict may use semantic ink, but the supporting structure stays calm/achromatic.

## 3. Count ladder

```text
12 EARLY | 8 BUILDING | 3 READY | 1 ACTIVE
```

The active stage is emphasized by weight/surface, not a new hue. Counts are one canonical population accounting, not independent recounts.

## 4. Degraded state

```text
STALE
Data is behind
Showing the last settled observation.
```

or

```text
ERROR
Feed unavailable
Settled evidence still works.
[Retry]
```

State copy says what is wrong and what is still safe to use.

## 5. Evidence Lens

At rest, keep the claim short. The Lens contains method/source/receipt depth. The open path must work by keyboard and touch as well as pointer hover.

## 6. Dense data panel

- state column
- entity/member
- tabular figure(s)
- signed/meaningful delta
- Evidence link
- L1 max 8 rows; `See all N` afterward
- if the table is wide, the table container scrolls; never the page

## 7. Question-first chart

Caption the user question before the geometry, e.g. “Is breadth broadening?” Use at most four generic categorical series. Direction series use direction tokens; health uses health tokens. More than four series means the question is mis-tiered: split it or demote to a table/study view.

## 8. Mobile reduction

At 390px, preserve:

1. current answer/state
2. top change(s)
3. useful action/stance
4. critical caveat/degraded state
5. deeper evidence landing

Do not merely stack every desktop panel. Desktop-only density gets a named landing rather than disappearing.
