# Final role isolation qualification

**Source only. This kit does not install or activate Hermes and does not clear the
NO INSTALL / DO NOT DEPLOY hold.** It supplies a finite, credential-free observation
inside an existing approved role service. Final role qualification still requires
the external witnesses described below.

The source was composed on protected Mastermind
`da34c7cf2beef8c16a7f95e41a4d4b0193391d5b`. The six production guard/profile dependency
blobs match reviewed #1966 head `b10dce8892a3bba10a8115a266c8d8ad71ddf7ac`.
See [ROLE_ISOLATION_REPAIR.md](ROLE_ISOLATION_REPAIR.md) and
[ROOT_CONFINED_SYSTEM_UNIT.md](ROOT_CONFINED_SYSTEM_UNIT.md).

## Scope and evidence

The probe imports these production functions without copying or weakening them:

1. `assert_root_service_cgroup`
2. `assert_role_network_profile`
3. `assert_role_credential_isolation`
4. `enforce_role_tcp_ports`

The first three observations run again after the matrix and child cleanup.
Identity, cgroup, source and profile changes invalidate `context_rechecked`.
Landlock is applied once; it is never reapplied as a supposed observation.

Import starts nothing. Execution reads synthetic marker files and non-secret
source/profile/identity metadata, creates finite owned loopback fixture children,
and publishes one report. It does not read credential contents, call a provider,
send Slack messages, create accounts, install/reload/start/stop services, modify
routes/firewalls, or instantiate the serving runtime. The report includes private
path metadata; retain it as private operator evidence, not a public UI response.

| Role/account | Exact unit | Address | Gateway | Backend | Proxy connect |
|---|---|---|---:|---:|---:|
| mmsecretary | hermes-runtime-mmsecretary.service | 127.0.0.2 | 8765 | 8766 | 18651 |
| mmmeta | hermes-runtime-mmmeta.service | 127.0.0.3 | 8865 | 8866 | 18652 |

The expected cgroup is `/system.slice/<exact unit>`. The probe uses
`role_tcp_ports(profile)` for policy and separately checks fixed role ports.
A transient unit or shell outside that actual cgroup cannot substitute for it.

## Thirteen cases and their limits

Examples below use Secretary ports; Meta-CEO uses its own row above.

| Case | Required observation |
|---|---|
| profile.fixed_ports | Loaded profile matches the documented fixed ports. |
| bind.own_alias.gateway_port | Owned listener actually binds 127.0.0.2:8765 after Landlock. |
| bind.own_alias.backend_port | Owned listener actually binds 127.0.0.2:8766 after Landlock. |
| bind.own_alias.ephemeral_port | Bind port0 succeeds before Landlock and is immediately refused with EACCES/EPERM afterward. |
| tcp.own_alias.gateway_port | Connection succeeds against the current owned gateway fixture. |
| tcp.own_alias.backend_port | Connection succeeds against the current owned backend fixture. |
| tcp.own_alias.denied_port | Same-target positive before Landlock; current owned listener before/after; immediate EACCES/EPERM afterward. |
| tcp.sibling_alias.gateway_port | A Landlock-allowed port on the other role's address is denied; external positive bracketing is still required. |
| tcp.shared_loopback.gateway_port | A Landlock-allowed port on127.0.0.1 is denied; external positive bracketing is still required. |
| exec.own_alias.denied_port | Exact positive and owned-listener bracket followed by inherited immediate port refusal in an exec descendant. |
| exec.own_alias.gateway_port | Exec descendant reaches the current allowed fixture. |
| file.own.read | Exact synthetic path, actual bounded regular FD, role UID/GID0600, marker bytes and digest, unchanged file/parent custody. |
| file.peer.read | Peer synthetic read fails; copied earlier evidence alone cannot prove the file currently exists behind an inaccessible parent. |

A listener witness joins our child PID, parent, process start ticks, exact socket
FD/inode and exact address/port LISTEN row. A foreign socket or wildcard row is
not a substitute. The denied port defaults to45151/45152 and must be outside both
roles' fixed ports and the current role's policy.

