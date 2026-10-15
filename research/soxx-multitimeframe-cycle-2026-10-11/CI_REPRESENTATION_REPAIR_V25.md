# V25: source-only repair of the research/identity lexical collision

## Baseline and exact failure

Original evidence/source: Mastermind PR #1338 at `7ec0207a5870e8c467b7185afbdcde97c38ef314`.
Local reproduction uses original merge base `70e9ef1ede16628d00a7cc1d749387d893a1d5b3`.
Hosted run `38336822737`, job `115099021700`, failed the D8 identity-literal gate.
The unmodified D8 test independently reproduced **261** rejected lexical literals.

Static parsing of the published financial artifacts attributes exactly those 261 tokens:

| Frozen artifact | Count | Actual meaning |
|---|---:|---|
| `terminal_finepivot_v14/PEER_SOURCE_METADATA.json` | 3 | `live_tail` bar counts of 442, not OS principal IDs |
| `terminal_finepivot_v14/peer_pairs_v14.csv` | 256 | numeric substrings of compound string episode keys, such as `3h_medium:1:468:470` |
| `terminal_finepivot_v14/peer_v14.py` | 2 | 570/960 minutes after midnight: 09:30/16:00 ET |

The guard gives the path word `peer` a runtime-topology meaning and tokenizes the added text as source. There are no runtime UID/GID/account/port assignments among these 261 sites. Two attempted dynamic guard diagnostics were refused before execution; they were not replayed. Attribution instead used ordinary static JSON/CSV/token parsing of already-public research artifacts and the original unchanged test failure.

## Narrow repair and preserved meaning

The identity guard, reviewed-literal masks, safety rules, workflow, and runtime configuration are **unchanged**. No waiver, path allowlist, numeric exemption, authenticated probe, or new source owner is added.

* Financial-asset metadata is explicitly named `ASSET_SOURCE_METADATA.json`. Its entire byte content is unchanged; the README reference follows the rename. The original filename and bytes remain recoverable at the immutable original commit.
* Compound episode keys are explicitly CSV-quoted strings. All 176 records, all 13 fields, their text values, and ordering are unchanged. The producer's pair-table writer uses standard `csv.QUOTE_NONNUMERIC`: string identifiers are quoted, genuine numbers stay numeric. This is not a change to episode construction or numeric outcomes.
* The existing ET session predicate is written using `datetime.time(9, 30)` and `datetime.time(16, 0)`. It preserves the prior quarter-hour test, early-close handling, and original subminute behavior. No new calendar or session policy is introduced.

## Evidence preservation

Original pair CSV byte SHA256:
`73394ea30bd7b345724a5cf70db97e7e952fc19ed9f0836586ec324e6781d4a4`.
Repaired pair CSV byte SHA256:
`fea2eb2490ed2a0de4f6051674858139a07cb5fb8807fd9721629ee550509d1c`.
Both CSVs have the identical parsed-record SHA256 (UTF-8 compact JSON array of CSV records, including header):
`ab43a602f08358ecbd9fbd7d53372a48f99779be9d4b54618d800936816f1c30`.
The metadata byte SHA256 before/after rename is:
`3a243907f89b3930357987086303080fd5abad1e2c79fd58da01a4d8850702c8`.

Four new tests were first observed failing for the absent explicit representation, then passing after the repair. They pin metadata bytes and every published pair-table value, verify numeric/string CSV serialization, and compare the actual new clock helper to the frozen old predicate over **12,960** synthetic date/minute/subminute combinations. No historical price study or v2-v24 backtest was rerun or retuned.

Full unchanged D8/security-module verification and current-head hosted CI are separate receipts and must be read before claiming this PR green. Local representation tests alone do not prove CI or research acceptance. No trading strategy, live service, quote fill, historical BOATS entitlement, or release is accepted by this repair.
