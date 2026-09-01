# Linear Portfolio Projector MAS-64 H0 — Host Credential Boundary

**Date:** 2026-08-28  
**Owner:** Sol, AI CEO  
**Chairman authority:** Chris directed Sol to repair Linear / Slack / GitHub synchronization end to end.  
**Linear:** MAS-188, child of MAS-64 / MAS-27  
**Operating-surface wave:** OSC-L1  
**Authority:** architecture/source law only. This document does not create a Linear OAuth app, credential, token, project mutation, daemon, scheduler, webhook, Executive Job, Worker, queue or lifecycle state.

## 1. Outcome

Before MAS-64 can create and prove the dedicated `Mastermind Portfolio Projector` Linear app actor, the Chairman's Mac needs one deterministic native host boundary that can accept the OAuth client secret without exposing it to ChatGPT, Slack, GitHub, argv, environment variables, shell variables, logs, temporary files or another product's credential store.

H0 makes that boundary buildable and testable. It remains manual-canary infrastructure only. MAS-64 still owns real app creation, app attribution and the isolated Linear create/read/update/no-op/conflict/cleanup canary. MAS-66 still owns projects-only P1. OSC-C1 still owns any later selected wave/gate issue/comment projection.

## 2. Canonical ownership / no-rebuild law

- Linear OAuth app identity and scopes: Linear / MAS-64 receipt.
- Organizational portfolio truth: Agent OS.
- Project mutation semantics: MAS-66 after prerequisites.
- Runtime Job/Attempt/Worker/Event: Executive OS — untouched.
- Secret bytes: fixed local H0 private file only; they are never organizational/runtime truth.

H0 MUST NOT:

- store the projector secret under `/Library/Application Support/MastermindExecutive`;
- reuse `scripts/mas115_keychain_store.py` or its fixed Multilogin Keychain coordinates;
- introduce a generic secrets manager, Keychain abstraction, credential database, daemon, launchd job, scheduler, queue, cursor, token cache or retry store;
- put a client secret or access token in repository files, Linear comments, Slack, Agent OS, environment variables or command arguments;
- expose a caller-selectable secret path.

## 3. Fixed host coordinates

V1 coordinates are compile-time constants in the H0 helper:

```text
ROOT        = /Library/Application Support/MastermindPortfolioProjector
CONFIG_DIR  = /Library/Application Support/MastermindPortfolioProjector/config
CONFIG_PATH = /Library/Application Support/MastermindPortfolioProjector/config/projector.json
SECRET_PATH = /Library/Application Support/MastermindPortfolioProjector/config/oauth-client-secret
```

The root is deliberately separate from MastermindExecutive because the projector is a portfolio integration, not an Executive runtime authority.

V1 is manual administrator / canary only. Files are therefore `root:wheel`; no projector Unix service account is created before continuous/scheduled execution is separately authorized.

Required filesystem state:

- `ROOT` and `CONFIG_DIR`: real directories, owner UID 0, GID 0, mode `0750`, no symlink;
- `CONFIG_PATH`: regular file, one link, UID 0/GID 0, mode `0640`, no symlink;
- `SECRET_PATH`: regular file, one link, UID 0/GID 0, mode `0600`, no symlink;
- enrollment uses `O_CREAT|O_EXCL` and `O_NOFOLLOW` where available; existing/ambiguous state is refusal, never overwrite;
- writes fsync file + parent; partial/ambiguous writes are not retried blindly.

## 4. Non-secret config contract

`projector.json` is exact schema `mastermind.linear_projector_host.v1` and contains only non-secret identity/config facts:

```json
{
  "schema": "mastermind.linear_projector_host.v1",
  "app_name": "Mastermind Portfolio Projector",
  "client_id": "<Linear OAuth client id>",
  "workspace_id": "93bfb3d6-93f1-48a8-9720-aa653cba4335",
  "team_id": "26b5bb87-2482-4f8f-a42f-955250bd9eaf",
  "team_key": "MAS"
}
```

`client_id` is non-secret but must be bounded ASCII and recorded exactly. Workspace/team constants are current canonical MAS-64 targets. A future workspace/team change is a source-law update, not a caller parameter.

No redirect URI, access token, refresh token, client secret, browser cookie or personal actor identity is written here.

## 5. Secret input law

Enrollment accepts the client secret only from stdin.

