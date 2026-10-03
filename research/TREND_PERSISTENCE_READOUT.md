# Trend Persistence — Development, holdout and walk-forward readout

Wave B, stock level. Development sample (formation dates 2003–2021), one holdout run
(formation dates 2022-07-06 to 2026-06-02) and one walk-forward comparison on the holdout
dates (Wave B2).

**Where this stands.** The family stops at Wave B for these constructions. The walk-forward
comparison (§11) found no model value. The 29 confirmed tests cover twelve features. Added to
a model built from trailing returns, beta and volatility in detail, those features raise its
rank correlation with forward drawdown by 0.001 to 0.002, and at the gated horizons the tenth
of stocks it rates most at risk catches no more of the deepest drawdowns. By the rule fixed
before that run, no calibrated profile, shadow snapshot or advisory field is built.

**The holdout.** The one holdout run is done (§10). All 29 development survivors passed
the four pre-registered holdout gates: 21 drawdown-shape tests and 8 path-quality tests. By
the rule fixed before the run, those two families are labelled `RESEARCH_PREDICTIVE` for
describing downside risk, on the confirmed members only.

**The label does not mean these features say something volatility does not.** A review after
the run (§4) found, and a committed benchmark confirms (§10), that simulated prices with no
trend persistence of any kind — no drift, no return autocorrelation, only volatility that
differs across stocks, clusters in time and rises after falls — pass the same holdout gates on
14 to 29 of the 29 tests. What the run establishes is narrower: these features are associated
with forward drawdown after eleven rank-linear controls, and that association is not
distinguished from one more estimate of volatility.

Gain retention had no survivor and stays `DESCRIPTIVE`. Nothing is promoted for forward return
(§2). The effect is small: between the top and bottom fifth of stocks on a confirmed feature,
average forward maximum drawdown differs by 0.03 to 1.2 percentage points. No advisory field,
score or gate follows from this.

## 1. Results in one view

| Question | Design | Tests | Survive development | Reading |
| --- | --- | --- | --- | --- |
| Do these features say anything about forward return vs SPY beyond momentum, volatility and beta? | V1 | 72 | **0** | Null. Closed for these constructions, this universe, these horizons. |
| Do they say anything about forward maximum drawdown beyond momentum, one volatility window and beta? | V1 | 72 | 34 | Not usable as evidence: volatility was under-controlled (§4). |
| Same, with volatility at four spans, downside volatility, the quoted-price mask and price floors on printed closes? | V2 | 72 | **29** | A filter, not evidence. These 29 go to the holdout. |
| Do the 29 hold on formation dates from 2022-07-06, on the repaired universe? | V2 holdout | 29 | **29 pass** | Passed the pre-registered gates. Small (§10). Not distinguished from volatility: next row. |
| Does a simulated market with volatility and no persistence pass the same gates? | V2 on simulated prices | 72 / 29 | **24–41 of 72** pass development, **14–29 of the 29** pass the holdout gates | Yes. The gates do not separate these features from volatility estimates (§10). |
| Added to a model of trailing returns, beta and volatility in detail, do the features behind the 29 tests improve its out-of-sample ranking of forward drawdown by a material amount? | B2, walk-forward on the holdout dates | 2 gated horizons | **0 pass** | No. Rank IC rises by 0.001 to 0.002 on a base of 0.49 to 0.53 and the flagged tenth catches no more events (§11). Nothing is built. |
| Once the realised volatility of the label's own window is known, is anything left beyond what two simulated volatility-only markets leave? | B2 | 29 | **3 pass** | Three overlapping distance-from-high tests, at about 0.01 rank correlation. Recorded; nothing rests on it (§11). |

A development survivor has passed pre-registered gates on a sample that was inspected before
V2 was written and that is tilted toward survivors (§5). Development alone confirms nothing.
The holdout run is the pre-registered confirmation (§10). The benchmark beside it says what
that confirmation can and cannot mean.

## 2. V1 — forward return relative to SPY: null

| Family | Endpoint | Tests | Survive | Largest abs mean IC | Largest abs HAC t |
| --- | --- | --- | --- | --- | --- |
| path quality | `forward_rel` | 36 | 0 | 0.0143 | 2.86 |
| path quality | `forward_max_drawdown` | 36 | 11 | 0.0249 | 9.06 |
| gain retention | `forward_rel` | 9 | 0 | 0.0138 | 2.82 |
| gain retention | `forward_max_drawdown` | 9 | 1 | 0.0200 | 5.94 |
| drawdown shape | `forward_rel` | 27 | 0 | 0.0084 | 2.75 |
| drawdown shape | `forward_max_drawdown` | 27 | 22 | 0.0965 | 24.03 |

No test of forward relative return clears the gates. 11 of 72 pass the false-discovery
step, but only 2 of the 72 reach an absolute mean IC of 0.010, and both fail the
non-overlapping check. The strongest, `signed_efficiency_120d` at 60 sessions, has mean IC
−0.014 (HAC t −2.9): a *cleaner* advance is followed by slightly *worse* relative return,
the opposite of a continuation claim, and it does not hold across eras. The full per-test
table is in Appendix B.

## 3. V1 — forward maximum drawdown: 34 survive, and why that is not used

Drawdown shape accounts for 22 of the 34. The largest is `max_drawdown_120d` at 60
sessions: mean IC +0.096 — stocks with a shallow past drawdown go on to have a shallow
forward drawdown. Appendix C has every test.

That reads like volatility persistence, and V1 controls volatility with a single 60-session
window. An exploratory rerun on the development sample (not pre-registered, labelled as
such) added volatility at 20, 120 and 252 sessions and downside volatility. The drawdown
ICs fell by about half and the gain-retention and signed-efficiency survivors disappeared.
V1's drawdown result is therefore mostly a statement about its control set. V2 fixes the
control set and tests the claim again.

## 4. Independent review of the instrument

An independent read-only review attacked the V1 instrument before any holdout use. Labels,
judge parity, inference, gate logic and feature arithmetic passed. It found:

| # | Finding | Severity | What was done |
| --- | --- | --- | --- |
| F1 | The audited sanitizer fills gaps inside a name's life; whether a day is inside depends on later prices. Eligibility and feature windows could rest on a filled price. 506 of 504,883 eligible stock-dates before 2022. | blocker, small | V2 uses a quoted-price mask. Measured on V1: survivors 34 → 35, largest change in any mean IC 0.0013. |
| F2 | `build_panel` took the holdout boundary as an argument, so a caller could score 2022+ as "development". | blocker (fence) | Boundaries are module constants; the argument is gone. The V1 run used the default and is unaffected. |
| F3 | The pre-registration hash was read from a relocatable path and never pinned; the survivor list for a holdout run was caller-supplied. | major | Hash pinned in code; nothing scores on a mismatch. A holdout run re-derives the survivors itself. |
| F4 | 864 of 2,249 pre-2022 member tickers have no price column, and the result did not say so. | major | Coverage is stamped on every result (§5). Repaired for the holdout window. |
| F5 | A holdout run computed and emitted coverage for horizons with no survivor. | minor | Horizons without a survivor are not touched. |
| F6 | The judge rounds p to four decimals before the false-discovery step. | minor | Kept and declared in V2 §5. |
| F7 | A test without a p-value dropped out of the false-discovery family. | minor | Such a test now enters as p = 1. None occurred in V1 (144 of 144 had a p-value). |
| F8 | Several small rules were implemented but not written down. | minor | Written into V2 §5–§6. |

**V1's holdout is closed.** With F1 and the volatility finding, a V1 holdout run would test
a design already known to be wrong. The instrument now refuses it.

### Second review — the V2 instrument, fence and substrate

V2 §7 makes an independent review a precondition of the holdout run. A second read-only
review attacked revision 1 of V2. It reproduced the development result exactly (29
survivors, every number), confirmed the statistics, the judge parity with eleven controls and
the survivor-only holdout path, and related no feature to any label on 2022 onward. Its
verdict: pass with fixes, and the holdout must not run until they land.

| # | Finding | Severity | What was done |
| --- | --- | --- | --- |
| B1 | The $1 and $5 floors were tested on back-adjusted prices, so a later split could decide eligibility on a holdout date. About 274 of 294,780 eligible stock-dates. | blocker, small | Floors are tested on the close as printed, read from the whole-market store, wherever it prints one. |
| B2 | For audited names the $5 floor was tested on the cleaner's rebuilt level, which can sit far from the printed price. 1,091 holdout stock-dates failed $5 on the rebuilt level while printing $5 or more; 181 the other way. | major | Same fix. |
| A1 | A holdout run was not tied to the inputs the development result used, and the survivor re-check could not see the store-sourced block. | major | Every result carries a digest of its panel. A holdout run refuses unless its panel matches the development result's. The inputs are snapshotted. |
| A2 | The holdout run would have printed statistics V2 did not list: quintile-group, era and non-overlapping statistics and a hit rate. | minor | The holdout forms and prints only what V2 §7 and §9 list. |
| A3 | A deliberate caller could get around the fence: alter a panel, edit the design registry, call private functions, or use the older generic harness. | minor | The registry is read-only and a panel off the pre-registered calendar is refused. What the fence cannot bind is declared in V2 §0 and §10. |
| C1 | Large single-day moves remain in store-sourced names after cleaning, and some raw jumps look like splits the reference does not list. | minor | Counted in §5. The audited-only bracket printed beside each holdout number shows the effect. |
| D2 | A survivor with no usable holdout date would have vanished from the output. | minor | It is printed as unconfirmed. |

The repairs change eligibility, so V2 was re-frozen as revision 2 and development was scored
again (§6, §7).

### Re-review of revision 2

A third read-only review, by a different reviewer, attacked the diff that made the repairs
(`28c445e0..9a429b70`). It reproduced the committed development result with no field
differing, confirmed the pin and the panel digest, reproduced every count in V2 §3 and the
repaired coverage columns, and confirmed on known splits that the store's closes are
unadjusted. It related no feature to any label on 2022 onward. Its verdict: pass with fixes —
no blocker, no major finding, and the holdout may be run once as the code stands, with the
items below fixed or recorded first.

They are recorded here before the run. The instrument that runs the holdout is the
instrument that was reviewed, unchanged; the code fixes follow the run.

| # | Finding | Severity | Disposition |
| --- | --- | --- | --- |
| N1 | A holdout run is bound to the development result the caller supplies, not to a digest pinned in code. Development could be scored on other inputs and the holdout then run on those. | minor | Deviation from V2 §0 (Binding). The run uses the committed development result; panel digest `48cb5e76…` is printed on both results. Fixed after the run: `HOLDOUT_PANEL_SHA256` pins the one panel a design's holdout may be scored on, and a test proves a self-consistent development result on another panel is refused. |
| N2 | On holdout dates the instrument still computes the share of positive dates, the non-overlapping t and the era means, then deletes them. V2 §7 says they are not computed. | minor | Deviation from V2 §7. They are never printed or read. Fixed after the run: on holdout dates they are no longer formed. The development result reproduces byte for byte on the fixed code. |
| N3 | No test covers the printed-$1 leg of the quoted-price mask or the loader that applies it. | minor | Test added after the run (`test_a_printed_close_under_a_dollar_is_not_a_quote`). |
| N4 | A wrong print in the store on an audited name now moves its quote test. PLMR prints $0.01–0.03 for 14 sessions from 2023-03-16 against a real price near $55, which takes it out of the cross-section until its windows clear. 81 member cells since the store began are unquoted by a print under $1 while the adjusted price is $1 or more; most are real sub-$1 prints. | minor | Disclosed here. V2 §10 says store prints are taken as they are. |
| N4b | The audited panel keys prices by today's ticker. Where a symbol changed hands (DOC, HR, SAFE, CNR among them), the audited column holds the successor company's prices for the earlier member. | minor | Disclosed here. It predates this work and affects development and holdout alike. For those names the floor test reads the right company's printed close while features, controls and labels read the audited column. |
| N5 | V2 §3 says about 50 names are on the fallback. The count is 34, and they are not only class shares and renamed symbols (MPT, DCH and GAP are among them). | note | An error in the frozen text. It changes no rule, so the document is not re-frozen. |
| N6 | `score` trusts the digest stored in the panel it is handed. | note | The edge V2 §0 already declares. |

### Fourth review: the conclusion

A fourth read-only review, by a different reviewer, attacked the holdout conclusion in §10
after the run. It recomputed every number in §10 from the committed result, re-derived the
four holdout gates and the false-discovery step for all 29 tests, and checked that no feature
window overlaps its label window. All of that holds. Its verdict on the reading was **fail**:
§10 presented the confirmed tests as saying something beyond volatility, and the instrument
cannot show that.

| # | Finding | Severity | Disposition |
| --- | --- | --- | --- |
| R1 | Simulated prices with no drift, no return autocorrelation and nothing but volatility differences give positive ICs of the same order as the confirmed ones, pass all seven development gates on a third of the 72 tests, and pass the holdout gates on most of the 29. | blocker, on the reading | Accepted. Reproduced independently and committed as a benchmark (`research/trend_persistence_null.py`; §10, "Against a market with only volatility"). The reading in §10 is rewritten. |
| R2 | The limit "a dependence on volatility that is not rank-linear can pass through" was stated as a possibility. It is measured, and it is the size of the effect. | major | Accepted. §10 limits rewritten. |
| R3 | "Holdout ICs did not shrink" was offered as support. An artefact of volatility does not shrink either, and development and holdout are different universes. | major | Accepted. Paragraph rewritten. |
| R4 | The `distance_to_high` confirmations lean on store-sourced names far more than the two tests §10 named. | major | Accepted. §10 brackets now print all nine. |
| R5 | The fifths for `distance_to_high` form an inverted U, and the simulated market reproduces that shape. | minor | Accepted. Shape paragraph rewritten. |
| R6 | Two rows of the third review's table were both numbered N4. | minor | The second is now N4b. |
| R7 | The holdout result stores no false-discovery q. The largest, recomputed, is 0.0415. | note | Recorded here. The result file is not regenerated. |

