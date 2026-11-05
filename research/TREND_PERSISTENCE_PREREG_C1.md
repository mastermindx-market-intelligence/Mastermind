# Trend Persistence — Pre-registration C1 (sector group persistence: development and frozen confirmation)

Status: FROZEN on merge to `master`. The instrument (`research/trend_persistence_group.py`,
to be written after this freeze) pins this file's sha256 as `PREREG_SHA256` and scores nothing
if the file on disk differs. This is one document with two parts. The development part (C1)
is scored once on formation dates the family has already used; nothing it finds is a claim.
The confirmation part (C2) fixes, now, every construction choice, gate, constant and the rule
that produces the one constant that cannot be known yet (the number of forward dates), and is
scored once on formation dates that begin after this freeze. No text about C2 is written
later: the only later artifact is a machine-written constants block whose contents are a
closed list (§6).

Program: WS:TREND-PERSISTENCE. Written by the Fable CEO seat (session 3b488a7c) on
2026-10-04, after two independent adversarial analyses of a seat design brief (§12).

## 0. What is already known, and how this document binds

**The family's state.** Waves A, B and B2 tested stock-level path-shape features. V1 returned
the null on forward return relative to SPY (72 tests, none confirmed). V2's holdout
(`research/TREND_PERSISTENCE_PREREG_V2.md`, revision 2, sha256
`2882865d02ad75a6db78a292daae1a8391bf7f876f615234d063cb455b782d17`) confirmed 29 feature–horizon
tests on forward maximum drawdown. B2
(`research/TREND_PERSISTENCE_PREREG_B2.md`, sha256
`79764bf5f9bf18c6ce8a6161fa221188dc1a5859fe82d715711fecb7bb0380aa`) asked whether those 29
carried information beyond a volatility-aware baseline and returned the null on model value
(`research/data/trend_persistence_b2_result.json`, sha256
`e0b177cb51dececc173e67817e76356f201d498626022440487cce0a3a2ba443`). The decision record
DEC:TREND-PERSISTENCE-STOPS-AT-WAVE-B closes the 29 tests and Waves D–F for those
constructions and says: "It does not close the idea: other constructions and sector or group
persistence were not tested."

**The protocol names this wave.** `research/TREND_PERSISTENCE_PROTOCOL.md` (sha256
`ab0ed7fe45e6107a17e686431118805a9776d68dd9ac566659c36aee59240412`): Wave C is group
persistence, starting with GICS sector and existing basket membership, measuring group RS
persistence, breadth participation, member hit-rate, leader retention and within-group
dispersion, testing group-only, stock-only, additive and interaction models. "The key claim
must fail if group features add no OOS information beyond member momentum." A family may
advance from descriptive to shadow-advisory only if its direction is stable across
walk-forward folds and at least one economically relevant horizon, "with no single sector or
episode explaining the result"; a family is killed when "performance is concentrated in a tiny
number of names/themes".

**The dates are used up.** The readout (`research/TREND_PERSISTENCE_READOUT.md`, sha256
`7013662ff9aae27118082314dd3cb8e5bdb1ea72d17ddcc053dd776f62435443`) says of formation dates
2022-07-06 to 2026-06-02: "Formation dates from 2022-07-06 to 2026-06-02 were V2's holdout and
B2's test. A third claim cannot rest on them." Every year in the panel has been looked at.
Therefore:

- Everything scored on formation dates whose label exits on or before 2026-06-02 is
  **development**. It chooses what is carried forward (§7) and sets the constants the forward
  read needs (§6). It confirms nothing, whatever it shows.
- A **confirmatory** statement about sector group persistence can rest only on formation
  dates after this document is frozen (§3). Dates between 2026-06-03 and the freeze are also
  not confirmatory: the question they answer — did the leading sectors of mid-2026 keep
  leading — is public and is shown daily by every sector-leadership dashboard, this
  repository's included. They are printed as a bridge and gate nothing.

**What Wave C-0 built (macro repository, PR #8403).** A point-in-time S&P 1500 sector
substrate for the 1,083 names that left the index, labelled through the EDGAR filer-CIK bridge
only, never through a ticker string (tickers are recycled). Artifacts and digests as built on
2026-10-04:

| Artifact (macro `data/breadth/`) | sha256 | What it is |
| --- | --- | --- |
| `sp1500_pit_sectors.parquet` | `cba7fc07da53a6230122fec5797b15163bbe3b31f78918839f5722e885c00de3` | 2,589 rows, one per ticker ever in the membership file; 1,083 leavers, 1,506 current members; columns ticker, is_leaver, membership_start, membership_end, sector, basis, sic, sic_desc, cik, cik_method, label_join, label_asof, era_correct |
| `_sp1500_pit_sectors_coverage.json` | `ce5c692075dc14b1a830c611565b4ba7c48e637fcfaa2a53690829a4ed0ff34c` | coverage receipt |
| `_sp1500_pit_sic_cache.json` | `0c137ff35b4b46d327d3e93f9f951cf414fa8d168902f662bbfd811172cf9084` | SIC lookup cache |
| `sp1500_pit_membership.parquet` | `7b34316c0561619ba052f02036ec1fbe7fff3d00dcda3e7acb7dffda10582eca` | 3,286 membership spans (ticker, start_date, end_date, src); last end_date 2026-06-02; the file V2 and B2 scored on (first 16 hex digits match their provenance) |

Label facts, from the receipt: `label_asof` is 2026-10-04 on every row and `era_correct` is
False on every row — every label is as-of-now (the current GICS map for members; the filer's
current SEC SIC mapped to GICS-style sectors for leavers), none is the sector of the
membership era. Members: 1,492 `gics_current`, 12 `sic_current`, 1 `sic_derived`, 1
unlabelled. Leavers: 281 `sic_derived`, 802 unlabelled. Eleven sectors; labelled rows per
sector: Industrials 294, Financials 284, Information Technology 241, Consumer Discretionary
225, Health Care 216, Real Estate 121, Materials 99, Consumer Staples 96, Energy 88,
Utilities 61, Communication Services 61.

Counts taken before this freeze on PIT membership joined to those labels, using no price and
no label of any kind (§12): on formation dates 2019-01-04, 2022-07-06, 2024-01-05 and
2026-01-05 **every unlabelled member was a future index leaver** (116 of 116, 185 of 185, 107
of 107, 26 of 26); 67% of unlabelled members are sp600; on every test date from 2022-07-06 to
2026-06-02 the smallest labelled sector (Communication Services) has at least 43 members
(Energy ≥ 49, Utilities ≥ 54, Industrials ≥ 221); from 2019 the minimum is 30; the member
universe is 912 in 2019 (no small caps) and about 1,520 from 2020; 14–16% of 2019–2021
member-dates are unlabelled, 12.2% on 2022-07-06.

**The panel.** V2's repaired price panel, digest
`48cb5e76269b3a503d2973aecdd04733a2d8b88434db06de8367a224ba4ef178`, built by the V2
instrument's loader from the macro breadth files (`_closes_deep.parquet` sha256 starting
`88e3261ca077543a`, `_closes_delisted.parquet` `1e668fe0c181a59f`, the membership file above)
and the committed split reference. Its last session is 2026-06-15. Mastermind reaches these
files through `vendor/macro`.

