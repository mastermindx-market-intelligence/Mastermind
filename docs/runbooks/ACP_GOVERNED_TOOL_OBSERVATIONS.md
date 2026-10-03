# ACP governed tool observations — experimental, not installed

Issue #1142 extends the existing ACP/native owner, rather than adding a worker,
grant issuer, provider route, scheduler or result store. The default remains
tool-denying. This slice is **BUILT_NOT_PROVEN** and must remain a draft until
the configured real-donor journey passes and independent review accepts it.

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

- 110 focused Python tests and 40 subtests passed, including 24 new native-channel
  and tool-observation tests. Four opt-in N1 tests skipped in that invocation were
  separately executed with their actual pinned supply: **4/4 passed**.
- New configured donor scope/source/schema/model controls: **4/4 passed**. The scope
  control runs two actual Node tests: the unadapted profile refuses; the adapted
  profile executes all four original preflight checks, discovers real MCP tools,
  performs a real read, preserves revocation/cross-agent isolation, and disposes
  registrations and every observed MCP process.
- Actual donor ACP read/search-to-WorkerResult positive journey: **FAILED** at the
  first scheduled tool, after successful private readiness and `session/new`.
  No useful result, real provider call or actual Executive parent consumption is
  claimed. The original owner settled the native process and child transports.

### Two observed dependency constraints

1. The existing profile registers preflight probes in the agent context but omits
   the agent on `tools.execute`. Donor 4878 intentionally resolves that as global.
   `experiments/harness_convergence/dsh_worker/scoped_profile.mjs` is an experimental
   one-use host decorator: it supplies only the exact unpublished agent identity,
   rejects explicit cross-agent dispatch, and retains normal plugin ownership and
   every existing preflight check. It neither mounts globally nor changes #1060.
2. The published compiled #1060 test artifact bundles a private
   `Symbol('@deepseek-ai/dsh-tools.scheduler')`, while donor AgentLoop imports a
   distinct symbol from its own tools module. The first scheduled call fails with
   `Cannot read properties of undefined (reading 'prepare')`. Its three exports
   provide no public interop contract. The incumbent #1060/package owner must
   publish a pinned compatible closure sharing one tools module with the selected
   AgentLoop. Do not reflect private symbols, copy scheduler methods, monkeypatch
   globals or reinterpret standalone profile tests as the full worker journey.

The failing positive test remains an assertion, not an xfail/skip. CI without the
external supply explicitly skips native qualification and cannot clear this gate.

## Exact optional test supply

No dependency, credential or generated state is committed. Supply construction
and use occur outside the assigned source workspace, under an explicitly verified
dependency directory; this is not another Mastermind source checkout.

| Input | Exact identity |
|---|---|
| Donor | `4878cdabd87d4041bdaff61d04c966883b9fd07a` |
| #1060 source provenance | `92e71a4c1bb0d1b0a45cf6b691fce3ea62695567` |
| Published profile artifact SHA256 | `c98434fbb1c175dbe3ee96daf95a0c88d41518f735c5458a6eb6d93479be5cc4` |
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

After the incumbent publishes a composable closure, intentionally review/update
its pinned identity and rebuild. Require the entire suite: useful actual read and
search, failed MCP result, revocation, source/schema/model drift, invalid result,
cancellation and cleanup. Then prove real Executive admission, confinement and
original parent consumption through existing result interfaces. Provider canary
remains conditional on current provider/Capacity authority. Do not redo #825's
accepted semantics or acquire #1060's held source carrier to solve this dependency.
