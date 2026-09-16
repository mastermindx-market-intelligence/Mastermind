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
