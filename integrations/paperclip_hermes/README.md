# Paperclip finite credentials for Hermes

Status: qualified source candidate; not installed in the live Hermes fleet.
The fleet baseline is delivered in Mastermind PR #2399, merge
`dee7a38a1e184e38cdcdd75889223d5b0ec27414`. This follow-up addresses the
credential gap observed in the original Product task, MAS-2. The task reached
real Hermes model/tool execution, but Paperclip's temporary API and runtime-tool
credentials were removed by Hermes' ordinary client-environment filter.

## Existing owners

Paperclip issues the temporary credentials and remains their authorization
server. Hermes' local session creation, private launch-key custody, staged
publication, finite admission, terminal dispatch and retirement remain the
execution owners. The existing plugin manager owns registration. OMH and
Capacity Fabric remain the memory and model-provider owners.

The standalone plugin contains a declarative `plugin.yaml` and an ID-only
registration function. The generic extension has no Paperclip credential names,
company IDs, URL, provider-account choice, network client, scheduler or persistent
secret store. Its forwarded and withheld environment destinations are rejected if native
provider, adapter or internal-runtime metadata already owns them. The native SecretSource
interface is per-home fetch/cache; it does not carry a private client launch
payload or a finite-admission retirement hook and cannot supply this boundary.

## Supported execution path

1. The Paperclip adapter explicitly supplies the nonsecret marker
   `HERMES_REQUIRED_LAUNCH_BINDING=paperclip-run`. The plugin must already be
   installed and enabled for the launch and served profile.
2. The CLI uses native manifest precedence and enable/disable gates to read the
   declaration before importing plugin code or starting a plugin host. It
   validates issuer context, expiry, exact destination names and same-origin
   runtime-tool URL. Reading JWT claims is not signature authentication;
   Paperclip still validates the token on every API request.
3. The gateway must advertise `finite-launch-credentials-v1` and the private
   `launch_credentials_v1` create parameter. A missing plugin, old gateway or
   resumed session refuses the launch before a prompt is submitted.
4. The local creation owner consumes the private field before policy, receipts
   or launch-request projection. It binds the enabled plugin owner/spec digest,
   client context, profile, principal, session, instance and owner epoch. Durable
   policy contains fingerprints, context/spec digests, expiry and run identity.
5. Native transaction publication releases losing/rolled-back grants. The
   finite executor claims one admission and generation; denied or duplicate
   claims cannot revoke another active admission's grant.
6. Only a live synchronous tool dispatch supplies the private values to the
   local terminal environment. Native code-cell RPC can reuse its active outer
   dispatch; persistent Python kernels do not receive the values. Completion,
   failure, cancellation, expiry or owner retirement closes access through the
   Hermes lease. Paperclip remains responsible for issuer-side token expiry and
   revocation.

The installed Paperclip producer issues a 48-hour API JWT and, when available,
a one-hour runtime-tools token. The required API credential sets the maximum
lease lifetime; the optional runtime token is removed independently at its own
expiry. Expired values cannot be reacquired from copied execution contexts.
Already expired inputs are refused at admission. No issuer expiry is extended.

Paperclip also supplies a persistent agent-identity private key. The manifest
declares `PAPERCLIP_AGENT_PRIVATE_KEY` as withheld: it is excluded from child
environments and never collected into the private launch payload. Paperclip
keeps that identity's custody. This extension does not implement identity-key
signing or private-key delivery to Hermes.

First support is local, in-process, finite execution. Managed workers, remote
terminal backends, background terminal jobs, delegated/forked sessions, kanban,
safe mode and user-config bypass are refused for credential-bearing execution.
This does not disable those features for ordinary unbound Hermes sessions.

## Privacy and profile isolation

The plugin manifest contains metadata only. Private values are not placed in
prompts, ordinary `client_env`, profile YAML or `.env`, plugin-host environments,
daemon environments or a new credential service.

The first ambient metadata lookup freezes a names-only witness for the launch
process: native launch-home identity, required binding, plugin owner/spec digest
and exact credential-name set. Subsequent changes refuse before spawning a
child. Removal follows `get_routing_process_hermes_home()`, even when a child
uses another profile. Exact-name removal occurs before and after native profile
overlays. Ownership classification uses the launch profile and a finite
reentry guard: provider metadata cannot recursively start a child and bypass
validation. Server classification retains the existing session owner scope.
Plugin hosts retain the incumbent `hermes_subprocess_env` filtering
and authorized ambient-provider overlay.

