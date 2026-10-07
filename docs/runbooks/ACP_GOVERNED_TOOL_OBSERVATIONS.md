# ACP governed tool observations — experimental, not installed

Issue #1142 extends the existing ACP/native owner, rather than adding a worker,
grant issuer, provider route, scheduler or result store. The default remains
tool-denying. This slice is **BUILT_NOT_PROVEN** for installed use. The configured
real-donor journey passes; independent review and normal source-release gates
remain required.

## Boundary

Trusted construction may give `AcpNativeProcessOwner` an `AcpNativeToolGate`.
Neither a Job nor ACP/model output can configure the gate. The owner checks a
fixed artifact closure, supplies one inherited socket, and binds its seed to the
original process generation, Job/run/worker, source base, projection digest and
admitted tool-contract digests. The bootstrap must remove the environment hint
and prevent descriptor inheritance before starting descendants. After actual
grant discovery it returns the exact seed with readiness; owner ACK precedes
session publication. Standard ACP session/model negotiation and the single-use
owner receipt must then complete before prompt.

This is a same-principal, fixed-artifact composition check, **not hostile-writer
or OS confinement**. Python does not independently inspect the child's grant
registry. The reviewed bootstrap asserts post-discovery contract equality;
the incumbent profile enforces live dispatch and revocation. A private startup
directory inode does not attest the effective child. Installed artifact ownership,
credential/provider admission, OS/process isolation and live Executive binding
remain separate prerequisites.

The turn accepts only bounded, ordered start/terminal observations for admitted
tool names. Unadmitted names, extra fields, duplicate/orphan/missing completions,
late callbacks, wrong sessions, model drift and malformed content fail closed.
The SDK observer detects transport-order terminals; queued callbacks must settle
before success. The ordinary immutable `WorkerResult.usage.acp_tool_observation`
carries owner provenance, tool-contract digests and observation counts/hash. These
are not provider token or monetary usage. Parent/result validation stays unchanged.

## Current evidence (2026-10-03)

- 72 focused ACP tests passed, including 24 native-channel/tool-observation tests
  and all four actual pinned N1 cases. The worker-contract and ACP probe suites
  additionally passed 63 tests and 40 subtests; these are disjoint test files.
- Configured donor journey and adverse controls: **11/11 passed**. The scope
  control runs two actual Node tests: the unadapted profile refuses; the adapted
  profile executes all four original preflight checks, discovers real MCP tools,
  performs a real read, preserves revocation/cross-agent isolation, and disposes
  registrations and every observed MCP process.
- Actual donor ACP read/search-to-WorkerResult positive journey: **PASSED**. It
  performs exactly one admitted read and search, observes both committed results
  in three scripted model requests, and returns the exact file bytes/hash/nonce
  and two search matches. The test took 0.624 seconds including fixture setup on
  mini4; this is not a provider or installed-worker latency measurement.
- The native result now satisfies the existing non-orchestration
  `worker_result_schema(...)`, with job/run/worker IDs from the private owner seed.
  Actual read/search data lives in its permitted summary. Wrong identity, invalid
  status and malformed summary refuse as INVALID_RESULT; failed/revoked tools
  preserve their errors in a FAILED envelope. No second result contract is added.
- Every case checks original process/child absence and unchanged inputs. No real
  provider call or actual Executive parent consumption is claimed. Scripted usage
  tokens are fixture values, not measured provider usage/cost.

### Two observed dependency constraints

1. The existing profile registers preflight probes in the agent context but omits
   the agent on `tools.execute`. Donor 4878 intentionally resolves that as global.
   `experiments/harness_convergence/dsh_worker/scoped_profile.mjs` is an experimental
   one-use host decorator: it supplies only the exact unpublished agent identity,
   rejects explicit cross-agent dispatch, and retains normal plugin ownership and
   every existing preflight check. It neither mounts globally nor changes #1060.
2. The former compiled #1060 test artifact bundled a private
   `Symbol('@deepseek-ai/dsh-tools.scheduler')`, while donor AgentLoop imports a
   distinct symbol from its own tools module. The first scheduled call fails with
   `Cannot read properties of undefined (reading 'prepare')`. The incumbent's
   published `4159c403` repair exports AgentLoop, ToolRuntime and the grant profile
   from one artifact. This fixture imports all three from that module, and the
   unchanged read/search assertions now pass. The prior RED evidence is preserved.
   Do not reflect private symbols, copy scheduler methods, monkeypatch globals or
   substitute standalone profile tests for the full worker journey.