**What this document does not license.** No product surface, no brain field, no
shadow-advisory standing comes from C1. A C1 result is descriptive tier. Only a C2 pass (§8)
moves the family one rung.

**Binding on the people who run this.** The V2 and B2 pre-registrations, the four modules B2
pins, and the committed V2/B2 result, attempt and reference files are not edited. V2 and B2
are not re-run. No statistic that joins a group feature with any label is computed before this
file is frozen (none has been, §12). One C1 run; one C2 read.

## 1. Questions

**Q1 (value).** Does sector-level persistence information about a member's GICS sector improve
the cross-sectional ranking of members' forward returns relative to SPY, at 20 and 60
sessions, beyond a stock-level baseline that already holds the member's own trailing returns,
its volatility descriptors, its sector's volatility, its sector's size, its index tier and
market-state interactions? In the protocol's terms: does (c) group + stock beat (a) stock-only,
where stock-only is deliberately strong?

**Q2 (form).** If it does, is the information additive, or does it live in the interaction
"theme first, stock second": within a leading sector, the within-sector leaders continue most?

**Q3 (label handling).** Does the answer to Q1 depend on how members without a sector label —
who are, on every date checked, future index leavers — are handled?

The falsifier for Q1 is the protocol's: group features add nothing out of sample beyond what
the member's own trailing returns and volatility already say. This document makes the baseline
carry everything a sector aggregate could reproduce without persistence (§4), so that a
positive answer cannot be sector volatility, sector size, index tier or market direction in
disguise.

## 2. Substrate, universe, labels

**Prices and eligibility: exactly V2 §3.** The repaired panel; the quoted-price mask; the
$5 floor on the printed close; point-in-time membership; the formation calendar (every fifth
session of the panel, starting at session index 252); entry at the close of *t*+1. The C1
instrument refuses any panel whose digest is not `48cb5e76…ef178`.

**Index tier at *t*.** sp500, sp400 or sp600, from the `src` of the membership span that
covers *t*.

**Sector at *t*.** From the sector snapshot (§0): the member's `sector`, as-of-now. For C1
the snapshot is the C-0 file, `cba7fc07…0de3`. For C2 see §3.

**Labels.** For *h* in {5, 20, 60}: entry is the close of *t*+1, exit the close of *t*+1+*h*;
a stock that stops trading inside the window keeps its last price to the exit and is flagged
(V2 §3). Three labels:

- `rel_spy_h` — the stock's log return from entry to exit minus SPY's over the same sessions.
  **The gated label**, at *h* = 20 and 60.
- `rel_sector_h` — the stock's log return minus the equal-weight log return of all eligible
  labelled members of its sector over the same sessions. Reported, never gated: a
  decomposition.
- `forward_max_drawdown_h` — as V2/B2. Reported, never gated (§5, §9).

Within a date, subtracting SPY changes no rank and therefore no gated statistic (SPY is a
constant on the date); the relative form is kept so that spreads read as excess returns.

**Complete case.** An eligible stock-date with the label, every regressor of model B* and
every group feature of §4. A date needs at least 100 complete cases (B2 §2). **Every model on
a date is fitted and scored on the identical case set.**

**Group date.** A formation date is scored only if all eleven sectors have at least 25
eligible labelled members with valid values for every group feature. Where a feature has its
own count rule (`grp_leader_retention_60x60`, §4) that rule applies too. On the test dates
this never binds (minimum 43); in 2019–2021 it may remove Communication Services dates, which
are printed only.

**Members without a sector label.** Three treatments, fixed now.

- **Primary — labelled only.** Cases are members with a sector label. Group aggregates are
  computed from eligible labelled members only, including the member being scored. Every
  model uses this same case set.
- **Bracket NI — neutral imputation.** Cases are the full eligible set. An unlabelled case
  receives rank 0 (the cross-sector midpoint, §4) for every group feature and sector-level
  variable and 0 for every interaction; no model carries an unlabelled indicator, because on
  this substrate such an indicator is a future-leaver flag. Group aggregates are unchanged
  (labelled members only).
- **Bracket CM — current members only.** Primary cases, but every group aggregate is computed
  from members who are still in the index at the snapshot's `label_asof`. This is fully
  future-conditioned and is reported against the primary to bound how much the labelled
  universe's survivor tilt moves the group features.

