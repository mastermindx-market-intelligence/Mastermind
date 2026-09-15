# Business Sol HC0 Host-Context Probe Runbook

## Capability boundary

HC0 exposes exactly one read-only tool:

```text
inspect_surface_context({})
```

It returns pseudonymous correlation evidence for documented ChatGPT request metadata. Each identifier has an app-local `fingerprint`, separated by app realm and generation, plus a `comparison_fingerprint` for the controlled cross-app experiment. Neither value is reversible or usable for authorization. The tool does not return raw host identifiers and cannot authenticate Chris, assign Sol/worker responsibility, create a RuntimeBinding, admit an Executive Job, mutate Mastermind OS, or authorize another tool.

Account availability, plugin import, app registration, tunnel connection, tool delivery, OAuth, RuntimeBinding, Executive admission, worker execution, production proof and final operational cutover are separate gates.

## Two-account topology

Use the two concurrent Business Premium accounts as a canary/control pair. Do not merge, migrate or disable either account merely to run HC0.

- **Account A — canary:** primary HC0 development and same-conversation repeat testing.
- **Account B — control:** cross-principal and organization-boundary testing. Do not share Account A credentials, cookies, tokens, browser profile or app registration.

For the cross-app experiment, create two separate private HC0 app registrations, `surface-probe-a` and `surface-probe-b`. They may temporarily share one probe-cohort HMAC key solely so `comparison_fingerprint` equality can be tested without exposing raw host values. The comparison domain binds the exact result schema, `cross_app_comparison` purpose, fingerprint scope, key ID, key version, field and raw value while excluding app realm and generation. The app-local `fingerprint` retains realm and generation separation. The key and both fingerprint forms grant no authority, and the key must be rotated or destroyed after the experiment.

## Exact source and dependency prerequisite

Use one exact reviewed HC0 branch head that already contains the accepted A1 Task-1 floor:

```text
mcp==1.28.1
PyJWT[crypto]==2.13.0
```

Do not run the registered-surface canary against the historical `mcp==1.28.0` HC0 head. The local source head, app generation and contract digest belong in every receipt.

## Local prerequisites

- Python 3.11 or newer;
- repository dependencies installed from the exact reviewed branch;
- Secure MCP Tunnel or another approved private HTTPS transport;
- one randomly generated secret of 32–256 bytes encoded as standard or URL-safe base64;
- no production Executive, Agent OS, Slack, Linear, GitHub, RuntimeBinding or credential write access.

## Generate the temporary cohort key

Run locally in a trusted terminal:

```bash
python3 - <<'PY'
import base64
import secrets
print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("="))
PY
```

Place the value into a secret-owning local environment or service manager. Do not paste it into ChatGPT, Slack, Linear, GitHub, issue comments, PR bodies, screenshots, shell history, logs or experiment receipts.

## Configure and validate App A

```bash
export MASTERMIND_SURFACE_PROBE_APP_REALM=surface-probe-a
export MASTERMIND_SURFACE_PROBE_APP_GENERATION=hc0-a-g1
export MASTERMIND_SURFACE_PROBE_TRANSPORT_PROFILE=secure-mcp-tunnel-readonly
export MASTERMIND_SURFACE_PROBE_HMAC_KEY_ID=hc0-cohort
export MASTERMIND_SURFACE_PROBE_HMAC_KEY_VERSION=v1
export MASTERMIND_SURFACE_PROBE_FINGERPRINT_SCOPE=hc0-cross-app-probe
export MASTERMIND_SURFACE_PROBE_HMAC_KEY='<out-of-band base64url key>'
export MASTERMIND_SURFACE_PROBE_HOST=127.0.0.1
export MASTERMIND_SURFACE_PROBE_PORT=8011
export MASTERMIND_SURFACE_PROBE_MCP_PATH=/mastermind-surface-probe/mcp
```

Validate configuration and inspect the secret-free contract:

```bash
python3 scripts/run_mastermind_surface_probe.py --check-config
python3 scripts/run_mastermind_surface_probe.py --describe \
  > /tmp/mastermind-surface-probe-a.json
```

Start the loopback server:

```bash
python3 scripts/run_mastermind_surface_probe.py
```

The process binds only `127.0.0.1`. The MCP endpoint is fixed at:

```text
http://127.0.0.1:8011/mastermind-surface-probe/mcp
```

The approved private HTTPS tunnel is the outer transport. A tunnel is transport, not authentication or Mastermind authority.

The historical `scripts/mastermind_surface_probe.py` path is a compatibility wrapper to the same canonical entrypoint. New setup should use `scripts/run_mastermind_surface_probe.py`.

## Configure and validate App B

Use a separate process and separate Business/browser context. Change only the app-local generation and loopback port. Reuse the temporary cohort key only for this controlled cross-app falsification:

