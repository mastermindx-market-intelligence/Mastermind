# Final-role isolation qualification kit

**Status: SOURCE-ONLY. Nothing is installed, activated, provisioned or proven on a
host by this document.** This is the runbook and the exact input/output contract
for `integrations/hermes_runtime/isolation_probe.py`, a credential-free one-shot
host qualification utility. It does not change the `NO INSTALL / DO NOT DEPLOY`
posture of [ROLE_ISOLATION_REPAIR.md](ROLE_ISOLATION_REPAIR.md) or
[ROOT_CONFINED_SYSTEM_UNIT.md](ROOT_CONFINED_SYSTEM_UNIT.md).

Source baseline: Mastermind `b10dce8892a3bba10a8115a266c8d8ad71ddf7ac`
(the reviewed head of #1966). The kit imports the production guards from that
baseline and copies none of them.

---

## 1. What this kit is for

`ROLE_ISOLATION_REPAIR.md` requires, verbatim, that "actual host qualification
requires zero skips, then the same negative matrix inside both final PID1 role
cgroups, plus synthetic cross-role file denial", and that "the authorized
account owner must prove synthetic sibling-file reads are denied from both
actual service contexts".

This kit is that negative matrix, expressed as a bounded, reviewable, one-shot
probe plus a runbook. It is deliberately **not** a runtime component: it is not
a model tool, not a controller, not a queue, not a daemon, not an identity
registry and not a permission plane. It runs once, prints one JSON report and
exits.

### What it does

* Reuses the four production guards, **in their production order**, so that the
  observed identity, cgroup, private paths and TCP policy are the production
  ones rather than a re-implementation:
  `assert_root_service_cgroup` → `assert_role_network_profile` →
  `assert_role_credential_isolation` → `enforce_role_tcp_ports`.
* Executes the negative matrix **inside one existing final role service
  context**: the role's own `systemd` unit cgroup, the role's own NSS account,
  the role's own private paths and the role's own unit hardening.
* Uses synthetic credential-free fixtures only: loopback TCP listeners it binds
  itself, and synthetic text files it reads. It never reads a real credential,
  never calls a provider, never touches Slack and never performs a canary or a
  text turn.

### What it does not do

* It does not install, enable, start, stop, restart, reload or edit a unit.
* It does not create an account, change a firewall or an authentication
  setting, load a secret, or instantiate `ServiceRuntime`.
* It does not qualify the incumbent `hermes-egress.service` proxy, the vendor
  CONNECT allowlists, TLS, provider billing, the Slack round trip or a
  cutover. A synthetic listener is **not** the proxy and is never offered as
  proxy proof.
* It does not qualify UDP or Unix-domain isolation; the production TCP policy
  is TCP-only and this kit does not widen that claim.

---

## 2. The roles under qualification

| | Secretary | Meta-CEO |
|---|---|---|
| Role / account | `mmsecretary` | `mmmeta` |
| Unit | `/etc/systemd/system/hermes-runtime-mmsecretary.service` | `/etc/systemd/system/hermes-runtime-mmmeta.service` |
| Expected cgroup | `/system.slice/hermes-runtime-mmsecretary.service` | `/system.slice/hermes-runtime-mmmeta.service` |
| Allowed address | `127.0.0.2/32` | `127.0.0.3/32` |
| Gateway (bind+connect) | `8765` | `8865` |
| Backend (bind+connect) | `8766` | `8866` |
| Proxy (connect only) | `18651` | `18652` |

Landlock, for `mmsecretary`, therefore permits TCP **bind** on `{8765, 8766}`
and TCP **connect** on `{8765, 8766, 18651}`. The probe reads that set from the
production `role_tcp_ports()`, never from a constant of its own.

The probe takes the addresses and ports from the **loaded profile** and checks
them against the documented fixed ports above. A profile that disagrees is
reported as a `FAIL` in the `profile.fixed_ports` case, not silently accepted.

---

## 3. The matrix and its required witnesses

Every case names the witness that must exist **before** a refusal may be
counted as proof. A refusal without its witness is `UNAVAILABLE`, never
`PASS`. A missing listener, an `ECONNREFUSED` and a skipped case are never
denial proof.

| Case id | Target | Expected | Witness required for a `PASS` |
|---|---|---|---|
| `profile.fixed_ports` | the loaded profile | matches the fixed role ports | the profile itself |
| `tcp.own_alias.gateway_port` | `127.0.0.2:8765` | allowed | kernel `LISTEN` entry for `127.0.0.2:8765`, **and** an unconfined connect that completed |
| `tcp.own_alias.backend_port` | `127.0.0.2:8766` | allowed | kernel `LISTEN` entry for `127.0.0.2:8766`, **and** an unconfined connect that completed |
| `tcp.sibling_alias.gateway_port` | `127.0.0.3:8765` | refused | kernel `LISTEN` entry for `127.0.0.3:8765` |
| `tcp.shared_loopback.gateway_port` | `127.0.0.1:8765` | refused | kernel `LISTEN` entry for `127.0.0.1:8765` |
| `tcp.own_alias.denied_port` | `127.0.0.2:<denied port>` | refused | kernel `LISTEN` entry for the wildcard listener on `<denied port>`, **and** an unconfined connect that completed |
| `file.own.read` | this role's synthetic file | allowed | the file's own `0600` role-owned regular-file facts and its sha256 |
| `file.peer.read` | the sibling role's synthetic file | refused | the **sibling role's own probe report**, proving that file exists in the sibling's private directory |
| `exec.own_alias.denied_port` | `127.0.0.2:<denied port>` from an exec'd descendant | refused | an exec probe that **reached** the same target before the restriction was applied |
| `exec.own_alias.gateway_port` | `127.0.0.2:8765` from an exec'd descendant | allowed | the same, proving the inherited denial is port-specific and not a blanket refusal |

`<denied port>` defaults to `45151` (`mmsecretary`) / `45152` (`mmmeta`). It must
be an unprivileged port **outside** the role's allowed set and must not collide
with the sibling role's ports; the probe refuses the run otherwise.

### How each denial is attributed

The two controls are independent and the matrix separates them on purpose.

* **Landlock restricts TCP ports.** A port inside the role's connect set is
  permitted by Landlock, so a refusal of it can only come from the unit's
  cgroup address policy.
* **The unit's `IPAddressDeny=any` / `IPAddressAllow=<role>/32` restricts
  addresses.** A port outside the role's connect set is refused by Landlock
  whatever the address is.

So `tcp.sibling_alias.gateway_port` and `tcp.shared_loopback.gateway_port` use
a **Landlock-allowed** port, which isolates the address control, and
`tcp.own_alias.denied_port` uses the role's **own** address on a
**Landlock-disallowed** port, which isolates the port control. Each case
reports `attribution` and `attribution_basis` in the report.

### Symptom distinctions are preserved

The probe never collapses a timeout into a refusal:

* `EACCES` — an immediate refusal. Landlock refuses a disallowed TCP port
  this way.
* `EAGAIN` / `ETIMEDOUT` — the bounded connect did not complete. The cgroup
  address policy blackholes the SYN, so this is the expected shape of an
  address denial, matching the transient-unit observation recorded in
  `ROOT_CONFINED_SYSTEM_UNIT.md` (errno 11).
* `ECONNREFUSED` — **not** denial proof. The case becomes `UNAVAILABLE`.
* `EPERM` — reported verbatim; it is consistent with a cgroup `connect` denial
  but the probe does not assert which layer produced it.

---

## 4. Classification vocabulary

| Field | Values |
|---|---|
| `observed` | `ALLOWED`, `REFUSED`, `UNAVAILABLE`, `NOT_RUN`, `ERROR` |
| `status` | `PASS`, `FAIL`, `UNAVAILABLE`, `NOT_RUN` |
| report `status` | `PASS`, `FAIL`, `INCOMPLETE` |
| exit code | `0` PASS, `2` (`POLICY_EXIT`) FAIL, `78` (`CONFIG_EXIT`) INCOMPLETE or a refusal, `3` (`IO_EXIT`) an I/O error |

`PASS` is granted only when every selected case is `PASS`. Any `UNAVAILABLE`,
`NOT_RUN` or `FAIL` makes the report `INCOMPLETE` or `FAIL`, and
`qualified` is then `false`. **A missing resource is never a pass.**

Every report carries a `context_fingerprint`: the sha256 of the observed host
identity, role, service context, effective cgroup, profile, private paths,
Landlock port sets and the selected matrix. A `PASS` is bound to that exact
fingerprint; a different host, account, cgroup, profile or matrix is a
different result and needs its own run.

---

## 5. Preconditions the host owner must satisfy

The probe refuses rather than degrades. Before it can run for a role:

1. **The role's NSS account exists**, with a non-zero UID and GID that differ
   from the sibling role's. The probe reads them through NSS; it never invents
   a numeric identity and never treats an account name as identity proof.
2. **The role's private paths are qualified**, and the production guard
   `assert_role_credential_isolation` accepts them:
   * `state_dir` — an absolute, non-symlinked `0700` directory owned by the
     role's UID **and** GID;
   * the secrets file's parent — likewise `0700` and role-owned;
   * every ancestor of both — owned by root or by the role, and **not**
     group- or other-writable;
   * the secrets file — a regular, single-linked, `0600`, role-owned file.

   The probe never reads the secrets file's contents; the production guard
   only `lstat`s it. An **empty** `0600` role-owned file is sufficient for the
   isolation qualification and is **not** a credential. A real secret is a
   separate, separately authorized host step.

   An ordinary writable `/tmp` ancestry is **not** private-path proof: the
   production guard rejects any ancestor with a group or other write bit, and
   the probe's report shows each ancestor's mode, owner and write bits so the
   qualification is auditable rather than asserted.

3. **The role's unit is installed and reviewed**, root-owned `0644` under
   `/etc/systemd/system/`, and `systemd-analyze verify` has passed. The unit
   must retain `After=`/`Requires=`/`BindsTo=hermes-egress.service`,
   `IPAddressDeny=any`, exactly one `IPAddressAllow=<role>/32` and **no**
   `EnvironmentFile=`.
4. **The incumbent `hermes-egress.service` exists and is approved.** It has
   **no definition in this repository**; it is host-owned. Because the unit
   `Requires=` and `BindsTo=` it, the role unit cannot start without it. A
   missing egress unit is a **preflight refusal**, not a reason to start with
   weaker isolation. The kit does not stand in for it.
5. **The pinned source checkout and the installed profile are present** at the
   unit's `PYTHONPATH` root and at `{state}/current/profile.yaml`.
6. **The synthetic fixtures exist** (see §6) and, for the cross-role file
   case, the sibling's probe report is available to this role.

---

## 6. The runbook

### 6.1 Prepare the synthetic fixtures (host owner, root)

Each role gets one synthetic file inside its own private state directory. The
content is a fixed, credential-free marker; the same marker is used by both
roles so the reports can be matched.

```sh
# mmsecretary
install -d -o mmsecretary -g mmsecretary -m 0700 \
  /home/mmsecretary/.local/state/hermes-runtime-mmsecretary/qualification
printf 'mastermind-hermes-role-isolation-qualification-synthetic-v1\n' \
  | install -o mmsecretary -g mmsecretary -m 0600 /dev/stdin \
  /home/mmsecretary/.local/state/hermes-runtime-mmsecretary/qualification/synthetic.txt

# mmmeta
install -d -o mmmeta -g mmmeta -m 0700 \
  /home/mmmeta/.local/state/hermes-runtime-mmmeta/qualification
printf 'mastermind-hermes-role-isolation-qualification-synthetic-v1\n' \
  | install -o mmmeta -g mmmeta -m 0600 /dev/stdin \
  /home/mmmeta/.local/state/hermes-runtime-mmmeta/qualification/synthetic.txt
```

Do not create these with a mode that the production private-path guard would
refuse, and never place them in a shared or world-writable directory.

### 6.2 The temporary ExecStart qualification override

The probe must run **inside the role's own service cgroup**, because
`assert_root_service_cgroup` requires
`/system.slice/hermes-runtime-<role>.service`. A transient unit
(`systemd-run --system`) has a different cgroup path and is refused by the
production guard. The supported route is therefore a **temporary, explicit
ExecStart override** on the role's own unit.

The override is a per-role drop-in under
`/etc/systemd/system/hermes-runtime-<role>.service.d/`. It is created, used
and then removed **and read back** before any production claim. It must never
be left in place.

```ini
# /etc/systemd/system/hermes-runtime-mmsecretary.service.d/90-role-isolation-qualification.conf
# TEMPORARY -- created for one qualification run and removed afterwards.
[Service]
ExecStart=
ExecStart=/usr/bin/python3 -P -m integrations.hermes_runtime.isolation_probe --profile /home/mmsecretary/.local/state/hermes-runtime-mmsecretary/current/profile.yaml --role mmsecretary --own-file /home/mmsecretary/.local/state/hermes-runtime-mmsecretary/qualification/synthetic.txt --peer-file /home/mmmeta/.local/state/hermes-runtime-mmmeta/qualification/synthetic.txt --peer-report /var/lib/hermes-qualification/report-mmmeta.json --report /home/mmsecretary/.local/state/hermes-runtime-mmsecretary/qualification/report-mmsecretary.json
```

Notes on the arguments:

* `--report` **must** live under the role's `state_dir`. The unit sets
  `ProtectSystem=strict` with `ReadWritePaths={state}`, so nothing outside the
  state directory is writable, and `PrivateTmp=true` makes `/tmp` and
  `/var/tmp` private to each unit instance. A report in `/var/tmp` from the
  sibling role is therefore invisible.
* `--peer-report` **must** live at a path readable by this role. The sibling's
  own state directory is `0700` and sibling-owned, so it is unreadable by
  design. The host owner copies the sibling's report to a shared, non-secret
  evidence directory (for example `/var/lib/hermes-qualification/`, mode
  `0755`, files `0644`) after the sibling's run. The report contains no
  credential, no secret value and no provider traffic.
* `--peer-file` points at the sibling's synthetic file. It is expected to be
  unreadable, and in the production layout it is unreadable at the directory
  traversal, which the probe reports precisely.

```sh
sudo systemctl daemon-reload
sudo systemctl start hermes-runtime-mmsecretary.service
sudo journalctl -u hermes-runtime-mmsecretary.service -o cat --no-pager
```

### 6.3 Three invocations cover both directions

The cross-role file case needs an **independent** witness for the sibling's
file, and only the sibling role can produce it. The protocol is therefore
three runs, not two:

| Run | Role | `--peer-report` | What it proves |
|---|---|---|---|
| 1 | `mmsecretary` | *(none)* | mmsecretary's own file is readable; the peer file case is `UNAVAILABLE` because no independent witness exists yet |
| 2 | `mmmeta` | mmsecretary's report | **mmmeta cannot read mmsecretary's file** (`file.peer.read` → `PASS`) |
| 3 | `mmsecretary` | mmmeta's report | **mmsecretary cannot read mmmeta's file** (`file.peer.read` → `PASS`) |

Between runs the host owner copies each role's report out of its private state
directory into the shared evidence directory:

```sh
sudo install -d -m 0755 /var/lib/hermes-qualification
sudo install -m 0644 \
  /home/mmmeta/.local/state/hermes-runtime-mmmeta/qualification/report-mmmeta.json \
  /var/lib/hermes-qualification/report-mmmeta.json
```

Runs 2 and 3 use the same unit drop-in shape with the role's own paths. The
`sibling_alias` and `shared_loopback` cases are exercised against the
synthetic listeners the probe binds itself, so both roles may run
concurrently for the TCP portion; the file witness chain is the only reason
the file cases need the three-run order.

### 6.4 Remove the override and read it back

```sh
sudo rm -f /etc/systemd/system/hermes-runtime-mmsecretary.service.d/90-role-isolation-qualification.conf
sudo rmdir --ignore-fail-on-non-empty /etc/systemd/system/hermes-runtime-mmsecretary.service.d
sudo systemctl daemon-reload
sudo systemctl show -p ExecStart hermes-runtime-mmsecretary.service   # read back
sudo systemctl cat hermes-runtime-mmsecretary.service | grep -c 'isolation_probe'  # expect 0
```

The readback is part of the qualification. A report whose override is still
present is not a qualification result.

---

## 7. Input/output contract

### Input

| Argument | Required | Meaning |
|---|---|---|
| `--profile` | yes | the role's installed `profile.yaml`; a path only, never a secret |
| `--role` | yes | `mmsecretary` or `mmmeta`; must equal the profile's role |
| `--own-file` | yes | this role's synthetic fixture file |
| `--peer-file` | yes | the sibling role's synthetic fixture file |
| `--peer-report` | no | the sibling's probe report; without it the peer file case is `UNAVAILABLE` |
| `--denied-port` | no | an unprivileged port outside the role's allowed set |
| `--report` | no | also write the JSON report to this path (mode `0600`) |
| `--connect-timeout` | no | bounded connect timeout, default 2 s, maximum 30 s |
| `--only` | no | comma-separated subset of case ids |
| `--list-cases` | no | print the case identifiers and exit |

### Output

One JSON document on stdout, and the same document at `--report` when given.
Top-level keys: `schema`, `tool`, `generated_at_utc`, `role`, `peer_role`,
`status`, `qualified`, `context_fingerprint`, `selected_matrix`, `context`,
`guards`, `guard_order`, `private_paths`, `listeners`, `witnesses`, `matrix`,
`counts`, `own_file`, `scope`, `limitations`.

`schema` is `mastermind.hermes_role_isolation_qualification.v1`.

The report contains no credential, no secret value and no provider or Slack
traffic. It contains paths, numeric identities, ports, modes, owners, errnos
and the matrix results. A secret value is never read, so none can leak.

### Guard failures

If any of the three observation guards refuses, the probe writes a report with
every case `NOT_RUN`, names the refusing guard and its production refusal code
(`ROOT_UNIT_CGROUP_UNQUALIFIED`, `ROLE_OS_PROCESS_IDENTITY_MISMATCH`,
`ROLE_PRIVATE_ANCESTOR_UNQUALIFIED`, `ROLE_OS_ACCOUNT_UNAVAILABLE`, …), and
exits `78`. **The TCP port policy is never applied after a refused guard**, and
no listener is ever bound in that path.

---

## 8. Host mutations this kit will require

The parent adjudicates these prospectively. The kit itself performs none of
them; it is source preparation only.

| # | Mutation | Owner | Notes |
|---|---|---|---|
| M1 | two NSS accounts with distinct non-zero UID/GID | host owner | already required by the production guards |
| M2 | per-role home, `0700` state dir, `0700` secrets parent, `0600` secrets file | host owner | the secrets file may be an empty placeholder for this qualification |
| M3 | the two root-owned units under `/etc/systemd/system/` | root operator | rendered by the existing `system_service` renderer, reviewed, `systemd-analyze verify` |
| M4 | the incumbent `hermes-egress.service` | host owner | no repository definition exists; it is a hard prerequisite of M3 |
| M5 | one temporary ExecStart drop-in per role, per run | root operator | created, used, removed and read back (§6.4) |
| M6 | the pinned source checkout and the installed profile | host owner | the profile is the unit's own `PYTHONPATH` root |
| M7 | the synthetic fixture files | host owner | credential-free marker, `0600`, role-owned (§6.1) |
| M8 | a shared, non-secret evidence directory for the copied reports | host operator | mode `0755`; contains no credential |

**M3 and M4 are the wider production activation hold.** This kit does not
weaken it, and it does not install anything. If the egress unit or the role
units are not approved and installed, the probe simply cannot run, and the
correct disposition is a preflight refusal.

---

## 9. Cleanup and rollback boundaries

* The Landlock restriction is per-process and is destroyed when the probe
  exits. It cannot outlive the run and cannot affect another process.
* The synthetic listeners are child processes of the probe. The probe reaps
  them before it exits; nothing survives it. No firewall or routing rule is
  changed at any point.
* The probe writes only its own report. It never modifies the profile, the
  secrets file, the unit, or any role state.
* Remove the drop-in and read back §6.4. Leaving a qualification override in
  place would silently replace the production `ExecStart`.
* Remove the synthetic fixtures from each role's state directory after the
  reports are archived.
* Remove the empty placeholder secrets file **only** if it is still the empty
  placeholder and no credential was ever written to it. Never delete a real
  secrets file.
* The shared evidence directory may be retained as the qualification record;
  it contains no credential.
* The role unit itself is stopped by the operator after the run. The probe
  never starts or stops anything.

---

## 10. Known limitations

* **Off-host results do not transfer.** A qualification report from any host
  other than the one that will run the production role proves nothing about
  that host. The `context_fingerprint` exists so that a result cannot be
  silently reused across a host, an account, a cgroup, a profile or a matrix.
* **A timeout is a non-completion, not a policy proof.** The address-policy
  cases accept a bounded connect that did not complete as a refusal *only*
  because the kernel reports a `LISTEN` socket on that exact address and port.
  A non-completion on a target with no listener is `UNAVAILABLE`.
* **The proxy is out of scope by design.** The proxy port is deliberately not
  exercised: a synthetic listener would not be the incumbent
  `hermes-egress.service`, and the vendor CONNECT allowlists, TLS peer
  verification, provider authentication, billing and the original-parent
  two-bot Slack round trip remain with their existing owners.
* **Landlock is TCP-only.** Unix-domain IPC and UDP are not covered by the
  production policy and are not covered here.
* **The peer-report witness is an artifact, not a cryptographic attestation.**
  It proves that the same tool, run inside the sibling role's own context,
  read the sibling's file. The operator copies it unchanged; the copy step
  is an operator obligation.
* **Both directions need both roles.** The probe qualifies one role per
  invocation. The cross-role file claim is only complete after the §6.3
  three-run protocol has been executed for both roles.
* **This is not the kernel component test.** The existing real-kernel Landlock
  component test at this baseline already passed and is not repeated here as
  a substitute for the final-role run.

---

## 11. Source artifacts

| Path | Role |
|---|---|
| `integrations/hermes_runtime/isolation_probe.py` | the probe: imports the production guards, runs the matrix, writes the report |
| `integrations/hermes_runtime/tests/test_isolation_probe.py` | unit tests: guard reuse and order, witness rules, classification vocabulary, attribution, report shape. Boundary probes are mocked; **no test claims real final-role execution** |
| `docs/hermes/FINAL_ROLE_QUALIFICATION.md` | this runbook and contract |
