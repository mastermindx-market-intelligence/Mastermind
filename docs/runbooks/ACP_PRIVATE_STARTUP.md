# ACP native private startup

Operation: `deepseek-harness-acp-production-integration-20261002-astra-001`,
carrier Mastermind #1142. This is a prerequisite source slice, not a useful DSH
worker or a production installation.

## Existing owner and opt-in contract

`AcpNativeProcessOwner` remains the only native process/cancellation owner.
An installation's trusted factory may construct an `AcpNativeProfile` with
`private_startup=True` and an explicit `allowed_environment_keys` tuple.
Neither setting comes from `WorkerLaunchSpec`, ACP wire data, or model output.
The tuple is a **ceiling**: an empty tuple or a subset of its keys is valid.
`HOME` and `TMPDIR` are reserved to the native owner. Other keys and their
values still require review by the installation owner; an allowlisted key is
not a provider, tool, or credential grant.

Before opening captures or spawning, the owner checks the loader environment,
adds its own HOME/TMPDIR and checks the existing final environment limits. It
then exclusively creates mode-0700 `run_dir/startup`, `startup/home`, and
`startup/tmp`. An existing directory or symlink is refused. The child starts
in `startup`; the repository remains the ACP session's workspace. No ambient
environment is merged. Legacy profiles keep their existing startup behavior.

The existing launch attestation adds `private_startup` with directory paths,
device/inode/principal/mode observations and the loader-key ceiling. It records
environment key names, never values. These are launch configuration facts,
not a DSH effective Agent/tool roster attestation. An interpreter or OS may
add its own runtime environment keys after exec; the macOS framework Python
probe observes `__CF_USER_TEXT_ENCODING` separately from the submitted keys.

## Failure and cleanup

Environment and stale-directory refusals occur before native spawn. If capture
creation or spawn fails, successfully opened capture descriptors close. If a
process was started, the existing owner performs its existing settlement path.
The existing adapter quarantines an open failure; it does not infer no effect
or authorize a retry.

Failed-run directories and capture files are retained as reconciliation
evidence. They are not silently deleted to make the same run launchable again.
A second open of that startup directory refuses. Successful settlement reaps
the process and capture tasks, while retaining the run's artifacts normally.

## Acceptance evidence and limits

`tests/test_acp_native_startup.py` executes a harmless real Python child. It
checks actual cwd/HOME/TMPDIR/PATH, exclusion of ambient variables, absence of
workspace/home `.env` files at the child's startup locations, private directory
identity, secret-value exclusion from attestation, and original-process
settlement. Negative cases cover reserved/unadmitted environment keys,
malformed profiles, final environment overflow, existing/symlinked startup,
and stderr/result/spawn failures with descriptor cleanup and retry refusal.

Focused qualification on mini4: **32 passed**, comprising 21 startup cases,
7 existing broker cases, and 4 actual pinned DSH ACP cases. No provider calls
or installed runtime changes are involved. The existing #825 files remain
byte-identical to their independently reviewed semantic head.

This is **startup configuration isolation, not an OS sandbox**. It does not
prevent a deliberately malicious same-principal process from reading other
paths, writing, making network calls, or loading repository configuration
explicitly after session creation. DSH-specific effective configuration,
governed MCP dispatch, confinement, provider admission, and actual original
parent consumption remain separate acceptance gates. The attestation therefore
states `os_sandbox_proven: false`.

## Predecessor qualification on the recovered host

The #825 predecessor at integrated commit
`cd60bd0c13cadc023f3f0707c9073ce22ab5487f` passed 69 tests plus 40 subtests on
mini4; the real Python ACP SDK conformance script passed 13 cases. This was a
new-host supply qualification after the historical temporary cache was lost.

The reconstructed supply is `/tmp/mmx1142-dsh-supply`, outside source. Inputs:

- DSH `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`, archive SHA-256
  `61ea8b495bec3f1debcfd58b95350edb2d48548493e0af4111244399dc29dd22`;
- unchanged upstream lock SHA-256
  `ca131858949bd12b2acfc227b1af7dfa3c8d65e74b234824d5c741e6421010a1`;
- official portable Node 22.22.0 darwin-arm64 binary SHA-256
  `913b144fdb40638b1acef7974ab3c33fbd527cc0974cb5da467ab1e6ac51b4d4`;
- unchanged fixture source SHA-256
  `38584b0b13ff97458922505bfe7ea6fde15cea0c2fe476b7319fdcfe8f24e2b6`;
- rebuilt bundle SHA-256
  `d04dfaa356aae23d29cd298dadc51a7a3a588f3b7a2aa6cf42a3bf6489470985`.

The ten fixture workspace roots were installed with pinned pnpm 11.7.0,
`--prod --frozen-lockfile --ignore-scripts` and dependency filters. No lifecycle
scripts or provider calls ran. Pinned TypeScript 6.0.3 built the direct package
projects with `tsc -b`, preserving each vendor's own declaration boundary; a
separate strict fixture config resolved those declarations. Both checks passed.
Flattening all vendor source under the fixture's strict config had failed and
was corrected without weakening fixture checking or modifying upstream source.

esbuild 0.28.1 bundled the fixture with upstream source aliases, Node target22,
ESM format, and a `createRequire(import.meta.url)` compatibility banner. The
unmodified `packages/llm/llm/package.json` is supplied at the bundle's expected
`../package.json` path (SHA-256
`d569e58e8fe7117ab278a0a1b9696fa5469f5143a9b87d547d5afb1d9181a288`).
Earlier attempts exposed the nonportable Homebrew Node dylib dependency and
the bundle's metadata/CommonJS requirements. The new hashes deliberately do
not claim reproduction of #825's historical binary or bundle.

## Remaining composition boundary

Ordinary donor ACP `mcpServers` declarations mount a plain `McpClient`; passing
them alone would bypass #1060's granted-profile wrapper. A future useful wave
must compose that existing source-owned wrapper through a trusted host-only
donor mount seam and verify its actual admitted discovery generation before
prompt. #825 and #1060 use different donor closures; select and qualify one
complete closure before joint execution. This slice neither copies #1060's
held source nor claims that an in-memory fixture tool proves useful research.
