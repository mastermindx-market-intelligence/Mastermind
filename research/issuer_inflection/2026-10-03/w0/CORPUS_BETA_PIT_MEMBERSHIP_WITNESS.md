# Historical beta PIT-membership witness — metadata only

**Result: 12/12 beta candidates are single-match S&P 500 members at the latest pre-freeze filing metadata dates in the unmerged #8392 candidate. This is NOT event assignment.**

Record SHA-256: `548cccc660880639259779104aa1186afe0cb65a7e97cd752a7b15435a9fddb7`

## Source boundaries

- Earnings metadata candidate: Macro #8392 head `3ec016886c2fd359cacab5c3739dc2fc7fd76f26`, parquet SHA-256 `5309ece0...`; open/unmerged and not I3-admitted.
- Earnings owner event key: `(CIK, report_date)` from `engine/earnings_release/binding.py`; a filing remains exact `(CIK, accession)`.
- PIT membership owner: `data/breadth/sp1500_pit_membership.parquet` blob `ec7085bc...`, current byte SHA-256 `7b34316c...`.
- Selection witness: latest `acceptance_datetime` per frozen beta ticker, accession lexical tie-break. No body/outcome/model/price read.

## Result

| Ticker | Candidate event key | Accession | Source acceptance | PIT source |
|---|---|---|---|---|
| BAC | `0000070858|2026-07-14` | `0000070858-26-000353` | 2026-07-14T10:45:08.000Z | sp500 |
| C | `0000831001|2026-07-14` | `0001104659-26-083383` | 2026-07-14T13:39:47.000Z | sp500 |
| CFG | `0000759944|2026-07-16` | `0000759944-26-000133` | 2026-07-16T10:32:21.000Z | sp500 |
| AME | `0001037868|2026-08-04` | `0001037868-26-000173` | 2026-08-04T13:56:19.000Z | sp500 |
| AOS | `0000091142|2026-07-30` | `0000091142-26-000096` | 2026-07-30T10:58:56.000Z | sp500 |
| CAT | `0000018230|2026-08-04` | `0000018230-26-000040` | 2026-08-04T10:31:44.000Z | sp500 |
| ADSK | `0000769397|2026-08-27` | `0000769397-26-000059` | 2026-08-27T20:05:06.000Z | sp500 |
| APP | `0001751008|2026-08-05` | `0001751008-26-000057` | 2026-08-05T20:06:12.000Z | sp500 |
| CRM | `0001108524|2026-08-26` | `0001108524-26-000187` | 2026-08-26T20:03:53.000Z | sp500 |
| ADI | `0000006281|2026-08-19` | `0000006281-26-000072` | 2026-08-19T11:03:13.000Z | sp500 |
| AMD | `0000002488|2026-08-04` | `0000002488-26-000121` | 2026-08-04T20:16:24.000Z | sp500 |
| AVGO | `0001730168|2026-09-02` | `0001730168-26-000076` | 2026-09-02T20:26:04.000Z | sp500 |

Every row has exactly one active PIT interval and every source is `sp500` at the witness date. This closes only the historical index-membership check for this candidate snapshot.

## Still open

- #8392 is unmerged and its repaired head has not yet returned current-head review/CI acceptance; these rows are not canonical source metadata yet.
- Current industry/proxy metadata is static/current. Repository evidence explicitly says it is not PIT production proof. No admitted historical business-family classification has been found, so archetype balance at these historical events remains **unqualified**.
- The 12 prospective temporal-holdout candidates are not evaluated here. #8392 ends 2026-10-02, before the 2026-10-04 freeze, so none of its historical rows may become a prospective holdout event.
- No filing body, exhibit, transcript, Q&A, outcome, price or sealed revision was read.
- `event_identity_admitted=false`, `source_revision_assigned=false`, `trial_registered=false`.

If #8392 lands and the research owner wants historical beta events, it may rerun this exact metadata rule against the accepted dataset, then must resolve historical business-family eligibility (or explicitly accept an unstratified limitation under a separately amended preregistration) before body inspection. I3 does not back-project today’s proxy labels.
