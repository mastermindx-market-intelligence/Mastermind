# Executive Capacity CF2-P0 — read-only installed-host census

**Observed at:** `2026-08-26T02:58:56Z`
**Owner:** Sol, AI CEO
**Chairman:** Chris
**Status:** **P0 COMPLETE / NO SAFE CF1 ACQUISITION PATH / CF2-I HELD**
**Protected Mastermind and Skillpack basis:** `31523ee9c40d9dedaadf73d5caeafad657dcd193`
**Accepted CF2-F source law:** Mastermind PR #150 / merge
`e9cb5cbd745b36dc51f54bd83238ec38ef0c80c7`
**Accepted Macro CF1:** candidate `fc12904f59a5758817aa2c76ffaa40bb1ebcbf8e` /
merge `dcdd939c45b23abce5ba04f95e330ac914a3904b`
**Host reference:** `local-unbound`
**Mutation count:** zero

Protected master advanced after observation only through the disjoint Cursor/Grok records law in
PR #154. It changes no P0 host surface, CF1 source contract, worker installation or Skillpack blob.

---

## 0. Closed result

The exact CF2-P0 result is:

```text
NO_SAFE_CF1_ACQUISITION_PATH
```

This is the terminal refusal defined by accepted CF2-F. It creates no
`mastermind.executive_capacity_p0_acceptance/v1` object, no acceptance digest and no fabricated
source/release/material identity. It releases no CF2-I-A, CF2-I-B or CF2-I-C implementation.

The current Mac has useful Executive Phase 1C remnants and user-owned Macro checkouts, but it has
neither:

1. an existing bounded Macro-owned process/API with a frozen local projection protocol; nor
2. a root-owned exact-commit grounded CF1 Git release usable by `_mastermind_exec`.

Treating a user checkout, a dirty CI workspace, the old Mastermind release bundle or a stale socket
as the accepted source would violate the one-producer, grounding, ownership and ambiguity laws.

---

## 1. Read-only method and redlines

The census inspected only:

- installed launchd plist metadata and launchd service presence;
- path type, owner, group, mode, ACL summary, size and existence;
- local user/group membership;
- process/socket presence without sending a request;
- Git commit/worktree metadata for candidate Macro checkouts;
- exact executable hashes and exact file presence;
- protected GitHub/Macro commit ancestry already accepted by the program.

The census did **not**:

- open, parse, hash or copy any `auth.json`, token, cookie, Keychain item or provider response;
- traverse the Chairman's ordinary Codex configuration as a credential source;
- call Codex, Claude, Grok, Cursor or any provider;
- run the CF1 producer under another principal;
- start/stop/kickstart a service or connect to an Executive socket;
- create a user/group/home/socket/config/release;
- change a permission, ACL, group membership, environment, file, database or launchd state;
- arm routing, create an Attempt/Event, claim a Job or run a worker.

---

## 2. Installed Executive topology

### 2.1 Installed release and configuration

The installed Executive plists point to Mastermind release:

```text
/Library/Application Support/MastermindExecutive/releases/
  b5e45be20a752b689e08a88d15816ef26fb2c45c
```

Observed boundary:

| Surface | Sanitized observation | P0 interpretation |
|---|---|---|
| Release directory | `root:wheel`, mode `0755` | Root-owned, but it is the old Phase 1C Mastermind release, not Macro CF1 |
| Control config | `root:_mastermind_exec`, mode `0440`, 1,565 bytes | Existing control config; contents were not used as a CF1 protocol |
| Worker config | `root:_mastermind_worker`, mode `0440`, 941 bytes | One legacy worker config only |
| Python | `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12` | Present; SHA-256 `d4f152f2a753c94e0e7935c8ebbe6b2609979e1df7898422b577d0076383d08b` |
| CF1 wrapper | absent from installed release | Cannot execute accepted producer |
| CF1 engine module | absent from installed release | Cannot execute accepted projection |
| Git metadata | absent from installed release | Cannot satisfy CF1 material/audit grounding |

The installed release therefore is not a grounded Macro source and cannot be upgraded by inference.

### 2.2 launchd and socket state

Installed plist files exist for:

```text
com.mastermind.executive.control
com.mastermind.executive.worker.codex
```

At observation time neither label was present in the system launchd domain. No matching Executive
process or open Unix-socket owner was observed. Filesystem socket nodes still existed at the control
and worker paths. They are stale/ambiguous artifacts, not proof that a service or broker is live.

No request was sent to either socket, and P0 does not attempt repair.

### 2.3 Principal and worker-realm state

The installed principal inventory contains only:

```text
_mastermind_exec   uid/gid 450
_mastermind_worker uid/gid 451
```

There are not three distinct Codex worker principals. The sole worker plist uses
`_mastermind_worker`, one broker socket and the configured logical realm `codex-01`.

Observed topology facts:

- `_mastermind_exec` currently has the legacy `_mastermind_worker` artifact group as a
  supplementary group, as the accepted Phase 1C workspace boundary requires;
- the worker root contains only `codex-01`;
- `codex-01` is `_mastermind_worker:_mastermind_worker`, mode `0700`;
- its configured `provider-home` path was absent at observation time;
- no `codex-02` or `codex-03` worker realm, home, config, socket or service exists.

The `0700` owner-only `codex-01` directory still prevents group-based traversal, so P0 does not claim
that credential material was readable. The shared `_mastermind_worker` artifact group is not one of
the three Personal Pro primary groups and is not itself a CF2-F violation. The blockers are that the
three dedicated users/groups/homes are not installed and therefore no negative control-membership or
traversal proof exists for `_mastermind_codex_01`, `_mastermind_codex_02` and
`_mastermind_codex_03`. Host preparation must keep `_mastermind_exec` outside those three Pro groups
while preserving only the separately reviewed legacy artifact boundary.

