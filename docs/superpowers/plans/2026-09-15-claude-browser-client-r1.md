# Claude Browser Client R1 Implementation Plan

> For agentic workers: use executing-plans or subagent-driven-development for this bounded slice.

**Goal:** Translate existing, validated MCP grants into Claude client configuration without granting new browser, credential, host, helper or lifecycle authority.

**Architecture:** Existing Executive capability grants remain the input. One pure client projection serializes their transport and exact tool names for Claude Code, Agent SDK, local Desktop and eligible inline helpers. It starts no process and does not change the sealed subscription-worker launcher.

**Tech Stack:** Python, existing ExecutionCapabilityProfile/McpServerGrant, official Playwright MCP already pinned to 0.0.79.

**Spec:** The end-to-end program and dependency boundaries are in `research/CLAUDE_BROWSER_FLEET_PROGRAM_2026-09-15.md`.

## Global Constraints

- Exact source: 4709b9483182c20153868dac164e1f621aac505c.
- Source workspace: installed mmx-workspace operation claude-browser-fleet-client-20260915-sol-001, lane web.
- Preserve Executive lifecycle, Operator Harness resource ownership, SCF exposure and Capacity/Fleet placement.
- Preserve B1 isolation and its authenticated-browser prohibition.
- No raw credentials, cookie export, existing browser attachment, provider execution, global Claude configuration edits, production installation or PR #473/#633 effect changes.
- Client configuration is not launch attestation, isolation proof, permission enforcement, authentication or admission.

## R1 deliverable

Files: `control_plane/claude_mcp_client_projection.py` and `tests/test_claude_mcp_client_projection.py`.

Interface: `project_claude_mcp_client(profile: ExecutionCapabilityProfile, *, surface: str) -> ClaudeMcpClientProjection`. Accepted surfaces: `cli`, `agent-sdk`, `desktop-local`, `inline-subagent`. The immutable return supplies `configuration()`, `cli_arguments()`, exact enabled/auto-approved tool names, and source profile/grant/schema digests. Return configurations are independent copies.

1. Add executable tests for exact stdio/HTTP translation, current B1 bootstrap preservation, no ambient extension inheritance in CLI arguments, precise non-wildcard tool names, refusal of unsupported transports/surfaces, Desktop HTTP refusal, disabled profile refusal, duplicate/ambiguous names, invalid approval semantics, helper-disabled refusal and immutable projection copies.
2. Run `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_claude_mcp_client_projection.py --tb=short`. The first test must fail because the projection does not exist.
3. Implement the pure serializer. Reuse grant values; do not invent an executable, URL, environment, token or resource identity. Fail closed rather than dropping a required server. Desktop cannot directly use an HTTP entry through local stdio configuration.
4. Run the new test and `tests/test_executive_agent_capabilities.py`; verify the existing policy and sealed worker remain untouched.
5. Use the already-pinned official MCP in a development-only local fixture to verify independent browser connections and synthetic session persistence. Do not label this a Claude-account or production acceptance.
6. Commit scoped source/test/research only and open a draft. Independent review, provider-specific attestation and live enrollment remain release prerequisites.

## Parent program remains open

R2 owns actual admitted Claude adapter/resource composition; R3 owns authenticated browser profiles through the credential owner; R4 owns Fleet placement and multi-host rollout; R5 owns Desktop/remote connector enrollment; R6 is concurrent real-account, child, restart and revocation acceptance. R1 does not silently authorize or complete any of them.


## Native-client permission repair and replay amendment

Continuation procedure: protected Mastermind `f590c068880dbb848bda90b80b73dbcb6688d6fc`, compatible Skillpack 1.0.1 with the enrolled WEB_CEO_DELEGATION companion. Same operation, branch and owned workspace; no native-provider/PF1 source custody is acquired. Direct investigation was retained for PRINCIPAL_JUDGMENT: native tool inheritance was an unresolved authority-sensitive interface, not a frozen routine implementation.

The provider-execution prohibition above means no real provider inference, real-account authentication, enrollment, quota use or production activation. The opt-in native test consumer uses an installed Claude CLI, actual isolated Chrome, and a deterministic loopback model-protocol fixture with an obvious fake key. It is not a WorkerExecutionAdapter, Executive admission route, daemon or authenticated account test.

### Discovered incompatibility and implementation

