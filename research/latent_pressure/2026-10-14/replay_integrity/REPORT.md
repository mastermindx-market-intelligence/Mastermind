# Recovery replay integrity: atomic observations, proven coverage and lossless research output

## What this continuation accomplished

The normalized recovery prototype now has a tested end-to-end path from a finite synthetic event fixture to a cutoff-aware research observation. This phase repaired actual correctness problems rather than fitting another model to the same already-studied market day.

**Verified scope:** explicit normalized synthetic events and their declared availability/coverage. **Not verified:** actual DEEP+ order-event mapping, real-book recovery/fatigue forecasting, independent-day predictive value, production installation or trading authority. Existing empirical results and their limitations are unchanged.

The original mission calls for useful earlier warnings, not merely attractive explanations. Timing mistakes in a recovery engine can create fictitious warnings; this phase removes several such paths before a real source is connected. It remains research/prototype work on the original PR1470 and original root `latent-pressure-research-20261014-chatgpt4-001`.

## 1. A false-depletion path was demonstrated and corrected

The original engine processed each normalized event as separately observable. That is appropriate for its single-event contract, but not for a source adapter that delivers an explicitly atomic group of updates.

In the constructed red case, an execution left40 units of an original100-unit displayed bid. A subsequent declared atomic observation deleted that remainder and re-added100 units before the complete observation became available. The original serial treatment recorded LEVEL_DEPLETED after the deletion, although the committed batch ended with restored depth.

`RecoveryBook.apply_batch` now stages and validates all changes before touching the public book or measurement history. Only the final committed state resolves an existing response. In this fixture it records RECOVERED, not an intermediate depletion. The resolution clock is the complete batch's availability time, not the first internal message time.

This does **not** assert that real equal-timestamp IEX messages are atomic. Equal timestamps are insufficient. Atomic boundaries must be supplied by a separately verified real-source mapping, which remains unavailable in this mission. The existing single-event `apply` interface remains valid for separately observable updates; serial deletion and addition still produce a real observed depletion under that explicit contract.

Additional batch rules prevent another manufactured prediction: a shock completely replenished or depleted inside the same committed observation is counted as an already observed event, not credited as a forecast of a later outcome. Executions at the initial best level are aggregated within the declared observation. Existing pending responses are not split and reopened on the same batch.

## 2. Batch failures can no longer leave partial effects

Every normalized event in a batch is checked before orders, clocks, censoring or response histories change. An unknown order, excessive execution, invalid identity, backward clock, partial batch or malformed final record rejects the whole batch.

The adversarial test deliberately places an apparently valid recovery before an invalid last event. After rejection, the entire book and response state must match the pre-batch state. A second test makes the invalid batch arrive after an old response's deadline: the failed batch must not even cause that response to expire.

These guarantees matter when a source eventually becomes available. A parser error halfway through a group must not leave a plausible-looking book snapshot or a completed recovery measurement.

The tests also check order accounting against a separate dictionary-based reference over **3,200 randomly generated normalized batches**, using forty fixed seeds. These are constructed inputs, not market data, an exchange simulator or evidence of predictive performance.

## 3. A cutoff no longer invents source coverage

A clock advancing is not proof that a feed remained observed. The new `replay_reader.py` therefore distinguishes the requested cutoff from the latest measurement cutoff supported by its input.

An explicitly supplied normalized WATERMARK confirms a known decoded prefix through a stated time. It must match the known sequence, cannot assert coverage after its receipt, and cannot later be contradicted by an older event. It is a fixture declaration, not an automatically inferred heartbeat or a new production service.

Without coverage through the requested cutoff, the reader returns `COVERAGE_NOT_PROVEN_TO_REQUESTED_CUTOFF`. It retains the last supported measurement instead of stretching the elapsed recovery duration through an unknown interval. Delayed coverage information cannot appear at an earlier cutoff. A source gap censors at the last proven observation, not at the later moment the gap is noticed.

Symbol and session state are isolated. Order IDs reused in another synthetic symbol or explicitly reset session do not inherit old quantities or recovery history. A reset retires and censors the previous session; it cannot silently continue it. A session switch without an explicit reset is rejected. Completed batch observation and source coverage remain separate concepts.

The original real-book decoder is still disabled. No add-side, modify, reset, priority, cancellation or hidden-liquidity meaning was guessed from an exchange message.

## 4. Exact arithmetic and JSON fixes

The original constructor accepted a Boolean or fractional horizon despite a nanosecond-integer contract. It now rejects those inputs, as well as invalid identity ranges and nonfinite or Boolean shock fractions.