No number in §10 changed. What is claimed from them did.

### Fifth review: the B2 design, before its run

A fifth read-only review, by a different reviewer, attacked the B2 pre-registration and
instrument as first frozen (commit `b20e5f63`). It worked on simulated data only, before any
real run. Its verdict: **fail**. No real B2 run was made under that freeze. The design was
changed and frozen again (`research/TREND_PERSISTENCE_PREREG_B2.md` §12 lists what changed and
what did not).

| # | Finding | Severity | Disposition |
| --- | --- | --- | --- |
| B1 | The gate that asks whether a test says more than volatility (K5) compared each test with the largest of ten simulated run means, one test at a time. With one simulated run left out, every `clustered_leverage_jumps` run was given the label. | blocker | K5 now considers all 29 tests together. Per simulated specification, 100 runs give the largest leave-one-out standardised excess over the 29 tests; a real test must exceed the 95th of those for both specifications. On 100 further runs of each specification the rule gave the label to 0 and 4. |
| M1 | V2's significance rule (Bartlett kernel, normal reference) rejected a true zero 4.8% and 6.8% of the time at a stated 2.5%, at 20 and 60 sessions. B2's gates used it. | major | Every gating p-value in B2 now comes from an equal-weighted cosine variance with a Student t reference. On centred simulated series it rejects 2.2% to 3.4% at a stated 2.5%. V2's t is still printed beside it. V2's own result is not rescored; B2 prints V2's statistic under both rules. |
| M2 | The simulated reference was not tied to the code that produced it, and the frozen design left out constants a result depends on. | major | The reference stores one hash over the four modules a result depends on. The instrument refuses real data if that hash, the reference's file hash, the pre-registration's hash or the design constants differ. |
| M3 | The one-run guard could be passed by naming another output file, and a crash left no record. | major | One fixed result path. An attempt record is written before real prices are read. A second attempt needs a stated reason, which is kept in the result. An uncommitted tree is refused. |
| m1 | p-values were rounded to four decimals before gating. | minor | Not rounded. |
| m2 | The V2 holdout result was read without checking its hash. | minor | Pinned. |
| m3 | The label "path information" claimed more than the test shows. | minor | The label is `beyond_simulated_volatility`. B2 §8 says what it does not prove. |
| m4 | The calibration gate (W4) passes in almost every simulated run. | minor | Stated in B2 §7: 115 of 120. It is not evidence for the family. |
| m5 | K4's floor is applied to a statistic that a strong control has already shrunk. | minor | Stated in B2 §7. K5 is the higher bar for 28 of the 29 tests. |
| m6 | B2 §6 described an order of operations the code did not follow. | minor | Text corrected. |
| m7 | The simulated calendar has more test dates than the real one, so its spread is about 2% narrow. | minor | The simulated spread is scaled to the real number of dates. |
| m8 | The reference stored only run means. | minor | It stores each run's p-values and test dates, the size table and the K5 table. |
| m9 | Gaps in the tests. | minor | Tests added for each change above. |

### Sixth review: the second B2 freeze, before its run

A sixth read-only review, by a reviewer who had not seen the earlier ones, attacked the second
freeze (commit `aadb15d2`). It read the committed files, ran the tests, recomputed the printed
numbers from the committed reference and tried scratch copies of the guards. It read no real
price. Its verdict: **pass, with one fix required before the run**.

It found B1, M1, M2 and m1 to m9 closed or disclosed. Every number printed in B2 §7 matched its
recomputation: both K5 thresholds, all 29 bars, the 24 cells of the size table, the label
rates on the 200 threshold-setting runs and the 200 fresh ones, and the Q1 gate counts. On its
own made-up overlapping noise the new test rejected a true zero 2.55% and 2.72% of the time at
a stated 2.5% (20 and 60 sessions), against 4.45% and 6.82% for V2's rule.

| # | Finding | Severity | Disposition |
| --- | --- | --- | --- |
| NEW-1 | The code's one-run guard rests on a local file. Delete the attempt file, run from another checkout, or call the comparison function directly, and a second run leaves no trace. The dirty-tree check also ignores a deleted attempt file. B2 §6 and the M3 row above claim more than the code delivers. | major | Fixed by procedure, as the reviewer allowed, with no change to the frozen files. The attempt was recorded in a comment on pull request 1155 before the run read any real price (comment `5969307706`, 2026-10-03 12:47:13Z). The run was made from the clean pushed commit. Its two output files were committed and pushed as written before this write-up (commit `d671d3c2`). The code guard itself is unchanged and is weaker than B2 §6 says. |
| NEW-2 | The code hash ignores anything appended after the hash on the two pin lines. | minor | Nothing is appended at the commit that ran: both lines end at the closing quote. To be fixed if B2 is ever frozen again. |
| NEW-3 | K5 controls false labels only for the two simulated markets it was built from. The jumps specification sets the bar for 26 of the 29 tests, and the two specifications' means differ by as much as K5's own margin on some tests. A volatility-only market with stronger jumps or a stronger leverage effect could clear K5 more often than 5%. Also: "none of 40 passes all four gates" has a 95% upper bound near 9%. | minor | Disclosed in B2 §8 and §10. The heading over the label-rate table in B2 §7 reads more broadly than that. Three tests carry the label in the result (§11). The value question failed, so nothing rests on it. |
| NIT | A retry reason is kept in the result but the decision does not flag it. | — | No retry was needed: `attempts` in the result has one entry with no retry reason. |

The reviewer could not check three things: the fresh runs' label rates from first principles
(their statistics are not stored, only their labels), the size of the W1 test on the model
difference series itself, and B2 §6's statement that the simulated calendar trains on about as
many stock-dates as the real panel (its rough estimate was 750,000 against 525,918). The
`numpy` and `pandas` versions are not pinned.

### Seventh review: the B2 write-up

A seventh read-only review, by a reviewer who had not seen the earlier ones, attacked §11 and
the passages changed with it (commit `36e3899a`). It recomputed every printed number from the
committed result, re-derived gates W1 to W4 and K1 to K5 and the decision from the stored
statistics, and checked the commit history against the run record. It did not run the
instrument and read no price. Its verdict: **pass with fixes**. No number, gate or decision
differed. Every finding was about wording or disclosure.

| # | Finding | Severity | Disposition |
| --- | --- | --- | --- |
| M1 | The baseline was described as volatility only. Model B2 also holds trailing returns, beta, their squares and return-by-volatility products, which are close relatives of the features. No model of volatility descriptors alone was fitted. | major | §11, the opening and §1 now name what the baseline holds and say it removes part of the features by construction. |
| m1 | "The flags do not move" said more than the tables: only capture and the flagged tenth's mean drawdown were measured, and at 5 sessions capture and the Brier score do improve. | minor | Reworded. The 5-session numbers and the position of the 60-session capture difference in the simulated range are stated. |
| m2 | The list of limits left out two that B2 §10 states: removing the label window's volatility is a decomposition and not a causal control, and only one functional form was fitted. | minor | Both added, with the cross-sectional nature of the event. |
| m3 | "What it says" covered two of the three labelled tests and treated overlapping windows as separate findings. | minor | Reworded: one overlapping family. |
| m4 | The write-up did not say how demanding W3 is. One point of capture is about what the whole step from B1 to B2 adds. | minor | Stated after the layer table. The null does not rest on the bar, because the observed gain is zero or negative at the gated horizons. |
| m5 | B2 §9 promises V2's t beside every mean; the table prints only the new test's. | minor | The table says where V2's t is in the result file. |
| — | "29 features" should be 29 tests on twelve features; "near one half" did not hold at 5 sessions; "B2" meant both the wave and a model; some terms were undefined in §11. | nit | Corrected. |

The reviewer could not check the pull-request comment or its time, since it had no access to
GitHub. The comment is `5969307706`, created 2026-10-03 12:47:13Z; the attempt file records
the run starting at 12:47:29Z.

## 5. Substrate: what the universe actually is

Members by the membership file, and how many have a price, on the first session of the
year. *Eligible price* means a quoted price that also clears the $5 floor.

| Year | Members | Audited panel, quoted | Repaired, quoted | Repaired, eligible price |
| --- | --- | --- | --- | --- |
| 2004 | 494 | 268 | 268 | 256 |
| 2008 | 497 | 314 | 314 | 306 |
| 2012 | 497 | 346 | 346 | 331 |
| 2013 | 920 | 593 | 593 | 577 |
| 2016 | 920 | 647 | 647 | 642 |
| 2019 | 913 | 726 | 726 | 721 |
| 2020 | 1,521 | 1,085 | 1,085 | 1,074 |
| 2021 | 1,521 | 1,125 | 1,125 | 1,113 |
| 2022 | 1,516 | 1,167 | 1,501 | 1,492 |
| 2023 | 1,514 | 1,222 | 1,507 | 1,489 |
| 2024 | 1,510 | 1,314 | 1,506 | 1,498 |
| 2025 | 1,507 | 1,385 | 1,504 | 1,498 |
| 2026 | 1,506 | 1,458 | 1,505 | 1,496 |

Three things follow.

- **The membership file is not a constant S&P 1500.** It lists about 500 names until 2012,
  about 920 from 2013 and about 1,520 from 2020.
- **The audited panel is survivor-tilted.** It prices 54–80% of members in development,
  mostly names that are still listed. `loop/factor_experiment.py` calls the panel
  "survivorship-safe"; for this universe that overstates it. Every development number in
  this readout carries that tilt.
- **The holdout universe is close to whole.** For 2022 onward the gap is repaired from the
  whole-market daily store (410 names, split adjustment from a committed vendor reference,
  validated against the audited panel on names both sources hold: 91 of 91 real splits
  matched, no false adjustment). The repaired panel prices 99% or more of members, and
  98–99% are eligible. Names that left before mid-2021 cannot be repaired.

**Price floors on printed closes.** From 2021-07-06 the $1 and $5 floors are tested on the
close as it printed. On the 197 holdout formation dates that have a 5-session label
(2022-07-06 to 2026-06-02; prices and membership only):

| | Stock-dates |
| --- | --- |
| Members | 297,167 |
| Print $5 or more | 290,276 |
| — of those, eligible | 290,240 |
| Print under $5 (18 under $1) — not eligible | 2,314 |
| No printed close | 4,577 |
| — of those, eligible on the adjusted, cleaned price | 3,818 |
| Eligible in all | 294,058 |

98.7% of eligible stock-dates were tested on a printed close. The 1.3% on the fallback are
about 50 names: four class-share symbols the store files differently (BF-B, BRK-B, CWEN-A,
MOG-A) and symbols the store starts carrying only after a ticker change. Per formation date
roughly 1,480 to 1,500 names are eligible and roughly 1,460 to 1,495 have every feature and
control.

**What is still wrong in the store-sourced prices.** Counted by the second review, on prices
only, in the holdout window: 160 cleaned single-day moves beyond ±40% across 82 store-sourced
names (68 beyond ±55%). 3 of 29 applied split events do not match the raw price jump within
30% (BNED 2024-06-12, CARA 2024-12-31, and FI 2021-10-04, which falls in a listing the
segment rule drops). 16 split-like raw jumps are not in the reference; the review could not
verify those in RGS, KAMN, ORGO, APPS, MODV, WOLF and QURE, and identified those in FRC and
PACW as real crashes. A wrong price in a store-sourced name moves that name's features,
controls and labels. The audited-only bracket shows how much a holdout number leans on these
names.

## 6. V2 — development result

Controls: four trailing returns, volatility at 20/60/120/252 sessions, downside volatility at
60/252, beta. Quoted-price mask. Price floors on printed closes from 2021-07-06. Seven gates,
the seventh requiring the same sign in at least four of five volatility quintiles. 72 tests.

This is the result under revision 2. Revision 2 changes eligibility only in the last
half-year of the development sample (3–5% of development stock-dates have a printed close).
The survivors are the same 29 tests as under revision 1, no gate changed for any test, and
the largest change in any mean IC is 0.00002.

| Family | Tests | Survive |
| --- | --- | --- |
| drawdown shape | 27 | 21 |
| path quality | 36 | 8 |
| gain retention | 9 | 0 |

- **Drawdown shape.** `max_drawdown` and `distance_to_high` survive at every window and
  horizon, all positive: shallower past drawdown, shallower forward drawdown. Mean ICs run
  from +0.010 to +0.056 — about half of what V1's control set showed. `sessions_since_high`
  survives in 3 of 9.
- **Path quality.** `positive_day_fraction` survives in 6 of 9 and `efficiency_20d` in 2 of
  3, with mean ICs of +0.011 to +0.017. `directional_consistency` and `signed_efficiency`
  do not survive.
- **Gain retention.** Null under V2's controls. The single V1 survivor does not survive them.

These are small effects. The largest mean IC is 0.056. One survivor is there by a hair:
`distance_to_high_20d` at 5 sessions clears the 0.010 floor by 0.00002, in both revisions.