- Native TTY: echo is disabled before read and restored afterward.
- Non-TTY is allowed only for hermetic tests; production operator guidance requires a native hidden prompt.
- Secret must be one trimmed bounded UTF-8/ASCII line, 1–4096 bytes, no whitespace/control characters/newline within the value.
- No secret-shaped value may appear in argv or environment. The helper scans obvious Linear/OAuth/Authorization secret surfaces and refuses before any write.
- stdout/stderr use fixed opaque receipts and never echo input or exception text containing caller values.

## 6. Commands

One module under `ops/linear_projector/host_enrollment.py` exposes only:

```text
prepare
  create/check ROOT + CONFIG_DIR only; no credential

enroll --client-id <NON_SECRET_ID>
  require prepared safe directories, read one hidden secret from stdin, create CONFIG_PATH and SECRET_PATH exactly once

verify --expected-client-id <NON_SECRET_ID>
  read-only filesystem/config verification; never read or emit secret contents
```

`prepare` and `verify` are safe without a real app. `enroll` is a native administrator ceremony and must not be executed until MAS-64 creates the app.

No `rotate`, `delete`, generic `--path`, generic `--service`, token exchange or network operation exists in H0 V1. Rotation/revocation remains an explicit MAS-64 administrator action so V1 cannot overwrite ambiguous credentials.

## 7. Verification receipt

Successful commands print one exact non-secret line:

```text
LINEAR_PROJECTOR_HOST_PREPARED
LINEAR_PROJECTOR_CREDENTIAL_ENROLLED
LINEAR_PROJECTOR_CREDENTIAL_BOUNDARY_VERIFIED client_id_sha256=<hex>
```

The hash is over the non-secret client ID only and is a correlation receipt, not authentication.

Failure prints exactly one fixed code from a closed vocabulary and returns non-zero. At minimum:

- `PROJECTOR_HOST_ARGUMENTS_REFUSED`
- `PROJECTOR_HOST_SECRET_SURFACE_REFUSED`
- `PROJECTOR_HOST_PREPARE_REFUSED`
- `PROJECTOR_HOST_INPUT_REFUSED`
- `PROJECTOR_HOST_COLLISION`
- `PROJECTOR_HOST_WRITE_REFUSED`
- `PROJECTOR_HOST_CONFIG_REFUSED`
- `PROJECTOR_HOST_PERMISSIONS_REFUSED`
- `PROJECTOR_HOST_CLIENT_ID_MISMATCH`
- `PROJECTOR_HOST_INTERNAL`

No exception string is forwarded.

## 8. Tests / falsifiers

Hermetic tests use temporary roots by dependency injection/internal helpers; public CLI coordinates stay fixed. Tests must prove:

1. production constants never point into MastermindExecutive or MAS-115 Keychain paths;
2. prepare creates exact directory modes/owners under injected test owner and refuses symlink/collision/unsafe mode;
3. secret in argv/env refuses before stdin read/write;
4. TTY/no-echo reader restores terminal state on success and failure;
5. malformed/oversize/whitespace secret refuses;
6. enrollment writes secret bytes exactly once with mode `0600`, config separately with mode `0640`, fsyncs, and refuses existing final files;
7. verify never reads secret contents (metadata only) and catches link count/type/owner/group/mode/config/client-ID mismatch;
8. stdout/stderr never contain provided secret or arbitrary exception text;
9. caller cannot select a path or convert the helper into a generic secret writer;
10. zero network imports/calls and zero Executive/Linear mutation.

## 9. Acceptance

MAS-188 architecture may merge records-only after exact-head CI and review.

Implementation is `BUILT_NOT_PROVEN` when the helper passes hostile tests and can prepare/verify a fixture boundary. It becomes accepted H0 only after a native host dry ceremony proves `prepare` on the Chairman Mac and MAS-64 later uses the same helper for a real hidden enrollment/verify receipt without ChatGPT observing secret bytes.

That native real enrollment does **not** by itself complete MAS-64; MAS-64 still owes app identity/scopes/team restriction and the isolated Linear canary.

## 10. Continuation

After H0 implementation is accepted and MAS-65 P0 is merged, the one external Chairman/admin action is to create the private `Mastermind Portfolio Projector` OAuth app from the MAS-64 pre-populated form, restrict it to team MastermindX, then run the H0 native `enroll` ceremony locally with the client secret hidden. Return only non-secret client/app IDs and the exact H0 receipt.
