# Hermes BYOK vendor CONNECT egress — host operator deployment candidate

**SOURCE-ONLY; not installed.** This is **one existing Squid 6/7 data-plane
process**, configured with two fixed, role-specific listeners and no model
keys. It consumes the host network policy in PR #1961; it is **not** a new
agent, scheduler, admission service, queue, identity store or retry engine.
The Ubuntu1 network owner must inspect and independently approve the host
side before enabling any real bot.

## Fixed contract

| Source unit | Exact proxy socket | Only CONNECT destination |
| --- | --- | --- |
| `hermes-runtime-mmsecretary.service` | `127.0.0.2:18651` | `ark.ap-southeast.bytepluses.com:443` |
| `hermes-runtime-mmmeta.service` | `127.0.0.3:18652` | `api.z.ai:443` |

The Squid config defines two `http_port` listeners in one process, gates
access by `myportname`, exact `dstdomain -n` host (without a leading dot),
method CONNECT and destination port 443. Both vendor ACLs disable reverse-DNS
lookups: a numeric CONNECT target cannot qualify through a vendor-shaped PTR
record. This is hostname-only matching, not an assumption about vendor TLS. It denies non-CONNECT, all other
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
approved GitHub exact-head checks and independent review on #1917,
#1952 and #1961, plus this host proxy config; no unapproved duplicate
proxy process; Ubuntu1's actual systemd user-unit cgroup/eBPF support,
and all parent slice `IPAddressAllow` policies.

After authorization, the *intended* host operator sequence—not an instruction
to execute from this source review—is:

```sh
# Work from the reviewed, released checkout on Ubuntu1.
# Requires sudo/admin and has production host effects; do NOT run until approved.
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
   and alternate ports must be denied.
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
Any model call whose reply is missing remains effect-unknown until its
original operation is reconciled; do not replay it just because a proxy
or service was restarted.

Sources: https://www.squid-cache.org/Doc/config/http_access/ and
https://www.squid-cache.org/Doc/config/http_port/ ; systemd
https://www.freedesktop.org/software/systemd/man/257/systemd.resource-control.html .