| Feature | h | Mean IC | HAC t | BH q | V1 controls | Momentum only | Raw | Gates failed | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `directional_consistency_20d` | 5 | -0.0036 | -2.10 | 0.0497 | -0.0030 | +0.0192 | +0.0076 | G2, G4, G5, G6 | no |
| `directional_consistency_20d` | 20 | -0.0057 | -2.94 | 0.0057 | -0.0076 | +0.0225 | +0.0070 | G2, G5, G6 | no |
| `directional_consistency_20d` | 60 | -0.0085 | -3.86 | 0.0002 | -0.0094 | +0.0239 | +0.0044 | G2, G3, G5, G6 | no |
| `directional_consistency_60d` | 5 | -0.0043 | -2.30 | 0.0308 | -0.0094 | +0.0174 | +0.0103 | G2, G5, G6 | no |
| `directional_consistency_60d` | 20 | -0.0103 | -3.57 | 0.0007 | -0.0164 | +0.0203 | +0.0087 | G3, G5 | no |
| `directional_consistency_60d` | 60 | -0.0187 | -4.90 | 0.0000 | -0.0247 | +0.0152 | -0.0024 | G5 | no |
| `directional_consistency_120d` | 5 | -0.0089 | -4.16 | 0.0000 | -0.0086 | +0.0138 | +0.0082 | G2, G5, G6 | no |
| `directional_consistency_120d` | 20 | -0.0190 | -5.57 | 0.0000 | -0.0177 | +0.0124 | +0.0021 | G5 | no |
| `directional_consistency_120d` | 60 | -0.0272 | -5.83 | 0.0000 | -0.0245 | +0.0097 | -0.0042 | G5 | no |
| `efficiency_20d` | 5 | +0.0172 | +8.55 | 0.0000 | +0.0188 | +0.0516 | +0.0054 | — | yes |
| `efficiency_20d` | 20 | +0.0173 | +6.25 | 0.0000 | +0.0163 | +0.0590 | -0.0008 | — | yes |
| `efficiency_20d` | 60 | +0.0071 | +2.36 | 0.0273 | +0.0059 | +0.0507 | -0.0150 | G2, G3, G5, G6, G7 | no |
| `efficiency_60d` | 5 | +0.0093 | +3.66 | 0.0004 | +0.0128 | +0.0461 | -0.0045 | G2, G6, G7 | no |
| `efficiency_60d` | 20 | +0.0072 | +1.75 | 0.1069 | +0.0101 | +0.0548 | -0.0150 | G1, G2, G6, G7 | no |
| `efficiency_60d` | 60 | -0.0072 | -1.57 | 0.1419 | -0.0057 | +0.0413 | -0.0368 | G1, G2, G5, G6 | no |
| `efficiency_120d` | 5 | +0.0025 | +0.85 | 0.4282 | +0.0061 | +0.0430 | -0.0185 | G1, G2, G3, G6, G7 | no |
| `efficiency_120d` | 20 | -0.0068 | -1.42 | 0.1883 | -0.0014 | +0.0482 | -0.0382 | G1, G2, G3, G5, G6 | no |
| `efficiency_120d` | 60 | -0.0177 | -2.72 | 0.0102 | -0.0139 | +0.0402 | -0.0535 | G5 | no |
| `positive_day_fraction_20d` | 5 | +0.0107 | +5.62 | 0.0000 | +0.0111 | +0.0311 | +0.0526 | — | yes |
| `positive_day_fraction_20d` | 20 | +0.0093 | +3.65 | 0.0005 | +0.0090 | +0.0356 | +0.0607 | G2, G6 | no |
| `positive_day_fraction_20d` | 60 | +0.0092 | +3.58 | 0.0005 | +0.0113 | +0.0401 | +0.0570 | G2, G6 | no |
| `positive_day_fraction_60d` | 5 | +0.0139 | +7.28 | 0.0000 | +0.0137 | +0.0436 | +0.0703 | — | yes |
| `positive_day_fraction_60d` | 20 | +0.0150 | +5.06 | 0.0000 | +0.0144 | +0.0552 | +0.0875 | — | yes |
| `positive_day_fraction_60d` | 60 | +0.0117 | +2.93 | 0.0057 | +0.0142 | +0.0590 | +0.0845 | — | yes |
| `positive_day_fraction_120d` | 5 | +0.0136 | +7.71 | 0.0000 | +0.0166 | +0.0518 | +0.0804 | — | yes |
| `positive_day_fraction_120d` | 20 | +0.0149 | +4.99 | 0.0000 | +0.0188 | +0.0672 | +0.1009 | — | yes |
| `positive_day_fraction_120d` | 60 | +0.0107 | +2.41 | 0.0244 | +0.0183 | +0.0719 | +0.1007 | G7 | no |
| `signed_efficiency_20d` | 5 | +0.0072 | +3.83 | 0.0002 | +0.0106 | +0.0516 | +0.0581 | G2, G6 | no |
| `signed_efficiency_20d` | 20 | +0.0057 | +2.35 | 0.0273 | +0.0063 | +0.0635 | +0.0687 | G2, G3, G6 | no |
| `signed_efficiency_20d` | 60 | +0.0023 | +0.71 | 0.5083 | +0.0050 | +0.0677 | +0.0592 | G1, G2, G3, G4, G6 | no |
| `signed_efficiency_60d` | 5 | -0.0006 | -0.29 | 0.7680 | +0.0056 | +0.0762 | +0.0756 | G1, G2, G3, G4, G5, G6, G7 | no |
| `signed_efficiency_60d` | 20 | -0.0017 | -0.51 | 0.6302 | +0.0049 | +0.1023 | +0.0962 | G1, G2, G3, G4, G5, G6, G7 | no |
| `signed_efficiency_60d` | 60 | -0.0082 | -1.60 | 0.1349 | -0.0045 | +0.1095 | +0.0881 | G1, G2, G3, G4, G5, G6, G7 | no |
| `signed_efficiency_120d` | 5 | -0.0020 | -0.92 | 0.3981 | +0.0088 | +0.0951 | +0.0879 | G1, G2, G3, G4, G5, G6, G7 | no |
| `signed_efficiency_120d` | 20 | -0.0064 | -1.74 | 0.1075 | +0.0090 | +0.1304 | +0.1111 | G1, G2, G3, G5, G6, G7 | no |
| `signed_efficiency_120d` | 60 | -0.0093 | -2.01 | 0.0609 | +0.0066 | +0.1452 | +0.1102 | G2, G3, G5, G6, G7 | no |
| `retained_20d` | 5 | +0.0083 | +4.35 | 0.0000 | +0.0115 | +0.0524 | +0.0594 | G2, G6 | no |
| `retained_20d` | 20 | +0.0068 | +2.75 | 0.0098 | +0.0072 | +0.0643 | +0.0703 | G2, G3, G6 | no |
| `retained_20d` | 60 | +0.0034 | +1.08 | 0.3276 | +0.0060 | +0.0685 | +0.0608 | G1, G2, G3, G4, G6 | no |
| `retained_60d` | 5 | +0.0034 | +1.61 | 0.1349 | +0.0096 | +0.0791 | +0.0804 | G1, G2, G3, G4, G6 | no |
| `retained_60d` | 20 | +0.0036 | +1.05 | 0.3321 | +0.0100 | +0.1058 | +0.1023 | G1, G2, G4, G6 | no |
| `retained_60d` | 60 | -0.0025 | -0.46 | 0.6567 | +0.0011 | +0.1131 | +0.0954 | G1, G2, G3, G4, G5, G6, G7 | no |
| `retained_120d` | 5 | +0.0056 | +2.21 | 0.0384 | +0.0167 | +0.0998 | +0.0988 | G2, G3, G5, G6 | no |
| `retained_120d` | 20 | +0.0045 | +1.09 | 0.3265 | +0.0199 | +0.1370 | +0.1279 | G1, G2, G3, G4, G5, G6 | no |
| `retained_120d` | 60 | +0.0039 | +0.71 | 0.5083 | +0.0194 | +0.1529 | +0.1307 | G1, G2, G3, G4, G5, G6 | no |
| `distance_to_high_20d` | 5 | +0.0100 | +4.75 | 0.0000 | +0.0235 | +0.1360 | +0.1528 | — | yes |
| `distance_to_high_20d` | 20 | +0.0167 | +7.08 | 0.0000 | +0.0291 | +0.1817 | +0.2005 | — | yes |
| `distance_to_high_20d` | 60 | +0.0145 | +6.09 | 0.0000 | +0.0315 | +0.1959 | +0.2026 | — | yes |
| `distance_to_high_60d` | 5 | +0.0165 | +7.60 | 0.0000 | +0.0246 | +0.1734 | +0.1793 | — | yes |
| `distance_to_high_60d` | 20 | +0.0255 | +9.47 | 0.0000 | +0.0354 | +0.2359 | +0.2364 | — | yes |
| `distance_to_high_60d` | 60 | +0.0273 | +9.40 | 0.0000 | +0.0397 | +0.2576 | +0.2424 | — | yes |
| `distance_to_high_120d` | 5 | +0.0216 | +10.49 | 0.0000 | +0.0384 | +0.1933 | +0.1962 | — | yes |
| `distance_to_high_120d` | 20 | +0.0355 | +12.10 | 0.0000 | +0.0587 | +0.2665 | +0.2606 | — | yes |
| `distance_to_high_120d` | 60 | +0.0406 | +10.60 | 0.0000 | +0.0677 | +0.2925 | +0.2693 | — | yes |
| `max_drawdown_20d` | 5 | +0.0185 | +9.72 | 0.0000 | +0.0437 | +0.2174 | +0.2538 | — | yes |
| `max_drawdown_20d` | 20 | +0.0280 | +11.04 | 0.0000 | +0.0503 | +0.2844 | +0.3288 | — | yes |
| `max_drawdown_20d` | 60 | +0.0275 | +9.95 | 0.0000 | +0.0573 | +0.3090 | +0.3440 | — | yes |
| `max_drawdown_60d` | 5 | +0.0246 | +10.79 | 0.0000 | +0.0284 | +0.2321 | +0.2722 | — | yes |
| `max_drawdown_60d` | 20 | +0.0412 | +13.09 | 0.0000 | +0.0465 | +0.3186 | +0.3649 | — | yes |
| `max_drawdown_60d` | 60 | +0.0472 | +13.31 | 0.0000 | +0.0506 | +0.3445 | +0.3856 | — | yes |
| `max_drawdown_120d` | 5 | +0.0269 | +13.03 | 0.0000 | +0.0505 | +0.2397 | +0.2834 | — | yes |
| `max_drawdown_120d` | 20 | +0.0442 | +14.01 | 0.0000 | +0.0803 | +0.3319 | +0.3831 | — | yes |
| `max_drawdown_120d` | 60 | +0.0557 | +12.17 | 0.0000 | +0.0964 | +0.3648 | +0.4133 | — | yes |
| `sessions_since_high_20d` | 5 | -0.0019 | -1.06 | 0.3294 | -0.0037 | -0.0198 | -0.0409 | G1, G2, G3, G4, G5, G6, G7 | no |
| `sessions_since_high_20d` | 20 | -0.0035 | -1.64 | 0.1310 | -0.0048 | -0.0277 | -0.0512 | G1, G2, G3, G4, G6, G7 | no |
| `sessions_since_high_20d` | 60 | -0.0013 | -0.57 | 0.5905 | -0.0033 | -0.0274 | -0.0436 | G1, G2, G3, G4, G5, G6, G7 | no |
| `sessions_since_high_60d` | 5 | -0.0091 | -5.05 | 0.0000 | -0.0077 | -0.0358 | -0.0575 | G2, G6 | no |
| `sessions_since_high_60d` | 20 | -0.0124 | -4.58 | 0.0000 | -0.0121 | -0.0513 | -0.0742 | — | yes |
| `sessions_since_high_60d` | 60 | -0.0086 | -2.74 | 0.0099 | -0.0079 | -0.0518 | -0.0682 | G2, G6 | no |
| `sessions_since_high_120d` | 5 | -0.0075 | -3.97 | 0.0002 | -0.0131 | -0.0428 | -0.0717 | G2, G4, G6 | no |
| `sessions_since_high_120d` | 20 | -0.0164 | -5.89 | 0.0000 | -0.0256 | -0.0673 | -0.0961 | — | yes |
| `sessions_since_high_120d` | 60 | -0.0154 | -4.77 | 0.0000 | -0.0253 | -0.0720 | -0.0950 | — | yes |

## 7. Deviations from the pre-registrations

- **V1 holdout not run.** V1 §7 scheduled it after review. The review and the volatility
  finding closed it instead (§4).
- **V1 development was rerun on the refactored instrument.** Every per-test number, the
  coverage and the survivor set are identical to the first run (commit `9ee79b75`).
- **F1 sensitivity** (§4) scores V1's design with the quoted-price mask. It is a diagnostic
  outside V1's frozen design.
- **The volatility rerun in §3 is exploratory.** It informed V2's design and is the reason
  V2 treats development as a filter.
- **Price-only work on 2022 onward** was done to build and validate the repair: split
  validation, gap counts, member coverage. No feature was related to any label there.
- **V2 was re-frozen before any holdout run.** Revision 1 (sha256 `e63d49eb…d24c`) is
  superseded by revision 2 (sha256 `2882865d…2d17`), which makes the repairs the second
  review required (§4). Development was scored again under revision 2: the same 29
  survivors, largest change in any mean IC 0.00002. Revision 1's development result is in
  git history at commit `28c445e0`.
- **V1's development result was re-emitted** on the revised instrument so that it carries a
  panel digest. Every statistic and the survivor set are identical.
- **The holdout run was bound to the supplied development result, not to a pin in code** (N1,
  §4). V2 §0 reads as if the committed result were enforced. The run used the committed
  result. The pin was added after the run.
- **Unlisted statistics were computed and discarded on holdout dates** (N2, §4). V2 §7 says
  they are not computed. They were never printed. The instrument no longer forms them.
- **The volatility-only benchmark in §10 is post hoc.** It was designed after the holdout
  result was seen, in answer to the fourth review (§4). It scores simulated prices only: no
  real label is read, and the holdout was not run again.
- **V2 §3 misstates the fallback names** (N5, §4): 34 names, not about 50.
- **B2 was frozen twice before any real run.** The first freeze (B2 sha256 `75bf31d8…7972b`,
  commit `b20e5f63`) failed the fifth review (§4). The second changes the significance test
  and the volatility gate and adds the code pin and the attempt record. No model was fitted on
  real data and nothing of B2's second question was computed on a date from 2022 onward
  between the two.
- **More price-only work on 2022 onward** was done for revision 2, by the author and by the
  second and third reviews: printed-against-adjusted price comparisons, floor counts under each rule,
  eligible and complete-case counts per formation date, large-move and split checks. No
  feature was related to any label there.
