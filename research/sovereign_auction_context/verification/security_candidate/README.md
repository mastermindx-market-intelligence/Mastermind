# Mastermind security hardening candidate

Bound to CodeQL check **113599048562** and source head `42476573407fcb882c65a9388f98ed038801fc50`. This is a scratch candidate; root owns all canonical installation, checks and commits.

## Exact change

1. Renderer unit test selects the actual owned renderer using unique exact source boundaries and stops before its network call. It rejects missing/duplicate/out-of-order markers and any early case-insensitive closing script sequence, including inside a JavaScript comment. No HTML filtering regexp or scanner suppression is used for script selection.
2. The loopback harness snapshots contained, approved static bytes before serving. Request paths are only exact lookup keys. There is no request-derived filesystem access. Existing containment, suffix allowlist, loopback/network guard, native handlers, fixture isolation and clocks remain.
3. The live inherited status-pill attribute sink is repaired through quote-safe `esc`. All call sites were reviewed. Targeted hostile-status regression failed before the repair and passes after it; existing auction escaping and presentation tests still pass.
4. A small standard-library test file checks allowed assets, symlink containment and immutable request-time byte lookup boundaries.

## Install and verify

The four files and exact old/new hashes are in `SECURITY_HARDENING_RECEIPT.json`; `SECURITY_HARDENING.patch` contains the complete delta. `PREIMAGES.json` records the source bindings without adding duplicate historical source copies.

Run the renderer test from the real Mastermind repository:

```sh
node tests/test_sovereign_auction_renderer.cjs
```

Keep the static-boundary test beside the existing Python browser harness and run:

```sh
python3 test_mastermind_static_assets.py -v
```

Both pass locally. Then root runs native tests and the unchanged 48-case browser runner against the installed source in a new output directory, followed by normal exact-head CI/CodeQL assessment. No extra dependency, provider operation or external browser request is required.

## Acceptance boundary

Independent read-only review passed at the final hashes. Native HTTP/browser and new CodeQL results remain pending; prior browser receipts apply to their recorded source hashes. No source publication or full CI clearance is claimed. Existing archived preimages and receipt bytes were not edited; root separately owns their immutable-Git archival references.
