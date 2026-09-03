# CodeIntel Z0 Experiment Bundle

## Status and boundary

This runbook describes the manual, production-inert Z0 experiment forge in
`.github/workflows/codeintel-experiment-bundle.yml`. It is one closed vertical:
network-enabled acquisition and deterministic build in Phase P, followed by
complete re-verification and only the fixed Z0 consumer in a network namespace
in Phase E.

The forge is not a package manager, release pipeline, installer, service, index
publisher, or production control plane. It supports no Serena, Pyright,
TypeScript, C0 packaging, Universal Ctags, arbitrary repository, arbitrary
module, arbitrary executable, or argv extension. Creating or reviewing this
source does not authorize a workflow dispatch. An authorized operator must
select the protected `master` ref and supply the exact fixed Z0 consumer commit
and tree; the workflow itself refuses any other forge ref or repeated run
attempt.

The source child that introduced this workflow did not dispatch it and did not
build or trust a real bundle. Until an authorized run produces its own receipts,
the runtime state is `NOT_EMITTED_SOURCE_CHILD_NO_DISPATCH` and production is
`NONE`.

## Immutable lock

The canonical lock is
`research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.v1.json`.
Its schema is
`research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.schema.json`,
and `experiments/codeintel_supply/toolchain_lock.py` independently pins every
security-relevant value. Editing only the JSON cannot widen the accepted
contract.

The admitted upstream identities are:

- Zoekt repository: `sourcegraph/zoekt`
- Zoekt Go module: `github.com/sourcegraph/zoekt`
- Zoekt commit: `5f833dde1bc4b1a8f99007617b4b721e44506c4f`
- Zoekt tree: `8135ec1d7329e7f8de43714ac5c7a2bad14bd7b5`
- `go.mod` Git blob: `db33117af57ea746dff8064e70ce56e3721e44ba`
- `go.mod` SHA-256: `c125539d727350ae76fcc7b37da0c4a091eeb50f1e623ed4aa2455a8ef2fc607`
- `go.sum` Git blob: `6f54532eef8a9628275d1aa870c1b26f89987dd0`
- `go.sum` SHA-256: `a1a6672855e89ef9a30780de23de96d81e5e7ee23ed87eef2d190cd31cb4b2b0`
- Zoekt `LICENSE` Git blob: `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64`
- Zoekt `LICENSE` SHA-256: `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`
- Go archive: `go1.26.5.linux-amd64.tar.gz`
- Go archive size: `66879095` bytes
- Go archive SHA-256: `5c2c3b16caefa1d968a94c1daca04a7ca301a496d9b086e17ad77bb81393f053`
- Go source tag and commit: `go1.26.5` at
  `c19862e5f8415b4f24b189d065ed739517c548ba`
- Go source tree: `0bb2fb1cc06c334c36a2a92d2f0b07fea7236d74`
- Go `LICENSE` Git blob: `2a7cf70da6e498df9c11ab6a5eaa2ddd7af34da4`
- Go `LICENSE` SHA-256: `911f8f5782931320f5b8d1160a76365b83aea6447ee6c04fa6d5591467db9dad`
- Build recipe SHA-256:
  `50ac9f471a49fcda38359b1917277a736cadc8d45ee3a52db09dc6383974e2ae`

The `go.mod` blob is a deliberate correction authorized on the source carrier.
Primary GitHub commit/tree and contents reads agree on `db33117…`. The stale
derived packet prefix `a3917455…` is not an alternate pin; hostile regression
tests require its rejection.

All Actions are immutable commits:

- `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1`
- `actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c`
- `actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`

The execution platform is exactly GitHub-hosted `ubuntu-24.04`, Linux amd64.
The runner image/version, kernel, Python version, pinned Actions, and unavoidable
host utilities are recorded as confounds. The latter are `/bin/bash`,
`/usr/bin/curl`, `/usr/bin/env`, `/usr/bin/git`, `/usr/bin/gh`,
`/usr/bin/python3`, `/usr/bin/sudo`, `/usr/bin/tar`, `/usr/bin/unshare`,
`/usr/sbin/ip`, and `/usr/sbin/sysctl`. They are not claimed to be
content-addressed.