- **B2's one-run guard was completed by procedure, not by code.** B2 §6 says the instrument
  can be run once. The sixth review showed the code alone does not guarantee that (§4). The
  attempt was recorded publicly before the run and the outputs were pushed straight after it.
  The pre-registration was not edited.
- **The B2 §3 count was repeated before the run.** At the frozen commit, a minute before the
  attempt record, the price-only count of complete cases was run again to confirm the panel
  loads and matches V2's. It relates no feature to any label, and it matched the earlier
  count.

## 8. What happens next

1. Re-review of the changes revision 2 made — done (§4).
2. One holdout run — done (§10).
3. Code fixes N1–N3 from the re-review — done (§4).
4. Review of the conclusion and the volatility-only benchmark — done (§4, §10).
5. Walk-forward comparison (Wave B2), under its own pre-registration, two reviews before the
   run and one of the write-up — done (§11). The value question failed. By B2 §8 nothing is
   built and the family stops at Wave B for these constructions. The features stay available
   as descriptive fields.
6. Not entered: a calibrated profile, a shadow snapshot, an advisory field. Each was
   conditional on B2's value gates.
7. Open, and not started here: sector and size controls and group persistence (Wave C).
   They need point-in-time sector history for former members first.
8. Any further claim about these 29 features needs formation dates after 2026-06-02 or
   another universe. The dates from 2022-07-06 have been used by the V2 holdout and by B2.

Nothing above creates an advisory field, a score or a gate.

## 9. Reproduce

```
python3 -m research.trend_persistence_panel --design v1 --sample dev \
    --breadth-dir <breadth> --out research/data/trend_persistence_v1_dev.json
python3 -m research.trend_persistence_panel --design v2 --sample dev \
    --breadth-dir <breadth> --store-dir <massive_stock_day> \
    --out research/data/trend_persistence_v2_dev.json
```

`<breadth>` holds `_closes_deep.parquet`, `_closes_delisted.parquet` and
`sp1500_pit_membership.parquet`. Input digests are stamped in each result under
`provenance`, and the panel digest under `panel_sha256`.

The committed results were scored on these inputs (sha256, first 16 hex digits):
`_closes_deep.parquet` `88e3261ca077543a`, `_closes_delisted.parquet` `1e668fe0c181a59f`,
`sp1500_pit_membership.parquet` `7b34316c0561619b`, store-sourced block `4c86f65bb07784fe`, printed
closes `fae48d0d4fb90e19`. V2 panel digest: `48cb5e76269b3a50…`.

The holdout run. It was run once, on 2026-10-03; the result is
`research/data/trend_persistence_v2_holdout.json`:

```
python3 -m research.trend_persistence_panel --design v2 --sample holdout \
    --prereg-hash <sha256 of TREND_PERSISTENCE_PREREG_V2.md> \
    --dev-result research/data/trend_persistence_v2_dev.json \
    --breadth-dir <breadth> --store-dir <massive_stock_day> \
    --out research/data/trend_persistence_v2_holdout.json
```

It refuses a panel whose digest differs from the development result's or from the digest
pinned in `HOLDOUT_PANEL_SHA256`, so it can only reproduce the committed result on the same
inputs. It is not to be run for any other purpose.

The volatility-only benchmark (§10). Simulated prices; about 20 minutes:

```
python3 -m research.trend_persistence_null \
    --holdout-result research/data/trend_persistence_v2_holdout.json \
    --real-closes <breadth>/_closes_deep.parquet \
    --out research/data/trend_persistence_v2_null.json
```

`--real-closes` is optional. It reads prices before 2022 only, to print the real volatility
facts next to the simulated ones.

The B2 simulated reference. Simulated prices; about 15 minutes on 20 cores:

```
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
python3 -m research.trend_persistence_walkforward --reference --jobs 20 \
    --out research/data/trend_persistence_b2_reference.json
```

Two builds on the same machine gave identical runs.

The B2 run. It takes no output path and writes
`research/data/trend_persistence_b2_result.json`. It refuses to run while that file exists.
That guard is local (§4, sixth review). The run was made once, on 2026-10-03 (§11), and is
not to be made again.

```
python3 -m research.trend_persistence_walkforward \
    --breadth-dir <breadth> --store-dir <massive_stock_day>
```

## 10. V2 — holdout result

One run, on 2026-10-03, with the instrument as reviewed (code identical to commit `9a429b70`),
pre-registration `2882865d…2d17`, and the committed development result. The panel digest
(`48cb5e76…`) equals development's. Result: `research/data/trend_persistence_v2_holdout.json`.

**All 29 development survivors are confirmed.** Each passes the four pre-registered gates:
development sign, one-sided HAC p ≤ 0.05, false-discovery q ≤ 0.10 across the 29, absolute
mean IC ≥ 0.005.

| Family | Tests in V2 | Survived development | Confirmed | Tier after the run |
| --- | ---: | ---: | ---: | --- |
| drawdown shape | 27 | 21 | 21 | `RESEARCH_PREDICTIVE`, downside-risk description, the 21 members |
| path quality | 36 | 8 | 8 | `RESEARCH_PREDICTIVE`, downside-risk description, the 8 members |
| gain retention | 9 | 0 | — | `DESCRIPTIVE`; null printed in §6 |

The tier is the one V2 §8 fixed before the run, and it is applied as written. It records that
the pre-registered gates were passed. Those gates do not separate these features from
volatility (below), so the tier is not a claim that they do. It earns a walk-forward
comparison against a volatility-aware model (§8). It earns no advisory use.

| Horizon | Formation dates | First | Last | Median names | Store-sourced | Floor on printed close | Label carried through a delisting |
| ---: | ---: | --- | --- | ---: | ---: | ---: | ---: |
| 5 | 197 | 2022-07-06 | 2026-06-02 | 1,483 | 10.6% | 98.7% | 0.07% |
| 20 | 194 | 2022-07-06 | 2026-05-11 | 1,482 | 10.8% | 98.7% | 0.23% |
| 60 | 186 | 2022-07-06 | 2026-03-13 | 1,482 | 11.2% | 98.6% | 0.66% |

### How large the effect is

Small. Three ways to see it.

- **Mean IC.** After the eleven controls the confirmed ICs run from 0.007 to 0.051 in
  absolute value, median 0.024.
- **What the controls absorb.** `max_drawdown_120d` at 60 sessions is the strongest test. Its
  raw rank IC with forward drawdown is 0.42. With the four momentum controls it is 0.39. With
  V1's six controls it is 0.10. With V2's eleven it is 0.05. Most of what these features say
  about forward drawdown is volatility said another way, and the benchmark below shows the
  remainder is not clearly anything else.
- **In drawdown terms.** Sort stocks each date into fifths by the feature, after removing the
  controls. For the strongest test the bottom fifth's forward maximum drawdown averages
  −16.4% and the top fifth's −15.2%: 1.2 points over 60 sessions. Across the 29 tests the gap
  between the end fifths runs from 0.03 to 1.2 points, median 0.2.

The shape differs by feature. For `max_drawdown` over 60 and 120 sessions the five group
means are ordered (one pair, at the 5-session horizon, is 0.02 points out of order). For
`distance_to_high` the five means are not ordered in any of the nine tests: the bottom fifth
is the deepest, the second or third is the shallowest, and the top fifth — the stocks nearest
their high — is deeper than the second (60-day feature at 60 sessions: −16.7%, −15.2%,
−15.3%, −15.9%, −15.8%). The rank correlation is positive because of the bottom fifth. For
`max_drawdown_20d` the difference is also the bottom fifth. For `efficiency_20d` the lower two
fifths are deeper than the upper two by 0.1 to 0.3 points. For `positive_day_fraction` and
`sessions_since_high` the end fifths differ by 0.2 points or less and the middle fifths are
the deepest; the rank correlation passes the gates but the groups do not line up. The
simulated market below gives the same shapes: for `distance_to_high` both end fifths deeper
than the middle, and for `positive_day_fraction` the second and third fifths the deepest.

Holdout ICs are about the size of development's: the median ratio is 0.98 (drawdown shape
0.94, path quality 1.61; `efficiency_20d` at 20 sessions went from +0.017 to +0.031). That is
not support for the features. An association that comes from volatility would hold its size
as well, and the two samples are different universes: development's median date has 560
names and is tilted toward survivors (§5); the holdout's has 1,482 with former members
restored.

### Against a market with only volatility

The fourth review (§4) asked what the same instrument reports on prices that have no trend
persistence at all. `research/trend_persistence_null.py` simulates them: daily log returns
with zero mean and no autocorrelation, 500 stocks and a market factor, five specifications,
five seeds each. Each simulated panel is scored by the V2 instrument unchanged: a long panel
through development's seven gates, and an independent shorter one through the four holdout
gates, asked of the 29 real tests with their real development signs. No real label is read.
Result: `research/data/trend_persistence_v2_null.json`.

| Market | Volatility clustering, lag 1 / 20 / 60 | Leverage | Daily sd, 10th / 50th / 90th pct | Pass development, of 72 | Of the 29, pass the holdout gates |
| --- | --- | ---: | --- | ---: | ---: |
| Real prices, 2003–2021, 400 names | 0.25 / 0.16 / 0.10 | -0.049 | 1.6% / 2.3% / 3.3% | 29 | 29 |
| A. One volatility for every stock | -0.00 / 0.00 / -0.00 | -0.001 | 1.9% / 2.1% / 2.3% | 0 | 0–2 |
| B. Volatility differs by stock, constant in time | -0.00 / 0.00 / -0.00 | -0.002 | 1.4% / 2.1% / 3.2% | 2–6 | 8–13 |
| C. B, and volatility clusters in time | 0.15 / 0.10 / 0.07 | +0.005 | 1.8% / 2.6% / 3.8% | 9–12 | 8–11 |
| D. C, and falls raise volatility | 0.25 / 0.19 / 0.13 | -0.061 | 1.5% / 2.2% / 3.1% | 24–34 | 14–25 |
| E. D, and an occasional large move | 0.21 / 0.16 / 0.11 | -0.050 | 1.6% / 2.3% / 3.4% | 31–41 | 25–29 |

Ranges are over the five seeds. *Volatility clustering* is the median autocorrelation of
absolute daily returns. *Leverage* is the median correlation of a return with the next day's
absolute return. Market E is the closest to real prices on all three measures.

- **With one volatility for every stock the instrument finds nothing** (A). It is not biased
  when stocks do not differ.
- **Unequal volatility alone is enough to pass.** With volatility constant in time and
  independent returns (B), 8–13 of the 29 pass the holdout gates. Feature, controls and
  label are all noisy measures of the same volatility, and removing the controls rank-linearly
  leaves some of it behind.
- **The more the simulated volatility behaves like real volatility, the more pass.** In the
  market closest to real prices (E), 25–29 of the 29 pass, and 31–41 of the 72 pass
  development. Real prices gave 29.

Mean IC by feature group on the shorter simulated panels, against the holdout. The share of
the holdout IC is in brackets.

| Feature group | Tests | Mean holdout IC | B | C | D | E |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `distance_to_high` | 9 | +0.0213 | -0.0049 (-23%) | -0.0085 (-40%) | +0.0084 (40%) | +0.0113 (53%) |
| `max_drawdown` | 9 | +0.0336 | +0.0113 (34%) | +0.0173 (52%) | +0.0184 (55%) | +0.0336 (100%) |
| `sessions_since_high` | 3 | -0.0160 | +0.0001 (-1%) | +0.0075 (-47%) | -0.0014 (9%) | -0.0133 (83%) |
| `efficiency` | 2 | +0.0275 | +0.0132 (48%) | +0.0102 (37%) | +0.0084 (30%) | +0.0393 (143%) |
| `positive_day_fraction` | 6 | +0.0207 | +0.0009 (4%) | +0.0026 (13%) | +0.0162 (78%) | +0.0341 (165%) |

Seven tests have a holdout IC more than two standard deviations, across seeds, above the mean
of every simulated market: `distance_to_high_120d` at all three horizons,
`distance_to_high_60d` at 20 and 60 sessions, and `max_drawdown_120d` at 20 and 60 sessions.
They are 1.5 to 3.1 times market E's. The other 22 are inside what at least one simulated
market produces.

What follows:

- The pre-registered gates ask whether the IC is zero after rank-linear controls. A market
  with only volatility fails that test of zero as readily as real prices do. Passing the gates
  does not show information beyond volatility.
- For `efficiency_20d`, `positive_day_fraction`, `sessions_since_high`, `max_drawdown_20d` and
  `max_drawdown_60d`, market E reproduces most or all of the holdout IC.
- The seven tests above the simulated markets are not thereby shown to be something else.
  The simulation is one calibration, and real volatility has structure it lacks: sectors,
  earnings dates, regimes. They are the tests the next comparison looks at first (§8).

Per test, mean simulated IC on the shorter panels, and how many of the five runs pass the
holdout gates:

| Feature | Sessions | Holdout IC | B | C | D | E | Runs passing, D | Runs passing, E | Above every market |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `distance_to_high_20d` | 5 | +0.0073 | -0.0046 | -0.0101 | +0.0053 | +0.0092 | 2 of 5 | 4 of 5 | no |
| `distance_to_high_20d` | 20 | +0.0118 | -0.0062 | -0.0123 | +0.0086 | +0.0120 | 3 of 5 | 5 of 5 | no |
| `distance_to_high_20d` | 60 | +0.0135 | -0.0089 | -0.0135 | +0.0070 | +0.0074 | 4 of 5 | 4 of 5 | no |
| `distance_to_high_60d` | 5 | +0.0132 | -0.0026 | -0.0075 | +0.0057 | +0.0108 | 2 of 5 | 5 of 5 | no |
| `distance_to_high_60d` | 20 | +0.0260 | -0.0050 | -0.0099 | +0.0085 | +0.0135 | 3 of 5 | 5 of 5 | yes |
| `distance_to_high_60d` | 60 | +0.0259 | -0.0065 | -0.0088 | +0.0098 | +0.0124 | 3 of 5 | 4 of 5 | yes |
| `distance_to_high_120d` | 5 | +0.0211 | -0.0028 | -0.0041 | +0.0075 | +0.0111 | 4 of 5 | 5 of 5 | yes |
| `distance_to_high_120d` | 20 | +0.0366 | -0.0048 | -0.0057 | +0.0112 | +0.0136 | 3 of 5 | 5 of 5 | yes |
| `distance_to_high_120d` | 60 | +0.0360 | -0.0032 | -0.0048 | +0.0122 | +0.0117 | 3 of 5 | 4 of 5 | yes |
| `max_drawdown_20d` | 5 | +0.0220 | +0.0026 | +0.0111 | +0.0169 | +0.0394 | 5 of 5 | 5 of 5 | no |
| `max_drawdown_20d` | 20 | +0.0295 | +0.0047 | +0.0124 | +0.0203 | +0.0464 | 5 of 5 | 5 of 5 | no |
| `max_drawdown_20d` | 60 | +0.0289 | +0.0047 | +0.0099 | +0.0186 | +0.0346 | 5 of 5 | 5 of 5 | no |
| `max_drawdown_60d` | 5 | +0.0239 | +0.0125 | +0.0188 | +0.0189 | +0.0332 | 5 of 5 | 5 of 5 | no |
| `max_drawdown_60d` | 20 | +0.0380 | +0.0162 | +0.0239 | +0.0252 | +0.0422 | 5 of 5 | 5 of 5 | no |
| `max_drawdown_60d` | 60 | +0.0425 | +0.0156 | +0.0236 | +0.0229 | +0.0369 | 4 of 5 | 5 of 5 | no |
| `max_drawdown_120d` | 5 | +0.0253 | +0.0117 | +0.0144 | +0.0115 | +0.0215 | 4 of 5 | 5 of 5 | no |
| `max_drawdown_120d` | 20 | +0.0409 | +0.0167 | +0.0199 | +0.0155 | +0.0264 | 4 of 5 | 5 of 5 | yes |
| `max_drawdown_120d` | 60 | +0.0511 | +0.0172 | +0.0219 | +0.0158 | +0.0223 | 3 of 5 | 4 of 5 | yes |
| `sessions_since_high_60d` | 20 | -0.0181 | -0.0003 | +0.0105 | +0.0002 | -0.0178 | 0 of 5 | 5 of 5 | no |
| `sessions_since_high_120d` | 20 | -0.0155 | +0.0010 | +0.0068 | -0.0006 | -0.0130 | 0 of 5 | 5 of 5 | no |
| `sessions_since_high_120d` | 60 | -0.0143 | -0.0004 | +0.0052 | -0.0039 | -0.0091 | 0 of 5 | 3 of 5 | no |
| `efficiency_20d` | 5 | +0.0243 | +0.0109 | +0.0080 | +0.0063 | +0.0340 | 3 of 5 | 5 of 5 | no |
| `efficiency_20d` | 20 | +0.0308 | +0.0154 | +0.0123 | +0.0105 | +0.0445 | 4 of 5 | 5 of 5 | no |
| `positive_day_fraction_20d` | 5 | +0.0132 | -0.0001 | +0.0028 | +0.0115 | +0.0241 | 5 of 5 | 5 of 5 | no |
| `positive_day_fraction_60d` | 5 | +0.0224 | +0.0009 | +0.0027 | +0.0145 | +0.0337 | 5 of 5 | 5 of 5 | no |
| `positive_day_fraction_60d` | 20 | +0.0246 | +0.0013 | +0.0042 | +0.0198 | +0.0416 | 5 of 5 | 5 of 5 | no |
| `positive_day_fraction_60d` | 60 | +0.0188 | -0.0002 | +0.0046 | +0.0214 | +0.0358 | 5 of 5 | 5 of 5 | no |
| `positive_day_fraction_120d` | 5 | +0.0208 | +0.0014 | +0.0009 | +0.0127 | +0.0309 | 5 of 5 | 5 of 5 | no |
| `positive_day_fraction_120d` | 20 | +0.0244 | +0.0020 | +0.0005 | +0.0172 | +0.0385 | 5 of 5 | 5 of 5 | no |

### Brackets

- **Leavers' carried labels removed.** All 29 keep their sign and stay at 0.005 or above.
- **Audited names only** (store-sourced names removed). 27 of 29 keep their sign and stay at
  0.005 or above. The two that do not are `distance_to_high_20d` at 5 sessions (−0.0002) and
  at 20 sessions (+0.0038). The other `distance_to_high` tests shrink as well. Share of the
  holdout IC kept: the 20-day feature at 60 sessions, 41%; the 60-day feature, 42%, 66% and
  70% at 5, 20 and 60 sessions; the 120-day feature, 71%, 84% and 91%. `max_drawdown_20d`
  keeps 67% to 78%. Every other test keeps 86% or more. The `distance_to_high` confirmations
  lean on the repaired names, which are adjusted for splits only (V2 §10).
  `distance_to_high_20d` at 5 sessions is also the test that cleared development's IC floor
  by 0.00002, and its holdout p (0.042) is the weakest. It passes by the rule and is the
  marginal member.

### Every confirmed test

All four holdout gates pass on every row. "Six controls" and "Momentum only" are the same
statistic under V1's control set and under the four trailing returns alone. The last two
columns are the average forward maximum drawdown of the bottom and top fifth by
control-neutral feature rank.

| Feature | Sessions | Dev IC | Holdout IC | Dates | HAC t | p, one-sided | Leavers dropped | Audited only | Six controls | Momentum only | Raw | Bottom fifth | Top fifth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `distance_to_high_20d` | 5 | +0.0100 | +0.0073 | 197 | +1.73 | 0.0415 | +0.0068 | -0.0002 | +0.023 | +0.148 | +0.148 | -3.49% | -3.45% |
| `distance_to_high_20d` | 20 | +0.0167 | +0.0118 | 194 | +3.09 | 0.0010 | +0.0096 | +0.0038 | +0.027 | +0.200 | +0.192 | -8.84% | -8.66% |
| `distance_to_high_20d` | 60 | +0.0145 | +0.0135 | 186 | +4.26 | <0.0001 | +0.0079 | +0.0055 | +0.032 | +0.223 | +0.213 | -16.22% | -15.83% |
| `distance_to_high_60d` | 5 | +0.0165 | +0.0132 | 197 | +3.40 | 0.0003 | +0.0126 | +0.0055 | +0.019 | +0.186 | +0.182 | -3.59% | -3.44% |
| `distance_to_high_60d` | 20 | +0.0255 | +0.0260 | 194 | +4.89 | <0.0001 | +0.0234 | +0.0173 | +0.034 | +0.264 | +0.239 | -9.14% | -8.64% |
| `distance_to_high_60d` | 60 | +0.0273 | +0.0259 | 186 | +4.19 | <0.0001 | +0.0195 | +0.0180 | +0.035 | +0.290 | +0.259 | -16.74% | -15.83% |
| `distance_to_high_120d` | 5 | +0.0216 | +0.0211 | 197 | +5.27 | <0.0001 | +0.0205 | +0.0150 | +0.042 | +0.208 | +0.209 | -3.61% | -3.46% |
| `distance_to_high_120d` | 20 | +0.0355 | +0.0366 | 194 | +7.27 | <0.0001 | +0.0344 | +0.0308 | +0.067 | +0.295 | +0.273 | -9.17% | -8.64% |
| `distance_to_high_120d` | 60 | +0.0406 | +0.0360 | 186 | +6.20 | <0.0001 | +0.0304 | +0.0329 | +0.070 | +0.324 | +0.300 | -16.72% | -15.84% |
| `max_drawdown_20d` | 5 | +0.0185 | +0.0220 | 197 | +6.25 | <0.0001 | +0.0215 | +0.0147 | +0.051 | +0.230 | +0.242 | -3.58% | -3.35% |
| `max_drawdown_20d` | 20 | +0.0280 | +0.0295 | 194 | +6.19 | <0.0001 | +0.0278 | +0.0230 | +0.058 | +0.306 | +0.313 | -9.00% | -8.46% |
| `max_drawdown_20d` | 60 | +0.0275 | +0.0289 | 186 | +8.58 | <0.0001 | +0.0237 | +0.0218 | +0.062 | +0.336 | +0.340 | -16.45% | -15.62% |
| `max_drawdown_60d` | 5 | +0.0246 | +0.0239 | 197 | +6.18 | <0.0001 | +0.0235 | +0.0210 | +0.029 | +0.241 | +0.266 | -3.49% | -3.30% |
| `max_drawdown_60d` | 20 | +0.0412 | +0.0380 | 194 | +6.71 | <0.0001 | +0.0366 | +0.0343 | +0.043 | +0.337 | +0.354 | -8.82% | -8.28% |
| `max_drawdown_60d` | 60 | +0.0472 | +0.0425 | 186 | +6.31 | <0.0001 | +0.0403 | +0.0394 | +0.047 | +0.373 | +0.388 | -16.18% | -15.17% |
| `max_drawdown_120d` | 5 | +0.0269 | +0.0253 | 197 | +7.02 | <0.0001 | +0.0252 | +0.0253 | +0.054 | +0.250 | +0.281 | -3.54% | -3.29% |
| `max_drawdown_120d` | 20 | +0.0442 | +0.0409 | 194 | +6.74 | <0.0001 | +0.0408 | +0.0426 | +0.083 | +0.350 | +0.375 | -8.96% | -8.28% |
| `max_drawdown_120d` | 60 | +0.0557 | +0.0511 | 186 | +5.16 | <0.0001 | +0.0523 | +0.0541 | +0.097 | +0.391 | +0.420 | -16.41% | -15.18% |
| `sessions_since_high_60d` | 20 | -0.0124 | -0.0181 | 194 | -4.78 | <0.0001 | -0.0174 | -0.0178 | -0.015 | -0.041 | -0.088 | -8.35% | -8.50% |
| `sessions_since_high_120d` | 20 | -0.0164 | -0.0155 | 194 | -4.13 | <0.0001 | -0.0153 | -0.0169 | -0.025 | -0.041 | -0.109 | -8.45% | -8.49% |
| `sessions_since_high_120d` | 60 | -0.0154 | -0.0143 | 186 | -3.48 | 0.0003 | -0.0143 | -0.0175 | -0.026 | -0.044 | -0.123 | -15.50% | -15.56% |
| `efficiency_20d` | 5 | +0.0172 | +0.0243 | 197 | +6.03 | <0.0001 | +0.0240 | +0.0223 | +0.029 | +0.050 | +0.011 | -3.47% | -3.37% |
| `efficiency_20d` | 20 | +0.0173 | +0.0308 | 194 | +7.44 | <0.0001 | +0.0302 | +0.0293 | +0.036 | +0.066 | +0.010 | -8.76% | -8.48% |
| `positive_day_fraction_20d` | 5 | +0.0107 | +0.0132 | 197 | +4.17 | <0.0001 | +0.0130 | +0.0113 | +0.010 | +0.027 | +0.057 | -3.35% | -3.32% |
| `positive_day_fraction_60d` | 5 | +0.0139 | +0.0224 | 197 | +7.07 | <0.0001 | +0.0222 | +0.0202 | +0.018 | +0.043 | +0.090 | -3.38% | -3.31% |
| `positive_day_fraction_60d` | 20 | +0.0150 | +0.0246 | 194 | +6.06 | <0.0001 | +0.0240 | +0.0225 | +0.020 | +0.056 | +0.109 | -8.54% | -8.43% |
| `positive_day_fraction_60d` | 60 | +0.0117 | +0.0188 | 186 | +4.05 | <0.0001 | +0.0180 | +0.0166 | +0.016 | +0.055 | +0.117 | -15.64% | -15.59% |
| `positive_day_fraction_120d` | 5 | +0.0136 | +0.0208 | 197 | +7.52 | <0.0001 | +0.0208 | +0.0200 | +0.022 | +0.057 | +0.114 | -3.35% | -3.33% |
| `positive_day_fraction_120d` | 20 | +0.0149 | +0.0244 | 194 | +6.56 | <0.0001 | +0.0244 | +0.0242 | +0.026 | +0.075 | +0.142 | -8.48% | -8.44% |

A positive IC means a higher feature value goes with a shallower forward drawdown.
`max_drawdown` and `distance_to_high` are zero or negative, so higher means a shallower past
drawdown or a price nearer its high.

### What this does not show

- **One period.** Four years, one rate cycle. At 60 sessions that is about fifteen
  non-overlapping windows. The t-statistics are HAC on overlapping labels; the
  non-overlapping check is a development gate and by design is not run on the holdout.
- **Few ideas.** 29 tests are four ideas: depth of the trailing drawdown, distance from the
  high, how long since the high, and how steady the advance was.
- **No sector or size control.** Point-in-time sector history does not exist for former
  members (the current map covers 3 of 1,083). Part of the effect may be sector membership.
- **Not separated from volatility.** Volatility at four spans and downside volatility at two
  are removed rank-linearly. What that leaves behind in a market with only volatility is the
  size of the effect (above). The run does not show that any confirmed feature says something
  a better volatility estimate would not.
- **Two universes.** Development's median date has 560 names, tilted toward survivors. The
  holdout's has 1,482. Agreement between them is not a like-for-like replication.
- **The benchmark is one calibration.** 500 simulated names against about 1,480 real ones,
  five seeds, specifications written after the result was seen. It gives a range for what
  volatility alone produces, not an estimate. With more names, more simulated tests would
  pass, not fewer.
- **Not a strategy and not a forecast of return.** V1 found nothing for forward return (§2).
  An IC ignores costs and turnover.
- **Deviations N1, N2 and N5** (§4, §7) were recorded before the run and do not change what
  it computed.

## 11. Wave B2 — walk-forward result