```bash
export MASTERMIND_SURFACE_PROBE_APP_REALM=surface-probe-b
export MASTERMIND_SURFACE_PROBE_APP_GENERATION=hc0-b-g1
export MASTERMIND_SURFACE_PROBE_PORT=8012
python3 scripts/run_mastermind_surface_probe.py --check-config
python3 scripts/run_mastermind_surface_probe.py
```

The second local endpoint is:

```text
http://127.0.0.1:8012/mastermind-surface-probe/mcp
```

App B must use a separately registered private app identity and a separately authenticated Business principal. Reusing one app registration or one browser login does not test cross-app or cross-principal behavior.

## Private app registration

For each app registration:

1. Point the private developer-mode app to the corresponding approved HTTPS tunnel URL ending exactly in `/mastermind-surface-probe/mcp`.
2. Confirm the listed tool inventory is exactly `inspect_surface_context`.
3. Confirm the input schema is an empty closed object and the output schema identifies `mastermind.host_context_probe.v1`.
4. Confirm no resource, prompt, sampling, elicitation, task, write, OAuth or generic administration capability appears.
5. Record exact app identity, app generation, server version, contract digest, source head, endpoint identity and Business account role.
6. Do not grant a write scope merely because the platform offers one.
7. When a tool or schema changes, create a new immutable app generation and re-review it; do not treat a mutable label as the accepted contract.

Importing a plugin, seeing a tool or connecting a tunnel does not authenticate the caller or grant Mastermind authority.

## Live experiment matrix

For every row, record `PROVEN`, `DISPROVEN` or `UNKNOWN`. Never copy raw host metadata.

| Test | Account | App | Conversation condition | Compare |
|---|---|---|---|---|
| Same-app repeat | A | A | two calls in one conversation | local `fingerprint` for session/subject/org |
| New conversation | A | A | new conversation | old versus new local session `fingerprint` |
| Fork | A | A | fork existing conversation | parent versus fork local session `fingerprint` |
| Refresh | A | A | refresh same conversation | local `fingerprint` before versus after |
| Tunnel restart | A | A | restart local server/tunnel | local `fingerprint` before versus after |
| App generation | A | A-v2 | new immutable generation | behavior and domain-separated local `fingerprint` change |
| Cross-app | A | A then B | same conversation if host permits both | A versus B `comparison_fingerprint` only under shared cohort key |
| Cross-principal | B | B | equivalent steps in Account B | local subject and organization `fingerprint` separation |
| Organization boundary | A/B | A/B | another organization if available | `comparison_fingerprint` only when comparing different apps; otherwise local `fingerprint` |
| Metadata absence | A/B | A/B | host omits optional field | explicit absence/degradation |

Both fingerprint forms are correlation evidence only. Equality does not establish authority; inequality does not justify a fallback Business-session database. Never compare app-local `fingerprint` values across different realms or generations: construction requires them to differ. Cross-app experiment rows compare only `comparison_fingerprint` under the same temporary key ID, key version, scope and secret.

## Receipt template

```text
schema: mastermind.business_sol_hc0_receipt.v1
source_head:
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
app_local_fingerprint_result: equal | unequal | unavailable | not_applicable
comparison_fingerprint_result: equal | unequal | unavailable | not_applicable
claim_state: PROVEN | DISPROVEN | UNKNOWN
raw_host_values_captured: false
runtime_binding_created: false
canonical_system_mutation: false
evidence_refs:
```

Receipts must not contain the HMAC key, raw host IDs, tokens, cookies, email addresses, browser profiles, private endpoint secrets or prompt transcripts.

## Failure handling

- Missing metadata: record explicit absence; do not guess.
- Malformed metadata: the tool refuses with a fixed bounded error; do not retry with model-supplied identity.
- Tool inventory or digest drift: stop and compare exact app/server/source generation.
- Raw value in output or logs: stop, revoke/rotate the cohort key, quarantine the artifact and treat it as a security incident.
- Tunnel/server timeout: the call is read-only; retry only against the same exact generation. No host claim is proven until a valid response arrives.
- Cross-app `comparison_fingerprint` mismatch under the exact same key ID, key version, scope and secret: record `DISPROVEN`; do not substitute app-local `fingerprint` or create another session registry.
- App/account ambiguity: record `UNKNOWN`; do not infer which principal was active.
- Public bind or noncanonical path request: configuration must refuse before serving.

## Stop and cleanup

HC0 stops before RuntimeBinding or modifying authority.

After completing the matrix:

1. stop both local servers and tunnels;
2. remove temporary registrations no longer required;
3. destroy or rotate the probe-cohort HMAC key;
4. preserve only sanitized receipts;
5. record exact platform discoveries and the next architecture decision in the canonical durable system;
6. do not promote a modifying app generation from HC0 evidence alone.

## Promotion gate

HC0 may authorize the separately reviewed RuntimeBinding surface seam only when relevant correlation claims are supported by real Business receipts. It does not itself authorize plugin installation, OAuth, Executive admission, Company Dialogue write, Mastermind OS mutation or operational cutover.