---

## 3. Candidate Macro source census

### 3.1 Existing Macro process/API

No installed service, socket, fixed request schema or exact release/config binding was found for an
existing Macro process that emits strict `mastermind.provider_capacity.v1` to Executive.

Result:

```text
EXISTING_MACRO_PROJECTION_PATH_ACCEPTED = false
```

Discovery of a Python module in a checkout is not an existing process/API contract.

### 3.2 Installed grounded exact-Git source

No root-owned installed Macro checkout containing all of the following was found:

- exact accepted CF1 release `dcdd939c45b23abce5ba04f95e330ac914a3904b`;
- `scripts/build_provider_capacity.py`;
- `engine/provider_capacity.py` and every material source;
- intact `.git` metadata required by CF1 audit/material grounding;
- root-owned immutable installed configuration and fixed working directory.

Result:

```text
GROUNDED_CF1_GIT_RELEASE_PATH_ACCEPTED = false
```

### 3.3 Rejected lookalikes

| Candidate | Observation | Rejection reason |
|---|---|---|
| Chairman Macro checkout | Current user-owned development checkout | Not root-owned installed release; mutable user workspace |
| CI runner 2 workspace | User-owned, dirty, commit `612b3df2eaee904613525c31a12a36a9759b42d9` | Wrong release, dirty, mutable runner workspace |
| CI runner 3 workspace | User-owned, dirty, commit `8cf08e5d19bbe28590fd62b3be0847ad3e7a637d` | Wrong release, dirty, mutable runner workspace |
| CI runner 4 workspace | User-owned, dirty, commit `612b3df2eaee904613525c31a12a36a9759b42d9` | Wrong release, dirty, mutable runner workspace |
| Installed Mastermind release | Root-owned release `b5e45be...` | Different repository/release; CF1 wrapper, engine and Git metadata absent |
| Stale Executive sockets | Nodes present without loaded labels/process owners | Not a producer; effect/state ambiguous |

None is copied, re-permissioned or treated as evidence of a safe source.

---

## 4. Fixed three-home and telemetry findings

No root-owned installed `CODEX_ACCOUNT_HOMES` inventory for exactly three dedicated worker homes was
found. The one legacy worker realm does not supply three immutable Macro capability positions.

No root-owned, source-law-bound secret-free telemetry configuration was found for the accepted CF1
producer. User/CI checkout telemetry cannot be silently reused because its owner, release, mutability
and lifecycle are outside the accepted acquisition identity.

P0 therefore does not construct a source config, inventory digest, telemetry digest or P0 acceptance
digest. Doing so would turn absence into fabricated readiness.

---

## 5. Capability ledger after P0

| Capability | State | Exact meaning |
|---|---|---|
| CF2-F source law | `SPEC_ONLY` | PR #150 merged; architecture law is current on protected master but no runtime exists |
| Existing Macro projection path | `NOT_BUILT` | No frozen installed local process/API |
| Grounded CF1 Git release | `NOT_BUILT` | No root-owned exact accepted checkout with Git metadata |
| Three worker principals | `NOT_BUILT` | Only one shared `_mastermind_worker` exists |
| Three provider homes | `NOT_BUILT` | Only one configured path, absent at observation time |
| `capacity-observe/v1` | `NOT_BUILT` | Legacy worker broker has no accepted operation |
| Capacity-aware atomic claim | `NOT_BUILT` | CF2-I remains held |
| Three Personal Pro credentials | `DARK_OR_DISCONNECTED` | Prior ceremonies are not accepted here; P0 inspected no credential bytes |
| Live Executive service | `DARK_OR_DISCONNECTED` | Plists/socket nodes are installed, but no launchd label, process or live-service acceptance was observed |
| Cursor/Grok provider routes | `SPEC_ONLY` | Separate source-law carrier; no auth or runtime enablement |

Repository acceptance, installed state, authentication and live runtime proof remain separate claims.

---

## 6. Sol continuation ruling

P0 does not authorize CF2-I on this host. The next bounded program node is **CF2-H0 grounded-source
and three-principal host preparation**. It must remain on one carrier and prove, in order:

1. a root-owned, non-group/other-writable exact Macro CF1 Git checkout retaining its `.git` metadata;
2. one root-owned closed source config for the exact Python, entrypoint, working directory,
   environment-name allowlist, three-home inventory and secret-free telemetry identities;
3. three distinct worker users/groups, homes, configs, sockets and launchd services using the existing
   broker implementation family;
4. proof that `_mastermind_exec` is outside all three dedicated Personal Pro groups plus negative
   traversal proof, while preserving only the separate Phase 1C artifact-group boundary;
5. no credential copy during host preparation; each empty private realm receives credentials only
   through a later bounded native ceremony;
6. installed-host verification and rollback receipts before CF2-I-A is released.

The implementation must extend the current Phase 1C installer/broker/config surface. It may not add
another service family, credential store, queue, database, provider normalizer or lifecycle.

Only an exact installed-host PASS may rerun P0 and produce a lawful
`GROUNDED_CF1_GIT_RELEASE_PATH_ACCEPTED` record. Until then:

```text
CF2-I = HOLD
RF1/HF1 executable work = dependency-held
live provider routing = HOLD
three-seat fan-out/failover = HOLD
OAuth/device ceremonies = HOLD
```

Research, deterministic fixtures, installer tests and secret-free staging may proceed without
claiming host acceptance.

---

## 7. Stop receipt

This census completed with zero filesystem, service, credential, provider, database, routing or
runtime mutations. Its durable truth is the refusal itself:

```text
NO_SAFE_CF1_ACQUISITION_PATH
```

The next carrier must begin from the exact host-preparation mission in Section 6; it must not retry
CF1 acquisition against the same unchanged unsafe estate.
