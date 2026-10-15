# SOXX BOATS historical REST — one-request execution packet (no vendor request yet)

**Prepared:** October 14, 2026 ET / October 15 UTC. **Scope:** use the EXISTING incumbent Tiingo collector/4 TB archive, not a new writer, scheduler, API key path or data service. This file is an **execution-ready bounded request plus readback specification**, **not an admission receipt or completed acquisition**. User directed proceeding independently; separate platform/provider gates and prior tool refusals remain effective.

## 1. Exact current inputs and capability

Direct M2 source evidence: [4 TB BOATS archive audit](DIRECT_M2_BOATS_COVERAGE_AUDIT_2026-10-14.md). The mounted canonical archive at `/Volumes/Mastermind/market-data/tiingo` has only two historical `boats-bars` receipts, **AAPL 687 1m rows and AMD 720 1m rows**, with actual HTTP 200 responses captured 2026-10-11 UTC; no SOXX historical `boats-bars` receipt. The existing BOATS live SOXX tape consists of **7 trade observations, zero quotes** in the Oct 11 night ~3.3-second opening capture, plus the earlier independently accepted **142 trade and 2,926 quote observations** in the Oct 12 evening ~9m11s capture. None establishes a whole night or a fill. Storage check: **1,862.42 GiB free** on the 4 TB external mount, above the existing collector's **35 GiB minimum free**.

The installed canonical *read-only source and task planner* is in Macro git commit `2a08250fe61aa59ad3e1581149f0b93e9d5a17cf`, workspace `/Volumes/Mastermind/agent-workspaces/sol/tiingo-ingestion-20261009`. Original source SHA256s:
- `scripts/tiingo_ingest.py`: `ef52fd2f90842c85a362254dae219a2593fed024b340a38fa5333a50e06981e6`
- `collectors/tiingo_archive.py`: `54b694af53a940f8ea1148215b0a3ccfcfa5313270286b04a99c72d7dc004fa6`

The documented Tiingo fixed-origin REST endpoint is `/boats/SOXX/prices`, with date bounds, one-minute resampling, and explicit `columns=open,high,low,close,volume`. It returns single-venue BOATS overnight OHLCV **8 PM–3:59 AM New York**, **not** historical native best-bid/ask. Tiingo's docs require the **BOATS Real-time entitlement**; an earlier AAPL/AMD HTTP 200 does not prove the currently available per-symbol SOXX range or rights. Official documentation: https://www.tiingo.com/documentation/boats .

## 2. Source-selected **first** historical technical pilot, exactly one request

Choose **October 12–13, 2026** as the initial technical-coverage pilot, because actual October 12 20:00 ET SOXX quote/trade presence has already been observed in the existing short firehose; this pilot is **not untouched prospective strategy validation**. The source already generated and verified the following pure plan:

`source=boats-bars`, `symbol=SOXX`, `startDate=2026-10-12`, `endDate=2026-10-13`, `resampleFreq=1min`, `columns=open,high,low,close,volume`. **Exactly one task.** Deterministic incumbent `plan_page` SHA256: **`1626ffc125e3407d61e4090de39653a088539563366f1c2d53613e9f88efc999`**; source response `network=false`, `execution_authorized=false`, `execution_progress=NOT_OBSERVED`.

Pre-dispatch **offline** validation on the M2, using the already installed source code:

```bash
cd /Volumes/Mastermind/agent-workspaces/sol/tiingo-ingestion-20261009
python3 -m scripts.tiingo_ingest plan \
  --sources boats-bars --symbols SOXX \
  --start 2026-10-12 --end 2026-10-13 \
  --expect-plan-sha256 1626ffc125e3407d61e4090de39653a088539563366f1c2d53613e9f88efc999
```

**Exactly one existing-collector command to use only after current authenticated source/request admission and source-writer/effect fencing are positively established:**

```bash
cd /Volumes/Mastermind/agent-workspaces/sol/tiingo-ingestion-20261009
python3 -m scripts.tiingo_ingest collect \
  --sources boats-bars --symbols SOXX \
  --start 2026-10-12 --end 2026-10-13 \
  --max-requests 1 --pause-seconds 1.25
```

No `TIINGO_API_KEY`, token, cookie, signed request, raw price row, credential path or private account ID should be printed. The existing collector itself owns reading the existing key from its configured private source, HTTPS access, bounded response, immutable original receipt and external-drive-only storage. Do not duplicate its source authority. Actual `collect` is deliberately **not run** by this research turn: the original mission recorded an explicit pre-dispatch platform refusal of an authenticated Tiingo probe and forbids a cross-tool/host retry; this remains a real permission/safety boundary even after current task continuation. Provider/account limits, contemporary BOATS entitlement, actual quota, source-specific rights and any existing active source writer must be confirmed on the intended operation before dispatch. No credential read or network request has been made here.