Ubuntu 24.04's AppArmor policy normally permits an unprivileged user namespace
to be created while denying the namespace capabilities required to configure
its private mount and network namespaces. Each boundary-bearing top-level
command therefore uses one serialized privileged prelude on the single-use
GitHub-hosted VM. It requires protected runner identity fields to say exactly
`github-hosted`, Linux, x64, and `ubuntu24`; captures the original value of
`kernel.apparmor_restrict_unprivileged_userns` as exactly `0` or `1`; and
verifies an active readback of `0` before the command. Only an original value of
`1` invokes `/usr/bin/sudo -n /usr/sbin/sysctl -w
kernel.apparmor_restrict_unprivileged_userns=0`. An original value of `0` uses
no privileged write. A self-hosted, unidentified, differently imaged,
malformed, or noninteractive-sudo runner is refused before the boundary
command. The hosted live tests hard-fail, rather than skip, when
`GITHUB_ACTIONS=true` but any protected runner-identity field is incomplete or
drifted; skips remain local-only outside GitHub Actions.

The prelude restores the exact captured value and verifies that readback before
its command's outcome can be accepted. Restoration failure overrides success:
Phase P records `REFUSED / NOT_APPLIED`, while a Phase E invocation that may
have launched records `RECONCILIATION_REQUIRED / EFFECT_UNKNOWN`; neither
successful bundle nor result artifact is accepted. If the original was already
`0`, the prelude proves both active and final state by readback without calling
`sudo` or writing `0`; it does not claim to have re-enabled a mitigation. The
mutable original value is not part of deterministic bundle content.

Every semantic outcome published after normal restoration carries a closed
`host_userns_policy` object: the fixed scope, exact control key and `/proc`
path, observed original and active values, whether a privileged mutation was
performed, separate active/restoration readback-verification booleans, the
restored value equal to the original, and the fixed abrupt-termination cleanup
mode. A policy failure receipt contains only observations reached before the
failure; in particular it never supplies a restored value or claims verified
restoration when the final readback is absent or differs.

This is a temporary system-wide weakening of Ubuntu's user-namespace hardening,
so the user-namespace kernel attack surface is exposed during each bounded
window. Application egress enforcement comes from the fresh user/mount/network
namespaces, permanent capability drop, read-only Unix gate mount, fixed relay,
Landlock, seccomp, and process-group cleanup—not from AppArmor. Normal exit has
checked restoration. `SIGKILL`, forced job cancellation, or VM loss cannot
guarantee the trap/finalizer runs; cleanup then relies on GitHub decommissioning
the disposable VM. This workflow is not suitable for self-hosted runners and
does not claim wholly unprivileged execution, AppArmor confinement, mutation-free
execution when the original value is `1`, or restoration after abrupt
termination.

## Closed request and fixed consumer

The only dispatch inputs are:

- `operation_key`, whose only choice is
  `mastermind-codeintel-z0-discovery-falsifier-20260830-sol-001`
- `consumer_sha`, an exact 40-lowercase-hex commit
- `consumer_tree_sha`, an exact 40-lowercase-hex tree

Inputs enter shell steps only through environment variables. The runner derives
the forge commit/tree, lock digest, and workflow digest from a clean checkout and
writes one canonical request plus its SHA-256. A caller cannot choose a URL,
repository, ref, module, executable, path policy, mode, command, or argv suffix.

Phase E independently checks out the request's exact 40-character
`consumer_sha`; no pull ref, branch, tag, or default branch is executable
policy. It rejects the detached checkout unless its repository, HEAD, and tree
exactly equal the normalized request. The repository must normalize to
`mastermindx-market-intelligence/Mastermind`. The effective consumer diff is
derived from the Git merge base with the forge commit and must stay inside the
fixed Z0 ceiling. Every changed consumer path must be a regular Git blob, and
the required `experiments/code_discovery/z0_runner.py` must be present.

The fixed module is `experiments.code_discovery.z0_runner`. Its fixed role is
`Z0_DISPOSABLE_FALSIFIER`. The only indexed source selection is
`experiments/code_discovery/*`, governed by the committed
`research/code_intelligence_fabric/z0-path-policy.json`. Selected source bytes
are hashed before and after launch.