An "unlabelled" pseudo-sector is forbidden: it is not a group, it is the set of members who
will leave the index before mid-2026 and have no trusted CIK (§0).

## 3. Dates, blocks, training, embargo

**Development test blocks (C1).** Exactly B2 §3, with an embargo: T1 2022-07-06 to
2022-12-31; T2 2023; T3 2024; T4 2025; T5 2026-01-01 to the last formation date whose label
**exits on or before 2026-06-02**. The panel runs to 2026-06-15, so the embargo is a rule the
instrument enforces and prints (the last formation date per horizon). It exists so that no C1
label shares a session with a C2 label.

**Early blocks, printed only.** E1 2019, E2 2020, E3 2021, by formation date. They never count
in the selection rule (§7) and never set a C2 constant. They are for instrument shake-down and
for sizing the brackets (14–16% of member-dates unlabelled; universe 912 in 2019). Formation
dates from 2022-01-01 to 2022-07-05 are training only, as in B2.

**Training.** For each block and horizon every model is fitted once, on every formation date
from **2013-01-02** whose label exits before the block's first test date (B2 §3's rule; the
window starts in 2013, the first full year of the ~920-member universe, instead of at the
panel's first date, because earlier dates hold about 500 survivor-tilted members). At least
100 training dates. A and B* — and every other model — are fitted on the identical labelled
case set. A non-gating bracket trains from 2019-01-02.

**Confirmatory dates (C2).** The **freeze date** is the UTC committer date of the Mastermind
`master` commit that first contains this file at its pinned sha256. The **first confirmatory
formation date** is the first formation-calendar date strictly after the freeze date. The
calendar is V2's (every fifth session from session index 252 of a panel whose first session
is 2002-01-02); the C2 panel keeps that first session so the calendar is unchanged.
Formation dates from 2026-06-03 to the freeze date form the **bridge block**: printed, never
gated.

**C2 sector labels and snapshots.** A sector snapshot is minted by running the macro collector
(`collectors/sp1500_pit_sectors.py`) and committing the parquet and its coverage receipt to
macro `main`; each snapshot has a `label_asof` and a sha256. For a confirmatory formation date
the case's sector, and the member set of its group aggregates, come from the **earliest**
digest-pinned snapshot whose `label_asof` is on or after the formation date. Confirmatory dates
before the first prospective snapshot use the C-0 snapshot (`cba7fc07…0de3`, `label_asof`
2026-10-04). The interim and the gating read each mint one snapshot (§6).

**C2 membership and panel.** The membership file ends 2026-06-02 and is a single build. Before
the interim and before the gating read it is rebuilt by its macro collector through the read
date, the panel is rebuilt by the V2 loader, and both digests are appended to the constants
block (§6). The C2 panel digest will differ from `48cb5e76…ef178`; that is expected and
recorded, not a refusal.

## 4. Variables

All stock-level regressors and all labels are per-date centred percentile ranks across the
date's cases, ties sharing their average rank (B2 §4). Sector-level variables are ranked
**across the sectors present on the date**, not across stocks: with *K* sectors present, a
sector at rank *r* (1 = lowest) carries `(r − 0.5) / K − 0.5`, and every member of that sector
carries that value. Because every group aggregate is one number per sector-date computed from
all eligible labelled members including the scored member, no member's own return enters its
group value with a sign of its own; the instrument's unit test asserts zero within-sector
variance of every sector-level regressor on every date. There is no leave-one-out: leaving the
member out makes its group value a decreasing function of its own value inside the sector,
and B2 §4's per-stock ranking then turns that into an own-return regressor in disguise.

**(a) Stock-level controls — B2's model B2, exactly.** The eleven V2 controls (`ret_20d`,
`ret_60d`, `ret_120d`, `ret_252d`, `vol_20d`, `vol_60d`, `vol_120d`, `vol_252d`,
`downvol_60d`, `downvol_252d`, `beta_252d`) and their squares; B2's eleven volatility
descriptors (EWMA volatility at half-lives 3, 10 and 30 over 120 sessions; mean and maximum
absolute daily return over 20, 60 and 120 sessions; downside volatility over 20 and 120
sessions) and their squares; and B2's six products (return × volatility and return² ×
volatility at 20, 60 and 120 sessions). Fifty regressors. The brief's "eleven controls and
their squares" was B2's model B1; it is not the baseline here.

**(b) Sector-level volatility descriptors** (each one value per sector-date, ranked across
sectors):

| Name | Definition |
| --- | --- |
| `grp_dispersion_60` | standard deviation across the sector's members of their 60-session log returns |
| `grp_vol_60` | standard deviation of the sector's equal-weight daily log return over the last 60 sessions |
| `grp_medvol_60` | median across members of `vol_60d` |
| `grp_te_120` | standard deviation, over the last 24 non-overlapping 5-session blocks, of the sector's equal-weight block log return minus SPY's block log return |

These are what a sector aggregate reproduces without any persistence: `grp_dispersion_60` is
about sqrt(60) times the sector's average idiosyncratic volatility. B2 §7 found that a trace of
volatility information survives any finite set of stock-level descriptors; a pooled sector
estimate is a less noisy version of the same trace. So they sit in the baseline, never in G.

**(c) Sector size.** `grp_size` = number of eligible labelled members of the sector at *t*,
ranked across sectors. Nearly static sector identity (Industrials and Financials are always
largest, Communication Services smallest) and it jumps with the membership file's universe
changes. In the baseline.

