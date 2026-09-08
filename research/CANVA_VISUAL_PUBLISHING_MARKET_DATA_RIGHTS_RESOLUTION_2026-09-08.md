# Canva Visual Publishing — SMR market-data source and rights resolution

Date: 2026-09-08  
Status: **report-scoped evidence resolution / Canva artifact still `HOLD`**

This file supplements, and narrowly supersedes part of:

- `research/CANVA_VISUAL_PUBLISHING_R1_QA_2026-09-07.md`
- `research/CANVA_VISUAL_PUBLISHING_R2_CONTINUATION_2026-09-08.md`
- `research/CANVA_VISUAL_PUBLISHING_SOURCE_RIGHTS_GATE_2026-09-08.md`

It is not a new dataset, source identity, rights registry, market-data owner, Canva transaction, visual acceptance, export receipt or publication approval.

## 1. Mission, authority and exact carrier

The user outcome remains:

> canonical research → structured evidence package → accepted premium visual primitive → deterministic population → actual rendered inspection → explicit approval → controlled publication

Repository: `mastermindx-market-intelligence/Mastermind`  
Carrier: branch `sol/canva-publishing-r0-20260907`, PR #524  
Pre-write PR head re-read: `6f1421ce4167a45d6ba07c39831c2251eb80a603`  
Target Canva design: `DAHUgqi_7FA`  
Report: `SMR — Bottom Architecture & Re-rating Map — 2026-09-07`

Protected Sol procedure for this continuation was loaded atomically from protected Mastermind `master` at `fc29e14a0d9ee41105264a5abc1d182daee7abbf`.

The canonical market-data and rights records were read from Macro `main` at `7c66ed137601969b7f7a53c93753a34ec1dd7bd8`. The Mac's primary Macro checkout was materially dirty and was therefore used only as an authorized credential/runtime host. The executed corporate-action guard file had Git blob `0748935449ae781f5657601a34f82bd09cf3df00`, exactly matching protected Macro `main`; repository conclusions come from GitHub, not the dirty checkout.

## 2. CEO ruling

The StockAnalysis-derived price lane remains rejected for external emission. That website path is not needed for this report.

The exact SMR observations required by the report are independently present in the canonical Market Data store `equity.bars.daily.massive`, and the estate already contains an operator-confirmed enterprise redistribution record covering historical daily bars, derived calculations, charts, reports and end-user export. The report's exact price fields therefore move from `RIGHTS_BLOCKED` to **`PROVEN_LIVE` at the source/rights layer** when projected through the evidence below.

This does **not** make the Canva report publishable. Overall external publication remains `RIGHTS_BLOCKED` because the current Canva design has not been freshly read, repaired, previewed, approved or committed; its non-first-party fonts/elements/images have not been inventoried; full-size QA has not passed; and no publication authority has accepted an exact saved revision and channel.

No new procurement is required for the selected SMR daily bars. A future written vendor designation imposing a dataset-specific condition would supersede this report-level ruling for the affected output.

## 3. Canonical owner and rights authority

### Data owner

Existing Macro dataset registry row:

- dataset ID: `equity.bars.daily.massive`
- layer: `L1`
- status: `PRODUCED`
- owner: `macro-dashboard`
- producer: `collectors/massive_stock_day.py`
- storage: `data/massive_stock_day/{ticker}.parquet`, R2-canonical under `massive_stock_day/`
- temporal profile: daily `BARS`
- timezone: `America/New_York`
- adjustment: none
- close basis: raw print

This report consumes that owner. Canva must not collect, normalize, revise or license market data itself.

### Rights authority

`macro/research/licenses/MASSIVE_ENTITLEMENT_RECORD.md` records an operator-confirmed Enterprise Market Data License and Redistribution Addendum effective 2026-08-09. Engineering may rely on the recorded scope for daily bars, historical archives, derived materials, charts, research, reports and end-user export. The private governing instrument was deliberately not opened, copied or committed by this continuation.

Report-level classification for these exact fields:

- `redistribution_class`: `vendor_licensed_redistributable`
- attribution required: no
- public debrand required: yes
- intended use: derived figures and selected-session price cards in a report
- intended channel: internal preview first; external report only after all independent artifact gates pass

The current Macro dataset row does not yet carry the explicit `licensing` value beside `equity.bars.daily.massive`. That is canonical-registry metadata debt in Macro, not authority to create a second rights plane in Mastermind or silently modify a different repository from this carrier.

## 4. Security identity

The live licensed reference endpoint and the estate's symbol-directory evidence agree on:

- ticker: `SMR`
- issuer: NuScale Power Corporation
- security: Class A common stock / common stock
- CIK: `0001822966`
- primary exchange MIC: `XNYS`
- currency: USD
- composite FIGI: `BBG00YG48NM6`
- share-class FIGI: `BBG00YG48PG8`
- active at retrieval: true

Ticker remains an alias, not durable identity. The report envelope therefore carries CIK, exchange and FIGIs rather than treating the three-letter symbol as sufficient identity.

## 5. Exact source object and coverage proof

R2 object: `massive_stock_day/SMR.parquet`

| Field | Verified value |
|---|---|
| Object size | `48,388` bytes |
| ETag / local MD5 | `5fc01a54efad4cf47f4367a9cdbd47fd` |
| SHA-256 | `69ca0688b15db8fdfb4d136cb39db7d5171b8811e685cb655ce9bcde9499bbed` |
| R2 last modified / report `known_by` bound | `2026-09-05T06:17:16Z` |
| Rows | `1,089` |
| First session | `2022-05-03` |
| Last session | `2026-09-04` |
| Duplicate sessions | `0` |
| Null open/high/low/close/volume/transactions | `0` in every field |

Store-level proof:

- R2 manifest SHA-256: `77810f4e29f9eab5d5f72a871ab3f659cfc5d6448ac9f5d4b4b5f9ec1e24ff69`
- manifest file count: `21,496`; `SMR.parquet` is explicitly listed
- store ticker count: `21,495`
- coverage: `2021-07-06` through `2026-09-04`
- processed days: `1,349`
- maximum missing weekday run, full and recent windows: `0`
- anchor: SPY, `1,299` rows, first `2021-07-06`, last `2026-09-04`, maximum calendar gap `4` days
- backfill-state SHA-256: `54739798f028b4926cf3e691f92e8760c8ab4b33e693e1f8f7dcf4c495fccca1`
- backfill version: `2`; `last_captured_date`: `2026-09-04`

The report was prepared 2026-09-07. The selected source object was therefore present before the prepared date and contains the stated 2026-09-04 market-as-of session.

Per-row `captured_at` is null because the per-ticker parquet does not store a row-grain capture clock. Do not invent one. The R2 object timestamp, store manifest and backfill state establish only the safe bound that the selected rows were present by `2026-09-05T06:17:16Z`.

## 6. Report observations and deterministic calculation

Calculation:

```text
close_to_close_pct = (close_t / close_previous_session - 1) * 100
```

Display values are rounded to two decimal places. Unrounded values remain below.

| Session | Previous session / close | Open | High | Low | Close | Unrounded close-to-close | Display |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-07-17 | 2026-07-16 / 7.64 | 7.41 | 7.90 | 7.21 | 7.72 | `1.0471204188481575%` | `+1.05%` |
| 2026-07-29 | 2026-07-28 / 8.22 | 8.00 | 8.335 | 7.54 | 7.59 | `-7.664233576642343%` | `-7.66%` |
| 2026-07-30 | 2026-07-29 / 7.59 | 7.89 | 8.675 | 7.79 | 8.60 | `13.306982872200269%` | `+13.31%` |
| 2026-08-11 | 2026-08-10 / 9.18 | 9.36 | 9.95 | 9.17 | 9.89 | `7.734204793028332%` | `+7.73%` |
| 2026-09-04 | 2026-09-03 / 9.75 | 9.69 | 9.78 | 9.43 | 9.70 | `-0.5128205128205221%` | `-0.51%` |