**Exact first-call stop semantics:** one original operation only, no automatic failover. A 401/403 or 429 is a **STOP**, not a prompt to retry with another account; a response after transport uncertainty must be reconciled by exact original receipt/request identity before any further request. Preserve whole-response error/quality quarantine under the existing collector. An HTTP 200 with zero rows is **not** proof SOXX did not trade: confirm request dates, source validity and corrected vendor data; do not fabricate or fill silent minutes.

## 3. Once and only once an original SOXX historical receipt actually exists

Use the **existing** Mastermind read-only consumer `fullsession_v12/tiingo_canonical_consumer_v13.py`, source Git blob `6b2ef150f7b37479445de65b357b4c9480da3265`, bound to the **original** new `raw_sha256`, `receipt_id`, UTC capture-day directory and fixed UTC cutoff. It invokes the existing Macro `lib.dataos.tiingo_reader.read_research_view('boats-bars', source_day, raw_sha256, purpose='INSPECTION', max_rows=bounded)` and matches original compressed L0, L1 receipt and actual immutable raw-to-view equivalence; only **aggregate source metadata**, not prices, may appear in public GitHub.

For the October 12 night, pass **`--night-start-et 2026-10-12`**. Separately require true 8-hour evening-to-morning SOXX coverage, actual row timestamps and unique completed one-minute buckets; `resample_complete_30m` requires **all thirty original minutes** and never forward-fills a no-trade minute. Missing quote/book history must remain unmarketable, even if OHLC REST history becomes available. Contract must not treat the short Oct 13 00:00–00:09 UTC live burst as a complete night.

Record only: original response HTTP code, exact immutable SHA and receipt identity, actual captured rows, observed/expected true overnight minute buckets, missing buckets, complete 30-minute intervals, instrument/venue/PIT/adjustment/source rights statuses, conflicts/quarantines and whether any historical BOATS Q/size data is actually available. **Do not score any V27 original-cohort economic exit until real independent unseen paired outcomes mature and all prerequisite source/fill gates pass.**

## 4. Subsequent **prospective** night only after session close and qualified first call

A separate frozen second offline plan exists for **October 14–15, 2026**, covering the first preregistered prospective overnight night (20:00 Oct 14–04:00 Oct 15 Eastern). `source=boats-bars, symbol=SOXX, startDate=2026-10-14, endDate=2026-10-15`, 1m explicit OHLCV, one task. Plan SHA256 **`1cd9cda8d3a3dd6facd25ec384a65082f63c08fb8c4ca0b7aeafd4a62d510a5e`**. It must not be requested/treated as complete until the entire overnight session has ended and the provider's own final publication/correction time is qualified. **A source timestamp and same-day bar observation are not a mature 52-observed-RTH-hour paired strategy outcome**; the original full followthrough must complete. After receipt, the fixed V26 prospective contract (published October 13 before first entry) and V27 complete-population causal scorer remain controlling.

## 5. What is still blocked and the next action

Current research PR #1338 is open; previous source-integrity CI [run #38673976764](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/38673976764) completed **SUCCESS**. This packet is a future source-operation *recipe only*. The last direct M2 Python plan returned both plan SHA256s, mount and 35GiB floor check, without vendor access. Subsequently the M2 remote connector briefly reported **offline** before a separate read-only source inspection; no source-modifying operation was in flight, so this is **not** an uncertain vendor write.

**Exact unresolved frontier:** admitted source owner/operator must legitimately resolve the **previously refused authenticated Tiingo call**, verify the currently allowed API/key/BOATS rights and that no overlapping writer is active, then issue **one** canonical `collect --max-requests 1` on the originally controlled drive. This research session cannot recharacterize the denied credential/provider action as a fresh ordinary read or send it through an alternate carrier. Upon lawful first receipt, this session can independently consume it through the already accepted original reader and produce a first-night genuine coverage report.

**Status:** `ONE_REQUEST_OFFLINE_READY / PROVIDER_CALL_NOT_DISPATCHED / DATA_NOT_QUALIFIED`. Never report `QUEUED`, `STARTED`, `HTTP200`, historical SOXX bars, full-session data, executable fills, PR merge or strategy acceptance from the plan alone.
