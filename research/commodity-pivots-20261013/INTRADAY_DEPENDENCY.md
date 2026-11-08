# Commodity-pivot intraday input dependency

## Named consumer
The original Chairman commission asks which 2h/3h/4h technical setups and lower-timeframe entries identify gold, silver, oil and copper pivots and their producer-equity pivots. Current experiments use daily observations and cannot settle that question. The owning upstream workstream remains Macro `agentos/workstreams/WS-TIINGO-DATA-OS.md`; no competing collector, quote service, credentials, scheduler or data publication path is introduced.

## Actual availability reconciliation
The prior generic `RUNTIME_UNAVAILABLE_OR_INTEGRITY_FAILED` is no longer sufficient to claim that the installed Data & Lab adapter is unavailable.

A bounded, read-only diagnosis in this continuation established:
- Installed launcher SHA256 `381f3b12c4d80313acd518ac2d5571fe09bf3286009645a00dd15af64e5a809c` remained unchanged.
- Its Python executable exists and is executable; the required volume is mounted.
- The exact volume metadata query completed successfully.
- The unmodified release-integrity function passed. No check was removed, no file permission changed, no source hash rewritten and no runtime installed.
- The original launcher `--capabilities` path then passed, observed at `2026-10-14T04:18:59.459283Z`, reporting implementation revision `0b204cde017b88a9fec03ddb583f6b5e02ea4886`, read-only source access and production qualification NOT_ESTABLISHED_BY_THIS_ADAPTER.
- Only after that new same-carrier evidence, the bounded archive browse and four version-fenced first-row reads were performed. These were not an alternate-tool or permission bypass.

The precise cause of the earlier generic failure was not established. This is successful current-path verification, not a claimed repair or root-cause diagnosis.

## Bounded archive observation
The installed adapter's `tiingo:normalized/equity-intraday-bars` listing had one date directory, `2026-10-11`; the directory contained four Parquet files. Both directory scans completed without truncation. One selected metadata row per file identified AAPL, MSFT, NVDA and SPY. Every sampled row had `source_rights_admitted=false` and `pit_backtest_eligible=false`. The four reads did not inspect full-file content or independently prove all rows' ticker identity.

Read receipts, observed between `2026-10-14T04:21:38Z` and `04:21:41Z`:
- AAPL: `a7f02ed2d67d49999702fd84c3f3d9bf935a6b92ef0ba3a3f0ab791f9e8a6b5c`
- MSFT: `60b726d83fa288354785d4a65b09abe24d41d4a412ae33eadda98f242e83bdaf`
- NVDA: `6d42d459022444134aff3343bad5018ca5c2155b50f19da860b7546f46d4be95`
- SPY: `9e200180ccbab40008ee590d6402d1c9c699adf20c5baaf83dade8e76ae80f4f`

These observations establish adapter availability and a limited visible sample. They do not establish qualified commodity-specific intraday data, global absence of such history, rights to redistribute it, actual execution prices, or current production ingestion.

## Existing bounded qualification packet: unchanged, NOT_DISPATCHED here
Original diagnostic scope is 24 requests: eight instruments (GLD, AEM, SLV, PAAS, USO, COP, COPX, FCX) on three cash-session dates (2025-11-28 early close, 2026-01-30 previously problematic session, 2026-10-08 normal-session check).

Keep the existing source-owner request parameters: one-minute OHLCV, explicit volume column, no force filling, no after-hours conflation. Validate market-date and UTC interval boundaries, real exchange sessions/early closes, observed versus synthetic bars, receipts and hashes, raw/adjusted identity, and endpoint coverage. A three-session probe only qualifies the capture behavior; it is not adequate history for a strategy test.

The upstream owner must use the existing collector and its actual entitlement, dated identity, quota/storage, exclusive-writer and retry protections. This research does not authorize changing those gates or resubmitting held provider requests. It does not assume another subscription purchase is needed.

## Acceptance sequence
1. Incumbent Data OS owner determines whether the already-specified diagnostic windows are admissible and available on the authorized endpoint.
2. Consume actual request receipts and qualified outputs, or record the exact endpoint/window refusal. Do not infer successful collection from a plan.
3. Admit the resulting data only for the purpose justified by actual rights, revision and timestamp evidence. Leave unrelated flags unchanged.
4. Obtain sufficient non-overlapping history for the frozen 2h/3h/4h comparison, with partial-session bars and developing/confirmed higher-period states separately labeled.
5. Evaluate correctly timed entries and gaps under the agreed risk objective, then reserve a prospective period. Research summary publication is not trading adoption.

This file is a dependency handoff for the existing programme, not a new execution queue or claim that an agent is running it. All earlier action-scoped safety/permission denials remain intact. No background process or worker was created by this handoff.