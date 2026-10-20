# Claude Fabric enrollment - first-account operator gate

Status: PRE-LOGIN PREPARATION. No Claude native worker realm is claimed active by this document.
Source authority: protected docs/sol_skills/INDEX.md at fd1159695b0491a1b2c8d3042dce1232ad8365b4; approved provider-auth compatibility amendment and OCR-1 V3 plan.

## Scope and retained identities

- Enrollment target: one Claude Code **native subscription** worker realm, not an already-open Parallels Claude.app profile.
- Preserve existing Claude 3/5/6/8 applications and their support directories. Never launch, quit, move, log out or relink these apps for this task.
- Do not repurpose standalone `/Users/chriswong/.local/bin/claude` as evidence for an embedded Parallels account.
- Preserve `claude` (principal seat; aliases fable/claude-fable) versus `claude-native` (operator/reviewer) as separate routes.
- No tokens, Keychain payloads, provider-account emails, raw `auth status` output or account UUIDs enter repository, Slack, Executive events, notes or model context.
- Never substitute `CLAUDE_CONFIG_DIR` for native macOS OS-principal/Keychain isolation. No `claude setup-token`, `CLAUDE_CODE_OAUTH_TOKEN`, API key or unreviewed provider gateway.

## Safe preparation (operator-owned, before asking Chairman to authenticate)

1. Verify the installed Claude binary version/path and installed source release with non-credential metadata. Do not modify the default Claude application or invoke a model turn.
2. Resolve existing host_ref, dedicated native worker OS principal, provider-binary attestation and worker execution environment from their canonical owners. If missing, report the exact unfulfilled identity seam and prepare it through those owners; do not invent hashes or refs.
3. Use the canonical `ops/executive_os/claude-worker-preflight.py` and `ops/executive_os/claude-realm-set-verify.py`, not a new login/preflight command. CLI probing is limited to allowlisted `--version` and `auth status` in the **same reviewed worker environment** used later by the worker.
4. Validate the worker context refuses higher-precedence keys, cloud/gateway/provider profile selection, mismatched user or non-native auth; the preflight must fail closed if unable to demonstrate the actual worker context.
5. Determine first selected realm label, exact host and OS principal, verified path/binary, and native login command in that principal. Prepare a restricted authenticated human interactive shell for login; do not open GUI Claude.app.
6. Before asking the Chairman to log in, show a **single explicit manual command** for the already-isolated worker principal, identify which intended paid subscription to select, and state that the interactive provider sign-in must be completed by the human. Never paste secrets or raw auth metadata into chat.

## Chairman attended gate - do only when steps 1-6 pass

A. In the verified dedicated native worker-principal terminal, execute `claude auth login` using its reviewed binary. Complete the native subscription browser sign-in yourself. Do not use `setup-token`, API keys or a Parallels app profile.
B. Tell the operator only **"login completed"** (or describe a failure) and which opaque subscription slot you intended; never provide the credential, account email, login URL or Keychain item.
C. Operator runs the single canonical non-secret worker-context preflight and checks the closed receipt: `WORKER_CONTEXT_AUTH_READY`, `claudeai`, `first_party`, matching accepted host/principal, execution-context Worker Broker, binary and intended slot. Stop and diagnose any failure without switching auth method.
D. Only after the fresh preflight and distinct-realm-set verifier, qualify the source-owned provider capacity, native broker enrollment, approved host placement and one bounded original-parent model canary. Read back capacity selection and retained result; this is not granted by login success alone.
E. Repeat A-D one realm at a time. Confirm distinct OS-principal/credential realms and quota ownership before counting pooled concurrency. Never infer five or four usable subscriptions from GUI app count.
F. Follow the existing protected merge/release and attestation path before labeling any route production-ready. Do not edit a sealed live Fabric release in place.

## Exact-model optional delegation

- Keep auto selection the default. An explicit model request is an **exact allowed-model constraint**, not permission to bypass role, subscription, quota, capacity, host, plan provenance or review independence.
- Existing draft PR #1365 is the active selector source carrier. Reconcile that candidate's owner, head and release with existing installed Fabric before promotion; do not ship a parallel selector or copy a patch into a live immutable release.
- Principal-level Astra/Fable auditors are not interchangeable with leaf workers. First establish a supported principal/reviewer route and independent-review constraints; if unavailable, refuse the pinned model rather than silently substituting a different one.
- Model selection and account selection are separate: account is authorized by the provider realm/capacity owner, never raw `--model` or a user's host hint.

## Proof and closeout

Source tests: `python3 -m pytest tests/test_claude_worker_preflight.py tests/test_claude_realm_set_verify.py -q`. Passing tests prove the closed preflight contract, not enrolled accounts.
Live acceptance: a fresh worker-context auth receipt + realm-set distinctness + broker-enabled provider + admitted bounded original-parent worker result + accepted release/protected checks. Absent any one, report BUILT_NOT_PROVEN.