Canonical selected-observation digest, over stable sorted compact JSON of the retained observation records:

`cae0c86e9dddbf243e2c8648c046c879dc85ba5f5c87b3c58e1ff7404fb603fe`

The full local report-scoped evidence envelope was retained only in temporary operator evidence and was not committed as a new schema or raw-data artifact:

- local path: `/tmp/mmx-canva-r1-continuation-20260908/smr-market-data-source-envelope.json`
- SHA-256: `39ce1ba0f66c10be93f73c22d7b66a136b0bb66913ce864378a498763012529a`

## 7. Independent source and basis checks

### REST-to-R2 parity

For every selected session, the licensed single-ticker endpoint was requested with `adjusted=false`. Each request returned exactly one result. R2 and REST matched exactly on open, high, low, close and transaction count; `int(REST volume) == parquet volume`, which is the store's documented integer-volume behavior.

Stable `results[]` digests:

| Session | SHA-256 of canonical `results[]` JSON |
|---|---|
| 2026-07-17 | `167f46c1baf80b5011305dbfe95c77a0505fb27e6f628d4e5f1240067dbe97c9` |
| 2026-07-29 | `6b291d77afd14af2161f08e33aa1bd58920df5c4ee727164820d1e7c2d72a432` |
| 2026-07-30 | `c3968a0afa813370e0345a3402a7deda6c140833e7700bf1a0da3dad40984d45` |
| 2026-08-11 | `5cba1d8a2f84d906f325f72773d7bd45ce2803ebca267ceed15e2c2edb690b43` |
| 2026-09-04 | `e440da6b21bcf2830627742e9f1187a9ac45d75027d03495f6ce090201305557` |

The retained source object is a raw, unadjusted regular-hours daily aggregate. It is not an after-hours last print.

### Corporate-action guard

The exact protected-main corporate-action guard queried both split execution dates and ex-dividend dates. It completed without pagination/fetch failure on all five sessions. SMR was absent from both action families on every selected date:

| Session | Guard complete | Market split rows | Market ex-dividend rows | SMR action |
|---|---:|---:|---:|---:|
| 2026-07-17 | yes | 4 | 203 | no |
| 2026-07-29 | yes | 3 | 281 | no |
| 2026-07-30 | yes | 6 | 788 | no |
| 2026-08-11 | yes | 5 | 74 | no |
| 2026-09-04 | yes | 3 | 353 | no |

The displayed close-to-close returns therefore do not cross an SMR split or ex-dividend event on the selected session. This is a basis guard, not forecast or causal evidence.

## 8. Narrow supersession of the earlier rights gate

The following earlier statement remains true:

- StockAnalysis website-derived observations are `internal_only`/`unknown` for external transformed redistribution and must not be the report's released source.

The following implication is superseded:

- the report does **not** need to obtain a new vendor licence or wait for procurement before using the exact selected price fields.

The correct released source is the existing licensed canonical Market Data lane documented above. No StockAnalysis URL, vendor name or copied website chart belongs on the public report.

For the public-facing methodology/source line, use a debranded description such as:

> Price data: Mastermind Market Data; raw regular-hours daily aggregates; selected sessions; close-to-close returns; market as of 4 Sep 2026.

The internal artifact receipt must retain dataset ID, security identity, object/hash evidence, temporal bound, calculation and rights pointer. Because attribution is not required and public debranding is required, the absence of a public vendor hyperlink is not a source defect for this lane. It does not relax link/attribution requirements for SEC, NRC, issuer or other public-source claims.

## 9. Canva repair consequences

Apply these source changes in the same future transaction as R1/R2:

