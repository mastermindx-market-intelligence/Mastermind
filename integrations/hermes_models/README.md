# Hermes model providers (WP2)

Subordinate OpenAI-compatible provider layer for the Hermes profiles qualified
in `integrations/hermes_qualification/` (`mmsecretary`, `mmmeta`). It consumes
the existing Model Router catalog and the commercial BytePlus ModelArk contract
from PR #1824. It does not admit Executive work, claim Capacity, arm a live
route, or open a socket unless a caller injects a transport.

Upstream pin: `NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18`.

## Role chain

| Role | Profile | Order |
| --- | --- | --- |
| Meta-CEO | `mmmeta` | Z.AI `glm-5.3`, then Cursor pool |
| Secretary, watcher, implementation subagent | `mmsecretary` | ModelArk `glm-5-3-flash-260828`, then ModelArk `deepseek-v4-1-flash-261017`, then Cursor pool |
| Vision, computer-use | auxiliary on both profiles | `MiniMax-M3`, then Cursor pool |

ModelArk uses `https://ark.ap-southeast.bytepluses.com/api/v3` and realm
`byteplus-modelark-commercial`. The Personal Coding Plan `/api/coding`
endpoints are refused. Hermes `fallback_model` is not rendered, because that
feature replays 429 and 5xx. This client records backoff and does not replay.
Outage moves to the next provider only when the turn's effect is `read_only`.

Served `model` must equal the requested id. A mismatch or a missing id is a
refusal, not a failover.

## Credentials a human must provision

Provision **one** pointer per provider. Values stay in the environment or in a
regular mode-`0600` file. They are not written to this repo, argv, or logs.
If the file pointer is set, a missing or non-`0600` file does not fall back to
the env var.

| Provider | Env value | 0600 file path env |
| --- | --- | --- |
| Z.AI GLM-5.3 | `ZAI_API_KEY` | `ZAI_API_KEY_FILE` |
| BytePlus ModelArk GLM-5.3-Flash and DeepSeek Flash | `BYTEPLUS_MODELARK_API_KEY` | `BYTEPLUS_MODELARK_API_KEY_FILE` |
| MiniMax-M3 | `MINIMAX_TOKEN_PLAN_KEY` | `MINIMAX_TOKEN_PLAN_KEY_FILE` |
| Cursor pool | `CURSOR_API_KEY` | `CURSOR_API_KEY_FILE` |

`BYTEPLUS_MODELARK_API_KEY_FILE` and `ZAI_API_KEY_FILE` may be a raw one-line
token or JSON `{"api_key": "..."}`. Cursor's committed base URL is the disabled
placeholder `https://cursor-pool.invalid/v1`. A live Cursor call also needs the
non-secret endpoint name `HERMES_CURSOR_POOL_BASE_URL`.

Overlays: `profiles/mmsecretary.hermes-providers.yaml` and
`profiles/mmmeta.hermes-providers.yaml`. They are not the qualification
preflight documents.

```sh
python3 -m unittest discover -s integrations/hermes_models/tests -v
```
