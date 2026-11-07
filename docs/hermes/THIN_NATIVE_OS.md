# Thin native Hermes in Mastermind OS

## Scope and source
Chairman-directed continuation of `meta-ceo-open-harness-convergence-20261024-sol-001`.
Source operation: `hermes-thin-os-integration-20261106-c1-01`; base/procedure
`609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1`.
Recovery: https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6693932749.

**Outcome:** a signed-in native Mastermind OS user can connect to the same operating-system
user's already-running Hermes gateway, start a text conversation, submit once, reopen
native history, and inspect the original admission. This first release must not depend on
finishing the advanced Linux/Executive/Fabric stack. The remote web app is not a local
operator and gets no loopback proxy or credential. Native-first is a release slice, not
completion of the remote or always-on company-orchestration outcome.

## Architecture ruling
Use the actual `hermes-gateway-v1` session authority, not the unauthenticated dashboard.
Hermes owns sessions, admissions, event replay and execution. The native OS host owns
signed-in visibility and same-user attachment; a small replaceable adapter projects only
bounded conversation data. The UI consumes a versioned `mastermind.hermes_native_view.v1`
port. Later qualified role gateways can implement that same port. Neither advertised
capabilities nor chat text grant Executive/Capacity/Fabric authority.

The adapter is embedded in the Tauri binary and executes once per operation using the
existing Hermes Python environment. It uses the upstream private control client and an
explicit already-discovered endpoint; it never calls ensure/start/restart. It creates no
listener, database, task queue, retry engine, credential store or provider client. Private
session tickets never cross into the renderer or logs. In this first port, newly created
sessions request an empty toolset, disable hooks and preserve the existing model route.
Installed Hermes also exposes its existing read-only Capacity MCP through three scoped
discovery wrappers. The adapter qualifies that exact installed bridge and scope before
allowing sends, and the UI explicitly labels CAPACITY_READ_ONLY. Unqualified tool scopes
remain read-only. It does not grant the local agent company execution tools. Native user requests remain
exact, and the served model is not inferred from a configured model label.

Only status/list/create/read/send/receipt are exposed. No arbitrary RPC, endpoint, profile,
model, key, cwd, shell, role grant, approval, cancellation or restart arguments. Role labels
are conversation purposes, not two installed role authorities. Host auth generation is
checked before invocation and before releasing its result. Sign-out discards pending UI
results. Unexpected modifying outcomes remain unknown and are never automatically replayed.

## Verified input, not product acceptance
M2 upstream is clean at `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` (0.23.0).
Actual private identify answered runtime protocol 1, ready, session-authority-v1,
durable-admission-v1 and event-replay-v1. The gateway is distinct from dashboard9119.
The installed Capacity MCP only catalogs and previews; native worker dispatch is not enabled.
Preserve #2134 C35 unpublished C64/C65 and original effects, #2147 and all H24 owned paths.
The original new-workspace acquisition returned uncertain, then its same-carrier status
and exact worktree record proved the clean pinned branch; no second acquisition occurred.
A read-only Fabric child `hermes-thin-os-map-20261106-c1-01` was refused before launch
(EXECUTION_NOT_ELIGIBLE, controller exit75, no result). No replay/native child substitution.
Direct bounded implementation uses NO_ELIGIBLE_PRE_EFFECT_WORKER; principal retains acceptance.

## Task tree and acceptance
- THIN-1: native transport and projection. Closed requests, compatible live identity,
  bounded history, no secrets/authority fields, genuine refusal versus unknown effects,
  and no ensure/retry. Python contract/negative tests plus a real native canary using the qualified limited scope.
- THIN-2 (depends THIN-1): authenticated native host command and Office component.
  Scope generation/expiry tests, text preservation, accessible empty/loading/error states,
  original-admission status, read-only recovery, no automatic duplicate sends. Browser-only
  build has no local connection. Keep remote/advanced configuration independent.
- THIN-3 (depends THIN-2): focused tests, actual native compilation, protected publication,
  signed-in native user roundtrip and reconnect. No deployment/always-on claim before proof.
- ADV-1 (after THIN-3): compose accepted #2134/#2147/H24 capabilities through existing
  Executive/Capacity/Fabric/Agent OS contracts; no migration of native history by title.
- ADV-2: authenticated remote-host adapter, genuine role enrollment and event-driven
  Secretary/Meta-CEO continuity; actual start/result/parent-consumption and recovery proof.