## Phase P: acquire, verify, build

Phase P is the only subprocess network-enabled boundary. The replay
reconciliation and the build each receive their own host-policy window; the
window closes and exact restoration is verified before the step can succeed.
Each Phase P Python entrypoint starts with `/usr/bin/env -i`. Every subprocess
invocation permitted to contact upstream receives a freshly constructed environment that points
upper- and lower-case HTTP(S)/ALL proxy variables at `127.0.0.1:47853` and
empties both `NO_PROXY` forms.

Before each fixed `curl`, Git-fetch, Go, or `gh` client, the runner starts
`/usr/bin/unshare --user --map-current-user --keep-caps --mount --net`. The
bootstrap makes mount propagation private, bind-mounts the random parent-gate
directory read-only, brings up and verifies a fresh network namespace containing
only `lo`, and binds one relay listener at exactly `127.0.0.1:47853`. The relay
crosses back to the host network namespace only through the read-only pathname
Unix socket owned by the parent CONNECT gate. The hostile client never inherits
that Unix socket or any other socket descriptor.

The bootstrap retains the new namespace capabilities only long enough to freeze
the gate mount and configure loopback. It then installs `no_new_privs`, clears
ambient/effective/permitted/inheritable capability sets and drops the complete
capability bounding set, verifies the real/effective/saved UID and GID remain
the non-root runner identity, and forks the client before starting relay threads.
The client closes every descriptor except stdio
and the one close-on-exec receipt pipe. It requires Landlock ABI 4 or newer and
uses its port rule as defense in depth: TCP connect is admitted only for 47853,
while fixed-port TCP bind is not admitted. A seccomp filter admits socket
creation only for AF_INET stream sockets with protocol zero or TCP; it denies
AF_UNIX, AF_INET6, datagram/raw/alternate-protocol sockets, socketpair,
`io_uring`, namespace and mount changes, process-group escape, and
`MSG_FASTOPEN`. The filter is inherited by every client descendant.

Only after all checks succeed does the client emit
`CODEINTEL_PHASE_P_BOUNDARY_V1` through the receipt pipe and execute the fixed
argv. The parent refuses `ACQUISITION_ALLOWLIST_UNAVAILABLE` if `unshare`, the
private read-only mount, the loopback census, capability clearing, Landlock,
seccomp, descriptor closure, or the exact receipt fails. On normal exit or
timeout, the outer new-session process group is killed to remove descendants.

This topology is independent of client proxy-selection behavior. Go 1.26.5
hard-bypasses configured proxies for `localhost` and loopback IPs. The hostile
regression therefore uses a host proxy at `127.0.0.1:P` and a trap at
`127.0.0.2:P` with the exact same port: the unsealed real Go client reaches the
trap after a redirect, while the sealed client reaches the Unix-backed relay and
then fails to find any listener at `127.0.0.2:P` inside its fresh namespace; the
host trap records zero hits. A direct request to `127.0.0.1:P` reaches the
CONNECT gate and is refused as non-CONNECT traffic. Landlock ABI 4 is explicitly
port-only and is not represented as address-aware; the separate network
namespace and exact bound relay endpoint provide the address boundary.

The proxy refuses non-CONNECT traffic, every CONNECT port other than 443, and
every authority outside this exact host set before opening an upstream socket:
`api.github.com`, `dl.google.com`, `github.com`, `go.dev`,
`proxy.golang.org`, `results-receiver.actions.githubusercontent.com`,
`storage.googleapis.com`, and `sum.golang.org`. The only suffix rule is a strict
subdomain of `blob.core.windows.net`, required for GitHub's pre-signed replay
artifact redirect; the suffix apex and lookalike suffixes are refused.