Exact values are redacted before tool middleware/observers, transforms,
canonical history, events, logs and spill paths, independently of the optional
display-redaction flag. Shell snapshot exclusions are monotone across the run.
Pre-binding WebSocket frame logs and validation errors do not echo private
request values. Deferred execution contexts cannot reacquire retired tool scope.
Expiry prevents subsequent injection; it cannot erase an environment copy
already delivered to a running subprocess. The issuer still enforces expiry.

## Source and qualification

`build_overlay.py` renders constrained changes against an explicit source tree
into a distinct output directory. It refuses missing, ambiguous or already
changed anchors, parses every rendered Python file, and records before/after
SHA256 values in `overlay-manifest.json`. It does not install, start, restart,
select a gateway or change the source tree passed to it.

```sh
python build_overlay.py --source /absolute/hermes/source --output /distinct/output
```

The recorded qualification base is Hermes
`ba4ddf9945a213ede9dda016602a86591ed634f9`. Its native PM built the test
environment. Native tests were run through `scripts/run_tests.sh`, with isolated
home/runtime directories and file retries disabled. The generated gateway
contracts were regenerated from their canonical owner during qualification.

| Verification | Result |
| --- | --- |
| Generic credential/lease behavior | 15 passed |
| Native creation, plugin registration, finite execution, startup privacy | 34 passed |
| Real dispatch, terminal/snapshot, nested scope and logging privacy | 7 passed |
| Existing manifest and plugin-host/provider-auth compatibility | 48 passed |
| Existing gateway CLI compatibility | 14 passed |
| Generated gateway contract and profile-history checks | 4 passed |
| Total native qualification on the composed source | 122 passed |
| Mastermind manifest/edge contract and readiness fixtures | 16 passed |

The final 122 distinct cases use 88 unchanged passing cases from the main
qualification plus the affected gateway file's focused rerun (34 passes).
That rerun corrected a fixture's assumption about native metadata traversal
count; the privacy refusal already worked. No duplicate cases are added.

The earlier broader compatibility run recorded 144 passes and six platform
skips. Its three `test_session_client_env.py` failures reproduced on the untouched
base in the same macOS qualification environment. An introduced finite-wrapper
typo was corrected and the actual finite-executor test now passes. An archive
version fixture was made explicit; this did not change Hermes version policy.
The actual installed-source qualification preserves 85 other changed/new source
files. Its existing generated contracts were first reproduced exactly from the
unmodified canonical inputs, then regenerated with the extension. No installed
runtime file was changed.

Native `scripts/check` ran all 14 checks. Twelve pass, including health with
zero blocking/advisory findings. Footguns (3 findings) and Ruff (13 findings)
still fail identically on the installed baseline. This is a failing overall
check, not a waived or green release gate; unrelated source was not altered.
Two narrow health annotations protect fixed safe logging/metadata failures
from leaking private exception values. See the
[qualification evidence](../../ops/paperclip_fleet/evidence/2026-11-10-credential-qualification.json)
for exact source hashes, commands, baseline findings and limits.

Native test placement:

| Candidate file | Hermes qualification path |
| --- | --- |
| `tests/test_launch_credential_binding.py` | `tests/agent/test_launch_credential_binding.py` |
| `tests/test_launch_credential_gateway.py` | `tests/gateway/test_launch_credential_gateway.py` |
| `tests/test_launch_credential_tools.py` | `tests/tools/test_launch_credential_tools.py` |

Mastermind's `tests/test_paperclip_hermes_integration.py` checks the real
Paperclip manifest and pure finite-credential contract in its own CI. Those
checks do not substitute for the native Hermes integration suite or live fleet
acceptance.

## Release and remaining acceptance

Publish through the existing source controls. Compose against the actual installed
source in an owned artifact; preserve existing dirty changes. Before application,
verify all before-hashes and the current native gateway identity, writer custody
and active work. The recorded 04:34:02 UTC observation has eight active units
(four chats, one in-process cron job, three managed units), including an unsafe
cron marked wedged; this is not quiescence proof. Use the incumbent lifecycle owner only after its work is safe to
drain. Do not use a whole-source auto-stash/update as a file installer, hot-patch
running imports, or start a second gateway.

After the core capability is installed and read back, install/enable the plugin
through the native plugin owner and set the required-binding marker through the
Paperclip adapter's existing configuration owner. Do not enable the marker on an
old gateway. No token value belongs in either configuration.

Retry the reconciled original MAS-2 once against the changed capability. Required
acceptance remains authenticated same-issue return, a permitted runtime-tool
call, actual Capacity Fabric route/accounting evidence, OMH marker write/read,
second-run/profile isolation and representative leadership skill materialization.
An adapter exit code, model answer, source merge or successful static test does
not establish those outcomes.