## Required review cases
Wrong/missing native identity; missing protocol/capability; credential-bearing or remote
origin; extra caller authority; malformed/oversized frame; another session's receipt;
logout during IO; timeout after send; malformed history; no-tool baseline; upgrade mismatch.

## Progress
THIN-1 and THIN-2 are implemented as candidates. A real native create/send/receipt/read
roundtrip succeeded on M2. THIN-3 is not complete: source qualification, current-base
composition, actual signed-in packaged-app proof and protected release remain outstanding.
No remote, always-on company orchestration, paid-pool inference or Fabric dispatch is claimed.

## Crash recovery and continuation capsule

Recorded after the previous long implementation turn ended in `Thinking failed`.
This is a continuity boundary, not product acceptance. No failure cause beyond the
observed terminal generation failure is established. Recovery only reconciles and
persists existing work; no new native canary or delegated worker was submitted.

- Classification: CHECKPOINTED_CONTINUATION after verified source publication/readback;
  otherwise NOT_CANONICALLY_PERSISTED. MISSION_COMPLETE: false.
- Runtime/source operation and branch remain those above. The original acquired M2
  workspace is `/Volumes/Mastermind 2/agent-workspaces/web/hermes-thin-os-integration-20261106-c1-01`.
- Recovery procedure pin: `e63d8acaebe0d3cee1ce7cfb8d85294bf0c57f46`.
  INDEX and session reliability were read at that pin; changed AGENTS and delivery
  rules were inspected. The previous core skill/review/continuity blobs are unchanged.
- Protected movement overlaps the three existing mount files `auth.rs`, `main.rs` and
  `MetaCeoOffice.tsx`. This checkpoint does not compose or overwrite that newer work.
- The final interrupted action only read test source. It had no requested source or
  runtime mutation. This branch has no previous commit/push attempt to replay.
- PLAN_NOT_ORG_LINKED: the owning GitHub plan and source checkpoint are the continuity
  record. No Macro Agent OS, Linear status or protected organizational acceptance was
  changed or fabricated during this recovery.

### Actual retained verification

All test statements below are recovered original observations, not freshly rerun results.
Commands are relative to the original operation workspace unless specified otherwise.

| Verification | Actual result | Retained evidence |
|---|---|---|
| `python3 -m unittest discover -s tests -p test_hermes_native_os_bridge.py` | 16 passed | `/tmp/hermes-thin-send-contract-green-c1.log` |
| `cd app/mastermind_os && npm test -- --run src/hermes-native` | 12 passed | `/tmp/hermes-thin-ui-mounted-c1.log` |
| `cd app/mastermind_os && npm run build` | Passed; large-bundle and ineffective dynamic import warnings remain | `/tmp/hermes-thin-ui-build-c1.log` |
| `cd app/mastermind_os/src-tauri && MM_SOURCE_REVISION=609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1 MM_BUILD_IDENTITY=hermes-thin-c1-development-uncommitted cargo test --no-default-features` | 251 passed, 7 ignored across three binaries | `/tmp/hermes-thin-native-all-tests-c1.log` |
| `cd app/mastermind_os && npm test -- --run src/hermes-native src/meta-ceo` | 223 passed, 18 skipped; one failed suite | `/tmp/hermes-thin-office-tests-c1.log` |

The failed suite is `src/meta-ceo/mission-result-producer.test.ts`, committed-producer
replay. The file exists on disk, but `new URL(..., import.meta.url).pathname` leaves the
SSD space encoded as `%20`, causing ENOENT. Do not weaken the producer evidence check or
substitute fixtures. Next repair uses correct URL-to-file-path conversion and a path-with-
spaces regression, then reruns the affected suites. This defect is not yet repaired.
The full React repository suite was not run; no all-green claim is made.

### Original native result: do not recreate or resubmit

- Upstream runtime observed: `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`, protocol1,
  version0.23.0. No installed-runtime upgrade or restart was performed.
- Original session: `local-e8fb5ddbfda77657928449650b999e04e92db3e025422c6e3a9b0b662120dd6a`.
- Create request: `943d3e2ee6ea504cb3f38e78ca80297b`.
- Send request: `92e84d97bb2b5ec38377f1f217754b2f`.
- Admission: `bf54819d587c4d369536179f532c77ee`, sequence6, terminal,
  outcome `completed`, execution generation1.
- User input: `Reply exactly MASTERMIND_NATIVE_CANARY_OK. Do not call tools.`
- Recovered assistant text: `MASTERMIND_NATIVE_CANARY_OK`.
- The same-session read returned two messages, no pending admission, not running.
- Retained receipt: `/tmp/hermes-thin-os-canary-recovery-20261106-c1-01.json`, SHA256
  `4045491b7728e703d495d85328b20745b1ff11c4d5b9aaff964ac763ff2dd086`.
