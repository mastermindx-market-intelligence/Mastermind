# BSC-U1 Business Sol installation and enrollment implementation plan

**Operation:** `business-sol-u1-installation-binding-compiler-20260904-sol-001`  
**Carrier:** existing branch `sol/business-sol-plugin-app-integration-u1-20260901`  
**State after source merge:** `BUILT_NOT_PROVEN / U1_BINDING_AND_ENROLLMENT_TOOLING / PRODUCTION_INERT`

## Outcome

Produce a deterministic, reviewable bridge from the protected symbolic plugin template and approved Business workspace observations to one private staged binding artifact, redacted receipt, rollback manifest, and verify-only result. The bridge prevents stale app/tool identities and undocumented manual steps from becoming the basis for the real U1/C1 ceremony.

This plan does not install or publish anything. `.app.json` follows the documented OpenAI native app-reference format, not the
private Mastermind metadata envelope. The later admin/browser layer must assemble
and verify a plugin whose manifest references `./.app.json`; this compiler alone
does not assemble, import, install, or authenticate that plugin.

## Authority and no-rebuild boundaries

1. current protected Sol Skillpack and Business Sol architecture;
2. protected P1 plugin package and symbolic template;
3. protected A1 OAuth, Steward v2, and Executive app contracts;
4. official current OpenAI Business custom-app behavior at action time;
5. this bounded compiler source.

Do not create a workspace registry, credential store, app database, session table, OAuth cache, retry ledger, tunnel owner, lifecycle plane, or super-MCP. Executive OS, Agent OS, RuntimeBinding, Wake, GitHub and app authentication retain their owners.

## Source surface

Exactly eight paths:

- `integrations/business_sol_installation/__init__.py`
- `integrations/business_sol_installation/bindings.py`
- `scripts/mastermind_business_installation.py`
- `tests/test_business_sol_installation.py`
- `tests/test_business_sol_installation_adversarial.py`
- `tests/test_business_sol_installation_static.py`
- `docs/runbooks/business-sol-installation-enrollment.md`
- `docs/superpowers/plans/2026-08-31-business-sol-installation-enrollment.md`

No package manifest/template, OAuth/app implementation, workflow, dependency, Executive, Steward, RuntimeBinding, or deployment path is modified.

## Contracts

### Input

`mastermind.business_sol_installation_request.v1` is a closed plain-data observation packet. Exact types are required; Boolean is never accepted as integer; subclasses and unknown keys fail closed. Approved and observed source/package/app-policy values are compared. The compiler does not collect or authorize those facts.

### Preflight

`mastermind.business_sol_installation_preflight.v1` returns:

- `READY_TO_COMPILE` with zero issues; or
- `PREFLIGHT_HELD` with a complete deterministic issue set.

A held preflight emits no binding document digest or file.

### Native document and private validation envelope

The emitted `.app.json` contains only the native `apps` map. Its canonical ASCII
JSON and final LF define `binding_document_digest`. The internal
`mastermind.plugin_app_bindings.v1` envelope retains validated source, plugin,
app generation, resource, OAuth and tool metadata; canonical bytes WITHOUT an
app-file LF define the separate `installation_plan_digest`. It is not emitted
as `.app.json`. Compare both digests when reusing evidence. Equal inputs remain
byte-identical; metadata changes cannot be hidden by equal native references.

### Public receipt

`mastermind.business_sol_installation_receipt.v2` contains only source/package/workspace/template/binding/app-ID digests, logical names, observed install/connect Booleans, and explicit false authority/effect flags. It contains no raw plugin/app ID, URL, token, secret, local path, cookie, credential, or production claim.

### Stage/readback/rollback

The explicit output root must be absolute, existing or creatable, symlink-free, and disjoint from the protected source root. Stage uses one exclusive temporary file, fsync, exact mode `0600`, atomic rename, postimage verification and effect-unknown reconciliation. Verify is read-only. Rollback requires the exact postimage and restores the exact preimage or absence.

## RED-first proof sequence

1. RED tests for missing Steward, app ID absence, stale app/tool/resource/OAuth digests, duplicate and extra bindings, source/package drift, and incorrect authority flags.
2. GREEN pure preflight/compiler with deterministic canonical bytes and redacted receipts.
3. RED filesystem tests for output-in-source, output-containing-source, symlink components/target, preimage/temp conflicts, readback drift, and lost rename response.
4. GREEN staged write/readback/rollback with fixed public errors and no blind retry.
5. Mutation-style tests for exact-type admission, changed generation under the same identity, tool-order drift, installed/connected observation non-authority, and receipt leakage.
6. Static import fences proving no network/browser/MCP/Executive/Agent OS runtime dependency.
7. CLI positive, held and refusal proofs.
8. Focused tests, warnings-as-errors compile, complete repository/security checks, exact eight-path diff and independent non-author review.

## Real U1/C1 continuation

After source protection, a distinct privileged operation performs the real ceremony:

`source proof -> app publication -> endpoint reachability -> OAuth -> user installation -> successful read -> separately confirmed write admission -> production acceptance`

It must establish an approved Secure MCP Tunnel and exact published Steward app before the current missing-Steward hold can clear. A successful plugin import does not prove app access; OAuth does not prove a read; a read does not authorize write admission; a queued intent does not prove execution; none of these alone is production acceptance.

## Correction and replay law

- Same generation and same normalized inputs: same bytes/digest.
- Changed source, app, tool, resource, policy or package identity: new explicitly approved observation/generation; never silent in-place drift.
- Stage response loss: read the exact target and accept only the exact expected postimage; no second write.
- Changed preimage/postimage: conflict/refusal; do not overwrite.
- `STAGE_EFFECT_UNKNOWN` or `ROLLBACK_EFFECT_UNKNOWN`: preserve exact carrier and target until reconciled; no alternate path or session.

## Stop condition

Stop the source wave after one Draft PR has exact eight-path scope, focused/full/security proof, independent exact-head PASS and an immutable release candidate. The source merge makes tooling available only. It does not create a Business app, tunnel, OAuth client, connection, read canary, write admission, RuntimeBinding or production acceptance.


### Native-format correction — September 5, 2026

The official existing-app JSON format is documented at
https://learn.chatgpt.com/docs/enterprise/plugin-management . Output only the
native `apps` map with actual app IDs, while the v2 receipt binds native bytes
and the complete validated metadata separately. Reject `plugin_` directory IDs;
do not normalize an approved identifier silently. Generation one deliberately
continues to accept only the two commissioned custom-app identities. Source
repair does not authorize a ninth path or mutation of the protected P1 manifest.
The native-manifest pointer and authorized package publication remain required
before any installable-plugin claim, with real app readback after installation.
