# Executive Capacity CF2-H0 host preparation implementation plan

> **Carrier:** `sol/executive-capacity-cf2h0-host-preparation-20260825`
> **Base:** `205640da8e4e21c02960d4f409cd1d24bb485ce5`
> **Stop state:** reviewed, merged and installed credential-free H0 foundation; exactly three inert
> broker definitions installed but disabled and unloaded; socket nodes absent; no credentials,
> provider execution, routing, CF2-I implementation or P0 acceptance

## Observable mission

Turn the read-only CF2-P0 result `NO_SAFE_CF1_ACQUISITION_PATH` into one installable, fail-closed
host foundation without claiming that the independent P0 gate has passed. The installed Mac must
have:

1. the exact accepted Macro CF1 Git objects and material files in a root-owned, remote-free,
   detached checkout with direct `.git` metadata;
2. a root-owned, pip-free Python/PyYAML runtime with the exact pinned wheel, complete `RECORD`
   validation and a deterministic closed-tree digest;
3. the existing three dedicated Personal Pro users, groups and private empty provider homes;
4. exactly three realm-specific worker configs, Codex attestation receipts and launchd plists using
   the existing Phase 1C broker family; and
5. durable source, topology, rollback and installed-host receipts.

All three new labels remain persistently disabled and unloaded and all three socket nodes remain
absent. This wave does not authenticate a provider, read or write a credential, perform OAuth,
compose a worker with the control runtime, execute a worker/provider call, route a job, implement
CF2-I or emit a CF2-P0 acceptance object.

## Authority and source-law boundary

- Accepted CF2-F source law remains the architecture authority for the one-producer Capacity Fabric
  and the independent P0 gate.
- Accepted Macro CF1 remains the only provider-capacity normalizer and semantic-hash producer.
- The read-only P0 census remains the current installed-host fact until it is rerun after H0.
- H0 may prepare only the source/runtime/config/topology substrate required for a later independent
  P0 decision. Its success outcome is exactly `H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED`.
- `GROUNDED_CF1_GIT_RELEASE_PATH_ACCEPTED` may be emitted only by the subsequent independent P0
  census. H0 must never manufacture, embed or imply that acceptance.

## Existing surfaces to extend

- Reuse `ops/executive_os/bootstrap-host.sh` and `provider_worker_slots.py` for service identities,
  UID/GID allocation, exact group membership, private provider homes and realm paths.
- Reuse the installed PSF Python 3.12.10 attestation from
  `provision-python-runtime.sh`; do not replace or duplicate the base runtime.
- Reuse `com.mastermind.executive.worker.codex.plist.template` and the existing Phase 1C worker
  entrypoint. H0 renders realm-specific definitions; it adds no second broker family.
- Install only source/runtime/config/topology preparation surfaces and immutable receipts. Do not
  add another queue, lifecycle, credential store, provider normalizer, router or control plane.

## Frozen identities

- Macro repository: `mastermindx-market-intelligence/macro`
- Macro commit: `dcdd939c45b23abce5ba04f95e330ac914a3904b`
- Entry point: `scripts/build_provider_capacity.py`
- Material inventory: the exact eleven paths frozen in `prepare-capacity-host.sh`
- Operator transport: `mastermind.capacity_source_transport/v1`, one ZIP containing only
  `manifest.json` and a narrow Git `payload.pack`
- Base Python: `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12`
- PyYAML: `6.0.3`, macOS 11 arm64 CPython 3.12 wheel SHA-256
  `fc09d0aa354569bc501d4e787133afc08552722d3ab34836a80547331bb5d4a0`
- Personal Pro realms: exactly `codex-pro-01`, `codex-pro-02`, `codex-pro-03`, in the existing
  catalog order, owned only by `_mastermind_codex_01/02/03`
- Worker labels: exactly `com.mastermind.executive.worker.codex-pro-01/02/03`
- Worker sockets: exactly `/var/run/mastermind-executive/worker-codex-pro-01/02/03.sock`
- Worker socket owner/group/mode: `_mastermind_exec` UID/GID `450:450`, mode `0600`

## Implementation sequence

### 1. Close the source/runtime contracts

`capacity_source_contract.py` must define exact source, executable, entrypoint, working-directory,
inventory and telemetry identities. Its host receipt must bind the exact preparer commit, three
broker topology, shrink-only rollback contract and completed rollback-drill receipt while declaring
credentials, worker execution and CF2-I held.

`capacity_host_artifacts.py` must provide the only operator-to-root Macro source handoff:

- an already-authenticated operator supplies a local repository containing the exact accepted Macro
  commit;
- the helper reads immutable Git objects at that commit and creates one data-only custom transport;
- the transport contains only a closed manifest and narrow Git pack, never a recursive worktree
  copy, Git config, hook, index, ignored file, credential helper or credential material;
- the operator records the completed transport's SHA-256 and root requires that independent digest
  as `--macro-transport-sha256` before parsing or materializing it;
- root validates the archive inventory and hashes, creates a fresh direct repository, detaches the
  exact commit, removes every remote and verifies every material Git blob and file digest; and
