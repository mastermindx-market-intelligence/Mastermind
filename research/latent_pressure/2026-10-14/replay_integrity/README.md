# Recovery replay integrity

Read `REPORT.md` for the result and boundaries. All examples are **explicit synthetic normalized fixtures**, not reconstructed IEX order-book data. `DEEPPLUS_BOOK_FIELDS_UNVERIFIED` remains enforced by the existing real-source adapter.

## Reproduce the finite demonstration

Run from this directory in the existing research tree:

```sh
python3 replay_reader.py --fixture DEMONSTRATION_FIXTURE.json --at 1152921504606846980
python3 replay_reader.py --fixture DEMONSTRATION_FIXTURE.json --at 1152921504606846982
python3 replay_reader.py --fixture DEMONSTRATION_FIXTURE.json --at 1152921504606846983
```

The first cutoff is pending with proven follow-up; the second observes the declared committed outcomes; the third explicitly lacks coverage through the requested cutoff. No output contains an actionable probability. `--out` may name a new file; existing files are refused rather than overwritten.

`replay_reader.py` reuses `../event_recovery/book_recovery.py` and `../clock_pause/recovery_incidence.py`. These modules and the tests require only Python's standard library. There is no broker, network, data acquisition or production write path.

## Run affected tests

```sh
python3 -m unittest test_atomic_recovery test_replay_reader -v
python3 ../event_recovery/test_recovery.py
python3 ../clock_pause/test_recovery_incidence.py
node verify_wire.mjs .
```

The last command verifies the actual checked-in demonstration JSON using JavaScript BigInt. It is not a browser deployment test. Node is optional for the Python-only reader, but was available and used for the recorded cross-language proof.

## Exact normalized contract

A file envelope declares `origin: SYNTHETIC_NORMALIZED_FIXTURE` and a finite ordered `frames` array. Only `SYN-` symbol labels are admitted. Each frame declares `kind`, `observed_ns`, `symbol` and `session`. Times and identities may be exact integers or canonical nonnegative decimal strings; floats, Boolean values and scientific-notation strings are rejected.

`START` declares a new empty synthetic session. `BATCH` has `complete:true` and explicit ADD/MODIFY/DELETE/EXECUTE events. It becomes observable only at its complete `observed_ns`; received event times must be no later. Batch atomicity is supplied by the fixture, never inferred from equal timestamps. An invalid final event rejects all earlier changes in the batch.

`WATERMARK` declares `complete_through_ns` and the matching `last_sequence`. It cannot claim future or backward coverage. A later event cannot contradict the sealed prefix. `GAP` invalidates continued inference, with censoring at the last proven observation. `RESET` explicitly changes the session, retires/censors the old one and starts empty state. These are research-input declarations, not an installed exchange protocol or a new runtime control plane.

The underlying normalized MODIFY quantity replaces the remaining quantity; EXECUTE consumes its specified amount. The specification does not identify actual IEX side bits, reset messages, queue-priority rules or packet atomicity. Those still require separately permitted primary-source verification. Do not remove the real adapter's refusal merely because this fixture works.

## Evidence

`RED_OBSERVATIONS.json`: original constructed failures. `ATOMIC_VALIDATION.json` and `VALIDATION.json`: tested source identities and counts. `END_TO_END_PROOF.json`: four completed CLI runs with output hashes. `WIRE_PROOF.json`: completed cross-language check. `EXAMPLE_*.json`: the actual synthetic consumer outputs. `DEMONSTRATION_FIXTURE.json`: reproducible explicit input.

Older empirical studies and all private market captures/predictions are unchanged. No formerly blocked action was attempted. The original worker-return and legacy timestamp-audit obligations remain recorded in the preceding `clock_pause/BOUNDARY_STATUS.json` and this phase's frontier.