One run, on 2026-10-03 at 12:47 UTC, from commit `aadb15d2` with a clean tree:
pre-registration `79764bf5…80aa`, simulated reference `e2caf7e8…20f3`, code hash
`5c976ce8…fca6`. The attempt was recorded on pull request 1155 before the run read a real
price (§4, sixth review). It was the first attempt and needed no retry. The two files it wrote
are committed unedited (commit `d671d3c2`): `research/data/trend_persistence_b2_result.json`
and `research/data/trend_persistence_b2_attempt.json`. The panel is the one V2 was scored on
(digest `48cb5e76…f178`). Before fitting anything the instrument reproduced V2's 29 holdout
means from the committed result to 1e-9.

**Decision, by the rule in B2 §8: the null on model value.** Neither gated horizon passes the
value gates. No profile and no field is built, and the family stops at Wave B for these
constructions. The features stay available as descriptive fields.

### Value: do the features improve a volatility-aware model?

"B2" names both this wave and its baseline model. Below, "model B2" is the model and "B2 §8"
is a section of the pre-registration.

Model B2 is the baseline. It holds V2's eleven controls (trailing return at four spans,
volatility at four, downside volatility at two, and beta), their squares, eleven further
volatility descriptors (volatility at half-lives of 3, 10 and 30 sessions, mean and largest
absolute daily moves, downside volatility), their squares, and six products of trailing
return with volatility. Model A is model B2 plus the features confirmed at the horizon: 10,
11 and 8 of them at 5, 20 and 60 sessions. Both are refitted before each of five test blocks
(second half of 2022, then 2023, 2024, 2025, 2026), on earlier dates only. The event is a
stock whose forward maximum drawdown is in the deepest tenth on its date.

The baseline is not volatility alone. Trailing return and volatility over 20, 60 and 120
sessions are close relatives of distance from the high and trailing drawdown over the same
windows, so model B2 removes part of what the features measure by construction. The question
asked is what the features add to what is already cheap to know. No model built on
volatility descriptors alone was fitted.

Ranking. Rank IC is the correlation, across a date's stocks, between a model's score and the
rank of the realised forward drawdown.

| Horizon | Dates | Rank IC, B2 | Rank IC, A | A − B2 | t (df) | One-sided p | Blocks above zero | W1 | W2 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 5 | 197 | 0.3676 | 0.3683 | +0.00069 | 1.72 (13) | 0.055 | 5 of 5 | not gated | not gated |
| 20 | 194 | 0.4946 | 0.4959 | +0.00125 | 2.04 (13) | 0.031 | 5 of 5 | fail | pass |
| 60 | 186 | 0.5337 | 0.5354 | +0.00169 | 1.15 (7) | 0.143 | 3 of 5 | fail | fail |

Flags and calibration. Capture is the share of events among the tenth of stocks a model rates
most likely to be one. Chance is 10%. W3 asked for a gain of at least 1.0 point. The Brier
score is the mean squared error of the event probability; lower is better. The calibration
slope is 1 when the probabilities are neither too spread out nor too compressed.

| Horizon | Capture, B2 | Capture, A | A − B2 (points) | Brier, B2 | Brier, A | Calibration slope, A | W3 | W4 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 5 | 32.03% | 32.15% | +0.12 | 0.08130 | 0.08126 | 0.978 | not gated | not gated |
| 20 | 36.01% | 36.01% | +0.00 | 0.07822 | 0.07820 | 0.961 | fail | pass |
| 60 | 37.87% | 37.73% | −0.14 | 0.076477 | 0.076478 | 0.948 | fail | fail |

- **The ranking improves by one to two thousandths, on a base of 0.37 to 0.53.** The difference
  is positive at all three horizons and larger than in any of the 40 simulated runs (at 20
  sessions +0.00125 against −0.00000 to +0.00079; at 60, +0.00169 against −0.00008 to
  +0.00058). It does not reach the pre-registered 2.5% at either gated horizon, and at 60
  sessions it is positive in three blocks of five.
- **The flagged tenth catches no more events at the gated horizons.** A and model B2 put the
  same share of events in their top tenth at 20 sessions and A puts slightly fewer there at
  60. The mean forward drawdown of the flagged tenth is the same to within 0.03 points (A
  −14.43% and B2 −14.42% at 20 sessions; A −25.70% and B2 −25.73% at 60). Which names are
  flagged was not compared. The capture difference is inside the simulated range at every
  horizon; at 60 sessions it sits at the bottom of it (−0.1363 points against a simulated low
  of −0.1364).
  At 5 sessions, which does not gate, capture rises 0.12 points and the Brier score improves
  (one-sided p = 0.006).
- **The choice of test changes the name of the outcome, not its consequence.** Under V2's rule
  the 20-session t is 2.31 and W1 would pass. With W2 passing and W3 failing, that is B2 §8's
  "detectable and immaterial" branch, which the simulated market produces in 25 runs of 40.
  Both branches build nothing and stop the family here.

What each layer of the model buys, as rank IC:

| Horizon | B0: V2's controls | B1: plus their squares | B2: plus volatility descriptors and return × volatility products | A: plus confirmed features |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 0.3512 | 0.3521 | 0.3676 | 0.3683 |
| 20 | 0.4745 | 0.4767 | 0.4946 | 0.4959 |
| 60 | 0.5193 | 0.5219 | 0.5337 | 0.5354 |

The step from B1 to B2 (the descriptors, their squares and the products) adds 0.012 to 0.018
and 0.4 to 1.2 points of capture. The confirmed features add 0.001 to 0.002 after it and no
capture at the gated horizons.

W3 asks for about as much capture as that whole step adds: 1.0 to 1.2 points at 5 and 20
sessions, 0.4 at 60. The features add none at the gated horizons, so the null does not rest
on the height of the bar. A modest real effect would not have cleared it.

Reported, not gating:

- **Ablations.** The drawdown-shape features account for the whole difference: added alone
  they give +0.00064, +0.00121 and +0.00170 at 5, 20 and 60 sessions. The path-quality
  features alone give +0.00011, +0.00013 and +0.00004.
- **Audited names only.** +0.00027, +0.00086 and +0.00142.
- **Development dates, 2009 to 2021.** A − B2 is +0.00106, +0.00208 and +0.00378, positive in
  10, 11 and 12 of 13 years, with +0.11, +0.18 and +0.33 points of capture. The features were
  chosen on these dates and the universe there is tilted toward survivors, so this is not an
  out-of-sample number. It is larger than on the holdout dates and still far below W3's one
  point.

### Kind: is anything left beyond volatility?

For each of the 29 tests, the feature's rank is stripped of the eleven controls, their squares
and the realised volatility of the label's own window, which is not known at formation. What
is left is correlated with the label rank on each date.

Knowing the label window's volatility removes most of every association. The median test keeps
14% of V2's statistic (range −14% to 50%). The eleven descriptors, which are known at
formation, leave the median test with 69% of it. This is a decomposition, not a causal
control: a feature that predicts a drawdown which itself raises realised volatility loses
credit for it. The 14% is what survives the subtraction. It does not show the rest is a
volatility proxy.

| Gate | Requirement | Pass, of 29 |
| --- | --- | ---: |
| K1 | same sign as development | 27 |
| K2 | one-sided p ≤ 0.05 | 11 |
| K3 | Benjamini–Hochberg q ≤ 0.10 across the 29 | 8 |
| K4 | absolute mean of at least 0.005 | 7 |
| K5 | above what both simulated volatility-only markets leave, allowing for 29 tests | 4 |
| All five | | **3** |

The three are all distance from the high: `distance_to_high_60d` at 5 sessions (+0.0066),
`distance_to_high_120d` at 20 (+0.0111) and `distance_to_high_60d` at 20 (+0.0116). The result
records them as `beyond_simulated_volatility`. Because the value question failed, no profile
carries that label and nothing follows from it.

- **What it says.** How far a price sits below its 60- or 120-session high is associated with
  the next 5 and 20 sessions' drawdown at about 0.007 and 0.011 rank correlation once the
  window's own volatility is removed, and neither simulated volatility-only market leaves that
  much. The 60- and 120-session windows overlap heavily. The three labels are one overlapping
  family, not three independent findings.
- **What it does not say.** That this is trend persistence. The comparison is with two
  simulated markets; a market with only volatility, but stronger jumps or a stronger link
  from falls to volatility, could clear the same bar more often than 5% (§4, sixth review).
  There is no sector or size control. And inside model A the same features leave the flagged
  tenth unchanged.

Every mean below is multiplied by its development sign, so a positive number agrees with
development. The gated statistic is in bold. The two simulated markets are those of §10:
`clustered_leverage` has volatility that clusters and rises after falls, and
`clustered_leverage_jumps` adds jumps. "Excess" is the gated statistic's distance from each
simulated market's mean in that market's standard deviations; the bars are 2.95 and 2.87.
The gates column runs K1 to K5; ✓ is a pass.

| Feature | Horizon | V2's statistic | Controls and squares | Plus descriptors | Plus label-window volatility | Plus both | t | p | Excess, `clustered_leverage` | Excess, `clustered_leverage_jumps` | Gates | Labelled |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `distance_to_high_120d` | 5 | +0.0211 | +0.0254 | +0.0203 | **+0.0060** | +0.0049 | +1.77 | 0.0503 | +3.13 | +3.32 | ✓··✓✓ | no |
| `distance_to_high_20d` | 5 | +0.0073 | +0.0147 | +0.0087 | **+0.0018** | +0.0009 | +0.70 | 0.2478 | +0.32 | -0.50 | ✓···· | no |
| `distance_to_high_60d` | 5 | +0.0132 | +0.0213 | +0.0164 | **+0.0066** | +0.0052 | +2.29 | 0.0196 | +3.67 | +3.03 | ✓✓✓✓✓ | **yes** |
| `efficiency_20d` | 5 | +0.0243 | +0.0250 | +0.0106 | **+0.0025** | +0.0009 | +1.78 | 0.0496 | +0.92 | -0.94 | ✓✓··· | no |
| `max_drawdown_120d` | 5 | +0.0253 | +0.0218 | +0.0163 | **+0.0016** | +0.0019 | +0.61 | 0.2751 | +0.77 | -0.22 | ✓···· | no |
| `max_drawdown_20d` | 5 | +0.0220 | +0.0253 | +0.0104 | **+0.0019** | -0.0005 | +0.78 | 0.2242 | +0.51 | -1.28 | ✓···· | no |
| `max_drawdown_60d` | 5 | +0.0239 | +0.0177 | +0.0143 | **+0.0033** | +0.0031 | +1.30 | 0.1088 | +1.89 | +0.64 | ✓···· | no |
| `positive_day_fraction_120d` | 5 | +0.0208 | +0.0169 | +0.0112 | **+0.0043** | +0.0039 | +2.61 | 0.0107 | +2.84 | +1.33 | ✓✓✓·· | no |
| `positive_day_fraction_20d` | 5 | +0.0132 | +0.0098 | +0.0081 | **+0.0005** | +0.0010 | +0.21 | 0.4177 | +0.17 | -0.60 | ✓···· | no |
| `positive_day_fraction_60d` | 5 | +0.0224 | +0.0185 | +0.0116 | **+0.0047** | +0.0040 | +1.80 | 0.0475 | +3.30 | +1.66 | ✓✓··· | no |
| `distance_to_high_120d` | 20 | +0.0366 | +0.0420 | +0.0356 | **+0.0111** | +0.0103 | +3.15 | 0.0039 | +5.40 | +4.33 | ✓✓✓✓✓ | **yes** |
| `distance_to_high_20d` | 20 | +0.0118 | +0.0209 | +0.0138 | **+0.0017** | +0.0018 | +0.60 | 0.2784 | +1.60 | -0.69 | ✓···· | no |
| `distance_to_high_60d` | 20 | +0.0260 | +0.0348 | +0.0291 | **+0.0116** | +0.0110 | +3.24 | 0.0032 | +6.23 | +4.73 | ✓✓✓✓✓ | **yes** |
| `efficiency_20d` | 20 | +0.0308 | +0.0309 | +0.0119 | **+0.0040** | +0.0030 | +2.23 | 0.0220 | +2.53 | -0.25 | ✓✓✓·· | no |
| `max_drawdown_120d` | 20 | +0.0409 | +0.0342 | +0.0260 | **+0.0033** | +0.0034 | +0.72 | 0.2414 | +1.25 | +0.21 | ✓···· | no |
| `max_drawdown_20d` | 20 | +0.0295 | +0.0356 | +0.0193 | **+0.0072** | +0.0063 | +2.86 | 0.0067 | +3.82 | +1.44 | ✓✓✓✓· | no |
| `max_drawdown_60d` | 20 | +0.0380 | +0.0318 | +0.0276 | **+0.0094** | +0.0100 | +2.25 | 0.0214 | +4.03 | +2.65 | ✓✓✓✓· | no |
| `positive_day_fraction_120d` | 20 | +0.0244 | +0.0192 | +0.0121 | **+0.0049** | +0.0041 | +1.75 | 0.0518 | +2.43 | +0.66 | ✓···· | no |
| `positive_day_fraction_60d` | 20 | +0.0246 | +0.0214 | +0.0129 | **+0.0057** | +0.0053 | +1.88 | 0.0410 | +3.36 | +1.04 | ✓✓·✓· | no |
| `sessions_since_high_120d` | 20 | +0.0155 | +0.0158 | +0.0119 | **-0.0022** | -0.0022 | -0.88 | 0.8028 | -1.12 | -0.26 | ····· | no |
| `sessions_since_high_60d` | 20 | +0.0181 | +0.0172 | +0.0126 | **+0.0012** | +0.0010 | +0.47 | 0.3222 | +0.68 | +1.41 | ✓···· | no |
| `distance_to_high_120d` | 60 | +0.0360 | +0.0445 | +0.0382 | **+0.0015** | +0.0022 | +0.40 | 0.3499 | +1.60 | +0.37 | ✓···· | no |
| `distance_to_high_20d` | 60 | +0.0135 | +0.0247 | +0.0171 | **+0.0031** | +0.0036 | +2.44 | 0.0224 | +3.62 | +1.08 | ✓✓✓·· | no |
| `distance_to_high_60d` | 60 | +0.0259 | +0.0377 | +0.0325 | **+0.0041** | +0.0052 | +0.89 | 0.2024 | +3.27 | +1.37 | ✓···· | no |
| `max_drawdown_120d` | 60 | +0.0511 | +0.0416 | +0.0323 | **+0.0037** | +0.0030 | +0.43 | 0.3415 | +1.29 | +0.19 | ✓···· | no |
| `max_drawdown_20d` | 60 | +0.0289 | +0.0360 | +0.0232 | **+0.0044** | +0.0073 | +1.57 | 0.0800 | +3.93 | +0.19 | ✓···· | no |
| `max_drawdown_60d` | 60 | +0.0425 | +0.0352 | +0.0307 | **+0.0026** | +0.0033 | +0.59 | 0.2879 | +1.30 | -0.08 | ✓···· | no |
| `positive_day_fraction_60d` | 60 | +0.0188 | +0.0152 | +0.0091 | **+0.0014** | +0.0015 | +0.51 | 0.3136 | +1.18 | -0.64 | ✓···· | no |
| `sessions_since_high_120d` | 60 | +0.0143 | +0.0162 | +0.0146 | **-0.0016** | -0.0009 | -0.37 | 0.6404 | -0.57 | -0.62 | ····· | no |