An ECONNREFUSED, unrelated I/O/network/resource errno, child deadline/crash, malformed
exec output, empty witness or generic timeout never becomes Landlock denial PASS.
Successful forbidden connect/read is FAIL even if the fixture later disappears.
Children have a finite lifetime and exit on parent loss; cleanup signals only
unreaped owned children, uses bounded TERM/KILL/reap deadlines and precedes report
publication. Failed cleanup makes qualification incomplete.

### External evidence remains necessary

Same-role-cgroup fixture listeners cannot supply an outside-cgroup positive.
The two address-denial cases therefore remain UNAVAILABLE in this version.
The same holds under `--external-address-fixtures` below: the attempt is
recorded, but no denial is attributed and neither case is qualified.
A copied peer report is an earlier observation; peer-file denial likewise remains
UNAVAILABLE without a root-controlled before/after existence bracket. The probe
does not silently upgrade these observations, even with a matching peer report.

The existing authorized host owner must separately record, for the same host,
boot, source, profiles, role services, run ID and time interval:

- An outside-role-cgroup successful connection to each exact address/port before
  and after the role's negative attempt, with unchanged owned listener identity.
- Both role fixtures' actual path, device/inode, UID/GID,0600 mode, single link,
  marker bytes/digest and time facts before/after the cross-role negative attempts.
- Unchanged hashes of the root-copied reports throughout that bracket, plus both
  actual role contexts and unit definitions.

Do not improvise a fixture daemon, controller, registry or new admission path.
This utility does not ingest/attest those external observations yet; they are
separate final acceptance evidence. An INCOMPLETE report must remain INCOMPLETE.
A report's own-file PASS may still be useful earlier evidence in an A/B/A sequence.

### Operator-supplied outside-cgroup fixture

`--external-address-fixtures` is one closed boolean. It supplies no host, port,
path, command or authority. It changes the fixture ownership of two cases and
nothing else. Its normalized boolean is recorded in the existing fingerprinted
context, so internal and external fixture modes cannot share an evidence identity:

| Case | Default internal listener | Under the flag |
|---|---|---|
| tcp.sibling_alias.gateway_port | sibling_gateway | omitted; the target is the sibling role alias on this role's fixed gateway port |
| tcp.shared_loopback.gateway_port | shared_loopback_gateway | omitted; the target is 127.0.0.1 on this role's fixed gateway port |

The targets, ports and expectations are unchanged: they are still derived only
from the loaded profile, the role aliases and the documented fixed role ports.
Every other listener, case, guard, production guard order, profile/role
validation, Landlock invocation, file check, child ownership and cleanup rule,
report bound, context/source recheck and exit code is exactly as before, and
the default invocation is unchanged.

The current root operator may retain its own finite outside-role-cgroup socket
file descriptors at exactly those two targets — the sibling role alias and
127.0.0.1, each on this role's fixed gateway port — so that the fixture is
owned outside the unit cgroup instead of by a same-cgroup child. The operator
then proves, around ONE actual role-unit invocation:

- a successful connection to each of those two exact targets from outside the
  role cgroup, before the role's negative attempt and again after it;
- unchanged listener identity across that bracket: the same socket inode, the
  same owning process and start time, and the same exact address and port.

Those observations are the outside-cgroup positive. The probe cannot supply
them: it runs inside the role cgroup, so it can neither join that socket's
inode nor bracket it. It therefore records the attempt as an observation only.

Per case, the probe records the actual derived target, the observed errno and
errno name, and the symptom, and then only these outcomes are possible:

- The forbidden target answered the connection: FAIL. A forbidden address that
  is reachable is a real failure and the report says so.
- The attempt was refused immediately with EPERM, or timed out with
  EAGAIN/ETIMEDOUT: the refusal shape is recorded with an unverified
  attribution, the external witness is marked insufficient, and the case stays
  UNAVAILABLE. The role report stays INCOMPLETE.
- Nothing answered at the target (ECONNREFUSED): UNAVAILABLE; a missing
  listener is never policy proof.
- An unrelated error, including immediate EACCES, EIO, EMFILE or ENETUNREACH:
  ERROR/FAIL, preserving the existing probe's classification. It is never
  counted as policy denial.

