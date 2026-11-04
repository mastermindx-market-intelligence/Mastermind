# Prospective native Fabric prelaunch diagnostics

Source-only repair under the existing Mastermind #1829/#917 delivery owners and
#1957 task P1.R7. This is not an installed generation, new dispatcher, error ledger,
retry mechanism, or permission to repeat any refused request.

## Observed gap

Two original review requests in the November 2 turnaround were retained as
REQUEST_REFUSED_BEFORE_LAUNCH. Their matching original receipts proved
launch_attempted=false but stored only prelaunch_FabricTaskError. The controller
outputs contained exit 75 without a useful reason. Their exact routing cause is
UNKNOWN; it must not be reconstructed from a later availability snapshot.

The protected native source records only the exception type and its status reader
omits a diagnostic code. This proposal preserves a small closed code in the SAME
receipt and exposes it only after the existing schema, identity, digest and
no-launch checks. Legacy/missing/unknown codes remain explicitly unclassified.
Raw exceptions, paths, account details, provider output and credentials are never
copied into the diagnostic. NO_ROUTE means the existing routing owner refused to
produce a route, not that a different pool, account or retry is authorized.

## What remains unchanged

The original exception text/type and exit behavior, request identity, launch
marker, admission, routing decisions, quota, budgets, root verification, result
acceptance, and same-run no-replay fence remain controlling. A diagnostic cannot
attest a worker root, prove a START, or authorize a successor. The additive field
is not a Job state. The current active candidate, staged inventory, installed
release, selectors and manifests are untouched.

The test applies this exact-preimage patch only in a disposable directory. It
executes the materialized classification, route-parse and retained-status code,
checks adversarial/legacy receipts and compares the untouched admission/routing
AST. This is source/component evidence, not an end-to-end provider or installed
consumer canary. Original failed reviews are not rerun as tests.

## Release gate

Independent non-author review and normal protected source checks come first. The
existing native generation/composition owner must incorporate the reviewed delta,
requalify its actual inventory and select/install it through that owner's release
path. Then one genuinely new authorized request with a controlled prelaunch
refusal must demonstrate the code at the actual caller. Never patch an installed
private adapter, relax a refused operation, or use this artifact as installation
authority. The public candidate named in manifest.json is an exact source preimage,
not a claim about the current installed native generation.

## Executed source checks

### Historical preimage retained during browser-catalog integration

The exact original source is retained in `fabric_task.py.base`, with the same
`preimage_sha256` recorded in `manifest.json`. The patch, its postimage digest,
and the original manifest remain unchanged. The manifest's
`active_candidate_unchanged` records the proposal's original qualification;
it is not a claim that all later active-reader improvements are prohibited.
The browser catalog's separate owner-namespace read binding changes the active
adapter without applying this diagnostic patch. The prospective tests still
apply and qualify the exact historical patch in a disposable directory, and
also verify that its diagnostic classifier and status field remain absent from
the active adapter. Adopting the diagnostic patch later requires qualification
against that later source; these historical results do not establish it.

Two targeted tests against the unchanged preimage failed on the absent diagnostic
field/classifier (exit 1). The exact materialized postimage then passed all 31
focused cases (exit 0), including legacy, malformed, identity/digest mismatch,
launch-marker and symlink negatives. The existing Fabric MCP facade regression
suite passed 53/53 with zero skips. The active candidate preimage remained
byte-identical throughout. These counts are component/source checks, not proof of
an installed native generation or successful provider review.

Local evidence digests (SHA-256):
- RED: `89f2f4481b5079e79d363134ddab075bdfaf97c426a541ec8e4bd4cb5fe2333e`.
- Focused GREEN: `1b8f208de3636df279448e40805982570c4351601ce5723301928feea7d343cf`.
- Existing facade: `c2f89a6ea9c0edb6039026975450c1f11c63a1a6b46cc73adf8e679461796a5f`.

Commands: `MMX_REFUSAL_DIAGNOSTICS_BASELINE=1 python3 -m pytest -q
tests/test_native_fabric_refusal_diagnostics.py -k 'known_refusal_code_is_visible
or route_refusal_keeps_original'`; then `python3 -m pytest -q
tests/test_native_fabric_refusal_diagnostics.py`; then `node --test
integrations/studio_direct_mcp/fabric-backend.test.mjs`.
