# Ubuntu3 — first unattended T3 fleet host: user-space install recipe

**Status: RECIPE ONLY — not executed by the Rev 5 T3 lane (2026-11-08/09).**
Nothing below was installed, started, paired or armed by this lane. The steps
are user-space and require **no sudo** on ubuntu3; every precondition below was
verified read-only by the T3 census (`mmos/T3_CENSUS.md` §4–§5).

**Why ubuntu3 (192.168.8.245, user `ubuntu3`):**
- `loginctl` linger is **already enabled** → a systemd *user* service survives
  logout with no sudo step (the only Linux sudo contingency in T3's own docs
  is enabling lingering — already done fleet-wide by WO-15a).
- Full toolchain already present: node v24.21.0, pnpm 12.8.1, dsh 0.2.1-rc.2,
  291 GB free disk. Hermes runtime already paved (WO-15a READY).
- Not M2 → keeps build load off the control-plane host (plan l.182), and M2's
  T3 is the macOS desktop app, which is login-session-bound (stops on logout —
  `docs/user/background-service.md:90-93`), i.e. NOT an unattended owner.

## Steps (all under `~/.local` / `~/.t3`; no sudo, no system changes)

```sh
# 1. Install the release CLI (user-space; per docs/user/install.md)
curl -fsSL https://t3.codes/install.sh | sh
#    -> t3 CLI at ~/.local/bin/t3 (print PATH line if needed)

# 2. Background service: systemd USER service; lingering already on
t3 service install
t3 service status   # expect: running / enabled / linger-ok

# 3. Access for the Executive adapter (order of preference):
#    a. ON-HOST adapter (localhost:3773) — credentials may cross localhost.
#    b. Tailscale HTTPS — note: M2->tailnet IPv4 TCP is currently broken
#       (WO-15a); IPv6 tailnet SSH verified working. Use IPv6 or LAN+SSH
#       tunnel until the M2 route fix lands.
#    c. `t3 up` / T3 Connect — not a prerequisite for this build.
#    NEVER plain-HTTP LAN for credential-bearing sign-in
#    (docs/user/outside-agents.md:26-29: OAuth needs https or localhost).

# 4. Pair one outside agent ONCE (then 30-day sign-ins):
t3 auth pairing create          # pairing code; complete OAuth at
                                # https://<address>/mcp (or localhost /mcp)
#    Choose the LOWEST sufficient mode. Native Auto/Read-only is NOT company
#    authorization — the adapter enforces the project/root boundary (plan l.418).

# 5. DSH via Local ACP (when the DSH lane qualifies it):
#    Create a NON-managed dsh profile first (shipped `desktop`/`web` profiles
#    refuse CLI/ACP boot; `dsh --help` grammar requires a profile NAME):
dsh plugin --profile <name> add <package>
#    Then add the Local ACP provider with THREE argument rows
#    (the two-row doc example omits the required profile name):
#      executable: dsh
#      rows: --profile | <name> | acp
```

## Honest operating conditions (do not paper over these)

- Linux logout survival **requires** the user-service lingering — verified on.
- One server per data dir (`~/.t3`); default port 3773; `T3CODE_HOST/PORT`
  via `~/.t3/service.env`.
- Do not restart/update the service underneath active jobs (plan §3 l.178).
- Catalog visibility is not readiness: `orchestrator_capabilities` listing a
  provider does not mean its account/credits work (live finding on M2: the
  `codex` instance was listed but out of credits; the free `opencode_opencode1`
  lane was listed but stalled in delivery). Qualify with ONE real launch+read
  before counting the host ready — exactly what `T3EnvironmentProjection`
  records (`launch_eligible` stays False until every capability is observed
  `ready` and fresh).

Donor attribution: T3 Code (github.com/pingdotgg/t3code)
@0770446869d247a8b28c27d7ed93f47f8ff0c1e4 — install/service/auth behavior per
`docs/user/install.md`, `docs/user/background-service.md`,
`docs/user/outside-agents.md`, `docs/user/providers-acp.md` at that pin.