The absence of an observed denial is never upgraded into a denial, and a
missing witness never yields PASS. The operator adjudicates the separate
outside-cgroup bracket against this recorded attempt and reports it as separate
final acceptance evidence. The peer-file before/after witnesses described above
remain separate evidence: this mode neither supplies nor replaces them.

This flag is not an installation, serving, provider or Slack authorization. It
does not install, start, stop, reload or modify a unit, open a credential, call
a provider or a model, or send a message. It changes what the probe measures;
it does not change the hold.

## Required host preflight

The approved host operation must establish source/release custody and reconcile
existing writers and effects before any host mutation. This document is not that
authorization. Retain the original installation hold until its named conditions
are proved; unit source or a synthetic test does not clear it.

NSS accounts must have distinct nonzero UID/GID. State and private-secret parents
must satisfy the unchanged production0700 role-ownership and safe-ancestor rules.
The secrets leaf must satisfy the production0600 regular single-link guard.
An empty placeholder may be prepared for credential-free qualification only when
that exact path is absent and preparation is authorized. Never truncate, replace,
copy or display an existing credential.

The two root-managed units must preserve all original hardening, exact role
address allowlist, private state paths, no EnvironmentFile, and the incumbent
hermes-egress.service dependencies. Stop and reconcile a running role before
using its service for qualification; never overlay a live serving writer.

Egress has an existing repository owner:
[ops/hermes_egress](../../ops/hermes_egress/README.md). Its unit/configuration are
not invented by this kit. The source-address repair in
[PR2094](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2094)
belongs to that existing owner. Qualify its actual protected/install state,
unbound-client source address and ownership receipt; a source PR or disposable
network-namespace result is not an installed-host receipt. Do not substitute
a forced-source test, wildcard listener or weaker role IP policy.

## One bounded run through the existing unit

Choose one qualification ID matching `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`.
Bind the same ID to the complete host/boot/source/profile evidence set. Use a new
run suffix for each A/B/A invocation. An existing report or drop-in refuses;
do not overwrite it to hide an earlier failure.

The synthetic file is exactly `<state_dir>/qualification/synthetic.txt`, with
these fixed bytes, role UID/GID and0600 mode:

```text
mastermind-hermes-role-isolation-qualification-synthetic-v1
```

The trailing newline is required. Prepare with exclusive creation inside the
qualified0700 directory; compare an existing fixture's exact facts rather than
rewriting it. Capture the installed unit/drop-ins and effective ExecStart,
Restart, User, Group, ControlGroup, IPAddressDeny/Allow, dependencies and paths.

Prepare one root-owned0644 drop-in with an operation-specific previously absent
name, for example `90-isolation-<qid>-a1.conf`. This is a reviewable template;
substitute paths and executable from the approved effective unit:

```ini
[Service]
Restart=no
ExecStart=
ExecStart=/usr/bin/python3.12 -I -S -B /opt/mastermind-executive/releases/<40-character-commit>/ops/executive_os/release_manifest.py hermes-runtime isolation-probe --profile /home/mmsecretary/.local/state/hermes-runtime-mmsecretary/current/profile.yaml --role mmsecretary --qualification-id q20261105 --own-file /home/mmsecretary/.local/state/hermes-runtime-mmsecretary/qualification/synthetic.txt --peer-file /home/mmmeta/.local/state/hermes-runtime-mmmeta/qualification/synthetic.txt --report /home/mmsecretary/.local/state/hermes-runtime-mmsecretary/qualification/report-q20261105-mmsecretary-a1.json
```

Replace `<40-character-commit>` with the protected release selected by the
approved effective unit; it must match that unit's implementation identity.
The fixed `isolation-probe` entry uses the same held first-party source and
qualified pure-Python YAML context as `supervise` and `canary`. It does not
accept an arbitrary module or executable. `--list-cases` lists the closed
matrix without starting the probe. Preserve source-refusal exit 78 and the
probe's own report/exit semantics, including honest INCOMPLETE results.

`Restart=no` is essential: a failed/incomplete probe must not enter the serving
unit's restart loop. Create the drop-in exclusively, record its exact hash and
original effective properties, reload via the authorized existing system manager,
and read back both ExecStart and Restart before a single start. Do not change
User/Group, cgroup, environment, address policy, dependencies or other hardening.
Use the existing service owner's bounded observation; never start again merely
because a terminal report is delayed.