Degrees of freedom are 13 at 5 and 20 sessions and 7 at 60. The t shown is the new test's.
V2's t for every mean in the table is in the result file (`q2.<test>.<series>.t_v2_rule`).

### V2's statistic under B2's test

The fifth review found that V2's significance rule rejects too often when labels overlap. B2
reports V2's own statistic on the same dates under both rules. Here it makes no difference:
under either, V2's mean is significant in the development direction at a one-sided 5% for 29
of 29 tests and at 2.5% for 28 of 29. The exception is `distance_to_high_20d` at 5 sessions
(p = 0.031 under the new test, 0.041 under V2's rule). V2's four holdout gates are not
re-applied here.

### What this settles and what it does not

Settled, for these 29 constructions on this universe:

- Added to a model of trailing returns, volatility and beta (V2's controls and their squares)
  plus the eleven volatility descriptors and the return-by-volatility products (model B2),
  these features change neither the share of deepest-tenth drawdowns caught by the top tenth
  nor the calibration by a material amount. Rank correlation rises by about 0.001. No
  calibrated profile, shadow snapshot or advisory field is built. The later waves, which were
  conditional on the value gates, are not entered.
- V2's label stands as §10 words it: `RESEARCH_PREDICTIVE` for describing downside risk, on
  the confirmed members, not distinguished from volatility. The walk-forward comparison adds
  that what the features carry beyond trailing returns, beta and volatility is too small to
  change which drawdowns a model catches.

Not settled:

- **Other constructions, and group persistence.** A null here closes these 29 tests, not the
  idea. Sector and group persistence (Wave C) was not attempted: it needs point-in-time sector
  history for former members.
- **The baseline removes part of the features by construction.** The null says the features
  add nothing material to trailing returns, beta and volatility. It does not say they carry
  nothing.
- **Removing the label window's volatility is a decomposition, not a causal control** (above).
- **One functional form.** Rank-linear least squares and logistic models only. Another form
  could give a different size.
- **The event is cross-sectional.** It says which stocks draw down most on a date, not when
  the market does.
- **These dates are used up.** Formation dates from 2022-07-06 to 2026-06-02 were V2's holdout
  and B2's test. A third claim cannot rest on them.
- **One period, five blocks.** At 60 sessions the test has 7 degrees of freedom.
- **The "beyond volatility" label is relative to two simulated markets** (above, and §4).
- **The one-run guard in the code is weaker than B2 §6 says.** The public attempt record and
  the immediate push of the outputs stand in for it (§4, §7).
- **Library versions are not pinned.** The simulated reference was rebuilt twice on one
  machine with identical results; another `numpy` or `pandas` could differ in late decimals.

## Appendix A — gate legend

G1 false-discovery q ≤ 0.10 · G2 absolute mean IC ≥ 0.010 · G3 non-overlapping series, same
sign and absolute t ≥ 2 · G4 same sign in 4 of 5 eras · G5 same sign in 4 of 5 momentum
quintiles · G6 same sign and floor with delisting-carried labels removed · G7 (V2 only) same
sign in 4 of 5 volatility quintiles.

## Appendix B — V1, forward return relative to SPY, every test

| Feature | h | Mean IC | HAC t | BH q | Momentum only | Raw | Gates failed | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `directional_consistency_20d` | 5 | -0.0002 | -0.09 | 0.9432 | -0.0012 | -0.0014 | G1, G2, G3, G4, G6 | no |
| `directional_consistency_20d` | 20 | +0.0015 | +0.67 | 0.6449 | -0.0010 | -0.0024 | G1, G2, G3, G4, G5, G6 | no |
| `directional_consistency_20d` | 60 | +0.0038 | +1.49 | 0.2272 | +0.0024 | +0.0024 | G1, G2, G3, G6 | no |
| `directional_consistency_60d` | 5 | +0.0045 | +2.54 | 0.0264 | +0.0045 | +0.0065 | G2, G3, G5, G6 | no |
| `directional_consistency_60d` | 20 | +0.0056 | +1.79 | 0.1368 | +0.0051 | +0.0084 | G1, G2, G3, G6 | no |
| `directional_consistency_60d` | 60 | -0.0025 | -0.64 | 0.6480 | -0.0036 | -0.0011 | G1, G2, G3, G4, G5, G6 | no |
| `directional_consistency_120d` | 5 | +0.0001 | +0.04 | 0.9686 | -0.0007 | +0.0031 | G1, G2, G3, G4, G5, G6 | no |
| `directional_consistency_120d` | 20 | -0.0019 | -0.59 | 0.6796 | -0.0038 | -0.0012 | G1, G2, G3, G4, G6 | no |
| `directional_consistency_120d` | 60 | -0.0074 | -1.74 | 0.1471 | -0.0084 | -0.0064 | G1, G2, G3, G6 | no |
| `efficiency_20d` | 5 | -0.0011 | -0.54 | 0.7075 | -0.0014 | -0.0046 | G1, G2, G3, G5, G6 | no |
| `efficiency_20d` | 20 | -0.0024 | -0.84 | 0.5296 | -0.0049 | -0.0089 | G1, G2, G3, G6 | no |
| `efficiency_20d` | 60 | -0.0014 | -0.44 | 0.7687 | -0.0034 | -0.0045 | G1, G2, G3, G4, G6 | no |
| `efficiency_60d` | 5 | +0.0043 | +2.01 | 0.0884 | +0.0032 | +0.0049 | G2, G3, G5, G6 | no |
| `efficiency_60d` | 20 | +0.0044 | +1.22 | 0.3226 | +0.0029 | +0.0055 | G1, G2, G3, G4, G5, G6 | no |
| `efficiency_60d` | 60 | -0.0034 | -0.78 | 0.5678 | -0.0059 | -0.0018 | G1, G2, G3, G6 | no |
| `efficiency_120d` | 5 | +0.0028 | +1.35 | 0.2755 | +0.0005 | +0.0058 | G1, G2, G3, G5, G6 | no |
| `efficiency_120d` | 20 | +0.0011 | +0.36 | 0.8160 | -0.0005 | +0.0034 | G1, G2, G3, G4, G5, G6 | no |
| `efficiency_120d` | 60 | -0.0060 | -1.29 | 0.2962 | -0.0049 | +0.0012 | G1, G2, G3, G4, G6 | no |
| `positive_day_fraction_20d` | 5 | +0.0006 | +0.38 | 0.8090 | +0.0007 | -0.0018 | G1, G2, G3, G4, G5, G6 | no |
| `positive_day_fraction_20d` | 20 | -0.0030 | -1.03 | 0.4208 | -0.0036 | -0.0113 | G1, G2, G3, G6 | no |
| `positive_day_fraction_20d` | 60 | +0.0048 | +1.39 | 0.2652 | +0.0036 | -0.0058 | G1, G2, G6 | no |
| `positive_day_fraction_60d` | 5 | +0.0019 | +0.94 | 0.4733 | +0.0017 | +0.0019 | G1, G2, G3, G4, G5, G6 | no |
| `positive_day_fraction_60d` | 20 | +0.0039 | +1.08 | 0.3939 | +0.0028 | -0.0024 | G1, G2, G3, G4, G5, G6 | no |
| `positive_day_fraction_60d` | 60 | +0.0043 | +0.77 | 0.5708 | +0.0009 | -0.0058 | G1, G2, G3, G4, G6 | no |
| `positive_day_fraction_120d` | 5 | +0.0018 | +0.88 | 0.5063 | +0.0012 | +0.0052 | G1, G2, G3, G4, G5, G6 | no |
| `positive_day_fraction_120d` | 20 | +0.0013 | +0.34 | 0.8187 | -0.0002 | -0.0020 | G1, G2, G3, G4, G5, G6 | no |
| `positive_day_fraction_120d` | 60 | +0.0010 | +0.20 | 0.8933 | -0.0008 | -0.0060 | G1, G2, G3, G4, G5, G6 | no |
| `signed_efficiency_20d` | 5 | +0.0010 | +0.48 | 0.7462 | -0.0002 | -0.0060 | G1, G2, G3, G4, G5, G6 | no |
| `signed_efficiency_20d` | 20 | +0.0005 | +0.18 | 0.8988 | -0.0015 | -0.0161 | G1, G2, G3, G4, G5, G6 | no |
| `signed_efficiency_20d` | 60 | +0.0008 | +0.24 | 0.8778 | +0.0006 | -0.0150 | G1, G2, G3, G4, G6 | no |
| `signed_efficiency_60d` | 5 | -0.0026 | -1.23 | 0.3226 | -0.0032 | -0.0030 | G1, G2, G3, G4, G5, G6 | no |
| `signed_efficiency_60d` | 20 | -0.0024 | -0.69 | 0.6304 | -0.0049 | -0.0104 | G1, G2, G3, G4, G5, G6 | no |
| `signed_efficiency_60d` | 60 | -0.0091 | -1.83 | 0.1269 | -0.0111 | -0.0159 | G1, G2, G3, G4, G6 | no |
| `signed_efficiency_120d` | 5 | -0.0054 | -2.59 | 0.0242 | -0.0055 | +0.0028 | G2, G6 | no |
| `signed_efficiency_120d` | 20 | -0.0082 | -2.37 | 0.0409 | -0.0108 | -0.0073 | G2, G3, G6 | no |
| `signed_efficiency_120d` | 60 | -0.0143 | -2.86 | 0.0119 | -0.0157 | -0.0132 | G3, G4 | no |
| `retained_20d` | 5 | +0.0011 | +0.53 | 0.7075 | -0.0002 | -0.0059 | G1, G2, G3, G4, G6 | no |
| `retained_20d` | 20 | +0.0003 | +0.10 | 0.9432 | -0.0019 | -0.0163 | G1, G2, G3, G4, G5, G6 | no |
| `retained_20d` | 60 | +0.0007 | +0.20 | 0.8933 | +0.0002 | -0.0152 | G1, G2, G3, G4, G6 | no |
| `retained_60d` | 5 | -0.0024 | -1.09 | 0.3912 | -0.0030 | -0.0020 | G1, G2, G3, G4, G5, G6 | no |
| `retained_60d` | 20 | -0.0021 | -0.57 | 0.6924 | -0.0049 | -0.0089 | G1, G2, G3, G4, G5, G6 | no |
| `retained_60d` | 60 | -0.0093 | -1.80 | 0.1346 | -0.0118 | -0.0173 | G1, G2, G3, G4, G6 | no |
| `retained_120d` | 5 | -0.0062 | -2.81 | 0.0136 | -0.0060 | +0.0021 | G2, G6 | no |
| `retained_120d` | 20 | -0.0080 | -2.23 | 0.0565 | -0.0107 | -0.0065 | G2, G3, G6 | no |
| `retained_120d` | 60 | -0.0138 | -2.82 | 0.0133 | -0.0156 | -0.0106 | G3 | no |
| `distance_to_high_20d` | 5 | +0.0010 | +0.40 | 0.7908 | +0.0015 | -0.0066 | G1, G2, G3, G4, G5, G6 | no |
| `distance_to_high_20d` | 20 | +0.0009 | +0.33 | 0.8208 | +0.0018 | -0.0119 | G1, G2, G3, G4, G5, G6 | no |
| `distance_to_high_20d` | 60 | +0.0036 | +1.37 | 0.2749 | +0.0030 | -0.0144 | G1, G2, G6 | no |
| `distance_to_high_60d` | 5 | -0.0003 | -0.12 | 0.9369 | +0.0012 | -0.0054 | G1, G2, G3, G4, G5, G6 | no |
| `distance_to_high_60d` | 20 | -0.0004 | -0.14 | 0.9257 | -0.0002 | -0.0142 | G1, G2, G3, G4, G5, G6 | no |
| `distance_to_high_60d` | 60 | +0.0038 | +0.97 | 0.4578 | +0.0029 | -0.0163 | G1, G2, G3, G4, G6 | no |
| `distance_to_high_120d` | 5 | -0.0005 | -0.23 | 0.8778 | +0.0012 | -0.0013 | G1, G2, G3, G4, G5, G6 | no |
| `distance_to_high_120d` | 20 | +0.0021 | +0.64 | 0.6480 | +0.0009 | -0.0103 | G1, G2, G3, G4, G6 | no |
| `distance_to_high_120d` | 60 | +0.0083 | +1.89 | 0.1156 | +0.0053 | -0.0136 | G1, G2, G3, G4, G6 | no |
| `max_drawdown_20d` | 5 | +0.0030 | +1.31 | 0.2915 | +0.0041 | -0.0007 | G1, G2, G3, G5, G6 | no |
| `max_drawdown_20d` | 20 | +0.0036 | +1.17 | 0.3480 | +0.0021 | -0.0114 | G1, G2, G3, G4, G5, G6 | no |
| `max_drawdown_20d` | 60 | +0.0072 | +1.77 | 0.1404 | +0.0049 | -0.0146 | G1, G2, G6 | no |
| `max_drawdown_60d` | 5 | +0.0001 | +0.04 | 0.9686 | +0.0029 | +0.0005 | G1, G2, G3, G4, G6 | no |
| `max_drawdown_60d` | 20 | +0.0051 | +1.46 | 0.2369 | +0.0038 | -0.0075 | G1, G2, G3, G4, G6 | no |
| `max_drawdown_60d` | 60 | +0.0023 | +0.54 | 0.7075 | +0.0003 | -0.0164 | G1, G2, G3, G4, G5, G6 | no |
| `max_drawdown_120d` | 5 | -0.0007 | -0.31 | 0.8300 | +0.0018 | +0.0032 | G1, G2, G3, G4, G5, G6 | no |
| `max_drawdown_120d` | 20 | +0.0015 | +0.44 | 0.7687 | -0.0008 | -0.0065 | G1, G2, G3, G6 | no |
| `max_drawdown_120d` | 60 | +0.0045 | +0.90 | 0.4928 | +0.0006 | -0.0124 | G1, G2, G3, G6 | no |
| `sessions_since_high_20d` | 5 | +0.0028 | +1.55 | 0.2088 | +0.0030 | +0.0072 | G1, G2, G3, G4, G5, G6 | no |
| `sessions_since_high_20d` | 20 | +0.0045 | +1.85 | 0.1219 | +0.0043 | +0.0142 | G1, G2, G3, G6 | no |
| `sessions_since_high_20d` | 60 | +0.0037 | +1.49 | 0.2272 | +0.0047 | +0.0126 | G1, G2, G3, G4, G6 | no |
| `sessions_since_high_60d` | 5 | +0.0048 | +2.75 | 0.0160 | +0.0055 | +0.0064 | G2, G3, G6 | no |
| `sessions_since_high_60d` | 20 | +0.0082 | +2.72 | 0.0170 | +0.0099 | +0.0152 | G2, G3, G6 | no |
| `sessions_since_high_60d` | 60 | +0.0084 | +2.28 | 0.0506 | +0.0104 | +0.0159 | G2, G3, G4, G6 | no |
| `sessions_since_high_120d` | 5 | +0.0029 | +1.59 | 0.1945 | +0.0036 | -0.0020 | G1, G2, G3, G6 | no |
| `sessions_since_high_120d` | 20 | +0.0019 | +0.64 | 0.6480 | +0.0037 | +0.0052 | G1, G2, G3, G4, G6 | no |
| `sessions_since_high_120d` | 60 | +0.0010 | +0.27 | 0.8559 | +0.0022 | +0.0049 | G1, G2, G3, G4, G5, G6 | no |

## Appendix C — V1, forward maximum drawdown, every test

| Feature | h | Mean IC | HAC t | BH q | Momentum only | Raw | Gates failed | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `directional_consistency_20d` | 5 | -0.0043 | -2.50 | 0.0295 | +0.0168 | +0.0043 | G2, G4, G5, G6 | no |
| `directional_consistency_20d` | 20 | -0.0082 | -3.95 | 0.0003 | +0.0205 | +0.0038 | G2, G6 | no |
| `directional_consistency_20d` | 60 | -0.0096 | -4.03 | 0.0003 | +0.0222 | +0.0013 | G2, G3, G6 | no |
| `directional_consistency_60d` | 5 | -0.0107 | -5.37 | 0.0000 | +0.0150 | +0.0071 | G5 | no |
| `directional_consistency_60d` | 20 | -0.0169 | -5.52 | 0.0000 | +0.0184 | +0.0056 | G5 | no |
| `directional_consistency_60d` | 60 | -0.0249 | -5.97 | 0.0000 | +0.0134 | -0.0053 | G5 | no |
| `directional_consistency_120d` | 5 | -0.0099 | -4.39 | 0.0000 | +0.0114 | +0.0051 | G2, G5, G6 | no |
| `directional_consistency_120d` | 20 | -0.0181 | -5.15 | 0.0000 | +0.0107 | -0.0007 | G5 | no |
| `directional_consistency_120d` | 60 | -0.0246 | -5.20 | 0.0000 | +0.0081 | -0.0068 | G5 | no |
| `efficiency_20d` | 5 | +0.0190 | +9.06 | 0.0000 | +0.0520 | +0.0064 | — | yes |
| `efficiency_20d` | 20 | +0.0160 | +5.29 | 0.0000 | +0.0592 | -0.0002 | — | yes |
| `efficiency_20d` | 60 | +0.0056 | +1.70 | 0.1593 | +0.0507 | -0.0144 | G1, G2, G3, G6 | no |
| `efficiency_60d` | 5 | +0.0130 | +4.75 | 0.0000 | +0.0468 | -0.0035 | — | yes |
| `efficiency_60d` | 20 | +0.0096 | +2.23 | 0.0565 | +0.0549 | -0.0146 | G2, G6 | no |
| `efficiency_60d` | 60 | -0.0064 | -1.40 | 0.2652 | +0.0414 | -0.0362 | G1, G2, G3, G4, G5, G6 | no |
| `efficiency_120d` | 5 | +0.0064 | +1.99 | 0.0917 | +0.0441 | -0.0168 | G2, G3, G6 | no |
| `efficiency_120d` | 20 | -0.0018 | -0.34 | 0.8187 | +0.0488 | -0.0370 | G1, G2, G3, G4, G5, G6 | no |
| `efficiency_120d` | 60 | -0.0145 | -2.07 | 0.0810 | +0.0407 | -0.0524 | G3, G5 | no |
| `positive_day_fraction_20d` | 5 | +0.0099 | +5.00 | 0.0000 | +0.0287 | +0.0490 | G2, G6 | no |
| `positive_day_fraction_20d` | 20 | +0.0087 | +3.12 | 0.0052 | +0.0338 | +0.0571 | G2, G3, G6 | no |
| `positive_day_fraction_20d` | 60 | +0.0113 | +3.72 | 0.0006 | +0.0384 | +0.0536 | — | yes |
| `positive_day_fraction_60d` | 5 | +0.0125 | +5.80 | 0.0000 | +0.0412 | +0.0664 | — | yes |
| `positive_day_fraction_60d` | 20 | +0.0145 | +4.31 | 0.0000 | +0.0536 | +0.0839 | — | yes |
| `positive_day_fraction_60d` | 60 | +0.0145 | +3.17 | 0.0045 | +0.0574 | +0.0810 | — | yes |
| `positive_day_fraction_120d` | 5 | +0.0156 | +7.55 | 0.0000 | +0.0494 | +0.0765 | — | yes |
| `positive_day_fraction_120d` | 20 | +0.0190 | +5.51 | 0.0000 | +0.0656 | +0.0973 | — | yes |
| `positive_day_fraction_120d` | 60 | +0.0188 | +3.61 | 0.0009 | +0.0704 | +0.0972 | — | yes |
| `signed_efficiency_20d` | 5 | +0.0102 | +4.83 | 0.0000 | +0.0519 | +0.0581 | — | yes |
| `signed_efficiency_20d` | 20 | +0.0059 | +2.21 | 0.0580 | +0.0636 | +0.0684 | G2, G3, G6 | no |
| `signed_efficiency_20d` | 60 | +0.0043 | +1.28 | 0.2962 | +0.0678 | +0.0588 | G1, G2, G3, G6 | no |
| `signed_efficiency_60d` | 5 | +0.0056 | +2.58 | 0.0242 | +0.0768 | +0.0758 | G2, G3, G5, G6 | no |
| `signed_efficiency_60d` | 20 | +0.0044 | +1.30 | 0.2925 | +0.1027 | +0.0959 | G1, G2, G4, G5, G6 | no |
| `signed_efficiency_60d` | 60 | -0.0053 | -1.03 | 0.4208 | +0.1096 | +0.0877 | G1, G2, G3, G4, G5, G6 | no |
| `signed_efficiency_120d` | 5 | +0.0091 | +3.90 | 0.0003 | +0.0960 | +0.0882 | G2, G5, G6 | no |
| `signed_efficiency_120d` | 20 | +0.0089 | +2.39 | 0.0388 | +0.1311 | +0.1109 | G2, G4, G5, G6 | no |
| `signed_efficiency_120d` | 60 | +0.0063 | +1.36 | 0.2755 | +0.1456 | +0.1100 | G1, G2, G3, G4, G5, G6 | no |
| `retained_20d` | 5 | +0.0112 | +5.25 | 0.0000 | +0.0526 | +0.0594 | — | yes |
| `retained_20d` | 20 | +0.0070 | +2.58 | 0.0242 | +0.0644 | +0.0699 | G2, G3, G6 | no |
| `retained_20d` | 60 | +0.0055 | +1.63 | 0.1814 | +0.0686 | +0.0604 | G1, G2, G3, G6 | no |
| `retained_60d` | 5 | +0.0097 | +4.13 | 0.0000 | +0.0796 | +0.0808 | G2, G5, G6 | no |
| `retained_60d` | 20 | +0.0097 | +2.70 | 0.0180 | +0.1062 | +0.1022 | G2, G5, G6 | no |
| `retained_60d` | 60 | +0.0005 | +0.09 | 0.9432 | +0.1132 | +0.0951 | G1, G2, G3, G4, G5, G6 | no |
| `retained_120d` | 5 | +0.0172 | +5.94 | 0.0000 | +0.1009 | +0.0996 | G5 | no |
| `retained_120d` | 20 | +0.0200 | +4.29 | 0.0000 | +0.1378 | +0.1283 | G5 | no |
| `retained_120d` | 60 | +0.0194 | +3.14 | 0.0050 | +0.1534 | +0.1309 | G5 | no |
| `distance_to_high_20d` | 5 | +0.0240 | +10.42 | 0.0000 | +0.1371 | +0.1534 | — | yes |
| `distance_to_high_20d` | 20 | +0.0296 | +11.05 | 0.0000 | +0.1830 | +0.2010 | — | yes |
| `distance_to_high_20d` | 60 | +0.0319 | +11.52 | 0.0000 | +0.1970 | +0.2030 | — | yes |
| `distance_to_high_60d` | 5 | +0.0244 | +10.46 | 0.0000 | +0.1742 | +0.1797 | — | yes |
| `distance_to_high_60d` | 20 | +0.0351 | +11.67 | 0.0000 | +0.2368 | +0.2365 | — | yes |
| `distance_to_high_60d` | 60 | +0.0394 | +10.95 | 0.0000 | +0.2584 | +0.2422 | — | yes |
| `distance_to_high_120d` | 5 | +0.0379 | +16.82 | 0.0000 | +0.1936 | +0.1963 | — | yes |
| `distance_to_high_120d` | 20 | +0.0580 | +17.42 | 0.0000 | +0.2670 | +0.2603 | — | yes |
| `distance_to_high_120d` | 60 | +0.0672 | +14.48 | 0.0000 | +0.2929 | +0.2689 | — | yes |
| `max_drawdown_20d` | 5 | +0.0447 | +17.74 | 0.0000 | +0.2190 | +0.2552 | — | yes |
| `max_drawdown_20d` | 20 | +0.0513 | +14.57 | 0.0000 | +0.2860 | +0.3301 | — | yes |
| `max_drawdown_20d` | 60 | +0.0579 | +14.93 | 0.0000 | +0.3103 | +0.3450 | — | yes |
| `max_drawdown_60d` | 5 | +0.0288 | +11.56 | 0.0000 | +0.2334 | +0.2735 | — | yes |
| `max_drawdown_60d` | 20 | +0.0466 | +13.40 | 0.0000 | +0.3198 | +0.3657 | — | yes |
| `max_drawdown_60d` | 60 | +0.0503 | +12.59 | 0.0000 | +0.3453 | +0.3860 | — | yes |
| `max_drawdown_120d` | 5 | +0.0504 | +21.60 | 0.0000 | +0.2407 | +0.2842 | — | yes |
| `max_drawdown_120d` | 20 | +0.0801 | +24.03 | 0.0000 | +0.3327 | +0.3836 | — | yes |
| `max_drawdown_120d` | 60 | +0.0965 | +18.50 | 0.0000 | +0.3654 | +0.4137 | — | yes |
| `sessions_since_high_20d` | 5 | -0.0037 | -2.04 | 0.0846 | -0.0201 | -0.0411 | G2, G3, G5, G6 | no |
| `sessions_since_high_20d` | 20 | -0.0049 | -2.21 | 0.0576 | -0.0281 | -0.0513 | G2, G3, G6 | no |
| `sessions_since_high_20d` | 60 | -0.0032 | -1.33 | 0.2823 | -0.0277 | -0.0436 | G1, G2, G3, G4, G5, G6 | no |
| `sessions_since_high_60d` | 5 | -0.0074 | -3.90 | 0.0003 | -0.0358 | -0.0573 | G2, G6 | no |
| `sessions_since_high_60d` | 20 | -0.0118 | -4.11 | 0.0000 | -0.0513 | -0.0736 | — | yes |
| `sessions_since_high_60d` | 60 | -0.0073 | -2.06 | 0.0817 | -0.0516 | -0.0674 | G2, G6 | no |
| `sessions_since_high_120d` | 5 | -0.0128 | -6.20 | 0.0000 | -0.0426 | -0.0715 | — | yes |
| `sessions_since_high_120d` | 20 | -0.0250 | -8.21 | 0.0000 | -0.0670 | -0.0956 | — | yes |
| `sessions_since_high_120d` | 60 | -0.0248 | -6.80 | 0.0000 | -0.0716 | -0.0943 | — | yes |