`curl` disables ambient curl configuration and receives the loopback proxy
explicitly. Git receives an empty home, disables global and system config,
disables prompts and redirects, allows only HTTPS transport, and receives the
proxy explicitly. Go receives an empty home and caches, `GOENV=off`,
`GONOPROXY=`, `GOINSECURE=`, and `GOVCS=*:off` in addition to its fixed proxy
and checksum database. `gh` receives an empty config directory, fixed
`GH_HOST=github.com`, disabled prompts, the loopback proxy, and only the workflow
token. GitHub's pinned checkout/upload/download Actions and unavoidable hosted
runner/control traffic execute outside this in-process proxy and remain explicit
confounds; they are not represented as application-enforced egress.

The phase performs the following sequence:

1. Download the exact Go archive with fixed `/usr/bin/curl`, HTTPS-only
   redirects, bounded redirects, timeout, exact size, and exact SHA-256.
2. Reject a non-gzip archive; absolute/traversal paths; duplicate paths;
   unexpected roots; links; devices, FIFOs, or other special entries; unsafe
   modes; oversized members; excessive expanded bytes; and unsafe destination
   parents. Extract without overwrite or link following.
3. Execute only the extracted Go binary and require `go version go1.26.5
   linux/amd64`. Recompute the archive `LICENSE` Git blob and SHA-256, and verify
   the source tag, commit, tree, and license blob with GitHub object reads.
4. Initialize a new Zoekt repository with fixed `/usr/bin/git`; fetch only the
   exact commit; detach at that commit; and verify clean status, fixed origin,
   commit, tree, `go.mod`, `go.sum`, license blobs, content digests, sizes, and
   a regular-file-only source tree.
5. Use fresh explicit `GOMODCACHE`, `GOPATH`, `GOCACHE`, and `HOME` directories.
   Set `GOTOOLCHAIN=local`, `CGO_ENABLED=0`, `GOOS=linux`, `GOARCH=amd64`,
   `GOPROXY=https://proxy.golang.org`, `GOSUMDB=sum.golang.org`,
   `GOPRIVATE=`, `GONOPROXY=`, `GOINSECURE=`, `GONOSUMDB=off`, `GOENV=off`,
   and `GOVCS=*:off`. Ambient Go, ambient Zoekt executables, ambient VCS fallback,
   and ambient network configuration are never resolved by the subprocess lane.
6. Run `go mod download -json all`, `go mod verify`, and
   `go list -mod=readonly -m -json all`. Reject local or incompletely summed
   replacements and emit the normalized module inventory.
7. Build `./cmd/zoekt-git-index` and `./cmd/zoekt-webserver` twice with distinct
   clean build caches and fixed `-trimpath`, `-buildvcs=false`, and
   `-ldflags=-buildid=` flags. Both binaries must be regular, executable,
   non-privileged files and byte-identical across builds.
8. Reverify the complete Zoekt identity after the build, then assemble the
   bundle and verify it again from its finished bytes.

A typed Phase P failure writes `REFUSED / NOT_APPLIED` before the job exits and
uploads that single semantic receipt under the fixed operation artifact. An
abrupt runner loss that prevents the receipt from being written remains
ambiguous and blocks later execution rather than assuming no effect.

No GitHub cache, setup action, preinstalled Go, floating tag, package install,
or generic dependency resolver is trusted.

## Bundle and provenance

The bundle has exactly six payload files plus its root manifest:

- `bin/zoekt-git-index` — `Z0_INDEXER_EXECUTABLE`
- `bin/zoekt-webserver` — `Z0_SEARCH_EXECUTABLE`
- `meta/sbom.json` — `GO_MODULE_INVENTORY`
- `meta/NOTICE.txt` — `RIGHTS_AND_NOTICES`
- `meta/provenance.json` — `PHASE_P_PROVENANCE`
- `meta/toolchain-lock.json` — `EXACT_TOOLCHAIN_LOCK`
- `manifest.json` — canonical path, role, mode, size, and SHA-256 census plus
  request, lock, recipe, module-inventory, and provenance identities

Bundle creation rejects unexpected files, links, special entries, unsafe modes,
oversized files, secrets, credentials, and private absolute paths. Tar members
are sorted, modes are normalized, uid/gid and modification time are zero,
owner/group names and pax headers are empty, and gzip has an empty filename and
zero timestamp. The complete gzip byte stream is SHA-256-addressed as
`codeintel-z0-<sha256>.tar.gz`.

