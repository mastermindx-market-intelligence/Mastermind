# Ubuntu1 Hermes BYOK: root-owned services, non-root role processes

**SOURCE-ONLY — not installed or activated.**

## Why the architecture changed

On November 2, 2026, the actual Ubuntu1 user manager logged
"unit configures an IP firewall, but not running as root". Its systemd
user-unit had IPAddressDeny=any yet successfully connected directly to
1.1.1.1:443 (connect_ex=0): production egress was NOT confined.

Two reversible, root-managed transient service tests then used
systemd-run --system with User=longr, IPAddressDeny=any and exact
IPAddressAllow prefixes. Temporary synthetic listeners were present
at both proxy loopback addresses for both tests.

| Allowed proxy | Assigned listener | Other listener | Public 1.1.1.1:443 |
| --- | --- | --- | --- |
| Secretary 127.0.0.2/32 | connected (errno 0) | failed (errno 11) | failed (errno 11) |
| Meta-CEO 127.0.0.3/32 | connected (errno 0) | failed (errno 11) | failed (errno 11) |

The failed bounded-time connect attempts establish that those connections
did not complete during the probes, not that every future kernel policy
will work. Both transient units ended and were collected. No private
model key, Hermes process or real provider endpoint was touched.

## Source change

The system_service.py module generates one **root-owned systemd SYSTEM**
unit per role, not a user-manager unit. PID1 manages the cgroup firewall
while each role runs as its own pre-provisioned account/group: mmsecretary
or mmmeta, with different non-root numeric UIDs/GIDs. The former shared
longr example is NOT an admissible production configuration.
Each unit requires the one approved hermes-egress.service proxy and
allows exactly one role-specific loopback /32: 127.0.0.2 for Secretary,
127.0.0.3 for Meta-CEO. Its existing gateway, pinned native backend and
vendor CONNECT proxy bind distinct ports on that **same role-only IP**.
Neither unit grants 127.0.0.1, the sibling alias, wildcard loopback,
public IPs, root execution, a new scheduler or another credential store.
The system renderer and the production supervisor refuse a legacy profile
that still binds the shared 127.0.0.1 gateway before credential access.

The existing CLI supervise and operator canary entrypoints reject processes outside
the exact /system.slice/hermes-runtime-ROLE.service cgroup **before**
loading the role's secret file. This means even a previously generated
systemd --user unit cannot begin a provider session through the new
source. Rendered system unit text has NO EnvironmentFile (no pre-guard secret
loading), one ExecStart and one explicit operator-only ExecReload. Both
CLI entrypoints validate distinct numeric OS identities/private paths and
attach mandatory Linux Landlock TCP-port restrictions before loading secrets.
See ROLE_ISOLATION_REPAIR.md for exact scope and host acceptance. Rendering does not
install, enable, start or reload any service.

## Safe release and installation procedure

The human/system root operator must first obtain independent reviews,
the normal protected releases of #1865, #1917, #1963 and this patch,
actual private role credentials, the pinned source and compiled binary,
and the approved Squid proxy. No bot is activated simply because source
CI is green.

The existing source installer currently creates a user-unit artifact.
To stage its release without registering a LIVE user service, the
operator can pass an inert, isolated directory such as:

    --systemd-user-dir /home/longr/.local/share/hermes-stage/systemd/user

That directory must not be symlinked or watched by the user manager.
Do not enable or start the old user-unit; disable and stop any existing
user service for the selected role before the protected cutover.
Only one live service manager may own each role.

With the installed, pinned profile and protected checkout, render the
system unit for manual inspection (all path arguments must be actual
absolute, space-free paths, never model-proposed values):

    python3 -m integrations.hermes_runtime.system_service \
      --profile /absolute/state/current/profile.yaml \
      --user mmsecretary --group mmsecretary --python /usr/bin/python3 \
      --repo /absolute/reviewed/Mastermind

Repeat using the actual mmmeta profile with --user mmmeta --group mmmeta.
Never render both roles as the same user or run these as root model processes.

Review the complete generated source text; the root operator must install
it as root:root mode 0644 under /etc/systemd/system/ and run
systemd-analyze verify. Source rendering itself makes NO host writes.
Before any charged model canary, prove actual unit-cgroup policy in BOTH
directions from the **final installed** services: own vendor proxy,
own gateway and native backend allowed; sibling alias, a confirmed
listening 127.0.0.1 service, unrelated loopback and direct public 443
all denied. Also prove an unrelated wildcard-bound listener is denied when
addressed through the calling role's OWN alias and an unapproved TCP port,
and that each role cannot read a sibling-owned synthetic secret file.
Landlock tests must pass without skips; UDP/Unix IPC are outside the TCP
restriction's claimed scope. A missing listener/connection-refused result does not prove
the firewall denied the connection. systemd IPAddressAllow is an
IP-prefix filter, not a per-port firewall; do not add back
127.0.0.1/32 to make a gateway/health test pass.
Confirm effective parent policy and absence of unsupported-BPF warnings.
Test the actual reviewed Squid config for denied off-list CONNECT,
private IP targets, wrong ports and wildcard services.

After authorization only, the root operator may reload systemd, start
the approved proxy, enable and start ONE bot role at a time, verify
actual authenticated native text turns and credential separation, then
prove original-parent Slack roundtrips for two distinct bot identities.
The existing Grok Secretary stays live until acceptance and rollback
are actually observed. A local dashboard health 200 is not live
provider/Slack proof; source success or a failed request is not proof
of no billing effect.

A failed network probe or missing private credential BLOCKS production
activation. Never set IPAddressAllow=any, run model processes in the
unconfined user manager, or share keys between roles. The authorized
operator can stop the root system service and proxy to fail closed;
reconcile any uncertain charged model attempt before retrying.
