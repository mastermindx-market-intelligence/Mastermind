# Native Codex paired Workspace OAuth qualification

## Outcome and exact source

This candidate implements the opt-in ordinary API-principal connection required for the Mastermind COO MCP endpoint to receive a separately authorized Workspace companion. It reaches the real native config parser, MCP connection factory, credential stores, refresh transaction, HTTP capability, explicit CLI login and app-server login refusal. It does not assert native T3 origin.

The source is `openai/codex` at `086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a` (`rust-v0.167.0`). The pinned RMCP dependency is `98a54789b80110ad210495c4ad845c89e1980471`. The fixed descriptor and semantics come from Mastermind `95762fc3700598a7be1a12b8c6c1995753071eed`; protected law remains `c065e56b4cb7c4487e51249795ca6ebf010e6ffa`.

`codex-workspace-paired-oauth.patch` contains exactly 22 paths. `source_manifest.json` records each original Git blob and SHA256, final Git blob and SHA256, the patch hash, and hashes of the qualification evidence. `postimages/` contains those exact final files. The integrity replay applies the patch over the exact original blobs and checks all 22 resulting hashes. This is a reviewable native source candidate, not fork publication, an installed feature or production acceptance.

## Implemented ownership and behavior

The closed optional `oauth.workspace` configuration reuses `mastermind.hermes_workspace_oauth.v1` unchanged. Only the fixed local `mastermind_coo` name, primary URL/resource/scopes, registered public client and fixed Workspace resource/identity endpoint/scope are admitted. The source owner supplies the actual 64-character `principal_scope`. Generic header helpers, bearer/environment overrides, remote environments, confidential clients and alternative endpoints are refused. Omitted configuration retains legacy serialization and behavior.

The original MCP factory validates before HTTP effects. Its existing connection identity now includes the selected pair configuration and scopes/resource. An isolated primary credential does not imply pair readiness: preconnection status is `Unknown`, and the actual initialized connection owns proof.

Each resource retains its original concrete credential backend, selected home, OAuth manager and coordinated refresh transaction. The existing store checks home custody around reads and mutation, validates role/client/issuer/scope/token type/expiry, and preserves its refresh persistence, locking, cancellation and definitive-rejection retirement owners. No credential format, backend, queue or authentication service is added. The companion's off-loop store read preserves the original storage telemetry attribution.

The captured original HTTP capability acquires same-origin protected-resource metadata and a bounded fixed Workspace identity proof. Only the fixed primary MCP endpoint receives the companion header. Neither bearer is sent to an unrelated endpoint or redirect. Metadata/token requests carry no Authorization or companion header. Token errors retain a closed OAuth error code for the incumbent manager while dropping provider descriptions and arbitrary payload fields.

Current original credential snapshots and selected home are checked before the original protected request and after its response. The original request is sent once. A rejected request returns a nonretryable closed grant error; lost response or post-send drift returns `WORKSPACE_OAUTH_ORIGINAL_OUTCOME_UNCERTAIN`. Only the existing HTTP owner's explicit `RequestNotSent` retains proven-prewrite classification. No retry, replay or new operation owner is introduced.

The original explicit browser login performs two sequential authorization-code/PKCE consents and saves two resource-specific records through the existing store. An incomplete second consent does not erase the first grant or claim readiness. The one-URL app-server login RPC refuses before scope discovery, header resolution or any login flow. Silent, manual callback and CLI empty-scope retry paths also refuse the pair before starting those effects. No login occurs during connection startup.

## Executed checks

All Cargo commands use the isolated Rust 1.95.0 toolchain selected by the original source toolchain file. They use `--locked --profile dev-small`, two build jobs, and no installed user profile or credentials.

