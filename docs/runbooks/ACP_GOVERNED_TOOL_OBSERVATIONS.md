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

## Explicit real AgentLoop/WorkerResult acceptance (no silent skip)

The ordinary repository test suite skips `test_dsh_acp_governed_worker.py` when
`MMX_DSH_GOVERNED_ACP_SUPPLY` is absent. **Those skips never qualify the
AgentLoop-to-ACP WorkerResult journey.** The DSH Governed MCP CI job establishes
stdio grant, revocation and cancellation behavior only.

Use the separate fail-closed qualification runner **only after** the external
supply above exists with its frozen donor, profile, patch, manifest, fixture
inputs and exact Node executable:

```sh
python3.12 scripts/qualify_dsh_governed_worker.py \
  --supply /absolute/external/governed-dsh-supply \
  --evidence-dir /absolute/new/private/evidence-directory
```

The evidence directory must not already exist or reside under the source
checkout. The runner verifies all supplied file hashes and the exact
`4878cdab` donor, `4159c403` profile source,
`c7781490` profile binary and `243ec445` R4 patch identities *before*
launch. It runs the actual existing 11 provider-free pytest cases with
auto-loaded plugins and ambient provider credentials absent, and writes
`tests.xml`, captured test output and `qualification.json` outside Git.
Only 11 passed, zero failed/error/skipped and exit code zero produce
`REAL_PROVIDER_FREE_WORKERRESULT_PASS`. Missing/mismatched supply,
timeouts, lost JUnit, skipped cases or conflicting evidence fail closed.
An existing evidence directory is never overwritten.

Even this successful source/fixture receipt is **not** an Executive-host
installation, dedicated UID/Seatbelt/UID-sweep proof, production-routed
Attempt, provider call, authenticated donor UI, or the actual original
company parent consuming a WorkerResult. Those remain separate gates.

## Reproduce the exact real provider-free supply (macOS ARM64)

The complete original fixture is now reproducible from immutable local
inputs, without hand assembling the MCP projection or patching the donor
source checkout. The original provider-free 11-case suite ran successfully
both on the first isolated M2 supply and on a *fresh second* supply produced
by the checked-in preparer. The latter is a source-only test, not an
installed/armed Executive Job.

Prerequisites: a **clean** checkout of upstream `4878cdab` with frozen
pnpm dependencies already present (no implicit install); the authentic R4
patch `243ec445...` from the original contributor evidence; the exact
`c7781490...` compiled #1060 grant-profile artifact; and executable Node
22.22.0 darwin-arm64 `913b144f...` from official distribution. The
preparer validates donor lockfile, checkout state and all frozen artifact
hashes before creating a **new** external output directory. In addition to the
lockfile SHA `081d9f86...`, the installed, Git-ignored pnpm dependency tree
has an independently source-pinned macOS ARM64 content closure SHA256
`bc046d6eee33feed3fa4782ec38761937a875b8230f36a0645d306fd5bed0b86`.
It covers sorted file paths and bytes, executable bits, directories and
symlink destinations (rejecting escapes outside the donor). The original
clean donor and the separately built earlier frozen supply were measured
with the same result. Any changed installed package byte **within this
materialized .pnpm subtree** (including the pinned esbuild, TypeScript,
MCP client and SDK packages) causes rejection **before it is executed**;
the snapshot is checked again after copy, and qualification re-verifies it.
The wider top-level `node_modules/` outside `.pnpm` is *not* attested:
all current execution sites use explicit paths inside the pinned subtree.
Adding another package resolution path requires a revised closure and review.
This binds *this materialized installation* to its source-reviewed fixed
donor/lock profile. It does not independently attest an upstream npm
publisher or establish general portability to another package install.

```sh
python3.12 scripts/prepare_dsh_governed_supply.py \
  --donor /absolute/clean/deepseek-harness-4878 \
  --r4-patch /absolute/authentic/governed-acp-mount.patch \
  --profile /absolute/verified/profile1060.mjs \
  --node /absolute/verified/node-v22.22.0-darwin-arm64/bin/node \
  --output /absolute/new/deepseek-governed-supply
```

It creates an isolated copy-on-write donor snapshot (not another Git writer),
applies the exact reviewed R4 patch, typechecks and compiles the patched ACP
entrypoint, observes the **actual** stdio MCP tools, derives a read/search-only
`production_armed:false` projection through the original typed helper,
and bundles AgentLoop with the pinned grant profile. Before accepting the
projection, the preparer independently binds its exact read_file/search_files
tool identities and full observed tool rows (including annotations,
outputSchema and execution metadata), stdio command/server, synthetic
profile, and approval contract; two arbitrary tools never qualify.
The final
`preparation-receipt.json` has `SUPPLY_PINNED_NOT_YET_TESTED`: building
alone never asserts a successful worker result. No dependency download,
production installation, provider call, or Job/Attempt is performed.

Then use the existing *separate* fail-closed qualification runner with a
second new evidence directory:

```sh
python3.12 scripts/qualify_dsh_governed_worker.py \
  --supply /absolute/new/deepseek-governed-supply \
  --evidence-dir /absolute/new/deepseek-governed-supply/qualification-r1
```

Only `REAL_PROVIDER_FREE_WORKERRESULT_PASS` with **11 executed passes,
zero failures/errors/skips**, a JUnit receipt and all immutable hashes
verified qualifies this source-only WorkerResult experiment. The independently
source-anchored identities are the donor revision, lockfile, installed pnpm
content closure, grant-profile source and binary, R4 patch, frozen fixture
source files and Node executable. Other `files` and `fixture_input`
hashes in the fresh private manifest are self-attested consistency checks,
not a separate external provenance authority. An absent
input, donor drift, changed compiled profile, old/wrong Node, malicious
mount patch, accidental skipped test or replay of an evidence destination
must refuse. Neither success promotes `acp.implemented` or grants real
provider, original Executive parent, company credentials, runtime UID/
Seatbelt installation, browser login or production deployment authority.
