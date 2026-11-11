# Latent Pressure research — source audit and scope

Protected Mastermind source: `78388ac29f7e54c9dfe7799a8e4769fb46d4aed6`. Current Chairman commission is research-only: no purchases, live schema changes, production deployment, trade recommendations or sizing authority. This workspace owns only `research/latent_pressure/2026-10-14/`.

## Existing capability, not a replacement system

`brain/rotation_tensor.py` implements pairwise 20-session relative strength and five-session acceleration, sector leadership churn, optional breadth, volume/ETF-share proxies, and sign-consistent divergence episodes. Its `assemble` output remains advisory. `research/eyes/rotation_spec.md` is partly design intent, not production or alpha proof.

The preserved July 3 validation in `research/eyes/validation_runs/rotation_tensor_2026-07-02.md` reports FAIL: AUC 0.5426 over 3,888 evaluable sessions for a SPY five-session drawdown target; 20 fires and 0.20 conditional event frequency versus 0.1793 base frequency. The specification instead proposes a 20-session defensive-versus-offensive persistence target. These are different estimands. Neither a failed drawdown gate nor a plausible rotation narrative establishes new latent-flow predictability. No prior verdict is superseded here.

`brain/rotation_intake.py` is the sole firm-wide reader of `rotation_calls.v1`. Identification owns detection and immutable call IDs; consumption owns expansion, ledgers and grading. Evidence is opaque to the reader. Missing/stale data is not all-clear. `active_calls` can use explicitly tagged deterministic `fallback_synth` calls capped at 0.5 confidence; these are not validated forecasts. The reader uses a deliberately tighter two-calendar-day proxy for its two-session freshness budget. The current doctrine prefers early confirmation over unsupported ignition prediction and remains controlling.

## Data actually inspected

The installed Data and Lab adapter revision is `0b204cde017b88a9fec03ddb583f6b5e02ea4886`. Its read-only `macro_snapshot` binding points to the existing Macro data; physical availability is not point-in-time qualification. All 11 SPDR sectors plus SMH/SOXX/SPY have daily close, close_price and volume histories ending October 9, 2026. XLC begins June 19, 2018; XLRE October 8, 2015. Producer source distinguishes dividend-adjusted `close` from split-adjusted, dividend-unadjusted `close_price`. ETF data have no open/high/low or aggressor-side information.

The breadth close cache is only March 18, 2025–October 8, 2026 (393 rows; approximately 518 securities); sector breadth has 344 rows beginning May 28, 2025. Historical membership intervals exist, but sector labels explicitly use `gics_current`, `label_asof=2026-10-04`, `era_correct=False` in inspected rows. Names containing `pit` do not make these labels historically known. Full historical H3/thematic validation is therefore not claimed. ETF flow files examined have only 68–69 records from June 9 to October 7, 2026. They are insufficient for a multi-regime flow backtest.

Macro producer checkout observation: `eb55c8573d94700dde35b6ce5b9af23738c710c0`; no producer or data edits. Source files, hashes and complete selected-data checks will accompany the actual run.

## Research execution and custody

M2 Studio verified on the authorized Studio Direct transport. Attended research root/parent label: `latent-pressure-research-20261014-chatgpt4-001`; not a fabricated native Codex or Executive identity. Economical Fabric research returns `lp-20261014-micro-a` (microstructure) and `lp-20261014-options-b` (options) are available for principal review; no acceptance or truth claim follows merely from return status. No subdelegation authorized.

## Next result

Execute the frozen LP-ETF-01 pilot, inspect primary literature and data economics, adjudicate the bounded returns and independent statistical review, and publish the six decision-ready deliverables. The pilot is deliberately a discriminating test of inexpensive daily pressure proxies, not a demonstration that hidden inventories are observable.