**(d) Tier and market-state terms.** Indicators for sp500, sp400 and sp600 at *t*;
`rank(beta_252d) × z(SPY ret_20)`, `× z(SPY ret_60)`, `× z(SPY ret_120)`; and
`rank(vol_60d) × z(SPY vol_20)`. `z(·)` standardises the date-level SPY quantity by its own
mean and standard deviation over the trailing 252 sessions ending at *t*. A date-level
quantity on its own ranks to a constant on the date and adds nothing; these products are the
cross-sectional channels through which "market" could pose as "group" — high-beta sectors
leading in trends that persist, equal-weight sector strength against a cap-weighted benchmark.

**(e) Group features, G (seven).** One value per sector-date from all eligible labelled
members with valid windows, ranked across sectors.

| # | Name | Definition | Protocol measurement |
| ---: | --- | --- | --- |
| 1 | `grp_rs_60` | mean over the sector's members of (member 60-session log return − equal-weight 60-session log return of all eligible labelled members in the member's index tier) | RS persistence |
| 2 | `grp_rs_120` | the same at 120 sessions | RS persistence |
| 3 | `grp_rs_consistency_120` | share of the last 24 non-overlapping 5-session blocks in which the sector's equal-weight block log return exceeded the equal-weight block log return of all eligible labelled members | RS persistence |
| 4 | `grp_participation_50` | share of members whose close at *t* is above their own 50-session simple moving average | breadth participation |
| 5 | `grp_hit_20` | share of members with a positive 20-session log return | member hit-rate |
| 6 | `grp_leader_retention_60x60` | among members with a valid return in both windows, the share of the top third by return over (t−120, t−60] that are also in the top third by return over (t−60, t]; non-overlapping windows; null expectation 1/3; requires at least 25 contributing members, else the sector-date is invalid and the date is not a group date | leader retention |
| 7 | `grp_coherence_60` | equal-weight mean over members of the Pearson correlation between the member's daily log return and the sector's equal-weight daily log return over the last 60 sessions (member included in the equal-weight series) | within-group coherence |

Features 1 and 2 are tier-neutral so that an equal-weight sector return is not credited for
being small-cap-heavy against a cap-weighted benchmark. Feature 6 replaces the brief's
retention between 120-session windows ending at *t*−60 and *t*: those windows share 60
sessions, so under no persistence the two returns correlate at about 0.5 and top-fifth
retention sits near 0.45 by construction. "Within-group dispersion" from the protocol is
measured by (b) `grp_dispersion_60` and sits in the baseline (above); coherence (7) is the
persistence-relevant form of the same measurement.

**Redundancy rule, frozen, feature-only.** Before any model is fitted, the instrument computes,
on the T1–T5 formation dates, the per-date Spearman correlation across sectors between each
pair of the seven features and takes the median over dates. If a pair's median |ρ| exceeds
0.80, the later-numbered feature of the pair is dropped from G for every model, horizon and
bracket, and the drop is printed. No label enters this computation. The surviving list is a C2
constant.

**(f) Within-sector momentum.** `wr120` = the member's percentile rank of `ret_120d` within
its sector on the date, minus 0.5. Used only by model I.

## 5. Models