The positive remains an assertion, not an xfail/skip. CI without the external supply
explicitly skips native qualification and does not establish this proof.

## Remaining Executive boundary

Canonical envelope compatibility is not supervisor or original-parent consumption.
ACP currently emits `mastermind.acp_native_launch/v1`; complete Executive launch
attestation, dedicated worker identity, the final UID-sweep receipt and installed
ACP adapter registration are not provided by this source slice. Do not fabricate
a passing secret-canary, sweep receipt or adapter registration, or invoke a full
supervisor process controller against the same-UID fixture. No such run occurred.
Existing supervisor fake-worker tests do not prove composition with this ACP owner.
The installed readonly Executive reader is reachable again; that alone does not
admit an ACP route or install this source.

## Exact optional test supply

No dependency, credential or generated state is committed. Supply construction
and use occur outside the assigned source workspace, under an explicitly verified
dependency directory; this is not another Mastermind source checkout.

| Input | Exact identity |
|---|---|
| Donor | `4878cdabd87d4041bdaff61d04c966883b9fd07a` |
| #1060 source provenance | `4159c403cf63bac8bd18138fa232911589afe06f` |
| Published profile artifact SHA256 | `c77814901495ebb3131d28b4968bd3f1cce3f39233e1c0cb580de5a7b9f9106c` |
| Bundled AgentLoop | `0.2.0-rc.1`, bytes/lock identity in the published `agent-loop-manifest.json` |
| Contributor R4 patch SHA256 | `243ec445db513db3bb9ff0cad05bc70550df972a785b8af1546d89c055cadc1f` |
| Node 22.22.0 SHA256 | `913b144fdb40638b1acef7974ab3c33fbd527cc0974cb5da467ab1e6ac51b4d4` |
| ACP Python SDK | `0.12.1` |

The supplied directory contains the exact donor under `donor/`, corrected R4
patch, unmodified `profile1060.mjs`, published MCP fixture server, frozen lockfiles
and dependencies, synthetic fixture input/config, and a synthetic projection made
by the existing canonical projection helper. This projection is test-only and
`production_armed:false`; it is not Executive admission. Preserve the 4878
`updates.ts` result-message converter. Install with frozen lockfiles and lifecycle
scripts disabled; the #1060 fixture lock requires its legacy peer resolution.
Type-check the donor ACP, agent-loop and session-projection declaration projects.

Reconstruct the profile with the published `prepare.py`, `prepare_mcp.py` and
`build-profile.mjs`. Use the exact lock with a physical `node_modules` directory
at the dispatch-binding package: a symlinked dependency directory changes Vite's
recorded module-path comments and therefore the artifact hash. All measured source
inputs matched in that rejected build; a clean locked install reproduced the exact
published c778 bytes. Never weaken the artifact pin to accept a layout mismatch.

Build with the supplied Node and esbuild 0.28.1:

```sh
node experiments/harness_convergence/dsh_worker/build_governed_fixture.cjs \
  /absolute/dependency-supply /absolute/tooling/node_modules/esbuild
```

The builder refuses another profile artifact, records bundle/source digests in
the existing `supply-manifest.json`, and installs nothing. Tests verify those
digests, the projection/config/server/input identities, and exact Node bytes.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
MMX_DSH_GOVERNED_ACP_SUPPLY=/absolute/dependency-supply \
python -m pytest --noconftest -p no:cacheprovider -o addopts='' \
  tests/harness_convergence/test_dsh_acp_governed_worker.py
```

Require the entire suite after any pinned supply change: useful actual read/search,
failed MCP result, revocation, source/schema/model drift, invalid result/identity/
status, cancellation and cleanup. Next prove complete Executive launch/cleanup
composition, admitted routing, confinement and original parent consumption through
existing owners. Provider canary remains conditional on current provider/Capacity
authority. Do not redo #825's accepted semantics or acquire #1060's source carrier.
