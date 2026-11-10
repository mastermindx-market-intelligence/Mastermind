# Paperclip finite credentials for Hermes

Status: credential and native source checks qualified; protected delivery, live
activation and learning proof remain open. The specifically approved CodeQL
fixture alerts 272/273 are dismissed and read back as used in tests. The adopted
hygiene composition passes all 14 native checks. Shared CI and safe-cutover holds
remain in force. No live gateway capability is claimed.
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

## Memory, skills and learning

Keep the existing Hermes profiles, OMH provider and native skills. Paperclip's
installed adapter invokes `hermes chat -q`; the gateway admits this as finite
execution. Native `load_background_review_settings()` intentionally disables
automatic background review for that path, irrespective of the profile's
configured `enabled` value. That lifetime policy is preserved. Explicit auxiliary
review under a finite credential binding is outside this release's supported
execution contract; native interactive review remains a separate path.

The installed OMH provider inherits a no-op `sync_turn` hook. Its memory-write
hook journals provenance and consolidation metadata; it does not turn a built-in
file-memory write into an admitted OMH recall record. The migration therefore
uses the existing foreground `omh_remember` save/recall and `skill_manage` paths.
Managed v2 role instructions require useful durable learning before task return,
respect native admission states, preserve skill ownership and make no write when
there is no useful retained fact or procedure. No new learning daemon or memory
backend is introduced.

The instruction upgrade admits only exact role-scoped v1 SHA-256 preimages,
current v2 text or the original generic templates. Custom edits and another
role's document remain protected. Native content-hash CAS and exact readback
remain required. The existing installer's `--instructions-only` mode leaves
adapter configuration, skill assignments, native links and profile settings alone.

Acceptance requires a justified OMH save and verified reusable skill update in
one authorized finite run, followed by native retrieval/discovery in a fresh run
of the same profile. Both task returns must use the authenticated Paperclip path.
Configuration, installed instructions and isolated worker tests do not prove this
cross-run outcome.

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
| Generic credential/lease behavior | 21 passed |
| Native creation, plugin registration, finite execution, startup privacy | 34 passed |
| Real dispatch, terminal/snapshot, nested scope and logging privacy | 7 passed |
| Existing manifest and plugin-host/provider-auth compatibility | 48 passed |
| Existing gateway CLI compatibility | 14 passed |
| Generated gateway contract and profile-history checks | 4 passed |
| Total distinct native credential/compatibility qualification | 128 passed |
| Mastermind manifest/edge contract and readiness fixtures | 16 passed |
| Exact HTTPS-token and frozen metadata guard regressions | 26 passed |

The credential binding and overlay builder are restored byte-for-byte to the
qualified `7734f25d` predecessor, including its six origin regressions. Its native
runner established 128 credential and compatibility passes. The later `c99446e7`
auxiliary-worker addition was withdrawn after tracing the actual finite adapter
path. Its v10 hashes, 157 isolated passes and logs remain historical investigation
evidence; they do not qualify an included automatic learning feature or prove
OMH retention. No network, paid inference or live memory write was used in those
isolated checks.

The exact-origin repair and its six cases from head `7734f25d` are preserved.
Six new cases establish omitted/default-port equivalence and refusal when either
endpoint specifies port zero against a default-port peer. All four zero-port
cases failed on the old expression before the repair; only an omitted port now
receives the scheme default. Earlier duplicate passes are not counted.

Hosted CI exposed the standard HTTPS literal to D8's identity/topology guard.
The existing test-owned review table now pins this one token to the exact path,
complete source hash and typed token position. Fifteen regression cases preserve
missing/different postimage refusal, numeric/context/byte drift, added identities,
diff/postimage mismatch and restoration of the finding when the entry is removed.
The generic scanner and protected template assertions are unchanged.

The earlier broader compatibility run recorded 144 passes and six platform
skips. Its three `test_session_client_env.py` failures reproduced on the untouched
base in the same macOS qualification environment. An introduced finite-wrapper
typo was corrected and the actual finite-executor test now passes. An archive
version fixture was made explicit; this did not change Hermes version policy.
Qualification captured 85 existing changed/new source files. The adopted
composition changes three through the credential extension and eight through the
hygiene repair, while preserving the remaining 74 byte-for-byte. Its existing generated contracts were first reproduced exactly from the
unmodified canonical inputs, then regenerated with the extension. No installed
runtime file was changed.

The original v8 composition failed two of 14 native checks: three footgun and
thirteen Ruff findings reproduced on its installed-source preimage. That result
remains recorded in the [credential qualification](../../ops/paperclip_fleet/evidence/2026-11-10-credential-qualification.json).

The adopted v11 composition includes the existing, separately qualified
[native hygiene patch](native-baseline-hygiene.patch). It changes eight exact
captured preimages: four production files and four existing test files. It makes
the existing encoding and POSIX guards explicit to the checker, fixes BOM-prefixed
tick-lock parsing with a fresh-live-holder regression, and corrects the reported
annotation/import/unused-variable formatting. No checker rule is weakened.

All 14 native checks pass on qualified tree
`08ffdd48f5e0ed105fb628b137485073e8939b05`, including zero blocking or advisory
health findings. The combined affected run has 91 passes; 62 are the existing
credential cases, so this is not 91 additional cases. The original 25 credential
postimages are unchanged. The install composition now contains 33 source files:
29 production/generated files and four existing test files. Three qualification
credential fixtures stay in the isolated test tree. All captured preimages,
patch hashes and the preserved-source accounting are in the
[native hygiene qualification](../../ops/paperclip_fleet/evidence/2026-11-10-native-hygiene-qualification.json).
The composed patch is unapplied; live source custody and safe cutover remain required.

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
verify all 33 preimage conditions, including recorded absence for new files,
the remaining captured source bytes, and the current native gateway identity,
writer custody and active work. Apply the credential and
hygiene patches as the single hash-checked composition recorded in the v11 evidence. The recorded 04:58:56 UTC observation has nineteen active units
(nine chats, four in-process cron jobs, six managed units). All four crons are
restart-unsafe and none is marked wedged. The earlier long-running CEO execution
completed and delivered at 04:58:19 UTC and must not be replayed. Use the incumbent
lifecycle owner only after current work is safe to drain. Do not use a whole-source auto-stash/update as a file installer, hot-patch
running imports, or start a second gateway.

After the core capability is installed and read back, install/enable the plugin
through the native plugin owner and set the required-binding marker through the
Paperclip adapter's existing configuration owner. Do not enable the marker on an
old gateway. No token value belongs in either configuration.

Retry the reconciled original MAS-2 once against the changed capability. Required
acceptance remains authenticated same-issue return, a permitted runtime-tool
call, actual Capacity Fabric route/accounting evidence, OMH marker write/read,
second-run/profile isolation and representative leadership skill materialization.
Foreground OMH and skill learning also requires later fresh-run retrieval under
the same profile, with successful native admission/mutation references.
An adapter exit code, model answer, source merge or successful static test does
not establish those outcomes.
