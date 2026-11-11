# Hermes gateway compatibility required by Paperclip

Status: implemented and qualified source candidate; live activation and consumer
acceptance remain open. The original Product task exposed a concrete gap:
Hermes received nonsecret Paperclip context and executed real tools, but its
ordinary client-env filter removed the temporary API and runtime-tool tokens.
The filter must remain intact.

## Implementation and owners

The candidate is maintained at
[integrations/paperclip_hermes](../../integrations/paperclip_hermes/README.md).
Its builder renders a generic native extension against explicit source
preimages; the Paperclip-specific plugin declares exact run context, issuer
claims, expiry and credential destinations. Plugin registration contains no
credential values and uses the existing per-profile plugin manager.

The private create parameter `launch_credentials_v1` is accepted only with
`finite-launch-credentials-v1` advertised by the gateway. The local creation
owner consumes it before policy and receipt projection. Existing private
launch-key custody and staged publication hold the values; durable policy
contains public fingerprints, expiry and context/declaration digests.

The finite executor binds profile, principal, session, instance, owner epoch,
admission and generation. Existing local terminal dispatch supplies the
credentials only inside a live tool scope. Native code-cell RPC may reuse its
active outer dispatch; persistent code kernels receive no token environment.
Unsupported remote/managed/background/delegated credential execution refuses.
No managed-worker transport is claimed in this first release.

The incumbent SecretSource interface receives only configuration and home;
its per-home fetch/cache cannot carry private client-run values or retire them
with one admission. No second secret store, relay, memory provider or scheduler
is introduced.

## Privacy and startup

Enabled manifest metadata is read before plugin implementations can start a
host. The first real ambient lookup freezes a metadata-only launch witness:
native launch-home identity, binding, plugin owner/spec digest and exact secret
names. Origin, marker or manifest drift refuses before another process starts.
Removal follows the launch profile through native routing, not a child-profile
override, and occurs before and after profile overlays. Native provider,
ambient-provider and internal-runtime filtering remains in force.

Private values are excluded from prompts, ordinary client_env, static config,
plugin-host/daemon environments, policies, receipts and shell snapshots.
Redaction occurs before tool observers/middleware, canonical history/events,
spill paths and logging, independently of the optional display toggle.
Malformed private validation and pre-binding WebSocket logs do not echo payloads.
Paperclip remains the token verifier and issuer-side expiry/revocation owner.
The API JWT's 48-hour default is supported; the optional one-hour runtime token
expires independently and cannot reappear from a copied context. The producer's
persistent agent-identity private key is withheld from both launch payload and
child seeds. This does not implement identity signing. Both forwarded and
withheld names respect incumbent credential ownership. Origin-scoped metadata
validation refuses reentrant child startup instead of skipping validation.

## Evidence

Baseline PR #2399 merged at
`dee7a38a1e184e38cdcdd75889223d5b0ec27414`. The exact merged helper is installed;
all 13 adapter configurations now read back quiet=true. The approved isolated
workspace flag and original MAS-2 strategy were applied through their native
owners. The previous approval boundary is resolved.

Original live run `c54dc873-bb58-465e-801b-98c352cf9e5b` reached glm-5.3,
skill_view and terminal. Its API attempt lacked credentials and was refused
before effect. The run was cancelled natively and the Hermes admission/session
are terminal. Configured provider names and memory-recall logs do not prove the
required Capacity Fabric receipt or memory marker.

Hermes qualification starts at
`ba4ddf9945a213ede9dda016602a86591ed634f9` and carries the actual installed
source's 85 changed/new files. The native PM and `scripts/run_tests.sh` produced
128 passes: 62 credential tests plus 66 existing plugin, CLI and contract
checks. The origin repair preserves explicit port zero instead of treating it as
an omitted default; all four negative regressions failed on the old code.
All 16 Mastermind Paperclip contract/readiness fixtures and 26 exact-token and
metadata guard regressions pass separately. The existing hash/token-bound D8
review mechanism recognizes only the reviewed HTTPS literal and observed metadata
sites; scanner policy is unchanged.

The later auxiliary-review investigation was withdrawn after checking the actual
finite chat -q producer, which suppresses automatic background review. Runtime
bytes are restored to this 128-case credential candidate; the
[learning investigation and corrected disposition](evidence/2026-11-10-learning-qualification.json)
is historical evidence, not a different install target or proof of automatic
Paperclip learning. Foreground OMH save/recall and native skill_manage remain the
existing learning owners.

The historical v8 source check was 12/14, with three footgun and thirteen Ruff
findings reproduced on its installed baseline. The existing eight-file hygiene
repair is now adopted into the exact credential composition: all 14 native checks
pass on qualified tree `08ffdd48f5e0ed105fb628b137485073e8939b05`, with zero blocking
or advisory health findings. The affected native run has 91 passes, including
62 already counted credential cases. No checker rule or release hold is waived.

The original 25 credential postimages remain unchanged. The composed installation
has 33 files, including four existing test files; the separate three credential
qualification fixtures are not installation targets. Its eight hygiene preimages,
postimages, patch identity and preserved-source accounting are recorded in
[native hygiene qualification](evidence/2026-11-10-native-hygiene-qualification.json).
The [original qualification](evidence/2026-11-10-credential-qualification.json)
retains the historical baseline failures. The new composition is still unapplied;
current writer custody, safe cutover and protected source delivery remain required.

## Installed-source composition and release

The installed tree contains other owners' tracked and untracked changes.
A distinct composition artifact records exact preimages/postimages and carries
those changes into qualification. The builder is not an installer. Do not
overwrite, reset, stash or silently release unrelated changes.

Fresh native active-work evidence supersedes stale PID observations. At
04:58:56 UTC the gateway had nineteen active work units: nine chats, four
in-process cron jobs and six managed units. All four crons were restart-unsafe
and none was wedged. The earlier CEO execution completed/delivered at 04:58:19
UTC. Native restart waiting is not quiescence proof. There is no unconditional non-interrupting deferred
patch/restart owner. Preserve current work and use the existing source custody,
drain and guarded restart owners only when the finite cutover is ready.

## Remaining actual-path acceptance

After safe activation, require running capability readback and the enabled
plugin before setting `HERMES_REQUIRED_LAUNCH_BINDING=paperclip-run` on the
existing Paperclip adapter. No token values go in configuration.

Retry original MAS-2 once against the changed capability. Require authenticated
same-issue return, a permitted runtime-tool call, actual Capacity Fabric route
and accounting evidence, OMH marker write/read, a second run/profile and
representative leadership skill materialization. Preserve the original task's
scope and final disposition. Source merge, CLI success, tests and model output
are separate from fleet acceptance.
