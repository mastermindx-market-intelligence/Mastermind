# Paper Desktop catalog qualification · 1b9aff

## Decision and scope

The complete observed catalog is compatible with the bridge’s **existing allowed operations**, subject to the exact catalog pin and unchanged dispatch guards. Qualify only `1b9afff4c9bcf6f11f5ca2db301bf25ccdc442025344e2ec402459cedcd6a2db` for the new source generation. This is a source compatibility decision, not runtime installation, provider enrollment, execution permission or production acceptance.

The production bridge change is one constant: `SUPPORTED_CATALOG_SHA256`. Its resulting source hash is `82bc7f2d75aec423711922198b68f317618a83de177bf4934b73d7b418a6ecfb`. A separate source-only registry addition assigns that exact hash to **v13**. Every earlier runtime hash remains unchanged. The unmerged #1409/v12 hardening source and the previously blocked v12 staging operation are not adopted, retried or reinterpreted by this change.

Source base supplied by the root: isolated v13 workspace `ad125292b34f313924f9719b8de772027f0ea225`, clean at acquisition. The supplied bridge bytes match the installed v11 bridge hash `6d28be62b21bff12dc04ae1bdc50f12a4ff55fdb8261bdd6923bac2804fecf7c`. Installed C3/runtime binding and exact release authority remain root-owned. The worker performed local source/fixture/test work only.

## Complete catalog proof

Catalog identity uses the existing bridge `encode`/`digest`: sorted JSON keys, compact separators, ASCII escaping and rejection of non-finite values. No hashing behavior changes.

| Catalog | Tools | Canonical SHA-256 |
|---|---:|---|
| Previously accepted full fixture | 36 | `48b2587455d839a57b4b78f5cfdb2e75df8d530ad8059a3ad6af303c0d37224f` |
| Complete observed full fixture | 37 | `1b9afff4c9bcf6f11f5ca2db301bf25ccdc442025344e2ec402459cedcd6a2db` |

The new immutable fixture is `tests/fixtures/paper_desktop/1b9aff_full_catalog.json`, copied from the entire observed tool dictionary. It contains all tool names, descriptions, annotations and input schemas, including blocked tools. The prior dictionary was supplied from an immutable source solely as a validation fixture and independently matches the already accepted 48b258 pin. It is not authority to adopt other source changes from that branch.

Exactly **32 shared definitions are unchanged**. There are eight structural differences: two added tool definitions, one removed tool definition, two changed descriptions, and three added optional properties. No further field, required-input, annotation or schema difference exists in the compared dictionaries. `docs/PAPER_CATALOG_1B9AFF_DIFF.json` records every path and both complete dictionaries remain available to the root. The committed regression tests reconstruct this exact delta and compare the full objects.

## Exhaustive changes

| Changed path | Observed change | Qualification assessment |
|---|---|---|
| `create_page.description` | Documents insertion after the user-viewed page and the separate arrangement tool | No explicit target or authorization boundary changes. Creation still requires the guarded file; page arrangement remains unexposed. |
| `create_page.inputSchema.properties.icon` | Optional decorative string enum of 17 known values | Existing required fields and `additionalProperties:false` are unchanged. Any further change to the upstream schema fails the exact catalog check; this patch adds no argument-validation behavior. |
| `get_basic_info.description` | Describes ordered page/divider records; divider IDs have no canvas | The bridge preserves this opaque list within the hashed basic-info object. It derives identity from the exact file ID, not the list. Divider/order changes invalidate a prior snapshot. Callers must use page IDs from page records for page-scoped operations. |
| `get_jsx.inputSchema.properties.includeNodeIds` | Optional boolean; documented default true | A read-only export option. The bridge forwards read results and does not parse/export them into a modifying operation. Clean source exports should request false explicitly. |
| `get_jsx.inputSchema.properties.includeRootPositioning` | Optional boolean; documented default false | A read-only export option. Portable source exports can request false explicitly; inspect node coordinates with the existing read tool. |
| `rename_pages` | Removed upstream | It remains absent from the bridge allowlists. Calling the old name is refused before upstream initialization. |
| `arrange_pages` | Added; reorders pages and creates/removes visual dividers | **Blocked.** Its destructive annotation is not an authorization grant. It is never added to READ_TOOLS or EDIT_TOOLS. |
| `update_pages` | Added; batch page name/icon changes | **Blocked.** This preserves the old page-renaming restriction under the new tool name. |

