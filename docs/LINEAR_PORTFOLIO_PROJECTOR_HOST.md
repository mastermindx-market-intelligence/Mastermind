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

The root/config directories are root-owned mode `0750`; the non-secret config is mode `0640`; the secret file is mode `0600`. Existing, symlinked, wrong-owner, wrong-mode or otherwise ambiguous state is a refusal. Enrollment is create-once and never overwrites or blindly retries an uncertain write.

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