- Tested bridge SHA256: `e42fccd302ef7efb08e99b74b3fa30e19ba2718738f7d4b05d8f6189672510c0`.
  The displayed `qwen3:14b` is configured-model metadata, not served-model attestation.

Initial attempts failed before native admission: missing local dependency import,
then native invalid-parameter checks. The concrete repairs selected the incumbent
committed dependency generation, preserved the installed model route rather than a
safe-mode model-less request, and removed an unsupported surface/unattended flag.
The accepted original admission above is settled; do not replay earlier requests.

### Unfinished acceptance and exact next action

The next assigned fresh Pro session takes this same branch/workspace and checkpoint;
no old-chat ACK or new project is needed. First reconcile the current source head and
live-writer facts, then repair the fixture path conversion with a regression test.
Compose only actual overlaps with protected source, preserving merged Hermes work.
Review the native host/adapter boundary and test auth invalidation during IO, native
identity/dependency drift and unknown effects across component unmount/reopen. The current
UI holds uncertainty in component state only; durable/reopened recovery must be qualified
before claiming duplicate-safe reconnect. Verify the effective upstream tool scope and
no silent authority enlargement. No automatic retry or permission weakening.

Then run affected React and Rust suites and the full available app suite, publish the
qualified successor on this same carrier, consume required hosted CI and follow the
normal protected release path. Real signed-in packaged-app roundtrip, logout/reconnect,
upgrade behavior and role journeys remain owed. Native adapter canary is not app acceptance.
Remote web access and advanced role/Fabric/Capacity integration remain ADV-1/ADV-2.
The initial native slice is not a completed always-on CEO or Secretary service.

DO_NOT_REDO: upstream install, working private-socket discovery, completed synthetic native
turn, fulfilled dependency selection proof, acquired source workspace, or accepted sibling
work. No automatic worker/observer is running for this continuation; foreground recovery
needs one fresh same-mode conversation because this long chat already failed.

### Owned code/test bytes retained for publication

SHA256 of the sorted lines below: `62616c1025a88db6805648e8adb8978079a5db472e67b92a278fcd8aaaf6afbf`.

```text
c1249971c863234312c05e789d82c845f4f46793167583128f65e2c970be3c9b  app/mastermind_os/src-tauri/src/auth.rs
ed4ddf8b16614f7d03525fc68edac0ce6ea7e7834ca699a7d4650d1c0d372760  app/mastermind_os/src-tauri/src/auth/hermes_native.rs
e42fccd302ef7efb08e99b74b3fa30e19ba2718738f7d4b05d8f6189672510c0  app/mastermind_os/src-tauri/src/hermes_native/bridge.py
81580bb39c8697909572c0ae5e20691b22bb94b17529d524f0326a29b3a18b6d  app/mastermind_os/src-tauri/src/hermes_native/core.rs
a6ab00255adb7f19dbfe10eba842244b6b5b00aba2141870cf774d06c166bba2  app/mastermind_os/src-tauri/src/main.rs
1b65bcb747e057be22cf723a7aa59a63c0b0fe82ca3bb1585a13580b8602a62f  app/mastermind_os/src/hermes-native/HermesNativePanel.test.tsx
a1f9c61c1ec4e00900627709b17b90a72f412bda6de94b87d8adccf6def98249  app/mastermind_os/src/hermes-native/HermesNativePanel.tsx
47f596ec6d80e889454cc77b509a34da9848e473b74599abfc9487dda3025f16  app/mastermind_os/src/hermes-native/contract.test.ts
b949549427a3b17105f61621e406b5bc1f114b92c2323197162d4a21da0b1e6f  app/mastermind_os/src/hermes-native/contract.ts
90d3fedd6b8292691f6566a4544df30ba5ddae3436b2594b1581617869b71577  app/mastermind_os/src/hermes-native/native-panel.css
5eb523587b511afbdb8ee626f9f410ece13a348b09cf22e2575e6752859670aa  app/mastermind_os/src/hermes-native/native-port.ts
0653885afca18191ae2be8f5d9cd56556ffff6fce7caf2ab600feff1dd8ce72d  app/mastermind_os/src/meta-ceo/MetaCeoOffice.tsx
ce8793e256db8a9a424074dcd1b7e57c42aa2ee8e35b787b153fc83b3fbecd4f  tests/test_hermes_native_os_bridge.py
```
