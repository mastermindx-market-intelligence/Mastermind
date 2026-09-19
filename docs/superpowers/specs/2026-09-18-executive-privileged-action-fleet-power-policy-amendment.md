# Executive Privileged Action Broker — Fleet Power Policy Amendment

**Status:** source candidate under Chairman-authorized Fleet #644 production integration.  
**Operation:** `fleet-secondary-host-power-policy-20260918-sol-001`.  
**Protected base:** `55473bb43c3ae1908f53ddd4ccfe724643dd6c69`.

## Narrow precedence

This amendment changes only the closed privileged-action catalog count in the
2026-09-13 broker design/plan. Their statements that V1 exposes "exactly six"
effect actions are superseded by one additive seventh action. All existing
request/status schemas, peer authentication, exact installed-release execution,
idempotency, receipt, `EFFECT_UNKNOWN`, no-retry, no-generic-shell, credential,
service and lifecycle laws remain unchanged.

The closed catalog adds:

| Action | Effect class | Arguments | Root implementation |
|---|---|---|---|
| `executive.host.prepare_secondary_power_policy` | `HOST_POWER_POLICY` | none | exact installed `ops/executive_os/secondary_host_power_policy.py` |

No caller may supply a host, path, executable, argv, power setting, value or
scope. Physical host selection and Fleet placement remain owned elsewhere.

## Exact effect

The installed helper may execute only this fixed charger/AC mutation:

```text
/usr/bin/pmset -c sleep 0 autorestart 1
```

It then performs one fixed readback:

```text
/usr/bin/pmset -g custom
```

Success requires the readback's `AC Power` section to contain exactly the two
load-bearing #829 predicates:

- `sleep == 0`;
- `autorestart == 1`.

The helper consumes the existing strict `pmset -g custom` parser owned by
`ops/executive_os/host_recovery_readiness.py`. It emits only a bounded,
secret-free receipt. It never emits raw `pmset` output.

The `-c` scope is deliberate: this capability prepares an always-available
secondary fleet host while leaving battery power policy unchanged on portable
Macs. `autorestartatconnect` remains advisory because #829 does not require it.

## Safety and effect semantics

The existing privileged broker remains the only mutation owner. A request is
content-addressed by its stable request id before effect. Transport loss after
admission remains `EFFECT_UNKNOWN`; the caller uses the existing status path
and never retries or fails over blindly.

The helper:
- refuses when not running as root;
- has no CLI arguments;
- uses absolute `pmset` paths, a closed environment, no shell and bounded time/output;
- refuses if the mutation command fails;
- refuses if post-write observation is unavailable, malformed or does not prove
  both required predicates.

This is not a generic power-management capability, installer, host selector,
scheduler, retry plane or second privileged broker.

## Fleet integration boundary

The first intended production canary is `admins-Mini-652`, whose latest
read-only #829-compatible observation already proves AC `sleep=0` and currently
fails on `autorestart=0`. Source acceptance does not authorize direct
worktree/root execution: production proof still requires this exact source to be
merged, installed through the existing exact-release privileged-broker owner,
then invoked non-root through `mmx-admin`, followed by a fresh #829 read-only
preflight.

The MacBook remains a later candidate; charger-only `sleep=0` preserves its
battery sleep policy.

## Acceptance

Source acceptance requires:
1. closed action validation and fixed installed argv;
2. caller-argument refusal;
3. root-before-effect refusal;
4. mutation-before-readback ordering;
5. failure on wrong/missing postconditions;
6. existing six actions remain backward compatible;
7. broker/client receipt correlation and `EFFECT_UNKNOWN` behavior unchanged;
8. hosted owning tests and repository gates pass.

Real capability proof requires the mini's fresh #829 projection to change from
its current power-policy failure to a passing power predicate after one
receipt-backed invocation through the installed privileged broker.
