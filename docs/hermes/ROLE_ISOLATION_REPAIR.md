# Hermes role isolation: distinct OS identities plus exact TCP ports

Status: source candidate, NOT installed or production accepted.
Parent: original PR #1966 at 7b1c7736d49ef399ec74e91e8e251c84bc7d2bb6.
Finding: PR #1966 issuecomment-6618388066.
Operation: hermes-1966-isolation-repair-20261103-sol-001, under the existing
meta-ceo-open-harness-convergence-20261024-sol-001 program.
Procedure pin: Mastermind 910803421beca53ca25145392725ab2d84c7a8e9.

## Outcome and source custody

The existing Secretary and Meta-CEO services must not share credential-reading
OS authority or reach an unrelated TCP listener merely because it also accepts
connections to the allowed loopback alias. This repair changes the original
runtime, not the Executive, Agent OS, provider router, review queue, or bot owner.
The incumbent Grok Secretary remains live. No account is created, service started,
provider called, credential enrolled, or protected source merged by this change.

Direct-work basis: PRINCIPAL_JUDGMENT for the isolation boundary and
NO_ELIGIBLE_PRE_EFFECT_WORKER for this bounded implementation. The existing
Fabric reader returned NOT_FOUND/root_verified=false/dispatch_authorized=false
for the historical program label; it is not an authenticated new worker root.
No replacement root, native worker, or denied CodeQL repair was dispatched.
Source is in the registered isolated M2 workspace for the operation above;
original #1917 workspace and failed CodeQL worker remain untouched.

## Credential boundary

Each role has its own pre-provisioned OS account AND group, named exactly
`mmsecretary` or `mmmeta`. The source renderer refuses `longr`, the sibling
account, root, and arbitrary account substitutions. Naming alone is not proof:
before the runtime loads a secret, the existing CLI resolves both accounts and
groups through the host's normal NSS interfaces and verifies non-root, unequal
numeric UIDs/GIDs, matching real/effective IDs, and no extra supplementary groups.
No account registry or credential lifecycle is added.

The role's state directory and secrets parent must be actual owned `0700`
directories, with no symlink or unrelated/writable ancestor. The secret file must
be role-owned `0600`, regular and single-linked. Failure refuses startup; code
never fixes permissions automatically. Existing `load_secrets()` remains the
only secret-content reader. Both supervisor startup and operator canary use the
same identity/path gate. Root system units now have NO `EnvironmentFile=`:
systemd must not preload those secret bytes before Python's isolation gates.
Legacy user-unit artifacts are inert and remain ineligible for production.

Provision directories and all provider-key pointers privately under the selected
role account's home, not a shared operator home. Both roles need a distinct
native Hermes install and upstream attestation. The authorized account owner
must prove synthetic sibling-file reads are denied from both actual service
contexts. Do not test by opening real sibling credentials.

## TCP boundary without another firewall service

The existing PID1 cgroup keeps `IPAddressDeny=any` and only the role's own /32.
`tcp_sandbox.py` additionally applies Linux Landlock's TCP bind/connect rights,
ABI >= 4, before credentials, threads, sockets, or model-child processes. This
unprivileged, inherited process restriction cannot be removed by descendants.
No privileged helper, firewall daemon, ruleset file, scheduler or polling loop
is introduced. Unsupported architecture, disabled Landlock, old ABI, preexisting
threads/Internet sockets, rule failure or attach failure refuses startup. There is no
best-effort downgrade or automatic alternate route.

| Role | Allowed TCP binds | Allowed TCP connects |
| --- | --- | --- |
| mmsecretary | configured fixed gateway/backend (defaults 8765/8766) | those two ports plus 18651 |
| mmmeta | configured fixed gateway/backend (defaults 8865/8866) | those two ports plus 18652 |

Ports must be distinct, nonprivileged and fixed: zero/ephemeral, boolean,
colliding, or out-of-range values fail. The existing private proxy pointer is
now bound to the actual source-qualified Squid listener's exact role port, not
an arbitrary port on the role alias. IP rules and TCP rules are complementary:
Landlock does not itself select the destination IP or authenticate a listener.

Reference: Linux kernel userspace Landlock API, TCP network rights introduced
at ABI 4: https://docs.kernel.org/userspace-api/landlock.html .
The implementation uses the documented 16-byte ruleset/net-port layouts and
Linux x86_64/aarch64 syscall numbers; other platforms refuse live activation.

**Limits are explicit:** this restriction handles TCP, not UDP or Unix-domain
IPC. It does not authenticate the proxy, attest executable ownership, establish
TLS/billing, or replace the actual cgroup firewall. An attacker occupying an
allowed service port is a separate service-identity/custody failure. The real
proxy and both service listeners must be observed under their intended owners.
No general compromised-process containment or production certification is claimed.

## Tests and actual acceptance

Hermetic tests cover both numeric identities, NSS aliases, groups, root and
wrong process identity, symlinks, modes, hard links, parent ownership, fixed
ports, each failed Landlock syscall, inherited-socket/late-thread refusal,
and BOTH production entrypoints refusing before secret/model access.

`test_tcp_sandbox_linux.py` creates harmless positive wildcard listeners in a
parent test process, then starts a fresh credential-free Linux child. For BOTH
127.0.0.2 and 127.0.0.3 it requires permitted TCP connect/bind, EACCES for the
unrelated listener through the allowed alias, forbidden ephemeral bind, and
inherited EACCES after exec. ECONNREFUSED is never counted as firewall denial.
A non-Linux/unsupported-kernel skip is NOT enforcement acceptance. Actual host
qualification requires zero skips, then the same negative matrix inside both
final PID1 role cgroups, plus synthetic cross-role file denial.

The final host must separately prove private paths/UIDs, active service and proxy
identity, actual cgroup/IP policy, actual TCP restrictions, vendor CONNECT ACLs,
no inherited Internet sockets (the AF_UNIX journal stream is allowed), authenticated provider result/TLS/billing,
original-parent two-bot Slack replies and rollback. Do not stop the existing
Grok Secretary until the original product acceptance is satisfied.