The Phase P artifact uses the same `codeintel-z0-<sha256>` identity and contains
only that bundle and `phase-p-result.json`. Upload compression is disabled so
the artifact service does not become a second claimed content identity.

## Phase E: reverify, seal, invoke

Phase E downloads only the Phase P content-addressed artifact and then:

1. Rederives the normalized request from the clean forge checkout.
2. Requires the bundle filename to bind the supplied complete SHA-256.
3. Recomputes complete bundle bytes, manifest bytes, member census, types,
   canonical metadata, roles, sizes, modes, and every payload SHA-256 before
   extraction.
4. Rechecks exact consumer repository, commit, tree, effective path census, path
   modes, path policy, and selected source digest.
5. Runs the separate
   `/usr/bin/unshare --user --map-root-user --mount --net` probe in one
   host-policy window, makes the new mount tree private, and verifies exact
   host-policy restoration. Failure writes a durable `REFUSED / NOT_APPLIED`
   receipt with `NETWORK_SEAL_UNAVAILABLE` (or the typed host-policy failure);
   no consumer is launched.
6. Opens a second host-policy window for exactly one sealed invocation, enters a
   fresh user, mount, and network namespace through `/usr/bin/env -i`, and
   verifies exact restoration before accepting the staged semantic receipt.
   No GitHub or Actions credential is passed. Only loopback is raised.
7. Uses the same closed `/usr/bin/git` environment to resolve the exact source
   root, per-worktree Git directory, and `--git-common-dir`. A normal checkout
   deduplicates its identical Git/common directory; a linked worktree retains
   the external common directory as a separate seal root. Symlink, noncanonical,
   malformed `.git` file, or Git-dir/common-dir containment ambiguity is refused.
   Every consumer output, scratch, request, bundle, receipt, home, and temporary
   path must resolve outside all unique seal roots.
8. Makes the namespace mount tree private, self-bind-mounts each unique source
   or Git-metadata root exactly once, and remounts it
   `ro,nosuid,nodev,noexec`. Before consumer launch it proves each device/inode
   is unchanged, `ST_RDONLY` is set, and a create attempt fails with `EROFS`.
   Failure writes a durable prelaunch `REFUSED / NOT_APPLIED` receipt. The
   completed receipt binds every role to its path digest, device/inode, deduped
   seal identity, read-only proof, mount options, and namespace-exit cleanup.
9. Inside that namespace, requires the interface census to be exactly `lo`, the
   non-loopback route census to be empty, and a TCP connect to `1.1.1.1:443` to
   fail with an admitted network-denial errno. This proof strictly precedes the
   consumer launch.
10. Invokes only the fixed isolated Python bootstrap and Z0 module with fixed
   manifest, path-policy, bundle-binary, digest, scratch, result/report, and
   ten-second startup-timeout arguments.
11. Places the consumer in a new process group; sets core, CPU, file-size,
   open-file, process-count, log-byte, and 900-second wall-clock bounds; hashes
   stdout/stderr instead of persisting them; and records PID/process group,
   return code, CPU time, maximum RSS, byte counts, and truncation state.
12. Recomputes source, binary, bundle, and manifest identities after launch;
    removes shard/log scratch; proves the process group is dead and residue is
    absent; and records result/report names, sizes, and digests. A zero return
    code is accepted only when both bounded regular files decode as strict
    UTF-8, contain no secrets or private paths, and exactly satisfy the pinned
    Z0 result schema, manifest/path/tool/binary identities, production-inert
    observations, repository status, non-acceptance decision, and byte-exact
    rendered report. A known nonzero return remains an `APPLIED` experiment
    outcome and is not misreported as a successful Z0 result.

If the sealed child ends without a durable receipt, the outer boundary records
`RECONCILIATION_REQUIRED / EFFECT_UNKNOWN` and fails. It never substitutes a
new candidate, falls back to a different host, or starts again.

## Replay and semantic receipts

The exact run name is:

`codeintel-z0|op=<operation>|consumer=<commit>|tree=<tree>|forge=<forge-commit>`

