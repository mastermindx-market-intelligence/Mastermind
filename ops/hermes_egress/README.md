# Hermes BYOK vendor CONNECT egress — host operator deployment candidate

**SOURCE-ONLY; not installed.** This is **one existing Squid 6/7 data-plane
process**, configured with two fixed, role-specific listeners and no model
keys. It consumes the host network policy in PR #1961; it is **not** a new
agent, scheduler, admission service, queue, identity store or retry engine.
The assigned network/release session must qualify the actual host boundary
under the existing protected release and activation requirements before enabling
any real bot.

## Fixed contract

| Source unit | Exact proxy socket | Only CONNECT destination |
| --- | --- | --- |
| `hermes-runtime-mmsecretary.service` | `127.0.0.2:18651` | `ark.ap-southeast.bytepluses.com:443` |
| `hermes-runtime-mmmeta.service` | `127.0.0.3:18652` | `api.z.ai:443` |

The Squid config defines two `http_port` listeners in one process, gates
access by `myportname`, exact `dstdomain -n` host (without a leading dot),
method CONNECT and destination port 443. The `-n` flag prevents an IP-literal
CONNECT target from matching a vendor hostname through a reverse-DNS/PTR
lookup. An attacker-controlled PTR record is not a vendor identity. It denies non-CONNECT, all other
ports, private/loopback destinations and every unmatched request. There
are **no generic allow-lists, wildcard domains, open forward HTTP
requests, TLS interception, CA injection or bearer token handling** in
the proxy. The Hermes native client continues verifying HTTPS TLS itself.
Squid cannot see encrypted HTTP bodies or bearer values inside CONNECT.

The default proxy is still a **trusted host component** and can make
remote TCP connections to the approved vendors. A config file, or a
passing syntax test, does not prove that a running Squid instance actually
uses it, or that the host prevents a malicious local client from crossing
proxy sockets.

## Admin admission (separate authorization)