An inline child declaring six permitted browser tools still executed an omitted seventh when the parent auto-approved it. The historical `native-child-ceiling-r1.json` receipt records that failed permission expectation and the synthetic form submission. Explicit child disallowedTools refused the same action. The unsafe configuration is retained as immutable failure evidence, not a supported runnable path in the repaired fixture.

`project_claude_mcp_client(profile, *, surface, observed_tool_catalogs=None)` now consumes complete owner-supplied tools/list responses. It requires that observation for inline children, refuses missing/extra server identities, pagination, duplicate names, absent granted tools and allowed-schema drift, and reuses `observed_mcp_tool_schema_digest` rather than defining a second attestation format. It records full-catalog digests and generates exact denied names for every observed tool outside the grant. CLI and SDK also emit these denies when the catalog is supplied. SDK always preserves strict_mcp_config=True. No wildcard permission or bypass mode is emitted.

Catalog-derived deny configuration is defense in depth, not a replacement for the existing server-side browser guard, admission, destination restrictions or exact requested/observed runtime attestation. A changed or incomplete catalog must be rejected/reconciled before use; caller-provided config alone is not authority. Desktop stdio configuration cannot express per-tool enforcement and remains dependent on its guarded local bridge; no Desktop installation or proof is claimed.

### Replayable source/evidence envelope

- Existing four R1 paths remain owned.
- `tests/claude_browser_native_conformance.py` is an opt-in native transport fixture; importing it does not launch a client.
- `tests/test_claude_browser_native_conformance.py` tests the deterministic oracle, exact result binding and configuration consumer.
- `research/evidence/claude_browser_mcp_tools_0_0_79.json` is an exact tools/list capture from the pinned Apache-2.0 Microsoft Playwright MCP runtime, not a credential or a production readiness record. Top-level output provenance is preserved in the accompanying evidence summary.
- `research/evidence/claude_browser_client_native_2026-09-16.json` records sanitized successful/control receipts, source hashes, the historical failing witness and explicit proof limitations.

Install only the existing locked test dependency in a private test runtime with `npm ci --ignore-scripts --no-audit --no-fund`; do not install a global service or use @latest. Supply that runtime path explicitly. The SDK case separately requires test-local claude-agent-sdk 0.2.153 under the runtime parent's sdk-libs directory. No caller should substitute a real subscription credential for the fixture's fake local key.