1. **Page 4:** retain the historical chronology only after replacing the website-derived source with the licensed Market Data envelope. Preserve closing-low versus intraday-low labels.
2. **Page 6:** the selected positive session is `30 Jul 2026`, not 29 Jul. Preserve `17 Jul 2026` for the intraday-low session and `4 Sep 2026` as the report market-as-of close. Do not attribute the 11 Aug regular-session gain to the 16:21 ET filing.
3. **Page 11:** replace website sourcing with the debranded methodology line above. Retain an internal evidence ID/hash in the publication package rather than exposing the vendor or private licence record.
4. **All pages:** source rights do not authorize probabilities, targets, ranking, trade instructions or causal claims. R1/R2 language repairs remain mandatory.

## 10. Negative tests

The data/publication path must fail or visibly hold when:

- a public report uses StockAnalysis values or URL instead of the licensed canonical lane;
- a vendor name reaches the public surface despite debrand law;
- the exact security cannot resolve beyond ticker;
- a selected bar differs between R2 and the single-ticker source;
- a corporate-action guard is incomplete or names SMR on the session;
- raw and adjusted observations are mixed in one return calculation;
- 29 Jul receives the `+13.31%` label;
- a per-row capture timestamp is invented from object metadata;
- 7 Sep is presented as a market session rather than the report-prepared date;
- the licensed price source is treated as causal, forecast, rank or trade authority;
- preview approval is treated as a rights, save or publication receipt;
- a rights-cleared price table is placed inside a design whose fonts/images/elements remain unlicensed or unknown.

## 11. Capability ledger

| Capability | State | Evidence / missing gate |
|---|---|---|
| Exact SMR security identity | `PROVEN_LIVE` | CIK, XNYS, FIGIs and common-stock type agree with symbol-directory evidence. |
| Canonical SMR daily object through 4 Sep | `PROVEN_LIVE` | R2 object, manifest, backfill state and hashes above. |
| Selected OHLC/return calculations | `PROVEN_LIVE` | R2 rows, deterministic formula and independent REST parity. |
| Selected-session corporate-action basis guard | `PROVEN_LIVE` | Complete split/ex-dividend queries; no SMR action. |
| Distribution rights for exact price fields | `PROVEN_LIVE` at source layer | Existing enterprise entitlement record covers bars, derived materials, reports and export. |
| Report-scoped source envelope | `BUILT_NOT_PROVEN` | Durable summary exists; it is not yet consumed/rendered by Canva or a production publisher. |
| Macro registry licensing field on Massive row | `PARTIAL` | Estate rights authority exists; explicit row metadata is absent and belongs to Macro. |
| Public debranded methodology line in saved design | `NOT_BUILT` | Canva authentication/edit/preview is still blocked. |
| Canva visual-asset inventory and rights | `NOT_BUILT` | Requires fresh native design read. |
| Saved R1/R2 report repair | `NOT_BUILT` | No fresh transaction or commit. |
| Full-size premium QA | `NOT_BUILT` | No accepted changed-page rendering. |
| Overall external export/publication | `RIGHTS_BLOCKED` | Remaining Canva asset, visual, save and publication gates are independent of resolved price rights. |

## 12. Review ruling and exact continuation

Market-data verdict for the exact SMR report fields: **SOURCE AND DISTRIBUTION RIGHTS RESOLVED through the existing canonical licensed lane.**

Canva/product verdict: **HOLD / REQUEST_REPAIR / NOT SAVED / NOT PUBLISHABLE.**

Primary next action remains unchanged at the product seam:

1. complete the security-gated selection of the existing Mastermind-X Canva identity;
2. perform a fresh saved-design/revision/page/element/asset read on `DAHUgqi_7FA`;
3. stop on material drift or unknown effect;
4. open one new same-design transaction;
5. apply R1, R2 and this debranded source replacement;
6. retrieve and inspect every changed-page preview at usable size;
7. obtain one explicit post-preview Chairman approval before any commit;
8. read back and inspect the exact saved revision;
9. inventory and clear every non-first-party visual asset;
10. obtain separate publication approval for the exact saved revision and channel.

Dialogue edge: `NOT_WATCHER_ENABLED`.  
Watcher state: `NOT_APPLICABLE`.
