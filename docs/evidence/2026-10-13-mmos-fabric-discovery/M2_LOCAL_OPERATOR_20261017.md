# M2 direct Fabric · Private native operator history

**Carrier:** [Fabric Discovery PR #1426](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1426). Original parent source `26cc7e0e8f22ad57fe301765c562a7e486f53270`. **Delivery state: BUILT_NOT_RELEASED.** This slice does not replace Executive/Agent OS, create a daemon, install a new plugin, or give ordinary Mastermind OS web users M2 access.

## Outcome

A working M2-owner-only Rust reader, `src-tauri/src/bin/fabric-local-report.rs`, uses the **existing** installed Fabric ledger and fixed C3 profile. It emits `mastermind.local_fabric_owner_runs.v1`: at most 32 unique newest retained run IDs with source-declared root/parent labels, pool, model, signal, return code and time. It strips keys, prompts, raw response, model text, billing, acceptance and every non-allowlisted field. Output is explicitly `LOCAL_MACHINE_OWNER` / `RETAINED_LEDGER_OUTCOMES_ONLY`. Active count, total workers and full fleet coverage are **unknown**, not zero.

The optional `LocalFabricOwnerImport` is mounted inside the **existing** Fleet & Capacity → Attended Fabric workspace only when running in the native Tauri application. It accepts an explicit owner-selected JSON file (max 65,536 bytes), validates a closed shape, and lets the operator search and follow source-consistent parent/child links **only within the loaded 32 rows**. It performs no network calls, M2 controller actions, launches, accepts, or automatic reads. It does not render in an ordinary web browser. It requires the native app's existing signed-in Workspace acquisition state and source generation before displaying an import.

**Important architecture:** The native import component installs **no new authentication listener**. It relies on the existing App/Host auth generation and native route remount. A prior multi-listener implementation disrupted a single-subscriber operation-recovery fixture; the exact recovery test was reproduced red in an isolated overlay, passed on the untouched original, and passed after removing the extra listener. The corrected source clears imported data or makes it inaccessible as soon as the parent identity/epoch changes. The unprivileged WebView never receives a machine-read command.

## How to use privately on M2

Run from the *M2 owner account*, on the same installed C3 and ledger that were actually verified:

```bash
R=/Volumes/Mastermind/agent-workspaces/web/mmos-fabric-discovery-20261013-c4
OUT="$HOME/Documents/mm-fabric-history-$(date -u +%Y%m%dT%H%M%SZ).json"
(
  umask 077
  cd "$R/app/mastermind_os/src-tauri"
  MM_SOURCE_REVISION="$(git -C "$R" rev-parse HEAD)" \
    MM_BUILD_IDENTITY=m2-local-operator \
    cargo run --quiet --bin fabric-local-report > "$OUT"
)
printf 'Private report saved at %s\n' "$OUT"
```

The CLI uses a fixed M2-only path and refuses another UID, root process, unsafe final-file symlink/hardlink, incorrect C3 host/profile or changed ledger identity. It does **not** load a JWT, modify the pool ledger, talk to MCP, or assert per-person ownership. The file should stay **private** (use `umask 077`) because run labels can contain project references.

**After a reviewed native app build/installation**, sign in using its existing Workspace auth, open **Fleet & Capacity → Direct M2 Fabric history**, and use **Import local Fabric snapshot (JSON)** to select that file. The import panel never uploads it. To refresh, generate a new owner file and import it explicitly. No background polling, watch process or second controller is introduced.

This is a **local operator history workflow**, not the still-owed signed-in web/native *remote user* run catalog. A native-app marker in JavaScript is presentation gating, not a server-issued authorization token. `MACHINE_OWNER` data never becomes `EXACT_RUN_SET` merely through this import.

## Actual verification

- Original M2 operator executed successfully against its **real ledger**. The most recent sanitized report contained **32 unique run IDs**, `machine_wide_fleet_complete=false`, `total_records=null`, `active_workers=null`, with JSON SHA256 `39471c706d2df824d4f9c2a989a3d2b2ccafba15f0747e72e50c506a6addf3a6`. It is held privately in the M2 evidence workspace, **not checked into GitHub**.
- The frontend TypeScript decoder parsed that **actual Rust-produced file** directly in Node 26, with 32 distinct records and the expected explicit unknown coverage. No raw private rows were printed to the test output.
- Rust reader tests: **6 passed** (strict owner/profile refusal, metadata sanitization, malformed HTML/overlong rows, source bounds, latest unique run identity, corrupt/partial line handling). Normal native-app Rust tests: **27 passed**. Targeted new Rust source `rustfmt --check`: pass.
- Frontend focused: **39 passed across three test files** (local import+contract and existing operation reauthentication). Full current Mastermind OS suite: **1,529 passed, one existing skipped, zero failures across 69 files**. TypeScript `tsc --noEmit` and Vite production build: pass; existing Tauri dynamic-import and large-chunk warnings remain.
- Regression diagnosis: original operation-reopen test **passed on unchanged PR head**, failed under an overlay that mounted the new component with its second auth subscription, then passed with the second subscription eliminated. No upstream auth implementation was replaced or relaxed.
- Exact code files, test logs and SHA256 manifests are in the companion `M2_LOCAL_OPERATOR_20261017.json`. Source and evidence were frozen before the PR commit; the final SHA should be read back after publication.

## Nonclaims and remaining gates

This is **not** a release of an installed native app, a browser screenshot, an independently reviewed PR, a live M2 status count, result-content retrieval, model quality verdict, or any authorization to inspect another web user's native run. No new token, public endpoint, privileged tool passthrough, Fabric task, queue, ledger writer, CI waiver or server-side principal grant was created.

The direct M2 realtime/remote Catalog still needs the canonical issuer-authenticated principal/workstream → original Native Run association, positive/sibling-denial/revocation tests and protected backend review. The original Fabric Catalog #1426 remains **Draft/Hold** until its appropriate source/CI/browser/installation gates clear. This local private operator slice is usable *without waiting for Executive OS* but does not remove those separate release requirements.

**Prior independent Fabric architecture audit:** `mmos-native-m2-local-operator-design-20261017-c4-01` completed and advised preferring a local CLI over exposing machine-owned data in a persistent web transport. It was not an exact-source independent security approval and contained Linux-specific suggestions inapplicable to M2/macOS. Do not misclassify it as accepted production review.