A second fixture exposed a threshold problem with large quantities. When total displayed quantity is `2**60+1`, consuming its integer floor-half is strictly less than50%. A floating ratio can round that distinction away. The threshold now uses exact rational arithmetic, so a below-threshold event does not become a qualifying shock.

The original snapshot encoded its top-level clocks as strings but left nested pending-response timestamps and sequence IDs as JSON numbers. Large integers can be rounded by ordinary JavaScript consumers. The current research output recursively preserves integers beyond the safe JSON-number range as decimal strings. A related median calculation now retains large half-integer nanosecond durations without rounding them through a floating value.

The actual Python-produced demonstration was parsed by Node's JavaScript JSON parser. BigInt checks recovered the exact large start timestamps and sequences, and confirmed pending/completed outcomes, coverage limits, null forecast fields and false action authorities. This is a cross-language serialization check—not a browser deployment or live-source proof.

## 5. Executed end-to-end demonstration

The source-independent fixture contains two explicitly synthetic symbols, SYN-FAST and SYN-SLOW. Both begin with identical displayed depth and an observed shock. The input declares complete batches and coverage markers; it is not a sample decoded from the real IEX capture.

| Requested fixture cutoff | Verified observation |
|---|---|
| Shock cutoff | Both responses remain pending; neither final duration is available |
| Later proven coverage, before batch receipt | Both are still pending, now with two units of observed follow-up |
| Complete batch receipt | SYN-FAST is recovered after four units; SYN-SLOW's displayed level is depleted |
| One unit later without more proven coverage | Both measurements remain at the previous supported cutoff; the coverage gap is explicit |

All four command-line runs completed successfully. At the earlier cutoffs, appending the future recovery cannot alter the prior answer. The fast symbol's internal delete/re-add does not appear as a false externally observed depletion. Every output retains `forecast_probability=null`, `institutional_inventory=null` and false rotation-call, alert, rank and sizing authorities.

The output reuses the existing recovery engine and the existing descriptive competing-outcome summaries. No new production reader, collection pipeline, source-rights assertion, memory store, runtime lifecycle or trading system was created.

## 6. Verification and exact acceptance scope

Final source verification includes:

- **48 new test cases:**20 atomic-recovery tests and28 replay-reader tests.
- **34 affected existing test cases rerun:**18 original recovery-contract tests and16 censoring-adapter tests.
- **3,200 normalized batches** checked against independent dictionary bookkeeping inside the randomized test.
- **Four executed CLI cutoff cases** and one executed Python-to-JavaScript JSON round-trip.

Thus82 test cases ran on the final affected code. Unrelated earlier empirical or decoder suites were not rerun or added to this count. No earlier statistical model was refitted, no archive was rescanned and no prior real-data label audit was attempted.

`RED_OBSERVATIONS.json` records the constructed pre-repair findings. `ATOMIC_VALIDATION.json`, `VALIDATION.json`, `END_TO_END_PROOF.json` and `WIRE_PROOF.json` retain checks, source hashes and artifact identities. Initial atomic implementation commit: `3c424f0f4`; later replay and exact-median changes are identified by the final source hashes.

The dictionary and rational checks are separate deterministic reference implementations executed by the principal. They are not an independent model/human approval. No empirical forecast benefit is inferred from passing tests.

## 7. Remaining boundaries and scientific decision

The source-document inspection restriction is unchanged. A permitted, verified full DEEP+ order-event mapping is still needed before actual book reconstruction can proceed. When available, that adapter must explicitly establish event-group boundaries, order identity, side, quantity replacement/decrement, repricing/priority, session reset and sequence-gap behavior. It must then conserve order quantities on real input and preserve actual observation availability.

The previously blocked original GLM return check (`lp-clock04-design-review`) and the legacy timestamp-label impact audit were **not retried or rerouted**. Their last recorded status remains unresolved. This phase makes no assertion that the worker finished or that the old labels were unaffected.

The next real forecast experiment must test ordered recovery/fatigue at matched false-alarm rates, with independent days and realistic latency. The earlier daily, execution-history and pause results remain negative or insufficient; this phase does not relabel them successful.

**Decision:** the normalized replay/consumer is ready for further source-qualified research integration under its explicit contract. The real-market early-warning capability remains incomplete. Additional source-independent repair would not substitute for the missing semantic qualification and forward evidence; repeatedly tuning the already-used day is not a justified next experiment.

No production deployment, purchase, live connection, data-admission change, rank, alert, sizing or trade action occurred. The value delivered here is removal of specific false-positive and false-timing paths in the proposed research capability—not a claimed new profitable signal.
