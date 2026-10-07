# SEC EDGAR rights-purpose reconciliation — W0

**Disposition: source-law reuse is favorable; I3 runtime-purpose admission remains fail-closed.**

This record separates two different questions that earlier W0 notes intentionally kept distinct:

1. **Does the estate have an accepted source-law determination that SEC EDGAR material can be acquired, processed, stored, used by models and redistributed?**
2. **Has I3 been admitted through the current shared runtime rights gate for each purpose it intends to exercise?**

They are not the same gate.

## Current source-law determination

Current Macro source pin refreshed for this reconciliation: `ae54a785984153d595de69a13c1dea4415557ed8`.

Canonical source-rights register:

`research/licenses/PROPHET_US_SOURCE_RIGHTS_REGISTER_2026-09-23.md`

Blob: `a9ee6f288bfb2716facd88dcf2c5135ca8125303`.

Its SEC EDGAR section records all five dimensions as **DETERMINED-FROM-PUBLISHED-TERMS** and user-facing:

| Source-law dimension | Current determination |
|---|---|
| acquisition | determined / user-facing |
| processing | determined / user-facing |
| storage | determined / user-facing |
| model use | determined / user-facing |
| user redistribution | determined / user-facing, citation-and-trademark-limited |

The register's closure table narrows the remaining source-level caveat to **filing-specific third-party restrictions**. I3 must therefore keep exact source ancestry and must not treat a primary SEC filing determination as permission to redistribute third-party attachments, expressive documents, logos or separately restricted material.

## Current runtime/public-emission state

At the same Macro pin, shared runtime rights registry:

`config/theme_sources.yml`

Blob: `e59ce0a9f98e34e45165545f21a84596c23a6de4`.

It contains **no `sec_edgar` family row**. The reviewed but unmerged #7870 head contains a proposed `sec_edgar` row; protected/current main does not.

Therefore I3 must keep these two truths simultaneously:

- **source-law support exists** for SEC EDGAR acquisition/processing/storage/model-use/redistribution at the cited register;
- **I3 runtime purpose admission is not yet bound** through the current shared registry/snapshot and named consumer contract.

## I3 purpose matrix

| I3 purpose | Source-law evidence | Runtime/consumer binding | Current I3 disposition |
|---|---|---|---|
| internal development/use | processing + storage determined | no named I3 binding | `SOURCE_LAW_SUPPORTED_NOT_RUNTIME_BOUND` |
| historical research | processing + storage over historical SEC material determined | no named I3 historical-research binding | `SOURCE_LAW_SUPPORTED_NOT_RUNTIME_BOUND` |
| model context | model use determined | no named I3 model-context binding | `SOURCE_LAW_SUPPORTED_NOT_RUNTIME_BOUND` |
| public display/redistribution | redistribution determined with citation/trademark limits | `sec_edgar` absent on protected shared runtime registry; no I3 source-family mapping | `NOT_ADMITTED_RUNTIME` |

A successful fetch, a public SEC URL, or the source-law register **must not** cause I3 to mint a runtime rights profile. I3 consumes the existing owner rights plane only.

## Consequence for W1

This reconciliation removes a false ambiguity: internal development work is not blocked because SEC source-law reuse is wholly unknown. It does **not** unlock connected/public W1.

Before I3 can emit a public or model-consumer transition, the existing owner must still bind the exact owner-issued FIF source family and exact I3 purpose to the accepted shared rights snapshot/consumer contract, preserve revocation behavior, and read back the admitted decision. Public emission additionally requires the `sec_edgar` row to land on protected main (or an accepted successor runtime rights contract).

Until then:

- `rights.state` remains `not_admitted` in the I3 transition candidate;
- `product_publication_admitted=false`;
- model-context delivery is not claimed;
- historical-research use is not called runtime-admitted;
- no rights profile is copied from #7870 or synthesized from source URLs.

This is source-law reconciliation only. It changes no Macro rights registry, source acquisition, product route, model prompt, trial registry, or publication state.