| Check | Result | Evidence |
|---|---|---|
| Focused config and native OAuth tests | 17 passed: 3 config and 14 native OAuth | `paired-tests-qualified.log` |
| Final full native `codex-rmcp-client` owner suite | 275 passed; one incumbent helper ignored by default and explicitly run by its parent subprocess test, which passed | `final-rmcp-owner-suite.log` |
| Actual `codex-mcp` source/currentness and status factories | 2 passed | `final-mcp-consumer.log` |
| CLI and app-server libraries | Passed (10m 24s) | `native-callers-check.log` |
| Actual CLI binary containing the changed login command | Passed (13.58s) | `native-cli-check.log` |
| Canonical config schema generator | Passed; 37 added lines, no removed lines | `schema-generation.log` |
| Independent schema regeneration readback | Exact bytes; SHA256 `8f5b4fc958c0b8719330c9c5b9b5be3104e55dfa0d72866d2ce2c499f773b8e4` | `schema-readback.log` |
| Rustfmt and whitespace | All 20 changed Rust files pass; `git diff --check` passes | `rustfmt-final.log`, `integrity.log` |
| Exact source replay | All 22 postimages match original-base patch application | `integrity.log` |

The final owner suite re-executed all 14 new native cases after the final storage-attribution and error-redaction changes. The 3 config tests' source remained unchanged. Tests exercise actual parsing, PKCE/callback, OAuth managers, file credential stores, locks, refresh and native MCP handshake using a disposable supplied HTTP capability. They include missing companion, foreign/stale/oversized proof, source/home/scope drift, concurrency, refresh rejection retirement, cancellation, lost response, and unsupported login surfaces.

The actual handshake test exposed a material integration defect during development: classifying a denied original request as generic HTTP failure caused the incumbent initialize owner to send it three times. Fixed-contract outcomes now use the original nonretryable protocol-error classification. The qualified actual native handshake proves one send and zero reactive refreshes after a 401. Earlier failing diagnostic logs are not passing evidence.

## Reproducible tag lock reconciliation

The exact upstream tag declares workspace version `0.167.0` but its checked-in lock records 171 workspace packages as `0.0.0`. An initial unchanged `--locked` build therefore refused. Qualification temporarily uses `version-reconciled-Cargo.lock`, changing only those 171 workspace-package version fields. All 1,479 package records are accounted for; no third-party version, checksum, Git pin or dependency changes. `run_qualification.py` asserts this difference and restores the exact original lock in `finally`. The lock is not part of the source patch. `lock-metadata.diff` records the temporary build-only difference.

The native rustup installer was verified against its downloaded checksum `b1c8cb14e30889e7e2999e6b69e62d9e9b9ffc0f4df8180564d306d9680e6c55`. Toolchain/cache/target files remain isolated in this qualification directory. The separately generated broad diagnostic lock was never used for qualification and is not candidate evidence.

## Explicit limits and next owned step

No native or T3 fork was changed remotely. No installed executable, profile, consent, account, service or model/session was started. The candidate must pass the intended distribution's existing review/build/release owner before installation. T3 fork and native source publication remain ungranted in this assignment. A real enrolled public client, matching current source binding and independent Executive and Workspace authorization are still required. No grant is inferred from the descriptor or passing fixtures.

The tests run on Linux. They do not establish macOS Keychain custody, actual browser consent or an installed M2/T3 end-to-end journey. The separate frozen 10-case Mastermind API proof covers the real ProjectTeam handoff through the authenticated API source path; it is not presented as a single installed native journey with this candidate.

For streaming responses the final transport currentness check brackets response headers. The original HTTP/MCP owner retains later streaming and cancellation; the application's source/result validators remain authoritative. Local credential removal is distinct from remote authorization revocation. Existing primary logout makes the pair unusable but this candidate does not add a second remote logout/revocation protocol.

Native T3 thread/turn/tool-call attestation remains unavailable: the Control enrollment owner has no enrolled native-host attester bound to the original provider connection. Ordinary metadata cannot supply that authority. This candidate provides the independent ordinary API-principal avenue without inventing a signer, registry or native identity.