The bridge’s existing server-name requirement remains `paper-desktop`. Release version stays observed diagnostic metadata, as it was before this patch; this change does not weaken a version check. The reported upstream version is 0.5.14. Write dispatch fails closed for any catalog change beyond the exact reviewed dictionary, even if the server version remains the same. Read-only inspection remains available under the pre-existing policy.

## Permissions and effect semantics

`READ_TOOLS` remains the same 16 names; `EDIT_TOOLS` remains the same 12 names. The current catalog projection has the same **28 exposed tools** and these nine blocked tools:

`arrange_pages`, `create_file`, `delete_nodes`, `export`, `export_combined_pdf`, `list_resources`, `open_file`, `rename_resource`, `update_pages`.

Legacy `rename_pages`, unknown tools and other absent names remain blocked. The implementation does not infer tool permission from upstream annotations or auto-admit renamed tools.

Every edit still requires write opt-in, an allowed tool, stable operation ID, valid snapshot hash, exact explicit file ID, matching inspected target and fresh execution-binding guard. Token deletion remains refused. The per-host mutex, fixed loopback transport, private artifact paths, server identity and input limits are unchanged. There is no new retry, queue, registry authority or provider-home configuration.

Once an edit is dispatched, a timeout, upstream tool error or unverifiable after-state remains `EFFECT_UNKNOWN`, with the original operation ID and `retry_allowed:false`. The catalog qualification does not turn a partial error into a definite no-effect result. Previously unresolved operations require their own same-carrier reconciliation.

The old 48b258 catalog is **not silently added** to the new default pin. The immutable v11 runtime keeps its historical source identity; a v13 runtime would require the newly qualified exact catalog. This patch introduces no multi-catalog fallback or override route.

## Tests and release boundary

`tests/test_paper_catalog_1b9aff.py` adds focused proof for:

- Complete fixture hashes and the exhaustive eight-path delta.
- Preserved file requirements and exact optional field types/enum.
- Guarded acceptance through the production default pin, with synthetic transport.
- Catalog projection and refusal of both new page mutators before client initialization.
- Fifteen further descriptor/schema/annotation/name changes refused before dispatch.
- Prior catalog and wrong server identity refusal.
- Write opt-in, operation, snapshot, file, runtime binding and token-deletion guards.
- Mixed page/divider snapshot binding and explicit JSX read-option forwarding.
- One-dispatch unknown effects with no retry.

Existing bridge tests are updated to reference the new current fixture while retaining the historical font-catalog proof. Runtime-stage tests check the new v13 source hash and preserve immutable v11/v10/v9 pins. Tests use synthetic clients and temporary directories. They do not prove that a real Paper edit occurred or grant runtime release authority.

The supplied local suite ran **73 tests: 72 passed, no assertion failures, no skips, and one environment error**. The unchanged `WireTests.test_handshake_session_json_and_sse` could not create its ephemeral loopback socket because the local sandbox refused `socket.socket`. All 13 new catalog tests, all 21 runtime-stage tests and all 38 bridge core tests passed. No test was weakened to work around that restriction. The canonical environment must run the existing HTTP fixture before release. `validation/unittest-full.log` and `validation/unittest-summary.json` in the handoff preserve the complete attempt.

An exact byte comparison additionally proves that reverting only the new catalog pin reproduces the canonical bridge, and removing only the v13 registry entry reproduces the canonical runtime-stage module. The root verified that the source transport added one final line-feed byte to `runtime_stage.py` and its test file; the candidate restores the original absence of that byte, with both original hashes confirmed against HEAD. Every historical v2–v11 registry value remains byte-identical and no v12 entry is present. This establishes that allowed-tool sets, guard logic, transport and staging behavior were not changed by the proposal.

The root must obtain the required independent source/release checks before any deployment, then verify the exact installed bridge/runtime binding and new live catalog receipt. A subsequent real guarded edit and its screenshot/readback provide application proof. No v13 runtime creation, Paper mutation, C3 app edit or provider restart was performed by this worker.
