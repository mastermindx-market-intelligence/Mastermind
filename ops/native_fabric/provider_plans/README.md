# ModelArk and Experiential plan integration

This profile adds two explicit providers to the incumbent native Fabric. It
composes over selected M2 generation `ef94479b8c768088e7c6b611d498879b9b6896ba24faa2558135ad8465f8be46`
(sequence 35), preserves all 107 original files, and adds nine source-owned
dependencies. Six existing files receive exact preimage/postimage patches.

## Request policy

| Pool / selector | Selected model | Funding boundary |
| --- | --- | --- |
| `byteplus`, default | `glm-5.3-flash` | Personal $50 coding plan |
| `byteplus --model deepseek-v4.1-flash` | Exact DeepSeek model | Same subscription windows |
| `experiential --model free` | First catalog-present free model, DeepSeek first | Exact `:free`; provider stops at allowance |
| `experiential --model uncensored` | DeepSeek Flash Uncensored first | Existing prepaid wallet/plan allowance |
| `experiential --model glm-5.3-flash-uncensored` | Exact GLM Flash Uncensored | Same paid allowance |

The five native chat free IDs are DeepSeek V4.1 Flash, DeepSeek V4.1 Flash 1017,
GPT-6 Luna, Clef and Clef Flash, all with `:free`. The existing gateway additionally
maps `jev-latest:free` to System One and `gpt-6-luna-decisions:free` to Decisions.
Those protocols are not misrepresented as chat-completion workers.

A new selection can choose an available eligible model. A request already sent
never changes model, retries, or falls through to another paid model.

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
  outcome parser, Broker `observe-provider` and pool ledger before lease release.
  Post-dispatch uncertainty remains reconciliation-required.
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
