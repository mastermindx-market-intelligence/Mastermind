# Portfolio V3 evidence inspector — partial S0 source release

## Scope

This release is an operator-only, read-only inspector over existing immutable V3 evidence. It includes the pure contract, twelve-domain composer, immutable store and `status`/`show` CLI. It does **not** include a production source-capture adapter, automatic snapshot creation, an HTTP endpoint, browser integration or Fabric dispatch. No snapshot is claimed to exist merely because this code is installed. The current active V2 book and all execution/provider controls remain independent.

The storage implementation targets the existing macOS/Linux Python environment. Windows directory-descriptor support is not qualified. Use the repository's supported dependency environment; the verification environment was Python 3.12.13 with exact hash-locked dependencies and the CI-pinned Macro library.

## Read existing evidence

From the actual reviewed source workspace:

```sh
.venv/bin/python -m scripts.portfolio_decision_snapshot status
.venv/bin/python -m scripts.portfolio_decision_snapshot show
```

Both commands return bounded JSON. `status=ABSENT` means no stored record was found; it is not a complete market view. `status=AVAILABLE` means a verified record was read, not that its coverage is complete or its market content is correct. Inspect `snapshot.state`, `snapshot.coverage_state`, the evidence cutoff, recorded time, correction predecessors and authority fields.

For a selected identity returned by `status`, use:

```sh
.venv/bin/python -m scripts.portfolio_decision_snapshot show \
  --snapshot-id 'sha256:<64-hex identity returned by status>' \
  --section book_truth --offset 0 --limit 20
```

Replace the bracketed identity with the actual recorded value. No caller-controlled filesystem path or storage root is accepted. Only `autonomous` is a valid book for this S0 implementation. `offset` requires an explicit section; `limit` is 1–100. Without an identity, the inspector selects the latest verified record by cutoff, recording time and identity. A specific identity inspects that exact record rather than silently switching generations.

Summary/status results do not expose raw source or position rows. Rows are included only for an explicitly requested section. The section's `stored_rows`, source `omitted_rows`, page `rows_returned` and `next_offset` describe different denominators and must not be combined as if a page were the entire source. A projection is not a resealable snapshot.

## Error meanings

| Exit | JSON error | Operator interpretation |
|---|---|---|
| 0 | none | Valid bounded read, including an explicit ABSENT result. |
| 2 | `INVALID_REQUEST` | Invalid command/book/identity/section/range or oversized projection. No write fallback. |
| 3 | `SNAPSHOT_NOT_FOUND` | The explicitly requested identity does not exist. Do not invent a replacement. |
| 4 | `SNAPSHOT_CORRUPT` | Bad content/address/schema, missing domains, symlink, non-regular file or inconsistent read. Freeze consumption. |
| 5 | `SNAPSHOT_UNAVAILABLE` | Filesystem/scan-bound failure. Not equivalent to an empty complete dataset. |

The CLI deliberately has no `compose`, `capture`, `--path` or `--root` option. It does not perform a network call, provider turn, transaction recovery, queue action or account write. Known errors are sanitized and do not echo arbitrary input paths or private filesystem locations.

## Storage and correction integrity

Only explicit callers of the library persistence function can publish records; the CLI cannot. Publication accepts a closed, verified twelve-domain snapshot and creates only its fixed evidence-store path. It syncs newly created parent directories, writes and syncs a private temporary inode, publishes by a no-replace link, and syncs the leaf directory. Readers never see an intentionally half-written final record. An identical content-address replay verifies existing canonical bytes; a conflicting address is refused, not overwritten. Tests cover parallel publication, corrupted addresses, disappearing records and injected sync failure; they do not simulate every storage-device or operating-system crash.

A correction must refer to existing verified predecessors with the same decision cutoff. Existing records are not rewritten. A content seal establishes identity, not source authenticity, licensing, independence, market correctness or investment authority. The pure contract can represent minimal fixtures, but the store and production composer refuse incomplete twelve-domain inventory.

If publication reports `SnapshotWriteUncertain`, preserve the exact snapshot identity and original operation. Read back that identity through this same store before any further publication decision; do not mint a replacement ID or clear a pending portfolio operation. Cleanup errors cannot erase the original uncertain-publication diagnosis.

Automatic same-generation capture deduplication, source freshness/rights qualification, capture-driven correction discovery and a real current-market snapshot remain future S0 work. Do not populate the production store with test fixtures to create a green dashboard.

## Rollout and no-effect proof

This source release alone does not authorize deployment or arming. Before rollout require independent exact-head review, current-base checks, a real licensed source capture, authenticated UI/API boundaries and user-visible evidence inspection. Existing V2 account, fill, NAV, pending-target and settlement files must remain untouched by snapshot capture and reads. The calendar repair is separate from snapshot reads and must be recorded as an execution-policy generation on an authorized rollout; it never rewrites old ledgers or performance history.

The shared calendars remain explicitly bounded to the repository's 2025–2027 horizon. The repair unifies existing US/HK early-close facts; it does not establish a complete future-calendar service, HK closing-auction participation, overnight execution, Stock Connect settlement or derivatives-market hours.

## Application inspector — source candidate, not production SSO acceptance

The application now mounts GET `/api/decision-snapshot` and a browser shell at `/decision-evidence`. The API reuses `app.auth` operator authorization on every request, refuses read mirrors, and reports a missing authoritative operator configuration as unavailable. The new endpoint is excluded from `app.response_cache`; a route-local check is insufficient when a shared middleware cache could answer before entering the route.

The shell is public source-only HTML with no embedded evidence. It fetches the protected API with same-origin credentials and never collects, stores or embeds an operator token. Without the existing authorized operator request context it displays a locked state. This feature does not repair or replace production SSO. Do not paste the operator credential into the browser to claim acceptance.

The page selects immutable snapshot identities, displays cutoff/recorded clocks and coverage independently from correction status, and requests individual evidence domains with bounded exact-identity paging. Delayed/cancelled old requests cannot overwrite a new selection. All evidence renders as text. No capture, model call, allocation, write or order endpoint is exposed. Absence, corruption and missing authorization clear displayed data rather than preserving stale evidence as current.

Section responses are bounded at 65,536 bytes including their HTTP JSON envelope, not only the section payload. A too-large envelope returns a small typed refusal. Unknown/duplicate query keys and non-integer page values fail before storage access. API responses are no-store/private with Authorization/Cookie variation; the HTML shell has a self-only script/connect policy and no inline script.

### Verification commands

```sh
.venv/bin/python -m pytest -o addopts='' -q tests/test_decision_snapshot_api.py tests/test_decision_snapshot_ui.py
NODE_PATH="$PWD/.venv/evidence-browser/node_modules" node tests/decision_evidence_browser.cjs
```

Browser tooling is test-only: Playwright 1.64.0 in an isolated ignored npm directory, using an ephemeral profile of installed Chrome. `CHROME_PATH` can select the test machine's browser executable. The browser script intercepts all requests to `evidence.test`; it does not start a server or use live credentials/data. Its checks prove rendering, selection, paging, text isolation and stale-response behavior, **not** real network authentication, production capture or live trading. Real FastAPI auth/cache/store behavior is covered separately by the Python suite.

The separate proposed fixture-server file-write was refused pre-dispatch and confirmed absent. It was not retried. Consequently a combined real-HTTP-browser fixture journey remains unproven; do not combine the two test classes into a stronger claim. Screenshots are explicitly synthetic browser fixtures under `tests/fixtures/decision_evidence_browser/`.
