# Stage a sealed Executive release without selecting it

The existing `ops/executive_os/install.sh` accepts `--stage-release-only`. This is
source preparation for an explicitly commissioned recovery, not permission to
retry a transaction, change a configuration, or select a release.

Use the same root-owned signed Python runtime, account, authentication and exact
clean current protected source prerequisites as ordinary installation, with a
complete source-bound `--os-web-assets` bundle. The ordinary source policy is
unchanged. Frozen-ancestor mode, `--arm-privileged-broker` and `--control-config`
are rejected in this mode. Existing `/Library`, `/Library/Application Support`,
`MastermindExecutive` and `releases` ancestry must be direct, root-owned 0755 and
free of native ACLs. Only the established root:admin 0755 exception for
`/Library/Application Support` is allowed.

After all read-only prerequisites pass, the staging branch calls the same archive,
asset import, manifest seal, verification and exclusive publication implementation
as normal installation. It exits before Codex helper preparation, the service
cleanup trap, service commands, configuration writes and release selection. The
normal installation branch continues to fence the C1 Relay before calling that
shared implementation.

The stage has the fixed name `releases/.stage.<exact-sha>`. An occupied name,
including a dangling symlink, refuses without adoption or cleanup. A new stage
is retained on any failure or uncertainty. Publication uses the existing native
exclusive rename; it cannot overwrite or nest into a concurrent destination.
A canonical release already present is only verified against the trusted source
manifest helper and the identical asset bundle. Nothing is grafted, resealed or
repaired there. A publication whose final readback fails remains unresolved;
never infer successful staging or issue recovery from that failure.

Successful output contains `staged_unselected: true`, the exact commit, and false
values for selection, service, configuration, receipt and transaction changes.
These fields describe this staging operation: they do not certify that the release
has never been selected historically, that a runtime is stopped, or that recovery
is authorized. The caller must still verify the protected composition, original
transaction bindings, commissioned recovery operation and fresh physical gates.
No service is stopped or restarted by staging, and no original journal is read or
changed. The separate reviewed recovery command remains solely responsible for
its exact original-transaction checks and one-way publication/cleanup semantics.

Tests execute the production shell functions and dispatch with real temporary
Git archives, source qualification, asset validation and release manifests.
Explicit test-only OS ownership/ACL collaborators allow unprivileged fixtures;
there is no production fixture selector or alternate destination flag. These
checks are source evidence, not a host installation or recovery result.
