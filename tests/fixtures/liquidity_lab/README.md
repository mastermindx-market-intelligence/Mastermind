# W-LIQ.1 exact producer fixture

`glt_producer_20260904.json` is the unchanged repository-owned Macro sample from
`site/liquiditydata/global_liquidity_transmission.json` at Macro commit
`67c0fc151bffa8729610707979916a9855b36b0e`.

Git blob: `89a1ac142d4c9545b8ef1a1237430cf2cd7b35bd`.
Size: 31,180 bytes. Economic state date: 2026-08-28.
Recorded first-known time: 2026-09-04T11:03:41.497178Z.
Source contract: `global_liquidity_transmission.v1`, producer `w-liq.1.0`.

This old sample is contract evidence, not fresh production data or an untouched
forecast. Tests that change its fields are synthetic. The explicit 2.0/0.5
material/reset thresholds in adapter integration tests are test-only; no event
policy, empirical threshold, probability, live-forward result or trading
permission is established by the fixture.

The adapter treats the producer hash as an opaque identity reference. It does
not authenticate a publisher or recompute source factors to establish numerical
truth. A future live reader must validate its admitted source and source age;
this adapter's `as_of` only prevents consuming evidence published after the
specified cutoff. Source freshness is preserved, never refreshed from build time.