| Model | Regressors | Role |
| --- | --- | --- |
| G | the group features (e) alone | reported only; printed so that a null can be read as "no group information at all" or "group information already in B*" |
| B | B2's model B2, (a) alone | reported only: A − B beside A − B* is the volatility-reproduction diagnostic |
| **B\*** | (a) + (b) + (c) + (d) | **the gating baseline** |
| **A** | B\* + (e) | additive group model |
| **I** | A + { `wr120`, `wr120 × grp_rs_120`, `wr120 × grp_participation_50` } | interaction model, Q2 |
| B\*+D | B\* + eleven sector indicators | reported only: does G beat a static sector premium? |
| SPLIT | B\* with `ret_60d` and `ret_120d` each replaced by a between part (the sector's equal-weight return over the window) and a within part (member minus sector) | reported only: where in the member's own momentum the sector sits |

Fit: rank-linear least squares on the centred ranks, per block, on training dates (§3), for
`rel_spy_h` and `rel_sector_h`; logistic regression as B2 §5 for the drawdown event (the
worst tenth of `forward_max_drawdown_h` on the date). The interaction terms in I use the
sector-level ranks of §4(e) and the within-sector `wr120`; the interaction with `rank(ret_120d)`
proposed in the brief is not used, because that cross-sectional rank already contains the
sector's own move and the product is partly `grp_rs_120` squared. Pre-registered and reported,
not gated: in I the coefficient on `wr120 × grp_rs_120` is positive.

**Reproduction before any group feature is computed.** The instrument rebuilds model B2 under
B2 §3 on the V2 panel, full eligible set, forward maximum drawdown at 20 and 60 sessions, and
stops — reporting nothing further — unless the mean per-date rank IC equals the committed
values, read from the B2 result file by pinned sha256, to 1e-9: `0.49461154432499976` at 20
sessions over 194 dates and `0.5337496007208158` at 60 over 186 (`/horizons/20/models/B2/ic/mean`,
`/horizons/60/models/B2/ic/mean`). This proves the baseline is B2's, not a re-implementation.

## 6. What is measured

**Per date, per horizon, per model:** the Spearman rank IC between the fitted score and the
label; the mean forward relative return of the top tenth of scores minus the bottom tenth (the
spread); for the drawdown event, capture, Brier score and the reliability inputs as B2 §6.
**Per date, differences:** A − B\*, A − B, I − A, I − B\*, G − 0, (B\*+D) − B\*, SPLIT − B\*,
each as a rank-IC difference and as a spread difference. Each difference series is summarised
by its mean and the test below.

**The test of a mean (B2 §6, verbatim).** Every p-value that gates comes from one test. For a
series of `n` per-date values at horizon `h`, whose labels each span `q = ceil(h / 5)`
formation dates:

- the long-run variance is the mean of the squares of the first `ν` cosine transforms of the
  series, `Λ_j = sqrt(2 / n) × Σ_t x_t cos(π j (t − ½) / n)`, `j = 1 … ν`;
- `ν = max(4, min(floor(0.4 × n^(2/3)), floor(n / (2 q))))`;
- `t = sqrt(n) × mean / sqrt(variance)`, referred to Student's t with `ν` degrees of freedom.

One-sided, unrounded. On the development test dates ν is 13 at 20 sessions and 7 at 60 (B2).
The implementation is imported from `research/trend_persistence_walkforward.py`, which is not
edited.

**Validity refusal.** The instrument refuses to **gate** any cell at which
`floor(n / (2 q)) < 4`, because there the floor of 4 overrides the overlap cap and the test
leaves the regime B2 checked: with overlapping 60-session labels and n between 48 and 95,
synthetic series with a true mean of zero were rejected 3.7–4.8% of the time at a stated 2.5%
(§12). At 60 sessions this means a cell can gate only with n ≥ 96 formation dates. Below the
rule the statistics are printed and marked "not a valid gate under the family's test".
Degrees of freedom the rule gives: n = 48, h = 20 → ν = 5 (t at 0.025: 2.571); n = 96, h = 20
→ 8; n = 144, h = 20 → 10; n = 96, h = 60 → 4 (the cap, not the floor); n = 144, h = 60 → 6.

**Leave-one-sector-out.** For each difference series that can gate, the mean per-date
difference is recomputed with each sector's members removed from the scored cross-section,
without refitting: eleven numbers.

**Power rule (C2's one unknown constant).** For each cell the selection rule carries (§7) the
C1 instrument computes, mechanically: `σ_LR` = the square root of the cosine long-run variance
above, on the cell's development per-date difference series over T1–T5; `δ*` =
`max(0.008, 0.5 × the development mean)`; and `n_read(cell)` = the smallest n in {48, 96,
144} at which a one-sided test at level 0.025 with ν(n) degrees of freedom, against a
noncentral t with noncentrality `δ* × sqrt(n) / σ_LR`, has power at least 0.80. If no n in the
set reaches 0.80 the cell is **futile**: it is not carried, and the readout prints its σ_LR and
the n it would have needed. The C2 read size is `n_read = n_read(primary)`.

**The C2 constants block.** When at least one cell is carried, the C1 run writes
`research/data/trend_persistence_c2_constants.json` containing only:

1. the carried cells and the step each occupies in §7's sequence;
2. per carried cell: development mean, σ_LR, δ*, n_read(cell); and n_read;
3. the group-feature list after the redundancy rule;
4. the sha256 of `research/data/trend_persistence_c1_result.json`;
5. the freeze date, the first confirmatory formation date, the interim date and the gating
   read's trigger rule, as data;
6. the sha256 of the frozen coefficients of every model at every horizon, fitted once on all
   formation dates from 2013-01-02 whose label exits before the first confirmatory formation
   date (C2 scores with these coefficients; nothing is refitted inside C2);
7. appended by the instrument at the interim and at the read: the rebuilt membership, sector
   snapshot and panel digests and the coverage receipts.

Nothing else. A reviewer's record lives in the pull request that commits the block. Any other
content voids the gating read and the result is labelled development only.

**The interim.** Exactly one, on the first session on or after the freeze date plus 182
calendar days. It mints a sector snapshot, rebuilds membership and panel, and prints only:
dates scored so far, complete cases per date, the unlabelled share, group-date failures by
sector, and the digests and receipts of item 7. **No statistic that uses a forward label — the
baseline's own IC included — is computed before the gating read.** No constant changes after
the freeze; an interim that is read by a human is still not actionable, because there is
nothing left to decide.

**One C1 run.** The real run is made once, from a committed tree, to one fixed path,
`research/data/trend_persistence_c1_result.json`. Before it reads a label it records the
attempt (time, commit, code hash) in `research/data/trend_persistence_c1_attempt.json`. It
refuses to run while the result exists. If an attempt is on record with no result, another
attempt needs a stated reason, kept in the result as a deviation. B2's readout notes that this
guard can be defeated by a careless operator; the public attempt record and the immediate
commit of the outputs are the backstop, as there.

## 7. Gates

### 7.1 C1 selection rule — what is carried to the forward read

A **return cell** is a horizon in {20, 60} with the comparison A − B\* on `rel_spy_h`. It is
carried only if, on the T1–T5 dates, all five hold:

| | Condition |
| --- | --- |
| (i) | mean per-date rank-IC difference A − B\* ≥ 0.010 (V2's development floor G2) |
| (ii) | one-sided p ≤ 0.10 under the test of §6 |
| (iii) | A − B\* positive in at least 4 of the 5 blocks |
| (iv) | the mean A − B\* has the same sign under Bracket NI |
| (v) | W5: mean A − B\* > 0 with each sector removed in turn, 11 of 11 |

The **interaction cell** is h = 20 with the comparison I − A on `rel_spy_20`. It is carried
only if the same five hold for I − A. I − B\* is never a carry route. The early blocks and the
bridge block never count.

The **primary** is h = 20, A − B\*. If the primary is not carried there is no C2; h = 60 cannot
be made primary after the development read. If the primary is carried but futile under §6's
power rule, there is no C2 either (§8).

Using development data to choose which cells get forward data is the V1→V2 pattern; it leaks
nothing into C2 because every C2 gate value is fixed here and the forward data are
independent. The floor in (i) is V2's own; (ii) scales it by the series' noise so that a
noisy 0.010 is not carried.

### 7.2 C2 — one read, fixed sequence

One gating read (§7.3). Steps are tested in this order, each at one-sided 0.025 with the test
of §6, and a step is entered **only if the previous step passed every gate**. A cell that was
not carried is skipped and the sequence continues. No other cell gates. There is no
false-discovery adjustment across cells: the decision "any pass builds a field" is family-wise,
and a fixed sequence controls the family-wise rate at 0.025 without splitting it.

| Step | Cell | Condition to be live |
| ---: | --- | --- |
| 1 (primary) | `rel_spy_20`, A − B\* | always, if carried |
| 2 | `rel_spy_60`, A − B\* | carried **and** n_read ≥ 96 (§6 validity) |
| 3 | `rel_spy_20`, I − A | carried |

Gates per live cell:

| | Gate |
| --- | --- |
| W1 | one-sided p ≤ 0.025, test of §6 |
| W2 | mean difference positive in at least 3 of 4 blocks, where the blocks are the n_read confirmatory formation dates cut into 4 consecutive blocks of equal count, remainder to the last. Under the null this passes about 31–38% of the time; W2 guards stability, not error rate |
| W3 | mean per-date spread difference (A minus B\*, or I minus A) in top-tenth-minus-bottom-tenth forward relative return ≥ 0.0025 at h = 20 and ≥ 0.0050 at h = 60 |
| W5 | leave-one-sector-out: mean difference > 0 with each sector removed, 11 of 11 |

W3's floors: two legs × incremental decile turnover of about 0.4 per 20-session and 0.7 per
60-session rebalance × a blended S&P 1500 round-trip cost of about 0.30% gives 0.24 and 0.42
percentage points, rounded up. The cost and turnover inputs are reasoning, not measured on
disk; 10% of B\*'s own development spread is printed beside W3, non-gating. B2's W4
(calibration) is not a C2 gate: no gated cell is logistic. B2's K3 (false-discovery) is
replaced by the fixed sequence; B2's K5 (clearance of a simulated market) is not used because
no sector-structured volatility-only simulated reference exists, and building one is outside
this wave — which is one reason the drawdown label is not gated (§9).

### 7.3 When the read happens

`n_read = n_read(primary)`. The read is made on the first session on which the n_read-th
confirmatory formation date has a complete label at the longest horizon that is live (60 if
step 2 is live, else 20). Each live horizon uses the **first n_read** confirmatory formation
dates; further dates that have a complete 20-session label by then are printed, not gated. The
read is made once; a cell that fails is not read again. A later claim about any cell needs a
new pre-registration whose first sentence says what C1 and C2 showed and whose formation dates
begin after this read.

Estimates, on the every-fifth-session calendar with a first confirmatory date in mid-October
2026: n_read = 48 at h = 20 → the read falls in late 2027; n_read = 96 with h = 60 live → late
2028; n_read = 144 at h = 20 → 2029. These are estimates; the constants block holds the rule,
not a date.

## 8. Decision rule

**C1 outcomes (development; none is a claim).**

- **C1-CARRY.** The primary is carried and not futile. The constants block is written (§6);
  the result file and the readout label every C1 number DEVELOPMENT; the forward wait begins.
- **C1-NULL.** No return cell is carried. Then: *"The family stops at Wave C for the
  eleven-sector, as-of-now-labelled constructions of §4 on this universe and these horizons.
  GICS industry-group or industry, basket and dynamic-theme constructions are untested and not
  closed."* The null readout must print: the scope sentence (eleven sectors; as-of-now labels;
  a survivor-tilted labelled universe; these features, horizons and the rank-linear form); G
  against zero; A − B and A − B\*; the SPY-relative against the sector-relative decomposition;
  the per-date standard deviation of A − B\* and the smallest mean detectable at one-sided
  2.5% with 80% power on these dates; the leave-one-sector-out table; and the sentence *"Group
  information already contained in a member's own trailing returns and volatility is not group
  persistence; this design credits only what is left after B\*."*
- **C1-UNDERPOWERED.** The primary is carried but futile at n = 144. Same stop wording, with:
  *"Under the family's own test, the effect seen in development cannot be confirmed in a
  forward window of at most 144 formation dates; it is neither confirmed nor refuted."* No C2.

**C2 outcomes (one read).**

- Step 1 passes W1, W2, W3 and W5: the sector group-persistence family advances from
  descriptive to **shadow-advisory** on the protocol's ladder as a return-ranking evidence
  family at 20 sessions, scope limited to the constructions of §4. Step 2 passing adds 60
  sessions. Step 3 passing adds the interaction form — "theme first, stock second" at the
  within-sector-leader level.
- Any step failing stops the sequence there. Failed cells are closed with the C1-NULL wording
  restricted to them; cells that passed keep their standing. Nothing is re-read.
- A result that is passed but whose block carries anything beyond the closed list of §6 is
  development only.

Whatever the outcome, Wave C's drawdown findings earn nothing (§9), and nothing here promotes
a feature past shadow-advisory: the protocol's later rungs need their own pre-registration.

## 9. Reported but not gating

G alone against zero; B, and A − B beside A − B\*; B\*+D and SPLIT against B\*; I − B\*; every
cell at horizon 5; `rel_sector_h` at 20 and 60 for every model; `forward_max_drawdown_h` at 20
and 60 against B\* — rank IC, capture, Brier score, calibration slope — labelled
*"volatility-type, not distinguished from sector volatility"*, since W1 and W2 passed in 25 of
40 volatility-only simulated runs in B2 §7 and a pooled sector feature is a less noisy sector
volatility estimate; Bracket NI and Bracket CM for every gated comparison; the
training-from-2019 bracket; the early blocks and the bridge block; A − B\* split by the sign of
SPY's trailing 60-session return at formation; each sector's contribution and each block's
mean for every gated comparison; the sign of I's `wr120 × grp_rs_120` coefficient; A − B\* on
the audited-panel names alone (V2 §9's precedent, because store-sourced names omit dividends);
the redundancy correlation matrix and any drop; per-date complete-case counts, the unlabelled
share, and group-date failures by sector.

## 10. Known limits

1. **Labels are as-of-now.** `era_correct` is False on every row. A historical sector
   aggregate here is the aggregate of today's sector membership backcast; the GICS changes of
   2018-09-28 (Communication Services) and 2023-03 moved large names between sectors. This
   alone makes C1 non-confirmatory, and it is why C2's labels come from snapshots with
   `label_asof` on or after the formation date.
2. **The labelled universe is survivor-tilted.** 281 of 1,083 leavers (26%) carry a label,
   about 42% in the newest exit era; on every date measured, every unlabelled member was a
   future leaver. Hence the primary, Bracket NI and Bracket CM.
3. **Eleven effective units.** The group term is identified only from between-sector ordering,
   eleven values per date among about 1,400 stocks; the sector component of a per-date IC has
   eleven effective units, and power is low.
4. **The label is cross-sectional.** It says which members beat others on a date, not when
   the market does; SPY-relativity changes no gated statistic. A beta × market-direction
   channel can give a positive A − B\* without group persistence; B\* carries beta × SPY-trend
   terms for that reason and the SPY-sign split is printed.
5. **One forward window is about one market regime.**
6. **Store-sourced names are adjusted for splits only** (V2 §10): high-yield sectors'
   relative strength and labels are understated by roughly yield × h / 252.
7. **The membership file is a single build ending 2026-06-02.** C2 needs rebuilt, digest-pinned
   membership and panel; the C2 panel digest differs from C1's.
8. **Power figures are reasoning.** The per-date noise of a sector-feature increment was
   simulated under an assumed between-sector variance share of about 0.10; the real σ_LR is
   unknown until C1 runs, which is why the read size is a rule, not a number.
9. **W3's inputs are reasoning**, not costs measured on disk.
10. **Library versions are not pinned** (B2's precedent and caveat).
11. **One functional form**: rank-linear least squares; logistic for the reported drawdown
    event.
12. **The redundancy rule uses development dates.** It uses no label, is deterministic, and is
    printed; but the surviving feature list is chosen on data the family has seen.

## 11. Frozen constants

| Constant | Value |
| --- | --- |
| C1 panel | V2's; digest `48cb5e76269b3a503d2973aecdd04733a2d8b88434db06de8367a224ba4ef178`; first session 2002-01-02 |
| Sector snapshot (C1; C2 fallback) | macro `data/breadth/sp1500_pit_sectors.parquet`, sha256 `cba7fc07da53a6230122fec5797b15163bbe3b31f78918839f5722e885c00de3`, `label_asof` 2026-10-04 |
| Coverage receipt | `_sp1500_pit_sectors_coverage.json`, sha256 `ce5c692075dc14b1a830c611565b4ba7c48e637fcfaa2a53690829a4ed0ff34c` |
| Membership (C1) | `sp1500_pit_membership.parquet`, sha256 `7b34316c0561619ba052f02036ec1fbe7fff3d00dcda3e7acb7dffda10582eca` |
| B2 result | `research/data/trend_persistence_b2_result.json`, sha256 `e0b177cb51dececc173e67817e76356f201d498626022440487cce0a3a2ba443`; reproduction means 0.49461154432499976 (h 20, 194 dates), 0.5337496007208158 (h 60, 186 dates); tolerance 1e-9 |
| Gated label | `rel_spy_h`, h = 20, 60; printed h = 5; `rel_sector_h` and `forward_max_drawdown_h` printed |
| Development blocks | T1 2022-07-06..2022-12-31; T2 2023; T3 2024; T4 2025; T5 2026-01-01..last formation date with label exit ≤ 2026-06-02 |
| Early blocks (printed) | E1 2019, E2 2020, E3 2021 |
| Training-only dates | 2022-01-01..2022-07-05 |
| Embargo | every C1 label exit ≤ 2026-06-02 |
| Training window | formation dates from 2013-01-02, label exit before the block's first test date; ≥ 100 training dates; bracket from 2019-01-02 |
| Minimum complete cases per date | 100 |
| Group date | all 11 sectors with ≥ 25 eligible labelled members with valid group features |
| Formation calendar, entry | every fifth session from index 252; entry close of t+1; exit close of t+1+h |
| Eligibility | V2 §3 (PIT member, quoted price, close ≥ $5) |
| Baseline B\* | B2's model B2 (50 regressors) + `grp_dispersion_60`, `grp_vol_60`, `grp_medvol_60`, `grp_te_120`, `grp_size` + tier indicators + `rank(beta_252d) × z(SPY ret_20/60/120)` + `rank(vol_60d) × z(SPY vol_20)`; z over trailing 252 sessions |
| Group features G | `grp_rs_60`, `grp_rs_120`, `grp_rs_consistency_120`, `grp_participation_50`, `grp_hit_20`, `grp_leader_retention_60x60`, `grp_coherence_60`; redundancy drop at median cross-sector |ρ| > 0.80 (later-numbered dropped) |
| Sector-level ranking | across the K sectors present: `(r − 0.5) / K − 0.5`; no leave-one-out; zero within-sector variance asserted |
| Model I terms | `wr120`, `wr120 × grp_rs_120`, `wr120 × grp_participation_50`; `wr120` = within-sector percentile rank of `ret_120d` − 0.5 |
| Unlabelled handling | primary labelled-only; Bracket NI (group ranks 0, interactions 0, no indicator); Bracket CM (aggregates from current members); pseudo-sector forbidden |
| Test of a mean | B2 §6: cosine long-run variance; `ν = max(4, min(floor(0.4 n^(2/3)), floor(n / (2 ceil(h / 5)))))`; Student t, one-sided, unrounded |
| Validity refusal | no gate where `floor(n / (2 ceil(h / 5))) < 4` (h = 60 needs n ≥ 96) |
| C1 selection | (i) mean ≥ 0.010; (ii) p ≤ 0.10; (iii) ≥ 4 of 5 blocks; (iv) same sign under Bracket NI; (v) W5 11 of 11; primary h 20 A − B\*; interaction cell h 20 I − A; I − B\* never |
| Power rule | σ_LR from the development series; `δ* = max(0.008, 0.5 × development mean)`; n_read(cell) = smallest n in {48, 96, 144} with power ≥ 0.80 at one-sided 0.025 (noncentral t, ν(n)); futile otherwise; `n_read = n_read(primary)` |
| C2 sequence | 1: `rel_spy_20` A − B\*; 2: `rel_spy_60` A − B\* if n_read ≥ 96; 3: `rel_spy_20` I − A; each at 0.025; proceed only on a full pass |
| C2 gates | W1 p ≤ 0.025; W2 ≥ 3 of 4 equal-count consecutive blocks; W3 spread difference ≥ 0.0025 (h 20) / 0.0050 (h 60); W5 11 of 11. No W4, K3, K5 |
| C2 read | once, when the n_read-th confirmatory formation date has a complete label at the longest live horizon; first n_read dates per horizon; no re-read |
| C2 start | first formation-calendar date after the freeze date (UTC committer date of the first `master` commit containing this file at its sha256); bridge 2026-06-03..freeze printed only |
| C2 labels | earliest digest-pinned snapshot with `label_asof` ≥ formation date; fallback `cba7fc07…0de3` |
| Interim | one, first session on or after freeze date + 182 days; data health only; no forward-label statistic |
| Frozen coefficients | every model and horizon, fitted once on formation dates from 2013-01-02 with label exit before the first confirmatory date; sha256 in the constants block |
| Files | `research/data/trend_persistence_c1_attempt.json`, `trend_persistence_c1_result.json`, `trend_persistence_c2_constants.json`, `trend_persistence_c2_interim.json`, `trend_persistence_c2_result.json` |
| Instrument | `research/trend_persistence_group.py`; imports the loaders of `trend_persistence_substrate.py` / `trend_persistence_panel.py` and the test of a mean from `trend_persistence_walkforward.py`; edits none of them |
| Pins in the instrument | `PREREG_SHA256` (this file), `B2_RESULT_SHA256`, `V2_PANEL_SHA256`, `SECTOR_SNAPSHOT_SHA256`, `MEMBERSHIP_SHA256`; any mismatch refuses the run |

Unit tests required before the C1 run, named here so that their absence is a deviation: zero
within-sector variance of every sector-level regressor; reproduction of the two B2 means;
validity refusal at h = 60 with n < 96 and acceptance at n = 96; determinism of the redundancy
rule; the group-date rule; Bracket NI sets ranks 0, interactions 0 and adds no indicator; the
snapshot chosen for a confirmatory date is the earliest with `label_asof` on or after it;
the embargo drops every C1 label exiting after 2026-06-02.

## 12. What was looked at before this freeze

- V2's development and holdout results and B2's result on the same formation dates — path
  features and forward drawdown — and the readout. **No group feature, no group model and no
  quantity joining a sector aggregate with any label has been computed on real data.** The B2
  baseline means quoted in §5 are read from the committed result, not recomputed.
- The Wave C-0 substrate and its coverage receipt; the leaver label rate by exit era; the
  four-date check that every unlabelled member is a future leaver; the smallest labelled
  sector per date; universe sizes by year. Prices were not read for these counts.
- Synthetic series only, for the test of §6 on sector-type data: with overlapping 60-session
  labels and n between 48 and 95 the test rejects a true zero 3.7–4.8% of the time at a stated
  2.5%; a null group-only score has a per-date IC standard deviation of about 0.076, 0.105 and
  0.150 when the between-sector share of return variance is 0.05, 0.10 and 0.20, against about
  0.026 for a stock-level score; a null A − B increment has a per-date standard deviation of
  about 0.014, 0.023 and 0.046 on the same assumptions; at n = 48 the detectable increment is
  about 0.010–0.046 rank IC. These are reasoning on an assumed variance share, which is why
  §6 fixes a rule for the read size rather than a number.
- A seat design brief (2026-10-04) and two independent adversarial analyses of it, one on
  construction and one on statistics, before anything was frozen. What changed from the brief
  as a result: the baseline, from "controls and squares" (B2's model B1) to B2's model B2 and
  then to B\* with sector-level volatility, size, tier and market-state terms; the brief's
  "unlabelled" bracket, forbidden as a basket of future leavers, replaced by Bracket NI and
  Bracket CM; leave-one-out removed; `grp_dispersion_60` and `grp_size` moved from the group
  features to the baseline; leader retention made non-overlapping; the interaction terms
  re-specified on the within-sector rank; gating of both labels reduced to the return label
  with drawdown reported; false-discovery adjustment across cells replaced by a fixed sequence;
  a fixed N of 48 replaced by the power rule with the validity refusal; "first gating read"
  replaced by one read; two authored documents replaced by this one document and a
  machine-written constants block; the selection rule raised from 4-of-5 blocks and 0.005 to
  the five conditions of §7.1; the confirmatory start moved from 2026-06-03 to the first date
  after the freeze, with the bridge printed; 2019–2021 made printed-only and training started
  in 2013; the minimum sector size raised from 20 to 25 with the all-eleven rule.
- Not looked at: price eligibility per sector-date; the real cross-sector correlations of the
  group features; the real long-run noise of any difference series; the real between-sector
  variance share. The first two are computed by the instrument before any fit and printed; the
  last two are what C1 measures.
