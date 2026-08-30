# Business Sol HC0 Host-Context Probe Runbook

## Capability boundary

HC0 exposes exactly one read-only tool:

```text
inspect_surface_context({})
```

It returns pseudonymous correlation evidence for documented ChatGPT request metadata. It does not return raw host identifiers and cannot authenticate Chris, assign Sol/worker responsibility, create a RuntimeBinding, admit an Executive Job, mutate Mastermind OS, or authorize another tool.

Account upgrade, app connection, tool delivery, OAuth, RuntimeBinding, Executive admission, worker execution, and final operational cutover are separate gates.

## Two-account test topology

Use the two Business Premium accounts as an explicit canary/control pair:

- **Account A — canary:** primary HC0 development and same-conversation repeat testing.
- **Account B — control:** cross-principal and organization-boundary testing. Do not share Account A credentials, cookies, tokens, or browser profile.

For the cross-app experiment, create two separate private HC0 app registrations, `surface-probe-a` and `surface-probe-b`. They may temporarily share one probe-cohort HMAC key solely so equality can be tested without exposing raw host values. The key grants no authority and must be rotated or destroyed after the experiment.

Do not merge or migrate existing ChatGPT accounts merely to run HC0. Preserve current sessions and use the two Business accounts concurrently.

## Local prerequisites

- exact reviewed Mastermind branch/head;
- Python 3.11 or newer;
- repository dependencies including the pinned MCP SDK and Uvicorn;
- Secure MCP Tunnel or another approved private HTTPS transport;
- one randomly generated 32-byte-or-longer HMAC key;
- no production Executive, Agent OS, Slack, Linear, GitHub, RuntimeBinding, or credential write access.

## Generate the temporary cohort key

Run locally in a trusted terminal:

```bash
python3 - <<'PY'
import base64, secrets
print(base64.b64encode(secrets.token_bytes(32)).decode())
PY
```

Do not paste the result into ChatGPT, Slack, Linear, GitHub, issue comments, PR bodies, screenshots, shell history, logs, or experiment receipts.

## Configure App A

```bash
export MASTERMIND_SURFACE_PROBE_APP_REALM=surface-probe-a
export MASTERMIND_SURFACE_PROBE_APP_GENERATION=hc0-20260829-a
export MASTERMIND_SURFACE_PROBE_TRANSPORT_PROFILE=secure-mcp-tunnel-readonly
export MASTERMIND_SURFACE_PROBE_HMAC_KEY_ID=hc0-cohort
export MASTERMIND_SURFACE_PROBE_HMAC_KEY_VERSION=v1
export MASTERMIND_SURFACE_PROBE_FINGERPRINT_SCOPE=hc0-cross-app-probe
export MASTERMIND_SURFACE_PROBE_HMAC_KEY_B64='<out-of-band base64 key>'
```

Validate without exposing the key:

```bash
python3 scripts/mastermind_surface_probe.py --check-config
python3 scripts/mastermind_surface_probe.py --describe > /tmp/hc0-schema.json
```

Start the loopback server:

```bash
python3 scripts/mastermind_surface_probe.py \
  --host 127.0.0.1 \
  --port 8765 \
  --path /mcp
```

The local process intentionally cannot bind `0.0.0.0` or a public interface. The approved private tunnel is the outer transport.

## Configure App B

Run a second isolated process and browser/account context:

```bash
export MASTERMIND_SURFACE_PROBE_APP_REALM=surface-probe-b
export MASTERMIND_SURFACE_PROBE_APP_GENERATION=hc0-20260829-b
# Reuse the same temporary probe-cohort key only for this falsification exercise.
python3 scripts/mastermind_surface_probe.py --host 127.0.0.1 --port 8766 --path /mcp
```

App B must use a separately registered private app identity and a separately authenticated Business principal. Reusing one app registration or one browser login does not test cross-app or cross-principal behavior.

## Private app registration

For each app registration:

1. Enable only the exact private developer-mode app.
2. Point it at the corresponding approved HTTPS tunnel endpoint ending in `/mcp`.
3. Confirm the listed tool inventory is exactly `inspect_surface_context`.
4. Confirm no resource, prompt, sampling, elicitation, task, write, OAuth, or generic administration capability appears.
5. Record app identity, generation, server version, contract digest, endpoint identity, and account role in the experiment receipt.
6. Do not grant a write scope merely because the platform offers one.

Importing a plugin, seeing a tool, or connecting a tunnel does not authenticate the caller or grant Mastermind authority.

## Live experiment matrix

For every row, record `PROVEN`, `DISPROVEN`, or `UNKNOWN`. Never copy raw host metadata.

| Test | Account | App | Conversation condition | Compare |
|---|---|---|---|---|
| Same-app repeat | A | A | two calls in one conversation | session/subject/org fingerprints |
| New conversation | A | A | new conversation | old versus new session fingerprint |
| Fork | A | A | fork existing conversation | parent versus fork session fingerprint |
| Refresh | A | A | refresh same conversation | before versus after |
| Tunnel restart | A | A | restart local server/tunnel | before versus after |
| App generation | A | A-v2 | republish/new generation | behavior and expected domain-separated change |
| Cross-app | A | A then B | same conversation if host permits both | A versus B under shared cohort key |
| Cross-principal | B | B | equivalent steps in Account B | subject and organization separation |
| Organization boundary | A/B | A/B | another organization if available | organization fingerprint separation |
| Metadata absence | A/B | A/B | host omits optional field | explicit absence/degradation |

A fingerprint is correlation evidence only. Equality does not establish authority; inequality does not justify a fallback session database.

## Receipt template

```text
schema: mastermind.business_sol_hc0_receipt.v1
app_realm:
app_generation:
server_version:
contract_digest:
fingerprint_key_id:
fingerprint_key_version:
fingerprint_scope:
business_account_role: canary | control
condition:
observed_at:
host_field_presence:
comparison_result: equal | unequal | unavailable | not_applicable
claim_state: PROVEN | DISPROVEN | UNKNOWN
raw_host_values_captured: false
runtime_binding_created: false
canonical_system_mutation: false
evidence_refs:
```

Receipts must not contain the HMAC key, raw host IDs, tokens, cookies, email addresses, browser profiles, private endpoint secrets, or prompt transcripts.

## Failure handling

- Missing metadata: record explicit absence; do not guess.
- Malformed metadata: the tool refuses with a fixed bounded error; do not retry with model-supplied identity.
- Tool inventory drift: stop and compare the exact app/server generation.
- Raw value appears in output or logs: stop, revoke/rotate the cohort key, quarantine the artifact, and treat as a security incident.
- Tunnel or server timeout: this is a read-only call; retrying is harmless only after confirming the same app generation. It still proves no host behavior until a valid response arrives.
- Cross-app mismatch: record `DISPROVEN`; do not create another session registry.
- App/account ambiguity: record `UNKNOWN`; do not infer which principal was active.

## Stop and cleanup

HC0 stops before RuntimeBinding or modifying authority.

After completing the matrix:

1. stop both local servers and tunnels;
2. remove the temporary app registrations if they are no longer needed;
3. destroy or rotate the probe-cohort HMAC key;
4. preserve only sanitized receipts;
5. record the exact platform discoveries and next architecture decision in the canonical durable system;
6. do not promote a modifying app generation from HC0 evidence alone.

## Promotion gate

HC0 may authorize planning of the RuntimeBinding surface seam only when the exact relevant host-correlation claims are supported by real Business receipts. It does not itself authorize plugin installation, OAuth, Executive admission, Company Dialogue write, Mastermind OS mutation, or operational cutover.
