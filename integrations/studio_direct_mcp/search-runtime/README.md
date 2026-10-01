# #1027 bounded search candidate — source qualification

This package retains mihailt's PR768/PR779 composition and applies the reviewed-artifact V3 candidate to the exact upstream donor. It is a draft integration input, **not an installed backend or release-ready repair**.

- Upstream: wonderwhy-er/DesktopCommanderMCP, commit `56b5127ec6539f1d182ed4c3ffdeb114cf6bfd66`.
- PR779 already contains PR768 `7cc1ff30646ef294cee4a1daa04470c27aebea30`; do not cherry-pick it again.
- Upstream MIT license and ownership are preserved in `LICENSE.upstream`.
- Patch SHA256: `2202d6a95e58fa7d6d8401330579496891faddccca39445957dc8f910c7cb435`.
- Carrier: https://github.com/mastermindx-market-intelligence/Mastermind/issues/1027#issuecomment-5923687741

## Reproduce

Use Node/npm, Python 3, patch and existing ripgrep. Select a **new disposable evidence directory**, not an installed package or Git checkout:

```sh
python3 validate-upstream.py --output /approved/evidence/new-issue1027-build
```

The script materializes bounded build inputs from the pinned archive, verifies exact donor blobs, applies the six-file patch, installs lockfile dependencies with lifecycle scripts disabled, runs the actual upstream package build, then seven upstream suites. The upstream runner uses temporary isolated configuration and disables telemetry. Build outputs are deliberately outside source. No native app, installed setting, credential or service is changed.

## Implemented and verified

V3 adds finite default result/deadline budgets, shared retained-text/context/output caps, terminal guards, truthful settlement, exact-handle ripgrep TERM/KILL escalation, and session-owned Node Workers for existing ExcelJS/PizZip parsing. One unacknowledged IPC record prevents producer flooding; completion waits for actual Worker exit.

Preserved V3 evidence: 22/22 deterministic checks, 4/4 handler checks, 16/16 real Office checks, 17 worker exits, zero residual workers/processes, 11/11 mutation discriminators. These are prior artifact checks, not claimed rerun by this script. The immutable artifact includes their detailed harness and V2 control; ZIP SHA256 `eb5f5995d4b6f4eab504fa1ac72c11aed4a60ad79ff733fc5c5e50a27365f2ae`.

New integration evidence: actual full TypeScript and package builds pass; seven upstream search suites pass with zero skips, including genuine XLSX/DOCX parsing. See `qualification.json`.

## Release blockers

This candidate does **not** yet implement pre-validation/pre-spawn deadline coverage, broad-root refusal, bounded ripgrep thread count, host/executor-wide live-work admission, identical-live-scan reconciliation or operation/native-handle attribution. Retained-text and Worker V8 heap budgets do not bound aggregate/native RSS. These remain explicit #1027 acceptance gates, not suppressed tests.

Independent admitted non-Codex Fabric review is pending; the current exposed Executive route reports readonly. Registration is source custody, not independent review or installer authority. Full vendor suite, native schema/transport acceptance and exact installed-generation canary remain pending.

The existing Studio installer owns gateway/account state and seals the configured backend identity; it is not the vendor updater and refuses changed backend identity. Existing backend bytes are outside the observed allowed paths. Do not hot-edit them, widen permissions, modify credentials, change security settings or restart active work. Resolve backend updater/preimage access through the existing installer owner before planning a quiesced canary and rollback. Executive/Capacity and BackendOwner retain their current responsibilities.


The patch is byte-pinned, including original unified-diff context whitespace. The local Git attribute exempts only this patch artifact from whitespace diagnostics; generated TypeScript is still compiled and tested.
