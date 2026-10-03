# Rates observation origin: preventing a missing update from becoming a momentum plateau

Operation: `rates-evidence-context-20260917-sol-002`. Scope: a verified source-contract finding and a conservative consumer qualification, not a live outage, trading-loss claim or change to Macro's data owner. Macro evidence pin: `60db17a8e6e59381f0648f110035b1cc513da638`.

## Verified mechanism

`engine/inputs.py` lines 184–205 defines `put()` with a default forward-fill limit of five. Its FRED rates, real-rate and breakeven loop calls that default. The resulting frame contains values at aligned frame dates even when the original source did not produce a new observation there. That fill can be appropriate for a carried-state display; it does not establish a new measurement or its knowledge time.

`engine/yield_momentum.py` (blob `ab0db4518e61fc8d3ba972c8ba1a9200ec2a9844`, SHA-256 `4c9c47173a4c32705838396a92cb11bc4bcf130945f16328c432bddbd145fdca`) obtains the reported observation date from the last non-null frame index. It correctly withholds a missing latest frame cell. Once the upstream fill replaces that missing cell, however, it cannot distinguish an observed value from an imputed one because that source-origin information is not in the received contract.

A controlled 90-weekday frame with 85 genuine synthetic observations and the latest five missing was passed through the exact downstream source. Without fill: status `stale`, reported date May 1, level and changes null. With the upstream five-row fill rule: status `available`, reported date May 8, level 4.84, five-row change 0 bp, 22-row change 17 bp, 63-row change 58 bp, acceleration -5 bp and `extreme_high_watch`. The last actual synthetic observation remained May 1. The upstream fill rule was reproduced on a weekday fixture; the full production feature builder and a live outage were not executed or proven. Receipt: `forward_fill_observation_clock_probe.json` in the original private evidence directory.

**Consequence:** a model cannot interpret flat or decelerating frame values as newly observed rate exhaustion without knowing whether those values were observed, carried or otherwise modeled. This finding does not establish that the September production snapshot suffered that gap, and it does not justify deleting global forward-fill behavior across unrelated consumers.

## Consumer correction in the existing PR

The rates projection now says `observation_origin=unverified`, `horizon_basis=source_frame_intervals`, and `freshness_basis=frame_alignment_only`, with an explicit forward-fill limitation. These are more precise descriptions of the received contract than calling every aligned row an observed interval. The original numeric readings, per-row source dates and all-false action authority are preserved. No raw-observation certification, history reconstruction, new calendar, new source store or trade gate is invented. The new origin regression failed before the correction and then passed with the relevant suite.

## Separate real-rate composition finding

The pinned existing `data/transmission/latest.json` already reports real 10-year levels and 22/63-interval changes. It is therefore an existing owner to extend, not a missing reason to create another real-rate engine. Its reported 10-year nominal 5.00%, real 2.62%, and breakeven 2.33% produce a **5 bp residual** in nominal minus real minus breakeven. Reported 63-interval changes 54 bp minus 41 bp minus 8 bp also leave 5 bp. These are arithmetic checks of an internal artifact, not independently verified market quotes or a mispricing signal.

The input owner retains independently sourced `breakeven_10y` where present and uses `tips_nominal_spread` only as fallback (`combine_first`). Independent fills, source basis, effective dates and quote conventions must therefore be reconciled before treating the three objects as an exact common-curve identity. The residual's specific cause is **unresolved**, not proven stale data or a confirmed source defect. Do not rewrite one component to force equality, and do not count identity-dependent inputs as independent confirmations.

## Exact existing-owner follow-up and falsifier

The source owner should expose genuine source-origin date, source identity/version, known availability and observed-versus-carried status alongside rates through its existing data/provenance contract. Preserve the declared calendar grid and horizon: dropping missing rows is not an acceptable replacement for five dated intervals. The downstream momentum owner must discriminate a genuinely flat observed interval from an equal-valued interval created only by fill. A regression must use the same final numerical frame but different source-origin masks and prove that raw-observation/currentness claims differ; unknown origin must remain unknown. A second regression must keep independently sourced breakevens separate from a matched-input arithmetic difference and flag unexplained residuals without inventing an economic signal.

The finding is falsified/closed when the actual producer-to-consumer contract carries that origin evidence and the controlled missing-tail case no longer promotes filled frame dates to new source observations. Production closure additionally requires actual source-to-served-output proof through existing Macro owners. Current PR #769 corrects its consumer description only; Macro source repair, real-rate companion qualification, point-in-time replay and forecasting validation remain separate work. Preserve RIC/Transmission, Prophet #6805, TOI/Radar, existing calendars, Evaluation OS and the three independent research assignments.