Run ordinary tests:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -o addopts='' -q -p no:cacheprovider tests/test_claude_mcp_client_projection.py tests/test_claude_browser_native_conformance.py tests/test_executive_agent_capabilities.py --tb=short
```

For each of direct, scoped-child, sdk, denied and child-generated-deny, run the opt-in fixture with `--run --binary` naming the exact installed Claude executable, `--runtime` naming the private pinned runtime, `--case` naming the case, and a new absolute `--evidence` filename. `--catalog` can supply a newly captured complete tools/list response; the default is the checked-in exact capture. Using the checked-in capture is replay against that snapshot, not a fresh production-catalog observation. The real MCP connection and browser still run; actual returned tool sets/results are recorded.

Native acceptance requires exact final source/projection identities; permitted flows expose only the seven granted tools and return an actual snapshot/image; denied flows submit no form; broader parent permission cannot lift the generated child deny; native result is non-error and nonce-bound; the original parent consumes child results; owned process-group absence is observed. No real-account, fleet, browser-egress-firewall, full UID sweep or provider-surface single-fill acceptance follows.

Publication is Draft/HOLD followed by independent exact-head review and current-base checks. The native Anthropic worker/PF1, credential owners #634/#663, Fleet #644, and held #473/#633 effects retain their owners. Real-account and Desktop integration are downstream capabilities, not excuses to weaken this source's boundaries.

## Hosted-gate repair — September 16, 2026

The first full hosted run (35058060537, job 104672301403) completed with one failure: D8 tokenized every non-test added line as Python and treated the report's HTTP status and synthetic character counts as service-account identities. The exact failure was reproduced on the same source workspace.

The envelope adds `tests/test_ceo_submit_armed_composition.py` as a ninth path. Its original literal scanner, real topology defaults and positive identity-change controls remain intact. File-role classification excludes only Markdown under docs/research and JSON in the established non-runtime research/evidence subtree; executable code in those directories and other configuration paths remain guarded. The gate consumes per-file Git diffs instead of merging documentation and executable source into one token stream.

Fourteen new classifier cases first failed. Eight real temporary-Git-repository cases verify documentation/evidence acceptance and source/config/script rejection through the actual D8 test. The full owning suite plus the existing three browser/capability suites passed 129 tests. No test is skipped, baselined, disabled or removed by this repair.

Projector and native-fixture SHA-256 values still match the five completed native browser proofs. This repair does not rerun those provider-free proofs or claim new account, browser-resource, Desktop, credential or fleet activation. Publish on the same PR/branch, require fresh hosted CI and independent review of this guard change, and retain all production gates.

## R3 — server-bound catalog identity (September 16)

Author review after the R2 full hosted test succeeded found a metadata collision: sorting bare full-catalog digests loses the association to the MCP server. Two servers with identical granted schemas but different ungranted schemas could exchange catalogs without changing the stored digest tuple or any generated permissions. The new twin-server regression reproduced that exact failure before repair.

Keep the existing `source_tool_catalog_digests` field, but its unshipped internal shape is now an immutable, server-name-sorted tuple of `(config_name, schema_digest)` pairs. The same owner-supplied catalogs and existing schema-digest function are used. No new catalog store, authority, tool grant, client config, launch flag, runtime guard or credential path is added. Consumers of this candidate metadata must use the paired shape; the metadata remains observation, not admission.

Five additional cases cover a swapped-catalog witness, exact name/digest pairing on CLI/SDK/inline-child surfaces, and order invariance. The four owning/browser/capability files pass 134 tests. Restoring the old bare-digest behavior in an isolated interpreter fails four new checks while the reorder control still passes; source files are not mutated by the fault injection.

The two-line production-module change affects only returned catalog metadata. Preserve earlier native browser receipts at their original hashes; do not claim they were rerun on this new revision. The native fixture file and generated client configurations are unchanged; fresh exact-head independent review and hosted CI remain required before release.

Current procedure pin: `a78b8fe23d8e1ed129880ac47e97ebe96afa8aea`, Skillpack 1.0.1. Direct execution reason: PRINCIPAL_JUDGMENT / CRITICAL_PATH_SHORTCUT for a reproduced permission-attestation defect in this incumbent source lane; independent reviewer placement remains unconfirmed. No account or service activation is authorized by this amendment.

## R4 — close independent review's evidence-JSON identity hole

Independent exact-head review by `mastermindx-3` on R3 (`PRR_kwDOTotz3c8AAAABNyj39w`) returned CHANGES_REQUESTED. Its two-file witness puts `peer_uid` in research/evidence JSON and a loader in control_plane. The real Git-diff gate accepted that combination. Eight hostile variants were first reproduced RED; the benign metric control passed.

Keep R3 client/permission/runtime code unchanged. Replace the blanket evidence-JSON exemption with a structural literal check over the complete committed postimage. Reuse the existing numeric identity range and reserved principal-name convention. Scan UID/GID/peer/account/principal/user/group/owner/identity fields and their nested values, including string-encoded identities and camel-case keys. Benign HTTP status, character counts, byte counts and hashes stay valid. Duplicate members, malformed/non-finite JSON, primitive roots, excessive depth/nodes and oversized documents refuse rather than silently evade inspection. Deleted records introduce no identities. Markdown remains prose; every other executable/config path retains the original added-token scanner and topology controls.

This remains a static identity-literal guard, not arbitrary-program dataflow analysis, a runtime parser, an account-admission mechanism or a general ban on reading evidence. Runtime identity/authentication owners are unchanged. Historical evidence values are not rewritten. All new writes are limited to this owning test file and the existing plan.

Evidence: real Git repositories containing both JSON and a source consumer; eight hostile cases RED -> GREEN; additional scalar/non-finite controls RED -> GREEN; complete four-file campaign 156 PASS. Run isolated fault injections and verify source hashes before publication. The projector and native fixture must remain byte-identical to R3; native browser replay is not owed for this test-only repair. Preserve original proof epochs and source limits.

Release still needs a new immutable head, current-base integration, full hosted/security checks and independent non-author re-review. Use the existing GitHub reviewer/PR return; reconcile the still-unassigned placement request to prevent a duplicate review. No reviewer delivery is native START, and no source review permits deployment or credential/account effects.

R4 hostile validation: the first in-memory driver amended `tests.test_ceo_submit_armed_composition`, but pytest collected the distinct module `test_ceo_submit_armed_composition`. Its mutant GREEN was discarded as a driver failure, not claimed as guard evidence. A collection hook now modifies the exact collected module and records both names/object inequality. Correct baseline: 22 PASS. Four real fault removals were detected: disconnect JSON dispatch (8 failures), remove nested identity context (12), permit duplicate-key shadowing (1), and permit non-finite metrics (1). Source files remained unchanged by fault injection. Canonical local receipt: `pr684-r4-mutation-proof.json`, SHA256 `e5b2671303d153cfe96c58bdaad1248b49a896563459c1efd17c95d6b5bc52ec` in the same operation's agent-evidence directory.

The still-unassigned Secretary placement request was sent an explicit terminal STOP at `C0BSBM78V1N/1789546835.419979`, reply `1789550790.560659`, after the GitHub independent review was verified. This stops duplicate placement only; counterpart consumption is not yet proven, and it does not close the source/program or transfer an actual reviewer RuntimeBinding. Re-review belongs on PR #684 with its existing non-author reviewer.

## R5 — exact normalization of identity-bearing evidence strings

Independent review 5221059060 by `mastermindx-3` on `f3f99a243abe4ad13190d4a6f4c756e939659d7f` accepted the R4 boundary improvement but reproduced three remaining normalization bypasses: scientific notation, decimal-form integers and leading whitespace before reserved principals. Continue the same source writer/branch. Direct repair reason: CRITICAL_PATH_SHORTCUT; the small review-bounded change does not justify another builder or source-custody transfer. Keep independent review with the existing reviewer.

The three real committed-JSON-plus-loader reproductions are preserved. Along with encoding, exactness and bounds controls, the initial 25-case campaign produced 13 failures and 12 passes. After repair all 25 passed. The initially slow test completed normally; the exact-PID check confirmed absence before any termination signal, so no cancellation or duplicate run occurred.

Normalize only identity-bearing strings: strip outer whitespace, enforce a bounded length before numeric conversion, retain `int(..., 0)` for integral/base-prefixed forms, and otherwise construct exact finite Decimal values. Check the existing guarded range and exact integrality before converting a Decimal to int. Never round through binary float or the ambient Decimal context. Preserve nested field classification, JSON/document bounds and all benign metric controls. This remains a static literal check, not general source dataflow or runtime account admission.

The reviewer requested three regressions; the 25-case addition also covers all range boundaries, legacy encodings, Unicode decimal digits, exponent extremes, long identity values, exact near-integer fractions and an adverse Decimal context. A separate deterministic domain probe checked every one of the 600 protected integers under ten encodings (6000 checks), plus six negative controls. That probe is supplemental, not 6000 additional pytest tests or production proof. Receipt: `pr684-r5-normalization-domain.json`, SHA256 `6e928d4278037b118cfbb8f679755d6f7c55fcf8711a6b6c8b9dbb0db05c9fd2` in the same operation evidence root.

Only this existing plan and the owning guard test change in R5. Browser projector, native fixture, catalog capture and runtime/credential/configuration sources must remain byte-identical. Complete the full four-file suite, exact-collected-module fault tests, immutable current-base integration and hosted checks; publish one fast-forward repair and request exact-head re-review. Do not replay historical native browser proofs or create another review-placement request. No Ready/merge/install/provider/account effect is inferred from author test results.

R5 full-suite outcome: 181 PASS on the unchanged candidate bytes in one sequential diagnostic run, with private pytest basetemp and verbose/faulthandler reporting. An earlier concurrent full-suite attempt timed out after 300 seconds and was terminated/reconciled; that result remains a timeout, not a pass. The diagnostic stack placed the delay inside the pre-existing D5 nested ingress pytest subprocess. No D5, conftest, runtime or production test was changed or skipped. The subsequent complete run passed in 86.01 seconds. Receipt: `pr684-r5-diagnostic-receipt.json`; owning test SHA256 `7fa69a3d938f4ddc194146caac083b913ad6b91de4437d42317202ca0b5e407d`. The first fault-test attempt likewise timed out after its passing baseline; only the separately recorded sequential fault campaign may supply fault-detection evidence.
