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
while User=longr and Group=longr keep the Hermes process unprivileged.
Each unit requires the one approved hermes-egress.service proxy and
uses only its own loopback proxy /32 plus 127.0.0.1/32 for the native
gateway. No blanket localhost, root process, new scheduler or
alternate credential store.

The existing CLI supervise entrypoint now rejects all processes outside
the exact /system.slice/hermes-runtime-ROLE.service cgroup **before**
loading the role's secret file. This means even a previously generated
systemd --user unit cannot begin a provider session through the new
source. Rendered system unit text has exactly one protected EnvironmentFile,
ExecStart and explicit operator-only ExecReload. Rendering does not
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
      --user longr --group longr --python /usr/bin/python3 \
      --repo /absolute/reviewed/Mastermind

Review the complete generated source text; the root operator must install
it as root:root mode 0644 under /etc/systemd/system/ and run
systemd-analyze verify. Source rendering itself makes NO host writes.
Before any charged model canary, prove actual unit-cgroup policy in BOTH
directions from the final installed system services: own proxy allowed;
other proxy, unrelated loopback and direct public 443 all denied.
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
