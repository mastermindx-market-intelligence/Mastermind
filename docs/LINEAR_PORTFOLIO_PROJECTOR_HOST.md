# Mastermind Portfolio Projector — Native Host Credential Boundary

This document describes the fixed manual host ceremony for the `Mastermind Portfolio Projector` OAuth client.

The boundary is intentionally separate from Mastermind Executive OS and from every personal ChatGPT/Claude/Grok credential. It is a local administrator prerequisite only: it performs **no OAuth/token exchange** and **no Linear mutation**.

## Fixed production location

The helper owns only:

```text
/Library/Application Support/MastermindPortfolioProjector
/Library/Application Support/MastermindPortfolioProjector/config/projector.json
/Library/Application Support/MastermindPortfolioProjector/config/oauth-client-secret
```

The root/config directories are `root:wheel` (UID/GID `0:0`) mode `0750`; the non-secret config is mode `0640`; the secret file is mode `0600`. Existing, symlinked, wrong-owner, wrong-group, wrong-mode or otherwise ambiguous state is a refusal. Enrollment is create-once and never overwrites or blindly retries an uncertain write.

On macOS, `/Library/Application Support` is commonly `root:admin`. A new child directory can inherit its `admin` group even under `sudo`. The helper corrects the group **only on the directory inode it just created**, using a no-follow directory descriptor, then verifies exact `root:wheel 0750` ownership/mode. It never changes an existing mismatched directory, its children, or any credential file.

## Administrator ceremony

Run these commands on the native Mac terminal only:

```bash
sudo python3 -m ops.linear_projector.host_enrollment prepare
sudo python3 -m ops.linear_projector.host_enrollment enroll --client-id <NON_SECRET_CLIENT_ID>
sudo python3 -m ops.linear_projector.host_enrollment verify --expected-client-id <NON_SECRET_CLIENT_ID>
```

`prepare` creates/checks only the fixed directories. It does not create a credential.

`enroll` reads exactly one bounded secret line from stdin and disables terminal echo while reading from a native TTY. The Linear client secret must be entered only into that hidden native prompt. **Never paste or transcribe the secret into ChatGPT, Slack, GitHub, Linear descriptions/comments, Agent OS, shell command arguments, environment variables, screenshots, logs, notes or checked-in files.**

`verify` validates directory/config/secret metadata and the expected non-secret client ID. It never reads or emits the secret contents. Its correlation hash is SHA-256 of the non-secret client ID only; it is not authentication.

## If `prepare` refuses on an existing directory

`REFUSED: PROJECTOR_HOST_PERMISSIONS_REFUSED` can mean a previous, partially completed `prepare` left an existing `root:admin 0750` directory. **Do not repeatedly enroll or overwrite credentials.** An administrator must inspect the exact projector directory and children using metadata-only tools before any repair. Only when the directory is conclusively a root-owned, empty `0750` projector directory, with no config or credential files, may the administrator make a **non-recursive group-only** correction to `wheel` and run `prepare` once more. Recheck the source helper's exact permission contract afterwards. If any directory contains unknown files, ACLs or an enrolled credential, stop and reconcile rather than changing permissions, deleting files, or performing a second enrollment.

The `LINEAR_PROJECTOR_HOST_PREPARED` receipt proves only prepared directories. It is **not** a credential, OAuth app, authorized token or app-attributed canary.

## Exact non-secret receipts

Successful commands emit only one of:

```text
LINEAR_PROJECTOR_HOST_PREPARED
LINEAR_PROJECTOR_CREDENTIAL_ENROLLED
LINEAR_PROJECTOR_CREDENTIAL_BOUNDARY_VERIFIED client_id_sha256=<64hex>
```

Failures emit only:

```text
REFUSED: <closed_error_code>
```

Exception text and input values are never forwarded.

## What this does not authorize

This boundary does not create the Linear app, install an OAuth integration, exchange a code/token, refresh a token, call the Linear API, create/update a project, create a daemon/scheduler/launchd job, or create a generic secret manager.

The next real action belongs to MAS-64: after this host boundary is accepted, a workspace administrator creates the private `Mastermind Portfolio Projector` app with the reviewed least-privilege project-only authorization, then uses the hidden `enroll` ceremony above. Only non-secret app/client identity and the opaque verification receipt return to Sol.