If the first role produced valid own-file evidence, the root operator may copy
that report unchanged into an already qualified root-owned non-writable evidence
directory, using exclusive creation and0644 mode. This public-readable copy
contains synthetic/path metadata, never credential values. Every ancestor must
be root-owned and non-group/other-writable. Rehash/read back the copy.

A later peer invocation supplies all three additional arguments:

```text
--peer-report <exact root-copied report>
--peer-report-sha256 <64 lowercase hex of that exact copy>
--peer-profile-sha256 <64 lowercase hex of that peer's actual profile bytes>
```

Use the same qualification ID, host/boot and imported source. Reports older
than900seconds, future-dated, malformed, duplicate-keyed, wrong-role, mismatched
profile/source/identity/cgroup, incomplete guard/context/cleanup proof or changed
custody are refused as peer evidence. Root ownership alone cannot make stale or
inconsistent data qualify.

A1 Secretary, B1 Meta-CEO and A2 Secretary can establish earlier own-file evidence
for both directions. **This sequence alone proves neither current peer existence
nor cross-role isolation.** Supply the independent bracket above. Execute serially
under the existing owner; each invocation gets an exclusive report filename.

### Restore before any serving claim

After the bounded invocation, reconcile its exit and child cleanup. Through the
existing root service owner, stop any remaining qualification process before
removing only the exact hash-matching drop-in created by this operation. Preserve
all unrelated drop-ins. Reload once and read back:

- Effective ExecStart equals the recorded original serving command.
- Effective Restart equals its recorded original value.
- No qualification module or operation-specific override remains.
- Role identity, cgroup/address hardening, dependencies and private paths match
  the approved original configuration.

Do not automatically start the serving runtime, invoke ExecReload/canary or
enroll credentials as cleanup. Those are separate authorized effects. Remove only
proven operation-owned unchanged synthetic fixtures/placeholders; preserve real
credentials and useful evidence. Any uncertain cleanup stays on its original
service/operation until reconciled.

## Version2 input/output

Schema: `mastermind.hermes_role_isolation_qualification.v2`.

Required inputs are `--profile`, `--role`, `--qualification-id`,
`--own-file` and `--peer-file`. Optional inputs are the three peer-evidence
arguments above, `--report`, `--denied-port`, `--connect-timeout`, `--only` and
the closed boolean `--external-address-fixtures`. `--list-cases` is inert and
needs no host qualification.

Timeout must be finite and in(0,30]seconds. A report path must be inside the exact
state qualification directory, be named `report-*.json` and contain the run ID.
Reports use exclusive0600 temporary creation, fsync, atomic no-replace publication,
directory sync and bounded readback. Existing files, symlinks and concurrent
publication losers are refused. Directory traversal is FD-relative with
O_DIRECTORY/O_NOFOLLOW and retained/current ancestor identity checks.

The output binds machine ID, boot ID, network namespace, kernel, imported source
bytes and loaded guard code, bounded actual profile bytes and complete semantic
profile, actual NSS/process/cgroup identity, initial guards and final observations,
matrix selection, owned witnesses, cleanup and file facts. Source/profile/host
provenance is compared around profile loading and after the matrix.

Aggregate PASS requires the entire13-case matrix, all four production guards,
stable final context and completed cleanup. A subset never qualifies the whole
role. Current external-witness limitations mean a real full run remains INCOMPLETE.
Under `--external-address-fixtures` the two address-denial cases can never earn
PASS. Without a failing observation, their insufficient external witness keeps
the report INCOMPLETE; any observed FAIL remains FAIL.
Exit0 means aggregate PASS;2 means FAIL;78 means INCOMPLETE/configuration refusal;
3 means I/O failure. An early setup refusal can produce only a fixed stderr
refusal, without a report.

Mocked aggregate PASS tests prove classifier logic only. Unit tests, root-custody
fixtures, Linux listener fixtures, transient units and off-host tests are not
actual final-role acceptance. Neither this kit nor an isolation report proves
provider identity, served model, credentials, TLS, billing, Slack round trip or
a useful end-to-end CEO/Secretary result.