- no privileged step performs an anonymous HTTPS fetch.

The runtime is created with `venv --copies --without-pip`. The pinned wheel is extracted without
pip, links, archive-controlled modes or undeclared files. Complete `RECORD` hashes and sizes, the
absence of `.pth`/site customization and the full hardened runtime-tree digest are required before
installation.

### 2. Install the closed inert host topology

`prepare-capacity-host.sh` runs as root only from a clean, direct, root-owned checkout at the exact
merged protected Mastermind commit supplied as `--expected-mastermind-sha`. It must reverify the
base Python receipt, every transport/wheel/source/runtime identity and the exact protected source
tree before mutation. The disposable checkout must sit beneath a root-owned, non-writable parent;
the checkout, executed helpers and template inputs must contain no ACL, unapproved extended
attribute, executable symlink, hard-linked file or group/other write path. The only tolerated xattr
name is macOS's system-maintained `com.apple.provenance`; it is not caller-controlled and is not
included in content identity. Every other xattr fails closed.

After the staged source/runtime candidates pass, the existing bootstrap surface establishes or
revalidates the three dedicated principals and empty `0700` provider homes. `_mastermind_exec` must
remain outside all three Personal Pro groups and fail the required traversal probes. Existing
Phase 1C files and stopped service state are bound by a pre-install digest and remain unchanged.

A root-only process lock excludes overlapping H0 writers. If a prior H0 process was interrupted,
the same carrier may recover only direct, root-owned, mode-safe partial topology targets and its
own hidden staging/candidate directories while every H0 label is disabled/unloaded and every socket
node is absent. Recovery intent and receipt publication use resumable same-directory candidates,
file and directory durability barriers and atomic renames; every source-to-archive move fsyncs both
parents. Recovery is archive-only, emits `INTERRUPTED_H0_PARTIAL_RECOVERED`, and then resumes;
it must never overwrite ambiguity or reinterpret an accepted generation.

The topology renderer creates exactly three of each:

- `worker-codex-pro-01/02/03.json` broker configs;
- `codex-attestation-0.147.0-codex-pro-01/02/03.json` attestation receipts; and
- `com.mastermind.executive.worker.codex-pro-01/02/03.plist` launchd definitions.

The plists retain `RunAtLoad`/`KeepAlive` from the existing template, so H0 must first persistently
disable and boot out each new label and must prove the label is disabled and unloaded before and
after every installation step. Merely installing a plist never grants start authority. The three
declared socket nodes must remain absent.

### 3. Prove real shrink-only rollback and reinstall

After the first exact topology installation, the preparer must perform—not merely describe—the
rollback drill:

1. move all nine new config/attestation/plist artifacts into a new root-only rollback archive;
2. prove all three labels are still disabled and unloaded and all three socket nodes are absent;
3. retain service principals, private homes, credentials, immutable releases, grounded Macro
   source, capacity runtime, read-only telemetry boundary and all legacy Phase 1C artifacts;
4. emit a canonical `SHRINK_ONLY_ROLLBACK_PASS` receipt binding the topology and rollback-contract
   digests; and
5. reinstall and reverify the same nine inert artifacts.

Rollback grants neither deletion authority nor service-start authority. Failure cleanup is also
archive-only and fail-closed; it does not recursively delete ambiguous host state.

### 4. Commit the receipt generation last

The immutable H0 generation contains exactly the component manifest, source config,
installed-host receipt, broker topology, rollback contract and rollback-drill receipt. The copied
drill receipt must validate against its root-only original and the nine archived artifact hashes.
Every source/runtime/release,
telemetry, topology, legacy-file and stopped-service invariant is rechecked before the generation
is made canonical. The final generation rename is the last filesystem mutation.

`--verify-only` validates the installed generation, exact source/runtime/release/topology, immutable
empty telemetry boundary, label state, socket absence, principal isolation and preserved legacy
state without mutation. Its only success outcome is
`H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED`.

### 5. Run the independent P0 gate

After installation and repeated `--verify-only`, rerun the independent read-only CF2-P0 census.
Only that separately governed census may emit `GROUNDED_CF1_GIT_RELEASE_PATH_ACCEPTED`. Until then,
and if it refuses again, CF2-I-A/B/C, OAuth/device ceremonies, credentials, provider calls, runtime
composition, routing, worker fan-out and failover remain held.

## Verification and stop condition

Run the focused source-contract, artifact, topology and host-preparation tests; the existing
provider-slot/bootstrap/runtime/launchd suites; shell syntax; Python compile checks; the full
repository suite; and independent adversarial review of the exact head. Merge only when all
exact-head hosted CI and CodeQL checks are green.

Privileged host preparation occurs only after that exact reviewed carrier is merged to protected
master. The H0 stop condition is an installed `H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED` receipt plus
fresh repeated `--verify-only` proof with the three labels disabled/unloaded and sockets absent.
The next action is the independent CF2-P0 census, not OAuth, service start, routing or CF2-I.