The network and release owner must first reconcile all of these:
required GitHub exact-head checks and binding release approvals for #1917,
#1952 and #1961, plus this host proxy config and route prerequisite; no unapproved duplicate
proxy process; independently verified cgroup/eBPF enforcement on the actual
host and all parent slice `IPAddressAllow` policies. The Ubuntu1 user manager
was observed not to enforce its IP firewall; a root-managed system service
running the role unprivileged needs separate qualification (see #1966).
Do not activate either model on the strength of unit text or parser success.

Ubuntu package installation can start the stock `squid.service`, whose
localhost proxy can bypass the intended vendor restriction. Inventory its
users and ownership first: **do not stop it without its owner's authorization**.
If another product depends on it, hold this host cutover until the network
owner supplies a separate, verified boundary. The commands below apply only
to the authorized dedicated Hermes host, not to an arbitrary shared proxy.

After authorization, the *intended* host operator sequence—not an instruction
to execute from this source review—is:

```sh
# Work from the reviewed, released checkout on Ubuntu1.
# Requires sudo/admin and has production host effects; do NOT run until approved.
set -eu
# Reconcile any existing stock-proxy consumers before the authorized cutover.
sudo systemctl disable --now squid.service && sudo systemctl mask squid.service
sudo install -d -o root -g root -m 0755 /usr/local/libexec
sudo install -o root -g root -m 0644 ops/hermes_egress/role_loopback.py /usr/local/libexec/mastermind-hermes-loopback.py
sudo install -m 0644 ops/hermes_egress/squid.conf /etc/squid/hermes-byok.conf
sudo install -m 0644 ops/hermes_egress/hermes-egress.service /etc/systemd/system/hermes-egress.service
sudo squid -k parse -f /etc/squid/hermes-byok.conf
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-egress.service
```

Squid is a distro-managed prerequisite; the system service runs
`/usr/sbin/squid -N` as its existing unprivileged `proxy` account.
Systemd provides protected `/run/hermes-egress` and
`/var/log/hermes-egress` directories. **Do not install** a second
unrelated proxy or expose port 3128/other public interfaces. If the host
has an existing company-approved proxy that can enforce the identical
contract, reconcile it first instead of blindly adding this unit.

The custom unit also declares `Conflicts=squid.service` and orders itself
`After=squid.service`: starting the custom unit cannot legitimately leave
the conflicting stock unit running. The persistent mask protects against
subsequent distro-service activation. Neither declaration proves that port
3128 (or another arbitrary proxy) is absent: inspect actual listening sockets,
process ownership and config, and run the negative probes below after
installation and on any relevant service/package change. Never unmask the
stock proxy while relying on Hermes' shared 127.0.0.1 gateway allowance.

## Actual acceptance falsifiers

The operator must collect timestamps, unit/cgroup IDs and destination
proofs for both roles. The test must be **run inside each real
`hermes-runtime-ROLE.service` cgroup**, not merely in an interactive
Ubuntu shell:

1. A no-credential CONNECT to the assigned vendor from the own proxy
   must reach Squid and obtain a proxy tunnel, with TLS certificate
   verification by the client. An admitted vendor destination still
   does not prove a model API key works.
2. A CONNECT to the **other role's** allowed vendor/port through the
   own proxy must be forbidden; all non-CONNECT methods, unwanted
   domains, subdomains, IP literals, private/link-local destinations,
   and alternate ports must be denied. The IP-literal negative case must
   include a controlled PTR record naming an allowed vendor; an ordinary
   IP address with no matching PTR does not exercise the former bypass.
3. Trying the **sibling proxy socket itself** from within the role's
   cgroup must be denied. Check the other proxy really is listening
   first, or a connection-refused result may be a false positive.
4. Any direct public IP:443 connection, including a bypass with
   environment proxy variables unset, must be denied by effective
   cgroup policy. If the kernel/parent service manager ignores or
   overrides `IPAddressDeny=any`, neither role is qualified.
5. Both proxies must be observed as loopback-only bindings with exactly
   the reviewed active config, not a different global distro Squid
   configuration or wildcard listener. Verify logs disclose only
   CONNECT host/port/time, never tokens. Preserve ability to disable
   this unit and return both role services to blocked state.
6. From **each actual role cgroup**, a CONNECT through `127.0.0.1:3128`
   and through **any other non-gateway loopback listener** must fail to
   establish an external tunnel. Confirm the stock unit is stopped and
   masked, inventory all listeners, and verify their ownership and protocol.
   A permitted 127.0.0.1/32 address permits every port on that address; the
   absence of a broad forwarding service is a mandatory host condition,
   not something this address filter or a successful vendor call proves.

**Source tests are not those receipts.** CI runs static ACL tests plus
the distro Squid parser; it never binds sockets or sends network requests.
Passing CI means `CONFIG_PARSE_QUALIFIED`, *not* `PROVEN_HOST_NETWORK_POLICY`,
`PROVIDER_AUTHENTICATED`, `SLACK_ROUNDTRIP` or `DEPLOYED`.
Actual authorized role models/keys, two distinct Slack bot apps and
original-parent Agent Dialogue transport remain separate acceptance gates.

## Rollback

The approved host operator may stop the proxy system service and leave
the two confined bot units **unable to reach vendor models** while
preserving their state/credentials:
`sudo systemctl stop hermes-egress.service`.
Do not replace this with an unrestricted network exception or share keys.
Keep the stock proxy masked during fail-closed rollback; restoring a shared
stock service requires a separate owner-approved plan with both Hermes
roles stopped and their network exposure reconciled.
Any model call whose reply is missing remains effect-unknown until its
original operation is reconciled; do not replay it just because a proxy
or service was restarted.

Sources: https://www.squid-cache.org/Doc/config/acl/ ;
https://www.squid-cache.org/Doc/config/http_access/ and
https://www.squid-cache.org/Doc/config/http_port/ ; systemd
https://www.freedesktop.org/software/systemd/man/257/systemd.resource-control.html .

Unit conflict/ordering: https://www.freedesktop.org/software/systemd/man/257/systemd.unit.html .


## Fixed loopback source prerequisite

Final role units allow only their own `/32` in both directions. Linux's ordinary
`127/8` route can choose `127.0.0.1` for an unbound client connecting to
`127.0.0.2` or `127.0.0.3`. That source can break the role's own backend health
request. Explicit ephemeral binding and widening the role address policy are
not remedies: the existing Landlock and cgroup restrictions remain unchanged.

`role_loopback.py` belongs to this existing proxy owner. It exclusively adds
exactly two local-table, host-scope, static routes on `lo`: `127.0.0.2/32` with
preferred source `127.0.0.2`, and `127.0.0.3/32` with preferred source
`127.0.0.3`. It never replaces or flushes routes, configures interfaces, starts
services, or accepts destinations, binaries, paths or commands from a caller.
The normal `127.0.0.0/8` route is observed before and after and preserved.

The existing unit invokes the fixed root-installed helper as an `ExecCondition`
using `/usr/bin/python3 -I -S`. Systemd's per-command `+` permits this command's
root network administration without changing the main Squid process's user,
capability set, `NoNewPrivileges`, or address-family restrictions. This prefix
does not bypass inherited cgroup-wide restrictions. The helper returns 78 on
refusal; a condition refusal skips startup rather than entering the unit's
`Restart=on-failure` loop. No automatic rollback or `ExecStopPost` is installed.
Normal proxy stop/restart preserves acknowledged routes.

The helper validates its fixed root-owned file and ancestors, the actual host
boot/machine/network-namespace identity, an up loopback interface, and a
universal first local-table rule. Its fixed unbound `ip route get` queries do
not supply a source or force an output interface. Exit-zero ensure means
**SOURCE_SELECTION_QUALIFIED** in that host lookup context. It does not mean
role cgroup/Landlock isolation, provider connection, or a successful model turn.
Actual role service-context proof is still required before activating models.

### Custody and interruption behavior

`/run/mastermind-hermes-network` is root-owned mode 0700, separate from the
proxy-owned `/run/hermes-egress`. It contains one stable root-only lock inode
and one root-only receipt. Each route has its own durable preimage, dispatch,
acknowledgement and postimage. The receipt binds the helper source digest and
current host/boot/network-namespace epoch. A copied old-boot receipt refuses;
normal `/run` cleanup on reboot allows a new generation only when both routes
are actually absent. Matching routes without a current receipt are external,
even when they have protocol `static`; they are never silently adopted.

Before every new route effect, both roles must be stopped with no remaining
unit processes. The proxy must also be stopped, or this helper must be its
sole `ExecCondition` process. Do not run another network writer concurrently.
The helper lock coordinates this helper only: it is not a kernel CAS against
NetworkManager or another privileged administrator replacing identical routes.
Host cutover admission must reconcile those writers and cached role sockets.

An add/delete intent is fsynced before the command, its actual acknowledgement
before the result is claimed. A lost acknowledgement remains unresolved even
if a matching route or absence is observed. `ensure` never blindly repeats an
issued operation. A partially successful pair is retained; there is no exception
handler that removes the first route. A failed source lookup after acknowledged
creation preserves known ownership but blocks startup.

After a failure, inspect the original receipt and fixed `status` result. The
explicit `reconcile` verb can settle a **durably acknowledged** operation whose
exact postimage is present; it cannot infer ownership from an unacknowledged
matching route. It never issues a route command. Preserve an unresolved receipt
and original process evidence for the existing release/effect owner; do not
remove the receipt, copy one from another boot, or restart repeatedly to clear it.

### Explicit route rollback

Stopping `hermes-egress.service` remains the normal fail-closed operational
rollback and leaves both routes intact. If removing these routes is explicitly
needed, first stop both role units and the proxy, reconcile every pending effect,
then use the same installed helper's fixed `rollback` verb. It deletes only
acknowledged owned routes whose complete current attributes match the receipt,
in reverse order, with durable delete intent, acknowledgement and absence
readback. A foreign, replaced or uncertain route is never deleted. The receipt
is retained; `ensure` refuses to silently reopen that rolled-back transaction.
A later re-enablement requires the release owner to preserve the terminal
receipt and authorize a fresh generation, with all live routes reconciled.

Primary behavior references:
https://www.freedesktop.org/software/systemd/man/257/systemd.service.html
(`ExecCondition`, per-command `+`), and the iproute2 `ip-route(8)` specification
(`src`, `route get`, and exact route deletion attributes). The qualified isolated
Linux source-selection experiment is recorded in
https://github.com/mastermindx-market-intelligence/Mastermind/pull/1966#issuecomment-6656001374 .
