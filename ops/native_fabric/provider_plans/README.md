# ModelArk and Experiential plan integration

This successor connects the two enrolled plans to ordinary eligible AUTO
requests as well as explicit native selections. It composes over selected M2
generation `205b8321c22858b568fe37b7f11b861ee9aeed9c6615bd47847d986b14dfea08` (sequence 36),
preserves the complete 116-file predecessor, and changes the existing picker,
request adapter, local controller, slot and provider worker. The original
publisher owns selection.

## Request policy

| Pool / selector | Selected model | Funding boundary |
| --- | --- | --- |
| `byteplus`, default | `glm-5.3-flash` | Personal $50 coding plan |
| `byteplus --model deepseek-v4.1-flash` | Exact DeepSeek model | Same subscription windows |
| `experiential --model free` | First catalog-present free model, DeepSeek first | Exact `:free`; provider stops at allowance |
| `experiential --model uncensored` | DeepSeek Flash Uncensored first | Existing prepaid wallet/plan allowance |
| `experiential --model glm-5.3-flash-uncensored` | Exact GLM Flash Uncensored | Same paid allowance |

All seven screenshot free models have native Fabric paths. DeepSeek V4.1 Flash,
DeepSeek V4.1 Flash 1017, GPT-6 Luna, Clef and Clef Flash use Chat Completions,
all with `:free`. Explicit `jev-latest:free` uses System One and
`gpt-6-luna-decisions:free` uses Decisions through the same bridge, account,
leases and result path. The default `free` selector chooses a chat model;
typed decision models require an explicit model and JSON packet.

A Jev packet contains `state` and a `questions` object, for example:

```json
{"state":"The list contains apple and pear.","questions":{"has_apple":{"type":"noul","instructions":"The list contains apple."}}}
```

A Luna Decisions packet contains `input` and a `questions` array:

```json
{"input":"The list contains apple and pear.","questions":[{"name":"has_apple","type":"predicate","instructions":"The list contains apple."}]}
```

Both accept bounded choice/score questions as documented by their providers.
Fabric returns the validated typed answer JSON; it never performs an action
chosen by a model. Native decision calls have no chat token-limit field,
streaming or idempotency header. The ordinary one-send reservation remains.
Malformed question/answer identities and substituted protocols fail closed.

A new selection can choose an available eligible model. A request already sent
never changes model, retries, or falls through to another paid model.

## Ordinary automatic selection

An unpinned fabric_task.py request can select an enrolled plan for bounded
C0/C1 work. Consent-qualified, response-only free chat work considers
Experiential first; supported coding work considers BytePlus. The existing
selector continues through its ordinary providers when those candidates are
ineligible or unavailable. A preference for another pool retains its existing
selection behavior.

Experiential AUTO requires --experiential-response-only,
--experiential-retention-acknowledged and
--experiential-sensitive-data-opt-in. Proprietary code additionally requires
the existing code-exposure opt-in. Response-only means the task can be completed
solely from its supplied packet; this transport does not inspect or edit a
workspace. Ordinary callers without these facts can use BytePlus for qualified
coding work. Paid Uncensored and typed Jev/Decisions selection remain explicit.

The request keeps its original cwd and task facts. The launch seals the selected
pool/model and the resolved local cwd, including the ordinary tilde directory
contract. The send boundary rechecks both. The existing shared-active binding
is verified before its real read-only occupancy observation. Host load/disk,
physical holds, quality floor, cooldowns and shared account caps remain binding.

This local AUTO path excludes operator children and unsupported commission
deadlines, artifact/native-return, new-worktree and CPU-scope contracts. Those
requests retain ordinary compatible routing. No selection change occurs after
a possible send.

## Original owners

- Existing `fabric_task.request` owns the original run and retained packet.
- Existing `slot.py` now acquires a physical `LaneLease` for these two local pools,
  then its normal provider flock, Broker lease, heartbeat and child supervisor.
- Existing `accounts.yaml` owns account registration and operator concurrency.
- The new-provider validation adapter reads the exact original Broker account,
  pool, model, root, state and expiry. The separately sealed GLM helper remains
  byte-identical.
- The one-shot send reserves the original `.task-cli-started.json` artifact.
  A restart cannot send that run again.
- `native_plan_worker.py` composes the existing owned-process receipt, provider
  outcome parser and Broker `observe-provider`. After the slot returns, the
  existing local controller retains `lanes/<run>.remote.stdout`, verifies the
  raw provider frame, process cleanup, quota observation and released custody,
  then publishes one strict terminal ledger row under the original run/root.
- Actual slot refusals before provider acquisition retain a bound phase witness.
  A generic exit code without that witness never invents no-send proof.
  `LOCAL_RETURNED` is settling; `DONE` follows durable ledger acknowledgement.
  Post-dispatch uncertainty remains reconciliation-required, and duplicate
  captures cannot append a new refusal over an earlier completed run.
- Existing `native_generation.py` owns publication and CAS selection.

M2's enrollment adds only `byteplus` and `experiential` to
`local_only_engines`. Its physical ceiling of 2, load gate, disk gate and
seat role remain in force. These initial provider registrations have an operator
concurrency cap of 1 each. This cap is not a claim about provider entitlements.

## Credentials and service

ModelArk uses the existing private provider-home installer/reader, a distinct
Claude configuration home, and the supported Claude Code harness. Its sole base
is `https://ark.ap-southeast.bytepluses.com/api/coding`. Commercial PAYG endpoints,
native-login fallback and inherited alternative authentication are excluded.

Experiential uses the existing gateway, bound to `127.0.0.1:8311`. Its provider key
stays in a private gateway environment file; workers receive only the separate
local proxy token. The service entrypoint parses that file without shell eval.
The gateway requires its policy digest and permits only the requested free IDs
and the two Flash Uncensored IDs in plan mode. Unsafe nested retry/fallback
controls are refused.

## Quotas

ModelArk's five-hour, weekly and subscription-month windows share one
`quota_scope` per subscription. Unknown management telemetry stays UNKNOWN;
bounded supported-tool requests remain provider-enforced. Known exhausted
windows and the incumbent cooldown circuit deny admission. Management readbacks
from authenticated Ark CLI can update the existing projection. A separate API key
does not establish a separate subscription.

Experiential's 7,000 free credits/day and $200/month are configured, Chairman-
declared entitlements. They are never reported as observed remaining balances.
The `:free` contract enforces zero wallet spill. Paid requests require an observed
positive wallet balance and remain within the existing provider's prepaid
funding boundary. No provisioning key, top-up, auto-recharge or second local
billing ledger is required or created.

## Compose and publish

`compose.py --base <verified-native-release> --output <new-private-stage>`
checks every original file, patch and canonical dependency. It has no publication
or selection capability. Publish the resulting FILES.json with the original
publisher, then select with its exact-current-generation CAS after normal
protected source delivery. Never replace another writer's pointer or active run.

See the source-linked integration report for the actual installation and
real-path receipt state; this README does not itself claim live acceptance.