Before Phase P acquisition, the runner reads every bounded page of prior manual
runs for this workflow. Collection movement, duplicate rows, an excessive
census, any same-operation changed request, any incomplete prior run, a missing
or non-unique receipt artifact, disagreeing receipts, malformed receipt bytes,
or an unknown prior effect fails closed.

The fixed receipt artifact is
`codeintel-z0-operation-9aae1af9ef430044fbba77ae0f87cf12d4425c75f577b4427c09ae66cec11bf4`.
Its archive must contain exactly one regular `semantic-receipt.json`. The
bounded `z0-result.json` and `z0-report.md` files are uploaded under a
separate `codeintel-z0-result-<bundle-sha256>` artifact so they cannot widen the
receipt artifact's replay census. That separate artifact is uploaded only after
a successful sealed step and only after both files have passed the full strict
semantic validator described above. The receipt has one of only three
status/effect pairs:

- `COMPLETED / APPLIED`: the fixed consumer launched and the exact normalized
  outcome is known, including a known nonzero return code.
- `REFUSED / NOT_APPLIED`: the consumer did not launch.
- `RECONCILIATION_REQUIRED / EFFECT_UNKNOWN`: launch may have occurred but the
  effect cannot be proven.

Each receipt includes its canonical request and request digest, bounded evidence,
and a semantic SHA-256 over every other receipt field. Secret-bearing or
private-path-bearing evidence is rejected.

An identical known receipt is returned byte-for-byte without acquisition or
launch. A prior refusal preserves a failing workflow outcome; a prior known
consumer return code preserves that same outcome. A changed request is
`REQUEST_CONFLICT`. `EFFECT_UNKNOWN` is
`EFFECT_UNKNOWN_REPLAY_BLOCKED` until externally reconciled; there is no
automatic failover or second supply-chain plane.

## Verification and evidence reading

Source verification is:

```text
python3 -m pytest -q tests/codeintel_supply/test_toolchain_lock.py tests/codeintel_supply/test_hosted_runner.py tests/codeintel_supply/test_workflow_source.py
python3 -m py_compile experiments/codeintel_supply/toolchain_lock.py experiments/codeintel_supply/hosted_runner.py
git diff --check
```

The hostile suite covers alternate checksum/source/tree/main-module/license pins
(including stale `a3917455…`), floating acquisition, action movement, archive
traversal/link/special/mode attacks, unsafe extraction destinations, ambient Go
and Git, disallowed CONNECT authorities and proxy bypass configuration, bundle
substitution and post-launch drift, consumer identity/path/mode/cross-boundary-rename
widening, arbitrary module/argv widening, network exposure, secret/private-path
leaks, result bounds, process cleanup, changed replay requests, receipt tamper,
unknown effects, self-hosted or malformed policy contexts, missing/malformed
sysctl state, noninteractive-sudo/write/readback/restore failures, forced-body
cleanup, and suppression of otherwise-successful receipts when restoration
fails. Hosted Linux discrimination proves policy `1` blocks the private boundary
receipt while policy `0` lets the identical boundary reach it, then verifies the
original policy is restored. The live client also proves runner UID/GID,
zero inheritable/permitted/effective/bounding/ambient capability sets,
`NoNewPrivs: 1`, and denial of namespace `clone`, `clone3`, `unshare`, `setns`,
and capability regain.

For an authorized run, retain and compare these independently emitted values:

- forge commit/tree, workflow SHA-256, lock SHA-256, and request digest
- bundle filename, complete SHA-256 and size
- manifest, module-inventory, provenance, and build-recipe SHA-256 values
- both binary SHA-256 values and repeat-build equality
- exact consumer commit/tree, merge base, changed paths, and source digests
- source, Git worktree-dir, and Git common-dir path digests, device/inode
  identities, deduplicated seal IDs, and read-only verification
- network-seal observation, fixed invocation role/contract, return code,
  resource/process/cleanup evidence, result/report digests, receipt semantic
  digest, runner image, and host-utility confounds

Those receipts prove only that exact disposable experiment run. They are not
evidence of installation, a durable service or index, a profile change,
deployment, live production, or approval to promote the bundle.
